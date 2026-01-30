# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/vmcraft/storage.py
"""
Storage stack activation for LVM, LUKS, mdraid, and ZFS.

Mirrors existing OfflineMountEngine patterns but uses native Linux tools
instead of libguestfs.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from ._utils import run_sudo


logger = logging.getLogger(__name__)


def _has_command(cmd: str) -> bool:
    """Check if command is available in PATH."""
    return shutil.which(cmd) is not None


class LVMActivator:
    """
    LVM (Logical Volume Manager) activation.

    Scans for volume groups and activates logical volumes.
    """

    @staticmethod
    def activate(logger: logging.Logger) -> dict[str, Any]:
        """
        Activate LVM volumes.

        Returns:
            Audit dict: {"attempted": bool, "ok": bool, "error": str | None}
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None}

        if not _has_command("vgscan") or not _has_command("vgchange"):
            audit["error"] = "lvm_tools_not_available"
            return audit

        audit["attempted"] = True

        try:
            # Deactivate any stale volume groups first
            run_sudo(logger, ["vgchange", "-an"], check=False, capture=True)

            # Refresh physical volume cache (critical for NBD device changes)
            if _has_command("pvscan"):
                run_sudo(logger, ["pvscan", "--cache"], check=True, capture=True)

            # Scan for volume groups with cache refresh
            run_sudo(logger, ["vgscan", "--cache"], check=True, capture=True)

            # Activate all volume groups
            run_sudo(logger, ["vgchange", "-ay"], check=True, capture=True)

            audit["ok"] = True
            logger.info("LVM volumes activated successfully")
            return audit

        except Exception as e:
            audit["error"] = str(e)
            logger.warning(f"LVM activation failed: {e}")
            return audit

    @staticmethod
    def list_logical_volumes(logger: logging.Logger) -> list[str]:
        """
        List logical volumes.

        Returns:
            List of LV device paths (e.g., ['/dev/mapper/vg-lv'])
        """
        try:
            # Use lvs with JSON output for structured parsing
            result = run_sudo(
                logger,
                ["lvs", "--reportformat", "json", "--noheadings"],
                check=True,
                capture=True
            )

            data = json.loads(result.stdout)
            lvs_data = data.get("report", [{}])[0].get("lv", [])

            devices = []
            for lv in lvs_data:
                vg_name = lv.get("vg_name", "")
                lv_name = lv.get("lv_name", "")
                if vg_name and lv_name:
                    devices.append(f"/dev/mapper/{vg_name}-{lv_name}")

            return devices

        except Exception as e:
            logger.warning(f"Failed to list logical volumes: {e}")
            return []


