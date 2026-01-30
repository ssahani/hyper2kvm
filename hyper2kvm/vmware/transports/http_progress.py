# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/vmware/transports/http_progress.py
"""
Progress reporter implementations for HTTP downloads.

Provides multiple progress reporting strategies using the Strategy pattern:
- RichProgressReporter: Fancy animated progress bars (requires Rich + TTY)
- SimpleProgressReporter: Basic percentage display (requires TTY)
- LoggingProgressReporter: Log-based progress (works everywhere)
- NoopProgressReporter: Silent (no output)
"""

from __future__ import annotations

import logging
import sys
from abc import ABC, abstractmethod
from typing import Any

# Import from sibling module
from ...core.utils import U
from ..utils.utils import create_console as _console
from ..utils.utils import is_tty as _is_tty

# Optional: Rich UI
try:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
    )

    RICH_AVAILABLE = True
except Exception:
    Console = None  # type: ignore
    Progress = None  # type: ignore
    SpinnerColumn = None  # type: ignore
    BarColumn = None  # type: ignore
    DownloadColumn = None  # type: ignore
    TextColumn = None  # type: ignore
    TimeRemainingColumn = None  # type: ignore
    TimeElapsedColumn = None  # type: ignore
    TransferSpeedColumn = None  # type: ignore
    RICH_AVAILABLE = False


# Helper Functions
def _rich_construct(cls: Any, *args: Any, **kwargs: Any) -> Any:
    """
    Construct a Rich column in a way that is compatible across Rich versions.

    Some Rich versions do not accept certain kwargs (e.g., TimeRemainingColumn(style=...)).
    We try once with kwargs; if that fails, we retry after dropping known-problem kwargs.
    """
    try:
        return cls(*args, **kwargs)
    except TypeError:
        # Retry with a reduced set of kwargs.
        # Common offender: style= on TimeRemainingColumn / TimeElapsedColumn.
        for bad in ("style", "justify", "markup"):
            if bad in kwargs:
                kwargs = dict(kwargs)
                kwargs.pop(bad, None)
        return cls(*args, **kwargs)


# Progress Reporter Interface (Strategy Pattern)
class ProgressReporter(ABC):
    """Abstract base class for progress reporters."""

    @abstractmethod
    def start(self, description: str, total: int | None = None) -> None:
        """Start progress tracking."""
        ...

    @abstractmethod
    def update(self, delta: int) -> None:
        """Update progress by delta bytes."""
        ...

    @abstractmethod
    def finish(self) -> None:
        """Finish progress tracking."""
        ...


class RichProgressReporter(ProgressReporter):
    """Rich-based progress reporter with fancy animated bars."""

    def __init__(self, console: Any, refresh_hz: float = 10.0):
        self.console = console
        self.refresh_hz = refresh_hz
        self.progress: Any | None = None
        self.task_id: int | None = None

    def start(self, description: str, total: int | None = None) -> None:
        # Build columns with version-safe constructors
        spinner = _rich_construct(SpinnerColumn, style="bright_green")
        desc = _rich_construct(TextColumn, "[progress.description]{task.description}", style="bold cyan")
        bar = _rich_construct(
            BarColumn,
            complete_style="bright_blue",
            finished_style="bright_green",
            pulse_style="magenta",
        )
        downloaded = _rich_construct(DownloadColumn)
        speed = _rich_construct(TransferSpeedColumn)
        remaining = _rich_construct(TimeRemainingColumn, style="yellow")
        elapsed = _rich_construct(TimeElapsedColumn, style="dim green")

        self.progress = Progress(
            spinner,
            desc,
            bar,
            downloaded,
            speed,
            remaining,
            elapsed,
            console=self.console,
            transient=False,  # Keep progress bar visible after completion
            refresh_per_second=max(1, int(self.refresh_hz)),
        )
        self.progress.start()
        self.task_id = self.progress.add_task(
            description,
            total=total if total and total > 0 else None,
        )

    def update(self, delta: int) -> None:
        if self.progress and self.task_id is not None:
            self.progress.update(self.task_id, advance=delta)

    def finish(self) -> None:
        if self.progress:
            try:
                self.progress.stop()
            except Exception:
                pass


