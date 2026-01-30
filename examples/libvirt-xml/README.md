# Libvirt XML Templates

Tested and working libvirt domain XML templates for migrated VMs.

## Templates

### Linux (CentOS/RHEL/Fedora)

1. **`centos-linux-bios.xml`** - BIOS/Legacy boot
   - ✅ Tested with CentOS 8, CentOS 9
   - Q35 chipset, VirtIO disk/network
   - SPICE graphics, serial console
   - QEMU guest agent ready

2. **`rhel-linux-uefi.xml`** - UEFI boot
   - ✅ Tested with RHEL 9.4, CentOS 9
   - OVMF UEFI firmware
   - Secure Boot ready (disabled by default)
   - Q35 chipset, VirtIO disk/network

### Windows

3. **`windows-server-uefi.xml`** - Windows Server/10/11
   - UEFI boot with OVMF
   - Hyper-V enlightenments for performance
   - VirtIO disk/network (requires drivers)
   - Local time clock (Windows requirement)

## Usage

### Method 1: Direct Import

```bash
# Edit the XML file first:
# 1. Change VM name
# 2. Update disk path
# 3. Adjust memory/CPU if needed

# Import to libvirt
virsh define centos-linux-bios.xml

# Start the VM
virsh start centos-linux-vm
```

### Method 2: Use as Template for hyper2kvm

The `hyper2kvm` tool can automatically generate similar XML during migration.

## Customization Guide

### Common Edits

- **VM Name**: `<name>your-vm-name</name>`
- **Memory**: `<memory unit='KiB'>8388608</memory>  <!-- 8 GB -->`
- **CPUs**: `<vcpu placement='static'>4</vcpu>`
- **Disk**: `<source file='/path/to/your/disk.qcow2'/>`

## License

LGPL-3.0-or-later (same as hyper2kvm)
