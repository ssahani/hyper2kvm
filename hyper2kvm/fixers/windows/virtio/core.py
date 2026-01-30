# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/windows/virtio/core.py
# -*- coding: utf-8 -*-
"""
Windows VirtIO driver injection for VMware to KVM migration.
"""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List

import guestfs  # type: ignore

from ....core.utils import U

# Import from split modules - configuration
from .windows_virtio_config import (
    DEFAULT_VIRTIO_CONFIG,
    DriverStartType,
    DriverType,
    WindowsRelease,
    _load_virtio_config,
)

# Import from split modules - utilities
from .windows_virtio_utils import (
    _log,
    _log_mountpoints_best_effort,
    _safe_logger,
    _step,
)

# Import from split modules - paths
from .windows_virtio_paths import (
    WindowsSystemPaths,
    _find_windows_root,
)

# Import from split modules - detection
from .detection import (
    DriverFile,
    WindowsVirtioPlan,
    _bucket_candidates,
    _choose_driver_plan,
    _plan_to_dict,
    _windows_version_info,
    is_windows,
)

# Import from split modules - discovery
from .discovery import _discover_virtio_drivers, _warn_if_driver_defs_suspicious

# Import from split modules - installation
from .install import (
    _virtio_bcd_backup,
    _virtio_copy_sys_binaries,
    _virtio_edit_registry_system,
    _virtio_ensure_system_volume,
    _virtio_ensure_temp_dir,
    _virtio_init_result,
    _virtio_preflight,
    _virtio_provision_firstboot,
    _virtio_remove_vmware_sys_files,
    _virtio_stage_manual_setup_cmd,
    _virtio_stage_packages,
    _virtio_update_devicepath,
)

# Optional ISO extractor
try:
    import pycdlib  # type: ignore
except Exception:  # pragma: no cover
    pycdlib = None


# Public API exports
__all__ = [
    # Enums and types
    "DriverType",
    "WindowsRelease",
    "DriverStartType",
    "WindowsVirtioPlan",
    "DriverFile",
    "WindowsSystemPaths",
    # Configuration
    "DEFAULT_VIRTIO_CONFIG",
    # Public API functions
    "is_windows",
    "windows_bcd_actual_fix",
    "inject_virtio_drivers",
    # Main class
    "WindowsFixer",
]


# VirtIO source materialization (dir OR ISO)


@contextmanager
def _materialize_virtio_source(self, virtio_path: Path):
    """
    Context manager to materialize VirtIO driver source.

    Accepts either:
    - Directory: yields as-is
    - ISO file: extracts to temporary directory, yields temp dir, cleans up on exit

    Args:
        self: Context object with logger
        virtio_path: Path to VirtIO drivers (directory or .iso file)

    Yields:
        Path: Directory containing VirtIO drivers

    Raises:
        RuntimeError: If path is neither directory nor .iso, or if pycdlib is missing for ISO
    """
    logger = _safe_logger(self)

    if virtio_path.is_dir():
        yield virtio_path
        return

    if virtio_path.suffix.lower() != ".iso":
        raise RuntimeError(f"virtio_drivers_dir must be a directory or .iso, got: {virtio_path}")

    if pycdlib is None:
        raise RuntimeError(
            "virtio_drivers_dir is an ISO but pycdlib is not installed. "
            "Install pycdlib or provide an extracted virtio-win directory."
        )

    td = Path(tempfile.mkdtemp(prefix="hyper2kvm-virtio-iso-"))
    extracted = 0
    tried: List[str] = []
    try:
        _log(logger, logging.INFO, "📀 Extracting VirtIO ISO -> %s", td)
        iso = pycdlib.PyCdlib()
        iso.open(str(virtio_path))

        def _children(iso_dir: str, use_joliet: bool):
            if use_joliet:
                return iso.list_children(joliet_path=iso_dir)
            return iso.list_children(iso_path=iso_dir)

        def _walk(iso_dir: str, use_joliet: bool):
            try:
                kids = _children(iso_dir, use_joliet)
            except Exception:
                return
            for c in kids:
                try:
                    name = c.file_identifier().decode("utf-8", errors="ignore").rstrip(";1")
                except Exception:
                    continue
                if name in (".", "..") or not name:
                    continue
                child = iso_dir.rstrip("/") + "/" + name
                try:
                    if c.is_dir():
                        yield from _walk(child, use_joliet)
                    else:
                        yield child
                except Exception:
                    continue

        for use_joliet in (False, True):
            mode = "joliet" if use_joliet else "iso9660"
            tried.append(mode)
            for iso_file in _walk("/", use_joliet):
                rel = iso_file.lstrip("/").rstrip(";1")
                out = td / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                try:
                    if use_joliet:
                        iso.get_file_from_iso(str(out), joliet_path=iso_file)
                    else:
                        iso.get_file_from_iso(str(out), iso_path=iso_file)
                    extracted += 1
                except Exception as e:
                    _log(logger, logging.DEBUG, "ISO extract failed for %s (%s): %s", iso_file, mode, e)

        try:
            iso.close()
        except Exception:
            pass

        _log(logger, logging.INFO, "📀 ISO extraction complete: %d files (modes tried=%s)", extracted, tried)
        yield td
    finally:
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass


