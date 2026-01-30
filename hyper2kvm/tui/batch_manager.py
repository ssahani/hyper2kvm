# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/batch_manager.py
"""
Batch migration manager for handling multiple VM migrations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from ..core.optional_imports import (
    TEXTUAL_AVAILABLE,
    ComposeResult,
    Static,
    Container,
    Vertical,
    Horizontal,
    Button,
    DataTable,
    ProgressBar,
)

if not TEXTUAL_AVAILABLE:
    raise ImportError("Textual required")

from .migration_tracker import MigrationTracker
from .migration_controller import MigrationController

logger = logging.getLogger(__name__)


class BatchMigrationManager(Container):
    """
    Manage multiple VM migrations in batch mode.

    Features:
    - View all active/queued/completed migrations
    - Pause/resume/cancel migrations
    - View detailed progress for each migration
    - Export migration reports
    """

    DEFAULT_CSS = """
    BatchMigrationManager {
        height: 100%;
        border: heavy #DE7356;  /* Coral brand color */
        background: $surface;
    }

    .batch-header {
        height: 5;
        background: #DE7356;  /* Coral brand color */
        color: white;
        padding: 1 2;
        text-style: bold;
    }

    .batch-toolbar {
        height: 4;
        background: $surface-darken-1;
        padding: 0 2;
    }

    .batch-body {
        height: 1fr;
        padding: 1 2;
    }

    .batch-footer {
        height: 5;
        background: $surface-darken-1;
        padding: 1 2;
    }

    .toolbar-row {
        layout: horizontal;
        height: auto;
        align: left middle;
    }

    .toolbar-row Button {
        margin: 0 1;
    }

    .migrations-table {
        height: 1fr;
    }

    .status-active {
        color: #DE7356;  /* Coral brand color */
        text-style: bold;
    }

    .status-completed {
        color: $success;
    }

    .status-failed {
        color: $error;
    }

    .status-queued {
        color: $text-muted;
    }

    .stats-row {
        layout: horizontal;
        height: auto;
        align: left middle;
    }

    .stats-row Static {
        margin: 0 2;
    }
    """

    def __init__(self, tracker: Optional[MigrationTracker] = None, **kwargs):
        super().__init__(**kwargs)
        self.migrations: List[Dict[str, Any]] = []
        self.selected_migration: Optional[str] = None
        self.tracker = tracker or MigrationTracker(logger=logger)
        self.controller = MigrationController(self.tracker, logger=logger)

    def compose(self) -> ComposeResult:
        """Compose the batch manager UI."""
        # Header
        with Container(classes="batch-header"):
            yield Static("🗂️ Batch Migration Manager")

        # Toolbar
        with Container(classes="batch-toolbar"):
            with Horizontal(classes="toolbar-row"):
                yield Button("➕ New Batch", id="btn_new_batch", variant="primary")
                yield Button("⏸️ Pause", id="btn_pause", variant="default")
                yield Button("▶️ Resume", id="btn_resume", variant="default")
                yield Button("🗑️ Cancel", id="btn_cancel", variant="error")
                yield Button("📊 Export Report", id="btn_export", variant="default")
                yield Button("🔄 Refresh", id="btn_refresh", variant="default")

        # Body with migrations table
        with Container(classes="batch-body"):
            table = DataTable(classes="migrations-table", id="table_migrations")
            table.add_columns(
                "ID",
                "VM Name",
                "Status",
                "Progress",
                "Stage",
                "Throughput",
                "ETA",
                "Started"
            )
            table.cursor_type = "row"

            # Populate with sample data
            self.populate_sample_migrations(table)

            yield table

        # Footer with statistics
        with Container(classes="batch-footer"):
            with Horizontal(classes="stats-row"):
                yield Static("Active: 0", id="stat_active")
                yield Static("Queued: 0", id="stat_queued")
                yield Static("Completed: 0", id="stat_completed")
                yield Static("Failed: 0", id="stat_failed")
                yield Static("Total: 0", id="stat_total")

    def populate_sample_migrations(self, table: DataTable) -> None:
        """Populate table with sample migration data."""
        sample_migrations = [
            ("001", "web-server-01", "active", "45%", "convert", "120 MB/s", "5m 30s", "14:30:15"),
            ("002", "database-server", "active", "78%", "validate", "95 MB/s", "2m 15s", "14:25:00"),
            ("003", "app-server-03", "queued", "0%", "pending", "-", "-", "-"),
            ("004", "backup-server", "completed", "100%", "done", "-", "0s", "14:15:00"),
            ("005", "dev-machine", "failed", "23%", "transfer", "-", "-", "14:20:00"),
        ]

        for idx, (id, name, status, progress, stage, throughput, eta, started) in enumerate(sample_migrations):
            # Apply style based on status
            status_class = f"status-{status}"

            table.add_row(
                id,
                name,
                status,
                progress,
                stage,
                throughput,
                eta,
                started,
                key=f"mig_{idx}"
            )

        # Update stats
        self.update_stats(sample_migrations)

    def update_stats(self, migrations: List[tuple]) -> None:
        """Update statistics display."""
        stats = {
            "active": sum(1 for m in migrations if m[2] == "active"),
            "queued": sum(1 for m in migrations if m[2] == "queued"),
            "completed": sum(1 for m in migrations if m[2] == "completed"),
            "failed": sum(1 for m in migrations if m[2] == "failed"),
            "total": len(migrations),
        }

        # Update Static widgets with calculated stats
        stat_widgets = {
            "stat_active": f"Active: {stats['active']}",
            "stat_queued": f"Queued: {stats['queued']}",
            "stat_completed": f"Completed: {stats['completed']}",
            "stat_failed": f"Failed: {stats['failed']}",
            "stat_total": f"Total: {stats['total']}",
        }

        for widget_id, text in stat_widgets.items():
            try:
                widget = self.query_one(f"#{widget_id}", Static)
                widget.update(text)
            except Exception:
                # Widget might not exist yet during initialization
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn_new_batch":
            self.new_batch()
        elif button_id == "btn_pause":
            self.pause_migration()
        elif button_id == "btn_resume":
            self.resume_migration()
        elif button_id == "btn_cancel":
            self.cancel_migration()
        elif button_id == "btn_export":
            self.export_report()
        elif button_id == "btn_refresh":
            self.refresh_migrations()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        self.selected_migration = event.row_key
        self.notify(f"Selected migration: {self.selected_migration}")

    def new_batch(self) -> None:
        """Create a new batch migration."""
        self.notify("Opening batch migration wizard...")
        # Note: Batch creation requires file dialog or wizard:
        # Option 1: File dialog to select batch manifest (JSON/YAML)
        #   - Use Textual's DirectoryTree or custom file picker
        #   - Parse manifest with batch loader
        # Option 2: Multi-step wizard for batch creation
        #   - Collect VMs, settings, and migration order
        #   - Generate batch manifest programmatically
        # Current implementation shows notification only.

    def pause_migration(self) -> None:
        """Pause selected migration."""
        if not self.selected_migration:
            self.notify("No migration selected", severity="warning")
            return

        migration_id = self.selected_migration
        if self.controller.pause_migration(migration_id):
            self.notify(f"Migration paused: {migration_id}", severity="information")
            self.refresh_migrations()
        else:
            self.notify(f"Failed to pause migration: {migration_id}", severity="error")

    def resume_migration(self) -> None:
        """Resume selected migration."""
        if not self.selected_migration:
            self.notify("No migration selected", severity="warning")
            return

        migration_id = self.selected_migration
        if self.controller.resume_migration(migration_id):
            self.notify(f"Migration resumed: {migration_id}", severity="information")
            self.refresh_migrations()
        else:
            self.notify(f"Failed to resume migration: {migration_id}", severity="error")

    def cancel_migration(self) -> None:
        """Cancel selected migration."""
        if not self.selected_migration:
            self.notify("No migration selected", severity="warning")
            return

        migration_id = self.selected_migration
        if self.controller.cancel_migration(migration_id):
            self.notify(f"Migration cancelled: {migration_id}", severity="warning")
            self.refresh_migrations()
        else:
            self.notify(f"Failed to cancel migration: {migration_id}", severity="error")

    def export_report(self) -> None:
        """Export migration reports."""
        self.notify("Exporting reports...")
        # Note: Report export requires:
        # 1. Gather migration data from tracker:
        #    - Get all migrations or selected migrations
        #    - Compile statistics, durations, success/failure info
        # 2. Format report (multiple options):
        #    - JSON: Full machine-readable data
        #    - CSV: Spreadsheet-friendly tabular format
        #    - HTML: Rich formatted report with charts
        #    - Markdown: Human-readable text format
        # 3. Save to user-specified location:
        #    - Prompt for file path and format
        #    - Write formatted report to disk
        # Current implementation shows notification only.

    def refresh_migrations(self) -> None:
        """Refresh migration list from tracker."""
        try:
            # Reload from persistent storage
            self.tracker.load()

            # Cleanup finished processes
            self.controller.cleanup_finished_processes()

            # Get all migrations
            all_migrations = list(self.tracker.migrations.values())

            # Update statistics
            stats = self.tracker.get_statistics()
            self.update_stats_display(stats)

            self.notify(f"Refreshed: {len(all_migrations)} total migrations")

        except Exception as e:
            logger.exception("Failed to refresh migrations")
            self.notify(f"Refresh failed: {e}", severity="error")

    def update_stats_display(self, stats: Dict[str, Any]) -> None:
        """Update statistics widgets with new values."""
        try:
            # Update Static widgets if they exist
            stat_widgets = {
                "stat_active": f"Active: {stats.get('active_migrations', 0)}",
                "stat_queued": "Queued: 0",  # Would need separate queue tracking
                "stat_completed": f"Completed: {stats.get('total_completed', 0)}",
                "stat_failed": f"Failed: {stats.get('total_failed', 0)}",
                "stat_total": f"Total: {stats.get('total_migrations', 0)}",
            }

            for widget_id, text in stat_widgets.items():
                try:
                    widget = self.query_one(f"#{widget_id}", Static)
                    widget.update(text)
                except Exception:
                    # Widget might not exist yet
                    pass

        except Exception as e:
            logger.debug(f"Failed to update stats display: {e}")
