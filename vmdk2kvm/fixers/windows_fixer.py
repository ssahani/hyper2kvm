# SPDX-License-Identifier: LGPL-3.0-or-later
# vmdk2kvm/fixers/windows_fixer.py
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Thin façade for Windows fixing.

This module intentionally stays small and delegates the heavy lifting to:
  - windows_virtio.py     (driver discovery + injection + staging + BCD backup hints)
  - windows_registry.py   (offline hive edits: SYSTEM services/CDD + SOFTWARE DevicePath)

"""

import logging
from typing import Any, Dict

import guestfs  # type: ignore

from .windows_virtio import (
    inject_virtio_drivers,
    is_windows,
    windows_bcd_actual_fix,
)


def _safe_logger(self) -> logging.Logger:
    lg = getattr(self, "logger", None)
    if isinstance(lg, logging.Logger):
        return lg
    return logging.getLogger("vmdk2kvm.windows_fixer")


class WindowsFixer:
    """
    Optional OO wrapper for callers that expect a fixer object.

    This class is intentionally minimal: it forwards to the module-level functions
    implemented in windows_virtio.py (and indirectly windows_registry.py).
    """

    def __init__(self, **kwargs: Any):
        # Allow ad-hoc construction in tests; callers can also set attributes after init.
        # Typical attributes used by the implementation:
        #   logger, dry_run, virtio_drivers_dir, force_virtio_overwrite, export_report,
        #   enable_virtio_gpu, enable_virtio_input, enable_virtio_fs, enable_virtio_serial, enable_virtio_rng,
        #   inspect_root
        for k, v in kwargs.items():
            setattr(self, k, v)

    def is_windows(self, g: guestfs.GuestFS) -> bool:
        return is_windows(self, g)

    def windows_bcd_actual_fix(self, g: guestfs.GuestFS) -> Dict[str, Any]:
        return windows_bcd_actual_fix(self, g)

    def inject_virtio_drivers(self, g: guestfs.GuestFS) -> Dict[str, Any]:
        return inject_virtio_drivers(self, g)


__all__ = [
    "WindowsFixer",
    "is_windows",
    "windows_bcd_actual_fix",
    "inject_virtio_drivers",
]
