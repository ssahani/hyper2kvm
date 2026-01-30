# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/azure/__init__.py
"""Azure VM migration module for hyper2kvm."""

from __future__ import annotations

from .models import AzureConfig
from .source import AzureSourceProvider

__all__ = ["AzureConfig", "AzureSourceProvider"]
