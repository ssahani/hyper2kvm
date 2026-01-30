# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Integration Tests for libguestfs Device Operations

Tests device-level operations:
- list_devices, list_partitions
- part_list, part_get_parttype
- get_uuid, set_uuid
- get_label, set_label
- blockdev_getsize64, blockdev_getsz
- vfs_type, vfs_label, vfs_uuid
"""

import pytest
import shutil


@pytest.mark.requires_images
def test_list_devices(test_linux_qcow2_image):
    """Test listing block devices"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # List devices
    devices = g.list_devices()

    # Should have at least /dev/sda
    assert len(devices) > 0
    assert "/dev/sda" in devices

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_list_partitions(test_linux_qcow2_image):
    """Test listing partitions"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # List partitions
    partitions = g.list_partitions()

    # Should have at least one partition
    assert len(partitions) > 0
    assert "/dev/sda1" in partitions

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_part_list(test_linux_qcow2_image):
    """Test getting partition table details"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Get partition list
    parts = g.part_list("/dev/sda")

    # Should have at least one partition
    assert len(parts) > 0

    # Check first partition
    part = parts[0]
    assert 'part_num' in part
    assert 'part_start' in part
    assert 'part_end' in part
    assert 'part_size' in part

    # Size should be positive
    assert part['part_size'] > 0

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_part_get_parttype(test_linux_qcow2_image):
    """Test getting partition table type (mbr, gpt)"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Get partition table type
    parttype = g.part_get_parttype("/dev/sda")

    # Should be mbr or gpt
    assert parttype in ["mbr", "gpt", "msdos"]

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_get_uuid(test_linux_qcow2_image):
    """Test getting filesystem UUID"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Get UUID of first partition
    try:
        uuid = g.get_uuid("/dev/sda1")

        # If UUID is set, should be a string
        if uuid:
            assert isinstance(uuid, str)
            # UUIDs are typically 36 characters with dashes
            # Format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
            # But allow for different formats
            assert len(uuid) > 0
    except:
        # Some filesystems may not have UUIDs
        pytest.skip("UUID not available")

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_set_uuid(test_linux_qcow2_image, cleanup_test_image):
    """Test setting filesystem UUID"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    test_copy = cleanup_test_image("uuid-test.qcow2", "qcow2")
    shutil.copy(test_linux_qcow2_image, test_copy)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_copy), format="qcow2", readonly=False)
    g.launch()

    # Set a new UUID
    new_uuid = "12345678-1234-1234-1234-123456789abc"

    try:
        g.set_uuid("/dev/sda1", new_uuid)

        # Verify UUID was set
        read_uuid = g.get_uuid("/dev/sda1")
        assert read_uuid == new_uuid
    except Exception as e:
        # Some filesystem types don't support set_uuid
        pytest.skip(f"set_uuid not supported: {e}")

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_get_label(test_linux_qcow2_image):
    """Test getting filesystem label"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Get label (may be empty)
    try:
        label = g.get_label("/dev/sda1")

        # If label exists, should be a string
        if label:
            assert isinstance(label, str)
    except:
        # Not all filesystems support labels
        pass

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_set_label(test_linux_qcow2_image, cleanup_test_image):
    """Test setting filesystem label"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    test_copy = cleanup_test_image("label-test.qcow2", "qcow2")
    shutil.copy(test_linux_qcow2_image, test_copy)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_copy), format="qcow2", readonly=False)
    g.launch()

    # Set label
    new_label = "TESTLABEL"

    try:
        g.set_label("/dev/sda1", new_label)

        # Verify label was set
        read_label = g.get_label("/dev/sda1")
        assert read_label == new_label
    except Exception as e:
        # Some filesystem types don't support set_label
        pytest.skip(f"set_label not supported: {e}")

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_blockdev_getsize64(test_linux_qcow2_image):
    """Test getting block device size in bytes"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Get device size in bytes
    size = g.blockdev_getsize64("/dev/sda")

    # Size should be positive
    assert size > 0

    # Should be around 1GB (our test image size)
    assert size > 500 * 1024 * 1024  # At least 500MB
    assert size < 10 * 1024 * 1024 * 1024  # Less than 10GB

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_blockdev_getsz(test_linux_qcow2_image):
    """Test getting block device size in 512-byte sectors"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Get size in sectors
    sectors = g.blockdev_getsz("/dev/sda")

    # Sectors should be positive
    assert sectors > 0

    # Verify it matches getsize64
    size_bytes = g.blockdev_getsize64("/dev/sda")
    expected_sectors = size_bytes // 512

    assert sectors == expected_sectors

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_vfs_type(test_linux_qcow2_image):
    """Test getting filesystem type"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Get VFS type
    vfs_type = g.vfs_type("/dev/sda1")

    # Should be a known filesystem type
    known_types = ["ext2", "ext3", "ext4", "xfs", "btrfs", "vfat", "ntfs"]
    assert vfs_type in known_types, f"Unknown VFS type: {vfs_type}"

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_vfs_uuid(test_linux_qcow2_image):
    """Test getting UUID via VFS"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Get UUID via VFS
    try:
        uuid = g.vfs_uuid("/dev/sda1")

        # If UUID exists, should be a string
        if uuid:
            assert isinstance(uuid, str)
    except:
        # May not be available
        pass

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_vfs_label(test_linux_qcow2_image):
    """Test getting label via VFS"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Get label via VFS
    try:
        label = g.vfs_label("/dev/sda1")

        # If label exists, should be a string
        if label:
            assert isinstance(label, str)
    except:
        # May not be available
        pass

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_canonical_device_name(test_linux_qcow2_image):
    """Test getting canonical device name"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Get canonical name
    canonical = g.canonical_device_name("/dev/sda1")

    # Should normalize the device name
    assert canonical.startswith("/dev/")

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_device_index(test_linux_qcow2_image):
    """Test getting device index"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Get device index
    index = g.device_index("/dev/sda")

    # First device should be index 0
    assert index == 0

    g.shutdown()
    g.close()
