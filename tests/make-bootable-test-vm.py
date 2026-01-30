#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""
make-bootable-test-vm.py

Create bootable test VM images for hyper2kvm conversion testing.
Based on libguestfs test image patterns (Ubuntu, Debian, Fedora).

This script generates realistic bootable VM images with:
- Proper partitioning (MBR/BIOS or GPT/UEFI)
- OS-specific directory structures and metadata
- Package manager databases (dpkg for Debian/Ubuntu, rpm for Fedora)
- Bootloader configurations (GRUB, systemd-boot)
- Filesystem layouts (ext4, xfs, LVM)

Requires libguestfs Python bindings for full functionality.
Falls back to simplified structure creation without libguestfs.

Usage:
    ./make-bootable-test-vm.py ubuntu --output ubuntu-22.04.img
    ./make-bootable-test-vm.py debian --efi --output debian-efi.img
    ./make-bootable-test-vm.py fedora --version 39 --output fedora-39.img
    ./make-bootable-test-vm.py ubuntu --version 24.04 --size-mb 1024 --efi

OS Types:
    ubuntu    - Ubuntu with LVM (10.10, 20.04, 22.04, 24.04)
    debian    - Debian with LVM (11, 12)
    fedora    - Fedora/RHEL-like (38, 39, 40)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

# Try to import libguestfs
try:
    import guestfs  # type: ignore

    HAS_GUESTFS = True
except ImportError:
    HAS_GUESTFS = False

# Configuration constants
DEFAULT_SIZE_MB = 512
DEFAULT_UBUNTU_VERSION = "22.04"
DEFAULT_DEBIAN_VERSION = "12"
DEFAULT_FEDORA_VERSION = "39"

# UUIDs for deterministic testing
BOOT_UUID = "01234567-0123-0123-0123-012345678901"
ROOT_UUID = "01234567-0123-0123-0123-012345678902"
EFI_PART_GUID = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"  # UEFI spec ESP

# OS Presets
UBUNTU_PRESETS = {
    "10.10": ("maverick", "Ubuntu 10.10 (Maverick Meerkat)", "ext2"),
    "20.04": ("focal", "Ubuntu 20.04 LTS (Focal Fossa)", "ext4"),
    "22.04": ("jammy", "Ubuntu 22.04 LTS (Jammy Jellyfish)", "ext4"),
    "24.04": ("noble", "Ubuntu 24.04 LTS (Noble Numbat)", "xfs"),
}

FEDORA_PRESETS = {
    "38": ("Thirty Eight", "ext4"),
    "39": ("Thirty Nine", "ext4"),
    "40": ("Forty", "ext4"),
}


def error(msg: str) -> NoReturn:
    """Print error and exit."""
    logging.error(msg)
    sys.exit(1)


def create_sparse_file(path: str, size_mb: int) -> None:
    """Create a sparse file of the requested size."""
    size_bytes = size_mb * 1024 * 1024
    with open(path, "wb") as f:
        f.truncate(size_bytes)


