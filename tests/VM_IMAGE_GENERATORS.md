# VM Image Generators

This directory contains scripts for generating test VM disk images for hyper2kvm testing.

## Overview

hyper2kvm includes multiple test image generators inspired by libguestfs patterns:

1. **make-test-images.py** - VMDK descriptor and extent files
2. **make-test-vm-image.py** - Simple VM disk images
3. **make-bootable-test-vm.py** - Bootable OS images (requires libguestfs)

## Quick Start

### Generate VMDK Test Images

```bash
# Generate all VMDK test images
python make-test-images.py all test-data/

# Generate specific layouts
python make-test-images.py vmdk-descriptor test-data/
python make-test-images.py multi-extent test-data/
python make-test-images.py security test-data/
```

### Generate Simple VM Images

```bash
# Minimal Linux image (fast, no dependencies)
python make-test-vm-image.py minimal /tmp/test.qcow2

# Linux BIOS image
python make-test-vm-image.py linux-bios /tmp/linux-bios.qcow2 --size-mb 512

# Linux UEFI image
python make-test-vm-image.py linux-uefi /tmp/linux-uefi.qcow2

# Windows-like image
python make-test-vm-image.py windows-uefi /tmp/windows.qcow2 --size-mb 1024
```

### Generate Bootable OS Images (Requires libguestfs)

```bash
# Ubuntu 22.04
python make-bootable-test-vm.py ubuntu --output ubuntu-22.04.img

# Ubuntu 24.04 with UEFI
python make-bootable-test-vm.py ubuntu --version 24.04 --efi --output ubuntu-24.04-uefi.img

# Debian 12 with UEFI
python make-bootable-test-vm.py debian --version 12 --efi --output debian-12.img

# Fedora 39
python make-bootable-test-vm.py fedora --version 39 --output fedora-39.img
```

## Script Comparison

| Script | Dependencies | Boot able | Use Case |
|--------|-------------|-----------|----------|
| make-test-images.py | None | No | VMDK parser/security testing |
| make-test-vm-image.py | qemu-img, mkfs.* | No | Directory structure testing |
| make-bootable-test-vm.py | libguestfs | Yes | Full conversion pipeline testing |

## Script Details

### 1. make-test-images.py

**Purpose:** Create VMDK descriptor and extent files for testing the VMDK parser.

**Features:**
- VMDK descriptors with flat extents
- Multi-extent split sparse VMDKs
- Security test cases (path traversal, large files, binary files)
- Subdirectory reference validation
- Fast execution (no partitioning/formatting)

**Layouts:**
- `simple` - Single raw disk image
- `vmdk-descriptor` - Descriptor + flat extent pair
- `multi-extent` - Descriptor + 3 sparse extents
- `security` - Path traversal, large descriptor, binary file tests
- `all` - All of the above

**Example:**
```bash
python make-test-images.py all test-data/
```

**Generated Files:**
- `test.vmdk` + `test-flat.vmdk`
- `test-multi.vmdk` + `test-s001.vmdk`, `test-s002.vmdk`, `test-s003.vmdk`
- `malicious/traversal.vmdk`
- `subdir-test.vmdk` + `subdir/extent.vmdk`
- `large.vmdk` (>8 MiB)
- `binary.vmdk`

**Testing:** Used by `tests/unit/test_vmware/test_vmdk_integration.py`

### 2. make-test-vm-image.py

**Purpose:** Create simple VM disk images with realistic OS structures (no libguestfs).

**Features:**
- No libguestfs dependency
- Creates qcow2/raw/vmdk images
- Generates directory structures alongside images
- Fast and lightweight
- Multiple OS layouts (Linux BIOS/UEFI, Windows)

**Layouts:**
- `minimal` - Bare minimum bootable Linux
- `linux-bios` - Linux with MBR/BIOS boot structure
- `linux-uefi` - Linux with GPT/UEFI boot structure
- `windows-uefi` - Windows-like directory structure

**Example:**
```bash
# Create minimal Linux image
python make-test-vm-image.py minimal test.qcow2 --size-mb 512

# Create Linux UEFI image in raw format
python make-test-vm-image.py linux-uefi linux-uefi.raw --format raw
```

**Directory Structure:**
For each image, creates a companion directory with OS files:
- `<image-stem>-root/` - Root filesystem structure
- `<image-stem>-efi/` - EFI partition structure (UEFI images)

**Example Output:**
```
test.qcow2                    # Disk image
test-root/                    # Root filesystem
  etc/
    hostname
    fstab
    os-release
  boot/
    vmlinuz
    initramfs.img
    grub2/grub.cfg
```

### 3. make-bootable-test-vm.py

**Purpose:** Create fully bootable test VM images using libguestfs.

**Dependencies:**
- python3-guestfs
- libguestfs-tools
- qemu-utils

**Features:**
- Proper partitioning (MBR or GPT)
- Real filesystems (ext4, xfs, vfat)
- OS-specific package databases
- Bootloader configurations
- Systemd units
- Fallback to simplified mode without libguestfs

**OS Types:**
- `ubuntu` - Ubuntu (10.10, 20.04, 22.04, 24.04)
- `debian` - Debian (11, 12)
- `fedora` - Fedora (38, 39, 40)

**Example:**
```bash
# Ubuntu 22.04 with UEFI
python make-bootable-test-vm.py ubuntu --version 22.04 --efi \\
    --output ubuntu-22.04-uefi.img --size-mb 1024

# Debian 12 BIOS
python make-bootable-test-vm.py debian --version 12 \\
    --output debian-12.img
```

