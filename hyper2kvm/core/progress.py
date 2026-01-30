# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/progress.py
"""
Custom progress bars with orange theme fallback for when Rich is not available.

This module provides progress bar functionality that works with or without Rich,
maintaining the orange theme across both implementations.
"""

from __future__ import annotations

import sys
import time
from typing import Optional, IO
from dataclasses import dataclass

from .optional_imports import RICH_AVAILABLE


# ANSI color codes for orange theme
class Colors:
    """ANSI color codes for orange theme."""

    # Orange theme colors
    BRIGHT_ORANGE = "\033[38;5;208m"  # Bright orange
    GOLD_ORANGE = "\033[38;5;214m"  # Gold-orange
    LIGHT_ORANGE = "\033[38;5;216m"  # Light orange
    DARK_ORANGE = "\033[38;5;130m"  # Dark orange

    # Status colors
    SUCCESS_GREEN = "\033[38;5;46m"  # Bright green
    ERROR_RED = "\033[38;5;196m"  # Bright red
    WARNING_YELLOW = "\033[38;5;226m"  # Bright yellow

    # Text styles
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    # Backgrounds
    BG_DARK = "\033[48;5;52m"  # Dark orange-brown background

    @classmethod
    def supports_color(cls) -> bool:
        """Check if terminal supports ANSI colors."""
        # Check if stdout is a TTY and not being piped
        if not hasattr(sys.stdout, "isatty"):
            return False
        if not sys.stdout.isatty():
            return False
        # Windows check - only Windows 10+ supports ANSI properly
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                kernel32 = ctypes.windll.kernel32

                # Get stdout handle
                h_stdout = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
                if h_stdout == -1 or h_stdout == 0:
                    return False  # Invalid handle

                # Check if it's actually a console (not redirected to file)
                console_mode = wintypes.DWORD()
                if not kernel32.GetConsoleMode(h_stdout, ctypes.byref(console_mode)):
                    # Not a console (redirected), ANSI codes won't work
                    return False

                # Enable VT100 processing (ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004)
                ENABLE_VT100 = 0x0004
                new_mode = console_mode.value | ENABLE_VT100

                if not kernel32.SetConsoleMode(h_stdout, new_mode):
                    # Failed to enable VT100 (old Windows)
                    return False

                return True
            except Exception:
                return False
        return True


@dataclass
class ProgressBarConfig:
    """Configuration for progress bar appearance."""

    width: int = 40
    filled_char: str = "█"
    empty_char: str = "░"
    left_bracket: str = "["
    right_bracket: str = "]"
    show_percentage: bool = True
    show_spinner: bool = False
    show_eta: bool = False
    color_enabled: bool = True


class SimpleProgressBar:
    """
    Simple progress bar with orange theme (Rich fallback).

    This provides a basic progress bar that works without Rich,
    using ANSI colors to maintain the orange theme.
    """

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(
        self,
        total: float = 100.0,
        description: str = "",
        config: Optional[ProgressBarConfig] = None,
        file: IO = sys.stdout,
    ):
        """
        Initialize progress bar.

        Args:
            total: Total value for 100% completion
            description: Description text to show
            config: Progress bar configuration
            file: Output file (default: stdout)

        Note:
            If total <= 0, it will be reset to 100.0 with a warning
        """
        # Use property setter for validation
        self._total = 100.0  # Default
        self.total = total  # Will validate via property setter
        self.current = 0.0
        self.description = description
        self.config = config or ProgressBarConfig()
        self.file = file
        self.start_time = time.monotonic()  # Use monotonic clock to prevent negative elapsed time
        self.spinner_index = 0
        self._use_color = self.config.color_enabled and Colors.supports_color()

    @property
    def total(self) -> float:
        """Get total value."""
        return self._total

    @total.setter
    def total(self, value: float) -> None:
        """Set total value with validation to prevent division by zero."""
        if value <= 0:
            import logging
            logging.warning(f"Invalid total value {value}, using 100.0")
            value = 100.0
        self._total = value

    def update(self, current: float, description: Optional[str] = None) -> None:
        """
        Update progress bar.

        Args:
            current: Current progress value
            description: Optional new description
        """
        # Clamp current to valid range [0, total]
        self.current = max(0.0, min(current, self.total))
        if description:
            self.description = description
        self._render()

    def advance(self, amount: float = 1.0) -> None:
        """
        Advance progress by amount.

        Args:
            amount: Amount to advance
        """
        self.update(self.current + amount)

    def _render(self) -> None:
        """Render the progress bar."""
        # Calculate progress
        if self.total > 0:
            progress = self.current / self.total
        else:
            progress = 0.0

        progress = min(1.0, max(0.0, progress))

        # Build progress bar
        filled_width = int(progress * self.config.width)
        empty_width = self.config.width - filled_width

        # Create bar with orange theme
        if self._use_color:
            filled = f"{Colors.BRIGHT_ORANGE}{self.config.filled_char * filled_width}{Colors.RESET}"
            empty = f"{Colors.DIM}{self.config.empty_char * empty_width}{Colors.RESET}"
            bracket_color = Colors.GOLD_ORANGE
            desc_color = Colors.LIGHT_ORANGE
        else:
            filled = self.config.filled_char * filled_width
            empty = self.config.empty_char * empty_width
            bracket_color = ""
            desc_color = ""

        bar = f"{bracket_color}{self.config.left_bracket}{Colors.RESET if self._use_color else ''}"
        bar += filled + empty
        bar += f"{bracket_color}{self.config.right_bracket}{Colors.RESET if self._use_color else ''}"

        # Add percentage
        percentage_str = ""
        if self.config.show_percentage:
            pct = int(progress * 100)
            if self._use_color:
                percentage_str = f" {Colors.BOLD}{Colors.BRIGHT_ORANGE}{pct:3d}%{Colors.RESET}"
            else:
                percentage_str = f" {pct:3d}%"

        # Add spinner
        spinner_str = ""
        if self.config.show_spinner and progress < 1.0:
            spinner = self.SPINNER_FRAMES[self.spinner_index % len(self.SPINNER_FRAMES)]
            self.spinner_index += 1
            if self._use_color:
                spinner_str = f" {Colors.GOLD_ORANGE}{spinner}{Colors.RESET}"
            else:
                spinner_str = f" {spinner}"

        # Add ETA
        eta_str = ""
        if self.config.show_eta and progress > 0 and progress < 1.0:
            elapsed = time.monotonic() - self.start_time  # Use monotonic to prevent negative time
            if elapsed > 1.0:  # Only show ETA after 1 second to avoid huge estimates
                estimated_total = elapsed / progress
                eta_seconds = max(0, estimated_total - elapsed)
                # Cap ETA at reasonable maximum (7 days)
                eta_seconds = min(eta_seconds, 86400 * 7)

                if eta_seconds > 0:
                    eta_str = self._format_duration(eta_seconds)
                    if self._use_color:
                        eta_str = f" {Colors.DIM}ETA: {eta_str}{Colors.RESET}"
                    else:
                        eta_str = f" ETA: {eta_str}"

        # Build final output
        output = ""
        if self.description:
            if self._use_color:
                output = f"{desc_color}{self.description}{Colors.RESET} "
            else:
                output = f"{self.description} "

        output += bar + percentage_str + spinner_str + eta_str

        # Write output (overwrite previous line)
        self.file.write(f"\r{output}")
        self.file.flush()

    def finish(self, message: Optional[str] = None) -> None:
        """
        Finish progress bar and move to new line.

        Args:
            message: Optional completion message
        """
        self.update(self.total)
        if message:
            if self._use_color:
                self.file.write(f" {Colors.SUCCESS_GREEN}✓ {message}{Colors.RESET}")
            else:
                self.file.write(f" ✓ {message}")
        self.file.write("\n")
        self.file.flush()

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


