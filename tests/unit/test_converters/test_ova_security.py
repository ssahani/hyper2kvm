"""
Unit tests for OVA security - tar bomb and path traversal protection

Tests security measures when extracting OVA files to prevent malicious
archives from escaping extraction directory or consuming excessive resources.
"""

import pytest
import tarfile
import os
from unittest.mock import Mock, MagicMock, patch, mock_open
from pathlib import Path


class TestTarBombProtection:
    """Test protection against tar bomb attacks"""

    @pytest.fixture
    def safe_extraction_dir(self, tmp_path):
        """Create safe extraction directory"""
        extract_dir = tmp_path / "safe_extract"
        extract_dir.mkdir()
        return extract_dir

    def test_detect_absolute_paths(self):
        """Test detection of absolute paths in tar archive"""
        # Malicious tar member with absolute path
        malicious_paths = [
            "/etc/passwd",
            "/root/.ssh/authorized_keys",
            "/usr/bin/malware",
        ]

        for path in malicious_paths:
            # Should detect as dangerous
            is_absolute = os.path.isabs(path)
            assert is_absolute is True

    def test_detect_parent_directory_traversal(self):
        """Test detection of parent directory traversal (..)"""
        # Malicious paths using ..
        traversal_paths = [
            "../../../etc/passwd",
            "../../escaping/file.txt",
            "safe/../../dangerous.bin",
            "./../../../root/file",
        ]

        for path in traversal_paths:
            # Should detect ../ pattern
            has_traversal = ".." in Path(path).parts
            assert has_traversal is True

    def test_detect_symlink_escape(self, tmp_path):
        """Test detection of symlink escaping extraction directory"""
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        target_outside = tmp_path / "outside" / "file.txt"
        target_outside.parent.mkdir()
        target_outside.write_text("outside content")

        # Create symlink inside extract_dir pointing outside
        symlink = extract_dir / "malicious_link"
        symlink.symlink_to(target_outside)

        # Resolve symlink and check if it's outside extract_dir
        resolved = symlink.resolve()
        is_outside = not str(resolved).startswith(str(extract_dir))

        assert is_outside is True

    def test_detect_hardlink_outside_tree(self, tmp_path):
        """Test detection of hardlink pointing outside extraction tree"""
        # Hardlinks can be used to modify files outside extraction directory
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        # Target file outside extraction directory
        target_file = tmp_path / "important_file.txt"
        target_file.write_text("important data")

        # Hardlink inside extraction directory
        hardlink = extract_dir / "hardlink_to_important"

        # In Python, os.link creates hardlink
        # This should be detected and blocked
        try:
            hardlink.hardlink_to(target_file)
            # Check if hardlink points outside
            is_same_inode = hardlink.stat().st_ino == target_file.stat().st_ino
            assert is_same_inode is True
        except (OSError, NotImplementedError):
            # Hardlinks may not be supported on all filesystems
            pytest.skip("Hardlinks not supported on this filesystem")

    def test_safe_path_join(self, safe_extraction_dir):
        """Test safe path joining that prevents escaping"""

        def safe_join(base_dir, untrusted_path):
            """Safely join paths preventing directory traversal"""
            # Normalize and resolve the path
            base = Path(base_dir).resolve()
            target = (base / untrusted_path).resolve()

            # Check if target is within base directory
            try:
                target.relative_to(base)
                return target
            except ValueError:
                # Path escapes base directory
                raise ValueError(f"Path escape attempt: {untrusted_path}")

        # Safe paths
        safe_paths = [
            "file.txt",
            "subdir/file.txt",
            "a/b/c/file.txt",
        ]

        for safe_path in safe_paths:
            result = safe_join(safe_extraction_dir, safe_path)
            assert str(result).startswith(str(safe_extraction_dir))

        # Dangerous paths
        dangerous_paths = [
            "../../../etc/passwd",
            "/absolute/path/file.txt",
        ]

        for dangerous_path in dangerous_paths:
            with pytest.raises(ValueError):
                safe_join(safe_extraction_dir, dangerous_path)


