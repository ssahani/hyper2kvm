# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# hyper2kvm/fixers/windows/registry/mount.py
"""
Windows filesystem mount and validation.

CRITICAL: Ensures guestfs / is mapped to Windows C: drive before registry operations.
"""
from __future__ import annotations

import logging
from typing import List, Optional

import guestfs  # type: ignore

from .io import _log_mountpoints_best_effort


def _win_expected_paths() -> List[str]:
    """Expected paths on a Windows system volume."""
    return [
        "/Windows/System32/config/SYSTEM",
        "/Windows/System32/config/SOFTWARE",
        "/Windows/System32/cmd.exe",
    ]


def _guest_path_join(*parts: str) -> str:
    """Join path components for guest filesystem."""
    out = ""
    for p in parts:
        if not p:
            continue
        if not out:
            out = p
            continue
        out = out.rstrip("/") + "/" + p.lstrip("/")
    return out or "/"


def _looks_like_windows_root(g: guestfs.GuestFS) -> bool:
    """Check if current / looks like Windows C: drive."""
    for p in _win_expected_paths():
        try:
            if not g.is_file(p):
                return False
        except Exception:
            return False
    return True


def _mount_inspected_os_best_effort(logger: logging.Logger, g: guestfs.GuestFS) -> bool:
    """
    Canonical libguestfs mount recipe:
      roots = inspect_os()
      mps = inspect_get_mountpoints(root)
      mount in descending mountpoint-length order
    """
    try:
        roots = g.inspect_os()
    except Exception as e:
        logger.warning("inspect_os failed: %s", e)
        return False

    if not roots:
        logger.warning("inspect_os returned no roots")
        return False

    root = roots[0]
    try:
        mps = g.inspect_get_mountpoints(root)
    except Exception as e:
        logger.warning("inspect_get_mountpoints failed: %s", e)
        return False

    mps_sorted = sorted(mps, key=lambda x: len(x[0] or ""), reverse=True)

    try:
        g.umount_all()
    except Exception:
        pass

    for mp, dev in mps_sorted:
        try:
            g.mount(dev, mp)
            logger.debug("Mounted %s at %s", dev, mp)
        except Exception as e:
            logger.debug("Mount failed dev=%s mp=%s: %s", dev, mp, e)

    ok = False
    try:
        ok = _looks_like_windows_root(g)
    except Exception:
        ok = False

    if ok:
        logger.info("Windows root mounted correctly at / (contains /Windows/System32/config/*)")
    else:
        logger.warning("Mounted OS does not look like Windows at / (missing expected paths)")
    return ok


def _ensure_windows_root(logger: logging.Logger, g: guestfs.GuestFS, *, hint_hive_path: Optional[str] = None) -> None:
    """
    Ensure / is the Windows system volume (C: at runtime).

    Strategy:
      1) If / already looks like Windows and (optional) hint exists, accept.
      2) Otherwise, remount using inspect_os and require expected paths.
    """
    _log_mountpoints_best_effort(logger, g)

    looks = False
    try:
        looks = _looks_like_windows_root(g)
    except Exception:
        looks = False

    if looks:
        if hint_hive_path:
            try:
                if g.is_file(hint_hive_path):
                    return
            except Exception:
                pass
        else:
            return

    if _mount_inspected_os_best_effort(logger, g):
        if hint_hive_path:
            try:
                if g.is_file(hint_hive_path):
                    return
            except Exception:
                pass
        else:
            return

    try:
        fs = g.list_filesystems()
        logger.debug("list_filesystems=%r", fs)
    except Exception:
        pass
    raise RuntimeError("Unable to ensure Windows system volume is mounted at / (C: mapping uncertain)")
