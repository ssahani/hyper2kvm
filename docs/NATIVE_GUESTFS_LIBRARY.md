# VMCraft: Python Library for VM Disk Image Manipulation

## Overview

The native GuestFS implementation in hyper2kvm has evolved into **VMCraft** - a comprehensive Python library for crafting and manipulating VM disk images. This document outlines the vision and roadmap for extracting it into its own standalone library.

## Why Make It a Library?

### Current Benefits
1. **No libguestfs dependency** - Eliminates complex C library dependency
2. **Fast startup** - ~1-2s vs 5-10s for libguestfs appliance boot
3. **Low memory footprint** - No appliance VM required
4. **Transparent operation** - Uses standard Linux tools
5. **Easy debugging** - All operations visible in process list

### Additional Benefits as Standalone Library
1. **Broader adoption** - Useful beyond VM migration scenarios
2. **Independent versioning** - Evolve separately from hyper2kvm
3. **Community contributions** - Easier for others to contribute
4. **Focused testing** - Dedicated test suite and CI/CD
5. **Clear documentation** - Standalone docs and examples
6. **Multiple use cases**:
   - Disk image forensics
   - Backup/restore tools
   - Configuration management
   - Cloud image customization
   - Container image manipulation

## Feature Matrix

### Currently Implemented (in hyper2kvm)

**Core Operations:**
- ✅ NBD device management (qemu-nbd integration)
- ✅ Storage stack activation (LVM, LUKS, mdraid, ZFS)
- ✅ Automatic OS detection (Linux and Windows)
- ✅ Mount/umount with filesystem-specific options
- ✅ File operations (read, write, mkdir, cp, rm, etc.)
- ✅ Upload/download files between host and guest
- ✅ Performance metrics tracking

**Linux Support:**
- ✅ ext2/3/4, XFS, Btrfs, ZFS filesystems
- ✅ OS detection via /etc/os-release
- ✅ fstab parsing
- ✅ Command execution via chroot
- ✅ LVM volume management
- ✅ LUKS encryption support

**Windows Support:**
- ✅ NTFS, FAT32, exFAT filesystems
- ✅ OS detection via registry parsing
- ✅ Case-insensitive path resolution
- ✅ Driver injection to DriverStore
- ✅ Registry read/write (SOFTWARE, SYSTEM, SAM hives)
- ✅ Windows-specific path handling

**API Compatibility:**
- ✅ Drop-in replacement for guestfs.GuestFS
- ✅ python_return_dict=True semantics
- ✅ 60+ guestfs API methods implemented
- ✅ Context manager support
- ✅ Factory pattern for backend selection

### Roadmap for Standalone Library

**Phase 1: Extract Core Library** (1-2 weeks)
- [ ] Create new repository: `vmcraft`
- [ ] Extract core modules:
  - `vmcraft/core.py` - Main GuestFS class
  - `vmcraft/nbd.py` - NBD device management
  - `vmcraft/storage.py` - Storage stack activation
  - `vmcraft/windows.py` - Windows-specific operations
  - `vmcraft/factory.py` - Backend factory
- [ ] Remove hyper2kvm-specific dependencies
- [ ] Create standalone `pyproject.toml` with dependencies
- [ ] Add CLI tool: `vmcraft` command

**Phase 2: Enhanced Testing** (1 week)
- [ ] Comprehensive unit tests (pytest)
- [ ] Integration tests with real disk images
- [ ] Windows disk image tests
- [ ] Multi-disk scenarios
- [ ] Error condition tests
- [ ] Performance benchmarks

**Phase 3: Documentation** (1 week)
- [ ] API reference (Sphinx)
- [ ] User guide with examples
- [ ] Cookbook for common tasks
- [ ] Windows-specific guide
- [ ] Comparison with libguestfs
- [ ] System requirements per OS

**Phase 4: Packaging & Distribution** (1 week)
- [ ] PyPI package: `pip install vmcraft`
- [ ] GitHub repository with CI/CD
- [ ] Docker images with all dependencies
- [ ] Debian/Ubuntu packages
- [ ] Fedora/RHEL packages
- [ ] Homebrew formula (macOS)

**Phase 5: Additional Features** (ongoing)
- [ ] Multi-disk support (RAID configurations)
- [ ] Partition operations (resize, create, delete)
- [ ] Snapshot support
- [ ] Network block device support (iSCSI, NBD over network)
- [ ] Virtual machine configuration editing
- [ ] Bootloader installation/repair
- [ ] SELinux/AppArmor context handling
- [ ] File ACLs and extended attributes

