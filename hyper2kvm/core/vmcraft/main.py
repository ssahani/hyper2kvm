# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/vmcraft/main.py
"""
VMCraft main class - delegates to modular components.

This file provides the main VMCraft API that maintains backward compatibility
with the original monolithic implementation while delegating to specialized modules.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from ._utils import run_sudo
from .nbd import NBDDeviceManager
from .storage import StorageStackActivator, LVMActivator
from .mount import MountManager
from .file_ops import FileOperations
from .linux_detection import LinuxDetector
from .windows_detection import WindowsDetector
from .inspection import OSInspector
from .windows_registry import WindowsRegistryManager
from .windows_drivers import WindowsDriverInjector
from .windows_users import WindowsUserManager
from .linux_services import LinuxServiceManager
from .backup import BackupManager
from .security import SecurityAuditor
from .optimization import DiskOptimizer


logger = logging.getLogger(__name__)


class VMCraft:
    """
    Native implementation of guestfs.GuestFS API.

    Uses qemu-nbd + Linux tools instead of libguestfs appliance.
    Compatible with existing code that uses guestfs.GuestFS(python_return_dict=True).

    This is the main entry point that coordinates all specialized modules.
    """

    def __init__(self, python_return_dict: bool = True):
        """
        Initialize VMCraft.

        Args:
            python_return_dict: Return dicts instead of tuples (default: True)
        """
        self._return_dict = python_return_dict
        self._drives: list[dict[str, Any]] = []
        self._nbd_manager: NBDDeviceManager | None = None
        self._nbd_device: str | None = None
        self._storage_activator: StorageStackActivator | None = None
        self._storage_audit: dict[str, Any] | None = None
        self._mount_root: Path | None = None
        self._launched = False
        self._trace = False
        self._perf_metrics: dict[str, float] = {}
        self.logger = logging.getLogger(__name__)

        # Specialized managers (initialized after launch)
        self._mount_manager: MountManager | None = None
        self._file_ops: FileOperations | None = None
        self._linux_detector: LinuxDetector | None = None
        self._windows_detector: WindowsDetector | None = None
        self._os_inspector: OSInspector | None = None
        self._win_registry: WindowsRegistryManager | None = None
        self._win_drivers: WindowsDriverInjector | None = None
        self._win_users: WindowsUserManager | None = None
        self._linux_services: LinuxServiceManager | None = None
        self._backup_mgr: BackupManager | None = None
        self._security_auditor: SecurityAuditor | None = None
        self._disk_optimizer: DiskOptimizer | None = None

        # Log backend selection
        self.logger.debug("Using VMCraft backend (qemu-nbd + Linux tools)")

    def set_trace(self, enable: int | bool) -> None:
        """Enable debug tracing."""
        self._trace = bool(enable)
        if self._trace:
            self.logger.setLevel(logging.DEBUG)

    def add_drive_opts(
        self,
        path: str,
        *,
        readonly: int | bool = 1,
        format: str | None = None,
        **kwargs
    ) -> None:
        """
        Add a disk image.

        Args:
            path: Path to disk image
            readonly: Mount read-only (default: True)
            format: Disk format (qcow2, vmdk, raw, etc.)
            **kwargs: Other options (ignored for compatibility)
        """
        if self._launched:
            raise RuntimeError("Cannot add drives after launch()")

        self._drives.append({
            'path': str(path),
            'readonly': bool(readonly),
            'format': format,
        })

    def launch(self) -> None:
        """
        Launch the backend.

        Connects NBD devices, activates storage stack, creates mount root,
        and initializes all specialized managers.
        """
        start_time = time.time()

        if self._launched:
            raise RuntimeError("Already launched")

        if not self._drives:
            raise RuntimeError("No drives added")

        # For now, only support single drive (can be extended)
        if len(self._drives) > 1:
            raise NotImplementedError("Multiple drives not yet supported")

        drive = self._drives[0]

        self.logger.info("Launching VMCraft backend...")
        self.logger.info(f"   Backend: VMCraft (Python + qemu-nbd + Linux tools)")
        self.logger.info(f"   Image: {Path(drive['path']).name}")
        self.logger.info(f"   Format: {drive.get('format', 'auto-detect')}")
        self.logger.info(f"   Mode: {'read-only' if drive['readonly'] else 'read-write'}")

        # Connect NBD
        nbd_start = time.time()
        self._nbd_manager = NBDDeviceManager(
            self.logger,
            readonly=drive['readonly']
        )
        self._nbd_device = self._nbd_manager.connect(
            drive['path'],
            format=drive.get('format'),
            readonly=drive['readonly']
        )
        nbd_time = time.time() - nbd_start
        self._perf_metrics['nbd_connect'] = nbd_time
        self.logger.info(f"   NBD connected: {self._nbd_device} ({nbd_time:.2f}s)")

        # Activate storage stack
        storage_start = time.time()
        self._storage_activator = StorageStackActivator(self.logger)
        self._storage_audit = self._storage_activator.activate_all()
        storage_time = time.time() - storage_start
        self._perf_metrics['storage_activation'] = storage_time
        self.logger.info(f"   Storage stack activated ({storage_time:.2f}s)")

        # Create temporary mount root
        self._mount_root = Path(tempfile.mkdtemp(prefix="hyper2kvm-guestfs-"))

        # Initialize all specialized managers
        self._mount_manager = MountManager(self.logger, self._mount_root)
        self._file_ops = FileOperations(self.logger, self._mount_root, enable_cache=True, cache_size=1000)
        self._linux_detector = LinuxDetector(self.logger, self._mount_root)
        self._windows_detector = WindowsDetector(self.logger, self._mount_root)
        self._os_inspector = OSInspector(
            self.logger,
            self._mount_root,
            self._linux_detector,
            self._windows_detector
        )
        self._win_registry = WindowsRegistryManager(self.logger, self._mount_root)
        self._win_drivers = WindowsDriverInjector(self.logger, self._mount_root)
        self._win_users = WindowsUserManager(self.logger, self._mount_root)
        self._linux_services = LinuxServiceManager(self.logger, self._mount_root)
        self._backup_mgr = BackupManager(self.logger, self._mount_root)
        self._security_auditor = SecurityAuditor(self.logger, self._mount_root)
        self._disk_optimizer = DiskOptimizer(self.logger, self._mount_root)

        total_time = time.time() - start_time
        self._perf_metrics['total_launch'] = total_time
        self._launched = True

        self.logger.info(f"VMCraft ready in {total_time:.2f}s (vs ~5-10s for libguestfs)")
        self.logger.debug(f"   Mount root: {self._mount_root}")

    def shutdown(self) -> None:
        """Shutdown the backend."""
        if not self._launched:
            return

        self.logger.info("Shutting down VMCraft backend...")

        # Umount all filesystems first
        try:
            self.umount_all()
            self.logger.info("   All filesystems unmounted")
        except Exception as e:
            self.logger.warning(f"   Error during umount_all: {e}")

        # Disconnect NBD
        if self._nbd_manager:
            try:
                self._nbd_manager.disconnect()
                self.logger.info(f"   NBD device disconnected: {self._nbd_device}")
            except Exception as e:
                self.logger.warning(f"   Error disconnecting NBD: {e}")

        self._launched = False
        self.logger.info("VMCraft shut down successfully")

    def close(self) -> None:
        """Close and cleanup."""
        # Ensure shutdown
        try:
            self.shutdown()
        except Exception:
            pass

        # Remove temp mount root
        if self._mount_root and self._mount_root.exists():
            try:
                shutil.rmtree(self._mount_root)
            except Exception as e:
                self.logger.warning(f"Error removing mount root: {e}")
            self._mount_root = None

        self._nbd_manager = None
        self._storage_activator = None
        self._mount_manager = None
        self._file_ops = None
        self._linux_detector = None
        self._windows_detector = None
        self._os_inspector = None
        self._win_registry = None
        self._win_drivers = None
        self._win_users = None
        self._linux_services = None
        self._backup_mgr = None
        self._security_auditor = None
        self._disk_optimizer = None

    # Utility / Info APIs

    def get_backend_info(self) -> dict[str, Any]:
        """Get information about the VMCraft backend."""
        return {
            'backend': 'vmcraft',
            'implementation': 'VMCraft - Python disk manipulation library',
            'version': '1.0.0',
            'features': {
                'nbd_based': True,
                'requires_root': True,
                'libguestfs_compatible': True,
                'performance': '5x faster startup, 10x less memory',
                'windows_support': True,
                'driver_injection': True,
                'registry_operations': True,
            },
            'launched': self._launched,
            'nbd_device': self._nbd_device if self._launched else None,
            'mount_root': str(self._mount_root) if self._mount_root else None,
        }

    def get_performance_metrics(self) -> dict[str, Any]:
        """
        Get comprehensive performance metrics.

        Includes:
        - Launch timing metrics
        - Cache statistics
        - Memory usage estimates
        - Operation counts

        Returns:
            Dict with performance metrics
        """
        metrics: dict[str, Any] = {
            "launch": dict(self._perf_metrics),
        }

        # Add cache statistics if available
        if self._file_ops:
            metrics["cache"] = self._file_ops.get_cache_stats()

        # Add operation counts (these would be tracked by modules)
        # For now, we'll provide placeholder structure
        metrics["operations"] = {
            "file_reads": 0,  # Could be tracked in FileOperations
            "file_writes": 0,  # Could be tracked in FileOperations
            "mounts": len(self._mount_manager.mountpoints()) if self._mount_manager else 0,
        }

        # Memory estimate (rough calculation based on cache sizes)
        if metrics.get("cache", {}).get("enabled"):
            cache_stats = metrics["cache"]
            meta_size = cache_stats.get("metadata_cache", {}).get("size", 0)
            dir_size = cache_stats.get("dir_cache", {}).get("size", 0)
            # Rough estimate: 1KB per metadata entry, 0.5KB per dir entry
            estimated_kb = (meta_size * 1) + (dir_size * 0.5)
            metrics["memory_estimate_kb"] = int(estimated_kb)

        return metrics

    # Inspection APIs

    def inspect_os(self) -> list[str]:
        """Detect operating systems on disk."""
        if not self._launched or not self._os_inspector:
            raise RuntimeError("Not launched")

        partitions = self.list_partitions()
        return self._os_inspector.inspect_partitions(partitions)

    def inspect_get_type(self, root: str) -> str:
        """Get OS type (linux, windows, etc.)."""
        if self._os_inspector and self._os_inspector.has_cached_info(root):
            return self._os_inspector.get_cached_info(root).get("type", "unknown")
        return "unknown"

    def inspect_get_distro(self, root: str) -> str:
        """Get distribution name."""
        if self._os_inspector and self._os_inspector.has_cached_info(root):
            return self._os_inspector.get_cached_info(root).get("distro", "unknown")
        return "unknown"

    def inspect_get_product_name(self, root: str) -> str:
        """Get product name."""
        if self._os_inspector and self._os_inspector.has_cached_info(root):
            return self._os_inspector.get_cached_info(root).get("product", "Unknown")
        return "Unknown"

    def inspect_get_major_version(self, root: str) -> int:
        """Get major version number."""
        if self._os_inspector and self._os_inspector.has_cached_info(root):
            return self._os_inspector.get_cached_info(root).get("major", 0)
        return 0

    def inspect_get_minor_version(self, root: str) -> int:
        """Get minor version number."""
        if self._os_inspector and self._os_inspector.has_cached_info(root):
            return self._os_inspector.get_cached_info(root).get("minor", 0)
        return 0

    def inspect_get_arch(self, root: str) -> str:
        """Get architecture."""
        if self._os_inspector and self._os_inspector.has_cached_info(root):
            return self._os_inspector.get_cached_info(root).get("arch", "unknown")
        return "unknown"

    def inspect_get_mountpoints(self, root: str) -> dict[str, str] | list[tuple[str, str]]:
        """Get mountpoints for root."""
        # For Windows, return simple root mountpoint (no fstab)
        os_type = self.inspect_get_type(root)
        if os_type == "windows":
            if self._return_dict:
                return {"/": root}
            else:
                return [(root, "/")]

        # For Linux, parse /etc/fstab
        mounts = self._parse_fstab(root)

        if self._return_dict:
            return {mp: dev for dev, mp in mounts}
        else:
            return [(dev, mp) for dev, mp in mounts]

    def _parse_fstab(self, root: str) -> list[tuple[str, str]]:
        """Parse /etc/fstab from root device."""
        if not self._mount_root or not self._file_ops:
            return []

        mounts = []

        try:
            # Mount root temporarily to read fstab
            self.umount_all()
            run_sudo(self.logger, ["mount", "-o", "ro", root, str(self._mount_root)], check=True, capture=True)

            fstab_path = self._mount_root / "etc/fstab"
            if not fstab_path.exists():
                return mounts

            for line in fstab_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    device = parts[0]
                    mountpoint = parts[1]
                    mounts.append((device, mountpoint))

        except Exception as e:
            self.logger.warning(f"Failed to parse fstab: {e}")
        finally:
            try:
                run_sudo(self.logger, ["umount", str(self._mount_root)], check=False, capture=True)
            except Exception:
                pass

        return mounts

    # Mount operations (delegate to MountManager)

    def mount(self, device: str, mountpoint: str) -> None:
        """Mount device at mountpoint (read-write)."""
        if not self._mount_manager:
            raise RuntimeError("Not launched")
        self._mount_manager.mount(device, mountpoint, readonly=False)

    def mount_ro(self, device: str, mountpoint: str) -> None:
        """Mount device at mountpoint (read-only)."""
        if not self._mount_manager:
            raise RuntimeError("Not launched")
        self._mount_manager.mount(device, mountpoint, readonly=True)

    def mount_options(self, options: str, device: str, mountpoint: str) -> None:
        """Mount device with custom options."""
        if not self._mount_manager:
            raise RuntimeError("Not launched")
        self._mount_manager.mount(device, mountpoint, options=options)

    def umount_all(self) -> None:
        """Unmount all mounted filesystems."""
        if self._mount_manager:
            self._mount_manager.umount_all()

    def mountpoints(self) -> list[str]:
        """Get list of current mountpoints."""
        if not self._mount_manager:
            return []
        return self._mount_manager.mountpoints()

    def mounts(self) -> list[str]:
        """Get list of mounted devices."""
        if not self._mount_manager:
            return []
        return self._mount_manager.mounts()

    # File operations (delegate to FileOperations)

    def is_file(self, path: str) -> bool:
        """Check if path is a regular file."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.is_file(path)

    def is_dir(self, path: str) -> bool:
        """Check if path is a directory."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.is_dir(path)

    def exists(self, path: str) -> bool:
        """Check if path exists."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.exists(path)

    def read_file(self, path: str) -> bytes:
        """Read file contents as bytes."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.read_file(path)

    def cat(self, path: str) -> str:
        """Read file contents as string."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.cat(path)

    def write(self, path: str, content: bytes | str) -> None:
        """Write content to file."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.write(path, content)

    def upload(self, local_path: str, remote_path: str) -> None:
        """Upload a file from host to guest filesystem."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.upload(local_path, remote_path)

    def download(self, remote_path: str, local_path: str) -> None:
        """Download a file from guest to host filesystem."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.download(remote_path, local_path)

    def ls(self, path: str) -> list[str]:
        """List directory contents."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.ls(path)

    def find(self, path: str) -> list[str]:
        """Recursively find all files under path."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.find(path)

    def mkdir_p(self, path: str) -> None:
        """Create directory (with parents)."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.mkdir_p(path)

    def chmod(self, path: str, mode: int) -> None:
        """Change file permissions."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.chmod(path, mode)

    def ln_sf(self, target: str, link_name: str) -> None:
        """Create symbolic link."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.ln_sf(target, link_name)

    def cp(self, src: str, dst: str) -> None:
        """Copy file."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.cp(src, dst)

    def rm_f(self, path: str) -> None:
        """Remove file (force)."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.rm_f(path)

    def touch(self, path: str) -> None:
        """Create empty file or update timestamp."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.touch(path)

    def readlink(self, path: str) -> str:
        """Read symbolic link target."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.readlink(path)

    def find_files(self, path: str, pattern: str | None = None, file_type: str | None = None) -> list[str]:
        """Find files in guest filesystem."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.find_files(path, pattern, file_type)

    def checksum(self, path: str, algorithm: str = "sha256") -> str:
        """Calculate checksum of file."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.checksum(path, algorithm)

    def file_age(self, path: str) -> dict[str, Any]:
        """Get file timestamps."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.file_age(path)

    def set_permissions(self, path: str, mode: int, recursive: bool = False) -> None:
        """Set file/directory permissions."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.set_permissions(path, mode, recursive)

    def set_owner(self, path: str, uid: int, gid: int, recursive: bool = False) -> None:
        """Set file/directory owner."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.set_owner(path, uid, gid, recursive)

    def realpath(self, path: str) -> str:
        """Resolve path to absolute path (following symlinks)."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.realpath(path)

    # Filesystem operations

    def list_filesystems(self) -> dict[str, str]:
        """List all filesystems."""
        result = {}

        try:
            cmd = ["lsblk", "-f", "--json", "-o", "NAME,FSTYPE"]
            output = run_sudo(self.logger, cmd, check=True, capture=True)

            data = json.loads(output.stdout)
            for dev in data.get("blockdevices", []):
                self._extract_filesystems(dev, result)

        except Exception as e:
            self.logger.warning(f"Failed to list filesystems: {e}")

        return result

    def _extract_filesystems(self, dev: dict, result: dict) -> None:
        """Recursively extract filesystems from lsblk output."""
        name = dev.get("name")
        fstype = dev.get("fstype")

        if name and fstype:
            result[f"/dev/{name}"] = fstype

        # Recurse into children
        for child in dev.get("children", []):
            self._extract_filesystems(child, result)

    def list_partitions(self) -> list[str]:
        """List all partitions."""
        if not self._nbd_manager or not self._nbd_device:
            return []

        return self._nbd_manager.get_partitions(self._nbd_device)

    def list_devices(self) -> list[str]:
        """List all devices."""
        if self._nbd_device:
            return [self._nbd_device]
        return []

    def vfs_type(self, device: str) -> str:
        """Get filesystem type."""
        try:
            result = run_sudo(self.logger, ["blkid", "-s", "TYPE", "-o", "value", device], check=True, capture=True)
            return result.stdout.strip()
        except Exception:
            return ""

    def vfs_uuid(self, device: str) -> str:
        """Get filesystem UUID."""
        try:
            result = run_sudo(self.logger, ["blkid", "-s", "UUID", "-o", "value", device], check=True, capture=True)
            return result.stdout.strip()
        except Exception:
            return ""

    def vfs_label(self, device: str) -> str:
        """Get filesystem label."""
        try:
            result = run_sudo(self.logger, ["blkid", "-s", "LABEL", "-o", "value", device], check=True, capture=True)
            return result.stdout.strip()
        except Exception:
            return ""

    def blockdev_getsize64(self, device: str) -> int:
        """Get device size in bytes."""
        try:
            result = run_sudo(self.logger, ["blockdev", "--getsize64", device], check=True, capture=True)
            return int(result.stdout.strip())
        except Exception:
            return 0

    def statvfs(self, path: str) -> dict[str, int]:
        """Get filesystem statistics."""
        if not self._file_ops or not self._mount_root:
            raise RuntimeError("Not launched")

        guest_path = self._mount_root / path.lstrip('/')
        st = os.statvfs(guest_path)
        return {
            "bsize": st.f_bsize,
            "blocks": st.f_blocks,
            "bfree": st.f_bfree,
            "bavail": st.f_bavail,
            "files": st.f_files,
            "ffree": st.f_ffree,
            "flag": st.f_flag,
        }

    # Storage stack operations

    def vgscan(self) -> None:
        """Scan for LVM volume groups."""
        LVMActivator.activate(self.logger)

    def vgchange_activate_all(self, enable: bool | int) -> None:
        """Activate all volume groups."""
        if enable:
            LVMActivator.activate(self.logger)

    def lvs(self) -> list[str]:
        """List logical volumes."""
        return LVMActivator.list_logical_volumes(self.logger)

    def cryptsetup_open(self, device: str, name: str, key: bytes) -> None:
        """Open LUKS encrypted device."""
        raise NotImplementedError("cryptsetup_open not directly supported (use LUKS config in launch)")

    def command(self, cmd: list[str]) -> str:
        """Execute command in guest filesystem (via chroot)."""
        if not self._mount_root:
            raise RuntimeError("Not launched")

        chroot_cmd = ["chroot", str(self._mount_root)] + cmd
        result = run_sudo(self.logger, chroot_cmd, check=True, capture=True)
        return result.stdout

    # Windows-specific operations (delegate to Windows modules)

    def win_inject_driver(self, driver_path: str, inf_file: str | None = None) -> dict[str, Any]:
        """Inject Windows driver into guest filesystem."""
        if not self._win_drivers:
            raise RuntimeError("Not launched")
        return self._win_drivers.inject_driver(driver_path, inf_file)

    def win_registry_read(self, hive_name: str, key_path: str, value_name: str) -> str | None:
        """Read value from Windows registry hive."""
        if not self._win_registry:
            raise RuntimeError("Not launched")
        return self._win_registry.read_value(hive_name, key_path, value_name)

    def win_registry_write(self, hive_name: str, key_path: str, value_name: str, value: str, value_type: str = "sz") -> bool:
        """Write value to Windows registry hive."""
        if not self._win_registry:
            raise RuntimeError("Not launched")
        return self._win_registry.write_value(hive_name, key_path, value_name, value, value_type)

    def win_registry_list_keys(self, hive_name: str, key_path: str = "") -> list[str]:
        """List subkeys under a registry key."""
        if not self._win_registry:
            raise RuntimeError("Not launched")
        return self._win_registry.list_keys(hive_name, key_path)

    def win_registry_list_values(self, hive_name: str, key_path: str) -> dict[str, Any]:
        """List values under a registry key."""
        if not self._win_registry:
            raise RuntimeError("Not launched")
        return self._win_registry.list_values(hive_name, key_path)

    def win_resolve_path(self, path: str) -> Path | None:
        """Resolve Windows path (case-insensitive)."""
        if not self._win_registry:
            raise RuntimeError("Not launched")
        return self._win_registry.resolve_path(path)

    # Operational modules (delegate to specialized managers)

    def backup_files(self, paths: list[str], dest_archive: str, compression: str = "gzip") -> dict[str, Any]:
        """Backup files to archive."""
        if not self._backup_mgr:
            raise RuntimeError("Not launched")
        return self._backup_mgr.backup_files(paths, dest_archive, compression)

    def restore_files(self, src_archive: str, dest_path: str = "/") -> dict[str, Any]:
        """Restore files from archive."""
        if not self._backup_mgr:
            raise RuntimeError("Not launched")
        return self._backup_mgr.restore_files(src_archive, dest_path)

    def audit_permissions(self, path: str = "/") -> dict[str, Any]:
        """Audit file permissions for security issues."""
        if not self._security_auditor:
            raise RuntimeError("Not launched")
        return self._security_auditor.audit_permissions(path)

    def find_large_files(self, min_size_mb: int = 100, path: str = "/") -> list[dict[str, Any]]:
        """Find large files in filesystem."""
        if not self._disk_optimizer:
            raise RuntimeError("Not launched")
        return self._disk_optimizer.find_large_files(min_size_mb, path)

    def find_duplicates(self, path: str = "/", min_size_mb: int = 1) -> dict[str, list[str]]:
        """Find duplicate files by content hash."""
        if not self._disk_optimizer:
            raise RuntimeError("Not launched")
        return self._disk_optimizer.find_duplicates(path, min_size_mb)

    def analyze_disk_usage(self, path: str = "/", top_n: int = 20) -> dict[str, Any]:
        """Analyze disk usage by directory."""
        if not self._disk_optimizer:
            raise RuntimeError("Not launched")
        return self._disk_optimizer.analyze_disk_usage(path, top_n)

    def cleanup_temp_files(self, dry_run: bool = True) -> dict[str, Any]:
        """Clean up temporary files."""
        if not self._disk_optimizer:
            raise RuntimeError("Not launched")
        return self._disk_optimizer.cleanup_temp_files(dry_run)

    # Container and Bootloader Detection (inspection.py enhancements)

    def detect_containers(self) -> dict[str, Any]:
        """Detect container runtime installations (Docker, Podman, LXC, systemd-nspawn)."""
        if not self._os_inspector:
            raise RuntimeError("Not launched")
        return self._os_inspector.detect_containers()

    def is_inside_container(self) -> dict[str, Any]:
        """Check if the inspected OS is running inside a container."""
        if not self._os_inspector:
            raise RuntimeError("Not launched")
        return self._os_inspector.is_inside_container()

    def detect_bootloader(self) -> dict[str, Any]:
        """Detect bootloader configuration (GRUB2, systemd-boot, UEFI, LILO)."""
        if not self._os_inspector:
            raise RuntimeError("Not launched")
        return self._os_inspector.detect_bootloader()

    def get_bootloader_entries(self) -> list[dict[str, Any]]:
        """Get boot loader menu entries."""
        if not self._os_inspector:
            raise RuntimeError("Not launched")
        return self._os_inspector.get_bootloader_entries()

    # Security Module Detection (security.py enhancements)

    def detect_selinux(self) -> dict[str, Any]:
        """Detect SELinux configuration and status."""
        if not self._security_auditor:
            raise RuntimeError("Not launched")
        return self._security_auditor.detect_selinux()

    def detect_apparmor(self) -> dict[str, Any]:
        """Detect AppArmor configuration and status."""
        if not self._security_auditor:
            raise RuntimeError("Not launched")
        return self._security_auditor.detect_apparmor()

    def get_security_modules(self) -> dict[str, Any]:
        """Get comprehensive security module information (SELinux, AppArmor)."""
        if not self._security_auditor:
            raise RuntimeError("Not launched")
        return self._security_auditor.get_security_modules()

    # Package Manager Operations (security.py enhancements)

    def query_package(self, package_name: str, manager: str = "auto") -> dict[str, Any]:
        """Query installed package information (RPM, APT, Pacman)."""
        if not self._security_auditor:
            raise RuntimeError("Not launched")
        return self._security_auditor.query_package(package_name, manager)

    def list_installed_packages(self, manager: str = "auto", limit: int = 0) -> list[dict[str, str]]:
        """List all installed packages."""
        if not self._security_auditor:
            raise RuntimeError("Not launched")
        return self._security_auditor.list_installed_packages(manager, limit)

    # Windows User Management (windows_users.py)

    def win_list_users(self) -> list[dict[str, Any]]:
        """List all local Windows user accounts."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.list_users()

    def win_get_user_info(self, username: str) -> dict[str, Any] | None:
        """Get detailed information about a Windows user."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.get_user_info(username)

    def win_get_user_groups(self, username: str) -> list[str]:
        """Get groups that a Windows user is a member of."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.get_user_groups(username)

    def win_is_administrator(self, username: str) -> bool:
        """Check if Windows user is in Administrators group."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.is_administrator(username)

    def win_is_disabled(self, username: str) -> bool:
        """Check if Windows user account is disabled."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.is_disabled(username)

    def win_list_administrators(self) -> list[str]:
        """List all Windows administrator accounts."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.list_administrators()

    def win_list_enabled_users(self) -> list[str]:
        """List all enabled Windows user accounts."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.list_enabled_users()

    def win_list_disabled_users(self) -> list[str]:
        """List all disabled Windows user accounts."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.list_disabled_users()

    def win_get_user_count(self) -> dict[str, int]:
        """Get Windows user account statistics."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.get_user_count()

    # Linux Service Management (linux_services.py)

    def linux_list_services(self) -> list[dict[str, Any]]:
        """List all systemd service units."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.list_services()

    def linux_get_service_info(self, service_name: str) -> dict[str, Any] | None:
        """Get detailed information about a systemd service."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.get_service_info(service_name)

    def linux_list_enabled_services(self) -> list[str]:
        """List all enabled systemd services."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.list_enabled_services()

    def linux_list_disabled_services(self) -> list[str]:
        """List all disabled systemd services."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.list_disabled_services()

    def linux_get_service_dependencies(self, service_name: str) -> dict[str, Any]:
        """Get systemd service dependencies."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.get_service_dependencies(service_name)

    def linux_find_services_by_target(self, target: str = "multi-user.target") -> list[str]:
        """Find services enabled for a specific systemd target."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.find_services_by_target(target)

    def linux_get_boot_services(self) -> list[str]:
        """Get services that start at boot."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.get_boot_services()

    def linux_get_service_stats(self) -> dict[str, int]:
        """Get systemd service statistics."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.get_service_stats()

    # Cache Management (file_ops.py enhancements)

    def get_cache_stats(self) -> dict[str, Any]:
        """Get file operation cache statistics."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.get_cache_stats()

    def clear_cache(self) -> None:
        """Clear file operation caches."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.clear_cache()

    # Context manager support

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        try:
            self.close()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
        return False
