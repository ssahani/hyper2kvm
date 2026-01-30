# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test NBD device support for VMCraft backend.

Tests the fixes for openSUSE Leap 15.4 migration where NBD devices
(nbd0p1, nbd0p2) need to be recognized and handled correctly.
"""
import unittest

from hyper2kvm.fixers.filesystem.fstab import Ident


class TestNBDDeviceSupport(unittest.TestCase):
    """Test NBD device pattern recognition and partition inference."""

    def test_root_dev_base_recognizes_nbd_devices(self):
        """Test that NBD devices are correctly parsed to base device."""
        # NBD devices use 'p' separator like nvme
        self.assertEqual(Ident.root_dev_base("/dev/nbd0p1"), "/dev/nbd0")
        self.assertEqual(Ident.root_dev_base("/dev/nbd0p2"), "/dev/nbd0")
        self.assertEqual(Ident.root_dev_base("/dev/nbd1p5"), "/dev/nbd1")
        self.assertEqual(Ident.root_dev_base("/dev/nbd15p3"), "/dev/nbd15")

    def test_root_dev_base_recognizes_loop_devices(self):
        """Test that loop devices with partitions are correctly parsed."""
        # Loop devices also use 'p' separator
        self.assertEqual(Ident.root_dev_base("/dev/loop0p1"), "/dev/loop0")
        self.assertEqual(Ident.root_dev_base("/dev/loop5p2"), "/dev/loop5")
        self.assertEqual(Ident.root_dev_base("/dev/loop10p3"), "/dev/loop10")

    def test_root_dev_base_still_handles_nvme(self):
        """Test that existing nvme support still works."""
        self.assertEqual(Ident.root_dev_base("/dev/nvme0n1p1"), "/dev/nvme0n1")
        self.assertEqual(Ident.root_dev_base("/dev/nvme0n1p2"), "/dev/nvme0n1")
        self.assertEqual(Ident.root_dev_base("/dev/nvme1n1p5"), "/dev/nvme1n1")

    def test_root_dev_base_still_handles_mmcblk(self):
        """Test that existing mmcblk support still works."""
        self.assertEqual(Ident.root_dev_base("/dev/mmcblk0p1"), "/dev/mmcblk0")
        self.assertEqual(Ident.root_dev_base("/dev/mmcblk0p2"), "/dev/mmcblk0")
        self.assertEqual(Ident.root_dev_base("/dev/mmcblk1p3"), "/dev/mmcblk1")

    def test_root_dev_base_handles_traditional_devices(self):
        """Test that traditional devices (sda, vda) still work."""
        self.assertEqual(Ident.root_dev_base("/dev/sda1"), "/dev/sda")
        self.assertEqual(Ident.root_dev_base("/dev/sda2"), "/dev/sda")
        self.assertEqual(Ident.root_dev_base("/dev/vda5"), "/dev/vda")
        self.assertEqual(Ident.root_dev_base("/dev/xvda3"), "/dev/xvda")
        self.assertEqual(Ident.root_dev_base("/dev/hda1"), "/dev/hda")

    def test_root_dev_base_returns_none_for_invalid(self):
        """Test that invalid paths return None."""
        self.assertIsNone(Ident.root_dev_base(None))
        self.assertIsNone(Ident.root_dev_base(""))
        self.assertIsNone(Ident.root_dev_base("/dev/sda"))  # No partition number
        self.assertIsNone(Ident.root_dev_base("/some/random/path"))

    def test_infer_partition_from_bypath_with_nbd_device(self):
        """
        Test partition inference with NBD root device.

        This is the critical fix for openSUSE Leap 15.4 migration where
        VMware by-path devices need to be mapped to NBD devices.
        """
        # VMware by-path part2 -> NBD partition 2
        inferred = Ident.infer_partition_from_bypath(
            "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2",
            root_dev="/dev/nbd0p2"
        )
        self.assertEqual(inferred, "/dev/nbd0p2")

        # VMware by-path part3 -> NBD partition 3
        inferred = Ident.infer_partition_from_bypath(
            "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part3",
            root_dev="/dev/nbd0p2"  # Root is p2, but we can infer p3
        )
        self.assertEqual(inferred, "/dev/nbd0p3")

        # Part1 from by-path with nbd0p2 as root
        inferred = Ident.infer_partition_from_bypath(
            "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part1",
            root_dev="/dev/nbd0p2"
        )
        self.assertEqual(inferred, "/dev/nbd0p1")

    def test_infer_partition_from_bypath_with_traditional_device(self):
        """Test that traditional device inference still works."""
        # VMware by-path part2 -> sda2
        inferred = Ident.infer_partition_from_bypath(
            "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2",
            root_dev="/dev/sda2"
        )
        self.assertEqual(inferred, "/dev/sda2")

        # VMware by-path part3 -> sda3
        inferred = Ident.infer_partition_from_bypath(
            "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part3",
            root_dev="/dev/sda2"
        )
        self.assertEqual(inferred, "/dev/sda3")

    def test_infer_partition_from_bypath_with_nvme_device(self):
        """Test partition inference with nvme devices."""
        # VMware by-path part2 -> nvme0n1p2
        inferred = Ident.infer_partition_from_bypath(
            "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2",
            root_dev="/dev/nvme0n1p2"
        )
        self.assertEqual(inferred, "/dev/nvme0n1p2")

        # Part5 inference
        inferred = Ident.infer_partition_from_bypath(
            "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part5",
            root_dev="/dev/nvme0n1p2"
        )
        self.assertEqual(inferred, "/dev/nvme0n1p5")

    def test_infer_partition_returns_none_without_root_dev(self):
        """Test that inference requires root_dev to be set."""
        inferred = Ident.infer_partition_from_bypath(
            "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2",
            root_dev=None
        )
        self.assertIsNone(inferred)

    def test_infer_partition_returns_none_for_non_bypath(self):
        """Test that non-bypath specs return None."""
        inferred = Ident.infer_partition_from_bypath(
            "/dev/sda2",
            root_dev="/dev/sda2"
        )
        self.assertIsNone(inferred)

    def test_infer_partition_returns_none_without_part_suffix(self):
        """Test that by-path without -partN suffix returns None."""
        inferred = Ident.infer_partition_from_bypath(
            "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0",
            root_dev="/dev/sda2"
        )
        self.assertIsNone(inferred)


class TestOpenSUSEMigrationScenario(unittest.TestCase):
    """
    Integration-style test for the full openSUSE Leap 15.4 migration scenario.

    This documents the exact bug that was fixed:
    1. openSUSE uses /dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-partN in fstab
    2. VMCraft connects VMDK to /dev/nbd0
    3. Partitions appear as /dev/nbd0p1, /dev/nbd0p2, etc.
    4. by-path symlinks don't exist (VMware-specific topology)
    5. Must infer /dev/nbd0pN from partition number + root_dev
    """

    def test_opensuse_migration_complete_flow(self):
        """Test the complete openSUSE by-path -> NBD -> UUID flow."""
        # Step 1: Root detected as /dev/nbd0p2
        root_dev = "/dev/nbd0p2"

        # Step 2: Parse root device base
        base = Ident.root_dev_base(root_dev)
        self.assertEqual(base, "/dev/nbd0")

        # Step 3: Infer various partitions from by-path specs
        test_cases = [
            ("/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part1", "/dev/nbd0p1"),
            ("/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2", "/dev/nbd0p2"),
            ("/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part3", "/dev/nbd0p3"),
        ]

        for by_path_spec, expected_nbd in test_cases:
            inferred = Ident.infer_partition_from_bypath(by_path_spec, root_dev)
            self.assertEqual(
                inferred,
                expected_nbd,
                f"Failed to infer {expected_nbd} from {by_path_spec} with root_dev={root_dev}"
            )


if __name__ == "__main__":
    unittest.main()
