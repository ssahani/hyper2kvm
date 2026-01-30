# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/offline_fixer.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import contextlib
import datetime as _dt
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...

from ..core.guestfs_factory import create_guestfs

from .. import __version__
from ..core.recovery_manager import RecoveryManager
from ..core.utils import U, blinking_progress, guest_has_cmd
from ..core.vmcraft._utils import run_sudo
from ..core.validation_suite import ValidationSuite
from . import network_fixer  # type: ignore
from .bootloader import grub as grub_fixer  # type: ignore

# Delegated fixers (keep OfflineFSFix "thin")
from .filesystem import fixer as filesystem_fixer  # type: ignore
from .filesystem.fstab import (
    Change,
    FstabMode,
    parse_btrfsvol_spec,
)
from .offline.config_rewriter import FstabCrypttabRewriter

# Extracted modules for focused functionality
from .offline.spec_converter import SpecConverter
from .offline.validation import OfflineValidationManager
from .offline.vmware_tools_remover import OfflineVmwareToolsRemover
from .report_writer import write_report
from .windows import fixer as windows_fixer  # type: ignore
from . import firstboot_injector  # type: ignore
from . import network_config_injector  # type: ignore
from . import user_config_injector  # type: ignore
from . import service_config_injector  # type: ignore
from . import hostname_config_injector  # type: ignore

_T = TypeVar("_T")


# VMware removal result wrapper (report-friendly)
@dataclass
class VmwareRemovalResult:
    enabled: bool = True
    removed_paths: list[str] = field(default_factory=list)
    removed_services: list[str] = field(default_factory=list)
    removed_symlinks: list[str] = field(default_factory=list)
    package_hints: list[str] = field(default_factory=list)
    touched_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "removed_paths": self.removed_paths,
            "removed_services": self.removed_services,
            "removed_symlinks": self.removed_symlinks,
            "package_hints": self.package_hints,
            "touched_files": self.touched_files,
            "warnings": self.warnings,
            "notes": self.notes,
            "errors": self.errors,
            "counts": {
                "removed_paths": len(self.removed_paths),
                "removed_services": len(self.removed_services),
                "removed_symlinks": len(self.removed_symlinks),
                "package_hints": len(self.package_hints),
                "touched_files": len(self.touched_files),
                "warnings": len(self.warnings),
                "notes": len(self.notes),
                "errors": len(self.errors),
            },
        }


