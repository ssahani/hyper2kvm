"""
initramfs Fixer - Production-Grade Implementation

Rebuilds initramfs with virtio drivers for migrated VMs to ensure first-boot success.

Operations:
1. Detect initramfs tool (dracut, mkinitramfs, mkinitrd)
2. Find all installed kernels
3. Add virtio modules (virtio_blk, virtio_scsi, virtio_net, virtio_pci)
4. Add LVM/dm modules if LVM detected
5. Regenerate initramfs for all kernels
6. Validate virtio drivers are present in output

Idempotent: Safe to re-run multiple times.
Portable: Works in VM, bare metal, or online mode.
OS-aware: Handles RHEL/CentOS (dracut), Ubuntu/Debian (mkinitramfs).
"""

import os
import re
import logging
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

from .utils import (
    run_command,
    detect_os_from_root,
    create_backup
)


logger = logging.getLogger(__name__)


class InitramfsTool(str, Enum):
    """Initramfs generation tool."""
    DRACUT = "dracut"           # RHEL/CentOS/Fedora
    MKINITRAMFS = "mkinitramfs" # Ubuntu/Debian
    MKINITRD = "mkinitrd"       # Legacy RHEL
    UNKNOWN = "unknown"


@dataclass
class KernelInfo:
    """Information about an installed kernel."""
    version: str                      # e.g., "5.14.0-284.el9.x86_64"
    image_path: Path                  # e.g., /boot/vmlinuz-5.14.0-284.el9.x86_64
    initramfs_path: Path             # e.g., /boot/initramfs-5.14.0-284.el9.x86_64.img
    modules_dir: Path                # e.g., /lib/modules/5.14.0-284.el9.x86_64
    has_virtio: bool = False         # Does initramfs already have virtio?
    needs_rebuild: bool = True       # Should we rebuild this initramfs?


