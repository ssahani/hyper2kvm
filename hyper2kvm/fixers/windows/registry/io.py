# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# hyper2kvm/fixers/windows/registry/io.py
"""
Registry hive I/O operations - downloading and validation.

Provides robust hive download with fallback mechanisms and validation.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import guestfs  # type: ignore


def _is_probably_regf(path: Path) -> bool:
    """
    Windows registry hives start with ASCII 'regf' signature.
    Cheap corruption/truncation guardrail.
    """
    try:
        b = path.read_bytes()
        return len(b) >= 4 and b[:4] == b"regf"
    except Exception:
        return False


def _download_hive_local(logger: logging.Logger, g: guestfs.GuestFS, remote: str, local: Path) -> None:
    """
    Robustly download a hive from the guest to a local path.

    We've seen cases where g.download() does not materialize the local file
    (or produces an empty/truncated file) without raising. This helper:
      1) tries g.download()
      2) verifies local exists + size >= 4KiB + 'regf' signature
      3) falls back to g.read_file()/g.cat() and writes bytes locally
    """
    local.parent.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("Downloading hive: %r -> %r", remote, str(local))
        g.download(remote, str(local))
    except Exception as e:
        logger.warning("g.download(%r, %r) failed: %s", remote, str(local), e)

    try:
        if local.exists() and local.stat().st_size >= 4096 and _is_probably_regf(local):
            return
    except Exception:
        pass

    logger.warning("Hive not materialized after download; falling back to guestfs read: %r", remote)
    data: Optional[bytes] = None

    for fn_name in ("read_file", "cat"):
        fn = getattr(g, fn_name, None)
        if not callable(fn):
            continue
        try:
            out = fn(remote)
            if isinstance(out, (bytes, bytearray)):
                data = bytes(out)
            else:
                # guestfs bindings sometimes return str-ish
                data = str(out).encode("latin-1", errors="ignore")
            break
        except Exception as e:
            logger.warning("%s(%r) failed: %s", fn_name, remote, e)

    if not data or len(data) < 4096:
        raise RuntimeError(
            f"Failed to download hive locally: remote={remote} local={local} (len={len(data) if data else 0})"
        )

    local.write_bytes(data)

    if not local.exists() or local.stat().st_size < 4096:
        raise RuntimeError(f"Local hive still missing after fallback: {local}")

    if not _is_probably_regf(local):
        raise RuntimeError(f"Local hive downloaded but missing regf signature: {local}")


def _log_mountpoints_best_effort(logger: logging.Logger, g: guestfs.GuestFS) -> None:
    """Log current guestfs mountpoints for debugging."""
    try:
        mps = g.mountpoints()
        logger.debug("guestfs mountpoints=%r", mps)
    except Exception:
        pass
