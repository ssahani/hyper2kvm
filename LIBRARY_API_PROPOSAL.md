# hyper2kvm Library API Proposal

## Overview

The hyper2kvm project can be used both as a **CLI tool** and as a **Python library**. This document proposes a clean public API for programmatic use.

## Current State

### Already Library-Ready ✅

These modules already have proper `__all__` exports:

- **`hyper2kvm.core`** - Guest detection, identity
- **`hyper2kvm.orchestrator`** - High-level orchestration
- **`hyper2kvm.azure`** - Azure VM migration

### Needs Improvement 🔧

These modules need `__all__` definitions:

- **`hyper2kvm.converters`** - Disk conversion utilities
- **`hyper2kvm.fixers`** - Guest OS fixers
- **`hyper2kvm.vmware`** - VMware/vSphere client
- **`hyper2kvm.testers`** - Boot testing

### Main Package 📦

The main `hyper2kvm/__init__.py` currently only exports `__version__`. It should expose the most commonly used APIs.

---

## Proposed Library API

### Level 1: High-Level API (Recommended for Most Users)

```python
from hyper2kvm import (
    # Main orchestrator
    Orchestrator,

    # Guest detection
    GuestIdentity,
    GuestDetector,
    GuestType,

    # Platform providers
    AzureSourceProvider,
    VMwareClient,

    # Version
    __version__,
)
```

### Level 2: Mid-Level API (Advanced Users)

```python
from hyper2kvm.orchestrator import (
    DiskProcessor,
    DiskDiscovery,
    VirtV2VConverter,
    VsphereExporter,
)

from hyper2kvm.converters import (
    Flatten,
    Convert,
    OVF,
)

from hyper2kvm.fixers import (
    OfflineFixer,
    NetworkFixer,
    CloudInitInjector,
)

from hyper2kvm.testers import (
    QemuTester,
    LibvirtTester,
)
```

### Level 3: Low-Level API (Library Developers)

```python
from hyper2kvm.vmware.clients import VMwareClient
from hyper2kvm.vmware.transports import VDDKTransport, HTTPTransport
from hyper2kvm.fixers.bootloader import GrubFixer, WindowsBootFixer
from hyper2kvm.fixers.filesystem import FstabFixer
```

---

## Usage Examples

### Example 1: Convert Local VMDK to qcow2

```python
from hyper2kvm.orchestrator import DiskProcessor
from hyper2kvm.core import GuestDetector

# Initialize processor
processor = DiskProcessor()

# Detect guest OS
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

print(f"Conversion complete: {result.output_path}")
```

### Example 2: Migrate from vSphere

```python
from hyper2kvm.vmware.clients import VMwareClient
from hyper2kvm.orchestrator import VsphereExporter

# Connect to vSphere
client = VMwareClient(
    host='vcenter.example.com',
    user='administrator@vsphere.local',
    password='password',
    datacenter='DC1'
)

# Export VM
exporter = VsphereExporter(client)
result = exporter.export_vm(
    vm_name='rhel9-prod',
    output_dir='/export/vms',
    transport='vddk',
    vddk_libdir='/opt/vmware-vix-disklib-distrib'
)

print(f"Exported {result.vm_name} to {result.output_dir}")
```

### Example 3: Migrate from Azure

```python
from hyper2kvm.azure import AzureSourceProvider, AzureConfig
from hyper2kvm.orchestrator import Orchestrator

# Configure Azure source
config = AzureConfig(
    subscription_id='xxx-xxx-xxx',
    resource_group='my-rg',
    vm_name='ubuntu-vm-01'
)

# Initialize provider
provider = AzureSourceProvider(config)

# Run migration
orchestrator = Orchestrator(source_provider=provider)
result = orchestrator.run(
    output_dir='/var/lib/libvirt/images',
    compress=True
)

print(f"Migration complete: {result.output_path}")
```

### Example 4: Standalone Guest Fixing

```python
from hyper2kvm.fixers import OfflineFixer
from hyper2kvm.core import GuestDetector

# Detect guest type
detector = GuestDetector()
guest = detector.detect('/mnt/guest-disk')

# Apply fixes
fixer = OfflineFixer(
    image_path='/var/lib/libvirt/images/vm.qcow2',
    guest_identity=guest
)

fixer.fix_fstab()
fixer.fix_grub()
fixer.fix_network()
fixer.regenerate_initramfs()

print(f"Fixes applied to {guest.os_pretty}")
```

### Example 5: Boot Testing

