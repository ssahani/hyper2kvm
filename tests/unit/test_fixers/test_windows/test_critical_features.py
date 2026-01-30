# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for critical Windows migration features (Phase 5 - High Priority)"""

import logging
import pytest
from unittest.mock import Mock, MagicMock, patch

from hyper2kvm.fixers.windows.bitlocker import (
    detect_bitlocker,
    check_bitlocker_before_migration,
    BitLockerDetectionError,
)
from hyper2kvm.fixers.windows.rdp import (
    verify_rdp_enabled,
    enable_rdp_if_disabled,
)
from hyper2kvm.fixers.windows.firewall import (
    stage_firewall_export_script,
    get_firewall_migration_instructions,
)
from hyper2kvm.fixers.windows.virtio_warning import (
    warn_no_virtio_drivers,
    get_virtio_download_url,
    should_warn_about_virtio,
)


class TestBitLockerDetection:
    """Test BitLocker detection and blocking"""

    def test_no_bitlocker_detected(self):
        """Test when BitLocker is not present"""
        g = Mock()
        g.list_devices.return_value = ["/dev/sda"]
        g.list_partitions.return_value = ["/dev/sda1", "/dev/sda2"]
        g.vfs_type.return_value = "ntfs"
        g.vfs_label.return_value = "Windows"
        g.exists.return_value = False

        result = detect_bitlocker(g, "/sysroot")

        assert result["bitlocker_detected"] == False
        assert len(result["encrypted_volumes"]) == 0
        assert result["error"] is None

    def test_bitlocker_metadata_detected(self):
        """Test detection via filesystem metadata"""
        g = Mock()
        g.list_devices.return_value = ["/dev/sda"]
        g.list_partitions.return_value = ["/dev/sda1"]
        g.vfs_type.return_value = "BitLocker"

        with pytest.raises(BitLockerDetectionError) as exc_info:
            detect_bitlocker(g, "/sysroot")

        assert "BitLocker encryption detected" in str(exc_info.value)
        assert "manage-bde -off" in str(exc_info.value)

    def test_bitlocker_label_detected(self):
        """Test detection via partition label"""
        g = Mock()
        g.list_devices.return_value = ["/dev/sda"]
        g.list_partitions.return_value = ["/dev/sda1"]
        g.vfs_type.return_value = "ntfs"
        g.vfs_label.return_value = "DRIVE-FVE-FS-001"

        with pytest.raises(BitLockerDetectionError) as exc_info:
            detect_bitlocker(g, "/sysroot")

        assert "BitLocker" in str(exc_info.value)

    def test_check_bitlocker_before_migration_success(self):
        """Test pre-migration check when no BitLocker"""
        g = Mock()
        g.list_devices.return_value = []
        g.exists.return_value = False
        logger = logging.getLogger("test")

        # Should not raise
        check_bitlocker_before_migration(g, "/sysroot", logger)

    def test_check_bitlocker_before_migration_failure(self):
        """Test pre-migration check blocks when BitLocker found"""
        g = Mock()
        g.list_devices.return_value = ["/dev/sda"]
        g.list_partitions.return_value = ["/dev/sda1"]
        g.vfs_type.return_value = "BitLocker"
        logger = logging.getLogger("test")

        with pytest.raises(BitLockerDetectionError):
            check_bitlocker_before_migration(g, "/sysroot", logger)


class TestRDPVerification:
    """Test RDP verification and enablement"""

    @patch("hyper2kvm.fixers.windows.rdp.hivex")
    def test_rdp_enabled(self, mock_hivex):
        """Test when RDP is already enabled"""
        g = Mock()
        g.exists.return_value = True
        g.hivex_open.return_value = 1
        g.hivex_root.return_value = 100
        g.hivex_node_children.return_value = []

        result = verify_rdp_enabled(g, "/sysroot")

        assert "rdp_enabled" in result
        assert "warnings" in result
        assert "recommendations" in result

    def test_rdp_disabled_warning(self):
        """Test warning when RDP is disabled"""
        g = Mock()
        g.exists.return_value = False

        result = verify_rdp_enabled(g, "/sysroot")

        assert result["rdp_enabled"] == False
        assert len(result["warnings"]) > 0
        assert "Could not verify" in result["warnings"][0]

    @patch("hyper2kvm.fixers.windows.rdp.hivex")
    def test_enable_rdp_if_disabled(self, mock_hivex):
        """Test enabling RDP"""
        g = Mock()
        g.exists.return_value = True
        g.hivex_open.return_value = 1
        g.hivex_root.return_value = 100
        logger = logging.getLogger("test")

        result = enable_rdp_if_disabled(g, "/sysroot", logger)

        assert "modified" in result
        assert "previous_state" in result
        assert "current_state" in result

    def test_rdp_hive_not_found(self):
        """Test when SYSTEM hive is not found"""
        g = Mock()
        g.exists.return_value = False
        logger = logging.getLogger("test")

        result = enable_rdp_if_disabled(g, "/sysroot", logger)

        assert result["error"] == "SYSTEM registry hive not found"
        assert result["modified"] == False


