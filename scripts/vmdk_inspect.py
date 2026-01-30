#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""
vmdk_inspect.py (v1.1)

Enterprise-grade VMDK inspection tool for ESXi → KVM migration.

Exit codes:
  0 = OK
  2 = HIGH risks present
  3 = FATAL risks present
"""

import re
import sys
import json
import glob
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional


# ============================================================
# Risk model
# ============================================================

@dataclass
class Risk:
    level: str   # FATAL | HIGH | MEDIUM | INFO
    message: str


# ============================================================
# Parsed VMDK information
# ============================================================

@dataclass
class VMDKInfo:
    path: Path

    create_type: Optional[str] = None
    parent_cid: Optional[str] = None
    adapter_type: Optional[str] = None
    thin: bool = False

    sectors: Optional[int] = None
    extent_type: Optional[str] = None
    extent_file: Optional[str] = None

    geometry: dict = field(default_factory=dict)

    boot_mode: Optional[str] = None  # BIOS | UEFI | UNKNOWN
    risks: List[Risk] = field(default_factory=list)

    @property
    def size_bytes(self):
        return self.sectors * 512 if self.sectors else None

    @property
    def size_gb(self):
        if self.size_bytes:
            return round(self.size_bytes / (1024 ** 3), 2)
        return None


# ============================================================
# Constants
# ============================================================

FATAL_CONTROLLERS = {"buslogic"}
HIGH_RISK_CONTROLLERS = {"lsilogic", "lsilogicsas"}

EXTENT_RE = re.compile(r'^RW\s+(\d+)\s+(\w+)\s+"(.+)"')


# ============================================================
# Descriptor parsing
# ============================================================

def parse_vmdk_descriptor(path: Path) -> VMDKInfo:
    info = VMDKInfo(path=path)

    with path.open(errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("createType"):
                info.create_type = _val(line)

            elif line.startswith("parentCID"):
                info.parent_cid = _val(line)

            elif line.startswith("ddb.adapterType"):
                info.adapter_type = _val(line).lower()

            elif line.startswith("ddb.thinProvisioned"):
                info.thin = _val(line) == "1"

            elif line.startswith("ddb.geometry"):
                key = line.split(".")[-1].split("=")[0]
                info.geometry[key] = _val(line)

            elif line.startswith("RW"):
                m = EXTENT_RE.match(line)
                if m:
                    info.sectors = int(m.group(1))
                    info.extent_type = m.group(2)
                    info.extent_file = m.group(3)

    analyze_risks(info)
    detect_boot_mode(info)
    return info


def _val(line: str) -> str:
    return line.split("=", 1)[1].strip().strip('"')


# ============================================================
# Risk analysis
# ============================================================

def analyze_risks(info: VMDKInfo):
    # Snapshot
    if info.parent_cid and info.parent_cid.lower() != "ffffffff":
        info.risks.append(Risk(
            "FATAL",
            "Snapshot chain detected (parentCID != ffffffff)"
        ))

    # Controller
    if info.adapter_type:
        at = info.adapter_type

        if at in FATAL_CONTROLLERS:
            info.risks.append(Risk(
                "FATAL",
                f"Legacy controller '{at}' – unsupported on KVM"
            ))

        elif at in HIGH_RISK_CONTROLLERS:
            info.risks.append(Risk(
                "HIGH",
                f"Controller '{at}' – initramfs may lack driver"
            ))

        if at != "virtio" and at not in FATAL_CONTROLLERS:
            info.risks.append(Risk(
                "HIGH",
                f"Controller mismatch: guest expects '{at}', libvirt will use virtio"
            ))
    else:
        info.risks.append(Risk(
            "MEDIUM",
            "Missing ddb.adapterType"
        ))

    # Geometry
    if info.geometry:
        info.risks.append(Risk(
            "INFO",
            "Legacy CHS geometry present (ignored by modern kernels)"
        ))

    # Extent validation
    if info.extent_type == "VMFS":
        info.risks.append(Risk(
            "INFO",
            "VMFS-backed extent – convert using descriptor only"
        ))

    if info.extent_file and info.sectors:
        flat = info.path.parent / info.extent_file
        expected = info.sectors * 512

        if not flat.exists():
            info.risks.append(Risk(
                "FATAL",
                f"Extent file missing: {flat}"
            ))
        else:
            actual = flat.stat().st_size
            if actual < expected:
                info.risks.append(Risk(
                    "FATAL",
                    f"Extent size mismatch: expected ≥ {expected}, got {actual}"
                ))


# ============================================================
# Boot mode detection (UEFI vs BIOS)
# ============================================================

def detect_boot_mode(info: VMDKInfo):
    """
    Detect UEFI by checking for EFI System Partition using libguestfs.
    """
    flat = info.path.parent / info.extent_file if info.extent_file else None
    if not flat or not flat.exists():
        info.boot_mode = "UNKNOWN"
        return

    try:
        cmd = [
            "virt-inspector",
            "--no-applications",
            "--no-icon",
            str(flat)
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)

        if "firmware=\"uefi\"" in out.lower():
            info.boot_mode = "UEFI"
            info.risks.append(Risk(
                "HIGH",
                "UEFI guest detected – libvirt domain must use OVMF firmware"
            ))
        else:
            info.boot_mode = "BIOS"

    except FileNotFoundError:
        info.boot_mode = "UNKNOWN"
        info.risks.append(Risk(
            "INFO",
            "libguestfs not available – boot mode detection skipped"
        ))
    except subprocess.CalledProcessError:
        info.boot_mode = "UNKNOWN"
        info.risks.append(Risk(
            "INFO",
            "Unable to inspect guest boot mode"
        ))


# ============================================================
# libvirt XML generation
# ============================================================

def generate_libvirt_disk_xml(image_path: str, boot_mode: str = "BIOS") -> str:
    """Generate libvirt disk XML configuration."""
    disk_xml = f"""