# Public: BCD backup + hints (offline-safe)


def windows_bcd_actual_fix(self, g: guestfs.GuestFS) -> Dict[str, Any]:
    """
    Discover and back up Windows BCD stores (Boot Configuration Data).

    This is an offline-safe operation that:
    1. Locates BCD stores (BIOS and UEFI locations)
    2. Creates backups with timestamps
    3. Provides boot mode hints based on discovered stores

    NOTE: Deep BCD edits (e.g., boot device changes) require Windows tools
    (bcdedit/bootrec) run inside Windows Recovery Environment.

    Args:
        self: Context object with logger and optional dry_run flag
        g: GuestFS handle with Windows system volume mounted at /

    Returns:
        Dict with:
        - windows: bool - Whether this is a Windows system
        - bcd: str - Status: "found", "no_bcd_store", "no_windows_directory", "error"
        - stores: Dict of discovered BCD stores (path, size, exists status)
        - backups: Dict of created backups (backup_path, timestamp, size)
        - notes: List of hints about boot mode (UEFI vs BIOS)
        - reason: str (only if windows=False)
    """
    logger = _safe_logger(self)

    if not is_windows(self, g):
        return {"windows": False, "reason": "not_windows"}

    windows_root = _find_windows_root(self, g)
    if not windows_root:
        return {"windows": True, "bcd": "no_windows_directory"}

    bcd_stores = {
        "bios": f"{windows_root}/Boot/BCD",
        "uefi_standard": "/boot/efi/EFI/Microsoft/Boot/BCD",
        "uefi_alternative": "/boot/EFI/Microsoft/Boot/BCD",
        "uefi_fallback": "/efi/EFI/Microsoft/Boot/BCD",
        "uefi_root": "/EFI/Microsoft/Boot/BCD",
    }

    found: Dict[str, Any] = {}
    backups: Dict[str, Any] = {}
    dry_run = getattr(self, "dry_run", False)

    for store_type, store_path in bcd_stores.items():
        try:
            if g.is_file(store_path):
                size = g.filesize(store_path)
                found[store_type] = {"path": store_path, "size": size, "exists": True}
                if not dry_run:
                    ts = U.now_ts()
                    backup_path = f"{store_path}.backup.hyper2kvm.{ts}"
                    try:
                        g.cp(store_path, backup_path)
                        backups[store_type] = {"backup_path": backup_path, "timestamp": ts, "size": size}
                    except Exception as be:
                        backups[store_type] = {"error": str(be), "path": store_path}
            else:
                found[store_type] = {"path": store_path, "exists": False}
        except Exception as e:
            found[store_type] = {"path": store_path, "exists": False, "error": str(e)}

    if not any(v.get("exists") for v in found.values()):
        return {"windows": True, "bcd": "no_bcd_store", "stores": found}

    notes: List[str] = [
        "Offline-safe: backups created where possible.",
        "Deep BCD edits need Windows tools (bcdedit/bootrec) inside Windows RE.",
    ]

    has_uefi = any(found.get(k, {}).get("exists") for k in ("uefi_standard", "uefi_alternative", "uefi_fallback", "uefi_root"))
    has_bios = found.get("bios", {}).get("exists")

    if has_uefi and not has_bios:
        notes.append("Hint: UEFI-style BCD present; boot the converted VM in UEFI mode.")
    if has_bios and not has_uefi:
        notes.append("Hint: BIOS-style BCD present; boot the converted VM in legacy BIOS mode.")
    if has_bios and has_uefi:
        notes.append("Hint: Both BIOS+UEFI BCD stores found; boot mode must match installed Windows mode.")

    return {"windows": True, "bcd": "found", "stores": found, "backups": backups, "notes": notes}


# Finalization + reporting