**Ubuntu Versions:**
| Version | Codename | Root FS |
|---------|----------|---------|
| 10.10 | maverick | ext2 |
| 20.04 | focal | ext4 |
| 22.04 | jammy | ext4 |
| 24.04 | noble | xfs |

**Partition Layout (UEFI):**
1. /dev/sda1 - EFI System Partition (200 MiB, vfat)
2. /dev/sda2 - Boot partition (256 MiB, ext2)
3. /dev/sda3 - Root partition (rest, ext4/xfs)

**Partition Layout (BIOS):**
1. /dev/sda1 - Boot partition (256 MiB, ext2)
2. /dev/sda2 - Root partition (rest, ext4/xfs)

## Installation

### Minimal (No Dependencies)

Only `make-test-images.py` works with no additional dependencies:

```bash
python make-test-images.py all test-data/
```

### Basic VM Images (qemu-img)

For `make-test-vm-image.py`:

```bash
# Fedora/RHEL
sudo dnf install qemu-img e2fsprogs dosfstools

# Debian/Ubuntu
sudo apt install qemu-utils e2fsprogs dosfstools
```

### Bootable Images (libguestfs)

For `make-bootable-test-vm.py`:

```bash
# Fedora/RHEL
sudo dnf install python3-libguestfs libguestfs-tools qemu-img

# Debian/Ubuntu
sudo apt install python3-guestfs libguestfs-tools qemu-utils
```

## Testing

### Run Integration Tests

```bash
# Generate test images first
python make-test-images.py all tests/test-data/

# Run integration tests
pytest tests/unit/test_vmware/test_vmdk_integration.py -v
```

### Verify Image

```bash
# Check image info
qemu-img info test.qcow2

# Test boot (BIOS)
qemu-system-x86_64 -m 2048 -hda test.qcow2

# Test boot (UEFI)
qemu-system-x86_64 -m 2048 -bios /usr/share/ovmf/OVMF.fd -hda test-uefi.qcow2
```

## Comparison to libguestfs Patterns

These scripts are inspired by libguestfs test image generators:

| libguestfs | hyper2kvm | Adaptation |
|------------|-----------|------------|
| make-fedora-img.py | make-bootable-test-vm.py | Added Ubuntu/Debian, made libguestfs optional |
| make-ubuntu-img.py | make-bootable-test-vm.py (ubuntu) | Integrated into unified script |
| make-debian-img.py | make-bootable-test-vm.py (debian) | Integrated into unified script |
| make-windows-img.py | make-test-vm-image.py (windows-uefi) | Simplified, no registry hives |
| make-coreos-img.py | (not implemented) | CoreOS not priority for hyper2kvm |

**Key Differences:**
1. **Unified Interface:** Single script (`make-bootable-test-vm.py`) for multiple OS types
2. **Optional Dependencies:** Graceful fallback when libguestfs not available
3. **Focus on VMDK:** Added `make-test-images.py` specifically for VMDK testing
4. **Simplified Windows:** No registry hive manipulation, just directory structure
5. **Smaller Images:** Default 512 MiB vs libguestfs's 2-6 GiB

## Use Cases

### VMDK Parser Testing
```bash
python make-test-images.py all test-data/
pytest tests/unit/test_vmware/test_vmdk_integration.py
```

### Conversion Pipeline Testing
```bash
# Create source VM
python make-bootable-test-vm.py ubuntu --output source.img

# Convert to VMDK (would use hyper2kvm's converter)
# ... conversion logic ...

# Test converted image
qemu-system-x86_64 -m 2048 -hda converted.qcow2
```

### Security Testing
```bash
# Generate malicious VMDK descriptors
python make-test-images.py security test-data/

# Run security tests
pytest tests/unit/test_vmware/test_vmdk_security.py -v
```

## Troubleshooting

### "libguestfs not available"

**Solution:** Install libguestfs or use simplified scripts:
```bash
# Use make-test-vm-image.py instead (no libguestfs needed)
python make-test-vm-image.py minimal test.qcow2
```

### "qemu-img not found"

**Solution:** Install qemu-utils/qemu-img:
```bash
# Fedora
sudo dnf install qemu-img

# Ubuntu
sudo apt install qemu-utils
```

### "mkfs.ext4 not found"

**Solution:** Install e2fsprogs:
```bash
# Fedora
sudo dnf install e2fsprogs

# Ubuntu
sudo apt install e2fsprogs
```

### Partition layout errors

**Problem:** `part_add: location outside of device`

**Solution:** Increase image size:
```bash
# Use at least 512 MiB for bootable images
python make-bootable-test-vm.py ubuntu --size-mb 1024 --output ubuntu.img
```

## Contributing

When adding new test image generators:

1. Follow the libguestfs pattern (single Python file, CLI args, clear docstrings)
2. Make dependencies optional with graceful fallback
3. Add documentation to this file
4. Create integration tests in `tests/unit/`
5. Update `TEST_IMAGE_INTEGRATION.md`

## References

- [libguestfs Test Image Generators](https://github.com/libguestfs/libguestfs/tree/master/test-data/phony-guests)
- [VMDK Format Specification](https://www.vmware.com/app/vmdk/?src=vmdk)
- [libguestfs Python API](https://libguestfs.org/guestfs-python.3.html)
