# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/libvirt/libvirt_utils.py
"""Shared libvirt utility functions

Provides common helpers for libvirt operations to avoid duplication across modules.
"""
from __future__ import annotations

import re
from pathlib import Path

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._+-]+")
_DEFAULT_IMAGES_DIR = Path("/var/lib/libvirt/images")
_DEFAULT_NVRAM_DIR = Path("/var/lib/libvirt/qemu/nvram")


def sanitize_name(s: str) -> str:
    """Sanitize name for libvirt-friendly identifiers and filenames.

    Args:
        s: String to sanitize

    Returns:
        Sanitized string safe for libvirt names and filenames

    Behavior:
        - Keeps: A-Za-z0-9._+-
        - Replaces everything else with '-'
        - Strips '-' from edges
        - Returns 'vm' if result is empty

    Example:
        >>> sanitize_name("My VM (test)")
        'My-VM--test-'
        >>> sanitize_name(" ")
        'vm'
        >>> sanitize_name("linux-server-01.example.com")
        'linux-server-01.example.com'
    """
    s = (s or "").strip()
    s = _SAFE_NAME_RE.sub("-", s).strip("-")
    return s or "vm"


def default_libvirt_images_dir() -> Path:
    """Return the default libvirt images directory.

    Returns:
        Path to /var/lib/libvirt/images
    """
    return _DEFAULT_IMAGES_DIR


def default_libvirt_nvram_dir() -> Path:
    """Return the default libvirt NVRAM directory.

    Returns:
        Path to /var/lib/libvirt/qemu/nvram
    """
    return _DEFAULT_NVRAM_DIR


__all__ = [
    "sanitize_name",
    "default_libvirt_images_dir",
    "default_libvirt_nvram_dir",
]
