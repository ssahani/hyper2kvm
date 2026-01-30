# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/migrations_panel.py
"""
Migrations panel for displaying active migrations in the main app.
"""

from __future__ import annotations

import logging
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


class MigrationsPanel(Container):
    """
    Panel for displaying and monitoring active migrations.

    Features:
    - Real-time migration status table
    - Progress bars for each migration
    - Performance metrics (throughput, ETA)
    - Control actions (pause, cancel)
    """

    DEFAULT_CSS = """
    MigrationsPanel {
        height: 100%;
        background: $surface;
    }

    .migrations-header {
        height: 5;
        background: #DE7356;  /* Coral brand color */
        color: white;
        padding: 1 2;
        text-style: bold;
    }

    .migrations-toolbar {
        height: 4;
        background: $surface-darken-1;
        padding: 0 2;
    }

    .migrations-body {
        height: 1fr;
        padding: 1 2;
    }

    .migrations-footer {
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

    .status-running {
        color: #DE7356;  /* Coral brand color */
        text-style: bold;
    }

    .status-completed {
        color: $success;
    }

    .status-failed {
        color: $error;
    }

    .status-paused {
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
        self.active_migrations: List[Dict[str, Any]] = []
        self.selected_migration: Optional[str] = None
        self.tracker = tracker or MigrationTracker(logger=logger)
        self.controller = MigrationController(self.tracker, logger=logger)

    def compose(self) -> ComposeResult:
        """Compose the migrations panel UI."""
        # Header
        with Container(classes="migrations-header"):
            yield Static("📊 Active Migrations - Real-time monitoring")

        # Toolbar
        with Container(classes="migrations-toolbar"):
            with Horizontal(classes="toolbar-row"):
                yield Button("⏸️ Pause", id="btn_pause_migration", variant="default")
                yield Button("▶️ Resume", id="btn_resume_migration", variant="default")
                yield Button("🗑️ Cancel", id="btn_cancel_migration", variant="error")
                yield Button("🔄 Refresh", id="btn_refresh_migrations", variant="default")
                yield Button("📊 Details", id="btn_migration_details", variant="default")

        # Body with migrations table
        with Container(classes="migrations-body"):
            table = DataTable(classes="migrations-table", id="table_active_migrations")
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
        with Container(classes="migrations-footer"):
            with Horizontal(classes="stats-row"):
                yield Static("Running: 0", id="stat_running")
                yield Static("Paused: 0", id="stat_paused")
                yield Static("Completed: 0", id="stat_completed_migrations")
                yield Static("Failed: 0", id="stat_failed_migrations")
                yield Static("Avg Speed: 0 MB/s", id="stat_avg_speed")

    def populate_sample_migrations(self, table: DataTable) -> None:
        """Populate table with sample migration data."""
        sample_migrations = [
            ("001", "web-server-01", "running", "45%", "convert", "120 MB/s", "5m 30s", "14:30:15"),
            ("002", "database-server", "running", "78%", "validate", "95 MB/s", "2m 15s", "14:25:00"),
            ("003", "app-server-03", "paused", "23%", "transfer", "0 MB/s", "-", "14:20:00"),
            ("004", "backup-server", "completed", "100%", "done", "-", "0s", "14:15:00"),
        ]

        for idx, (id, name, status, progress, stage, throughput, eta, started) in enumerate(sample_migrations):
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
            "running": sum(1 for m in migrations if m[2] == "running"),
            "paused": sum(1 for m in migrations if m[2] == "paused"),
            "completed": sum(1 for m in migrations if m[2] == "completed"),
            "failed": sum(1 for m in migrations if m[2] == "failed"),
        }

        # Update Static widgets with calculated stats
        avg_speed = sum(1 for m in migrations if m[2] == "running") * 100  # Placeholder calculation

        stat_widgets = {
            "stat_running": f"Running: {stats['running']}",
            "stat_paused": f"Paused: {stats['paused']}",
            "stat_completed_migrations": f"Completed: {stats['completed']}",
            "stat_failed_migrations": f"Failed: {stats['failed']}",
            "stat_avg_speed": f"Avg Speed: {avg_speed} MB/s",
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

        if button_id == "btn_pause_migration":
            self.pause_migration()
        elif button_id == "btn_resume_migration":
            self.resume_migration()
        elif button_id == "btn_cancel_migration":
            self.cancel_migration()
        elif button_id == "btn_refresh_migrations":
            self.refresh_migrations()
        elif button_id == "btn_migration_details":
            self.show_details()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        self.selected_migration = event.row_key
        self.notify(f"Selected migration: {self.selected_migration}")

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

    def show_details(self) -> None:
        """Show detailed migration information."""
        if not self.selected_migration:
            self.notify("No migration selected", severity="warning")
            return

        self.notify("Migration details viewer - Coming soon!")
        # Note: Detailed dialog requires:
        # 1. Retrieve full migration record from tracker:
        #    - migration = self.tracker.get_migration(self.selected_migration)
        # 2. Create modal screen (similar to HelpDialog):
        #    - Display all migration metadata (VM name, paths, timestamps)
        #    - Show progress history and stage transitions
        #    - Display error messages if failed
        #    - Include performance metrics (throughput, duration)
        # 3. Push screen to display:
        #    - self.app.push_screen(MigrationDetailsDialog(migration))
        # Current implementation shows notification only.

    def refresh_migrations(self) -> None:
        """Refresh migration list from tracker."""
        try:
            # Reload from persistent storage
            self.tracker.load()

            # Cleanup finished processes
            self.controller.cleanup_finished_processes()

            # Get active migrations
            active_migrations = self.tracker.get_active_migrations()

            # Update statistics
            stats = self.tracker.get_statistics()
            self.update_stats_display(stats)

            self.notify(f"Refreshed: {len(active_migrations)} active migrations")

        except Exception as e:
            logger.exception("Failed to refresh migrations")
            self.notify(f"Refresh failed: {e}", severity="error")

    def update_stats_display(self, stats: Dict[str, Any]) -> None:
        """Update statistics widgets with new values."""
        try:
            # Update Static widgets if they exist
            stat_widgets = {
                "stat_running": f"Running: {stats.get('active_migrations', 0)}",
                "stat_paused": "Paused: 0",  # Would need to count paused specifically
                "stat_completed_migrations": f"Completed: {stats.get('total_completed', 0)}",
                "stat_failed_migrations": f"Failed: {stats.get('total_failed', 0)}",
                "stat_avg_speed": f"Avg Speed: {stats.get('avg_duration_seconds', 0):.1f} MB/s",
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
