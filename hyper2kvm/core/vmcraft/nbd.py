# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/vmcraft/nbd.py
"""
NBD (Network Block Device) management for exposing disk images as block devices.

Uses qemu-nbd to connect disk images (qcow2, vmdk, vdi, vhd, raw) to /dev/nbdX devices,
enabling native Linux tools to access and modify VM disk images.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
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
        self._converted_qcow2_path: Path | None = None  # Track temp qcow2 for cleanup

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

    def _needs_conversion(self, image_path: Path) -> bool:
        """
        Check if VMDK needs conversion to qcow2 (streamOptimized, compressed, sparse, etc.).

        Problematic VMDK types that cause "can't read superblock" errors via qemu-nbd:
        - streamOptimized: Random-access read issues with decompression
        - monolithicSparse: Sparse regions cause I/O errors when accessing unallocated blocks
        - compressed: Similar decompression issues

        Args:
            image_path: Path to image file

        Returns:
            True if image should be converted before mounting
        """
        if image_path.suffix.lower() != ".vmdk":
            return False

        try:
            result = subprocess.run(
                ["qemu-img", "info", "--output=json", str(image_path)],
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            info = json.loads(result.stdout)

            # Check for problematic VMDK types
            format_specific = info.get("format-specific", {})
            vmdk_info = format_specific.get("data", {})

            create_type = vmdk_info.get("create-type", "").lower()
            compressed = vmdk_info.get("compressed", False)

            # Problematic types that need conversion:
            # - streamOptimized: decompression issues
            # - monolithicSparse: sparse region I/O errors
            # - compressed: similar to streamOptimized
            needs_conversion = False
            reason = []

            if "streamoptimized" in create_type:
                needs_conversion = True
                reason.append(f"streamOptimized format")
            elif "sparse" in create_type:
                # monolithicSparse, twoGbMaxExtentSparse, etc.
                needs_conversion = True
                reason.append(f"sparse format ({create_type})")

            if compressed:
                needs_conversion = True
                reason.append("compressed")

            if needs_conversion:
                self.logger.warning(
                    f"Detected problematic VMDK: {', '.join(reason)}. "
                    f"Will convert to qcow2 for reliability."
                )
                return True

            return False

        except Exception as e:
            self.logger.debug(f"Could not check VMDK type: {e}, proceeding without conversion")
            return False

    def _convert_to_qcow2(self, vmdk_path: Path) -> Path:
        """
        Convert VMDK to qcow2 in temp directory.

        Args:
            vmdk_path: Path to VMDK file

        Returns:
            Path to converted qcow2 file
        """
        # Get original VMDK virtual size for verification
        try:
            result = subprocess.run(
                ["qemu-img", "info", "--output=json", str(vmdk_path)],
                capture_output=True, text=True, check=True, timeout=30
            )
            vmdk_info = json.loads(result.stdout)
            original_virtual_size = vmdk_info.get("virtual-size", 0)
        except Exception as e:
            self.logger.warning(f"Could not get VMDK size: {e}")
            original_virtual_size = 0

        # Create temp qcow2 file
        # Use /var/tmp instead of /tmp for large conversions (sparse VMDKs with -S 0 can be huge)
        # /var/tmp is typically on the root filesystem with more space than tmpfs /tmp
        temp_dir = Path("/var/tmp/vmcraft-conversions")
        temp_dir.mkdir(exist_ok=True, mode=0o700)

        temp_qcow2 = temp_dir / f"{vmdk_path.stem}.qcow2"

        # Check available space before conversion
        if original_virtual_size:
            stat = subprocess.run(
                ["df", "--output=avail", "-B1", str(temp_dir)],
                capture_output=True, text=True, check=True
            )
            avail_bytes = int(stat.stdout.strip().split('\n')[-1])
            # Estimate needed space: virtual_size * 0.3 (qcow2 compression estimate for -S 0)
            needed_bytes = int(original_virtual_size * 0.4)  # 40% safety margin

            if avail_bytes < needed_bytes:
                self.logger.warning(
                    f"Low disk space in {temp_dir}: {avail_bytes / (1024**3):.1f} GiB available, "
                    f"~{needed_bytes / (1024**3):.1f} GiB needed for conversion"
                )

        self.logger.info(f"Converting {vmdk_path.name} to qcow2...")
        self.logger.info(f"  Source: {vmdk_path}")
        self.logger.info(f"  Destination: {temp_qcow2}")
        if original_virtual_size:
            self.logger.info(f"  Original virtual size: {original_virtual_size / (1024**3):.2f} GiB")

        try:
            # Convert with progress
            # CRITICAL: Use -S 0 to disable sparse detection for sparse VMDKs
            # Without this, unallocated sparse regions won't be written to qcow2,
            # causing I/O errors when LVM volumes span those regions
            subprocess.run(
                [
                    "qemu-img", "convert",
                    "-p",  # Progress
                    "-S", "0",  # Disable sparse detection - write all blocks
                    "-f", "vmdk",
                    "-O", "qcow2",
                    str(vmdk_path),
                    str(temp_qcow2)
                ],
                check=True,
                timeout=3600  # 1 hour max for large disks
            )

            # Verify converted size matches original
            if original_virtual_size:
                try:
                    result = subprocess.run(
                        ["qemu-img", "info", "--output=json", str(temp_qcow2)],
                        capture_output=True, text=True, check=True, timeout=30
                    )
                    qcow2_info = json.loads(result.stdout)
                    qcow2_virtual_size = qcow2_info.get("virtual-size", 0)

                    if qcow2_virtual_size != original_virtual_size:
                        self.logger.warning(
                            f"Virtual size mismatch after conversion: "
                            f"original={original_virtual_size / (1024**3):.2f} GiB, "
                            f"converted={qcow2_virtual_size / (1024**3):.2f} GiB"
                        )
                    else:
                        self.logger.info(
                            f"✓ Virtual size verified: {qcow2_virtual_size / (1024**3):.2f} GiB"
                        )
                except Exception as e:
                    self.logger.debug(f"Could not verify qcow2 size: {e}")

            self.logger.info(f"✓ Conversion completed: {temp_qcow2}")
            return temp_qcow2

        except subprocess.TimeoutExpired:
            if temp_qcow2.exists():
                temp_qcow2.unlink()
            raise RuntimeError(f"VMDK conversion timed out after 1 hour")
        except subprocess.CalledProcessError as e:
            if temp_qcow2.exists():
                temp_qcow2.unlink()
            raise RuntimeError(f"VMDK conversion failed: {e}")

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

        Automatically converts streamOptimized VMDKs to qcow2 for reliability.

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

        # Check if VMDK needs conversion (streamOptimized, compressed)
        if self._needs_conversion(image_path):
            original_path = image_path
            converted_path = self._convert_to_qcow2(image_path)
            self._converted_qcow2_path = converted_path  # Track for cleanup
            image_path = converted_path
            format = "qcow2"  # Override format after conversion
            self.logger.info(f"Using converted qcow2 instead of original {original_path.name}")

        # Auto-detect format from extension if not specified
        # This is critical for VMDKs, especially ESXi thin-provisioned ones
        if not format:
            suffix = image_path.suffix.lower()
            format_map = {
                ".vmdk": "vmdk",
                ".qcow2": "qcow2",
                ".qcow": "qcow2",
                ".vdi": "vdi",
                ".vhd": "vpc",
                ".vhdx": "vhdx",
                ".img": "raw",
                ".raw": "raw",
            }
            format = format_map.get(suffix)
            if format:
                self.logger.info(f"Auto-detected format '{format}' from extension '{suffix}'")

        # Find free NBD device
        nbd_device = self.find_free_nbd()

        # Build qemu-nbd command
        cmd = ["qemu-nbd", "--connect", nbd_device]

        if format:
            cmd.extend(["--format", format])
        else:
            self.logger.warning(f"No format specified and couldn't auto-detect from '{image_path.suffix}' - qemu-nbd will try to auto-detect")

        if readonly:
            cmd.append("--read-only")

        # Use cache=none for data integrity (prevents corruption from kernel cache issues)
        # This is especially important for write operations
        cmd.extend(["--cache", "none"])

        # Use native AIO for better performance and stability
        cmd.extend(["--aio", "native"])

        # Enable discard for thin-provisioned images (VMware, qcow2)
        cmd.extend(["--discard", "unmap"])

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
            # Clean up temporary converted qcow2 if it exists
            if self._converted_qcow2_path and self._converted_qcow2_path.exists():
                try:
                    self.logger.info(f"Removing temporary converted qcow2: {self._converted_qcow2_path}")
                    self._converted_qcow2_path.unlink()
                    self.logger.info(f"✓ Cleaned up {self._converted_qcow2_path.name}")
                except Exception as cleanup_error:
                    self.logger.warning(f"Failed to remove temp qcow2: {cleanup_error}")

            self._nbd_device = None
            self._connected = False
            self._nbd_process = None
            self._converted_qcow2_path = None

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
