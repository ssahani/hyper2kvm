# SPDX-License-Identifier: LGPL-3.0-or-later
import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch

from hyper2kvm.core.utils import U


class TestUtilsFileOperations(unittest.TestCase):
    """Test utility file operations."""

    def test_ensure_dir_creates_directory(self):
        """Test that ensure_dir creates directory."""
        with tempfile.TemporaryDirectory() as td:
            new_dir = Path(td) / "subdir" / "nested"

            U.ensure_dir(new_dir)

            self.assertTrue(new_dir.exists())
            self.assertTrue(new_dir.is_dir())

    def test_ensure_dir_handles_existing(self):
        """Test that ensure_dir handles existing directory."""
        with tempfile.TemporaryDirectory() as td:
            existing = Path(td) / "existing"
            existing.mkdir()

            # Should not raise
            U.ensure_dir(existing)

            self.assertTrue(existing.exists())

    def test_safe_read_text(self):
        """Test safe text file reading."""
        with tempfile.TemporaryDirectory() as td:
            file_path = Path(td) / "test.txt"
            content = "Test content\nLine 2"
            file_path.write_text(content, encoding="utf-8")

            result = U.safe_read_text(file_path)

            self.assertEqual(result, content)

    def test_safe_read_text_missing_file(self):
        """Test safe read of missing file."""
        result = U.safe_read_text(Path("/nonexistent/file.txt"))

        self.assertIsNone(result)

    def test_safe_write_text(self):
        """Test safe text file writing."""
        with tempfile.TemporaryDirectory() as td:
            file_path = Path(td) / "test.txt"
            content = "Test content"

            U.safe_write_text(file_path, content)

            self.assertEqual(file_path.read_text(), content)


class TestUtilsCommandExecution(unittest.TestCase):
    """Test utility command execution."""

    def setUp(self):
        self.logger = Mock()

    @patch('subprocess.run')
    def test_run_cmd_executes_command(self, mock_run):
        """Test command execution."""
        mock_run.return_value = Mock(returncode=0, stdout="output", stderr="")

        result = U.run_cmd(self.logger, ["echo", "test"])

        self.assertTrue(mock_run.called)
        self.assertEqual(result.returncode, 0)

    @patch('subprocess.run')
    def test_run_cmd_captures_output(self, mock_run):
        """Test output capture."""
        mock_run.return_value = Mock(returncode=0, stdout="test output", stderr="")

        result = U.run_cmd(self.logger, ["echo", "test"], capture=True)

        self.assertEqual(result.stdout, "test output")

    @patch('subprocess.run')
    def test_run_cmd_handles_failure(self, mock_run):
        """Test handling of command failure."""
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="error")

        result = U.run_cmd(self.logger, ["false"], check=False)

        self.assertEqual(result.returncode, 1)

    def test_which_finds_command(self):
        """Test finding command in PATH."""
        # ls should exist on most systems
        result = U.which("ls")

        self.assertIsNotNone(result)
        self.assertIn("ls", str(result))

    def test_which_returns_none_for_missing(self):
        """Test that which returns None for missing command."""
        result = U.which("nonexistent-command-xyz123")

        self.assertIsNone(result)


class TestUtilsPathOperations(unittest.TestCase):
    """Test utility path operations."""

    def test_expand_path(self):
        """Test path expansion."""
        # Test tilde expansion
        path = "~/test"
        expanded = U.expand_path(path)

        self.assertNotIn("~", str(expanded))
        self.assertTrue(str(expanded).startswith("/"))

    def test_resolve_path(self):
        """Test path resolution."""
        with tempfile.TemporaryDirectory() as td:
            # Create a symlink
            real_file = Path(td) / "real.txt"
            real_file.write_text("content")

            link = Path(td) / "link.txt"
            link.symlink_to(real_file)

            resolved = U.resolve_path(link)

            self.assertEqual(resolved, real_file)

    def test_is_safe_path(self):
        """Test path safety check."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            safe = base / "subdir" / "file.txt"

            self.assertTrue(U.is_safe_path(base, safe))

    def test_detects_unsafe_path_traversal(self):
        """Test detection of path traversal."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "base"
            unsafe = Path(td) / "outside"

            self.assertFalse(U.is_safe_path(base, unsafe))


class TestUtilsStringOperations(unittest.TestCase):
    """Test utility string operations."""

    def test_sanitize_filename(self):
        """Test filename sanitization."""
        unsafe = "file/with:illegal*chars?.txt"
        safe = U.sanitize_filename(unsafe)

        self.assertNotIn("/", safe)
        self.assertNotIn(":", safe)
        self.assertNotIn("*", safe)
        self.assertNotIn("?", safe)

    def test_truncate_string(self):
        """Test string truncation."""
        long_str = "a" * 1000
        truncated = U.truncate(long_str, max_len=50)

        self.assertLessEqual(len(truncated), 53)  # 50 + "..."

    def test_human_readable_size(self):
        """Test human-readable size formatting."""
        self.assertEqual(U.human_size(1024), "1.0 KiB")
        self.assertEqual(U.human_size(1024 * 1024), "1.0 MiB")
        self.assertEqual(U.human_size(1024 * 1024 * 1024), "1.0 GiB")

    def test_parse_size_string(self):
        """Test parsing size strings."""
        self.assertEqual(U.parse_size("10G"), 10 * 1024 * 1024 * 1024)
        self.assertEqual(U.parse_size("5M"), 5 * 1024 * 1024)
        self.assertEqual(U.parse_size("100K"), 100 * 1024)


class TestUtilsLogging(unittest.TestCase):
    """Test utility logging helpers."""

    def setUp(self):
        self.logger = Mock()

    def test_banner_logs_formatted_message(self):
        """Test banner logging."""
        U.banner(self.logger, "Test Message")

        self.assertTrue(self.logger.info.called)

    def test_step_logs_with_prefix(self):
        """Test step logging."""
        U.step(self.logger, "Step 1: Do something")

        self.assertTrue(self.logger.info.called)

    def test_die_exits_with_code(self):
        """Test die function exits."""
        with self.assertRaises(SystemExit) as cm:
            U.die(self.logger, "Fatal error", code=42)

        self.assertEqual(cm.exception.code, 42)
        self.assertTrue(self.logger.error.called)


if __name__ == "__main__":
    unittest.main()
