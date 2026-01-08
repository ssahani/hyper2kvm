# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional


WinStage = Literal["bootstrap", "final"]


@dataclass(frozen=True)
class WinDomainSpec:
    """
    Windows domain XML spec (UEFI-focused).

    Notes:
      - stage=bootstrap => disk on SATA (boots even without VirtIO storage driver)
      - stage=final     => disk on VirtIO (performance, requires VirtIO storage driver installed)
      - graphics/video defaults are Windows-friendly for SPICE-based consoles
    """
    name: str
    img_path: str

    # Firmware / NVRAM
    ovmf_code: str = "/usr/share/edk2/ovmf/OVMF_CODE.fd"
    nvram_vars: str = "/var/tmp/VM_VARS.fd"

    # Compute
    memory_mib: int = 8192
    vcpus: int = 4
    machine: str = "q35"

    # Devices
    net_model: str = "virtio"

    # Display
    video: str = "qxl"
    graphics: str = "spice"
    graphics_listen: str = "127.0.0.1"  # safer default; change to 0.0.0.0 if you want remote consoles

    # Disk
    disk_cache: str = "none"
    disk_type: str = "qcow2"  # allow "raw" etc.

    # Optional: attach drivers ISO (virtio-win.iso) as CDROM for bootstrap
    driver_iso: Optional[str] = None

    # Windows niceties
    localtime_clock: bool = True
    hyperv: bool = True

    # Optional: add later if needed
    # tpm: bool = False


def render_windows_domain_xml(spec: WinDomainSpec, *, stage: WinStage) -> str:
    """
    stage:
      - "bootstrap" => disk on SATA (safe boot)
      - "final"     => disk on VirtIO (performance)
    """
    if stage not in ("bootstrap", "final"):
        raise ValueError(f"invalid stage: {stage}")

    img = Path(spec.img_path)
    if not img.exists():
        raise FileNotFoundError(f"image not found: {img}")

    # Sanity: firmware path must exist (don’t silently generate broken XML)
    if not os.path.exists(spec.ovmf_code):
        raise FileNotFoundError(f"OVMF_CODE not found: {spec.ovmf_code}")

    # Disk bus/dev selection
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
        iso = Path(spec.driver_iso)
        if not iso.exists():
            raise FileNotFoundError(f"driver ISO not found: {iso}")
        cdrom_xml = f"""
    <disk type='file' device='cdrom'>
      <driver name='qemu' type='raw' cache='none'/>
      <source file='{iso}'/>
      <target dev='sdc' bus='sata'/>
      <readonly/>
    </disk>"""

    # Clock: Windows often expects localtime
    clock_xml = "  <clock offset='localtime'/>" if spec.localtime_clock else "  <clock offset='utc'/>"

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
    graphics_xml = f"""
    <graphics type='{spec.graphics}'>
      <listen type='address' address='{spec.graphics_listen}'/>
    </graphics>"""

    video_xml = f"    <video><model type='{spec.video}'/></video>"

    input_xml = """
    <input type='tablet' bus='usb'/>
    <input type='keyboard' bus='usb'/>
    <input type='mouse' bus='usb'/>"""

    # NIC: keep virtio both stages
    nic_xml = f"""
    <interface type='network'>
      <source network='default'/>
      <model type='{spec.net_model}'/>
    </interface>"""

    # Make q35 less “surprising”: stable PCIe root ports help device placement
    pcie_rootports_xml = """
    <controller type='pci' model='pcie-root'/>
    <controller type='pci' model='pcie-root-port' index='1'>
      <target chassis='1' port='0x10'/>
    </controller>
    <controller type='pci' model='pcie-root-port' index='2'>
      <target chassis='2' port='0x11'/>
    </controller>
    <controller type='pci' model='pcie-root-port' index='3'>
      <target chassis='3' port='0x12'/>
    </controller>"""

    # Helpful extras for Windows guests
    rng_xml = "    <rng model='virtio'><backend model='random'>/dev/urandom</backend></rng>"
    panic_xml = "    <panic model='isa'/>"

    return f"""<domain type='kvm'>
  <name>{spec.name}</name>

  <metadata>
    <vmdk2kvm:stage xmlns:vmdk2kvm='https://github.com/ssahani/vmdk2kvm'>{stage}</vmdk2kvm:stage>
  </metadata>

  <description>Windows UEFI domain ({stage}): {stage_note}</description>

  <memory unit='MiB'>{spec.memory_mib}</memory>
  <vcpu>{spec.vcpus}</vcpu>

  <os>
    <type arch='x86_64' machine='{spec.machine}'>hvm</type>
    <loader readonly='yes' type='pflash'>{spec.ovmf_code}</loader>
    <nvram>{spec.nvram_vars}</nvram>
  </os>

  <features>
    <acpi/>
    <apic/>{hyperv_xml}
  </features>

  <cpu mode='host-passthrough'/>
{clock_xml}

  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
{pcie_rootports_xml}

    <disk type='file' device='disk'>
      <driver name='qemu' type='{spec.disk_type}' cache='{spec.disk_cache}'/>
      <source file='{img}'/>
      <target dev='{disk_dev}' bus='{disk_bus}'/>
      <boot order='1'/>
    </disk>{cdrom_xml}
{nic_xml}

{graphics_xml}
{input_xml}
{video_xml}

{rng_xml}
{panic_xml}

    <memballoon model='virtio'/>
  </devices>
</domain>
"""
