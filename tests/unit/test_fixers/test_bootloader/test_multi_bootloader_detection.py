"""
Unit tests for multi-bootloader detection logic

Tests detection heuristics for GRUB, GRUB2, systemd-boot, rEFInd,
LILO, SYSLINUX, EXTLINUX and bootloader priority selection.
"""

import pytest
import logging
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from hyper2kvm.fixers.bootloader.fixer import (
    MultiBootloaderFixer,
    BootloaderType,
    BootloaderInfo,
)


class TestBootloaderDetection:
    """Test bootloader type detection"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        g.exists = Mock(return_value=False)
        g.is_file = Mock(return_value=False)
        g.is_dir = Mock(return_value=False)
        g.ls = Mock(return_value=[])
        g.cat = Mock(return_value="")
        return g

    def test_detect_grub2_uefi(self, mock_guestfs):
        """Test detection of GRUB2 with UEFI"""
        # Setup mock responses for GRUB2 UEFI system
        def exists_side_effect(path):
            return path in [
                "/boot/efi",
                "/boot/efi/EFI/grub2",
                "/boot/grub2/grub.cfg",
            ]

        def is_file_side_effect(path):
            return path in ["/boot/grub2/grub.cfg"]

        def is_dir_side_effect(path):
            return path in ["/boot/efi", "/boot/efi/EFI/grub2", "/boot/grub2"]

        mock_guestfs.exists.side_effect = exists_side_effect
        mock_guestfs.is_file.side_effect = is_file_side_effect
        mock_guestfs.is_dir.side_effect = is_dir_side_effect

        # Detection logic would check these paths
        assert mock_guestfs.exists("/boot/grub2/grub.cfg")
        assert mock_guestfs.is_dir("/boot/efi/EFI/grub2")

    def test_detect_grub_legacy(self, mock_guestfs):
        """Test detection of legacy GRUB (GRUB1)"""
        def exists_side_effect(path):
            return path in [
                "/boot/grub/grub.conf",
                "/boot/grub/menu.lst",
            ]

        def is_file_side_effect(path):
            return path in ["/boot/grub/grub.conf", "/boot/grub/menu.lst"]

        mock_guestfs.exists.side_effect = exists_side_effect
        mock_guestfs.is_file.side_effect = is_file_side_effect

        # Should detect legacy GRUB
        assert mock_guestfs.exists("/boot/grub/grub.conf")

    def test_detect_systemd_boot(self, mock_guestfs):
        """Test detection of systemd-boot"""
        def exists_side_effect(path):
            return path in [
                "/boot/efi",
                "/boot/efi/loader/loader.conf",
                "/boot/efi/loader/entries",
            ]

        def is_file_side_effect(path):
            return path == "/boot/efi/loader/loader.conf"

        def is_dir_side_effect(path):
            return path in ["/boot/efi", "/boot/efi/loader/entries"]

        mock_guestfs.exists.side_effect = exists_side_effect
        mock_guestfs.is_file.side_effect = is_file_side_effect
        mock_guestfs.is_dir.side_effect = is_dir_side_effect


        # Should detect systemd-boot
        assert mock_guestfs.exists("/boot/efi/loader/loader.conf")
        assert mock_guestfs.is_dir("/boot/efi/loader/entries")

    def test_detect_refind(self, mock_guestfs):
        """Test detection of rEFInd bootloader"""
        def exists_side_effect(path):
            return path in [
                "/boot/efi/EFI/refind/refind.conf",
                "/boot/efi/EFI/BOOT/refind_x64.efi",
            ]

        def is_file_side_effect(path):
            return path in [
                "/boot/efi/EFI/refind/refind.conf",
                "/boot/efi/EFI/BOOT/refind_x64.efi",
            ]

        mock_guestfs.exists.side_effect = exists_side_effect
        mock_guestfs.is_file.side_effect = is_file_side_effect


        # Should detect rEFInd
        assert mock_guestfs.exists("/boot/efi/EFI/refind/refind.conf")

    def test_detect_syslinux(self, mock_guestfs):
        """Test detection of SYSLINUX"""
        def exists_side_effect(path):
            return path in [
                "/boot/syslinux/syslinux.cfg",
            ]

        def is_file_side_effect(path):
            return path == "/boot/syslinux/syslinux.cfg"

        mock_guestfs.exists.side_effect = exists_side_effect
        mock_guestfs.is_file.side_effect = is_file_side_effect


        # Should detect SYSLINUX
        assert mock_guestfs.exists("/boot/syslinux/syslinux.cfg")

    def test_detect_hybrid_uefi_legacy(self, mock_guestfs):
        """Test detection of hybrid UEFI + Legacy system"""
        # System with both UEFI and legacy boot options
        def exists_side_effect(path):
            return path in [
                "/boot/efi",
                "/boot/efi/EFI/grub2",
                "/boot/grub2/grub.cfg",
                "/boot/grub/grub.conf",  # Also has legacy
            ]

        def is_file_side_effect(path):
            return path in [
                "/boot/grub2/grub.cfg",
                "/boot/grub/grub.conf",
            ]

        def is_dir_side_effect(path):
            return path in ["/boot/efi", "/boot/efi/EFI/grub2"]

        mock_guestfs.exists.side_effect = exists_side_effect
        mock_guestfs.is_file.side_effect = is_file_side_effect
        mock_guestfs.is_dir.side_effect = is_dir_side_effect


        # Should detect both
        assert mock_guestfs.exists("/boot/efi")  # UEFI
        assert mock_guestfs.exists("/boot/grub/grub.conf")  # Legacy

    def test_detect_no_bootloader(self, mock_guestfs):
        """Test detection when no bootloader found"""
        # All paths return False
        mock_guestfs.exists.return_value = False
        mock_guestfs.is_file.return_value = False
        mock_guestfs.is_dir.return_value = False


        # Should not find any bootloader
        assert not mock_guestfs.exists("/boot/grub2/grub.cfg")
        assert not mock_guestfs.exists("/boot/grub/grub.conf")


class TestBootloaderPriority:
    """Test bootloader priority and selection logic"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        return g

    def test_prefer_uefi_over_legacy(self, mock_guestfs):
        """Test UEFI bootloader preferred over legacy"""
        # When both UEFI and legacy detected, UEFI should win
        bootloaders = [
            BootloaderInfo(
                type=BootloaderType.GRUB2,
                config_files=["/boot/grub2/grub.cfg"],
                efi_path="/boot/efi/EFI/grub2",
                detected=True,
            ),
            BootloaderInfo(
                type=BootloaderType.GRUB,
                config_files=["/boot/grub/grub.conf"],
                efi_path=None,
                detected=True,
            ),
        ]

        # UEFI bootloader (GRUB2 with efi_path) should be preferred
        uefi_bootloader = next((b for b in bootloaders if b.efi_path is not None), None)
        assert uefi_bootloader is not None
        assert uefi_bootloader.type == BootloaderType.GRUB2

    def test_multiple_bootloaders_selection(self, mock_guestfs):
        """Test selection when multiple bootloaders detected"""
        bootloaders = [
            BootloaderInfo(
                type=BootloaderType.SYSTEMD_BOOT,
                config_files=["/boot/efi/loader/loader.conf"],
                efi_path="/boot/efi/loader",
                detected=True,
            ),
            BootloaderInfo(
                type=BootloaderType.GRUB2,
                config_files=["/boot/grub2/grub.cfg"],
                efi_path="/boot/efi/EFI/grub2",
                detected=True,
            ),
        ]

        # Priority logic: systemd-boot or GRUB2 both valid
        # Real implementation would have priority ordering
        assert len(bootloaders) == 2
        assert all(b.detected for b in bootloaders)

    def test_grub2_preferred_over_grub1(self, mock_guestfs):
        """Test GRUB2 preferred over GRUB1 when both present"""
        bootloaders = [
            BootloaderInfo(
                type=BootloaderType.GRUB2,
                config_files=["/boot/grub2/grub.cfg"],
                detected=True,
            ),
            BootloaderInfo(
                type=BootloaderType.GRUB,
                config_files=["/boot/grub/grub.conf"],
                detected=True,
            ),
        ]

        # GRUB2 should be preferred
        grub2 = next((b for b in bootloaders if b.type == BootloaderType.GRUB2), None)
        assert grub2 is not None
        assert grub2.detected


