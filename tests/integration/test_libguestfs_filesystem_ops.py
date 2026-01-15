# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Integration Tests for libguestfs Filesystem Operations

Tests file/directory operations inside guest filesystems:
- mkdir, rmdir, touch, rm
- read, write, cat
- chmod, chown
- cp, mv
- exists, is_file, is_dir
"""

import pytest
import tempfile
import shutil


@pytest.mark.requires_images
def test_mkdir_and_rmdir(test_linux_qcow2_image, cleanup_test_image):
    """Test creating and removing directories"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    # Create a copy to modify
    test_copy = cleanup_test_image("mkdir-test.qcow2", "qcow2")
    shutil.copy(test_linux_qcow2_image, test_copy)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_copy), format="qcow2", readonly=False)
    g.launch()
    g.mount("/dev/sda1", "/")

    # Create directory
    g.mkdir("/test-dir")
    assert g.exists("/test-dir")
    assert g.is_dir("/test-dir")

    # Create nested directory
    g.mkdir_p("/test-dir/subdir/nested")
    assert g.exists("/test-dir/subdir/nested")

    # Remove directory
    g.rmdir("/test-dir/subdir/nested")
    assert not g.exists("/test-dir/subdir/nested")

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_touch_and_file_operations(test_linux_qcow2_image, cleanup_test_image):
    """Test creating and manipulating files"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    test_copy = cleanup_test_image("touch-test.qcow2", "qcow2")
    shutil.copy(test_linux_qcow2_image, test_copy)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_copy), format="qcow2", readonly=False)
    g.launch()
    g.mount("/dev/sda1", "/")

    # Create empty file
    g.touch("/test-file.txt")
    assert g.exists("/test-file.txt")
    assert g.is_file("/test-file.txt")

    # Write content
    content = "Test content from libguestfs\n"
    g.write("/test-file.txt", content)

    # Read content back
    read_content = g.cat("/test-file.txt")
    assert read_content == content

    # Check file size
    size = g.filesize("/test-file.txt")
    assert size == len(content)

    # Delete file
    g.rm("/test-file.txt")
    assert not g.exists("/test-file.txt")

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_write_and_read_operations(test_linux_qcow2_image, cleanup_test_image):
    """Test writing and reading file content"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    test_copy = cleanup_test_image("write-test.qcow2", "qcow2")
    shutil.copy(test_linux_qcow2_image, test_copy)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_copy), format="qcow2", readonly=False)
    g.launch()
    g.mount("/dev/sda1", "/")

    # Write multi-line content
    content = """Line 1
Line 2
Line 3
"""
    g.write("/multiline.txt", content)

    # Read with cat
    read_content = g.cat("/multiline.txt")
    assert read_content == content

    # Read with read_file (returns bytes)
    read_bytes = g.read_file("/multiline.txt")
    assert read_bytes.decode('utf-8') == content

    # Read lines
    lines = g.read_lines("/multiline.txt")
    assert len(lines) == 3
    assert lines[0] == "Line 1"
    assert lines[1] == "Line 2"

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_copy_and_move_operations(test_linux_qcow2_image, cleanup_test_image):
    """Test copying and moving files"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    test_copy = cleanup_test_image("copy-test.qcow2", "qcow2")
    shutil.copy(test_linux_qcow2_image, test_copy)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_copy), format="qcow2", readonly=False)
    g.launch()
    g.mount("/dev/sda1", "/")

    # Create original file
    original_content = "Original content"
    g.write("/original.txt", original_content)

    # Copy file
    g.cp("/original.txt", "/copy.txt")
    assert g.exists("/copy.txt")

    # Verify copy has same content
    copy_content = g.cat("/copy.txt")
    assert copy_content == original_content

    # Move file
    g.mv("/copy.txt", "/moved.txt")
    assert g.exists("/moved.txt")
    assert not g.exists("/copy.txt")

    # Verify moved file has same content
    moved_content = g.cat("/moved.txt")
    assert moved_content == original_content

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_chmod_operations(test_linux_qcow2_image, cleanup_test_image):
    """Test changing file permissions"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    test_copy = cleanup_test_image("chmod-test.qcow2", "qcow2")
    shutil.copy(test_linux_qcow2_image, test_copy)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_copy), format="qcow2", readonly=False)
    g.launch()
    g.mount("/dev/sda1", "/")

    # Create file
    g.write("/test-perms.txt", "test")

    # Change permissions to 0644
    g.chmod(0o644, "/test-perms.txt")

    # Get file stat
    stat = g.stat("/test-perms.txt")
    mode = stat['mode'] & 0o777

    # Verify permissions
    assert mode == 0o644

    # Change to 0755
    g.chmod(0o755, "/test-perms.txt")
    stat = g.stat("/test-perms.txt")
    mode = stat['mode'] & 0o777
    assert mode == 0o755

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_exists_and_type_checks(test_linux_qcow2_image):
    """Test file existence and type checking"""
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

    # Check standard directories exist
    assert g.exists("/etc")
    assert g.is_dir("/etc")
    assert not g.is_file("/etc")

    # Check fstab exists and is a file
    if g.exists("/etc/fstab"):
        assert g.is_file("/etc/fstab")
        assert not g.is_dir("/etc/fstab")

    # Check non-existent file
    assert not g.exists("/nonexistent-file-12345.txt")

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_ls_and_ll_operations(test_linux_qcow2_image):
    """Test listing directory contents"""
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

    # List /etc
    files = g.ls("/etc")
    assert isinstance(files, list)
    assert len(files) > 0

    # Should have fstab
    assert "fstab" in files

    # List with details
    details = g.ll("/etc")
    assert isinstance(details, str)
    assert "fstab" in details

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_find_and_find0(test_linux_qcow2_image):
    """Test recursive file finding"""
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

    # Find all files in /etc
    files = g.find("/etc")
    assert isinstance(files, list)
    assert len(files) > 0

    # Should find fstab
    assert any("fstab" in f for f in files)

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_stat_operations(test_linux_qcow2_image):
    """Test getting file statistics"""
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

    if g.exists("/etc/fstab"):
        # Get file stat
        stat = g.stat("/etc/fstab")

        # Check stat fields
        assert 'size' in stat
        assert 'mode' in stat
        assert 'uid' in stat
        assert 'gid' in stat

        # Size should be positive
        assert stat['size'] > 0

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_grep_operations(test_linux_qcow2_image):
    """Test grep inside guest filesystem"""
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

    if g.exists("/etc/fstab"):
        # Grep for UUID in fstab
        lines = g.grep("UUID", "/etc/fstab")

        # Should return list of lines (may be empty)
        assert isinstance(lines, list)

        # If any matches, verify they contain UUID
        for line in lines:
            if line.strip():  # Ignore empty lines
                assert "UUID" in line or line.startswith("#")

    g.umount("/")
    g.shutdown()
    g.close()


