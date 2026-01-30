# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Unit tests for VMCraft systemd unit file management (Phase 4).

Tests the SystemdUnitsManager class and unit file management APIs.
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
import pytest

from hyper2kvm.core.vmcraft.systemd_units import SystemdUnitsManager


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    return logging.getLogger("test")


@pytest.fixture
def temp_guest_root(tmp_path):
    """Create a temporary guest root directory."""
    guest_root = tmp_path / "guest_root"
    guest_root.mkdir()
    return guest_root


@pytest.fixture
def units_mgr(mock_logger, temp_guest_root):
    """Create SystemdUnitsManager instance."""
    return SystemdUnitsManager(mock_logger, str(temp_guest_root))


# ==================================================================================
# Service Unit Creation Tests
# ==================================================================================

class TestServiceUnitCreation:
    """Test service unit file creation."""

    def test_create_service_unit_basic(self, units_mgr):
        """Test creating basic service unit."""
        result = units_mgr.create_service_unit(
            name="myapp",
            description="My Application",
            exec_start="/usr/bin/myapp"
        )

        assert result["ok"] is True
        assert result["unit"] == "myapp.service"
        assert "path" in result

        # Verify file was created
        unit_file = Path(result["path"])
        assert unit_file.exists()

        # Verify content
        content = unit_file.read_text()
        assert "[Unit]" in content
        assert "Description=My Application" in content
        assert "[Service]" in content
        assert "ExecStart=/usr/bin/myapp" in content
        assert "Type=simple" in content
        assert "Restart=on-failure" in content
        assert "[Install]" in content
        assert "WantedBy=multi-user.target" in content

    def test_create_service_unit_with_dependencies(self, units_mgr):
        """Test creating service with dependencies."""
        result = units_mgr.create_service_unit(
            name="myapp",
            description="My App",
            exec_start="/usr/bin/myapp",
            after=["network.target", "sshd.service"],
            requires=["postgresql.service"],
            wants=["redis.service"]
        )

        assert result["ok"] is True

        content = Path(result["path"]).read_text()
        assert "After=network.target sshd.service" in content
        assert "Requires=postgresql.service" in content
        assert "Wants=redis.service" in content

    def test_create_service_unit_with_user(self, units_mgr):
        """Test creating service that runs as specific user."""
        result = units_mgr.create_service_unit(
            name="myapp",
            description="My App",
            exec_start="/usr/bin/myapp",
            user="myuser"
        )

        assert result["ok"] is True

        content = Path(result["path"]).read_text()
        assert "User=myuser" in content

    def test_create_service_unit_auto_extension(self, units_mgr):
        """Test automatic .service extension."""
        result = units_mgr.create_service_unit(
            name="myapp",
            description="My App",
            exec_start="/usr/bin/myapp"
        )

        assert result["ok"] is True
        assert result["unit"] == "myapp.service"


# ==================================================================================
# Timer Unit Creation Tests
# ==================================================================================

class TestTimerUnitCreation:
    """Test timer unit file creation."""

    def test_create_timer_unit_calendar(self, units_mgr):
        """Test creating timer with calendar specification."""
        result = units_mgr.create_timer_unit(
            name="backup",
            description="Daily Backup",
            on_calendar="daily"
        )

        assert result["ok"] is True
        assert result["unit"] == "backup.timer"

        content = Path(result["path"]).read_text()
        assert "[Timer]" in content
        assert "OnCalendar=daily" in content
        assert "WantedBy=timers.target" in content

    def test_create_timer_unit_boot(self, units_mgr):
        """Test creating timer triggered after boot."""
        result = units_mgr.create_timer_unit(
            name="startup",
            description="Startup Task",
            on_boot_sec="5min"
        )

        assert result["ok"] is True

        content = Path(result["path"]).read_text()
        assert "OnBootSec=5min" in content

    def test_create_timer_unit_no_trigger(self, units_mgr):
        """Test creating timer without trigger fails."""
        result = units_mgr.create_timer_unit(
            name="invalid",
            description="Invalid Timer"
        )

        assert result["ok"] is False
        assert result["error"] == "at least one timer trigger required"


# ==================================================================================
# Mount Unit Creation Tests
# ==================================================================================

class TestMountUnitCreation:
    """Test mount unit file creation."""

    def test_create_mount_unit(self, units_mgr):
        """Test creating mount unit."""
        result = units_mgr.create_mount_unit(
            name="data",
            what="/dev/sdb1",
            where="/mnt/data",
            type="ext4",
            options="defaults"
        )

        assert result["ok"] is True
        assert result["unit"] == "data.mount"

        content = Path(result["path"]).read_text()
        assert "[Mount]" in content
        assert "What=/dev/sdb1" in content
        assert "Where=/mnt/data" in content
        assert "Type=ext4" in content
        assert "Options=defaults" in content


