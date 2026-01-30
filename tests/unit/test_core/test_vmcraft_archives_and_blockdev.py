# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test VMCraft archive operations and additional block device APIs.

Tests the 7 methods:
Archive Operations:
- tar_in: Unpack tarball into guest
- tar_out: Pack guest directory into tarball
- tgz_in: Unpack gzipped tarball (convenience wrapper)
- tgz_out: Pack to gzipped tarball (convenience wrapper)

Block Device APIs:
- blockdev_getsize64: Get device size in bytes
- blockdev_getsz: Get device size in 512-byte sectors
- dd_copy: Copy data using dd
"""
import unittest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path
import tempfile
import os

from hyper2kvm.core.vmcraft.main import VMCraft


class TestTarIn(unittest.TestCase):
    """Test tar_in method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()
        self.vmcraft._mount_root = Path("/tmp/test-mount")

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    @patch('pathlib.Path.mkdir')
    def test_tar_in_uncompressed(self, mock_mkdir, mock_run_sudo):
        """Test extracting uncompressed tarball."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.tar_in("/tmp/archive.tar", "/opt")

        # Verify mkdir was called
        mock_mkdir.assert_called_once()

        # Verify tar command
        mock_run_sudo.assert_called_once()
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("tar", cmd)
        self.assertIn("-xf", cmd)
        self.assertIn("/tmp/archive.tar", cmd)
        self.assertIn("-C", cmd)

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    @patch('pathlib.Path.mkdir')
    def test_tar_in_gzip(self, mock_mkdir, mock_run_sudo):
        """Test extracting gzipped tarball."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.tar_in("/tmp/archive.tar.gz", "/opt", compress="gzip")

        # Verify tar command includes -z flag
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("-z", cmd)
        self.assertIn("-xf", cmd)

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    @patch('pathlib.Path.mkdir')
    def test_tar_in_bzip2(self, mock_mkdir, mock_run_sudo):
        """Test extracting bzip2 tarball."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.tar_in("/tmp/archive.tar.bz2", "/opt", compress="bzip2")

        # Verify tar command includes -j flag
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("-j", cmd)
        self.assertIn("-xf", cmd)

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    @patch('pathlib.Path.mkdir')
    def test_tar_in_xz(self, mock_mkdir, mock_run_sudo):
        """Test extracting xz tarball."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.tar_in("/tmp/archive.tar.xz", "/opt", compress="xz")

        # Verify tar command includes -J flag
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("-J", cmd)
        self.assertIn("-xf", cmd)

    def test_tar_in_not_launched(self):
        """Test that tar_in raises if not launched."""
        vmcraft = VMCraft()
        vmcraft._mount_root = None

        with self.assertRaises(RuntimeError) as ctx:
            vmcraft.tar_in("/tmp/archive.tar", "/opt")

        self.assertIn("Not launched", str(ctx.exception))

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    @patch('pathlib.Path.mkdir')
    def test_tar_in_creates_directory(self, mock_mkdir, mock_run_sudo):
        """Test that tar_in creates target directory."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.tar_in("/tmp/archive.tar", "/opt/myapp")

        # Verify mkdir was called with parents=True, exist_ok=True
        mock_mkdir.assert_called_once()
        call_kwargs = mock_mkdir.call_args[1]
        self.assertTrue(call_kwargs.get('parents'))
        self.assertTrue(call_kwargs.get('exist_ok'))


class TestTarOut(unittest.TestCase):
    """Test tar_out method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()
        self.vmcraft._mount_root = Path("/tmp/test-mount")

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    @patch('pathlib.Path.exists')
    def test_tar_out_uncompressed(self, mock_exists, mock_run_sudo):
        """Test creating uncompressed tarball."""
        mock_exists.return_value = True
        mock_run_sudo.return_value = Mock()

        self.vmcraft.tar_out("/etc", "/tmp/backup.tar")

        # Verify tar command
        mock_run_sudo.assert_called_once()
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("tar", cmd)
        self.assertIn("-cf", cmd)
        self.assertIn("/tmp/backup.tar", cmd)
        self.assertIn("-C", cmd)

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    @patch('pathlib.Path.exists')
    def test_tar_out_gzip(self, mock_exists, mock_run_sudo):
        """Test creating gzipped tarball."""
        mock_exists.return_value = True
        mock_run_sudo.return_value = Mock()

        self.vmcraft.tar_out("/etc", "/tmp/backup.tar.gz", compress="gzip")

        # Verify tar command includes -z flag
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("-z", cmd)
        self.assertIn("-cf", cmd)

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    @patch('pathlib.Path.exists')
    def test_tar_out_bzip2(self, mock_exists, mock_run_sudo):
        """Test creating bzip2 tarball."""
        mock_exists.return_value = True
        mock_run_sudo.return_value = Mock()

        self.vmcraft.tar_out("/etc", "/tmp/backup.tar.bz2", compress="bzip2")

        # Verify tar command includes -j flag
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("-j", cmd)
        self.assertIn("-cf", cmd)

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    @patch('pathlib.Path.exists')
    def test_tar_out_xz(self, mock_exists, mock_run_sudo):
        """Test creating xz tarball."""
        mock_exists.return_value = True
        mock_run_sudo.return_value = Mock()

        self.vmcraft.tar_out("/etc", "/tmp/backup.tar.xz", compress="xz")

        # Verify tar command includes -J flag
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("-J", cmd)
        self.assertIn("-cf", cmd)

    @patch('pathlib.Path.exists')
    def test_tar_out_directory_not_exists(self, mock_exists):
        """Test that tar_out raises if directory doesn't exist."""
        mock_exists.return_value = False

        with self.assertRaises(RuntimeError) as ctx:
            self.vmcraft.tar_out("/nonexistent", "/tmp/backup.tar")

        self.assertIn("does not exist", str(ctx.exception))

    def test_tar_out_not_launched(self):
        """Test that tar_out raises if not launched."""
        vmcraft = VMCraft()
        vmcraft._mount_root = None

        with self.assertRaises(RuntimeError) as ctx:
            vmcraft.tar_out("/etc", "/tmp/backup.tar")

        self.assertIn("Not launched", str(ctx.exception))


