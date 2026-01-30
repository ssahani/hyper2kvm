# SPDX-License-Identifier: LGPL-3.0-or-later
# vmdk2kvm/fixers/filesystem_fixer.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import guestfs  # type: ignore

from ..core.utils import U


def _vfs_type(g: guestfs.GuestFS, dev: str) -> str:
    """
    Best-effort filesystem type detection:
      - prefer guestfs vfs_type() if available
      - fall back to list_filesystems() map if present
    """
    try:
        if hasattr(g, "vfs_type"):
            t = U.to_text(g.vfs_type(dev)).strip()
            if t:
                return t
    except Exception:
        pass

    try:
        fsmap = g.list_filesystems() or {}
        # python_return_dict=True => dev keys may be bytes-ish
        for k, v in fsmap.items():
            if U.to_text(k) == dev:
                return U.to_text(v)
    except Exception:
        pass

    return ""


def log_vfs_type_best_effort(ctx: Any, g: guestfs.GuestFS, dev: str) -> None:
    """
    Logging helper for mount/debug paths. Kept here so offline_fixer stays thin.
    """
    try:
        vt = _vfs_type(g, dev)
        if vt:
            ctx.logger.info(f"Root vfs_type({dev}) = {vt}")
    except Exception:
        pass


def best_effort_fsck(ctx: Any, g: guestfs.GuestFS, dev: str) -> Dict[str, Any]:
    """
    Safe-ish fsck/repair attempt used as a fallback when mounting fails.

    - dry_run: prefer read-only checks (e2fsck -n, xfs_repair -n)
    - non-dry_run: allow "auto/repair-ish" where possible (e2fsck -p, xfs_repair -L)

    IMPORTANT:
      - Never run btrfs check automatically (too risky).
    """
    audit: Dict[str, Any] = {
        "attempted": False,
        "fstype": None,
        "mode": "dry_run" if bool(getattr(ctx, "dry_run", False)) else "repair",
        "ok": False,
        "error": None,
        "cmd": None,
    }

    fstype = _vfs_type(g, dev).strip()
    audit["fstype"] = fstype or None
    if not fstype:
        return audit

    # Never try btrfs "check" automatically; too risky.
    if fstype.startswith("btrfs"):
        return audit

    audit["attempted"] = True

    try:
        dry = bool(getattr(ctx, "dry_run", False))

        # ext2/3/4
        if fstype.startswith("ext"):
            if hasattr(g, "command"):
                args = ["e2fsck", "-n" if dry else "-p", dev]
                audit["cmd"] = args
                g.command(args)
                audit["ok"] = True
                return audit
            if hasattr(g, "e2fsck") and (not dry):
                audit["cmd"] = ["guestfs.e2fsck", dev]
                g.e2fsck(dev)
                audit["ok"] = True
                return audit
            return audit

        # xfs
        if fstype == "xfs" and hasattr(g, "command"):
            args = ["xfs_repair", "-n" if dry else "-L", dev]
            audit["cmd"] = args
            g.command(args)
            audit["ok"] = True
            return audit

        # vfat / others: no-op
        return audit

    except Exception as e:
        audit["error"] = str(e)
        return audit


def fix_filesystems(ctx: Any, g: guestfs.GuestFS) -> Dict[str, Any]:
    """
    Offline filesystem fixer pass (unmounted).
    Intended to be called as an explicit stage by OfflineFSFix.

    Behavior:
      - unmounts everything first
      - enumerates mountable filesystems
      - runs lightweight check/repair (best_effort_fsck) on supported types
      - does NOT touch btrfs
      - does NOT fail the whole pipeline; returns an audit dict
    """
    enabled = bool(getattr(ctx, "filesystem_repair_enable", False))
    if not enabled:
        return {"enabled": False, "skipped": "filesystem_repair_disabled"}

    audit: Dict[str, Any] = {
        "enabled": True,
        "dry_run": bool(getattr(ctx, "dry_run", False)),
        "attempted": [],
        "skipped": [],
        "errors": [],
        "summary": {"total": 0, "attempted": 0, "ok": 0, "failed": 0, "skipped": 0},
    }

    # Make sure we are unmounted; filesystem tools should run on block devs.
    try:
        if hasattr(ctx, "_safe_umount_all"):
            ctx._safe_umount_all(g)  # type: ignore[attr-defined]
        else:
            try:
                g.umount_all()
            except Exception:
                pass
    except Exception:
        pass

    # Prefer list_filesystems() to see LVs etc. after LUKS/LVM activation.
    devices: List[Tuple[str, str]] = []
    try:
        fsmap = g.list_filesystems() or {}
        for dev, fstype in fsmap.items():
            d = U.to_text(dev)
            t = U.to_text(fstype)
            if not d.startswith("/dev/"):
                continue
            if t in ("swap", "crypto_LUKS"):
                continue
            devices.append((d, t))
    except Exception as e:
        audit["errors"].append(f"list_filesystems_failed:{e}")
        return audit

    # Stable ordering: try root first if known, then the rest.
    root_dev = U.to_text(getattr(ctx, "root_dev", "") or "").strip()
    if root_dev:
        devices.sort(key=lambda x: (0 if x[0] == root_dev else 1, x[0]))

    audit["summary"]["total"] = len(devices)

    for dev, hinted in devices:
        fstype = _vfs_type(g, dev).strip() or hinted.strip()
        if not fstype:
            audit["skipped"].append({"device": dev, "reason": "unknown_fstype"})
            audit["summary"]["skipped"] += 1
            continue

        if fstype.startswith("btrfs"):
            audit["skipped"].append({"device": dev, "fstype": fstype, "reason": "btrfs_no_auto_check"})
            audit["summary"]["skipped"] += 1
            continue

        res = best_effort_fsck(ctx, g, dev)
        audit["attempted"].append({"device": dev, "fstype": fstype, **res})
        audit["summary"]["attempted"] += 1
        if res.get("ok"):
            audit["summary"]["ok"] += 1
        else:
            audit["summary"]["failed"] += 1

    return audit
