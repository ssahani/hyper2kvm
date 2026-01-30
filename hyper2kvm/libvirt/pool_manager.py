# SPDX-License-Identifier: LGPL-3.0-or-later
"""Libvirt storage pool management for disk import operations.

This module provides high-level storage pool operations for hyper2kvm,
enabling automatic disk import to libvirt pools after VM conversion.

Capabilities:
- Create and manage storage pools
- Import converted disks to pools
- Volume operations (create, delete, clone)
- Pool discovery and validation
- Automatic pool refresh

Security:
- Validates pool paths before creation
- Safe volume name sanitization
- Proper permission handling
- Resource cleanup
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from ..core.utils import U
from .libvirt_utils import sanitize_name

try:
    import libvirt  # type: ignore

    LIBVIRT_AVAILABLE = True
except ImportError:
    libvirt = None  # type: ignore
    LIBVIRT_AVAILABLE = False


class PoolManagerError(Exception):
    """Errors raised during storage pool management operations."""

    pass


class PoolManager:
    """
    Manage libvirt storage pools and volumes.

    This class provides a high-level interface to libvirt storage pools
    for disk import and management tasks after VM conversion.

    Example:
        >>> manager = PoolManager(logger)
        >>> pool = manager.ensure_pool("vms", "/var/lib/libvirt/images")
        >>> manager.import_disk(pool, "/converted/disk.qcow2", "vm-disk-boot")
    """

    def __init__(
        self,
        logger: logging.Logger | None = None,
        uri: str = "qemu:///system",
    ):
        """
        Initialize PoolManager.

        Args:
            logger: Logger instance for operations
            uri: Libvirt connection URI (default: qemu:///system)

        Raises:
            PoolManagerError: If libvirt is not available
        """
        if not LIBVIRT_AVAILABLE:
            raise PoolManagerError(
                "libvirt Python bindings not available. "
                "Install with: pip install libvirt-python"
            )

        self.logger = logger or logging.getLogger(__name__)
        self.uri = uri
        self.conn: Any = None

    def connect(self) -> None:
        """
        Establish connection to libvirt daemon.

        Raises:
            PoolManagerError: If connection fails
        """
        if self.conn is not None:
            return  # Already connected

        try:
            self.conn = libvirt.open(self.uri)
            if self.conn is None:
                raise PoolManagerError(f"Failed to connect to libvirt at {self.uri}")

            self.logger.info(f"Connected to libvirt: {self.uri}")

        except libvirt.libvirtError as e:
            raise PoolManagerError(f"Libvirt connection failed: {e}") from e

    def disconnect(self) -> None:
        """Close libvirt connection and cleanup resources."""
        if self.conn is not None:
            try:
                self.conn.close()
                self.logger.info("Disconnected from libvirt")
            except Exception as e:
                self.logger.warning(f"Error closing libvirt connection: {e}")
            finally:
                self.conn = None

    def __enter__(self) -> PoolManager:
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()

    def pool_exists(self, name: str) -> bool:
        """
        Check if storage pool with given name exists.

        Args:
            name: Pool name to check

        Returns:
            True if pool exists, False otherwise
        """
        if self.conn is None:
            self.connect()

        try:
            self.conn.storagePoolLookupByName(name)
            return True
        except libvirt.libvirtError:
            return False

    def get_pool(self, name: str) -> Any:
        """
        Get storage pool by name.

        Args:
            name: Pool name

        Returns:
            libvirt storage pool object

        Raises:
            PoolManagerError: If pool not found
        """
        if self.conn is None:
            self.connect()

        try:
            pool = self.conn.storagePoolLookupByName(name)
            if pool is None:
                raise PoolManagerError(f"Pool '{name}' not found")
            return pool

        except libvirt.libvirtError as e:
            raise PoolManagerError(f"Failed to get pool '{name}': {e}") from e

    def create_pool(
        self,
        name: str,
        path: Path | str,
        *,
        pool_type: str = "dir",
        autostart: bool = True,
    ) -> Any:
        """
        Create a new storage pool.

        Args:
            name: Pool name
            path: Path to pool directory
            pool_type: Pool type (default: "dir" for directory-based)
            autostart: Enable autostart on host boot

        Returns:
            libvirt storage pool object

        Raises:
            PoolManagerError: If pool creation fails
        """
        if self.conn is None:
            self.connect()

        path = Path(path).resolve()

        # Validate path
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Created pool directory: {path}")
            except Exception as e:
                raise PoolManagerError(f"Failed to create pool directory {path}: {e}") from e

        # Check if pool already exists
        if self.pool_exists(name):
            raise PoolManagerError(f"Pool '{name}' already exists")

        # Build pool XML
        pool_xml = f"""<pool type='{pool_type}'>
  <name>{name}</name>
  <target>
    <path>{path}</path>
  </target>
</pool>"""

        # Define and start pool
        try:
            pool = self.conn.storagePoolDefineXML(pool_xml, 0)
            if pool is None:
                raise PoolManagerError(f"Failed to define pool '{name}'")

            pool.create(0)
            self.logger.info(f"Created storage pool: {name}")

            if autostart:
                pool.setAutostart(1)
                self.logger.info(f"Enabled autostart for pool: {name}")

            return pool

        except libvirt.libvirtError as e:
            raise PoolManagerError(f"Failed to create pool '{name}': {e}") from e

    def ensure_pool(
        self,
        name: str,
        path: Path | str,
        *,
        autostart: bool = True,
    ) -> Any:
        """
        Ensure pool exists, creating if necessary.

        Args:
            name: Pool name
            path: Path to pool directory
            autostart: Enable autostart if creating new pool

        Returns:
            libvirt storage pool object
        """
        if self.pool_exists(name):
            pool = self.get_pool(name)
            # Ensure pool is active
            if not pool.isActive():
                pool.create(0)
                self.logger.info(f"Started existing pool: {name}")
            return pool
        else:
            return self.create_pool(name, path, autostart=autostart)

    def import_disk(
        self,
        pool_or_name: Any | str,
        disk_path: Path | str,
        volume_name: str | None = None,
        *,
        copy: bool = True,
        overwrite: bool = False,
    ) -> str:
        """
        Import a disk into a storage pool.

        Args:
            pool_or_name: Pool object or name string
            disk_path: Path to disk file to import
            volume_name: Name for volume (default: sanitized disk filename)
            copy: If True, copy disk; if False, move disk
            overwrite: If True, overwrite existing volume

        Returns:
            Path to volume in pool

        Raises:
            PoolManagerError: If import fails
        """
        if self.conn is None:
            self.connect()

        # Get pool object
        if isinstance(pool_or_name, str):
            pool = self.get_pool(pool_or_name)
        else:
            pool = pool_or_name

        pool_name = pool.name()

        # Validate source disk
        disk_path = Path(disk_path).resolve()
        if not disk_path.exists():
            raise PoolManagerError(f"Disk not found: {disk_path}")

        if not disk_path.is_file():
            raise PoolManagerError(f"Disk is not a file: {disk_path}")

        # Determine volume name
        if volume_name is None:
            volume_name = sanitize_name(disk_path.stem)

        # Get pool path
        pool_xml = pool.XMLDesc(0)
        import xml.etree.ElementTree as ET

        root = ET.fromstring(pool_xml)
        target = root.find("target/path")
        if target is None or not target.text:
            raise PoolManagerError(f"Failed to get path for pool '{pool_name}'")

        pool_path = Path(target.text)
        dest_path = pool_path / f"{volume_name}{disk_path.suffix}"

        # Check if volume already exists
        if dest_path.exists():
            if overwrite:
                self.logger.warning(f"Volume exists, overwriting: {dest_path}")
                dest_path.unlink()
            else:
                raise PoolManagerError(
                    f"Volume '{volume_name}' already exists in pool '{pool_name}' "
                    f"(use overwrite=True to replace)"
                )

        # Copy or move disk
        try:
            if copy:
                shutil.copy2(disk_path, dest_path)
                self.logger.info(f"Copied disk to pool: {disk_path} → {dest_path}")
            else:
                shutil.move(str(disk_path), dest_path)
                self.logger.info(f"Moved disk to pool: {disk_path} → {dest_path}")

            # Refresh pool to detect new volume
            pool.refresh(0)
            self.logger.info(f"✅ Imported disk '{volume_name}' to pool '{pool_name}'")

            return str(dest_path)

        except Exception as e:
            raise PoolManagerError(
                f"Failed to import disk to pool '{pool_name}': {e}"
            ) from e

    def list_volumes(self, pool_or_name: Any | str) -> list[str]:
        """
        List all volumes in a pool.

        Args:
            pool_or_name: Pool object or name string

        Returns:
            List of volume names

        Raises:
            PoolManagerError: If listing fails
        """
        if self.conn is None:
            self.connect()

        # Get pool object
        if isinstance(pool_or_name, str):
            pool = self.get_pool(pool_or_name)
        else:
            pool = pool_or_name

        try:
            pool.refresh(0)  # Refresh to ensure up-to-date list
            volumes = pool.listVolumes()
            return volumes

        except libvirt.libvirtError as e:
            raise PoolManagerError(f"Failed to list volumes: {e}") from e

    def delete_pool(
        self,
        pool_or_name: Any | str,
        *,
        delete_volumes: bool = False,
    ) -> None:
        """
        Delete a storage pool.

        Args:
            pool_or_name: Pool object or name string
            delete_volumes: If True, also delete all volumes in pool

        Raises:
            PoolManagerError: If deletion fails
        """
        if self.conn is None:
            self.connect()

        # Get pool object
        if isinstance(pool_or_name, str):
            pool = self.get_pool(pool_or_name)
        else:
            pool = pool_or_name

        pool_name = pool.name()

        try:
            # Stop pool if active
            if pool.isActive():
                pool.destroy()
                self.logger.info(f"Stopped pool: {pool_name}")

            # Delete volumes if requested
            if delete_volumes:
                pool.delete(0)
                self.logger.info(f"Deleted volumes in pool: {pool_name}")

            # Undefine pool
            pool.undefine()
            self.logger.info(f"Deleted pool: {pool_name}")

        except libvirt.libvirtError as e:
            raise PoolManagerError(f"Failed to delete pool '{pool_name}': {e}") from e


__all__ = [
    "PoolManager",
    "PoolManagerError",
    "LIBVIRT_AVAILABLE",
]
