# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Unit tests for VMCraft systemd journal integration (Phase 3).

Tests the SystemdJournalManager class and journal access APIs.
"""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
import pytest

from hyper2kvm.core.vmcraft.systemd_journal import SystemdJournalManager


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    return logging.getLogger("test")


@pytest.fixture
def temp_guest_root(tmp_path):
    """Create a temporary guest root directory."""
    guest_root = tmp_path / "guest_root"
    guest_root.mkdir()

    # Create journalctl binary to simulate systemd journal presence
    journalctl_dir = guest_root / "usr/bin"
    journalctl_dir.mkdir(parents=True)
    (journalctl_dir / "journalctl").touch()

    return guest_root


@pytest.fixture
def journal_mgr(mock_logger, temp_guest_root):
    """Create SystemdJournalManager instance."""
    return SystemdJournalManager(mock_logger, str(temp_guest_root))


# ==================================================================================
# Journal Availability Tests
# ==================================================================================

class TestJournalAvailability:
    """Test journalctl detection and availability checking."""

    def test_is_journalctl_available_true(self, journal_mgr):
        """Test journalctl detection when binary exists."""
        assert journal_mgr.is_journalctl_available() is True

    def test_is_journalctl_available_false(self, mock_logger, tmp_path):
        """Test journalctl detection when binary doesn't exist."""
        empty_root = tmp_path / "empty_root"
        empty_root.mkdir()

        mgr = SystemdJournalManager(mock_logger, str(empty_root))
        assert mgr.is_journalctl_available() is False

    def test_is_journalctl_available_cached(self, journal_mgr):
        """Test that journalctl availability is cached."""
        # First call
        result1 = journal_mgr.is_journalctl_available()

        # Second call should use cached value
        result2 = journal_mgr.is_journalctl_available()

        assert result1 == result2 == True


# ==================================================================================
# Journal Query Tests
# ==================================================================================

class TestJournalQuery:
    """Test journal entry querying."""

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_get_all_entries(self, mock_run_sudo, journal_mgr):
        """Test getting all journal entries."""
        mock_result = Mock()
        mock_result.stdout = json.dumps({"MESSAGE": "Test log 1", "_PID": "123"}) + "\n" + \
                            json.dumps({"MESSAGE": "Test log 2", "_PID": "456"})
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = journal_mgr.get()

        assert result["ok"] is True
        assert result["count"] == 2
        assert len(result["entries"]) == 2
        assert result["entries"][0]["MESSAGE"] == "Test log 1"
        assert result["entries"][1]["MESSAGE"] == "Test log 2"

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_get_with_lines_limit(self, mock_run_sudo, journal_mgr):
        """Test getting limited number of entries."""
        mock_result = Mock()
        mock_result.stdout = json.dumps({"MESSAGE": "Test log"})
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = journal_mgr.get(lines=50)

        assert result["ok"] is True
        # Verify -n 50 was passed
        args = mock_run_sudo.call_args[0][1]
        assert "-n" in args
        assert "50" in args

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_get_with_unit_filter(self, mock_run_sudo, journal_mgr):
        """Test getting entries for specific unit."""
        mock_result = Mock()
        mock_result.stdout = json.dumps({"MESSAGE": "SSH log", "UNIT": "sshd.service"})
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = journal_mgr.get(unit="sshd.service")

        assert result["ok"] is True
        # Verify -u sshd.service was passed
        args = mock_run_sudo.call_args[0][1]
        assert "-u" in args
        assert "sshd.service" in args

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_get_with_priority_filter(self, mock_run_sudo, journal_mgr):
        """Test getting entries by priority."""
        mock_result = Mock()
        mock_result.stdout = json.dumps({"MESSAGE": "Error message", "PRIORITY": "3"})
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = journal_mgr.get(priority="err")

        assert result["ok"] is True
        # Verify -p err was passed
        args = mock_run_sudo.call_args[0][1]
        assert "-p" in args
        assert "err" in args

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_get_with_time_filter(self, mock_run_sudo, journal_mgr):
        """Test getting entries with time filtering."""
        mock_result = Mock()
        mock_result.stdout = json.dumps({"MESSAGE": "Recent log"})
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = journal_mgr.get(since="-1h", until="now")

        assert result["ok"] is True
        # Verify --since and --until were passed
        args = mock_run_sudo.call_args[0][1]
        assert "--since" in args
        assert "-1h" in args
        assert "--until" in args
        assert "now" in args

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_get_with_grep_filter(self, mock_run_sudo, journal_mgr):
        """Test getting entries with grep pattern."""
        mock_result = Mock()
        mock_result.stdout = json.dumps({"MESSAGE": "Failed to start service"})
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = journal_mgr.get(grep="Failed")

        assert result["ok"] is True
        # Verify -g Failed was passed
        args = mock_run_sudo.call_args[0][1]
        assert "-g" in args
        assert "Failed" in args

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_get_no_journalctl(self, mock_run_sudo, mock_logger, tmp_path):
        """Test getting entries when journalctl is not available."""
        empty_root = tmp_path / "no_journal"
        empty_root.mkdir()

        mgr = SystemdJournalManager(mock_logger, str(empty_root))
        result = mgr.get()

        assert result["ok"] is False
        assert result["error"] == "journalctl_not_available"
        mock_run_sudo.assert_not_called()


