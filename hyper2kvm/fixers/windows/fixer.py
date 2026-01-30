# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/windows/fixer.py
from __future__ import annotations

"""
Thin façade for Windows fixing.

This module intentionally stays small and delegates the heavy lifting to:
  - virtio/core.py (driver discovery + injection + staging + BCD backup hints)
  - registry_core.py (offline hive edits: SYSTEM services/CDD + SOFTWARE DevicePath)
  - network_fixer.py (best-effort network config retention via firstboot PowerShell)
"""

import logging
from typing import Any, Dict

try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore

from ...core.logging_utils import safe_logger as _safe_logger_base
from .virtio.core import (
    inject_virtio_drivers,
    is_windows,
    windows_bcd_actual_fix,
)

from .network_fixer import retain_windows_network_config
from .license.extractor import extract_license_info
from .license.reactivator import stage_reactivation_script, get_reactivation_command
from .activedirectory.extractor import extract_domain_info
from .activedirectory.rejoin import (
    stage_domain_rejoin_script,
    get_rejoin_command,
    DomainRejoinMethod,
)


def _safe_logger(self) -> logging.Logger:
    """Wrapper for backward compatibility - calls shared safe_logger."""
    return _safe_logger_base(self, "hyper2kvm.windows_fixer")


class WindowsFixer:
    """
    Optional OO wrapper for callers that expect a fixer object.

    This class is intentionally minimal: it forwards to module-level functions
    implemented elsewhere.
    """

    def __init__(self, **kwargs: Any):
        # Allow ad-hoc construction in tests; callers can also set attributes after init.
        # Typical attributes used:
        #   logger, dry_run, virtio_drivers_dir, force_virtio_overwrite, export_report,
        #   enable_virtio_gpu, enable_virtio_input, enable_virtio_fs, enable_virtio_serial, enable_virtio_rng,
        #   virtio_config_path, virtio_config,
        #   inspect_root
        for k, v in kwargs.items():
            setattr(self, k, v)

    def is_windows(self, g: guestfs.GuestFS) -> bool:
        return is_windows(self, g)

    def windows_bcd_actual_fix(self, g: guestfs.GuestFS) -> Dict[str, Any]:
        return windows_bcd_actual_fix(self, g)

    def inject_virtio_drivers(self, g: guestfs.GuestFS) -> Dict[str, Any]:
        return inject_virtio_drivers(self, g)

    def retain_windows_network_config(self, g: guestfs.GuestFS) -> Dict[str, Any]:
        return retain_windows_network_config(self, g)

    def extract_license_info(self, g: guestfs.GuestFS, root: str):
        """Extract Windows license information from offline registry."""
        return extract_license_info(g, root)

    def stage_license_reactivation(
        self,
        g: guestfs.GuestFS,
        root: str,
        license_info,
        kms_server_override=None,
        kms_port_override=None,
    ):
        """Stage license reactivation script for first boot."""
        return stage_reactivation_script(
            g, root, license_info, kms_server_override, kms_port_override
        )

    def extract_domain_info(self, g: guestfs.GuestFS, root: str):
        """Extract Active Directory domain membership information."""
        return extract_domain_info(g, root)

    def stage_domain_rejoin(
        self,
        g: guestfs.GuestFS,
        root: str,
        domain_info,
        method=DomainRejoinMethod.MANUAL,
        domain_override=None,
        ou_path=None,
        unattended_join_file=None,
    ):
        """Stage domain rejoin script for first boot."""
        return stage_domain_rejoin_script(
            g, root, domain_info, method, domain_override, ou_path, unattended_join_file
        )


__all__ = [
    "WindowsFixer",
    "is_windows",
    "windows_bcd_actual_fix",
    "inject_virtio_drivers",
    "retain_windows_network_config",
    "extract_license_info",
    "stage_reactivation_script",
    "extract_domain_info",
    "stage_domain_rejoin_script",
    "DomainRejoinMethod",
]
