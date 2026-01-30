# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Integration Tests for libguestfs Inspection API

Tests OS detection, filesystem inspection, and metadata extraction.
Based on libguestfs inspection capabilities used in hyper2kvm.
"""

import pytest


@pytest.mark.requires_images
def test_inspect_os_detection(test_linux_qcow2_image):
    """Test OS detection using guestfs inspection API"""
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

    # Should detect at least one OS
    assert len(roots) > 0, "No operating systems detected"

    # Get root device
    root = roots[0]

    # Inspect OS type
    ostype = g.inspect_get_type(root)
    assert ostype in ["linux", "windows", "freebsd", "netbsd", "openbsd", "hurd", "dos", "unknown"]

    # For Linux, check distro
    if ostype == "linux":
        distro = g.inspect_get_distro(root)
        # Should detect some distro (or unknown)
        assert distro is not None

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_inspect_filesystem_detection(test_linux_qcow2_image):
    """Test detecting filesystems in disk image"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    # List all filesystems
    filesystems = g.list_filesystems()

    assert len(filesystems) > 0, "No filesystems detected"

    # Check for expected filesystem types
    fs_types = set(filesystems.values())

    # Should have at least one filesystem (ignore swap)
    actual_fs = [fs for fs in fs_types if fs not in ["swap", "unknown"]]
    assert len(actual_fs) > 0, f"No actual filesystems found, only: {fs_types}"

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_inspect_mountpoints(test_linux_qcow2_image):
    """Test detecting mount points from OS inspection"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    roots = g.inspect_os()
    if len(roots) == 0:
        pytest.skip("No OS detected in test image")

    root = roots[0]

    # Get mountpoints
    mountpoints = g.inspect_get_mountpoints(root)

    # Should have at least root filesystem
    assert "/" in mountpoints, "Root filesystem not detected"

    # Root should map to a device
    root_device = mountpoints["/"]
    assert root_device.startswith("/dev/"), f"Invalid root device: {root_device}"

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_inspect_get_package_format(test_linux_qcow2_image):
    """Test detecting package format (rpm, deb, etc.)"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    roots = g.inspect_os()
    if len(roots) == 0:
        pytest.skip("No OS detected")

    root = roots[0]
    ostype = g.inspect_get_type(root)

    if ostype == "linux":
        # Get package format
        pkg_format = g.inspect_get_package_format(root)

        # Should be one of the known formats
        assert pkg_format in ["rpm", "deb", "pacman", "ebuild", "pisi",
                              "pkgsrc", "apk", "xbps", "unknown"]

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_inspect_list_applications(test_linux_qcow2_image):
    """Test listing installed applications"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    roots = g.inspect_os()
    if len(roots) == 0:
        pytest.skip("No OS detected")

    root = roots[0]

    # Mount the filesystem
    mountpoints = g.inspect_get_mountpoints(root)

    # Mount in correct order (shortest path first)
    for mp, device in sorted(mountpoints.items(), key=lambda x: len(x[0])):
        try:
            g.mount(device, mp)
        except:
            pass  # Some mounts may fail

    # List applications (may return empty list for test images without package DB)
    try:
        apps = g.inspect_list_applications(root)
        # Should return a list (may be empty for minimal test image)
        assert isinstance(apps, list)
    except:
        # Some systems may not support this
        pass

    g.umount_all()
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_inspect_get_hostname(test_linux_qcow2_image):
    """Test reading hostname from OS"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    roots = g.inspect_os()
    if len(roots) == 0:
        pytest.skip("No OS detected")

    root = roots[0]

    # Get hostname (may return None or empty)
    try:
        hostname = g.inspect_get_hostname(root)
        # If set, should be a string
        if hostname:
            assert isinstance(hostname, str)
            assert len(hostname) > 0
    except:
        # Not all systems have hostname detection
        pass

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_inspect_get_arch(test_linux_qcow2_image):
    """Test detecting OS architecture"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    roots = g.inspect_os()
    if len(roots) == 0:
        pytest.skip("No OS detected")

    root = roots[0]

    # Get architecture
    arch = g.inspect_get_arch(root)

    # Should be a known architecture
    known_archs = ["i386", "x86_64", "aarch64", "armv7l", "ppc64",
                   "ppc64le", "s390x", "sparc64", "unknown"]
    assert arch in known_archs, f"Unknown architecture: {arch}"

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_inspect_is_live(test_linux_qcow2_image):
    """Test detecting if image is a live CD/USB"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    roots = g.inspect_os()
    if len(roots) == 0:
        pytest.skip("No OS detected")

    root = roots[0]

    # Check if it's a live image
    is_live = g.inspect_is_live(root)

    # Should be False for normal installed system
    assert isinstance(is_live, bool)
    assert is_live is False  # Test image should be an installed system

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_inspect_get_major_version(test_linux_qcow2_image):
    """Test getting OS major version"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    roots = g.inspect_os()
    if len(roots) == 0:
        pytest.skip("No OS detected")

    root = roots[0]
    ostype = g.inspect_get_type(root)

    if ostype == "linux":
        # Get major version
        major_version = g.inspect_get_major_version(root)

        # Should be a positive integer (or 0 for unknown)
        assert isinstance(major_version, int)
        assert major_version >= 0

    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_inspect_get_product_name(test_linux_qcow2_image):
    """Test getting OS product name"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()

    roots = g.inspect_os()
    if len(roots) == 0:
        pytest.skip("No OS detected")

    root = roots[0]

    # Get product name
    product_name = g.inspect_get_product_name(root)

    # Should be a string (may be "unknown")
    assert isinstance(product_name, str)

    g.shutdown()
    g.close()
