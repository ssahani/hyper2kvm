# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/testers/libvirt_tester.py
from __future__ import annotations

import logging
import os
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from ..core.utils import U

# Types / Config

GraphicsMode = Literal["none", "vnc", "spice"]
MachineType = Literal["pc", "q35"]

GuestOS = Literal["linux", "windows"]
WinStage = Literal["bootstrap", "final"]  # bootstrap=sata (safe), final=virtio (fast)


@dataclass(frozen=True)
class FirmwareConfig:
    """
    Firmware selection.

      - uefi=False => BIOS
      - uefi=True => UEFI via OVMF (CODE+VARS)
    """
    uefi: bool = False


@dataclass(frozen=True)
class GraphicsConfig:
    """
    libvirt graphics:

      - none => no display device
      - vnc => VNC server (good for headless servers)
      - spice => SPICE server
    """
    mode: GraphicsMode = "none"
    listen: str = "127.0.0.1"
    autoport: bool = True
    port: int | None = None
    passwd: str | None = None
    keymap: str | None = None


@dataclass(frozen=True)
class VideoConfig:
    """
    Video device config (only meaningful when graphics != none).
    Common models: qxl, virtio, vga, cirrus, bochs.
    """
    enabled: bool = False
    model: str = "qxl"
    vram: int = 65536


@dataclass(frozen=True)
class InputConfig:
    """
    Input devices. USB tablet is a big quality-of-life improvement for VNC/SPICE.
    """
    usb_tablet: bool = False
    usb_kbd: bool = False
    usb_mouse: bool = False


@dataclass(frozen=True)
class DomainConfig:
    """
    Domain “shape” and runtime knobs.
    """
    name: str
    memory_mib: int = 2048
    vcpus: int = 2
    machine: MachineType = "q35"
    network: str = "default"
    timeout_s: int = 60
    keep: bool = False


@dataclass(frozen=True)
class OVMFPaths:
    code: str
    vars: str


@dataclass(frozen=True)
class GuestProfile:
    """
    Guest OS profile.

    - linux: defaults stay virtio disk/net
    - windows bootstrap: disk on SATA (safer first boot if virtio not installed)
    - windows final: disk on VirtIO (performance)
    """
    os: GuestOS = "linux"
    win_stage: WinStage = "final"

    # Optional Windows niceties
    hyperv: bool = True
    localtime_clock: bool = True  # windows often expects localtime
    tpm: bool = False             # needed for Win11 (plus other checks)
    tpm_model: Literal["tpm-tis", "tpm-crb"] = "tpm-crb"
    # Optional: attach virtio driver ISO (virtio-win.iso)
    driver_iso: Path | None = None


# Implementation

