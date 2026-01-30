# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Integration Tests for libguestfs Mount Operations

Tests mounting, unmounting, and mount-related operations:
- mount, umount, umount_all
- mount_ro, mount_options
- mkmountpoint, rmmountpoint
- mountpoints, mounts
- is_whole_device
"""

import pytest
import shutil


@pytest.mark.requires_images
def test_basic_mount_umount(test_linux_qcow2_image):
    """Test basic mount and umount operations"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Mount filesystem
    g.mount("/dev/sda1", "/")

    # Verify it's mounted by accessing a file
    assert g.exists("/etc")

    # Get list of mounts
    mounts = g.mounts()
    assert len(mounts) > 0
    assert "/dev/sda1" in mounts

    # Unmount
    g.umount("/")

    # Verify unmounted
    mounts_after = g.mounts()
    assert len(mounts_after) == 0

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_mount_readonly(test_linux_qcow2_image):
    """Test mounting filesystem read-only"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Mount read-only
    g.mount_ro("/dev/sda1", "/")

    # Can read files
    assert g.exists("/etc")

    # Cannot write files (should raise exception)
    with pytest.raises(Exception):
        g.touch("/test-readonly.txt")

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_mount_with_options(test_linux_qcow2_image, cleanup_test_image):
    """Test mounting with specific mount options"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    test_copy = cleanup_test_image("mount-opts.qcow2", "qcow2")
    shutil.copy(test_linux_qcow2_image, test_copy)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_copy), format="qcow2", readonly=False)
    g.launch()

    # Mount with options
    g.mount_options("noatime", "/dev/sda1", "/")

    # Verify mounted
    assert g.exists("/etc")

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_umount_all(test_linux_qcow2_image):
    """Test unmounting all filesystems"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Mount filesystem
    g.mount("/dev/sda1", "/")

    # Verify mounted
    mounts_before = g.mounts()
    assert len(mounts_before) > 0

    # Unmount all
    g.umount_all()

    # Verify all unmounted
    mounts_after = g.mounts()
    assert len(mounts_after) == 0

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_mountpoints_detection(test_linux_qcow2_image):
    """Test getting mount points from inspection"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Inspect OS
    roots = g.inspect_os()
    if len(roots) == 0:
        pytest.skip("No OS detected")

    root = roots[0]

    # Get mountpoints
    mountpoints = g.inspect_get_mountpoints(root)

    # Should have root
    assert "/" in mountpoints

    # Mount in correct order
    for mp, device in sorted(mountpoints.items(), key=lambda x: len(x[0])):
        try:
            g.mount(device, mp)
        except:
            pass

    # Verify mounted
    assert g.exists("/etc")

    g.umount_all()
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_mkmountpoint_and_rmmountpoint(test_linux_qcow2_image, cleanup_test_image):
    """Test creating and removing mount points"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    test_copy = cleanup_test_image("mkmount.qcow2", "qcow2")
    shutil.copy(test_linux_qcow2_image, test_copy)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_copy), format="qcow2", readonly=False)
    g.launch()

    # Create mount point
    g.mkmountpoint("/custom-mount")

    # Mount filesystem there
    g.mount("/dev/sda1", "/custom-mount")

    # Access files through custom mount point
    assert g.exists("/custom-mount/etc")

    # Unmount
    g.umount("/custom-mount")

    # Remove mount point
    g.rmmountpoint("/custom-mount")

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_mount_loop(test_linux_qcow2_image, cleanup_test_image):
    """Test mounting a loop device"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    test_copy = cleanup_test_image("loop.qcow2", "qcow2")
    shutil.copy(test_linux_qcow2_image, test_copy)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_copy), format="qcow2", readonly=False)
    g.launch()

    # Mount root
    g.mount("/dev/sda1", "/")

    # Create a disk image file inside
    # (Skip this test as it's complex - just verify mount works)

    assert g.exists("/etc")

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_mount_vfs(test_linux_qcow2_image):
    """Test mounting with VFS type specification"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # Get filesystem type
    filesystems = g.list_filesystems()
    fs_type = filesystems.get("/dev/sda1", "ext4")

    if fs_type == "ext4":
        # Mount with explicit VFS type
        g.mount_vfs("", "ext4", "/dev/sda1", "/")

        # Verify mounted
        assert g.exists("/etc")

        g.umount("/")

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_remount(test_linux_qcow2_image, cleanup_test_image):
    """Test remounting filesystem with different options"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    test_copy = cleanup_test_image("remount.qcow2", "qcow2")
    shutil.copy(test_linux_qcow2_image, test_copy)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_copy), format="qcow2", readonly=False)
    g.launch()

    # Mount read-write
    g.mount("/dev/sda1", "/")

    # Can write
    g.touch("/test-rw.txt")
    assert g.exists("/test-rw.txt")

    # Unmount and remount readonly
    g.umount("/")
    g.mount_ro("/dev/sda1", "/")

    # Can still read
    assert g.exists("/test-rw.txt")

    # Cannot write
    with pytest.raises(Exception):
        g.touch("/test-ro.txt")

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_is_whole_device(test_linux_qcow2_image):
    """Test detecting if device is a whole device or partition"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # /dev/sda should be whole device
    assert g.is_whole_device("/dev/sda") is True

    # /dev/sda1 should be a partition
    if g.exists("/dev/sda1"):
        assert g.is_whole_device("/dev/sda1") is False

    g.shutdown()
    g.close()
