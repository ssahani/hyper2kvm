# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/types.py
"""
Shared type definitions for TUI components.

This module provides common types used across all TUI implementations,
avoiding code duplication and ensuring consistency.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class MigrationStatus:
    """
    Status of a single VM migration.

    This dataclass is used across all TUI implementations (Textual, Curses, CLI)
    to track the state of VM migrations.
    """

    vm_name: str
    hypervisor: str
    status: str  # 'pending', 'in_progress', 'completed', 'failed'
    progress: float  # 0.0 to 1.0
    current_stage: str  # 'export', 'convert', 'validate', etc.
    throughput_mbps: float = 0.0
    elapsed_seconds: float = 0.0
    eta_seconds: Optional[float] = None
    error: Optional[str] = None


# Shared constants
MAX_LOG_ENTRIES = 1000  # Maximum number of log entries to keep
MAX_LOG_ENTRIES_CLI = 100  # Maximum for CLI (more constrained)
DEFAULT_REFRESH_INTERVAL = 1.0  # Default refresh interval in seconds
CLI_REFRESH_INTERVAL = 2.0  # CLI uses slower refresh to reduce flicker