# OfflineFSFix (thin orchestrator)
class OfflineFSFix:
    """
    Offline guest fix engine (thin orchestrator):
      - robust root detection + safe mount
      - rewrite fstab/crypttab -> stable IDs
      - optional filesystem fixer pass (delegated)
      - network config sanitization (delegated)
      - grub root/device.map + regen (delegated)
      - Windows hooks (delegated)
      - VMware tools removal (mounted-tree remover)
      - report + recovery checkpoints
      - FULL LUKS support: unlock + map + LVM activation + audit

    Additive storage-stack support:
      - mdraid assemble (mdadm --assemble --scan --run) if available in appliance
      - best-effort ZFS import if zpool exists in appliance
      - stronger brute-force root choice via scoring (multi-root safety)
    """

    _BTRFS_COMMON_SUBVOLS = ["@", "@/", "@root", "@rootfs", "@/.snapshots/1/snapshot"]
    _ROOT_HINT_FILES = ["/etc/fstab", "/etc/os-release", "/bin/sh", "/sbin/init"]
    _ROOT_STRONG_HINTS = ["/etc/passwd", "/usr/bin/env", "/var/lib", "/proc"]  # heuristic only

    def __init__(
        self,
        logger: logging.Logger,
        image: Path,
        *,
        dry_run: bool,
        no_backup: bool,
        print_fstab: bool,
        update_grub: bool,
        regen_initramfs: bool,
        fstab_mode: str,
        report_path: Path | None,
        remove_vmware_tools: bool = False,
        inject_cloud_init: dict[str, Any] | None = None,
        firstboot_scripts: dict[str, Any] | None = None,
        network_config_inject: dict[str, Any] | None = None,
        user_config_inject: dict[str, Any] | None = None,
        service_config_inject: dict[str, Any] | None = None,
        hostname_config_inject: dict[str, Any] | None = None,
        recovery_manager: RecoveryManager | None = None,
        resize: str | None = None,
        virtio_drivers_dir: str | None = None,
        # ---- LUKS support (FULLY WIRED) ----
        luks_enable: bool = False,
        luks_passphrase: str | None = None,
        luks_passphrase_env: str | None = None,
        luks_keyfile: Path | None = None,
        luks_mapper_prefix: str = "hyper2kvm-crypt",
        # ---- filesystem fixer (delegated) ----
        filesystem_repair_enable: bool = False,
    ):
        self.logger = logger
        self.image = Path(image)
        self.dry_run = bool(dry_run)
        self.no_backup = bool(no_backup)
        self.print_fstab = bool(print_fstab)
        self.update_grub = bool(update_grub)
        self.regen_initramfs = bool(regen_initramfs)
        self.fstab_mode = FstabMode(fstab_mode)
        self.report_path = Path(report_path) if report_path else None
        self.remove_vmware_tools = bool(remove_vmware_tools)
        self.inject_cloud_init_data = inject_cloud_init or {}
        self.firstboot_config = firstboot_scripts or {}
        self.network_config_inject = network_config_inject or {}
        self.user_config_inject = user_config_inject or {}
        self.service_config_inject = service_config_inject or {}
        self.hostname_config_inject = hostname_config_inject or {}
        self.recovery_manager = recovery_manager
        self.resize = resize
        self.virtio_drivers_dir = virtio_drivers_dir

        # LUKS configuration
        self.luks_enable = bool(luks_enable)
        self.luks_passphrase = luks_passphrase
        self.luks_passphrase_env = luks_passphrase_env
        self.luks_keyfile = Path(luks_keyfile) if luks_keyfile else None
        self.luks_mapper_prefix = luks_mapper_prefix
        self._luks_opened: dict[str, str] = {}  # luks_dev -> /dev/mapper/name

        # Storage stack activation tracking (prevent redundant activations)
        self._lvm_activated: bool = False

        # Filesystem fixer flag (avoid shadowing method name)
        self.filesystem_repair_enable = bool(filesystem_repair_enable)

        self.inspect_root: str | None = None
        self.root_dev: str | None = None
        self.root_btrfs_subvol: str | None = None
        self.converted_image_path: Path | None = None  # Path to converted qcow2 if created

        self.report: dict[str, Any] = {
            "tool": "hyper2kvm",
            "version": __version__,
            "image": str(self.image),
            "dry_run": self.dry_run,
            "changes": {},
            "analysis": {},
            "timestamps": {"start": _dt.datetime.now().isoformat()},
        }

        # Timings/metrics stash
        self._timings: dict[str, float] = {}

        # Initialize helper modules (composition over inheritance)
        self._spec_converter = SpecConverter(
            fstab_mode=self.fstab_mode,
            root_dev=None,  # Will be set after root detection
        )
        self._config_rewriter = FstabCrypttabRewriter(
            logger=self.logger,
            spec_converter=self._spec_converter,
            dry_run=self.dry_run,
            no_backup=self.no_backup,
            print_fstab=self.print_fstab,
            fstab_mode=self.fstab_mode,
        )
        self._validation_manager = OfflineValidationManager(logger=self.logger)

    # stage runner (timing + per-stage error capture)
    @contextlib.contextmanager
    def _time_stage(self, name: str) -> Any:
        t0 = time.time()
        try:
            yield
        finally:
            dt = time.time() - t0
            self._timings[name] = dt
            try:
                self.report.setdefault("analysis", {}).setdefault("stages", {})[name] = {
                    "duration_s": round(dt, 6),
                }
            except Exception as e:
                self.logger.debug(f"Failed to record stage timing for {name}: {e}")

    def _run_stage(
        self,
        name: str,
        fn: Callable[[], _T],
        *,
        critical: bool = False,
        default: _T | None = None,
    ) -> _T:
        """
        Run a stage, capture duration, and write a structured entry into report.
        - critical=True re-raises on failure (preserving existing "fail fast" semantics where needed)
        - critical=False returns default and records error (keeps report complete)
        """
        self.logger.debug(f"Stage start: {name}")
        with self._time_stage(name):
            try:
                out = fn()
                try:
                    self.report.setdefault("analysis", {}).setdefault("stages", {})[name].update(
                        {"ok": True, "error": None}
                    )
                except Exception as e:
                    self.logger.debug(f"Failed to record stage success for {name}: {e}")
                self.logger.debug(f"Stage ok: {name}")
                return out
            except Exception as e:
                tb = traceback.format_exc(limit=50)
                self.logger.warning(f"Stage failed: {name}: {e}")
                try:
                    self.report.setdefault("analysis", {}).setdefault("stages", {})[name].update(
                        {"ok": False, "error": str(e), "traceback": tb}
                    )
                except Exception as e2:
                    self.logger.debug(f"Failed to record stage error for {name}: {e2}")
                if critical:
                    raise
                return default  # type: ignore[return-value]

    def _stash_guestfs_info(self, g: guestfs.GuestFS) -> None:
        info: dict[str, Any] = {}
        try:
            if hasattr(g, "version"):
                info["version"] = g.version()
        except Exception:
            pass
        try:
            if hasattr(g, "get_backend_settings"):
                info["backend_settings"] = g.get_backend_settings()
        except Exception:
            pass
        try:
            self.report.setdefault("analysis", {})["guestfs"] = info
        except Exception as e:
            self.logger.debug(f"Failed to store guestfs info in report: {e}")

    # guestfs open/close helpers
    def open(self) -> guestfs.GuestFS:
        g = create_guestfs(python_return_dict=True, backend='vmcraft')
        if self.logger.isEnabledFor(logging.DEBUG):
            try:
                g.set_trace(1)
            except Exception as e:
                self.logger.debug(f"Failed to enable guestfs trace: {e}")
        # NOTE: read-only when dry_run (prevents accidental writes).
        g.add_drive_opts(str(self.image), readonly=self.dry_run)
        g.launch()

        # Log backend info if available (VMCraft backend specific)
        if hasattr(g, 'get_backend_info'):
            try:
                backend_info = g.get_backend_info()
                self.logger.debug(f"Backend: {backend_info.get('implementation', 'unknown')}")
                if hasattr(g, 'get_performance_metrics'):
                    metrics = g.get_performance_metrics()
                    if metrics:
                        self.logger.debug(f"Launch performance: {metrics}")
            except Exception:
                pass  # Ignore if not available

        self._stash_guestfs_info(g)
        return g

    @staticmethod
    def _safe_umount_all(g: guestfs.GuestFS) -> None:
        try:
            g.umount_all()
        except Exception:
            pass

    # LUKS / LVM
    def _read_luks_key_bytes(self) -> bytes | None:
        # Keyfile wins
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

    def _activate_lvm(self, g: guestfs.GuestFS) -> None:
        # Skip if already activated (prevent redundant scans)
        if self._lvm_activated:
            self.logger.debug("LVM already activated, skipping redundant activation")
            return

        if not hasattr(g, "vgscan") or not hasattr(g, "vgchange_activate_all"):
            return
        try:
            g.vgscan()
        except Exception:
            return
        try:
            g.vgchange_activate_all(True)
            self._lvm_activated = True  # Mark as activated on success
        except Exception:
            try:
                g.vgchange_activate_all(1)
                self._lvm_activated = True  # Mark as activated on success
            except Exception:
                pass

    def _regenerate_xfs_uuids(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """
        Regenerate UUIDs for all XFS filesystems to fix duplicates.

        Critical for cloned VMware VMs which often have duplicate XFS UUIDs
        that prevent mounting. Must run BEFORE mounting any filesystems.

        Returns:
            Audit dict with regeneration results
        """
        audit: dict[str, Any] = {
            "attempted": False,
            "xfs_partitions_found": 0,
            "regenerated": [],
            "fstab_updated": False,
            "errors": [],
        }

        try:
            # Find all XFS partitions
            xfs_partitions = []
            try:
                partitions = g.list_partitions()
                for part in partitions:
                    try:
                        fstype = U.to_text(g.vfs_type(part))
                        if fstype == "xfs":
                            xfs_partitions.append(part)
                    except Exception:
                        continue
            except Exception as e:
                audit["errors"].append(f"Failed to list partitions: {e}")
                return audit

            audit["xfs_partitions_found"] = len(xfs_partitions)

            if not xfs_partitions:
                self.logger.debug("No XFS filesystems found, skipping UUID regeneration")
                return audit

            audit["attempted"] = True
            self.logger.info(f"Found {len(xfs_partitions)} XFS filesystem(s), regenerating UUIDs...")

            # Regenerate UUID for each XFS partition
            for device in xfs_partitions:
                try:
                    # Get old UUID
                    old_uuid = None
                    try:
                        old_uuid = U.to_text(g.vfs_uuid(device))
                    except Exception:
                        pass

                    if not old_uuid:
                        self.logger.debug(f"  Skipping {device}: could not read UUID")
                        continue

                    # Generate new UUID (run on HOST, not in guest chroot)
                    # At this point filesystems are unmounted, so we use host's xfs_admin
                    try:
                        run_sudo(self.logger, ["xfs_admin", "-U", "generate", device], check=True, capture=True)
                    except Exception as e:
                        error_msg = str(e).lower()
                        if "mounted" in error_msg:
                            audit["errors"].append(f"{device}: device_mounted")
                            self.logger.debug(f"  Skipping {device}: currently mounted")
                            continue
                        raise

                    # Get new UUID
                    new_uuid = None
                    try:
                        new_uuid = U.to_text(g.vfs_uuid(device))
                    except Exception:
                        pass

                    if new_uuid and new_uuid != old_uuid:
                        audit["regenerated"].append({
                            "device": device,
                            "old_uuid": old_uuid,
                            "new_uuid": new_uuid
                        })
                        self.logger.info(f"  ✓ Regenerated UUID for {device}: {old_uuid[:8]}... → {new_uuid[:8]}...")
                    else:
                        audit["errors"].append(f"{device}: could_not_read_new_uuid")

                except Exception as e:
                    audit["errors"].append(f"{device}: {str(e)}")
                    self.logger.warning(f"  ⚠️  Failed to regenerate UUID for {device}: {e}")

            if audit["regenerated"]:
                self.logger.info(f"  ✓ Successfully regenerated {len(audit['regenerated'])} XFS UUIDs")
            else:
                self.logger.info("  No UUIDs were regenerated")

        except Exception as e:
            audit["errors"].append(f"Unexpected error: {e}")
            self.logger.error(f"XFS UUID regeneration failed: {e}")

        return audit

    def _rebuild_fstab_from_disk_layout(self, g: guestfs.GuestFS, uuid_changes: list[dict[str, Any]]) -> bool:
        """
        Completely rebuild fstab when UUIDs don't match (indicates fstab from different VM).

        Uses actual device layout and new UUIDs to create a fresh, correct fstab.

        Args:
            uuid_changes: List of dicts with device, old_uuid, new_uuid

        Returns:
            True if fstab was rebuilt, False otherwise
        """
        if not uuid_changes:
            return False

        self.logger.info("🔧 Rebuilding fstab from actual disk layout...")

        try:
            # Build device-to-uuid mapping
            device_to_uuid = {change["device"]: change["new_uuid"] for change in uuid_changes}

            # Read existing fstab to understand expected mountpoints
            if not g.is_file("/etc/fstab"):
                self.logger.warning("  No /etc/fstab found")
                return False

            old_fstab = g.read_file("/etc/fstab")
            if isinstance(old_fstab, bytes):
                old_fstab = old_fstab.decode('utf-8', errors='replace')

            # Parse mountpoints from old fstab (to preserve the layout intention)
            expected_mounts = {}  # mountpoint -> (fstype, options, dump, pass)
            for line in old_fstab.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue
                parts = stripped.split()
                if len(parts) >= 4:
                    mountpoint = parts[1]
                    fstype = parts[2]
                    options = parts[3] if len(parts) > 3 else "defaults"
                    dump = parts[4] if len(parts) > 4 else "0"
                    passno = parts[5] if len(parts) > 5 else "0"
                    expected_mounts[mountpoint] = (fstype, options, dump, passno)

            self.logger.debug(f"  Expected mountpoints from old fstab: {list(expected_mounts.keys())}")

            # Determine which device should be mounted where
            # We know root is mounted already at self.root_dev
            mountpoint_to_device = {}

            if self.root_dev and "/" in expected_mounts:
                mountpoint_to_device["/"] = self.root_dev
                self.logger.debug(f"  Root: {self.root_dev} → /")

            # For other mountpoints, we need to check what's actually on each partition
            # Simplified: use partition numbering heuristics
            for device in device_to_uuid.keys():
                if device == self.root_dev:
                    continue  # Already assigned

                # Common patterns:
                # p1 or sda1 → /boot
                # p5 or sda5 → /home
                # Higher numbered partitions → data partitions

                if device.endswith('p1') or device.endswith('sda1'):
                    if "/boot" in expected_mounts and "/boot" not in mountpoint_to_device:
                        mountpoint_to_device["/boot"] = device
                        self.logger.debug(f"  Boot: {device} → /boot")
                elif device.endswith('p5') or device.endswith('sda5'):
                    if "/home" in expected_mounts and "/home" not in mountpoint_to_device:
                        mountpoint_to_device["/home"] = device
                        self.logger.debug(f"  Home: {device} → /home")

            # Build new fstab
            new_lines = []
            new_lines.append("#")
            new_lines.append("# /etc/fstab")
            new_lines.append("# Rebuilt by hyper2kvm based on actual disk UUIDs")
            new_lines.append("#")
            new_lines.append("# Accessible filesystems, by reference, are maintained under '/dev/disk/'.")
            new_lines.append("# See man pages fstab(5), findfs(8), mount(8) and/or blkid(8) for more info.")
            new_lines.append("#")

            rebuilt_count = 0

            # Add entries for known mountpoints
            for mountpoint in sorted(expected_mounts.keys()):
                if mountpoint == "none":
                    # Swap - copy from old fstab
                    for line in old_fstab.splitlines():
                        if not line.strip().startswith('#') and 'swap' in line:
                            new_lines.append(line)
                            rebuilt_count += 1
                    continue

                if mountpoint not in mountpoint_to_device:
                    self.logger.warning(f"  Could not determine device for {mountpoint}, skipping")
                    continue

                device = mountpoint_to_device[mountpoint]
                if device not in device_to_uuid:
                    self.logger.warning(f"  No UUID for device {device}, skipping")
                    continue

                uuid = device_to_uuid[device]
                fstype, options, dump, passno = expected_mounts[mountpoint]

                # Build entry
                spec = f"UUID={uuid}"
                entry = f"{spec} {mountpoint}\t{fstype}\t{options}\t{dump} {passno}"
                new_lines.append(entry)
                rebuilt_count += 1

                self.logger.info(f"  ✓ Rebuilt entry: {mountpoint} → {device} (UUID: {uuid[:8]}...)")

            if rebuilt_count == 0:
                self.logger.warning("  No entries could be rebuilt")
                return False

            # Write new fstab
            new_fstab = '\n'.join(new_lines) + '\n'

            # Write using sudo (VMCraft mounts are owned by root)
            import tempfile
            try:
                # Write to temp file first
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.fstab') as tf:
                    tf.write(new_fstab)
                    temp_path = tf.name

                # Get the actual mount path
                if hasattr(g, '_mount_root') and g._mount_root:
                    fstab_path = Path(g._mount_root) / "etc" / "fstab"
                else:
                    # Fallback: try to find mount root
                    self.logger.error("  Could not determine mount root")
                    return False

                # Backup old fstab first
                backup_path = Path(str(fstab_path) + ".hyper2kvm_backup")
                try:
                    run_sudo(self.logger, ["cp", str(fstab_path), str(backup_path)], check=True, capture=True)
                    self.logger.debug(f"  Backed up old fstab to {backup_path}")
                except Exception as e:
                    self.logger.debug(f"  Could not backup old fstab: {e}")

                # Copy temp file to fstab using sudo
                run_sudo(self.logger, ["cp", temp_path, str(fstab_path)], check=True, capture=True)

                # Cleanup temp file
                Path(temp_path).unlink()

                self.logger.info(f"  ✓ Rebuilt /etc/fstab with {rebuilt_count} entries")
                return True

            except Exception as e:
                self.logger.error(f"  Failed to write fstab: {e}")
                import traceback
                self.logger.debug(traceback.format_exc())
                return False

        except Exception as e:
            self.logger.error(f"  ⚠️  Failed to rebuild fstab: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return False

    def _update_fstab_with_new_uuids(self, g: guestfs.GuestFS, uuid_changes: list[dict[str, Any]]) -> None:
        """
        Update /etc/fstab with new UUIDs after XFS UUID regeneration.

        Uses simple direct approach: for any fstab entry with a UUID= spec,
        check if that device exists in our regenerated list and update it.

        Args:
            uuid_changes: List of dicts with device, old_uuid, new_uuid
        """
        if not uuid_changes:
            self.logger.debug("  No UUID changes to apply to fstab")
            return

        self.logger.debug(f"  Received {len(uuid_changes)} UUID changes to apply")
        for change in uuid_changes:
            self.logger.debug(f"    {change['device']}: {change['old_uuid']} → {change['new_uuid']}")

        # Build device-to-new-uuid mapping
        device_to_new_uuid = {change["device"]: change["new_uuid"] for change in uuid_changes}
        old_uuid_to_new = {change["old_uuid"]: (change["new_uuid"], change["device"]) for change in uuid_changes}

        try:
            if not g.is_file("/etc/fstab"):
                self.logger.debug("No /etc/fstab found, skipping UUID update")
                return

            fstab_content = g.read_file("/etc/fstab")
            if isinstance(fstab_content, bytes):
                fstab_content = fstab_content.decode('utf-8', errors='replace')

            self.logger.debug(f"  Read fstab content ({len(fstab_content)} bytes, {len(fstab_content.splitlines())} lines)")

            # Show what UUIDs are currently in fstab
            fstab_uuids = set()
            for line in fstab_content.splitlines():
                if 'UUID=' in line and not line.strip().startswith('#'):
                    parts = line.strip().split()
                    if parts and parts[0].startswith('UUID='):
                        uuid_val = parts[0][5:]
                        fstab_uuids.add(uuid_val)
                        self.logger.debug(f"    fstab references UUID: {uuid_val}")

            # Try matching by old UUID first
            modified = False
            new_lines = []
            update_count = 0

            for i, line in enumerate(fstab_content.splitlines(), 1):
                new_line = line

                # Skip comments and empty lines
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    new_lines.append(new_line)
                    continue

                # Parse fstab entry
                parts = stripped.split()
                if len(parts) < 2:
                    new_lines.append(new_line)
                    continue

                fs_spec = parts[0]

                # Update UUID= entries
                if fs_spec.startswith("UUID="):
                    old_uuid_in_fstab = fs_spec[5:]

                    # Check if this is one of the old UUIDs we just changed
                    if old_uuid_in_fstab in old_uuid_to_new:
                        new_uuid, device = old_uuid_to_new[old_uuid_in_fstab]
                        new_spec = f"UUID={new_uuid}"
                        new_line = line.replace(fs_spec, new_spec, 1)
                        modified = True
                        update_count += 1
                        mountpoint = parts[1] if len(parts) > 1 else "unknown"
                        self.logger.info(f"  ✓ Updated fstab line {i} ({mountpoint}): UUID={old_uuid_in_fstab[:8]}... → UUID={new_uuid[:8]}...")
                        self.logger.debug(f"    Device: {device}")
                        self.logger.debug(f"    Old line: {line.strip()}")
                        self.logger.debug(f"    New line: {new_line.strip()}")

                new_lines.append(new_line)

            if modified:
                new_fstab = '\n'.join(new_lines) + '\n'

                # Write using sudo (VMCraft mounts are owned by root)
                import tempfile
                try:
                    # Write to temp file first
                    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.fstab') as tf:
                        tf.write(new_fstab)
                        temp_path = tf.name

                    # Get the actual mount path
                    if hasattr(g, '_mount_root') and g._mount_root:
                        fstab_path = Path(g._mount_root) / "etc" / "fstab"

                        # Backup old fstab first
                        backup_path = Path(str(fstab_path) + ".hyper2kvm_backup")
                        try:
                            run_sudo(self.logger, ["cp", str(fstab_path), str(backup_path)], check=True, capture=True)
                            self.logger.debug(f"  Backed up old fstab to {backup_path}")
                        except Exception as e:
                            self.logger.debug(f"  Could not backup old fstab: {e}")

                        # Copy temp file to fstab using sudo
                        run_sudo(self.logger, ["cp", temp_path, str(fstab_path)], check=True, capture=True)

                        # Cleanup temp file
                        Path(temp_path).unlink()

                        self.logger.info(f"  ✓ Updated /etc/fstab with {update_count} new UUID(s)")
                    else:
                        self.logger.error("  Could not determine mount root for fstab write")
                        Path(temp_path).unlink()

                except Exception as write_error:
                    self.logger.error(f"  Failed to write fstab: {write_error}")
                    if 'temp_path' in locals():
                        Path(temp_path).unlink(missing_ok=True)
            else:
                self.logger.warning("  ⚠️  fstab UUIDs don't match any regenerated UUIDs")
                self.logger.warning("  This likely means fstab is from a different VM or previous migration")
                self.logger.debug(f"  fstab UUIDs: {fstab_uuids}")
                self.logger.debug(f"  Old UUIDs we regenerated: {set(old_uuid_to_new.keys())}")
                self.logger.debug(f"  Devices with new UUIDs: {list(device_to_new_uuid.keys())}")

                # Try automatic fstab rebuild
                self.logger.info("  Attempting automatic fstab rebuild...")
                if self._rebuild_fstab_from_disk_layout(g, uuid_changes):
                    self.logger.info("  ✓ fstab successfully rebuilt from disk layout")
                else:
                    self.logger.error("  ⚠️  Automatic fstab rebuild failed - manual intervention required")

        except Exception as e:
            self.logger.error(f"  ⚠️  Failed to update fstab with new UUIDs: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())

    def _unlock_luks_devices(self, g: guestfs.GuestFS) -> dict[str, Any]:
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
        if not hasattr(g, "cryptsetup_open"):
            audit["errors"].append("guestfs_missing:cryptsetup_open")
            return audit

        try:
            fsmap = g.list_filesystems() or {}
        except Exception as e:
            audit["errors"].append(f"list_filesystems_failed:{e}")
            return audit

        luks_devs = [U.to_text(dev) for dev, fstype in fsmap.items() if U.to_text(fstype) == "crypto_LUKS"]
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
                g.cryptsetup_open(dev, name, key_bytes)
                mapped = f"/dev/mapper/{name}"
                self._luks_opened[dev] = mapped
                audit["opened"].append({"device": dev, "mapped": mapped})
                self.logger.info(f"LUKS: opened {dev} -> {mapped}")
            except Exception as e:
                audit["errors"].append({"device": dev, "error": str(e)})
                self.logger.warning(f"LUKS: failed to open {dev}: {e}")

        if audit["opened"]:
            self._activate_lvm(g)
        return audit

    # storage stack activation (mdraid/zfs) — additive
    def _guestfs_can_run(self, g: guestfs.GuestFS, prog: str) -> bool:
        try:
            return bool(getattr(g, "command", None)) and guest_has_cmd(g, prog)
        except Exception:
            return False

    def _activate_mdraid(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """
        Best-effort mdraid assembly inside the guestfs appliance.
        Helps when root lives on /dev/mdX or PV-on-md.
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "details": "", "error": None}
        if not self._guestfs_can_run(g, "mdadm"):
            audit["details"] = "mdadm_not_available_in_appliance"
            return audit
        audit["attempted"] = True
        try:
            g.command(["mdadm", "--assemble", "--scan", "--run"])
            audit["ok"] = True
            audit["details"] = "mdadm_assemble_scan_ok"
            return audit
        except Exception as e:
            audit["error"] = str(e)
            audit["details"] = "mdadm_assemble_scan_failed"
            return audit

    def _activate_zfs(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """
        Best-effort ZFS import. Harmless on non-ZFS guests.
        Depends on guestfs appliance having zpool.
        """
        if not self._guestfs_can_run(g, "zpool"):
            return {"attempted": False, "ok": False, "reason": "zpool_not_available_in_appliance"}
        audit: dict[str, Any] = {"attempted": True, "ok": False, "pools": [], "error": None}
        try:
            out = g.command(["sh", "-lc", "ZPOOL_VDEV_NAME_PATH=1 zpool import 2>/dev/null || true"])
            text = U.to_text(out).strip()
            audit["pools"] = [ln.strip() for ln in text.splitlines() if ln.strip()][:100]
        except Exception:
            pass
        try:
            # -N: do not auto-mount datasets
            g.command(["sh", "-lc", "ZPOOL_VDEV_NAME_PATH=1 zpool import -a -N -f 2>/dev/null || true"])
            audit["ok"] = True
            return audit
        except Exception as e:
            audit["error"] = str(e)
            return audit

    def _pre_mount_activate_storage_stack(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """
        Additive activation pipeline (best-effort, do-no-harm):
          - mdraid assemble
          - zfs import
          - lvm activate
        """
        audit: dict[str, Any] = {"mdraid": None, "zfs": None, "lvm": None}
        audit["mdraid"] = self._activate_mdraid(g)
        audit["zfs"] = self._activate_zfs(g)
        try:
            self._activate_lvm(g)
            audit["lvm"] = {"attempted": True, "ok": True}
        except Exception as e:
            audit["lvm"] = {"attempted": True, "ok": False, "error": str(e)}
        return audit

    # mount logic (safe + robust)
    def _mount_root_direct(self, g: guestfs.GuestFS, dev: str, subvol: str | None) -> None:
        """
        Enhanced (non-breaking): keep original behavior, but add a safe mount fallback ladder
        and a best-effort fsck pass for ext4/xfs when mount fails.

        Helps cases where guestfs mount fails with superblock/journal quirks.
        """
        filesystem_fixer.log_vfs_type_best_effort(self, g, dev)

        def _try_mount(mode: str) -> None:
            # mode: "rw" | "ro" | "opts:<csv>"
            if subvol:
                self.root_btrfs_subvol = subvol
                opts = f"subvol={subvol}"
                if self.dry_run or mode == "ro":
                    opts = f"ro, {opts}"
                if mode.startswith("opts:"):
                    extra = mode.split(":", 1)[1]
                    opts = f"{extra}, {opts}"
                g.mount_options(opts, dev, "/")
                return

            if mode == "rw" and not self.dry_run:
                g.mount(dev, "/")
                return
            if mode == "ro" or self.dry_run:
                g.mount_ro(dev, "/")
                return
            if mode.startswith("opts:"):
                opts = mode.split(":", 1)[1]
                if self.dry_run and "ro" not in opts:
                    opts = f"ro, {opts}"
                g.mount_options(opts, dev, "/")
                return

            # fallback
            g.mount_ro(dev, "/")

        # 1) original behavior path
        try:
            _try_mount("rw" if not self.dry_run else "ro")
            self.root_dev = dev
            self.logger.info(f"Mounted root at / using {dev}" + (f" (btrfs subvol={subvol})" if subvol else ""))
            return
        except Exception as e:
            first_err = e

        # 2) fallback ladder
        tries = ["ro", "opts:noload", "opts:ro, noload", "opts:ro, norecovery"]
        last_err: Exception | None = None
        for t in tries:
            self._safe_umount_all(g)
            try:
                _try_mount(t)
                self.root_dev = dev
                self.logger.info(
                    f"Mounted root at / using {dev}"
                    + (f" (btrfs subvol={subvol})" if subvol else "")
                    + f" [{t}]"
                )
                return
            except Exception as e:
                last_err = e

        # 3) best-effort fsck then retry RO once
        self._safe_umount_all(g)
        fsck_audit = filesystem_fixer.best_effort_fsck(self, g, dev)
        try:
            self.report.setdefault("analysis", {}).setdefault("mount", {})["fsck"] = fsck_audit
        except Exception as e:
            self.logger.debug(f"Failed to store fsck audit in report: {e}")

        self._safe_umount_all(g)
        try:
            _try_mount("ro")
            self.root_dev = dev
            self.logger.info(
                f"Mounted root at / using {dev}"
                + (f" (btrfs subvol={subvol})" if subvol else "")
                + " [ro-after-fsck]"
            )
            return
        except Exception as e:
            last_err = e

        raise RuntimeError(f"Failed mounting root {dev} (subvol={subvol}): {last_err or first_err}")

    def _looks_like_root(self, g: guestfs.GuestFS) -> bool:
        """
        Check if mounted filesystem looks like guest root (not /boot).

        Root signals (any one is enough):
          - /etc/os-release exists (definitive)
          - /etc exists AND (systemd or a shell exists)

        /boot signals (reject if found):
          - vmlinuz-* or initramfs-* at the top level
          - AND any of: /grub2, /grub, /efi, /loader directories
          - AND missing /etc/os-release
        """
        # Gather diagnostic information
        has_os_release = False
        has_etc = False
        has_systemd = False
        has_shell = False
        has_vmlinuz = False
        has_initramfs = False
        has_boot_dirs = False

        try:
            # Best root signal: /etc/os-release
            has_os_release = g.is_file("/etc/os-release")
            if has_os_release:
                self.logger.info("🔍 Accepted: has /etc/os-release (definitive root indicator)")
                return True

            # Check for /etc directory
            has_etc = g.is_dir("/etc")

            # Check for systemd
            has_systemd = (g.is_file("/usr/bin/systemctl") or
                          g.is_file("/usr/lib/systemd/systemd") or
                          g.is_file("/lib/systemd/systemd"))

            # Check for shell
            has_shell = (g.is_file("/bin/bash") or
                        g.is_file("/usr/bin/bash") or
                        g.is_file("/bin/sh"))

            # Check top-level for boot signatures
            try:
                top_files = [U.to_text(x) for x in g.ls("/") if U.to_text(x)]
                has_vmlinuz = any(name.startswith("vmlinuz-") for name in top_files)
                has_initramfs = any(name.startswith("initramfs-") for name in top_files)
            except Exception:
                pass

            # Check for boot directories
            has_boot_dirs = (g.is_dir("/grub2") or g.is_dir("/grub") or
                           g.is_dir("/efi") or g.is_dir("/loader"))

            # CRITICAL: Reject /boot partitions
            # /boot has kernel/initramfs at top-level + boot directories + no /etc/os-release
            if (has_vmlinuz or has_initramfs) and has_boot_dirs:
                self.logger.info(
                    f"🔍 Rejected: looks like /boot "
                    f"(vmlinuz={has_vmlinuz}, initramfs={has_initramfs}, "
                    f"boot_dirs={has_boot_dirs}, os_release={has_os_release})"
                )
                return False

            # Secondary root signal: /etc + (systemd OR shell)
            if has_etc and (has_systemd or has_shell):
                self.logger.info(
                    f"🔍 Accepted: has /etc + systemd/shell "
                    f"(etc={has_etc}, systemd={has_systemd}, shell={has_shell})"
                )
                return True

            # If we can't prove it's root, treat as not-root (safer)
            self.logger.info(
                f"🔍 Rejected: insufficient root indicators "
                f"(os_release={has_os_release}, etc={has_etc}, "
                f"systemd={has_systemd}, shell={has_shell}, "
                f"vmlinuz={has_vmlinuz}, initramfs={has_initramfs})"
            )
            return False

        except Exception as e:
            self.logger.debug(f"Error in root detection: {e}")
            return False

    def _score_root(self, g: guestfs.GuestFS) -> int:
        """
        Additive root scoring: helps multi-OS / ambiguous layouts.
        Higher score = more likely this mount is the real rootfs.
        """
        score = 0
        for p in self._ROOT_HINT_FILES:
            try:
                if g.is_file(p):
                    score += 5
            except Exception:
                pass
        for p in self._ROOT_STRONG_HINTS:
            try:
                if p.endswith("/"):
                    if g.is_dir(p[:-1]):
                        score += 2
                else:
                    if g.is_file(p) or g.is_dir(p):
                        score += 2
            except Exception:
                pass
        try:
            if g.is_file("/etc/os-release"):
                score += 10
        except Exception:
            pass
        try:
            if g.is_file("/usr/lib/systemd/systemd") or g.is_file("/sbin/init"):
                score += 5
        except Exception:
            pass
        try:
            if g.is_file("/.discinfo") or g.is_file("/isolinux/isolinux.cfg"):
                score -= 20
        except Exception:
            pass
        return score

    def detect_and_mount_root(self, g: guestfs.GuestFS) -> None:
        try:
            roots = g.inspect_os()
        except Exception:
            roots = []
        if not roots:
            self.logger.warning("inspect_os() found no roots; falling back to brute-force mount.")
            self.mount_root_bruteforce(g)
            return

        # Pick best-looking root (avoid roots[0] roulette)
        best_root: str | None = None
        best_score = -10**9
        for r in roots:
            rr = U.to_text(r)
            score = 0
            try:
                if g.inspect_get_product_name(rr):
                    score += 2
            except Exception:
                pass
            try:
                if g.inspect_get_distro(rr):
                    score += 2
            except Exception:
                pass
            try:
                mp = g.inspect_get_mountpoints(rr) or {}
                if U.to_text(mp.get("/", "")).strip():
                    score += 2
            except Exception:
                pass
            if score > best_score:
                best_score = score
                best_root = rr

        root = best_root or U.to_text(roots[0])
        self.inspect_root = root

        # Log identity (best-effort)
        product = "Unknown"
        distro = "unknown"
        major = 0
        minor = 0
        try:
            product_val = g.inspect_get_product_name(root)
            if product_val:
                product = U.to_text(product_val)
        except Exception:
            pass
        try:
            distro = U.to_text(g.inspect_get_distro(root))
        except Exception:
            pass
        try:
            major = g.inspect_get_major_version(root)
            minor = g.inspect_get_minor_version(root)
        except Exception:
            pass
        self.logger.info(f"Detected guest: {product} {major}.{minor} (distro={distro})")

        try:
            mp_map = g.inspect_get_mountpoints(root)
        except Exception:
            mp_map = {}

        root_spec = U.to_text(mp_map.get("/", "")).strip()
        if not root_spec:
            self.logger.warning("Inspection did not provide a root (/) devspec; brute-force mounting.")
            self.mount_root_bruteforce(g)
            return

        root_dev = root_spec
        subvol: str | None = None
        if root_spec.startswith("btrfsvol:"):
            root_dev, subvol = parse_btrfsvol_spec(root_spec)
            root_dev = root_dev.strip()

        real: str | None = None
        if root_dev.startswith("/dev/disk/by-"):
            # Try guestfs realpath first (works for by-uuid, by-label inside guest)
            try:
                rp = U.to_text(g.realpath(root_dev)).strip()
                if rp.startswith("/dev/"):
                    real = rp
            except Exception:
                real = None

            # For by-path devices, use host-level symlink resolution
            # because VMCraft device paths are on the host, not in the guest filesystem
            if not real and root_dev.startswith("/dev/disk/by-path/"):
                try:
                    import os
                    real_dev = os.readlink(root_dev)
                    # Handle relative symlinks
                    if not real_dev.startswith("/"):
                        real_dev = os.path.normpath(os.path.join(os.path.dirname(root_dev), real_dev))
                    if real_dev.startswith("/dev/"):
                        real = real_dev
                        self.logger.info(f"Resolved by-path root device: {root_dev} -> {real}")
                except Exception as e:
                    self.logger.warning(f"Failed to resolve by-path root device {root_dev}: {e}")
                    real = None

        # by-path from inspection may be meaningless in a different VM topology
        if not real and root_dev.startswith("/dev/disk/by-path/"):
            self.logger.warning("Root spec is by-path and not resolvable; falling back to brute-force root detection.")
            self.mount_root_bruteforce(g)
            return

        if not real and root_dev.startswith("/dev/"):
            real = root_dev

        if not real:
            self.logger.warning("Could not determine root device from inspection; brute-force mounting.")
            self.mount_root_bruteforce(g)
            return

        try:
            self._mount_root_direct(g, real, subvol)
        except Exception as e:
            self.logger.warning(f"{e}; brute-force mounting.")
            self.mount_root_bruteforce(g)

    def _candidate_root_devices(self, g: guestfs.GuestFS) -> list[str]:
        """
        Build candidate list for root filesystem detection.

        Uses native guestfs calls instead of shell commands to avoid
        dependencies on /bin/sh in minimal appliances.

        After LUKS open + mdraid assemble + LVM activation, new mountables appear.
        list_filesystems() often includes LV paths.
        """
        candidates: list[str] = []

        # 1) Partitions
        try:
            partitions = [U.to_text(p) for p in (g.list_partitions() or [])]
            candidates.extend(partitions)
            self.logger.debug(f"Partitions: {partitions}")
        except Exception as e:
            self.logger.warning(f"Failed to list partitions: {e}")

        # 2) Mountable filesystems (includes /dev/mapper/* from list_filesystems)
        try:
            fsmap = g.list_filesystems() or {}
            self.logger.debug(f"Filesystems map: {list(fsmap.keys())}")
            for dev, fstype in fsmap.items():
                d = U.to_text(dev)
                t = U.to_text(fstype)
                # Skip non-mountable filesystem types
                # swap: cannot mount as root
                # crypto_LUKS: need to unlock first, then mount the unlocked device
                # LVM2_member: these are PVs, not filesystems - activate VG, then mount LVs
                if t in ("swap", "crypto_LUKS", "LVM2_member"):
                    self.logger.debug(f"Skipping {d} (type={t})")
                    continue
                if d.startswith("/dev/"):
                    candidates.append(d)
                    self.logger.debug(f"Added from filesystems: {d} (type={t})")
        except Exception as e:
            self.logger.warning(f"Failed to list filesystems: {e}")

        # 3) LVM logical volumes (native guestfs call)
        try:
            if hasattr(g, "lvs"):
                lvs_list = g.lvs() or []
                self.logger.info(f"LVM logical volumes: {lvs_list}")
                for lv in lvs_list:
                    d = U.to_text(lv)
                    if d.startswith("/dev/"):
                        # Skip swap LVs - they can't be root filesystems
                        if "swap" in d.lower():
                            self.logger.debug(f"Skipping swap LV: {d}")
                            continue
                        candidates.append(d)
                        self.logger.info(f"Added LV candidate: {d}")
        except Exception as e:
            self.logger.warning(f"LVM enumeration failed: {e}")

        # 4) Deduplicate while preserving order
        seen: set[str] = set()
        out: list[str] = []
        for d in candidates:
            if d and d not in seen:
                seen.add(d)
                out.append(d)

        # Filter out known non-root devices and resolve by-path devices
        filtered = []
        for d in out:
            # Skip VMCraft loop devices
            if d.startswith("/dev/loop"):
                self.logger.debug(f"Filtering out loop device: {d}")
                continue
            # Skip LUKS placeholder devices that don't exist
            if "/luks-" in d and not d.startswith("/dev/mapper/luks-"):
                self.logger.debug(f"Filtering out LUKS placeholder: {d}")
                continue

            # CRITICAL: Resolve by-path devices to real device paths
            # Device paths with colons (e.g., /dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part2)
            # are interpreted as NFS paths by mount, causing "mount.nfs: Failed to resolve server" errors
            if d.startswith("/dev/disk/by-path/"):
                try:
                    import os
                    # Resolve symlink on host system (not inside guest filesystem)
                    real_dev = os.readlink(d)
                    # Handle relative symlinks
                    if not real_dev.startswith("/"):
                        real_dev = os.path.normpath(os.path.join(os.path.dirname(d), real_dev))
                    self.logger.debug(f"Resolved by-path device: {d} -> {real_dev}")
                    d = real_dev
                except Exception as e:
                    self.logger.warning(f"Failed to resolve by-path device {d}: {e}; skipping")
                    continue

            filtered.append(d)

        # Get current NBD device and its partitions to filter candidates
        current_nbd = None
        current_nbd_parts = []
        try:
            devices = g.list_devices() or []
            if devices:
                current_nbd = U.to_text(devices[0])
                self.logger.debug(f"Current NBD device: {current_nbd}")
                # Get partitions of current NBD
                parts = g.list_partitions() or []
                current_nbd_parts = [U.to_text(p) for p in parts if U.to_text(p).startswith(current_nbd)]
                self.logger.debug(f"Current NBD partitions: {current_nbd_parts}")
        except Exception as e:
            self.logger.warning(f"Failed to get current NBD device: {e}")

        # Get LVM devices that belong to the current disk
        # VMCraft's lvs() with nbd_device filtering returns only NBD-backed LVs
        # in /dev/mapper/ format with proper hyphen escaping
        current_disk_lv = set()
        if current_nbd_parts:
            try:
                # Get LVM volumes from current disk (already filtered by VMCraft)
                # VMCraft returns /dev/mapper/ format paths
                lvs_list = g.lvs() or [] if hasattr(g, "lvs") else []
                for lv in lvs_list:
                    lv_text = U.to_text(lv)
                    current_disk_lv.add(lv_text)

                self.logger.debug(f"LVM devices from current disk: {current_disk_lv}")
            except Exception as e:
                self.logger.warning(f"Failed to filter LVM devices: {e}")

        # Filter candidates to only include devices from current NBD disk
        # This prevents trying devices from other NBD connections or the host system
        nbd_filtered = []
        for d in filtered:
            # Include /dev/mapper/ LVM devices ONLY if they're in our LVM list
            if d.startswith("/dev/mapper/") and "control" not in d.lower():
                if d in current_disk_lv:
                    nbd_filtered.append(d)
                    self.logger.debug(f"Including LVM device: {d}")
                else:
                    self.logger.debug(f"Filtering out LVM device not from current disk: {d}")
            # Include partitions from current NBD device
            elif current_nbd and d.startswith(current_nbd):
                nbd_filtered.append(d)
            # Skip devices from other NBD devices or host system
            elif current_nbd:
                self.logger.debug(f"Filtering out device from different disk: {d}")
            else:
                # If we can't determine current NBD, include all (fallback)
                nbd_filtered.append(d)

        self.logger.info(f"Filtered to current disk: {len(nbd_filtered)} of {len(filtered)} candidates")

        # Prioritize LVM logical volumes in /dev/mapper/ format
        # Try these first as they're most likely to be root filesystems
        priority = []
        standard = []
        for d in nbd_filtered:
            # LVM device in /dev/mapper/ format
            if d.startswith("/dev/mapper/") and "control" not in d.lower():
                priority.append(d)
            else:
                standard.append(d)

        result = priority + standard
        self.logger.info(f"Candidate priority order: {result}")
        return result

    def mount_root_bruteforce(self, g: guestfs.GuestFS) -> None:
        candidates = self._candidate_root_devices(g)
        if not candidates:
            U.die(self.logger, "Failed to list partitions/filesystems for brute-force mount.", 1)

        mount_failures: list[dict[str, str]] = []

        # Validate partition devices exist before attempting mount
        import os
        validated_candidates = []
        for dev in candidates:
            if os.path.exists(dev):
                validated_candidates.append(dev)
            else:
                self.logger.warning(f"⚠️ Device {dev} doesn't exist, skipping")
                mount_failures.append({"device": dev, "error": "device_not_found"})

        if not validated_candidates:
            U.die(self.logger, "No valid partition devices found.", 1)

        self.logger.info(f"Validated {len(validated_candidates)} of {len(candidates)} candidate devices")
        candidates = validated_candidates

        # Give a brief pause for devices to settle (especially important for non-sequential partition layouts)
        import time
        time.sleep(0.3)

        # Try normal mounts first, but score candidates and pick best
        best: tuple[int, str | None] = (-10**9, None)
        for dev in candidates:
            self._safe_umount_all(g)
            try:
                # Get filesystem type before attempting mount
                vfs_type = None
                try:
                    vfs_type = filesystem_fixer._vfs_type(g, dev)
                    self.logger.debug(f"Device {dev} has filesystem type: {vfs_type}")
                except Exception as e:
                    self.logger.debug(f"Could not determine vfs_type for {dev}: {e}")

                filesystem_fixer.log_vfs_type_best_effort(self, g, dev)

                # Skip non-mountable device types
                if vfs_type in ("LVM2_member", "swap"):
                    self.logger.debug(f"Skipping non-mountable device: {dev} (type={vfs_type})")
                    continue

                self.logger.info(f"🔄 Attempting to mount {dev} at /...")

                # Try mount with appropriate options
                try:
                    if self.dry_run:
                        g.mount_ro(dev, "/")
                    else:
                        g.mount(dev, "/")
                except Exception as mount_error:
                    # Log mount failures at DEBUG - expected during partition probing
                    # (EFI partitions, swap, etc. will fail to mount)
                    self.logger.debug(f"Mount failed for {dev} (type={vfs_type}): {mount_error}")

                    # Try filesystem-specific recovery strategies
                    if vfs_type == "xfs":
                        # XFS: Try read-only with norecovery (skips dirty log replay)
                        self.logger.info(f"XFS mount failed, retrying with ro,norecovery for {dev}")
                        try:
                            g.mount_options("ro,norecovery", dev, "/")
                            self.logger.info(f"✓ Mount succeeded with ro,norecovery: {dev}")
                            # Continue with read-only mode for detection
                        except Exception as xfs_error:
                            self.logger.debug(f"XFS recovery mount also failed: {xfs_error}")
                            # Try with nouuid (common for cloned VMware VMs with duplicate UUIDs)
                            self.logger.info(f"XFS mount failed, retrying with nouuid for {dev}")
                            try:
                                g.mount_options("nouuid", dev, "/")
                                self.logger.info(f"✓ Mount succeeded with nouuid: {dev}")
                                # Continue with nouuid mode for detection
                            except Exception as nouuid_error:
                                self.logger.debug(f"XFS nouuid mount also failed: {nouuid_error}")
                                raise mount_error
                    elif vfs_type == "ext4":
                        self.logger.info(f"Attempting fsck for ext4 partition {dev}")
                        try:
                            # Run fsck in non-interactive mode
                            run_sudo(self.logger, ["fsck.ext4", "-p", "-f", dev], check=False, capture=True)
                            # Retry mount after repair
                            if self.dry_run:
                                g.mount_ro(dev, "/")
                            else:
                                g.mount(dev, "/")
                            self.logger.info(f"✓ Mount succeeded after fsck: {dev}")
                        except Exception as repair_error:
                            self.logger.debug(f"Filesystem repair failed: {repair_error}")
                            raise mount_error
                    else:
                        raise

                self.logger.info(f"✓ Mount succeeded for {dev}, checking if it looks like root...")

                # Debug: Check what's accessible
                try:
                    # Check if files exist via direct path
                    import os
                    mount_root = getattr(g, "_mount_root", None)
                    if mount_root:
                        actual_files = os.listdir(mount_root) if os.path.exists(mount_root) else []
                        fstab_exists = os.path.exists(os.path.join(mount_root, "etc", "fstab"))
                        self.logger.info(f"🔍 mount_root={mount_root}, contents={actual_files[:10]}, fstab_exists={fstab_exists}")
                    self.logger.info(f"🔍 Via GuestFS: is_dir('/') = {g.is_dir('/')}, is_file('/etc/fstab') = {g.is_file('/etc/fstab')}")
                except Exception as e:
                    self.logger.warning(f"❌ Error checking files: {e}")

                if self._looks_like_root(g):
                    sc = self._score_root(g)
                    self.logger.info(f"✓ {dev} looks like root (score={sc})")
                    if sc > best[0]:
                        best = (sc, dev)
                else:
                    self.logger.info(f"✗ {dev} doesn't look like root filesystem")

                self._safe_umount_all(g)
            except Exception as e:
                # DEBUG level since mount failures are expected during root detection
                # (swap partitions, wrong filesystems, etc.)
                self.logger.debug(f"Mount failed for {dev}: {e}")
                mount_failures.append({"device": dev, "error": str(e)})
                continue

        if best[1]:
            dev = best[1]
            self._safe_umount_all(g)
            try:
                # Get filesystem type for proper mounting
                vfs_type = None
                try:
                    vfs_type = filesystem_fixer._vfs_type(g, dev)
                except Exception:
                    pass

                # Try mount with appropriate options (including XFS nouuid for cloned VMs)
                mounted = False
                try:
                    if self.dry_run:
                        g.mount_ro(dev, "/")
                    else:
                        g.mount(dev, "/")
                    mounted = True
                except Exception as mount_error:
                    # Apply same XFS recovery strategies as during detection
                    if vfs_type == "xfs":
                        self.logger.info(f"Retrying root mount with XFS recovery options for {dev}")
                        try:
                            g.mount_options("ro,norecovery", dev, "/")
                            mounted = True
                        except Exception:
                            try:
                                g.mount_options("nouuid", dev, "/")
                                mounted = True
                                self.logger.info(f"Root mounted with nouuid option")
                            except Exception:
                                raise mount_error
                    else:
                        raise mount_error

                if mounted:
                    self.root_dev = dev
                    self.logger.info(f"✅ Mounted root filesystem: {dev} (score={best[0]})")
                    if mount_failures:
                        try:
                            self.report.setdefault("analysis", {}).setdefault("mount", {})[
                                "bruteforce_failures"
                            ] = mount_failures
                        except Exception as e:
                            self.logger.debug(f"Failed to store mount failures in report: {e}")
                    return
            except Exception as e:
                mount_failures.append({"device": dev, "error": f"best_root_mount_failed:{e}"})
        else:
            self.logger.warning(f"No candidate devices passed _looks_like_root check in first pass. Trying btrfs subvolumes...")

        # Then attempt btrfs common subvols (also scored)
        # Only attempt btrfs subvolumes on actual btrfs filesystems
        best_btrfs: tuple[int, str | None, str | None] = (-10**9, None, None)
        for dev in candidates:
            # Check filesystem type before trying btrfs subvolumes
            try:
                vfs_type = filesystem_fixer._vfs_type(g, dev)
                self.logger.debug(f"Btrfs check: {dev} has vfs_type={vfs_type}")
            except Exception:
                vfs_type = "unknown"

            # Skip non-btrfs filesystems for subvolume mounting
            if vfs_type != "btrfs":
                self.logger.debug(f"Skipping {dev} for btrfs subvolumes (type={vfs_type})")
                continue

            self.logger.info(f"Discovering btrfs subvolumes on {dev}")

            # Discover actual subvolumes using host-side btrfs command
            discovered_subvols = []
            temp_mount = None
            try:
                # Create temporary mount point for btrfs inspection
                import tempfile
                import os
                temp_mount = tempfile.mkdtemp(prefix="hyper2kvm-btrfs-")
                self.logger.debug(f"Created temp mount point: {temp_mount}")

                # Mount the btrfs filesystem on the host to list subvolumes
                try:
                    self.logger.debug(f"Mounting {dev} at {temp_mount} with subvolid=5")
                    run_sudo(
                        self.logger,
                        ["mount", "-o", "ro,subvolid=5", dev, temp_mount],
                        check=True,
                        capture=True
                    )
                    self.logger.debug("Mount successful, listing subvolumes")

                    # List subvolumes using host btrfs command
                    result = run_sudo(
                        self.logger,
                        ["btrfs", "subvolume", "list", temp_mount],
                        check=True,
                        capture=True
                    )

                    output = U.to_text(result.stdout).strip()
                    self.logger.debug(f"Btrfs subvolume list output: {output[:200]}")

                    # Parse output like: "ID 256 gen 7 top level 5 path @"
                    # or "ID 256 gen 7 top level 5 path root"
                    for line in output.splitlines():
                        parts = line.split()
                        if "path" in parts:
                            idx = parts.index("path")
                            if idx + 1 < len(parts):
                                subvol = parts[idx + 1]
                                discovered_subvols.append(subvol)
                                self.logger.debug(f"Found subvolume: {subvol}")

                    self.logger.info(f"✅ Discovered {len(discovered_subvols)} btrfs subvolumes: {discovered_subvols}")

                except Exception as e:
                    self.logger.warning(f"Could not list btrfs subvolumes using host command: {e}")
                finally:
                    # Unmount and cleanup
                    try:
                        run_sudo(self.logger, ["umount", temp_mount], check=False, capture=True)
                        os.rmdir(temp_mount)
                        self.logger.debug(f"Cleaned up temp mount: {temp_mount}")
                    except Exception as cleanup_error:
                        self.logger.debug(f"Cleanup warning: {cleanup_error}")

            except Exception as e:
                self.logger.warning(f"Could not discover btrfs subvolumes on {dev}: {e}")

            # Combine discovered and common subvolumes
            subvols_to_try = discovered_subvols if discovered_subvols else self._BTRFS_COMMON_SUBVOLS
            if discovered_subvols:
                # Also try common patterns in case discovery missed them
                for common in self._BTRFS_COMMON_SUBVOLS:
                    if common not in subvols_to_try:
                        subvols_to_try.append(common)

            self.logger.info(f"Trying {len(subvols_to_try)} btrfs subvolumes on {dev}")
            for sv in subvols_to_try:
                self._safe_umount_all(g)
                try:
                    filesystem_fixer.log_vfs_type_best_effort(self, g, dev)
                    opts = f"subvol={sv}"
                    if self.dry_run:
                        opts = f"ro,{opts}"
                    g.mount_options(opts, dev, "/")
                    if self._looks_like_root(g):
                        sc = self._score_root(g)
                        self.logger.info(f"✓ {dev} subvol={sv} looks like root (score={sc})")
                        if sc > best_btrfs[0]:
                            best_btrfs = (sc, dev, sv)
                    else:
                        self.logger.debug(f"✗ {dev} subvol={sv} doesn't look like root")
                    self._safe_umount_all(g)
                except Exception as e:
                    mount_failures.append({"device": f"{dev} subvol={sv}", "error": str(e)})
                    continue

        if best_btrfs[1] and best_btrfs[2]:
            dev = best_btrfs[1]
            sv = best_btrfs[2]
            self._safe_umount_all(g)
            try:
                filesystem_fixer.log_vfs_type_best_effort(self, g, dev)
                opts = f"subvol={sv}"
                if self.dry_run:
                    opts = f"ro, {opts}"
                g.mount_options(opts, dev, "/")
                self.root_dev = dev
                self.root_btrfs_subvol = sv
                self.logger.info(f"Fallback btrfs root detected at {dev} (subvol={sv}, score={best_btrfs[0]})")
                if mount_failures:
                    try:
                        self.report.setdefault("analysis", {}).setdefault("mount", {})[
                            "bruteforce_failures"
                        ] = mount_failures
                    except Exception as e:
                        self.logger.debug(f"Failed to store mount failures in report: {e}")
                return
            except Exception as e:
                mount_failures.append({"device": f"{dev} subvol={sv}", "error": f"best_btrfs_mount_failed:{e}"})

        # stash failures before dying
        if mount_failures:
            try:
                self.report.setdefault("analysis", {}).setdefault("mount", {})["bruteforce_failures"] = mount_failures
            except Exception as e:
                self.logger.debug(f"Failed to store mount failures in report: {e}")

        U.die(self.logger, "Failed to mount root filesystem.", 1)

    # normalize validation results (bool/dict compatibility)
    @staticmethod
    def _normalize_validation_results(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Delegate to validation manager."""
        return OfflineValidationManager.normalize_validation_results(raw)

    @staticmethod
    def _summarize_validation(norm: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Delegate to validation manager."""
        return OfflineValidationManager.summarize_validation(norm)

    # Configuration rewriting (delegated to modules)
    def backup_file(self, g: guestfs.GuestFS, path: str) -> None:
        """Delegate to config rewriter."""
        self._config_rewriter.backup_file(g, path)

    def convert_spec(self, g: guestfs.GuestFS, spec: str) -> tuple[str, str]:
        """Delegate to spec converter."""
        # Update root_dev in spec_converter if it's been detected
        if self.root_dev and self._spec_converter.root_dev != self.root_dev:
            self._spec_converter.root_dev = self.root_dev
        return self._spec_converter.convert_spec(g, spec)

    def rewrite_fstab(self, g: guestfs.GuestFS) -> tuple[int, list[Change], dict[str, Any]]:
        """Delegate to config rewriter."""
        return self._config_rewriter.rewrite_fstab(g)

    def rewrite_crypttab(self, g: guestfs.GuestFS) -> int:
        """Delegate to config rewriter."""
        return self._config_rewriter.rewrite_crypttab(g)

    # Filesystem fixer (delegated)
    def fix_filesystems(self, g: guestfs.GuestFS) -> dict[str, Any]:
        return filesystem_fixer.fix_filesystems(self, g)

    # Delegated fixers (explicit wrappers; no monkey-patching)
    def fix_network_config(self, g: guestfs.GuestFS) -> dict[str, Any]:
        return network_fixer.fix_network_config(self, g)

    def remove_stale_device_map(self, g: guestfs.GuestFS) -> int:
        return grub_fixer.remove_stale_device_map(self, g)

    def update_grub_root(self, g: guestfs.GuestFS) -> int:
        return grub_fixer.update_grub_root(self, g)

    def regen(self, g: guestfs.GuestFS) -> dict[str, Any]:
        return grub_fixer.regen(self, g)

    # Windows delegation
    def is_windows(self, g: guestfs.GuestFS) -> bool:
        return windows_fixer.is_windows(self, g)

    def windows_bcd_actual_fix(self, g: guestfs.GuestFS) -> dict[str, Any]:
        return windows_fixer.windows_bcd_actual_fix(self, g)

    def inject_virtio_drivers(self, g: guestfs.GuestFS) -> dict[str, Any]:
        return windows_fixer.inject_virtio_drivers(self, g)

    # VMware tools removal (mounted tree remover)
    def _mount_local_run_threaded(
        self,
        g: guestfs.GuestFS,
        mountpoint: Path,
        *,
        ready_timeout_s: float = 15.0,
    ) -> tuple[bool, str | None, threading.Thread | None, list[str]]:
        """
        guestfs.mount_local_run() is a blocking FUSE loop.
        Pattern:
          - mount_local(mountpoint)
          - start background thread calling mount_local_run()
          - do host-side file operations against mountpoint
          - umount_local() to stop

        Returns any mount_local_run() exceptions collected in the background thread.
        """
        err: list[str] = []

        try:
            g.mount_local(str(mountpoint))
        except Exception as e:
            return False, f"mount_local_failed:{e}", None, err

        def _runner() -> None:
            try:
                g.mount_local_run()
            except Exception as e:
                err.append(str(e))

        t = threading.Thread(target=_runner, name="guestfs-mount-local-run", daemon=True)
        t.start()

        deadline = time.time() + ready_timeout_s
        while time.time() < deadline:
            try:
                if mountpoint.exists():
                    _ = list(mountpoint.iterdir())
                    return True, None, t, err
            except Exception:
                pass
            time.sleep(0.1)

        try:
            g.umount_local()
        except Exception:
            pass
        return False, "mount_local_ready_timeout", t, err

    def remove_vmware_tools_func(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """
        Exposes the mounted guest filesystem via mount_local + background mount_local_run(),
        then runs OfflineVmwareToolsRemover against that host-visible tree.

        Always attempts umount_local() + cleanup.
        """
        if not self.remove_vmware_tools:
            return {"enabled": False}

        U.banner(self.logger, "VMware tools removal (OFFLINE)")
        res = VmwareRemovalResult(enabled=True)

        if self.dry_run:
            res.notes.append("dry_run: remover will only log; no changes written")
        if self.no_backup:
            res.notes.append("no_backup: remover will not create .bak copies")
        if not self.root_dev:
            res.errors.append("root_not_mounted")
            return res.as_dict()

        mnt = Path(tempfile.mkdtemp(prefix="hyper2kvm.guestfs.mnt."))
        mounted_local = False
        t: threading.Thread | None = None
        thread_errs: list[str] = []

        try:
            ok, why, t, thread_errs = self._mount_local_run_threaded(g, mnt)
            if not ok:
                res.errors.append(why or "mount_local_failed")
                if thread_errs:
                    res.warnings.append(f"mount_local_run_errors:{thread_errs[:3]}")
                return res.as_dict()
            mounted_local = True

            remover = OfflineVmwareToolsRemover(
                logger=self.logger,
                mount_point=mnt,
                dry_run=self.dry_run,
                no_backup=self.no_backup,
            )
            rr = remover.run()

            res.removed_paths = rr.removed_paths
            res.removed_services = rr.removed_services
            res.removed_symlinks = rr.removed_symlinks
            res.package_hints = rr.package_hints
            res.touched_files = rr.touched_files
            res.errors = rr.errors
            if getattr(rr, "warnings", None):
                res.warnings.extend(rr.warnings)

            if thread_errs:
                res.warnings.append(f"mount_local_run_errors:{thread_errs[:5]}")

            return res.as_dict()

        finally:
            if mounted_local:
                try:
                    g.umount_local()
                except Exception:
                    pass
            if t:
                t.join(timeout=3.0)
                if t.is_alive():
                    res.warnings.append("mount_local_thread_still_alive_after_join")
            try:
                shutil.rmtree(str(mnt), ignore_errors=True)
            except Exception:
                pass

    # disk usage analysis
    def analyze_disk_space(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Delegate to validation manager."""
        return self._validation_manager.analyze_disk_space(g)

    def create_validation_suite(self, g: guestfs.GuestFS) -> ValidationSuite:
        """Delegate to validation manager."""
        return self._validation_manager.create_validation_suite(g)

    # resizing (image-level)
    def _resize_image_container(self) -> dict[str, Any] | None:
        if not self.resize:
            return None
        if self.dry_run:
            self.logger.info("DRY-RUN: skipping image resize")
            return {"image_resize": "skipped", "dry_run": True}
        try:
            cp = U.run_cmd(self.logger, ["qemu-img", "info", "--output=json", str(self.image)], capture=True)
            info = json.loads(cp.stdout or "{}")
            current_size = int(info.get("virtual-size", 0))
            if current_size <= 0:
                raise RuntimeError("qemu-img info did not return virtual-size")
            if str(self.resize).startswith("+"):
                add = U.human_to_bytes(str(self.resize)[1:])
                new_size = current_size + add
            else:
                new_size = U.human_to_bytes(str(self.resize))
            if new_size < current_size:
                self.logger.warning("Shrink not supported (requested size < current size)")
                return {"image_resize": "skipped", "reason": "shrink_not_supported"}
            cmd = ["qemu-img", "resize", str(self.image), str(new_size)]
            proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, universal_newlines=True)
            blinking_progress("Resizing image", proc)
            proc.wait()
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, cmd)
            self.logger.info(f"Resized image to {U.human_bytes(new_size)}")
            return {"image_resize": "ok", "new_size": new_size, "old_size": current_size}
        except Exception as e:
            self.logger.error(f"Image resize failed: {e}")
            return {"image_resize": "failed", "error": str(e)}

    # report writer
    def write_report(self) -> None:
        write_report(self)

    # main run
    def run(self) -> None:
        U.banner(self.logger, "Offline guest fix")
        self.logger.info(f"Opening offline image: {self.image}")

        if self.recovery_manager:
            self.recovery_manager.save_checkpoint("start", {"image": str(self.image)})

        if self.resize:
            self.report["analysis"]["image_resize"] = self._run_stage("image_resize", self._resize_image_container)  # type: ignore

        g = self.open()
        try:
            # 1) LUKS (optional but wired)
            luks_audit = self._run_stage("luks_unlock", lambda: self._unlock_luks_devices(g), default={})
            self.report["analysis"]["luks"] = luks_audit
            self.logger.info(f"LUKS audit: {U.json_dump(luks_audit)}")

            # 2) storage stack activation (additive)
            stack_audit = self._run_stage("storage_stack", lambda: self._pre_mount_activate_storage_stack(g), default={})
            self.report.setdefault("analysis", {})["storage_stack"] = stack_audit

            # 3) LVM activation (existing behavior; safe even if no LVM)
            self._run_stage("lvm_activate", lambda: self._activate_lvm(g), default=None)

            # 3.5) Regenerate XFS UUIDs (CRITICAL for cloned VMs with duplicate UUIDs)
            # Must run BEFORE mounting (xfs_admin requires unmounted filesystems)
            uuid_audit = self._run_stage("regenerate_xfs_uuids", lambda: self._regenerate_xfs_uuids(g), default={})
            self.report.setdefault("analysis", {})["xfs_uuid_regeneration"] = uuid_audit

            # 4) Mount root (critical)
            self._run_stage("mount_root", lambda: self.detect_and_mount_root(g), critical=True, default=None)

            # 4.1) Update fstab with new UUIDs if any were regenerated
            regenerated_uuids = uuid_audit.get("regenerated", []) if uuid_audit else []
            self.logger.debug(f"UUID audit: {uuid_audit}")
            self.logger.debug(f"Regenerated UUIDs to update in fstab: {len(regenerated_uuids)}")
            if regenerated_uuids:
                self.logger.info(f"Updating fstab with {len(regenerated_uuids)} regenerated UUIDs...")
                self._run_stage(
                    "update_fstab_uuids",
                    lambda: self._update_fstab_with_new_uuids(g, regenerated_uuids),
                    default=None
                )

            # 4.5) Filesystem fixer stage (optional; runs unmounted)
            fs_audit = self._run_stage("filesystem_repair", lambda: self.fix_filesystems(g), default={"enabled": False})
            self.report.setdefault("analysis", {})["filesystem_repair"] = fs_audit
            if (fs_audit or {}).get("enabled"):
                # fix_filesystems() unmounts; re-mount to proceed
                self._run_stage(
                    "remount_root_after_fs_repair",
                    lambda: self.detect_and_mount_root(g),
                    critical=True,
                    default=None,
                )

            # identity into report
            def _read_os_release() -> str:
                try:
                    return U.to_text(g.read_file("/etc/os-release")) if g.is_file("/etc/os-release") else ""
                except Exception:
                    return ""

            osr = self._run_stage("read_os_release", _read_os_release, default="")
            self.report["analysis"]["guest"] = {
                "inspect_root": self.inspect_root,
                "root_dev": self.root_dev,
                "root_btrfs_subvol": self.root_btrfs_subvol,
                "os_release": osr,
            }

            # validation (bool/dict compatible)
            def _do_validation() -> dict[str, Any]:
                suite = self.create_validation_suite(g)
                ctx = {"image": str(self.image), "root_dev": self.root_dev, "subvol": self.root_btrfs_subvol}
                raw = suite.run_all(ctx)
                norm = self._normalize_validation_results(raw)
                summary = self._summarize_validation(norm)
                return {"results": norm, "summary": summary}

            self.report["validation"] = self._run_stage("validation", _do_validation, default={"results": {}, "summary": {}})

            norm = (self.report.get("validation") or {}).get("results", {}) or {}
            critical_failures = [name for name, r in norm.items() if r.get("critical") and not r.get("passed")]
            if critical_failures:
                self.logger.warning(f"Critical validation failures: {critical_failures}")

            if self.recovery_manager:
                self.recovery_manager.save_checkpoint(
                    "mounted",
                    {
                        "root_dev": self.root_dev,
                        "root_btrfs_subvol": self.root_btrfs_subvol,
                        "validation": self.report.get("validation"),
                    },
                )

            # fixes
            # Update spec_converter with detected root_dev before fstab conversion
            if self.root_dev and self._spec_converter.root_dev != self.root_dev:
                self._spec_converter.root_dev = self.root_dev

            c_fstab, fstab_changes, fstab_audit = self._run_stage(
                "rewrite_fstab", lambda: self.rewrite_fstab(g), default=(0, [], {})
            )
            c_crypt = self._run_stage("rewrite_crypttab", lambda: self.rewrite_crypttab(g), default=0)
            network_audit = self._run_stage("fix_network", lambda: self.fix_network_config(g), default={"enabled": False})

            # grub steps gated
            c_devmap = 0
            c_grub = 0
            if self.update_grub:
                c_devmap = self._run_stage("grub_remove_device_map", lambda: self.remove_stale_device_map(g), default=0)
                c_grub = self._run_stage("grub_update_root", lambda: self.update_grub_root(g), default=0)
            else:
                try:
                    self.report.setdefault("analysis", {}).setdefault("stages", {})["grub_update_root"] = {
                        "ok": True,
                        "skipped": "update_grub_disabled",
                        "duration_s": 0.0,
                    }
                except Exception as e:
                    self.logger.debug(f"Failed to record grub skip in report: {e}")

            # keep your existing mdraid_check()/inject_cloud_init() if they exist
            mdraid = self._run_stage(
                "mdraid_check",
                lambda: self.mdraid_check(g) if hasattr(self, "mdraid_check") else {"present": False},
                default={"present": False},
            )
            cloud_init = self._run_stage(
                "inject_cloud_init",
                lambda: self.inject_cloud_init(g) if hasattr(self, "inject_cloud_init") else {"enabled": False},
                default={"enabled": False},
            )

            # firstboot scripts injection (Linux only)
            firstboot = self._run_stage(
                "inject_firstboot",
                lambda: firstboot_injector.inject_firstboot(self, g),
                default={"injected": False, "reason": "not_attempted"},
            )

            # network config injection (Linux only)
            network_config_inject_result = self._run_stage(
                "inject_network_config",
                lambda: network_config_injector.inject_network_config(self, g),
                default={"injected": False, "reason": "not_attempted"},
            )

            # user config injection (Linux only)
            user_config_inject_result = self._run_stage(
                "inject_user_config",
                lambda: user_config_injector.inject_user_config(self, g),
                default={"injected": False, "reason": "not_attempted"},
            )

            # service config injection (Linux only)
            service_config_inject_result = self._run_stage(
                "inject_service_config",
                lambda: service_config_injector.inject_service_config(self, g),
                default={"injected": False, "reason": "not_attempted"},
            )

            # hostname config injection (Linux only)
            hostname_config_inject_result = self._run_stage(
                "inject_hostname_config",
                lambda: hostname_config_injector.inject_hostname_config(self, g),
                default={"injected": False, "reason": "not_attempted"},
            )

            # Windows hooks: only run on Windows
            is_win = self._run_stage("detect_windows", lambda: self.is_windows(g), default=False)
            if is_win:
                win = self._run_stage(
                    "windows_bcd_fix",
                    lambda: self.windows_bcd_actual_fix(g),
                    default={"enabled": True, "error": "failed"},
                )
                virtio = self._run_stage(
                    "windows_inject_virtio",
                    lambda: self.inject_virtio_drivers(g),
                    default={"enabled": True, "error": "failed"},
                )
            else:
                win = {"enabled": False, "skipped": "not_windows"}
                virtio = {"enabled": False, "skipped": "not_windows"}

            disk = self._run_stage("disk_analysis", lambda: self.analyze_disk_space(g), default={"analysis": "failed"})
            vmware_removal = self._run_stage(
                "vmware_tools_removal",
                lambda: self.remove_vmware_tools_func(g),
                default={"enabled": False, "error": "failed"},
            )

            # Post-conversion boot hardening (3 golden fixes for Linux)
            # This runs for Linux guests only and applies production-grade boot fixes
            post_conversion_audit: dict[str, Any] = {"enabled": False}
            if not is_win and self.regen_initramfs:
                from .bootloader.post_conversion import PostConversionBootFixer

                post_conversion_audit = self._run_stage(
                    "post_conversion_boot_hardening",
                    lambda: PostConversionBootFixer(self.logger).apply_golden_fixes(
                        g,
                        harden_fstab=True,
                        rebuild_initramfs=True,
                        regenerate_grub=self.update_grub,
                    ),
                    default={"enabled": False, "error": "failed"},
                )
                self.logger.info(f"Post-conversion boot hardening: {U.json_dump(post_conversion_audit)}")

            regen_info: dict[str, Any]
            # Skip old regen if post_conversion already rebuilt initramfs successfully
            # Otherwise the old regen will overwrite the generic initramfs with a hostonly one
            skip_old_regen = post_conversion_audit.get("initramfs_rebuilt", False)
            if skip_old_regen:
                self.logger.info("⏭️  Skipping old initramfs regen (post_conversion already rebuilt generic initramfs)")
                regen_info = {"enabled": False, "skipped": "post_conversion_handled_initramfs"}
            elif self.regen_initramfs:
                regen_info = self._run_stage(
                    "regen_initramfs_and_bootloader",
                    lambda: self.regen(g),
                    default={"enabled": True, "error": "failed"},
                )
            else:
                regen_info = {"enabled": False, "skipped": "regen_initramfs_disabled"}

            if not self.dry_run:
                self._run_stage("guestfs_sync", lambda: g.sync(), default=None)

            self._safe_umount_all(g)

            # report aggregation
            self.report["changes"] = {
                "fstab": c_fstab,
                "crypttab": c_crypt,
                "network": network_audit,
                "grub_root": c_grub,
                "grub_device_map_removed": c_devmap,
                "vmware_tools_removed": vmware_removal,
                "cloud_init_injected": cloud_init,
                "firstboot_scripts_injected": firstboot,
                "network_config_injected": network_config_inject_result,
                "user_config_injected": user_config_inject_result,
                "service_config_injected": service_config_inject_result,
                "hostname_config_injected": hostname_config_inject_result,
            }
            self.report["analysis"]["fstab_audit"] = fstab_audit
            self.report["analysis"]["fstab_changes"] = [vars(x) for x in fstab_changes]
            self.report["analysis"]["mdraid"] = mdraid
            self.report["analysis"]["windows"] = win
            self.report["analysis"]["virtio"] = virtio
            self.report["analysis"]["disk"] = disk
            self.report["analysis"]["regen"] = regen_info
            self.report["analysis"]["post_conversion_boot_hardening"] = post_conversion_audit
            self.report["analysis"]["timings"] = dict(self._timings)
            self.report["timestamps"]["end"] = _dt.datetime.now().isoformat()

        finally:
            try:
                self._safe_umount_all(g)
            except Exception:
                pass

            # Save converted image path before closing (for final conversion)
            try:
                if g.converted_image_path:
                    self.converted_image_path = g.converted_image_path
                    g.keep_converted_image()  # Don't delete the temp qcow2
                    self.logger.info(f"Preserved converted image for final conversion: {self.converted_image_path.name}")
            except Exception as e:
                self.logger.debug(f"Could not preserve converted image: {e}")

            try:
                g.close()
            except Exception:
                pass

        self.write_report()