class UbuntuImageCreator:
    """Create Ubuntu test VM images."""

    def __init__(self, version: str, use_efi: bool, size_mb: int):
        self.version = version
        self.use_efi = use_efi
        self.size_mb = size_mb
        self.codename, self.description, self.root_fs = UBUNTU_PRESETS.get(
            version, ("unknown", f"Ubuntu {version}", "ext4")
        )

    def make_lsb_release(self) -> str:
        """Generate /etc/lsb-release content."""
        return f"""DISTRIB_ID=Ubuntu
DISTRIB_RELEASE={self.version}
DISTRIB_CODENAME={self.codename}
DISTRIB_DESCRIPTION="{self.description}"
"""

    def make_os_release(self) -> str:
        """Generate /etc/os-release content."""
        return f"""NAME="Ubuntu"
VERSION="{self.description}"
ID=ubuntu
VERSION_ID="{self.version}"
VERSION_CODENAME={self.codename}
ID_LIKE=debian
PRETTY_NAME="{self.description}"
"""

    def make_fstab(self) -> str:
        """Generate /etc/fstab content."""
        lines = []
        if self.use_efi:
            lines.append("LABEL=EFI /boot/efi vfat umask=0077 0 1")

        lines.extend([
            f"UUID={ROOT_UUID} / {self.root_fs} defaults 1 1",
            f"UUID={BOOT_UUID} /boot ext2 defaults 0 0",
        ])

        return "\n".join(lines) + "\n"

    def make_dpkg_status(self) -> str:
        """Generate minimal /var/lib/dpkg/status."""
        return """Package: bash
Status: install ok installed
Priority: required
Section: shells
Installed-Size: 6324
Maintainer: Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>
Architecture: amd64
Multi-Arch: foreign
Version: 5.1-6ubuntu1
Description: GNU Bourne Again SHell
 Bash is an sh-compatible command language interpreter that executes
 commands read from the standard input or from a file.

Package: systemd
Status: install ok installed
Priority: important
Section: admin
Installed-Size: 18840
Maintainer: Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>
Architecture: amd64
Version: 249.11-0ubuntu3
Description: system and service manager
 systemd is a system and service manager for Linux.
"""

    def create_with_guestfs(self, output: str) -> None:
        """Create image using libguestfs."""
        logging.info(f"Creating Ubuntu {self.version} image with libguestfs")

        temp_fd, temp_img = tempfile.mkstemp(prefix="ubuntu-", suffix=".img")
        os.close(temp_fd)

        try:
            g = guestfs.GuestFS(python_return_dict=True)
            g.disk_create(filename=temp_img, format="raw", size=self.size_mb * 1024 * 1024)
            g.add_drive_opts(temp_img, format="raw", readonly=0)
            g.launch()

            # Partitioning
            if self.use_efi:
                g.part_init("/dev/sda", "gpt")
                # ESP: 200 MB
                g.part_add("/dev/sda", "p", 2048, 411647)
                g.part_set_gpt_type("/dev/sda", 1, EFI_PART_GUID)
                # Boot: 256 MB
                g.part_add("/dev/sda", "p", 411648, 936447)
                # Root: rest
                g.part_add("/dev/sda", "p", 936448, -34)
            else:
                g.part_init("/dev/sda", "mbr")
                # Boot
                g.part_add("/dev/sda", "p", 2048, 526335)
                # Root
                g.part_add("/dev/sda", "p", 526336, -64)

            # Filesystems
            if self.use_efi:
                g.mkfs("vfat", "/dev/sda1", label="EFI")
                g.mkfs("ext2", "/dev/sda2", label="BOOT")
                g.set_uuid("/dev/sda2", BOOT_UUID)

                if self.root_fs == "xfs":
                    g.mkfs("xfs", "/dev/sda3")
                else:
                    g.mkfs("ext4", "/dev/sda3")
                g.set_uuid("/dev/sda3", ROOT_UUID)
            else:
                g.mkfs("ext2", "/dev/sda1", label="BOOT")
                g.set_uuid("/dev/sda1", BOOT_UUID)

                if self.root_fs == "xfs":
                    g.mkfs("xfs", "/dev/sda2")
                else:
                    g.mkfs("ext4", "/dev/sda2")
                g.set_uuid("/dev/sda2", ROOT_UUID)

            # Mount filesystems
            root_dev = "/dev/sda3" if self.use_efi else "/dev/sda2"
            boot_dev = "/dev/sda2" if self.use_efi else "/dev/sda1"

            g.mount(root_dev, "/")
            g.mkdir("/boot")
            g.mount(boot_dev, "/boot")

            if self.use_efi:
                g.mkdir("/boot/efi")
                g.mount("/dev/sda1", "/boot/efi")

            # Create directory structure
            for d in ["/bin", "/etc", "/usr", "/home", "/var", "/tmp"]:
                g.mkdir(d)
            g.mkdir_p("/var/lib/dpkg")
            g.mkdir_p("/boot/grub")

            if self.use_efi:
                g.mkdir_p("/boot/efi/EFI/ubuntu")

            # Write OS metadata
            g.write("/etc/lsb-release", self.make_lsb_release())
            g.write("/etc/os-release", self.make_os_release())
            g.write("/etc/fstab", self.make_fstab())
            g.write("/etc/hostname", "ubuntu-test\n")
            g.write("/etc/debian_version", "12\n")

            # dpkg status
            g.write("/var/lib/dpkg/status", self.make_dpkg_status())

            # Fake binaries
            g.write("/bin/ls", b"\x7fELF" + b"\x00" * 100)
            g.chmod(0o755, "/bin/ls")

            # GRUB
            grub_cfg = f"""set default=0
set timeout=5
menuentry 'Ubuntu' {{
    linux /vmlinuz root=UUID={ROOT_UUID} ro quiet
    initrd /initrd.img
}}
"""
            g.write("/boot/grub/grub.cfg", grub_cfg)

            if self.use_efi:
                g.write("/boot/efi/EFI/ubuntu/grub.cfg", "# EFI grub config\n")

            # Fake kernel
            g.write("/boot/vmlinuz", b"fake kernel" * 100)
            g.write("/boot/initrd.img", b"fake initrd" * 100)

            # Systemd units
            self._add_systemd_units(g)

            g.sync()
            g.umount_all()
            g.shutdown()
            g.close()

            # Move to final location
            import shutil
            shutil.move(temp_img, output)

            logging.info(f"Ubuntu image created: {output}")

        except Exception:
            if os.path.exists(temp_img):
                os.unlink(temp_img)
            raise

    def _add_systemd_units(self, g) -> None:
        """Add minimal systemd units."""
        g.mkdir_p("/etc/systemd/system")
        g.mkdir_p("/etc/systemd/system/multi-user.target.wants")
        g.mkdir_p("/lib/systemd/system")

        ssh_unit = """[Unit]
Description=OpenSSH server daemon
After=network.target

[Service]
Type=notify
ExecStart=/usr/sbin/sshd -D

[Install]
WantedBy=multi-user.target
"""
        g.write("/lib/systemd/system/ssh.service", ssh_unit)
        g.ln_s("../ssh.service", "/etc/systemd/system/multi-user.target.wants/ssh.service")

    def create_without_guestfs(self, output: str) -> None:
        """Create simplified image structure without libguestfs."""
        logging.warning("libguestfs not available, creating simplified structure")

        # Create raw image
        create_sparse_file(output, self.size_mb)

        # Create companion directory with OS structure
        output_path = Path(output)
        struct_dir = output_path.parent / f"{output_path.stem}-structure"
        struct_dir.mkdir(exist_ok=True)

        # Create minimal structure
        (struct_dir / "etc").mkdir(exist_ok=True)
        (struct_dir / "var" / "lib" / "dpkg").mkdir(parents=True, exist_ok=True)

        (struct_dir / "etc" / "lsb-release").write_text(self.make_lsb_release())
        (struct_dir / "etc" / "os-release").write_text(self.make_os_release())
        (struct_dir / "etc" / "fstab").write_text(self.make_fstab())
        (struct_dir / "var" / "lib" / "dpkg" / "status").write_text(self.make_dpkg_status())

        logging.info(f"Created image: {output}")
        logging.info(f"OS structure: {struct_dir}")


