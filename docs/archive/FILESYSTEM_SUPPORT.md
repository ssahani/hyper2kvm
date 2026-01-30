# Comprehensive Linux Filesystem Support

hyper2kvm provides comprehensive support for all common Linux filesystems with automatic fstab stabilization using stable device identifiers (UUID, PARTUUID, LABEL).

## Supported Filesystems

### Standard Linux Filesystems ✅
| Filesystem | Status | Mount Options | fsck Support | Notes |
|------------|--------|---------------|--------------|-------|
| **ext2** | Full | errors=remount-ro, noatime | Yes (pass=1/2) | Legacy, reliable |
| **ext3** | Full | errors=remount-ro, noatime, data=ordered | Yes (pass=1/2) | Journaling |
| **ext4** | Full | errors=remount-ro, noatime | Yes (pass=1/2) | Modern standard |
| **XFS** | Full | noatime, inode64 | No (pass=0) | RHEL/Fedora default |
| **Btrfs** | Full | noatime, compress=zstd, space_cache=v2, subvol= | No (pass=0) | Subvolume support |

### Advanced/Specialized Filesystems ✅
| Filesystem | Status | Mount Options | fsck Support | Notes |
|------------|--------|---------------|--------------|-------|
| **F2FS** | Full | noatime, nodiscard | No | Flash-optimized |
| **JFS** | Full | noatime | No | IBM Journaled |
| **ReiserFS** | Full | noatime, notail | No | Legacy |
| **NILFS2** | Full | noatime | No | Continuous snapshots |
| **ZFS** | Partial | N/A (pool-based) | No | Via stable pool IDs |
| **bcachefs** | Partial | defaults | No | Experimental |

### Cross-Platform Filesystems ✅
| Filesystem | Status | Mount Options | Notes |
|------------|--------|---------------|-------|
| **FAT16/FAT32/VFAT** | Full | iocharset=utf8, shortname=mixed | Windows compat |
| **exFAT** | Full | iocharset=utf8 | Modern FAT |
| **NTFS** | Full | permissions, streams_interface=windows | Via ntfs-3g |

### Special Filesystems (Non-Root)
- tmpfs, devtmpfs, sysfs, proc, devpts
- cgroup, cgroup2, securityfs
- Skipped (not converted to stable IDs)

---

## Stable Device Identifiers

### Priority Order

hyper2kvm uses the following priority for stable identifiers:

#### Default Mode (UUID-first)
1. **UUID** - Filesystem UUID (most common, reliable)
2. **PARTUUID** - Partition UUID (survives filesystem recreation)
3. **LABEL** - User-friendly label (may not be unique)
4. **PARTLABEL** - GPT partition label

#### Hypervisor Migration Mode (PARTUUID-first)
1. **PARTUUID** - Most stable across hypervisors
2. **UUID** - Fallback
3. **LABEL** - User-friendly fallback

### When to Use PARTUUID

PARTUUID is automatically preferred for:
- **Root filesystem** in hypervisor migrations (cross-platform stability)
- **Btrfs filesystems** (UUID is shared across all subvolumes)
- **Cross-hypervisor migrations** (more portable than filesystem UUID)

UUID is preferred for:
- **Non-root filesystems** (standard practice)
- **ext4/XFS** standard installations (widely expected)

---

## Btrfs Subvolume Support

### Automatic Subvolume Detection

hyper2kvm automatically detects and converts Btrfs subvolume specifications:

**Before** (unstable):
```fstab
/dev/sda2        /       btrfs   subvol=@,defaults  0 0
/dev/sda2        /home   btrfs   subvol=@home       0 0
btrfsvol:/dev/sda2/@root /       btrfs   defaults   0 0
```

**After** (stable):
```fstab
UUID=9d4c0f6e... /       btrfs   subvol=@,noatime,compress=zstd     0 0
UUID=9d4c0f6e... /home   btrfs   subvol=@home,noatime,compress=zstd 0 0
UUID=9d4c0f6e... /       btrfs   subvol=@root,noatime,compress=zstd 0 0
```

