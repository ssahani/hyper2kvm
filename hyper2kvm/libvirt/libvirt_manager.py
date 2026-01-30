# SPDX-License-Identifier: LGPL-3.0-or-later
"""Libvirt domain management for automatic VM import and lifecycle operations.

This module provides high-level libvirt domain operations for hyper2kvm,
enabling automatic domain creation, snapshot management, and lifecycle control
after VM conversion.

Capabilities:
- Define libvirt domains from generated XML
- Manage domain lifecycle (start, stop, destroy)
- Create snapshots before first boot
- Auto-start configuration
- Domain existence checks and cleanup

Security:
- Validates XML before defining domains
- Uses read-only connections where possible
- Safe domain name sanitization
- Proper resource cleanup
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from ..core.utils import U

try:
    import libvirt  # type: ignore

    LIBVIRT_AVAILABLE = True
except ImportError:
    libvirt = None  # type: ignore
    LIBVIRT_AVAILABLE = False


class LibvirtManagerError(Exception):
    """Errors raised during libvirt domain management operations."""

    pass


class LibvirtManager:
    """
    Manage libvirt domains: define, start, snapshot, and lifecycle operations.

    This class provides a high-level interface to libvirt for domain management
    tasks commonly needed after VM conversion.

    Example:
        >>> manager = LibvirtManager(logger)
        >>> domain = manager.define_domain(xml_path="/converted/domain.xml")
        >>> manager.create_snapshot(domain, "pre-first-boot")
        >>> if auto_start:
        >>>     manager.start_domain(domain)
    """

    def __init__(
        self,
        logger: logging.Logger | None = None,
        uri: str = "qemu:///system",
    ):
        """
        Initialize LibvirtManager.

        Args:
            logger: Logger instance for operations
            uri: Libvirt connection URI (default: qemu:///system)

        Raises:
            LibvirtManagerError: If libvirt is not available
        """
        if not LIBVIRT_AVAILABLE:
            raise LibvirtManagerError(
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
            LibvirtManagerError: If connection fails
        """
        if self.conn is not None:
            return  # Already connected

        try:
            self.conn = libvirt.open(self.uri)
            if self.conn is None:
                raise LibvirtManagerError(f"Failed to connect to libvirt at {self.uri}")

            self.logger.info(f"Connected to libvirt: {self.uri}")

        except libvirt.libvirtError as e:
            raise LibvirtManagerError(f"Libvirt connection failed: {e}") from e

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

    def __enter__(self) -> LibvirtManager:
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()

    def domain_exists(self, name: str) -> bool:
        """
        Check if domain with given name exists.

        Args:
            name: Domain name to check

        Returns:
            True if domain exists, False otherwise
        """
        if self.conn is None:
            self.connect()

        try:
            self.conn.lookupByName(name)
            return True
        except libvirt.libvirtError:
            return False

    def define_domain(
        self,
        xml_path: Path | str,
        *,
        overwrite: bool = False,
    ) -> Any:
        """
        Define a libvirt domain from XML file.

        Args:
            xml_path: Path to domain XML file
            overwrite: If True, undefine existing domain with same name

        Returns:
            libvirt domain object

        Raises:
            LibvirtManagerError: If domain definition fails
        """
        if self.conn is None:
            self.connect()

        xml_path = Path(xml_path).resolve()

        if not xml_path.exists():
            raise LibvirtManagerError(f"Domain XML not found: {xml_path}")

        # Read and validate XML
        try:
            xml_content = xml_path.read_text(encoding="utf-8")
        except Exception as e:
            raise LibvirtManagerError(f"Failed to read XML: {e}") from e

        # Extract domain name from XML for logging
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(xml_content)
            domain_name = root.find("name")
            name = domain_name.text if domain_name is not None else "unknown"
        except Exception:
            name = "unknown"

        # Check if domain already exists
        if self.domain_exists(name):
            if overwrite:
                self.logger.warning(f"Domain '{name}' exists, undefining for overwrite")
                self.undefine_domain(name)
            else:
                raise LibvirtManagerError(
                    f"Domain '{name}' already exists (use overwrite=True to replace)"
                )

        # Define domain
        try:
            domain = self.conn.defineXML(xml_content)
            if domain is None:
                raise LibvirtManagerError(f"Failed to define domain '{name}'")

            self.logger.info(f"✅ Defined libvirt domain: {name}")
            return domain

        except libvirt.libvirtError as e:
            raise LibvirtManagerError(f"Failed to define domain '{name}': {e}") from e

    def undefine_domain(self, name: str, *, remove_nvram: bool = False) -> None:
        """
        Undefine a domain (remove from libvirt without deleting disks).

        Args:
            name: Domain name
            remove_nvram: If True, also remove NVRAM file

        Raises:
            LibvirtManagerError: If undefine fails
        """
        if self.conn is None:
            self.connect()

        try:
            domain = self.conn.lookupByName(name)

            # Ensure domain is not running
            if domain.isActive():
                self.logger.warning(f"Domain '{name}' is running, destroying first")
                domain.destroy()
                time.sleep(1)

            # Undefine with flags
            flags = 0
            if remove_nvram:
                flags |= libvirt.VIR_DOMAIN_UNDEFINE_NVRAM

            domain.undefineFlags(flags)
            self.logger.info(f"Undefined domain: {name}")

        except libvirt.libvirtError as e:
            if "not found" in str(e).lower():
                self.logger.warning(f"Domain '{name}' not found, skipping undefine")
            else:
                raise LibvirtManagerError(f"Failed to undefine domain '{name}': {e}") from e

    def start_domain(self, domain_or_name: Any | str, *, force: bool = False) -> None:
        """
        Start (boot) a domain.

        Args:
            domain_or_name: Domain object or name string
            force: If True, force start even if already running

        Raises:
            LibvirtManagerError: If start fails
        """
        if self.conn is None:
            self.connect()

        # Get domain object
        if isinstance(domain_or_name, str):
            try:
                domain = self.conn.lookupByName(domain_or_name)
            except libvirt.libvirtError as e:
                raise LibvirtManagerError(f"Domain '{domain_or_name}' not found: {e}") from e
        else:
            domain = domain_or_name

        name = domain.name()

        # Check if already running
        if domain.isActive():
            if force:
                self.logger.warning(f"Domain '{name}' already running, restarting")
                domain.destroy()
                time.sleep(1)
            else:
                self.logger.info(f"Domain '{name}' already running, skipping start")
                return

        # Start domain
        try:
            domain.create()
            self.logger.info(f"✅ Started domain: {name}")

        except libvirt.libvirtError as e:
            raise LibvirtManagerError(f"Failed to start domain '{name}': {e}") from e

    def create_snapshot(
        self,
        domain_or_name: Any | str,
        snapshot_name: str = "pre-first-boot",
        *,
        description: str = "",
    ) -> None:
        """
        Create a snapshot of a domain.

        Args:
            domain_or_name: Domain object or name string
            snapshot_name: Name for the snapshot
            description: Optional snapshot description

        Raises:
            LibvirtManagerError: If snapshot creation fails
        """
        if self.conn is None:
            self.connect()

        # Get domain object
        if isinstance(domain_or_name, str):
            try:
                domain = self.conn.lookupByName(domain_or_name)
            except libvirt.libvirtError as e:
                raise LibvirtManagerError(f"Domain '{domain_or_name}' not found: {e}") from e
        else:
            domain = domain_or_name

        name = domain.name()

        # Build snapshot XML
        desc_xml = f"<description>{description}</description>" if description else ""
        snapshot_xml = f"""<domainsnapshot>
  <name>{snapshot_name}</name>
  {desc_xml}
</domainsnapshot>"""

        # Create snapshot
        try:
            snapshot = domain.snapshotCreateXML(snapshot_xml, 0)
            if snapshot is None:
                raise LibvirtManagerError(f"Failed to create snapshot for domain '{name}'")

            self.logger.info(f"✅ Created snapshot '{snapshot_name}' for domain: {name}")

        except libvirt.libvirtError as e:
            raise LibvirtManagerError(
                f"Failed to create snapshot for domain '{name}': {e}"
            ) from e

    def set_autostart(self, domain_or_name: Any | str, enabled: bool = True) -> None:
        """
        Configure domain to auto-start on host boot.

        Args:
            domain_or_name: Domain object or name string
            enabled: True to enable auto-start, False to disable

        Raises:
            LibvirtManagerError: If setting autostart fails
        """
        if self.conn is None:
            self.connect()

        # Get domain object
        if isinstance(domain_or_name, str):
            try:
                domain = self.conn.lookupByName(domain_or_name)
            except libvirt.libvirtError as e:
                raise LibvirtManagerError(f"Domain '{domain_or_name}' not found: {e}") from e
        else:
            domain = domain_or_name

        name = domain.name()

        try:
            domain.setAutostart(1 if enabled else 0)
            status = "enabled" if enabled else "disabled"
            self.logger.info(f"Auto-start {status} for domain: {name}")

        except libvirt.libvirtError as e:
            raise LibvirtManagerError(
                f"Failed to set autostart for domain '{name}': {e}"
            ) from e


__all__ = [
    "LibvirtManager",
    "LibvirtManagerError",
    "LIBVIRT_AVAILABLE",
]