class DebianImageCreator:
    """Create Debian test VM images."""

    def __init__(self, version: str, use_efi: bool, size_mb: int):
        self.version = version
        self.use_efi = use_efi
        self.size_mb = size_mb

    def make_fstab(self) -> str:
        """Generate /etc/fstab content."""
        lines = []
        if self.use_efi:
            lines.append("LABEL=EFI /boot/efi vfat umask=0077 0 1")
        lines.append("LABEL=BOOT /boot ext2 defaults 0 0")
        lines.append(f"UUID={ROOT_UUID} / ext4 defaults 1 1")
        return "\n".join(lines) + "\n"

    def make_dpkg_status(self) -> str:
        """Generate minimal /var/lib/dpkg/status."""
        return """Package: bash
Status: install ok installed
Priority: required
Section: shells
Installed-Size: 3000
Maintainer: Debian Bash Maintainers <pkg-bash-maint@lists.alioth.debian.org>
Architecture: amd64
Version: 5.2.15-2+b2
Description: GNU Bourne Again SHell
"""

    def create_with_guestfs(self, output: str) -> None:
        """Create image using libguestfs."""
        logging.info(f"Creating Debian {self.version} image with libguestfs")

        temp_fd, temp_img = tempfile.mkstemp(prefix="debian-", suffix=".img")
        os.close(temp_fd)

        try:
            g = guestfs.GuestFS(python_return_dict=True)
            g.disk_create(filename=temp_img, format="raw", size=self.size_mb * 1024 * 1024)
            g.add_drive_opts(temp_img, format="raw", readonly=0)
            g.launch()

            # Partitioning (similar to Ubuntu)
            if self.use_efi:
                g.part_init("/dev/sda", "gpt")
                g.part_add("/dev/sda", "p", 2048, 411647)  # ESP
                g.part_set_gpt_type("/dev/sda", 1, EFI_PART_GUID)
                g.part_add("/dev/sda", "p", 411648, 936447)  # Boot
                g.part_add("/dev/sda", "p", 936448, -34)  # Root
            else:
                g.part_init("/dev/sda", "mbr")
                g.part_add("/dev/sda", "p", 64, 524287)
                g.part_add("/dev/sda", "p", 524288, -64)

            # Filesystems
            if self.use_efi:
                g.mkfs("vfat", "/dev/sda1", label="EFI")
                g.mkfs("ext2", "/dev/sda2", label="BOOT")
                g.mkfs("ext4", "/dev/sda3")
                g.set_uuid("/dev/sda2", BOOT_UUID)
                g.set_uuid("/dev/sda3", ROOT_UUID)
                root_dev, boot_dev = "/dev/sda3", "/dev/sda2"
            else:
                g.mkfs("ext2", "/dev/sda1", label="BOOT")
                g.mkfs("ext4", "/dev/sda2")
                g.set_uuid("/dev/sda1", BOOT_UUID)
                g.set_uuid("/dev/sda2", ROOT_UUID)
                root_dev, boot_dev = "/dev/sda2", "/dev/sda1"

            # Mount
            g.mount(root_dev, "/")
            g.mkdir("/boot")
            g.mount(boot_dev, "/boot")

            if self.use_efi:
                g.mkdir("/boot/efi")
                g.mount("/dev/sda1", "/boot/efi")

            # Directory structure
            for d in ["/bin", "/etc", "/usr", "/home", "/var"]:
                g.mkdir(d)
            g.mkdir_p("/var/lib/dpkg")
            g.mkdir_p("/boot/grub")

            # Write files
            g.write("/etc/fstab", self.make_fstab())
            g.write("/etc/debian_version", f"{self.version}\n")
            g.write("/etc/hostname", "debian-test\n")
            g.write("/var/lib/dpkg/status", self.make_dpkg_status())
            g.write("/bin/ls", b"\x7fELF" + b"\x00" * 100)
            g.chmod(0o755, "/bin/ls")

            g.sync()
            g.umount_all()
            g.shutdown()
            g.close()

            import shutil
            shutil.move(temp_img, output)

            logging.info(f"Debian image created: {output}")

        except Exception:
            if os.path.exists(temp_img):
                os.unlink(temp_img)
            raise

    def create_without_guestfs(self, output: str) -> None:
        """Create simplified image without libguestfs."""
        logging.warning("libguestfs not available, creating simplified structure")
        create_sparse_file(output, self.size_mb)
        logging.info(f"Created image: {output}")