Or with PARTUUID (cross-hypervisor migration):
```fstab
PARTUUID=3f1c2d2a-02 /      btrfs subvol=@,noatime,compress=zstd      0 0
PARTUUID=3f1c2d2a-02 /home  btrfs subvol=@home,noatime,compress=zstd  0 0
```

### Supported Subvolume Layouts

- **Ubuntu/Debian**: `@`, `@home`
- **openSUSE**: `@/.snapshots/1/snapshot`, `@/home`
- **Fedora**: `root`, `home`
- **Custom**: Any valid subvolume name

---

## Filesystem-Specific Mount Options

### ext4 (Modern Linux Standard)
```fstab
UUID=xxx  /  ext4  errors=remount-ro,noatime  0 1
```
**Options**:
- `errors=remount-ro` - Remount read-only on error (safety)
- `noatime` - Don't update access times (performance)
- `noload` - Don't replay journal (read-only mounts)
- `norecovery` - Skip recovery (read-only mounts)

### XFS (RHEL/Fedora Default)
```fstab
UUID=xxx  /  xfs  noatime,inode64  0 0
```
**Options**:
- `noatime` - Performance optimization
- `inode64` - Allow 64-bit inode numbers (modern systems)
- `norecovery` - Skip log replay (read-only mounts)

### Btrfs (Copy-on-Write, Snapshots)
```fstab
UUID=xxx  /  btrfs  subvol=@,noatime,compress=zstd,space_cache=v2  0 0
```
**Options**:
- `subvol=@` - Specify subvolume
- `noatime` - Performance
- `compress=zstd` - Transparent compression
- `space_cache=v2` - Modern space cache
- `norecovery` - Skip recovery (read-only)

### F2FS (Flash-Friendly)
```fstab
UUID=xxx  /  f2fs  noatime,nodiscard  0 0
```
**Options**:
- `noatime` - Reduce write wear
- `nodiscard` - Disable automatic TRIM (manual is better)

### FAT32/VFAT (Windows Compatibility)
```fstab
UUID=xxx  /boot/efi  vfat  iocharset=utf8,shortname=mixed,errors=remount-ro  0 0
```
**Options**:
- `iocharset=utf8` - Unicode support
- `shortname=mixed` - Mixed case 8.3 names
- `errors=remount-ro` - Safety

### NTFS (Windows Filesystems)
```fstab
UUID=xxx  /mnt/windows  ntfs  permissions,streams_interface=windows  0 0
```
**Options**:
- `permissions` - Enable Unix permissions
- `streams_interface=windows` - NTFS alternate data streams

---

## Conversion Examples

### Example 1: Simple ext4 Root

**Before**:
```fstab
/dev/sda1  /  ext4  defaults  0 1
```

**After**:
```fstab
UUID=68712420-f267-4669-be0b-718ca9a4ebc9  /  ext4  errors=remount-ro,noatime  0 1
```

**What Changed**:
- `/dev/sda1` → `UUID=...` (stable across device name changes)
- `defaults` → `errors=remount-ro,noatime` (safety + performance)
- fsck pass preserved: `0 1` (check root at boot)

---

### Example 2: XFS with LVM

**Before**:
```fstab
/dev/mapper/vg-root  /  xfs  defaults  0 0
```

**After**:
```fstab
UUID=9a8f7654-3210-abcd-ef12-345678901234  /  xfs  noatime,inode64  0 0
```

