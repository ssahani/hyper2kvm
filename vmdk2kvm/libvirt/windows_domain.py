# SPDX-License-Identifier: GPL-2.0-or-later
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class WinDomainSpec:
    name: str
    img_path: str
    ovmf_code: str = "/usr/share/edk2/ovmf/OVMF_CODE.fd"
    nvram_vars: str = "/var/tmp/VM_VARS.fd"
    memory_mib: int = 8192
    vcpus: int = 4
    machine: str = "q35"
    net_model: str = "virtio"
    video: str = "qxl"
    graphics: str = "spice"
    disk_cache: str = "none"


def render_windows_domain_xml(spec: WinDomainSpec, *, stage: str) -> str:
    """
    stage:
      - "bootstrap" => disk on SATA (safe boot)
      - "final"     => disk on VirtIO (performance)
    """
    if stage not in ("bootstrap", "final"):
        raise ValueError(f"invalid stage: {stage}")

    if stage == "bootstrap":
        disk_bus = "sata"
        disk_dev = "sda"
    else:
        disk_bus = "virtio"
        disk_dev = "vda"

    # Keep NIC virtio in both stages (safe + fast; usually fine even before login).
    return f"""<domain type='kvm'>
  <name>{spec.name}</name>
  <memory unit='MiB'>{spec.memory_mib}</memory>
  <vcpu>{spec.vcpus}</vcpu>

  <os>
    <type arch='x86_64' machine='{spec.machine}'>hvm</type>
    <loader readonly='yes' type='pflash'>{spec.ovmf_code}</loader>
    <nvram>{spec.nvram_vars}</nvram>
  </os>

  <features><acpi/><apic/></features>
  <cpu mode='host-passthrough'/>
  <clock offset='localtime'/>

  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>

    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='{spec.disk_cache}'/>
      <source file='{spec.img_path}'/>
      <target dev='{disk_dev}' bus='{disk_bus}'/>
      <boot order='1'/>
    </disk>

    <interface type='network'>
      <source network='default'/>
      <model type='{spec.net_model}'/>
    </interface>

    <graphics type='{spec.graphics}'/>
    <input type='tablet' bus='usb'/>
    <video><model type='{spec.video}'/></video>

    <memballoon model='virtio'/>
  </devices>
</domain>
"""
