# SPDX-License-Identifier: LGPL-3.0-or-later
"""Migration profiles package for hyper2kvm."""

from .profile_loader import ProfileLoadError, ProfileLoader

__all__ = ["ProfileLoader", "ProfileLoadError"]