@pytest.mark.requires_images
def test_tar_operations(test_linux_qcow2_image, cleanup_test_image):
    """Test tar archive operations inside guest"""
    if not test_linux_qcow2_image.exists():
        pytest.skip("Test image not available")

    try:
        import guestfs
    except ImportError:
        pytest.skip("libguestfs not available")

    test_copy = cleanup_test_image("tar-test.qcow2", "qcow2")
    shutil.copy(test_linux_qcow2_image, test_copy)

    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(test_copy), format="qcow2", readonly=False)
    g.launch()
    g.mount("/dev/sda1", "/")

    # Create some test files
    g.mkdir_p("/test-tar/dir1")
    g.write("/test-tar/file1.txt", "content1")
    g.write("/test-tar/dir1/file2.txt", "content2")

    # Create tar archive
    g.tar_out("/test-tar", "/tmp/test.tar", compress="gzip")

    # Verify tar was created
    assert g.exists("/tmp/test.tar")
    assert g.filesize("/tmp/test.tar") > 0

    # Extract to different location
    g.mkdir("/test-extract")
    g.tar_in("/tmp/test.tar", "/test-extract", compress="gzip")

    # Verify extracted files
    assert g.exists("/test-extract/file1.txt")
    assert g.exists("/test-extract/dir1/file2.txt")

    g.umount("/")
    g.shutdown()
    g.close()
