# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Unit tests for VMCraft systemd service management (Phase 1).

Tests the SystemdManager class and its integration with VMCraft main API.
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call
import pytest

from hyper2kvm.core.vmcraft.systemd_mgr import SystemdManager


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    return logging.getLogger("test")


@pytest.fixture
def temp_guest_root(tmp_path):
    """Create a temporary guest root directory."""
    guest_root = tmp_path / "guest_root"
    guest_root.mkdir()

    # Create systemd binary to simulate systemd presence
    systemd_dir = guest_root / "usr/lib/systemd"
    systemd_dir.mkdir(parents=True)
    (systemd_dir / "systemd").touch()

    return guest_root


@pytest.fixture
def systemd_mgr(mock_logger, temp_guest_root):
    """Create SystemdManager instance."""
    return SystemdManager(mock_logger, str(temp_guest_root))


# ==================================================================================
# Systemd Availability Tests
# ==================================================================================

class TestSystemdAvailability:
    """Test systemd detection and availability checking."""

    def test_is_systemd_available_true(self, systemd_mgr):
        """Test systemd detection when binary exists."""
        assert systemd_mgr.is_systemd_available() is True

    def test_is_systemd_available_false(self, mock_logger, tmp_path):
        """Test systemd detection when binary doesn't exist."""
        empty_root = tmp_path / "empty_root"
        empty_root.mkdir()

        mgr = SystemdManager(mock_logger, str(empty_root))
        assert mgr.is_systemd_available() is False

    def test_is_systemd_available_cached(self, systemd_mgr):
        """Test that systemd availability is cached."""
        # First call
        result1 = systemd_mgr.is_systemd_available()

        # Second call should use cached value
        result2 = systemd_mgr.is_systemd_available()

        assert result1 == result2 == True

    def test_is_systemd_available_alternate_path(self, mock_logger, tmp_path):
        """Test systemd detection with alternate path."""
        guest_root = tmp_path / "guest"
        guest_root.mkdir()

        # Create systemd in /lib/systemd/systemd
        systemd_dir = guest_root / "lib/systemd"
        systemd_dir.mkdir(parents=True)
        (systemd_dir / "systemd").touch()

        mgr = SystemdManager(mock_logger, str(guest_root))
        assert mgr.is_systemd_available() is True


# ==================================================================================
# Service Control Tests
# ==================================================================================

class TestServiceControl:
    """Test service start/stop/restart operations."""

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.run_sudo')
    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._check_nspawn_available')
    def test_service_start_success(self, mock_nspawn, mock_run_sudo, systemd_mgr):
        """Test successful service start."""
        mock_nspawn.return_value = True
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = systemd_mgr.service_start("sshd")

        assert result["ok"] is True
        assert result["service"] == "sshd"
        assert result["action"] == "start"
        mock_run_sudo.assert_called_once()

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.run_sudo')
    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._check_nspawn_available')
    def test_service_stop_success(self, mock_nspawn, mock_run_sudo, systemd_mgr):
        """Test successful service stop."""
        mock_nspawn.return_value = True
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = systemd_mgr.service_stop("vmtoolsd")

        assert result["ok"] is True
        assert result["service"] == "vmtoolsd"
        assert result["action"] == "stop"

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.run_sudo')
    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._check_nspawn_available')
    def test_service_restart_success(self, mock_nspawn, mock_run_sudo, systemd_mgr):
        """Test successful service restart."""
        mock_nspawn.return_value = True
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = systemd_mgr.service_restart("sshd")

        assert result["ok"] is True
        assert result["service"] == "sshd"
        assert result["action"] == "restart"

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.run_sudo')
    def test_service_start_no_systemd(self, mock_run_sudo, mock_logger, tmp_path):
        """Test service start when systemd is not available."""
        empty_root = tmp_path / "no_systemd"
        empty_root.mkdir()

        mgr = SystemdManager(mock_logger, str(empty_root))
        result = mgr.service_start("sshd")

        assert result["ok"] is False
        assert result["error"] == "systemd_not_available"
        mock_run_sudo.assert_not_called()

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.run_sudo')
    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._check_nspawn_available')
    def test_service_start_failure(self, mock_nspawn, mock_run_sudo, systemd_mgr):
        """Test service start failure."""
        mock_nspawn.return_value = True
        mock_run_sudo.side_effect = Exception("Service not found")

        result = systemd_mgr.service_start("nonexistent")

        assert result["ok"] is False
        assert "Service not found" in result["error"]


# ==================================================================================
# Service Enable/Disable Tests
# ==================================================================================

class TestServiceEnableDisable:
    """Test service enable/disable operations."""

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.run_sudo')
    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._check_nspawn_available')
    def test_service_enable_success(self, mock_nspawn, mock_run_sudo, systemd_mgr):
        """Test successful service enable."""
        mock_nspawn.return_value = True
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = systemd_mgr.service_enable("qemu-guest-agent")

        assert result["ok"] is True
        assert result["service"] == "qemu-guest-agent"
        assert result["action"] == "enable"

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.run_sudo')
    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._check_nspawn_available')
    def test_service_disable_success(self, mock_nspawn, mock_run_sudo, systemd_mgr):
        """Test successful service disable."""
        mock_nspawn.return_value = True
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = systemd_mgr.service_disable("vmtoolsd")

        assert result["ok"] is True
        assert result["service"] == "vmtoolsd"
        assert result["action"] == "disable"


