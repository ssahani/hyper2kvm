# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/vmcraft/mount.py
"""
Mount management for guest filesystems.

Handles mounting and unmounting of filesystems with support for:
- Linux filesystems (ext2/3/4, XFS, Btrfs, ZFS)
- Windows filesystems (NTFS via ntfs-3g, FAT32, exFAT)
- Read-only and read-write modes
- Filesystem-specific mount options
- Multi-device mount tracking
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from ._utils import run_sudo


logger = logging.getLogger(__name__)


class MountManager:
    """
    Manages filesystem mounting and unmounting.

    Tracks mounted filesystems and handles cleanup on shutdown.
    Provides filesystem-specific mount options for optimal compatibility.
    """

    def __init__(self, logger: logging.Logger, mount_root: Path):
        """
        Initialize mount manager.

        Args:
            logger: Logger instance
            mount_root: Root directory for mounting guest filesystems
        """
        self.logger = logger
        self.mount_root = mount_root
        self._mounted: dict[str, str] = {}  # mountpoint -> device

    def mount(self, device: str, mountpoint: str, *, readonly: bool = False, options: str | None = None) -> None:
        """
        Mount device at mountpoint.

        Args:
            device: Device path (e.g., /dev/nbd0p1)
            mountpoint: Mount point path (e.g., /)
            readonly: Mount read-only if True
            options: Custom mount options string

        Raises:
            RuntimeError: If mount fails
        """
        # Resolve mountpoint relative to mount root
        if mountpoint.startswith('/'):
            target = self.mount_root / mountpoint[1:]
        else:
            target = self.mount_root / mountpoint

        # Create mountpoint if needed
        target.mkdir(parents=True, exist_ok=True)

        # Detect filesystem type for appropriate mount options
        fstype = self._detect_fstype(device)

        # Build mount command with filesystem-specific options
        cmd = ["mount"]
        mount_opts = []

        if options:
            mount_opts.append(options)
        else:
            # Auto-configure based on filesystem type
            if fstype == "ntfs":
                # Use ntfs-3g for full read-write support
                cmd.extend(["-t", "ntfs-3g"])
                if readonly:
                    mount_opts.append("ro")
                else:
                    # Enable permissions, compression, and streams
                    mount_opts.extend(["permissions", "streams_interface=windows"])
            elif fstype in ("vfat", "msdos", "fat"):
                # FAT filesystems
                cmd.extend(["-t", "vfat"])
                mount_opts.extend(["iocharset=utf8", "shortname=mixed"])
                if readonly:
                    mount_opts.append("ro")
            elif fstype == "exfat":
                # exFAT filesystem
                cmd.extend(["-t", "exfat"])
                mount_opts.append("iocharset=utf8")
                if readonly:
                    mount_opts.append("ro")
            elif fstype in ("ext2", "ext3", "ext4"):
                # Linux ext filesystems
                if readonly:
                    mount_opts.extend(["ro", "noload"])
            elif fstype == "xfs":
                # XFS filesystem
                if readonly:
                    mount_opts.extend(["ro", "norecovery"])
            elif fstype == "btrfs":
                # Btrfs filesystem
                if readonly:
                    mount_opts.extend(["ro", "norecovery"])
            else:
                # Generic fallback
                if readonly:
                    mount_opts.append("ro")

        if mount_opts:
            cmd.extend(["-o", ",".join(mount_opts)])

        cmd.extend([device, str(target)])

        # Mount with retries for different filesystem states
        try:
            run_sudo(self.logger, cmd, check=True, capture=True)
            self._mounted[mountpoint] = device
            self.logger.debug(f"Mounted {device} at {mountpoint} (fstype={fstype})")
        except subprocess.CalledProcessError as e:
            # If mount failed and it's a Windows filesystem, try with additional recovery options
            if fstype in ("ntfs", "vfat", "exfat") and not readonly:
                self.logger.warning(f"Mount failed, retrying {device} in read-only mode...")
                # Retry in read-only mode
                cmd_ro = ["mount", "-t", fstype if fstype != "fat" else "vfat", "-o", "ro"]
                cmd_ro.extend([device, str(target)])
                try:
                    run_sudo(self.logger, cmd_ro, check=True, capture=True)
                    self._mounted[mountpoint] = device
                    self.logger.info(f"Mounted {device} at {mountpoint} in read-only mode")
                    return
                except subprocess.CalledProcessError:
                    pass
            raise RuntimeError(f"Failed to mount {device}: {e.stderr}")

    def _detect_fstype(self, device: str) -> str:
        """
        Detect filesystem type using blkid.

        Args:
            device: Device path

        Returns:
            Filesystem type string (e.g., "ext4", "ntfs", "xfs")
        """
        try:
            result = run_sudo(self.logger, ["blkid", "-o", "value", "-s", "TYPE", device], check=True, capture=True)
            fstype = result.stdout.strip()
            return fstype if fstype else "unknown"
        except Exception:
            return "unknown"

    def umount_all(self) -> None:
        """Unmount all mounted filesystems."""
        # Unmount in reverse order (deepest first)
        for mountpoint in sorted(self._mounted.keys(), reverse=True):
            try:
                if mountpoint.startswith('/'):
                    target = self.mount_root / mountpoint[1:]
                else:
                    target = self.mount_root / mountpoint

                run_sudo(self.logger, ["umount", str(target)], check=False, capture=True)
                self.logger.debug(f"Unmounted {mountpoint}")
            except Exception as e:
                self.logger.warning(f"Failed to unmount {mountpoint}: {e}")

        self._mounted.clear()

    def umount(self, mountpoint: str) -> None:
        """
        Unmount a specific mountpoint.

        Args:
            mountpoint: Mount point path to unmount
        """
        if mountpoint not in self._mounted:
            return

        try:
            if mountpoint.startswith('/'):
                target = self.mount_root / mountpoint[1:]
            else:
                target = self.mount_root / mountpoint

            run_sudo(self.logger, ["umount", str(target)], check=True, capture=True)
            del self._mounted[mountpoint]
            self.logger.debug(f"Unmounted {mountpoint}")
        except Exception as e:
            self.logger.warning(f"Failed to unmount {mountpoint}: {e}")

    def mountpoints(self) -> list[str]:
        """Get list of current mountpoints."""
        return list(self._mounted.keys())

    def mounts(self) -> list[str]:
        """Get list of mounted devices."""
        return list(self._mounted.values())

    def is_mounted(self, mountpoint: str) -> bool:
        """Check if a mountpoint is currently mounted."""
        return mountpoint in self._mounted

    def get_device(self, mountpoint: str) -> str | None:
        """Get the device mounted at a specific mountpoint."""
        return self._mounted.get(mountpoint)
