# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
Shared utility functions for VMware operations.

Provides common helpers to avoid duplication across VMware modules.
"""
from __future__ import annotations

import re
import sys
from typing import Any, Optional


def safe_vm_name(name: Optional[str]) -> str:
    """
    Sanitize VM name for use in filenames and paths.

    Replaces non-alphanumeric characters (except _, ., -) with underscores.
    Returns "vm" if the input is empty or None.

    Args:
        name: VM name to sanitize (can be None)

    Returns:
        Sanitized VM name safe for use in filenames

    Examples:
        >>> safe_vm_name("My VM (test)")
        'My_VM__test_'
        >>> safe_vm_name(None)
        'vm'
        >>> safe_vm_name("")
        'vm'
    """
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", (name or "vm").strip()) or "vm"


def is_tty(stream=None) -> bool:
    """
    Check if the specified stream (or stdout by default) is a TTY.

    Args:
        stream: File object to check (defaults to sys.stdout)

    Returns:
        True if stream is a TTY, False otherwise
    """
    try:
        if stream is None:
            stream = sys.stdout
        return stream.isatty()
    except Exception:
        return False


def create_console():
    """
    Create a Rich Console object for formatted output.

    Returns None if Rich is not available or not running in a TTY.

    Returns:
        Rich Console instance or None
    """
    if not is_tty():
        return None

    try:
        from rich.console import Console
        return Console(stderr=False)
    except Exception:
        return None