# ==================================================================================
# Service Status Tests
# ==================================================================================

class TestServiceStatus:
    """Test service status querying."""

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._run_systemctl')
    def test_service_status_running(self, mock_systemctl, systemd_mgr):
        """Test getting status of running service."""
        mock_systemctl.return_value = {
            "ok": True,
            "stdout": """● sshd.service - OpenSSH server daemon
   Loaded: loaded (/usr/lib/systemd/system/sshd.service; enabled)
   Active: active (running) since Mon 2026-01-26 10:00:00 UTC; 1h ago
"""
        }

        result = systemd_mgr.service_status("sshd")

        assert result["ok"] is True
        assert result["service"] == "sshd"
        assert result["loaded"] == "loaded"
        assert result["active"] == "active"
        assert result["sub"] == "running"

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._run_systemctl')
    def test_service_status_inactive(self, mock_systemctl, systemd_mgr):
        """Test getting status of inactive service."""
        mock_systemctl.return_value = {
            "ok": True,
            "stdout": """● vmtoolsd.service - VMware Tools Daemon
   Loaded: loaded (/usr/lib/systemd/system/vmtoolsd.service; disabled)
   Active: inactive (dead)
"""
        }

        result = systemd_mgr.service_status("vmtoolsd")

        assert result["ok"] is True
        assert result["loaded"] == "loaded"
        assert result["active"] == "inactive"
        assert result["sub"] == "dead"


# ==================================================================================
# Bulk Operations Tests
# ==================================================================================

class TestBulkOperations:
    """Test bulk service operations."""

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager.service_enable')
    def test_services_enable_multiple_all_success(self, mock_enable, systemd_mgr):
        """Test enabling multiple services successfully."""
        mock_enable.return_value = {"ok": True}

        services = ["sshd", "qemu-guest-agent", "chronyd"]
        results = systemd_mgr.services_enable_multiple(services)

        assert len(results) == 3
        assert all(results.values())
        assert mock_enable.call_count == 3

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager.service_enable')
    def test_services_enable_multiple_partial_failure(self, mock_enable, systemd_mgr):
        """Test enabling multiple services with some failures."""
        def side_effect(service):
            if service == "nonexistent":
                return {"ok": False, "error": "Service not found"}
            return {"ok": True}

        mock_enable.side_effect = side_effect

        services = ["sshd", "nonexistent", "chronyd"]
        results = systemd_mgr.services_enable_multiple(services)

        assert results["sshd"] is True
        assert results["nonexistent"] is False
        assert results["chronyd"] is True

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager.service_disable')
    def test_services_disable_multiple(self, mock_disable, systemd_mgr):
        """Test disabling multiple services."""
        mock_disable.return_value = {"ok": True}

        vmware_services = ["vmtoolsd", "vmware-tools", "open-vm-tools"]
        results = systemd_mgr.services_disable_multiple(vmware_services)

        assert len(results) == 3
        assert all(results.values())

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._run_systemctl')
    def test_services_mask(self, mock_systemctl, systemd_mgr):
        """Test masking services."""
        mock_systemctl.return_value = {"ok": True}

        services = ["vmtoolsd", "vmware-tools"]
        results = systemd_mgr.services_mask(services)

        assert len(results) == 2
        assert all(results.values())
        assert mock_systemctl.call_count == 2


# ==================================================================================
# Service Query Tests
# ==================================================================================

class TestServiceQuery:
    """Test service listing and querying."""

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._run_systemctl')
    def test_list_services_all(self, mock_systemctl, systemd_mgr):
        """Test listing all services."""
        mock_systemctl.return_value = {
            "ok": True,
            "stdout": """sshd.service                loaded active   running OpenSSH server daemon
vmtoolsd.service            loaded inactive dead    VMware Tools
chronyd.service             loaded active   running chrony NTP daemon
"""
        }

        services = systemd_mgr.list_services()

        assert len(services) == 3
        assert services[0]["name"] == "sshd.service"
        assert services[0]["active"] == "active"
        assert services[1]["name"] == "vmtoolsd.service"
        assert services[1]["active"] == "inactive"

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._run_systemctl')
    def test_list_services_by_state(self, mock_systemctl, systemd_mgr):
        """Test listing services filtered by state."""
        mock_systemctl.return_value = {
            "ok": True,
            "stdout": """failed-service.service    loaded failed  failed  Failed Service
another-fail.service      loaded failed  failed  Another Failed
"""
        }

        services = systemd_mgr.list_services(state="failed")

        assert len(services) == 2
        assert all(svc["active"] == "failed" for svc in services)

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager.list_services')
    def test_list_failed_services(self, mock_list, systemd_mgr):
        """Test listing only failed services."""
        mock_list.return_value = [
            {"name": "failed1.service", "active": "failed"},
            {"name": "failed2.service", "active": "failed"},
        ]

        failed = systemd_mgr.list_failed_services()

        assert len(failed) == 2
        assert "failed1.service" in failed
        assert "failed2.service" in failed

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._run_systemctl')
    def test_get_service_dependencies(self, mock_systemctl, systemd_mgr):
        """Test getting service dependencies."""
        mock_systemctl.return_value = {
            "ok": True,
            "stdout": """Requires=network.target dbus.service
Wants=network-online.target
After=network.target
Before=multi-user.target
"""
        }

        deps = systemd_mgr.get_service_dependencies("sshd.service")

        assert "network.target" in deps["requires"]
        assert "dbus.service" in deps["requires"]
        assert "network-online.target" in deps["wants"]
        assert "network.target" in deps["after"]
        assert "multi-user.target" in deps["before"]