# ==================================================================================
# Service-Specific Query Tests
# ==================================================================================

class TestServiceQuery:
    """Test service-specific journal queries."""

    @patch('hyper2kvm.core.vmcraft.systemd_journal.SystemdJournalManager.get')
    def test_get_service_with_suffix(self, mock_get, journal_mgr):
        """Test getting service logs (service already has .service suffix)."""
        mock_get.return_value = {"ok": True, "entries": [], "count": 0}

        result = journal_mgr.get_service("sshd.service", lines=50)

        assert result["ok"] is True
        mock_get.assert_called_once_with(unit="sshd.service", lines=50)

    @patch('hyper2kvm.core.vmcraft.systemd_journal.SystemdJournalManager.get')
    def test_get_service_without_suffix(self, mock_get, journal_mgr):
        """Test getting service logs (auto-add .service suffix)."""
        mock_get.return_value = {"ok": True, "entries": [], "count": 0}

        result = journal_mgr.get_service("sshd", lines=50)

        assert result["ok"] is True
        # Should auto-add .service suffix
        mock_get.assert_called_once_with(unit="sshd.service", lines=50)


# ==================================================================================
# Boot Log Tests
# ==================================================================================

class TestBootLogs:
    """Test boot-specific log queries."""

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_get_since_boot_current(self, mock_run_sudo, journal_mgr):
        """Test getting logs from current boot."""
        mock_result = Mock()
        mock_result.stdout = json.dumps({"MESSAGE": "Boot log", "_BOOT_ID": "abc123"})
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = journal_mgr.get_since_boot(boot_offset=0)

        assert result["ok"] is True
        assert result["count"] == 1
        # Verify -b 0 was passed
        args = mock_run_sudo.call_args[0][1]
        assert "-b" in args
        assert "0" in args

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_get_since_boot_previous(self, mock_run_sudo, journal_mgr):
        """Test getting logs from previous boot."""
        mock_result = Mock()
        mock_result.stdout = json.dumps({"MESSAGE": "Previous boot log"})
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = journal_mgr.get_since_boot(boot_offset=-1)

        assert result["ok"] is True
        # Verify -b -1 was passed
        args = mock_run_sudo.call_args[0][1]
        assert "-b" in args
        assert "-1" in args

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_list_boots(self, mock_run_sudo, journal_mgr):
        """Test listing available boots."""
        mock_result = Mock()
        mock_result.stdout = """0 abc123def456... Mon 2024-01-01 10:00:00 UTC—Mon 2024-01-01 18:00:00 UTC
-1 def456ghi789... Sun 2024-01-01 09:00:00 UTC—Sun 2024-01-01 17:00:00 UTC"""
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = journal_mgr.list_boots()

        assert result["ok"] is True
        assert result["count"] == 2
        assert len(result["boots"]) == 2
        assert result["boots"][0]["offset"] == "0"
        assert result["boots"][0]["boot_id"] == "abc123def456..."
        assert result["boots"][1]["offset"] == "-1"

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_get_boot_id(self, mock_run_sudo, journal_mgr):
        """Test getting current boot ID."""
        mock_result = Mock()
        mock_result.stdout = json.dumps({"_BOOT_ID": "abc123def456"})
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        boot_id = journal_mgr.get_boot_id()

        assert boot_id == "abc123def456"

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_get_boot_id_failure(self, mock_run_sudo, journal_mgr):
        """Test getting boot ID when it fails."""
        mock_run_sudo.side_effect = Exception("journalctl failed")

        boot_id = journal_mgr.get_boot_id()

        assert boot_id is None


# ==================================================================================
# Priority Query Tests
# ==================================================================================

class TestPriorityQuery:
    """Test priority-based filtering."""

    @patch('hyper2kvm.core.vmcraft.systemd_journal.SystemdJournalManager.get')
    def test_get_priority(self, mock_get, journal_mgr):
        """Test getting entries by priority."""
        mock_get.return_value = {"ok": True, "entries": [], "count": 0}

        result = journal_mgr.get_priority("crit", lines=50)

        assert result["ok"] is True
        mock_get.assert_called_once_with(priority="crit", lines=50)


# ==================================================================================
# Tail Query Tests
# ==================================================================================