# ==================================================================================
# Target Unit Creation Tests
# ==================================================================================

class TestTargetUnitCreation:
    """Test target unit file creation."""

    def test_create_target_unit(self, units_mgr):
        """Test creating target unit."""
        result = units_mgr.create_target_unit(
            name="myapp",
            description="My Application Target",
            wants=["myapp-web.service", "myapp-db.service"]
        )

        assert result["ok"] is True
        assert result["unit"] == "myapp.target"

        content = Path(result["path"]).read_text()
        assert "Description=My Application Target" in content
        assert "Wants=myapp-web.service myapp-db.service" in content


# ==================================================================================
# Path Unit Creation Tests
# ==================================================================================

class TestPathUnitCreation:
    """Test path unit file creation."""

    def test_create_path_unit_exists(self, units_mgr):
        """Test creating path unit watching for existence."""
        result = units_mgr.create_path_unit(
            name="watch-config",
            description="Watch Config",
            path_exists="/etc/myapp/config.yml",
            unit="myapp-reload.service"
        )

        assert result["ok"] is True
        assert result["unit"] == "watch-config.path"

        content = Path(result["path"]).read_text()
        assert "[Path]" in content
        assert "PathExists=/etc/myapp/config.yml" in content
        assert "Unit=myapp-reload.service" in content

    def test_create_path_unit_no_trigger(self, units_mgr):
        """Test creating path unit without trigger fails."""
        result = units_mgr.create_path_unit(
            name="invalid",
            description="Invalid Path"
        )

        assert result["ok"] is False
        assert result["error"] == "at least one path trigger required"


# ==================================================================================
# Unit File Reading Tests
# ==================================================================================

class TestUnitFileReading:
    """Test parsing unit files."""

    def test_read_unit_file(self, units_mgr):
        """Test reading and parsing unit file."""
        # Create a unit first
        units_mgr.create_service_unit(
            name="myapp",
            description="My App",
            exec_start="/usr/bin/myapp",
            user="myuser"
        )

        # Read it back
        result = units_mgr.read_unit_file("myapp.service")

        assert result["ok"] is True
        assert "sections" in result
        assert "Unit" in result["sections"]
        assert "Service" in result["sections"]
        assert result["sections"]["Unit"]["Description"] == "My App"
        assert result["sections"]["Service"]["ExecStart"] == "/usr/bin/myapp"
        assert result["sections"]["Service"]["User"] == "myuser"

    def test_read_nonexistent_unit(self, units_mgr):
        """Test reading non-existent unit file."""
        result = units_mgr.read_unit_file("nonexistent.service")

        assert result["ok"] is False
        assert result["error"] == "unit_file_not_found"


# ==================================================================================
# Unit File Modification Tests
# ==================================================================================

class TestUnitFileModification:
    """Test modifying unit files."""

    def test_modify_unit_file(self, units_mgr):
        """Test modifying unit file key."""
        # Create unit
        units_mgr.create_service_unit(
            name="myapp",
            description="My App",
            exec_start="/usr/bin/myapp"
        )

        # Modify Restart policy
        result = units_mgr.modify_unit_file(
            unit="myapp.service",
            section="Service",
            key="Restart",
            value="always"
        )

        assert result["ok"] is True

        # Verify modification
        read_result = units_mgr.read_unit_file("myapp.service")
        assert read_result["sections"]["Service"]["Restart"] == "always"

    def test_modify_nonexistent_unit(self, units_mgr):
        """Test modifying non-existent unit fails."""
        result = units_mgr.modify_unit_file(
            unit="nonexistent.service",
            section="Service",
            key="Restart",
            value="always"
        )

        assert result["ok"] is False
        assert result["error"] == "unit_file_not_found"


# ==================================================================================
# Unit File Deletion Tests
# ==================================================================================

class TestUnitFileDeletion:
    """Test deleting unit files."""

    def test_delete_unit_file(self, units_mgr):
        """Test deleting unit file."""
        # Create unit
        create_result = units_mgr.create_service_unit(
            name="myapp",
            description="My App",
            exec_start="/usr/bin/myapp"
        )
        assert create_result["ok"] is True

        # Delete it
        delete_result = units_mgr.delete_unit_file("myapp.service")
        assert delete_result["ok"] is True

        # Verify it's gone
        assert not Path(create_result["path"]).exists()

    def test_delete_nonexistent_unit(self, units_mgr):
        """Test deleting non-existent unit fails."""
        result = units_mgr.delete_unit_file("nonexistent.service")

        assert result["ok"] is False
        assert result["error"] == "unit_file_not_found"


# ==================================================================================
# Unit File Validation Tests
# ==================================================================================