<disk type='file' device='disk'>
  <driver name='qemu' type='qcow2' cache='none' io='native'/>
  <source file='{image_path}'/>
  <target dev='vda' bus='virtio'/>
</disk>

<controller type='scsi' index='0' model='virtio-scsi'/>
""".strip()

    if boot_mode == "UEFI":
        disk_xml += """

<!-- UEFI firmware configuration required -->
<os>
  <type arch='x86_64' machine='pc-q35'>hvm</type>
  <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
  <nvram>/var/lib/libvirt/qemu/nvram/GUEST_NAME_VARS.fd</nvram>
</os>
"""

    return disk_xml


# ============================================================
# CLI
# ============================================================

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} [--json] <vmdk | glob>")
        sys.exit(1)

    json_mode = "--json" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--json"]

    vmdks = []
    for a in args:
        vmdks.extend(Path(x) for x in glob.glob(a))

    if not vmdks:
        print("ERROR: no VMDK files found")
        sys.exit(1)

    worst = 0
    results = []

    for vmdk in vmdks:
        info = parse_vmdk_descriptor(vmdk)

        levels = {r.level for r in info.risks}
        if "FATAL" in levels:
            worst = max(worst, 3)
        elif "HIGH" in levels:
            worst = max(worst, 2)

        if not json_mode:
            print(f"\n=== {vmdk} ===")
            print(f"Size      : {info.size_gb} GB")
            print(f"Adapter   : {info.adapter_type}")
            print(f"Boot mode : {info.boot_mode}")
            for r in info.risks:
                print(f"[{r.level}] {r.message}")

            print("\nSuggested libvirt XML:")
            print(generate_libvirt_disk_xml(
                "/var/lib/libvirt/images/disk.qcow2",
                info.boot_mode or "BIOS"
            ))
        else:
            results.append({
                "file": str(vmdk),
                "size_gb": info.size_gb,
                "adapter": info.adapter_type,
                "boot_mode": info.boot_mode,
                "risks": [
                    {"level": r.level, "message": r.message}
                    for r in info.risks
                ]
            })

    if json_mode:
        print(json.dumps(results, indent=2))

    sys.exit(worst)


if __name__ == "__main__":
    main()