class TestTgzConvenienceWrappers(unittest.TestCase):
    """Test tgz_in and tgz_out convenience wrappers."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()
        self.vmcraft._mount_root = Path("/tmp/test-mount")

    @patch.object(VMCraft, 'tar_in')
    def test_tgz_in_calls_tar_in_with_gzip(self, mock_tar_in):
        """Test that tgz_in calls tar_in with gzip compression."""
        self.vmcraft.tgz_in("/tmp/app.tar.gz", "/opt")

        mock_tar_in.assert_called_once_with("/tmp/app.tar.gz", "/opt", compress="gzip")

    @patch.object(VMCraft, 'tar_out')
    def test_tgz_out_calls_tar_out_with_gzip(self, mock_tar_out):
        """Test that tgz_out calls tar_out with gzip compression."""
        self.vmcraft.tgz_out("/var/log", "/tmp/logs.tar.gz")

        mock_tar_out.assert_called_once_with("/var/log", "/tmp/logs.tar.gz", compress="gzip")


class TestArchiveWorkflows(unittest.TestCase):
    """Test complete archive workflows."""

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.exists')
    def test_backup_and_restore_workflow(self, mock_exists, mock_mkdir, mock_run_sudo):
        """Test backing up and restoring a directory."""
        vmcraft = VMCraft()
        vmcraft._mount_root = Path("/tmp/test-mount")

        mock_exists.return_value = True
        mock_run_sudo.return_value = Mock()

        # Backup /etc to tarball
        vmcraft.tar_out("/etc", "/tmp/etc-backup.tar.gz", compress="gzip")

        # Restore from tarball
        vmcraft.tar_in("/tmp/etc-backup.tar.gz", "/etc-restore", compress="gzip")

        # Verify both commands were called
        self.assertEqual(mock_run_sudo.call_count, 2)

        # Verify first call was tar -cf (create)
        first_cmd = mock_run_sudo.call_args_list[0][0][1]
        self.assertIn("-cf", first_cmd)

        # Verify second call was tar -xf (extract)
        second_cmd = mock_run_sudo.call_args_list[1][0][1]
        self.assertIn("-xf", second_cmd)


class TestBlockdevGetsize64(unittest.TestCase):
    """Test blockdev_getsize64 method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    def test_blockdev_getsize64_success(self, mock_run_sudo):
        """Test getting device size in bytes."""
        mock_result = Mock()
        mock_result.stdout = "10737418240\n"  # 10 GB
        mock_run_sudo.return_value = mock_result

        size = self.vmcraft.blockdev_getsize64("/dev/nbd0")

        self.assertEqual(size, 10737418240)
        mock_run_sudo.assert_called_once()
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("blockdev", cmd)
        self.assertIn("--getsize64", cmd)
        self.assertIn("/dev/nbd0", cmd)

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    def test_blockdev_getsize64_failure(self, mock_run_sudo):
        """Test that failures return 0."""
        mock_run_sudo.side_effect = Exception("Device not found")

        size = self.vmcraft.blockdev_getsize64("/dev/nonexistent")

        self.assertEqual(size, 0)

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    def test_blockdev_getsize64_partition(self, mock_run_sudo):
        """Test getting partition size."""
        mock_result = Mock()
        mock_result.stdout = "1073741824\n"  # 1 GB
        mock_run_sudo.return_value = mock_result

        size = self.vmcraft.blockdev_getsize64("/dev/nbd0p1")

        self.assertEqual(size, 1073741824)