```python
from hyper2kvm.testers import QemuTester

# Test boot with QEMU
tester = QemuTester(
    image_path='/var/lib/libvirt/images/vm.qcow2',
    memory=4096,
    vcpus=2,
    uefi=True,
    timeout=120
)

result = tester.test_boot()

if result.success:
    print(f"Boot successful in {result.boot_time}s")
else:
    print(f"Boot failed: {result.error}")
```

---

## Implementation Plan

### Phase 1: Module `__all__` Definitions

1. **`hyper2kvm/converters/__init__.py`**
   ```python
   from .flatten import Flatten
   from .qemu.converter import Convert
   from .extractors.ovf import OVF

   __all__ = ["Flatten", "Convert", "OVF"]
   ```

2. **`hyper2kvm/fixers/__init__.py`**
   ```python
   from .offline_fixer import OfflineFixer
   from .network_fixer import NetworkFixer
   from .cloud_init_injector import CloudInitInjector

   __all__ = ["OfflineFixer", "NetworkFixer", "CloudInitInjector"]
   ```

3. **`hyper2kvm/vmware/__init__.py`**
   ```python
   from .clients import VMwareClient

   __all__ = ["VMwareClient"]
   ```

4. **`hyper2kvm/testers/__init__.py`**
   ```python
   from .qemu_tester import QemuTester
   from .libvirt_tester import LibvirtTester

   __all__ = ["QemuTester", "LibvirtTester"]
   ```

### Phase 2: Main Package API

**`hyper2kvm/__init__.py`**
```python
# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# hyper2kvm/__init__.py

__version__ = "0.0.1"

# High-level API exports
from .orchestrator import Orchestrator, DiskProcessor
from .core import GuestIdentity, GuestDetector, GuestType
from .azure import AzureSourceProvider, AzureConfig
from .vmware import VMwareClient

__all__ = [
    # Version
    "__version__",

    # Orchestration
    "Orchestrator",
    "DiskProcessor",

    # Guest detection
    "GuestIdentity",
    "GuestDetector",
    "GuestType",

    # Platform providers
    "AzureSourceProvider",
    "AzureConfig",
    "VMwareClient",
]
```

### Phase 3: Documentation

1. Create `docs/08-Library-API.md` with comprehensive API documentation
2. Add library usage examples to existing docs
3. Update README.md with library installation/usage section

### Phase 4: Testing

1. Add integration tests for library usage patterns
2. Ensure all public APIs are tested
3. Add examples to docstrings

---

## Benefits

### For Users

- **Programmatic control** - Use hyper2kvm in custom scripts/tools
- **Embedding** - Integrate migration into larger workflows
- **Flexibility** - Mix and match components as needed

### For Developers

- **Reusability** - Components can be used independently
- **Extensibility** - Easy to build custom providers/fixers
- **Testing** - Library code is easier to unit test

---

## Compatibility

- **CLI remains unchanged** - All existing CLI functionality preserved
- **Backward compatible** - Current imports continue to work
- **Gradual adoption** - Users can adopt library API incrementally

---

## Next Steps

1. **Review this proposal** - Confirm the API design
2. **Implement Phase 1** - Add `__all__` to submodules
3. **Implement Phase 2** - Update main `__init__.py`
4. **Create documentation** - Write library API guide
5. **Add examples** - Include in `examples/` directory
6. **Test thoroughly** - Ensure library usage patterns work

---

## Example Project Structure

```
hyper2kvm/
├── hyper2kvm/              # Library code
│   ├── __init__.py         # Main API exports
│   ├── core/               # ✅ Already library-ready
│   ├── orchestrator/       # ✅ Already library-ready
│   ├── azure/              # ✅ Already library-ready
│   ├── converters/         # 🔧 Needs __all__
│   ├── fixers/             # 🔧 Needs __all__
│   ├── vmware/             # 🔧 Needs __all__
│   ├── testers/            # 🔧 Needs __all__
│   └── cli/                # CLI-only code (not exported)
├── examples/               # Library usage examples
│   ├── local_conversion.py
│   ├── vsphere_export.py
│   ├── azure_migration.py
│   └── custom_workflow.py
├── docs/
│   └── 08-Library-API.md   # New library API guide
└── tests/
    └── integration/
        └── test_library_api.py
```

---

## Questions to Consider

1. **Naming**: Should we use `hyper2kvm` or create a separate `libhyper2kvm` package?
2. **Versioning**: How do we version the library API vs CLI?
3. **Stability**: Which APIs should be marked as stable vs experimental?
4. **Dependencies**: Should library mode have fewer dependencies than CLI mode?

---

**Status**: Proposal - Awaiting Review and Approval