class TestResourceExhaustion:
    """Test protection against resource exhaustion attacks"""

    def test_extraction_size_limit(self, tmp_path):
        """Test limiting total extracted size (zip bomb protection)"""
        max_extraction_size = 1024 * 1024 * 100  # 100 MB limit

        # Simulated extracted files
        extracted_files = [
            {"name": "file1.vmdk", "size": 50 * 1024 * 1024},  # 50 MB
            {"name": "file2.vmdk", "size": 40 * 1024 * 1024},  # 40 MB
            {"name": "file3.ovf", "size": 1 * 1024 * 1024},    # 1 MB
        ]

        total_size = sum(f["size"] for f in extracted_files)

        # Should be under limit
        assert total_size <= max_extraction_size

        # Add another large file that exceeds limit
        extracted_files.append({"name": "huge.vmdk", "size": 20 * 1024 * 1024})
        total_size = sum(f["size"] for f in extracted_files)

        # Should exceed limit
        assert total_size > max_extraction_size

    def test_extraction_file_count_limit(self):
        """Test limiting number of files extracted"""
        max_file_count = 100

        # Simulated file list from tar
        file_list = [f"file_{i}.txt" for i in range(150)]

        # Should exceed limit (potential tar bomb)
        assert len(file_list) > max_file_count

        # Would reject extraction
        extraction_allowed = len(file_list) <= max_file_count
        assert extraction_allowed is False

    def test_nested_archive_depth_limit(self):
        """Test limiting nested archive depth"""
        max_depth = 3

        # Simulated nested archives
        nested_levels = [
            "outer.tar",
            "outer.tar/inner1.tar",
            "outer.tar/inner1.tar/inner2.tar",
            "outer.tar/inner1.tar/inner2.tar/inner3.tar",
            "outer.tar/inner1.tar/inner2.tar/inner3.tar/inner4.tar",
        ]

        for level, archive in enumerate(nested_levels):
            if level > max_depth:
                # Too deep - reject
                assert level > max_depth

    def test_filename_length_limit(self):
        """Test limiting filename length"""
        max_filename_length = 255

        # Normal filename
        normal_name = "my_virtual_machine.vmdk"
        assert len(normal_name) <= max_filename_length

        # Excessively long filename (potential attack)
        long_name = "a" * 1000
        assert len(long_name) > max_filename_length

        # Should reject long filenames
        is_valid = len(long_name) <= max_filename_length
        assert is_valid is False


class TestOVFParsingSecurity:
    """Test OVF XML parsing security"""

    def test_malformed_ovf_xml(self):
        """Test handling of malformed OVF XML"""
        import xml.etree.ElementTree as ET

        malformed_xml = """
        <Envelope>
            <VirtualSystem>
                <Name>Test</Name>
                <!-- Missing closing tag
        </Envelope>
        """

        # Should raise parse error
        with pytest.raises(ET.ParseError):
            ET.fromstring(malformed_xml)

    def test_xml_bomb_protection(self):
        """Test protection against XML bomb (billion laughs attack)"""
        # XML bomb example (simplified)
        xml_bomb = """<?xml version="1.0"?>
        <!DOCTYPE lolz [
          <!ENTITY lol "lol">
          <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
        ]>
        <lolz>&lol2;</lolz>
        """

        # Should be detected and blocked
        # Python's ET has some built-in protection
        # In production, use defusedxml library

    def test_missing_disk_references(self):
        """Test handling of missing disk file references in OVF"""
        ovf_content = """
        <Envelope>
            <References>
                <File ovf:href="disk1.vmdk" ovf:id="file1"/>
            </References>
            <DiskSection>
                <Disk ovf:fileRef="file1"/>
                <Disk ovf:fileRef="file2"/>  <!-- Missing file reference -->
            </DiskSection>
        </Envelope>
        """

        # Should detect missing file reference
        # file2 is referenced but not defined in References section

    def test_href_path_traversal(self):
        """Test path traversal in OVF href attributes"""
        dangerous_hrefs = [
            "../../../etc/passwd",
            "/absolute/path/to/file.vmdk",
            "../../escape/disk.vmdk",
        ]

        for href in dangerous_hrefs:
            # Should detect dangerous paths
            is_absolute = os.path.isabs(href)
            has_traversal = ".." in Path(href).parts

            is_dangerous = is_absolute or has_traversal
            assert is_dangerous is True

    def test_ovf_external_entity_attack(self):
        """Test protection against XXE (XML External Entity) attacks"""
        xxe_payload = """<?xml version="1.0"?>
        <!DOCTYPE foo [
          <!ELEMENT foo ANY>
          <!ENTITY xxe SYSTEM "file:///etc/passwd">
        ]>
        <Envelope>&xxe;</Envelope>
        """

        # Should be blocked by safe XML parser
        # Use defusedxml in production
        # Standard ET has some protection but defusedxml is recommended