class LibvirtTest:
    """
    Libvirt “smoke test” runner:
      - define XML
      - start domain
      - wait for RUNNING
      - optional cleanup (destroy + undefine)
    """

    # Prefer these common distro paths, but be generous.
    _OVMF_CODE_CANDIDATES: Sequence[str] = (
        "/usr/share/OVMF/OVMF_CODE.fd",
        "/usr/share/edk2/ovmf/OVMF_CODE.fd",
        "/usr/share/qemu/OVMF_CODE.fd",
        "/usr/share/edk2/x64/OVMF_CODE.fd",
        "/usr/share/edk2/ovmf/OVMF_CODE.secboot.fd",
        "/usr/share/edk2/x64/OVMF_CODE.secboot.fd",
    )
    _OVMF_VARS_CANDIDATES: Sequence[str] = (
        "/usr/share/OVMF/OVMF_VARS.fd",
        "/usr/share/edk2/ovmf/OVMF_VARS.fd",
        "/usr/share/qemu/OVMF_VARS.fd",
        "/usr/share/edk2/x64/OVMF_VARS.fd",
        "/usr/share/edk2/ovmf/OVMF_VARS.secboot.fd",
        "/usr/share/edk2/x64/OVMF_VARS.secboot.fd",
    )

    @staticmethod
    def run(
        logger: logging.Logger,
        disk: Path,
        *,
        name: str,
        memory_mib: int,
        vcpus: int,
        uefi: bool,
        timeout_s: int,
        keep: bool,
        headless: bool,
        # Optional upgrades (safe defaults):
        machine: MachineType = "q35",
        network: str = "default",
        graphics_mode: GraphicsMode | None = None,  # default derived from headless
        listen: str = "127.0.0.1",
        video_model: str = "qxl",
        video_vram: int = 65536,
        usb_tablet: bool = True,
        spice: bool = False,  # legacy-friendly switch: prefer SPICE over VNC if GUI

        # ✅ Windows support (backward compatible: default is linux)
        guest_os: GuestOS = "linux",
        windows_stage: WinStage = "final",
        windows_hyperv: bool = True,
        windows_tpm: bool = False,
        windows_driver_iso: Path | None = None,
    ) -> None:
        """
        Backward-compatible signature with extra knobs.

        Linux (default):
          guest_os="linux" (implicit), disk virtio, net virtio.

        Windows safe-first-boot:
          guest_os="windows", windows_stage="bootstrap"  # disk SATA
          (then install VirtIO drivers in Windows)
          then rerun with windows_stage="final" (disk VirtIO)

        Note: for Win11 you may need UEFI + TPM + secure boot policy depending on your image.
        """
        if U.which("virsh") is None:
            U.die(logger, "💥 virsh not found; cannot run libvirt test.", 1)

        disk = Path(disk)
        if not disk.exists():
            U.die(logger, f"💥 Disk not found: {disk}", 1)

        fw = FirmwareConfig(uefi=uefi)
        dom = DomainConfig(
            name=name,
            memory_mib=memory_mib,
            vcpus=vcpus,
            machine=machine,
            network=network,
            timeout_s=timeout_s,
            keep=keep,
        )

        prof = GuestProfile(
            os=guest_os,
            win_stage=windows_stage,
            hyperv=windows_hyperv,
            tpm=windows_tpm,
            driver_iso=Path(windows_driver_iso) if windows_driver_iso else None,
        )

        # Derive graphics defaults
        if graphics_mode is None:
            if headless:
                gm: GraphicsMode = "none"
            else:
                gm = "spice" if spice else "vnc"
        else:
            gm = graphics_mode

        gfx = GraphicsConfig(mode=gm, listen=listen, autoport=True)

        # If Windows and user didn’t override video_model, pick saner defaults:
        # - bootstrap: vga is widely compatible
        # - final: virtio is good if drivers exist; keep qxl only if user explicitly wants it
        effective_video_model = video_model
        effective_video_vram = video_vram
        if prof.os == "windows":
            if video_model == "qxl":
                effective_video_model = "vga" if prof.win_stage == "bootstrap" else "virtio"
                effective_video_vram = 16384 if effective_video_model in ("vga", "virtio") else video_vram

        vid = VideoConfig(enabled=(gm != "none"), model=effective_video_model, vram=effective_video_vram)

        # Input: Windows tends to behave nicer with explicit kbd+mouse (esp. early boot)
        inp = InputConfig(
            usb_tablet=(usb_tablet and gm != "none"),
            usb_kbd=(prof.os == "windows" and gm != "none"),
            usb_mouse=(prof.os == "windows" and gm != "none"),
        )

        ovmf = LibvirtTest._resolve_ovmf(logger, fw)
        nvram = LibvirtTest._prepare_nvram(logger, disk, dom.name, fw, ovmf)

        xml = LibvirtTest._build_domain_xml(
            logger=logger,
            disk=disk,
            dom=dom,
            fw=fw,
            ovmf=ovmf,
            nvram=nvram,
            gfx=gfx,
            vid=vid,
            inp=inp,
            prof=prof,
        )

        xml_path: Path | None = None

        U.banner(logger, "🧪 Libvirt smoke test")
        logger.info("🧾 Domain: %s", dom.name)
        logger.info("💽 Disk: %s", disk)
        logger.info("🧬 Guest: %s", prof.os)
        if prof.os == "windows":
            logger.info("🪟 Windows stage: %s (disk bus=%s)", prof.win_stage, LibvirtTest._disk_bus_for_profile(prof))
            if prof.driver_iso:
                logger.info("📀 Driver ISO: %s", prof.driver_iso)
            logger.info("🧩 Hyper-V features: %s", "on" if prof.hyperv else "off")
            logger.info("🕰️ Clock: %s", "localtime" if prof.localtime_clock else "utc")
            logger.info("🔐 TPM: %s", "on" if prof.tpm else "off")

        logger.info(
            "⚙️ Machine: %s | Firmware: %s | Graphics: %s | Network: %s | Video: %s",
            dom.machine,
            "UEFI" if fw.uefi else "BIOS",
            gfx.mode,
            dom.network,
            vid.model if gfx.mode != "none" else "none",
        )

        try:
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".xml") as f:
                f.write(xml)
                xml_path = Path(f.name)

            logger.debug("🧾 Generated domain XML at %s", xml_path)

            LibvirtTest._cleanup_domain(logger, dom.name)

            U.run_cmd(logger, ["virsh", "define", str(xml_path)], check=True, capture=True)
            U.run_cmd(logger, ["virsh", "start", dom.name], check=True, capture=True)

            if gfx.mode != "none":
                LibvirtTest._log_graphics_details(logger, dom.name)

            LibvirtTest._wait_running(logger, dom.name, dom.timeout_s)
            logger.info("✅ Smoke test passed: domain is RUNNING")
        finally:
            if not dom.keep:
                LibvirtTest._cleanup_domain(logger, dom.name)
                logger.info("🧹 Cleaned up libvirt domain: %s", dom.name)

                # If we created an NVRAM beside the disk, delete it too (common gotcha in repeated runs).
                if fw.uefi and nvram is not None:
                    try:
                        if nvram.exists():
                            U.safe_unlink(nvram)
                            logger.info("🧽 Removed NVRAM file: %s", nvram)
                    except Exception as e:
                        logger.debug("Could not remove NVRAM %s: %s", nvram, e)

            if xml_path is not None:
                U.safe_unlink(xml_path)

    # Helpers

    @staticmethod
    def _resolve_ovmf(logger: logging.Logger, fw: FirmwareConfig) -> OVMFPaths | None:
        if not fw.uefi:
            return None

        code = next((p for p in LibvirtTest._OVMF_CODE_CANDIDATES if os.path.exists(p)), None)
        vars_ = next((p for p in LibvirtTest._OVMF_VARS_CANDIDATES if os.path.exists(p)), None)
        logger.debug("🔎 OVMF probe: CODE=%s", code or "<missing>")
        logger.debug("🔎 OVMF probe: VARS=%s", vars_ or "<missing>")

        if not code or not vars_:
            U.die(logger, "💥 UEFI requested but OVMF not found (CODE/VARS missing).", 1)
        return OVMFPaths(code=code, vars=vars_)

    @staticmethod
    def _prepare_nvram(
        logger: logging.Logger,
        disk: Path,
        name: str,
        fw: FirmwareConfig,
        ovmf: OVMFPaths | None,
    ) -> Path | None:
        if not fw.uefi:
            return None
        if ovmf is None:
            raise RuntimeError("OVMF firmware unexpectedly None for UEFI boot")

        nvram = disk.parent / f"{name}.VARS.fd"
        if not nvram.exists():
            logger.info("🧬 Creating NVRAM VARS copy: %s", nvram)
            U.run_cmd(logger, ["cp", "-f", ovmf.vars, str(nvram)], check=True, capture=False)
        else:
            logger.debug("🧬 Reusing existing NVRAM VARS: %s", nvram)
        return nvram

    @staticmethod
    def _disk_format(logger: logging.Logger, disk: Path) -> str:
        suf = disk.suffix.lower().lstrip(".")
        if suf in ("qcow2", "raw", "vmdk", "vdi"):
            logger.debug("🧾 Disk format from suffix: %s", suf)
            return suf

        if U.which("qemu-img"):
            try:
                out = U.run_cmd(logger, ["qemu-img", "info", "--output=json", str(disk)], check=True, capture=True).stdout
                key = '"format"'
                i = out.find(key)
                if i != -1:
                    seg = out[i: i + 160]
                    c = seg.find(":")
                    q1 = seg.find('"', c + 1)
                    q2 = seg.find('"', q1 + 1)
                    if c != -1 and q1 != -1 and q2 != -1:
                        fmt = seg[q1 + 1: q2].strip().lower()
                        if fmt:
                            logger.debug("🧾 Disk format from qemu-img: %s", fmt)
                            return fmt
            except Exception as e:
                logger.debug("qemu-img info failed, falling back to qcow2: %s", e)

        logger.debug("🧾 Disk format fallback: qcow2")
        return "qcow2"

    @staticmethod
    def _disk_bus_for_profile(prof: GuestProfile) -> str:
        if prof.os != "windows":
            return "virtio"
        return "sata" if prof.win_stage == "bootstrap" else "virtio"

    @staticmethod
    def _disk_target_for_profile(prof: GuestProfile) -> tuple[str, str]:
        """
        Returns (dev, bus)
          - virtio => vda/virtio
          - sata => sda/sata (Windows bootstrap-friendly)
        """
        bus = LibvirtTest._disk_bus_for_profile(prof)
        if bus == "sata":
            return ("sda", "sata")
        return ("vda", "virtio")

    @staticmethod
    def _graphics_xml(gfx: GraphicsConfig) -> str:
        if gfx.mode == "none":
            return ""
        attrs = [f"type='{gfx.mode}'", "autoport='yes'", f"listen='{gfx.listen}'"]
        if not gfx.autoport:
            attrs = [f"type='{gfx.mode}'", "autoport='no'"]
            if gfx.port is None:
                raise ValueError("graphics.autoport=False requires graphics.port")
            attrs.append(f"port='{int(gfx.port)}'")
            attrs.append(f"listen='{gfx.listen}'")
        if gfx.passwd:
            attrs.append(f"passwd='{gfx.passwd}'")
        if gfx.keymap:
            attrs.append(f"keymap='{gfx.keymap}'")
        return f" <graphics {' '.join(attrs)}/>"

    @staticmethod
    def _video_xml(vid: VideoConfig, gfx: GraphicsConfig) -> str:
        if not vid.enabled or gfx.mode == "none":
            return ""
        return f"""    <video>
      <model type='{vid.model}' vram='{int(vid.vram)}'/>
    </video>"""

    @staticmethod
    def _input_xml(inp: InputConfig, gfx: GraphicsConfig) -> str:
        if gfx.mode == "none":
            return ""
        parts = []
        if inp.usb_tablet:
            parts.append(" <input type='tablet' bus='usb'/>")
        if inp.usb_kbd:
            parts.append(" <input type='keyboard' bus='usb'/>")
        if inp.usb_mouse:
            parts.append(" <input type='mouse' bus='usb'/>")
        return "\n".join(parts)

    @staticmethod
    def _clock_xml(prof: GuestProfile) -> str:
        if prof.os == "windows" and prof.localtime_clock:
            return " <clock offset='localtime'/>"
        return " <clock offset='utc'/>"

    @staticmethod
    def _features_xml(prof: GuestProfile) -> str:
        # Keep Linux baseline unchanged, add Windows Hyper-V hints when requested.
        base = [
            " <features>",
            " <acpi/>",
            " <apic/>",
        ]
        if prof.os == "windows" and prof.hyperv:
            base += [
                " <hyperv mode='custom'>",
                " <relaxed state='on'/>",
                " <vapic state='on'/>",
                " <spinlocks state='on' retries='8191'/>",
                " </hyperv>",
            ]
        base += [" </features>"]
        return "\n".join(base)

    @staticmethod
    def _tpm_xml(prof: GuestProfile) -> str:
        if not (prof.os == "windows" and prof.tpm):
            return ""
        # Most hosts use a swtpm socket at /run/libvirt/swtpm/<name>/swtpm-sock automatically
        # if created via virt-manager; here we only declare device. If socket doesn't exist,
        # libvirt start will fail (which is fine: it's a smoke test).
        return """    <tpm model='tpm-tis'>
      <backend type='emulator' version='2.0'/>
    </tpm>"""

    @staticmethod
    def _cdrom_xml(logger: logging.Logger, iso: Path | None) -> str:
        if not iso:
            return ""
        iso = Path(iso)
        if not iso.exists():
            U.die(logger, f"💥 Driver ISO not found: {iso}", 1)
        # attach as SATA CDROM (works broadly)
        return f"""    <disk type='file' device='cdrom'>
      <driver name='qemu' type='raw'/>
      <source file='{iso}'/>
      <target dev='sdc' bus='sata'/>
      <readonly/>
    </disk>"""

    @staticmethod
    def _build_domain_xml(
        *,
        logger: logging.Logger,
        disk: Path,
        dom: DomainConfig,
        fw: FirmwareConfig,
        ovmf: OVMFPaths | None,
        nvram: Path | None,
        gfx: GraphicsConfig,
        vid: VideoConfig,
        inp: InputConfig,
        prof: GuestProfile,
    ) -> str:
        disk_fmt = LibvirtTest._disk_format(logger, disk)
        (disk_dev, disk_bus) = LibvirtTest._disk_target_for_profile(prof)

        os_bits = [
            " <os>",
            f" <type arch='x86_64' machine='{dom.machine}'>hvm</type>",
        ]
        if fw.uefi:
            if ovmf is None or nvram is None:
                raise RuntimeError("OVMF firmware or NVRAM unexpectedly None for UEFI boot")
            os_bits.append(f" <loader readonly='yes' type='pflash'>{ovmf.code}</loader>")
            os_bits.append(f" <nvram>{nvram}</nvram>")
        else:
            os_bits.append(" <boot dev='hd'/>")
        os_bits.append(" </os>")
        os_xml = "\n".join(os_bits)

        clock_xml = LibvirtTest._clock_xml(prof)
        features_xml = LibvirtTest._features_xml(prof)

        gfx_xml = LibvirtTest._graphics_xml(gfx)
        vid_xml = LibvirtTest._video_xml(vid, gfx)
        inp_xml = LibvirtTest._input_xml(inp, gfx)
        tpm_xml = LibvirtTest._tpm_xml(prof)
        cdrom_xml = LibvirtTest._cdrom_xml(logger, prof.driver_iso)

        # Keep it simple and robust: virtio net always is usually fine (Windows has virtio-net driver),
        # but if you want absolute “always boots”, make model configurable too.
        xml = f"""<domain type='kvm'>
  <name>{dom.name}</name>

  <memory unit='MiB'>{dom.memory_mib}</memory>
  <vcpu>{dom.vcpus}</vcpu>

{os_xml}
{clock_xml}

{features_xml}

  <cpu mode='host-passthrough'/>

  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='{disk_fmt}'/>
      <source file='{disk}'/>
      <target dev='{disk_dev}' bus='{disk_bus}'/>
    </disk>
{cdrom_xml}

    <interface type='network'>
      <source network='{dom.network}'/>
      <model type='virtio'/>
    </interface>

    <console type='pty'/>
{gfx_xml}
{vid_xml}
{inp_xml}
{tpm_xml}
  </devices>
</domain>
"""
        return xml

    @staticmethod
    def _cleanup_domain(logger: logging.Logger, name: str) -> None:
        U.run_cmd(logger, ["virsh", "destroy", name], check=False, capture=True)
        U.run_cmd(logger, ["virsh", "undefine", name, "--nvram"], check=False, capture=True)
        U.run_cmd(logger, ["virsh", "undefine", name], check=False, capture=True)

    @staticmethod
    def _wait_running(logger: logging.Logger, name: str, timeout_s: int) -> None:
        t0 = time.time()
        last_state: str | None = None

        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("⏳ Waiting for domain start", total=timeout_s)
            while True:
                try:
                    st = U.run_cmd(logger, ["virsh", "domstate", name], check=True, capture=True).stdout.strip().lower()
                except Exception as e:
                    st = f"<error:{type(e).__name__}>"

                if st != last_state:
                    logger.debug("📡 domstate=%s", st)
                    last_state = st

                if "running" in st:
                    logger.info("🟢 Domain reached RUNNING state.")
                    return

                if time.time() - t0 > timeout_s:
                    try:
                        info = U.run_cmd(logger, ["virsh", "dominfo", name], check=False, capture=True).stdout.strip()
                        if info:
                            logger.debug("virsh dominfo:\n%s", info)
                    except Exception:
                        pass
                    U.die(logger, f"💥 Timeout waiting for domain to run (state={st})", 1)

                time.sleep(1)
                progress.update(task, advance=1)

    @staticmethod
    def _log_graphics_details(logger: logging.Logger, name: str) -> None:
        try:
            r = U.run_cmd(logger, ["virsh", "domdisplay", name], check=False, capture=True)
            s = (r.stdout or "").strip()
            if s:
                logger.info("🔗 Display URL: %s", s)
        except Exception as e:
            logger.debug("virsh domdisplay not available: %s", e)
