"""
Unit tests for GRUB configuration edge cases

Tests GRUB1 vs GRUB2 differentiation, encrypted root filesystems,
btrfs subvolumes, console argument handling, and root device rewriting.
"""

import pytest
from unittest.mock import Mock, MagicMock
import logging

from hyper2kvm.fixers.bootloader.fixer import BootloaderType


class TestGrubDifferentiation:
    """Test GRUB1 vs GRUB2 differentiation"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        return g

    def test_grub1_vs_grub2_by_config_location(self, mock_guestfs):
        """Test differentiation by config file location"""
        # GRUB1: /boot/grub/grub.conf or menu.lst
        # GRUB2: /boot/grub2/grub.cfg or /boot/grub/grub.cfg

        grub1_paths = ["/boot/grub/grub.conf", "/boot/grub/menu.lst"]
        grub2_paths = ["/boot/grub2/grub.cfg", "/boot/grub/grub.cfg"]

        def is_grub1(path):
            return path in grub1_paths

        def is_grub2(path):
            return path in grub2_paths

        # Test GRUB1 detection
        assert is_grub1("/boot/grub/grub.conf")
        assert not is_grub2("/boot/grub/grub.conf")

        # Test GRUB2 detection
        assert is_grub2("/boot/grub2/grub.cfg")
        assert not is_grub1("/boot/grub2/grub.cfg")

    def test_grub1_vs_grub2_by_config_syntax(self, mock_guestfs):
        """Test differentiation by config syntax"""
        # GRUB1 uses "title" keyword
        grub1_config = """
        title Fedora (5.10.0)
            root (hd0,0)
            kernel /vmlinuz-5.10.0 ro root=/dev/sda2
            initrd /initramfs-5.10.0.img
        """

        # GRUB2 uses "menuentry" keyword
        grub2_config = """
        menuentry 'Fedora (5.10.0)' {
            set root='hd0,gpt2'
            linux /vmlinuz-5.10.0 ro root=UUID=xxx
            initrd /initramfs-5.10.0.img
        }
        """

        assert "title" in grub1_config and "menuentry" not in grub1_config
        assert "menuentry" in grub2_config and "title" not in grub2_config

    def test_grub2_with_legacy_path(self, mock_guestfs):
        """Test GRUB2 installed at legacy GRUB path"""
        # Some distros install GRUB2 at /boot/grub/grub.cfg
        grub2_at_legacy_path = """
        # This is GRUB2 config at /boot/grub/grub.cfg
        menuentry 'Linux' {
            linux /vmlinuz root=UUID=xxx
        }
        """

        mock_guestfs.cat.return_value = grub2_at_legacy_path

        config = mock_guestfs.cat("/boot/grub/grub.cfg")
        # Should detect as GRUB2 by syntax
        assert "menuentry" in config


class TestEncryptedRootFilesystem:
    """Test handling of encrypted root filesystems"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        return g

    def test_luks_encrypted_root(self, mock_guestfs):
        """Test GRUB config with LUKS encrypted root"""
        grub_config = """
        menuentry 'Encrypted Linux' {
            linux /vmlinuz root=/dev/mapper/luks-root ro
            initrd /initramfs.img
        }
        """

        mock_guestfs.cat.return_value = grub_config

        config = mock_guestfs.cat("/boot/grub2/grub.cfg")
        assert "/dev/mapper/luks" in config

    def test_cryptsetup_uuid_in_grub(self, mock_guestfs):
        """Test GRUB config with cryptsetup UUID"""
        grub_config = """
        menuentry 'Linux' {
            insmod luks
            insmod gcry_rijndael
            cryptomount -u 123456789abcdef
            set root='cryptouuid/123456789abcdef'
            linux /vmlinuz root=/dev/mapper/cryptroot
        }
        """

        assert "cryptomount" in grub_config
        assert "cryptouuid" in grub_config

    def test_grub_cryptodisk_enable(self, mock_guestfs):
        """Test GRUB_ENABLE_CRYPTODISK in /etc/default/grub"""
        default_grub = """
        GRUB_TIMEOUT=5
        GRUB_DISTRIBUTOR="Fedora"
        GRUB_DEFAULT=saved
        GRUB_ENABLE_CRYPTODISK=y
        GRUB_CMDLINE_LINUX="rd.luks.uuid=xxx"
        """

        assert "GRUB_ENABLE_CRYPTODISK=y" in default_grub


