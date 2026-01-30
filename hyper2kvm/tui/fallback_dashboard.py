# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/fallback_dashboard.py
"""
Fallback TUI dashboard using curses (no external dependencies).

This provides a basic TUI when Textual is not installed.
"""

from __future__ import annotations

import curses
import logging
import time
import threading
from collections import deque
from datetime import datetime
from typing import Dict, Deque, List, Optional, Any

# Import shared types
from .types import MigrationStatus, MAX_LOG_ENTRIES

logger = logging.getLogger(__name__)


class CursesDashboard:
    """
    Basic TUI dashboard using curses (fallback when Textual unavailable).

    Features:
    - Live migration status
    - Real-time metrics display
    - Scrolling log viewer
    - Keyboard shortcuts

    Keyboard Shortcuts:
    - q: Quit application
    - r: Refresh display
    - UP/DOWN: Scroll logs
    """

    def __init__(self, refresh_interval: float = 1.0):
        """
        Initialize dashboard.

        Args:
            refresh_interval: How often to refresh display (seconds)
        """
        self.refresh_interval = refresh_interval
        self._migrations: Dict[str, MigrationStatus] = {}
        self._logs: Deque[str] = deque(maxlen=MAX_LOG_ENTRIES)  # Auto-eviction when full
        self._log_offset = 0
        self._running = False
        self._stdscr = None
        self._lock = threading.RLock()  # Thread-safe access to data

    def run(self) -> None:
        """Run the dashboard."""
        curses.wrapper(self._main)

    def _main(self, stdscr) -> None:
        """Main curses loop."""
        self._stdscr = stdscr
        self._running = True

        # Initialize curses
        curses.curs_set(0)  # Hide cursor
        stdscr.nodelay(True)  # Non-blocking input
        stdscr.keypad(True)  # Enable keypad mode

        # Initialize color pairs if available (orange theme)
        if curses.has_colors():
            curses.start_color()
            # Try to use custom colors if terminal supports it
            if curses.can_change_color() and curses.COLORS >= 256:
                # Orange color theme
                curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Success (green)
                curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)  # Error (red)
                curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # In-progress (orange-ish)
                curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)  # Info
                curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_YELLOW)  # Header (orange bg)
                curses.init_pair(6, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Accent (orange)
            else:
                # Fallback for basic terminals
                curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Success
                curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)  # Error
                curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Warning/In-progress
                curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)  # Info
                curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_YELLOW)  # Header
                curses.init_pair(6, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Accent

        self.log_message("Dashboard initialized", "INFO")
        self.log_message("Waiting for migrations...", "INFO")

        last_refresh = time.time()

        while self._running:
            try:
                # Handle keyboard input
                key = stdscr.getch()
                if key == ord('q'):
                    self._running = False
                    break
                elif key == ord('r'):
                    self.log_message("Display refreshed", "INFO")
                elif key == curses.KEY_UP:
                    self._log_offset = max(0, self._log_offset - 1)
                elif key == curses.KEY_DOWN:
                    self._log_offset = min(max(0, len(self._logs) - 1), self._log_offset + 1)

                # Refresh display at interval
                now = time.time()
                if now - last_refresh >= self.refresh_interval:
                    self._refresh_display()
                    last_refresh = now

                time.sleep(0.1)  # Small sleep to reduce CPU usage

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")

    def _refresh_display(self) -> None:
        """Refresh the display."""
        if not self._stdscr:
            return

        try:
            self._stdscr.clear()
            height, width = self._stdscr.getmaxyx()

            # Draw header
            self._draw_header(width)

            # Draw metrics (top section)
            metrics_height = 10
            self._draw_metrics(2, 0, width, metrics_height)

            # Draw migrations (middle section)
            migrations_start = metrics_height + 2
            migrations_height = max(5, (height - migrations_start - 10))
            self._draw_migrations(migrations_start, 0, width, migrations_height)

            # Draw logs (bottom section)
            logs_start = migrations_start + migrations_height
            logs_height = height - logs_start - 2
            self._draw_logs(logs_start, 0, width, logs_height)

            # Draw footer
            self._draw_footer(height - 1, width)

            self._stdscr.refresh()
        except Exception as e:
            logger.error(f"Error refreshing display: {e}")

    def _draw_header(self, width: int) -> None:
        """Draw header bar."""
        try:
            title = "hyper2kvm Migration Dashboard"
            time_str = datetime.now().strftime("%H:%M:%S")
            header_text = f" {title} | {time_str} ".center(width)

            if curses.has_colors():
                self._stdscr.attron(curses.color_pair(5))
            self._stdscr.addstr(0, 0, header_text[:width - 1])
            if curses.has_colors():
                self._stdscr.attroff(curses.color_pair(5))
        except curses.error:
            pass  # Ignore if text doesn't fit

    def _draw_footer(self, y: int, width: int) -> None:
        """Draw footer bar."""
        try:
            footer_text = " Press 'q' to quit | 'r' to refresh | UP/DOWN to scroll logs ".center(width)
            if curses.has_colors():
                self._stdscr.attron(curses.color_pair(5))
            self._stdscr.addstr(y, 0, footer_text[:width - 1])
            if curses.has_colors():
                self._stdscr.attroff(curses.color_pair(5))
        except curses.error:
            pass

    def _draw_metrics(self, y: int, x: int, width: int, height: int) -> None:
        """Draw metrics section."""
        try:
            metrics = self._compute_metrics()

            self._stdscr.addstr(y, x, "=== METRICS ===".center(width)[:width - 1])
            y += 1

            active = metrics.get("active_migrations", 0)
            total = metrics.get("total_migrations", 0)
            success = metrics.get("successful_migrations", 0)
            failed = metrics.get("failed_migrations", 0)

            lines = [
                f"Active Migrations:     {active}",
                f"Total Migrations:      {total} (Success: {success} | Failed: {failed})",
            ]

            if total > 0:
                success_rate = (success / total) * 100
                lines.append(f"Success Rate:          {success_rate:.1f}%")

            avg_throughput = metrics.get("avg_throughput_mbps", 0)
            lines.append(f"Avg Throughput:        {avg_throughput:.1f} MB/s")

            total_bytes = metrics.get("total_bytes_processed", 0)
            total_gb = total_bytes / (1024**3)
            lines.append(f"Data Processed:        {total_gb:.2f} GB")

            for i, line in enumerate(lines):
                if y + i < y + height - 1:
                    self._stdscr.addstr(y + i, x + 2, line[:width - 3])

        except curses.error:
            pass

    def _draw_migrations(self, y: int, x: int, width: int, height: int) -> None:
        """Draw migrations section."""
        try:
            self._stdscr.addstr(y, x, "=== ACTIVE MIGRATIONS ===".center(width)[:width - 1])
            y += 1

            # Thread-safe copy of migrations
            with self._lock:
                migrations_copy = dict(self._migrations)

            if not migrations_copy:
                self._stdscr.addstr(y, x + 2, "No active migrations")
                return

            row = y
            for vm_name, migration in list(migrations_copy.items())[:height - 2]:
                if row >= y + height - 1:
                    break

                # Status symbol
                status_symbol = {
                    "pending": "PENDING",
                    "in_progress": "IN-PROG",
                    "completed": "DONE",
                    "failed": "FAILED",
                }.get(migration.status, "UNKNOWN")

                # Color based on status
                color_pair = 0
                if curses.has_colors():
                    color_pair = {
                        "completed": 1,  # Green
                        "failed": 2,  # Red
                        "in_progress": 3,  # Yellow
                    }.get(migration.status, 4)  # Cyan for others

                # Format line
                progress_pct = int(migration.progress * 100)
                progress_bar = self._render_progress_bar(migration.progress, 15)
                line = f"{vm_name[:20]:20} [{status_symbol:7}] {progress_pct:3}% {progress_bar}"

                if curses.has_colors() and color_pair:
                    self._stdscr.attron(curses.color_pair(color_pair))
                self._stdscr.addstr(row, x + 2, line[:width - 3])
                if curses.has_colors() and color_pair:
                    self._stdscr.attroff(curses.color_pair(color_pair))

                row += 1

                # Show additional details
                if row < y + height - 1:
                    throughput = f"{migration.throughput_mbps:.1f} MB/s" if migration.throughput_mbps > 0 else "N/A"
                    details = f"  Stage: {migration.current_stage[:20]:20} | {throughput}"
                    self._stdscr.addstr(row, x + 2, details[:width - 3])
                    row += 1

        except curses.error:
            pass

    def _draw_logs(self, y: int, x: int, width: int, height: int) -> None:
        """Draw logs section."""
        try:
            self._stdscr.addstr(y, x, "=== LOGS ===".center(width)[:width - 1])
            y += 1

            if not self._logs:
                self._stdscr.addstr(y, x + 2, "No logs available")
                return

            # Show last N logs
            visible_logs = self._logs[-height + 2:]
            for i, log_line in enumerate(visible_logs):
                if y + i < y + height - 1:
                    self._stdscr.addstr(y + i, x + 2, log_line[:width - 3])

        except curses.error:
            pass

    def _render_progress_bar(self, progress: float, width: int = 15) -> str:
        """Render a simple text progress bar."""
        filled = int(progress * width)
        empty = width - filled
        return f"[{'=' * filled}{' ' * empty}]"

    def _compute_metrics(self) -> Dict[str, Any]:
        """Compute current metrics from migration data."""
        migrations = list(self._migrations.values())

        active = len([m for m in migrations if m.status == "in_progress"])
        total = len(migrations)
        success = len([m for m in migrations if m.status == "completed"])
        failed = len([m for m in migrations if m.status == "failed"])

        completed_migrations = [m for m in migrations if m.status == "completed"]

        if completed_migrations:
            avg_throughput = sum(m.throughput_mbps for m in completed_migrations) / len(completed_migrations)
            avg_duration = sum(m.elapsed_seconds for m in completed_migrations) / len(completed_migrations)
            total_bytes = sum(m.throughput_mbps * m.elapsed_seconds * 1024 * 1024 for m in completed_migrations)
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
        }

    def add_migration(self, migration: MigrationStatus) -> None:
        """
        Add or update a migration in the dashboard.

        Args:
            migration: Migration status to add/update
        """
        with self._lock:
            self._migrations[migration.vm_name] = migration
        self.log_message(f"{migration.vm_name}: {migration.status} - {migration.current_stage}", "INFO")

    def remove_migration(self, vm_name: str) -> None:
        """
        Remove a migration from the dashboard.

        Args:
            vm_name: Name of VM to remove
        """
        with self._lock:
            if vm_name in self._migrations:
                del self._migrations[vm_name]

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

    def log_message(self, message: str, level: str = "INFO") -> None:
        """
        Add a log message to the log viewer.

        Args:
            message: Message to log
            level: Log level (INFO, WARNING, ERROR)
        """
        now = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{now}] [{level}] {message}"

        with self._lock:
            self._logs.append(log_entry)  # deque auto-evicts oldest when maxlen reached


def run_curses_dashboard(refresh_interval: float = 1.0) -> None:
    """
    Run the curses-based migration dashboard.

    Args:
        refresh_interval: How often to refresh (seconds)

    Example:
        >>> from hyper2kvm.tui.fallback_dashboard import run_curses_dashboard
        >>> run_curses_dashboard()
    """
    app = CursesDashboard(refresh_interval=refresh_interval)
    app.run()