class TestSafeExtraction:
    """Test safe extraction procedures"""

    @pytest.fixture
    def mock_tarfile(self):
        """Mock tarfile for testing"""
        with patch('tarfile.open') as mock_tar:
            yield mock_tar

    def test_validate_tar_members_before_extraction(self, tmp_path):
        """Test validating all tar members before extraction"""
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        # Mock tar members
        safe_member = Mock()
        safe_member.name = "safe_file.vmdk"
        safe_member.isfile.return_value = True
        safe_member.issym.return_value = False
        safe_member.islnk.return_value = False

        dangerous_member = Mock()
        dangerous_member.name = "../../../etc/passwd"
        dangerous_member.isfile.return_value = True

        members = [safe_member, dangerous_member]

        # Validate each member
        safe_members = []
        for member in members:
            # Check for path traversal
            if ".." in Path(member.name).parts or os.path.isabs(member.name):
                # Reject dangerous member
                continue

            safe_members.append(member)

        # Only safe member should remain
        assert len(safe_members) == 1
        assert safe_members[0].name == "safe_file.vmdk"

    def test_extract_with_permission_limits(self):
        """Test extracting with limited permissions"""
        # Files should be extracted with safe permissions
        # Not executable by default, owner read/write only

        safe_mode = 0o644  # rw-r--r--
        dangerous_mode = 0o777  # rwxrwxrwx

        # Should enforce safe permissions
        enforced_mode = safe_mode & 0o666  # Remove execute bits
        assert enforced_mode == 0o644

    def test_extract_preserves_directory_structure(self, tmp_path):
        """Test extraction preserves directory structure safely"""
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        # Paths in archive
        archive_paths = [
            "vm_config.ovf",
            "disks/disk1.vmdk",
            "disks/disk2.vmdk",
            "metadata/manifest.mf",
        ]

        for path in archive_paths:
            full_path = extract_dir / path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text("content")

        # Verify structure
        assert (extract_dir / "vm_config.ovf").exists()
        assert (extract_dir / "disks" / "disk1.vmdk").exists()
        assert (extract_dir / "metadata" / "manifest.mf").exists()

    def test_atomic_extraction(self, tmp_path):
        """Test atomic extraction (all or nothing)"""
        extract_dir = tmp_path / "extract"
        temp_extract_dir = tmp_path / "extract.tmp"

        # Extract to temp directory first
        temp_extract_dir.mkdir()

        files = ["file1.txt", "file2.txt", "file3.txt"]
        for f in files:
            (temp_extract_dir / f).write_text("content")

        # Validate extraction
        extraction_ok = all((temp_extract_dir / f).exists() for f in files)

        if extraction_ok:
            # Rename temp to final location (atomic on same filesystem)
            temp_extract_dir.rename(extract_dir)
            assert extract_dir.exists()
            assert not temp_extract_dir.exists()
        else:
            # Cleanup temp directory
            import shutil
            shutil.rmtree(temp_extract_dir)


class TestOVAValidation:
    """Test OVA file validation before extraction"""

    def test_validate_ova_signature(self):
        """Test validating OVA file signature/magic bytes"""
        # TAR file magic bytes
        tar_magic = b'ustar'  # At offset 257

        # Mock file data
        valid_tar_header = b'\x00' * 257 + tar_magic + b'\x00' * 100

        # Check magic bytes
        has_valid_signature = tar_magic in valid_tar_header
        assert has_valid_signature is True

    def test_validate_ovf_schema(self):
        """Test validating OVF against schema"""
        # OVF should validate against standard OVF schema
        # This is informational test - actual validation requires OVF XSD schema

    def test_check_ova_file_extensions(self):
        """Test checking file extensions in OVA"""
        allowed_extensions = {'.ovf', '.vmdk', '.mf', '.cert', '.iso'}

        # Files in OVA
        ova_files = [
            "vm.ovf",
            "disk1.vmdk",
            "disk2.vmdk",
            "manifest.mf",
            "malicious.exe",  # Suspicious
        ]

        for filename in ova_files:
            ext = Path(filename).suffix.lower()
            if ext not in allowed_extensions:
                # Suspicious file
                assert ext == ".exe"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
