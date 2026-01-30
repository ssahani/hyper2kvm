# Optional Dependencies

hyper2kvm is designed to work with minimal dependencies, making it suitable for enterprise Linux distributions like RHEL where some Python packages may not be available in official repositories.

## Installation Options

### Minimal Installation (RHEL/Enterprise Linux)

For systems where only official repositories are available:

```bash
pip install hyper2kvm
```

This installs only core dependencies:
- `click` - Command-line interface
- `pyyaml` - Configuration file support

**What works with minimal installation:**
- ✅ Local VMDK/VHD/QCOW2 conversion
- ✅ Offline guest OS fixes (requires system libguestfs)
- ✅ All core migration functionality
- ❌ Progress bars (fallback to simple logging)
- ❌ vSphere integration (requires optional vsphere extras)
- ❌ Azure integration (requires optional azure extras)

### With UI Enhancements (Recommended)

Install with Rich library for better terminal UI:

```bash
pip install hyper2kvm[ui]
```

**Additional features:**
- ✅ Interactive progress bars
- ✅ Colored output
- ✅ Real-time transfer speed display

### With vSphere Support

For VMware vSphere/vCenter migrations:

```bash
pip install hyper2kvm[vsphere]
```

**Additional features:**
- ✅ Direct vSphere VM export
- ✅ VDDK disk downloads
- ✅ CBT (Changed Block Tracking)
- ✅ Snapshot management

### With Azure Support

For Microsoft Azure VM migrations:

```bash
pip install hyper2kvm[azure]
```

**Additional features:**
- ✅ Azure VM discovery and download
- ✅ Managed disk export
- ✅ Azure authentication

### Full Installation

Install all optional dependencies:

```bash
pip install hyper2kvm[full]
```

Or combine specific extras:

```bash
pip install hyper2kvm[ui,vsphere,azure]
```

## System Dependencies

Regardless of Python package installation method, these system packages are required:

### Required
- `qemu-img` - Disk format conversion
- `python3-libguestfs` - Offline guest filesystem access
- `libguestfs-tools` - Guest inspection utilities

### Optional
- `virt-v2v` - Alternative migration path (not required for basic usage)
- `libvirt` - For running smoke tests
- `govc` - Alternative vSphere export method

## RHEL 10 Installation Example

```bash
# Install system dependencies (all available in RHEL 10 base repos)
sudo dnf install -y python3-libguestfs libguestfs-tools qemu-img python3-pyyaml

# Install hyper2kvm (minimal - only click from PyPI)
pip install --user hyper2kvm

# Or with UI enhancements (requires rich from PyPI)
pip install --user hyper2kvm[ui]

# With vSphere support (requires pyvmomi from PyPI)
pip install --user hyper2kvm[vsphere]
```

### What's NOT in RHEL 10 Base Repos

The following packages require PyPI or external repos:

**UI Libraries:**
- `rich` - Progress bars and colored output (optional)

**Cloud/Virtualization SDKs:**
- `pyvmomi` - VMware vSphere SDK (only for vSphere integration)
- `azure-identity`, `azure-mgmt-*`, `azure-storage-blob` - Azure SDK (only for Azure)
- `paramiko` - SSH client (only for SSH operations)

**Utility Libraries:**
- `click` - CLI framework (required, but small - from PyPI)
- `pycdlib` - ISO extraction (optional, can use system isoinfo instead)

All core migration functionality works with only system packages + click from PyPI.

## Behavior Without Rich

When Rich library is not available, hyper2kvm automatically falls back to:

### Progress Indicators
**With Rich:**
```
Flattening ━━━━━━━━━━━━━━━━━━━━ 45% 0:00:12 0:00:15
```

**Without Rich:**
```
20:03:02 INFO Flattening progress: 45.0%
```

### File Downloads
**With Rich:**
```
Downloading ━━━━━━━━━━━━━━━━━━ 512 MB/1 GB 150 MB/s
```

**Without Rich:**
```
20:03:05 INFO Download: 512 MB / 1024 MB (50%)
```

### Configuration Loading
**With Rich:**
```
Loading configs ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:01
```

**Without Rich:**
```
20:03:01 INFO Loading configuration files...
20:03:02 INFO Loaded 5 configuration files
```

## Checking What's Available

You can check which optional dependencies are installed:

```bash
python3 -c "from hyper2kvm.core.optional_imports import *; print(f'Rich: {RICH_AVAILABLE}, Requests: {REQUESTS_AVAILABLE}, PyVmomi: {PYVMOMI_AVAILABLE}')"
```

Or use the built-in diagnostic:

```bash
hyper2kvm --version --verbose
```

## Feature Matrix

| Feature | Minimal | +UI | +vSphere | +Azure | +Full |
|---------|---------|-----|----------|--------|-------|
| Local disk conversion | ✅ | ✅ | ✅ | ✅ | ✅ |
| Offline guest fixes | ✅ | ✅ | ✅ | ✅ | ✅ |
| Progress bars | ❌ | ✅ | ✅ | ✅ | ✅ |
| vSphere export | ❌ | ❌ | ✅ | ❌ | ✅ |
| Azure export | ❌ | ❌ | ❌ | ✅ | ✅ |
| HTTP downloads | ❌ | ❌ | ✅ | ✅ | ✅ |

## Troubleshooting

### Import Errors

If you see import errors for optional dependencies:

