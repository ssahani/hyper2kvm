# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
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
from typing import Any, Optional, TYPE_CHECKING

# Import from sibling module
from ..core.utils import U

if TYPE_CHECKING:
    from dataclasses import dataclass

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


# --------------------------------------------------------------------------------------
# Helper Functions
# --------------------------------------------------------------------------------------
def _is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _console() -> Optional[Any]:
    if not (RICH_AVAILABLE and Console and _is_tty()):
        return None
    try:
        return Console(stderr=False)
    except Exception:
        return None


# --------------------------------------------------------------------------------------
# Progress Reporter Interface (Strategy Pattern)
# --------------------------------------------------------------------------------------
class ProgressReporter(ABC):
    """Abstract base class for progress reporters."""

    @abstractmethod
    def start(self, description: str, total: Optional[int] = None) -> None:
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
        self.progress: Optional[Any] = None
        self.task_id: Optional[int] = None

    def start(self, description: str, total: Optional[int] = None) -> None:
        self.progress = Progress(
            SpinnerColumn(style="bright_green"),
            TextColumn("[progress.description]{task.description}", style="bold cyan"),
            BarColumn(
                complete_style="bright_blue",
                finished_style="bright_green",
                pulse_style="magenta",
            ),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(style="yellow"),
            TimeElapsedColumn(style="dim green"),
            console=self.console,
            transient=False,  # Keep progress bar visible after completion
            refresh_per_second=max(1, int(self.refresh_hz)),
        )
        self.progress.start()
        self.task_id = self.progress.add_task(description, total=total if total and total > 0 else None)

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
        self.total: Optional[int] = None

    def start(self, description: str, total: Optional[int] = None) -> None:
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
        sys.stdout.write(f"Downloading {self.file_name}: {s}   \r")
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
        self.total: Optional[int] = None
        self.last_log_mark = 0

    def start(self, description: str, total: Optional[int] = None) -> None:
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
        self.logger.info("Download completed: %s", U.human_bytes(self.downloaded))


class NoopProgressReporter(ProgressReporter):
    """No-op progress reporter (silent)."""

    def start(self, description: str, total: Optional[int] = None) -> None:
        pass

    def update(self, delta: int) -> None:
        pass

    def finish(self) -> None:
        pass


# --------------------------------------------------------------------------------------
# Progress Reporter Factory
# --------------------------------------------------------------------------------------
def create_progress_reporter(
    options: Any,  # HTTPDownloadOptions from main module
    file_name: str,
    logger: logging.Logger,
) -> ProgressReporter:
    """
    Create appropriate progress reporter based on options and environment.

    Strategy:
    1. If show_progress=False → NoopProgressReporter
    2. If Rich available + TTY → RichProgressReporter
    3. If TTY (no Rich) → SimpleProgressReporter
    4. Fallback → LoggingProgressReporter

    Args:
        options: HTTPDownloadOptions with progress configuration
        file_name: Name of file being downloaded
        logger: Logger for LoggingProgressReporter

    Returns:
        ProgressReporter instance
    """
    if not options.show_progress:
        return NoopProgressReporter()

    if RICH_AVAILABLE and Progress and _is_tty():
        con = _console()
        if con:
            return RichProgressReporter(con, options.progress_refresh_hz)

    if options.simple_progress and _is_tty():
        return SimpleProgressReporter(file_name)

    return LoggingProgressReporter(logger, options.log_every_bytes)