class ProgressManager:
    """
    Progress manager that uses Rich if available, otherwise uses SimpleProgressBar.

    This provides a unified interface that automatically uses Rich for the best
    experience when available, or falls back to SimpleProgressBar.
    """

    def __init__(self, description: str = "", total: float = 100.0):
        """
        Initialize progress manager.

        Args:
            description: Progress description
            total: Total value for 100% completion
        """
        self.description = description
        self.total = total
        self._use_rich = RICH_AVAILABLE

        if self._use_rich:
            from .optional_imports import (
                Progress,
                BarColumn,
                TextColumn,
                TimeRemainingColumn,
                SpinnerColumn,
            )

            # Create Rich progress with orange theme
            self._rich_progress = Progress(
                SpinnerColumn(style="bold bright_white"),
                TextColumn("[bold #ff6600]{task.description}"),
                BarColumn(
                    complete_style="bold #ff6600",
                    finished_style="bold #66ff66",
                    bar_width=40,
                ),
                TextColumn("[bold #ffaa44]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
            )
            self._rich_task = None
        else:
            # Use simple progress bar with orange theme
            config = ProgressBarConfig(
                width=40,
                show_percentage=True,
                show_spinner=True,
                show_eta=True,
            )
            self._simple_progress = SimpleProgressBar(
                total=total,
                description=description,
                config=config,
            )

    def __enter__(self):
        """Enter context manager."""
        if self._use_rich:
            self._rich_progress.__enter__()
            self._rich_task = self._rich_progress.add_task(
                self.description,
                total=self.total,
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        try:
            if self._use_rich:
                self._rich_progress.__exit__(exc_type, exc_val, exc_tb)
            else:
                self._simple_progress.finish()
        except Exception as e:
            # Log but don't suppress the original exception
            import logging
            logging.error(f"Error cleaning up progress bar: {e}")
            # Return None to propagate the original exception if any

    def update(self, current: float, description: Optional[str] = None):
        """
        Update progress.

        Args:
            current: Current progress value
            description: Optional new description
        """
        if self._use_rich and self._rich_task is not None:
            kwargs = {"completed": current}
            if description:
                kwargs["description"] = description
            self._rich_progress.update(self._rich_task, **kwargs)
        else:
            self._simple_progress.update(current, description)

    def advance(self, amount: float = 1.0):
        """
        Advance progress by amount.

        Args:
            amount: Amount to advance
        """
        if self._use_rich and self._rich_task is not None:
            self._rich_progress.update(self._rich_task, advance=amount)
        else:
            self._simple_progress.advance(amount)


# Convenience function for simple usage
def create_progress_bar(
    description: str = "",
    total: float = 100.0,
    use_rich: Optional[bool] = None,
) -> ProgressManager:
    """
    Create a progress bar with orange theme.

    Args:
        description: Progress description
        total: Total value for 100% completion
        use_rich: Force Rich usage (None = auto-detect)

    Returns:
        ProgressManager instance

    Example:
        >>> with create_progress_bar("Migrating VM", total=100) as progress:
        ...     for i in range(100):
        ...         progress.update(i + 1)
        ...         time.sleep(0.1)
    """
    return ProgressManager(description=description, total=total)
