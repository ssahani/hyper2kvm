# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/windows/virtio/utils.py
# -*- coding: utf-8 -*-
"""Shared utility functions for Windows VirtIO driver injection"""

from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

import guestfs  # type: ignore

# Import shared logging utilities (use directly, no wrappers)
from ....core.logging_utils import safe_logger as _safe_logger_base, emoji_for_level as _emoji, log_with_emoji as _log, log_step as _step
# Import shared guest utilities (use directly, no wrappers)
from ....core.guest_utils import guest_mkdir_p as _guest_mkdir_p, guest_write_text as _guest_write_text, deep_merge_dict as _deep_merge_dict


# Logging helpers

def _safe_logger(self) -> logging.Logger:
    """Get logger from instance or create default for windows_virtio modules."""
    return _safe_logger_base(self, "hyper2kvm.windows_virtio")


# Misc helpers

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
