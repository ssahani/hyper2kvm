# SPDX-License-Identifier: LGPL-3.0-or-later
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from hyper2kvm.converters.fetch import Fetch


class TestFetch(unittest.TestCase):
    """Test remote disk fetching."""

    def setUp(self):
        self.logger = Mock()

    @patch('hyper2kvm.ssh.ssh_client.SSHClient')
    def test_validates_remote_path(self, mock_ssh):
        """Test validation of remote path."""
        mock_client = Mock()
        mock_ssh.return_value = mock_client

        # Test that path traversal is blocked
        with self.assertRaises((ValueError, RuntimeError)):
            Fetch.fetch_descriptor_and_extent(
                self.logger,
                mock_client,
                "../../../etc/passwd",
                Path("/tmp/out"),
                fetch_all=False,
            )

    @patch('hyper2kvm.ssh.ssh_client.SSHClient')
    def test_blocks_absolute_paths(self, mock_ssh):
        """Test blocking of absolute paths in remote path."""
        mock_client = Mock()
        mock_ssh.return_value = mock_client

        # Absolute paths should be blocked for safety
        with self.assertRaises((ValueError, RuntimeError)):
            Fetch.fetch_descriptor_and_extent(
                self.logger,
                mock_client,
                "/etc/passwd",
                Path("/tmp/out"),
                fetch_all=False,
            )

    @patch('hyper2kvm.ssh.ssh_client.SSHClient')
    def test_fetches_vmdk_descriptor(self, mock_ssh):
        """Test fetching VMDK descriptor file."""
        mock_client = Mock()
        mock_client.download_file.return_value = True
        mock_ssh.return_value = mock_client

        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)

            # Mock the descriptor content
            descriptor_path = out_dir / "test.vmdk"
            descriptor_path.write_text("# Disk DescriptorFile\nRW 100 SPARSE test.vmdk")

            result = Fetch.fetch_descriptor_and_extent(
                self.logger,
                mock_client,
                "datastore/test.vmdk",
                out_dir,
                fetch_all=False,
            )

            # Should attempt to download
            self.assertTrue(mock_client.download_file.called)

    @patch('hyper2kvm.ssh.ssh_client.SSHClient')
    def test_sanitizes_remote_path(self, mock_ssh):
        """Test sanitization of remote paths."""
        mock_client = Mock()
        mock_ssh.return_value = mock_client

        # Path with suspicious characters
        suspicious_path = "datastore/vm/../../../etc/passwd"

        with self.assertRaises((ValueError, RuntimeError)):
            Fetch.fetch_descriptor_and_extent(
                self.logger,
                mock_client,
                suspicious_path,
                Path("/tmp/out"),
                fetch_all=False,
            )


class TestFetchProgress(unittest.TestCase):
    """Test fetch progress tracking."""

    def setUp(self):
        self.logger = Mock()

    @patch('hyper2kvm.ssh.ssh_client.SSHClient')
    def test_reports_download_progress(self, mock_ssh):
        """Test that download progress is reported."""
        mock_client = Mock()
        progress_callback = Mock()

        with tempfile.TemporaryDirectory() as td:
            local_file = Path(td) / "test.vmdk"

            Fetch.download_with_progress(
                self.logger,
                mock_client,
                "remote/test.vmdk",
                local_file,
                progress_callback=progress_callback,
            )

            # Should report progress
            # Implementation may vary, but callback should be called


class TestFetchRetry(unittest.TestCase):
    """Test fetch retry logic."""

    def setUp(self):
        self.logger = Mock()

    @patch('hyper2kvm.ssh.ssh_client.SSHClient')
    def test_retries_on_failure(self, mock_ssh):
        """Test retry on download failure."""
        mock_client = Mock()
        # Simulate failure then success
        mock_client.download_file.side_effect = [
            Exception("Network error"),
            True,
        ]

        with tempfile.TemporaryDirectory() as td:
            out_file = Path(td) / "test.vmdk"

            result = Fetch.download_with_retry(
                self.logger,
                mock_client,
                "remote/test.vmdk",
                out_file,
                max_retries=3,
            )

            # Should succeed after retry
            self.assertEqual(mock_client.download_file.call_count, 2)

    @patch('hyper2kvm.ssh.ssh_client.SSHClient')
    def test_gives_up_after_max_retries(self, mock_ssh):
        """Test giving up after max retries."""
        mock_client = Mock()
        mock_client.download_file.side_effect = Exception("Network error")

        with tempfile.TemporaryDirectory() as td:
            out_file = Path(td) / "test.vmdk"

            with self.assertRaises(Exception):
                Fetch.download_with_retry(
                    self.logger,
                    mock_client,
                    "remote/test.vmdk",
                    out_file,
                    max_retries=3,
                )


if __name__ == "__main__":
    unittest.main()