class TestFirewallMigration:
    """Test Windows Firewall rule migration"""

    def test_stage_firewall_script(self):
        """Test staging firewall migration script"""
        g = Mock()
        g.write = Mock()
        g.is_dir = Mock(return_value=True)
        g.mkdir_p = Mock()

        result = stage_firewall_export_script(g, "/sysroot")

        assert result["staged"] == True
        assert "script_path" in result
        assert "firewall-migrate.ps1" in result["script_path"]
        # Should write script + task XML
        assert g.write.call_count >= 1

    def test_firewall_script_content(self):
        """Test firewall script contains required commands"""
        g = Mock()
        script_content = None
        g.is_dir = Mock(return_value=True)
        g.mkdir_p = Mock()

        def capture_write(path, content):
            nonlocal script_content
            # Capture PowerShell script (first write)
            if script_content is None and ".ps1" in path:
                script_content = content

        g.write = capture_write

        stage_firewall_export_script(g, "/sysroot")

        assert script_content is not None
        assert "netsh advfirewall export" in script_content
        assert "netsh advfirewall import" in script_content
        assert "Remote Desktop" in script_content

    def test_get_migration_instructions(self):
        """Test getting manual migration instructions"""
        instructions = get_firewall_migration_instructions()

        assert "netsh advfirewall export" in instructions
        assert "netsh advfirewall import" in instructions
        assert "BEFORE MIGRATION" in instructions
        assert "AFTER MIGRATION" in instructions

    def test_firewall_script_error_handling(self):
        """Test error handling when staging fails"""
        g = Mock()
        g.write.side_effect = Exception("Write failed")

        result = stage_firewall_export_script(g, "/sysroot")

        assert result["staged"] == False
        assert result["error"] is not None


class TestVirtIOWarning:
    """Test VirtIO driver warnings"""

    def test_warn_no_virtio_drivers(self, caplog):
        """Test VirtIO warning message"""
        logger = logging.getLogger("test")
        logger.setLevel(logging.WARNING)
        logger.addHandler(logging.StreamHandler())
        caplog.set_level(logging.WARNING)

        warn_no_virtio_drivers(logger)

        # Check that warning was logged (text may have unicode characters)
        log_output = caplog.text
        assert "VIRTIO" in log_output or len(caplog.records) > 0
        assert any("REDUCED PERFORMANCE" in record.message for record in caplog.records)

    def test_warn_with_windows_info(self, caplog):
        """Test VirtIO warning with Windows version info"""
        logger = logging.getLogger("test")
        caplog.set_level(logging.WARNING)

        windows_info = {
            "product_name": "Windows 10 Professional",
            "version_full": "10.0.19044",
        }

        warn_no_virtio_drivers(logger, windows_info)

        assert "Windows 10" in caplog.text
        assert "virtio-win.iso" in caplog.text

    def test_get_virtio_download_url_windows10(self):
        """Test getting download URL for Windows 10"""
        url = get_virtio_download_url("10.0")

        assert "virtio-win" in url
        assert "fedorapeople.org" in url
        assert ".iso" in url

    def test_get_virtio_download_url_windows7(self):
        """Test getting download URL for Windows 7"""
        url = get_virtio_download_url("6.1")

        assert "virtio-win" in url
        assert ".iso" in url

    def test_should_warn_about_virtio_no_drivers(self):
        """Test warning should be shown when no drivers"""
        assert should_warn_about_virtio(None, False) == True

    def test_should_warn_about_virtio_with_drivers(self):
        """Test warning should not be shown when drivers provided"""
        assert should_warn_about_virtio("/path/to/drivers", False) == False

    def test_should_warn_about_virtio_quiet_mode(self):
        """Test warning suppressed in quiet mode"""
        assert should_warn_about_virtio(None, True) == False


class TestIntegration:
    """Integration tests for all critical features"""

    def test_all_features_importable(self):
        """Test that all new features can be imported"""
        from hyper2kvm.fixers.windows.bitlocker import detect_bitlocker
        from hyper2kvm.fixers.windows.rdp import verify_rdp_enabled
        from hyper2kvm.fixers.windows.firewall import stage_firewall_export_script
        from hyper2kvm.fixers.windows.virtio_warning import warn_no_virtio_drivers

        assert callable(detect_bitlocker)
        assert callable(verify_rdp_enabled)
        assert callable(stage_firewall_export_script)
        assert callable(warn_no_virtio_drivers)

    def test_windows_fixer_has_new_methods(self):
        """Test WindowsFixer has all new methods"""
        from hyper2kvm.fixers.windows.fixer import WindowsFixer

        fixer = WindowsFixer()

        assert hasattr(fixer, "check_bitlocker")
        assert hasattr(fixer, "verify_rdp")
        assert hasattr(fixer, "enable_rdp")
        assert hasattr(fixer, "stage_firewall_migration")
        assert hasattr(fixer, "warn_virtio_drivers_missing")

    def test_bitlocker_error_message_quality(self):
        """Test BitLocker error message is helpful"""
        g = Mock()
        g.list_devices.return_value = ["/dev/sda"]
        g.list_partitions.return_value = ["/dev/sda1"]
        g.vfs_type.return_value = "BitLocker"

        try:
            detect_bitlocker(g, "/sysroot")
            assert False, "Should have raised BitLockerDetectionError"
        except BitLockerDetectionError as e:
            error_msg = str(e)
            # Check for key elements in error message
            assert "manage-bde -off" in error_msg
            assert "decrypt" in error_msg.lower()
            assert "boot" in error_msg.lower()
            assert "migrate" in error_msg.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