class TestTailQuery:
    """Test getting recent entries."""

    @patch('hyper2kvm.core.vmcraft.systemd_journal.SystemdJournalManager.get')
    def test_get_tail(self, mock_get, journal_mgr):
        """Test getting last N entries."""
        mock_get.return_value = {"ok": True, "entries": [], "count": 0}

        result = journal_mgr.get_tail(lines=100)

        assert result["ok"] is True
        mock_get.assert_called_once_with(lines=100)


# ==================================================================================
# Journal Management Tests
# ==================================================================================

class TestJournalManagement:
    """Test journal management operations."""

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_get_disk_usage(self, mock_run_sudo, journal_mgr):
        """Test getting journal disk usage."""
        mock_result = Mock()
        mock_result.stdout = "Archived and active journals take up 1.2G in the file system."
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = journal_mgr.get_disk_usage()

        assert result["ok"] is True
        assert result["size"] == "1.2G"
        assert "1.2G" in result["usage"]

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_vacuum_by_size(self, mock_run_sudo, journal_mgr):
        """Test vacuuming journal by size."""
        mock_result = Mock()
        mock_result.stdout = "Deleted archived journal files"
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = journal_mgr.vacuum(size="100M")

        assert result["ok"] is True
        # Verify --vacuum-size was passed
        args = mock_run_sudo.call_args[0][1]
        assert "--vacuum-size=100M" in args

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_vacuum_by_time(self, mock_run_sudo, journal_mgr):
        """Test vacuuming journal by time."""
        mock_result = Mock()
        mock_result.stdout = "Deleted archived journal files"
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = journal_mgr.vacuum(time="1week")

        assert result["ok"] is True
        # Verify --vacuum-time was passed
        args = mock_run_sudo.call_args[0][1]
        assert "--vacuum-time=1week" in args

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_vacuum_by_files(self, mock_run_sudo, journal_mgr):
        """Test vacuuming journal by file count."""
        mock_result = Mock()
        mock_result.stdout = "Deleted archived journal files"
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = journal_mgr.vacuum(files=10)

        assert result["ok"] is True
        # Verify --vacuum-files was passed
        args = mock_run_sudo.call_args[0][1]
        assert "--vacuum-files=10" in args

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_vacuum_no_params(self, mock_run_sudo, journal_mgr):
        """Test vacuuming without parameters fails."""
        result = journal_mgr.vacuum()

        assert result["ok"] is False
        assert result["error"] == "size, time, or files parameter required"
        mock_run_sudo.assert_not_called()

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_verify_success(self, mock_run_sudo, journal_mgr):
        """Test journal verification success."""
        mock_result = Mock()
        mock_result.stdout = "PASS"
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        result = journal_mgr.verify()

        assert result["ok"] is True
        assert result["verified"] is True
        # Verify --verify was passed
        args = mock_run_sudo.call_args[0][1]
        assert "--verify" in args

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_verify_failure(self, mock_run_sudo, journal_mgr):
        """Test journal verification failure."""
        mock_run_sudo.side_effect = Exception("Verification failed")

        result = journal_mgr.verify()

        assert result["ok"] is False
        assert result["verified"] is False
        assert result["error"] == "journal_verification_failed"


# ==================================================================================
# Integration Tests
# ==================================================================================

class TestIntegrationWorkflows:
    """Test complete journal analysis workflows."""

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_debug_service_failure_workflow(self, mock_run_sudo, journal_mgr):
        """Test workflow for debugging service failures."""
        # Mock service logs with errors
        mock_result = Mock()
        mock_result.stdout = json.dumps({
            "MESSAGE": "Failed to start service",
            "PRIORITY": "3",
            "UNIT": "myservice.service"
        })
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        # Get service logs
        result = journal_mgr.get_service("myservice", lines=50)

        assert result["ok"] is True
        assert result["count"] == 1
        assert "Failed to start" in result["entries"][0]["MESSAGE"]

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_boot_analysis_workflow(self, mock_run_sudo, journal_mgr):
        """Test workflow for analyzing boot issues."""
        # Mock boot logs
        mock_result = Mock()
        mock_result.stdout = json.dumps({"MESSAGE": "Boot completed", "_BOOT_ID": "abc123"})
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        # Get current boot logs
        result = journal_mgr.get_since_boot(boot_offset=0)

        assert result["ok"] is True
        assert result["count"] == 1

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_error_analysis_workflow(self, mock_run_sudo, journal_mgr):
        """Test workflow for finding all errors."""
        # Mock error logs
        mock_result = Mock()
        mock_result.stdout = json.dumps({
            "MESSAGE": "Critical error occurred",
            "PRIORITY": "2"
        })
        mock_result.stderr = ""
        mock_run_sudo.return_value = mock_result

        # Get critical errors
        result = journal_mgr.get_priority("crit", lines=100)

        assert result["ok"] is True
        assert result["count"] == 1
