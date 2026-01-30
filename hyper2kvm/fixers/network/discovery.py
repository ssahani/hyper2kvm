# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/network/discovery.py
"""
Network configuration file discovery and I/O operations.

This module handles finding network configuration files on guest filesystems
and performing safe file operations (reading, writing, backing up).

Supports multiple network backend formats:
- RHEL/CentOS ifcfg-rh
- Ubuntu/Debian netplan
- Debian interfaces
- systemd-networkd
- NetworkManager
- SUSE wicked
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...

from ...core.utils import U, guest_ls_glob
from .model import NetworkConfig, NetworkConfigType

# Network configuration file patterns for different backends
CONFIG_PATTERNS = {
    NetworkConfigType.IFCFG_RH: [
        "/etc/sysconfig/network-scripts/ifcfg-*",
        "/etc/sysconfig/network/ifcfg-*",
    ],
    NetworkConfigType.NETPLAN: [
        "/etc/netplan/*.yaml",
        "/etc/netplan/*.yml",
    ],
    NetworkConfigType.INTERFACES: [
        "/etc/network/interfaces",
        "/etc/network/interfaces.d/*",
    ],
    NetworkConfigType.SYSTEMD_NETWORK: [
        "/etc/systemd/network/*.network",
    ],
    NetworkConfigType.SYSTEMD_NETDEV: [
        "/etc/systemd/network/*.netdev",
    ],
    NetworkConfigType.NETWORK_MANAGER: [
        "/etc/NetworkManager/system-connections/*.nmconnection",
        "/etc/NetworkManager/system-connections/*",
    ],
    NetworkConfigType.WICKED: [
        "/etc/wicked/ifconfig/*.xml",
        "/etc/wicked/ifconfig/*",
    ],
    NetworkConfigType.WICKED_IFCFG: [
        "/etc/sysconfig/network/ifcfg-*",
    ],
}


class NetworkDiscovery:
    """
    Network configuration file discovery and I/O operations.

    Provides methods for:
    - Finding network config files on guest filesystem
    - Reading/writing config files safely
    - Creating backups
    - Content hashing for change detection
    """

    def __init__(self, logger: logging.Logger, backup_suffix: str):
        """
        Initialize network discovery.

        Args:
            logger: Logger instance
            backup_suffix: Suffix to append to backup files
        """
        self.logger = logger
        self.backup_suffix = backup_suffix

    # Safe file I/O operations

    def _get_mode_safe(self, g: guestfs.GuestFS, path: str) -> int | None:
        """
        Get file mode (permissions) safely.

        Args:
            g: GuestFS handle
            path: Path to file

        Returns:
            File mode as integer, or None if unable to determine
        """
        try:
            st = g.stat(path)
            mode = int(st.get("mode", 0)) & 0o7777
            return mode if mode else None
        except Exception:
            return None

    def _chmod_safe(self, g: guestfs.GuestFS, path: str, mode: int) -> None:
        """
        Change file mode safely (no exception on failure).

        Args:
            g: GuestFS handle
            path: Path to file
            mode: New mode to set
        """
        try:
            g.chmod(mode, path)
        except Exception as e:
            self.logger.debug("chmod(%s) failed for %s: %s", oct(mode), path, e)

    def _write_atomic(self, g: guestfs.GuestFS, path: str, data: bytes) -> None:
        """
        Write file atomically using temp file.

        Args:
            g: GuestFS handle
            path: Destination path
            data: Data to write
        """
        tmp = f"{path}.tmp.hyper2kvm"
        try:
            g.write(tmp, data)
            g.rename(tmp, path)
        except Exception:
            try:
                if g.exists(tmp):
                    g.rm_f(tmp)
            except Exception:
                pass
            g.write(path, data)

    def write_with_mode(
        self,
        g: guestfs.GuestFS,
        path: str,
        content: str,
        *,
        prefer_mode: int | None = None,
    ) -> None:
        """
        Write file content while preserving mode.

        Args:
            g: GuestFS handle
            path: File path
            content: Content to write
            prefer_mode: Fallback mode if original mode unknown
        """
        old_mode = self._get_mode_safe(g, path)
        self._write_atomic(g, path, content.encode("utf-8"))
        if old_mode is not None:
            self._chmod_safe(g, path, old_mode)
        elif prefer_mode is not None:
            self._chmod_safe(g, path, prefer_mode)

    # Configuration type detection

    def detect_config_type(self, path: str) -> NetworkConfigType:
        """
        Detect network configuration type from file path.

        Args:
            path: File path

        Returns:
            NetworkConfigType enum value
        """
        if "/etc/sysconfig/network-scripts/ifcfg-" in path:
            return NetworkConfigType.IFCFG_RH
        if "/etc/netplan/" in path and (path.endswith(".yaml") or path.endswith(".yml")):
            return NetworkConfigType.NETPLAN
        if "/etc/network/interfaces" in path:
            return NetworkConfigType.INTERFACES
        if "/etc/systemd/network/" in path:
            if path.endswith(".network"):
                return NetworkConfigType.SYSTEMD_NETWORK
            if path.endswith(".netdev"):
                return NetworkConfigType.SYSTEMD_NETDEV
        if "/etc/NetworkManager/system-connections/" in path:
            return NetworkConfigType.NETWORK_MANAGER
        if "/etc/wicked/" in path:
            return NetworkConfigType.WICKED
        if "/etc/sysconfig/network/ifcfg-" in path:
            return NetworkConfigType.WICKED_IFCFG
        return NetworkConfigType.UNKNOWN

    def _should_skip_path(self, path: str) -> bool:
        """
        Check if path should be skipped (backup, temp, loopback).

        Args:
            path: File path

        Returns:
            True if should skip
        """
        p = path or ""
        if self.backup_suffix and self.backup_suffix in p:
            return True
        if re.search(r"(\.bak|~|\.orig|\.rpmnew|\.rpmsave)$", p):
            return True
        base = p.split("/")[-1]
        if base in ("ifcfg-lo", "ifcfg-bonding_masters"):
            return True
        return False

    # Backup and hashing

    def create_backup(
        self,
        g: guestfs.GuestFS,
        path: str,
        content: str,
        *,
        suffix: str | None = None,
    ) -> str:
        """
        Create backup of file before modifying.

        Args:
            g: GuestFS handle
            path: Original file path
            content: File content (fallback if copy fails)
            suffix: Optional custom suffix (defaults to self.backup_suffix)

        Returns:
            Backup file path, or empty string on failure
        """
        backup_suffix = suffix if suffix is not None else self.backup_suffix
        backup_path = f"{path}{backup_suffix}"
        try:
            if hasattr(g, "cp_a"):
                try:
                    g.cp_a(path, backup_path)
                    self.logger.debug("Backup (cp_a): %s", backup_path)
                    return backup_path
                except Exception:
                    pass

            try:
                g.copy_file_to_file(path, backup_path)
                self.logger.debug("Backup (copy_file_to_file): %s", backup_path)
                return backup_path
            except Exception:
                pass

            g.write(backup_path, content.encode("utf-8"))
            self.logger.debug("Backup (write): %s", backup_path)
            return backup_path
        except Exception as e:
            self.logger.warning("Failed to create backup for %s: %s", path, e)
            return ""

    def calculate_hash(self, content: str) -> str:
        """
        Calculate hash of content for change detection.

        Args:
            content: File content

        Returns:
            First 12 characters of SHA256 hash
        """
        h = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
        return h[:12]

    # Configuration file discovery

    def read_config_file(self, g: guestfs.GuestFS, path: str) -> NetworkConfig | None:
        """
        Read and parse network configuration file.

        Args:
            g: GuestFS handle
            path: File path

        Returns:
            NetworkConfig object, or None on error
        """
        try:
            if not g.is_file(path):
                return None
            content_bytes = g.read_file(path)
            content = U.to_text(content_bytes)
            config_type = self.detect_config_type(path)
            content_hash = self.calculate_hash(content)
            return NetworkConfig(
                path=path,
                content=content,
                type=config_type,
                original_hash=content_hash,
            )
        except Exception as e:
            self.logger.error("Failed to read config file %s: %s", path, e)
            return None

    def find_network_configs(self, g: guestfs.GuestFS) -> list[NetworkConfig]:
        """
        Find all network configuration files on guest filesystem.

        Args:
            g: GuestFS handle with root filesystem mounted

        Returns:
            List of NetworkConfig objects
        """
        configs: list[NetworkConfig] = []
        seen: set[str] = set()

        # Search using known patterns for each config type
        for _config_type, patterns in CONFIG_PATTERNS.items():
            for pattern in patterns:
                try:
                    files = guest_ls_glob(g, pattern)
                    for file_path in files:
                        if file_path in seen:
                            continue
                        if self._should_skip_path(file_path):
                            continue
                        seen.add(file_path)
                        cfg = self.read_config_file(g, file_path)
                        if cfg:
                            configs.append(cfg)
                except Exception as e:
                    self.logger.debug("glob failed (%s): %s", pattern, e)

        # Extra fallback locations (some distros use non-standard paths)
        for location in ("/etc/sysconfig/network/ifcfg-*", "/etc/ifcfg-*"):
            try:
                files = guest_ls_glob(g, location)
                for file_path in files:
                    if file_path in seen:
                        continue
                    if self._should_skip_path(file_path):
                        continue
                    seen.add(file_path)
                    cfg = self.read_config_file(g, file_path)
                    if cfg:
                        configs.append(cfg)
            except Exception:
                pass

        return configs


__all__ = ["NetworkDiscovery", "CONFIG_PATTERNS"]
