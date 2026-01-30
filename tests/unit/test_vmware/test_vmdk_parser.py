# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Security tests for VMDK parser - Path traversal protection.

CRITICAL: These tests verify that malicious VMDK descriptors cannot
reference files outside the base directory using path traversal attacks.
"""
from __future__ import annotations

import logging
import pytest
from pathlib import Path
from hyper2kvm.vmware.utils.vmdk_parser import VMDK, VMDKError


@pytest.mark.security
class TestVMDKPathTraversalSecurity:
    """Test path traversal protection in VMDK parser."""

    def test_reject_parent_directory_traversal(self, tmp_path):
        """
        Test that references like '../../../etc/passwd' are rejected.

        This is a CRITICAL security test - malicious VMDK descriptors
        must not be able to access files outside the datastore directory.
        """
        base_dir = tmp_path / "datastore"
        base_dir.mkdir()

        # Attempt path traversal
        with pytest.raises(VMDKError) as exc_info:
            VMDK._resolve_ref(base_dir, "../../../etc/passwd")

        # Verify error message indicates path traversal
        assert "Path traversal" in str(exc_info.value)
        assert "../../../etc/passwd" in str(exc_info.value)

    def test_reject_multiple_parent_references(self, tmp_path):
        """Test rejection of multiple ../ sequences."""
        base_dir = tmp_path / "datastore"
        base_dir.mkdir()

        test_cases = [
            "../../sensitive.file",
            "../../../../../../../etc/shadow",
            "../../../../root/.ssh/id_rsa",
        ]

        for ref in test_cases:
            with pytest.raises(VMDKError) as exc_info:
                VMDK._resolve_ref(base_dir, ref)
            assert "Path traversal" in str(exc_info.value)

    def test_allow_legitimate_relative_path(self, tmp_path):
        """Test that legitimate relative paths work correctly."""
        base_dir = tmp_path / "datastore"
        base_dir.mkdir()

        # Normal relative reference (should work)
        result = VMDK._resolve_ref(base_dir, "disk-flat.vmdk")

        assert result == base_dir / "disk-flat.vmdk"
        assert str(base_dir) in str(result)

    def test_allow_subdirectory_reference(self, tmp_path):
        """Test that subdirectory references are allowed."""
        base_dir = tmp_path / "datastore"
        base_dir.mkdir()
        subdir = base_dir / "vm-name"
        subdir.mkdir()

        # Subdirectory reference (should work)
        result = VMDK._resolve_ref(base_dir, "vm-name/disk.vmdk")

        assert result == base_dir / "vm-name" / "disk.vmdk"
        # Verify path is within base directory
        assert result.resolve().is_relative_to(base_dir.resolve())

    def test_basename_fallback_safe(self, tmp_path):
        """Test basename fallback doesn't allow traversal."""
        base_dir = tmp_path / "datastore"
        base_dir.mkdir()

        # Path with parent refs - basename should be safe
        # Even if full path doesn't exist, basename fallback should be safe
        result = VMDK._resolve_ref(base_dir, "../evil/disk.vmdk")

        # Should use basename only (disk.vmdk)
        assert result.name == "disk.vmdk"
        assert result.parent == base_dir

    def test_absolute_path_outside_base_handled(self, tmp_path):
        """
        Test handling of absolute paths outside base directory.

        Note: Absolute paths outside base are allowed for backward
        compatibility but callers should validate if needed.
        """
        base_dir = tmp_path / "datastore"
        base_dir.mkdir()

        # Absolute path outside base
        result = VMDK._resolve_ref(base_dir, "/etc/passwd")

        # Should return the absolute path (backward compat)
        # but it's outside base_dir
        assert result == Path("/etc/passwd")

    def test_resolve_with_symlinks_safe(self, tmp_path):
        """Test path resolution with symlinks doesn't escape."""
        base_dir = tmp_path / "datastore"
        base_dir.mkdir()

        # Create a symlink that tries to escape
        escape_link = base_dir / "escape"
        try:
            escape_link.symlink_to("../../..")
        except OSError:
            pytest.skip("Symlink creation failed (permissions)")

        # Reference through symlink should be caught
        with pytest.raises(VMDKError):
            VMDK._resolve_ref(base_dir, "escape/etc/passwd")


@pytest.mark.unit
class TestVMDKParserBasics:
    """Basic VMDK parser functionality tests."""

    def test_descriptor_detection(self, tmp_path):
        """Test text descriptor detection."""
        descriptor = tmp_path / "test.vmdk"
        descriptor.write_text('''# Disk DescriptorFile
version=1
CID=fffffffe
parentCID=ffffffff
createType="monolithicSparse"

RW 41922560 SPARSE "test-flat.vmdk"

ddb.adapterType = "lsilogic"
''')

        assert VMDK._is_text_descriptor(descriptor) is True

    def test_binary_vmdk_not_descriptor(self, tmp_path):
        """Test binary VMDK is not detected as descriptor."""
        binary_vmdk = tmp_path / "disk-flat.vmdk"
        # Write some binary data (VMDK magic)
        binary_vmdk.write_bytes(b"KDMV" + b"\x00" * 100)

        assert VMDK._is_text_descriptor(binary_vmdk) is False

    def test_parse_simple_descriptor(self, tmp_path, caplog):
        """Test parsing a simple VMDK descriptor."""
        descriptor = tmp_path / "test.vmdk"
        descriptor.write_text('''# Disk DescriptorFile
version=1
CID=abc123
createType="monolithicSparse"

RW 41922560 SPARSE "test-flat.vmdk"
''')

        logger = logging.getLogger(__name__)
        info = VMDK.parse_descriptor_info(logger, descriptor)

        assert info is not None
        assert info.version == "1"
        assert info.cid == "abc123"
        assert info.create_type == "monolithicSparse"
        assert len(info.extents) == 1
        assert info.extents[0].file == "test-flat.vmdk"
        assert info.extents[0].size_sectors == 41922560

    def test_parse_descriptor_with_parent(self, tmp_path):
        """Test parsing descriptor with parent reference."""
        descriptor = tmp_path / "snapshot.vmdk"
        descriptor.write_text('''# Disk DescriptorFile
version=1
CID=abc123
parentCID=def456
createType="vmfsSparse"
parentFileNameHint="base-disk.vmdk"

RW 41922560 VMFSSPARSE "snapshot-delta.vmdk"
''')

        logger = logging.getLogger(__name__)
        info = VMDK.parse_descriptor_info(logger, descriptor)

        assert info.parent == "base-disk.vmdk"
        assert info.cid == "abc123"
        assert info.parent_cid == "def456"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-m', 'security or unit'])