class SimpleProgressReporter(ProgressReporter):
    """Simple single-line progress reporter for TTY."""

    def __init__(self, file_name: str):
        self.file_name = file_name
        self.downloaded = 0
        self.total: int | None = None

    def start(self, description: str, total: int | None = None) -> None:
        self.total = total
        self._update_display()

    def update(self, delta: int) -> None:
        self.downloaded += delta
        self._update_display()

    def _update_display(self) -> None:
        if self.total and self.total > 0:
            pct = (self.downloaded / self.total) * 100.0
            s = f"{pct:.1f}% ({U.human_bytes(self.downloaded)}/{U.human_bytes(self.total)})"
        else:
            s = f"{U.human_bytes(self.downloaded)} (size unknown)"
        sys.stdout.write(f"Downloading {self.file_name}: {s} \r")
        sys.stdout.flush()

    def finish(self) -> None:
        sys.stdout.write("\n")
        sys.stdout.flush()


class LoggingProgressReporter(ProgressReporter):
    """Logging-based progress reporter (works in all environments)."""

    def __init__(self, logger: logging.Logger, log_every_bytes: int = 128 * 1024 * 1024):
        self.logger = logger
        self.log_every_bytes = log_every_bytes
        self.downloaded = 0
        self.total: int | None = None
        self.last_log_mark = 0
        self.description = ""

    def start(self, description: str, total: int | None = None) -> None:
        self.description = description
        self.total = total
        self.logger.info("Starting download: %s", description)

    def update(self, delta: int) -> None:
        self.downloaded += delta
        if self.downloaded - self.last_log_mark >= self.log_every_bytes:
            self.last_log_mark = self.downloaded
            if self.total and self.total > 0:
                pct = (self.downloaded / self.total) * 100.0
                self.logger.info(
                    "Download progress: %s / %s (%.1f%%)",
                    U.human_bytes(self.downloaded),
                    U.human_bytes(self.total),
                    pct,
                )
            else:
                self.logger.info("Download progress: %s", U.human_bytes(self.downloaded))

    def finish(self) -> None:
        if self.total and self.total > 0:
            pct = (self.downloaded / self.total) * 100.0
            self.logger.info(
                "Download completed: %s (%s / %s, %.1f%%)",
                self.description,
                U.human_bytes(self.downloaded),
                U.human_bytes(self.total),
                pct,
            )
        else:
            self.logger.info("Download completed: %s (%s)", self.description, U.human_bytes(self.downloaded))


class NoopProgressReporter(ProgressReporter):
    """No-op progress reporter (silent)."""

    def start(self, description: str, total: int | None = None) -> None:
        pass

    def update(self, delta: int) -> None:
        pass

    def finish(self) -> None:
        pass


# Progress Reporter Factory
def create_progress_reporter(
    options: Any,  # HTTPDownloadOptions from main module
    file_name: str,
    logger: logging.Logger,
) -> ProgressReporter:
    """
    Create appropriate progress reporter based on options and environment.

    Strategy:
    1. If show_progress=False → NoopProgressReporter
    2. If Rich available + TTY → RichProgressReporter (unless simple_progress forced)
    3. If TTY (no Rich) → SimpleProgressReporter
    4. Fallback → LoggingProgressReporter
    """
    if not getattr(options, "show_progress", True):
        return NoopProgressReporter()

    # If user explicitly asked for simple progress, honor that first.
    if getattr(options, "simple_progress", False) and _is_tty():
        return SimpleProgressReporter(file_name)

    if RICH_AVAILABLE and Progress and _is_tty():
        con = _console()
        if con:
            return RichProgressReporter(con, getattr(options, "progress_refresh_hz", 10.0))

    if _is_tty():
        return SimpleProgressReporter(file_name)

    return LoggingProgressReporter(logger, getattr(options, "log_every_bytes", 128 * 1024 * 1024))
