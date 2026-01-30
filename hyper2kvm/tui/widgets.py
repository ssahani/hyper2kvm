# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/widgets.py
"""
Custom Textual widgets for hyper2kvm TUI.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, Optional
from ..core.optional_imports import (
    TEXTUAL_AVAILABLE,
    Static,
    ProgressBar,
    DataTable,
    Container,
    Vertical,
    Horizontal,
    reactive,
)

# Import shared types
from .types import MigrationStatus

if not TEXTUAL_AVAILABLE:
    raise ImportError(
        "Textual library is required for TUI. "
        "Install with: pip install 'hyper2kvm[tui]'"
    )


class MigrationStatusWidget(Static):
    """Widget showing status of a single VM migration."""

    DEFAULT_CSS = """
    /* Orange theme for migration status widgets */
    MigrationStatusWidget {
        height: 5;
        border: heavy #ff8833;  /* Light orange */
        background: #331a00;
        color: #ffbb66;
        padding: 0 1;
        margin: 0 0 1 0;
    }

    MigrationStatusWidget.completed {
        border: heavy #66ff66;  /* Success green */
        background: #002200;
        color: #aaffaa;
    }

    MigrationStatusWidget.failed {
        border: heavy #ff4444;  /* Error red */
        background: #330000;
        color: #ff8888;
    }

    MigrationStatusWidget.in_progress {
        border: heavy #ffaa33;  /* Bright orange */
        background: #442200;
        color: #ffdd77;
    }

    MigrationStatusWidget.pending {
        border: heavy #ff6600;  /* Standard orange */
        background: #261500;
        color: #ffaa66;
    }
    """

    migration: reactive[Optional[MigrationStatus]] = reactive(None)

    def __init__(
        self,
        migration: Optional[MigrationStatus] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.migration = migration

    def watch_migration(self, migration: Optional[MigrationStatus]) -> None:
        """Update display when migration changes."""
        if migration:
            # Update CSS class based on status
            self.remove_class("completed", "failed", "in_progress")
            self.add_class(migration.status)

        self.update(self._render_migration())

    def _get_status_emoji(self, status: str) -> str:
        """
        Get status emoji with fallback for terminals that don't support Unicode.

        Args:
            status: Migration status

        Returns:
            Emoji or ASCII fallback
        """
        emoji_map = {
            "pending": "⏳",
            "in_progress": "🔄",
            "completed": "✅",
            "failed": "❌",
        }

        # Fallback for terminals that don't support Unicode
        ascii_map = {
            "pending": "[WAIT]",
            "in_progress": "[WORK]",
            "completed": "[DONE]",
            "failed": "[FAIL]",
        }

        try:
            # Check if stdout can encode emoji
            import sys
            emoji = emoji_map.get(status, "❓")
            encoding = sys.stdout.encoding or 'utf-8'
            emoji.encode(encoding)
            return emoji
        except (UnicodeEncodeError, LookupError, AttributeError):
            return ascii_map.get(status, "[????]")

    def _render_migration(self) -> str:
        """Render migration status as text."""
        if not self.migration:
            return "No migration data"

        m = self.migration

        # Status emoji with fallback
        status_emoji = self._get_status_emoji(m.status)

        # Format progress
        progress_pct = int(m.progress * 100)
        progress_bar = self._render_progress_bar(m.progress)

        # Format throughput
        throughput = f"{m.throughput_mbps:.1f} MB/s" if m.throughput_mbps > 0 else "N/A"

        # Format time
        elapsed = self._format_duration(m.elapsed_seconds)
        eta = f" | ETA: {self._format_duration(m.eta_seconds)}" if m.eta_seconds else ""

        # Build output
        lines = [
            f"{status_emoji} {m.vm_name} ({m.hypervisor}) - {m.status.upper()}",
            f"Stage: {m.current_stage} | {progress_pct}% {progress_bar}",
            f"Throughput: {throughput} | Elapsed: {elapsed}{eta}",
        ]

        if m.error:
            lines.append(f"Error: {m.error}")

        return "\n".join(lines)

    def _render_progress_bar(self, progress: float, width: int = 20) -> str:
        """Render a simple text progress bar."""
        filled = int(progress * width)
        empty = width - filled
        return f"[{'█' * filled}{'░' * empty}]"

    def _format_duration(self, seconds: Optional[float]) -> str:
        """Format duration in human-readable format."""
        if seconds is None:
            return "N/A"

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


class MetricsWidget(Static):
    """Widget showing key metrics."""

    DEFAULT_CSS = """
    /* Orange theme for metrics widget */
    MetricsWidget {
        height: 10;
        border: heavy #ff7722;  /* Medium orange */
        background: #261500;
        color: #ffbb66;  /* Light orange */
        padding: 0 1;
    }
    """

    metrics: reactive[Dict[str, Any]] = reactive({})

    def __init__(self, metrics: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(**kwargs)
        self.metrics = metrics or {}

    def watch_metrics(self, metrics: Dict[str, Any]) -> None:
        """Update display when metrics change."""
        self.update(self._render_metrics())

    def _render_metrics(self) -> str:
        """Render metrics as text."""
        if not self.metrics:
            return "No metrics available"

        lines = ["📊 Migration Metrics", "─" * 40]

        # Active migrations
        active = self.metrics.get("active_migrations", 0)
        lines.append(f"Active Migrations:     {active}")

        # Total migrations
        total = self.metrics.get("total_migrations", 0)
        success = self.metrics.get("successful_migrations", 0)
        failed = self.metrics.get("failed_migrations", 0)
        lines.append(f"Total Migrations:      {total} (✅ {success} | ❌ {failed})")

        # Success rate
        if total > 0:
            success_rate = (success / total) * 100
            lines.append(f"Success Rate:          {success_rate:.1f}%")
        else:
            lines.append(f"Success Rate:          N/A")

        # Throughput
        avg_throughput = self.metrics.get("avg_throughput_mbps", 0)
        lines.append(f"Avg Throughput:        {avg_throughput:.1f} MB/s")

        # Total data processed
        total_bytes = self.metrics.get("total_bytes_processed", 0)
        total_gb = total_bytes / (1024**3)
        lines.append(f"Data Processed:        {total_gb:.2f} GB")

        # Average duration
        avg_duration = self.metrics.get("avg_duration_seconds", 0)
        lines.append(f"Avg Duration:          {self._format_duration(avg_duration)}")

        # Error rate
        error_rate = self.metrics.get("error_rate_per_minute", 0)
        lines.append(f"Error Rate:            {error_rate:.2f} errors/min")

        return "\n".join(lines)

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


class MigrationTable(Static):
    """Table showing all migrations."""

    DEFAULT_CSS = """
    /* Orange theme for migration table */
    MigrationTable {
        height: 100%;
        border: heavy #ff8833;  /* Light orange */
        background: #261500;
        color: #ffbb66;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._migrations: Dict[str, MigrationStatus] = {}

    def compose(self):
        """Create child widgets."""
        table = DataTable()
        table.add_columns("VM Name", "Hypervisor", "Status", "Progress", "Stage", "Throughput")
        yield table

    def add_migration(self, migration: MigrationStatus) -> None:
        """Add or update a migration in the table."""
        self._migrations[migration.vm_name] = migration
        self._refresh_table()

    def remove_migration(self, vm_name: str) -> None:
        """Remove a migration from the table."""
        if vm_name in self._migrations:
            del self._migrations[vm_name]
            self._refresh_table()

    def _refresh_table(self) -> None:
        """Refresh the table with current migrations."""
        table = self.query_one(DataTable)
        table.clear()

        for vm_name, m in self._migrations.items():
            # Status emoji
            status_emoji = {
                "pending": "⏳",
                "in_progress": "🔄",
                "completed": "✅",
                "failed": "❌",
            }.get(m.status, "❓")

            # Format values
            progress_pct = f"{int(m.progress * 100)}%"
            throughput = f"{m.throughput_mbps:.1f} MB/s" if m.throughput_mbps > 0 else "N/A"

            table.add_row(
                vm_name,
                m.hypervisor,
                f"{status_emoji} {m.status}",
                progress_pct,
                m.current_stage,
                throughput,
            )
