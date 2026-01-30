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
        conversion_dir: str | Path | None = None,
    ):
        """
        Initialize NBD manager.

        Args:
            logger: Logger instance
            readonly: Mount NBD in read-only mode (default: True)
            nbd_min: Minimum NBD device number (default: 0)
            nbd_max: Maximum NBD device number (default: 15)
            conversion_dir: Directory for VMDK conversion temp files.
                           Defaults to ~/.cache/hyper2kvm/conversions
        """
        self.logger = logger
        self.readonly = bool(readonly)
        self.nbd_min = nbd_min
        self.nbd_max = nbd_max

        # Set conversion directory with proper default
        if conversion_dir:
            self._conversion_dir = Path(conversion_dir).expanduser().resolve()
        else:
            # Default: ~/.cache/hyper2kvm/conversions
            self._conversion_dir = Path.home() / ".cache" / "hyper2kvm" / "conversions"

        self._nbd_device: str | None = None
        self._nbd_process = None
        self._connected = False
        self._converted_qcow2_path: Path | None = None  # Track temp qcow2 for cleanup
        self._keep_converted = False  # Flag to preserve converted qcow2

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

    @property
    def converted_image_path(self) -> Path | None:
        """Get path to converted qcow2 if one was created, None otherwise."""
        return self._converted_qcow2_path

    def keep_converted_image(self) -> None:
        """Mark the converted qcow2 to be kept (not deleted on disconnect)."""
        self._keep_converted = True
        if self._converted_qcow2_path:
            self.logger.info(f"Preserving converted qcow2: {self._converted_qcow2_path.name}")

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
        # Get original VMDK info for verification and space estimation
        try:
            result = subprocess.run(
                ["qemu-img", "info", "--output=json", str(vmdk_path)],
                capture_output=True, text=True, check=True, timeout=30
            )
            vmdk_info = json.loads(result.stdout)
            original_virtual_size = vmdk_info.get("virtual-size", 0)
            actual_disk_size = vmdk_info.get("actual-size", 0)
            vmdk_createtype = vmdk_info.get("format-specific", {}).get("data", {}).get("create-type", "")
        except Exception as e:
            self.logger.warning(f"Could not get VMDK size: {e}")
            original_virtual_size = 0
            actual_disk_size = 0
            vmdk_createtype = ""

        # Create temp qcow2 file in configured conversion directory
        # Defaults to ~/.cache/hyper2kvm/conversions for better space management
        temp_dir = self._conversion_dir
        temp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        temp_qcow2 = temp_dir / f"{vmdk_path.stem}.qcow2"

        # Check available space before conversion
        if original_virtual_size:
            stat = subprocess.run(
                ["df", "--output=avail", "-B1", str(temp_dir)],
                capture_output=True, text=True, check=True
            )
            avail_bytes = int(stat.stdout.strip().split('\n')[-1])

            # Smart space estimation based on VMDK type
            is_sparse = vmdk_createtype in ("monolithicSparse", "streamOptimized")
            if is_sparse and actual_disk_size:
                # For sparse VMDKs: use actual size * 2 (for RAW intermediate) + margin
                needed_bytes = int(max(actual_disk_size * 2.5, original_virtual_size * 0.05))
            else:
                # For non-sparse: use virtual_size * 0.4 (qcow2 compression estimate)
                needed_bytes = int(original_virtual_size * 0.4)

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
            # For monolithicSparse VMDKs, use RAW intermediate for much faster conversion
            # Direct sparse VMDK → qcow2 with -S 0 is slow due to qcow2 metadata thrashing
            # Better: VMDK → RAW (fast, streaming) → QCOW2 (final)

            # Check if this is a sparse VMDK
            is_sparse = vmdk_createtype in ("monolithicSparse", "streamOptimized")

            if is_sparse:
                # Two-step conversion for sparse VMDKs
                temp_raw = temp_qcow2.with_suffix('.raw')

                try:
                    self.logger.info("  Using RAW intermediate for sparse VMDK (faster)")

                    # Step 1: VMDK → RAW (fast, sequential writes)
                    self.logger.info(f"  Step 1/2: VMDK → RAW")
                    subprocess.run(
                        [
                            "qemu-img", "convert",
                            "-p",  # Progress
                            "-f", "vmdk",
                            "-O", "raw",
                            str(vmdk_path),
                            str(temp_raw)
                        ],
                        check=True,
                        timeout=3600
                    )

                    # Step 2: RAW → QCOW2
                    # CRITICAL: Detect LVM/mdraid/luks and disable sparse detection if present
                    # Using -S with LVM causes data corruption as zero runs may contain LVM metadata
                    has_layered_storage = self._detect_layered_storage(temp_raw)

                    if has_layered_storage:
                        self.logger.info(f"  Step 2/2: RAW → QCOW2 (sparse disabled - LVM/mdraid/luks detected)")
                        self.logger.info(f"  ⚠️  Disabling sparse detection to prevent LVM metadata corruption")
                        sparse_opt = "0"  # Disable sparse detection for safety
                    else:
                        self.logger.info(f"  Step 2/2: RAW → QCOW2 (sparse-aware)")
                        sparse_opt = "64k"  # Safe to use sparse detection

                    subprocess.run(
                        [
                            "qemu-img", "convert",
                            "-p",  # Progress
                            "-S", sparse_opt,
                            "-f", "raw",
                            "-O", "qcow2",
                            str(temp_raw),
                            str(temp_qcow2)
                        ],
                        check=True,
                        timeout=3600
                    )

                finally:
                    # Cleanup RAW intermediate
                    if temp_raw.exists():
                        self.logger.debug(f"Removing RAW intermediate: {temp_raw}")
                        temp_raw.unlink()
            else:
                # Direct conversion for non-sparse VMDKs
                # CRITICAL: Use -S 0 to disable sparse detection
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

    def _detect_layered_storage(self, raw_image: Path) -> bool:
        """
        Detect if RAW image contains layered storage (LVM, mdraid, luks, btrfs).

        Using sparse detection (-S) with layered storage causes data corruption:
        - LVM metadata and extents may contain zero runs
        - mdraid superblocks span sparse regions
        - luks headers contain zero-padded areas
        - btrfs metadata trees have sparse regions

        Sparse detection would punch holes through these critical structures,
        making volumes unreadable.

        Args:
            raw_image: Path to RAW disk image

        Returns:
            True if layered storage detected, False otherwise
        """
        detected_types = []

        try:
            # Method 1: Check partition table for known types
            result = subprocess.run(
                ["parted", "-s", str(raw_image), "print"],
                capture_output=True,
                text=True,
                timeout=30
            )

            output = result.stdout.lower()

            # Check for LVM partition type (0x8e for DOS, E6D6D379-F507-44C2-A23C-238F2A3DF928 for GPT)
            if "lvm" in output or "8e" in output:
                detected_types.append("LVM")

            # Check for Linux RAID (0xfd for DOS)
            if "raid" in output or "fd" in output:
                detected_types.append("mdraid")

        except Exception as e:
            self.logger.debug(f"Partition table check failed: {e}")

        try:
            # Method 2: Use file/blkid to detect filesystem signatures
            # This catches luks and btrfs which may not have special partition types
            result = subprocess.run(
                ["file", "-s", str(raw_image)],
                capture_output=True,
                text=True,
                timeout=30
            )

            output = result.stdout.lower()

            # Check for LUKS signature
            if "luks" in output or "crypto_luks" in output:
                detected_types.append("LUKS")

            # Check for btrfs signature
            if "btrfs" in output:
                detected_types.append("btrfs")

        except Exception as e:
            self.logger.debug(f"Filesystem signature check failed: {e}")

        if detected_types:
            types_str = ", ".join(detected_types)
            self.logger.info(f"  🔍 Layered storage detected: {types_str}")
            self.logger.info(f"  ⚠️  Sparse detection will be disabled to prevent corruption")
            return True

        # If detection fails or no results, err on the side of caution
        if not detected_types:
            self.logger.debug("  No layered storage detected, sparse-aware conversion is safe")

        return False

    def _validate_image(self, image_path: Path) -> dict[str, any]:
        """
        Validate disk image integrity with qemu-img before attempting connection.

        Uses qemu-img check and qemu-img info to:
        1. Detect image corruption early (before NBD connection)
        2. Extract metadata (format, virtual size, backing files)
        3. Provide better error messages for invalid images

        Args:
            image_path: Path to disk image

        Returns:
            Image metadata dict from qemu-img info

        Raises:
            RuntimeError: If image is corrupted or invalid
        """
        try:
            # Step 1: Check image integrity
            self.logger.debug(f"Validating image integrity: {image_path.name}")
            check_result = run_sudo(
                self.logger,
                ["qemu-img", "check", str(image_path)],
                check=False,  # Don't raise on non-zero (some warnings are OK)
                capture=True,
                failure_log_level=logging.DEBUG
            )

            # Parse qemu-img check output for critical errors
            # Exit code 0 = no errors, 1 = errors found, 2 = check not supported, 3 = invalid image
            if check_result.returncode == 3:
                raise RuntimeError(
                    f"Image validation failed: {image_path.name}\n"
                    f"qemu-img cannot recognize this image format.\n"
                    f"Output: {check_result.stdout}"
                )
            elif check_result.returncode == 1:
                # Check if errors are critical
                stdout_lower = check_result.stdout.lower()
                if "leaked clusters" in stdout_lower or "corruptions" in stdout_lower:
                    self.logger.warning(
                        f"Image has corruption/leaks: {image_path.name}\n"
                        f"qemu-img check output: {check_result.stdout}\n"
                        f"Attempting to proceed anyway (may fail during mount)"
                    )

            # Step 2: Get image metadata
            self.logger.debug(f"Extracting image metadata: {image_path.name}")
            info_result = run_sudo(
                self.logger,
                ["qemu-img", "info", "--output=json", str(image_path)],
                check=True,
                capture=True
            )

            metadata = json.loads(info_result.stdout)

            # Log useful metadata
            virtual_size_gb = metadata.get('virtual-size', 0) / (1024**3)
            actual_size_gb = metadata.get('actual-size', 0) / (1024**3)
            format_name = metadata.get('format', 'unknown')

            self.logger.info(
                f"✓ Image validated: {format_name} "
                f"(virtual: {virtual_size_gb:.2f} GiB, actual: {actual_size_gb:.2f} GiB)"
            )

            # Warn about backing files (snapshots/linked clones)
            if 'backing-filename' in metadata:
                backing = metadata['backing-filename']
                self.logger.warning(
                    f"Image has backing file: {backing}\n"
                    f"This is a snapshot or linked clone. Ensure backing file is accessible."
                )

            return metadata

        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Failed to parse qemu-img info output for {image_path.name}: {e}"
            ) from None
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"qemu-img failed to read image {image_path.name}:\n{e.stdout}"
            ) from None
        except Exception as e:
            raise RuntimeError(f"Image validation failed for {image_path.name}: {e}") from None

    def validate_filesystems(
        self,
        image_path: str | Path,
        *,
        format: str | None = None,
        check_partitions: bool = True,
        run_fsck: bool = False,
    ) -> dict[str, any]:
        """
        Perform deep filesystem validation by temporarily connecting image via NBD.

        This performs structural validation beyond basic qemu-img checks:
        1. Attaches image via qemu-nbd
        2. Inspects partition table with lsblk
        3. Optionally runs read-only fsck on partitions

        WARNING: This is slower than basic validation and requires NBD device.
        Use for thorough pre-migration validation or troubleshooting.

        Args:
            image_path: Path to disk image
            format: Disk format hint (qcow2, vmdk, raw, etc.)
            check_partitions: Verify partition table is readable (default: True)
            run_fsck: Run read-only filesystem checks (default: False, slower)

        Returns:
            Validation report dict with partition info and fsck results

        Raises:
            RuntimeError: If validation fails or image is corrupted

        Example:
            nbd = NBDDeviceManager(logger)
            report = nbd.validate_filesystems('/vms/test.vmdk', run_fsck=True)
            print(report['partitions'])
            print(report['fsck_results'])
        """
        image_path = Path(image_path).resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"Disk image not found: {image_path}")

        self.logger.info(f"Performing deep filesystem validation: {image_path.name}")

        # First do basic image validation
        metadata = self._validate_image(image_path)

        # Temporarily connect to NBD for partition inspection
        temp_nbd = None
        report = {
            "image": str(image_path),
            "format": metadata.get("format", "unknown"),
            "virtual_size_gb": metadata.get("virtual-size", 0) / (1024**3),
            "actual_size_gb": metadata.get("actual-size", 0) / (1024**3),
            "partitions": [],
            "fsck_results": [],
            "status": "unknown"
        }

        try:
            # Find free NBD device
            self._check_nbd_module()
            for i in range(self.nbd_min, self.nbd_max + 1):
                candidate = f"/dev/nbd{i}"
                if self._is_nbd_free(candidate):
                    temp_nbd = candidate
                    break

            if not temp_nbd:
                raise RuntimeError("No free NBD device for validation")

            self.logger.debug(f"Using temporary NBD device: {temp_nbd}")

            # Connect image (read-only)
            connect_cmd = ["qemu-nbd", "--read-only", "--connect", temp_nbd]
            if format:
                connect_cmd.extend(["--format", format])
            connect_cmd.append(str(image_path))

            run_sudo(self.logger, connect_cmd, check=True, capture=True)
            time.sleep(1)  # Allow kernel to detect partitions

            # Scan partitions
            run_sudo(self.logger, ["partprobe", temp_nbd], check=False, capture=True)
            time.sleep(0.5)

            if check_partitions:
                # Get partition information with lsblk
                self.logger.debug("Inspecting partition table...")
                lsblk_result = run_sudo(
                    self.logger,
                    ["lsblk", "-f", "-o", "NAME,FSTYPE,SIZE,LABEL,UUID,MOUNTPOINT", temp_nbd],
                    check=True,
                    capture=True
                )
                report["partition_table"] = lsblk_result.stdout

                # Parse lsblk output for partition devices
                partition_devices = []
                for line in lsblk_result.stdout.splitlines()[1:]:  # Skip header
                    line = line.strip()
                    if line.startswith("├─") or line.startswith("└─"):
                        # Extract device name (e.g., nbd0p1, nbd0p2)
                        parts = line.split()
                        if parts:
                            dev_name = parts[0].replace("├─", "").replace("└─", "").strip()
                            partition_devices.append(f"/dev/{dev_name}")
                            report["partitions"].append({
                                "device": dev_name,
                                "info": " ".join(parts)
                            })

                self.logger.info(f"Found {len(partition_devices)} partitions")

                # Optionally run fsck (read-only) on partitions
                if run_fsck and partition_devices:
                    self.logger.info("Running read-only filesystem checks (fsck -n)...")
                    for part_dev in partition_devices:
                        if not Path(part_dev).exists():
                            continue

                        try:
                            fsck_result = run_sudo(
                                self.logger,
                                ["fsck", "-n", part_dev],  # -n = read-only, no fixes
                                check=False,  # fsck may return non-zero even for clean FS
                                capture=True,
                                failure_log_level=logging.DEBUG
                            )

                            status = "clean" if fsck_result.returncode == 0 else "errors_found"
                            report["fsck_results"].append({
                                "partition": part_dev,
                                "status": status,
                                "exit_code": fsck_result.returncode,
                                "output": fsck_result.stdout[:500]  # Truncate long output
                            })

                            if status == "errors_found":
                                self.logger.warning(
                                    f"Filesystem errors detected on {part_dev}:\n"
                                    f"{fsck_result.stdout[:200]}"
                                )
                            else:
                                self.logger.debug(f"Filesystem check passed: {part_dev}")

                        except Exception as e:
                            self.logger.debug(f"Could not check {part_dev}: {e}")
                            report["fsck_results"].append({
                                "partition": part_dev,
                                "status": "check_failed",
                                "error": str(e)
                            })

            report["status"] = "validated"
            self.logger.info(f"✓ Deep validation completed for {image_path.name}")

        except Exception as e:
            report["status"] = "validation_failed"
            report["error"] = str(e)
            self.logger.error(f"Deep validation failed: {e}")
            raise RuntimeError(f"Filesystem validation failed for {image_path.name}: {e}") from e

        finally:
            # Always disconnect
            if temp_nbd:
                try:
                    run_sudo(
                        self.logger,
                        ["qemu-nbd", "--disconnect", temp_nbd],
                        check=False,
                        capture=True
                    )
                    self.logger.debug(f"Disconnected validation NBD: {temp_nbd}")
                except Exception as e:
                    self.logger.debug(f"Could not disconnect {temp_nbd}: {e}")

        return report

    def inspect_disk(
        self,
        image_path: str | Path,
        *,
        format: str | None = None,
        check_lvm: bool = True,
        activate_lvm: bool = True,
        run_fsck: bool = False,
    ) -> dict[str, any]:
        """
        Perform comprehensive disk image inspection including LVM structures.

        This provides deeper inspection than validate_filesystems, including:
        - Full LVM structure analysis (PVs, VGs, LVs)
        - LVM activation and logical volume detection
        - Partition table details
        - Filesystem detection on both partitions and LVs
        - Optional filesystem integrity checks

        Args:
            image_path: Path to disk image
            format: Disk format hint (qcow2, vmdk, raw, etc.)
            check_lvm: Detect and analyze LVM structures
            activate_lvm: Activate LVM volume groups to see LVs
            run_fsck: Run read-only filesystem checks

        Returns:
            Comprehensive inspection report dict

        Raises:
            RuntimeError: If inspection fails

        Example:
            nbd = NBDDeviceManager(logger)
            report = nbd.inspect_disk(
                '/vms/disk.vmdk',
                check_lvm=True,
                activate_lvm=True,
                run_fsck=True
            )
            print(f"Partitions: {len(report['partitions'])}")
            print(f"LVM VGs: {len(report['lvm']['volume_groups'])}")
            print(f"LVM LVs: {len(report['lvm']['logical_volumes'])}")
        """
        image_path = Path(image_path).resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"Disk image not found: {image_path}")

        self.logger.info(f"Performing comprehensive disk inspection: {image_path.name}")

        # First do basic image validation
        metadata = self._validate_image(image_path)

        # Temporarily connect to NBD for deep inspection
        temp_nbd = None
        report = {
            "image": str(image_path),
            "format": metadata.get("format", "unknown"),
            "virtual_size_gb": metadata.get("virtual-size", 0) / (1024**3),
            "actual_size_gb": metadata.get("actual-size", 0) / (1024**3),
            "partitions": [],
            "lvm": {
                "physical_volumes": [],
                "volume_groups": [],
                "logical_volumes": []
            },
            "filesystems": [],
            "fsck_results": [],
            "status": "unknown"
        }

        try:
            # Find free NBD device (use existing auto-detection)
            self._check_nbd_module()
            for i in range(self.nbd_min, self.nbd_max + 1):
                candidate = f"/dev/nbd{i}"
                if self._is_nbd_free(candidate):
                    temp_nbd = candidate
                    break

            if not temp_nbd:
                raise RuntimeError("No free NBD device for inspection")

            self.logger.debug(f"Using NBD device: {temp_nbd}")

            # Connect image (read-only)
            connect_cmd = ["qemu-nbd", "--read-only", "--connect", temp_nbd]
            if format:
                connect_cmd.extend(["--format", format])
            connect_cmd.append(str(image_path))

            run_sudo(self.logger, connect_cmd, check=True, capture=True)
            time.sleep(2)  # Allow kernel to detect partitions

            # Scan partitions
            run_sudo(self.logger, ["partprobe", temp_nbd], check=False, capture=True)
            time.sleep(0.5)

            # Get partition information
            self.logger.debug("Inspecting partition table...")
            lsblk_result = run_sudo(
                self.logger,
                ["lsblk", "-f", "-o", "NAME,FSTYPE,SIZE,LABEL,UUID", temp_nbd],
                check=True,
                capture=True
            )

            # Parse partitions
            for line in lsblk_result.stdout.splitlines()[1:]:  # Skip header
                line = line.strip()
                if line.startswith("├─") or line.startswith("└─"):
                    parts = line.split()
                    if parts:
                        dev_name = parts[0].replace("├─", "").replace("└─", "").strip()
                        report["partitions"].append({
                            "device": dev_name,
                            "info": " ".join(parts)
                        })

            self.logger.info(f"Found {len(report['partitions'])} partitions")

            # LVM inspection
            if check_lvm:
                self.logger.debug("Scanning for LVM structures...")

                # Physical Volumes
                try:
                    pvs_result = run_sudo(
                        self.logger,
                        ["pvs", "--noheadings", "-o", "pv_name,vg_name,pv_size"],
                        check=False,
                        capture=True,
                        failure_log_level=logging.DEBUG
                    )
                    if pvs_result.stdout.strip():
                        for line in pvs_result.stdout.splitlines():
                            parts = line.split()
                            if len(parts) >= 3:
                                report["lvm"]["physical_volumes"].append({
                                    "pv": parts[0],
                                    "vg": parts[1],
                                    "size": parts[2]
                                })
                except Exception as e:
                    self.logger.debug(f"PV scan failed: {e}")

                # Volume Groups
                try:
                    vgs_result = run_sudo(
                        self.logger,
                        ["vgs", "--noheadings", "-o", "vg_name,pv_count,lv_count,vg_size"],
                        check=False,
                        capture=True,
                        failure_log_level=logging.DEBUG
                    )
                    if vgs_result.stdout.strip():
                        for line in vgs_result.stdout.splitlines():
                            parts = line.split()
                            if len(parts) >= 4:
                                report["lvm"]["volume_groups"].append({
                                    "vg": parts[0],
                                    "pv_count": parts[1],
                                    "lv_count": parts[2],
                                    "size": parts[3]
                                })
                except Exception as e:
                    self.logger.debug(f"VG scan failed: {e}")

                # Activate VGs if requested
                if activate_lvm and report["lvm"]["volume_groups"]:
                    self.logger.debug("Activating LVM volume groups...")
                    try:
                        run_sudo(
                            self.logger,
                            ["vgchange", "-ay"],
                            check=False,
                            capture=True,
                            failure_log_level=logging.DEBUG
                        )
                        time.sleep(1)  # Wait for device nodes

                        # Ensure device nodes are created
                        run_sudo(
                            self.logger,
                            ["dmsetup", "mknodes"],
                            check=False,
                            capture=True,
                            failure_log_level=logging.DEBUG
                        )
                        run_sudo(
                            self.logger,
                            ["udevadm", "settle"],
                            check=False,
                            capture=True,
                            failure_log_level=logging.DEBUG
                        )

                        self.logger.info(f"Activated {len(report['lvm']['volume_groups'])} volume groups")
                    except Exception as e:
                        self.logger.debug(f"VG activation failed: {e}")

                # Logical Volumes
                try:
                    lvs_result = run_sudo(
                        self.logger,
                        ["lvs", "--noheadings", "-o", "lv_name,lv_path,lv_size,vg_name"],
                        check=False,
                        capture=True,
                        failure_log_level=logging.DEBUG
                    )
                    if lvs_result.stdout.strip():
                        for line in lvs_result.stdout.splitlines():
                            parts = line.split()
                            if len(parts) >= 4:
                                report["lvm"]["logical_volumes"].append({
                                    "lv": parts[0],
                                    "path": parts[1],
                                    "size": parts[2],
                                    "vg": parts[3]
                                })
                except Exception as e:
                    self.logger.debug(f"LV scan failed: {e}")

                self.logger.info(
                    f"LVM: {len(report['lvm']['physical_volumes'])} PVs, "
                    f"{len(report['lvm']['volume_groups'])} VGs, "
                    f"{len(report['lvm']['logical_volumes'])} LVs"
                )

            # Detect filesystems on all block devices
            self.logger.debug("Detecting filesystems...")
            try:
                blkid_result = run_sudo(
                    self.logger,
                    ["blkid"],
                    check=False,
                    capture=True,
                    failure_log_level=logging.DEBUG
                )

                for line in blkid_result.stdout.splitlines():
                    if ":" in line:
                        device = line.split(":")[0]
                        # Check if this device is related to our NBD or LVM
                        if temp_nbd in device or "/dev/mapper/" in device or "/dev/dm-" in device:
                            # Extract filesystem type
                            fstype = ""
                            if 'TYPE="' in line:
                                fstype = line.split('TYPE="')[1].split('"')[0]

                            if fstype and fstype != "LVM2_member":
                                report["filesystems"].append({
                                    "device": device,
                                    "fstype": fstype
                                })

            except Exception as e:
                self.logger.debug(f"Filesystem detection failed: {e}")

            self.logger.info(f"Found {len(report['filesystems'])} filesystems")

            # Optional filesystem checks
            if run_fsck and report["filesystems"]:
                self.logger.info("Running read-only filesystem checks...")
                for fs in report["filesystems"]:
                    device = fs["device"]
                    fstype = fs["fstype"]

                    # Skip certain filesystem types
                    if fstype in ["swap", "crypto_LUKS"]:
                        continue

                    try:
                        fsck_result = run_sudo(
                            self.logger,
                            ["fsck", "-n", device],
                            check=False,
                            capture=True,
                            failure_log_level=logging.DEBUG
                        )

                        status = "clean" if fsck_result.returncode == 0 else "errors_found"
                        report["fsck_results"].append({
                            "device": device,
                            "fstype": fstype,
                            "status": status,
                            "exit_code": fsck_result.returncode,
                            "output": fsck_result.stdout[:500] if fsck_result.stdout else ""
                        })

                        if status == "clean":
                            self.logger.debug(f"Filesystem check passed: {device}")
                        else:
                            self.logger.warning(f"Filesystem errors on {device} (exit: {fsck_result.returncode})")

                    except Exception as e:
                        self.logger.debug(f"Could not check {device}: {e}")

            report["status"] = "inspected"
            self.logger.info(f"✓ Comprehensive inspection completed for {image_path.name}")

        except Exception as e:
            report["status"] = "inspection_failed"
            report["error"] = str(e)
            self.logger.error(f"Disk inspection failed: {e}")
            raise RuntimeError(f"Disk inspection failed for {image_path.name}: {e}") from e

        finally:
            # Cleanup: deactivate LVM and disconnect NBD
            if activate_lvm and check_lvm:
                try:
                    run_sudo(
                        self.logger,
                        ["vgchange", "-an"],
                        check=False,
                        capture=True,
                        failure_log_level=logging.DEBUG
                    )
                    self.logger.debug("Deactivated LVM volume groups")
                except Exception as e:
                    self.logger.debug(f"Could not deactivate VGs: {e}")

            if temp_nbd:
                try:
                    run_sudo(
                        self.logger,
                        ["qemu-nbd", "--disconnect", temp_nbd],
                        check=False,
                        capture=True
                    )
                    self.logger.debug(f"Disconnected inspection NBD: {temp_nbd}")
                except Exception as e:
                    self.logger.debug(f"Could not disconnect {temp_nbd}: {e}")

        return report

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

        # Validate image integrity before attempting connection
        self._validate_image(image_path)

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

            # Provide helpful error message for common VMDK issues
            error_str = str(e)
            if "invalid VMDK image descriptor" in error_str:
                # User provided -flat.vmdk instead of descriptor file
                if str(image_path).endswith("-flat.vmdk"):
                    raise RuntimeError(
                        f"Cannot open '{image_path}': This is a VMDK data file (-flat.vmdk).\n"
                        f"You need the descriptor file (without -flat suffix).\n"
                        f"Expected file: {str(image_path).replace('-flat.vmdk', '.vmdk')}"
                    ) from None
                else:
                    raise RuntimeError(
                        f"Invalid VMDK descriptor in '{image_path}'.\n"
                        f"The VMDK descriptor file may be corrupted or in an unsupported format."
                    ) from None

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
            # Clean up temporary converted qcow2 if it exists (unless marked to keep)
            if self._converted_qcow2_path and self._converted_qcow2_path.exists():
                if self._keep_converted:
                    self.logger.info(f"Keeping converted qcow2: {self._converted_qcow2_path}")
                else:
                    try:
                        self.logger.info(f"Removing temporary converted qcow2: {self._converted_qcow2_path}")
                        self._converted_qcow2_path.unlink()
                        self.logger.info(f"✓ Cleaned up {self._converted_qcow2_path.name}")
                    except Exception as cleanup_error:
                        self.logger.warning(f"Failed to remove temp qcow2: {cleanup_error}")

            self._nbd_device = None
            self._connected = False
            self._nbd_process = None
            if not self._keep_converted:
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
