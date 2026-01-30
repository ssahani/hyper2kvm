# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/libvirt/linux_domain.py


from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..core.xml_utils import xml_escape as _xml
from .libvirt_utils import sanitize_name as _sanitize_name

Firmware = Literal["bios", "uefi"]
Graphics = Literal["none", "vnc", "spice"]
Profile = Literal["default", "minimal-bios-gui"]
ClockOffset = Literal["utc", "localtime"]


# Small utilities

_DEFAULT_IMAGES_DIR = Path("/var/lib/libvirt/images")
_DEFAULT_NVRAM_DIR = Path("/var/lib/libvirt/qemu/nvram")


def _default_libvirt_images_dir() -> Path:
    return _DEFAULT_IMAGES_DIR


def _run_sudo(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    # NOTE: keep as simple as possible; user wants deterministic sudo behavior.
    return subprocess.run(["sudo", *args], check=check, text=True, capture_output=True)


def _restorecon_best_effort(path: Path) -> None:
    if shutil.which("restorecon") is None:
        return
    try:
        subprocess.run(["restorecon", "-v", str(path)], check=False, text=True, capture_output=True)
    except Exception:
        pass


def _validate_positive_int(value: int, *, field: str) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive int, got: {value!r}")


def _validate_listen_addr(addr: str) -> None:
    # Keep it lightweight; just avoid empty + obvious junk.
    if not addr or not addr.strip():
        raise ValueError("graphics_listen must be non-empty")


# Disk copy policy (avoid perms/SELinux surprises)

def copy_disk_for_libvirt(
    *,
    src: Path,
    name: str,
    dest_dir: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """
    Copy disk into /var/lib/libvirt/images (or override) to avoid perms/SELinux surprises.

    Keeps your prior policy:
      - sudo rm (optional overwrite)
      - sudo cp
      - sudo chown qemu:qemu
      - sudo chmod 0640
      - restorecon best-effort
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
        _run_sudo(["rm", "-f", str(dst)], check=True)

    _run_sudo(["cp", str(src), str(dst)], check=True)
    _run_sudo(["chown", "qemu:qemu", str(dst)], check=True)
    _run_sudo(["chmod", "0640", str(dst)], check=True)
    _restorecon_best_effort(dst)
    return dst


# Spec

@dataclass(frozen=True)
class LinuxDomainSpec:
    """
    Linux domain XML spec.

    Two modes:
      - profile="minimal-bios-gui" => emit *exactly* the known-good Photon smoke test XML shape.
      - profile="default" => richer/console-first XML (more knobs).
    """
    name: str
    img_path: str

    profile: Profile = "default"

    # Firmware
    firmware: Firmware = "bios"
    ovmf_code: str = "/usr/share/edk2/ovmf/OVMF_CODE.fd"
    ovmf_vars_template: str | None = None
    nvram_vars: str = "/var/tmp/VM_VARS.fd"

    # Compute
    memory_mib: int = 4096
    vcpus: int = 2

    # Machine
    machine: str = "q35"  # overridden by minimal-bios-gui profile

    # Disk
    disk_bus: str = "virtio"
    disk_dev: str = "vda"
    disk_type: str = "qcow2"
    disk_cache: str | None = None  # None => omit cache attr (matches your working XML)
    disk_io: str | None = None
    disk_discard: str | None = None
    disk_boot_order: int | None = None

    # Network
    network: str = "default"
    net_model: str = "virtio"

    # Display
    graphics: Graphics = "vnc"
    graphics_listen: str = "127.0.0.1"
    video: str = "vga"
    video_heads: int | None = None
    usb_tablet: bool = True

    # Console (default profile only)
    serial_pty: bool = True
    console_pty: bool = True

    # Optional cloud-init seed ISO (default profile only)
    cloudinit_iso: str | None = None

    # Clock (default profile only)
    clock: ClockOffset = "utc"


# XML rendering

def _render_minimal_bios_gui_xml(spec: LinuxDomainSpec) -> str:
    """
    Emit the same shape as your known-good Photon XML:
      - machine='pc'
      - <boot dev='hd'/>
      - disk driver type=qcow2 (no cache)
      - vnc + video + tablet
      - no memballoon / no serial / no extras
    """
    img = Path(spec.img_path)
    if not img.exists():
        raise FileNotFoundError(f"image not found: {img}")

    _validate_positive_int(spec.memory_mib, field="memory_mib")
    _validate_positive_int(spec.vcpus, field="vcpus")
    _validate_listen_addr(spec.graphics_listen)

    if spec.firmware != "bios":
        raise ValueError("minimal-bios-gui profile supports firmware='bios' only")

    machine = "pc"
    disk_bus = "virtio"
    disk_dev = "vda"
    disk_type = "qcow2"
    net_model = "virtio"

    # Your existing small vram tweak (kept), but still minimal.
    vram_attr = ""
    if spec.video == "qxl":
        vram_attr = " vram='65536'"

    return f"""<domain type='kvm'>
  <name>{_xml(spec.name)}</name>
  <memory unit='MiB'>{spec.memory_mib}</memory>
  <vcpu>{spec.vcpus}</vcpu>
  <os>
    <type arch='x86_64' machine='{machine}'>hvm</type>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
  </features>
  <cpu mode='host-passthrough'/>
  <devices>
    <!-- Disk -->
    <disk type='file' device='disk'>
      <driver name='qemu' type='{disk_type}'/>
      <source file='{_xml(img)}'/>
      <target dev='{disk_dev}' bus='{disk_bus}'/>
    </disk>
    <!-- Network -->
    <interface type='network'>
      <source network='{_xml(spec.network)}'/>
      <model type='{net_model}'/>
    </interface>
    <!-- Graphics -->
    <graphics type='vnc' autoport='yes' listen='{_xml(spec.graphics_listen)}'/>
    <!-- Video -->
    <video>
      <model type='{_xml(spec.video)}'{vram_attr}/>
    </video>
    <input type='tablet' bus='usb'/>
  </devices>
</domain>
"""


def _default_ovmf_vars_template() -> Path | None:
    candidates = [
        "/usr/share/edk2/ovmf/OVMF_VARS.fd",
        "/usr/share/OVMF/OVMF_VARS.fd",
        "/usr/share/edk2/ovmf/OVMF_VARS.secboot.fd",
        "/usr/share/qemu/OVMF_VARS.fd",
        # Some distros place these under /usr/share/edk2/ovmf/x64/...
        "/usr/share/edk2/ovmf/x64/OVMF_VARS.fd",
        "/usr/share/edk2/ovmf/x64/OVMF_VARS.secboot.fd",
    ]
    for p in candidates:
        pp = Path(p)
        if pp.exists():
            return pp
    return None


def _render_default_xml(spec: LinuxDomainSpec) -> str:
    img = Path(spec.img_path)
    if not img.exists():
        raise FileNotFoundError(f"image not found: {img}")

    _validate_positive_int(spec.memory_mib, field="memory_mib")
    _validate_positive_int(spec.vcpus, field="vcpus")
    if spec.graphics != "none":
        _validate_listen_addr(spec.graphics_listen)

    # OS / firmware block
    os_lines: list[str] = [
        " <os>",
        f" <type arch='x86_64' machine='{_xml(spec.machine)}'>hvm</type>",
    ]

    if spec.firmware == "uefi":
        if not os.path.exists(spec.ovmf_code):
            raise FileNotFoundError(f"OVMF_CODE not found: {spec.ovmf_code}")

        os_lines.append(f" <loader readonly='yes' type='pflash'>{_xml(spec.ovmf_code)}</loader>")

        nvram_line = " <nvram"
        if spec.ovmf_vars_template:
            nvram_line += f" template='{_xml(spec.ovmf_vars_template)}'"
        nvram_line += f">{_xml(spec.nvram_vars)}</nvram>"
        os_lines.append(nvram_line)

    elif spec.firmware == "bios":
        os_lines.append(" <boot dev='hd'/>")
    else:
        raise ValueError(f"invalid firmware: {spec.firmware}")

    os_lines.append(" </os>")

    clock_xml = f"""  <clock offset='{_xml(spec.clock)}'>
    <timer name='rtc' tickpolicy='catchup'/>
    <timer name='pit' tickpolicy='delay'/>
    <timer name='hpet' present='no'/>
  </clock>"""

    on_actions = """  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>restart</on_crash>"""

    # Optional cloud-init ISO
    cidata_xml = ""
    if spec.cloudinit_iso:
        iso = Path(spec.cloudinit_iso)
        if not iso.exists():
            raise FileNotFoundError(f"cloud-init ISO not found: {iso}")
        cidata_xml = f"""
    <disk type='file' device='cdrom'>
      <driver name='qemu' type='raw' cache='none'/>
      <source file='{_xml(iso)}'/>
      <target dev='sdc' bus='sata'/>
      <readonly/>
    </disk>"""

    # Disk driver line
    cache_attr = f" cache='{_xml(spec.disk_cache)}'" if spec.disk_cache else ""
    io_attr = f" io='{_xml(spec.disk_io)}'" if spec.disk_io else ""
    discard_attr = f" discard='{_xml(spec.disk_discard)}'" if spec.disk_discard else ""
    disk_driver = f" <driver name='qemu' type='{_xml(spec.disk_type)}'{cache_attr}{io_attr}{discard_attr}/>"
    disk_boot = f" <boot order='{spec.disk_boot_order}'/>" if spec.disk_boot_order else ""

    # Graphics / video / input / usb
    graphics_xml = ""
    video_xml = ""
    input_xml = ""
    usb_controller_xml = ""

    if spec.graphics != "none":
        graphics_xml = (
            f" <graphics type='{_xml(spec.graphics)}' autoport='yes' listen='{_xml(spec.graphics_listen)}'/>"
        )
        heads_attr = f" heads='{spec.video_heads}'" if spec.video_heads else ""
        video_xml = f" <video><model type='{_xml(spec.video)}'{heads_attr}/></video>"
        if spec.usb_tablet:
            input_xml = " <input type='tablet' bus='usb'/>"
            usb_controller_xml = " <controller type='usb' index='0' model='qemu-xhci'/>"

    # Console
    serial_xml = " <serial type='pty'><target port='0'/></serial>" if spec.serial_pty else ""
    console_xml = " <console type='pty'><target type='serial' port='0'/></console>" if spec.console_pty else ""

    guest_agent_xml = """    <channel type='unix'>
      <source mode='bind'/>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
    </channel>"""

    rng_xml = """    <rng model='virtio'>
      <backend model='random'>/dev/urandom</backend>
    </rng>"""

    memballoon_xml = " <memballoon model='virtio'/>"

    return (
        f"""<domain type='kvm'>
  <name>{_xml(spec.name)}</name>
  <memory unit='MiB'>{spec.memory_mib}</memory>
  <currentMemory unit='MiB'>{spec.memory_mib}</currentMemory>
  <vcpu placement='static'>{spec.vcpus}</vcpu>
"""
        + "\n".join(os_lines)
        + "\n"
        + clock_xml
        + "\n"
        + on_actions
        + f"""
  <features>
    <acpi/>
    <apic/>
    <vmport state='off'/>
  </features>
  <cpu mode='host-passthrough' check='none'/>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
{usb_controller_xml}
    <disk type='file' device='disk'>
{disk_driver}
      <source file='{_xml(img)}'/>
      <target dev='{_xml(spec.disk_dev)}' bus='{_xml(spec.disk_bus)}'/>
{disk_boot}
    </disk>{cidata_xml}
    <interface type='network'>
      <source network='{_xml(spec.network)}'/>
      <model type='{_xml(spec.net_model)}'/>
    </interface>
{serial_xml}
{console_xml}
{graphics_xml}
{input_xml}
{video_xml}
{guest_agent_xml}
{rng_xml}
{memballoon_xml}
  </devices>
</domain>
"""
    )


def render_linux_domain_xml(spec: LinuxDomainSpec) -> str:
    if spec.profile == "minimal-bios-gui":
        return _render_minimal_bios_gui_xml(spec)
    if spec.profile == "default":
        return _render_default_xml(spec)
    raise ValueError(f"invalid profile: {spec.profile}")


# Write/define helpers

@dataclass(frozen=True)
class LinuxDomainPaths:
    out_dir: Path
    xml_path: Path
    nvram_path: Path | None = None
    disk_path: Path | None = None


def write_linux_domain_xml(
    *,
    spec: LinuxDomainSpec,
    out_dir: Path,
    filename: str | None = None,
    overwrite: bool = True,
    disk_path: Path | None = None,
) -> LinuxDomainPaths:
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    xml_text = render_linux_domain_xml(spec)
    xml_path = out_dir / (filename or f"{_sanitize_name(spec.name)}.xml")

    if xml_path.exists() and not overwrite:
        raise FileExistsError(f"domain XML already exists: {xml_path}")

    xml_path.write_text(xml_text, encoding="utf-8")

    nvram_path: Path | None = Path(spec.nvram_vars) if spec.firmware == "uefi" else None
    return LinuxDomainPaths(out_dir=out_dir, xml_path=xml_path, nvram_path=nvram_path, disk_path=disk_path)


def define_linux_domain(*, xml_path: Path) -> None:
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


# High-level "emit" function (your main entry point)

def emit_linux_domain(
    *,
    name: str,
    image_path: Path,
    out_dir: Path,
    # profile/firmware
    profile: Profile = "minimal-bios-gui",
    firmware: Firmware = "bios",
    # compute
    memory_mib: int = 4096,
    vcpus: int = 2,
    # machine (default depends on profile/firmware)
    machine: str | None = None,
    # disk/network/display knobs (some ignored in minimal-bios-gui)
    disk_bus: str = "virtio",
    disk_dev: str = "vda",
    disk_type: str = "qcow2",
    disk_cache: str | None = None,
    disk_io: str | None = None,
    disk_discard: str | None = None,
    disk_boot_order: int | None = None,
    network: str = "default",
    net_model: str = "virtio",
    graphics: Graphics = "vnc",
    graphics_listen: str = "127.0.0.1",
    video: str = "vga",
    video_heads: int | None = None,
    usb_tablet: bool = True,
    serial_pty: bool = True,
    console_pty: bool = True,
    cloudinit_iso: str | None = None,
    clock: ClockOffset = "utc",
    # uefi-specific
    ovmf_code: str = "/usr/share/edk2/ovmf/OVMF_CODE.fd",
    nvram_vars: str | None = None,
    ovmf_vars_template: str | None = None,
    # actions
    write_xml: bool = True,
    virsh_define: bool = False,
    # storage policy
    copy_to_libvirt_images: bool | None = None,  # default True if virsh_define else False
    libvirt_images_dir: str | None = None,
    overwrite_disk_copy: bool = False,
) -> LinuxDomainPaths:
    image_path = image_path.expanduser().resolve()
    out_dir = out_dir.expanduser().resolve()

    if not image_path.exists():
        raise FileNotFoundError(f"converted image not found: {image_path}")

    _validate_positive_int(memory_mib, field="memory_mib")
    _validate_positive_int(vcpus, field="vcpus")

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

    # Decide machine defaults
    if machine is None:
        if profile == "minimal-bios-gui":
            machine = "pc"
        else:
            machine = "pc" if firmware == "bios" else "q35"

    # Decide NVRAM path + default tuning for UEFI
    nvram_path = nvram_vars
    if firmware == "uefi":
        if ovmf_vars_template is None:
            tpl = _default_ovmf_vars_template()
            if tpl is not None:
                ovmf_vars_template = str(tpl)
            else:
                raise FileNotFoundError("No default OVMF_VARS template found.")

        if not nvram_path:
            _DEFAULT_NVRAM_DIR.mkdir(parents=True, exist_ok=True)
            nvram_path = str(_DEFAULT_NVRAM_DIR / f"{_sanitize_name(name)}_VARS.fd")

        # Sensible UEFI defaults (kept from your earlier logic)
        disk_cache = "none" if disk_cache is None else disk_cache
        disk_io = "native" if disk_io is None else disk_io
        disk_discard = "unmap" if disk_discard is None else disk_discard
        disk_boot_order = 1 if disk_boot_order is None else disk_boot_order

        if graphics == "vnc":
            graphics = "spice"
        if video == "vga":
            video = "virtio"
        if video_heads is None:
            video_heads = 1

    spec = LinuxDomainSpec(
        name=name,
        img_path=str(effective_disk),
        profile=profile,
        firmware=firmware,
        ovmf_code=ovmf_code,
        ovmf_vars_template=ovmf_vars_template,
        nvram_vars=(nvram_path or "/var/tmp/VM_VARS.fd"),
        memory_mib=memory_mib,
        vcpus=vcpus,
        machine=machine,
        disk_bus=disk_bus,
        disk_dev=disk_dev,
        disk_type=disk_type,
        disk_cache=disk_cache,
        disk_io=disk_io,
        disk_discard=disk_discard,
        disk_boot_order=disk_boot_order,
        network=network,
        net_model=net_model,
        graphics=graphics,
        graphics_listen=graphics_listen,
        video=video,
        video_heads=video_heads,
        usb_tablet=usb_tablet,
        serial_pty=serial_pty,
        console_pty=console_pty,
        cloudinit_iso=cloudinit_iso,
        clock=clock,
    )

    if not write_xml:
        xml_path = out_dir / f"{_sanitize_name(spec.name)}.xml"
        return LinuxDomainPaths(
            out_dir=out_dir,
            xml_path=xml_path,
            nvram_path=Path(spec.nvram_vars) if firmware == "uefi" else None,
            disk_path=effective_disk,
        )

    paths = write_linux_domain_xml(
        spec=spec,
        out_dir=out_dir,
        filename=f"{_sanitize_name(spec.name)}.xml",
        overwrite=True,
        disk_path=effective_disk,
    )

    if virsh_define:
        define_linux_domain(xml_path=paths.xml_path)

    return paths
