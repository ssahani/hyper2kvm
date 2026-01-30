# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/windows/virtio/install.py
# -*- coding: utf-8 -*-
"""
VirtIO driver installation pipeline stages.

This module contains the installation pipeline functions that handle
the sequential stages of VirtIO driver injection into Windows guests.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import guestfs  # type: ignore

from ..registry_core import (
    append_devicepath_software_hive,
    edit_system_hive,
    provision_firstboot_payload_and_service,
    _ensure_windows_root,
)
from .windows_virtio_utils import (
    _safe_logger,
    _log,
    _guest_mkdir_p,
    _guest_write_text,
    _guest_sha256,
    _is_probably_driver_payload,
)
from .windows_virtio_config import DriverStartType, DriverType
from .windows_virtio_paths import WindowsSystemPaths, _guestfs_to_windows_path
from .detection import WindowsVirtioPlan, DriverFile, _plan_to_dict


def _sha256_path(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# Injection pipeline (split into smaller functions)

def _virtio_preflight(self, g: guestfs.GuestFS) -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
    logger = _safe_logger(self)
    virtio_dir = getattr(self, "virtio_drivers_dir", None)
    if not virtio_dir:
        _log(logger, logging.INFO, "VirtIO inject: virtio_drivers_dir not set -> skip")
        return None, {"injected": False, "reason": "virtio_drivers_dir_not_set"}

    virtio_src = Path(str(virtio_dir))
    if not virtio_src.exists():
        return None, {"injected": False, "reason": "virtio_drivers_dir_not_found", "path": str(virtio_src)}
    if not (virtio_src.is_dir() or virtio_src.suffix.lower() == ".iso"):
        return None, {"injected": False, "reason": "virtio_drivers_dir_invalid", "path": str(virtio_src)}

    # Import here to avoid circular dependency
    from .core import is_windows
    if not is_windows(self, g):
        return None, {"injected": False, "reason": "not_windows"}
    if not getattr(self, "inspect_root", None):
        return None, {"injected": False, "reason": "no_inspect_root"}

    return virtio_src, None


def _virtio_ensure_system_volume(self, g: guestfs.GuestFS) -> WindowsSystemPaths:
    from .windows_virtio_utils import _step
    from .windows_virtio_paths import _resolve_windows_system_paths
    logger = _safe_logger(self)
    with _step(logger, "🧭 Ensure Windows system volume mounted (C: -> /)"):
        _ensure_windows_root(logger, g, hint_hive_path="/Windows/System32/config/SYSTEM")
    return _resolve_windows_system_paths(self, g)


def _virtio_ensure_temp_dir(self, g: guestfs.GuestFS, paths: WindowsSystemPaths, *, dry_run: bool) -> None:
    from .windows_virtio_utils import _step
    logger = _safe_logger(self)
    with _step(logger, "📁 Ensure Windows Temp dir exists"):
        try:
            _guest_mkdir_p(g, paths.temp_dir, dry_run=dry_run)
        except Exception as e:
            _log(logger, logging.WARNING, "Temp dir ensure failed (%s): %s", paths.temp_dir, e)


def _virtio_init_result(self, virtio_src: Path, win_info: Dict[str, Any], plan: WindowsVirtioPlan, paths: WindowsSystemPaths) -> Dict[str, Any]:
    dry_run = bool(getattr(self, "dry_run", False))
    force_overwrite = bool(getattr(self, "force_virtio_overwrite", False))
    return {
        "injected": False,
        "success": False,
        "dry_run": bool(dry_run),
        "force_overwrite": bool(force_overwrite),
        "windows": win_info,
        "plan": _plan_to_dict(plan),
        "virtio_dir": str(virtio_src),
        "windows_paths": {
            "windows_dir": paths.windows_dir,
            "system32_dir": paths.system32_dir,
            "drivers_dir": paths.drivers_dir,
            "config_dir": paths.config_dir,
            "temp_dir": paths.temp_dir,
            "system_hive": paths.system_hive,
            "software_hive": paths.software_hive,
        },
        "drivers_found": [],
        "files_copied": [],
        "packages_staged": [],
        "registry_changes": {},
        "devicepath_changes": {},
        "bcd_changes": {},
        "firstboot": {},
        "artifacts": [],
        "warnings": [],
        "notes": [],
    }


def _virtio_copy_sys_binaries(self, g: guestfs.GuestFS, result: Dict[str, Any], paths: WindowsSystemPaths, drivers: List[DriverFile]) -> None:
    from .windows_virtio_utils import _step
    logger = _safe_logger(self)
    dry_run = bool(result.get("dry_run"))
    force_overwrite = bool(result.get("force_overwrite"))

    with _step(logger, "🧱 Ensure System32\\drivers exists"):
        if not g.is_dir(paths.drivers_dir) and not dry_run:
            g.mkdir_p(paths.drivers_dir)

    with _step(logger, "📦 Upload .sys driver binaries"):
        for drv in drivers:
            dest_path = f"{paths.drivers_dir}/{drv.dest_name}"
            try:
                src_size = drv.src_path.stat().st_size
                host_hash = _sha256_path(drv.src_path)

                if g.is_file(dest_path) and not force_overwrite:
                    try:
                        guest_hash = _guest_sha256(g, dest_path)
                        if guest_hash and guest_hash == host_hash:
                            result["files_copied"].append(
                                {
                                    "name": drv.dest_name,
                                    "action": "skipped",
                                    "reason": "already_exists_same_hash",
                                    "source": str(drv.src_path),
                                    "destination": dest_path,
                                    "size": src_size,
                                    "sha256": host_hash,
                                    "type": drv.type.value,
                                    "service": drv.service_name,
                                }
                            )
                            result["artifacts"].append(
                                {
                                    "kind": "driver_sys",
                                    "service": drv.service_name,
                                    "type": drv.type.value,
                                    "src": str(drv.src_path),
                                    "dst": dest_path,
                                    "size": src_size,
                                    "sha256": host_hash,
                                    "action": "skipped",
                                }
                            )
                            _log(logger, logging.INFO, "Skip (same hash): %s -> %s", drv.src_path, dest_path)
                            continue
                    except Exception:
                        pass

                if not dry_run:
                    g.upload(str(drv.src_path), dest_path)

                verify = None
                if drv.type == DriverType.STORAGE and not dry_run:
                    try:
                        verify = _guest_sha256(g, dest_path)
                    except Exception:
                        verify = None

                action = "copied" if not dry_run else "dry_run"
                result["files_copied"].append(
                    {
                        "name": drv.dest_name,
                        "action": action,
                        "source": str(drv.src_path),
                        "destination": dest_path,
                        "size": src_size,
                        "sha256": host_hash,
                        "guest_sha256": verify,
                        "type": drv.type.value,
                        "service": drv.service_name,
                        "bucket_used": drv.bucket_used,
                        "match_pattern": drv.match_pattern,
                    }
                )
                result["artifacts"].append(
                    {
                        "kind": "driver_sys",
                        "service": drv.service_name,
                        "type": drv.type.value,
                        "src": str(drv.src_path),
                        "dst": dest_path,
                        "size": src_size,
                        "sha256": host_hash,
                        "guest_sha256": verify,
                        "action": action,
                        "bucket_used": drv.bucket_used,
                        "match_pattern": drv.match_pattern,
                    }
                )
                _log(logger, logging.INFO, "Upload: %s -> %s", drv.src_path, dest_path)
            except Exception as e:
                msg = f"VirtIO inject: copy failed {drv.src_path} -> {dest_path}: {e}"
                result["warnings"].append(msg)
                _log(logger, logging.WARNING, "%s", msg)


def _virtio_stage_packages(self, g: guestfs.GuestFS, result: Dict[str, Any], drivers: List[DriverFile]) -> Tuple[str, str]:
    """
    Stage INF/CAT/DLL payloads so firstboot can pnputil /install them.

    Returns (staging_root_guestfs_path, devicepath_append_string)
    """
    from .windows_virtio_utils import _step
    logger = _safe_logger(self)
    dry_run = bool(result.get("dry_run"))

    staging_root = "/hyper2kvm/drivers/virtio"
    devicepath_append = r"%SystemDrive%\hyper2kvm\drivers\virtio"

    with _step(logger, "📁 Stage driver packages (INF/CAT/DLL) for PnP"):
        try:
            _guest_mkdir_p(g, staging_root, dry_run=dry_run)
        except Exception as e:
            msg = f"VirtIO stage: failed to create staging root {staging_root}: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)

        for drv in drivers:
            if not drv.package_dir or not drv.package_dir.exists() or not drv.inf_path:
                continue

            guest_pkg_dir = f"{staging_root}/{drv.service_name}"
            try:
                _guest_mkdir_p(g, guest_pkg_dir, dry_run=dry_run)
            except Exception as e:
                msg = f"VirtIO stage: cannot create {guest_pkg_dir}: {e}"
                result["warnings"].append(msg)
                _log(logger, logging.WARNING, "%s", msg)
                continue

            staged_files: List[Dict[str, Any]] = []
            try:
                payload = sorted([p for p in drv.package_dir.iterdir() if p.is_file() and _is_probably_driver_payload(p)])
                for p in payload:
                    gp = f"{guest_pkg_dir}/{p.name}"
                    try:
                        if not dry_run:
                            g.upload(str(p), gp)
                        staged_files.append({"name": p.name, "source": str(p), "dest": gp, "size": p.stat().st_size})
                        result["artifacts"].append(
                            {
                                "kind": "staged_payload",
                                "service": drv.service_name,
                                "type": drv.type.value,
                                "src": str(p),
                                "dst": gp,
                                "size": p.stat().st_size,
                                "action": "copied" if not dry_run else "dry_run",
                            }
                        )
                    except Exception as e:
                        msg = f"VirtIO stage: upload failed {p} -> {gp}: {e}"
                        result["warnings"].append(msg)
                        _log(logger, logging.WARNING, "%s", msg)

                if staged_files:
                    result["packages_staged"].append(
                        {
                            "service": drv.service_name,
                            "type": drv.type.value,
                            "package_dir": str(drv.package_dir),
                            "inf": str(drv.inf_path),
                            "guest_dir": guest_pkg_dir,
                            "files": staged_files,
                        }
                    )
                    _log(logger, logging.INFO, "Staged package: %s -> %s (%d files)", drv.service_name, guest_pkg_dir, len(staged_files))
            except Exception as e:
                msg = f"VirtIO stage: failed staging package for {drv.service_name}: {e}"
                result["warnings"].append(msg)
                _log(logger, logging.WARNING, "%s", msg)

    return staging_root, devicepath_append


def _virtio_stage_manual_setup_cmd(self, g: guestfs.GuestFS, result: Dict[str, Any]) -> None:
    from .windows_virtio_utils import _step
    logger = _safe_logger(self)
    dry_run = bool(result.get("dry_run"))

    if not result.get("packages_staged"):
        return

    setup_script = "/hyper2kvm/setup.cmd"
    script_content = "@echo off\r\n"
    script_content += "echo Installing staged VirtIO drivers...\r\n"
    for staged in result["packages_staged"]:
        inf = staged.get("inf")
        if inf:
            inf_name = Path(str(inf)).name
            script_content += f'pnputil /add-driver "C:\\hyper2kvm\\drivers\\virtio\\{staged["service"]}\\{inf_name}" /install\r\n'
    script_content += "echo Done.\r\n"

    try:
        with _step(logger, "🧾 Stage manual setup.cmd (optional)"):
            _guest_write_text(g, setup_script, script_content, dry_run=dry_run)
        result["setup_script"] = {"path": setup_script, "content": script_content}
        result["artifacts"].append({"kind": "setup_cmd", "dst": setup_script, "action": "written" if not dry_run else "dry_run"})
    except Exception as e:
        msg = f"Failed to stage setup.cmd: {e}"
        result["warnings"].append(msg)
        _log(logger, logging.WARNING, "%s", msg)


def _virtio_edit_registry_system(self, g: guestfs.GuestFS, result: Dict[str, Any], paths: WindowsSystemPaths, drivers: List[DriverFile]) -> None:
    from .windows_virtio_utils import _step
    logger = _safe_logger(self)
    with _step(logger, "🧬 Edit SYSTEM hive (Services + CDD + StartOverride + Remove VMware)"):
        try:
            reg_res = edit_system_hive(
                self,
                g,
                paths.system_hive,
                drivers,
                driver_type_storage_value=DriverType.STORAGE.value,
                boot_start_value=DriverStartType.BOOT.value,
            )
            result["registry_changes"] = reg_res
            if not reg_res.get("success"):
                _log(logger, logging.WARNING, "SYSTEM hive edit reported errors: %s", reg_res.get("errors"))

            # Report VMware removal stats
            vmware_removed = reg_res.get("vmware_services_removed", [])
            if vmware_removed:
                _log(logger, logging.INFO, "Removed %d VMware services from registry: %s",
                     len(vmware_removed), ", ".join(vmware_removed[:5]))
        except Exception as e:
            result["registry_changes"] = {"success": False, "error": str(e)}
            msg = f"Registry edit failed: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)


def _virtio_remove_vmware_sys_files(self, g: guestfs.GuestFS, result: Dict[str, Any], paths: WindowsSystemPaths) -> None:
    """
    Delete VMware .sys driver files from System32\\drivers to prevent boot errors.
    """
    from .windows_virtio_utils import _step
    logger = _safe_logger(self)
    dry_run = bool(result.get("dry_run"))

    vmware_sys_files = [
        "vm3dmp.sys", "vmmouse.sys", "vmusbmouse.sys", "vmxnet3.sys", "vmxnet.sys",
        "vmhgfs.sys", "vmci.sys", "vmscsi.sys", "pvscsi.sys", "vmmemctl.sys",
        "vsock.sys", "vmrawdsk.sys"
    ]

    deleted = []
    with _step(logger, "🗑️ Remove VMware driver files from System32\\drivers"):
        for sys_file in vmware_sys_files:
            sys_path = f"{paths.drivers_dir}/{sys_file}"
            try:
                if g.is_file(sys_path):
                    if not dry_run:
                        g.rm(sys_path)
                    deleted.append(sys_file)
                    _log(logger, logging.INFO, "Deleted VMware driver: %s", sys_path)
            except Exception as e:
                _log(logger, logging.DEBUG, "VMware driver %s not found or cannot delete: %s", sys_file, e)

    result["vmware_sys_files_deleted"] = deleted
    if deleted:
        _log(logger, logging.INFO, "Removed %d VMware .sys files from System32\\drivers", len(deleted))


def _virtio_update_devicepath(self, g: guestfs.GuestFS, result: Dict[str, Any], paths: WindowsSystemPaths, devicepath_append: str) -> None:
    from .windows_virtio_utils import _step
    logger = _safe_logger(self)
    with _step(logger, "🧩 Update SOFTWARE DevicePath (PnP discovery)"):
        try:
            if result.get("packages_staged"):
                dp_res = append_devicepath_software_hive(self, g, paths.software_hive, devicepath_append)
                result["devicepath_changes"] = dp_res
                if not dp_res.get("success", True):
                    _log(logger, logging.WARNING, "DevicePath update reported errors: %s", dp_res.get("errors"))
            else:
                result["devicepath_changes"] = {"skipped": True, "reason": "no_packages_staged"}
                _log(logger, logging.INFO, "DevicePath: skipped (no packages staged)")
        except Exception as e:
            result["devicepath_changes"] = {"success": False, "error": str(e)}
            msg = f"DevicePath update failed: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)


def _virtio_provision_firstboot(self, g: guestfs.GuestFS, result: Dict[str, Any], paths: WindowsSystemPaths, staging_root: str) -> None:
    from .windows_virtio_utils import _step
    logger = _safe_logger(self)
    if not result.get("packages_staged"):
        result["firstboot"] = {"skipped": True, "reason": "no_packages_staged"}
        return

    log_path_guestfs = f"{paths.temp_dir}/hyper2kvm-firstboot.log"

    with _step(logger, "🛠️ Provision firstboot service (pnputil /install + logging)"):
        try:
            fb = provision_firstboot_payload_and_service(
                self,
                g,
                system_hive_path=paths.system_hive,
                service_name="hyper2kvm-firstboot",
                guest_dir="/hyper2kvm",
                log_path=log_path_guestfs,
                driver_stage_dir=staging_root,
                extra_cmd=None,
                remove_vmware_tools=True,
            )
            result["firstboot"] = fb
            if not fb.get("success", True):
                msg = f"Firstboot provisioning failed: {fb.get('errors')}"
                result["warnings"].append(msg)
                _log(logger, logging.WARNING, "%s", msg)
            else:
                _log(
                    logger,
                    logging.INFO,
                    "Firstboot installed: service=%s log=%s",
                    "hyper2kvm-firstboot",
                    _guestfs_to_windows_path(log_path_guestfs),
                )
        except Exception as e:
            result["firstboot"] = {"success": False, "error": str(e)}
            msg = f"Firstboot provisioning exception: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)


def _virtio_bcd_backup(self, g: guestfs.GuestFS, result: Dict[str, Any]) -> None:
    from .windows_virtio_utils import _step
    # Import here to avoid circular dependency
    from .core import windows_bcd_actual_fix
    logger = _safe_logger(self)
    with _step(logger, "🧷 BCD store discovery + backup"):
        try:
            result["bcd_changes"] = windows_bcd_actual_fix(self, g)
        except Exception as e:
            result["bcd_changes"] = {"windows": True, "bcd": "error", "error": str(e)}
            msg = f"BCD check failed: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)
