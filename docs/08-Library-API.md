# hyper2kvm Library API

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [API Levels](#api-levels)
  - [Level 1: High-Level API (Recommended)](#level-1-high-level-api-recommended)
  - [Level 2: Mid-Level API](#level-2-mid-level-api)
  - [Level 3: Low-Level API](#level-3-low-level-api)
- [Usage Examples](#usage-examples)
  - [Local VMDK Conversion](#local-vmdk-conversion)
  - [vSphere Migration](#vsphere-migration)
  - [Azure Migration](#azure-migration)
  - [Guest OS Fixing](#guest-os-fixing)
  - [Boot Testing](#boot-testing)
  - [Custom Workflows](#custom-workflows)
- [API Reference](#api-reference)
  - [Orchestration](#orchestration)
  - [Guest Detection](#guest-detection)
  - [Platform Providers](#platform-providers)
  - [Converters](#converters)
  - [Fixers](#fixers)
  - [Testers](#testers)
- [Error Handling](#error-handling)
- [Best Practices](#best-practices)
- [Migration from CLI to Library](#migration-from-cli-to-library)

---

## Overview

hyper2kvm can be used both as a **command-line tool** and as a **Python library**. The library API provides programmatic control over VM migration, allowing you to:

- **Embed migrations** in custom workflows
- **Build automation tools** for large-scale migrations
- **Integrate** with existing infrastructure management systems
- **Customize behavior** beyond CLI capabilities

### Design Principles

- **Simple by default** - High-level API for common use cases
- **Flexible when needed** - Low-level components for customization
- **Backward compatible** - CLI functionality preserved
- **Well-documented** - Comprehensive examples and API reference

---

## Installation

### As a Library

```bash
pip install hyper2kvm
```

### Development Installation

```bash
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm
pip install -e .
```

### Dependencies

The library requires the same dependencies as the CLI:

```bash
# Fedora/RHEL
sudo dnf install -y \
    python3-rich \
    python3-click \
    python3-pyyaml \
    python3-requests \
    python3-pyvmomi \
    libguestfs-tools \
    qemu-img

# Ubuntu/Debian
sudo apt install -y \
    python3-rich \
    python3-click \
    python3-yaml \
    python3-requests \
    python3-pyvmomi \
    libguestfs-tools \
    qemu-utils
```

---

## Quick Start

### Basic Local Conversion

```python
from hyper2kvm import DiskProcessor

# Convert VMDK to qcow2
processor = DiskProcessor()
result = processor.process_disk(
    source_path='/data/vm.vmdk',
    output_path='/data/vm.qcow2',
    flatten=True,
    compress=True
)

print(f"Conversion complete: {result.output_path}")
```

### Detect Guest OS

```python
from hyper2kvm import GuestDetector

# Detect guest operating system
detector = GuestDetector()
guest = detector.detect('/mnt/guest-disk')

print(f"Detected: {guest.os_pretty}")
print(f"Type: {guest.guest_type}")
```

### Full Migration Workflow

```python
from hyper2kvm import Orchestrator, VMwareClient

# Connect to vSphere
client = VMwareClient(
    host='vcenter.example.com',
    user='administrator@vsphere.local',
    password='password',
    datacenter='DC1'
)

# Run migration
orchestrator = Orchestrator(vmware_client=client)
result = orchestrator.run(
    vm_name='production-web-01',
    output_dir='/var/lib/libvirt/images',
    compress=True
)

print(f"Migration complete: {result.output_path}")
```

---

## API Levels

### Level 1: High-Level API (Recommended)

For most users, the high-level API provides everything needed:

```python
from hyper2kvm import (
    # Main orchestrator
    Orchestrator,
    DiskProcessor,

    # Guest detection
    GuestIdentity,
    GuestDetector,
    GuestType,

    # Platform providers
    AzureSourceProvider,
    AzureConfig,
    VMwareClient,

    # Version
    __version__,
)
```

**Use cases:**
- Standard VM migrations
- Batch conversions
- Integration with management tools

### Level 2: Mid-Level API

For advanced users who need more control:

```python
from hyper2kvm.orchestrator import (
    VirtV2VConverter,
    VsphereExporter,
)

from hyper2kvm.converters import (
    Flatten,
    Convert,
    OVF,
)

from hyper2kvm.fixers import (
    OfflineFSFix,
    NetworkFixer,
    LiveFixer,
)

from hyper2kvm.testers import (
    QemuTest,
    LibvirtTest,
)
```

**Use cases:**
- Custom conversion pipelines
- Selective guest OS fixes
- Integration testing

### Level 3: Low-Level API

For library developers and specialized workflows:

```python
from hyper2kvm.vmware.clients import VMwareClient
from hyper2kvm.vmware.transports import VDDKTransport, HTTPTransport
from hyper2kvm.fixers.bootloader import GrubFixer
from hyper2kvm.fixers.filesystem import FstabFixer
from hyper2kvm.fixers.network import NetworkTopology
```

**Use cases:**
- Building custom migration tools
- Implementing new platform providers
- Deep customization of fixers

---

## Usage Examples

### Local VMDK Conversion

Convert a local VMDK file to qcow2 with compression:

```python
from hyper2kvm import DiskProcessor, GuestDetector

# Initialize processor
processor = DiskProcessor()

# Optional: Detect guest OS for optimizations
detector = GuestDetector()
guest = detector.detect('/mnt/source-disk')

# Convert disk
result = processor.process_disk(
    source_path='/data/vm.vmdk',
    output_path='/data/vm.qcow2',
    flatten=True,
    compress=True,
    guest_identity=guest
)

print(f"Conversion complete!")
print(f"  Input:  {result.source_path}")
print(f"  Output: {result.output_path}")
print(f"  Size:   {result.output_size} bytes")
print(f"  Time:   {result.duration}s")
```

### vSphere Migration

Migrate a VM from vCenter/ESXi to KVM:

```python
from hyper2kvm import VMwareClient, Orchestrator

# Connect to vSphere
client = VMwareClient(
    host='vcenter.example.com',
    user='administrator@vsphere.local',
    password='password',
    datacenter='DC1',
    insecure=False  # Set True to skip SSL verification
)

# List available VMs
vms = client.list_vms()
print(f"Found {len(vms)} VMs")

# Export specific VM
result = client.export_vm(
    vm_name='rhel9-prod',
    output_dir='/export/vms',
    transport='vddk',
    vddk_libdir='/opt/vmware-vix-disklib-distrib'
)

print(f"Exported {result.vm_name}")
print(f"  Disks: {len(result.disks)}")
print(f"  Path:  {result.output_dir}")
```

### Azure Migration

Migrate a VM from Azure to KVM:

```python
from hyper2kvm import AzureSourceProvider, AzureConfig, Orchestrator

# Configure Azure source
config = AzureConfig(
    subscription_id='your-subscription-id',
    resource_group='my-rg',
    vm_name='ubuntu-vm-01',
    # Optional: Use managed identity or service principal
    tenant_id='your-tenant-id',
    client_id='your-client-id',
    client_secret='your-client-secret'
)

# Initialize provider
provider = AzureSourceProvider(config)

# Run full migration
orchestrator = Orchestrator(source_provider=provider)
result = orchestrator.run(
    output_dir='/var/lib/libvirt/images',
    compress=True,
    apply_fixes=True
)

print(f"Migration complete!")
print(f"  Source: {result.source_vm}")
print(f"  Output: {result.output_path}")
print(f"  Fixes:  {len(result.fixes_applied)}")
```

### Guest OS Fixing

Apply offline fixes to a converted disk image:

```python
from hyper2kvm.fixers import OfflineFSFix
from hyper2kvm import GuestDetector

# Detect guest type
detector = GuestDetector()
guest = detector.detect('/mnt/guest-disk')

print(f"Detected: {guest.os_pretty}")

# Apply fixes
fixer = OfflineFSFix(
    image_path='/var/lib/libvirt/images/vm.qcow2',
    guest_identity=guest,
    verbose=True
)

# Fix fstab (UUID-based mounting)
fstab_result = fixer.fix_fstab()
print(f"Fixed fstab: {fstab_result.changes_made} changes")

# Fix GRUB bootloader
grub_result = fixer.fix_grub()
print(f"Fixed GRUB: {grub_result.success}")

# Fix network configuration
network_result = fixer.fix_network()
print(f"Fixed network: {network_result.interfaces_fixed} interfaces")

# Regenerate initramfs
initramfs_result = fixer.regenerate_initramfs()
print(f"Regenerated initramfs: {initramfs_result.success}")

# Generate report
report = fixer.generate_report()
print(f"\nReport saved to: {report.path}")
```

### Boot Testing

Test a migrated VM boots correctly:

```python
from hyper2kvm.testers import QemuTest

# Test boot with QEMU
tester = QemuTest(
    image_path='/var/lib/libvirt/images/vm.qcow2',
    memory=4096,
    vcpus=2,
    uefi=True,
    timeout=120,
    headless=False  # Set True for automated testing
)

# Run boot test
result = tester.test_boot()

if result.success:
    print(f"✓ Boot successful in {result.boot_time}s")
    print(f"  Console output: {result.console_log}")
else:
    print(f"✗ Boot failed: {result.error}")
    print(f"  Last output: {result.last_console_lines}")
```

### Custom Workflows

Build a custom migration pipeline:

```python
from hyper2kvm import VMwareClient, GuestDetector
from hyper2kvm.converters import Flatten, Convert
from hyper2kvm.fixers import OfflineFSFix
from hyper2kvm.testers import LibvirtTest
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_vm(vcenter_host, vm_name, output_dir):
    """Custom migration workflow."""

    # Step 1: Export from vSphere
    logger.info(f"Exporting {vm_name} from vCenter...")
    client = VMwareClient(host=vcenter_host, user='admin', password='pass')
    export_result = client.export_vm(vm_name, output_dir='/tmp/export')

    # Step 2: Flatten VMDK
    logger.info("Flattening VMDK...")
    flattener = Flatten()
    flat_vmdk = flattener.flatten(
        source=export_result.disks[0],
        output=f'/tmp/{vm_name}-flat.vmdk'
    )

    # Step 3: Convert to qcow2
    logger.info("Converting to qcow2...")
    converter = Convert()
    qcow2_path = f'{output_dir}/{vm_name}.qcow2'
    converter.convert(
        source=flat_vmdk,
        output=qcow2_path,
        format='qcow2',
        compress=True
    )

    # Step 4: Detect guest and apply fixes
    logger.info("Detecting guest OS...")
    detector = GuestDetector()
    guest = detector.detect_from_image(qcow2_path)

    logger.info(f"Applying fixes for {guest.os_pretty}...")
    fixer = OfflineFSFix(image_path=qcow2_path, guest_identity=guest)
    fixer.fix_fstab()
    fixer.fix_grub()
    fixer.fix_network()

    # Step 5: Boot test
    logger.info("Testing boot...")
    tester = LibvirtTest(
        image_path=qcow2_path,
        memory=4096,
        vcpus=2,
        uefi=(guest.firmware == 'uefi')
    )
    test_result = tester.test_boot()

    if not test_result.success:
        raise RuntimeError(f"Boot test failed: {test_result.error}")

    logger.info(f"Migration complete: {qcow2_path}")
    return qcow2_path

# Run migration
result = migrate_vm(
    vcenter_host='vcenter.example.com',
    vm_name='production-web-01',
    output_dir='/var/lib/libvirt/images'
)
```

---

## API Reference

### Orchestration

#### `Orchestrator`

High-level orchestrator for complete VM migrations.

```python
class Orchestrator:
    def __init__(
        self,
        source_provider=None,
        vmware_client=None,
        azure_provider=None,
        config=None
    ):
        """Initialize orchestrator with source provider."""
        ...

    def run(
        self,
        vm_name=None,
        output_dir=None,
        compress=True,
        apply_fixes=True,
        test_boot=False
    ):
        """
        Run complete migration workflow.

        Returns:
            MigrationResult with details of the migration
        """
        ...
```

#### `DiskProcessor`

Process individual disk images.

```python
class DiskProcessor:
    def process_disk(
        self,
        source_path: str,
        output_path: str,
        flatten: bool = False,
        compress: bool = False,
        guest_identity=None
    ):
        """
        Convert and process a disk image.

        Args:
            source_path: Input disk path (VMDK, VHD, etc.)
            output_path: Output qcow2 path
            flatten: Flatten multi-part VMDKs
            compress: Compress output image
            guest_identity: Optional GuestIdentity for optimizations

        Returns:
            ProcessResult with conversion details
        """
        ...
```

### Guest Detection

#### `GuestDetector`

Detect guest operating system from disk images.

```python
class GuestDetector:
    def detect(self, mount_point: str) -> GuestIdentity:
        """Detect guest OS from mounted filesystem."""
        ...

    def detect_from_image(self, image_path: str) -> GuestIdentity:
        """Detect guest OS from disk image (auto-mounts)."""
        ...
```

#### `GuestIdentity`

Information about detected guest OS.

```python
@dataclass
class GuestIdentity:
    guest_type: GuestType
    os_id: str
    os_version: str
    os_pretty: str
    architecture: str
    firmware: str  # 'bios' or 'uefi'
    init_system: str  # 'systemd', 'upstart', 'sysv'
    package_manager: str  # 'dnf', 'apt', 'zypper', etc.
```

#### `GuestType`

Enum of supported guest OS types.

```python
class GuestType(Enum):
    LINUX = "linux"
    WINDOWS = "windows"
    UNKNOWN = "unknown"
```

### Platform Providers

#### `VMwareClient`

vSphere/vCenter client for VM export.

```python
class VMwareClient:
    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        datacenter: str = None,
        insecure: bool = False
    ):
        """Connect to vCenter/ESXi."""
        ...

    def list_vms(self) -> List[str]:
        """List all VM names."""
        ...

    def export_vm(
        self,
        vm_name: str,
        output_dir: str,
        transport: str = 'vddk',
        vddk_libdir: str = None
    ):
        """Export VM to local disk."""
        ...
```

#### `AzureSourceProvider`

Azure VM migration provider.

```python
class AzureSourceProvider:
    def __init__(self, config: AzureConfig):
        """Initialize with Azure configuration."""
        ...

    def download_vm(self, output_dir: str):
        """Download VM disks from Azure."""
        ...
```

#### `AzureConfig`

Azure connection configuration.

```python
@dataclass
class AzureConfig:
    subscription_id: str
    resource_group: str
    vm_name: str
    tenant_id: str = None
    client_id: str = None
    client_secret: str = None
```

### Converters

#### `Flatten`

Flatten multi-part VMDK files.

```python
class Flatten:
    def flatten(self, source: str, output: str) -> str:
        """Flatten VMDK snapshot chain."""
        ...
```

#### `Convert`

Convert between disk formats.

```python
class Convert:
    def convert(
        self,
        source: str,
        output: str,
        format: str = 'qcow2',
        compress: bool = False
    ) -> str:
        """Convert disk format using qemu-img."""
        ...
```

#### `OVF`

Extract VMs from OVF/OVA packages.

```python
class OVF:
    def extract(self, source: str, output_dir: str):
        """Extract OVF/OVA package."""
        ...
```

### Fixers

#### `OfflineFSFix`

Offline guest OS fixer (libguestfs-based).

```python
class OfflineFSFix:
    def __init__(
        self,
        image_path: str,
        guest_identity: GuestIdentity,
        verbose: bool = False
    ):
        """Initialize offline fixer."""
        ...

    def fix_fstab(self) -> FixResult:
        """Fix /etc/fstab for KVM."""
        ...

    def fix_grub(self) -> FixResult:
        """Fix GRUB bootloader configuration."""
        ...

    def fix_network(self) -> FixResult:
        """Fix network interface configuration."""
        ...

    def regenerate_initramfs(self) -> FixResult:
        """Regenerate initramfs with virtio drivers."""
        ...

    def remove_vmware_tools(self) -> FixResult:
        """Remove VMware Tools."""
        ...

    def generate_report(self) -> Report:
        """Generate migration report."""
        ...
```

#### `NetworkFixer`

Advanced network configuration fixer.

```python
class NetworkFixer:
    def fix(self, guest: guestfs.GuestFS) -> FixResult:
        """Fix network configuration for KVM."""
        ...
```

#### `LiveFixer`

Online fixer (for running VMs).

```python
class LiveFixer:
    def __init__(self, ssh_host: str, ssh_user: str, ssh_key: str):
        """Initialize live fixer with SSH access."""
        ...

    def apply_fixes(self) -> FixResult:
        """Apply fixes to running VM."""
        ...
```

### Testers

#### `QemuTest`

QEMU-based boot testing.

```python
class QemuTest:
    def __init__(
        self,
        image_path: str,
        memory: int = 2048,
        vcpus: int = 1,
        uefi: bool = False,
        timeout: int = 120,
        headless: bool = True
    ):
        """Initialize QEMU tester."""
        ...

    def test_boot(self) -> TestResult:
        """Test if VM boots successfully."""
        ...
```

#### `LibvirtTest`

Libvirt-based boot testing.

```python
class LibvirtTest:
    def __init__(
        self,
        image_path: str,
        memory: int = 2048,
        vcpus: int = 1,
        uefi: bool = False,
        timeout: int = 120
    ):
        """Initialize libvirt tester."""
        ...

    def test_boot(self) -> TestResult:
        """Test boot using libvirt."""
        ...
```

---

## Error Handling

All library functions raise exceptions on errors. Use standard Python exception handling:

```python
from hyper2kvm import VMwareClient, Orchestrator
from hyper2kvm.exceptions import (
    ConnectionError,
    ConversionError,
    GuestDetectionError,
    BootTestError
)

try:
    client = VMwareClient(host='vcenter.example.com', ...)
    orchestrator = Orchestrator(vmware_client=client)
    result = orchestrator.run(vm_name='prod-vm')

except ConnectionError as e:
    print(f"Failed to connect to vCenter: {e}")

except ConversionError as e:
    print(f"Disk conversion failed: {e}")
    print(f"  Source: {e.source_path}")
    print(f"  Output: {e.output_path}")

except GuestDetectionError as e:
    print(f"Could not detect guest OS: {e}")

except BootTestError as e:
    print(f"Boot test failed: {e}")
    print(f"  Console: {e.console_output}")

except Exception as e:
    print(f"Unexpected error: {e}")
```

### Common Exceptions

- `ConnectionError` - Failed to connect to source platform
- `AuthenticationError` - Invalid credentials
- `ConversionError` - Disk conversion failed
- `GuestDetectionError` - Could not identify guest OS
- `FixerError` - Guest OS fix failed
- `BootTestError` - Boot test failed
- `ValidationError` - Configuration validation failed

---

## Best Practices

### 1. Always Detect Guest OS

Guest detection enables optimizations and proper fixes:

```python
# Good
detector = GuestDetector()
guest = detector.detect_from_image(image_path)
fixer = OfflineFSFix(image_path, guest_identity=guest)

# Less optimal
fixer = OfflineFSFix(image_path)  # Will auto-detect, but slower
```

### 2. Use Context Managers for Cleanup

```python
from hyper2kvm import VMwareClient

with VMwareClient(host='vcenter.example.com', ...) as client:
    result = client.export_vm('vm-name', '/output')
    # Connection automatically closed
```

### 3. Enable Verbose Logging for Debugging

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Now all hyper2kvm operations will log details
```

### 4. Test Boots Before Production

```python
from hyper2kvm.testers import QemuTest

# Always test boot after migration
tester = QemuTest(image_path=result.output_path, timeout=180)
test_result = tester.test_boot()

if not test_result.success:
    raise RuntimeError(f"Boot test failed: {test_result.error}")
```

### 5. Generate Migration Reports

```python
# Generate detailed report of all changes
fixer = OfflineFSFix(image_path, guest_identity=guest)
fixer.fix_fstab()
fixer.fix_grub()
fixer.fix_network()

report = fixer.generate_report()
print(f"Report saved to: {report.path}")
```

### 6. Handle Partial Failures Gracefully

```python
fixes_applied = []
fixes_failed = []

for fix_name, fix_func in [
    ('fstab', fixer.fix_fstab),
    ('grub', fixer.fix_grub),
    ('network', fixer.fix_network),
]:
    try:
        result = fix_func()
        if result.success:
            fixes_applied.append(fix_name)
        else:
            fixes_failed.append((fix_name, result.error))
    except Exception as e:
        fixes_failed.append((fix_name, str(e)))

print(f"Applied {len(fixes_applied)} fixes")
print(f"Failed {len(fixes_failed)} fixes")
```

---

## Migration from CLI to Library

If you're using the CLI and want to migrate to the library, here's how:

### CLI Command

```bash
sudo python -m hyper2kvm vsphere \
    --vcenter vcenter.example.com \
    --user administrator@vsphere.local \
    --password-env VC_PASSWORD \
    --datacenter DC1 \
    --vm rhel9-prod \
    --output-dir /var/lib/libvirt/images \
    --compress
```

### Equivalent Library Code

```python
import os
from hyper2kvm import VMwareClient, Orchestrator

# Get password from environment
password = os.environ['VC_PASSWORD']

# Connect to vSphere
client = VMwareClient(
    host='vcenter.example.com',
    user='administrator@vsphere.local',
    password=password,
    datacenter='DC1'
)

# Run migration
orchestrator = Orchestrator(vmware_client=client)
result = orchestrator.run(
    vm_name='rhel9-prod',
    output_dir='/var/lib/libvirt/images',
    compress=True
)

print(f"Migration complete: {result.output_path}")
```

### Batch Operations

CLI:

```bash
for vm in vm1 vm2 vm3; do
    sudo python -m hyper2kvm vsphere --vm $vm ...
done
```

Library:

```python
from hyper2kvm import VMwareClient, Orchestrator

client = VMwareClient(...)
orchestrator = Orchestrator(vmware_client=client)

for vm_name in ['vm1', 'vm2', 'vm3']:
    try:
        result = orchestrator.run(vm_name=vm_name, ...)
        print(f"✓ Migrated {vm_name}")
    except Exception as e:
        print(f"✗ Failed {vm_name}: {e}")
```

---

## Next Steps

- **[Quick Start Guide](03-Quick-Start.md)** - CLI usage
- **[Architecture](01-Architecture.md)** - Internal design
- **[Cookbook](06-Cookbook.md)** - Advanced scenarios
- **[API Examples](/examples)** - Complete example scripts

---

**Status**: Library API fully implemented and documented