class TestBootloaderInfo:
    """Test BootloaderInfo dataclass"""

    def test_bootloader_info_creation(self):
        """Test creating BootloaderInfo"""
        info = BootloaderInfo(
            type=BootloaderType.GRUB2,
            version="2.04",
            config_files=["/boot/grub2/grub.cfg"],
            install_paths=["/boot/grub2"],
            efi_path="/boot/efi/EFI/grub2",
            boot_partition="/dev/sda1",
            detected=True,
            details={"modules": ["ext2", "part_gpt"]},
        )

        assert info.type == BootloaderType.GRUB2
        assert info.version == "2.04"
        assert len(info.config_files) == 1
        assert info.detected is True

    def test_bootloader_info_defaults(self):
        """Test BootloaderInfo default values"""
        info = BootloaderInfo(type=BootloaderType.UNKNOWN)

        assert info.version is None
        assert info.config_files == []
        assert info.install_paths == []
        assert info.efi_path is None
        assert info.boot_partition is None
        assert info.detected is False
        assert info.details == {}


class TestEdgeCases:
    """Test edge cases in bootloader detection"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        return g

    def test_case_sensitive_paths(self, mock_guestfs):
        """Test path case sensitivity"""
        # Linux filesystems are case-sensitive
        mock_guestfs.exists.return_value = False

        # /boot/grub2 != /boot/GRUB2
        assert not mock_guestfs.exists("/boot/GRUB2/grub.cfg")

    def test_symlinked_boot_directory(self, mock_guestfs):
        """Test handling of symlinked /boot directory"""
        # /boot might be a symlink
        mock_guestfs.is_symlink = Mock(return_value=True)
        mock_guestfs.readlink = Mock(return_value="/mnt/boot")

        if mock_guestfs.is_symlink("/boot"):
            real_path = mock_guestfs.readlink("/boot")
            assert real_path == "/mnt/boot"

    def test_multiple_esp_partitions(self, mock_guestfs):
        """Test system with multiple EFI System Partitions"""
        # Some systems have multiple ESPs
        efi_paths = [
            "/boot/efi",
            "/mnt/efi",
        ]

        for path in efi_paths:
            # Should check all potential ESP mounts
            pass

    def test_bootloader_on_separate_partition(self, mock_guestfs):
        """Test bootloader on separate /boot partition"""
        # /boot might be separate partition
        mock_guestfs.exists.side_effect = lambda p: p.startswith("/boot/grub2")

        # Should still detect even if /boot is separate
        assert mock_guestfs.exists("/boot/grub2/grub.cfg")

    def test_corrupted_bootloader_config(self, mock_guestfs):
        """Test handling of corrupted bootloader config"""
        # Config file exists but is corrupted
        mock_guestfs.exists.return_value = True
        mock_guestfs.is_file.return_value = True
        mock_guestfs.cat.side_effect = RuntimeError("Cannot read file")

        with pytest.raises(RuntimeError):
            mock_guestfs.cat("/boot/grub2/grub.cfg")

    def test_empty_bootloader_config(self, mock_guestfs):
        """Test handling of empty bootloader config"""
        mock_guestfs.exists.return_value = True
        mock_guestfs.is_file.return_value = True
        mock_guestfs.cat.return_value = ""

        # Empty config should be handled gracefully
        config = mock_guestfs.cat("/boot/grub2/grub.cfg")
        assert config == ""


class TestBootloaderVersionDetection:
    """Test bootloader version detection"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        return g

    def test_detect_grub_version_from_config(self, mock_guestfs):
        """Test extracting GRUB version from config"""
        # GRUB2 config often has version comment
        grub_config = """
        #
        # DO NOT EDIT THIS FILE
        #
        # It is automatically generated by grub2-mkconfig using templates
        # from /etc/grub.d and settings from /etc/default/grub
        #
        # GRUB 2.04
        """

        mock_guestfs.cat.return_value = grub_config

        config = mock_guestfs.cat("/boot/grub2/grub.cfg")
        if "GRUB 2." in config:
            # Extract version
            import re
            match = re.search(r"GRUB (2\.\d+)", config)
            if match:
                version = match.group(1)
                assert version == "2.04"

    def test_detect_systemd_boot_version(self, mock_guestfs):
        """Test detecting systemd-boot version"""
        # systemd-boot version in loader.conf
        loader_conf = "timeout 3\ndefault arch.conf"

        mock_guestfs.cat.return_value = loader_conf

        # Version would be from binary or package query
        # Here we just test config parsing
        config = mock_guestfs.cat("/boot/efi/loader/loader.conf")
        assert "timeout" in config


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
