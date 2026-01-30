# Fedora 42 Server Migration Analysis

## Test Overview
- **Source**: `/home/ssahani/Downloads/VMs/extracted/fedora/64bit/fedora42-server.vmdk` (2.09 GiB)
- **Output**: `/home/ssahani/tt/hyper2kvm/out/fedora42-test/fedora42-server.qcow2` (1.3 GiB compressed)
- **Date**: 2026-01-25
- **Status**: **Conversion Successful** | **Offline Fix Incomplete**

---

## What Worked ✅

### 1. VMDK → QCOW2 Conversion
- Successfully converted 2.09 GiB VMDK to 1.3 GiB compressed QCOW2
- Partition layout preserved correctly:
  - `/dev/nbd2p1`: 1M BIOS boot partition
  - `/dev/nbd2p2`: 1G `/boot` (XFS, UUID=031625db-4bbc-4a56-b3b2-c61d71ba681f)
  - `/dev/nbd2p3`: 499G LVM physical volume

### 2. LVM Detection and Activation
- Volume group `fedora` detected and activated
- Logical volume `fedora/root` (15 GiB XFS) accessible
- LVM cache refresh fix working:
  ```bash
  vgchange -an          # Deactivate stale VGs
  pvscan --cache        # Refresh PV cache
  vgscan --cache        # Refresh VG cache
  vgchange -ay          # Activate all VGs
  ```

### 3. Storage Stack
- mdraid assembly: Not present
- ZFS import: Not present
- LVM activation: **Success**
- LUKS: Not configured

### 4. Filesystem Integrity
- `/dev/mapper/fedora-root`: XFS filesystem intact
- fstab already contains stable UUID references:
  ```fstab
  UUID=68712420-f267-4669-be0b-718ca9a4ebc9 /     xfs  defaults  0 0
  UUID=031625db-4bbc-4a56-b3b2-c61d71ba681f /boot xfs  defaults  0 0
  ```
- UUIDs verified to match actual devices ✅

---

## What Failed ❌

### Root Filesystem Mount Detection
The offline mount engine mounted `/dev/loop0` (libguestfs appliance) instead of `/dev/mapper/fedora-root` (actual guest root).

**Root Cause**:
- `inspect_os()` found no roots (guestfs inspection failed for LVM)
- Brute-force mount fallback attempted to list `/dev/mapper/*` devices
- Command `sh -lc 'ls -1 /dev/mapper/*'` failed because guestfs appliance has no `/bin/sh`
- `/dev/mapper/fedora-root` never added to candidate list
- Scored `/dev/loop0` (libguestfs appliance squashfs) as best match

**Impact**:
- fstab fixes: `0` (reported "no_fstab")
- initramfs regen: Failed (no guest kernel found)
- GRUB updates: Failed (no grub config found)
- Network fixes: Failed (no network configs found)

---

## Key Insights

### 1. fstab Stabilization is Critical
Even though this Fedora image already had UUID entries, **we cannot trust source fstabs**:
- VMs from ESXi may have `/dev/sdX` or `/dev/disk/by-path/...`
- VMs from Hyper-V may have `/dev/sda1`, `/dev/sdb2`
- Manual installations may have inconsistent device references

**Solution**: Always run fstab stabilizer to convert to `UUID=` or `PARTUUID=` regardless of current state.

### 2. Mount Detection Needs Improvement
The brute-force mount logic has dependencies on shell commands that fail in minimal guestfs environments:
- `g.command(["sh", "-lc", "ls -1 /dev/mapper/*"])` fails without `/bin/sh`
- Alternative: Use `g.list_filesystems()` + `g.lvs()` instead of shell commands

### 3. LVM Logical Volumes Must Be Prioritized
When scoring mount candidates, LVM LVs should be weighted higher than:
- Loop devices (libguestfs appliance)
- LUKS placeholder devices
- Partitions without filesystems

---

## Recommended Fixes

### 1. Improve Candidate Device Detection
Replace shell-dependent commands with native guestfs calls:

```python
# Current (fails without /bin/sh):
out = g.command(["sh", "-lc", "ls -1 /dev/mapper/*"])

# Proposed (native guestfs):
lvs = g.lvs() or []  # Returns ['/dev/fedora/root', ...]
fsmap = g.list_filesystems() or {}  # Includes /dev/mapper/* devices
```

### 2. Prioritize LVM LVs in Scoring
```python
def score_candidate(dev: str, fstype: str) -> int:
    score = 0
    if dev.startswith("/dev/mapper/") and "control" not in dev:
        score += 100  # Heavily prefer LVM logical volumes
    if dev.startswith("/dev/loop"):
        score -= 50   # Penalize loop devices (likely appliance)
    # ... existing scoring logic
```

### 3. Make Offline Fixes Optional for Conversion
Allow conversion to succeed even if offline mount fails:
- Primary goal: VMDK → QCOW2 conversion
- Secondary goal: fstab/initramfs/grub fixes
- If mount fails, still produce valid QCOW2

---

## Manual Verification

Successfully mounted and verified the converted QCOW2:

```bash
# Connect QCOW2 to NBD
sudo qemu-nbd --connect /dev/nbd2 fedora42-server.qcow2

# Activate LVM
sudo pvscan --cache
sudo vgscan --cache
sudo vgchange -ay fedora

# Mount and verify
sudo mount /dev/mapper/fedora-root /mnt/fedora-test
cat /mnt/fedora-test/etc/fstab  # ✅ UUID entries present and correct

# Verify UUIDs
sudo blkid /dev/mapper/fedora-root  # UUID=68712420... ✅
sudo blkid /dev/nbd2p2              # UUID=031625db... ✅
```

---

## Next Steps

1. **Fix mount detection**: Implement native guestfs-based device enumeration
2. **Test boot**: Deploy converted QCOW2 to libvirt and verify first boot
3. **Document workaround**: For LVM images, manual mount verification is working
4. **Extend fstab fixer**: Add Btrfs subvolume handling per earlier guidance

---

## Comparison: Windows 10 vs Fedora 42

| Feature | Windows 10 | Fedora 42 |
|---------|-----------|-----------|
| VMDK → QCOW2 | ✅ Success | ✅ Success |
| Root Mount | ✅ Success | ❌ Failed (wrong FS mounted) |
| Driver Injection | ✅ 4 drivers | N/A (Linux) |
| Registry Editing | ✅ SYSTEM + SOFTWARE | N/A (Linux) |
| Firstboot Service | ✅ Installed | N/A |
| fstab Fixes | N/A (Windows) | ⚠️ Skipped (mount issue) |
| Boot Test | ✅ SATA + VirtIO | 🔄 Pending |
| Overall | **Complete Success** | **Conversion OK, Fixes Incomplete** |

---

## Conclusion

The Fedora 42 conversion **successfully produced a valid QCOW2** with intact LVM structure and stable fstab UUIDs. The offline fix phase failed due to mount detection issues, but manual verification confirms the converted image has correct filesystem references and should boot successfully.

**Status**: Ready for libvirt boot testing.
