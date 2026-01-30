# VMDK Inspector

Enterprise-grade VMDK inspection and pre-migration risk analysis.

## Overview

The VMDK Inspector performs comprehensive validation of VMDK files **before** migration to detect:

- **Controller compatibility** issues (BusLogic, LSI Logic, etc.)
- **Snapshot chains** (parentCID verification)
- **Boot firmware mode** (UEFI vs BIOS)
- **Extent file** integrity
- **Size mismatches**
- **Migration risks** with severity levels

This prevents migration failures by catching issues early.

---

## Quick Start

### CLI Usage

```bash
# Inspect single VMDK
./scripts/vmdk_inspect.py /path/to/disk.vmdk

# Inspect multiple VMDKs
./scripts/vmdk_inspect.py /vms/*.vmdk

# JSON output for automation
./scripts/vmdk_inspect.py --json /path/to/disk.vmdk
```

### Library Usage

```python
from hyper2kvm.validation import VMDKInspector, RiskLevel
from pathlib import Path

# Create inspector
inspector = VMDKInspector()

# Inspect VMDK
result = inspector.inspect(Path("/path/to/disk.vmdk"))

# Check results
if result.has_fatal_risks:
    print("FATAL: Migration will fail!")
    for risk in result.risks:
        if risk.level == RiskLevel.FATAL:
            print(f"  - {risk.message}")
elif result.has_high_risks:
    print("WARNING: High risk of boot failure")

# Boot mode detection
if result.boot_mode == BootMode.UEFI:
    print("UEFI detected - use OVMF firmware in libvirt")

# Generate libvirt config
xml = inspector.generate_libvirt_config(
    result,
    "/var/lib/libvirt/images/disk.qcow2"
)
print(xml)
```

---

## Risk Levels

| Level | Description | Action Required |
|-------|-------------|-----------------|
| **FATAL** | Migration will fail | Must fix before migration |
| **HIGH** | Boot failure likely | Initramfs rebuild needed |
| **MEDIUM** | Minor compatibility issue | Review configuration |
| **INFO** | Informational only | No action required |

---

## Detected Issues

### 1. Snapshot Chains (FATAL)

**Problem**: VMDK has `parentCID != ffffffff`

**Fix**: Consolidate snapshots in VMware before migration

```bash
# In vSphere:
# Right-click VM → Snapshots → Consolidate
```

### 2. Legacy Controllers (FATAL)

**Problem**: BusLogic controller detected

**Fix**: No fix available - BusLogic not supported on KVM. Change controller in VMware first.

### 3. Controller Mismatch (HIGH)

**Problem**: Guest expects `lsilogic` but KVM uses `virtio`

**Fix**: hyper2kvm automatically rebuilds initramfs with virtio drivers

### 4. UEFI vs BIOS (HIGH)

**Problem**: UEFI guest detected

**Action**: Use OVMF firmware in libvirt domain

```xml
<os>
  <type arch='x86_64' machine='pc-q35'>hvm</type>
  <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
  <nvram>/var/lib/libvirt/qemu/nvram/VM_NAME_VARS.fd</nvram>
</os>
```

### 5. Missing Extent Files (FATAL)

**Problem**: Descriptor references extent file that doesn't exist

**Fix**: Verify VMDK files are complete before migration

### 6. Size Mismatch (FATAL)

**Problem**: Extent file smaller than expected

**Fix**: Re-export VMDK from vSphere

---

## Exit Codes (CLI)

| Code | Meaning |
|------|---------|
| `0` | No issues or only INFO/MEDIUM |
| `2` | HIGH risk detected |
| `3` | FATAL risk detected |

Use in scripts:

```bash
#!/bin/bash
if ! ./scripts/vmdk_inspect.py disk.vmdk; then
    echo "Pre-migration validation failed!"
    exit 1
fi

# Proceed with migration
hyper2kvm --config migration.yaml
```

---

## JSON Output Format

```json
[
  {
    "file": "/path/to/disk.vmdk",
    "size_gb": 50.0,
    "adapter": "lsilogic",
    "boot_mode": "UEFI",
    "risks": [
      {
        "level": "HIGH",
        "message": "Controller 'lsilogic' – initramfs may require rebuild",
        "component": "controller"
      },
      {
        "level": "HIGH",
        "message": "UEFI firmware detected - libvirt domain MUST use OVMF",
        "component": "boot"
      }
    ]
  }
]
```

