# SPDX-License-Identifier: LGPL-3.0-or-later
# vmdk2kvm/fixers/filesystem_fixer.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import guestfs  # type: ignore

from ..core.utils import U


class FilesystemFixer:
    """
    Enhanced filesystem fixer with better safety, logging, and repair capabilities.

    Key goals:
      - detect filesystem types robustly
      - never touch dangerous filesystems automatically (btrfs/zfs/...)
      - run safe check/repair tools with good logs
      - for XFS, be *extra careful* with memory usage:
          * always use -P (noprefetch)
          * always pass -m with a conservative value (approximate cap, not hard)
    """

    # File systems we should NEVER attempt to auto-repair
    DANGEROUS_FS_TYPES = {"btrfs", "zfs", "reiserfs", "reiser4", "f2fs"}

    # File systems we can safely check/repair
    SAFE_FS_TYPES = {"ext2", "ext3", "ext4", "xfs", "vfat", "ntfs", "exfat"}

    # File systems requiring special handling
    SPECIAL_FS_TYPES = {"swap", "crypto_luks", "lvm2_member", "bcachefs"}

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.stats = {
            "total_devices": 0,
            "checked": 0,
            "repaired": 0,
            "skipped": 0,
            "errors": 0,
            "start_time": 0.0,
            "end_time": 0.0,
        }

    def _log(self, level: int, msg: str, *args, **kwargs) -> None:
        """Safe logging wrapper."""
        if self.logger:
            self.logger.log(level, msg, *args, **kwargs)

    # -------------------------------------------------------------------------
    # Appliance memory helpers (best-effort)
    # -------------------------------------------------------------------------

    def _get_guestfs_memsize_mib_best_effort(self, ctx: Any | None = None) -> Optional[int]:
        """
        Best-effort appliance RAM size (MiB). Prefer explicit ctx, then env.
        We can't reliably query this from guestfs API in all builds.
        """
        # Explicit ctx fields (if your orchestrator provides them)
        for key in ("guestfs_memsize_mib", "memsize_mib", "appliance_memsize_mib"):
            try:
                v = int(getattr(ctx, key))  # type: ignore[arg-type]
                if v > 0:
                    return v
            except Exception:
                pass

        # Env used by libguestfs tooling
        for k in ("LIBGUESTFS_MEMSIZE", "VMDK2KVM_GUESTFS_MEMSIZE"):
            try:
                v = int(os.environ.get(k, "") or "0")
                if v > 0:
                    return v
            except Exception:
                pass

        return None

    def _xfs_safe_maxmem_mib(self, memsize_mib: Optional[int]) -> int:
        """
        Choose conservative -m for xfs_repair.

        Important:
          - xfs_repair -m is NOT a hard cap (manpage says it may exceed)
          - we must leave headroom for guestfsd + kernel + overshoot
        """
        if not memsize_mib or memsize_mib <= 0:
            return 768  # sane default if unknown

        # Reserve 1GiB outright; xfs_repair can exceed -m.
        reserve = 1024
        usable = max(256, memsize_mib - reserve)

        # Use only ~30% of total RAM for xfs_repair cache (extra conservative).
        m = int(memsize_mib * 0.30)

        # Clamp to a reasonable envelope
        m = max(256, min(m, usable))
        m = min(m, 2048)
        return m

    # -------------------------------------------------------------------------
    # Filesystem type detection
    # -------------------------------------------------------------------------

    def _vfs_type(self, g: guestfs.GuestFS, dev: str) -> str:
        """
        Enhanced filesystem type detection with fallbacks.

        Returns:
            Filesystem type string, empty if unknown.
        """
        dev_text = U.to_text(dev)
        self._log(logging.DEBUG, "🔎 vfs detect: probing %s", dev_text)

        # Method 1: guestfs vfs_type() (best)
        try:
            if hasattr(g, "vfs_type"):
                fs_type = U.to_text(g.vfs_type(dev_text)).strip()
                if fs_type:
                    self._log(logging.DEBUG, "🧬 vfs_type: %s -> %s", dev_text, fs_type)
                    return fs_type
        except Exception as e:
            self._log(logging.DEBUG, "🫥 vfs_type failed for %s: %s", dev_text, str(e))

        # Method 2: list_filesystems() mapping
        try:
            fsmap = g.list_filesystems() or {}
            for k, v in fsmap.items():
                if U.to_text(k) == dev_text:
                    fs_type = U.to_text(v).strip()
                    if fs_type:
                        self._log(logging.DEBUG, "🗺️  list_filesystems: %s -> %s", dev_text, fs_type)
                        return fs_type
        except Exception as e:
            self._log(logging.DEBUG, "🫥 list_filesystems failed: %s", str(e))

        # Method 3: `file -s` heuristic (best-effort)
        try:
            if hasattr(g, "command"):
                out_raw = g.command(["file", "-s", dev_text])
                out = U.to_text(out_raw)
                out_l = out.lower()
                if out:
                    self._log(logging.DEBUG, "📄 file -s %s => %s", dev_text, out.strip())
                for fs_candidate in sorted(self.SAFE_FS_TYPES | self.DANGEROUS_FS_TYPES):
                    if fs_candidate in out_l:
                        self._log(logging.DEBUG, "🧩 file heuristic: %s -> %s", dev_text, fs_candidate)
                        return fs_candidate
        except Exception as e:
            self._log(logging.DEBUG, "🫥 file -s failed for %s: %s", dev_text, str(e))

        self._log(logging.DEBUG, "❓ vfs detect: could not detect filesystem type for %s", dev_text)
        return ""

    def _classify_fs_type(self, fs_type: str) -> Dict[str, Any]:
        """
        Classify filesystem type and determine appropriate handling.

        Returns:
            Dictionary with classification info.
        """
        fs_lower = (fs_type or "").lower()
        fs_lower_norm = fs_lower.replace("-", "_")

        classification: Dict[str, Any] = {
            "type": fs_type,
            "is_dangerous": False,
            "is_safe": False,
            "is_special": False,
            "can_check": False,
            "can_repair": False,
            "recommended_action": "skip",
        }

        # Dangerous bucket (never auto-repair)
        if any(d in fs_lower_norm for d in self.DANGEROUS_FS_TYPES):
            classification["is_dangerous"] = True
            classification["recommended_action"] = "skip_dangerous"
            return classification

        # Special bucket
        if any(s in fs_lower_norm for s in self.SPECIAL_FS_TYPES):
            classification["is_special"] = True
            classification["recommended_action"] = "skip_special"
            return classification

        # Safe bucket
        if any(safe in fs_lower_norm for safe in self.SAFE_FS_TYPES):
            classification["is_safe"] = True
            classification["can_check"] = True

            if fs_lower_norm.startswith("ext"):
                classification["can_repair"] = True
                classification["recommended_action"] = "check_and_repair"
            elif fs_lower_norm == "xfs":
                classification["can_repair"] = True
                classification["recommended_action"] = "check_and_repair"
            elif fs_lower_norm in ("vfat", "ntfs", "exfat", "fat", "fat32"):
                classification["can_repair"] = True
                classification["recommended_action"] = "check_and_repair"

        return classification

    # -------------------------------------------------------------------------
    # Repair runners
    # -------------------------------------------------------------------------

    def _run_fsck_ext(
        self,
        g: guestfs.GuestFS,
        dev: str,
        dry_run: bool,
        force_repair: bool = False,
    ) -> Dict[str, Any]:
        """
        Run e2fsck on ext2/3/4 filesystems.
        """
        result: Dict[str, Any] = {
            "tool": "e2fsck",
            "device": dev,
            "dry_run": dry_run,
            "force_repair": force_repair,
            "success": False,
            "output": "",
            "error": None,
        }

        try:
            if hasattr(g, "command"):
                args = ["e2fsck"]

                if dry_run:
                    args.extend(["-n", "-v"])
                else:
                    if force_repair:
                        args.extend(["-p", "-f"])
                    else:
                        args.extend(["-p"])

                args.append(dev)
                result["command"] = " ".join(args)

                self._log(
                    logging.INFO,
                    "🧰 fsck(ext): %s dry_run=%s force=%s cmd=%s",
                    dev,
                    dry_run,
                    force_repair,
                    result["command"],
                )
                out = g.command(args)
                result["output"] = U.to_text(out)
                result["success"] = True

            elif hasattr(g, "e2fsck") and not dry_run:
                result["command"] = "guestfs.e2fsck(correct=True)"
                self._log(logging.INFO, "🧰 fsck(ext): %s via guestfs.e2fsck correct=True", dev)
                g.e2fsck(dev, correct=True)
                result["success"] = True

            else:
                result["error"] = "No supported e2fsck execution method in guestfs handle"
                self._log(logging.WARNING, "⚠️ fsck(ext): %s no supported method", dev)

        except Exception as e:
            result["error"] = str(e)
            self._log(logging.WARNING, "💥 fsck(ext) failed for %s: %s", dev, str(e))

        return result

    def _run_xfs_repair(
        self,
        g: guestfs.GuestFS,
        dev: str,
        dry_run: bool,
        force_repair: bool = False,
        ctx: Any | None = None,
    ) -> Dict[str, Any]:
        """
        Run xfs_repair on XFS filesystems.

        Safety:
          - always use -P (noprefetch)
          - always pass -m with conservative value
          - only use -L when force_repair=True (explicitly requested)
        """
        result: Dict[str, Any] = {
            "tool": "xfs_repair",
            "device": dev,
            "dry_run": dry_run,
            "force_repair": force_repair,
            "success": False,
            "output": "",
            "error": None,
        }

        try:
            if not hasattr(g, "command"):
                result["error"] = "guestfs handle does not support command()"
                self._log(logging.WARNING, "⚠️ xfs_repair: %s no guestfs.command()", dev)
                return result

            memsize = self._get_guestfs_memsize_mib_best_effort(ctx)
            maxmem = self._xfs_safe_maxmem_mib(memsize)

            # -P reduces memory spikes (prefetch can be hungry)
            args: List[str] = ["xfs_repair", "-P", "-m", str(maxmem)]

            if dry_run:
                args.append("-n")
            elif force_repair:
                args.append("-L")

            args.append(dev)
            result["command"] = " ".join(args)

            self._log(
                logging.INFO,
                "🧠 xfs_repair mem: dev=%s memsize=%sMiB maxmem(-m)=%sMiB dry_run=%s force=%s",
                dev,
                str(memsize) if memsize else "unknown",
                maxmem,
                dry_run,
                force_repair,
            )
            self._log(logging.INFO, "🧰 xfs_repair: cmd=%s", result["command"])

            out = g.command(args)
            result["output"] = U.to_text(out)
            result["success"] = True

        except Exception as e:
            result["error"] = str(e)
            self._log(logging.WARNING, "💥 xfs_repair failed for %s: %s", dev, str(e))

        return result

    def _run_vfat_check(self, g: guestfs.GuestFS, dev: str, dry_run: bool) -> Dict[str, Any]:
        """
        Run fsck.vfat on FAT filesystems.
        """
        result: Dict[str, Any] = {
            "tool": "fsck.vfat",
            "device": dev,
            "dry_run": dry_run,
            "success": False,
            "output": "",
            "error": None,
        }

        try:
            if not hasattr(g, "command"):
                result["error"] = "guestfs handle does not support command()"
                self._log(logging.WARNING, "⚠️ fsck.vfat: %s no guestfs.command()", dev)
                return result

            args = ["fsck.vfat"]
            if dry_run:
                args.append("-n")
            else:
                args.append("-a")
            args.append(dev)
            result["command"] = " ".join(args)

            self._log(logging.INFO, "🧰 fsck(vfat): %s dry_run=%s cmd=%s", dev, dry_run, result["command"])
            out = g.command(args)
            result["output"] = U.to_text(out)
            result["success"] = True

        except Exception as e:
            result["error"] = str(e)
            self._log(logging.WARNING, "💥 fsck.vfat failed for %s: %s", dev, str(e))

        return result

    def _run_ntfs_check(self, g: guestfs.GuestFS, dev: str, dry_run: bool) -> Dict[str, Any]:
        """
        Run ntfsfix on NTFS filesystems.
        """
        result: Dict[str, Any] = {
            "tool": "ntfsfix",
            "device": dev,
            "dry_run": dry_run,
            "success": False,
            "output": "",
            "error": None,
        }

        try:
            if not hasattr(g, "command"):
                result["error"] = "guestfs handle does not support command()"
                self._log(logging.WARNING, "⚠️ ntfsfix: %s no guestfs.command()", dev)
                return result

            args = ["ntfsfix"]
            if dry_run:
                args.append("-n")  # check only
            args.append(dev)  # device should be last
            result["command"] = " ".join(args)

            self._log(logging.INFO, "🧰 ntfsfix: %s dry_run=%s cmd=%s", dev, dry_run, result["command"])
            out = g.command(args)
            result["output"] = U.to_text(out)
            result["success"] = True

        except Exception as e:
            result["error"] = str(e)
            self._log(logging.WARNING, "💥 ntfsfix failed for %s: %s", dev, str(e))

        return result

    # -------------------------------------------------------------------------
    # Main entry: check/repair
    # -------------------------------------------------------------------------

    def check_and_repair(
        self,
        g: guestfs.GuestFS,
        dev: str,
        dry_run: bool = True,
        force_repair: bool = False,
        ctx: Any | None = None,
    ) -> Dict[str, Any]:
        """
        Enhanced filesystem check and repair with classification.

        Args:
            g: GuestFS instance
            dev: Device path (e.g., "/dev/sda1")
            dry_run: If True, only check, don't repair
            force_repair: If True, use more aggressive repair options
            ctx: Optional context (used for appliance memsize hints)

        Returns:
            Dictionary with detailed results.
        """
        t0 = time.time()
        self.stats["start_time"] = self.stats["start_time"] or t0

        dev_text = U.to_text(dev)

        result: Dict[str, Any] = {
            "device": dev_text,
            "fs_type": None,
            "classification": None,
            "dry_run": dry_run,
            "force_repair": force_repair,
            "check_result": None,
            "repair_result": None,
            "success": False,
            "warnings": [],
            "errors": [],
        }

        self.stats["total_devices"] += 1

        self._log(logging.INFO, "🧪 fs check: dev=%s dry_run=%s force=%s", dev_text, dry_run, force_repair)

        # Detect filesystem type
        fs_type = self._vfs_type(g, dev_text)
        result["fs_type"] = fs_type

        if not fs_type:
            msg = "Could not detect filesystem type"
            result["errors"].append(msg)
            self._log(logging.WARNING, "⏭️  skip: %s (%s)", dev_text, msg)
            self.stats["skipped"] += 1
            result["duration"] = time.time() - t0
            return result

        # Classify filesystem
        classification = self._classify_fs_type(fs_type)
        result["classification"] = classification

        self._log(
            logging.DEBUG,
            "🧭 classify: %s -> %s",
            dev_text,
            {
                "type": classification.get("type"),
                "dangerous": classification.get("is_dangerous"),
                "safe": classification.get("is_safe"),
                "special": classification.get("is_special"),
                "action": classification.get("recommended_action"),
            },
        )

        # Skip dangerous filesystems
        if classification["is_dangerous"]:
            msg = f"Dangerous filesystem type: {fs_type}"
            result["errors"].append(msg)
            self._log(logging.WARNING, "☢️  skip dangerous: %s (%s)", dev_text, fs_type)
            self.stats["skipped"] += 1
            result["duration"] = time.time() - t0
            return result

        # Skip special filesystems
        if classification["is_special"]:
            msg = f"Special filesystem type: {fs_type}"
            result["warnings"].append(msg)
            self._log(logging.INFO, "🧊 skip special: %s (%s)", dev_text, fs_type)
            self.stats["skipped"] += 1
            result["duration"] = time.time() - t0
            return result

        # Check if filesystem can be checked
        if not classification["can_check"]:
            msg = f"Cannot check filesystem type: {fs_type}"
            result["warnings"].append(msg)
            self._log(logging.INFO, "⏭️  skip: %s (%s)", dev_text, msg)
            self.stats["skipped"] += 1
            result["duration"] = time.time() - t0
            return result

        self._log(logging.INFO, "🔧 checking: %s (%s) dry_run=%s", dev_text, fs_type, dry_run)
        self.stats["checked"] += 1

        fs_lower = fs_type.lower().replace("-", "_")
        check_result: Optional[Dict[str, Any]] = None

        try:
            if fs_lower.startswith("ext"):
                check_result = self._run_fsck_ext(g, dev_text, dry_run, force_repair)
            elif fs_lower == "xfs":
                check_result = self._run_xfs_repair(g, dev_text, dry_run, force_repair, ctx=ctx)
            elif fs_lower in ("vfat", "fat", "fat32"):
                check_result = self._run_vfat_check(g, dev_text, dry_run)
            elif fs_lower in ("ntfs", "ntfs_3g"):
                check_result = self._run_ntfs_check(g, dev_text, dry_run)
            else:
                msg = f"No handler for filesystem type: {fs_type}"
                result["warnings"].append(msg)
                self._log(logging.INFO, "🤷 no handler: %s (%s)", dev_text, fs_type)
                self.stats["skipped"] += 1
                result["duration"] = time.time() - t0
                return result

            result["check_result"] = check_result
            result["success"] = bool(check_result and check_result.get("success", False))

        except Exception as e:
            msg = f"Check/repair failed: {str(e)}"
            result["errors"].append(msg)
            self._log(logging.ERROR, "💥 check/repair failed for %s: %s", dev_text, str(e))
            self.stats["errors"] += 1
            result["duration"] = time.time() - t0
            return result

        # Update stats + logs
        if result["success"] and not dry_run:
            self.stats["repaired"] += 1
            self._log(logging.INFO, "✅ repaired: %s (%s)", dev_text, fs_type)
        elif result["success"]:
            self._log(logging.INFO, "✅ checked: %s (%s)", dev_text, fs_type)
        else:
            self._log(
                logging.WARNING,
                "⚠️ check finished but not marked success: %s (%s) err=%s",
                dev_text,
                fs_type,
                (check_result or {}).get("error"),
            )

        result["duration"] = time.time() - t0
        self.stats["end_time"] = time.time()
        return result

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics from all operations."""
        stats = self.stats.copy()
        if stats["end_time"] and stats["start_time"]:
            stats["total_duration"] = stats["end_time"] - stats["start_time"]
        return stats


# Legacy functions for backward compatibility
def _vfs_type(g: guestfs.GuestFS, dev: str) -> str:
    """Backward compatibility wrapper."""
    fixer = FilesystemFixer()
    return fixer._vfs_type(g, dev)


def log_vfs_type_best_effort(ctx: Any, g: guestfs.GuestFS, dev: str) -> None:
    """Backward compatibility wrapper."""
    fixer = FilesystemFixer(ctx.logger if hasattr(ctx, "logger") else None)
    try:
        vt = fixer._vfs_type(g, dev)
        if vt and hasattr(ctx, "logger") and ctx.logger:
            ctx.logger.info("🧬 Root vfs_type(%s) = %s", dev, vt)
    except Exception:
        pass


def best_effort_fsck(ctx: Any, g: guestfs.GuestFS, dev: str) -> Dict[str, Any]:
    """Backward compatibility wrapper."""
    fixer = FilesystemFixer(ctx.logger if hasattr(ctx, "logger") else None)
    dry_run = bool(getattr(ctx, "dry_run", False))
    result = fixer.check_and_repair(g, dev, dry_run=dry_run, ctx=ctx)

    audit = {
        "attempted": result["success"] or bool(result.get("check_result")),
        "fstype": result.get("fs_type"),
        "mode": "dry_run" if dry_run else "repair",
        "ok": result["success"],
        "error": "\n".join(result.get("errors", [])) if result.get("errors") else None,
        "cmd": (result.get("check_result") or {}).get("command"),
        "classification": result.get("classification"),
        "warnings": result.get("warnings", []),
    }
    return audit


def fix_filesystems(ctx: Any, g: guestfs.GuestFS) -> Dict[str, Any]:
    """
    Enhanced offline filesystem fixer with better safety and reporting.

    Returns:
        Detailed audit dictionary with classification and results.
    """
    enabled = bool(getattr(ctx, "filesystem_repair_enable", False))
    if not enabled:
        if hasattr(ctx, "logger") and ctx.logger:
            ctx.logger.info("⏭️ filesystem fixer disabled (filesystem_repair_enable=false)")
        return {"enabled": False, "skipped": "filesystem_repair_disabled"}

    dry_run = bool(getattr(ctx, "dry_run", False))
    logger = ctx.logger if hasattr(ctx, "logger") else None
    fixer = FilesystemFixer(logger)

    if logger:
        logger.info("🧰 filesystem fixer: enabled=true dry_run=%s", dry_run)

    audit: Dict[str, Any] = {
        "enabled": True,
        "dry_run": dry_run,
        "fixer_version": "2.2",
        "devices_processed": [],
        "classification_summary": {"dangerous": 0, "safe": 0, "special": 0, "unknown": 0},
        "statistics": {},
        "errors": [],
        "warnings": [],
    }

    # Make sure we are unmounted
    try:
        if hasattr(ctx, "_safe_umount_all"):
            if logger:
                logger.debug("🔻 umount: using ctx._safe_umount_all()")
            ctx._safe_umount_all(g)
        else:
            try:
                if logger:
                    logger.debug("🔻 umount: using g.umount_all()")
                g.umount_all()
            except Exception as e:
                if logger:
                    logger.debug("🫥 umount_all failed (ignored): %s", str(e))
    except Exception as e:
        audit["warnings"].append(f"Unmount failed: {str(e)}")
        if logger:
            logger.warning("⚠️ umount step failed: %s", str(e))

    # Get all devices
    devices: List[Tuple[str, str]] = []
    try:
        fsmap = g.list_filesystems() or {}
        for dev, fstype in fsmap.items():
            d = U.to_text(dev)
            t = U.to_text(fstype)

            if not d.startswith("/dev/"):
                continue

            # Skip known non-filesystems
            t_norm = t.lower().replace("-", "_")
            if t_norm in ("swap", "crypto_luks", "lvm2_member"):
                continue

            devices.append((d, t))
    except Exception as e:
        audit["errors"].append(f"list_filesystems failed: {str(e)}")
        if logger:
            logger.error("💥 list_filesystems failed: %s", str(e))
        return audit

    root_dev = U.to_text(getattr(ctx, "root_dev", "") or "").strip()
    if root_dev:
        devices.sort(key=lambda x: (0 if x[0] == root_dev else 1, x[0]))

    if logger:
        logger.info("📦 filesystem devices: %d (root_dev=%s)", len(devices), root_dev or "unknown")
        logger.debug("🧾 devices: %s", [d for d, _t in devices])

    # Process each device
    for dev, hinted_fstype in devices:
        if logger:
            logger.info("➡️ device: %s (hint=%s)", dev, hinted_fstype or "n/a")

        device_result = fixer.check_and_repair(g, dev, dry_run=dry_run, ctx=ctx)
        audit["devices_processed"].append(device_result)

        classification = device_result.get("classification", {}) or {}
        if classification.get("is_dangerous"):
            audit["classification_summary"]["dangerous"] += 1
        elif classification.get("is_safe"):
            audit["classification_summary"]["safe"] += 1
        elif classification.get("is_special"):
            audit["classification_summary"]["special"] += 1
        else:
            audit["classification_summary"]["unknown"] += 1

        if device_result.get("errors"):
            audit["errors"].extend([f"{dev}: {err}" for err in device_result["errors"]])
            if logger:
                logger.warning("❌ device errors: %s => %s", dev, device_result["errors"])
        if device_result.get("warnings"):
            audit["warnings"].extend([f"{dev}: {warn}" for warn in device_result["warnings"]])
            if logger:
                logger.info("⚠️ device warnings: %s => %s", dev, device_result["warnings"])

    stats = fixer.get_stats()
    audit["statistics"] = stats

    audit["summary"] = {
        "total_devices": len(devices),
        "successfully_checked": stats.get("checked", 0),
        "successfully_repaired": stats.get("repaired", 0) if not dry_run else 0,
        "skipped": stats.get("skipped", 0),
        "errors": stats.get("errors", 0),
        "has_dangerous_filesystems": audit["classification_summary"]["dangerous"] > 0,
    }

    if logger:
        logger.info(
            "📊 fs summary: total=%d checked=%d repaired=%d skipped=%d errors=%d dangerous=%d",
            audit["summary"]["total_devices"],
            audit["summary"]["successfully_checked"],
            audit["summary"]["successfully_repaired"],
            audit["summary"]["skipped"],
            audit["summary"]["errors"],
            audit["classification_summary"]["dangerous"],
        )

    return audit
