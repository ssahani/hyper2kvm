# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/offline/mount.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...

from ...core.utils import U, guest_has_cmd
from ..filesystem import fixer as filesystem_fixer  # type: ignore
from ..filesystem.fstab import parse_btrfsvol_spec


@dataclass
class RootMountResult:
    inspect_root: str | None
    root_dev: str | None
    root_btrfs_subvol: str | None
    method: str
    details: dict[str, Any]


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

    @staticmethod
    def _sanitize_subvol_path(subvol: str) -> str:
        """
        Sanitize BTRFS subvolume path to prevent path traversal and option injection.

        SECURITY: Validates subvolume paths to prevent:
        - Path traversal attacks (../)
        - Mount option injection (commas, special chars)
        - Command injection attempts

        Args:
            subvol: BTRFS subvolume path to validate

        Returns:
            Sanitized subvolume path

        Raises:
            ValueError: If subvolume path contains dangerous characters
        """
        if not subvol:
            raise ValueError("Subvolume path cannot be empty")

        # Check for path traversal attempts
        if ".." in subvol:
            raise ValueError(f"Invalid subvolume path: contains '..': {subvol!r}")

        # Check for null bytes (path truncation attack)
        if "\x00" in subvol:
            raise ValueError(f"Invalid subvolume path: contains null byte: {subvol!r}")

        # Check for mount option injection attempts (commas separate mount options)
        if "," in subvol:
            raise ValueError(f"Invalid subvolume path: contains comma: {subvol!r}")

        # Check for shell metacharacters (defense in depth)
        dangerous_chars = [";", "&", "|", "`", "$", "(", ")", "<", ">", "\n", "\r"]
        for char in dangerous_chars:
            if char in subvol:
                raise ValueError(f"Invalid subvolume path: contains dangerous character: {subvol!r}")

        # Normalize path separators and remove redundant slashes
        normalized = subvol.replace("\\", "/")
        # Remove double slashes but preserve leading slash
        parts = [p for p in normalized.split("/") if p]
        if normalized.startswith("/"):
            normalized = "/" + "/".join(parts)
        else:
            normalized = "/".join(parts)

        # Additional length check (defense in depth)
        if len(normalized) > 4096:
            raise ValueError(f"Subvolume path too long (max 4096): {len(normalized)}")

        return normalized

    def __init__(
        self,
        logger: logging.Logger,
        *,
        dry_run: bool,
        # LUKS config
        luks_enable: bool = False,
        luks_passphrase: str | None = None,
        luks_passphrase_env: str | None = None,
        luks_keyfile: Path | None = None,
        luks_mapper_prefix: str = "hyper2kvm-crypt",
    ):
        self.logger = logger
        self.dry_run = bool(dry_run)

        self.luks_enable = bool(luks_enable)
        self.luks_passphrase = luks_passphrase
        self.luks_passphrase_env = luks_passphrase_env
        self.luks_keyfile = Path(luks_keyfile) if luks_keyfile else None
        self.luks_mapper_prefix = luks_mapper_prefix

        self._luks_opened: dict[str, str] = {}  # luks_dev -> /dev/mapper/name

    # safe helpers

    @staticmethod
    def safe_umount_all(g: guestfs.GuestFS) -> None:
        try:
            g.umount_all()
        except Exception:
            pass

    # LUKS / LVM

    def _read_luks_key_bytes(self) -> bytes | None:
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

    def activate_lvm(self, g: guestfs.GuestFS) -> dict[str, Any]:
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None}
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

    def unlock_luks_devices(self, g: guestfs.GuestFS) -> dict[str, Any]:
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

        # After opening LUKS, LVM may appear
        if audit["opened"]:
            _ = self.activate_lvm(g)
        return audit

    # mdraid/zfs — additive

    def _guestfs_can_run(self, g: guestfs.GuestFS, prog: str) -> bool:
        try:
            return bool(getattr(g, "command", None)) and guest_has_cmd(g, prog)
        except Exception:
            return False

    def activate_mdraid(self, g: guestfs.GuestFS) -> dict[str, Any]:
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

    def activate_zfs(self, g: guestfs.GuestFS) -> dict[str, Any]:
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
            g.command(["sh", "-lc", "ZPOOL_VDEV_NAME_PATH=1 zpool import -a -N -f 2>/dev/null || true"])
            audit["ok"] = True
            return audit
        except Exception as e:
            audit["error"] = str(e)
            return audit

    def pre_mount_activate_storage_stack(self, g: guestfs.GuestFS) -> dict[str, Any]:
        audit: dict[str, Any] = {"mdraid": None, "zfs": None, "lvm": None}
        audit["mdraid"] = self.activate_mdraid(g)
        audit["zfs"] = self.activate_zfs(g)
        audit["lvm"] = self.activate_lvm(g)
        return audit

    # mount logic

    def _try_mount_root(self, g: guestfs.GuestFS, dev: str, subvol: str | None, mode: str) -> None:
        # mode: "rw" | "ro" | "opts:<csv>"
        if subvol:
            # SECURITY: Validate subvolume path to prevent path traversal and option injection
            try:
                sanitized_subvol = self._sanitize_subvol_path(subvol)
            except ValueError as e:
                self.logger.error(f"Rejecting dangerous subvolume path: {e}")
                raise RuntimeError(f"Invalid subvolume path: {e}") from e

            opts = f"subvol={sanitized_subvol}"
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

    def mount_root_direct(self, g: guestfs.GuestFS, dev: str, subvol: str | None) -> None:
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

    def _candidate_root_devices(self, g: guestfs.GuestFS) -> list[str]:
        """
        Build candidate list for root filesystem detection.

        Uses native guestfs calls instead of shell commands to avoid
        dependencies on /bin/sh in minimal appliances.
        """
        candidates: list[str] = []

        # 1. Partitions
        try:
            partitions = [U.to_text(p) for p in (g.list_partitions() or [])]
            candidates.extend(partitions)
            self.logger.debug(f"Partitions: {partitions}")
        except Exception as e:
            self.logger.warning(f"Failed to list partitions: {e}")

        # 2. Filesystems (includes /dev/mapper/* from list_filesystems)
        try:
            fsmap = g.list_filesystems() or {}
            self.logger.debug(f"Filesystems map: {list(fsmap.keys())}")
            for dev, fstype in fsmap.items():
                d = U.to_text(dev)
                t = U.to_text(fstype)
                # Skip swap and LUKS containers (we want unlocked devices)
                if t in ("swap", "crypto_LUKS"):
                    self.logger.debug(f"Skipping {d} (type={t})")
                    continue
                if d.startswith("/dev/"):
                    candidates.append(d)
                    self.logger.debug(f"Added from filesystems: {d} (type={t})")
        except Exception as e:
            self.logger.warning(f"Failed to list filesystems: {e}")

        # 3. LVM logical volumes (native guestfs call)
        try:
            if hasattr(g, "lvs"):
                lvs_list = g.lvs() or []
                self.logger.info(f"🔍 LVM logical volumes: {lvs_list}")
                for lv in lvs_list:
                    d = U.to_text(lv)
                    if d.startswith("/dev/"):
                        candidates.append(d)
                        self.logger.info(f"✅ Added LV candidate: {d}")
        except Exception as e:
            self.logger.warning(f"⚠️ LVM enumeration failed: {e}")

        # 4. Deduplicate while preserving order
        seen: set[str] = set()
        out: list[str] = []
        for d in candidates:
            if d and d not in seen:
                seen.add(d)
                out.append(d)

        # Filter out known non-root devices
        filtered = []
        for d in out:
            # Skip libguestfs appliance loop devices
            if d.startswith("/dev/loop"):
                self.logger.debug(f"Filtering out loop device: {d}")
                continue
            # Skip LUKS placeholder devices that don't exist
            if "/luks-" in d and not d.startswith("/dev/mapper/luks-"):
                self.logger.debug(f"Filtering out LUKS placeholder: {d}")
                continue
            filtered.append(d)

        # Prioritize LVM logical volumes and mapper devices
        # Try these first as they're most likely to be root filesystems
        priority = []
        standard = []
        for d in filtered:
            if d.startswith("/dev/mapper/") and "control" not in d.lower():
                priority.append(d)
            elif "/dev/" in d and ("-" in d.split("/")[-1] or d.startswith("/dev/vg")):
                # LVM naming pattern: /dev/vgname-lvname or /dev/vgname/lvname
                priority.append(d)
            else:
                standard.append(d)

        result = priority + standard
        self.logger.info(f"📋 Candidate priority order: {result}")
        return result

    def mount_root_bruteforce(self, g: guestfs.GuestFS) -> RootMountResult:
        candidates = self._candidate_root_devices(g)
        self.logger.info(f"🔍 Brute-force mount candidates: {candidates}")
        if not candidates:
            raise RuntimeError("Failed to list partitions/filesystems for brute-force mount")

        mount_failures: list[dict[str, str]] = []

        best: tuple[int, str | None] = (-10**9, None)
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

        best_btrfs: tuple[int, str | None, str | None] = (-10**9, None, None)
        for dev in candidates:
            # Check filesystem type before trying btrfs subvolumes
            self.logger.info(f"🔍 Checking {dev} for btrfs subvolume mounting...")
            try:
                vfs_type = filesystem_fixer._vfs_type(g, dev)
                filesystem_fixer.log_vfs_type_best_effort(self, g, dev)
            except Exception:
                vfs_type = "unknown"

            # Only try btrfs subvolume mounting on actual btrfs filesystems
            if vfs_type != "btrfs":
                self.logger.info(f"⏭️ Skipping {dev} (vfs_type={vfs_type}, not btrfs) - NO SUBVOL MOUNTS")
                continue

            self.logger.info(f"✅ {dev} is btrfs, trying subvolume mounts...")
            for sv in self._BTRFS_COMMON_SUBVOLS:
                self.safe_umount_all(g)
                try:
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

        try:
            mp_map = g.inspect_get_mountpoints(root)
        except Exception:
            mp_map = {}

        root_spec = U.to_text(mp_map.get("/", "")).strip()
        if not root_spec:
            return self.mount_root_bruteforce(g)

        root_dev = root_spec
        subvol: str | None = None
        if root_spec.startswith("btrfsvol:"):
            root_dev, subvol = parse_btrfsvol_spec(root_spec)
            root_dev = root_dev.strip()

        real: str | None = None
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