---

## Integration with Pipeline

The VMDK Inspector is automatically used during pre-migration validation:

```python
from hyper2kvm.validation import VMDKInspector
from hyper2kvm.orchestrator import Orchestrator

# Inspector runs before conversion
inspector = VMDKInspector(logger)
result = inspector.inspect(vmdk_path)

if result.has_fatal_risks:
    raise MigrationError("Pre-migration validation failed")
```

---

## Boot Mode Detection

Uses `virt-inspector` from libguestfs to detect UEFI:

```bash
# Manual boot mode check
virt-inspector --no-applications --no-icon disk.vmdk
```

If libguestfs is not installed, boot mode detection is skipped (INFO risk added).

### Install libguestfs

```bash
# Fedora/RHEL
sudo dnf install libguestfs-tools

# Ubuntu/Debian
sudo apt install libguestfs-tools
```

---

## Examples

### Example 1: Valid VMDK

```bash
$ ./scripts/vmdk_inspect.py test.vmdk

=== /vms/test.vmdk ===
Size      : 20.0 GB
Adapter   : lsilogic
Boot mode : BIOS
[HIGH] Controller 'lsilogic' – initramfs may require rebuild
[INFO] Legacy CHS geometry present (ignored by modern kernels)

Suggested libvirt XML:
<disk type='file' device='disk'>
  <driver name='qemu' type='qcow2' cache='none' io='native'/>
  <source file='/var/lib/libvirt/images/disk.qcow2'/>
  <target dev='vda' bus='virtio'/>
</disk>
```

Exit code: `2` (HIGH risk)

### Example 2: Snapshot Chain (FATAL)

```bash
$ ./scripts/vmdk_inspect.py snapshot.vmdk

=== /vms/snapshot.vmdk ===
Size      : 10.0 GB
Adapter   : lsilogic
Boot mode : BIOS
[FATAL] Snapshot chain detected (parentCID != ffffffff)
```

Exit code: `3` (FATAL risk)

### Example 3: UEFI Guest

```bash
$ ./scripts/vmdk_inspect.py uefi-guest.vmdk

=== /vms/uefi-guest.vmdk ===
Size      : 40.0 GB
Adapter   : lsilogic
Boot mode : UEFI
[HIGH] UEFI firmware detected - libvirt domain MUST use OVMF
[HIGH] Controller mismatch: guest expects 'lsilogic', KVM will use virtio

Suggested libvirt XML:
<disk type='file' device='disk'>
  <driver name='qemu' type='qcow2' cache='none' io='native'/>
  <source file='/var/lib/libvirt/images/disk.qcow2'/>
  <target dev='vda' bus='virtio'/>
</disk>

<!-- UEFI firmware configuration (REQUIRED for UEFI guests) -->
<os>
  <type arch='x86_64' machine='pc-q35'>hvm</type>
  <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
  <nvram>/var/lib/libvirt/qemu/nvram/VM_NAME_VARS.fd</nvram>
</os>
```

---

## API Reference

### VMDKInspector

```python
class VMDKInspector:
    def __init__(self, logger: Optional[logging.Logger] = None)

    def inspect(self, vmdk_path: Path) -> VMDKInspectionResult

    def generate_libvirt_config(
        self,
        result: VMDKInspectionResult,
        converted_image_path: str
    ) -> str
```

### VMDKInspectionResult

```python
@dataclass
class VMDKInspectionResult:
    path: Path
    valid: bool

    # Metadata
    create_type: Optional[str]
    parent_cid: Optional[str]
    adapter_type: Optional[str]
    thin_provisioned: bool

    # Size
    sectors: Optional[int]
    extent_type: Optional[str]
    extent_file: Optional[str]

    # Boot mode
    boot_mode: BootMode  # BIOS | UEFI | UNKNOWN

    # Risks
    risks: List[Risk]

    # Properties
    @property
    def size_gb(self) -> Optional[float]

    @property
    def has_fatal_risks(self) -> bool

    @property
    def has_high_risks(self) -> bool

    @property
    def max_risk_level(self) -> Optional[RiskLevel]

    def to_dict(self) -> Dict[str, Any]
```

---

## See Also

- [Migration Guide](../guides/migration/)
- [Troubleshooting](../guides/troubleshooting.md)
- [VMCraft Inspection](vmcraft-inspection.md)
- [Validation Framework](validation-framework.md)
