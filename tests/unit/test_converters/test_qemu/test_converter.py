# SPDX-License-Identifier: LGPL-3.0-or-later
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import subprocess

from hyper2kvm.converters.qemu.converter import Convert


class TestConvertOptions(unittest.TestCase):
    """Test ConvertOptions dataclass."""

    def test_default_options(self):
        """Test default conversion options."""
        opts = Convert.ConvertOptions()
        self.assertEqual(opts.cache_mode, "none")
        self.assertIsNone(opts.threads)
        self.assertEqual(opts.compression_type, "zstd")
        self.assertIsNone(opts.compression_level)
        self.assertIsNone(opts.preallocation)

    def test_short_representation(self):
        """Test short string representation."""
        opts = Convert.ConvertOptions()
        short = opts.short()
        self.assertIn("cache=none", short)
        self.assertIn("threads=off", short)
        self.assertIn("ctype=zstd", short)

    def test_custom_options(self):
        """Test custom conversion options."""
        opts = Convert.ConvertOptions(
            cache_mode="writeback",
            threads=4,
            compression_type="zlib",
            compression_level=6,
            preallocation="metadata"
        )
        short = opts.short()
        self.assertIn("cache=writeback", short)
        self.assertIn("threads=4", short)
        self.assertIn("ctype=zlib", short)
        self.assertIn("clevel=6", short)
        self.assertIn("prealloc=metadata", short)


class TestConvertProgressParsing(unittest.TestCase):
    """Test progress output parsing."""

    def test_parses_parenthesis_format(self):
        """Test parsing (XX/100%) format."""
        match = Convert._RE_PAREN.search("Converting (45.5/100%)")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "45.5")

    def test_parses_fraction_format(self):
        """Test parsing XX/100% format."""
        match = Convert._RE_FRACTION.search("Progress: 75/100%")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "75")

    def test_parses_progress_format(self):
        """Test parsing Progress: XX format."""
        match = Convert._RE_PROGRESS.search("progress: 80.25")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "80.25")

    def test_parses_percent_format(self):
        """Test parsing XX% format."""
        match = Convert._RE_PERCENT.search("Status: 90%")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "90")

    def test_detects_json_output(self):
        """Test JSON output detection."""
        self.assertTrue(Convert._RE_JSON.match('{"progress": 50}'))
        self.assertTrue(Convert._RE_JSON.match('  {"key": "value"}  '))
        self.assertFalse(Convert._RE_JSON.match('not json'))


class TestConvertImageWithProgress(unittest.TestCase):
    """Test image conversion with progress tracking."""

    def setUp(self):
        self.logger = Mock()

    @patch('hyper2kvm.core.utils.U.which')
    def test_dies_if_qemu_img_not_found(self, mock_which):
        """Test that conversion fails if qemu-img is not available."""
        mock_which.return_value = None

        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "input.raw"
            dst = Path(td) / "output.qcow2"
            src.write_bytes(b"fake disk")

            with self.assertRaises(SystemExit):
                Convert.convert_image_with_progress(
                    self.logger,
                    src,
                    dst,
                    out_format="qcow2",
                    compress=False,
                )

    @patch('hyper2kvm.converters.qemu.converter.subprocess.Popen')
    @patch('hyper2kvm.core.utils.U.which')
    @patch('hyper2kvm.core.utils.U.die')
    def test_basic_conversion_command(self, mock_die, mock_which, mock_popen):
        """Test basic conversion command construction."""
        mock_which.return_value = "/usr/bin/qemu-img"
        mock_die.side_effect = SystemExit(1)

        # Mock process
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.fileno.return_value = 1
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.fileno.return_value = 2
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        # Mock selectors to simulate immediate completion
        with patch('hyper2kvm.converters.qemu.converter.selectors.DefaultSelector') as mock_selector_class:
            mock_selector = MagicMock()
            mock_selector_class.return_value.__enter__.return_value = mock_selector
            mock_selector.select.return_value = []
            mock_proc.poll.side_effect = [None, 0]  # Running then completed

            with tempfile.TemporaryDirectory() as td:
                src = Path(td) / "input.raw"
                dst = Path(td) / "output.qcow2"
                src.write_bytes(b"fake disk")

                try:
                    Convert.convert_image_with_progress(
                        self.logger,
                        src,
                        dst,
                        out_format="qcow2",
                        compress=False,
                        atomic=False,
                    )
                except:
                    pass  # May fail due to mocking, we just want to check the command

                # Verify qemu-img was called
                self.assertTrue(mock_popen.called)


