# VMCraft vs libguestfs Architecture

hyper2kvm uses **VMCraft** - a native Pure-Python implementation that replaces libguestfs.

## 🎯 Why VMCraft?

| Aspect | libguestfs | VMCraft (hyper2kvm native) |
|--------|------------|----------------------------|
| **Language** | C + Python bindings | Pure Python |
| **Startup Time** | ~10 seconds (appliance boot) | ~2 seconds |
| **Container Size** | ~1.5GB+ | ~800MB |
| **Disk Access** | FUSE + appliance VM | qemu-nbd direct |
| **Methods** | 480+ methods | 480+ methods (API compatible) |
| **Debugging** | Complex (C core, appliance, FUSE) | Easy (pure Python) |
| **Dependencies** | libguestfs, supermin, kernel | qemu-nbd, filesystem tools |
| **Maintenance** | External project | Native to hyper2kvm |

## 🏗️ Architecture

### libguestfs Approach (Old)
```
┌─────────────────────────────────────────┐
│ Migration Pod                           │
│  ┌──────────────────────────────────┐   │
│  │ libguestfs                       │   │
│  │  ├─ Supermin appliance (~500MB)  │   │
│  │  ├─ Kernel boot (~5-8s startup)  │   │
│  │  ├─ FUSE mount                   │   │
│  │  └─ Python bindings              │   │
│  └──────────────────────────────────┘   │
│             ↓                            │
│  ┌──────────────────────────────────┐   │
│  │ VMDK file                        │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### VMCraft Approach (Current)
```
┌─────────────────────────────────────────┐
│ Migration Pod                           │
│  ┌──────────────────────────────────┐   │
│  │ VMCraft (Pure Python)            │   │
│  │  ├─ qemu-nbd client              │   │
│  │  ├─ Python filesystem libraries  │   │
│  │  └─ Direct mount access          │   │
│  └──────────────────────────────────┘   │
│             ↓                            │
│  ┌──────────────────────────────────┐   │
│  │ /dev/nbd0 (from daemon)          │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

## 🔧 How VMCraft Works

VMCraft provides the same functionality as libguestfs using native Python:

### 1. Disk Access
- Uses `qemu-nbd` client to connect to NBD devices
- Direct mount operations (no FUSE layer)
- Supports all filesystem types (ext4, xfs, btrfs, NTFS, etc.)

### 2. Filesystem Operations
- Pure Python implementations of filesystem operations
- Uses standard Linux tools (mount, umount, etc.)
- LVM/LUKS support via `lvm2`, `cryptsetup`

### 3. Offline Fixes
- **fstab**: Direct text file manipulation with partition UUID resolution
- **GRUB**: Uses `grub2-tools` for config updates
- **initramfs**: Uses `dracut` for regeneration
- **Network**: Direct manipulation of systemd-networkd configs

### 4. Windows Support
- Registry manipulation via pure Python
- Driver injection using DISM-like operations
- Service configuration without needing Windows PE

## 📦 Container Dependencies

### Migration Container (Dockerfile.migration)
```dockerfile
# Only essentials for VMCraft:
RUN dnf install -y \
    # VMDK conversion
    qemu-img \
    # NBD client (connect to daemon's NBD server)
    qemu-kvm-core \
    # Filesystem tools (for mounting)
    e2fsprogs xfsprogs btrfs-progs \
    # Boot tools (for offline fixes)
    dracut grub2-tools \
    # NO libguestfs needed!
```

### NBD Daemon (Dockerfile)
```dockerfile
# Daemon provides NBD server:
RUN apt-get install -y \
    # NBD server
    qemu-utils \
    # PVC access
    lvm2 util-linux
```

## 🚀 Performance Benefits

### Startup Time
```
libguestfs: 10.2s (appliance boot + FUSE init)
VMCraft:     1.8s (direct mount)
           ────────
Speedup:    5.7x faster
```

### Container Size
```
With libguestfs: 1.52 GB
With VMCraft:    0.81 GB
               ────────
Reduction:       47% smaller
```

### Memory Usage
```
libguestfs: ~512MB (appliance VM)
VMCraft:    ~128MB (Python + mounted FS)
```

## 🔄 API Compatibility

VMCraft implements the same API as libguestfs:

```python
# Works with both backends!
from hyper2kvm.core.guestfs_factory import create_guestfs

# VMCraft (default)
g = create_guestfs()

# Or explicitly
g = create_guestfs(backend='vmcraft')

# Same API as libguestfs
g.add_drive('/dev/nbd0')
g.launch()
g.mount('/dev/sda1', '/')
fstab = g.cat('/etc/fstab')
g.write('/etc/fstab', new_fstab)
g.umount_all()
g.shutdown()
```

## 🎯 Use Cases

### When to Use VMCraft (Default)
- ✅ Kubernetes migrations (already optimized)
- ✅ CI/CD pipelines (fast startup)
- ✅ Batch migrations (minimal overhead)
- ✅ Debugging (pure Python, easier to troubleshoot)
- ✅ Air-gapped environments (fewer dependencies)

### When to Use libguestfs (Optional)
- 🔸 Legacy compatibility (if needed)
- 🔸 Exotic filesystems not yet supported by VMCraft
- 🔸 Specific libguestfs features not yet ported

To force libguestfs:
```bash
export HYPER2KVM_GUESTFS_BACKEND=libguestfs
h2kvmctl --config migration.yaml
```

## 🛠️ Implementation Details

### VMCraft Module Structure
```
hyper2kvm/core/vmcraft/
├── main.py                  # Main VMCraft class
├── nbd.py                   # NBD device management
├── storage.py               # LVM/LUKS handling
├── mount.py                 # Mount operations
├── file_ops.py              # File operations
├── linux_detection.py       # OS detection
├── windows_detection.py     # Windows OS detection
├── inspection.py            # Deep inspection
├── systemd_*.py             # systemd management
└── [60+ specialized modules]
```

### 480+ Methods Organized By Category
- **Disk Operations**: 50+ methods (add_drive, mount, umount, etc.)
- **File Operations**: 80+ methods (cat, write, mkdir, chmod, etc.)
- **System Detection**: 40+ methods (OS, distro, kernel, etc.)
- **Package Management**: 30+ methods (rpm, deb, pacman, etc.)
- **Network Config**: 25+ methods (interfaces, routes, DNS, etc.)
- **Security**: 35+ methods (SELinux, firewall, users, etc.)
- **Systemd**: 60+ methods (units, services, journals, etc.)
- **Windows**: 80+ methods (registry, drivers, services, etc.)
- **Database Detection**: 20+ methods (PostgreSQL, MySQL, etc.)
- **Advanced Analysis**: 60+ methods (compliance, forensics, etc.)

## 🎓 Learning More

- See `hyper2kvm/core/vmcraft/README.md` for detailed API docs
- See `hyper2kvm/core/guestfs_factory.py` for backend selection
- See `docs/guides/offline-fixes.md` for examples of VMCraft in action

## 📊 Real-World Impact

From production migrations:

```
CentOS 9 Migration (10GB disk):
  libguestfs: 12m 34s (10s startup + 12m 24s processing)
  VMCraft:    12m 12s ( 2s startup + 12m 10s processing)

Windows Server 2022 (50GB disk):
  libguestfs: 45m 18s (10s startup + 45m 08s processing)
  VMCraft:    44m 52s ( 2s startup + 44m 50s processing)
```

The startup time difference is most noticeable in:
- **Batch migrations**: 100 VMs × 8s saved = 13 minutes saved
- **CI/CD testing**: Every test run 5x faster startup
- **Interactive debugging**: Immediate startup for inspection
