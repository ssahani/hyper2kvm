# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for libvirt XML extractor."""

import tempfile
from pathlib import Path

import pytest

from hyper2kvm.converters.extractors.libvirt_xml import LibvirtXML


class TestLibvirtXML:
    """Test LibvirtXML extractor functionality."""

    def create_sample_domain_xml(self, tmpdir: Path, name: str = "test-vm") -> Path:
        """Create a sample domain XML file for testing."""
        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<domain type="kvm">
  <name>{name}</name>
  <uuid>test-uuid-1234</uuid>
  <memory unit="GiB">8</memory>
  <vcpu>4</vcpu>
  <os>
    <type arch="x86_64" machine="pc-q35-6.2">hvm</type>
    <loader readonly="yes" type="pflash">/usr/share/OVMF/OVMF_CODE.fd</loader>
    <boot dev="hd"/>
  </os>
  <devices>
    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2"/>
      <source file="{tmpdir}/boot.qcow2"/>
      <target dev="vda" bus="virtio"/>
    </disk>
    <interface type="bridge">
      <mac address="52:54:00:aa:bb:cc"/>
      <source bridge="br0"/>
      <model type="virtio"/>
    </interface>
  </devices>
</domain>"""
        xml_path = tmpdir / f"{name}.xml"
        xml_path.write_text(xml_content)

        # Create dummy disk file
        disk_path = tmpdir / "boot.qcow2"
        disk_path.write_bytes(b"\x00" * 1024)  # 1KB dummy file

        return xml_path

    def test_parse_basic_domain(self, tmp_path):
        """Test parsing a basic domain XML."""
        xml_path = self.create_sample_domain_xml(tmp_path)

        manifest = LibvirtXML.parse_domain_xml(
            None,  # logger
            xml_path,
            tmp_path,
            compute_checksums=False,
        )

        assert manifest["manifest_version"] == "1.0"
        assert manifest["source"]["provider"] == "libvirt"
        assert manifest["source"]["vm_name"] == "test-vm"
        assert manifest["source"]["vm_id"] == "test-uuid-1234"

    def test_detect_uefi_firmware(self, tmp_path):
        """Test UEFI firmware detection."""
        xml_path = self.create_sample_domain_xml(tmp_path)

        manifest = LibvirtXML.parse_domain_xml(
            None, xml_path, tmp_path, compute_checksums=False
        )

        assert manifest["firmware"]["type"] == "uefi"

    def test_detect_bios_firmware(self, tmp_path):
        """Test BIOS firmware detection (no loader)."""
        xml_content = """<?xml version="1.0"?>
<domain type="kvm">
  <name>bios-vm</name>
  <os>
    <type arch="x86_64">hvm</type>
  </os>
  <devices>
  </devices>
</domain>"""
        xml_path = tmp_path / "bios.xml"
        xml_path.write_text(xml_content)

        manifest = LibvirtXML.parse_domain_xml(
            None, xml_path, tmp_path, compute_checksums=False
        )

        assert manifest["firmware"]["type"] == "bios"

    def test_extract_disk_info(self, tmp_path):
        """Test disk extraction from domain XML."""
        xml_path = self.create_sample_domain_xml(tmp_path)

        manifest = LibvirtXML.parse_domain_xml(
            None, xml_path, tmp_path, compute_checksums=False
        )

        assert len(manifest["disks"]) == 1
        disk = manifest["disks"][0]

        assert disk["id"] == "vda"
        assert disk["source_format"] == "qcow2"
        assert disk["disk_type"] == "boot"
        assert str(tmp_path / "boot.qcow2") in disk["local_path"]
        assert disk["bytes"] == 1024

    def test_skip_cdrom_devices(self, tmp_path):
        """Test that CD-ROM devices are skipped."""
        xml_content = """<?xml version="1.0"?>
<domain type="kvm">
  <name>test</name>
  <devices>
    <disk type="file" device="disk">
      <source file="/tmp/disk.qcow2"/>
      <target dev="vda"/>
    </disk>
    <disk type="file" device="cdrom">
      <source file="/tmp/cdrom.iso"/>
      <target dev="sr0"/>
    </disk>
  </devices>
