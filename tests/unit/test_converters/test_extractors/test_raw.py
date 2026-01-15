# SPDX-License-Identifier: LGPL-3.0-or-later
import unittest
import tempfile
import tarfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from hyper2kvm.converters.extractors.raw import (
    normalize_tar_name,
    unique_path,
    short_hash,
    ensure_no_symlink_components,
    ExtractPolicy,
    ExtractResult,
    safe_extract_one,
    RAW,
)


class TestNormalizeTarName(unittest.TestCase):
    """Test tar path normalization and security checks."""

    def test_simple_name(self):
        """Test normalization of simple filename."""
        self.assertEqual(normalize_tar_name("file.txt"), "file.txt")

    def test_removes_leading_dotslash(self):
        """Test removal of leading ./"""
        self.assertEqual(normalize_tar_name("./file.txt"), "file.txt")
        self.assertEqual(normalize_tar_name("././file.txt"), "file.txt")

    def test_normalizes_backslashes(self):
        """Test backslash to forward slash conversion."""
        self.assertEqual(normalize_tar_name("dir\\file.txt"), "dir/file.txt")

    def test_blocks_absolute_paths(self):
        """Test blocking of absolute paths."""
        with self.assertRaises(RuntimeError) as cm:
            normalize_tar_name("/etc/passwd")
        self.assertIn("absolute path", str(cm.exception))

    def test_blocks_windows_absolute_paths(self):
        """Test blocking of Windows absolute paths."""
        with self.assertRaises(RuntimeError):
            normalize_tar_name("C:\\Windows\\System32")

    def test_blocks_parent_directory_traversal(self):
        """Test blocking of .. path traversal."""
        with self.assertRaises(RuntimeError) as cm:
            normalize_tar_name("../../etc/passwd")
        self.assertIn("..", str(cm.exception))

        with self.assertRaises(RuntimeError):
            normalize_tar_name("foo/../bar")

    def test_blocks_null_bytes(self):
        """Test blocking of NUL bytes in paths."""
        with self.assertRaises(RuntimeError) as cm:
            normalize_tar_name("file\x00.txt")
        self.assertIn("NUL byte", str(cm.exception))

    def test_blocks_empty_name(self):
        """Test blocking of empty filenames."""
        with self.assertRaises(RuntimeError):
            normalize_tar_name("")
        with self.assertRaises(RuntimeError):
            normalize_tar_name("./")

    def test_nested_path(self):
        """Test normalization of nested paths."""
        self.assertEqual(normalize_tar_name("dir/subdir/file.txt"), "dir/subdir/file.txt")


class TestUniquePath(unittest.TestCase):
    """Test unique path generation."""

    def test_returns_same_path_if_not_exists(self):
        """Test that non-existing path is returned as-is."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "nonexistent.txt"
            self.assertEqual(unique_path(p), p)

    def test_generates_unique_name_if_exists(self):
        """Test unique name generation for existing file."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "file.txt"
            p.write_text("content")

            unique = unique_path(p)
            self.assertEqual(unique, Path(td) / "file (1).txt")
            self.assertFalse(unique.exists())

    def test_increments_counter(self):
        """Test counter incrementation for multiple collisions."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "file.txt"
            base.write_text("0")
            (Path(td) / "file (1).txt").write_text("1")
            (Path(td) / "file (2).txt").write_text("2")

            unique = unique_path(base)
            self.assertEqual(unique, Path(td) / "file (3).txt")


class TestShortHash(unittest.TestCase):
    """Test hash generation utility."""

    def test_generates_consistent_hash(self):
        """Test that same input produces same hash."""
        h1 = short_hash("test", n=10)
        h2 = short_hash("test", n=10)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 10)

    def test_different_inputs_different_hashes(self):
        """Test that different inputs produce different hashes."""
        h1 = short_hash("test1")
        h2 = short_hash("test2")
        self.assertNotEqual(h1, h2)


class TestEnsureNoSymlinkComponents(unittest.TestCase):
    """Test symlink security checks."""

    def test_accepts_regular_path(self):
        """Test that regular paths are accepted."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            target = base / "subdir" / "file.txt"
            target.parent.mkdir(parents=True)

            # Should not raise
            ensure_no_symlink_components(base, target.parent)

    def test_blocks_symlink_in_path(self):
        """Test blocking of symlink in path components."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            real_dir = base / "real"
            real_dir.mkdir()

            symlink = base / "link"
            symlink.symlink_to(real_dir)

            target = symlink / "file.txt"

            with self.assertRaises(RuntimeError) as cm:
                ensure_no_symlink_components(base, target)
            self.assertIn("symlink", str(cm.exception).lower())

    def test_blocks_path_escape(self):
        """Test blocking of paths that escape base."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "base"
            base.mkdir()
            outside = Path(td) / "outside"
            outside.mkdir()

            with self.assertRaises(RuntimeError) as cm:
                ensure_no_symlink_components(base, outside)
            self.assertIn("escape", str(cm.exception).lower())


class TestExtractPolicy(unittest.TestCase):
    """Test extract policy configuration."""

    def test_default_policy(self):
        """Test default policy values."""
        policy = ExtractPolicy()
        self.assertTrue(policy.skip_special)
        self.assertTrue(policy.preserve_permissions)
        self.assertFalse(policy.preserve_timestamps)
        self.assertFalse(policy.overwrite)
        self.assertEqual(policy.max_manifest_bytes, 5 * 1024 * 1024)