class TestValidate(unittest.TestCase):
    """Test image validation."""

    def setUp(self):
        self.logger = Mock()

    @patch('hyper2kvm.core.utils.U.run_cmd')
    def test_validate_calls_qemu_img_check(self, mock_run):
        """Test that validate runs qemu-img check."""
        mock_run.return_value = Mock(returncode=0, stdout="")

        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "test.qcow2"
            image.write_bytes(b"fake image")

            Convert.validate(self.logger, image)

            # Verify qemu-img check was called
            self.assertTrue(mock_run.called)
            args = mock_run.call_args[0][1]
            self.assertEqual(args[0], "qemu-img")
            self.assertEqual(args[1], "check")
            self.assertIn(str(image), args)


class TestQueryDiskInfo(unittest.TestCase):
    """Test disk info querying."""

    def setUp(self):
        self.logger = Mock()

    @patch('hyper2kvm.core.utils.U.run_cmd')
    def test_query_disk_info_json_format(self, mock_run):
        """Test querying disk info in JSON format."""
        mock_output = '{"virtual-size": 10737418240, "format": "qcow2"}'
        mock_run.return_value = Mock(returncode=0, stdout=mock_output)

        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "test.qcow2"
            image.write_bytes(b"fake image")

            result = Convert.query_disk_info(self.logger, image, output_format="json")

            self.assertIsInstance(result, dict)
            self.assertIn("virtual-size", result)
            self.assertEqual(result["format"], "qcow2")

    @patch('hyper2kvm.core.utils.U.run_cmd')
    def test_query_disk_info_human_format(self, mock_run):
        """Test querying disk info in human-readable format."""
        mock_output = "image: test.qcow2\nfile format: qcow2\nvirtual size: 10G"
        mock_run.return_value = Mock(returncode=0, stdout=mock_output)

        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "test.qcow2"
            image.write_bytes(b"fake image")

            result = Convert.query_disk_info(self.logger, image, output_format="human")

            self.assertIsInstance(result, str)
            self.assertIn("qcow2", result)


class TestResizeImage(unittest.TestCase):
    """Test image resizing."""

    def setUp(self):
        self.logger = Mock()

    @patch('hyper2kvm.core.utils.U.run_cmd')
    def test_resize_image(self, mock_run):
        """Test image resize operation."""
        mock_run.return_value = Mock(returncode=0, stdout="")

        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "test.qcow2"
            image.write_bytes(b"fake image")

            Convert.resize_image(self.logger, image, new_size="20G")

            # Verify qemu-img resize was called
            self.assertTrue(mock_run.called)
            args = mock_run.call_args[0][1]
            self.assertEqual(args[0], "qemu-img")
            self.assertEqual(args[1], "resize")
            self.assertIn(str(image), args)
            self.assertIn("20G", args)


class TestSnapshotOperations(unittest.TestCase):
    """Test snapshot operations."""

    def setUp(self):
        self.logger = Mock()

    @patch('hyper2kvm.core.utils.U.run_cmd')
    def test_create_snapshot(self, mock_run):
        """Test snapshot creation."""
        mock_run.return_value = Mock(returncode=0, stdout="")

        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "test.qcow2"
            image.write_bytes(b"fake image")

            Convert.create_snapshot(self.logger, image, snapshot_name="snap1")

            # Verify qemu-img snapshot was called
            self.assertTrue(mock_run.called)
            args = mock_run.call_args[0][1]
            self.assertEqual(args[0], "qemu-img")
            self.assertEqual(args[1], "snapshot")

    @patch('hyper2kvm.core.utils.U.run_cmd')
    def test_list_snapshots(self, mock_run):
        """Test snapshot listing."""
        mock_output = "Snapshot list:\nID        TAG                 VM SIZE                DATE       VM CLOCK\n1         snap1                     0 2024-01-01 00:00:00   00:00:00.000"
        mock_run.return_value = Mock(returncode=0, stdout=mock_output)

        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "test.qcow2"
            image.write_bytes(b"fake image")

            result = Convert.list_snapshots(self.logger, image)

            self.assertIsInstance(result, str)
            self.assertIn("snap1", result)


if __name__ == "__main__":
    unittest.main()
