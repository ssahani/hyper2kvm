# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/vmcraft/__init__.py
"""
VMCraft: Python library for VM disk image manipulation.

Drop-in replacement for libguestfs that uses:
- qemu-nbd for disk image access
- Native Linux tools (mount, lvm, cryptsetup, etc.)
- Python file I/O for guest filesystem operations

This module provides a modular, maintainable architecture while preserving
complete backward compatibility with the original monolithic implementation.
"""

# Export main VMCraft class for backward compatibility
from .main import VMCraft

# Export custom exception classes
from ._utils import (
    VMCraftError,
    MountError,
    DeviceError,
    FileSystemError,
    RegistryError,
    DetectionError,
    CacheError,
)

# Export specialized modules (for advanced usage)
from .windows_users import WindowsUserManager
from .linux_services import LinuxServiceManager

__all__ = [
    # Main API
    "VMCraft",
    # Exception classes
    "VMCraftError",
    "MountError",
    "DeviceError",
    "FileSystemError",
    "RegistryError",
    "DetectionError",
    "CacheError",
    # Specialized modules
    "WindowsUserManager",
    "LinuxServiceManager",
]
