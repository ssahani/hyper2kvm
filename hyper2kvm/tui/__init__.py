# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/__init__.py
"""
Terminal User Interface (TUI) components for hyper2kvm.

Provides real-time monitoring dashboard for VM migrations with automatic fallback:
1. Textual (best) - Feature-rich TUI with full interactivity
2. Curses (good) - Built-in TUI with basic functionality
3. CLI (basic) - Simple terminal output (works everywhere including Windows)
"""

import sys
from ..core.optional_imports import TEXTUAL_AVAILABLE

__all__ = ["TEXTUAL_AVAILABLE", "run_dashboard", "get_dashboard_type"]

# Check for curses availability (not available on Windows by default)
CURSES_AVAILABLE = False
try:
    import curses
    CURSES_AVAILABLE = True
except ImportError:
    pass


def get_dashboard_type() -> str:
    """
    Get the type of dashboard that will be used.

    Returns:
        str: 'textual', 'curses', or 'cli'
    """
    if TEXTUAL_AVAILABLE:
        return 'textual'
    elif CURSES_AVAILABLE:
        return 'curses'
    else:
        return 'cli'


def run_dashboard(refresh_interval: float = 1.0) -> None:
    """
    Run the migration dashboard with automatic fallback.

    This function automatically selects the best available TUI implementation:
    1. Textual (if installed) - Full-featured modern TUI
    2. Curses (if available) - Basic TUI using stdlib
    3. CLI (always available) - Simple terminal output

    Args:
        refresh_interval: How often to refresh display (seconds)

    Example:
        >>> from hyper2kvm.tui import run_dashboard
        >>> run_dashboard(refresh_interval=2.0)
    """
    dashboard_type = get_dashboard_type()

    if dashboard_type == 'textual':
        from .dashboard import run_dashboard as run_textual_dashboard
        print("Starting Textual dashboard (best experience)")
        run_textual_dashboard(refresh_interval)
    elif dashboard_type == 'curses':
        from .fallback_dashboard import run_curses_dashboard
        print("Starting curses dashboard (Textual not installed)")
        print("For the best experience: pip install 'hyper2kvm[tui]'")
        run_curses_dashboard(refresh_interval)
    else:
        from .cli_dashboard import run_cli_dashboard
        print("Starting CLI dashboard (basic fallback)")
        print("For a better experience: pip install 'hyper2kvm[tui]'")
        run_cli_dashboard(refresh_interval)


# Always export shared types
from .types import MigrationStatus
__all__ += ["MigrationStatus"]

# Export appropriate widgets based on availability
if TEXTUAL_AVAILABLE:
    from .dashboard import MigrationDashboard
    from .widgets import MigrationStatusWidget, MetricsWidget

    __all__ += ["MigrationDashboard", "MigrationStatusWidget", "MetricsWidget"]
else:
    # Export fallback classes
    if CURSES_AVAILABLE:
        from .fallback_dashboard import CursesDashboard
        __all__ += ["CursesDashboard"]
    else:
        from .cli_dashboard import CLIDashboard
        __all__ += ["CLIDashboard"]
