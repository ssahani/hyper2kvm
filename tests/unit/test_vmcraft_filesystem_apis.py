# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Unit tests for VMCraft filesystem detection APIs.

Tests the new APIs added for partition operations, inspection,
extended attributes, and filesystem-specific operations.
"""

import pytest
from hyper2kvm.core.vmcraft.main import VMCraft


class TestPartitionOperations:
    """Test partition-related APIs."""

    def test_part_to_partnum_traditional(self):
        """Test partition number extraction from traditional devices."""
        g = VMCraft()

        assert g.part_to_partnum("/dev/sda1") == 1
        assert g.part_to_partnum("/dev/sda2") == 2
        assert g.part_to_partnum("/dev/vda1") == 1
        assert g.part_to_partnum("/dev/hda3") == 3

    def test_part_to_partnum_nvme(self):
        """Test partition number extraction from NVMe devices."""
        g = VMCraft()

        assert g.part_to_partnum("/dev/nvme0n1p1") == 1
        assert g.part_to_partnum("/dev/nvme0n1p2") == 2
        assert g.part_to_partnum("/dev/nvme1n1p5") == 5

    def test_part_to_partnum_nbd(self):
        """Test partition number extraction from NBD devices."""
        g = VMCraft()

        assert g.part_to_partnum("/dev/nbd0p1") == 1
        assert g.part_to_partnum("/dev/nbd0p2") == 2
        assert g.part_to_partnum("/dev/nbd1p3") == 3

    def test_part_to_partnum_by_path(self):
        """Test partition number extraction from by-path devices."""
        g = VMCraft()

        assert g.part_to_partnum("/dev/disk/by-path/pci-0000:00:1f.2-ata-1-part1") == 1
        assert g.part_to_partnum("/dev/disk/by-path/pci-0000:00:1f.2-ata-1-part2") == 2

    def test_part_to_partnum_invalid(self):
        """Test partition number extraction with invalid input."""
        g = VMCraft()

        with pytest.raises(RuntimeError, match="Cannot extract partition number"):
            g.part_to_partnum("/dev/sda")

        with pytest.raises(RuntimeError, match="Cannot extract partition number"):
            g.part_to_partnum("/invalid/path")

    def test_part_to_dev_traditional(self):
        """Test parent device extraction from traditional devices."""
        g = VMCraft()

        assert g.part_to_dev("/dev/sda1") == "/dev/sda"
        assert g.part_to_dev("/dev/sda2") == "/dev/sda"
        assert g.part_to_dev("/dev/vda1") == "/dev/vda"
        assert g.part_to_dev("/dev/hda3") == "/dev/hda"

    def test_part_to_dev_nvme(self):
        """Test parent device extraction from NVMe devices."""
        g = VMCraft()

        assert g.part_to_dev("/dev/nvme0n1p1") == "/dev/nvme0n1"
        assert g.part_to_dev("/dev/nvme0n1p2") == "/dev/nvme0n1"
        assert g.part_to_dev("/dev/nvme1n1p5") == "/dev/nvme1n1"

    def test_part_to_dev_nbd(self):
        """Test parent device extraction from NBD devices."""
        g = VMCraft()

        assert g.part_to_dev("/dev/nbd0p1") == "/dev/nbd0"
        assert g.part_to_dev("/dev/nbd0p2") == "/dev/nbd0"
        assert g.part_to_dev("/dev/nbd1p3") == "/dev/nbd1"

    def test_part_to_dev_invalid(self):
        """Test parent device extraction with invalid input."""
        g = VMCraft()

        with pytest.raises(RuntimeError, match="Cannot determine parent device"):
            g.part_to_dev("/dev/sda")

        with pytest.raises(RuntimeError, match="Cannot determine parent device"):
            g.part_to_dev("/invalid/path")


class TestBlockDeviceAPIs:
    """Test block device APIs."""

    def test_blockdev_getss_returns_int(self):
        """Test that blockdev_getss returns an integer."""
        g = VMCraft()

        # Should return default 512 for non-existent device
        result = g.blockdev_getss("/dev/nonexistent")
        assert isinstance(result, int)
        assert result > 0

    def test_blockdev_getsz_returns_int(self):
        """Test that blockdev_getsz returns an integer."""
        g = VMCraft()

        # Should return 0 for non-existent device
        result = g.blockdev_getsz("/dev/nonexistent")
        assert isinstance(result, int)
        assert result >= 0

    def test_blockdev_getbsz_returns_int(self):
        """Test that blockdev_getbsz returns an integer."""
        g = VMCraft()

        # Should return default 4096 for non-existent device
        result = g.blockdev_getbsz("/dev/nonexistent")
        assert isinstance(result, int)
        assert result > 0

    def test_blockdev_getro_returns_bool(self):
        """Test that blockdev_getro returns a boolean."""
        g = VMCraft()

        # Should return False for non-existent device
        result = g.blockdev_getro("/dev/nonexistent")
        assert isinstance(result, bool)


class TestInspectionAPIs:
    """Test filesystem inspection APIs."""

    def test_inspect_filesystems_returns_dict(self):
        """Test that inspect_filesystems returns a dictionary."""
        g = VMCraft()

        result = g.inspect_filesystems()
        assert isinstance(result, dict)
        # Should return empty dict or dict with string keys and list values
        for key, value in result.items():
            assert isinstance(key, str)
            assert isinstance(value, list)
            for item in value:
                assert isinstance(item, str)

    def test_inspect_get_filesystems_returns_list(self):
        """Test that inspect_get_filesystems returns a list."""
        g = VMCraft()

        result = g.inspect_get_filesystems("/dev/sda1")
        assert isinstance(result, list)
        # Should return empty list for non-existent root
        for item in result:
            assert isinstance(item, str)


class TestExtendedAttributes:
    """Test extended attribute APIs (requires launched VMCraft)."""

    def test_get_e2attrs_not_launched(self):
        """Test that get_e2attrs raises error when not launched."""
        g = VMCraft()

        with pytest.raises(RuntimeError, match="Not launched"):
            g.get_e2attrs("/etc/fstab")

    def test_set_e2attrs_not_launched(self):
        """Test that set_e2attrs raises error when not launched."""
        g = VMCraft()

        with pytest.raises(RuntimeError, match="Not launched"):
            g.set_e2attrs("/etc/fstab", "i")


class TestFilesystemSpecificOperations:
    """Test filesystem-specific operation APIs."""

    def test_ntfs_3g_probe_returns_int(self):
        """Test that ntfs_3g_probe returns an integer."""
        g = VMCraft()

        # Should return non-zero for non-existent device
        result = g.ntfs_3g_probe("/dev/nonexistent")
        assert isinstance(result, int)

    def test_btrfs_filesystem_show_returns_list(self):
        """Test that btrfs_filesystem_show returns a list."""
        g = VMCraft()

        result = g.btrfs_filesystem_show()
        assert isinstance(result, list)
        # Should return empty list if no btrfs or command fails
        for item in result:
            assert isinstance(item, dict)
            assert "uuid" in item or "label" in item

    def test_btrfs_subvolume_list_not_launched(self):
        """Test that btrfs_subvolume_list raises error when not launched."""
        g = VMCraft()

        with pytest.raises(RuntimeError, match="Not launched"):
            g.btrfs_subvolume_list("/dev/sda1")

    def test_zfs_pool_list_returns_list(self):
        """Test that zfs_pool_list returns a list."""
        g = VMCraft()

        result = g.zfs_pool_list()
        assert isinstance(result, list)
        # Should return empty list if no ZFS pools or command fails
        for item in result:
            assert isinstance(item, str)

    def test_zfs_dataset_list_returns_list(self):
        """Test that zfs_dataset_list returns a list."""
        g = VMCraft()

        result = g.zfs_dataset_list()
        assert isinstance(result, list)
        # Should return empty list if no ZFS datasets or command fails
        for item in result:
            assert isinstance(item, dict)
            assert "name" in item

    def test_zfs_dataset_list_with_pool(self):
        """Test that zfs_dataset_list with pool parameter returns a list."""
        g = VMCraft()

        result = g.zfs_dataset_list("nonexistent_pool")
        assert isinstance(result, list)

    def test_xfs_info_returns_dict(self):
        """Test that xfs_info returns a dictionary."""
        g = VMCraft()

        result = g.xfs_info("/dev/nonexistent")
        assert isinstance(result, dict)
        # Should return empty dict if no XFS filesystem or command fails

    def test_xfs_admin_returns_dict(self):
        """Test that xfs_admin returns a dictionary."""
        g = VMCraft()

        result = g.xfs_admin("/dev/nonexistent")
        assert isinstance(result, dict)
        # Should have label and uuid keys
        assert "label" in result or "uuid" in result

    def test_xfs_growfs_requires_mountpoint(self):
        """Test that xfs_growfs raises error for invalid mountpoint."""
        g = VMCraft()

        with pytest.raises(RuntimeError):
            g.xfs_growfs("/nonexistent/mountpoint")

    def test_xfs_repair_returns_dict(self):
        """Test that xfs_repair returns a dictionary with expected keys."""
        g = VMCraft()

        # Should return dict even for non-existent device (graceful error handling)
        result = g.xfs_repair("/dev/nonexistent", check_only=True)
        assert isinstance(result, dict)

    def test_xfs_db_returns_string(self):
        """Test that xfs_db returns a string."""
        g = VMCraft()

        result = g.xfs_db("/dev/nonexistent", ["sb 0", "p"])
        assert isinstance(result, str)
        # Should return empty string on failure


class TestAPISignatures:
    """Test that all new APIs have correct signatures."""

    def test_all_methods_exist(self):
        """Test that all expected methods exist in VMCraft."""
        g = VMCraft()

        expected_methods = [
            # Partition operations
            'part_to_partnum',
            'part_to_dev',
            # Block device APIs
            'blockdev_getss',
            'blockdev_getsz',
            'blockdev_getbsz',
            'blockdev_setrw',
            'blockdev_setro',
            'blockdev_getro',
            'blockdev_flushbufs',
            'blockdev_rereadpt',
            # Inspection APIs
            'inspect_filesystems',
            'inspect_get_filesystems',
            # Extended attributes
            'get_e2attrs',
            'set_e2attrs',
            # Filesystem-specific operations
            'ntfs_3g_probe',
            'btrfs_filesystem_show',
            'btrfs_subvolume_list',
            'zfs_pool_list',
            'zfs_dataset_list',
            'xfs_info',
            'xfs_admin',
            'xfs_growfs',
            'xfs_repair',
            'xfs_db',
        ]

        for method_name in expected_methods:
            assert hasattr(g, method_name), f"Method {method_name} not found"
            method = getattr(g, method_name)
            assert callable(method), f"Method {method_name} is not callable"

    def test_methods_have_docstrings(self):
        """Test that all new methods have docstrings."""
        g = VMCraft()

        methods_to_check = [
            'part_to_partnum', 'part_to_dev', 'blockdev_getss',
            'blockdev_getsz', 'blockdev_getbsz', 'blockdev_setrw',
            'blockdev_setro', 'blockdev_getro', 'blockdev_flushbufs',
            'blockdev_rereadpt', 'inspect_filesystems',
            'inspect_get_filesystems', 'get_e2attrs', 'set_e2attrs',
            'ntfs_3g_probe', 'btrfs_filesystem_show',
            'btrfs_subvolume_list', 'zfs_pool_list', 'zfs_dataset_list',
            'xfs_info', 'xfs_admin', 'xfs_growfs', 'xfs_repair', 'xfs_db',
        ]

        for method_name in methods_to_check:
            method = getattr(g, method_name)
            assert method.__doc__ is not None, f"Method {method_name} has no docstring"
            assert len(method.__doc__.strip()) > 0, f"Method {method_name} has empty docstring"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