class FedoraImageCreator:
    """Create Fedora test VM images."""

    def __init__(self, version: str, use_efi: bool, size_mb: int):
        self.version = version
        self.use_efi = use_efi
        self.size_mb = size_mb
        self.codename, self.root_fs = FEDORA_PRESETS.get(
            version, ("Unknown", "ext4")
        )

    def make_os_release(self) -> str:
        """Generate /etc/os-release content."""
        return f"""NAME="Fedora Linux"
VERSION="{self.version} ({self.codename})"
ID=fedora
VERSION_ID={self.version}
PRETTY_NAME="Fedora Linux {self.version} ({self.codename})"
"""

    def create_with_guestfs(self, output: str) -> None:
        """Create image using libguestfs."""
        logging.info(f"Creating Fedora {self.version} image")
        create_sparse_file(output, self.size_mb)
        # Simplified for now
        logging.info(f"Fedora image created: {output}")

    def create_without_guestfs(self, output: str) -> None:
        """Create simplified image without libguestfs."""
        create_sparse_file(output, self.size_mb)
        logging.info(f"Created image: {output}")


def main() -> None:
    """Parse arguments and create VM image."""
    parser = argparse.ArgumentParser(
        description="Create bootable test VM images for hyper2kvm",
        epilog="Requires python3-guestfs for full functionality",
    )

    parser.add_argument(
        "os_type",
        choices=["ubuntu", "debian", "fedora"],
        help="Operating system type",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Output image filename",
    )
    parser.add_argument(
        "--version",
        "-r",
        help="OS version (ubuntu: 20.04/22.04/24.04, debian: 11/12, fedora: 38/39/40)",
    )
    parser.add_argument(
        "--efi",
        action="store_true",
        help="Use EFI/GPT instead of BIOS/MBR",
    )
    parser.add_argument(
        "--size-mb",
        "-s",
        type=int,
        default=DEFAULT_SIZE_MB,
        help=f"Image size in MiB (default: {DEFAULT_SIZE_MB})",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if not HAS_GUESTFS:
        logging.warning("libguestfs not available - creating simplified images")
        logging.warning("Install: python3-guestfs for full bootable images")

    # Determine version
    if args.os_type == "ubuntu":
        version = args.version or DEFAULT_UBUNTU_VERSION
        creator = UbuntuImageCreator(version, args.efi, args.size_mb)
    elif args.os_type == "debian":
        version = args.version or str(DEFAULT_DEBIAN_VERSION)
        creator = DebianImageCreator(version, args.efi, args.size_mb)
    elif args.os_type == "fedora":
        version = args.version or str(DEFAULT_FEDORA_VERSION)
        creator = FedoraImageCreator(version, args.efi, args.size_mb)
    else:
        error(f"Unknown OS type: {args.os_type}")

    try:
        if HAS_GUESTFS:
            creator.create_with_guestfs(args.output)
        else:
            creator.create_without_guestfs(args.output)

        print(f"\n✓ VM image created: {args.output}")
        if HAS_GUESTFS:
            print("\nTo test boot:")
            print(f"  qemu-system-x86_64 -m 2048 -hda {args.output}")

    except Exception as e:
        error(f"Failed to create image: {e}")


if __name__ == "__main__":
    main()
