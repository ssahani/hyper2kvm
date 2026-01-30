# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/guestfs_factory.py
"""
Factory for creating GuestFS instances with backend selection.

Supports:
- 'auto': Try libguestfs first, fall back to VMCraft
- 'libguestfs': Force libguestfs (raise if unavailable)
- 'vmcraft': Force VMCraft implementation (default)
"""

from __future__ import annotations

import os
from typing import Any


# Check libguestfs availability
try:
    import guestfs  # type: ignore
    LIBGUESTFS_AVAILABLE = True
except ImportError:
    LIBGUESTFS_AVAILABLE = False


def create_guestfs(
    *,
    python_return_dict: bool = True,
    backend: str | None = None,
) -> Any:
    """
    Create a GuestFS instance with backend selection.

    Args:
        python_return_dict: Return dicts instead of tuples (default: True)
        backend: Backend to use:
            - 'auto': Try libguestfs, fall back to VMCraft
            - 'libguestfs': Force libguestfs (raise if unavailable)
            - 'vmcraft': Force VMCraft implementation (default)
            - None: Defaults to 'vmcraft'

    Returns:
        GuestFS instance (either guestfs.GuestFS or VMCraft)

    Raises:
        RuntimeError: If requested backend is unavailable
        ImportError: If libguestfs backend requested but not available

    Environment Variables:
        HYPER2KVM_GUESTFS_BACKEND: Override backend selection (auto, libguestfs, vmcraft)

    Examples:
        # Use VMCraft (default)
        g = create_guestfs()

        # Explicit VMCraft
        g = create_guestfs(backend='vmcraft')

        # Force libguestfs
        g = create_guestfs(backend='libguestfs')

        # Auto-select (tries libguestfs, falls back to VMCraft)
        g = create_guestfs(backend='auto')
    """
    # Check environment variable override
    env_backend = os.environ.get('HYPER2KVM_GUESTFS_BACKEND')
    if env_backend:
        backend = env_backend.lower()

    # Default to 'vmcraft'
    if backend is None:
        backend = 'vmcraft'

    backend = backend.lower()

    # Validate backend
    if backend not in ('auto', 'libguestfs', 'vmcraft'):
        raise ValueError(f"Invalid backend: {backend}. Must be 'auto', 'libguestfs', or 'vmcraft'")

    # Try libguestfs backend
    if backend == 'libguestfs':
        if not LIBGUESTFS_AVAILABLE:
            raise ImportError(
                "libguestfs backend requested but not available. "
                "Install python3-guestfs or use backend='vmcraft'"
            )
        return guestfs.GuestFS(python_return_dict=python_return_dict)

    # Try auto (libguestfs first, then VMCraft)
    if backend == 'auto':
        if LIBGUESTFS_AVAILABLE:
            return guestfs.GuestFS(python_return_dict=python_return_dict)
        # Fall back to VMCraft
        from .vmcraft import VMCraft
        return VMCraft(python_return_dict=python_return_dict)

    # VMCraft backend
    if backend == 'vmcraft':
        from .vmcraft import VMCraft
        return VMCraft(python_return_dict=python_return_dict)

    # Should not reach here
    raise RuntimeError(f"Unexpected backend: {backend}")
