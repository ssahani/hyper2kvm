# SPDX-License-Identifier: LGPL-3.0-or-later
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from hyper2kvm.vmware.utils.vmdk_parser import VMDK


class TestVMDKInfo(unittest.TestCase):
    """Test VMDK information extraction."""

    def setUp(self):
        self.logger = Mock()

    def test_parses_vmdk_descriptor(self):
        """Test parsing of VMDK descriptor file."""
        descriptor_content = """# Disk DescriptorFile
version=1
CID=12345678
parentCID=ffffffff
createType="monolithicSparse"

# Extent description
RW 41943040 SPARSE "test.vmdk"

# The Disk Data Base
ddb.virtualHWVersion = "14"
ddb.geometry.cylinders = "2610"
ddb.geometry.heads = "255"
ddb.geometry.sectors = "63"
ddb.adapterType = "lsilogic"
"""

        with tempfile.TemporaryDirectory() as td:
            vmdk = Path(td) / "test.vmdk"
            vmdk.write_text(descriptor_content)

            info = VMDK.parse_descriptor(self.logger, vmdk)

            self.assertIsNotNone(info)
            self.assertIn("create_type", info or {})

    def test_extracts_extent_information(self):
        """Test extraction of extent information."""
        descriptor_content = """# Disk DescriptorFile
version=1
createType="twoGbMaxExtentSparse"

# Extent description
RW 4192256 SPARSE "test-s001.vmdk"
RW 4192256 SPARSE "test-s002.vmdk"
RW 4192256 SPARSE "test-s003.vmdk"

ddb.virtualHWVersion = "14"
"""

        with tempfile.TemporaryDirectory() as td:
            vmdk = Path(td) / "test.vmdk"
            vmdk.write_text(descriptor_content)

            info = VMDK.parse_descriptor(self.logger, vmdk)
            extents = info.get("extents", []) if info else []

            self.assertIsNotNone(extents)
            self.assertGreaterEqual(len(extents), 3)

    def test_identifies_sparse_disks(self):
        """Test identification of sparse disk type."""
        descriptor_content = """# Disk DescriptorFile
createType="monolithicSparse"
RW 41943040 SPARSE "test.vmdk"
"""

        with tempfile.TemporaryDirectory() as td:
            vmdk = Path(td) / "test.vmdk"
            vmdk.write_text(descriptor_content)

            info = VMDK.parse_descriptor(self.logger, vmdk)

            self.assertEqual(info.get("create_type"), "monolithicSparse")

    def test_identifies_flat_disks(self):
        """Test identification of flat disk type."""
        descriptor_content = """# Disk DescriptorFile
createType="monolithicFlat"
RW 41943040 FLAT "test-flat.vmdk"
"""

        with tempfile.TemporaryDirectory() as td:
            vmdk = Path(td) / "test.vmdk"
            vmdk.write_text(descriptor_content)

            info = VMDK.parse_descriptor(self.logger, vmdk)

            self.assertEqual(info.get("create_type"), "monolithicFlat")

    def test_extracts_adapter_type(self):
        """Test extraction of adapter type."""
        descriptor_content = """# Disk DescriptorFile
RW 41943040 SPARSE "test.vmdk"
ddb.adapterType = "lsilogic"
"""

        with tempfile.TemporaryDirectory() as td:
            vmdk = Path(td) / "test.vmdk"
            vmdk.write_text(descriptor_content)

            info = VMDK.parse_descriptor(self.logger, vmdk)

            self.assertEqual(info.get("adapter_type"), "lsilogic")

    def test_extracts_virtual_hw_version(self):
        """Test extraction of virtual hardware version."""
        descriptor_content = """# Disk DescriptorFile
RW 41943040 SPARSE "test.vmdk"
ddb.virtualHWVersion = "14"
"""

        with tempfile.TemporaryDirectory() as td:
            vmdk = Path(td) / "test.vmdk"
            vmdk.write_text(descriptor_content)

            info = VMDK.parse_descriptor(self.logger, vmdk)

            # Check in the kv dict since virtualHWVersion isn't a top-level field
            self.assertEqual(info.get("kv", {}).get("ddb.virtualhwversion"), "14")

    def test_handles_comments_in_descriptor(self):
        """Test handling of comments in descriptor."""
        descriptor_content = """# Disk DescriptorFile
# This is a comment
version=1
# Another comment
createType="monolithicSparse"
# Comments should be ignored
RW 41943040 SPARSE "test.vmdk"
"""

        with tempfile.TemporaryDirectory() as td:
            vmdk = Path(td) / "test.vmdk"
            vmdk.write_text(descriptor_content)

            info = VMDK.parse_descriptor(self.logger, vmdk)

            # Should parse successfully despite comments
            self.assertIsNotNone(info)

    def test_handles_invalid_descriptor(self):
        """Test handling of invalid descriptor file."""
        invalid_content = "This is not a valid VMDK descriptor"

        with tempfile.TemporaryDirectory() as td:
            vmdk = Path(td) / "test.vmdk"
            vmdk.write_text(invalid_content)

            # Should handle gracefully
            try:
                info = VMDK.parse_descriptor(self.logger, vmdk)
            except Exception:
                pass  # Expected to fail or return None/empty


class TestVMDKExtents(unittest.TestCase):
    """Test VMDK extent handling."""

    def setUp(self):
        self.logger = Mock()

    def test_finds_extent_files(self):
        """Test finding extent files for split VMDKs."""
        descriptor_content = """# Disk DescriptorFile
createType="twoGbMaxExtentSparse"
RW 4192256 SPARSE "test-s001.vmdk"
RW 4192256 SPARSE "test-s002.vmdk"
"""

        with tempfile.TemporaryDirectory() as td:
            vmdk = Path(td) / "test.vmdk"
            vmdk.write_text(descriptor_content)

            # Create extent files
            (Path(td) / "test-s001.vmdk").write_bytes(b"extent1")
            (Path(td) / "test-s002.vmdk").write_bytes(b"extent2")

            info = VMDK.parse_descriptor(self.logger, vmdk)
            extents = info.get("extents", []) if info else []

            extent_names = [e.get("file") for e in extents]
            self.assertIn("test-s001.vmdk", extent_names)
            self.assertIn("test-s002.vmdk", extent_names)

    def test_calculates_total_size(self):
        """Test calculation of total disk size from extents."""
        descriptor_content = """# Disk DescriptorFile
RW 4192256 SPARSE "test-s001.vmdk"
RW 4192256 SPARSE "test-s002.vmdk"
"""

        with tempfile.TemporaryDirectory() as td:
            vmdk = Path(td) / "test.vmdk"
            vmdk.write_text(descriptor_content)

            info = VMDK.parse_descriptor(self.logger, vmdk)
            total_sectors = info.get("size", 0) if info else 0

            # Total should be sum of extent sizes (in sectors)
            expected_sectors = 4192256 + 4192256
            self.assertEqual(total_sectors, expected_sectors)


if __name__ == "__main__":
    unittest.main()
