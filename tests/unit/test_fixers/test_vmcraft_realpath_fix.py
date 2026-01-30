# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test VMCraft realpath() handling fix in spec_converter.

Tests the critical bug fix where VMCraft's realpath() would return
the same path unchanged, blocking the partition inference fallback.
"""
import unittest

from hyper2kvm.fixers.filesystem.fstab import FstabMode
from hyper2kvm.fixers.offline.spec_converter import SpecConverter


class FakeGuestFSRealpathReturnsUnchanged:
    """
    Fake GuestFS that simulates VMCraft's realpath() bug.

    VMCraft's realpath() returns the path unchanged when it can't
    resolve it (instead of raising an exception like libguestfs does).
    """

    def __init__(self):
        self.blkid_data = {}

    def realpath(self, path: str) -> str:
        """Return path unchanged (simulates VMCraft behavior)."""
        return path

    def blkid(self, dev: str) -> dict:
        """Return blkid data for device."""
        return self.blkid_data.get(dev, {})


class TestVMCraftRealpathFix(unittest.TestCase):
    """
    Test that spec_converter correctly handles VMCraft's realpath behavior.

    The bug: VMCraft's realpath() returns the same path when it can't resolve,
    so checking `if rp.startswith("/dev/")` would accept it as "resolved".
    Then blkid("/dev/disk/by-path/...") would fail (path doesn't exist),
    and inference never ran because mapped was already set.

    The fix: Only accept realpath result if it DIFFERS from the input path.
    This allows the inference fallback to run.
    """

    def setUp(self):
        """Set up test fixtures."""
        self.fake_g = FakeGuestFSRealpathReturnsUnchanged()

        # Provide blkid data for NBD partitions
        self.fake_g.blkid_data = {
            "/dev/nbd0p2": {
                "UUID": "f293ef3c-255a-4582-8016-f72fb8dd3f85",
                "TYPE": "btrfs",
            },
            "/dev/nbd0p3": {
                "UUID": "03c038b5-fb29-470c-9f81-7100da936770",
                "TYPE": "swap",
            },
        }

    def test_realpath_same_path_rejected(self):
        """
        CRITICAL: Test that realpath returning same path is rejected.

        This tests the bug fix commit that added:
        ```
        if rp.startswith("/dev/") and rp != spec:
        ```
        Instead of just:
        ```
        if rp.startswith("/dev/"):
        ```
        """
        converter = SpecConverter(
            fstab_mode=FstabMode.STABILIZE_ALL,
            root_dev="/dev/nbd0p2"
        )

        spec = "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2"

        # VMCraft's realpath will return the same path
        # Old code would accept this and try blkid on the by-path (fails)
        # New code rejects it and uses inference instead
        new_spec, reason = converter.convert_spec(self.fake_g, spec)

        # Should use inference and successfully convert
        self.assertEqual(new_spec, "UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85")
        self.assertIn("mapped", reason)
        self.assertIn("/dev/nbd0p2", reason)

    def test_inference_fallback_works_with_vmcraft(self):
        """
        Test that partition inference works when realpath returns same path.

        This documents the complete openSUSE fix:
        1. VMCraft's realpath returns path unchanged
        2. Spec_converter rejects it (rp == spec)
        3. Falls back to partition inference
        4. Inference works because root_dev is set
        5. blkid on inferred device succeeds
        6. Conversion to UUID succeeds
        """
        converter = SpecConverter(
            fstab_mode=FstabMode.STABILIZE_ALL,
            root_dev="/dev/nbd0p2"
        )

        # Test multiple partitions
        test_cases = [
            (
                "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2",
                "UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85"
            ),
            (
                "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part3",
                "UUID=03c038b5-fb29-470c-9f81-7100da936770"
            ),
        ]

        for by_path_spec, expected_uuid in test_cases:
            new_spec, reason = converter.convert_spec(self.fake_g, by_path_spec)
            self.assertEqual(
                new_spec,
                expected_uuid,
                f"Failed to convert {by_path_spec} to {expected_uuid}"
            )
            self.assertIn("mapped", reason)

    def test_realpath_returning_different_path_still_works(self):
        """
        Test that legitimate realpath resolution still works.

        If realpath actually resolves to a different device (like libguestfs does),
        that should still be accepted and used.
        """
        # Create a fake that can resolve some paths
        class FakeGuestFSWithRealResolution:
            def __init__(self):
                self.blkid_data = {
                    "/dev/sda2": {
                        "UUID": "real-uuid-for-sda2",
                        "TYPE": "ext4",
                    }
                }

            def realpath(self, path: str) -> str:
                # Actually resolves this specific by-path to sda2
                if path == "/dev/disk/by-path/pci-0000:00:1f.2-ata-1-part2":
                    return "/dev/sda2"
                # Returns unchanged for others
                return path

            def blkid(self, dev: str) -> dict:
                return self.blkid_data.get(dev, {})

        fake_g = FakeGuestFSWithRealResolution()

        converter = SpecConverter(
            fstab_mode=FstabMode.STABILIZE_ALL,
            root_dev="/dev/sda2"
        )

        spec = "/dev/disk/by-path/pci-0000:00:1f.2-ata-1-part2"
        new_spec, reason = converter.convert_spec(fake_g, spec)

        # Should use the realpath result
        self.assertEqual(new_spec, "UUID=real-uuid-for-sda2")
        self.assertIn("mapped", reason)
        self.assertIn("/dev/sda2", reason)


class TestRealpathVsInferencePriority(unittest.TestCase):
    """Test the priority order: realpath -> inference -> unresolved."""

    def test_priority_order_realpath_first(self):
        """Test that successful realpath takes priority over inference."""
        class FakeGuestFSPriority:
            def realpath(self, path: str) -> str:
                # Successfully resolves to different path
                if "part2" in path:
                    return "/dev/mapper/vg-root"
                return path

            def blkid(self, dev: str) -> dict:
                if dev == "/dev/mapper/vg-root":
                    return {"UUID": "realpath-uuid", "TYPE": "ext4"}
                elif dev == "/dev/sda2":
                    return {"UUID": "inference-uuid", "TYPE": "ext4"}
                return {}

        fake_g = FakeGuestFSPriority()

        converter = SpecConverter(
            fstab_mode=FstabMode.STABILIZE_ALL,
            root_dev="/dev/sda2"  # Inference would use this
        )

        spec = "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2"
        new_spec, reason = converter.convert_spec(fake_g, spec)

        # Should use realpath result, not inference
        self.assertEqual(new_spec, "UUID=realpath-uuid")
        self.assertIn("/dev/mapper/vg-root", reason)

    def test_priority_order_inference_when_realpath_same(self):
        """Test that inference runs when realpath returns same path."""
        fake_g = FakeGuestFSRealpathReturnsUnchanged()
        fake_g.blkid_data = {
            "/dev/sda2": {"UUID": "inference-uuid", "TYPE": "ext4"}
        }

        converter = SpecConverter(
            fstab_mode=FstabMode.STABILIZE_ALL,
            root_dev="/dev/sda2"
        )

        spec = "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2"
        new_spec, reason = converter.convert_spec(fake_g, spec)

        # Should use inference
        self.assertEqual(new_spec, "UUID=inference-uuid")
        self.assertIn("/dev/sda2", reason)

    def test_priority_order_unresolved_when_all_fail(self):
        """Test that spec is unchanged when both realpath and inference fail."""
        fake_g = FakeGuestFSRealpathReturnsUnchanged()
        fake_g.blkid_data = {}  # No blkid data

        converter = SpecConverter(
            fstab_mode=FstabMode.STABILIZE_ALL,
            root_dev=None  # No root_dev, inference can't work
        )

        spec = "/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2"
        new_spec, reason = converter.convert_spec(fake_g, spec)

        # Should return unchanged
        self.assertEqual(new_spec, spec)
        self.assertEqual(reason, "by-path-unresolved")


if __name__ == "__main__":
    unittest.main()
