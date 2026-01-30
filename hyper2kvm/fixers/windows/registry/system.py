# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/windows/registry/system.py
# -*- coding: utf-8 -*-
"""
SYSTEM hive editing for driver installation and control settings.

This module provides functionality for editing Windows SYSTEM registry hive
to configure driver services, critical device database entries, and system
control settings. It handles:
  - Creating/updating Services entries for drivers
  - Populating CriticalDeviceDatabase for storage controllers
  - Removing StartOverride keys that can disable drivers
  - Setting generic DWORD values in ControlSet paths
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    import guestfs  # type: ignore
else:
    try:
        import guestfs  # type: ignore
    except ImportError:
        guestfs = None  # type: ignore
import hivex  # type: ignore

from ....core.utils import U

# Import registry utilities from sub-modules
from .io import _download_hive_local, _log_mountpoints_best_effort
from .mount import _ensure_windows_root
from .encoding import (
    _close_best_effort,
    _commit_best_effort,
    _delete_child_if_exists,
    _detect_current_controlset,
    _driver_start_default,
    _driver_type_norm,
    _ensure_child,
    _hivex_read_dword,
    _node_id,
    _open_hive_local,
    _pci_id_normalize,
    _set_dword,
    _set_sz,
)

# Import shared logging utilities
from ....core.logging_utils import safe_logger as _safe_logger_base


def _safe_logger(self) -> logging.Logger:
    """Get logger from self or create default logger."""
    return _safe_logger_base(self, "hyper2kvm.registry_system")


# Public: SYSTEM hive edit (Services + CDD + StartOverride)


def _hive_backup_best_effort(
    logger: logging.Logger,
    g: guestfs.GuestFS,
    hive_path: str,
    *,
    dry_run: bool,
    results: Dict[str, Any],
) -> None:
    if dry_run:
        return
    ts = U.now_ts()
    backup_path = f"{hive_path}.hyper2kvm.backup.{ts}"
    g.cp(hive_path, backup_path)
    logger.info("Hive backup created: %s", backup_path)
    results["hive_backup"] = backup_path


def _open_system_hive_local_for_edit(
    logger: logging.Logger,
    g: guestfs.GuestFS,
    hive_path: str,
    *,
    dry_run: bool,
    local_hive: Path,
) -> Dict[str, Any]:
    _download_hive_local(logger, g, hive_path, local_hive)
    return {"sha256_before": hashlib.sha256(local_hive.read_bytes()).hexdigest()}


def _resolve_controlset_node(h: hivex.Hivex, root: int, *, logger: logging.Logger) -> Dict[str, Any]:
    cs_name = _detect_current_controlset(h, root)
    logger.info("Using control set: %s", cs_name)

    cs = _node_id(h.node_get_child(root, cs_name))
    if cs == 0:
        logger.warning("%s missing; falling back to ControlSet001", cs_name)
        cs_name = "ControlSet001"
        cs = _node_id(h.node_get_child(root, cs_name))
        if cs == 0:
            raise RuntimeError("No usable ControlSet found (001/current)")
    return {"controlset_name": cs_name, "controlset_node": cs}


def _service_group_for_driver_type(drv_type_value: str, *, storage_type_norm: str) -> str:
    if str(drv_type_value) == storage_type_norm:
        return "SCSI miniport"
    if str(drv_type_value) == "network":
        return "NDIS"
    return "System Bus Extender"


def _edit_system_services(
    logger: logging.Logger,
    h: hivex.Hivex,
    services_node: int,
    drivers: List[Any],
    *,
    storage_type_norm: str,
    boot_start_value: int,
    results: Dict[str, Any],
) -> None:
    for drv in drivers:
        try:
            drv_type_value = _driver_type_norm(drv)
            svc_name = str(getattr(drv, "service_name"))
            dest_name = str(getattr(drv, "dest_name"))

            start_default = _driver_start_default(drv, fallback=3)
            svc = _node_id(h.node_get_child(services_node, svc_name))
            action = "updated" if svc != 0 else "created"
            if svc == 0:
                svc = _node_id(h.node_add_child(services_node, svc_name))
            if svc == 0:
                raise RuntimeError(f"failed to open/create service key {svc_name}")

            logger.info("Registry service %s: Services\\%s", action, svc_name)

            _set_dword(h, svc, "Type", 1)  # SERVICE_KERNEL_DRIVER
            _set_dword(h, svc, "ErrorControl", 1)

            start = int(start_default)
            if str(drv_type_value) == storage_type_norm:
                start = int(boot_start_value)
            _set_dword(h, svc, "Start", start)

            group = _service_group_for_driver_type(str(drv_type_value), storage_type_norm=storage_type_norm)
            _set_sz(h, svc, "Group", group)
            _set_sz(h, svc, "ImagePath", fr"\SystemRoot\System32\drivers\{dest_name}")
            _set_sz(h, svc, "DisplayName", svc_name)

            removed = _delete_child_if_exists(h, svc, "StartOverride", logger=logger)
            if removed:
                logger.info("Removed StartOverride: Services\\%s\\StartOverride", svc_name)
                results["startoverride_removed"].append(svc_name)

            results["services"].append(
                {
                    "service": svc_name,
                    "type": drv_type_value,
                    "start": start,
                    "group": group,
                    "image": fr"\SystemRoot\System32\drivers\{dest_name}",
                    "action": action,
                }
            )
        except Exception as e:
            msg = f"Failed to create/update service {getattr(drv, 'service_name', '?')}: {e}"
            logger.error(msg)
            results["errors"].append(msg)


def _edit_system_cdd(
    logger: logging.Logger,
    h: hivex.Hivex,
    controlset_node: int,
    drivers: List[Any],
    *,
    storage_type_norm: str,
    results: Dict[str, Any],
) -> None:
    control = _ensure_child(h, controlset_node, "Control")
    cdd = _ensure_child(h, control, "CriticalDeviceDatabase")

    for drv in drivers:
        drv_type_value = _driver_type_norm(drv)
        if str(drv_type_value) != storage_type_norm:
            continue

        svc_name = str(getattr(drv, "service_name"))
        class_guid = str(getattr(drv, "class_guid"))
        dev_name = str(getattr(drv, "name"))

        pci_ids = list(getattr(drv, "pci_ids", []) or [])
        for pci_id in pci_ids:
            pci_id = _pci_id_normalize(pci_id)
            if not pci_id:
                continue
            try:
                node = _node_id(h.node_get_child(cdd, pci_id))
                action = "updated" if node != 0 else "created"
                if node == 0:
                    node = _node_id(h.node_add_child(cdd, pci_id))
                if node == 0:
                    raise RuntimeError(f"failed to open/create CDD node {pci_id}")

                _set_sz(h, node, "Service", svc_name)
                _set_sz(h, node, "ClassGUID", class_guid)
                _set_sz(h, node, "Class", "SCSIAdapter")
                _set_sz(h, node, "DeviceDesc", dev_name)

                logger.info("CDD %s: %s -> %s", action, pci_id, svc_name)
                results["cdd"].append({"pci_id": pci_id, "service": svc_name, "action": action})
            except Exception as e:
                msg = f"Failed CDD entry {pci_id} -> {svc_name}: {e}"
                logger.error(msg)
                results["errors"].append(msg)


def _upload_hive_and_verify(
    logger: logging.Logger,
    g: guestfs.GuestFS,
    hive_path: str,
    local_hive: Path,
    *,
    results: Dict[str, Any],
    sha_before: str,
) -> None:
    logger.info("Uploading modified hive back to guest: %s", hive_path)
    g.upload(str(local_hive), hive_path)

    try:
        results.setdefault("uploaded_files", []).append(
            {"guest_path": hive_path, "sha256_local": hashlib.sha256(local_hive.read_bytes()).hexdigest()}
        )
    except Exception:
        pass

    with tempfile.TemporaryDirectory() as verify_tmp:
        verify_path = Path(verify_tmp) / "HIVE_verify"
        _download_hive_local(logger, g, hive_path, verify_path)
        sha_after = hashlib.sha256(verify_path.read_bytes()).hexdigest()

    results["verification"] = {
        "sha256_before": sha_before,
        "sha256_after": sha_after,
        "changed": (sha_after != sha_before),
    }


def _verify_services_post_write(
    logger: logging.Logger,
    g: guestfs.GuestFS,
    hive_path: str,
    *,
    cs_name: str,
    drivers: List[Any],
    storage_type_norm: str,
    boot_start_value: int,
    results: Dict[str, Any],
) -> None:
    # Best-effort verification: download the hive again, open read-only, and check Start values exist.
    with tempfile.TemporaryDirectory() as verify_dir:
        verify_hive = Path(verify_dir) / "SYSTEM_verify"
        _download_hive_local(logger, g, hive_path, verify_hive)

        vh: Optional[hivex.Hivex] = None
        try:
            vh = _open_hive_local(verify_hive, write=False)
            vroot = _node_id(vh.root())
            vcs = _node_id(vh.node_get_child(vroot, cs_name))
            if vcs == 0:
                vcs = _node_id(vh.node_get_child(vroot, "ControlSet001"))
            vservices = _node_id(vh.node_get_child(vcs, "Services")) if vcs != 0 else 0

            if vservices == 0:
                results["verification_errors"].append("Verification failed: Services node missing")
                return

            for drv in drivers:
                svc_name = str(getattr(drv, "service_name"))
                drv_type_value = _driver_type_norm(drv)
                start_default = _driver_start_default(drv, fallback=3)

                svc = _node_id(vh.node_get_child(vservices, svc_name))
                if svc == 0:
                    results["verification_errors"].append(f"Missing service after edit: {svc_name}")
                    continue

                got = _hivex_read_dword(vh, svc, "Start")
                expected = int(start_default)
                if str(drv_type_value) == storage_type_norm:
                    expected = int(boot_start_value)

                if got == expected:
                    results["verified_services"].append(svc_name)
                else:
                    results["verification_errors"].append(f"{svc_name} Start mismatch: got={got} expected={expected}")
        finally:
            _close_best_effort(vh)


def _remove_vmware_driver_services(
    logger: logging.Logger,
    h: hivex.Hivex,
    services_node: int,
    *,
    results: Dict[str, Any],
) -> None:
    """
    Remove VMware driver service entries from the SYSTEM hive Services key.

    This prevents Windows from showing error messages about missing VMware drivers
    in Device Manager and Event Viewer.

    Args:
        logger: Logger instance
        h: Opened hivex handle
        services_node: Node ID of Services key in ControlSet
        results: Results dict to accumulate vmware_services_removed list
    """
    vmware_drivers = [
        "vm3dmp", "vmmouse", "vmusbmouse", "vmxnet3", "vmxnet",
        "vmhgfs", "vmci", "vmscsi", "pvscsi", "vmmemctl", "vsock",
        "vmrawdsk", "vm3dservice", "vmvss", "VMTools", "VGAuthService",
        "vmware-aliases", "vmtoolsd"
    ]

    removed = results.setdefault("vmware_services_removed", [])

    for svc_name in vmware_drivers:
        try:
            svc_node = _node_id(h.node_get_child(services_node, svc_name))
            if svc_node != 0:
                # Service exists - delete it
                h.node_delete_child(svc_node)
                removed.append(svc_name)
                logger.info(f"Removed VMware service from registry: Services\\{svc_name}")
        except Exception as e:
            # Service doesn't exist or can't be deleted - that's fine
            logger.debug(f"VMware service {svc_name} not found or already removed: {e}")
            pass


def edit_system_hive(
    self,
    g: guestfs.GuestFS,
    hive_path: str,
    drivers: List[Any],
    *,
    driver_type_storage_value: str,
    boot_start_value: int,
) -> Dict[str, Any]:
    """
    Edit SYSTEM hive offline to:
      - Create Services\\<driver> keys with correct Type/Start/ImagePath/Group
      - Add CriticalDeviceDatabase entries for STORAGE drivers
      - Remove StartOverride keys that frequently disable boot drivers
    """
    logger = _safe_logger(self)
    dry_run = bool(getattr(self, "dry_run", False))

    results: Dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "registry_modified": False,
        "hive_path": hive_path,
        "errors": [],
        "services": [],
        "cdd": [],
        "startoverride_removed": [],
        "notes": [],
        "verified_services": [],
        "verification_errors": [],
        "uploaded_files": [],
        "verification": {},
    }

    try:
        _ensure_windows_root(logger, g, hint_hive_path=hive_path)
    except Exception as e:
        results["errors"].append(str(e))
        return results

    try:
        if not g.is_file(hive_path):
            results["errors"].append(f"SYSTEM hive not found: {hive_path}")
            return results
    except Exception as e:
        results["errors"].append(f"Failed to stat hive {hive_path}: {e}")
        return results

    with tempfile.TemporaryDirectory() as tmpdir:
        local_hive = Path(tmpdir) / "SYSTEM"
        h: Optional[hivex.Hivex] = None

        try:
            _log_mountpoints_best_effort(logger, g)
            _hive_backup_best_effort(logger, g, hive_path, dry_run=dry_run, results=results)

            meta = _open_system_hive_local_for_edit(logger, g, hive_path, dry_run=dry_run, local_hive=local_hive)
            sha_before = str(meta.get("sha256_before") or "")

            h = _open_hive_local(local_hive, write=(not dry_run))
            root = _node_id(h.root())
            if root == 0:
                raise RuntimeError("python-hivex root() returned invalid node")

            cs = _resolve_controlset_node(h, root, logger=logger)
            cs_name = str(cs["controlset_name"])
            control_set = int(cs["controlset_node"])

            services = _ensure_child(h, control_set, "Services")
            storage_type_norm = str(driver_type_storage_value)

            _edit_system_services(
                logger,
                h,
                services,
                drivers,
                storage_type_norm=storage_type_norm,
                boot_start_value=int(boot_start_value),
                results=results,
            )
            _edit_system_cdd(
                logger,
                h,
                control_set,
                drivers,
                storage_type_norm=storage_type_norm,
                results=results,
            )

            # Remove VMware drivers from Services to prevent boot errors
            _remove_vmware_driver_services(logger, h, services, results=results)

            if not dry_run:
                try:
                    logger.info("Committing SYSTEM hive changes (python-hivex commit)")
                    _commit_best_effort(h)
                finally:
                    _close_best_effort(h)
                    h = None

                _upload_hive_and_verify(logger, g, hive_path, local_hive, results=results, sha_before=sha_before)
                results["registry_modified"] = bool(results.get("verification", {}).get("changed", False))

                _verify_services_post_write(
                    logger,
                    g,
                    hive_path,
                    cs_name=cs_name,
                    drivers=drivers,
                    storage_type_norm=storage_type_norm,
                    boot_start_value=int(boot_start_value),
                    results=results,
                )
            else:
                logger.info("Dry-run: registry edits computed but not committed/uploaded")

            results["success"] = len(results["errors"]) == 0
            results["notes"] += [
                "Windows root is validated/remounted to ensure C: mapping (prevents writing to wrong partition).",
                "Storage services forced to BOOT start to prevent INACCESSIBLE_BOOT_DEVICE.",
                "StartOverride keys removed (if present) because they can silently disable drivers.",
                "Registry strings written as UTF-16LE REG_SZ/REG_EXPAND_SZ (Windows-correct).",
                "CriticalDeviceDatabase populated for storage PCI IDs.",
                "Node ids normalized across python-hivex versions (0 vs None).",
                "Driver start_type None handled with fallback Start=3 (demand).",
                "Driver type comparisons normalized via _driver_type_norm().",
                "Hive integrity checked via size + 'regf' signature during downloads.",
            ]
            return results

        except Exception as e:
            msg = f"Registry editing failed: {e}"
            logger.error(msg)
            results["errors"].append(msg)
            return results
        finally:
            _close_best_effort(h)


# Public: SYSTEM hive generic DWORD setter (for CrashControl etc.)


def _resolve_controlset_for_path(h: hivex.Hivex, root: int) -> Dict[str, Any]:
    cs_name = _detect_current_controlset(h, root)
    cs = _node_id(h.node_get_child(root, cs_name))
    if cs == 0:
        cs_name = "ControlSet001"
        cs = _node_id(h.node_get_child(root, cs_name))
    if cs == 0:
        raise RuntimeError("No usable ControlSet found (001/current)")
    return {"controlset_name": cs_name, "controlset_node": cs}


def _ensure_key_path(h: hivex.Hivex, start_node: int, key_path: List[str]) -> int:
    node = int(start_node)
    for comp in key_path:
        node = _ensure_child(h, node, comp)
    return node


def set_system_dword(
    self,
    g: guestfs.GuestFS,
    hive_path: str,
    *,
    key_path: List[str],
    name: str,
    value: int,
) -> Dict[str, Any]:
    logger = _safe_logger(self)
    dry_run = bool(getattr(self, "dry_run", False))

    out: Dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "hive_path": hive_path,
        "key_path": list(key_path),
        "name": name,
        "value": int(value),
        "modified": False,
        "original": None,
        "new": None,
        "errors": [],
        "notes": [],
        "uploaded_files": [],
        "verification": {},
    }

    try:
        _ensure_windows_root(logger, g, hint_hive_path=hive_path)
    except Exception as e:
        out["errors"].append(str(e))
        return out

    try:
        if not g.is_file(hive_path):
            out["errors"].append(f"SYSTEM hive not found: {hive_path}")
            return out
    except Exception as e:
        out["errors"].append(f"Failed to stat hive {hive_path}: {e}")
        return out

    with tempfile.TemporaryDirectory() as td:
        local = Path(td) / "SYSTEM"
        h: Optional[hivex.Hivex] = None
        try:
            _log_mountpoints_best_effort(logger, g)
            _hive_backup_best_effort(logger, g, hive_path, dry_run=dry_run, results=out)

            _download_hive_local(logger, g, hive_path, local)
            orig_hash = hashlib.sha256(local.read_bytes()).hexdigest()

            h = _open_hive_local(local, write=(not dry_run))
            root = _node_id(h.root())
            if root == 0:
                out["errors"].append("Invalid hivex root()")
                return out

            cs = _resolve_controlset_for_path(h, root)
            cs_name = str(cs["controlset_name"])
            cs_node = int(cs["controlset_node"])

            node = _ensure_key_path(h, cs_node, list(key_path))

            old = _hivex_read_dword(h, node, name)
            out["original"] = old

            if old != int(value):
                _set_dword(h, node, name, int(value))
                out["modified"] = True
                out["new"] = int(value)
            else:
                out["new"] = old

            if not dry_run:
                try:
                    _commit_best_effort(h)
                finally:
                    _close_best_effort(h)
                    h = None

                g.upload(str(local), hive_path)
                out["uploaded_files"].append(
                    {"guest_path": hive_path, "sha256_local": hashlib.sha256(local.read_bytes()).hexdigest()}
                )

                with tempfile.TemporaryDirectory() as vtd:
                    vlocal = Path(vtd) / "SYSTEM_verify"
                    _download_hive_local(logger, g, hive_path, vlocal)
                    new_hash = hashlib.sha256(vlocal.read_bytes()).hexdigest()

                out["verification"] = {
                    "sha256_before": orig_hash,
                    "sha256_after": new_hash,
                    "changed": (new_hash != orig_hash),
                }
                out["success"] = True
            else:
                out["success"] = True

            out["notes"] += [
                f"ControlSet resolved and edited at: {cs_name}",
                "DWORD written as REG_DWORD (little-endian).",
                "Node ids normalized across python-hivex versions (0 vs None).",
                "Windows root mount validated to ensure correct C: mapping.",
                "Hive integrity checked via size + 'regf' signature during downloads.",
            ]
            return out

        except Exception as e:
            out["errors"].append(f"SYSTEM dword set failed: {e}")
            return out
        finally:
            _close_best_effort(h)
