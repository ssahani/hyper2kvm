# Orchestrator Package - Refactored Architecture

## Overview

The orchestrator has been refactored from a single 1,197-line monolithic class into focused, maintainable components following the **Single Responsibility Principle**.

## Architecture

### Component Classes

#### 1. **VirtV2VConverter** (`virt_v2v_converter.py`)
- **Responsibility**: virt-v2v conversion operations
- **Methods**:
  - `convert()`: Single virt-v2v conversion
  - `convert_parallel()`: Parallel multi-disk conversions
- **Features**:
  - LUKS key handling (passphrase/keyfile)
  - Automatic output discovery
  - Temp file cleanup
  - Retry logic

#### 2. **VsphereExporter** (`vsphere_exporter.py`)
- **Responsibility**: vSphere VM export operations
- **Methods**:
  - `is_v2v_enabled()`: Check if export enabled
  - `get_vm_names()`: Extract VM names from args
  - `export_many_sync()`: Export VMs from vSphere
- **Features**:
  - Multiple export modes (v2v, download-only, VDDK)
  - Snapshot management
  - Credential resolution
  - Batch export with failure tracking

#### 3. **DiskDiscovery** (`disk_discovery.py`)
- **Responsibility**: Input disk detection and preparation
- **Methods**:
  - `discover()`: Discover disks based on input mode
- **Supported Inputs**:
  - Local VMDK files
  - Remote fetch-and-fix (SSH)
  - OVA/OVF archives
  - VHD/VHDX files
  - RAW/IMG files
  - AMI tarballs
  - Live-fix mode (SSH)

#### 4. **DiskProcessor** (`disk_processor.py`)
- **Responsibility**: Disk processing pipeline
- **Methods**:
  - `process_single_disk()`: Process one disk through pipeline
  - `process_disks_parallel()`: Process multiple disks in parallel
- **Pipeline Stages**:
  - Flatten (optional snapshot collapse)
  - Offline fixes (libguestfs)
  - Convert to output format
  - Validation

#### 5. **Orchestrator** (`orchestrator_refactored.py`)
- **Responsibility**: Main coordinator
- **Methods**:
  - `run()`: Main orchestration pipeline
  - `_setup_recovery()`: Initialize recovery manager
  - `_discover_disks()`: Delegate to DiskDiscovery
  - `_process_disks()`: Delegate to DiskProcessor
  - `_run_pre_v2v()`: Optional pre-processing v2v
  - `_run_post_v2v()`: Optional post-processing v2v
  - `_run_tests()`: Execute validation tests
  - `_emit_domain_xml()`: Generate libvirt XML

## Benefits of Refactoring

### Before (Monolithic)
```python
# orchestrator.py - 1,197 lines, 50+ methods
class Orchestrator:
    def v2v_convert(...)              # Lines 112-228
    def v2v_convert_parallel(...)     # Lines 234-322
    def _vsphere_export_many_sync(...) # Lines 348-524
    def _discover_disks(...)          # Lines 804-1013
    def process_single_disk(...)      # Lines 645-748
    def process_disks_parallel(...)   # Lines 750-794
    def run(...)                      # Lines 1015-1181
    # ... 40+ more methods
```

### After (Focused Components)
```python
# 5 focused classes, each < 300 lines
VirtV2VConverter      # 270 lines - virt-v2v only
VsphereExporter       # 280 lines - vSphere only
DiskDiscovery         # 260 lines - disk discovery only
DiskProcessor         # 310 lines - processing pipeline only
Orchestrator          # 290 lines - coordination only
```

### Improvements
1. **Maintainability**: Each class has a clear, focused purpose
2. **Testability**: Components can be tested in isolation
3. **Reusability**: Components can be used independently
4. **Readability**: Smaller, focused files are easier to understand
5. **Extensibility**: New input/output modes can be added easily
6. **Debugging**: Issues isolated to specific components

## Usage

