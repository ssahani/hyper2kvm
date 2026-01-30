# SPDX-License-Identifier: LGPL-3.0-or-later
"""Libvirt integration for hyper2kvm.

This package provides libvirt domain and storage pool management capabilities
for automatic VM import and lifecycle operations after conversion.
"""

from __future__ import annotations

# Import utilities
from .libvirt_utils import (
    default_libvirt_images_dir,
    default_libvirt_nvram_dir,
    sanitize_name,
)

# Import managers (may not be available if libvirt not installed)
try:
    from .libvirt_manager import LIBVIRT_AVAILABLE, LibvirtManager, LibvirtManagerError
    from .pool_manager import PoolManager, PoolManagerError
except ImportError:
    LIBVIRT_AVAILABLE = False  # type: ignore
    LibvirtManager = None  # type: ignore
    LibvirtManagerError = None  # type: ignore
    PoolManager = None  # type: ignore
    PoolManagerError = None  # type: ignore

__all__ = [
    # Utilities
    "sanitize_name",
    "default_libvirt_images_dir",
    "default_libvirt_nvram_dir",
    # Managers
    "LibvirtManager",
    "LibvirtManagerError",
    "PoolManager",
    "PoolManagerError",
    "LIBVIRT_AVAILABLE",
]
