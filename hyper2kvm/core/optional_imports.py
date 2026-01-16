# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# hyper2kvm/core/optional_imports.py
"""
Centralized optional imports to eliminate duplicate import guards.

This module provides a single location for optional dependencies, eliminating
the need for try/except import blocks scattered across 20+ files.
"""

from __future__ import annotations

from typing import Any, Optional

# Rich library (progress bars, panels, console formatting)
try:
    from rich.console import Console
    from rich.panel import Panel
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
    Panel = None  # type: ignore
    Progress = None  # type: ignore
    BarColumn = None  # type: ignore
    DownloadColumn = None  # type: ignore
    SpinnerColumn = None  # type: ignore
    TextColumn = None  # type: ignore
    TimeElapsedColumn = None  # type: ignore
    TimeRemainingColumn = None  # type: ignore
    TransferSpeedColumn = None  # type: ignore
    RICH_AVAILABLE = False

# requests library (HTTP client)
try:
    import requests
    import requests.adapters

    REQUESTS_AVAILABLE = True
except Exception:
    requests = None  # type: ignore
    REQUESTS_AVAILABLE = False

# urllib3 library (HTTP utilities, TLS warnings)
try:
    import urllib3

    URLLIB3_AVAILABLE = True
except Exception:
    urllib3 = None  # type: ignore
    URLLIB3_AVAILABLE = False

# pyVmomi library (VMware vSphere API)
try:
    from pyVmomi import vim, vmodl

    PYVMOMI_AVAILABLE = True
except Exception:
    vim = None  # type: ignore
    vmodl = None  # type: ignore
    PYVMOMI_AVAILABLE = False

# paramiko library (SSH client)
try:
    import paramiko

    PARAMIKO_AVAILABLE = True
except Exception:
    paramiko = None  # type: ignore
    PARAMIKO_AVAILABLE = False

# Helper functions


def require_rich() -> None:
    """Raise ImportError if Rich is not available."""
    if not RICH_AVAILABLE:
        raise ImportError(
            "Rich library is required but not installed. "
            "Install with: pip install rich"
        )


def require_requests() -> None:
    """Raise ImportError if requests is not available."""
    if not REQUESTS_AVAILABLE:
        raise ImportError(
            "requests library is required but not installed. "
            "Install with: pip install requests"
        )


def require_pyvmomi() -> None:
    """Raise ImportError if pyVmomi is not available."""
    if not PYVMOMI_AVAILABLE:
        raise ImportError(
            "pyVmomi library is required but not installed. "
            "Install with: pip install pyvmomi"
        )


def require_paramiko() -> None:
    """Raise ImportError if paramiko is not available."""
    if not PARAMIKO_AVAILABLE:
        raise ImportError(
            "paramiko library is required but not installed. "
            "Install with: pip install paramiko"
        )
