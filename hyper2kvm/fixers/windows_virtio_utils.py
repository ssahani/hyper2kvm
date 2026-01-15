# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/windows_virtio_utils.py
# -*- coding: utf-8 -*-
"""Shared utility functions for Windows VirtIO driver injection"""

from __future__ import annotations

import hashlib
import logging
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional

import guestfs  # type: ignore

# Import shared logging utilities
from ..core.logging_utils import safe_logger, emoji_for_level, log_with_emoji, log_step
# Import shared guest utilities
from ..core.guest_utils import guest_mkdir_p, guest_write_text, deep_merge_dict


# ---------------------------
# Logging helpers (wrappers for shared utilities)
# ---------------------------

def _safe_logger(self) -> logging.Logger:
    """Get logger from instance or create default."""
    return safe_logger(self, "hyper2kvm.windows_virtio")


def _emoji(level: int) -> str:
    """Return emoji for log level."""
    return emoji_for_level(level)


def _log(logger: logging.Logger, level: int, msg: str, *args: Any) -> None:
    """Log with emoji prefix."""
    log_with_emoji(logger, level, msg, *args)


def _step(logger: logging.Logger, title: str):
    """Context manager for logging and timing operation steps."""
    return log_step(logger, title)


# ---------------------------
# Misc helpers
# ---------------------------

def _is_probably_driver_payload(p: Path) -> bool:
    """Check if a file is likely a driver payload file.

    Args:
        p: Path to check

    Returns:
        True if the file extension indicates a driver payload file

    Note:
        Checks for .inf, .cat, .sys, .dll, .mui extensions.
    """
    ext = p.suffix.lower()
    return ext in (".inf", ".cat", ".sys", ".dll", ".mui")


def _to_int(v: Any, default: int = 0) -> int:
    if isinstance(v, int):
        return v
    try:
        return int(float(v)) if isinstance(v, (float, str)) else default
    except Exception:
        return default


def _normalize_product_name(name: str) -> str:
    import re
    if not name:
        return ""
    s = name.lower()
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _guest_download_bytes(g: guestfs.GuestFS, guest_path: str, max_bytes: Optional[int] = None) -> bytes:
    with tempfile.TemporaryDirectory() as td:
        lp = Path(td) / "dl"
        g.download(guest_path, str(lp))
        b = lp.read_bytes()
        return b[:max_bytes] if max_bytes is not None else b


def _guest_sha256(g: guestfs.GuestFS, guest_path: str) -> Optional[str]:
    try:
        return hashlib.sha256(_guest_download_bytes(g, guest_path)).hexdigest()
    except Exception:
        return None


def _sha256_path(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _log_mountpoints_best_effort(logger: logging.Logger, g: guestfs.GuestFS) -> None:
    try:
        mps = g.mountpoints()
        _log(logger, logging.DEBUG, "guestfs mountpoints=%r", mps)
    except Exception:
        pass


def _guest_mkdir_p(g: guestfs.GuestFS, path: str, *, dry_run: bool) -> None:
    """Wrapper for backward compatibility - calls shared guest_mkdir_p."""
    return guest_mkdir_p(g, path, dry_run=dry_run)


def _guest_write_text(g: guestfs.GuestFS, path: str, content: str, *, dry_run: bool) -> None:
    """Wrapper for backward compatibility - calls shared guest_write_text."""
    return guest_write_text(g, path, content, dry_run=dry_run)


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Wrapper for backward compatibility - calls shared deep_merge_dict."""
    return deep_merge_dict(base, override)
