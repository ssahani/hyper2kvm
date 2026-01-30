# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/cli_dashboard.py
"""
CLI-based dashboard fallback (for systems without curses, e.g., Windows).

This provides a simple terminal output when neither Textual nor curses are available.
"""

from __future__ import annotations

import sys
import time
import os
import threading
from collections import deque
from datetime import datetime
from typing import Dict, Deque, List, Optional, Any

# Import shared types
from .types import MigrationStatus, MAX_LOG_ENTRIES_CLI, CLI_REFRESH_INTERVAL


class CLIDashboard:
    """
    Simple CLI-based dashboard (fallback when Textual and curses unavailable).

    This continuously updates the terminal with migration status.
    Works on all platforms including Windows.
    """

    def __init__(self, refresh_interval: float = CLI_REFRESH_INTERVAL):
        """
        Initialize dashboard.

        Args:
            refresh_interval: How often to refresh display (seconds)
        """
        self.refresh_interval = refresh_interval
        self._migrations: Dict[str, MigrationStatus] = {}
        self._logs: Deque[str] = deque(maxlen=MAX_LOG_ENTRIES_CLI)  # Auto-eviction when full
        self._running = False
        self._last_line_count = 0
        self._lock = threading.RLock()  # Thread-safe access to data

    def run(self) -> None:
        """Run the dashboard."""
        self._running = True

        print("=" * 80)
        print("hyper2kvm Migration Dashboard".center(80))
        print("=" * 80)
        print("\nPress Ctrl+C to quit\n")

        self.log_message("Dashboard initialized", "INFO")
        self.log_message("Waiting for migrations...", "INFO")

        try:
            while self._running:
                self._refresh_display()
                time.sleep(self.refresh_interval)
        except KeyboardInterrupt:
            print("\n\nDashboard stopped.")
            self._running = False

    def _refresh_display(self) -> None:
        """Refresh the display."""
        # Clear previous output (simple approach)
        self._clear_screen()

        # Print header
        print("=" * 80)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"hyper2kvm Migration Dashboard - {timestamp}".center(80))
        print("=" * 80)

        # Print metrics
        self._print_metrics()

        # Print migrations
        self._print_migrations()

        # Print recent logs
        self._print_logs()

        # Print footer
        print("\n" + "=" * 80)
        print("Press Ctrl+C to quit".center(80))
        print("=" * 80)

    def _clear_screen(self) -> None:
        """Clear the terminal screen using ANSI escape codes."""
        # Use ANSI escape codes - works on all modern terminals, no shell execution
        # \033[2J clears entire screen, \033[H moves cursor to home position
        print('\033[2J\033[H', end='')
        sys.stdout.flush()

    def _print_metrics(self) -> None:
        """Print metrics section."""
        metrics = self._compute_metrics()

        print("\n[METRICS]")
        print("-" * 80)

        active = metrics.get("active_migrations", 0)
        total = metrics.get("total_migrations", 0)
        success = metrics.get("successful_migrations", 0)
        failed = metrics.get("failed_migrations", 0)

        print(f"  Active Migrations:     {active}")
        print(f"  Total Migrations:      {total} (Success: {success} | Failed: {failed})")

        if total > 0:
            success_rate = (success / total) * 100
            print(f"  Success Rate:          {success_rate:.1f}%")

        avg_throughput = metrics.get("avg_throughput_mbps", 0)
        print(f"  Avg Throughput:        {avg_throughput:.1f} MB/s")

        total_bytes = metrics.get("total_bytes_processed", 0)
        total_gb = total_bytes / (1024**3)
        print(f"  Data Processed:        {total_gb:.2f} GB")

    def _print_migrations(self) -> None:
        """Print migrations section."""
        print("\n[ACTIVE MIGRATIONS]")
        print("-" * 80)

        # Thread-safe copy of migrations
        with self._lock:
            migrations_copy = dict(self._migrations)

        if not migrations_copy:
            print("  No active migrations")
            return

        for vm_name, migration in migrations_copy.items():
            # Status symbol
            status_symbol = {
                "pending": "⏳ PENDING",
                "in_progress": "🔄 IN-PROGRESS",
                "completed": "✅ COMPLETED",
                "failed": "❌ FAILED",
            }.get(migration.status, "❓ UNKNOWN")

            # Progress bar
            progress_pct = int(migration.progress * 100)
            progress_bar = self._render_progress_bar(migration.progress, 30)

            print(f"\n  {vm_name} ({migration.hypervisor})")
            print(f"  Status: {status_symbol}")
            print(f"  Progress: {progress_pct:3}% {progress_bar}")
            print(f"  Stage: {migration.current_stage}")

            if migration.throughput_mbps > 0:
                print(f"  Throughput: {migration.throughput_mbps:.1f} MB/s")

            if migration.elapsed_seconds > 0:
                elapsed = self._format_duration(migration.elapsed_seconds)
                print(f"  Elapsed: {elapsed}")

            if migration.error:
                print(f"  Error: {migration.error}")

    def _print_logs(self) -> None:
        """Print logs section."""
        print("\n[RECENT LOGS]")
        print("-" * 80)

        # Thread-safe copy of logs
        with self._lock:
            recent_logs = list(self._logs[-10:])

        if not recent_logs:
            print("  No logs available")
            return

        # Show last 10 logs
        for log_line in recent_logs:
            print(f"  {log_line}")

    def _render_progress_bar(self, progress: float, width: int = 30) -> str:
        """Render a simple text progress bar."""
        filled = int(progress * width)
        empty = width - filled
        return f"[{'=' * filled}{' ' * empty}]"

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            mins = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        else:
            hours = int(seconds / 3600)
            mins = int((seconds % 3600) / 60)
            return f"{hours}h {mins}m"

    def _compute_metrics(self) -> Dict[str, Any]:
        """Compute current metrics from migration data."""
        # Thread-safe copy of migrations
        with self._lock:
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
            self._migrations.pop(vm_name, None)

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


def run_cli_dashboard(refresh_interval: float = 2.0) -> None:
    """
    Run the CLI-based migration dashboard.

    Args:
        refresh_interval: How often to refresh (seconds)

    Example:
        >>> from hyper2kvm.tui.cli_dashboard import run_cli_dashboard
        >>> run_cli_dashboard()
    """
    app = CLIDashboard(refresh_interval=refresh_interval)
    app.run()