### Using the Orchestrator

```python
from hyper2kvm.orchestrator import Orchestrator

# Create orchestrator
orch = Orchestrator(logger, args)

# Run full pipeline
orch.run()
```

**Note**: The monolithic orchestrator has been replaced with this refactored version. A backup of the original is preserved as `orchestrator.py.backup-*` for reference.

### Using Individual Components

```python
from hyper2kvm.orchestrator import (
    VirtV2VConverter,
    VsphereExporter,
    DiskDiscovery,
    DiskProcessor,
)

# Just virt-v2v conversion
converter = VirtV2VConverter(logger)
output = converter.convert(disks, out_root, "qcow2", compress=True)

# Just disk discovery
discovery = DiskDiscovery(logger, args)
disks, temp_dir = discovery.discover(out_root)

# Just disk processing
processor = DiskProcessor(logger, args)
result = processor.process_single_disk(disk, out_root, 0, 1)
```

## Migration Complete

### Status

✅ **The refactored orchestrator is now the active implementation**

- Original monolithic `orchestrator.py` (1,197 lines) has been **replaced**
- Backup preserved as `orchestrator.py.backup-20260115-014819`
- All existing imports work without changes
- No breaking changes to existing code

### Import Patterns (All Work)

```python
# Pattern 1: Package-level import (recommended)
from hyper2kvm.orchestrator import Orchestrator

# Pattern 2: Direct module import (as used in __main__.py)
from hyper2kvm.orchestrator.orchestrator import Orchestrator

# Both reference the same refactored class
```

## Testing

All components are designed for independent testing:

```python
# tests/orchestrator/test_virt_v2v_converter.py
def test_v2v_converter(mocker):
    logger = mocker.Mock()
    converter = VirtV2VConverter(logger)
    # Test virt-v2v logic in isolation
    ...

# tests/orchestrator/test_disk_discovery.py
def test_discover_local_vmdk(mocker):
    logger, args = mocker.Mock(), mocker.Mock()
    args.cmd = "local"
    args.vmdk = "/path/to/disk.vmdk"

    discovery = DiskDiscovery(logger, args)
    disks, temp_dir = discovery.discover(Path("/out"))

    assert len(disks) == 1
    assert temp_dir is None
```

## File Organization

```
hyper2kvm/orchestrator/
├── __init__.py                           # Package exports
├── README.md                             # This file
├── orchestrator.py                       # Main coordinator (refactored)
├── orchestrator.py.backup-*              # Original monolithic version (backup)
├── virt_v2v_converter.py                 # virt-v2v operations
├── vsphere_exporter.py                   # vSphere export
├── disk_discovery.py                     # Disk discovery
└── disk_processor.py                     # Disk processing
```

## Performance Considerations

### Parallel Processing

Both the refactored and legacy implementations support parallel processing:

```python
# Parallel disk processing (multi-threaded)
args.parallel_processing = True

# Parallel virt-v2v (multi-process)
args.v2v_parallel = True
args.v2v_concurrency = 4
```

**Note**: Consider using `ProcessPoolExecutor` instead of `ThreadPoolExecutor` for CPU-bound operations to avoid GIL limitations.

## Future Enhancements

Potential improvements now easier to implement:

1. **Plugin System**: Add custom disk sources/processors
2. **Alternative Fixers**: Swap out libguestfs for alternatives
3. **Cloud Integration**: Add AWS/Azure/GCP direct export
4. **Progress Tracking**: Better real-time progress reporting
5. **Metrics Collection**: Add telemetry and performance monitoring
6. **Configuration Validation**: Pydantic models for args validation

## Contributing

When adding new features:

1. Determine which component it belongs to
2. If it doesn't fit, create a new focused component
3. Keep classes under 300 lines when possible
4. Add unit tests for the component
5. Update this README with new functionality

## Questions?

For issues or questions about the refactored architecture, please open a GitHub issue with the `refactoring` label.
