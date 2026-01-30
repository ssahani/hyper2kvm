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
from .appcompat.detector import (
    detect_hardware_dependent_apps,
    detect_license_services,
    detect_dongle_drivers,
)
from .appcompat.sqlserver import (
    detect_sql_server_instances,
    generate_sql_reconfiguration_script,
)
from .appcompat.reporter import generate_compatibility_report


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

    def detect_application_compatibility(
        self, g: guestfs.GuestFS, root: str
    ) -> Dict[str, Any]:
        """Detect application compatibility issues for migration.

        Scans for:
        - Hardware-dependent applications
        - License manager services
        - Hardware dongle drivers
        - SQL Server instances

        Returns:
            Dict with findings and compatibility report
        """
        logger = _safe_logger(self)
        logger.info("Running application compatibility detection")

        results = {
            "hardware_apps": [],
            "license_services": [],
            "dongle_drivers": [],
            "sql_instances": [],
            "report_json": None,
            "report_markdown": None,
        }

        try:
            # Detect hardware-dependent applications
            results["hardware_apps"] = detect_hardware_dependent_apps(g, root)

            # Detect license services
            results["license_services"] = detect_license_services(g, root)

            # Detect dongle drivers
            results["dongle_drivers"] = detect_dongle_drivers(g, root)

            # Detect SQL Server instances
            results["sql_instances"] = detect_sql_server_instances(g, root)

            # Generate compatibility report
            hostname = self._extract_hostname(g, root)

            report = generate_compatibility_report(
                hardware_apps=results["hardware_apps"],
                license_services=results["license_services"],
                dongle_drivers=results["dongle_drivers"],
                sql_instances=results["sql_instances"],
                hostname=hostname,
            )

            results["report_json"] = report.to_json()
            results["report_markdown"] = report.to_markdown()

            logger.info(
                f"Compatibility scan complete: {report.total_findings} findings "
                f"({report.critical_findings} critical, {report.high_findings} high)"
            )

        except Exception as e:
            logger.error(f"Application compatibility detection failed: {e}")
            logger.debug("Compatibility detection error", exc_info=True)

        return results

    def generate_sql_reconfiguration_script(
        self,
        g: guestfs.GuestFS,
        root: str,
        old_hostname: str = None,
        new_hostname: str = None,
    ) -> str:
        """Generate SQL Server reconfiguration script.

        Args:
            g: GuestFS instance
            root: Windows root path
            old_hostname: Old server hostname (optional)
            new_hostname: New server hostname (optional)

        Returns:
            T-SQL script as string
        """
        instances = detect_sql_server_instances(g, root)
        return generate_sql_reconfiguration_script(
            instances, old_hostname, new_hostname
        )

    def _extract_hostname(self, g: guestfs.GuestFS, root: str) -> str:
        """Extract Windows hostname from registry.

        Args:
            g: GuestFS instance
            root: Windows root path

        Returns:
            Hostname string or "Unknown"
        """
        try:
            import tempfile
            from pathlib import Path
            from .registry.io import detect_windows_hive, download_and_open_hive
            from .registry.encoding import _close_best_effort, _detect_current_controlset

            system_path = detect_windows_hive(g, root, "SYSTEM")
            if not system_path:
                return "Unknown"

            with tempfile.TemporaryDirectory() as tmpdir:
                local_hive = Path(tmpdir) / "SYSTEM"
                hive = download_and_open_hive(
                    _safe_logger(self), g, system_path, local_hive, write=False
                )

                try:
                    root_node = hive.root()
                    controlset_name = _detect_current_controlset(hive, root_node)
                    hostname_path = (
                        f"{controlset_name}\\Control\\ComputerName\\ComputerName"
                    )

                    hostname_node = hive.node_get_child(root_node, hostname_path)
                    if not hostname_node:
                        return "Unknown"

                    value = hive.node_get_value(hostname_node, "ComputerName")
                    if value:
                        hostname_bytes = hive.value_value(value)
                        return hostname_bytes.decode(
                            "utf-16le", errors="ignore"
                        ).rstrip("\x00")

                finally:
                    _close_best_effort(hive)

        except Exception:
            pass

        return "Unknown"


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
    "detect_hardware_dependent_apps",
    "detect_license_services",
    "detect_dongle_drivers",
    "detect_sql_server_instances",
    "generate_sql_reconfiguration_script",
    "generate_compatibility_report",
]
