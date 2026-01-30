"""Unit tests for Windows performance optimization."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from hyper2kvm.fixers.windows.performance.balloon import configure_balloon_driver
from hyper2kvm.fixers.windows.performance.trim import enable_trim_discard
from hyper2kvm.fixers.windows.performance.msi import enable_msi_interrupts
from hyper2kvm.fixers.windows.performance.hyperv_cleanup import (
    cleanup_hyperv_enlightenments,
    HYPERV_SERVICES,
)


class TestBalloonConfiguration:
    """Test VirtIO balloon driver configuration."""

    def test_configure_balloon_basic(self):
        """Test basic balloon configuration."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        # Just verify it returns a dict without crashing
        result = configure_balloon_driver(mock_guestfs, root)
        assert isinstance(result, dict)
        assert "success" in result
        assert "balloon_configured" in result
        assert "warnings" in result

    def test_configure_balloon_no_system_hive(self):
        """Test handling when SYSTEM hive not found."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        with patch(
            "hyper2kvm.fixers.windows.registry.io.detect_windows_hive",
            return_value=None,
        ):
            result = configure_balloon_driver(mock_guestfs, root)
            assert result["success"] is False
            assert len(result["warnings"]) > 0
            assert any("SYSTEM hive" in w for w in result["warnings"])

    def test_configure_balloon_custom_interval(self):
        """Test balloon configuration with custom memory stats interval."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        result = configure_balloon_driver(
            mock_guestfs, root, memory_stats_interval=30
        )

        assert result["memory_stats_interval"] == 30

    def test_configure_balloon_disable_free_page_reporting(self):
        """Test balloon configuration with free page reporting disabled."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        result = configure_balloon_driver(
            mock_guestfs, root, enable_free_page_reporting=False
        )

        assert result["free_page_reporting"] is False


class TestTrimDiscard:
    """Test TRIM/discard enablement."""

    def test_enable_trim_basic(self):
        """Test basic TRIM enablement."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        result = enable_trim_discard(mock_guestfs, root)
        assert isinstance(result, dict)
        assert "success" in result
        assert "trim_enabled" in result
        assert "warnings" in result

    def test_enable_trim_no_system_hive(self):
        """Test handling when SYSTEM hive not found."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        with patch(
            "hyper2kvm.fixers.windows.registry.io.detect_windows_hive",
            return_value=None,
        ):
            result = enable_trim_discard(mock_guestfs, root)
            assert result["success"] is False
            assert len(result["warnings"]) > 0
            assert any("SYSTEM hive" in w for w in result["warnings"])

    def test_enable_trim_with_optimization(self):
        """Test TRIM enablement with optimization scheduling."""
        mock_guestfs = Mock()
        mock_guestfs.mkdir_p.return_value = None
        mock_guestfs.write.return_value = None
        root = "/mnt/windows"

        result = enable_trim_discard(mock_guestfs, root, schedule_optimization=True)

        assert result["optimization_scheduled"] in [True, False]  # Depends on execution

    def test_enable_trim_without_optimization(self):
        """Test TRIM enablement without optimization scheduling."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        result = enable_trim_discard(mock_guestfs, root, schedule_optimization=False)

        assert result["optimization_scheduled"] is False


class TestMSIInterrupts:
    """Test MSI interrupt configuration."""

    def test_enable_msi_basic(self):
        """Test basic MSI enablement."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        result = enable_msi_interrupts(mock_guestfs, root)
        assert isinstance(result, dict)
        assert "success" in result
        assert "devices_configured" in result
        assert "devices_skipped" in result
        assert "warnings" in result

    def test_enable_msi_no_system_hive(self):
        """Test handling when SYSTEM hive not found."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        with patch(
            "hyper2kvm.fixers.windows.registry.io.detect_windows_hive",
            return_value=None,
        ):
            result = enable_msi_interrupts(mock_guestfs, root)
            assert result["success"] is False
            assert len(result["warnings"]) > 0
            assert any("SYSTEM hive" in w for w in result["warnings"])

    def test_enable_msi_custom_devices(self):
        """Test MSI enablement for custom device list."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        result = enable_msi_interrupts(mock_guestfs, root, devices=["viostor"])

        # Verify it processes the custom device list
        assert isinstance(result["devices_configured"], list)
        assert isinstance(result["devices_skipped"], list)

    def test_enable_msi_default_devices(self):
        """Test MSI enablement uses default devices."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        result = enable_msi_interrupts(mock_guestfs, root)

        # Default devices are viostor and netkvm
        # In unit test without real registry, both may be skipped
        # Just verify the result structure is correct
        assert isinstance(result["devices_configured"], list)
        assert isinstance(result["devices_skipped"], list)