```python
ImportError: cannot import name 'Progress' from 'rich.progress'
```

This usually means:
1. You're using a feature that requires optional dependencies
2. Install the appropriate extras: `pip install hyper2kvm[ui]`

### RHEL/CentOS Compatibility

Rich is not available in RHEL 10 base repositories. Options:

1. **Use minimal installation** (recommended for production):
   ```bash
   pip install hyper2kvm  # Works without Rich
   ```

2. **Install Rich from PyPI** (if external packages allowed):
   ```bash
   pip install --user rich
   pip install --user hyper2kvm
   ```

3. **Build RPM with vendored dependencies** (for air-gapped systems):
   See `PACKAGING.md` for RPM build instructions.

## See Also

- [Installation Guide](01-Installation.md)
- [Configuration](02-Configuration.md)
- [Library API](08-Library-API.md)

## Complete Package Availability Matrix

### Available in RHEL 10 Base Repositories

| Package | RHEL Package Name | Purpose | Required |
|---------|-------------------|---------|----------|
| libguestfs | python3-libguestfs | Guest filesystem access | ✅ Yes |
| PyYAML | python3-pyyaml | YAML config parsing | ✅ Yes |
| qemu-img | qemu-img | Disk conversion | ✅ Yes |
| libguestfs-tools | libguestfs-tools | Guest inspection | ✅ Yes |
| requests | python3-requests | HTTP client | Optional |
| urllib3 | python3-urllib3 | HTTP utilities | Optional |

### NOT in RHEL 10 - Require PyPI

| Package | Purpose | When Needed | Install Extra |
|---------|---------|-------------|---------------|
| rich | Progress bars, UI | Optional (recommended) | `[ui]` |
| click | CLI framework | Always | Core dependency |
| pyvmomi | VMware vSphere SDK | vSphere migrations | `[vsphere]` |
| requests | HTTP client | vSphere/Azure | `[vsphere]` or `[azure]` |
| azure-identity | Azure auth | Azure migrations | `[azure]` |
| azure-mgmt-compute | Azure VM management | Azure migrations | `[azure]` |
| azure-mgmt-network | Azure network | Azure migrations | `[azure]` |
| azure-mgmt-resource | Azure resources | Azure migrations | `[azure]` |
| azure-storage-blob | Azure storage | Azure migrations | `[azure]` |
| paramiko | SSH client | SSH operations | Optional |
| pycdlib | ISO extraction | VirtIO ISO sources | Optional |

### Installation Strategy for RHEL 10

**Option 1: Minimal (Most Restrictive Environment)**
```bash
# System packages only
sudo dnf install -y python3-libguestfs libguestfs-tools qemu-img python3-pyyaml

# Minimal pip install (only click)
pip install --user hyper2kvm

# Works for:
# ✅ Local VMDK/VHD/QCOW2 conversion
# ✅ All offline guest fixes
# ✅ All core functionality
# ❌ No progress bars (logs instead)
# ❌ No vSphere direct integration
# ❌ No Azure integration
```

**Option 2: With UI (Recommended)**
```bash
# System packages
sudo dnf install -y python3-libguestfs libguestfs-tools qemu-img python3-pyyaml

# With Rich for better UX
pip install --user hyper2kvm[ui]

# Adds:
# ✅ Interactive progress bars
# ✅ Colored output
# ✅ Real-time speed display
```

**Option 3: With vSphere**
```bash
# For VMware vSphere migrations
pip install --user hyper2kvm[vsphere]

# Adds:
# ✅ Direct vSphere VM export
# ✅ VDDK support
# ✅ Snapshot management
# ✅ CBT (Changed Block Tracking)
```

**Option 4: Full Featured**
```bash
# Everything including Azure
pip install --user hyper2kvm[full]
```

### Alternative: Using RPM Build

For air-gapped or strictly controlled RHEL environments, build an RPM with bundled dependencies:

```bash
# On build system (with internet)
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm
make rpm  # or rpmbuild -ba hyper2kvm.spec

# Transfer RPM to target system
sudo dnf install ./hyper2kvm-*.rpm
```

The RPM includes all Python dependencies bundled, requiring only system packages like libguestfs.

### Checking Available Features

To see what features are available in your installation:

```bash
python3 << 'PYEOF'
from hyper2kvm.core.optional_imports import (
    RICH_AVAILABLE,
    REQUESTS_AVAILABLE, 
    PYVMOMI_AVAILABLE,
    PARAMIKO_AVAILABLE
)

print(f"""
hyper2kvm Feature Availability
==============================
✅ Core Migration: Always available
{'✅' if RICH_AVAILABLE else '❌'} Progress Bars: {RICH_AVAILABLE}
{'✅' if PYVMOMI_AVAILABLE else '❌'} vSphere Integration: {PYVMOMI_AVAILABLE}
{'✅' if REQUESTS_AVAILABLE else '❌'} HTTP Downloads: {REQUESTS_AVAILABLE}
{'✅' if PARAMIKO_AVAILABLE else '❌'} SSH Operations: {PARAMIKO_AVAILABLE}
""")
PYEOF
```

### Performance Impact

**Without Rich (minimal install):**
- No performance impact on actual migration
- Slightly less frequent progress updates (every 2-5% vs real-time)
- No visual overhead from terminal rendering

**With Rich:**
- Real-time progress bars (~60 FPS updates)
- Colored output
- Minimal CPU overhead (<0.1%)