class LVMCreator:
    """
    LVM creation and management operations.

    Creates physical volumes, volume groups, and logical volumes.
    Complements LVMActivator which only activates existing LVM structures.
    """

    @staticmethod
    def pvcreate(logger: logging.Logger, devices: list[str]) -> dict[str, Any]:
        """
        Create physical volumes.

        Args:
            logger: Logger instance
            devices: List of device paths to initialize as PVs

        Returns:
            Audit dict with created PV list

        Example:
            result = LVMCreator.pvcreate(logger, ["/dev/nbd0p1"])
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "pvs": []}

        if not _has_command("pvcreate"):
            audit["error"] = "lvm_tools_not_available"
            return audit

        if not devices:
            audit["error"] = "no_devices_provided"
            return audit

        audit["attempted"] = True

        try:
            cmd = ["pvcreate", "-f"] + devices
            run_sudo(logger, cmd, check=True, capture=True)

            audit["ok"] = True
            audit["pvs"] = devices
            logger.info(f"Created physical volumes: {devices}")
            return audit

        except Exception as e:
            audit["error"] = str(e)
            logger.warning(f"PV creation failed: {e}")
            return audit

    @staticmethod
    def vgcreate(logger: logging.Logger, vgname: str, pvs: list[str]) -> dict[str, Any]:
        """
        Create volume group.

        Args:
            logger: Logger instance
            vgname: Volume group name
            pvs: List of physical volumes

        Returns:
            Audit dict with VG name

        Example:
            result = LVMCreator.vgcreate(logger, "test_vg", ["/dev/nbd0p1"])
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "vg": None}

        if not _has_command("vgcreate"):
            audit["error"] = "lvm_tools_not_available"
            return audit

        if not vgname or not pvs:
            audit["error"] = "invalid_parameters"
            return audit

        audit["attempted"] = True

        try:
            cmd = ["vgcreate", vgname] + pvs
            run_sudo(logger, cmd, check=True, capture=True)

            audit["ok"] = True
            audit["vg"] = vgname
            logger.info(f"Created volume group: {vgname}")
            return audit

        except Exception as e:
            audit["error"] = str(e)
            logger.warning(f"VG creation failed: {e}")
            return audit

    @staticmethod
    def lvcreate(
        logger: logging.Logger,
        lvname: str,
        vgname: str,
        size_mb: int | None = None,
        extents: str | None = None
    ) -> dict[str, Any]:
        """
        Create logical volume.

        Args:
            logger: Logger instance
            lvname: Logical volume name
            vgname: Volume group name
            size_mb: Size in megabytes (mutually exclusive with extents)
            extents: Size in extents (e.g., "100%FREE")

        Returns:
            Audit dict with LV path

        Example:
            # Create LV with specific size
            result = LVMCreator.lvcreate(logger, "data", "vg0", size_mb=1024)

            # Create LV using all free space
            result = LVMCreator.lvcreate(logger, "data", "vg0", extents="100%FREE")
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "lv": None}

        if not _has_command("lvcreate"):
            audit["error"] = "lvm_tools_not_available"
            return audit

        if not lvname or not vgname:
            audit["error"] = "invalid_parameters"
            return audit

        if not size_mb and not extents:
            audit["error"] = "size_mb or extents required"
            return audit

        if size_mb and extents:
            audit["error"] = "size_mb and extents are mutually exclusive"
            return audit

        audit["attempted"] = True

        try:
            cmd = ["lvcreate", "-n", lvname]

            if size_mb:
                cmd.extend(["-L", f"{size_mb}M"])
            elif extents:
                cmd.extend(["-l", extents])

            cmd.append(vgname)

            run_sudo(logger, cmd, check=True, capture=True)

            lv_path = f"/dev/{vgname}/{lvname}"
            audit["ok"] = True
            audit["lv"] = lv_path
            logger.info(f"Created logical volume: {lv_path}")
            return audit

        except Exception as e:
            audit["error"] = str(e)
            logger.warning(f"LV creation failed: {e}")
            return audit

    @staticmethod
    def lvresize(logger: logging.Logger, lvpath: str, size_mb: int) -> dict[str, Any]:
        """
        Resize logical volume.

        Args:
            logger: Logger instance
            lvpath: LV device path (e.g., "/dev/vg0/data")
            size_mb: New size in megabytes

        Returns:
            Audit dict

        Example:
            result = LVMCreator.lvresize(logger, "/dev/vg0/data", 2048)
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None}

        if not _has_command("lvresize"):
            audit["error"] = "lvm_tools_not_available"
            return audit

        if not lvpath or size_mb <= 0:
            audit["error"] = "invalid_parameters"
            return audit

        audit["attempted"] = True

        try:
            cmd = ["lvresize", "-L", f"{size_mb}M", lvpath]
            run_sudo(logger, cmd, check=True, capture=True)

            audit["ok"] = True
            logger.info(f"Resized LV {lvpath} to {size_mb}M")
            return audit

        except Exception as e:
            audit["error"] = str(e)
            logger.warning(f"LV resize failed: {e}")
            return audit

    @staticmethod
    def lvremove(logger: logging.Logger, lvpath: str, force: bool = False) -> dict[str, Any]:
        """
        Remove logical volume.

        Args:
            logger: Logger instance
            lvpath: LV device path
            force: Force removal without confirmation

        Returns:
            Audit dict

        Example:
            result = LVMCreator.lvremove(logger, "/dev/vg0/data", force=True)
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None}

        if not _has_command("lvremove"):
            audit["error"] = "lvm_tools_not_available"
            return audit

        if not lvpath:
            audit["error"] = "invalid_parameters"
            return audit

        audit["attempted"] = True

        try:
            cmd = ["lvremove"]
            if force:
                cmd.append("-f")
            cmd.append(lvpath)

            run_sudo(logger, cmd, check=True, capture=True)

            audit["ok"] = True
            logger.info(f"Removed LV {lvpath}")
            return audit

        except Exception as e:
            audit["error"] = str(e)
            logger.warning(f"LV removal failed: {e}")
            return audit

    @staticmethod
    def vgremove(logger: logging.Logger, vgname: str, force: bool = False) -> dict[str, Any]:
        """
        Remove volume group.

        Args:
            logger: Logger instance
            vgname: Volume group name
            force: Force removal without confirmation

        Returns:
            Audit dict

        Example:
            result = LVMCreator.vgremove(logger, "vg0", force=True)
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None}

        if not _has_command("vgremove"):
            audit["error"] = "lvm_tools_not_available"
            return audit

        if not vgname:
            audit["error"] = "invalid_parameters"
            return audit

        audit["attempted"] = True

        try:
            cmd = ["vgremove"]
            if force:
                cmd.append("-f")
            cmd.append(vgname)

            run_sudo(logger, cmd, check=True, capture=True)

            audit["ok"] = True
            logger.info(f"Removed VG {vgname}")
            return audit

        except Exception as e:
            audit["error"] = str(e)
            logger.warning(f"VG removal failed: {e}")
            return audit


