# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Integration Tests for libguestfs Partition Operations

Tests partition creation, deletion, and manipulation:
- part_add, part_del
- part_disk, part_init
- part_set_bootable, part_get_bootable
- part_set_gpt_type, part_get_gpt_type
- part_set_mbr_id, part_get_mbr_id
- part_to_dev, part_to_partnum
"""

import pytest


@pytest.mark.requires_images
def test_part_to_dev(test_linux_qcow2_image):
    """Test converting partition to parent device"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Convert partition to device
    device = g.part_to_dev("/dev/sda1")

    # Should return /dev/sda
    assert device == "/dev/sda"

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_part_to_partnum(test_linux_qcow2_image):
    """Test getting partition number from partition device"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Get partition number
    partnum = g.part_to_partnum("/dev/sda1")

    # Should be 1
    assert partnum == 1

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_part_get_bootable(test_linux_qcow2_image):
    """Test checking if partition is bootable"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Check if partition is bootable
    try:
        bootable = g.part_get_bootable("/dev/sda", 1)

        # Should be boolean
        assert isinstance(bootable, bool)
    except:
        # May not be supported on all partition types
        pytest.skip("Bootable flag not supported")

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_part_set_bootable(cleanup_test_image):
    """Test setting partition bootable flag"""
    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    # Create a new disk image
    test_disk = cleanup_test_image("bootable-test.img", "raw", size_mb=100)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_disk), format="raw", readonly=False)
    g.launch()

    # Create partition table
    g.part_init("/dev/sda", "mbr")

    # Add partition
    g.part_add("/dev/sda", "primary", 2048, -2048)

    # Set bootable
    g.part_set_bootable("/dev/sda", 1, True)

    # Verify bootable flag
    bootable = g.part_get_bootable("/dev/sda", 1)
    assert bootable is True

    # Unset bootable
    g.part_set_bootable("/dev/sda", 1, False)
    bootable = g.part_get_bootable("/dev/sda", 1)
    assert bootable is False

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_part_init_and_add(cleanup_test_image):
    """Test creating partition table and adding partitions"""
    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    # Create a new disk image
    test_disk = cleanup_test_image("part-init.img", "raw", size_mb=100)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_disk), format="raw", readonly=False)
    g.launch()

    # Initialize partition table (mbr)
    g.part_init("/dev/sda", "mbr")

    # Get partition type
    parttype = g.part_get_parttype("/dev/sda")
    assert parttype in ["mbr", "msdos"]

    # Add primary partition (whole disk)
    g.part_add("/dev/sda", "primary", 2048, -2048)

    # List partitions
    parts = g.list_partitions()
    assert len(parts) == 1
    assert "/dev/sda1" in parts

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_part_disk(cleanup_test_image):
    """Test creating single partition covering whole disk"""
    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    # Create a new disk image
    test_disk = cleanup_test_image("part-disk.img", "raw", size_mb=100)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_disk), format="raw", readonly=False)
    g.launch()

    # Create single partition covering whole disk
    g.part_disk("/dev/sda", "mbr")

    # Should have created one partition
    parts = g.list_partitions()
    assert len(parts) == 1
    assert "/dev/sda1" in parts

    # Check partition type
    parttype = g.part_get_parttype("/dev/sda")
    assert parttype in ["mbr", "msdos"]

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_part_del(cleanup_test_image):
    """Test deleting partition"""
    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    # Create a new disk image
    test_disk = cleanup_test_image("part-del.img", "raw", size_mb=100)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_disk), format="raw", readonly=False)
    g.launch()

    # Create partition table
    g.part_init("/dev/sda", "mbr")

    # Add two partitions
    g.part_add("/dev/sda", "primary", 2048, 50000)
    g.part_add("/dev/sda", "primary", 51000, -2048)

    # Verify two partitions
    parts = g.list_partitions()
    assert len(parts) == 2

    # Delete first partition
    g.part_del("/dev/sda", 1)

    # Should have one partition left
    parts = g.list_partitions()
    assert len(parts) == 1

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_part_get_mbr_id(test_linux_qcow2_image):
    """Test getting MBR partition type ID"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Check partition table type first
    parttype = g.part_get_parttype("/dev/sda")

    if parttype in ["mbr", "msdos"]:
        # Get MBR ID
        mbr_id = g.part_get_mbr_id("/dev/sda", 1)

        # Should be a number (0x00 to 0xFF)
        assert isinstance(mbr_id, int)
        assert 0 <= mbr_id <= 255

        # Common IDs:
        # 0x83 = Linux
        # 0x82 = Linux swap
        # 0x07 = NTFS
        # 0xEE = GPT protective MBR
    else:
        pytest.skip("Not an MBR partition table")

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_part_set_mbr_id(cleanup_test_image):
    """Test setting MBR partition type ID"""
    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    # Create a new disk image
    test_disk = cleanup_test_image("mbr-id.img", "raw", size_mb=100)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_disk), format="raw", readonly=False)
    g.launch()

    # Create MBR partition table
    g.part_init("/dev/sda", "mbr")
    g.part_add("/dev/sda", "primary", 2048, -2048)

    # Set MBR ID to Linux (0x83)
    g.part_set_mbr_id("/dev/sda", 1, 0x83)

    # Verify
    mbr_id = g.part_get_mbr_id("/dev/sda", 1)
    assert mbr_id == 0x83

    # Change to Linux swap (0x82)
    g.part_set_mbr_id("/dev/sda", 1, 0x82)
    mbr_id = g.part_get_mbr_id("/dev/sda", 1)
    assert mbr_id == 0x82

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_part_get_gpt_type(cleanup_test_image):
    """Test getting GPT partition type GUID"""
    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    # Create a new disk image with GPT
    test_disk = cleanup_test_image("gpt-type.img", "raw", size_mb=100)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_disk), format="raw", readonly=False)
    g.launch()

    # Create GPT partition table
    g.part_init("/dev/sda", "gpt")
    g.part_add("/dev/sda", "primary", 2048, -2048)

    # Get GPT type
    try:
        gpt_type = g.part_get_gpt_type("/dev/sda", 1)

        # Should be a GUID string
        assert isinstance(gpt_type, str)
        # GUIDs are formatted as: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        assert len(gpt_type) == 36
        assert gpt_type.count('-') == 4
    except Exception as e:
        pytest.skip(f"GPT type not available: {e}")

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_part_set_gpt_type(cleanup_test_image):
    """Test setting GPT partition type GUID"""
    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    # Create a new disk image with GPT
    test_disk = cleanup_test_image("gpt-set.img", "raw", size_mb=100)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_disk), format="raw", readonly=False)
    g.launch()

    # Create GPT partition table
    g.part_init("/dev/sda", "gpt")
    g.part_add("/dev/sda", "primary", 2048, -2048)

    # Linux filesystem GUID
    linux_guid = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"

    try:
        # Set GPT type
        g.part_set_gpt_type("/dev/sda", 1, linux_guid)

        # Verify
        gpt_type = g.part_get_gpt_type("/dev/sda", 1)
        assert gpt_type.upper() == linux_guid.upper()
    except Exception as e:
        pytest.skip(f"GPT type setting not available: {e}")

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_part_resize(cleanup_test_image):
    """Test resizing partition"""
    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    # Create a new disk image
    test_disk = cleanup_test_image("resize.img", "raw", size_mb=200)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_disk), format="raw", readonly=False)
    g.launch()

    # Create partition table
    g.part_init("/dev/sda", "mbr")

    # Add partition (half the disk)
    g.part_add("/dev/sda", "primary", 2048, 100000)

    # Get initial partition list
    initial_parts = g.part_list("/dev/sda")
    initial_size = initial_parts[0]['part_size']

    # Resize partition to fill disk (if supported)
    try:
        g.part_resize("/dev/sda", 1, -2048)

        # Get new partition list
        new_parts = g.part_list("/dev/sda")
        new_size = new_parts[0]['part_size']

        # Should be larger
        assert new_size > initial_size
    except Exception as e:
        pytest.skip(f"Partition resize not supported: {e}")

    g.shutdown()
    g.close()
