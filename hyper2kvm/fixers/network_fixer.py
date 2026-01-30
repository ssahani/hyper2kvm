# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/network_fixer.py
"""
Comprehensive network configuration fixer for VMware -> KVM migration.

This module provides backward-compatible imports and compatibility wrappers
for the network fixer functionality, which has been refactored into focused
single-responsibility modules:

- network_discovery.py: File discovery and I/O operations
- network_topology.py: Topology building and rename planning
- network_validation.py: Configuration validation
- network_fixers_backend.py: Backend-specific fix implementations
- network_fixer_core.py: Main orchestrator

The NetworkFixer class is now imported from network_fixer_core and re-exported
here for backward compatibility with existing code.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import guestfs  # type: ignore

# Import main orchestrator (re-export for backward compatibility)
from .network_fixer_core import NetworkFixer

# Import model types for compatibility
from .network_model import FixLevel

# Re-export for backward compatibility
__all__ = ["NetworkFixer", "fix_network_config", "fix_network_config_compat"]


# -----------------------------------------------------------------------------
# Optional compatibility wrapper (for project style)
# -----------------------------------------------------------------------------


def fix_network_config(self, g: guestfs.GuestFS) -> Dict[str, Any]:
    """
    Compatibility entrypoint: call NetworkFixer directly.

    This function is designed to be called as a method on an object (like
    OfflineFixer) that has logger, network_fix_level, dry_run, and report
    attributes.

    Args:
        self: Object with logger, network_fix_level, dry_run, report attributes
        g: GuestFS handle with root filesystem mounted

    Returns:
        Dict with updated_files, count, and analysis
    """
    fix_level_str = getattr(self, "network_fix_level", "moderate")
    try:
        fix_level = FixLevel(fix_level_str)
    except Exception:
        fix_level = FixLevel.MODERATE

    fixer = NetworkFixer(
        logger=getattr(self, "logger", logging.getLogger(__name__)),
        fix_level=fix_level,
        dry_run=bool(getattr(self, "dry_run", False)),
    )

    result = fixer.fix_network_config(g, progress_callback=None)

    if hasattr(self, "report"):
        self.report.setdefault("network", {})
        self.report["network"] = result

    updated_files = [d["path"] for d in result["stats"]["details"] if d.get("modified", False)]
    return {"updated_files": updated_files, "count": len(updated_files), "analysis": result}


# Alias that reads nicer in some call sites (keeps old name intact)
fix_network_config_compat = fix_network_config
