# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/libvirt/windows_domain.py
"""
Windows libvirt domain XML emitter (UEFI-focused).

What this module does well (on purpose):
- Generates a sane Windows UEFI libvirt XML for two stages:
    * bootstrap: SATA disk (Windows boots even without VirtIO storage driver)
    * final: VirtIO disk (performance, after driver is installed)
- Optionally copies the disk into /var/lib/libvirt/images with safe perms + restorecon
- Optionally runs `virsh define` (via sudo) on the generated XML

"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..core.xml_utils import xml_escape_attr as _xml_escape_attr
from ..core.xml_utils import xml_escape_text as _xml_escape_text
from .libvirt_utils import sanitize_name as _sanitize_name

WinStage = Literal["bootstrap", "final"]


# Models

@dataclass(frozen=True, slots=True)
class WinDomainSpec:
    """
    Windows domain XML spec (UEFI-focused).

    Notes:
      - stage=bootstrap => disk on SATA (boots even without VirtIO storage driver)
      - stage=final => disk on VirtIO (performance, requires VirtIO storage driver installed)
      - graphics/video defaults are Windows-friendly for SPICE-based consoles
    """
    name: str
    img_path: str

    # Firmware / NVRAM
    ovmf_code: str = "/usr/share/edk2/ovmf/OVMF_CODE.fd"
    ovmf_vars_template: str | None = "/usr/share/edk2/ovmf/OVMF_VARS.fd"
    nvram_vars: str = "/var/lib/libvirt/qemu/nvram/VM_VARS.fd"

    # Compute
    memory_mib: int = 8192
    vcpus: int = 4
    machine: str = "q35"

    # Devices
    net_model: str = "virtio"

    # Display
    video: str = "qxl"
    graphics: str = "spice"
    graphics_listen: str = "127.0.0.1"  # safer default; use 0.0.0.0 for remote consoles

    # Disk
    disk_cache: str = "none"
    disk_type: str = "qcow2"  # allow "raw" etc.

    # Optional: attach drivers ISO (virtio-win.iso) as CDROM for bootstrap
    driver_iso: str | None = None

    # Windows niceties
    localtime_clock: bool = True

    # Hyper-V enlightenments (off by default; enable if you know you want it)
    hyperv: bool = False


@dataclass(frozen=True, slots=True)
class WinDomainPaths:
    out_dir: Path
    xml_path: Path
    nvram_path: Path | None = None
    disk_path: Path | None = None


# Small utilities

def _default_libvirt_images_dir() -> Path:
    return Path("/var/lib/libvirt/images")


def _restorecon_best_effort(path: Path) -> None:
    """
    Best-effort SELinux labeling fix. Silent on systems without restorecon / SELinux.
    """
    if shutil.which("restorecon") is None:
        return
    try:
        subprocess.run(
            ["restorecon", "-v", str(path)],
            check=False,
            text=True,
            capture_output=True,
        )
    except Exception:
        # Intentionally swallow: SELinux tools absent or permission issues shouldn't kill flow
        return


def _require_file(path: str | Path, *, label: str) -> Path:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"{label} not found: {p}")
    return p


# XML rendering

def render_windows_domain_xml(spec: WinDomainSpec, *, stage: WinStage) -> str:
    """
    Render libvirt domain XML for Windows.

    stage:
      - "bootstrap" => disk on SATA (safe boot)
      - "final" => disk on VirtIO (performance)
    """
    if stage not in ("bootstrap", "final"):
        raise ValueError(f"invalid stage: {stage}")

    img = _require_file(spec.img_path, label="image")
    ovmf_code = _require_file(spec.ovmf_code, label="OVMF_CODE")

    if stage == "bootstrap":
        disk_bus = "sata"
        disk_dev = "sda"
        stage_note = "SATA bootstrap (VirtIO storage driver not yet trusted by Windows)"
    else:
        disk_bus = "virtio"
        disk_dev = "vda"
        stage_note = "VirtIO final (Windows has bound + promoted boot-critical VirtIO storage driver)"

    # Optional driver ISO (commonly used during bootstrap)
    cdrom_xml = ""
    if spec.driver_iso:
        iso = _require_file(spec.driver_iso, label="driver ISO")
        cdrom_xml = f"""
    <disk type='file' device='cdrom'>
      <driver name='qemu' type='raw' cache='none'/>
      <source file='{_xml_escape_attr(str(iso))}'/>
      <target dev='sdc' bus='sata'/>
      <readonly/>
    </disk>"""

    # Clock: Windows often expects localtime
    clock_xml = " <clock offset='localtime'/>" if spec.localtime_clock else " <clock offset='utc'/>"

    # Hyper-V enlightenments (conservative but useful)
    hyperv_xml = ""
    if spec.hyperv:
        hyperv_xml = """
    <hyperv mode='custom'>
      <relaxed state='on'/>
      <vapic state='on'/>
      <spinlocks state='on' retries='8191'/>
      <vpindex state='on'/>
      <synic state='on'/>
      <stimer state='on'/>
      <reset state='on'/>
    </hyperv>"""

    # Graphics: include listen so it behaves consistently across hosts
    graphics_xml = (
        f" <graphics type='{_xml_escape_attr(spec.graphics)}' autoport='yes' "
        f"listen='{_xml_escape_attr(spec.graphics_listen)}'/>"
    )
    video_xml = f" <video><model type='{_xml_escape_attr(spec.video)}'/></video>"
    input_xml = " <input type='tablet' bus='usb'/>"

    # NIC: keep virtio both stages
    nic_xml = f"""
    <interface type='network'>
      <source network='default'/>
      <model type='{_xml_escape_attr(spec.net_model)}'/>
    </interface>"""

    # Helpful extras for Windows guests
    memballoon_xml = " <memballoon model='virtio'/>" if stage == "final" else ""

    # NVRAM template is optional in libvirt; include attribute only when present
    if spec.ovmf_vars_template:
        nvram_line = (
            f" <nvram template='{_xml_escape_attr(spec.ovmf_vars_template)}'>"
            f"{_xml_escape_text(spec.nvram_vars)}</nvram>"
        )
    else:
        nvram_line = f" <nvram>{_xml_escape_text(spec.nvram_vars)}</nvram>"

    # NOTE: We keep cpu mode host-passthrough (good default for Windows perf),
    # and avoid piling on dozens of options until the caller asks for them.
    return f"""<domain type='kvm'>
  <name>{_xml_escape_text(spec.name)}</name>
  <description>{_xml_escape_text(f"Windows UEFI domain ({stage}): {stage_note}")}</description>
  <memory unit='MiB'>{spec.memory_mib}</memory>
  <vcpu>{spec.vcpus}</vcpu>
  <os>
    <type arch='x86_64' machine='{_xml_escape_attr(spec.machine)}'>hvm</type>
    <loader readonly='yes' type='pflash'>{_xml_escape_text(str(ovmf_code))}</loader>
{nvram_line}
  </os>
  <features>
    <acpi/>
    <apic/>{hyperv_xml}
  </features>
  <cpu mode='host-passthrough'/>
{clock_xml}
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='{_xml_escape_attr(spec.disk_type)}' cache='{_xml_escape_attr(spec.disk_cache)}'/>
      <source file='{_xml_escape_attr(str(img))}'/>
      <target dev='{_xml_escape_attr(disk_dev)}' bus='{_xml_escape_attr(disk_bus)}'/>
      <boot order='1'/>
    </disk>{cdrom_xml}
{nic_xml}
{graphics_xml}
{input_xml}
{video_xml}
{memballoon_xml}
  </devices>