def _virtio_finalize(self, result: Dict[str, Any], drivers: List[DriverFile], *, plan: WindowsVirtioPlan, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Finalize VirtIO injection result.

    Updates result dict with:
    - drivers_found: List of discovered driver details
    - injected/success: Overall success status
    - notes: Detailed information about detection, discovery, installation
    - warnings: Critical issues (missing storage drivers)
    - report_exported: Path to JSON report (if export_report=True)

    Args:
        self: Context object with logger and optional export_report flag
        result: Accumulating result dict
        drivers: List of discovered driver files
        plan: Windows driver plan (release, arch, bucket)
        cfg: VirtIO configuration dict

    Returns:
        Updated result dict
    """
    logger = _safe_logger(self)

    result["drivers_found"] = [d.to_dict() for d in drivers]

    sys_ok = any(x.get("action") in ("copied", "dry_run", "skipped") for x in result.get("files_copied", []))
    reg_ok = bool(result.get("registry_changes", {}).get("success"))
    result["injected"] = bool(sys_ok and reg_ok)
    result["success"] = result["injected"]
    if not result["success"]:
        result["reason"] = "registry_update_failed" if not reg_ok else "sys_copy_failed"

    storage_found = sorted({d.service_name for d in drivers if d.type == DriverType.STORAGE})
    storage_missing: List[str] = []
    if "viostor" not in storage_found:
        storage_missing.append("viostor")
    if "vioscsi" not in storage_found:
        storage_missing.append("vioscsi")

    result["notes"] += [
        "Release detection: prefers ProductName + build number (CurrentBuildNumber/CurrentBuild) over major/minor.",
        "Config-driven: driver definitions + OS(bucket) mapping can come from YAML/JSON config (self.config) or an override file.",
        "Config merge: dicts deep-merge; lists are replaced (override wins).",
        "Default release fallback: Windows 11.",
        "Driver discovery: canonical pattern first; fallback globs warn on multiple matches and pick a best candidate.",
        "Storage: injects viostor + vioscsi when present and forces BOOT start in SYSTEM hive.",
        "Registry: StartOverride removed when found (can silently disable boot drivers).",
        "CDD: CriticalDeviceDatabase populated for virtio storage PCI IDs to ensure early binding.",
        f"Driver discovery buckets: {_bucket_candidates(plan.release, cfg)}",
        f"Storage drivers found: {storage_found} missing: {storage_missing}",
        r"Staging: payload staged under C:\hyper2kvm\drivers\virtio and installed via firstboot service (pnputil).",
        r"Logs: see the 'firstboot' section for the exact log path.",
    ]

    if storage_missing:
        msg = f"Missing critical storage drivers: {storage_missing} (guest may BSOD INACCESSIBLE_BOOT_DEVICE)"
        result["warnings"].append(msg)
        _log(logger, logging.WARNING, "%s", msg)

    export_report = bool(getattr(self, "export_report", False))
    if export_report:
        report_path = "virtio_inject_report.json"
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            result["report_exported"] = report_path
            _log(logger, logging.INFO, "Report exported: %s", report_path)
        except Exception as e:
            msg = f"Failed to export report: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)

    return result


# Public: VirtIO injection orchestration


def inject_virtio_drivers(self, g: guestfs.GuestFS) -> Dict[str, Any]:
    """
    Inject VirtIO drivers into a Windows guest image (main entry point).

    This orchestrates the complete VirtIO injection pipeline:
    1. Preflight checks (Windows detection, virtio_drivers_dir validation)
    2. Configuration loading and driver plan creation
    3. Driver discovery from source directory/ISO
    4. System volume mounting and path resolution
    5. Driver binary (.sys) upload to System32\\drivers
    6. Driver package staging (INF/CAT/DLL) for PnP installation
    7. Registry edits (SYSTEM hive: Services, CDD, StartOverride)
    8. DevicePath update (SOFTWARE hive) for PnP discovery
    9. Firstboot service provisioning (pnputil /install on first boot)
    10. BCD backup and boot mode detection

    Args:
        self: Context object with configuration attributes:
            - virtio_drivers_dir: Path - VirtIO source (directory or .iso)
            - inspect_root: str - GuestFS inspect root
            - dry_run: bool (optional) - Skip actual writes
            - force_virtio_overwrite: bool (optional) - Overwrite existing drivers
            - enable_virtio_gpu/input/fs/serial/rng: bool (optional) - Enable extra drivers
            - virtio_config/virtio_config_path/virtio_config_inline_json: (optional) - Config overrides
            - config: Dict (optional) - Merged app config
            - export_report: bool (optional) - Export JSON report
            - logger: logging.Logger (optional)
        g: GuestFS handle (should be launched but not mounted)

    Returns:
        Dict with comprehensive injection status:
        - injected: bool - Overall success
        - success: bool - Same as injected
        - dry_run: bool - Whether this was a dry run
        - windows: Dict - Windows version info (build, product_name, arch, major, minor)
        - plan: Dict - Driver plan (release, arch_dir, bucket_hint, drivers_needed)
        - drivers_found: List[Dict] - Discovered drivers with metadata
        - files_copied: List[Dict] - Uploaded .sys files
        - packages_staged: List[Dict] - Staged INF/CAT/DLL packages
        - registry_changes: Dict - SYSTEM hive edit results
        - devicepath_changes: Dict - SOFTWARE hive DevicePath update results
        - firstboot: Dict - Firstboot service provisioning results
        - bcd_changes: Dict - BCD discovery and backup results
        - artifacts: List[Dict] - All created artifacts
        - warnings: List[str] - Non-fatal issues
        - notes: List[str] - Detailed information about the injection
        - reason: str (only if injected=False) - Failure reason

    Raises:
        Exception: Critical failures during injection (logged and returned in result)
    """
    logger = _safe_logger(self)

    virtio_src, early = _virtio_preflight(self, g)
    if early is not None:
        return early
    assert virtio_src is not None

    cfg = _load_virtio_config(self)
    _warn_if_driver_defs_suspicious(self, cfg)

    _log_mountpoints_best_effort(logger, g)

    paths = _virtio_ensure_system_volume(self, g)
    if not paths.windows_dir or not g.is_dir(paths.windows_dir):
        return {"injected": False, "reason": "no_windows_root", "windows_dir": paths.windows_dir}

    dry_run = bool(getattr(self, "dry_run", False))
    _virtio_ensure_temp_dir(self, g, paths, dry_run=dry_run)

    win_info = _windows_version_info(self, g, paths=paths)
    plan = _choose_driver_plan(self, win_info, cfg)

    with _step(logger, "🔎 Discover VirtIO drivers"):
        drivers = _discover_virtio_drivers(self, virtio_src, plan, cfg)

    if not drivers:
        return {
            "injected": False,
            "reason": "no_drivers_found",
            "virtio_dir": str(virtio_src),
            "windows_info": win_info,
            "plan": _plan_to_dict(plan),
            "buckets_tried": _bucket_candidates(plan.release, cfg),
            "windows_paths": {
                "windows_dir": paths.windows_dir,
                "system32_dir": paths.system32_dir,
                "drivers_dir": paths.drivers_dir,
                "config_dir": paths.config_dir,
                "temp_dir": paths.temp_dir,
            },
        }

    result = _virtio_init_result(self, virtio_src, win_info, plan, paths)

    try:
        _virtio_copy_sys_binaries(self, g, result, paths, drivers)
    except Exception as e:
        return {**result, "reason": f"sys_copy_failed: {e}"}

    staging_root, devicepath_append = _virtio_stage_packages(self, g, result, drivers)

    _virtio_stage_manual_setup_cmd(self, g, result)
    _virtio_edit_registry_system(self, g, result, paths, drivers)
    _virtio_remove_vmware_sys_files(self, g, result, paths)
    _virtio_update_devicepath(self, g, result, paths, devicepath_append)
    _virtio_provision_firstboot(self, g, result, paths, staging_root)
    _virtio_bcd_backup(self, g, result)

    return _virtio_finalize(self, result, drivers, plan=plan, cfg=cfg)


# Public API wrapper class


class WindowsFixer:
    """
    Windows VirtIO driver injection interface.
    """

    def is_windows(self, g: guestfs.GuestFS) -> bool:
        """
        Detect whether the guest is Windows.

        Args:
            g: GuestFS handle with system volume mounted

        Returns:
            bool: True if Windows, False otherwise
        """
        return is_windows(self, g)

    def windows_bcd_actual_fix(self, g: guestfs.GuestFS) -> Dict[str, Any]:
        """
        Discover and back up Windows BCD stores.

        Args:
            g: GuestFS handle with Windows system volume mounted

        Returns:
            Dict with BCD discovery and backup results
        """
        return windows_bcd_actual_fix(self, g)

    def inject_virtio_drivers(self, g: guestfs.GuestFS) -> Dict[str, Any]:
        """
        Inject VirtIO drivers into Windows guest.

        Args:
            g: GuestFS handle (should be launched but not mounted)

        Returns:
            Dict with comprehensive injection status
        """
        return inject_virtio_drivers(self, g)
