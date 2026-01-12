# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/vmware/vsphere_command.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import errno
import fnmatch
import socket
import subprocess
from dataclasses import asdict, is_dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from ..core.exceptions import VMwareError
from ..core.utils import U
from .govc_common import GovcRunner, normalize_ds_path
from .vmware_client import V2VExportOptions, VMwareClient


# --------------------------------------------------------------------------------------
# Exit codes (stable buckets for CI/shell)
# --------------------------------------------------------------------------------------


class VsphereExitCode(IntEnum):
    OK = 0
    UNKNOWN = 1
    USAGE = 2

    AUTH = 10
    NOT_FOUND = 11
    NETWORK = 12
    TOOL_MISSING = 13

    EXTERNAL_TOOL = 20
    VSPHERE_API = 30
    LOCAL_IO = 40

    INTERRUPTED = 130


def _is_usage_error(e: BaseException) -> bool:
    msg = str(e).lower()
    return (
        "unknown action" in msg
        or "missing vs_action" in msg
        or "missing required arg" in msg
        or "argparse" in msg
        or "usage:" in msg
    )


def _is_tool_missing_error(e: BaseException) -> bool:
    msg = str(e).lower()
    return (
        ("govc" in msg and ("not found" in msg or "no such file" in msg))
        or ("ovftool" in msg and ("not found" in msg or "no such file" in msg))
        or ("executable file not found" in msg)
    )


def _is_auth_error(e: BaseException) -> bool:
    msg = str(e).lower()
    needles = [
        "not authenticated",
        "authentication",
        "unauthorized",
        "forbidden",
        "invalid login",
        "no permission",
        "access denied",
        "permission denied",
        "authorization",
    ]
    return any(n in msg for n in needles)


def _is_not_found_error(e: BaseException) -> bool:
    msg = str(e).lower()
    needles = [
        "vm not found",
        "snapshot not found",
        "not found",
        "does not exist",
        "no such file",
        "file not found",
    ]
    return any(n in msg for n in needles)


def _is_network_error(e: BaseException) -> bool:
    if isinstance(e, (socket.timeout, TimeoutError, ConnectionError)):
        return True
    if isinstance(e, OSError) and e.errno in (
        errno.ECONNREFUSED,
        errno.ETIMEDOUT,
        errno.EHOSTUNREACH,
        errno.ENETUNREACH,
        errno.ECONNRESET,
    ):
        return True
    msg = str(e).lower()
    needles = [
        "timed out",
        "timeout",
        "connection refused",
        "connection reset",
        "name or service not known",
        "temporary failure in name resolution",
        "tls",
        "ssl",
        "handshake",
        "certificate verify failed",
    ]
    return any(n in msg for n in needles)


def _is_local_io_error(e: BaseException) -> bool:
    if isinstance(e, OSError) and e.errno in (
        errno.EACCES,
        errno.EPERM,
        errno.ENOSPC,
        errno.EROFS,
        errno.EDQUOT,
    ):
        return True
    msg = str(e).lower()
    needles = ["no space left", "permission denied", "read-only file system"]
    return any(n in msg for n in needles)


def _is_external_tool_error(e: BaseException) -> bool:
    msg = str(e).lower()
    return "govc failed" in msg or "subprocess" in msg


def _classify_exit_code(e: BaseException) -> VsphereExitCode:
    if isinstance(e, KeyboardInterrupt):
        return VsphereExitCode.INTERRUPTED

    # Treat VMwareError as "expected operational failure" buckets.
    if isinstance(e, VMwareError):
        if _is_usage_error(e):
            return VsphereExitCode.USAGE
        if _is_tool_missing_error(e):
            return VsphereExitCode.TOOL_MISSING
        if _is_auth_error(e):
            return VsphereExitCode.AUTH
        if _is_not_found_error(e):
            return VsphereExitCode.NOT_FOUND
        if _is_network_error(e):
            return VsphereExitCode.NETWORK
        if _is_external_tool_error(e):
            return VsphereExitCode.EXTERNAL_TOOL
        return VsphereExitCode.VSPHERE_API

    # Non-VMwareError exceptions
    if _is_usage_error(e):
        return VsphereExitCode.USAGE
    if _is_local_io_error(e):
        return VsphereExitCode.LOCAL_IO
    if _is_network_error(e):
        return VsphereExitCode.NETWORK
    if _is_tool_missing_error(e):
        return VsphereExitCode.TOOL_MISSING

    return VsphereExitCode.UNKNOWN