# ==================================================================================
# Daemon Reload Tests
# ==================================================================================

class TestDaemonReload:
    """Test daemon-reload operations."""

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._run_systemctl')
    def test_daemon_reload_success(self, mock_systemctl, systemd_mgr):
        """Test successful daemon reload."""
        mock_systemctl.return_value = {"ok": True}

        result = systemd_mgr.daemon_reload()

        assert result["ok"] is True
        assert result["action"] == "daemon-reload"


# ==================================================================================
# Preset Tests
# ==================================================================================

class TestPreset:
    """Test systemctl preset operations."""

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._run_systemctl')
    def test_systemctl_preset(self, mock_systemctl, systemd_mgr):
        """Test applying systemctl preset."""
        mock_systemctl.return_value = {"ok": True}

        result = systemd_mgr.systemctl_preset("sshd.service")

        assert result["ok"] is True
        assert result["action"] == "preset"
        assert result["service"] == "sshd.service"


# ==================================================================================
# Service Active/Enabled Check Tests
# ==================================================================================

class TestServiceChecks:
    """Test is_active and is_enabled checks."""

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._run_systemctl')
    def test_is_service_active_true(self, mock_systemctl, systemd_mgr):
        """Test checking if service is active."""
        mock_systemctl.return_value = {"ok": True, "stdout": "active"}

        assert systemd_mgr.is_service_active("sshd") is True

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._run_systemctl')
    def test_is_service_active_false(self, mock_systemctl, systemd_mgr):
        """Test checking if service is inactive."""
        mock_systemctl.return_value = {"ok": True, "stdout": "inactive"}

        assert systemd_mgr.is_service_active("vmtoolsd") is False

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._run_systemctl')
    def test_is_service_enabled_true(self, mock_systemctl, systemd_mgr):
        """Test checking if service is enabled."""
        mock_systemctl.return_value = {"ok": True, "stdout": "enabled"}

        assert systemd_mgr.is_service_enabled("sshd") is True

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._run_systemctl')
    def test_is_service_enabled_false(self, mock_systemctl, systemd_mgr):
        """Test checking if service is disabled."""
        mock_systemctl.return_value = {"ok": True, "stdout": "disabled"}

        assert systemd_mgr.is_service_enabled("vmtoolsd") is False


# ==================================================================================
# Nspawn vs Chroot Tests
# ==================================================================================

class TestNspawnVsChroot:
    """Test systemd-nspawn vs chroot fallback."""

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.run_sudo')
    def test_check_nspawn_available_true(self, mock_run_sudo, systemd_mgr):
        """Test detecting systemd-nspawn availability."""
        mock_result = Mock()
        mock_result.stdout = "/usr/bin/systemd-nspawn"
        mock_run_sudo.return_value = mock_result

        assert systemd_mgr._check_nspawn_available() is True

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.run_sudo')
    def test_check_nspawn_available_false(self, mock_run_sudo, systemd_mgr):
        """Test handling missing systemd-nspawn."""
        mock_run_sudo.side_effect = Exception("Command not found")

        assert systemd_mgr._check_nspawn_available() is False

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.run_sudo')
    def test_run_systemctl_with_nspawn(self, mock_run_sudo, systemd_mgr):
        """Test running systemctl with systemd-nspawn."""
        systemd_mgr._use_nspawn = True

        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = systemd_mgr._run_systemctl(["is-enabled", "sshd"])

        assert result["ok"] is True
        # Verify systemd-nspawn was used
        args = mock_run_sudo.call_args[0][1]
        assert "systemd-nspawn" in args

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.run_sudo')
    def test_run_systemctl_with_chroot(self, mock_run_sudo, systemd_mgr):
        """Test running systemctl with chroot fallback."""
        systemd_mgr._use_nspawn = False

        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = systemd_mgr._run_systemctl(["is-enabled", "sshd"])

        assert result["ok"] is True
        # Verify chroot was used
        args = mock_run_sudo.call_args[0][1]
        assert "chroot" in args
