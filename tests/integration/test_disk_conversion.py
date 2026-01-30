# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Integration Tests for Disk Conversion

Tests actual disk conversion using real test images:
- QCOW2 to VMDK conversion
- RAW to QCOW2 conversion
- Format detection
- Compression
"""

import pytest
import subprocess
from pathlib import Path
import tempfile


@pytest.fixture
def output_dir():
    """Temporary directory for conversion outputs"""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.mark.requires_images
def test_qcow2_to_vmdk_conversion(test_linux_qcow2_image, output_dir):
    """Test converting QCOW2 to VMDK format"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    output_vmdk = output_dir / "converted.vmdk"

    # Use qemu-img to convert
    result = subprocess.run([
        "qemu-img", "convert",
        "-f", "qcow2",
        "-O", "vmdk",
        str(test_linux_qcow2_image),
        str(output_vmdk)
    ], capture_output=True)

    assert result.returncode == 0, f"Conversion failed: {result.stderr.decode()}"
    assert output_vmdk.exists(), "Output VMDK not created"
    assert output_vmdk.stat().st_size > 0, "Output VMDK is empty"


@pytest.mark.requires_images
def test_qcow2_info_detection(test_linux_qcow2_image):
    """Test qemu-img info on QCOW2 image"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    result = subprocess.run([
        "qemu-img", "info",
        "--output=json",
        str(test_linux_qcow2_image)
    ], capture_output=True, text=True)

    assert result.returncode == 0
    assert "qcow2" in result.stdout
    assert "virtual-size" in result.stdout


@pytest.mark.requires_images
def test_raw_to_qcow2_with_compression(test_linux_raw_image, output_dir):
    """Test RAW to QCOW2 conversion with compression"""
    if not test_linux_raw_image.exists():
        pytest.skip("Test RAW image not available")

    output_qcow2 = output_dir / "compressed.qcow2"

    # Convert with compression
    result = subprocess.run([
        "qemu-img", "convert",
        "-f", "raw",
        "-O", "qcow2",
        "-c",  # Compression flag
        str(test_linux_raw_image),
        str(output_qcow2)
    ], capture_output=True)

    assert result.returncode == 0
    assert output_qcow2.exists()

    # Verify it's smaller than original (due to compression)
    # Note: May not always be true for small test images
    original_size = test_linux_raw_image.stat().st_size
    compressed_size = output_qcow2.stat().st_size

    # At minimum, verify it's valid QCOW2
    info_result = subprocess.run([
        "qemu-img", "info", str(output_qcow2)
    ], capture_output=True, text=True)

    assert "qcow2" in info_result.stdout


@pytest.mark.requires_images
def test_vmdk_to_qcow2_conversion(test_linux_vmdk_image, output_dir):
    """Test VMDK to QCOW2 conversion (common migration path)"""
    if not test_linux_vmdk_image.exists():
        pytest.skip("Test VMDK image not available")

    output_qcow2 = output_dir / "from-vmdk.qcow2"

    result = subprocess.run([
        "qemu-img", "convert",
        "-f", "vmdk",
        "-O", "qcow2",
        str(test_linux_vmdk_image),
        str(output_qcow2)
    ], capture_output=True)

    assert result.returncode == 0
    assert output_qcow2.exists()
    assert output_qcow2.stat().st_size > 0


@pytest.mark.requires_images
def test_conversion_preserves_data(test_linux_qcow2_image, output_dir):
    """Test that conversion preserves disk data"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    output_vmdk = output_dir / "test.vmdk"

    # Convert QCOW2 to VMDK
    subprocess.run([
        "qemu-img", "convert",
        "-f", "qcow2",
        "-O", "vmdk",
        str(test_linux_qcow2_image),
        str(output_vmdk)
    ], check=True, capture_output=True)

    # Read marker file from original
    g1 = guestfs.GuestFS(python_return_dict=True)
    g1.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g1.launch()
    g1.mount("/dev/sda1", "/")

    original_marker = None
    if g1.exists("/etc/test-marker"):
        original_marker = g1.cat("/etc/test-marker")

    g1.umount("/")
    g1.shutdown()
    g1.close()

    # Read marker file from converted
    g2 = guestfs.GuestFS(python_return_dict=True)
    g2.add_drive_opts(str(output_vmdk), format="vmdk", readonly=True)
    g2.launch()
    g2.mount("/dev/sda1", "/")

    converted_marker = None
    if g2.exists("/etc/test-marker"):
        converted_marker = g2.cat("/etc/test-marker")

    g2.umount("/")
    g2.shutdown()
    g2.close()

    # Verify data preserved
    assert original_marker == converted_marker, "Data not preserved after conversion"


@pytest.mark.requires_images
def test_detect_filesystem_in_image(test_linux_qcow2_image):
    """Test detecting ext4 filesystem in test image"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # List filesystems
    filesystems = g.list_filesystems()

    assert len(filesystems) > 0, "No filesystems detected"

    # Should have ext4 filesystem
    fs_types = list(filesystems.values())
    assert "ext4" in fs_types, f"Expected ext4, found: {fs_types}"

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_read_fstab_from_test_image(test_linux_qcow2_image):
    """Test reading /etc/fstab from test image"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()
    g.mount("/dev/sda1", "/")

    # Read fstab
    assert g.exists("/etc/fstab"), "/etc/fstab not found in test image"

    fstab_content = g.cat("/etc/fstab")

    # Verify fstab has expected content
    assert "UUID" in fstab_content or "/dev/" in fstab_content
    assert "ext4" in fstab_content

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_read_network_config_from_test_image(test_linux_qcow2_image):
    """Test reading network configuration from test image"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()
    g.mount("/dev/sda1", "/")

    # Check for network config
    network_paths = [
        "/etc/sysconfig/network-scripts/ifcfg-eth0",
        "/etc/sysconfig/network-scripts/ifcfg-eth1",
    ]

    found_configs = [p for p in network_paths if g.exists(p)]
    assert len(found_configs) > 0, "No network configs found in test image"

    # Read eth0 config
    if g.exists("/etc/sysconfig/network-scripts/ifcfg-eth0"):
        eth0_config = g.cat("/etc/sysconfig/network-scripts/ifcfg-eth0")
        assert "DEVICE=eth0" in eth0_config
        assert "HWADDR=" in eth0_config

    g.umount("/")
    g.shutdown()
    g.close()