class TestSafeExtractOne(unittest.TestCase):
    """Test safe tar extraction with security checks."""

    def setUp(self):
        self.logger = Mock()

    def test_extracts_regular_file(self):
        """Test extraction of regular file from tar."""
        with tempfile.TemporaryDirectory() as td:
            tar_path = Path(td) / "test.tar"
            out_dir = Path(td) / "out"
            out_dir.mkdir()

            # Create a tar with a regular file
            content = b"test content"
            with tarfile.open(tar_path, "w") as tar:
                import io
                info = tarfile.TarInfo("test.txt")
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))

            # Extract it
            with tarfile.open(tar_path, "r") as tar:
                member = tar.getmembers()[0]
                policy = ExtractPolicy()
                result = safe_extract_one(self.logger, tar, member, out_dir, policy=policy)

            self.assertEqual(result.extracted_bytes, len(content))
            self.assertIsNotNone(result.extracted_path)
            self.assertEqual(result.extracted_path.read_bytes(), content)

    def test_skips_special_file(self):
        """Test skipping of special files when policy says so."""
        with tempfile.TemporaryDirectory() as td:
            tar_path = Path(td) / "test.tar"
            out_dir = Path(td) / "out"
            out_dir.mkdir()

            # Create a tar with a symlink
            with tarfile.open(tar_path, "w") as tar:
                info = tarfile.TarInfo("link")
                info.type = tarfile.SYMTYPE
                info.linkname = "target"
                tar.addfile(info)

            # Extract with skip_special=True
            with tarfile.open(tar_path, "r") as tar:
                member = tar.getmembers()[0]
                policy = ExtractPolicy(skip_special=True)
                result = safe_extract_one(self.logger, tar, member, out_dir, policy=policy)

            self.assertEqual(result.reason, "skipped_special")
            self.assertIsNone(result.extracted_path)

    def test_enforces_max_total_bytes(self):
        """Test enforcement of max_total_bytes limit."""
        with tempfile.TemporaryDirectory() as td:
            tar_path = Path(td) / "test.tar"
            out_dir = Path(td) / "out"
            out_dir.mkdir()

            # Create a tar with a file larger than limit
            content = b"x" * 1000
            with tarfile.open(tar_path, "w") as tar:
                import io
                info = tarfile.TarInfo("large.txt")
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))

            # Try to extract with small limit
            with tarfile.open(tar_path, "r") as tar:
                member = tar.getmembers()[0]
                policy = ExtractPolicy(max_total_bytes=100)

                with self.assertRaises(RuntimeError) as cm:
                    safe_extract_one(self.logger, tar, member, out_dir, policy=policy)
                self.assertIn("max_total_bytes", str(cm.exception))


class TestRAWExtractor(unittest.TestCase):
    """Test RAW image extractor."""

    def setUp(self):
        self.logger = Mock()

    @patch('hyper2kvm.converters.extractors.raw.RAW._log_virt_filesystems')
    def test_extracts_raw_file_directly(self, mock_log):
        """Test direct extraction of .raw file."""
        mock_log.return_value = {}

        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "disk.raw"
            src.write_bytes(b"fake raw disk content")
            out_dir = Path(td) / "out"
            out_dir.mkdir()

            result = RAW.extract_raw_or_tar(
                self.logger,
                src,
                out_dir,
                log_virt_filesystems=False,
            )

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].name, "disk.raw")

    @patch('hyper2kvm.converters.extractors.raw.RAW._log_virt_filesystems')
    def test_extracts_img_file_directly(self, mock_log):
        """Test direct extraction of .img file."""
        mock_log.return_value = {}

        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "disk.img"
            src.write_bytes(b"fake img disk content")
            out_dir = Path(td) / "out"
            out_dir.mkdir()

            result = RAW.extract_raw_or_tar(
                self.logger,
                src,
                out_dir,
                log_virt_filesystems=False,
            )

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].name, "disk.img")

    def test_extracts_raw_from_tarball(self):
        """Test extraction of .raw file from tarball."""
        with tempfile.TemporaryDirectory() as td:
            tar_path = Path(td) / "archive.tar"
            out_dir = Path(td) / "out"
            out_dir.mkdir()

            # Create tar with .raw file
            raw_content = b"fake raw disk"
            with tarfile.open(tar_path, "w") as tar:
                import io
                info = tarfile.TarInfo("disk.raw")
                info.size = len(raw_content)
                tar.addfile(info, io.BytesIO(raw_content))

            result = RAW.extract_raw_or_tar(
                self.logger,
                tar_path,
                out_dir,
            )

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].name, "disk.raw")
            self.assertEqual(result[0].read_bytes(), raw_content)

    def test_rejects_unsupported_format(self):
        """Test rejection of unsupported file formats."""
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "file.txt"
            src.write_text("not a disk image")
            out_dir = Path(td) / "out"
            out_dir.mkdir()

            with self.assertRaises(SystemExit):
                RAW.extract_raw_or_tar(self.logger, src, out_dir)

    def test_looks_like_tar(self):
        """Test tar file detection."""
        self.assertTrue(RAW._looks_like_tar(Path("file.tar")))
        self.assertTrue(RAW._looks_like_tar(Path("file.tar.gz")))
        self.assertTrue(RAW._looks_like_tar(Path("file.tgz")))
        self.assertTrue(RAW._looks_like_tar(Path("file.tar.xz")))
        self.assertTrue(RAW._looks_like_tar(Path("file.txz")))

        self.assertFalse(RAW._looks_like_tar(Path("file.raw")))
        self.assertFalse(RAW._looks_like_tar(Path("file.img")))
        self.assertFalse(RAW._looks_like_tar(Path("file.txt")))


if __name__ == "__main__":
    unittest.main()
