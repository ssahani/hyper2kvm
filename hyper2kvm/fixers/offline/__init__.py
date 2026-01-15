# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/offline/__init__.py
"""
Offline fixer helper modules for VMware -> KVM migration.

This package provides helper modules for offline guest modifications:
- config_rewriter: Configuration file rewriting operations
- spec_converter: Spec conversion utilities
- validation: Post-modification validation and health checks
"""

from .config_rewriter import FstabCrypttabRewriter
from .spec_converter import SpecConverter
from .validation import OfflineValidationManager

__all__ = [
    "FstabCrypttabRewriter",
    "SpecConverter",
    "OfflineValidationManager",
]
