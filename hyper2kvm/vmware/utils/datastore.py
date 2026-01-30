# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/vmware/utils/datastore.py

"""
Datastore operations, VM discovery, and download-only mode for VMware
"""

from __future__ import annotations

import fnmatch
import re
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# Optional: pyvmomi imports (conditional)
try:
    from pyVmomi import vim  # type: ignore

    PYVMOMI_AVAILABLE = True
except Exception:  # pragma: no cover
    vim = None  # type: ignore
    PYVMOMI_AVAILABLE = False

# HTTP download client
try:
    from ..transports.http_client import HTTPDownloadClient, VMwareError
except Exception:  # pragma: no cover
    HTTPDownloadClient = None  # type: ignore
    try:
        from ...core.exceptions import VMwareError  # type: ignore
    except Exception:  # pragma: no cover

        class VMwareError(RuntimeError):
            pass


# govc helpers
try:
    from ..transports.govc_common import GovcRunner
except Exception:  # pragma: no cover
    GovcRunner = None  # type: ignore


from .utils import ensure_output_dir as _ensure_output_dir

_BACKING_RE = re.compile(r"\[(.+?)\]\s+(.*)")


# Datacenters / Hosts


def _refresh_datacenter_cache(client: Any) -> None:
    _require_pyvmomi(client)
    content = _content(client)
    view = content.viewManager.CreateContainerView(  # type: ignore[attr-defined]
        content.rootFolder, [vim.Datacenter], True
    )
    try:
        dcs = list(view.view)
        names = sorted([str(getattr(dc, "name", "")) for dc in dcs if getattr(dc, "name", None)])
        client._dc_cache = dcs
        client._dc_name_cache = names
    finally:
        try:
            view.Destroy()
        except Exception:
            pass


def list_datacenters(client: Any, *, refresh: bool = False) -> list[str]:
    if refresh or client._dc_name_cache is None:
        _refresh_datacenter_cache(client)
    return list(client._dc_name_cache or [])


def get_datacenter_by_name(client: Any, name: str, *, refresh: bool = False) -> Any:
    if refresh or client._dc_cache is None:
        _refresh_datacenter_cache(client)
    target = (name or "").strip()
    for dc in (client._dc_cache or []):
        if str(getattr(dc, "name", "")).strip() == target:
            return dc
    return None


def datacenter_exists(client: Any, name: str, *, refresh: bool = False) -> bool:
    n = (name or "").strip()
    if not n:
        return False
    return get_datacenter_by_name(client, n, refresh=refresh) is not None


def _refresh_host_cache(client: Any) -> None:
    _require_pyvmomi(client)
    content = _content(client)
    view = content.viewManager.CreateContainerView(  # type: ignore[attr-defined]
        content.rootFolder, [vim.HostSystem], True
    )
    try:
        client._host_name_cache = sorted([str(getattr(h, "name", "")) for h in view.view if getattr(h, "name", None)])
    finally:
        try:
            view.Destroy()
        except Exception:
            pass


def list_host_names(client: Any, *, refresh: bool = False) -> list[str]:
    if refresh or client._host_name_cache is None:
        _refresh_host_cache(client)
    return list(client._host_name_cache or [])


# VM lookup


def get_vm_by_name(client: Any, name: str) -> Any:
    _require_pyvmomi(client)
    n = (name or "").strip()
    if not n:
        return None
    if n in client._vm_obj_by_name_cache:
        return client._vm_obj_by_name_cache[n]

    content = _content(client)
    view = content.viewManager.CreateContainerView(  # type: ignore[attr-defined]
        content.rootFolder, [vim.VirtualMachine], True
    )
    try:
        for vm_obj in view.view:
            if getattr(vm_obj, "name", None) == n:
                client._vm_obj_by_name_cache[n] = vm_obj
                return vm_obj
        return None
    finally:
        try:
            view.Destroy()
        except Exception:
            pass


def vm_to_datacenter(client: Any, vm_obj: Any) -> Any:
    _require_pyvmomi(client)
    obj = vm_obj
    for _ in range(0, 64):
        if obj is None:
            break
        if isinstance(obj, vim.Datacenter):  # type: ignore[attr-defined]
            return obj
        obj = getattr(obj, "parent", None)
    return None


def vm_datacenter_name(client: Any, vm_obj: Any) -> str | None:
    dc = vm_to_datacenter(client, vm_obj)
    if dc is None:
        return None
    name = getattr(dc, "name", None)
    return str(name) if name else None


