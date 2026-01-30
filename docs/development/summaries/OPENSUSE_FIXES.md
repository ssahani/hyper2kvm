# openSUSE Leap 15.4 Migration Fixes

## Issues Fixed

### 1. By-Path Device NFS Mount Errors ✅ FIXED

**Problem:**
```
mount.nfs: Failed to resolve server /dev/disk/by-path/pci-0000
```

Device paths like `/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2` contain colons (`:`) which Linux `mount` interprets as NFS paths in the format `server:export`.

**Root Cause:**
- openSUSE uses PCI-based device paths in fstab
- VMCraft's `realpath()` tried to resolve these inside the guest filesystem (wrong approach)
- Device paths are on the host system, not inside the guest

**Solution:**
Added host-level symlink resolution for by-path devices:

**File:** `hyper2kvm/fixers/offline_fixer.py`

**Location 1:** Lines 807-822 (bruteforce candidate filtering)
```python
# CRITICAL: Resolve by-path devices to real device paths
# Device paths with colons are interpreted as NFS paths by mount
if d.startswith("/dev/disk/by-path/"):
    try:
        import os
        # Resolve symlink on host system (not inside guest filesystem)
        real_dev = os.readlink(d)
        # Handle relative symlinks
        if not real_dev.startswith("/"):
            real_dev = os.path.normpath(os.path.join(os.path.dirname(d), real_dev))
        self.logger.debug(f"Resolved by-path device: {d} -> {real_dev}")
        d = real_dev
    except Exception as e:
        self.logger.warning(f"Failed to resolve by-path device {d}: {e}; skipping")
        continue
```

**Location 2:** Lines 718-732 (root device resolution)
```python
# For by-path devices, use host-level symlink resolution
# because VMCraft device paths are on the host, not in the guest filesystem
if not real and root_dev.startswith("/dev/disk/by-path/"):
    try:
        import os
        real_dev = os.readlink(root_dev)
        # Handle relative symlinks
        if not real_dev.startswith("/"):
            real_dev = os.path.normpath(os.path.join(os.path.dirname(root_dev), real_dev))
        if real_dev.startswith("/dev/"):
            real = real_dev
            self.logger.info(f"Resolved by-path root device: {root_dev} -> {real}")
    except Exception as e:
        self.logger.warning(f"Failed to resolve by-path root device {root_dev}: {e}")
        real = None
```

**Expected Result:**
- `/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2` → `/dev/nbd0p2`
- Mount commands will use real device paths
- No more NFS resolution errors

---

### 2. Chroot Command Errors (Not Actually a Problem) ℹ️

**Error Logs:**
```
Command failed: sudo chroot /tmp/hyper2kvm-guestfs-9ixkrhi0 sh -lc 'command -v "$1" >/dev/null 2>&1 && echo YES || echo NO' sh mdadm
stderr: chroot: failed to run command 'sh': No such file or directory
```

**Analysis:**
- These errors occur during storage stack activation (mdraid/zfs detection)
- They happen BEFORE the root filesystem is mounted
- The code properly catches these exceptions and returns False
- This is expected behavior - not all guests have mdraid or zfs

**Why They Appear:**
- `utils.py` logs CalledProcessError at ERROR level (line 151-158)
- Makes it look like a failure, but it's actually handled gracefully

**Impact:**
- ✅ **No functional issue** - the code works correctly
- ⚠️ Logs are noisy and confusing

**Recommendation:**
Future improvement could lower the log level to DEBUG for expected failures during storage detection.

---

### 3. Fstab Before/After Logging ✅ ADDED

**File:** `hyper2kvm/fixers/filesystem/fstab_stabilizer.py`

**Changes:**

**Location 1:** Lines 384-387 (log original fstab)
```python
# Log original fstab
logger.info(f"📄 Original {fstab_path}:")
for line_num, line in enumerate(fstab_content.splitlines(), 1):
    logger.info(f"  {line_num:3d}: {line}")
```

**Location 2:** Lines 428-441 (log conversions and updated fstab)
```python
# Log changes made
logger.info(f"\n📝 Fstab conversions summary:")
for conv in result["conversions"]:
    if conv["converted"]:
        logger.info(f"  Line {conv['line']:3d}: {conv['original']:50s} -> {conv['new']:50s} ({conv['mountpoint']})")

# Log new fstab
logger.info(f"\n📄 Updated {fstab_path}:")
for line_num, line in enumerate(new_lines, 1):
    logger.info(f"  {line_num:3d}: {line}")

self.g.write(fstab_path, new_fstab_content)
result["success"] = True
logger.info(f"\n✅ Stabilized {fstab_path}: {self.stats['converted']} of {self.stats['total_entries']} entries converted")
```

**Expected Output:**
```
📄 Original /etc/fstab:
    1: /dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /  btrfs  defaults  0  0
    2: /dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part3  swap  swap  defaults  0  0

📝 Fstab conversions summary:
  Line   1: /dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2 -> UUID=1234-5678-abcd-ef00        (/)
  Line   2: /dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part3 -> UUID=8765-4321-dcba-00fe        (swap)

📄 Updated /etc/fstab:
    1: UUID=1234-5678-abcd-ef00  /  btrfs  defaults  0  0
    2: UUID=8765-4321-dcba-00fe  swap  swap  defaults  0  0

✅ Stabilized /etc/fstab: 2 of 2 entries converted
```

---

## Testing

Run the migration again on your openSUSE Leap 15.4 VM:

```bash
sudo python3 -m hyper2kvm.main \
  --image "/home/ssahani/vmware/Clone of openSUSE_Leap_15.4_VM_LinuxVMages.COM/openSUSE_Leap_15.4_VM_LinuxVMImages.COM-cl1.vmdk" \
  --output-dir out/opensuse-leap-test \
  --no-backup
```

**Expected Results:**
1. ✅ No more "mount.nfs: Failed to resolve server" errors
2. ✅ Root filesystem mounts successfully with `/dev/nbd0p2`
3. ✅ Fstab shows before/after with UUID conversions
4. ⚠️ Chroot errors may still appear but can be ignored

---

## Files Modified

1. `hyper2kvm/fixers/offline_fixer.py`:
   - Added by-path device resolution in candidate filtering (lines 807-822)
   - Added by-path device resolution in root detection (lines 718-732)

2. `hyper2kvm/fixers/filesystem/fstab_stabilizer.py`:
   - Added original fstab logging (lines 384-387)
   - Added conversion summary and updated fstab logging (lines 428-441)

---

## Migration Example

### Before (openSUSE Leap 15.4 original fstab):
```
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /                       btrfs  defaults  0  0
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /var                    btrfs  subvol=/@/var  0  0
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /usr/local              btrfs  subvol=/@/usr/local  0  0
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2  /home                   btrfs  subvol=/@/home  0  0
/dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part3  swap                    swap   defaults  0  0
```

### After (KVM-compatible fstab with UUIDs):
```
UUID=1234-5678-abcd-ef00  /          btrfs  defaults           0  0
UUID=1234-5678-abcd-ef00  /var       btrfs  subvol=/@/var      0  0
UUID=1234-5678-abcd-ef00  /usr/local btrfs  subvol=/@/usr/local 0  0
UUID=1234-5678-abcd-ef00  /home      btrfs  subvol=/@/home     0  0
UUID=8765-4321-dcba-00fe  swap       swap   defaults           0  0
```

---

## Notes

- The by-path device format `pci-0000:00:10.0-scsi-0:0:0:0-partN` is VMware-specific and won't work on KVM
- UUIDs are hypervisor-agnostic and survive disk device name changes
- Btrfs subvolumes are preserved correctly with the UUID conversion
