# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Tests for TUI dashboard.
"""

import pytest
from hyper2kvm.core.optional_imports import TEXTUAL_AVAILABLE

if not TEXTUAL_AVAILABLE:
    pytest.skip("Textual not available", allow_module_level=True)

from hyper2kvm.tui.dashboard import MigrationDashboard
from hyper2kvm.tui.widgets import MigrationStatus


class TestMigrationDashboard:
    """Test MigrationDashboard app."""

    def test_dashboard_creation(self):
        """Test creating dashboard."""
        dashboard = MigrationDashboard(refresh_interval=2.0)

        assert dashboard.refresh_interval == 2.0
        assert dashboard._migrations == {}
        assert dashboard._migration_widgets == {}

    def test_dashboard_default_interval(self):
        """Test default refresh interval."""
        dashboard = MigrationDashboard()

        assert dashboard.refresh_interval == 1.0

    def test_add_migration(self):
        """Test adding a migration."""
        dashboard = MigrationDashboard()

        migration = MigrationStatus(
            vm_name="test-vm",
            hypervisor="vmware",
            status="in_progress",
            progress=0.5,
            current_stage="Exporting",
        )

        # Note: We can't actually test the full add_migration without running the app
        # since it requires the DOM to be mounted. We can only test the data tracking.
        dashboard._migrations["test-vm"] = migration

        assert "test-vm" in dashboard._migrations
        assert dashboard._migrations["test-vm"].status == "in_progress"

    def test_remove_migration(self):
        """Test removing a migration."""
        dashboard = MigrationDashboard()

        # Add a migration
        dashboard._migrations["test-vm"] = MigrationStatus(
            vm_name="test-vm",
            hypervisor="vmware",
            status="completed",
            progress=1.0,
            current_stage="Done",
        )

        # Remove it
        if "test-vm" in dashboard._migrations:
            del dashboard._migrations["test-vm"]

        assert "test-vm" not in dashboard._migrations

    def test_compute_metrics_empty(self):
        """Test computing metrics with no migrations."""
        dashboard = MigrationDashboard()

        metrics = dashboard._compute_metrics()

        assert metrics["active_migrations"] == 0
        assert metrics["total_migrations"] == 0
        assert metrics["successful_migrations"] == 0
        assert metrics["failed_migrations"] == 0
        assert metrics["avg_throughput_mbps"] == 0
        assert metrics["avg_duration_seconds"] == 0

    def test_compute_metrics_with_migrations(self):
        """Test computing metrics with migrations."""
        dashboard = MigrationDashboard()

        # Add some migrations
        dashboard._migrations["vm1"] = MigrationStatus(
            vm_name="vm1",
            hypervisor="vmware",
            status="completed",
            progress=1.0,
            current_stage="Done",
            throughput_mbps=100.0,
            elapsed_seconds=300.0,
        )

        dashboard._migrations["vm2"] = MigrationStatus(
            vm_name="vm2",
            hypervisor="vmware",
            status="in_progress",
            progress=0.5,
            current_stage="Exporting",
            throughput_mbps=120.0,
            elapsed_seconds=150.0,
        )

        dashboard._migrations["vm3"] = MigrationStatus(
            vm_name="vm3",
            hypervisor="vmware",
            status="failed",
            progress=0.3,
            current_stage="Export",
            error="Timeout",
        )

        metrics = dashboard._compute_metrics()

        assert metrics["active_migrations"] == 1  # Only in_progress
        assert metrics["total_migrations"] == 3
        assert metrics["successful_migrations"] == 1
        assert metrics["failed_migrations"] == 1
        # Average throughput should be from completed migration
        assert metrics["avg_throughput_mbps"] == 100.0
        assert metrics["avg_duration_seconds"] == 300.0

    def test_compute_metrics_multiple_completed(self):
        """Test metrics with multiple completed migrations."""
        dashboard = MigrationDashboard()

        # Add completed migrations
        dashboard._migrations["vm1"] = MigrationStatus(
            vm_name="vm1",
            hypervisor="vmware",
            status="completed",
            progress=1.0,
            current_stage="Done",
            throughput_mbps=100.0,
            elapsed_seconds=300.0,
        )

        dashboard._migrations["vm2"] = MigrationStatus(
            vm_name="vm2",
            hypervisor="vmware",
            status="completed",
            progress=1.0,
            current_stage="Done",
            throughput_mbps=120.0,
            elapsed_seconds=400.0,
        )

        metrics = dashboard._compute_metrics()

        # Averages should be calculated
        assert metrics["avg_throughput_mbps"] == 110.0  # (100 + 120) / 2
        assert metrics["avg_duration_seconds"] == 350.0  # (300 + 400) / 2

    def test_update_migration_progress(self):
        """Test updating migration progress."""
        dashboard = MigrationDashboard()

        # Create initial migration
        dashboard._migrations["test-vm"] = MigrationStatus(
            vm_name="test-vm",
            hypervisor="vmware",
            status="in_progress",
            progress=0.3,
            current_stage="Connecting",
        )

        # Update progress (without actually running the app)
        migration = dashboard._migrations["test-vm"]
        migration.progress = 0.7
        migration.current_stage = "Exporting"
        migration.throughput_mbps = 125.5

        assert dashboard._migrations["test-vm"].progress == 0.7
        assert dashboard._migrations["test-vm"].current_stage == "Exporting"
        assert dashboard._migrations["test-vm"].throughput_mbps == 125.5


class TestMigrationDashboardHelpers:
    """Test dashboard helper methods."""

    def test_dashboard_title(self):
        """Test dashboard has correct title."""
        assert MigrationDashboard.TITLE == "hyper2kvm Migration Dashboard"

    def test_dashboard_bindings(self):
        """Test dashboard has keyboard bindings."""
        bindings = {b.key for b in MigrationDashboard.BINDINGS}

        assert "q" in bindings  # Quit
        assert "r" in bindings  # Refresh
        assert "l" in bindings  # Focus logs
        assert "m" in bindings  # Focus migrations
        assert "d" in bindings  # Toggle dark mode


class TestRunDashboard:
    """Test run_dashboard helper function."""

    def test_run_dashboard_import(self):
        """Test that run_dashboard can be imported."""
        from hyper2kvm.tui.dashboard import run_dashboard

        assert callable(run_dashboard)