def resolve_datacenter_for_vm(client: Any, vm_name: str, preferred: str | None) -> str:
    pref = (preferred or "").strip()
    if pref and pref.lower() not in ("auto", "detect", "guess") and datacenter_exists(client, pref, refresh=False):
        return pref

    vm_obj = get_vm_by_name(client, vm_name)
    vm_dc = vm_datacenter_name(client, vm_obj) if vm_obj is not None else None
    if vm_dc and datacenter_exists(client, vm_dc, refresh=False):
        return vm_dc

    _refresh_datacenter_cache(client)
    if pref and pref.lower() not in ("auto", "detect", "guess") and datacenter_exists(client, pref, refresh=False):
        return pref

    if vm_obj is not None:
        vm_dc = vm_datacenter_name(client, vm_obj)
        if vm_dc and datacenter_exists(client, vm_dc, refresh=False):
            return vm_dc

    dcs = list_datacenters(client, refresh=False)
    if len(dcs) == 1:
        return dcs[0]
    raise VMwareError(
        f"Could not resolve datacenter for VM={vm_name!r}. Preferred={pref!r}, VM_dc={vm_dc!r}. "
        f"Available datacenters: {dcs}"
    )


def _vm_runtime_host(client: Any, vm_obj: Any) -> Any:
    rt = getattr(vm_obj, "runtime", None)
    return getattr(rt, "host", None) if rt else None


def _host_parent_compute_name(client: Any, host_obj: Any) -> str | None:
    try:
        parent = getattr(host_obj, "parent", None)
        if parent is None:
            return None
        name = getattr(parent, "name", None)
        return str(name).strip() if name else None
    except Exception:
        return None


def resolve_host_system_for_vm(client: Any, vm_name: str) -> str:
    vm_obj = get_vm_by_name(client, vm_name)
    if vm_obj is None:
        raise VMwareError(f"VM not found: {vm_name!r}")

    host_obj = _vm_runtime_host(client, vm_obj)
    if host_obj is None:
        raise VMwareError(
            f"VM {vm_name!r} has no runtime.host; cannot build vpx compute path. "
            f"Specify opt.compute='host/<cluster>/<host>' or opt.compute='host/<host>'. "
            f"Known hosts: {list_host_names(client, refresh=True)}"
        )

    host_name = str(getattr(host_obj, "name", "") or "").strip()
    if not host_name:
        raise VMwareError(
            f"Could not resolve ESXi host name for VM={vm_name!r}. "
            f"Known hosts: {list_host_names(client, refresh=True)}"
        )

    cr_name = _host_parent_compute_name(client, host_obj)
    if cr_name and cr_name.lower() != host_name.lower():
        return f"host/{cr_name}/{host_name}"
    return f"host/{host_name}"


def resolve_compute_for_vm(client: Any, vm_name: str, preferred: str | None) -> str:
    pref = (preferred or "").strip()
    if not pref or pref.lower() in ("auto", "detect", "guess"):
        return resolve_host_system_for_vm(client, vm_name)
    p = pref.strip().lstrip("/")
    if "/" not in p:
        return f"host/{p}"
    return p


# Datastore parsing + HTTPS /folder download


def parse_backing_filename(file_name: str) -> tuple[str, str]:
    """
    Parse VMware style backing fileName:
      "[datastore] path/to/file.ext" -> ("datastore", "path/to/file.ext")
    """
    m = _BACKING_RE.match(file_name or "")
    if not m:
        raise VMwareError(f"Could not parse backing filename: {file_name}")
    return m.group(1), m.group(2)


def _split_ds_path(path: str) -> tuple[str, str, str]:
    """
    "[ds] folder/file" -> (ds, "folder", "file")
    """
    ds, rel = parse_backing_filename(path)
    rel = (rel or "").lstrip("/")
    folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
    base = rel.rsplit("/", 1)[1] if "/" in rel else rel
    return ds, folder, base


def _resolve_datacenter_for_download(client: Any, dc_name: str | None) -> str:
    """
    Resolve a usable datacenter name for /folder URL construction.
    """
    dc_use = (dc_name or "").strip()
    if dc_use and not datacenter_exists(client, dc_use, refresh=False):
        client.logger.warning("Requested dc_name=%r not found; will auto-resolve", dc_use)
        dc_use = ""

    if dc_use:
        return dc_use

    dcs = list_datacenters(client, refresh=False)
    if len(dcs) == 1:
        return dcs[0]
    if dcs:
        return sorted(dcs)[0]
    raise VMwareError("No datacenters found; cannot build /folder URL")


