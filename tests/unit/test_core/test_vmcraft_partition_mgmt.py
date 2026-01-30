# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test VMCraft partition management APIs.

Tests the 7 partition management methods:
- part_init: Initialize empty partition table
- part_add: Add partition to device
- part_del: Delete partition from device
- part_disk: Initialize table and create single partition
- part_set_name: Set GPT partition name
- part_set_gpt_type: Set GPT partition type GUID
- part_get_parttype: Get partition table type
"""
import logging
import unittest
from unittest.mock import Mock, MagicMock, patch, call

from hyper2kvm.core.vmcraft.main import VMCraft


class TestPartInit(unittest.TestCase):
    """Test part_init method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()
        self.vmcraft._nbd_device = "/dev/nbd0"

    @patch('hyper2kvm.core.vmcraft.main.VMCraft.blockdev_rereadpt')
    @patch('hyper2kvm.core.vmcraft.main.VMCraft.invalidate_partition_cache')
    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_init_gpt(self, mock_run_sudo, mock_invalidate, mock_rereadpt):
        """Test initializing GPT partition table."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.part_init("/dev/nbd0", "gpt")

        # Should call parted mklabel
        mock_run_sudo.assert_called_once()
        args = mock_run_sudo.call_args[0]
        self.assertIn("parted", args[1])
        self.assertIn("mklabel", args[1])
        self.assertIn("gpt", args[1])

        # Should invalidate cache and re-read partition table
        mock_invalidate.assert_called_once_with("/dev/nbd0")
        mock_rereadpt.assert_called_once_with("/dev/nbd0")

    @patch('hyper2kvm.core.vmcraft.main.VMCraft.blockdev_rereadpt')
    @patch('hyper2kvm.core.vmcraft.main.VMCraft.invalidate_partition_cache')
    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_init_msdos(self, mock_run_sudo, mock_invalidate, mock_rereadpt):
        """Test initializing msdos partition table."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.part_init("/dev/nbd0", "msdos")

        args = mock_run_sudo.call_args[0]
        self.assertIn("msdos", args[1])

    @patch('hyper2kvm.core.vmcraft.main.VMCraft.blockdev_rereadpt')
    @patch('hyper2kvm.core.vmcraft.main.VMCraft.invalidate_partition_cache')
    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_init_mbr_normalized_to_msdos(self, mock_run_sudo, mock_invalidate, mock_rereadpt):
        """Test that 'mbr' is normalized to 'msdos'."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.part_init("/dev/nbd0", "mbr")

        args = mock_run_sudo.call_args[0]
        self.assertIn("msdos", args[1])
        self.assertNotIn("mbr", args[1])

    def test_part_init_invalid_parttype(self):
        """Test that invalid partition type raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.vmcraft.part_init("/dev/nbd0", "invalid")

        self.assertIn("Invalid partition type", str(ctx.exception))

    def test_part_init_not_launched(self):
        """Test that part_init raises if not launched."""
        vmcraft = VMCraft()
        vmcraft._nbd_device = None

        with self.assertRaises(RuntimeError) as ctx:
            vmcraft.part_init("/dev/nbd0", "gpt")

        self.assertIn("Not launched", str(ctx.exception))


