# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/offline/mount.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import os
import tempfile
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import guestfs  # type: ignore

from ...core.utils import U, guest_has_cmd
from ..filesystem.fstab import parse_btrfsvol_spec
from ..filesystem import fixer as filesystem_fixer  # type: ignore


@dataclass
class RootMountResult:
    inspect_root: Optional[str]
    root_dev: Optional[str]
    root_btrfs_subvol: Optional[str]
    method: str
    details: Dict[str, Any]


class OfflineMountEngine:
    """
    Storage-stack + root-mount engine for OfflineFSFix.

    Responsibilities:
      - Additive storage activation: mdraid, zfs, lvm, luks-open
      - Root detection: inspect_os + scoring + fallback brute-force
      - Mount ladder: rw/ro/options + fsck best-effort retry
    """

    _BTRFS_COMMON_SUBVOLS = ["@", "@/", "@root", "@rootfs", "@/.snapshots/1/snapshot"]
    _ROOT_HINT_FILES = ["/etc/fstab", "/etc/os-release", "/bin/sh", "/sbin/init"]
    _ROOT_STRONG_HINTS = ["/etc/passwd", "/usr/bin/env", "/var/lib", "/proc"]  # heuristic only

    def __init__(
        self,
        logger: logging.Logger,
        *,
        dry_run: bool,
        # LUKS config
        luks_enable: bool = False,
        luks_passphrase: Optional[str] = None,
        luks_passphrase_env: Optional[str] = None,
        luks_keyfile: Optional[Path] = None,
        luks_mapper_prefix: str = "hyper2kvm-crypt",
    ):
        self.logger = logger
        self.dry_run = bool(dry_run)

        self.luks_enable = bool(luks_enable)
        self.luks_passphrase = luks_passphrase
        self.luks_passphrase_env = luks_passphrase_env
        self.luks_keyfile = Path(luks_keyfile) if luks_keyfile else None
        self.luks_mapper_prefix = luks_mapper_prefix

        self._luks_opened: Dict[str, str] = {}  # luks_dev -> /dev/mapper/name

    # -----------------------
    # safe helpers
    # -----------------------

    @staticmethod
    def safe_umount_all(g: guestfs.GuestFS) -> None:
        try:
            g.umount_all()
        except Exception:
            pass

    # -----------------------
    # LUKS / LVM
    # -----------------------

    def _read_luks_key_bytes(self) -> Optional[bytes]:
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

    def activate_lvm(self, g: guestfs.GuestFS) -> Dict[str, Any]:
        audit: Dict[str, Any] = {"attempted": False, "ok": False, "error": None}
        if not hasattr(g, "vgscan") or not hasattr(g, "vgchange_activate_all"):
            audit["error"] = "guestfs_missing:lvm"
            return audit
        audit["attempted"] = True
        try:
            g.vgscan()
            try:
                g.vgchange_activate_all(True)
            except Exception:
                g.vgchange_activate_all(1)
            audit["ok"] = True
            return audit
        except Exception as e:
            audit["error"] = str(e)
            return audit

    def unlock_luks_devices(self, g: guestfs.GuestFS) -> Dict[str, Any]:
        audit: Dict[str, Any] = {
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

        # After opening LUKS, LVM may appear
        if audit["opened"]:
            _ = self.activate_lvm(g)
        return audit

    # -----------------------
    # mdraid/zfs — additive
    # -----------------------

    def _guestfs_can_run(self, g: guestfs.GuestFS, prog: str) -> bool:
        try:
            return bool(getattr(g, "command", None)) and guest_has_cmd(g, prog)
        except Exception:
            return False

    def activate_mdraid(self, g: guestfs.GuestFS) -> Dict[str, Any]:
        audit: Dict[str, Any] = {"attempted": False, "ok": False, "details": "", "error": None}
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

    def activate_zfs(self, g: guestfs.GuestFS) -> Dict[str, Any]:
        if not self._guestfs_can_run(g, "zpool"):
            return {"attempted": False, "ok": False, "reason": "zpool_not_available_in_appliance"}
        audit: Dict[str, Any] = {"attempted": True, "ok": False, "pools": [], "error": None}
        try:
            out = g.command(["sh", "-lc", "ZPOOL_VDEV_NAME_PATH=1 zpool import 2>/dev/null || true"])
            text = U.to_text(out).strip()
            audit["pools"] = [ln.strip() for ln in text.splitlines() if ln.strip()][:100]
        except Exception:
            pass
        try:
            g.command(["sh", "-lc", "ZPOOL_VDEV_NAME_PATH=1 zpool import -a -N -f 2>/dev/null || true"])
            audit["ok"] = True
            return audit
        except Exception as e:
            audit["error"] = str(e)
            return audit

    def pre_mount_activate_storage_stack(self, g: guestfs.GuestFS) -> Dict[str, Any]:
        audit: Dict[str, Any] = {"mdraid": None, "zfs": None, "lvm": None}
        audit["mdraid"] = self.activate_mdraid(g)
        audit["zfs"] = self.activate_zfs(g)
        audit["lvm"] = self.activate_lvm(g)
        return audit

    # -----------------------
    # mount logic
    # -----------------------

    def _try_mount_root(self, g: guestfs.GuestFS, dev: str, subvol: Optional[str], mode: str) -> None:
        # mode: "rw" | "ro" | "opts:<csv>"
        if subvol:
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

        g.mount_ro(dev, "/")

    def mount_root_direct(self, g: guestfs.GuestFS, dev: str, subvol: Optional[str]) -> None:
        """
        Mount ladder:
          1) rw/ro (original)
          2) ro + mount_options fallback (noload/norecovery)
          3) best-effort fsck then ro retry
        """
        filesystem_fixer.log_vfs_type_best_effort(self, g, dev)

        # 1) original path
        try:
            self._try_mount_root(g, dev, subvol, "rw" if not self.dry_run else "ro")
            return
        except Exception as first_err:
            last_err: Exception = first_err  # type: ignore[assignment]

        # 2) fallback ladder
        tries = ["ro", "opts:noload", "opts:ro, noload", "opts:ro, norecovery"]
        for t in tries:
            self.safe_umount_all(g)
            try:
                self._try_mount_root(g, dev, subvol, t)
                return
            except Exception as e:
                last_err = e  # type: ignore[misc]

        # 3) fsck then ro retry
        self.safe_umount_all(g)
        _ = filesystem_fixer.best_effort_fsck(self, g, dev)

        self.safe_umount_all(g)
        try:
            self._try_mount_root(g, dev, subvol, "ro")
            return
        except Exception as e:
            last_err = e  # type: ignore[misc]

        raise RuntimeError(f"Failed mounting root {dev} (subvol={subvol}): {last_err}")

    def looks_like_root(self, g: guestfs.GuestFS) -> bool:
        hits = 0
        for p in self._ROOT_HINT_FILES:
            try:
                if g.is_file(p):
                    hits += 1
            except Exception:
                continue
        for p in self._ROOT_STRONG_HINTS:
            try:
                if p.endswith("/"):
                    if g.is_dir(p[:-1]):
                        hits += 1
                else:
                    if g.is_file(p) or g.is_dir(p):
                        hits += 1
            except Exception:
                continue
        return hits >= 2

    def score_root(self, g: guestfs.GuestFS) -> int:
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

    def _candidate_root_devices(self, g: guestfs.GuestFS) -> List[str]:
        candidates: List[str] = []

        try:
            candidates.extend([U.to_text(p) for p in (g.list_partitions() or [])])
        except Exception:
            pass

        try:
            fsmap = g.list_filesystems() or {}
            for dev, fstype in fsmap.items():
                d = U.to_text(dev)
                t = U.to_text(fstype)
                if t in ("swap", "crypto_LUKS"):
                    continue
                if d.startswith("/dev/"):
                    candidates.append(d)
        except Exception:
            pass

        try:
            if hasattr(g, "lvs"):
                for lv in (g.lvs() or []):
                    d = U.to_text(lv)
                    if d.startswith("/dev/"):
                        candidates.append(d)
        except Exception:
            pass

        try:
            if hasattr(g, "command"):
                out = g.command(["sh", "-lc", "ls -1 /dev/md* 2>/dev/null || true"])
                for ln in U.to_text(out).splitlines():
                    d = ln.strip()
                    if d.startswith("/dev/"):
                        candidates.append(d)
        except Exception:
            pass

        try:
            if hasattr(g, "command"):
                out = g.command(["sh", "-lc", "ls -1 /dev/mapper/* 2>/dev/null || true"])
                for ln in U.to_text(out).splitlines():
                    d = ln.strip()
                    if d.startswith("/dev/mapper/") and "control" not in d:
                        candidates.append(d)
        except Exception:
            pass

        seen: set[str] = set()
        out: List[str] = []
        for d in candidates:
            if d and d not in seen:
                seen.add(d)
                out.append(d)
        return out

    def mount_root_bruteforce(self, g: guestfs.GuestFS) -> RootMountResult:
        candidates = self._candidate_root_devices(g)
        if not candidates:
            raise RuntimeError("Failed to list partitions/filesystems for brute-force mount")

        mount_failures: List[Dict[str, str]] = []

        best: Tuple[int, Optional[str]] = (-10**9, None)
        for dev in candidates:
            self.safe_umount_all(g)
            try:
                filesystem_fixer.log_vfs_type_best_effort(self, g, dev)
                if self.dry_run:
                    g.mount_ro(dev, "/")
                else:
                    g.mount(dev, "/")
                if self.looks_like_root(g):
                    sc = self.score_root(g)
                    if sc > best[0]:
                        best = (sc, dev)
                self.safe_umount_all(g)
            except Exception as e:
                mount_failures.append({"device": dev, "error": str(e)})

        if best[1]:
            dev = best[1]
            self.safe_umount_all(g)
            if self.dry_run:
                g.mount_ro(dev, "/")
            else:
                g.mount(dev, "/")
            return RootMountResult(
                inspect_root=None,
                root_dev=dev,
                root_btrfs_subvol=None,
                method="bruteforce",
                details={"score": best[0], "failures": mount_failures[:200]},
            )

        best_btrfs: Tuple[int, Optional[str], Optional[str]] = (-10**9, None, None)
        for dev in candidates:
            for sv in self._BTRFS_COMMON_SUBVOLS:
                self.safe_umount_all(g)
                try:
                    filesystem_fixer.log_vfs_type_best_effort(self, g, dev)
                    opts = f"subvol={sv}"
                    if self.dry_run:
                        opts = f"ro, {opts}"
                    g.mount_options(opts, dev, "/")
                    if self.looks_like_root(g):
                        sc = self.score_root(g)
                        if sc > best_btrfs[0]:
                            best_btrfs = (sc, dev, sv)
                    self.safe_umount_all(g)
                except Exception as e:
                    mount_failures.append({"device": f"{dev} subvol={sv}", "error": str(e)})

        if best_btrfs[1] and best_btrfs[2]:
            dev = best_btrfs[1]
            sv = best_btrfs[2]
            self.safe_umount_all(g)
            opts = f"subvol={sv}"
            if self.dry_run:
                opts = f"ro, {opts}"
            g.mount_options(opts, dev, "/")
            return RootMountResult(
                inspect_root=None,
                root_dev=dev,
                root_btrfs_subvol=sv,
                method="bruteforce-btrfs",
                details={"score": best_btrfs[0], "failures": mount_failures[:200]},
            )

        raise RuntimeError(f"Failed to mount root filesystem (failures={mount_failures[:40]})")

    def detect_and_mount_root(self, g: guestfs.GuestFS) -> RootMountResult:
        """
        Preferred path: inspect_os -> mountpoints -> mount_root_direct.
        Fallback: bruteforce.
        """
        try:
            roots = g.inspect_os()
        except Exception:
            roots = []

        if not roots:
            r = self.mount_root_bruteforce(g)
            return r

        # Pick best-looking root (avoid roots[0] roulette)
        best_root: Optional[str] = None
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

        try:
            mp_map = g.inspect_get_mountpoints(root)
        except Exception:
            mp_map = {}

        root_spec = U.to_text(mp_map.get("/", "")).strip()
        if not root_spec:
            return self.mount_root_bruteforce(g)

        root_dev = root_spec
        subvol: Optional[str] = None
        if root_spec.startswith("btrfsvol:"):
            root_dev, subvol = parse_btrfsvol_spec(root_spec)
            root_dev = root_dev.strip()

        real: Optional[str] = None
        if root_dev.startswith("/dev/disk/by-"):
            try:
                rp = U.to_text(g.realpath(root_dev)).strip()
                if rp.startswith("/dev/"):
                    real = rp
            except Exception:
                real = None

        if not real and root_dev.startswith("/dev/disk/by-path/"):
            return self.mount_root_bruteforce(g)

        if not real and root_dev.startswith("/dev/"):
            real = root_dev

        if not real:
            return self.mount_root_bruteforce(g)

        try:
            self.mount_root_direct(g, real, subvol)
            return RootMountResult(
                inspect_root=root,
                root_dev=real,
                root_btrfs_subvol=subvol,
                method="inspect_os",
                details={"chosen_root_score": best_score},
            )
        except Exception:
            # fallback
            return self.mount_root_bruteforce(g)