def download_datastore_file(
    client: Any,
    *,
    datastore: str,
    ds_path: str,
    local_path: Path,
    dc_name: str | None = None,
    on_bytes: Any | None = None,
    chunk_size: int = 1024 * 1024,
    force_https: bool = False,
) -> None:
    """
    Download a single datastore file.

    Preference:
      - normally prefer govc datastore.download when present (unless force_https=True)
      - fallback to HTTPS /folder (session cookie)
    """
    if not force_https:
        g = client._govc()
        if g is not None:
            try:
                g.datastore_download(datastore=datastore, ds_path=ds_path, local_path=local_path)
                return
            except Exception as e:
                client.logger.warning("govc datastore.download failed; falling back to /folder HTTP: %s", e)

    if not client.si:
        raise VMwareError("Not connected to vSphere; cannot download. Call connect() first.")

    dc_use = _resolve_datacenter_for_download(client, dc_name)

    client._http_download_client().download_file(
        datastore=datastore,
        ds_path=ds_path,
        local_path=local_path,
        dc_name=dc_use,
        on_bytes=on_bytes,
        chunk_size=chunk_size,
    )


# Download-only (list via DatastoreBrowser, download via govc/https)


def wait_for_task(client: Any, task: Any) -> None:
    _require_pyvmomi(client)
    while task.info.state not in (vim.TaskInfo.State.success, vim.TaskInfo.State.error):  # type: ignore[attr-defined]
        time.sleep(1)
    if task.info.state == vim.TaskInfo.State.error:  # type: ignore[attr-defined]
        raise VMwareError(str(task.info.error))


def _get_vm_datastore_browser(client: Any, vm_obj: Any) -> Any:
    _require_pyvmomi(client)
    ds = None
    try:
        ds_list = getattr(vm_obj, "datastore", None) or []
        if ds_list:
            ds = ds_list[0]
    except Exception:
        ds = None
    if ds is None:
        raise VMwareError("Could not resolve VM datastore reference (vm.datastore empty)")
    browser = getattr(ds, "browser", None)
    if browser is None:
        raise VMwareError("Datastore has no browser (unexpected)")
    return browser


def _vmx_pathname(client: Any, vm_obj: Any) -> str:
    s = getattr(vm_obj, "summary", None)
    cfg = getattr(s, "config", None) if s else None
    vmx = getattr(cfg, "vmPathName", None) if cfg else None
    if not vmx:
        try:
            files = getattr(getattr(vm_obj, "config", None), "files", None)
            vmx = getattr(files, "vmPathName", None) if files else None
        except Exception:
            vmx = None
    if not vmx:
        raise VMwareError("Could not determine VMX path (summary.config.vmPathName missing)")
    return str(vmx)


def _list_vm_directory_files(client: Any, vm_obj: Any) -> tuple[str, str, list[str]]:
    """
    Returns: (datastore_name, folder_rel, [files...]) where files are relative to folder_rel.
    Uses DatastoreBrowser.SearchDatastoreSubFolders_Task against the VM folder.
    """
    _require_pyvmomi(client)
    vmx = _vmx_pathname(client, vm_obj)
    ds_name, folder_rel, _base = _split_ds_path(vmx)
    folder_rel = folder_rel.strip("/")

    search_root = f"[{ds_name}] {folder_rel}" if folder_rel else f"[{ds_name}]"
    browser = _get_vm_datastore_browser(client, vm_obj)

    q = vim.HostDatastoreBrowserSearchSpec()  # type: ignore[attr-defined]
    q.matchPattern = ["*"]
    q.details = vim.HostDatastoreBrowserFileInfoDetails()  # type: ignore[attr-defined]
    q.details.fileSize = True
    q.details.modification = True
    q.details.fileType = True

    task = browser.SearchDatastoreSubFolders_Task(search_root, q)  # type: ignore[attr-defined]
    wait_for_task(client, task)

    results = getattr(task.info, "result", None) or []
    files: list[str] = []
    for r in results:
        for fi in (getattr(r, "file", None) or []):
            name = str(getattr(fi, "path", "") or "")
            if name:
                files.append(name)

    files = sorted(set(files))
    return ds_name, folder_rel, files


def _glob_any(name: str, globs: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(name, g) for g in globs) if globs else False


def _filter_download_only_files(
    client: Any,
    files: Sequence[str],
    *,
    include_globs: Sequence[str],
    exclude_globs: Sequence[str],
    max_files: int,
) -> list[str]:
    out: list[str] = []
    for f in files:
        if include_globs and not _glob_any(f, include_globs):
            continue
        if exclude_globs and _glob_any(f, exclude_globs):
            continue
        out.append(f)
    if max_files and len(out) > int(max_files):
        raise VMwareError(
            f"Refusing to download {len(out)} files (limit={max_files}). "
            "Tune download_only_max_files / include/exclude globs."
        )
    return out