## Proposed Library Structure

```
vmcraft/
├── pyproject.toml
├── README.md
├── LICENSE (LGPL-3.0)
├── docs/
│   ├── index.md
│   ├── api.md
│   ├── windows.md
│   ├── cookbook.md
│   └── comparison.md
├── vmcraft/
│   ├── __init__.py
│   ├── core.py              # NativeGuestFS class
│   ├── nbd.py               # NBD management
│   ├── storage.py           # LVM/LUKS/mdraid/ZFS
│   ├── windows.py           # Windows operations
│   ├── linux.py             # Linux operations
│   ├── factory.py           # Backend factory
│   ├── utils.py             # Utilities
│   └── cli.py               # Command-line interface
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── examples/
    ├── basic_usage.py
    ├── windows_driver_inject.py
    ├── registry_edit.py
    └── forensics.py
```

## API Design

### Simple API (beginner-friendly)

```python
from vmcraft import GuestFS

# Context manager for automatic cleanup
with GuestFS('/path/to/disk.qcow2') as g:
    # Auto-detect and mount root
    g.mount_root()

    # File operations
    hostname = g.read('/etc/hostname')
    g.write('/etc/motd', 'Welcome!\n')

    # Windows operations
    if g.is_windows():
        g.inject_driver('/path/to/drivers', 'viostor.inf')
        product = g.registry_read('SOFTWARE',
                                   r'Microsoft\Windows NT\CurrentVersion',
                                   'ProductName')
```

### Advanced API (full control)

```python
from vmcraft import NativeGuestFS

g = NativeGuestFS()
g.add_drive('/path/to/disk.qcow2', readonly=False, format='qcow2')
g.launch()

# Manual mount
roots = g.inspect_os()
for root in roots:
    mounts = g.inspect_get_mountpoints(root)
    for mp, device in sorted(mounts.items()):
        g.mount(device, mp)

# Full guestfs API available
g.upload('/local/file', '/remote/file')
g.download('/remote/file', '/local/file')
output = g.command(['ls', '-la', '/'])

# Performance metrics
metrics = g.get_performance_metrics()
print(f"Launch time: {metrics['total_launch']:.2f}s")

g.shutdown()
g.close()
```

### CLI Interface

```bash
# Interactive shell
vmcraft -a disk.qcow2 -i
> mount-root
> cat /etc/hostname
> write /etc/motd "Welcome!"
> exit

# One-shot commands
vmcraft -a disk.qcow2 --run 'cat /etc/hostname'
vmcraft -a disk.qcow2 --run 'upload /local/file /remote/file'

# Windows operations
vmcraft -a windows.vmdk \
  --inject-driver /path/to/virtio viostor.inf

# Registry operations
vmcraft -a windows.vmdk \
  --reg-read 'SOFTWARE' 'Microsoft\Windows NT\CurrentVersion' 'ProductName'
```

## Use Cases

### 1. Disk Image Forensics
```python
with GuestFS('/evidence/disk.dd', readonly=True) as g:
    g.mount_root()

    # Extract system information
    os_info = g.inspect_os_info()

    # Find recently modified files
    recent = g.find_modified_since('2024-01-01')

    # Extract logs
    g.download('/var/log/auth.log', '/evidence/auth.log')
```

### 2. Cloud Image Customization
```python
with GuestFS('/images/ubuntu-cloud.qcow2') as g:
    g.mount_root()

    # Inject SSH keys
    g.write('/root/.ssh/authorized_keys', public_key)

    # Set hostname
    g.write('/etc/hostname', 'web-server-01\n')

    # Install packages (via chroot)
    g.command(['apt', 'update'])
    g.command(['apt', 'install', '-y', 'nginx'])
```

### 3. Windows Driver Injection
```python
with GuestFS('/vms/windows10.vmdk') as g:
    g.mount_root()

    # Inject multiple drivers
    for driver in ['viostor', 'NetKVM', 'vioscsi']:
        result = g.inject_driver(f'/drivers/{driver}')
        print(f"Injected {driver}: {result['files_copied']} files")

    # Update registry for boot start
    g.registry_write('SYSTEM',
                     r'ControlSet001\Services\viostor',
                     'Start', '0', value_type='dword')
```

