# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/optional_imports.py
"""
Centralized optional imports to eliminate duplicate import guards.

This module provides a single location for optional dependencies, eliminating
the need for try/except import blocks scattered across 20+ files.
"""

from __future__ import annotations

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

# httpx library (Async HTTP client)
try:
    import httpx
    from httpx import AsyncClient, Limits, Timeout

    HTTPX_AVAILABLE = True
except Exception:
    httpx = None  # type: ignore
    AsyncClient = None  # type: ignore
    Limits = None  # type: ignore
    Timeout = None  # type: ignore
    HTTPX_AVAILABLE = False

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

# Pydantic (configuration validation)
try:
    from pydantic import BaseModel, Field, field_validator, ConfigDict, ValidationError
    from pydantic_settings import BaseSettings, SettingsConfigDict

    PYDANTIC_AVAILABLE = True
except Exception:
    BaseModel = None  # type: ignore
    Field = None  # type: ignore
    field_validator = None  # type: ignore
    ConfigDict = None  # type: ignore
    ValidationError = None  # type: ignore
    BaseSettings = None  # type: ignore
    SettingsConfigDict = None  # type: ignore
    PYDANTIC_AVAILABLE = False

# Tenacity (advanced retry logic)
try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        wait_fixed,
        retry_if_exception_type,
        before_sleep_log,
        after_log,
        RetryError,
    )

    TENACITY_AVAILABLE = True
except Exception:
    retry = None  # type: ignore
    stop_after_attempt = None  # type: ignore
    wait_exponential = None  # type: ignore
    wait_fixed = None  # type: ignore
    retry_if_exception_type = None  # type: ignore
    before_sleep_log = None  # type: ignore
    after_log = None  # type: ignore
    RetryError = None  # type: ignore
    TENACITY_AVAILABLE = False

# Watchdog (file system monitoring for daemon mode)
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent

    WATCHDOG_AVAILABLE = True
except Exception:
    Observer = None  # type: ignore
    FileSystemEventHandler = None  # type: ignore
    FileCreatedEvent = None  # type: ignore
    WATCHDOG_AVAILABLE = False

# Textual (Terminal User Interface framework)
try:
    from textual.app import App, ComposeResult
    from textual.screen import Screen
    from textual.widgets import (
        Header,
        Footer,
        Static,
        DataTable,
        Log as TextualLog,
        ProgressBar,
        Label,
        Button,
        Input,
        Select,
        Checkbox,
        RadioButton,
        RadioSet,
        DirectoryTree,
        TabbedContent,
        TabPane,
        Tabs,
        Tab,
    )
    from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
    from textual.reactive import reactive
    from textual.binding import Binding
    from textual import work
    from textual.worker import Worker

    TEXTUAL_AVAILABLE = True
except Exception:
    App = None  # type: ignore
    ComposeResult = None  # type: ignore
    Screen = None  # type: ignore
    Header = None  # type: ignore
    Footer = None  # type: ignore
    Static = None  # type: ignore
    DataTable = None  # type: ignore
    TextualLog = None  # type: ignore
    ProgressBar = None  # type: ignore
    Label = None  # type: ignore
    Button = None  # type: ignore
    Input = None  # type: ignore
    Select = None  # type: ignore
    Checkbox = None  # type: ignore
    RadioButton = None  # type: ignore
    RadioSet = None  # type: ignore
    DirectoryTree = None  # type: ignore
    TabbedContent = None  # type: ignore
    TabPane = None  # type: ignore
    Tabs = None  # type: ignore
    Tab = None  # type: ignore
    Container = None  # type: ignore
    Vertical = None  # type: ignore
    Horizontal = None  # type: ignore
    ScrollableContainer = None  # type: ignore
    reactive = None  # type: ignore
    Binding = None  # type: ignore
    work = None  # type: ignore
    Worker = None  # type: ignore
    TEXTUAL_AVAILABLE = False

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


def require_httpx() -> None:
    """Raise ImportError if httpx is not available."""
    if not HTTPX_AVAILABLE:
        raise ImportError(
            "httpx library is required but not installed. "
            "Install with: pip install httpx>=0.24.0"
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


def require_pydantic() -> None:
    """Raise ImportError if pydantic is not available."""
    if not PYDANTIC_AVAILABLE:
        raise ImportError(
            "pydantic library is required but not installed. "
            "Install with: pip install pydantic>=2.5.0 pydantic-settings>=2.1.0"
        )


def require_tenacity() -> None:
    """Raise ImportError if tenacity is not available."""
    if not TENACITY_AVAILABLE:
        raise ImportError(
            "tenacity library is required but not installed. "
            "Install with: pip install tenacity>=8.2.0"
        )


def require_watchdog() -> None:
    """Raise ImportError if watchdog is not available."""
    if not WATCHDOG_AVAILABLE:
        raise ImportError(
            "watchdog library is required but not installed. "
            "Install with: pip install watchdog>=3.0.0"
        )


def require_textual() -> None:
    """Raise ImportError if textual is not available."""
    if not TEXTUAL_AVAILABLE:
        raise ImportError(
            "textual library is required but not installed. "
            "Install with: pip install textual>=0.47.0"
        )