class TestPartAdd(unittest.TestCase):
    """Test part_add method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()
        self.vmcraft._nbd_device = "/dev/nbd0"

    @patch('hyper2kvm.core.vmcraft.main.VMCraft.blockdev_rereadpt')
    @patch('hyper2kvm.core.vmcraft.main.VMCraft.invalidate_partition_cache')
    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_add_primary_to_end(self, mock_run_sudo, mock_invalidate, mock_rereadpt):
        """Test adding primary partition to end of disk."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.part_add("/dev/nbd0", "primary", 2048, -1)

        # Verify command
        args = mock_run_sudo.call_args[0]
        cmd = args[1]
        self.assertIn("parted", cmd)
        self.assertIn("mkpart", cmd)
        self.assertIn("primary", cmd)
        self.assertIn("2048s", cmd)
        self.assertIn("100%", cmd)

        # Should invalidate cache and re-read
        mock_invalidate.assert_called_once_with("/dev/nbd0")
        mock_rereadpt.assert_called_once_with("/dev/nbd0")

    @patch('hyper2kvm.core.vmcraft.main.VMCraft.blockdev_rereadpt')
    @patch('hyper2kvm.core.vmcraft.main.VMCraft.invalidate_partition_cache')
    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_add_with_specific_end(self, mock_run_sudo, mock_invalidate, mock_rereadpt):
        """Test adding partition with specific end sector."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.part_add("/dev/nbd0", "primary", 2048, 1024000)

        args = mock_run_sudo.call_args[0]
        cmd = args[1]
        self.assertIn("2048s", cmd)
        self.assertIn("1024000s", cmd)
        self.assertNotIn("100%", cmd)

    def test_part_add_invalid_type(self):
        """Test that invalid partition type raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.vmcraft.part_add("/dev/nbd0", "invalid", 2048, -1)

        self.assertIn("Invalid partition type", str(ctx.exception))

    def test_part_add_not_launched(self):
        """Test that part_add raises if not launched."""
        vmcraft = VMCraft()
        vmcraft._nbd_device = None

        with self.assertRaises(RuntimeError) as ctx:
            vmcraft.part_add("/dev/nbd0", "primary", 2048, -1)

        self.assertIn("Not launched", str(ctx.exception))


