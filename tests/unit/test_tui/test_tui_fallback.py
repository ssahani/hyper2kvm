# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Unit tests for TUI fallback system.
"""

import pytest
from unittest.mock import Mock, patch
from hyper2kvm.tui import get_dashboard_type, TEXTUAL_AVAILABLE


class TestTUIFallback:
    """Test the TUI fallback system."""

    def test_get_dashboard_type_with_textual(self):
        """Test dashboard type detection when Textual is available."""
        if TEXTUAL_AVAILABLE:
            dashboard_type = get_dashboard_type()
            assert dashboard_type == 'textual'

    @patch('hyper2kvm.tui.TEXTUAL_AVAILABLE', False)
    @patch('hyper2kvm.tui.CURSES_AVAILABLE', True)
    def test_get_dashboard_type_with_curses(self):
        """Test dashboard type detection when only curses is available."""
        # Import after patching
        from hyper2kvm import tui
        dashboard_type = tui.get_dashboard_type()
        assert dashboard_type == 'curses'

    @patch('hyper2kvm.tui.TEXTUAL_AVAILABLE', False)
    @patch('hyper2kvm.tui.CURSES_AVAILABLE', False)
    def test_get_dashboard_type_cli_fallback(self):
        """Test dashboard type detection when neither Textual nor curses is available."""
        from hyper2kvm import tui
        dashboard_type = tui.get_dashboard_type()
        assert dashboard_type == 'cli'

    def test_migration_status_dataclass(self):
        """Test MigrationStatus dataclass."""
        from hyper2kvm.tui.widgets import MigrationStatus

        migration = MigrationStatus(
            vm_name="test-vm",
            hypervisor="vmware",
            status="in_progress",
            progress=0.5,
            current_stage="export",
            throughput_mbps=100.0,
            elapsed_seconds=60.0,
        )

        assert migration.vm_name == "test-vm"
        assert migration.hypervisor == "vmware"
        assert migration.status == "in_progress"
        assert migration.progress == 0.5
        assert migration.current_stage == "export"
        assert migration.throughput_mbps == 100.0
        assert migration.elapsed_seconds == 60.0
        assert migration.eta_seconds is None
        assert migration.error is None

    def test_migration_status_with_error(self):
        """Test MigrationStatus with error."""
        from hyper2kvm.tui.widgets import MigrationStatus

        migration = MigrationStatus(
            vm_name="failed-vm",
            hypervisor="azure",
            status="failed",
            progress=0.3,
            current_stage="convert",
            error="Disk conversion failed",
        )

        assert migration.status == "failed"
        assert migration.error == "Disk conversion failed"

    def test_cli_dashboard_creation(self):
        """Test CLI dashboard can be created."""
        from hyper2kvm.tui.cli_dashboard import CLIDashboard

        dashboard = CLIDashboard(refresh_interval=2.0)
        assert dashboard.refresh_interval == 2.0
        assert dashboard._running is False
        assert len(dashboard._migrations) == 0
        assert len(dashboard._logs) == 0

    def test_cli_dashboard_add_migration(self):
        """Test adding migration to CLI dashboard."""
        from hyper2kvm.tui.cli_dashboard import CLIDashboard, MigrationStatus

        dashboard = CLIDashboard()
        migration = MigrationStatus(
            vm_name="test-vm",
            hypervisor="vmware",
            status="in_progress",
            progress=0.5,
            current_stage="export",
        )

        dashboard.add_migration(migration)
        assert "test-vm" in dashboard._migrations
        assert len(dashboard._logs) > 0

    def test_cli_dashboard_update_progress(self):
        """Test updating migration progress in CLI dashboard."""
        from hyper2kvm.tui.cli_dashboard import CLIDashboard, MigrationStatus

        dashboard = CLIDashboard()
        migration = MigrationStatus(
            vm_name="test-vm",
            hypervisor="vmware",
            status="in_progress",
            progress=0.5,
            current_stage="export",
        )
        dashboard.add_migration(migration)

        dashboard.update_migration_progress(
            vm_name="test-vm",
            progress=0.75,
            stage="convert",
            throughput_mbps=150.0,
        )

        updated = dashboard._migrations["test-vm"]
        assert updated.progress == 0.75
        assert updated.current_stage == "convert"
        assert updated.throughput_mbps == 150.0

    def test_cli_dashboard_remove_migration(self):
        """Test removing migration from CLI dashboard."""
        from hyper2kvm.tui.cli_dashboard import CLIDashboard, MigrationStatus

        dashboard = CLIDashboard()
        migration = MigrationStatus(
            vm_name="test-vm",
            hypervisor="vmware",
            status="completed",
            progress=1.0,
            current_stage="complete",
        )
        dashboard.add_migration(migration)

        dashboard.remove_migration("test-vm")
        assert "test-vm" not in dashboard._migrations

    def test_cli_dashboard_log_message(self):
        """Test logging messages in CLI dashboard."""
        from hyper2kvm.tui.cli_dashboard import CLIDashboard

        dashboard = CLIDashboard()
        dashboard.log_message("Test message", "INFO")

        assert len(dashboard._logs) == 1
        assert "Test message" in dashboard._logs[0]
        assert "INFO" in dashboard._logs[0]

    def test_cli_dashboard_compute_metrics(self):
        """Test metrics computation in CLI dashboard."""
        from hyper2kvm.tui.cli_dashboard import CLIDashboard, MigrationStatus

        dashboard = CLIDashboard()

        # Add some migrations
        migrations = [
            MigrationStatus("vm1", "vmware", "completed", 1.0, "done", 100.0, 60.0),
            MigrationStatus("vm2", "azure", "in_progress", 0.5, "export", 150.0, 30.0),
            MigrationStatus("vm3", "vmware", "failed", 0.3, "convert", 0.0, 20.0),
        ]

        for m in migrations:
            dashboard.add_migration(m)

        metrics = dashboard._compute_metrics()

        assert metrics["total_migrations"] == 3
        assert metrics["active_migrations"] == 1
        assert metrics["successful_migrations"] == 1
        assert metrics["failed_migrations"] == 1

    def test_cli_dashboard_progress_bar(self):
        """Test progress bar rendering in CLI dashboard."""
        from hyper2kvm.tui.cli_dashboard import CLIDashboard

        dashboard = CLIDashboard()

        # Test different progress values
        bar_0 = dashboard._render_progress_bar(0.0, 10)
        assert bar_0 == "[          ]"

        bar_50 = dashboard._render_progress_bar(0.5, 10)
        assert bar_50 == "[=====     ]"

        bar_100 = dashboard._render_progress_bar(1.0, 10)
        assert bar_100 == "[==========]"

    def test_cli_dashboard_format_duration(self):
        """Test duration formatting in CLI dashboard."""
        from hyper2kvm.tui.cli_dashboard import CLIDashboard

        dashboard = CLIDashboard()

        assert dashboard._format_duration(30) == "30s"
        assert dashboard._format_duration(90) == "1m 30s"
        assert dashboard._format_duration(3661) == "1h 1m"

    @pytest.mark.skipif(not TEXTUAL_AVAILABLE, reason="Textual not installed")
    def test_textual_widgets_import(self):
        """Test that Textual widgets can be imported when available."""
        from hyper2kvm.tui.widgets import MigrationStatusWidget, MetricsWidget

        assert MigrationStatusWidget is not None
        assert MetricsWidget is not None

    @pytest.mark.skipif(not TEXTUAL_AVAILABLE, reason="Textual not installed")
    def test_textual_dashboard_import(self):
        """Test that Textual dashboard can be imported when available."""
        from hyper2kvm.tui.dashboard import MigrationDashboard

        assert MigrationDashboard is not None

    def test_curses_dashboard_creation(self):
        """Test curses dashboard can be created."""
        from hyper2kvm.tui.fallback_dashboard import CursesDashboard

        dashboard = CursesDashboard(refresh_interval=1.5)
        assert dashboard.refresh_interval == 1.5
        assert dashboard._running is False
        assert len(dashboard._migrations) == 0
        assert len(dashboard._logs) == 0

    def test_curses_dashboard_add_migration(self):
        """Test adding migration to curses dashboard."""
        from hyper2kvm.tui.fallback_dashboard import CursesDashboard, MigrationStatus

        dashboard = CursesDashboard()
        migration = MigrationStatus(
            vm_name="test-vm",
            hypervisor="vmware",
            status="in_progress",
            progress=0.5,
            current_stage="export",
        )

        dashboard.add_migration(migration)
        assert "test-vm" in dashboard._migrations
        assert len(dashboard._logs) > 0

    def test_curses_dashboard_progress_bar(self):
        """Test progress bar rendering in curses dashboard."""
        from hyper2kvm.tui.fallback_dashboard import CursesDashboard

        dashboard = CursesDashboard()

        bar_0 = dashboard._render_progress_bar(0.0, 15)
        assert bar_0 == "[               ]"

        bar_50 = dashboard._render_progress_bar(0.5, 15)
        assert "=" in bar_50
        assert " " in bar_50

        bar_100 = dashboard._render_progress_bar(1.0, 15)
        assert bar_100 == "[===============]"
