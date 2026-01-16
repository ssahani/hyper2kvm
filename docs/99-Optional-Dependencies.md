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
# Install system dependencies
sudo dnf install -y python3-libguestfs libguestfs-tools qemu-img

# Install hyper2kvm without Rich (works on RHEL 10)
pip install --user hyper2kvm

# Or with Rich from EPEL/external repo if available
pip install --user hyper2kvm[ui]
```

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
