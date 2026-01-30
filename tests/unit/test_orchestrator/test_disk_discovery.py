# SPDX-License-Identifier: LGPL-3.0-or-later
import unittest
import tempfile
import argparse
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from hyper2kvm.orchestrator.disk_discovery import DiskDiscovery


class TestDiskDiscovery(unittest.TestCase):
    """Test disk discovery from various sources."""

    def setUp(self):
        self.logger = Mock()

    def test_normalize_ssh_opts_none(self):
        """Test normalization of None SSH options."""
        result = DiskDiscovery._normalize_ssh_opts(None)
        self.assertIsNone(result)

    def test_normalize_ssh_opts_list(self):
        """Test normalization of list SSH options."""
        result = DiskDiscovery._normalize_ssh_opts(["opt1", "opt2"])
        self.assertEqual(result, ["opt1", "opt2"])

    def test_normalize_ssh_opts_single_value(self):
        """Test normalization of single SSH option."""
        result = DiskDiscovery._normalize_ssh_opts("opt1")
        self.assertEqual(result, ["opt1"])

    def test_normalize_ssh_opts_filters_none(self):
        """Test that None values are filtered from lists."""
        result = DiskDiscovery._normalize_ssh_opts(["opt1", None, "opt2"])
        self.assertEqual(result, ["opt1", "opt2"])

    def test_discover_local_mode(self):
        """Test disk discovery in local mode."""
        with tempfile.TemporaryDirectory() as td:
            vmdk = Path(td) / "test.vmdk"
            vmdk.write_bytes(b"fake vmdk")
            out_root = Path(td) / "out"
            out_root.mkdir()

            args = argparse.Namespace(cmd="local", vmdk=str(vmdk))
            discovery = DiskDiscovery(self.logger, args)

            disks, temp_dir = discovery.discover(out_root)

            self.assertEqual(len(disks), 1)
            self.assertEqual(disks[0].name, "test.vmdk")
            self.assertIsNone(temp_dir)

    @patch('hyper2kvm.orchestrator.disk_discovery.Fetch.fetch_descriptor_and_extent')
    @patch('hyper2kvm.orchestrator.disk_discovery.SSHClient')
    def test_discover_fetch_and_fix_mode(self, mock_ssh_client, mock_fetch):
        """Test disk discovery in fetch-and-fix mode."""
        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td) / "out"
            out_root.mkdir()

            # Mock the fetched descriptor
            fetched_vmdk = out_root / "downloaded" / "fetched.vmdk"
            mock_fetch.return_value = fetched_vmdk

            args = argparse.Namespace(
                cmd="fetch-and-fix",
                host="remote.host",
                user="testuser",
                port=22,
                remote="/path/to/remote.vmdk",
                identity=None,
                ssh_opt=None,
                fetch_dir=None,
                fetch_all=False,
            )
            discovery = DiskDiscovery(self.logger, args)

            # This will create the fetch directory
            with patch('hyper2kvm.core.utils.U.ensure_dir'):
                disks, temp_dir = discovery.discover(out_root)

            # Verify SSH client was created
            self.assertTrue(mock_ssh_client.called)
            # Verify fetch was called
            self.assertTrue(mock_fetch.called)

    def test_discover_handles_missing_cmd(self):
        """Test that discovery handles missing cmd attribute."""
        args = argparse.Namespace()  # No cmd attribute
        discovery = DiskDiscovery(self.logger, args)

        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td)

            # Should handle gracefully
            disks, temp_dir = discovery.discover(out_root)
            self.assertEqual(disks, [])


class TestDiskDiscoveryIntegration(unittest.TestCase):
    """Integration tests for disk discovery."""

    def setUp(self):
        self.logger = Mock()

    def test_local_mode_with_real_file(self):
        """Test local mode with actual file."""
        with tempfile.TemporaryDirectory() as td:
            # Create a fake VMDK file
            vmdk = Path(td) / "test.vmdk"
            vmdk.write_bytes(b"# Disk DescriptorFile\nfake vmdk content")

            out_root = Path(td) / "output"
            out_root.mkdir()

            args = argparse.Namespace(cmd="local", vmdk=str(vmdk))
            discovery = DiskDiscovery(self.logger, args)

            disks, temp_dir = discovery.discover(out_root)

            # Verify disk was discovered
            self.assertEqual(len(disks), 1)
            self.assertTrue(disks[0].exists())
            self.assertEqual(disks[0].name, "test.vmdk")

    def test_local_mode_resolves_path(self):
        """Test that local mode resolves and expands paths."""
        with tempfile.TemporaryDirectory() as td:
            vmdk = Path(td) / "test.vmdk"
            vmdk.write_bytes(b"fake vmdk")

            # Use relative path with ..
            subdir = Path(td) / "subdir"
            subdir.mkdir()
            relative_vmdk = "../test.vmdk"

            out_root = Path(td) / "output"
            out_root.mkdir()

            # Change to subdir context
            import os
            orig_dir = os.getcwd()
            try:
                os.chdir(subdir)

                args = argparse.Namespace(cmd="local", vmdk=relative_vmdk)
                discovery = DiskDiscovery(self.logger, args)

                disks, temp_dir = discovery.discover(out_root)

                # Should resolve to absolute path
                self.assertTrue(disks[0].is_absolute())
                self.assertEqual(disks[0].name, "test.vmdk")
            finally:
                os.chdir(orig_dir)


if __name__ == "__main__":
    unittest.main()