# --------------------------------------------------------------------------------------
# Small generic helpers
# --------------------------------------------------------------------------------------


def _p(s: Optional[str]) -> Optional[Path]:
    if not s:
        return None
    return Path(s).expanduser()


def _normalize_ds_path(datastore: str, ds_path: str) -> Tuple[str, str]:
    """Backwards-compatible wrapper; real logic lives in govc_common.normalize_ds_path()."""
    return normalize_ds_path(datastore, ds_path)


def _arg_any(args: Any, *names: str, default: Any = None) -> Any:
    """
    Return the first present, non-empty attribute from args among names.
    Useful to support legacy flags without infecting code with suffixes like "2".
    """
    for n in names:
        if not n:
            continue
        v = getattr(args, n, None)
        if v not in (None, ""):
            return v
    return default


def _require(args: Any, name: str) -> Any:
    """
    Validate that argparse-like object has attribute AND it is non-None.
    Keep this for action-specific required args (not global argparse requirements).
    """
    if not hasattr(args, name):
        raise VMwareError(f"Missing required arg: {name}")
    v = getattr(args, name)
    if v is None:
        raise VMwareError(f"Missing required arg: {name}")
    return v


def _merged_cfg(args: Any, conf: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge CLI + YAML config into a single dict for VMwareClient.from_config().
    CLI overrides config. We also populate vs_* aliases for compat.
    """
    cfg: Dict[str, Any] = dict(conf or {})

    vcenter = getattr(args, "vcenter", None)
    vc_user = getattr(args, "vc_user", None)
    vc_password = getattr(args, "vc_password", None)
    vc_password_env = getattr(args, "vc_password_env", None)
    vc_port = getattr(args, "vc_port", None)
    vc_insecure = getattr(args, "vc_insecure", None)
    dc_name = getattr(args, "dc_name", None)

    cfg.update(
        {
            # canonical
            "vcenter": vcenter,
            "vc_user": vc_user,
            "vc_password": vc_password,
            "vc_password_env": vc_password_env,
            "vc_port": vc_port,
            "vc_insecure": vc_insecure,
            "dc_name": dc_name,
            # aliases (historical)
            "vs_host": vcenter,
            "vs_user": vc_user,
            "vs_password": vc_password,
            "vs_password_env": vc_password_env,
            "vs_port": vc_port,
            "vs_insecure": vc_insecure,
        }
    )

    # Drop None so config can still supply defaults
    return {k: v for k, v in cfg.items() if v is not None}


def _as_payload(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    return obj


# --------------------------------------------------------------------------------------
# Output policy (single source of truth)
# --------------------------------------------------------------------------------------


class _Emitter:
    """
    Exactly one output style per action:
      - --json => print JSON payload only
      - non-json => log human lines (or a single human message)
    """

    def __init__(self, args: Any, logger: Any):
        self.args = args
        self.logger = logger

    def json_enabled(self) -> bool:
        return bool(getattr(self.args, "json", False))

    def emit(
        self,
        payload: Any,
        *,
        human: Optional[Iterable[str]] = None,
        human_msg: Optional[str] = None,
    ) -> None:
        payload = _as_payload(payload)
        if self.json_enabled():
            print(U.json_dump(payload))
            return

        if human is not None:
            for line in human:
                self.logger.info("%s", line)
            return

        if human_msg:
            self.logger.info("%s", human_msg)
            return

        # fallback (still non-json, but structured)
        self.logger.info("%s", U.json_dump(payload))


# --------------------------------------------------------------------------------------
# govc adapter (centralized subprocess execution)
# --------------------------------------------------------------------------------------


class GovmomiCLI(GovcRunner):
    """
    Best-effort integration with govmomi CLI (`govc`).

    Preference policy (unchanged):
      - If govc exists AND user didn't disable it: prefer it for
          * list_vm_names
          * download_datastore_file
          * datastore_ls / download_datastore_dir
      - Everything else stays in VMwareClient/pyvmomi.
    """

    def __init__(self, args: Any, logger: Any):
        super().__init__(logger=logger, args=args)

    def _run_text(self, argv: List[str]) -> str:
        """
        Centralized subprocess runner for text output.
        We intentionally do NOT scatter subprocess.run across the file.
        """
        full = [self.govc_bin] + list(argv)
        try:
            self.logger.debug("govc: %s", " ".join(full))
        except Exception:
            pass

        p = subprocess.run(
            full,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.env(),
            text=True,
        )
        if p.returncode != 0:
            raise VMwareError(f"govc failed ({p.returncode}): {p.stderr.strip()}")
        return p.stdout or ""

    def list_vm_names(self) -> List[str]:
        """
        Prefer: govc find -type m -json .
        Returns VM *names* (basename of inventory paths).
        """
        data = self.run_json(["find", "-type", "m", "-json", "."]) or {}
        elems = data.get("Elements") or []
        if not isinstance(elems, list):
            elems = []
        names = [str(p).split("/")[-1] for p in elems if p]
        return sorted({n for n in names if n})

    def download_datastore_file(self, datastore: str, ds_path: str, local_path: Path) -> None:
        """
        govc datastore.download -ds <datastore> <remote> <local>
        """
        local_path.parent.mkdir(parents=True, exist_ok=True)

        ds, remote = normalize_ds_path(datastore, ds_path)
        if not remote:
            raise VMwareError("govc datastore.download: empty ds_path after normalization")

        self._run_text(["datastore.download", "-ds", str(ds), remote, str(local_path)])

    def _extract_names_from_ls_json(self, files: Any) -> List[str]:
        """
        Robust extraction of leaf names from govc datastore.ls -json output.
        Shapes vary across govc versions and flags.
        """
        out: List[str] = []
        if files is None:
            return out

        if isinstance(files, list):
            items = files
        elif isinstance(files, dict):
            items = []
            for k in ("Files", "files", "File", "file", "Elements", "elements"):
                v = files.get(k)
                if isinstance(v, list):
                    items = v
                    break
        else:
            items = []

        for it in items:
            if it is None:
                continue
            if isinstance(it, str):
                out.append(Path(it).name)
                continue
            if isinstance(it, dict):
                for k in ("Name", "name", "Path", "path", "File", "file"):
                    v = it.get(k)
                    if isinstance(v, str) and v.strip():
                        out.append(Path(v).name)
                        break
                continue
            out.append(Path(str(it)).name)

        seen = set()
        uniq: List[str] = []
        for n in out:
            if n and n not in seen:
                uniq.append(n)
                seen.add(n)
        return uniq

    def datastore_ls_names(self, datastore: str, ds_dir: str) -> List[str]:
        """
        govc datastore.ls -json -ds <datastore> <dir/>
        Returns *leaf names* (non-recursive).
        """
        files = self.datastore_ls_json(datastore=datastore, ds_dir=ds_dir)
        return self._extract_names_from_ls_json(files)

    def download_datastore_dir(
        self,
        datastore: str,
        ds_dir: str,
        local_dir: Path,
        *,
        include_globs: Tuple[str, ...] = ("*",),
        exclude_globs: Tuple[str, ...] = (),
        max_files: int = 5000,
    ) -> Dict[str, Any]:
        """
        Non-recursive directory download using:
          - govc datastore.ls -json
          - govc datastore.download (per file)
        """
        ds, rel_dir = normalize_ds_path(datastore, ds_dir)
        rel_dir = rel_dir.rstrip("/") + "/"
        local_dir.mkdir(parents=True, exist_ok=True)

        names = self.datastore_ls_names(ds, rel_dir)

        picked: List[str] = []
        for n in names:
            ok = True
            if include_globs:
                ok = any(fnmatch.fnmatch(n, g) for g in include_globs)
            if ok and exclude_globs and any(fnmatch.fnmatch(n, g) for g in exclude_globs):
                ok = False
            if ok:
                picked.append(n)
            if len(picked) >= int(max_files or 5000):
                break

        for n in picked:
            remote = rel_dir + n
            dst = local_dir / n
            self.download_datastore_file(ds, remote, dst)

        return {
            "ok": True,
            "provider": "govc",
            "datastore": str(ds),
            "ds_dir": rel_dir,
            "local_dir": str(local_dir),
            "files_total": len(names),
            "files_downloaded": len(picked),
            "files": picked,
        }


def _prefer_govc(args: Any, logger: Any) -> Optional[GovmomiCLI]:
    g = GovmomiCLI(args=args, logger=logger)
    return g if g.enabled() else None


# --------------------------------------------------------------------------------------
# Snapshot helpers (normalize snapshot object type)
# --------------------------------------------------------------------------------------


def _find_snapshot_tree_by_name(vm_obj: Any, name: str) -> Optional[Any]:
    target = (name or "").strip()
    if not target:
        return None

    snap = getattr(vm_obj, "snapshot", None)
    roots = getattr(snap, "rootSnapshotList", None) if snap else None
    if not roots:
        return None

    stack = list(roots)
    while stack:
        node = stack.pop()
        if str(getattr(node, "name", "") or "") == target:
            return node
        kids = getattr(node, "childSnapshotList", None) or []
        stack.extend(list(kids))
    return None


def _snapshot_ref_from_tree(node: Any) -> Any:
    snap = getattr(node, "snapshot", None)
    return snap if snap is not None else node


class VsphereCommands:
    def __init__(self, client: VMwareClient, args: Any):
        self.client = client
        self.args = args
        self.logger = client.logger
        self.emit = _Emitter(args, self.logger)

    # ---- shared helpers ----

    def _vm_or_raise(self, vm_name: str) -> Any:
        vm = self.client.get_vm_by_name(vm_name)
        if vm is None:
            raise VMwareError(f"VM not found: {vm_name!r}")
        return vm

    def _govc(self) -> Optional[GovmomiCLI]:
        return _prefer_govc(self.args, self.logger)

    def _govc_try(self, op: Callable[[GovmomiCLI], Any], *, warn: str) -> Tuple[bool, Any]:
        g = self._govc()
        if not g:
            return (False, None)
        try:
            return (True, op(g))
        except Exception as e:
            self.logger.warning("%s: %s", warn, e)
            return (False, None)

    def _vm_summary_payload(self, vm: Any) -> Dict[str, Any]:
        s = getattr(vm, "summary", None)
        cfg = getattr(s, "config", None) if s else None
        runtime = getattr(s, "runtime", None) if s else None
        guest = getattr(s, "guest", None) if s else None

        return {
            "name": getattr(vm, "name", None),
            "moId": getattr(vm, "_moId", None),
            "uuid": getattr(cfg, "uuid", None),
            "instanceUuid": getattr(cfg, "instanceUuid", None),
            "powerState": str(getattr(runtime, "powerState", None)),
            "guestFullName": getattr(guest, "guestFullName", None),
            "vmPathName": getattr(cfg, "vmPathName", None),
            "datacenter": self.client.vm_datacenter_name(vm),
            "esx_host": getattr(getattr(getattr(vm, "runtime", None), "host", None), "name", None),
        }

    def _disk_payload(self, device: Any, index: int) -> Dict[str, Any]:
        label = getattr(getattr(device, "deviceInfo", None), "label", None)
        key = getattr(device, "key", None)
        cap = getattr(device, "capacityInKB", None)
        backing = getattr(device, "backing", None)
        fname = getattr(backing, "fileName", None) if backing else None
        return {
            "index": index,
            "label": str(label) if label else None,
            "device_key": int(key) if key is not None else None,
            "capacity_kb": int(cap) if cap is not None else None,
            "backing_file": str(fname) if fname else None,
        }

    def _selected_disk_payload(self, vm_name: str, selector: Any, device: Any) -> Dict[str, Any]:
        label = getattr(getattr(device, "deviceInfo", None), "label", None)
        key = getattr(device, "key", None)
        backing = getattr(device, "backing", None)
        fname = getattr(backing, "fileName", None) if backing else None
        return {
            "vm": vm_name,
            "selector": selector,
            "label": str(label) if label else None,
            "device_key": int(key) if key is not None else None,
            "backing_file": str(fname) if fname else None,
        }

    def _resolve_snapshot_ref(self, vm: Any, snapshot_name: str) -> Any:
        node = _find_snapshot_tree_by_name(vm, snapshot_name)
        if node is None:
            raise VMwareError(f"Snapshot not found by name: {snapshot_name!r}")
        return _snapshot_ref_from_tree(node)

    # ---- actions ----

    def list_vm_names(self) -> Any:
        used, names = self._govc_try(
            lambda g: g.list_vm_names(),
            warn="govc list_vm_names failed; falling back to pyvmomi",
        )
        provider = "govc" if used else "pyvmomi"
        if not used:
            names = self.client.list_vm_names()

        payload = {"vms": names, "provider": provider}
        self.emit.emit(payload, human=names)
        return names

    def get_vm_by_name(self) -> Any:
        name = _require(self.args, "name")
        vm = self._vm_or_raise(name)
        out = self._vm_summary_payload(vm)
        self.emit.emit(out)
        return out

    def vm_disks(self) -> Any:
        vm_name = _require(self.args, "vm_name")
        vm = self._vm_or_raise(vm_name)
        disks = self.client.vm_disks(vm)
        out = [self._disk_payload(d, i) for i, d in enumerate(disks)]
        payload = {"vm": vm_name, "disks": out}
        self.emit.emit(payload)
        return out

    def select_disk(self) -> Any:
        vm_name = _require(self.args, "vm_name")
        selector = getattr(self.args, "label_or_index", None)
        vm = self._vm_or_raise(vm_name)
        d = self.client.select_disk(vm, selector)
        out = self._selected_disk_payload(vm_name, selector, d)
        self.emit.emit(out)
        return out

    def download_datastore_file(self) -> Any:
        datastore = _require(self.args, "datastore")
        ds_path = _require(self.args, "ds_path")
        local_path = Path(_require(self.args, "local_path")).expanduser()
        chunk_size = int(getattr(self.args, "chunk_size", 1024 * 1024) or 1024 * 1024)
        dc_name = getattr(self.args, "dc_name", None)

        used, _ = self._govc_try(
            lambda g: g.download_datastore_file(datastore=datastore, ds_path=ds_path, local_path=local_path),
            warn="govc download_datastore_file failed; falling back to pyvmomi",
        )
        if used:
            out = {"ok": True, "local_path": str(local_path), "provider": "govc"}
            self.emit.emit(out, human_msg=str(local_path))
            return out

        self.client.download_datastore_file(
            datastore=datastore,
            ds_path=ds_path,
            local_path=local_path,
            dc_name=dc_name,
            chunk_size=chunk_size,
        )
        out = {"ok": True, "local_path": str(local_path), "provider": "pyvmomi"}
        self.emit.emit(out, human_msg=str(local_path))
        return out

    def datastore_ls(self) -> Any:
        datastore = _require(self.args, "datastore")
        ds_dir = _require(self.args, "ds_dir")

        govc = self._govc()
        if not govc:
            raise VMwareError("datastore_ls requires govc (install govc or disable this action)")

        files = govc.datastore_ls_json(datastore=datastore, ds_dir=ds_dir)
        names = govc._extract_names_from_ls_json(files)

        out = {"ok": True, "provider": "govc", "datastore": datastore, "ds_dir": ds_dir, "files": files}
        self.emit.emit(out, human=names)
        return out

    def download_datastore_dir(self) -> Any:
        datastore = _require(self.args, "datastore")
        ds_dir = _require(self.args, "ds_dir")
        local_dir = Path(_require(self.args, "local_dir")).expanduser()

        include_globs = tuple(getattr(self.args, "include_glob", None) or []) or ("*",)
        exclude_globs = tuple(getattr(self.args, "exclude_glob", None) or []) or ()
        max_files = int(getattr(self.args, "max_files", 5000) or 5000)

        govc = self._govc()
        if not govc:
            raise VMwareError("download_datastore_dir requires govc (install govc or disable this action)")

        res = govc.download_datastore_dir(
            datastore=datastore,
            ds_dir=ds_dir,
            local_dir=local_dir,
            include_globs=include_globs,
            exclude_globs=exclude_globs,
            max_files=max_files,
        )
        self.emit.emit(res, human=res.get("files") or [])
        return res

    def create_snapshot(self) -> Any:
        vm_name = _require(self.args, "vm_name")
        snap_name = _require(self.args, "name")
        quiesce = bool(getattr(self.args, "quiesce", True))
        memory = bool(getattr(self.args, "memory", False))
        description = getattr(self.args, "description", "Created by hyper2kvm") or "Created by hyper2kvm"

        vm = self._vm_or_raise(vm_name)
        snap = self.client.create_snapshot(vm, snap_name, quiesce=quiesce, memory=memory, description=description)

        out = {"ok": True, "vm": vm_name, "snapshot_name": snap_name, "snapshot_moref": self.client.snapshot_moref(snap)}
        self.emit.emit(out)
        return out

    def enable_cbt(self) -> Any:
        vm_name = _require(self.args, "vm_name")
        vm = self._vm_or_raise(vm_name)

        self.client.enable_cbt(vm)
        out = {"ok": True, "vm": vm_name, "cbt_enabled": True}
        self.emit.emit(out)
        return out

    def query_changed_disk_areas(self) -> Any:
        vm_name = _require(self.args, "vm_name")
        snapshot_name = _require(self.args, "snapshot_name")
        start_offset = int(getattr(self.args, "start_offset", 0) or 0)
        change_id = str(getattr(self.args, "change_id", "*") or "*")

        device_key = getattr(self.args, "device_key", None)
        disk_sel = getattr(self.args, "disk", None)

        vm = self._vm_or_raise(vm_name)
        snapshot_ref = self._resolve_snapshot_ref(vm, snapshot_name)

        if device_key is None:
            d = self.client.select_disk(vm, disk_sel)
            device_key = int(getattr(d, "key", 0) or 0)
            if not device_key:
                raise VMwareError("Could not resolve device_key from selected disk")

        r = self.client.query_changed_disk_areas(
            vm,
            snapshot=snapshot_ref,
            device_key=int(device_key),
            start_offset=start_offset,
            change_id=change_id,
        )

        out = {
            "vm": vm_name,
            "snapshot": snapshot_name,
            "device_key": int(device_key),
            "start_offset": start_offset,
            "change_id": change_id,
            "changedArea_count": len(getattr(r, "changedArea", []) or []),
            "length": int(getattr(r, "length", 0) or 0),
        }
        self.emit.emit(out)
        return out

    def download_vm_disk(self) -> Any:
        vm_name = _require(self.args, "vm_name")
        disk_sel = getattr(self.args, "disk", None)
        local_path = Path(_require(self.args, "local_path")).expanduser()
        chunk_size = int(getattr(self.args, "chunk_size", 1024 * 1024) or 1024 * 1024)

        vm = self._vm_or_raise(vm_name)
        d = self.client.select_disk(vm, disk_sel)

        backing = self.client._vm_disk_backing_filename(d)  # usually "[datastore] folder/file.vmdk"
        ds_name, rel_path = self.client.parse_backing_filename(backing)

        used, _ = self._govc_try(
            lambda g: g.download_datastore_file(datastore=ds_name, ds_path=rel_path, local_path=local_path),
            warn="govc download_vm_disk failed; falling back to pyvmomi",
        )
        if used:
            out = {
                "ok": True,
                "vm": vm_name,
                "disk": disk_sel,
                "remote": backing,
                "local_path": str(local_path),
                "provider": "govc",
            }
            self.emit.emit(out, human_msg=str(local_path))
            return out

        dc = self.client.resolve_datacenter_for_vm(vm_name, getattr(self.args, "dc_name", None))
        self.client.download_datastore_file(
            datastore=ds_name,
            ds_path=rel_path,
            local_path=local_path,
            dc_name=dc,
            chunk_size=chunk_size,
        )

        out = {
            "ok": True,
            "vm": vm_name,
            "disk": disk_sel,
            "remote": backing,
            "local_path": str(local_path),
            "provider": "pyvmomi",
        }
        self.emit.emit(out, human_msg=str(local_path))
        return out

    def cbt_sync(self) -> Any:
        """
        Scaffold: enable CBT + snapshot + one-shot QueryChangedDiskAreas summary.
        (Real delta patching requires VDDK/NBD reads + applying extents into the base image.)
        """
        vm_name = _require(self.args, "vm_name")
        disk_sel = getattr(self.args, "disk", None)
        local_path = Path(_require(self.args, "local_path")).expanduser()
        enable = bool(getattr(self.args, "enable_cbt", False))
        snapshot_name = getattr(self.args, "snapshot_name", "hyper2kvm-cbt") or "hyper2kvm-cbt"
        change_id = str(getattr(self.args, "change_id", "*") or "*")

        vm = self._vm_or_raise(vm_name)

        if enable:
            self.client.enable_cbt(vm)

        snap = self.client.create_snapshot(vm, snapshot_name, quiesce=True, memory=False)

        d = self.client.select_disk(vm, disk_sel)
        device_key = int(getattr(d, "key", 0) or 0)
        if not device_key:
            raise VMwareError("Could not resolve device_key for selected disk")

        # base pull so you at least have a consistent local artifact
        self.download_vm_disk_with(vm_name=vm_name, disk_sel=disk_sel, local_path=local_path)

        r = self.client.query_changed_disk_areas(
            vm,
            snapshot=snap,
            device_key=device_key,
            start_offset=0,
            change_id=change_id,
        )

        out = {
            "ok": True,
            "vm": vm_name,
            "disk": disk_sel,
            "snapshot_moref": self.client.snapshot_moref(snap),
            "device_key": device_key,
            "change_id": change_id,
            "changedArea_count": len(getattr(r, "changedArea", []) or []),
        }
        self.emit.emit(out)
        return out

    def download_vm_disk_with(self, *, vm_name: str, disk_sel: Any, local_path: Path) -> Any:
        """
        Internal reuse helper: call download_vm_disk logic without mutating self.args.
        """
        shim = _ArgsShim(
            vm_name=vm_name,
            disk=disk_sel,
            local_path=str(local_path),
            chunk_size=1024 * 1024,
            dc_name=getattr(self.args, "dc_name", None),
            json=getattr(self.args, "json", False),
            vcenter=getattr(self.args, "vcenter", None),
            vc_user=getattr(self.args, "vc_user", None),
            vc_password=getattr(self.args, "vc_password", None),
            vc_password_env=getattr(self.args, "vc_password_env", None),
            vc_insecure=getattr(self.args, "vc_insecure", None),
            govc_bin=getattr(self.args, "govc_bin", None),
            no_govmomi=getattr(self.args, "no_govmomi", False),
        )
        tmp = VsphereCommands(self.client, shim)
        return tmp.download_vm_disk()

    def download_only_vm(self) -> Any:
        vm_name = _require(self.args, "vm_name")
        out_dir = getattr(self.args, "output_dir", None) or getattr(self.args, "output_dir", "./out")
        out_dir_path = Path(out_dir).expanduser()

        include_globs = tuple(getattr(self.args, "vs_include_glob", None) or []) or ("*",)
        exclude_globs = tuple(getattr(self.args, "vs_exclude_glob", None) or []) or ()

        opt = V2VExportOptions(
            vm_name=vm_name,
            export_mode="download_only",
            output_dir=out_dir_path,
            datacenter=getattr(self.args, "dc_name", "auto") or "auto",
            download_only_include_globs=include_globs,
            download_only_exclude_globs=exclude_globs,
            download_only_concurrency=int(getattr(self.args, "vs_concurrency", 4) or 4),
            download_only_max_files=int(getattr(self.args, "vs_max_files", 5000) or 5000),
            download_only_use_async_http=bool(getattr(self.args, "vs_use_async_http", True)),
            download_only_fail_on_missing=bool(getattr(self.args, "vs_fail_on_missing", False)),
        )

        res = self.client.export_vm(opt)
        out = {"ok": True, "vm": vm_name, "output_dir": str(res)}
        self.emit.emit(out, human_msg=str(res))
        return out

    def vddk_download_disk(self) -> Any:
        vm_name = _require(self.args, "vm_name")
        disk_sel = getattr(self.args, "disk", None)
        local_path = Path(_require(self.args, "local_path")).expanduser()

        # accept both new and legacy flag names
        vddk_libdir = _p(_arg_any(self.args, "vddk_libdir", "vs_vddk_libdir2"))
        vddk_thumbprint = _arg_any(self.args, "vddk_thumbprint", "vs_vddk_thumbprint2")
        vddk_transports = _arg_any(self.args, "vddk_transports", "vs_vddk_transports2")
        no_verify = bool(_arg_any(self.args, "no_verify", "vs_no_verify2", default=False))

        opt = V2VExportOptions(
            vm_name=vm_name,
            export_mode="vddk_download",
            output_dir=local_path.parent,
            vddk_download_disk=disk_sel,
            vddk_download_output=local_path,
            vddk_libdir=vddk_libdir,
            vddk_thumbprint=vddk_thumbprint,
            vddk_transports=vddk_transports,
            no_verify=no_verify,
        )

        res = self.client.export_vm(opt)
        out = {"ok": True, "vm": vm_name, "disk": disk_sel, "local_path": str(res)}
        self.emit.emit(out, human_msg=str(res))
        return out


class _ArgsShim:
    """Tiny shim so we can reuse action funcs without argparse objects."""

    def __init__(self, **kw: Any):
        for k, v in kw.items():
            setattr(self, k, v)


# --------------------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------------------


_ACTIONS: Dict[str, str] = {
    "list_vm_names": "list_vm_names",
    "get_vm_by_name": "get_vm_by_name",
    "vm_disks": "vm_disks",
    "select_disk": "select_disk",
    "download_datastore_file": "download_datastore_file",
    "datastore_ls": "datastore_ls",
    "download_datastore_dir": "download_datastore_dir",
    "create_snapshot": "create_snapshot",
    "enable_cbt": "enable_cbt",
    "query_changed_disk_areas": "query_changed_disk_areas",
    "download_vm_disk": "download_vm_disk",
    "cbt_sync": "cbt_sync",
    "download_only_vm": "download_only_vm",
    "vddk_download_disk": "vddk_download_disk",
}


def _get_action_or_raise(args: Any) -> str:
    action = getattr(args, "vs_action", None)
    if not action:
        raise VMwareError("Missing vs_action (argparse should have required=True)")
    action = str(action)
    if action not in _ACTIONS:
        raise VMwareError(f"vsphere: unknown action: {action}")
    return action


def _build_client(args: Any, conf: Optional[Dict[str, Any]], logger: Any) -> VMwareClient:
    cfg = _merged_cfg(args, conf)
    return VMwareClient.from_config(
        logger=logger,
        cfg=cfg,
        port=getattr(args, "vc_port", None),
        insecure=getattr(args, "vc_insecure", None),
        timeout=None,
    )


def run_vsphere_command(args: Any, conf: Optional[Dict[str, Any]], logger: Any) -> int:
    """
    Entry point for: hyper2kvm.py vsphere <action> ...
    Returns structured exit codes suitable for shell/CI.
    """
    try:
        action = _get_action_or_raise(args)
        client = _build_client(args, conf, logger)

        with client:
            cmd = VsphereCommands(client, args)
            meth_name = _ACTIONS[action]
            meth = getattr(cmd, meth_name, None)
            if not callable(meth):
                raise VMwareError(f"vsphere: action not callable: {action} -> {meth_name}")
            meth()

        return int(VsphereExitCode.OK)

    except KeyboardInterrupt:
        logger.warning("Interrupted by user (Ctrl+C).")
        return int(VsphereExitCode.INTERRUPTED)

    except VMwareError as e:
        code = _classify_exit_code(e)
        logger.error("vsphere command failed (%s): %s", code.name, e)
        return int(code)

    except Exception as e:
        code = _classify_exit_code(e)
        logger.exception("vsphere command crashed (%s): %s", code.name, e)
        return int(code)
