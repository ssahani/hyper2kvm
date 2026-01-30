# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Tests for VMDK Inspector.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from hyper2kvm.validation.vmdk_inspector import (
    BootMode,
    Risk,
    RiskLevel,
    VMDKInspectionResult,
    VMDKInspector,
)


@pytest.fixture
def logger():
    """Create a test logger."""
    return logging.getLogger(__name__)


@pytest.fixture
def inspector(logger):
    """Create a VMDKInspector instance."""
    return VMDKInspector(logger)


def create_test_vmdk(path: Path, descriptor_content: str, extent_size: int = 0):
    """Create a test VMDK descriptor and extent file."""
    # Write descriptor
    path.write_text(descriptor_content)

    # Create extent if specified
    if extent_size > 0:
        extent_name = "test-flat.vmdk"
        extent_path = path.parent / extent_name
        extent_path.write_bytes(b"\x00" * extent_size)


class TestVMDKInspector:
    """Test VMDK Inspector functionality."""

    def test_parse_valid_vmdk(self, inspector, tmp_path):
        """Test parsing a valid VMDK descriptor."""
        vmdk = tmp_path / "test.vmdk"
        descriptor = """# Disk DescriptorFile
version=1
CID=12345678
parentCID=ffffffff
createType=monolithicFlat

# Extent description
RW 2097152 FLAT "test-flat.vmdk" 0

# Disk Data Base
ddb.adapterType = "lsilogic"
ddb.thinProvisioned = "1"
ddb.geometry.sectors = "63"
ddb.geometry.heads = "255"
ddb.geometry.cylinders = "1024"
"""
        create_test_vmdk(vmdk, descriptor, extent_size=2097152 * 512)

        result = inspector.inspect(vmdk)

        assert result.path == vmdk
        assert result.valid is True
        assert result.create_type == "monolithicFlat"
        assert result.parent_cid == "ffffffff"
        assert result.adapter_type == "lsilogic"
        assert result.thin_provisioned is True
        assert result.sectors == 2097152
        assert result.extent_type == "FLAT"
        assert result.extent_file == "test-flat.vmdk"
        assert result.size_gb == pytest.approx(1.0, rel=0.1)

    def test_snapshot_detection(self, inspector, tmp_path):
        """Test snapshot chain detection."""
        vmdk = tmp_path / "snapshot.vmdk"
        descriptor = """# Disk DescriptorFile
version=1
CID=abcdef01
parentCID=12345678
createType=vmfsSparse

RW 2097152 VMFSSPARSE "snapshot-000001.vmdk"

ddb.adapterType = "lsilogic"
"""
        create_test_vmdk(vmdk, descriptor)

        result = inspector.inspect(vmdk)

        # Should detect snapshot (parent_cid != ffffffff)
        assert result.parent_cid == "12345678"
        snapshot_risks = [r for r in result.risks if r.component == "snapshot"]
        assert len(snapshot_risks) > 0
        assert snapshot_risks[0].level == RiskLevel.FATAL
        assert result.has_fatal_risks is True

    def test_controller_risks(self, inspector, tmp_path):
        """Test controller compatibility analysis."""
        test_cases = [
            ("buslogic", RiskLevel.FATAL),
            ("lsilogic", RiskLevel.HIGH),
            ("lsilogicsas", RiskLevel.HIGH),
            ("ide", RiskLevel.HIGH),  # Not in safe list
        ]

        for adapter, expected_level in test_cases:
            vmdk = tmp_path / f"test-{adapter}.vmdk"
            descriptor = f"""# Disk DescriptorFile
version=1
parentCID=ffffffff
createType=monolithicFlat
RW 2097152 FLAT "test-flat.vmdk" 0
ddb.adapterType = "{adapter}"
"""
            create_test_vmdk(vmdk, descriptor, extent_size=2097152 * 512)

            result = inspector.inspect(vmdk)
            controller_risks = [r for r in result.risks if r.component == "controller"]

            assert len(controller_risks) > 0, f"Expected risk for {adapter}"
            assert controller_risks[0].level == expected_level, \
                f"Expected {expected_level} for {adapter}, got {controller_risks[0].level}"

    def test_missing_extent(self, inspector, tmp_path):
        """Test detection of missing extent files."""
        vmdk = tmp_path / "broken.vmdk"
        descriptor = """# Disk DescriptorFile
version=1
parentCID=ffffffff
createType=monolithicFlat
RW 2097152 FLAT "missing-flat.vmdk" 0
ddb.adapterType = "lsilogic"
"""
        create_test_vmdk(vmdk, descriptor)  # No extent created

        result = inspector.inspect(vmdk)

        extent_risks = [r for r in result.risks if r.component == "extent"]
        assert len(extent_risks) > 0
        assert any(r.level == RiskLevel.FATAL for r in extent_risks)
        assert result.has_fatal_risks is True

    def test_extent_size_mismatch(self, inspector, tmp_path):
        """Test detection of extent size mismatches."""
        vmdk = tmp_path / "size-mismatch.vmdk"
        descriptor = """# Disk DescriptorFile
version=1
parentCID=ffffffff
createType=monolithicFlat
RW 2097152 FLAT "test-flat.vmdk" 0
ddb.adapterType = "lsilogic"
"""
        # Create extent smaller than expected
        expected_size = 2097152 * 512
        actual_size = expected_size // 2
        create_test_vmdk(vmdk, descriptor, extent_size=actual_size)

        result = inspector.inspect(vmdk)

        extent_risks = [r for r in result.risks if r.component == "extent"]
        assert len(extent_risks) > 0
        assert any("size mismatch" in r.message.lower() for r in extent_risks)

    def test_json_serialization(self, inspector, tmp_path):
        """Test JSON serialization of results."""
        vmdk = tmp_path / "test.vmdk"
        descriptor = """# Disk DescriptorFile
version=1
parentCID=ffffffff
createType=monolithicFlat
RW 2097152 FLAT "test-flat.vmdk" 0
ddb.adapterType = "lsilogic"
"""
        create_test_vmdk(vmdk, descriptor, extent_size=2097152 * 512)

        result = inspector.inspect(vmdk)
        data = result.to_dict()

        assert isinstance(data, dict)
        assert data["path"] == str(vmdk)
        assert data["valid"] is True
        assert data["adapter_type"] == "lsilogic"
        assert data["boot_mode"] in ["BIOS", "UEFI", "UNKNOWN"]
        assert "risks" in data
        assert isinstance(data["risks"], list)

    def test_libvirt_config_generation_bios(self, inspector, tmp_path):
        """Test libvirt config generation for BIOS."""
        result = VMDKInspectionResult(
            path=Path("/test/disk.vmdk"),
            valid=True,
            boot_mode=BootMode.BIOS
        )

        xml = inspector.generate_libvirt_config(result, "/var/lib/libvirt/images/disk.qcow2")

        assert "<disk type='file' device='disk'>" in xml
        assert "type='qcow2'" in xml
        assert "bus='virtio'" in xml
        assert "OVMF" not in xml  # BIOS mode, no UEFI config

    def test_libvirt_config_generation_uefi(self, inspector, tmp_path):
        """Test libvirt config generation for UEFI."""
        result = VMDKInspectionResult(
            path=Path("/test/disk.vmdk"),
            valid=True,
            boot_mode=BootMode.UEFI
        )

        xml = inspector.generate_libvirt_config(result, "/var/lib/libvirt/images/disk.qcow2")

        assert "<disk type='file' device='disk'>" in xml
        assert "OVMF" in xml  # UEFI firmware
        assert "loader" in xml
        assert "nvram" in xml

    def test_max_risk_level(self, inspector, tmp_path):
        """Test max_risk_level property."""
        result = VMDKInspectionResult(path=Path("/test"), valid=True)

        # No risks
        assert result.max_risk_level is None

        # Add INFO risk
        result.risks.append(Risk(RiskLevel.INFO, "Info message"))
        assert result.max_risk_level == RiskLevel.INFO

        # Add HIGH risk
        result.risks.append(Risk(RiskLevel.HIGH, "High risk"))
        assert result.max_risk_level == RiskLevel.HIGH

        # Add FATAL risk
        result.risks.append(Risk(RiskLevel.FATAL, "Fatal error"))
        assert result.max_risk_level == RiskLevel.FATAL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
