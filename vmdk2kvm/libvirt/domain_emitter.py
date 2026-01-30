# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# vmdk2kvm/libvirt/domain_emitter.py
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional

from ..core.logger import Log
from ..core.utils import U


try:
    from .linux_domain import emit_linux_domain  # type: ignore
    _LINUX_DOMAIN_OK = True
except Exception:  # pragma: no cover
    emit_linux_domain = None  # type: ignore
    _LINUX_DOMAIN_OK = False


try:
    from .windows_domain import WinDomainSpec, render_windows_domain_xml  # type: ignore
    _WIN_DOMAIN_OK = True
except Exception:  # pragma: no cover
    WinDomainSpec = None  # type: ignore
    render_windows_domain_xml = None  # type: ignore
    _WIN_DOMAIN_OK = False


def _guess_guest_kind(args: argparse.Namespace, img: Path) -> str:
    """
    Decide linux vs windows without being too clever.

    Priority:
      1) explicit args.guest_os (linux/windows)
      2) explicit args.windows / args.win / args.is_windows booleans
      3) heuristic from name/image stem (contains 'win', 'windows')
      4) default: linux
    """
    v = str(getattr(args, "guest_os", "") or "").strip().lower()
    if v in ("windows", "win"):
        return "windows"
    if v in ("linux", "lin"):
        return "linux"

    for b in ("windows", "win", "is_windows"):
        if bool(getattr(args, b, False)):
            return "windows"

    name = str(getattr(args, "vm_name", None) or getattr(args, "name", None) or img.stem).lower()
    stem = img.stem.lower()
    if "windows" in name or "win" in name or "windows" in stem or stem.startswith("win"):
        return "windows"

    return "linux"


def _write_text(path: Path, s: str) -> None:
    U.ensure_dir(path.parent)
    path.write_text(s, encoding="utf-8")