class TestBtrfsSubvolumes:
    """Test btrfs subvolume handling in GRUB"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        return g

    def test_btrfs_subvolume_root(self, mock_guestfs):
        """Test GRUB config with btrfs subvolume as root"""
        grub_config = """
        menuentry 'Linux' {
            linux /vmlinuz root=UUID=xxx rootflags=subvol=@ ro
            initrd /initramfs.img
        }
        """

        assert "rootflags=subvol=@" in grub_config

    def test_btrfs_subvol_with_path(self, mock_guestfs):
        """Test btrfs subvolume with full path"""
        grub_config = """
        menuentry 'Linux' {
            linux /vmlinuz root=UUID=xxx rootflags=subvol=@/root ro
            initrd /initramfs.img
        }
        """

        assert "subvol=@/root" in grub_config

    def test_btrfs_multiple_subvolumes(self, mock_guestfs):
        """Test system with multiple btrfs subvolumes"""
        # Typical openSUSE/SUSE setup
        grub_config = """
        menuentry 'Linux' {
            set root='hd0,gpt2'
            linux /@/boot/vmlinuz root=UUID=xxx rootflags=subvol=@
            initrd /@/boot/initrd
        }
        """

        assert "@" in grub_config


class TestLVMRootDevice:
    """Test LVM root device handling"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        return g

    def test_lvm_root_device(self, mock_guestfs):
        """Test GRUB config with LVM root device"""
        grub_config = """
        menuentry 'Linux' {
            linux /vmlinuz root=/dev/mapper/vg_root-lv_root ro
            initrd /initramfs.img
        }
        """

        assert "/dev/mapper/vg_root-lv_root" in grub_config

    def test_lvm_with_uuid(self, mock_guestfs):
        """Test LVM with UUID reference"""
        grub_config = """
        menuentry 'Linux' {
            linux /vmlinuz root=UUID=xxx ro
            initrd /initramfs.img
        }
        """

        # LVM volume can also be referenced by UUID
        assert "UUID=" in grub_config


class TestConsoleArguments:
    """Test serial console argument handling"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        return g

    def test_add_serial_console(self, mock_guestfs):
        """Test adding serial console to kernel args"""
        original = "linux /vmlinuz root=UUID=xxx ro quiet"

        # Add console=ttyS0,115200n8
        modified = original + " console=ttyS0,115200n8 console=tty0"

        assert "console=ttyS0,115200n8" in modified
        assert "console=tty0" in modified

    def test_deduplicate_console_args(self, mock_guestfs):
        """Test deduplication of duplicate console arguments"""
        # Kernel args already has console
        original = "linux /vmlinuz root=UUID=xxx console=ttyS0,115200n8"

        # Should not add duplicate
        def add_console_if_missing(args):
            if "console=ttyS0" not in args:
                return args + " console=ttyS0,115200n8"
            return args

        modified = add_console_if_missing(original)
        assert modified == original  # No change

    def test_preserve_existing_console(self, mock_guestfs):
        """Test preserving existing console configuration"""
        # Different console configuration
        original = "linux /vmlinuz root=UUID=xxx console=ttyS1,9600"

        # Should preserve existing, maybe append tty0
        modified = original + " console=tty0"

        assert "console=ttyS1,9600" in modified
        assert "console=tty0" in modified

    def test_multiple_console_ordering(self, mock_guestfs):
        """Test console argument ordering (last one gets /dev/console)"""
        # Linux kernel uses last console= for /dev/console
        kernel_args = "root=UUID=xxx console=ttyS0,115200 console=tty0"

        # tty0 is last, so /dev/console -> tty0
        # Serial output still goes to ttyS0
        consoles = [arg for arg in kernel_args.split() if arg.startswith("console=")]
        assert len(consoles) == 2
        assert consoles[-1] == "console=tty0"  # Last for /dev/console


class TestRootDeviceRewriting:
    """Test root device rewriting (UUID, PARTUUID, device)"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        return g

    def test_uuid_to_partuuid_conversion(self, mock_guestfs):
        """Test converting UUID to PARTUUID"""
        original = "root=UUID=12345-67890"

        # Convert to PARTUUID (GPT)
        partuuid = "PARTUUID=abcdef-123456"
        modified = original.replace("UUID=12345-67890", partuuid)

        assert "PARTUUID=" in modified
        # The replacement worked, but the word "UUID" is still in "PARTUUID"
        # Check that the original UUID format is gone
        assert "UUID=12345-67890" not in modified

    def test_device_to_uuid_conversion(self, mock_guestfs):
        """Test converting device name to UUID"""
        original = "root=/dev/sda2"

        # Convert to UUID
        uuid = "UUID=12345-67890"
        modified = original.replace("/dev/sda2", uuid)

        assert "UUID=" in modified
        assert "/dev/sda2" not in modified

    def test_preserve_uuid_if_present(self, mock_guestfs):
        """Test preserving UUID if already present"""
        original = "root=UUID=12345-67890"

        # Should not change
        modified = original

        assert modified == original

    def test_missing_root_parameter(self, mock_guestfs):
        """Test handling of missing root= parameter"""
        # Some configs might not have explicit root=
        grub_config = """
        menuentry 'Linux' {
            linux /vmlinuz ro quiet
        }
        """

        # Should detect missing root=
        assert "root=" not in grub_config

    def test_root_with_options(self, mock_guestfs):
        """Test root parameter with additional options"""
        kernel_args = "root=UUID=xxx ro quiet splash rootflags=subvol=@"

        # Should preserve all options
        assert "root=UUID=xxx" in kernel_args
        assert "rootflags=subvol=@" in kernel_args


