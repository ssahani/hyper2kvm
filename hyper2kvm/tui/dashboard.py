# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/dashboard.py
"""
Main TUI dashboard application for real-time migration monitoring.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from ..core.optional_imports import (
    TEXTUAL_AVAILABLE,
    App,
    ComposeResult,
    Header,
    Footer,
    Static,
    TextualLog,
    Container,
    Vertical,
    Horizontal,
    ScrollableContainer,
    Binding,
    work,
)

if not TEXTUAL_AVAILABLE:
    raise ImportError(
        "Textual library is required for TUI. "
        "Install with: pip install 'hyper2kvm[tui]'"
    )

from .widgets import MigrationStatusWidget, MetricsWidget, MigrationStatus
from ..core.metrics import (
    migrations_active,
    migrations_total,
    migration_duration_seconds,
    disk_conversion_bytes_total,
)

logger = logging.getLogger(__name__)


class MigrationDashboard(App):
    """
    Real-time TUI dashboard for hyper2kvm migrations.

    Features:
    - Live migration status with progress bars
    - Real-time metrics display
    - Scrolling log viewer
    - Keyboard shortcuts for navigation

    Keyboard Shortcuts:
    - q: Quit application
    - r: Refresh display
    - l: Focus log viewer
    - m: Focus migrations
    - d: Toggle dark mode
    """

    CSS = """
    /* Orange theme - warm, energetic color scheme */
    Screen {
        layout: grid;
        grid-size: 2 3;
        grid-rows: auto 1fr auto;
        background: #1a0f00;  /* Deep dark orange-brown */
    }

    Header {
        background: #ff6600;  /* Bright orange */
        color: #fff;
        text-style: bold;
    }

    Footer {
        background: #ff6600;  /* Bright orange */
        color: #fff;
    }

    #migrations_container {
        column-span: 2;
        height: 1fr;
        border: heavy #ff8833;  /* Light orange */
        background: #261500;
        border-title-color: #ffaa44;
        border-title-style: bold;
    }

    #migrations_header {
        color: #ffaa44;  /* Gold-orange */
        text-style: bold;
        background: #331a00;
        padding: 1;
    }

    #metrics_container {
        height: 1fr;
        border: heavy #ff7722;  /* Medium orange */
        background: #261500;
        border-title-color: #ffaa44;
    }

    #logs_container {
        height: 1fr;
        border: heavy #ff7722;  /* Medium orange */
        background: #261500;
        border-title-color: #ffaa44;
    }

    #status_bar {
        column-span: 2;
        height: 3;
        background: #331a00;  /* Dark orange-brown */
        border: heavy #ff8833;
        border-title-color: #ffaa44;
        color: #ffcc66;  /* Light orange-yellow */
        padding: 0 1;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("l", "focus_logs", "Logs", show=True),
        Binding("m", "focus_migrations", "Migrations", show=True),
        Binding("d", "toggle_dark", "Dark Mode", show=True),
    ]

    TITLE = "hyper2kvm Migration Dashboard"

    def __init__(self, refresh_interval: float = 1.0, **kwargs):
        """
        Initialize dashboard.

        Args:
            refresh_interval: How often to refresh display (seconds)
        """
        super().__init__(**kwargs)
        self.refresh_interval = refresh_interval
        self._migrations: Dict[str, MigrationStatus] = {}
        self._metrics: Dict[str, Any] = {}
        self._migration_widgets: Dict[str, MigrationStatusWidget] = {}

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header(show_clock=True)

        # Migrations container
        with ScrollableContainer(id="migrations_container"):
            yield Static("📦 Active Migrations", id="migrations_header")

        # Metrics panel
        with Container(id="metrics_container"):
            yield MetricsWidget(id="metrics_widget")

        # Logs panel
        with Container(id="logs_container"):
            log_widget = TextualLog(id="log_widget")
            log_widget.border_title = "📝 Migration Logs"
            yield log_widget

        # Status bar
        yield Static("Ready | Press 'q' to quit, 'r' to refresh", id="status_bar")

        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted."""
        logger.info("Migration dashboard started")

        # Start background refresh worker
        self.refresh_worker()

        # Log some initial messages
        log = self.query_one("#log_widget", TextualLog)
        log.write_line("✅ Dashboard initialized")
        log.write_line("⏳ Waiting for migrations...")

    @work(exclusive=True)
    async def refresh_worker(self) -> None:
        """Background worker to refresh dashboard periodically."""
        while not self.is_exiting:
            try:
                await asyncio.sleep(self.refresh_interval)
                if not self.is_exiting:
                    self.refresh_display()
            except asyncio.CancelledError:
                # Normal shutdown
                break
            except Exception as e:
                logger.error(f"Error in refresh worker: {e}")
                # Don't re-raise, just log and continue

    def refresh_display(self) -> None:
        """Refresh all widgets with latest data."""
        # Update metrics widget
        metrics_widget = self.query_one("#metrics_widget", MetricsWidget)
        metrics_widget.metrics = self._compute_metrics()

        # Update status bar
        status_bar = self.query_one("#status_bar", Static)
        now = datetime.now().strftime("%H:%M:%S")
        active = len([m for m in self._migrations.values() if m.status == "in_progress"])
        status_bar.update(f"Last update: {now} | Active migrations: {active} | Press 'q' to quit")

    def _compute_metrics(self) -> Dict[str, Any]:
        """Compute current metrics from migration data."""
        migrations = list(self._migrations.values())

        active = len([m for m in migrations if m.status == "in_progress"])
        total = len(migrations)
        success = len([m for m in migrations if m.status == "completed"])
        failed = len([m for m in migrations if m.status == "failed"])

        # Calculate averages
        completed_migrations = [m for m in migrations if m.status == "completed"]

        if completed_migrations:
            avg_throughput = sum(m.throughput_mbps for m in completed_migrations) / len(
                completed_migrations
            )
            avg_duration = sum(m.elapsed_seconds for m in completed_migrations) / len(
                completed_migrations
            )
            total_bytes = sum(
                m.throughput_mbps * m.elapsed_seconds * 1024 * 1024 for m in completed_migrations
            )
        else:
            avg_throughput = 0
            avg_duration = 0
            total_bytes = 0

        return {
            "active_migrations": active,
            "total_migrations": total,
            "successful_migrations": success,
            "failed_migrations": failed,
            "avg_throughput_mbps": avg_throughput,
            "avg_duration_seconds": avg_duration,
            "total_bytes_processed": total_bytes,
            "error_rate_per_minute": 0,  # TODO: Calculate from error log
        }

    def add_migration(self, migration: MigrationStatus) -> None:
        """
        Add or update a migration in the dashboard.

        Args:
            migration: Migration status to add/update
        """
        vm_name = migration.vm_name

        # Update internal tracking
        self._migrations[vm_name] = migration

        # Get migrations container
        container = self.query_one("#migrations_container", ScrollableContainer)

        # Update or create widget
        if vm_name in self._migration_widgets:
            # Update existing widget
            widget = self._migration_widgets[vm_name]
            widget.migration = migration
        else:
            # Create new widget
            widget = MigrationStatusWidget(migration)
            self._migration_widgets[vm_name] = widget
            container.mount(widget)

        # Log the update
        log = self.query_one("#log_widget", TextualLog)
        now = datetime.now().strftime("%H:%M:%S")
        log.write_line(f"[{now}] {migration.vm_name}: {migration.status} - {migration.current_stage}")

        # Refresh display
        self.refresh_display()

    def remove_migration(self, vm_name: str) -> None:
        """
        Remove a migration from the dashboard.

        Args:
            vm_name: Name of VM to remove
        """
        if vm_name in self._migrations:
            del self._migrations[vm_name]

        if vm_name in self._migration_widgets:
            widget = self._migration_widgets[vm_name]
            try:
                widget.remove()
            except Exception as e:
                logger.error(f"Error removing widget for {vm_name}: {e}")
            finally:
                # Always remove from dict to prevent memory leak
                del self._migration_widgets[vm_name]

        self.refresh_display()

    def update_migration_progress(
        self,
        vm_name: str,
        progress: float,
        stage: str = "",
        throughput_mbps: float = 0.0,
    ) -> None:
        """
        Update progress for a migration.

        Args:
            vm_name: Name of VM
            progress: Progress (0.0 to 1.0)
            stage: Current stage name
            throughput_mbps: Current throughput in MB/s
        """
        if vm_name in self._migrations:
            migration = self._migrations[vm_name]
            migration.progress = progress
            if stage:
                migration.current_stage = stage
            if throughput_mbps > 0:
                migration.throughput_mbps = throughput_mbps

            # Update widget
            if vm_name in self._migration_widgets:
                self._migration_widgets[vm_name].migration = migration

    def log_message(self, message: str, level: str = "INFO") -> None:
        """
        Add a log message to the log viewer.

        Args:
            message: Message to log
            level: Log level (INFO, WARNING, ERROR)
        """
        log = self.query_one("#log_widget", TextualLog)
        now = datetime.now().strftime("%H:%M:%S")

        # Add emoji based on level
        emoji = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "SUCCESS": "✅",
        }.get(level, "📝")

        log.write_line(f"[{now}] {emoji} {message}")

    # Action handlers

    def action_refresh(self) -> None:
        """Refresh the display."""
        self.refresh_display()
        self.log_message("Display refreshed", "INFO")

    def action_focus_logs(self) -> None:
        """Focus the log viewer."""
        log_widget = self.query_one("#log_widget", TextualLog)
        log_widget.focus()

    def action_focus_migrations(self) -> None:
        """Focus the migrations container."""
        container = self.query_one("#migrations_container", ScrollableContainer)
        container.focus()

    def action_toggle_dark(self) -> None:
        """Toggle dark mode."""
        self.dark = not self.dark


# Convenience function to run dashboard
def run_dashboard(refresh_interval: float = 1.0) -> None:
    """
    Run the migration dashboard TUI.

    Args:
        refresh_interval: How often to refresh (seconds)

    Example:
        >>> from hyper2kvm.tui.dashboard import run_dashboard
        >>> run_dashboard()
    """
    app = MigrationDashboard(refresh_interval=refresh_interval)
    app.run()
