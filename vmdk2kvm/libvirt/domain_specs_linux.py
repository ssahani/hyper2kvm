# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# vmdk2kvm/libvirt/domain_specs_linux.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

Firmware = Literal["bios", "uefi"]
Graphics = Literal["none", "vnc", "spice"]


@dataclass(frozen=True)
class LinuxDomainSpec:
    """
    Linux domain XML spec.

    Defaults are “console-first” (works great over SSH):
      - graphics=none => no GUI, keep serial/console enabled
      - virtio disk + virtio net
      - UTC clock default (common for Linux servers)
      - optional cloud-init seed ISO attachment
    """
    name: str
    img_path: str

    # Firmware
    firmware: Firmware = "bios"
    ovmf_code: str = "/usr/share/edk2/ovmf/OVMF_CODE.fd"
    nvram_vars: str = "/var/tmp/VM_VARS.fd"

    # Compute
    memory_mib: int = 2048
    vcpus: int = 2
    machine: str = "q35"

    # Disk
    disk_bus: str = "virtio"   # virtio | sata | scsi ...
    disk_dev: str = "vda"
    disk_type: str = "qcow2"   # qcow2/raw
    disk_cache: str = "none"

    # Network
    network: str = "default"
    net_model: str = "virtio"

    # Display
    graphics: Graphics = "none"
    graphics_listen: str = "127.0.0.1"
    video: str = "virtio"      # virtio/qxl/vga/bochs...
    usb_tablet: bool = True

    # Console
    serial_pty: bool = True
    console_pty: bool = True

    # Optional cloud-init seed ISO
    cloudinit_iso: Optional[str] = None

    # Clock
    clock: Literal["utc", "localtime"] = "utc"


def render_linux_domain_xml(spec: LinuxDomainSpec) -> str:
    img = Path(spec.img_path)
    if not img.exists():
        raise FileNotFoundError(f"image not found: {img}")

    # Firmware validation
    os_xml = [
        "  <os>",
        f"    <type arch='x86_64' machine='{spec.machine}'>hvm</type>",
    ]
    if spec.firmware == "uefi":
        if not os.path.exists(spec.ovmf_code):
            raise FileNotFoundError(f"OVMF_CODE not found: {spec.ovmf_code}")
        os_xml.append(f"    <loader readonly='yes' type='pflash'>{spec.ovmf_code}</loader>")
        os_xml.append(f"    <nvram>{spec.nvram_vars}</nvram>")
    elif spec.firmware == "bios":
        os_xml.append("    <boot dev='hd'/>")
    else:
        raise ValueError(f"invalid firmware: {spec.firmware}")
    os_xml.append("  </os>")

    # Optional cloud-init ISO
    cidata_xml = ""
    if spec.cloudinit_iso:
        iso = Path(spec.cloudinit_iso)
        if not iso.exists():
            raise FileNotFoundError(f"cloud-init ISO not found: {iso}")
        # attach as CDROM (SATA is broadly compatible)
        cidata_xml = f"""
    <disk type='file' device='cdrom'>
      <driver name='qemu' type='raw' cache='none'/>
      <source file='{iso}'/>
      <target dev='sdc' bus='sata'/>
      <readonly/>
    </disk>"""

    # Graphics/video/input
    graphics_xml = ""
    video_xml = ""
    input_xml = ""
    if spec.graphics != "none":
        graphics_xml = f"    <graphics type='{spec.graphics}' listen='{spec.graphics_listen}' autoport='yes'/>"
        video_xml = f"    <video><model type='{spec.video}'/></video>"
        if spec.usb_tablet:
            input_xml = "    <input type='tablet' bus='usb'/>"

    # Console / serial
    serial_xml = "    <serial type='pty'/>" if spec.serial_pty else ""
    console_xml = "    <console type='pty'/>" if spec.console_pty else ""

    clock_xml = "  <clock offset='utc'/>" if spec.clock == "utc" else "  <clock offset='localtime'/>"

    return f"""<domain type='kvm'>
  <name>{spec.name}</name>
  <memory unit='MiB'>{spec.memory_mib}</memory>
  <vcpu>{spec.vcpus}</vcpu>

{'\n'.join(os_xml)}
{clock_xml}

  <features>
    <acpi/>
    <apic/>
  </features>

  <cpu mode='host-passthrough'/>

  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>

    <disk type='file' device='disk'>
      <driver name='qemu' type='{spec.disk_type}' cache='{spec.disk_cache}'/>
      <source file='{img}'/>
      <target dev='{spec.disk_dev}' bus='{spec.disk_bus}'/>
      <boot order='1'/>
    </disk>{cidata_xml}

    <interface type='network'>
      <source network='{spec.network}'/>
      <model type='{spec.net_model}'/>
    </interface>

{serial_xml}
{console_xml}
{graphics_xml}
{input_xml}
{video_xml}

    <memballoon model='virtio'/>
  </devices>
</domain>
"""
