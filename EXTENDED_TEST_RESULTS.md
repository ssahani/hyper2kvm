# Extended Distribution Test Results

## Test Date: 2026-01-25

### Images Found in ~/Downloads

1. **Fedora Cloud Base 43** (QCOW2, 557M)
   - Path: `/home/ssahani/Downloads/VMs/Fedora-Cloud-Base-Generic-43-1.6.x86_64.qcow2`  
   - Status: ❌ FAILED
   - Issue: Btrfs subvolume naming - uses "root" subvolume, not standard "@" or "@rootfs"
   - Filesystem: Btrfs with subvolumes (root, home, var)
   - Fix needed: Dynamic Btrfs subvolume discovery

2. **VMware Photon OS 5.0** (OVA → VMDK, 308M)
   - Path: `/tmp/photon-extract/photon-ova-disk1.vmdk` (extracted from OVA)
   - Status: ❌ FAILED  
   - Issue: Automated mount detection fails on ext4 partition (manual mount works)
   - Filesystem: ext4 on /dev/nbd*p2
   - Partition layout: Out-of-order GPT (p1, p3, p2)
   - Fix needed: Improved partition detection for non-sequential layouts

3. **Arch Linux 2024** (VMDK, 768M)
   - Path: `/home/ssahani/Downloads/Projects/arch-64bit/64bit/ArchLinux 20240601 (64bit).vmdk`
   - Status: ✅ PASSED
   - Output: `/home/ssahani/tt/hyper2kvm/out/arch2-test/arch-2024.qcow2` (564M)
   - Filesystem: Successfully handled (likely Btrfs or ext4)

4. **Photon OS 5.0 Azure** (VHD, 17G)
   - Path: `/home/ssahani/Downloads/VMs/photon-azure-5.0-dde71ec57.x86_64.vhD`
   - Status: ⊘ NOT TESTED (very large)
   - Format: VHD (Hyper-V format)

## Summary

- **Total images found**: 7 (4 already tested in core suite + 3 new)
- **Extended tests**: 3 new images
- **Passed**: 1/3 (33%)
- **Failed**: 2/3 (67%)

## Core Suite Results (from previous session)

All 4 core distributions passed (100%):
- ✅ Fedora 42 Server (XFS on LVM)
- ✅ CentOS 10 Server (XFS on LVM)
- ✅ Arch Linux (Btrfs)
- ✅ Ubuntu Server 25.04 (ext4)

## Combined Results

- **Total distinct distributions tested**: 7
- **Passed**: 5/7 (71%)
- **Failed**: 2/7 (29%)

## Issues Identified

### 1. Btrfs Subvolume Discovery
**Affected**: Fedora Cloud Base 43

Current code has hardcoded subvolume names (@, @root, @rootfs, etc.), but Fedora Cloud uses "root". Need dynamic discovery:
```bash
sudo mount -o subvol=root /dev/nbdXpY /mnt
```

**Solution**: Mount with `subvolid=5` first, list subvolumes, then try each one.

### 2. Non-Sequential Partition Layouts
**Affected**: VMware Photon OS 5.0

When GPT partitions are out-of-order (p1: 2048-10239, p3: 10240-30719, p2: 30720-end), the partition detection logic may struggle.

**Solution**: Use fdisk/lsblk to get actual partition order, not assume sequential numbering.

## Recommendations

1. Implement dynamic Btrfs subvolume discovery
2. Improve partition ordering detection for GPT disks  
3. Add VHD format support for Hyper-V images
4. Test with the large Photon Azure VHD image once fixes are applied

## Test Configurations Created

- `test-confs/fedora43-cloud-test.yaml`
- `test-confs/photon-test.yaml`
- `test-confs/arch2-test.yaml`
- `test-extended-distros.sh` (test runner)
