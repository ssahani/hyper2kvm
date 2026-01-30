# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/vmware/transports/vddk_loader.py
"""
VDDK disk download orchestration for VMware
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Import VMwareError
try:
    from .http_client import VMwareError
except Exception:  # pragma: no cover
    try:
        from ...core.exceptions import VMwareError  # type: ignore
    except Exception:  # pragma: no cover

        class VMwareError(Exception):  # type: ignore
            pass


# Import ExportOptions
try:
    from ..clients.client import ExportOptions, _safe_vm_name
except Exception:  # pragma: no cover
    ExportOptions = None  # type: ignore
    _safe_vm_name = None  # type: ignore

# Import pyvmomi (vim)
try:
    from pyVmomi import vim  # type: ignore

    PYVMOMI_AVAILABLE = True
except Exception:  # pragma: no cover
    vim = None  # type: ignore
    PYVMOMI_AVAILABLE = False

# ✅ VDDK client (ALL heavy logic in vddk_client.py)
try:
    from .vddk_client import VDDKConnectionSpec, VDDKESXClient  # type: ignore

    VDDK_CLIENT_AVAILABLE = True
except Exception:  # pragma: no cover
    VDDKConnectionSpec = None  # type: ignore
    VDDKESXClient = None  # type: ignore
    VDDK_CLIENT_AVAILABLE = False


def _require_vddk_client() -> None:
    if not VDDK_CLIENT_AVAILABLE:
        raise VMwareError(
            "VDDK raw download requested but vddk_client is not importable. "
            "Ensure hyper2kvm/vsphere/vddk_client.py exists and imports cleanly."
        )


def vm_disks(client: Any, vm_obj: Any) -> list[Any]:
    disks: list[Any] = []
    devices = getattr(getattr(getattr(vm_obj, "config", None), "hardware", None), "device", []) or []
    for dev in devices:
        if isinstance(dev, vim.vm.device.VirtualDisk):  # type: ignore[attr-defined]
            disks.append(dev)
    return disks


def select_disk(client: Any, vm_obj: Any, label_or_index: str | None) -> Any:
    disks = vm_disks(client, vm_obj)
    if not disks:
        raise VMwareError("No virtual disks found on VM")
    if label_or_index is None:
        return disks[0]
    s = str(label_or_index).strip()
    if s.isdigit():
        idx = int(s)
        if idx < 0 or idx >= len(disks):
            raise VMwareError(f"Disk index out of range: {idx} (found {len(disks)})")
        return disks[idx]
    sl = s.lower()
    for d in disks:
        label = getattr(getattr(d, "deviceInfo", None), "label", "") or ""
        if sl in str(label).lower():
            return d
    raise VMwareError(f"No disk matching label: {s}")


def _vm_disk_backing_filename(client: Any, disk_obj: Any) -> str:
    backing = getattr(disk_obj, "backing", None)
    fn = getattr(backing, "fileName", None) if backing else None
    if not fn:
        raise VMwareError("Selected disk has no backing.fileName (unexpected)")
    return str(fn)


def _resolve_esx_host_for_vm(client: Any, vm_obj: Any) -> str:
    host_obj = client._vm_runtime_host(vm_obj)
    if host_obj is None:
        raise VMwareError("VM has no runtime.host; cannot determine ESXi host for VDDK download")
    name = str(getattr(host_obj, "name", "") or "").strip()
    if not name:
        raise VMwareError("Could not resolve ESXi host name for VM runtime.host")
    return name


def _default_vddk_download_path(client: Any, opt: ExportOptions, *, disk_index: int) -> Path:
    out_dir = client._ensure_output_dir(opt.output_dir)
    return out_dir / f"{_safe_vm_name(opt.vm_name)}-disk{disk_index}.vmdk"


def vddk_download_disk(client: Any, opt: ExportOptions) -> Path:
    """
    export_mode="vddk_download" (EXPERIMENTAL)
      - control-plane: pyvmomi finds ESXi host + disk backing path
      - data-plane: vddk_client.VDDKESXClient reads and writes local file
    """
    _require_vddk_client()
    if not client.si:
        raise VMwareError("Not connected to vSphere; cannot download. Call connect() first.")

    vm_obj = client.get_vm_by_name(opt.vm_name)
    if vm_obj is None:
        raise VMwareError(f"VM not found: {opt.vm_name!r}")

    disk_obj = select_disk(client, vm_obj, opt.vddk_download_disk)
    try:
        disks = vm_disks(client, vm_obj)
        disk_index = disks.index(disk_obj)
    except Exception:
        disk_index = 0

    remote_vmdk = _vm_disk_backing_filename(client, disk_obj)  # "[ds] folder/disk.vmdk"
    esx_host = _resolve_esx_host_for_vm(client, vm_obj)

    local_path = (
        Path(opt.vddk_download_output)
        if opt.vddk_download_output
        else _default_vddk_download_path(client, opt, disk_index=disk_index)
    )

    spec = VDDKConnectionSpec(  # type: ignore[misc]
        host=esx_host,
        user=client.user,
        password=client.password,
        port=443,
        vddk_libdir=Path(opt.vddk_libdir) if opt.vddk_libdir else None,
        transport_modes=opt.vddk_transports or "nbdssl:nbd",
        thumbprint=opt.vddk_thumbprint,
        insecure=bool(opt.no_verify),
    )

    c = VDDKESXClient(client.logger, spec)  # type: ignore[misc]

    def _progress(done: int, total: int, pct: float) -> None:
        le = int(opt.vddk_download_log_every_bytes or 0)
        if total and done and le > 0:
            if done % le < int(opt.vddk_download_sectors_per_read or 2048) * 512:
                client.logger.info(
                    "VDDK download progress: %.1f GiB / %.1f GiB (%.1f%%)",
                    done / (1024**3),
                    total / (1024**3),
                    pct,
                )

    client.logger.warning("VDDK raw download is EXPERIMENTAL (explicit mode requested).")
    client.logger.info(
        "VDDK download: vm=%s disk=%s esx=%s remote=%s -> %s",
        opt.vm_name,
        opt.vddk_download_disk or str(disk_index),
        esx_host,
        remote_vmdk,
        local_path,
    )

    c.connect()
    try:
        out = c.download_vmdk(
            remote_vmdk,
            Path(local_path),
            sectors_per_read=int(opt.vddk_download_sectors_per_read or 2048),
            progress=_progress,
            log_every_bytes=int(opt.vddk_download_log_every_bytes or 0),
        )
        return Path(out)
    finally:
        c.disconnect()