class LUKSUnlocker:
    """
    LUKS (Linux Unified Key Setup) encryption unlocking.

    Detects and unlocks LUKS-encrypted devices.
    """

    def __init__(
        self,
        logger: logging.Logger,
        *,
        luks_enable: bool = False,
        luks_passphrase: str | None = None,
        luks_passphrase_env: str | None = None,
        luks_keyfile: Path | None = None,
        luks_mapper_prefix: str = "hyper2kvm-crypt",
    ):
        """
        Initialize LUKS unlocker.

        Args:
            logger: Logger instance
            luks_enable: Enable LUKS unlocking
            luks_passphrase: Direct passphrase
            luks_passphrase_env: Environment variable containing passphrase
            luks_keyfile: Path to key file
            luks_mapper_prefix: Prefix for mapper device names
        """
        self.logger = logger
        self.luks_enable = bool(luks_enable)
        self.luks_passphrase = luks_passphrase
        self.luks_passphrase_env = luks_passphrase_env
        self.luks_keyfile = Path(luks_keyfile) if luks_keyfile else None
        self.luks_mapper_prefix = luks_mapper_prefix
        self._luks_opened: dict[str, str] = {}  # device -> mapper_name

    def _read_luks_key_bytes(self) -> bytes | None:
        """Read LUKS key material from keyfile or passphrase."""
        try:
            if self.luks_keyfile and self.luks_keyfile.exists():
                return self.luks_keyfile.read_bytes()
        except Exception:
            pass

        pw = self.luks_passphrase
        if (not pw) and self.luks_passphrase_env:
            pw = os.environ.get(self.luks_passphrase_env)
        if pw:
            return pw.encode("utf-8")
        return None

    def _detect_luks_devices(self) -> list[str]:
        """
        Detect LUKS-encrypted devices using blkid.

        Returns:
            List of device paths with LUKS encryption
        """
        try:
            # Use blkid to find LUKS devices
            result = run_sudo(
                self.logger,
                ["blkid", "-t", "TYPE=crypto_LUKS", "-o", "device"],
                check=True,
                capture=True
            )

            devices = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            return devices

        except Exception as e:
            self.logger.warning(f"Failed to detect LUKS devices: {e}")
            return []

    def unlock(self, lvm_activator: LVMActivator | None = None) -> dict[str, Any]:
        """
        Unlock LUKS devices.

        Args:
            lvm_activator: LVM activator to re-run after unlocking (LUKS may contain LVM)

        Returns:
            Audit dict with detailed unlock results
        """
        audit: dict[str, Any] = {
            "attempted": False,
            "configured": False,
            "enabled": bool(self.luks_enable),
            "passphrase_env": self.luks_passphrase_env,
            "keyfile": str(self.luks_keyfile) if self.luks_keyfile else None,
            "luks_devices": [],
            "opened": [],
            "skipped": [],
            "errors": [],
        }

        if not self.luks_enable:
            audit["skipped"].append("luks_disabled")
            return audit

        key_bytes = self._read_luks_key_bytes()
        audit["configured"] = bool(key_bytes)
        if not key_bytes:
            audit["skipped"].append("no_key_material_configured")
            return audit

        if not _has_command("cryptsetup"):
            audit["errors"].append("cryptsetup_not_available")
            return audit

        luks_devs = self._detect_luks_devices()
        audit["luks_devices"] = luks_devs
        if not luks_devs:
            audit["skipped"].append("no_crypto_LUKS_devices_found")
            return audit

        audit["attempted"] = True

        for idx, dev in enumerate(luks_devs, 1):
            if dev in self._luks_opened:
                continue

            name = f"{self.luks_mapper_prefix}{idx}"

            try:
                # Write key to temp file for cryptsetup
                with tempfile.NamedTemporaryFile(mode='wb', delete=False) as key_file:
                    key_file.write(key_bytes)
                    key_file_path = key_file.name

                try:
                    # Open LUKS device
                    run_sudo(
                        self.logger,
                        ["cryptsetup", "open", dev, name, "--key-file", key_file_path],
                        check=True,
                        capture=True
                    )

                    mapped = f"/dev/mapper/{name}"
                    self._luks_opened[dev] = mapped
                    audit["opened"].append({"device": dev, "mapped": mapped})
                    self.logger.info(f"LUKS: opened {dev} -> {mapped}")

                finally:
                    # Clean up temp key file
                    try:
                        os.unlink(key_file_path)
                    except Exception:
                        pass

            except Exception as e:
                audit["errors"].append({"device": dev, "error": str(e)})
                self.logger.warning(f"LUKS: failed to open {dev}: {e}")

        # After opening LUKS, LVM may appear
        if audit["opened"] and lvm_activator:
            _ = lvm_activator.activate(self.logger)

        return audit

    def get_opened_devices(self) -> dict[str, str]:
        """Get dict of opened LUKS devices (device -> mapper_path)."""
        return self._luks_opened.copy()