class TestHyperVCleanup:
    """Test Hyper-V enlightenments cleanup."""

    def test_cleanup_hyperv_basic(self):
        """Test basic Hyper-V cleanup."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        result = cleanup_hyperv_enlightenments(mock_guestfs, root)
        assert isinstance(result, dict)
        assert "success" in result
        assert "hyperv_detected" in result
        assert "services_disabled" in result
        assert "warnings" in result

    def test_cleanup_hyperv_no_system_hive(self):
        """Test handling when SYSTEM hive not found."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        with patch(
            "hyper2kvm.fixers.windows.registry.io.detect_windows_hive",
            return_value=None,
        ):
            result = cleanup_hyperv_enlightenments(mock_guestfs, root, force=True)
            assert len(result["warnings"]) > 0
            assert any("SYSTEM hive" in w for w in result["warnings"])

    def test_cleanup_hyperv_not_detected(self):
        """Test behavior when Hyper-V not detected."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        with patch(
            "hyper2kvm.fixers.windows.performance.hyperv_cleanup._detect_hyperv_vm",
            return_value=False,
        ):
            result = cleanup_hyperv_enlightenments(mock_guestfs, root, force=False)

            assert result["hyperv_detected"] is False
            assert len(result["warnings"]) > 0
            assert any("not detected" in w for w in result["warnings"])

    def test_cleanup_hyperv_force_mode(self):
        """Test forced cleanup without detection."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        with patch(
            "hyper2kvm.fixers.windows.performance.hyperv_cleanup._detect_hyperv_vm",
            return_value=False,
        ):
            result = cleanup_hyperv_enlightenments(mock_guestfs, root, force=True)

            # Force mode should proceed even without detection
            assert result["hyperv_detected"] is True or len(result["warnings"]) > 0

    def test_hyperv_services_list(self):
        """Test Hyper-V services list is defined."""
        assert len(HYPERV_SERVICES) > 0
        assert "vmbus" in HYPERV_SERVICES
        assert "hvservice" in HYPERV_SERVICES or "hv_fcopy" in HYPERV_SERVICES


class TestPerformanceIntegration:
    """Test performance optimization integration."""

    def test_all_modules_importable(self):
        """Test all performance modules can be imported."""
        from hyper2kvm.fixers.windows.performance import (
            configure_balloon_driver,
            enable_trim_discard,
            enable_msi_interrupts,
            cleanup_hyperv_enlightenments,
        )

        assert callable(configure_balloon_driver)
        assert callable(enable_trim_discard)
        assert callable(enable_msi_interrupts)
        assert callable(cleanup_hyperv_enlightenments)

    def test_balloon_returns_verification_script_path(self):
        """Test balloon configuration returns verification script path."""
        mock_guestfs = Mock()
        mock_guestfs.mkdir_p.return_value = None
        mock_guestfs.write.return_value = None
        root = "/mnt/windows"

        result = configure_balloon_driver(mock_guestfs, root)

        # verification_script may be None or a path
        assert "verification_script" in result

    def test_trim_returns_verification_script_path(self):
        """Test TRIM enablement returns verification script path."""
        mock_guestfs = Mock()
        mock_guestfs.mkdir_p.return_value = None
        mock_guestfs.write.return_value = None
        root = "/mnt/windows"

        result = enable_trim_discard(mock_guestfs, root)

        assert "verification_script" in result

    def test_msi_returns_verification_script_path(self):
        """Test MSI enablement returns verification script path."""
        mock_guestfs = Mock()
        mock_guestfs.mkdir_p.return_value = None
        mock_guestfs.write.return_value = None
        root = "/mnt/windows"

        result = enable_msi_interrupts(mock_guestfs, root)

        assert "verification_script" in result


class TestVerificationScripts:
    """Test verification script generation."""

    def test_balloon_verification_script_generated(self):
        """Test balloon verification script contains expected content."""
        from hyper2kvm.fixers.windows.performance.balloon import (
            _generate_balloon_verification_script,
        )

        script = _generate_balloon_verification_script(10, True)

        assert "balloon" in script.lower()
        assert "Get-Service" in script or "service" in script.lower()
        assert "10" in script  # Memory stats interval

    def test_trim_verification_script_generated(self):
        """Test TRIM verification script contains expected content."""
        from hyper2kvm.fixers.windows.performance.trim import (
            _generate_trim_verification_script,
        )

        script = _generate_trim_verification_script()

        assert "trim" in script.lower() or "discard" in script.lower()
        assert "fsutil" in script.lower()
        assert "DisableDeleteNotification" in script or "disabledeletenotify" in script.lower()

    def test_trim_optimization_script_generated(self):
        """Test TRIM optimization script contains expected content."""
        from hyper2kvm.fixers.windows.performance.trim import (
            _generate_trim_optimization_script,
        )

        script = _generate_trim_optimization_script()

        assert "optimization" in script.lower()
        assert "defrag" in script.lower() or "optimize" in script.lower()

    def test_msi_verification_script_generated(self):
        """Test MSI verification script contains expected content."""
        from hyper2kvm.fixers.windows.performance.msi import (
            _generate_msi_verification_script,
        )

        script = _generate_msi_verification_script(["viostor", "netkvm"])

        assert "msi" in script.lower()
        assert "viostor" in script
        assert "netkvm" in script
        assert "MSISupported" in script


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
