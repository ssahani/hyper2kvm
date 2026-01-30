# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/dashboard.py
"""
Main TUI dashboard application for real-time migration monitoring.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
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
        self._lock = threading.RLock()  # Thread-safe access to data
        self._error_timestamps: List[float] = []  # Track error times for rate calculation

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
        try:
            while not self.is_exiting:
                try:
                    await asyncio.sleep(self.refresh_interval)
                    if not self.is_exiting:
                        self.refresh_display()
                except Exception as e:
                    if self.is_exiting:
                        break
                    logger.error(f"Error in refresh worker: {e}")
        except asyncio.CancelledError:
            logger.debug("Refresh worker cancelled")
            # Clean up any pending operations
            with self._lock:
                # Clear widget references to prevent stale references
                for widget_id in list(self._migration_widgets.keys()):
                    try:
                        widget = self._migration_widgets.get(widget_id)
                        if widget and hasattr(widget, 'is_mounted') and widget.is_mounted:
                            widget.remove()
                    except Exception:
                        pass  # Best effort cleanup
            raise  # Re-raise to ensure proper cleanup
        finally:
            logger.debug("Refresh worker terminated")

    def _sanitize_text(self, text: str) -> str:
        """
        Sanitize text for safe display in logs and UI.

        Removes control characters, escape sequences, and newlines to prevent
        log injection and terminal escape sequence attacks.

        Args:
            text: Text to sanitize

        Returns:
            Sanitized text safe for display
        """
        # Remove control characters (0x00-0x1f, 0x7f-0x9f) except tab
        sanitized = re.sub(r'[\x00-\x08\x0b-\x1f\x7f-\x9f]', '', text)
        # Replace newlines and tabs with spaces
        sanitized = sanitized.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
        # Collapse multiple spaces
        sanitized = re.sub(r'\s+', ' ', sanitized)
        return sanitized.strip()

    def refresh_display(self) -> None:
        """Refresh all widgets with latest data."""
        # Update metrics widget
        metrics_widget = self.query_one("#metrics_widget", MetricsWidget)
        metrics_widget.metrics = self._compute_metrics()

        # Update status bar
        status_bar = self.query_one("#status_bar", Static)
        now = datetime.now().strftime("%H:%M:%S")
        with self._lock:
            active = len([m for m in self._migrations.values() if m.status == "in_progress"])
        status_bar.update(f"Last update: {now} | Active migrations: {active} | Press 'q' to quit")

    def _compute_metrics(self) -> Dict[str, Any]:
        """Compute current metrics from migration data."""
        import time

        # Thread-safe copy of migrations and error timestamps
        with self._lock:
            migrations = list(self._migrations.values())
            error_timestamps = list(self._error_timestamps)

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

        # Calculate error rate per minute (errors in last minute)
        current_time = time.time()
        one_minute_ago = current_time - 60
        recent_errors = [t for t in error_timestamps if t >= one_minute_ago]
        error_rate = len(recent_errors)

        # Clean up old error timestamps (keep last hour only)
        with self._lock:
            one_hour_ago = current_time - 3600
            self._error_timestamps = [t for t in self._error_timestamps if t >= one_hour_ago]

        return {
            "active_migrations": active,
            "total_migrations": total,
            "successful_migrations": success,
            "failed_migrations": failed,
            "avg_throughput_mbps": avg_throughput,
            "avg_duration_seconds": avg_duration,
            "total_bytes_processed": total_bytes,
            "error_rate_per_minute": error_rate,
        }

    def add_migration(self, migration: MigrationStatus) -> None:
        """
        Add or update a migration in the dashboard.

        Args:
            migration: Migration status to add/update
        """
        vm_name = migration.vm_name
        needs_mount = False
        widget = None

        # Phase 1: Update data structures (hold lock briefly)
        # This prevents TOCTOU race by checking and updating atomically
        with self._lock:
            # Track error timestamps for rate calculation
            old_migration = self._migrations.get(vm_name)
            if (old_migration is None or old_migration.status != "failed") and migration.status == "failed":
                # New failure detected
                import time
                self._error_timestamps.append(time.time())

            self._migrations[vm_name] = migration

            if vm_name in self._migration_widgets:
                widget = self._migration_widgets[vm_name]
                # Will update existing widget outside lock
            else:
                # Create new widget
                widget = MigrationStatusWidget(migration)
                # Only add to dict after successful mount to prevent leaks
                needs_mount = True

        # Phase 2: Update or mount widget (no lock held to prevent deadlock)
        if needs_mount:
            try:
                container = self.query_one("#migrations_container", ScrollableContainer)
                container.mount(widget)
                # Only add to dict if mount succeeds (prevents memory leak)
                with self._lock:
                    self._migration_widgets[vm_name] = widget
            except Exception as e:
                # Clean up widget on failure
                try:
                    if hasattr(widget, 'remove'):
                        widget.remove()
                except Exception:
                    pass
                logger.error(f"Error mounting widget for {vm_name}: {e}")
                raise
        else:
            # Update existing widget
            widget.migration = migration

        # Phase 3: Logging (no lock held, sanitize to prevent injection)
        log = self.query_one("#log_widget", TextualLog)
        now = datetime.now().strftime("%H:%M:%S")
        safe_vm_name = self._sanitize_text(migration.vm_name)
        safe_status = self._sanitize_text(migration.status)
        safe_stage = self._sanitize_text(migration.current_stage)
        log.write_line(f"[{now}] {safe_vm_name}: {safe_status} - {safe_stage}")

        # Refresh display
        self.refresh_display()

    def remove_migration(self, vm_name: str) -> None:
        """
        Remove a migration from the dashboard.

        Args:
            vm_name: Name of VM to remove
        """
        widget_to_remove = None

        # Atomically remove from both data structures to prevent races
        with self._lock:
            self._migrations.pop(vm_name, None)
            widget_to_remove = self._migration_widgets.pop(vm_name, None)

        # Remove widget outside lock to prevent deadlock
        if widget_to_remove:
            try:
                # Check widget is still valid and mounted before removing
                if hasattr(widget_to_remove, 'is_mounted') and widget_to_remove.is_mounted:
                    widget_to_remove.remove()
            except Exception as e:
                logger.error(f"Error removing widget for {vm_name}: {e}", exc_info=True)
                # Try force removal from parent
                try:
                    if hasattr(widget_to_remove, 'parent') and widget_to_remove.parent:
                        parent = widget_to_remove.parent
                        if hasattr(parent, 'children'):
                            parent.children.remove(widget_to_remove)
                except Exception:
                    logger.critical(f"Failed to force-remove widget {vm_name}, potential memory leak")

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
        with self._lock:
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

        # Sanitize message to prevent log injection
        safe_message = self._sanitize_text(message)
        log.write_line(f"[{now}] {emoji} {safe_message}")

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