def emit_from_args(
    logger,
    args: argparse.Namespace,
    *,
    out_root: Path,
    out_images: List[Path],
) -> Optional[Path]:
    """
    Policy: emit ONE domain (first image) unless you later add multi-domain support.

    Controlled by args (common):
      - emit_domain_xml: bool
      - virsh_define: bool (Linux emitter supports define; Windows emitter here writes XML only)
      - vm_name, memory, vcpus, uefi, headless, libvirt_network, graphics*, ovmf*
      - machine, disk_cache, out_format, net_model, video
      - cloudinit_iso/cloudinit_seed_iso (Linux only)

    Windows-specific knobs (optional):
      - win_stage: bootstrap|final (default bootstrap)
      - win_driver_iso / virtio_win_iso / driver_iso
      - win_localtime_clock: bool (default True)
      - win_hyperv: bool (default True)

    Returns the XML path if written, else None.
    """
    if not getattr(args, "emit_domain_xml", False):
        Log.trace(logger, "🧾 emit_domain_xml disabled")
        return None
    if not out_images:
        Log.trace(logger, "🧾 emit_domain_xml: no outputs")
        return None

    img = Path(out_images[0]).expanduser().resolve()
    name = str(getattr(args, "vm_name", None) or getattr(args, "name", None) or img.stem)

    domain_dir = out_root / "libvirt"
    U.ensure_dir(domain_dir)

    guest_kind = _guess_guest_kind(args, img)
    uefi = bool(getattr(args, "uefi", False))
    headless = bool(getattr(args, "headless", False))

    # default graphics policy:
    # - headless => none
    # - otherwise => spice unless user overrides
    graphics = "none"
    if not headless:
        graphics = str(getattr(args, "graphics", None) or "spice")

    # ---------------------------
    # WINDOWS
    # ---------------------------
    if guest_kind == "windows":
        if not _WIN_DOMAIN_OK or WinDomainSpec is None or render_windows_domain_xml is None:
            logger.warning("emit_domain_xml requested for Windows but windows_domain not available")
            return None

        Log.step(logger, "Emit libvirt domain XML (Windows)")

        stage = str(getattr(args, "win_stage", None) or getattr(args, "stage", None) or "bootstrap").strip().lower()
        if stage not in ("bootstrap", "final"):
            raise ValueError(f"invalid win_stage: {stage!r} (expected bootstrap|final)")

        driver_iso = (
            getattr(args, "win_driver_iso", None)
            or getattr(args, "virtio_win_iso", None)
            or getattr(args, "driver_iso", None)
        )

        # If user asked headless, force graphics none for Windows too
        win_graphics = "none" if headless else str(getattr(args, "graphics", None) or "spice")

        spec = WinDomainSpec(  # type: ignore[misc]
            name=name,
            img_path=str(img),

            ovmf_code=str(getattr(args, "ovmf_code", "/usr/share/edk2/ovmf/OVMF_CODE.fd")),
            nvram_vars=str(getattr(args, "nvram_vars", "/var/tmp/VM_VARS.fd")),
            memory_mib=int(getattr(args, "memory", 8192)),
            vcpus=int(getattr(args, "vcpus", 4)),
            machine=str(getattr(args, "machine", "q35")),

            net_model=str(getattr(args, "net_model", "virtio")),

            video=str(getattr(args, "video", "qxl")),
            graphics=win_graphics,
            graphics_listen=str(getattr(args, "graphics_listen", "127.0.0.1")),

            disk_cache=str(getattr(args, "disk_cache", "none")),
            disk_type=str(getattr(args, "out_format", "qcow2")),

            driver_iso=str(driver_iso) if driver_iso else None,

            localtime_clock=bool(getattr(args, "win_localtime_clock", True)),
            hyperv=bool(getattr(args, "win_hyperv", True)),
        )

        xml = render_windows_domain_xml(spec, stage=stage)  # type: ignore[misc]
        xml_path = domain_dir / f"{name}.xml"
        _write_text(xml_path, xml)

        logger.info("🧩 Domain XML: %s", xml_path)
        if stage == "bootstrap" and driver_iso:
            logger.info("💿 VirtIO driver ISO: %s", driver_iso)
        return xml_path

    # ---------------------------
    # LINUX (existing path)
    # ---------------------------
    if not _LINUX_DOMAIN_OK or emit_linux_domain is None:
        logger.warning("emit_domain_xml requested but libvirt linux_domain not available")
        return None

    cloudinit_iso = getattr(args, "cloudinit_iso", None) or getattr(args, "cloudinit_seed_iso", None)

    Log.step(logger, "Emit libvirt domain XML (Linux)")
    paths = emit_linux_domain(  # type: ignore[misc]
        name=name,
        image_path=img,
        out_dir=domain_dir,

        firmware=("uefi" if uefi else "bios"),
        memory_mib=int(getattr(args, "memory", 2048)),
        vcpus=int(getattr(args, "vcpus", 2)),
        machine=str(getattr(args, "machine", "q35")),

        disk_bus=str(getattr(args, "disk_bus", "virtio")),
        disk_dev=str(getattr(args, "disk_dev", "vda")),
        disk_type=str(getattr(args, "out_format", "qcow2")),
        disk_cache=str(getattr(args, "disk_cache", "none")),

        network=str(getattr(args, "libvirt_network", "default")),
        net_model=str(getattr(args, "net_model", "virtio")),

        graphics=graphics,
        graphics_listen=str(getattr(args, "graphics_listen", "127.0.0.1")),
        video=str(getattr(args, "video", "virtio")),
        usb_tablet=bool(getattr(args, "usb_tablet", True)),

        serial_pty=True,
        console_pty=True,

        cloudinit_iso=str(cloudinit_iso) if cloudinit_iso else None,
        clock=str(getattr(args, "clock", "utc")),

        ovmf_code=str(getattr(args, "ovmf_code", "/usr/share/edk2/ovmf/OVMF_CODE.fd")),
        nvram_vars=getattr(args, "nvram_vars", None),
        ovmf_vars_template=getattr(args, "ovmf_vars_template", None),

        write_xml=True,
        virsh_define=bool(getattr(args, "virsh_define", False)),
    )

    logger.info("🧩 Domain XML: %s", paths.xml_path)
    if paths.nvram_path:
        logger.info("🧬 NVRAM: %s", paths.nvram_path)
    return paths.xml_path
