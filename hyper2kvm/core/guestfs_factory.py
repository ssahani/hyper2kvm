# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/guestfs_factory.py
"""
Factory for creating GuestFS instances with backend selection.

Supports:
- 'auto': Try libguestfs first, fall back to native
- 'libguestfs': Force libguestfs (raise if unavailable)
- 'native': Force native implementation
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
            - 'auto': Try libguestfs, fall back to native (default)
            - 'libguestfs': Force libguestfs (raise if unavailable)
            - 'native': Force native implementation
            - None: Same as 'auto'

    Returns:
        GuestFS instance (either guestfs.GuestFS or NativeGuestFS)

    Raises:
        RuntimeError: If requested backend is unavailable
        ImportError: If libguestfs backend requested but not available

    Environment Variables:
        HYPER2KVM_GUESTFS_BACKEND: Override backend selection (auto, libguestfs, native)

    Examples:
        # Auto-select (tries libguestfs, falls back to native)
        g = create_guestfs()

        # Force native
        g = create_guestfs(backend='native')

        # Force libguestfs
        g = create_guestfs(backend='libguestfs')
    """
    # Check environment variable override
    env_backend = os.environ.get('HYPER2KVM_GUESTFS_BACKEND')
    if env_backend:
        backend = env_backend.lower()

    # Default to 'native' (we're dropping libguestfs dependency)
    if backend is None:
        backend = 'native'

    backend = backend.lower()

    # Validate backend
    if backend not in ('auto', 'libguestfs', 'native'):
        raise ValueError(f"Invalid backend: {backend}. Must be 'auto', 'libguestfs', or 'native'")

    # Try libguestfs backend
    if backend == 'libguestfs':
        if not LIBGUESTFS_AVAILABLE:
            raise ImportError(
                "libguestfs backend requested but not available. "
                "Install python3-guestfs or use backend='native'"
            )
        return guestfs.GuestFS(python_return_dict=python_return_dict)

    # Try auto (libguestfs first, then native)
    if backend == 'auto':
        if LIBGUESTFS_AVAILABLE:
            return guestfs.GuestFS(python_return_dict=python_return_dict)
        # Fall back to native
        from .native_guestfs import NativeGuestFS
        return NativeGuestFS(python_return_dict=python_return_dict)

    # Native backend
    if backend == 'native':
        from .native_guestfs import NativeGuestFS
        return NativeGuestFS(python_return_dict=python_return_dict)

    # Should not reach here
    raise RuntimeError(f"Unexpected backend: {backend}")