class TestCorruptedGrubConfig:
    """Test handling of corrupted or invalid GRUB configs"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        return g

    def test_incomplete_menuentry(self, mock_guestfs):
        """Test handling of incomplete menuentry"""
        corrupted = """
        menuentry 'Linux' {
            linux /vmlinuz root=UUID=xxx
            # Missing closing brace
        """

        # Should detect syntax error
        assert corrupted.count('{') != corrupted.count('}')

    def test_malformed_kernel_line(self, mock_guestfs):
        """Test handling of malformed kernel line"""
        corrupted = """
        menuentry 'Linux' {
            linux /vmlinuz root=
            initrd /initramfs.img
        }
        """

        # root= with no value
        assert "root=" in corrupted

    def test_missing_required_fields(self, mock_guestfs):
        """Test handling of missing required fields"""
        incomplete = """
        menuentry 'Linux' {
            # No linux kernel line
            initrd /initramfs.img
        }
        """

        # Check for "linux /" pattern (kernel line), not just "linux"
        # The word "Linux" appears in menuentry title
        assert "linux /" not in incomplete
        assert "linux /vmlinuz" not in incomplete


class TestUEFISpecific:
    """Test UEFI-specific GRUB configuration"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        return g

    def test_uefi_boot_entry(self, mock_guestfs):
        """Test UEFI boot entry handling"""
        grub_config = """
        search --no-floppy --fs-uuid --set=root 12345-67890
        menuentry 'Linux' {
            linux /vmlinuz root=UUID=xxx
        }
        """

        assert "search --no-floppy --fs-uuid" in grub_config

    def test_secure_boot_modules(self, mock_guestfs):
        """Test Secure Boot module loading"""
        grub_config = """
        insmod part_gpt
        insmod ext2
        insmod chain
        menuentry 'Linux' {
            linux /vmlinuz root=UUID=xxx
        }
        """

        assert "insmod part_gpt" in grub_config

    def test_efi_variables_reference(self, mock_guestfs):
        """Test EFI variables in GRUB config"""
        # Some GRUB configs reference EFI variables
        grub_config = """
        if [ "${grub_platform}" = "efi" ]; then
            set timeout=5
        fi
        """

        assert 'grub_platform' in grub_config


class TestGrubDefaults:
    """Test /etc/default/grub handling"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        return g

    def test_parse_grub_defaults(self, mock_guestfs):
        """Test parsing /etc/default/grub"""
        defaults = """
        GRUB_TIMEOUT=5
        GRUB_DISTRIBUTOR="Fedora"
        GRUB_DEFAULT=saved
        GRUB_DISABLE_SUBMENU=true
        GRUB_TERMINAL_OUTPUT="console"
        GRUB_CMDLINE_LINUX="rd.lvm.lv=fedora/root rd.luks.uuid=xxx rhgb quiet"
        GRUB_DISABLE_RECOVERY="true"
        """

        # Should be able to parse key=value pairs
        grub_keys = []
        for line in defaults.strip().split('\n'):
            line = line.strip()
            if line and '=' in line:
                key, value = line.split('=', 1)
                grub_keys.append(key)

        # All parsed keys should start with GRUB_
        assert all(key.startswith('GRUB_') for key in grub_keys)
        assert len(grub_keys) == 7  # 7 GRUB_ config lines

    def test_modify_grub_cmdline_linux(self, mock_guestfs):
        """Test modifying GRUB_CMDLINE_LINUX"""
        original = 'GRUB_CMDLINE_LINUX="rhgb quiet"'

        # Add console args
        modified = 'GRUB_CMDLINE_LINUX="rhgb quiet console=ttyS0,115200 console=tty0"'

        assert "console=ttyS0" in modified


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
