"""Hyper-V enlightenments removal for Hyper-V to KVM migrations.

Removes Hyper-V-specific enlightenments and synthetic devices when migrating
FROM Hyper-V TO KVM. This prevents conflicts and ensures optimal performance
on the KVM hypervisor.
"""

import logging
import tempfile
from pathlib import Path
from typing import Dict, Any, List

try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore

logger = logging.getLogger(__name__)

# Hyper-V services to disable/remove
HYPERV_SERVICES = [
    "hv_fcopy",        # Hyper-V File Copy
    "hv_kvp_daemon",   # Hyper-V KVP Daemon
    "hv_vss_daemon",   # Hyper-V VSS Daemon
    "hvservice",       # Hyper-V Service
    "vmbus",           # Hyper-V Virtual Machine Bus
    "vmicheartbeat",   # Hyper-V Heartbeat Service
    "vmickvpexchange",  # Hyper-V Data Exchange Service
    "vmicrdv",         # Hyper-V Remote Desktop Virtualization Service
    "vmicshutdown",    # Hyper-V Guest Shutdown Service
    "vmictimesync",    # Hyper-V Time Synchronization Service
    "vmicvmsession",   # Hyper-V PowerShell Direct Service
    "vmicvss",         # Hyper-V Volume Shadow Copy Requestor
]


def cleanup_hyperv_enlightenments(
    g: "guestfs.GuestFS",
    root: str,
    force: bool = False,
) -> Dict[str, Any]:
    """Remove Hyper-V enlightenments and synthetic devices.

    Args:
        g: GuestFS instance
        root: Windows root path
        force: Force cleanup even if Hyper-V detection uncertain (default: False)

    Returns:
        Dict with cleanup results

    Configuration:
        - Detects if VM was running on Hyper-V
        - Disables Hyper-V integration services
        - Removes Hyper-V synthetic device drivers
        - Only executes for Hyper-V → KVM migrations
    """
    logger.info("Checking for Hyper-V enlightenments")

    results = {
        "success": False,
        "hyperv_detected": False,
        "services_disabled": [],
        "services_skipped": [],
        "warnings": [],
    }

    try:
        # Detect if this is a Hyper-V VM
        is_hyperv = _detect_hyperv_vm(g, root)

        if not is_hyperv and not force:
            logger.info("Hyper-V not detected - skipping enlightenment cleanup")
            results["warnings"].append(
                "Hyper-V not detected - cleanup skipped (use force=True to override)"
            )
            results["success"] = True
            return results

        results["hyperv_detected"] = is_hyperv or force

        if force and not is_hyperv:
            logger.warning("Force cleanup enabled - proceeding without Hyper-V detection")
            results["warnings"].append("Forced cleanup without Hyper-V detection")

        from ..registry.io import detect_windows_hive, download_and_open_hive
        from ..registry.encoding import _close_best_effort, _detect_current_controlset

        system_path = detect_windows_hive(g, root, "SYSTEM")
        if not system_path:
            results["warnings"].append("SYSTEM hive not found - cannot cleanup")
            return results

        with tempfile.TemporaryDirectory() as tmpdir:
            local_hive = Path(tmpdir) / "SYSTEM"
            hive = download_and_open_hive(logger, g, system_path, local_hive, write=True)

            try:
                root_node = hive.root()
                controlset_name = _detect_current_controlset(hive, root_node)

                # Disable Hyper-V services
                for service in HYPERV_SERVICES:
                    if _disable_service(hive, root_node, controlset_name, service):
                        results["services_disabled"].append(service)
                        logger.info(f"Disabled Hyper-V service: {service}")
                    else:
                        results["services_skipped"].append(service)

                # Commit changes
                from ..registry.encoding import _commit_best_effort

                _commit_best_effort(hive)

                # Upload modified hive
                g.upload(str(local_hive), system_path)

                results["success"] = True
                logger.info(
                    f"Hyper-V cleanup complete: {len(results['services_disabled'])} services disabled"
                )

            finally:
                _close_best_effort(hive)

    except Exception as e:
        logger.error(f"Failed to cleanup Hyper-V enlightenments: {e}")
        logger.debug("Hyper-V cleanup error", exc_info=True)
        results["warnings"].append(f"Cleanup failed: {e}")

    return results


def _detect_hyperv_vm(g: "guestfs.GuestFS", root: str) -> bool:
    """Detect if VM was running on Hyper-V.

    Args:
        g: GuestFS instance
        root: Windows root path

    Returns:
        True if Hyper-V detected, False otherwise
    """
    try:
        from ..registry.io import detect_windows_hive, download_and_open_hive
        from ..registry.encoding import _close_best_effort, _detect_current_controlset

        system_path = detect_windows_hive(g, root, "SYSTEM")
        if not system_path:
            return False

        with tempfile.TemporaryDirectory() as tmpdir:
            local_hive = Path(tmpdir) / "SYSTEM"
            hive = download_and_open_hive(logger, g, system_path, local_hive, write=False)

            try:
                root_node = hive.root()
                controlset_name = _detect_current_controlset(hive, root_node)

                # Check for Hyper-V services
                for service in HYPERV_SERVICES[:3]:  # Check first 3 services
                    service_path = f"{controlset_name}\\Services\\{service}"
                    service_node = hive.node_get_child(root_node, service_path)

                    if service_node:
                        logger.info(f"Hyper-V service detected: {service}")
                        return True

            finally:
                _close_best_effort(hive)

    except Exception as e:
        logger.debug(f"Error detecting Hyper-V: {e}")

    return False


def _disable_service(
    hive: "hivex.Hivex",
    root_node: int,
    controlset_name: str,
    service: str,
) -> bool:
    """Disable a Windows service by setting Start=4 (disabled).

    Args:
        hive: Hivex instance
        root_node: Registry root node
        controlset_name: Current control set name
        service: Service name

    Returns:
        True if service was disabled, False if not found
    """
    from ..registry.encoding import _set_dword

    service_path = f"{controlset_name}\\Services\\{service}"
    service_node = hive.node_get_child(root_node, service_path)

    if not service_node:
        return False

    # Set Start = 4 (SERVICE_DISABLED)
    _set_dword(hive, service_node, "Start", 4)

    return True
