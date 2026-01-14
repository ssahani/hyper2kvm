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


# ---------------------------
# Logging helpers (emoji + steps)
# ---------------------------

def _safe_logger(self) -> logging.Logger:
    lg = getattr(self, "logger", None)
    if isinstance(lg, logging.Logger):
        return lg
    return logging.getLogger("hyper2kvm.windows_virtio")


def _emoji(level: int) -> str:
    if level >= logging.ERROR:
        return "❌"
    if level >= logging.WARNING:
        return "⚠️"
    if level >= logging.INFO:
        return "✅"
    return "🔍"


def _log(logger: logging.Logger, level: int, msg: str, *args: Any) -> None:
    logger.log(level, f"{_emoji(level)} {msg}", *args)


@contextmanager
def _step(logger: logging.Logger, title: str):
    t0 = time.time()
    _log(logger, logging.INFO, "%s ...", title)
    try:
        yield
        _log(logger, logging.INFO, "%s done (%.2fs)", title, time.time() - t0)
    except Exception as e:
        _log(logger, logging.ERROR, "%s failed (%.2fs): %s", title, time.time() - t0, e)
        raise


# ---------------------------
# Misc helpers
# ---------------------------

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
    if dry_run:
        return
    try:
        if not g.is_dir(path):
            g.mkdir_p(path)
    except Exception:
        g.mkdir_p(path)


def _guest_write_text(g: guestfs.GuestFS, path: str, content: str, *, dry_run: bool) -> None:
    if dry_run:
        return
    g.write(path, content.encode("utf-8", errors="ignore"))


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge dicts:
      - dict values merge recursively
      - lists are replaced (override wins)
      - scalars replaced
    """
    out: Dict[str, Any] = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge_dict(out[k], v)
        else:
            out[k] = v
    return out