**What Changed**:
- `/dev/mapper/vg-root` → `UUID=...` (survives LVM renames)
- Added XFS-recommended options
- fsck pass set to 0 (XFS doesn't need boot-time fsck)

---

### Example 3: Btrfs with Subvolumes

**Before**:
```fstab
/dev/sda2          /       btrfs  subvol=@,defaults        0 0
/dev/sda2          /home   btrfs  subvol=@home,defaults    0 0
/dev/sda2          /.snapshots  btrfs  subvol=@snapshots   0 0
```

**After** (UUID mode):
```fstab
UUID=9d4c0f6e-1234-5678-90ab-cdef12345678  /            btrfs  subvol=@,noatime,compress=zstd,space_cache=v2         0 0
UUID=9d4c0f6e-1234-5678-90ab-cdef12345678  /home        btrfs  subvol=@home,noatime,compress=zstd,space_cache=v2     0 0
UUID=9d4c0f6e-1234-5678-90ab-cdef12345678  /.snapshots  btrfs  subvol=@snapshots,noatime,compress=zstd,space_cache=v2 0 0
```

**After** (PARTUUID mode for hypervisor migration):
```fstab
PARTUUID=3f1c2d2a-02  /            btrfs  subvol=@,noatime,compress=zstd,space_cache=v2         0 0
PARTUUID=3f1c2d2a-02  /home        btrfs  subvol=@home,noatime,compress=zstd,space_cache=v2     0 0
PARTUUID=3f1c2d2a-02  /.snapshots  btrfs  subvol=@snapshots,noatime,compress=zstd,space_cache=v2 0 0
```

**What Changed**:
- Device paths → stable identifiers
- Subvolumes preserved (critical for Btrfs)
- Optimized mount options added
- UUID shared across all subvolumes (expected for Btrfs)

---

### Example 4: Multi-Boot System

**Before**:
```fstab
/dev/sda1  /boot/efi       vfat  defaults        0 0
/dev/sda2  /boot           ext4  defaults        0 0
/dev/sda3  /               ext4  defaults        0 1
/dev/sda4  /home           ext4  defaults        0 2
/dev/sdb1  /mnt/windows    ntfs  defaults        0 0
/dev/sdb2  /mnt/data       exfat defaults        0 0
```

**After**:
```fstab
UUID=1A2B-3C4D                                /boot/efi    vfat   iocharset=utf8,shortname=mixed,errors=remount-ro  0 0
UUID=a1b2c3d4-e5f6-7890-abcd-ef1234567890    /boot        ext4   errors=remount-ro,noatime                         0 2
UUID=68712420-f267-4669-be0b-718ca9a4ebc9    /            ext4   errors=remount-ro,noatime                         0 1
UUID=9a8f7654-3210-abcd-ef12-345678901234    /home        ext4   errors=remount-ro,noatime                         0 2
UUID=12345678ABCDEF01                        /mnt/windows ntfs   permissions,streams_interface=windows             0 0
UUID=4567-89AB                               /mnt/data    exfat  iocharset=utf8                                    0 0
```

**What Changed**:
- All devices → UUIDs (stable across disk reordering)
- Filesystem-specific options for each type
- Correct fsck ordering (root=1, others=2, no fsck for NTFS/exFAT)

---

## Usage

### Automatic Stabilization (Default)

hyper2kvm automatically stabilizes fstab during conversion:

```bash
python3 -m hyper2kvm --config myvm.yaml
```

fstab is stabilized by default with:
- Mode: `stabilize-all`
- Prefer PARTUUID: Automatic (for root in hypervisor migrations)
- Preserve options: Yes
- Optimize options: Optional

### Manual Stabilization (Python API)

```python
from hyper2kvm.fixers.filesystem.fstab_stabilizer import FstabStabilizer

# Create stabilizer
stabilizer = FstabStabilizer(
    g,  # GuestFS instance
    prefer_partuuid=True,        # Prefer PARTUUID over UUID
    preserve_options=True,        # Keep existing mount options
    optimize_options=True,        # Add recommended options
    context="hypervisor_migration"
)

# Stabilize fstab
result = stabilizer.stabilize_fstab("/etc/fstab")

print(f"Converted: {result['stats']['converted']} entries")
print(f"Already stable: {result['stats']['already_stable']} entries")
```

### Configuration Options

**In YAML config**:
```yaml
# Fedora 42 with XFS root
fstab_mode: stabilize-all           # or: bypath-only, noop
fstab_prefer_partuuid: false        # Use UUID (default for Fedora)
fstab_optimize_options: true        # Add recommended options

# Ubuntu with Btrfs subvolumes
fstab_mode: stabilize-all
fstab_prefer_partuuid: true         # Use PARTUUID (better for Btrfs)
fstab_optimize_options: true
```

---

## Benefits

### 1. Cross-Hypervisor Stability
**Problem**: Device names change between hypervisors
- VMware: `/dev/sdX`
- KVM/QEMU: `/dev/vdX` or `/dev/sdX`
- Hyper-V: `/dev/sdX`

**Solution**: Stable identifiers work everywhere
```fstab
UUID=68712420-f267-4669-be0b-718ca9a4ebc9  /  xfs  defaults  0 0
```

### 2. Disk Reordering Resilience
**Problem**: Adding/removing disks changes device names
- Add USB disk → `/dev/sda` becomes `/dev/sdb`

**Solution**: UUIDs remain constant
```fstab
UUID=9d4c0f6e-...  /home  ext4  defaults  0 2
```

### 3. Btrfs Subvolume Preservation
**Problem**: Subvolume specs using device paths break
```fstab
/dev/sda2  /  btrfs  subvol=@,defaults  0 0  # Breaks if sda→vda
```

**Solution**: Stable identifier + subvolume
```fstab
PARTUUID=3f1c2d2a-02  /  btrfs  subvol=@,defaults  0 0  # Always works
```

### 4. LVM Flexibility
**Problem**: LVM device mapper names can change
```fstab
/dev/mapper/vg-root  /  xfs  defaults  0 0  # vg name might change
```

**Solution**: Filesystem UUID
```fstab
UUID=68712420-...  /  xfs  defaults  0 0  # Survives LVM changes
```

---

## Limitations

### Filesystems Without UUID Support
Some filesystems don't have UUIDs:
- Old FAT16 volumes (pre-mtools 4.0)
- Some exotic filesystems

**Fallback**: PARTUUID or LABEL used instead

### ZFS Special Handling
ZFS doesn't use traditional device references:
```fstab
pool/dataset  /data  zfs  defaults  0 0
```
hyper2kvm preserves ZFS pool/dataset specifications (already stable).

### Network Filesystems
NFS/CIFS/GlusterFS specifications are preserved as-is:
```fstab
server:/export  /mnt/nfs  nfs  defaults  0 0  # Not converted (already stable)
```

---

## Verification

After conversion, verify fstab:

```bash
# Connect QCOW2
sudo qemu-nbd --connect /dev/nbd0 image.qcow2

# Activate LVM (if needed)
sudo pvscan --cache
sudo vgchange -ay

# Mount and check fstab
sudo mount /dev/mapper/vg-root /mnt/test
cat /mnt/test/etc/fstab

# Verify UUIDs match
sudo blkid | grep -E "UUID|PARTUUID"
```

Expected output:
```fstab
UUID=68712420-f267-4669-be0b-718ca9a4ebc9  /      xfs   noatime,inode64  0 0
UUID=031625db-4bbc-4a56-b3b2-c61d71ba681f  /boot  xfs   noatime          0 0
```

---

## References

- [Fedora: Filesystem Recommendations](https://docs.fedoraproject.org/en-US/fedora/latest/system-administrators-guide/kernel-module-driver-configuration/Working_with_the_GRUB_2_Boot_Loader/#sec-GRUB_2-Configuration)
- [Ubuntu: Btrfs Subvolumes](https://help.ubuntu.com/community/btrfs)
- [Arch Linux: fstab](https://wiki.archlinux.org/title/Fstab)
- [systemd: Automatic Boot Assessment](https://www.freedesktop.org/software/systemd/man/systemd-gpt-auto-generator.html)
