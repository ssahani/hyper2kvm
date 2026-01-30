# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Tests for TUI widgets.
"""

import pytest
from hyper2kvm.core.optional_imports import TEXTUAL_AVAILABLE

if not TEXTUAL_AVAILABLE:
    pytest.skip("Textual not available", allow_module_level=True)

from hyper2kvm.tui.widgets import (
    MigrationStatus,
    MigrationStatusWidget,
    MetricsWidget,
)


class TestMigrationStatus:
    """Test MigrationStatus dataclass."""

    def test_create_migration_status(self):
        """Test creating a migration status."""
        status = MigrationStatus(
            vm_name="test-vm",
            hypervisor="vmware",
            status="in_progress",
            progress=0.5,
            current_stage="Exporting disk",
        )

        assert status.vm_name == "test-vm"
        assert status.hypervisor == "vmware"
        assert status.status == "in_progress"
        assert status.progress == 0.5
        assert status.current_stage == "Exporting disk"

    def test_migration_status_with_optional_fields(self):
        """Test migration status with all optional fields."""
        status = MigrationStatus(
            vm_name="test-vm",
            hypervisor="vmware",
            status="in_progress",
            progress=0.75,
            current_stage="Converting",
            throughput_mbps=125.5,
            elapsed_seconds=300.0,
            eta_seconds=100.0,
        )

        assert status.throughput_mbps == 125.5
        assert status.elapsed_seconds == 300.0
        assert status.eta_seconds == 100.0

    def test_migration_status_with_error(self):
        """Test migration status with error."""
        status = MigrationStatus(
            vm_name="failed-vm",
            hypervisor="vmware",
            status="failed",
            progress=0.3,
            current_stage="Export",
            error="Network connection lost",
        )

        assert status.status == "failed"
        assert status.error == "Network connection lost"


class TestMigrationStatusWidget:
    """Test MigrationStatusWidget."""

    def test_widget_creation(self):
        """Test creating widget."""
        migration = MigrationStatus(
            vm_name="test-vm",
            hypervisor="vmware",
            status="pending",
            progress=0.0,
            current_stage="Initializing",
        )

        widget = MigrationStatusWidget(migration)

        assert widget.migration == migration

    def test_widget_without_migration(self):
        """Test widget without initial migration."""
        widget = MigrationStatusWidget()

        assert widget.migration is None

    def test_render_migration_pending(self):
        """Test rendering pending migration."""
        migration = MigrationStatus(
            vm_name="test-vm",
            hypervisor="vmware",
            status="pending",
            progress=0.0,
            current_stage="Initializing",
        )

        widget = MigrationStatusWidget(migration)
        output = widget._render_migration()

        assert "test-vm" in output
        assert "PENDING" in output
        assert "Initializing" in output
        assert "⏳" in output  # Pending emoji

    def test_render_migration_in_progress(self):
        """Test rendering in-progress migration."""
        migration = MigrationStatus(
            vm_name="web-server",
            hypervisor="vmware",
            status="in_progress",
            progress=0.65,
            current_stage="Exporting disk",
            throughput_mbps=120.5,
            elapsed_seconds=180.0,
            eta_seconds=95.0,
        )

        widget = MigrationStatusWidget(migration)
        output = widget._render_migration()

        assert "web-server" in output
        assert "IN_PROGRESS" in output
        assert "Exporting disk" in output
        assert "65%" in output
        assert "120.5 MB/s" in output
        assert "🔄" in output  # In progress emoji

    def test_render_migration_completed(self):
        """Test rendering completed migration."""
        migration = MigrationStatus(
            vm_name="completed-vm",
            hypervisor="vmware",
            status="completed",
            progress=1.0,
            current_stage="Finalized",
            throughput_mbps=100.0,
            elapsed_seconds=600.0,
        )

        widget = MigrationStatusWidget(migration)
        output = widget._render_migration()

        assert "completed-vm" in output
        assert "COMPLETED" in output
        assert "100%" in output
        assert "✅" in output  # Success emoji

    def test_render_migration_failed(self):
        """Test rendering failed migration."""
        migration = MigrationStatus(
            vm_name="failed-vm",
            hypervisor="vmware",
            status="failed",
            progress=0.4,
            current_stage="Export",
            error="Connection timeout",
        )

        widget = MigrationStatusWidget(migration)
        output = widget._render_migration()

        assert "failed-vm" in output
        assert "FAILED" in output
        assert "Connection timeout" in output
        assert "❌" in output  # Failed emoji

    def test_format_duration_seconds(self):
        """Test duration formatting for seconds."""
        widget = MigrationStatusWidget()

        assert widget._format_duration(45.0) == "45s"
        assert widget._format_duration(0.0) == "0s"

    def test_format_duration_minutes(self):
        """Test duration formatting for minutes."""
        widget = MigrationStatusWidget()

        assert widget._format_duration(125.0) == "2m 5s"
        assert widget._format_duration(300.0) == "5m 0s"

    def test_format_duration_hours(self):
        """Test duration formatting for hours."""
        widget = MigrationStatusWidget()

        assert widget._format_duration(3665.0) == "1h 1m"
        assert widget._format_duration(7200.0) == "2h 0m"

    def test_format_duration_none(self):
        """Test duration formatting for None."""
        widget = MigrationStatusWidget()

        assert widget._format_duration(None) == "N/A"

    def test_progress_bar_rendering(self):
        """Test progress bar rendering."""
        widget = MigrationStatusWidget()

        # Empty progress
        bar = widget._render_progress_bar(0.0, width=10)
        assert "░" * 10 in bar

        # Half progress
        bar = widget._render_progress_bar(0.5, width=10)
        assert "█" in bar
        assert "░" in bar

        # Full progress
        bar = widget._render_progress_bar(1.0, width=10)
        assert "█" * 10 in bar


class TestMetricsWidget:
    """Test MetricsWidget."""

    def test_widget_creation(self):
        """Test creating metrics widget."""
        metrics = {
            "active_migrations": 3,
            "total_migrations": 10,
        }

        widget = MetricsWidget(metrics)

        assert widget.metrics == metrics

    def test_widget_without_metrics(self):
        """Test widget without initial metrics."""
        widget = MetricsWidget()

        assert widget.metrics == {}

    def test_render_empty_metrics(self):
        """Test rendering with no metrics."""
        widget = MetricsWidget()
        output = widget._render_metrics()

        assert "No metrics available" in output

    def test_render_full_metrics(self):
        """Test rendering complete metrics."""
        metrics = {
            "active_migrations": 2,
            "total_migrations": 15,
            "successful_migrations": 12,
            "failed_migrations": 1,
            "avg_throughput_mbps": 105.5,
            "total_bytes_processed": 50 * 1024**3,  # 50 GB
            "avg_duration_seconds": 450.0,
            "error_rate_per_minute": 0.05,
        }

        widget = MetricsWidget(metrics)
        output = widget._render_metrics()

        assert "Active Migrations:     2" in output
        assert "Total Migrations:      15" in output
        assert "✅ 12" in output
        assert "❌ 1" in output
        assert "105.5 MB/s" in output
        assert "50.00 GB" in output
        assert "7m 30s" in output  # 450 seconds

    def test_render_metrics_success_rate(self):
        """Test success rate calculation."""
        metrics = {
            "total_migrations": 20,
            "successful_migrations": 18,
            "failed_migrations": 2,
            "active_migrations": 0,
        }

        widget = MetricsWidget(metrics)
        output = widget._render_metrics()

        assert "90.0%" in output  # 18/20 = 90%

    def test_render_metrics_no_total(self):
        """Test rendering when total is 0."""
        metrics = {
            "total_migrations": 0,
            "successful_migrations": 0,
            "failed_migrations": 0,
            "active_migrations": 0,
        }

        widget = MetricsWidget(metrics)
        output = widget._render_metrics()

        assert "N/A" in output  # Success rate should be N/A

    def test_metrics_format_duration(self):
        """Test duration formatting in metrics."""
        widget = MetricsWidget()

        assert widget._format_duration(30.0) == "30s"
        assert widget._format_duration(120.0) == "2m 0s"
        assert widget._format_duration(3665.0) == "1h 1m"
