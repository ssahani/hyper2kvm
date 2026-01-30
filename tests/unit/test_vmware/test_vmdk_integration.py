# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Integration tests for VMDK parser using real test images
Tests the VMDK parser with actual generated test images
"""
import unittest
from pathlib import Path
from unittest.mock import Mock

from hyper2kvm.vmware.utils.vmdk_parser import VMDK, VMDKError, VMDKType


class TestVMDKWithTestImages(unittest.TestCase):
    """Test VMDK parser with generated test images."""

    @classmethod
    def setUpClass(cls):
        """Set up test data directory path."""
        cls.test_data_dir = Path(__file__).parent.parent.parent / "test-data"
        if not cls.test_data_dir.exists():
            raise unittest.SkipTest(f"Test data directory not found: {cls.test_data_dir}")

    def setUp(self):
        self.logger = Mock()

    def test_parse_simple_raw_image(self):
        """Test parsing simple raw disk image."""
        simple_raw = self.test_data_dir / "simple.raw"
        if not simple_raw.exists():
            self.skipTest("simple.raw not found")

        # Raw images are not VMDK descriptors
        is_desc = VMDK._is_text_descriptor(simple_raw)
        self.assertFalse(is_desc)

    def test_parse_vmdk_descriptor_flat(self):
        """Test parsing VMDK descriptor with flat extent."""
        vmdk = self.test_data_dir / "test.vmdk"
        if not vmdk.exists():
            self.skipTest("test.vmdk not found")

        # Parse the descriptor
        info = VMDK.parse_descriptor(self.logger, vmdk)

        # Check basic properties
        self.assertEqual(info.get("create_type"), "monolithicFlat")
        self.assertIsNotNone(info.get("size"))

        # Check extents
        extents = VMDK.get_all_extents(self.logger, vmdk)
        self.assertEqual(len(extents), 1)
        self.assertTrue(str(extents[0]).endswith("test-flat.vmdk"))

        # Extent should exist
        existing_extents = VMDK.get_existing_extents(self.logger, vmdk)
        self.assertEqual(len(existing_extents), 1)
        self.assertTrue(existing_extents[0].exists())

    def test_parse_multi_extent_vmdk(self):
        """Test parsing multi-extent VMDK."""
        vmdk = self.test_data_dir / "test-multi.vmdk"
        if not vmdk.exists():
            self.skipTest("test-multi.vmdk not found")

        # Parse the descriptor
        info = VMDK.parse_descriptor(self.logger, vmdk)

        # Check create type
        self.assertEqual(info.get("create_type"), "twoGbMaxExtentSparse")

        # Check extents
        extents = VMDK.get_all_extents(self.logger, vmdk)
        self.assertEqual(len(extents), 3)

        # All extents should exist
        existing_extents = VMDK.get_existing_extents(self.logger, vmdk)
        self.assertEqual(len(existing_extents), 3)

        # Verify extent names
        extent_names = [e.name for e in extents]
        self.assertIn("test-s001.vmdk", extent_names)
        self.assertIn("test-s002.vmdk", extent_names)
        self.assertIn("test-s003.vmdk", extent_names)

    def test_validate_descriptor_extent_pair(self):
        """Test validation of descriptor/extent pair."""
        descriptor = self.test_data_dir / "test.vmdk"
        extent = self.test_data_dir / "test-flat.vmdk"

        if not descriptor.exists() or not extent.exists():
            self.skipTest("test.vmdk or test-flat.vmdk not found")

        # Validate the pair
        is_valid = VMDK.validate_vmdk_pair(self.logger, descriptor, extent)
        self.assertTrue(is_valid)

    def test_guess_layout_descriptor_with_extent(self):
        """Test layout detection for descriptor with extent."""
        vmdk = self.test_data_dir / "test.vmdk"
        if not vmdk.exists():
            self.skipTest("test.vmdk not found")

        layout_type, extent_path = VMDK.guess_layout_typed(self.logger, vmdk)

        # Should be detected as descriptor
        self.assertEqual(layout_type, VMDKType.DESCRIPTOR)

        # Extent path should point to flat extent
        self.assertIsNotNone(extent_path)
        self.assertTrue(str(extent_path).endswith("test-flat.vmdk"))
        self.assertTrue(extent_path.exists())

    def test_is_sparse_detection(self):
        """Test sparse vs flat disk detection."""
        # Test flat descriptor
        flat_vmdk = self.test_data_dir / "test.vmdk"
        if flat_vmdk.exists():
            is_sparse = VMDK.is_sparse_vmdk(self.logger, flat_vmdk)
            self.assertFalse(is_sparse)

        # Test sparse descriptor
        sparse_vmdk = self.test_data_dir / "test-multi.vmdk"
        if sparse_vmdk.exists():
            is_sparse = VMDK.is_sparse_vmdk(self.logger, sparse_vmdk)
            self.assertTrue(is_sparse)


class TestVMDKSecurityWithTestImages(unittest.TestCase):
    """Test VMDK security features with generated test images."""

    @classmethod
    def setUpClass(cls):
        """Set up test data directory path."""
        cls.test_data_dir = Path(__file__).parent.parent.parent / "test-data"
        if not cls.test_data_dir.exists():
            raise unittest.SkipTest(f"Test data directory not found: {cls.test_data_dir}")

    def setUp(self):
        self.logger = Mock()

    def test_path_traversal_descriptor_rejected(self):
        """Test that path traversal descriptors are rejected."""
        malicious_vmdk = self.test_data_dir / "malicious" / "traversal.vmdk"
        if not malicious_vmdk.exists():
            self.skipTest("malicious/traversal.vmdk not found")

        # Attempting to get extents should raise error or handle gracefully
        try:
            extents = VMDK.get_all_extents(self.logger, malicious_vmdk)
            # If we get here, check that the path is rejected
            for extent in extents:
                # The extent path should not resolve outside the base directory
                # The security check happens during resolution
                if extent.exists():
                    # Verify it's not actually /etc/passwd
                    self.assertNotEqual(extent.name, "passwd")
        except VMDKError as e:
            # Expected: path traversal should be blocked
            self.assertIn("Path traversal", str(e))

    def test_subdirectory_reference_allowed(self):
        """Test that legitimate subdirectory references work."""
        subdir_vmdk = self.test_data_dir / "subdir-test.vmdk"
        if not subdir_vmdk.exists():
            self.skipTest("subdir-test.vmdk not found")

        # Parse the descriptor
        info = VMDK.parse_descriptor(self.logger, subdir_vmdk)
        self.assertIsNotNone(info)

        # Get extents
        extents = VMDK.get_all_extents(self.logger, subdir_vmdk)
        self.assertEqual(len(extents), 1)

        # Extent should be in subdir
        extent_path = extents[0]
        self.assertTrue("subdir" in str(extent_path))

    def test_large_descriptor_rejected(self):
        """Test that excessively large descriptors are rejected."""
        large_vmdk = self.test_data_dir / "large.vmdk"
        if not large_vmdk.exists():
            self.skipTest("large.vmdk not found")

        # Check file size
        file_size = large_vmdk.stat().st_size
        self.assertGreater(file_size, 8 * 1024 * 1024)  # > 8 MiB

        # Should not be treated as a valid text descriptor
        # VMDK._is_text_descriptor has a size limit
        is_desc = VMDK._is_text_descriptor(large_vmdk)
        # Large files should be rejected
        self.assertFalse(is_desc)

    def test_binary_file_not_descriptor(self):
        """Test that binary files are not treated as descriptors."""
        binary_vmdk = self.test_data_dir / "binary.vmdk"
        if not binary_vmdk.exists():
            self.skipTest("binary.vmdk not found")

        # Binary file should not be detected as text descriptor
        is_desc = VMDK._is_text_descriptor(binary_vmdk)
        self.assertFalse(is_desc)

        # Verify it contains binary data
        with open(binary_vmdk, "rb") as f:
            header = f.read(8)
            # Should start with KDMV magic or contain null bytes
            self.assertTrue(b"\x00" in header or header.startswith(b"KDMV"))


class TestVMDKExtentResolution(unittest.TestCase):
    """Test extent path resolution with real test images."""

    @classmethod
    def setUpClass(cls):
        """Set up test data directory path."""
        cls.test_data_dir = Path(__file__).parent.parent.parent / "test-data"
        if not cls.test_data_dir.exists():
            raise unittest.SkipTest(f"Test data directory not found: {cls.test_data_dir}")

    def setUp(self):
        self.logger = Mock()

    def test_extent_exists_check(self):
        """Test checking if extents exist."""
        vmdk = self.test_data_dir / "test.vmdk"
        if not vmdk.exists():
            self.skipTest("test.vmdk not found")

        # Get all extents
        all_extents = VMDK.get_all_extents(self.logger, vmdk)
        self.assertGreater(len(all_extents), 0)

        # Get only existing extents
        existing_extents = VMDK.get_existing_extents(self.logger, vmdk)
        self.assertEqual(len(all_extents), len(existing_extents))

        # All should exist
        for extent in existing_extents:
            self.assertTrue(extent.exists())

    def test_multi_extent_all_exist(self):
        """Test that all extents in multi-extent VMDK exist."""
        vmdk = self.test_data_dir / "test-multi.vmdk"
        if not vmdk.exists():
            self.skipTest("test-multi.vmdk not found")

        # Get existing extents
        existing_extents = VMDK.get_existing_extents(self.logger, vmdk)
        self.assertEqual(len(existing_extents), 3)

        # Verify all are readable
        for extent in existing_extents:
            self.assertTrue(extent.exists())
            self.assertTrue(extent.is_file())
            # Should be able to read
            self.assertGreater(extent.stat().st_size, 0)

    def test_extent_size_matches_descriptor(self):
        """Test that extent sizes match descriptor specifications."""
        vmdk = self.test_data_dir / "test-multi.vmdk"
        if not vmdk.exists():
            self.skipTest("test-multi.vmdk not found")

        # Parse descriptor
        info = VMDK.parse_descriptor(self.logger, vmdk)

        # Get total size from descriptor
        descriptor_size = info.get("size")
        self.assertIsNotNone(descriptor_size)

        # Each extent should be 100 MiB (204800 sectors * 512 bytes)
        expected_extent_size = 100 * 1024 * 1024

        # Check each extent
        extents = VMDK.get_existing_extents(self.logger, vmdk)
        for extent in extents:
            extent_size = extent.stat().st_size
            self.assertEqual(extent_size, expected_extent_size)


if __name__ == "__main__":
    unittest.main()