class InitramfsFixer:
    """
    Production-grade initramfs fixer.

    Rebuilds initramfs with virtio drivers and LVM support for VM migration.
    """

    # Virtio modules needed for KVM
    VIRTIO_MODULES = [
        "virtio_pci",       # Base virtio PCI driver
        "virtio_blk",       # Block device driver
        "virtio_scsi",      # SCSI driver
        "virtio_net",       # Network driver
        "virtio_ring",      # Ring buffer (dependency)
        "virtio",           # Core virtio
    ]

    # LVM/Device Mapper modules
    LVM_MODULES = [
        "dm_mod",           # Device mapper
        "dm_mirror",        # RAID1 support
        "dm_snapshot",      # Snapshot support
    ]

    def __init__(
        self,
        root_mount: str = "/mnt",
        add_lvm: bool = True,
        force_rebuild: bool = False,
        dry_run: bool = False,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize initramfs fixer.

        Args:
            root_mount: Path where root filesystem is mounted
            add_lvm: Add LVM modules to initramfs
            force_rebuild: Force rebuild even if virtio present
            dry_run: If True, don't modify files
            logger: Optional logger instance
        """
        self.root_mount = Path(root_mount)
        self.add_lvm = add_lvm
        self.force_rebuild = force_rebuild
        self.dry_run = dry_run
        self.logger = logger or logging.getLogger(__name__)

        self.boot_dir = self.root_mount / "boot"
        self.modules_dir = self.root_mount / "lib/modules"
        self.etc_dir = self.root_mount / "etc"

        # Detected information
        self.os_info: Dict[str, str] = {}
        self.tool: InitramfsTool = InitramfsTool.UNKNOWN
        self.kernels: List[KernelInfo] = []

        # Statistics
        self.stats = {
            'kernels_found': 0,
            'kernels_rebuilt': 0,
            'virtio_added': 0,
            'lvm_added': 0,
            'warnings': 0,
            'errors': 0
        }

    def fix(self) -> Dict[str, any]:
        """
        Execute initramfs fixes.

        Returns:
            Dictionary with fix results:
            - success: bool
            - stats: Fix statistics
            - warnings: List of warnings
            - errors: List of errors
        """
        self.logger.info(f"Starting initramfs fix: dry_run={self.dry_run}, force={self.force_rebuild}")

        results = {
            'success': False,
            'stats': {},
            'warnings': [],
            'errors': []
        }

        try:
            # Step 1: Detect OS and tool
            self.logger.info("Detecting OS and initramfs tool...")
            self.os_info = detect_os_from_root(str(self.root_mount))
            self.tool = self._detect_initramfs_tool()

            if self.tool == InitramfsTool.UNKNOWN:
                error = "Could not detect initramfs tool (dracut/mkinitramfs/mkinitrd)"
                self.logger.error(error)
                results['errors'].append(error)
                return results

            self.logger.info(f"Detected: OS={self.os_info['family']}, tool={self.tool.value}")

            # Step 2: Find installed kernels
            self.logger.info("Finding installed kernels...")
            self._find_kernels()
            self.stats['kernels_found'] = len(self.kernels)

            if not self.kernels:
                error = "No kernels found in /boot"
                self.logger.error(error)
                results['errors'].append(error)
                return results

            self.logger.info(f"Found {len(self.kernels)} kernel(s)")

            # Step 3: Check existing initramfs for virtio
            if not self.force_rebuild:
                self.logger.info("Checking existing initramfs for virtio...")
                self._check_existing_initramfs()

            # Step 4: Configure initramfs tool
            self.logger.info("Configuring initramfs tool...")
            if not self.dry_run:
                self._configure_initramfs_tool()

            # Step 5: Rebuild initramfs for each kernel
            self.logger.info("Rebuilding initramfs...")
            for kernel in self.kernels:
                if kernel.needs_rebuild or self.force_rebuild:
                    if not self.dry_run:
                        self._rebuild_initramfs(kernel)
                    else:
                        self.logger.info(f"DRY RUN: Would rebuild initramfs for {kernel.version}")
                    self.stats['kernels_rebuilt'] += 1

            # Step 6: Validate rebuilt initramfs
            if not self.dry_run:
                self.logger.info("Validating rebuilt initramfs...")
                self._validate_initramfs()

            # Collect results
            results['success'] = True
            results['stats'] = self.stats
            results['warnings'] = self._collect_warnings()

            self.logger.info(
                f"initramfs fix complete: rebuilt={self.stats['kernels_rebuilt']}/{self.stats['kernels_found']}"
            )

        except Exception as e:
            error = f"initramfs fix failed: {e}"
            self.logger.error(error, exc_info=True)
            results['errors'].append(error)
            self.stats['errors'] += 1

        return results

    def _detect_initramfs_tool(self) -> InitramfsTool:
        """Detect which initramfs tool is available."""

        # Check for dracut (RHEL/CentOS/Fedora)
        dracut_path = self.root_mount / "usr/bin/dracut"
        if dracut_path.exists():
            return InitramfsTool.DRACUT

        # Check for mkinitramfs (Ubuntu/Debian)
        mkinitramfs_path = self.root_mount / "usr/sbin/mkinitramfs"
        if mkinitramfs_path.exists():
            return InitramfsTool.MKINITRAMFS

        # Check for legacy mkinitrd (old RHEL)
        mkinitrd_path = self.root_mount / "sbin/mkinitrd"
        if mkinitrd_path.exists():
            return InitramfsTool.MKINITRD

        # Try OS family as fallback
        if self.os_info.get('family') in ['centos', 'rhel', 'fedora']:
            if dracut_path.exists() or (self.root_mount / "sbin/dracut").exists():
                return InitramfsTool.DRACUT
        elif self.os_info.get('family') in ['ubuntu', 'debian']:
            if mkinitramfs_path.exists():
                return InitramfsTool.MKINITRAMFS

        return InitramfsTool.UNKNOWN

    def _find_kernels(self):
        """Find all installed kernels."""
        if not self.boot_dir.exists():
            self.logger.warning(f"Boot directory not found: {self.boot_dir}")
            return

        # Find vmlinuz files
        vmlinuz_pattern = "vmlinuz-*"
        vmlinuz_files = list(self.boot_dir.glob(vmlinuz_pattern))

        # Also check for Image-* (some distros)
        image_files = list(self.boot_dir.glob("Image-*"))

        kernel_images = vmlinuz_files + image_files

        for kernel_image in kernel_images:
            # Extract version from filename
            # vmlinuz-5.14.0-284.el9.x86_64 → 5.14.0-284.el9.x86_64
            if kernel_image.name.startswith("vmlinuz-"):
                version = kernel_image.name[8:]
            elif kernel_image.name.startswith("Image-"):
                version = kernel_image.name[6:]
            else:
                continue

            # Find corresponding initramfs
            initramfs_path = self._find_initramfs_for_kernel(version)
            if not initramfs_path:
                self.logger.warning(f"No initramfs found for kernel {version}")
                continue

            # Check modules directory
            modules_dir = self.modules_dir / version
            if not modules_dir.exists():
                self.logger.warning(f"Modules directory not found: {modules_dir}")
                continue

            kernel_info = KernelInfo(
                version=version,
                image_path=kernel_image,
                initramfs_path=initramfs_path,
                modules_dir=modules_dir
            )

            self.kernels.append(kernel_info)
            self.logger.debug(f"Found kernel: {version}")

    def _find_initramfs_for_kernel(self, version: str) -> Optional[Path]:
        """Find initramfs file for a kernel version."""
        # Common patterns
        patterns = [
            f"initramfs-{version}.img",       # RHEL/CentOS
            f"initrd.img-{version}",          # Ubuntu/Debian
            f"initramfs-{version}",           # No extension
            f"initrd-{version}.img",          # Alternative
            f"initrd-{version}",              # Alternative
        ]

        for pattern in patterns:
            initramfs_path = self.boot_dir / pattern
            if initramfs_path.exists():
                return initramfs_path

        return None

    def _check_existing_initramfs(self):
        """Check if existing initramfs already has virtio drivers."""
        for kernel in self.kernels:
            has_virtio = self._initramfs_has_virtio(kernel.initramfs_path)
            kernel.has_virtio = has_virtio

            if has_virtio and not self.force_rebuild:
                kernel.needs_rebuild = False
                self.logger.info(f"Kernel {kernel.version}: virtio already present, skip rebuild")
            else:
                kernel.needs_rebuild = True
                if has_virtio:
                    self.logger.info(f"Kernel {kernel.version}: force rebuild requested")
                else:
                    self.logger.info(f"Kernel {kernel.version}: virtio missing, needs rebuild")

    def _initramfs_has_virtio(self, initramfs_path: Path) -> bool:
        """Check if initramfs contains virtio modules."""
        if not initramfs_path.exists():
            return False

        # Use lsinitrd for dracut-based systems
        if self.tool == InitramfsTool.DRACUT:
            try:
                # lsinitrd /boot/initramfs-X.img | grep virtio
                returncode, stdout, _ = run_command(
                    ["lsinitrd", str(initramfs_path)],
                    check=False,
                    timeout=30
                )

                if returncode == 0:
                    # Check for virtio modules in output
                    virtio_found = any(module in stdout for module in ['virtio_blk', 'virtio_scsi'])
                    return virtio_found

            except Exception as e:
                self.logger.debug(f"lsinitrd check failed: {e}")

        # Use lsinitramfs for Ubuntu/Debian
        elif self.tool == InitramfsTool.MKINITRAMFS:
            try:
                # lsinitramfs /boot/initrd.img-X | grep virtio
                returncode, stdout, _ = run_command(
                    ["lsinitramfs", str(initramfs_path)],
                    check=False,
                    timeout=30
                )

                if returncode == 0:
                    virtio_found = 'virtio' in stdout
                    return virtio_found

            except Exception as e:
                self.logger.debug(f"lsinitramfs check failed: {e}")

        return False

    def _configure_initramfs_tool(self):
        """Configure initramfs tool to include virtio drivers."""

        if self.tool == InitramfsTool.DRACUT:
            self._configure_dracut()
        elif self.tool == InitramfsTool.MKINITRAMFS:
            self._configure_mkinitramfs()
        elif self.tool == InitramfsTool.MKINITRD:
            # mkinitrd uses /etc/modprobe.conf, usually no config needed
            pass

    def _configure_dracut(self):
        """Configure dracut to include virtio drivers."""
        # Create /etc/dracut.conf.d/virtio.conf
        dracut_conf_dir = self.etc_dir / "dracut.conf.d"
        dracut_conf_dir.mkdir(parents=True, exist_ok=True)

        virtio_conf = dracut_conf_dir / "virtio.conf"

        # Build module list
        modules = self.VIRTIO_MODULES.copy()
        if self.add_lvm:
            modules.extend(self.LVM_MODULES)

        # Create dracut config
        config_lines = [
            "# Generated by hyper2kvm - virtio drivers for KVM migration",
            f"add_drivers+=\" {' '.join(modules)} \"",
            "",
            "# Force include these modules",
            "force_drivers+=\" virtio_blk virtio_scsi \"",
            ""
        ]

        if virtio_conf.exists():
            backup = create_backup(virtio_conf)
            self.logger.info(f"Backed up existing dracut config: {backup}")

        virtio_conf.write_text('\n'.join(config_lines))
        self.logger.info(f"Created dracut config: {virtio_conf}")
        self.stats['virtio_added'] = len(self.VIRTIO_MODULES)
        if self.add_lvm:
            self.stats['lvm_added'] = len(self.LVM_MODULES)

    def _configure_mkinitramfs(self):
        """Configure mkinitramfs to include virtio drivers."""
        # Create /etc/initramfs-tools/modules
        initramfs_tools_dir = self.etc_dir / "initramfs-tools"
        initramfs_tools_dir.mkdir(parents=True, exist_ok=True)

        modules_file = initramfs_tools_dir / "modules"

        # Build module list
        modules = self.VIRTIO_MODULES.copy()
        if self.add_lvm:
            modules.extend(self.LVM_MODULES)

        # Read existing modules
        existing_modules = []
        if modules_file.exists():
            existing_modules = modules_file.read_text().splitlines()
            backup = create_backup(modules_file)
            self.logger.info(f"Backed up existing modules file: {backup}")

        # Add virtio modules if not already present
        new_modules = existing_modules.copy()
        added = []

        for module in modules:
            if module not in new_modules:
                new_modules.append(module)
                added.append(module)

        if added:
            # Write updated modules file
            header = ["# Generated by hyper2kvm - virtio drivers for KVM migration", ""]
            modules_file.write_text('\n'.join(header + new_modules + [""]))
            self.logger.info(f"Added {len(added)} modules to {modules_file}")
            self.stats['virtio_added'] = len([m for m in added if m in self.VIRTIO_MODULES])
            if self.add_lvm:
                self.stats['lvm_added'] = len([m for m in added if m in self.LVM_MODULES])

    def _rebuild_initramfs(self, kernel: KernelInfo):
        """Rebuild initramfs for a specific kernel."""
        self.logger.info(f"Rebuilding initramfs for kernel {kernel.version}...")

        # Backup existing initramfs
        if kernel.initramfs_path.exists():
            backup = create_backup(kernel.initramfs_path)
            self.logger.info(f"Backed up initramfs: {backup}")

        try:
            if self.tool == InitramfsTool.DRACUT:
                self._rebuild_with_dracut(kernel)
            elif self.tool == InitramfsTool.MKINITRAMFS:
                self._rebuild_with_mkinitramfs(kernel)
            elif self.tool == InitramfsTool.MKINITRD:
                self._rebuild_with_mkinitrd(kernel)

            self.logger.info(f"Successfully rebuilt initramfs for {kernel.version}")

        except Exception as e:
            error = f"Failed to rebuild initramfs for {kernel.version}: {e}"
            self.logger.error(error)
            self.stats['errors'] += 1
            raise

    def _rebuild_with_dracut(self, kernel: KernelInfo):
        """Rebuild initramfs using dracut."""
        # dracut -f /boot/initramfs-$(uname -r).img $(uname -r)
        cmd = [
            "dracut",
            "-f",  # Force overwrite
            "--kver", kernel.version,
            str(kernel.initramfs_path)
        ]

        self.logger.debug(f"Running: {' '.join(cmd)}")

        # Run in chroot context
        chroot_cmd = ["chroot", str(self.root_mount)] + cmd

        returncode, stdout, stderr = run_command(chroot_cmd, timeout=300)

        if returncode != 0:
            raise RuntimeError(f"dracut failed: {stderr}")

        if stdout:
            self.logger.debug(f"dracut output: {stdout}")

    def _rebuild_with_mkinitramfs(self, kernel: KernelInfo):
        """Rebuild initramfs using mkinitramfs."""
        # mkinitramfs -o /boot/initrd.img-X X
        cmd = [
            "mkinitramfs",
            "-o", str(kernel.initramfs_path),
            kernel.version
        ]

        self.logger.debug(f"Running: {' '.join(cmd)}")

        # Run in chroot context
        chroot_cmd = ["chroot", str(self.root_mount)] + cmd

        returncode, stdout, stderr = run_command(chroot_cmd, timeout=300)

        if returncode != 0:
            raise RuntimeError(f"mkinitramfs failed: {stderr}")

    def _rebuild_with_mkinitrd(self, kernel: KernelInfo):
        """Rebuild initramfs using legacy mkinitrd."""
        # mkinitrd -f /boot/initramfs-X.img X
        cmd = [
            "mkinitrd",
            "-f",
            str(kernel.initramfs_path),
            kernel.version
        ]

        self.logger.debug(f"Running: {' '.join(cmd)}")

        # Run in chroot context
        chroot_cmd = ["chroot", str(self.root_mount)] + cmd

        returncode, stdout, stderr = run_command(chroot_cmd, timeout=300)

        if returncode != 0:
            raise RuntimeError(f"mkinitrd failed: {stderr}")

    def _validate_initramfs(self):
        """Validate that rebuilt initramfs contains virtio drivers."""
        for kernel in self.kernels:
            if kernel.needs_rebuild or self.force_rebuild:
                has_virtio = self._initramfs_has_virtio(kernel.initramfs_path)

                if has_virtio:
                    self.logger.info(f"✓ Kernel {kernel.version}: virtio drivers present in initramfs")
                else:
                    warning = f"Kernel {kernel.version}: virtio drivers NOT detected in initramfs"
                    self.logger.warning(warning)
                    self.stats['warnings'] += 1

    def _collect_warnings(self) -> List[str]:
        """Collect all warnings from fix process."""
        warnings = []

        # Check for kernels that couldn't be rebuilt
        failed_kernels = [k for k in self.kernels if k.needs_rebuild and not self.dry_run]
        if failed_kernels and self.stats['errors'] > 0:
            warnings.append(f"Failed to rebuild {len(failed_kernels)} kernel(s)")

        return warnings

    def get_summary(self) -> str:
        """Get human-readable summary of fixes."""
        lines = [
            "initramfs Fix Summary:",
            f"  Tool detected: {self.tool.value}",
            f"  Kernels found: {self.stats['kernels_found']}",
            f"  Kernels rebuilt: {self.stats['kernels_rebuilt']}",
            f"  Virtio modules added: {self.stats['virtio_added']}",
            f"  LVM modules added: {self.stats['lvm_added']}",
            f"  Warnings: {self.stats['warnings']}",
            f"  Errors: {self.stats['errors']}"
        ]

        if self.kernels:
            lines.append("\n  Kernels:")
            for kernel in self.kernels:
                status = "REBUILT" if kernel.needs_rebuild else "SKIPPED"
                virtio = "✓" if kernel.has_virtio else "✗"
                lines.append(f"    {status:8s} {kernel.version:40s} (virtio: {virtio})")

        return '\n'.join(lines)


# Convenience function for direct usage
def fix_initramfs(
    root_mount: str = "/mnt",
    add_lvm: bool = True,
    force_rebuild: bool = False,
    dry_run: bool = False
) -> Dict[str, any]:
    """
    Fix initramfs in mounted root filesystem.

    Args:
        root_mount: Path where root filesystem is mounted
        add_lvm: Add LVM modules to initramfs
        force_rebuild: Force rebuild even if virtio present
        dry_run: If True, don't modify files

    Returns:
        Dictionary with fix results

    Example:
        >>> results = fix_initramfs("/mnt", add_lvm=True, dry_run=False)
        >>> if results['success']:
        ...     print(f"Rebuilt {results['stats']['kernels_rebuilt']} kernel(s)")
    """
    fixer = InitramfsFixer(
        root_mount=root_mount,
        add_lvm=add_lvm,
        force_rebuild=force_rebuild,
        dry_run=dry_run
    )

    return fixer.fix()