class TestUnitFileValidation:
    """Test validating unit files."""

    def test_validate_valid_unit(self, units_mgr):
        """Test validating valid unit file."""
        # Create unit
        units_mgr.create_service_unit(
            name="myapp",
            description="My App",
            exec_start="/usr/bin/myapp"
        )

        # Validate it
        result = units_mgr.validate_unit_file("myapp.service")

        assert result["ok"] is True
        assert result["valid"] is True

    def test_validate_nonexistent_unit(self, units_mgr):
        """Test validating non-existent unit fails."""
        result = units_mgr.validate_unit_file("nonexistent.service")

        assert result["ok"] is False


# ==================================================================================
# Boot Performance Analysis Tests
# ==================================================================================

class TestBootPerformanceAnalysis:
    """Test boot performance analysis."""

    @patch('hyper2kvm.core.vmcraft.systemd_units.run_sudo')
    def test_analyze_boot_performance(self, mock_run_sudo, units_mgr):
        """Test boot performance analysis."""
        mock_result = Mock()
        mock_result.stdout = "Startup finished in 1.234s (kernel) + 5.678s (userspace) = 6.912s"
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = units_mgr.analyze_boot_performance()

        assert result["ok"] is True
        assert result["boot_time"] == "6.912s"
        assert result["kernel_time"] == "1.234s"
        assert result["userspace_time"] == "5.678s"

    @patch('hyper2kvm.core.vmcraft.systemd_units.run_sudo')
    def test_analyze_critical_chain(self, mock_run_sudo, units_mgr):
        """Test critical chain analysis."""
        mock_result = Mock()
        mock_result.stdout = "multi-user.target @5.678s\n  network.target @3.456s"
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = units_mgr.analyze_critical_chain()

        assert result["ok"] is True
        assert "multi-user.target" in result["output"]

    @patch('hyper2kvm.core.vmcraft.systemd_units.run_sudo')
    def test_analyze_blame(self, mock_run_sudo, units_mgr):
        """Test blame analysis."""
        mock_result = Mock()
        mock_result.stdout = """2.345s NetworkManager.service
1.234s sshd.service
0.567s systemd-logind.service"""
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = units_mgr.analyze_blame()

        assert result["ok"] is True
        assert len(result["services"]) == 3
        assert result["services"][0]["time"] == "2.345s"
        assert result["services"][0]["name"] == "NetworkManager.service"


# ==================================================================================
# Timer Listing Tests
# ==================================================================================

class TestTimerListing:
    """Test listing systemd timers."""

    @patch('hyper2kvm.core.vmcraft.systemd_units.run_sudo')
    def test_list_timers(self, mock_run_sudo, units_mgr):
        """Test listing active timers."""
        mock_result = Mock()
        # Simplified format that's easier to parse
        mock_result.stdout = """Sun n/a n/a n/a backup.timer backup.service
Mon n/a n/a n/a update.timer update.service"""
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = units_mgr.list_timers()

        assert result["ok"] is True
        assert len(result["timers"]) == 2
        assert result["timers"][0]["timer"] == "backup.timer"
        assert result["timers"][0]["activates"] == "backup.service"


# ==================================================================================
# Integration Tests
# ==================================================================================

class TestIntegrationWorkflows:
    """Test complete unit file management workflows."""

    def test_create_modify_validate_workflow(self, units_mgr):
        """Test create, modify, validate workflow."""
        # Create service
        create_result = units_mgr.create_service_unit(
            name="myapp",
            description="My App",
            exec_start="/usr/bin/myapp"
        )
        assert create_result["ok"] is True

        # Modify it
        modify_result = units_mgr.modify_unit_file(
            unit="myapp.service",
            section="Service",
            key="Restart",
            value="always"
        )
        assert modify_result["ok"] is True

        # Validate it
        validate_result = units_mgr.validate_unit_file("myapp.service")
        assert validate_result["ok"] is True
        assert validate_result["valid"] is True

        # Read and verify
        read_result = units_mgr.read_unit_file("myapp.service")
        assert read_result["sections"]["Service"]["Restart"] == "always"

    def test_timer_service_creation_workflow(self, units_mgr):
        """Test creating timer and associated service."""
        # Create service
        service_result = units_mgr.create_service_unit(
            name="backup",
            description="Backup Service",
            exec_start="/usr/bin/backup.sh",
            type="oneshot"
        )
        assert service_result["ok"] is True

        # Create timer for service
        timer_result = units_mgr.create_timer_unit(
            name="backup",
            description="Daily Backup Timer",
            on_calendar="daily",
            service="backup.service"
        )
        assert timer_result["ok"] is True

        # Verify both exist
        assert Path(service_result["path"]).exists()
        assert Path(timer_result["path"]).exists()
