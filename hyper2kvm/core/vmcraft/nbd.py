# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/vmcraft/nbd.py
"""
NBD (Network Block Device) management for exposing disk images as block devices.

Uses qemu-nbd to connect disk images (qcow2, vmdk, vdi, vhd, raw) to /dev/nbdX devices,
enabling native Linux tools to access and modify VM disk images without libguestfs.
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from hyper2kvm.core.retry import retry_with_backoff

from ._utils import run_sudo


logger = logging.getLogger(__name__)


class NBDDeviceManager:
    """
    Manages NBD device lifecycle for disk image access.

    Handles:
    - Finding free NBD devices (/dev/nbd0 through /dev/nbd15)
    - Connecting disk images via qemu-nbd
    - Disconnecting and cleanup
    - Partition mapping
    - Resource tracking for proper cleanup

    Example:
        manager = NBDDeviceManager(logger, readonly=True)
        try:
            nbd_device = manager.connect('/path/to/disk.qcow2', format='qcow2')
            partitions = manager.get_partitions(nbd_device)
            # Use partitions...
        finally:
            manager.disconnect()
    """

    def __init__(
        self,
        logger: logging.Logger,
        *,
        readonly: bool = True,
        nbd_min: int = 0,
        nbd_max: int = 15,
    ):
        """
        Initialize NBD manager.

        Args:
            logger: Logger instance
            readonly: Mount NBD in read-only mode (default: True)
            nbd_min: Minimum NBD device number (default: 0)
            nbd_max: Maximum NBD device number (default: 15)
        """
        self.logger = logger
        self.readonly = bool(readonly)
        self.nbd_min = nbd_min
        self.nbd_max = nbd_max

        self._nbd_device: str | None = None
        self._nbd_process = None
        self._connected = False

    def _check_nbd_module(self) -> None:
        """Ensure NBD kernel module is loaded."""
        try:
            # Check if /dev/nbd0 exists
            if not Path("/dev/nbd0").exists():
                self.logger.info("Loading NBD kernel module...")
                run_sudo(self.logger, ["modprobe", "nbd", f"max_part=16"], check=True)
                # Wait a moment for device nodes to appear
                time.sleep(0.5)
        except Exception as e:
            raise RuntimeError(f"Failed to load NBD module: {e}") from e

    def _is_nbd_free(self, nbd_device: str) -> bool:
        """
        Check if NBD device is free.

        Args:
            nbd_device: Device path (e.g., /dev/nbd0)

        Returns:
            True if device is free, False if in use
        """
        try:
            # Try to read from /sys/block/nbdX/size
            # If size is 0, device is free
            nbd_name = Path(nbd_device).name  # e.g., nbd0
            size_file = Path(f"/sys/block/{nbd_name}/size")
            if size_file.exists():
                size = int(size_file.read_text().strip())
                return size == 0
            return True
        except Exception:
            # If we can't check, assume it's free
            return True

    def find_free_nbd(self) -> str:
        """
        Find a free NBD device.

        Returns:
            Path to free NBD device (e.g., /dev/nbd0)

        Raises:
            RuntimeError: If no free NBD devices available
        """
        self._check_nbd_module()

        for i in range(self.nbd_min, self.nbd_max + 1):
            nbd_device = f"/dev/nbd{i}"
            if self._is_nbd_free(nbd_device):
                self.logger.debug(f"Found free NBD device: {nbd_device}")
                return nbd_device

        raise RuntimeError(
            f"No free NBD devices available (checked /dev/nbd{self.nbd_min} "
            f"through /dev/nbd{self.nbd_max})"
        )

    @retry_with_backoff(
        max_attempts=3,
        base_backoff_s=2.0,
        max_backoff_s=10.0,
        exceptions=(subprocess.CalledProcessError, OSError),
        logger=logger,
        log_level=logging.WARNING,
    )
    def connect(
        self,
        image_path: str | Path,
        *,
        format: str | None = None,
        readonly: bool | None = None,
    ) -> str:
        """
        Connect disk image to NBD device with automatic retry on transient failures.

        Uses exponential backoff retry strategy (max 3 attempts, 2-10s backoff) to
        handle transient qemu-nbd command failures and OS-level errors.

        Args:
            image_path: Path to disk image
            format: Disk format (qcow2, vmdk, raw, etc.). Auto-detected if None.
            readonly: Override instance readonly setting

        Returns:
            Path to connected NBD device (e.g., /dev/nbd0)

        Raises:
            RuntimeError: If connection fails after all retry attempts or already connected
            subprocess.CalledProcessError: If qemu-nbd command fails (after retries)
            OSError: If file system operations fail (after retries)
        """
        if self._connected:
            raise RuntimeError("Already connected to an NBD device. Disconnect first.")

        image_path = Path(image_path).resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"Disk image not found: {image_path}")

        readonly = readonly if readonly is not None else self.readonly

        # Find free NBD device
        nbd_device = self.find_free_nbd()

        # Build qemu-nbd command
        cmd = ["qemu-nbd", "--connect", nbd_device]

        if format:
            cmd.extend(["--format", format])

        if readonly:
            cmd.append("--read-only")

        cmd.append(str(image_path))

        # Connect NBD (requires sudo)
        try:
            self.logger.info(f"Connecting {image_path} to {nbd_device}...")
            run_sudo(self.logger, cmd, check=True, capture=True)

            # Wait for device to become ready
            max_wait = 5  # seconds
            start = time.time()
            while time.time() - start < max_wait:
                if not self._is_nbd_free(nbd_device):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError(f"NBD device {nbd_device} not ready after {max_wait}s")

            self._nbd_device = nbd_device
            self._connected = True

            # Trigger partition scan
            self._scan_partitions(nbd_device)

            self.logger.info(f"Successfully connected to {nbd_device}")
            return nbd_device

        except (subprocess.CalledProcessError, OSError) as e:
            # Cleanup on failure (for retryable errors)
            try:
                run_sudo(self.logger, ["qemu-nbd", "--disconnect", nbd_device], check=False)
            except Exception:
                pass
            # Re-raise the original exception to allow retry decorator to catch it
            raise
        except Exception as e:
            # Cleanup on failure (for non-retryable errors)
            try:
                run_sudo(self.logger, ["qemu-nbd", "--disconnect", nbd_device], check=False)
            except Exception:
                pass
            # Wrap non-retryable exceptions in RuntimeError
            raise RuntimeError(f"Failed to connect NBD: {e}") from e

    def _scan_partitions(self, nbd_device: str) -> None:
        """
        Trigger partition table scan.

        Uses partprobe to make kernel re-read partition table.
        Falls back to kpartx if partprobe unavailable.
        """
        try:
            # First try partprobe (simpler)
            run_sudo(self.logger, ["partprobe", nbd_device], check=False, capture=True)
            time.sleep(0.5)  # Give kernel time to create partition devices

            # Verify partitions were created by checking for partition devices
            # This is especially important for non-sequential partition layouts (e.g., Photon OS)
            max_retries = 3
            for attempt in range(max_retries):
                result = run_sudo(self.logger, ["lsblk", "-n", "-o", "NAME", nbd_device], check=False, capture=True)
                if result.stdout:
                    lines = result.stdout.strip().splitlines()
                    # If we have more than just the main device, partitions exist
                    if len(lines) > 1:
                        self.logger.debug(f"Partitions verified after {attempt + 1} attempt(s)")
                        break

                if attempt < max_retries - 1:
                    self.logger.debug(f"Waiting for partitions to appear (attempt {attempt + 1}/{max_retries})")
                    time.sleep(0.3)
        except Exception:
            # Fallback to kpartx if available
            try:
                run_sudo(self.logger, ["kpartx", "-a", nbd_device], check=False, capture=True)
                time.sleep(0.5)
            except Exception:
                # If both fail, partitions might still work
                pass

    def get_partitions(self, nbd_device: str | None = None) -> list[str]:
        """
        Get list of partition devices for NBD device.

        Args:
            nbd_device: NBD device path. Uses connected device if None.

        Returns:
            List of partition device paths (e.g., ['/dev/nbd0p1', '/dev/nbd0p2'])
        """
        if nbd_device is None:
            if not self._connected or not self._nbd_device:
                raise RuntimeError("No NBD device connected")
            nbd_device = self._nbd_device

        # Use lsblk to find partitions
        try:
            cmd = ["lsblk", "-n", "-o", "NAME", nbd_device]
            result = run_sudo(self.logger, cmd, check=True, capture=True)

            partitions = []
            nbd_name = Path(nbd_device).name
            for line in result.stdout.splitlines():
                # Remove tree-drawing characters (└, ─, ├, │, etc.) from lsblk output
                line = line.strip()
                # Strip common box-drawing characters
                for char in ['└', '─', '├', '│', '├─', '└─']:
                    line = line.replace(char, '')
                line = line.strip()

                if line and line != nbd_name:
                    # Check if this is an LVM logical volume (contains hyphen but doesn't start with NBD device name)
                    # LVM volumes appear in lsblk as "vgname-lvname" (e.g., "cs-root", "fedora-root")
                    # They need /dev/mapper/ prefix, not /dev/
                    if '-' in line and not line.startswith(nbd_name):
                        # LVM logical volume: /dev/mapper/vgname-lvname
                        partitions.append(f"/dev/mapper/{line}")
                        self.logger.debug(f"Detected LVM volume in partition list: {line} -> /dev/mapper/{line}")
                    else:
                        # Regular partition (e.g., nbd0p1)
                        partitions.append(f"/dev/{line}")

            return partitions

        except Exception as e:
            self.logger.warning(f"Failed to list partitions: {e}")
            return []

    def disconnect(self, nbd_device: str | None = None) -> None:
        """
        Disconnect NBD device.

        Args:
            nbd_device: Device to disconnect. Uses connected device if None.
        """
        if nbd_device is None:
            nbd_device = self._nbd_device

        if not nbd_device:
            return

        try:
            self.logger.info(f"Disconnecting {nbd_device}...")
            run_sudo(self.logger, ["qemu-nbd", "--disconnect", nbd_device], check=False, capture=True)

            # Wait for disconnect to complete
            max_wait = 3
            start = time.time()
            while time.time() - start < max_wait:
                if self._is_nbd_free(nbd_device):
                    break
                time.sleep(0.1)

            self.logger.info(f"Disconnected {nbd_device}")

        except Exception as e:
            self.logger.warning(f"Error disconnecting {nbd_device}: {e}")
        finally:
            self._nbd_device = None
            self._connected = False
            self._nbd_process = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        try:
            self.disconnect()
        except Exception as e:
            self.logger.error(f"Error during NBD cleanup: {e}")
        return False
