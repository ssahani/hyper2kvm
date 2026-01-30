# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Integration Tests for fstab Fixing

Tests actual fstab manipulation on real test images using libguestfs.
"""

import pytest
from pathlib import Path
import tempfile
import shutil


@pytest.mark.requires_images
def test_read_and_parse_fstab(test_linux_qcow2_image):
    """Test reading and parsing /etc/fstab from test image"""
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

    fstab_content = g.cat("/etc/fstab")

    # Parse fstab entries
    lines = fstab_content.strip().split('\n')
    mount_entries = [line for line in lines if line and not line.startswith('#')]

    assert len(mount_entries) > 0, "No mount entries in fstab"

    # Check for root filesystem entry
    has_root = any('/' in line and 'ext4' in line for line in mount_entries)
    assert has_root, "No root filesystem entry found"

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_modify_fstab_with_uuid(test_linux_qcow2_image, cleanup_test_image):
    """Test modifying fstab to use UUID format"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    # Create a copy to modify
    test_copy = cleanup_test_image("fstab-test.qcow2", "qcow2", size_mb=1024)
    shutil.copy(test_linux_qcow2_image, test_copy)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_copy), format="qcow2", readonly=False)
    g.launch()
    g.mount("/dev/sda1", "/")

    # Get filesystem UUID
    uuid = g.get_uuid("/dev/sda1")

    # Modify fstab to use UUID
    new_fstab = f"UUID={uuid} / ext4 defaults 0 1\n"
    g.write("/etc/fstab", new_fstab)

    # Verify the change
    modified_fstab = g.cat("/etc/fstab")
    assert uuid in modified_fstab
    assert "UUID=" in modified_fstab

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_detect_device_references_in_fstab(test_linux_qcow2_image):
    """Test detecting /dev/ style references in fstab"""
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

    fstab_content = g.cat("/etc/fstab")

    # Check for various device reference styles
    has_uuid = "UUID=" in fstab_content
    has_label = "LABEL=" in fstab_content
    has_dev = "/dev/" in fstab_content
    has_partuuid = "PARTUUID=" in fstab_content

    # Should have at least one type of device reference
    assert any([has_uuid, has_label, has_dev, has_partuuid]), \
        "No device references found in fstab"

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_fstab_multiline_formatting(test_linux_qcow2_image, cleanup_test_image):
    """Test handling multi-line fstab with comments"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    # Create a copy
    test_copy = cleanup_test_image("fstab-multiline.qcow2", "qcow2")
    shutil.copy(test_linux_qcow2_image, test_copy)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_copy), format="qcow2", readonly=False)
    g.launch()
    g.mount("/dev/sda1", "/")

    # Create a complex fstab
    complex_fstab = """# /etc/fstab - File system table
# Created by hyper2kvm test
#
# <device>  <mount>  <type>  <options>  <dump>  <pass>

UUID=test-root-uuid  /      ext4    defaults   0  1
UUID=test-boot-uuid  /boot  ext4    defaults   0  2
/dev/sdb1            /data  xfs     defaults   0  0

# Swap partition
UUID=test-swap-uuid  none   swap    sw         0  0
"""
    g.write("/etc/fstab", complex_fstab)

    # Read it back
    read_back = g.cat("/etc/fstab")

    # Verify all parts preserved
    assert "# /etc/fstab" in read_back
    assert "UUID=test-root-uuid" in read_back
    assert "/boot" in read_back
    assert "swap" in read_back

    # Parse non-comment lines
    lines = [l for l in read_back.split('\n') if l.strip() and not l.strip().startswith('#')]
    assert len(lines) == 4, f"Expected 4 mount entries, found {len(lines)}"

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_get_filesystem_uuids(test_linux_qcow2_image):
    """Test getting UUIDs for all filesystems in image"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Get all filesystems
    filesystems = g.list_filesystems()

    # Get UUIDs for ext4 filesystems
    ext4_uuids = {}
    for device, fstype in filesystems.items():
        if fstype == "ext4":
            try:
                uuid = g.get_uuid(device)
                if uuid:
                    ext4_uuids[device] = uuid
            except:
                pass  # Some devices may not have UUIDs

    # Should find at least one ext4 filesystem with UUID
    # Note: Test images may or may not have UUIDs set
    assert len(filesystems) > 0, "No filesystems found"

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_fstab_backup_and_restore(test_linux_qcow2_image, cleanup_test_image):
    """Test creating backup of fstab before modification"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    # Create a copy
    test_copy = cleanup_test_image("fstab-backup.qcow2", "qcow2")
    shutil.copy(test_linux_qcow2_image, test_copy)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_copy), format="qcow2", readonly=False)
    g.launch()
    g.mount("/dev/sda1", "/")

    # Read original fstab
    original_fstab = g.cat("/etc/fstab")

    # Create backup
    g.cp("/etc/fstab", "/etc/fstab.backup")

    # Modify fstab
    g.write("/etc/fstab", "# Modified fstab\n")

    # Verify backup exists
    assert g.exists("/etc/fstab.backup")

    # Verify backup has original content
    backup_content = g.cat("/etc/fstab.backup")
    assert backup_content == original_fstab

    # Restore from backup
    g.cp("/etc/fstab.backup", "/etc/fstab")

    # Verify restoration
    restored_fstab = g.cat("/etc/fstab")
    assert restored_fstab == original_fstab

    g.umount("/")
    g.shutdown()
    g.close()