class MDRaidAssembler:
    """
    MD RAID (Software RAID) assembler.

    Assembles mdraid arrays using mdadm.
    """

    @staticmethod
    def activate(logger: logging.Logger) -> dict[str, Any]:
        """
        Activate mdraid arrays.

        Returns:
            Audit dict: {"attempted": bool, "ok": bool, "details": str, "error": str | None}
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "details": "", "error": None}

        if not _has_command("mdadm"):
            audit["details"] = "mdadm_not_available"
            return audit

        audit["attempted"] = True

        try:
            # Assemble all arrays (log failures as DEBUG since "no arrays" is common)
            run_sudo(
                logger,
                ["mdadm", "--assemble", "--scan", "--run"],
                check=True,
                capture=True,
                failure_log_level=logging.DEBUG
            )

            audit["ok"] = True
            audit["details"] = "mdadm_assemble_scan_ok"
            logger.info("mdraid arrays assembled successfully")
            return audit

        except Exception as e:
            audit["error"] = str(e)
            audit["details"] = "mdadm_assemble_scan_failed"
            logger.debug(f"mdraid assembly failed (expected if no RAID): {e}")
            return audit


class ZFSImporter:
    """
    ZFS pool importer.

    Imports ZFS pools without mounting datasets.
    """

    @staticmethod
    def activate(logger: logging.Logger) -> dict[str, Any]:
        """
        Import ZFS pools.

        Returns:
            Audit dict: {"attempted": bool, "ok": bool, "pools": list, "error": str | None}
        """
        if not _has_command("zpool"):
            return {"attempted": False, "ok": False, "reason": "zpool_not_available"}

        audit: dict[str, Any] = {"attempted": True, "ok": False, "pools": [], "error": None}

        try:
            # List available pools
            result = run_sudo(
                logger,
                ["sh", "-lc", "ZPOOL_VDEV_NAME_PATH=1 zpool import 2>/dev/null || true"],
                check=False,
                capture=True
            )
            text = result.stdout.strip()
            audit["pools"] = [ln.strip() for ln in text.splitlines() if ln.strip()][:100]

        except Exception:
            pass

        try:
            # Import all pools without mounting (-N flag)
            run_sudo(
                logger,
                ["sh", "-lc", "ZPOOL_VDEV_NAME_PATH=1 zpool import -a -N -f 2>/dev/null || true"],
                check=False,
                capture=True
            )

            audit["ok"] = True
            logger.info("ZFS pools imported successfully")
            return audit

        except Exception as e:
            audit["error"] = str(e)
            logger.warning(f"ZFS import failed: {e}")
            return audit


class StorageStackActivator:
    """
    Composite storage stack activator.

    Activates all storage layers in correct order:
    1. mdraid (software RAID)
    2. ZFS pools
    3. LVM volume groups
    4. LUKS encrypted devices (which may contain LVM)
    """

    def __init__(
        self,
        logger: logging.Logger,
        *,
        luks_enable: bool = False,
        luks_passphrase: str | None = None,
        luks_passphrase_env: str | None = None,
        luks_keyfile: Path | None = None,
        luks_mapper_prefix: str = "hyper2kvm-crypt",
    ):
        """
        Initialize storage stack activator.

        Args:
            logger: Logger instance
            luks_enable: Enable LUKS unlocking
            luks_passphrase: Direct passphrase for LUKS
            luks_passphrase_env: Environment variable containing passphrase
            luks_keyfile: Path to LUKS key file
            luks_mapper_prefix: Prefix for LUKS mapper device names
        """
        self.logger = logger
        self.luks_unlocker = LUKSUnlocker(
            logger,
            luks_enable=luks_enable,
            luks_passphrase=luks_passphrase,
            luks_passphrase_env=luks_passphrase_env,
            luks_keyfile=luks_keyfile,
            luks_mapper_prefix=luks_mapper_prefix,
        )

    def activate_all(self) -> dict[str, Any]:
        """
        Activate entire storage stack.

        Returns:
            Audit dict: {"mdraid": dict, "zfs": dict, "lvm": dict, "luks": dict}
        """
        audit: dict[str, Any] = {"mdraid": None, "zfs": None, "lvm": None, "luks": None}

        # Order matters: mdraid -> ZFS -> LVM -> LUKS (which may reveal more LVM)
        audit["mdraid"] = MDRaidAssembler.activate(self.logger)
        audit["zfs"] = ZFSImporter.activate(self.logger)

        lvm_activator = LVMActivator()
        audit["lvm"] = lvm_activator.activate(self.logger)

        # LUKS last because it may contain LVM
        audit["luks"] = self.luks_unlocker.unlock(lvm_activator=lvm_activator)

        return audit
