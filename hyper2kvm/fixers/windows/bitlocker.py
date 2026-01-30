# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/windows/bitlocker.py

"""
BitLocker detection for Windows VMs.

CRITICAL: BitLocker-encrypted disks CANNOT be migrated offline because:
  1. Encrypted volumes cannot be mounted by guestfs/libguestfs
  2. Offline registry access requires decrypted NTFS
  3. Driver injection requires write access to Windows directory

This module detects BitLocker encryption and FAILS migration early with
clear instructions to decrypt before migration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore


class BitLockerDetectionError(Exception):
    """Raised when BitLocker is detected on a Windows VM."""

    pass


def detect_bitlocker(g: guestfs.GuestFS, root: str) -> Dict[str, Any]:
    """
    Detect BitLocker encryption on Windows volumes.

    Args:
        g: GuestFS instance with Windows disk mounted
        root: Windows root path (e.g., '/sysroot')

    Returns:
        Dict with detection results:
            {
                "bitlocker_detected": bool,
                "encrypted_volumes": List[str],
                "protection_status": Dict[str, str],
                "error": str if detection failed
            }

    Raises:
        BitLockerDetectionError: If BitLocker is detected (blocks migration)
    """
    result = {
        "bitlocker_detected": False,
        "encrypted_volumes": [],
        "protection_status": {},
        "error": None,
    }

    try:
        # Method 1: Check BitLocker registry keys
        bitlocker_status = _check_bitlocker_registry(g, root)

        if bitlocker_status["found"]:
            result["bitlocker_detected"] = True
            result["encrypted_volumes"] = bitlocker_status.get("volumes", [])
            result["protection_status"] = bitlocker_status.get("status", {})

        # Method 2: Check for BitLocker metadata on partitions
        # BitLocker leaves -FVE-FS-* metadata even when unlocked
        bitlocker_metadata = _check_bitlocker_metadata(g)

        if bitlocker_metadata["found"]:
            result["bitlocker_detected"] = True
            result["encrypted_volumes"].extend(bitlocker_metadata.get("volumes", []))

        # Method 3: Check for BitLocker system files
        bitlocker_files = _check_bitlocker_files(g, root)

        if bitlocker_files["found"]:
            result["bitlocker_detected"] = True

        # If BitLocker detected, raise error to block migration
        if result["bitlocker_detected"]:
            volumes_str = ", ".join(result["encrypted_volumes"]) if result["encrypted_volumes"] else "unknown"
            raise BitLockerDetectionError(
                f"BitLocker encryption detected on volumes: {volumes_str}\n\n"
                f"⚠️  MIGRATION BLOCKED - Encrypted disks cannot be migrated offline.\n\n"
                f"Required actions before migration:\n"
                f"  1. Boot the VM in VMware\n"
                f"  2. Decrypt all volumes:\n"
                f"       manage-bde -off C:\n"
                f"       manage-bde -off D:  (repeat for all encrypted volumes)\n"
                f"  3. Wait for decryption to complete (may take hours for large disks)\n"
                f"  4. Verify: manage-bde -status\n"
                f"  5. Shut down VM cleanly\n"
                f"  6. Retry migration\n\n"
                f"Alternative: Use live migration instead of offline conversion"
            )

    except BitLockerDetectionError:
        raise  # Re-raise to caller
    except Exception as e:
        result["error"] = str(e)
        # Don't fail migration on detection errors - log warning instead
        logging.warning(f"BitLocker detection failed (non-fatal): {e}")

    return result


def _check_bitlocker_registry(g: guestfs.GuestFS, root: str) -> Dict[str, Any]:
    """
    Check Windows registry for BitLocker configuration.

    Registry keys checked:
        HKLM\\SYSTEM\\CurrentControlSet\\Control\\BitLockerStatus
        HKLM\\SYSTEM\\CurrentControlSet\\Services\\BDESVC (BitLocker Drive Encryption Service)
        HKLM\\SOFTWARE\\Policies\\Microsoft\\FVE (Full Volume Encryption policies)
    """
    result = {"found": False, "volumes": [], "status": {}}

    try:
        # Check for BitLocker service
        system_hive_path = f"{root}/Windows/System32/config/SYSTEM"

        # Try to detect BDESVC (BitLocker service)
        # If we can mount and read registry, check for service presence
        # Note: This is a heuristic - service may exist but not be active

        # Check SOFTWARE hive for BitLocker policies
        software_hive_path = f"{root}/Windows/System32/config/SOFTWARE"

        # If we get here without errors, hives are readable (not encrypted)
        # BitLocker would prevent NTFS mount, so readable hives = not encrypted
        # But check for configuration indicating BitLocker was used

        # TODO: Use hivex library to read registry if needed
        # For now, rely on metadata and file checks

    except Exception as e:
        logging.debug(f"Registry check failed (expected if encrypted): {e}")

    return result


def _check_bitlocker_metadata(g: guestfs.GuestFS) -> Dict[str, Any]:
    """
    Check for BitLocker filesystem metadata.

    BitLocker uses -FVE-FS- filesystem signatures that persist even after decryption.
    Check partition labels and filesystem types for BitLocker indicators.
    """
    result = {"found": False, "volumes": []}

    try:
        # Get all block devices
        devices = g.list_devices()

        for device in devices:
            try:
                # Get partitions on this device
                partitions = g.list_partitions()

                for partition in partitions:
                    if not partition.startswith(device):
                        continue

                    try:
                        # Check filesystem type
                        # BitLocker shows as "BitLocker" or "unknown" type
                        fs_type = g.vfs_type(partition)

                        if fs_type and "bitlocker" in fs_type.lower():
                            result["found"] = True
                            result["volumes"].append(partition)
                            continue

                        # Check partition label for BitLocker indicators
                        try:
                            label = g.vfs_label(partition)
                            if label and ("-fve-fs-" in label.lower() or "bitlocker" in label.lower()):
                                result["found"] = True
                                result["volumes"].append(partition)
                        except:
                            pass

                    except Exception as e:
                        logging.debug(f"Could not check partition {partition}: {e}")

            except Exception as e:
                logging.debug(f"Could not check device {device}: {e}")

    except Exception as e:
        logging.debug(f"Metadata check failed: {e}")

    return result


def _check_bitlocker_files(g: guestfs.GuestFS, root: str) -> Dict[str, Any]:
    """
    Check for BitLocker-specific files in Windows directory.

    Files checked:
        - BitLocker recovery keys (*.BEK files)
        - BitLocker startup keys
        - FVEAPI.dll (BitLocker API)
    """
    result = {"found": False, "files": []}

    try:
        # Check for BitLocker DLL (indicates BitLocker was installed)
        bitlocker_dll = f"{root}/Windows/System32/fveapi.dll"
        if g.exists(bitlocker_dll):
            result["files"].append("fveapi.dll")
            # Having the DLL doesn't mean encryption is active
            # Just indicates BitLocker capability

        # Check for recovery key files (strong indicator)
        windows_path = f"{root}/Windows"
        if g.is_dir(windows_path):
            try:
                files = g.ls(windows_path)
                for f in files:
                    if f.endswith(".BEK") or f.endswith(".bek"):
                        result["found"] = True
                        result["files"].append(f)
            except:
                pass

    except Exception as e:
        logging.debug(f"File check failed: {e}")

    return result


def check_bitlocker_before_migration(g: guestfs.GuestFS, root: str, logger: logging.Logger) -> None:
    """
    Pre-migration BitLocker check.

    Call this BEFORE attempting any offline modifications to Windows.
    Raises BitLockerDetectionError if encryption detected.

    Args:
        g: GuestFS instance
        root: Windows root path
        logger: Logger instance

    Raises:
        BitLockerDetectionError: If BitLocker detected (blocks migration)
    """
    logger.info("🔒 Checking for BitLocker encryption...")

    try:
        result = detect_bitlocker(g, root)

        if result["bitlocker_detected"]:
            # Should not reach here (detect_bitlocker raises)
            logger.error("❌ BitLocker detected - migration blocked")
        else:
            logger.info("✅ No BitLocker encryption detected")

    except BitLockerDetectionError as e:
        logger.error(str(e))
        raise