### 4. Backup/Restore Configuration
```python
# Backup
with GuestFS('/vms/prod-db.qcow2', readonly=True) as g:
    g.mount_root()
    g.download('/etc/mysql/my.cnf', '/backup/mysql-config.cnf')
    g.download('/etc/hosts', '/backup/hosts')

# Restore
with GuestFS('/vms/new-db.qcow2') as g:
    g.mount_root()
    g.upload('/backup/mysql-config.cnf', '/etc/mysql/my.cnf')
    g.upload('/backup/hosts', '/etc/hosts')
```

## Dependencies

### Runtime Dependencies
```toml
[project]
dependencies = [
    "python >= 3.10",
]

[project.optional-dependencies]
windows = [
    # For Windows registry operations
    # Note: libhivex must be installed system-wide
]
```

### System Dependencies

**Required:**
- qemu-utils (qemu-nbd)
- util-linux (mount, lsblk, blkid)
- sudo (for privileged operations)

**Linux Filesystems:**
- lvm2 (LVM support)
- cryptsetup (LUKS support)
- e2fsprogs (ext2/3/4 fsck)
- xfsprogs (XFS fsck)
- btrfs-progs (Btrfs support)

**Windows Support:**
- ntfs-3g (NTFS read-write)
- libhivex-bin (registry tools)
- exfat-fuse (exFAT support)

**Optional:**
- mdadm (software RAID)
- zfsutils-linux (ZFS support)

## Comparison with libguestfs

| Feature | VMCraft | libguestfs |
|---------|---------------|------------|
| **Performance** |
| Launch time | ~1-2s | ~5-10s |
| Memory usage | <50MB | ~256MB+ |
| Disk I/O | Direct mount | Via appliance |
| **Dependencies** |
| Language | Pure Python | C library + Python bindings |
| System tools | Standard Linux tools | Custom appliance |
| Installation | `pip install` | System package + build |
| **Platforms** |
| Linux | ✅ Full support | ✅ Full support |
| macOS | ⚠️ Limited (via Docker) | ✅ Native |
| Windows | ❌ Not supported | ✅ Via WSL2 |
| **Features** |
| Linux guests | ✅ Full | ✅ Full |
| Windows guests | ✅ Full | ✅ Full |
| BSD guests | ⚠️ Limited | ✅ Full |
| Live VMs | ❌ Offline only | ✅ Supported |
| **API** |
| Stability | ⚠️ New | ✅ Stable (10+ years) |
| Coverage | ~60 methods | 400+ methods |
| Compatibility | Drop-in for common ops | Complete API |

## Migration from hyper2kvm

To use VMCraft in hyper2kvm:

```python
# Before:
from hyper2kvm.core.guestfs_factory import create_guestfs

# After (once library is published):
from vmcraft import GuestFS as create_guestfs
```

The hyper2kvm project would depend on `vmcraft` package:

```toml
[project]
dependencies = [
    "vmcraft >= 1.0.0",
]
```

## License

**Recommended: LGPL-3.0-or-later**

Reasons:
1. Compatibility with libguestfs (also LGPL)
2. Allows proprietary software to use the library
3. Requires sharing improvements to the library itself
4. More permissive than GPL for library use

Alternative: MIT/BSD for maximum permissiveness

## Community & Governance

**Project Hosting:**
- GitHub: `github.com/ssahani/vmcraft`
- PyPI: `pypi.org/project/vmcraft`
- Docs: `vmcraft.rtfd.io` or `vmcraft.dev`

**Contribution Guidelines:**
- Code of Conduct (Contributor Covenant)
- Issue templates for bugs/features
- PR templates with checklist
- Automated testing on PRs
- Changelog management

**Maintainers:**
- Initial: hyper2kvm team
- Goal: Build community maintainer team

## Next Steps

1. **Discuss with team**: Review this proposal
2. **Get approval**: Decide if extraction makes sense
3. **Plan timeline**: Allocate resources
4. **Create repo**: Set up GitHub project
5. **Extract code**: Phase 1 implementation
6. **Alpha release**: Internal testing
7. **Beta release**: Community testing
8. **1.0 release**: Production-ready

## Conclusion

VMCraft has evolved beyond a simple libguestfs replacement into a powerful, standalone library for disk image manipulation. Extracting it as a separate project would:

1. ✅ **Benefit hyper2kvm** - Cleaner separation, focused testing
2. ✅ **Benefit community** - Reusable tool for many use cases
3. ✅ **Advance Python ecosystem** - Fill gap in disk image tooling
4. ✅ **Improve quality** - Dedicated focus and testing
5. ✅ **Enable innovation** - Easier experimentation and extension

The library would maintain compatibility with hyper2kvm while opening up new possibilities for disk image manipulation in Python.