class TestBlockdevGetsz(unittest.TestCase):
    """Test blockdev_getsz method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    def test_blockdev_getsz_success(self, mock_run_sudo):
        """Test getting device size in sectors."""
        mock_result = Mock()
        mock_result.stdout = "20971520\n"  # 10 GB / 512
        mock_run_sudo.return_value = mock_result

        sectors = self.vmcraft.blockdev_getsz("/dev/nbd0")

        self.assertEqual(sectors, 20971520)
        mock_run_sudo.assert_called_once()
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("blockdev", cmd)
        self.assertIn("--getsz", cmd)
        self.assertIn("/dev/nbd0", cmd)

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    def test_blockdev_getsz_failure(self, mock_run_sudo):
        """Test that failures return 0."""
        mock_run_sudo.side_effect = Exception("Device not found")

        sectors = self.vmcraft.blockdev_getsz("/dev/nonexistent")

        self.assertEqual(sectors, 0)


class TestDdCopy(unittest.TestCase):
    """Test dd_copy method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    def test_dd_copy_basic(self, mock_run_sudo):
        """Test basic dd copy."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.dd_copy("/dev/nbd0", "/tmp/disk-backup.img")

        mock_run_sudo.assert_called_once()
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("dd", cmd)
        self.assertIn("if=/dev/nbd0", cmd)
        self.assertIn("of=/tmp/disk-backup.img", cmd)
        self.assertIn("bs=512", cmd)

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    def test_dd_copy_with_count(self, mock_run_sudo):
        """Test dd copy with block count."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.dd_copy("/dev/nbd0", "/tmp/mbr.bin", count=2048)

        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("count=2048", cmd)

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    def test_dd_copy_with_custom_blocksize(self, mock_run_sudo):
        """Test dd copy with custom block size."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.dd_copy("/dev/nbd0", "/tmp/backup.img", blocksize=4096)

        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("bs=4096", cmd)

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    def test_dd_copy_with_all_parameters(self, mock_run_sudo):
        """Test dd copy with all parameters."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.dd_copy("/dev/nbd0p1", "/dev/nbd1p1", count=1024, blocksize=1024)

        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("if=/dev/nbd0p1", cmd)
        self.assertIn("of=/dev/nbd1p1", cmd)
        self.assertIn("bs=1024", cmd)
        self.assertIn("count=1024", cmd)

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    def test_dd_copy_failure(self, mock_run_sudo):
        """Test dd copy failure handling."""
        mock_run_sudo.side_effect = Exception("I/O error")

        with self.assertRaises(RuntimeError) as ctx:
            self.vmcraft.dd_copy("/dev/nbd0", "/tmp/backup.img")

        self.assertIn("dd copy failed", str(ctx.exception))


class TestBlockDeviceWorkflows(unittest.TestCase):
    """Test complete block device workflows."""

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    def test_disk_size_and_backup_workflow(self, mock_run_sudo):
        """Test getting disk size and backing up specific sectors."""
        vmcraft = VMCraft()

        # Mock blockdev_getsize64 response (10 GB)
        mock_result_size = Mock()
        mock_result_size.stdout = "10737418240\n"

        # Mock dd response
        mock_result_dd = Mock()

        # Set up side_effect for multiple calls
        mock_run_sudo.side_effect = [mock_result_size, mock_result_dd]

        # Get disk size
        size_bytes = vmcraft.blockdev_getsize64("/dev/nbd0")
        self.assertEqual(size_bytes, 10737418240)

        # Backup first 1MB (2048 sectors of 512 bytes)
        vmcraft.dd_copy("/dev/nbd0", "/tmp/mbr-backup.bin", count=2048, blocksize=512)

        # Verify both commands were called
        self.assertEqual(mock_run_sudo.call_count, 2)

    @patch('hyper2kvm.core.vmcraft._utils.run_sudo')
    def test_sector_calculation_workflow(self, mock_run_sudo):
        """Test converting between bytes and sectors."""
        vmcraft = VMCraft()

        # Mock responses
        mock_result_bytes = Mock()
        mock_result_bytes.stdout = "10737418240\n"  # 10 GB

        mock_result_sectors = Mock()
        mock_result_sectors.stdout = "20971520\n"  # 10 GB / 512

        mock_run_sudo.side_effect = [mock_result_bytes, mock_result_sectors]

        # Get size in bytes
        size_bytes = vmcraft.blockdev_getsize64("/dev/nbd0")

        # Get size in sectors
        size_sectors = vmcraft.blockdev_getsz("/dev/nbd0")

        # Verify conversion: bytes / 512 = sectors
        self.assertEqual(size_bytes // 512, size_sectors)


if __name__ == "__main__":
    unittest.main()
