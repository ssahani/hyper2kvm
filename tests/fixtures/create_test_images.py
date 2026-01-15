#!/usr/bin/env python3
"""
Create Test VM Disk Images using libguestfs

This script creates realistic test VM disk images with:
- Partition tables
- Filesystems
- Boot configuration
- Network configuration
- fstab files

Used for comprehensive integration testing.
"""

import os
import sys
from pathlib import Path

def create_test_images():
    """Create test VM disk images with guestfs"""

    try:
        import guestfs
    except ImportError:
        print("ERROR: python3-guestfs not installed")
        print("Install with: sudo dnf install python3-libguestfs")
        sys.exit(1)

    script_dir = Path(__file__).parent
    images_dir = script_dir / "images"
    images_dir.mkdir(exist_ok=True)

    print("=" * 50)
    print("Creating Test VM Disk Images")
    print("=" * 50)
    print()

    # Create Linux QCOW2 test image
    create_linux_qcow2(images_dir / "test-linux-qcow2.qcow2")

    # Create Linux RAW test image
    create_linux_raw(images_dir / "test-linux-raw.img")

    # Create VMDK test image (converted from qcow2)
    create_vmdk_from_qcow2(
        images_dir / "test-linux-qcow2.qcow2",
        images_dir / "test-linux-vmdk.vmdk"
    )

    print()
    print("=" * 50)
    print("Test Image Creation Complete")
    print("=" * 50)
    print()
    print(f"Images created in: {images_dir}")

    # List created images
    for img in images_dir.glob("*"):
        size_mb = img.stat().st_size / (1024 * 1024)
        print(f"  {img.name} ({size_mb:.1f} MB)")


def create_linux_qcow2(image_path: Path):
    """Create a Linux test image with QCOW2 format"""
    import guestfs

    print(f"Creating {image_path.name}...")

    # Create guest instance
    g = guestfs.GuestFS(python_return_dict=True)

    # Create disk image
    g.disk_create(str(image_path), "qcow2", 1024 * 1024 * 1024)  # 1GB

    # Add the disk
    g.add_drive_opts(str(image_path), format="qcow2", readonly=False)

    # Launch the backend
    g.launch()

    # Create partition table
    g.part_disk("/dev/sda", "mbr")

    # Create filesystem
    g.mkfs("ext4", "/dev/sda1")

    # Set partition bootable
    g.part_set_bootable("/dev/sda", 1, True)

    # Mount filesystem
    g.mount("/dev/sda1", "/")

    # Create directory structure
    for d in ["boot", "boot/grub2", "etc", "etc/sysconfig",
              "etc/sysconfig/network-scripts", "var", "usr", "home"]:
        g.mkdir_p(f"/{d}")

    # Create /etc/fstab
    fstab_content = """# Test fstab for hyper2kvm testing
UUID=test-uuid-abcd-1234 /     ext4 defaults 1 1
UUID=test-boot-uuid       /boot ext4 defaults 1 2
"""
    g.write("/etc/fstab", fstab_content)

    # Create GRUB2 config
    grub_cfg = """# Test GRUB2 Configuration
set timeout=5
set default=0

menuentry 'Test Linux Kernel' {
    set root='hd0,msdos1'
    linux /boot/vmlinuz-test root=UUID=test-uuid-abcd-1234 ro quiet
    initrd /boot/initrd-test.img
}

menuentry 'Test Recovery Mode' {
    set root='hd0,msdos1'
    linux /boot/vmlinuz-test root=UUID=test-uuid-abcd-1234 ro single
    initrd /boot/initrd-test.img
}
"""
    g.write("/boot/grub2/grub.cfg", grub_cfg)

    # Create network config (RHEL/CentOS style)
    ifcfg_eth0 = """# Test Network Interface
DEVICE=eth0
BOOTPROTO=dhcp
ONBOOT=yes
TYPE=Ethernet
HWADDR=00:50:56:ab:cd:ef
NM_CONTROLLED=yes
"""
    g.write("/etc/sysconfig/network-scripts/ifcfg-eth0", ifcfg_eth0)

    # Create a second interface with static IP
    ifcfg_eth1 = """# Test Static Interface
DEVICE=eth1
BOOTPROTO=static
IPADDR=192.168.122.100
NETMASK=255.255.255.0
GATEWAY=192.168.122.1
ONBOOT=yes
TYPE=Ethernet
HWADDR=00:50:56:ab:cd:f0
"""
    g.write("/etc/sysconfig/network-scripts/ifcfg-eth1", ifcfg_eth1)

    # Create /etc/hostname
    g.write("/etc/hostname", "test-linux-vm\n")

    # Create /etc/hosts
    hosts_content = """127.0.0.1   localhost localhost.localdomain
::1         localhost localhost.localdomain
192.168.122.100 test-linux-vm test-linux-vm.localdomain
"""
    g.write("/etc/hosts", hosts_content)

    # Create a test file to verify mounting works
    g.write("/etc/test-marker", "hyper2kvm-test-image\n")

    # Unmount and close
    g.umount("/")
    g.shutdown()
    g.close()

    print(f"  ✓ Created {image_path.name} with ext4 filesystem")


def create_linux_raw(image_path: Path):
    """Create a RAW format test image"""
    import guestfs

    print(f"Creating {image_path.name}...")

    g = guestfs.GuestFS(python_return_dict=True)

    # Create RAW disk image
    g.disk_create(str(image_path), "raw", 1024 * 1024 * 1024)  # 1GB

    g.add_drive_opts(str(image_path), format="raw", readonly=False)
    g.launch()

    # Single partition
    g.part_disk("/dev/sda", "mbr")
    g.mkfs("ext4", "/dev/sda1")
    g.part_set_bootable("/dev/sda", 1, True)

    # Mount and add minimal content
    g.mount("/dev/sda1", "/")

    g.mkdir_p("/boot")
    g.mkdir_p("/etc")

    # Minimal fstab
    g.write("/etc/fstab", "/dev/sda1 / ext4 defaults 0 1\n")

    g.umount("/")
    g.shutdown()
    g.close()

    print(f"  ✓ Created {image_path.name} (RAW format)")


def create_vmdk_from_qcow2(source_qcow2: Path, target_vmdk: Path):
    """Convert QCOW2 to VMDK using qemu-img"""
    import subprocess

    if not source_qcow2.exists():
        print(f"  ! Source {source_qcow2} not found, skipping VMDK creation")
        return

    print(f"Creating {target_vmdk.name} from {source_qcow2.name}...")

    try:
        subprocess.run([
            "qemu-img", "convert",
            "-f", "qcow2",
            "-O", "vmdk",
            str(source_qcow2),
            str(target_vmdk)
        ], check=True, capture_output=True)

        print(f"  ✓ Converted to VMDK format")
    except subprocess.CalledProcessError as e:
        print(f"  ! Failed to create VMDK: {e}")
    except FileNotFoundError:
        print(f"  ! qemu-img not found, install qemu-utils")


if __name__ == "__main__":
    create_test_images()