class TestPartDel(unittest.TestCase):
    """Test part_del method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()
        self.vmcraft._nbd_device = "/dev/nbd0"

    @patch('hyper2kvm.core.vmcraft.main.VMCraft.blockdev_rereadpt')
    @patch('hyper2kvm.core.vmcraft.main.VMCraft.invalidate_partition_cache')
    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_del_success(self, mock_run_sudo, mock_invalidate, mock_rereadpt):
        """Test successful partition deletion."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.part_del("/dev/nbd0", 1)

        # Verify command
        args = mock_run_sudo.call_args[0]
        cmd = args[1]
        self.assertIn("parted", cmd)
        self.assertIn("rm", cmd)
        self.assertIn("1", cmd)

        # Should invalidate cache and re-read
        mock_invalidate.assert_called_once_with("/dev/nbd0")
        mock_rereadpt.assert_called_once_with("/dev/nbd0")

    def test_part_del_invalid_partnum(self):
        """Test that invalid partition number raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.vmcraft.part_del("/dev/nbd0", 0)

        self.assertIn("Invalid partition number", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            self.vmcraft.part_del("/dev/nbd0", -1)

        self.assertIn("Invalid partition number", str(ctx.exception))

    def test_part_del_not_launched(self):
        """Test that part_del raises if not launched."""
        vmcraft = VMCraft()
        vmcraft._nbd_device = None

        with self.assertRaises(RuntimeError) as ctx:
            vmcraft.part_del("/dev/nbd0", 1)

        self.assertIn("Not launched", str(ctx.exception))


class TestPartDisk(unittest.TestCase):
    """Test part_disk method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()
        self.vmcraft._nbd_device = "/dev/nbd0"

    @patch('hyper2kvm.core.vmcraft.main.VMCraft.blockdev_rereadpt')
    @patch('hyper2kvm.core.vmcraft.main.VMCraft.invalidate_partition_cache')
    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_disk_gpt(self, mock_run_sudo, mock_invalidate, mock_rereadpt):
        """Test part_disk with GPT."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.part_disk("/dev/nbd0", "gpt")

        # Should be called twice: mklabel + mkpart
        self.assertEqual(mock_run_sudo.call_count, 2)

        # First call: mklabel gpt
        first_call_args = mock_run_sudo.call_args_list[0][0]
        self.assertIn("mklabel", first_call_args[1])
        self.assertIn("gpt", first_call_args[1])

        # Second call: mkpart primary
        second_call_args = mock_run_sudo.call_args_list[1][0]
        self.assertIn("mkpart", second_call_args[1])
        self.assertIn("primary", second_call_args[1])
        self.assertIn("1MiB", second_call_args[1])
        self.assertIn("100%", second_call_args[1])

        # Should invalidate cache and re-read
        mock_invalidate.assert_called_once_with("/dev/nbd0")
        mock_rereadpt.assert_called_once_with("/dev/nbd0")

    @patch('hyper2kvm.core.vmcraft.main.VMCraft.blockdev_rereadpt')
    @patch('hyper2kvm.core.vmcraft.main.VMCraft.invalidate_partition_cache')
    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_disk_mbr(self, mock_run_sudo, mock_invalidate, mock_rereadpt):
        """Test that 'mbr' is normalized to 'msdos' in part_disk."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.part_disk("/dev/nbd0", "mbr")

        # First call should use msdos
        first_call_args = mock_run_sudo.call_args_list[0][0]
        self.assertIn("msdos", first_call_args[1])

    def test_part_disk_invalid_parttype(self):
        """Test that invalid partition type raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.vmcraft.part_disk("/dev/nbd0", "invalid")

        self.assertIn("Invalid partition type", str(ctx.exception))


class TestPartSetName(unittest.TestCase):
    """Test part_set_name method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()
        self.vmcraft._nbd_device = "/dev/nbd0"

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_set_name_success(self, mock_run_sudo):
        """Test setting partition name."""
        mock_run_sudo.return_value = Mock()

        self.vmcraft.part_set_name("/dev/nbd0", 1, "EFI System")

        # Verify command
        args = mock_run_sudo.call_args[0]
        cmd = args[1]
        self.assertIn("parted", cmd)
        self.assertIn("name", cmd)
        self.assertIn("1", cmd)
        self.assertIn("EFI System", cmd)

    def test_part_set_name_invalid_partnum(self):
        """Test that invalid partition number raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.vmcraft.part_set_name("/dev/nbd0", 0, "test")

        self.assertIn("Invalid partition number", str(ctx.exception))

    def test_part_set_name_not_launched(self):
        """Test that part_set_name raises if not launched."""
        vmcraft = VMCraft()
        vmcraft._nbd_device = None

        with self.assertRaises(RuntimeError) as ctx:
            vmcraft.part_set_name("/dev/nbd0", 1, "test")

        self.assertIn("Not launched", str(ctx.exception))


class TestPartSetGptType(unittest.TestCase):
    """Test part_set_gpt_type method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()
        self.vmcraft._nbd_device = "/dev/nbd0"

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_set_gpt_type_success(self, mock_run_sudo):
        """Test setting GPT partition type GUID."""
        mock_run_sudo.return_value = Mock()

        guid = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
        self.vmcraft.part_set_gpt_type("/dev/nbd0", 1, guid)

        # Verify command uses sgdisk
        args = mock_run_sudo.call_args[0]
        cmd = args[1]
        self.assertIn("sgdisk", cmd)
        self.assertIn(f"--typecode=1:{guid}", cmd)
        self.assertIn("/dev/nbd0", cmd)

    def test_part_set_gpt_type_invalid_partnum(self):
        """Test that invalid partition number raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.vmcraft.part_set_gpt_type("/dev/nbd0", 0, "test-guid")

        self.assertIn("Invalid partition number", str(ctx.exception))

    def test_part_set_gpt_type_not_launched(self):
        """Test that part_set_gpt_type raises if not launched."""
        vmcraft = VMCraft()
        vmcraft._nbd_device = None

        with self.assertRaises(RuntimeError) as ctx:
            vmcraft.part_set_gpt_type("/dev/nbd0", 1, "test-guid")

        self.assertIn("Not launched", str(ctx.exception))


class TestPartGetParttype(unittest.TestCase):
    """Test part_get_parttype method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_get_parttype_gpt(self, mock_run_sudo):
        """Test detecting GPT partition table."""
        mock_result = Mock()
        mock_result.stdout = "Partition Table: gpt\n"
        mock_run_sudo.return_value = mock_result

        parttype = self.vmcraft.part_get_parttype("/dev/nbd0")

        self.assertEqual(parttype, "gpt")

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_get_parttype_msdos(self, mock_run_sudo):
        """Test detecting msdos partition table."""
        mock_result = Mock()
        mock_result.stdout = "Partition Table: msdos\n"
        mock_run_sudo.return_value = mock_result

        parttype = self.vmcraft.part_get_parttype("/dev/nbd0")

        self.assertEqual(parttype, "msdos")

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_get_parttype_mbr(self, mock_run_sudo):
        """Test that 'mbr' is recognized as 'msdos'."""
        mock_result = Mock()
        mock_result.stdout = "Partition Table: mbr\n"
        mock_run_sudo.return_value = mock_result

        parttype = self.vmcraft.part_get_parttype("/dev/nbd0")

        self.assertEqual(parttype, "msdos")

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_get_parttype_unknown(self, mock_run_sudo):
        """Test unknown partition table type."""
        mock_result = Mock()
        mock_result.stdout = "No partition table\n"
        mock_run_sudo.return_value = mock_result

        parttype = self.vmcraft.part_get_parttype("/dev/nbd0")

        self.assertEqual(parttype, "unknown")

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_get_parttype_error(self, mock_run_sudo):
        """Test that errors return 'unknown'."""
        mock_run_sudo.side_effect = Exception("parted failed")

        parttype = self.vmcraft.part_get_parttype("/dev/nbd0")

        self.assertEqual(parttype, "unknown")


