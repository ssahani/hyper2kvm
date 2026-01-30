# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test fstab conversion spec_converter logic.

This test prevents regression of the issue where by-path entries
were not being converted to stable identifiers (UUID/PARTUUID).

Integration tests (requiring libguestfs) are in tests/integration/.
"""
import unittest
from unittest.mock import Mock

from hyper2kvm.fixers.filesystem.fstab import FstabMode, Ident
from hyper2kvm.fixers.offline.spec_converter import SpecConverter


class FakeGuestFS:
    """Minimal fake guestfs for testing spec conversion."""

    def __init__(self):
        self.blkid_data = {}
        self.realpath_map = {}

    def realpath(self, path: str) -> str:
        """Map by-path to real device. Raise if path not found (like real guestfs)."""
        if path not in self.realpath_map:
            raise Exception(f"realpath: {path}: No such file or directory")
        return self.realpath_map[path]

    def blkid(self, dev: str) -> dict:
        """Return blkid data for device."""
        return self.blkid_data.get(dev, {})


class TestSpecConverter(unittest.TestCase):
    """Test SpecConverter logic for converting device specs."""

    def setUp(self):
        """Set up test fixtures."""
        self.fake_g = FakeGuestFS()

        # Map by-path to real devices
        self.fake_g.realpath_map = {
            "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2": "/dev/sda2",
            "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part3": "/dev/sda3",
        }

        # Provide blkid data with UUIDs
        self.fake_g.blkid_data = {
            "/dev/sda2": {
                "UUID": "12345678-1234-1234-1234-123456789abc",
                "TYPE": "btrfs",
            },
            "/dev/sda3": {
                "UUID": "87654321-4321-4321-4321-cba987654321",
                "TYPE": "swap",
            },
        }

    def test_bypath_uses_inference_when_realpath_fails(self):
        """
        CRITICAL: Test that by-path inference works when g.realpath() fails.

        This simulates the real-world scenario where /dev/disk/by-path/ symlinks
        don't exist in the offline libguestfs mount (they're created by udev at boot).
        """
        # Remove realpath mapping to simulate g.realpath() failure
        self.fake_g.realpath_map = {}

        converter = SpecConverter(
            fstab_mode=FstabMode.STABILIZE_ALL,
            root_dev="/dev/sda2"  # CRITICAL: Must be set for inference to work
        )

        spec = "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2"

        # Convert the spec using inference
        new_spec, reason = converter.convert_spec(self.fake_g, spec)

        # Should still convert to UUID using inference
        self.assertEqual(new_spec, "UUID=12345678-1234-1234-1234-123456789abc")
        self.assertIn("mapped", reason)

    def test_bypath_fails_without_root_dev_and_realpath(self):
        """
        REGRESSION TEST: Documents the bug that was fixed in commit 3a545d3.

        When root_dev=None and g.realpath() fails (common in offline mounts),
        by-path entries CANNOT be converted and are returned unchanged.

        This is the bug that happened when:
        1. SpecConverter initialized with root_dev=None
        2. Root detected but spec_converter.root_dev never updated
        3. rewrite_fstab() called → by-path entries unchanged

        This test ensures we understand the failure mode.
        """
        # Remove realpath mapping to simulate g.realpath() failure
        self.fake_g.realpath_map = {}

        converter = SpecConverter(
            fstab_mode=FstabMode.STABILIZE_ALL,
            root_dev=None  # BUG: root_dev not set!
        )

        spec = "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2"

        # Convert the spec
        new_spec, reason = converter.convert_spec(self.fake_g, spec)

        # WITHOUT root_dev, inference fails and spec is unchanged
        self.assertEqual(new_spec, spec)  # Returned unchanged!
        self.assertEqual(reason, "by-path-unresolved")

    def test_bypath_converted_to_uuid_in_stabilize_all_mode(self):
        """
        REGRESSION TEST: by-path entries MUST be converted to UUID.

        This test documents the critical bug where making guestfs "optional"
        with TYPE_CHECKING broke fstab conversion. The g.realpath() and
        g.blkid() calls would fail silently, leaving by-path entries unchanged.
        """
        converter = SpecConverter(
            fstab_mode=FstabMode.STABILIZE_ALL,
            root_dev="/dev/sda2"
        )

        spec = "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2"

        # Convert the spec
        new_spec, reason = converter.convert_spec(self.fake_g, spec)

        # CRITICAL: Must convert to UUID, not leave as by-path
        self.assertEqual(new_spec, "UUID=12345678-1234-1234-1234-123456789abc")
        self.assertIn("mapped", reason)
        self.assertNotIn("/dev/disk/by-path/", new_spec)

    def test_bypath_converted_even_in_bypath_only_mode(self):
        """Test that by-path entries ARE converted even in BYPATH_ONLY mode."""
        converter = SpecConverter(
            fstab_mode=FstabMode.BYPATH_ONLY,
            root_dev="/dev/sda2"
        )

        spec = "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part3"

        # Convert the spec
        new_spec, reason = converter.convert_spec(self.fake_g, spec)

        # by-path entries should still be stabilized to UUID
        self.assertEqual(new_spec, "UUID=87654321-4321-4321-4321-cba987654321")
        self.assertIn("mapped", reason)

    def test_conversion_uses_partuuid_when_no_uuid(self):
        """Test that PARTUUID is used when UUID is not available."""
        # Set up device with only PARTUUID
        self.fake_g.blkid_data["/dev/sda2"] = {
            "PARTUUID": "abcd-1234",
            "TYPE": "btrfs",
        }

        converter = SpecConverter(
            fstab_mode=FstabMode.STABILIZE_ALL,
            root_dev="/dev/sda2"
        )

        spec = "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2"
        new_spec, reason = converter.convert_spec(self.fake_g, spec)

        # Should use PARTUUID when UUID not available
        self.assertEqual(new_spec, "PARTUUID=abcd-1234")
        self.assertIn("mapped", reason)

    def test_already_stable_uuid_unchanged(self):
        """Test that UUID entries are recognized as stable and unchanged."""
        converter = SpecConverter(
            fstab_mode=FstabMode.STABILIZE_ALL,
            root_dev="/dev/sda2"
        )

        spec = "UUID=12345678-1234-1234-1234-123456789abc"
        new_spec, reason = converter.convert_spec(self.fake_g, spec)

        # Should be unchanged (already stable)
        self.assertEqual(new_spec, spec)
        self.assertEqual(reason, "already-stable")

    def test_already_stable_label_unchanged(self):
        """Test that LABEL entries are recognized as stable."""
        converter = SpecConverter(
            fstab_mode=FstabMode.STABILIZE_ALL,
            root_dev="/dev/sda2"
        )

        spec = "LABEL=my-root"
        new_spec, reason = converter.convert_spec(self.fake_g, spec)

        self.assertEqual(new_spec, spec)
        self.assertEqual(reason, "already-stable")

    def test_dev_path_not_converted_in_bypath_only_mode(self):
        """Test that /dev/sdX is NOT converted in BYPATH_ONLY mode."""
        converter = SpecConverter(
            fstab_mode=FstabMode.BYPATH_ONLY,
            root_dev="/dev/sda2"
        )

        spec = "/dev/sda1"
        new_spec, reason = converter.convert_spec(self.fake_g, spec)

        # In BYPATH_ONLY mode, /dev/sdX should be unchanged
        self.assertEqual(new_spec, spec)
        self.assertEqual(reason, "unchanged")

    def test_dev_path_converted_in_stabilize_all_mode(self):
        """Test that /dev/sdX IS converted in STABILIZE_ALL mode."""
        # Add blkid data for /dev/sda1
        self.fake_g.blkid_data["/dev/sda1"] = {
            "UUID": "aaaa-bbbb-cccc-dddd",
            "TYPE": "ext4",
        }

        converter = SpecConverter(
            fstab_mode=FstabMode.STABILIZE_ALL,
            root_dev="/dev/sda2"
        )

        spec = "/dev/sda1"
        new_spec, reason = converter.convert_spec(self.fake_g, spec)

        # In STABILIZE_ALL mode, /dev/sdX should be converted
        self.assertEqual(new_spec, "UUID=aaaa-bbbb-cccc-dddd")
        self.assertIn("blkid", reason)


class TestIdentHelpers(unittest.TestCase):
    """Test Ident helper functions."""

    def test_is_stable_recognizes_uuid(self):
        """Test that UUID= is recognized as stable."""
        self.assertTrue(Ident.is_stable("UUID=12345678-1234-1234-1234-123456789abc"))
        self.assertTrue(Ident.is_stable("uuid=12345678-1234-1234-1234-123456789abc"))

    def test_is_stable_recognizes_partuuid(self):
        """Test that PARTUUID= is recognized as stable."""
        self.assertTrue(Ident.is_stable("PARTUUID=abcd-1234"))
        self.assertTrue(Ident.is_stable("partuuid=abcd-1234"))

    def test_is_stable_recognizes_label(self):
        """Test that LABEL= is recognized as stable."""
        self.assertTrue(Ident.is_stable("LABEL=my-root"))
        self.assertTrue(Ident.is_stable("label=my-root"))

    def test_is_stable_rejects_bypath(self):
        """Test that by-path is NOT recognized as stable."""
        self.assertFalse(Ident.is_stable("/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2"))

    def test_is_stable_rejects_dev_path(self):
        """Test that /dev/sdX is NOT recognized as stable."""
        self.assertFalse(Ident.is_stable("/dev/sda1"))
        self.assertFalse(Ident.is_stable("/dev/vda2"))
        self.assertFalse(Ident.is_stable("/dev/nvme0n1p3"))

    def test_choose_stable_prefers_uuid(self):
        """Test that UUID is preferred over other identifiers."""
        blkid = {
            "UUID": "12345678-1234-1234-1234-123456789abc",
            "PARTUUID": "abcd-1234",
            "LABEL": "my-root",
        }

        stable = Ident.choose_stable(blkid)
        self.assertEqual(stable, "UUID=12345678-1234-1234-1234-123456789abc")

    def test_choose_stable_falls_back_to_partuuid(self):
        """Test that PARTUUID is used when UUID not available."""
        blkid = {
            "PARTUUID": "abcd-1234",
            "LABEL": "my-root",
        }

        stable = Ident.choose_stable(blkid)
        self.assertEqual(stable, "PARTUUID=abcd-1234")

    def test_choose_stable_falls_back_to_label(self):
        """Test that LABEL is used when UUID and PARTUUID not available."""
        blkid = {
            "LABEL": "my-root",
        }

        stable = Ident.choose_stable(blkid)
        self.assertEqual(stable, "LABEL=my-root")

    def test_choose_stable_returns_none_when_no_identifiers(self):
        """Test that None is returned when no stable identifiers available."""
        blkid = {}
        stable = Ident.choose_stable(blkid)
        self.assertIsNone(stable)


if __name__ == "__main__":
    unittest.main()
