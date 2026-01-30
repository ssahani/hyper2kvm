# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Tests for initramfs_add_drivers configuration parsing and driver injection.
"""
import importlib

import pytest


@pytest.fixture
def grub_module():
    """Import grub module for testing"""
    try:
        return importlib.import_module("hyper2kvm.fixers.bootloader.grub")
    except Exception as e:
        pytest.skip(f"Cannot import grub module: {e}")


class TestGetInitramfsAddDrivers:
    """Test suite for _get_initramfs_add_drivers function"""

    def test_default_drivers_when_none_specified(self, grub_module):
        """Test that default drivers are returned when no drivers specified"""
        obj = type("Obj", (), {})()

        drivers = grub_module._get_initramfs_add_drivers(obj)

        # Check that defaults are returned
        assert isinstance(drivers, list)
        assert len(drivers) > 0

        # Check for expected default drivers
        expected_defaults = [
            "virtio",
            "virtio_ring",
            "virtio_blk",
            "virtio_scsi",
            "virtio_net",
            "virtio_pci",
            "nvme",
            "ahci",
            "sd_mod",
            "dm_mod",
            "dm_crypt",
            "xts",
        ]
        for driver in expected_defaults:
            assert driver in drivers, f"Expected default driver '{driver}' not found"

    def test_string_format_single_driver(self, grub_module):
        """Test parsing single driver from string"""
        obj = type("Obj", (), {})()
        obj.initramfs_add_drivers = "e1000e"

        drivers = grub_module._get_initramfs_add_drivers(obj)

        assert isinstance(drivers, list)
        assert "e1000e" in drivers
        assert len(drivers) == 1

    def test_string_format_multiple_drivers_space_separated(self, grub_module):
        """Test parsing multiple drivers from space-separated string"""
        obj = type("Obj", (), {})()
        obj.initramfs_add_drivers = "nvme e1000e mlx5_core ixgbe"

        drivers = grub_module._get_initramfs_add_drivers(obj)

        assert isinstance(drivers, list)
        assert "nvme" in drivers
        assert "e1000e" in drivers
        assert "mlx5_core" in drivers
        assert "ixgbe" in drivers
        assert len(drivers) == 4

    def test_string_format_with_extra_whitespace(self, grub_module):
        """Test parsing handles extra whitespace correctly"""
        obj = type("Obj", (), {})()
        obj.initramfs_add_drivers = "  nvme   e1000e  mlx5_core  "

        drivers = grub_module._get_initramfs_add_drivers(obj)

        assert isinstance(drivers, list)
        assert "nvme" in drivers
        assert "e1000e" in drivers
        assert "mlx5_core" in drivers
        assert len(drivers) == 3

    def test_list_format_multiple_drivers(self, grub_module):
        """Test parsing drivers from Python list"""
        obj = type("Obj", (), {})()
        obj.initramfs_add_drivers = ["e1000e", "ixgbe", "mlx5_core", "i40e"]

        drivers = grub_module._get_initramfs_add_drivers(obj)

        assert isinstance(drivers, list)
        assert "e1000e" in drivers
        assert "ixgbe" in drivers
        assert "mlx5_core" in drivers
        assert "i40e" in drivers
        assert len(drivers) == 4

    def test_list_format_with_whitespace_stripped(self, grub_module):
        """Test that list format strips whitespace from driver names"""
        obj = type("Obj", (), {})()
        obj.initramfs_add_drivers = ["  e1000e  ", " ixgbe", "mlx5_core  "]

        drivers = grub_module._get_initramfs_add_drivers(obj)

        assert isinstance(drivers, list)
        assert "e1000e" in drivers
        assert "ixgbe" in drivers
        assert "mlx5_core" in drivers
        # Should not have whitespace
        assert "  e1000e  " not in drivers
        assert " ixgbe" not in drivers

    def test_list_format_with_empty_entries_filtered(self, grub_module):
        """Test that empty entries in list are filtered out"""
        obj = type("Obj", (), {})()
        obj.initramfs_add_drivers = ["e1000e", "", "ixgbe", "   ", "mlx5_core"]

        drivers = grub_module._get_initramfs_add_drivers(obj)

        assert isinstance(drivers, list)
        assert "e1000e" in drivers
        assert "ixgbe" in drivers
        assert "mlx5_core" in drivers
        assert "" not in drivers
        assert "   " not in drivers
        assert len(drivers) == 3

    def test_legacy_regen_add_drivers_fallback(self, grub_module):
        """Test that legacy regen_add_drivers parameter works as fallback"""
        obj = type("Obj", (), {})()
        obj.regen_add_drivers = "megaraid_sas hpsa"

        drivers = grub_module._get_initramfs_add_drivers(obj)

        assert isinstance(drivers, list)
        assert "megaraid_sas" in drivers
        assert "hpsa" in drivers

    def test_initramfs_add_drivers_takes_precedence_over_legacy(self, grub_module):
        """Test that initramfs_add_drivers takes precedence over regen_add_drivers"""
        obj = type("Obj", (), {})()
        obj.initramfs_add_drivers = "e1000e"
        obj.regen_add_drivers = "should_not_be_used"

        drivers = grub_module._get_initramfs_add_drivers(obj)

        assert isinstance(drivers, list)
        assert "e1000e" in drivers
        assert "should_not_be_used" not in drivers

    def test_empty_string_returns_defaults(self, grub_module):
        """Test that empty string returns defaults"""
        obj = type("Obj", (), {})()
        obj.initramfs_add_drivers = ""

        drivers = grub_module._get_initramfs_add_drivers(obj)

        # Empty string should fall back to defaults
        assert isinstance(drivers, list)
        assert "virtio" in drivers  # Check for a default driver

    def test_none_value_returns_defaults(self, grub_module):
        """Test that None value returns defaults"""
        obj = type("Obj", (), {})()
        obj.initramfs_add_drivers = None

        drivers = grub_module._get_initramfs_add_drivers(obj)

        assert isinstance(drivers, list)
        assert "virtio" in drivers  # Check for a default driver

    def test_deduplication_preserves_order(self, grub_module):
        """Test that duplicate drivers are removed but order is preserved"""
        obj = type("Obj", (), {})()
        obj.initramfs_add_drivers = ["nvme", "e1000e", "nvme", "mlx5_core", "e1000e"]

        drivers = grub_module._get_initramfs_add_drivers(obj)

        assert isinstance(drivers, list)
        assert len(drivers) == 3  # Only unique drivers
        assert drivers.index("nvme") < drivers.index("e1000e")
        assert drivers.index("e1000e") < drivers.index("mlx5_core")

    def test_real_world_network_drivers(self, grub_module):
        """Test realistic network driver configuration"""
        obj = type("Obj", (), {})()
        obj.initramfs_add_drivers = [
            "e1000e",     # Intel Gigabit
            "ixgbe",      # Intel 10G
            "i40e",       # Intel XL710
            "mlx5_core",  # Mellanox ConnectX
        ]

        drivers = grub_module._get_initramfs_add_drivers(obj)

        assert all(d in drivers for d in ["e1000e", "ixgbe", "i40e", "mlx5_core"])

    def test_real_world_storage_drivers(self, grub_module):
        """Test realistic storage driver configuration"""
        obj = type("Obj", (), {})()
        obj.initramfs_add_drivers = "megaraid_sas mpt3sas hpsa aacraid"

        drivers = grub_module._get_initramfs_add_drivers(obj)

        expected = ["megaraid_sas", "mpt3sas", "hpsa", "aacraid"]
        assert all(d in drivers for d in expected)

    def test_real_world_raid_drivers(self, grub_module):
        """Test realistic RAID driver configuration"""
        obj = type("Obj", (), {})()
        obj.initramfs_add_drivers = ["md_mod", "raid0", "raid1", "raid10", "raid456"]

        drivers = grub_module._get_initramfs_add_drivers(obj)

        raid_drivers = ["md_mod", "raid0", "raid1", "raid10", "raid456"]
        assert all(d in drivers for d in raid_drivers)

    def test_yaml_use_case_string_format(self, grub_module):
        """Test YAML string format use case"""
        # Simulates: initramfs_add_drivers: "nvme e1000e mlx5_core"
        obj = type("Obj", (), {})()
        obj.initramfs_add_drivers = "nvme e1000e mlx5_core"

        drivers = grub_module._get_initramfs_add_drivers(obj)

        assert isinstance(drivers, list)
        assert drivers == ["nvme", "e1000e", "mlx5_core"]

    def test_yaml_use_case_list_format(self, grub_module):
        """Test YAML list format use case"""
        # Simulates:
        # initramfs_add_drivers:
        #   - nvme
        #   - e1000e
        #   - mlx5_core
        obj = type("Obj", (), {})()
        obj.initramfs_add_drivers = ["nvme", "e1000e", "mlx5_core"]

        drivers = grub_module._get_initramfs_add_drivers(obj)

        assert isinstance(drivers, list)
        assert drivers == ["nvme", "e1000e", "mlx5_core"]


class TestDriverListIntegrity:
    """Test driver list integrity and deduplication"""

    def test_defaults_have_no_duplicates(self, grub_module):
        """Test that default driver list has no duplicates"""
        obj = type("Obj", (), {})()

        drivers = grub_module._get_initramfs_add_drivers(obj)

        # Check no duplicates
        assert len(drivers) == len(set(drivers))

    def test_mixed_defaults_and_custom_dedup(self, grub_module):
        """Test that custom drivers don't duplicate defaults"""
        obj = type("Obj", (), {})()
        # virtio is in defaults, but we're adding it again
        obj.initramfs_add_drivers = "virtio nvme e1000e"

        drivers = grub_module._get_initramfs_add_drivers(obj)

        # Should only appear once
        assert drivers.count("virtio") == 1
        assert drivers.count("nvme") == 1