class TestPartitionWorkflows(unittest.TestCase):
    """Test complete partition management workflows."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()
        self.vmcraft._nbd_device = "/dev/nbd0"

    @patch('hyper2kvm.core.vmcraft.main.VMCraft.blockdev_rereadpt')
    @patch('hyper2kvm.core.vmcraft.main.VMCraft.invalidate_partition_cache')
    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_create_and_delete_partition_workflow(
        self, mock_run_sudo, mock_invalidate, mock_rereadpt
    ):
        """Test creating and deleting a partition."""
        mock_run_sudo.return_value = Mock()

        # Initialize partition table
        self.vmcraft.part_init("/dev/nbd0", "gpt")

        # Add partition
        self.vmcraft.part_add("/dev/nbd0", "primary", 2048, -1)

        # Delete partition
        self.vmcraft.part_del("/dev/nbd0", 1)

        # Verify cache was invalidated 3 times (init, add, del)
        self.assertEqual(mock_invalidate.call_count, 3)

        # Verify partition table was re-read 3 times
        self.assertEqual(mock_rereadpt.call_count, 3)

    @patch('hyper2kvm.core.vmcraft.main.VMCraft.blockdev_rereadpt')
    @patch('hyper2kvm.core.vmcraft.main.VMCraft.invalidate_partition_cache')
    @patch('hyper2kvm.core.vmcraft.main.VMCraft.part_get_parttype')
    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_part_disk_workflow(
        self, mock_run_sudo, mock_get_parttype, mock_invalidate, mock_rereadpt
    ):
        """Test complete disk partitioning workflow."""
        mock_run_sudo.return_value = Mock()
        mock_get_parttype.return_value = "gpt"

        # Use part_disk to create partition table and single partition
        self.vmcraft.part_disk("/dev/nbd0", "gpt")

        # Verify partition table type
        parttype = self.vmcraft.part_get_parttype("/dev/nbd0")
        self.assertEqual(parttype, "gpt")


if __name__ == "__main__":
    unittest.main()