def _download_selected_files(
    client: Any,
    *,
    selected: Sequence[str],
    out_dir: Path,
    ds_name: str,
    folder_rel: str,
    dc_name: str,
    force_https: bool,
    fail_on_missing: bool,
    log_prefix: str,
) -> None:
    failures: list[str] = []
    for name in selected:
        ds_path = f"{folder_rel}/{name}" if folder_rel else name
        local_path = out_dir / name
        try:
            download_datastore_file(
                client,
                datastore=ds_name,
                ds_path=ds_path,
                local_path=local_path,
                dc_name=dc_name,
                force_https=force_https,
            )
        except Exception as e:
            msg = f"{name}: {e}"
            failures.append(msg)
            if fail_on_missing:
                raise VMwareError(f"{log_prefix} download failed:\n" + "\n".join(failures)) from e
            client.logger.error("%s download failed (non-fatal): %s", log_prefix, msg)

    if failures and fail_on_missing:
        raise VMwareError(f"{log_prefix}: one or more downloads failed:\n" + "\n".join(failures))


def download_only_vm(client: Any, opt: Any) -> Path:
    if not client.si:
        raise VMwareError("Not connected to vSphere; cannot download. Call connect() first.")

    vm_obj = get_vm_by_name(client, opt.vm_name)
    if vm_obj is None:
        raise VMwareError(f"VM not found: {opt.vm_name!r}")

    resolved_dc = resolve_datacenter_for_vm(client, opt.vm_name, opt.datacenter)
    ds_name, folder_rel, files = _list_vm_directory_files(client, vm_obj)

    selected = _filter_download_only_files(
        client,
        files,
        include_globs=tuple(opt.download_only_include_globs or ()),
        exclude_globs=tuple(opt.download_only_exclude_globs or ()),
        max_files=int(opt.download_only_max_files or 0),
    )

    out_dir = _ensure_output_dir(opt.output_dir)

    client.logger.info(
        "Download-only VM folder: dc=%s ds=%s folder=%s files=%d (selected=%d)",
        resolved_dc,
        ds_name,
        folder_rel or ".",
        len(files),
        len(selected),
    )

    _download_selected_files(
        client,
        selected=selected,
        out_dir=out_dir,
        ds_name=ds_name,
        folder_rel=folder_rel,
        dc_name=resolved_dc,
        force_https=False,
        fail_on_missing=bool(opt.download_only_fail_on_missing),
        log_prefix="Download-only",
    )

    client.logger.info("Download-only completed: %s", out_dir)
    return out_dir


def _download_only_vm_force_https(client: Any, opt: Any) -> Path:
    """
    Forced HTTPS /folder fallback. This bypasses govc even if installed.
    """
    if not client.si:
        raise VMwareError("Not connected to vSphere; cannot download. Call connect() first.")

    vm_obj = get_vm_by_name(client, opt.vm_name)
    if vm_obj is None:
        raise VMwareError(f"VM not found: {opt.vm_name!r}")

    resolved_dc = resolve_datacenter_for_vm(client, opt.vm_name, opt.datacenter)
    ds_name, folder_rel, files = _list_vm_directory_files(client, vm_obj)

    selected = _filter_download_only_files(
        client,
        files,
        include_globs=tuple(opt.download_only_include_globs or ()),
        exclude_globs=tuple(opt.download_only_exclude_globs or ()),
        max_files=int(opt.download_only_max_files or 0),
    )

    out_dir = _ensure_output_dir(opt.output_dir)

    client.logger.info(
        "FORCED HTTPS fallback: dc=%s ds=%s folder=%s files=%d (selected=%d)",
        resolved_dc,
        ds_name,
        folder_rel or ".",
        len(files),
        len(selected),
    )

    _download_selected_files(
        client,
        selected=selected,
        out_dir=out_dir,
        ds_name=ds_name,
        folder_rel=folder_rel,
        dc_name=resolved_dc,
        force_https=True,
        fail_on_missing=bool(opt.download_only_fail_on_missing),
        log_prefix="FORCED HTTPS fallback",
    )

    client.logger.info("FORCED HTTPS fallback completed: %s", out_dir)
    return out_dir


# Helper functions (client dependencies)


def _require_pyvmomi(client: Any) -> None:
    if not PYVMOMI_AVAILABLE:
        raise VMwareError("pyvmomi not installed. Install: pip install pyvmomi")


def _content(client: Any) -> Any:
    if not client.si:
        raise VMwareError("Not connected")
    try:
        return client.si.RetrieveContent()
    except Exception as e:
        raise VMwareError(f"Failed to retrieve content: {e}") from e
