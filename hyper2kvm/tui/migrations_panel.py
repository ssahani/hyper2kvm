# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/migrations_panel.py
"""
Migrations panel for displaying active migrations in the main app.
"""

from __future__ import annotations

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
        background: $primary;
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
        color: $accent;
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.active_migrations: List[Dict[str, Any]] = []
        self.selected_migration: Optional[str] = None

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

        # TODO: Update Static widgets with actual stats

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

        self.notify(f"Pausing migration {self.selected_migration}...")
        # TODO: Implement pause logic

    def resume_migration(self) -> None:
        """Resume selected migration."""
        if not self.selected_migration:
            self.notify("No migration selected", severity="warning")
            return

        self.notify(f"Resuming migration {self.selected_migration}...")
        # TODO: Implement resume logic

    def cancel_migration(self) -> None:
        """Cancel selected migration."""
        if not self.selected_migration:
            self.notify("No migration selected", severity="warning")
            return

        self.notify(f"Cancelling migration {self.selected_migration}...", severity="warning")
        # TODO: Implement cancel logic

    def show_details(self) -> None:
        """Show detailed migration information."""
        if not self.selected_migration:
            self.notify("No migration selected", severity="warning")
            return

        self.notify("Migration details viewer - Coming soon!")
        # TODO: Show detailed dialog

    def refresh_migrations(self) -> None:
        """Refresh migration list."""
        self.notify("Refreshing migrations...")
        # TODO: Reload from backend