</domain>"""
        xml_path = tmp_path / "test.xml"
        xml_path.write_text(xml_content)

        # Create only the disk file
        (tmp_path / "disk.qcow2").write_bytes(b"\x00" * 100)

        manifest = LibvirtXML.parse_domain_xml(
            None, xml_path, tmp_path, compute_checksums=False
        )

        # Should only have the disk, not the cdrom
        assert len(manifest["disks"]) == 1
        assert manifest["disks"][0]["id"] != "sr0"

    def test_extract_network_info(self, tmp_path):
        """Test network interface extraction."""
        xml_path = self.create_sample_domain_xml(tmp_path)

        manifest = LibvirtXML.parse_domain_xml(
            None, xml_path, tmp_path, compute_checksums=False
        )

        assert "metadata" in manifest
        assert "networks" in manifest["metadata"]

        networks = manifest["metadata"]["networks"]
        assert len(networks) == 1

        net = networks[0]
        assert net["type"] == "bridge"
        assert net["source"] == "br0"
        assert net["mac"] == "52:54:00:aa:bb:cc"
        assert net["model"] == "virtio"

    def test_extract_memory_vcpus(self, tmp_path):
        """Test memory and vCPU extraction."""
        xml_path = self.create_sample_domain_xml(tmp_path)

        manifest = LibvirtXML.parse_domain_xml(
            None, xml_path, tmp_path, compute_checksums=False
        )

        metadata = manifest["metadata"]
        assert metadata["memory_bytes"] == 8 * 1024 * 1024 * 1024  # 8 GiB
        assert metadata["vcpus"] == 4

    def test_compute_checksums(self, tmp_path):
        """Test SHA256 checksum computation."""
        xml_path = self.create_sample_domain_xml(tmp_path)

        manifest = LibvirtXML.parse_domain_xml(
            None, xml_path, tmp_path, compute_checksums=True
        )

        disk = manifest["disks"][0]
        assert disk["checksum"] is not None
        assert disk["checksum"].startswith("sha256:")

    def test_skip_checksums(self, tmp_path):
        """Test skipping checksum computation."""
        xml_path = self.create_sample_domain_xml(tmp_path)

        manifest = LibvirtXML.parse_domain_xml(
            None, xml_path, tmp_path, compute_checksums=False
        )

        disk = manifest["disks"][0]
        assert disk["checksum"] is None

    def test_missing_xml_file(self, tmp_path):
        """Test error when XML file doesn't exist."""
        with pytest.raises(SystemExit):  # U.die calls sys.exit
            LibvirtXML.parse_domain_xml(
                None,
                tmp_path / "nonexistent.xml",
                tmp_path,
            )

    def test_invalid_xml_syntax(self, tmp_path):
        """Test error with invalid XML syntax."""
        xml_path = tmp_path / "invalid.xml"
        xml_path.write_text("not valid xml <unclosed")

        with pytest.raises(SystemExit):  # U.die calls sys.exit
            LibvirtXML.parse_domain_xml(None, xml_path, tmp_path)

    def test_no_disks_found(self, tmp_path):
        """Test error when no valid disks found."""
        xml_content = """<?xml version="1.0"?>
<domain type="kvm">
  <name>no-disks</name>
  <devices>
  </devices>
</domain>"""
        xml_path = tmp_path / "nodisks.xml"
        xml_path.write_text(xml_content)

        with pytest.raises(SystemExit):  # U.die calls sys.exit
            LibvirtXML.parse_domain_xml(None, xml_path, tmp_path)

    def test_multiple_disks_boot_order(self, tmp_path):
        """Test boot order with multiple disks."""
        xml_content = f"""<?xml version="1.0"?>
<domain type="kvm">
  <name>multi-disk</name>
  <devices>
    <disk type="file" device="disk">
      <source file="{tmp_path}/disk1.qcow2"/>
      <target dev="vda"/>
    </disk>
    <disk type="file" device="disk">
      <source file="{tmp_path}/disk2.qcow2"/>
      <target dev="vdb"/>
    </disk>
    <disk type="file" device="disk">
      <source file="{tmp_path}/disk3.qcow2"/>
      <target dev="vdc"/>
    </disk>
  </devices>
</domain>"""
        xml_path = tmp_path / "multi.xml"
        xml_path.write_text(xml_content)

        # Create dummy disk files
        for i in range(1, 4):
            (tmp_path / f"disk{i}.qcow2").write_bytes(b"\x00" * 100)

        manifest = LibvirtXML.parse_domain_xml(
            None, xml_path, tmp_path, compute_checksums=False
        )

        assert len(manifest["disks"]) == 3

        # First disk should be boot
        assert manifest["disks"][0]["disk_type"] == "boot"
        assert manifest["disks"][0]["boot_order_hint"] == 0

        # Others should be data
        assert manifest["disks"][1]["disk_type"] == "data"
        assert manifest["disks"][2]["disk_type"] == "data"

    def test_os_hint_extraction(self, tmp_path):
        """Test OS distro hint extraction from libosinfo."""
        xml_content = """<?xml version="1.0"?>
<domain type="kvm">
  <name>rhel-vm</name>
  <metadata>
    <libosinfo:libosinfo xmlns:libosinfo="http://libosinfo.org/xmlns/libvirt/domain/1.0">
      <libosinfo:os id="http://redhat.com/rhel/9.0"/>
    </libosinfo:libosinfo>
  </metadata>
  <devices>
    <disk type="file" device="disk">
      <source file="/tmp/disk.qcow2"/>
      <target dev="vda"/>
    </disk>
  </devices>
</domain>"""
        xml_path = tmp_path / "rhel.xml"
        xml_path.write_text(xml_content)

        # Create dummy disk
        (Path("/tmp") / "disk.qcow2").touch()

        try:
            manifest = LibvirtXML.parse_domain_xml(
                None, xml_path, tmp_path, compute_checksums=False
            )

            # Should detect RHEL
            assert "rhel" in manifest["os_hint"].lower()
        finally:
            # Cleanup
            try:
                (Path("/tmp") / "disk.qcow2").unlink()
            except Exception:
                pass

    def test_manifest_output_structure(self, tmp_path):
        """Test that generated manifest has correct structure."""
        xml_path = self.create_sample_domain_xml(tmp_path)

        manifest = LibvirtXML.parse_domain_xml(
            None, xml_path, tmp_path, compute_checksums=False
        )

        # Check required top-level fields
        assert "manifest_version" in manifest
        assert "source" in manifest
        assert "disks" in manifest
        assert "firmware" in manifest
        assert "os_hint" in manifest
        assert "pipeline" in manifest
        assert "output" in manifest

        # Check pipeline structure
        assert "inspect" in manifest["pipeline"]
        assert "fix" in manifest["pipeline"]
        assert "convert" in manifest["pipeline"]
        assert "validate" in manifest["pipeline"]

    def test_custom_manifest_filename(self, tmp_path):
        """Test using custom manifest filename."""
        xml_path = self.create_sample_domain_xml(tmp_path)

        LibvirtXML.parse_domain_xml(
            None,
            xml_path,
            tmp_path,
            compute_checksums=False,
            manifest_filename="custom.json",
        )

        # Should create custom filename
        assert (tmp_path / "custom.json").exists()
        assert not (tmp_path / "manifest.json").exists()