</domain>
"""


# Storage helpers

def copy_disk_for_libvirt(
    *,
    src: Path,
    name: str,
    dest_dir: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """
    Copy disk into /var/lib/libvirt/images (or override) to avoid perms/SELinux surprises.
    Matches guide: chmod 0644.
    """
    src = Path(src).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"image not found: {src}")

    dest_dir = (dest_dir or _default_libvirt_images_dir()).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    safe = _sanitize_name(name)
    suffix = src.suffix or ".qcow2"
    dst = dest_dir / f"{safe}{suffix}"

    if dst.exists():
        if not overwrite:
            return dst
        try:
            dst.unlink()
        except Exception:
            # If unlink fails, let copy2 raise something meaningful
            pass

    shutil.copy2(src, dst)
    os.chmod(dst, 0o644)
    _restorecon_best_effort(dst)
    return dst


# Output helpers

def write_windows_domain_xml(
    *,
    spec: WinDomainSpec,
    out_dir: Path,
    stage: WinStage,
    filename: str | None = None,
    overwrite: bool = True,
    disk_path: Path | None = None,
) -> WinDomainPaths:
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    xml_text = render_windows_domain_xml(spec, stage=stage)

    xml_name = filename or f"{_sanitize_name(spec.name)}-{stage}.xml"
    xml_path = out_dir / xml_name

    if xml_path.exists() and not overwrite:
        raise FileExistsError(f"domain XML already exists: {xml_path}")

    xml_path.write_text(xml_text, encoding="utf-8")

    return WinDomainPaths(
        out_dir=out_dir,
        xml_path=xml_path,
        nvram_path=Path(spec.nvram_vars) if spec.nvram_vars else None,
        disk_path=disk_path,
    )


def define_windows_domain(*, xml_path: Path) -> None:
    """
    `virsh define <xml>` with good error reporting.
    """
    xml_path = Path(xml_path).expanduser().resolve()
    if not xml_path.exists():
        raise FileNotFoundError(f"domain XML not found: {xml_path}")

    try:
        cp = subprocess.run(
            ["sudo", "virsh", "define", str(xml_path)],
            check=True,
            text=True,
            capture_output=True,
        )
        if cp.stdout.strip():
            print(cp.stdout.strip())
    except subprocess.CalledProcessError as e:
        out = (e.stdout or "").strip()
        err = (e.stderr or "").strip()
        raise RuntimeError(
            "virsh define failed\n"
            f" xml: {xml_path}\n"
            f" rc: {e.returncode}\n"
            f" stdout: {out or '(empty)'}\n"
            f" stderr: {err or '(empty)'}"
        ) from e


def emit_windows_domain(
    *,
    name: str,
    image_path: Path,
    out_dir: Path,
    stage: WinStage,
    # firmware
    ovmf_code: str = "/usr/share/edk2/ovmf/OVMF_CODE.fd",
    ovmf_vars_template: str | None = "/usr/share/edk2/ovmf/OVMF_VARS.fd",
    nvram_vars: str | None = None,
    # compute
    memory_mib: int = 8192,
    vcpus: int = 4,
    machine: str = "q35",
    # devices
    net_model: str = "virtio",
    video: str = "qxl",
    graphics: str = "spice",
    graphics_listen: str = "127.0.0.1",
    disk_cache: str = "none",
    disk_type: str = "qcow2",
    driver_iso: str | None = None,
    localtime_clock: bool = True,
    hyperv: bool = False,
    # actions
    write_xml: bool = True,
    virsh_define: bool = False,
    # storage policy
    copy_to_libvirt_images: bool | None = None,  # default True if virsh_define else False
    libvirt_images_dir: str | None = None,
    overwrite_disk_copy: bool = False,
) -> WinDomainPaths:
    """
    High-level helper:
    - resolves paths
    - optionally copies disk into libvirt images dir
    - picks a default NVRAM path if not supplied
    - writes XML
    - optionally `virsh define`
    """
    image_path = Path(image_path).expanduser().resolve()
    out_dir = Path(out_dir).expanduser().resolve()

    if not image_path.exists():
        raise FileNotFoundError(f"converted image not found: {image_path}")

    if copy_to_libvirt_images is None:
        copy_to_libvirt_images = bool(virsh_define)

    effective_disk = image_path
    if copy_to_libvirt_images:
        effective_images_dir = (
            Path(libvirt_images_dir).expanduser().resolve()
            if libvirt_images_dir
            else _default_libvirt_images_dir()
        )
        effective_disk = copy_disk_for_libvirt(
            src=image_path,
            name=name,
            dest_dir=effective_images_dir,
            overwrite=overwrite_disk_copy,
        )

    # Decide NVRAM path
    if not nvram_vars:
        nvram_dir = Path("/var/lib/libvirt/qemu/nvram")
        nvram_vars = str(nvram_dir / f"{_sanitize_name(name)}_VARS.fd")

    spec = WinDomainSpec(
        name=name,
        img_path=str(effective_disk),
        ovmf_code=ovmf_code,
        ovmf_vars_template=ovmf_vars_template,
        nvram_vars=nvram_vars,
        memory_mib=memory_mib,
        vcpus=vcpus,
        machine=machine,
        net_model=net_model,
        video=video,
        graphics=graphics,
        graphics_listen=graphics_listen,
        disk_cache=disk_cache,
        disk_type=disk_type,
        driver_iso=driver_iso,
        localtime_clock=localtime_clock,
        hyperv=hyperv,
    )

    # Caller might only want to know where we'd write things
    if not write_xml:
        xml_path = out_dir / f"{_sanitize_name(spec.name)}-{stage}.xml"
        return WinDomainPaths(
            out_dir=out_dir,
            xml_path=xml_path,
            nvram_path=Path(spec.nvram_vars),
            disk_path=effective_disk,
        )

    paths = write_windows_domain_xml(
        spec=spec,
        out_dir=out_dir,
        stage=stage,
        overwrite=True,
        disk_path=effective_disk,
    )

    if virsh_define:
        define_windows_domain(xml_path=paths.xml_path)

    return paths
