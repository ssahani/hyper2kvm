# vmdk2kvm/fixers/grub_fixer.py
# ---------------------------------------------------------------------
# GRUB root= update + device.map cleanup + initramfs/grub regen
# Linux-only. Windows logic stays in windows_fixer.py.
# ---------------------------------------------------------------------

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import re

import guestfs  # type: ignore
from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn

from ..core.utils import U
from .fstab_rewriter import Ident, parse_btrfsvol_spec


# ---------------------------
# GRUB device.map cleanup
# ---------------------------

def remove_stale_device_map(self, g: guestfs.GuestFS) -> int:
    """
    Removes stale grub device.map files that often break after bus/controller changes
    (sda->vda, hd0 mappings, etc.).
    """
    removed = 0
    for p in ("/boot/grub2/device.map", "/boot/grub/device.map", "/etc/grub2-device.map"):
        try:
            if g.is_file(p):
                txt = U.to_text(g.read_file(p))
                # device.map often contains stale BIOS disk mappings after bus/controller change
                if "hd0" in txt or "sda" in txt or "vda" in txt:
                    self.logger.info(f"GRUB: removing stale device.map: {p}")
                    removed += 1
                    if not self.dry_run:
                        g.rm_f(p)
        except Exception:
            continue
    return removed


# ---------------------------
# root= stabilization in grub configs
# ---------------------------

def _stable_root_id(self, g: guestfs.GuestFS) -> Optional[str]:
    """
    Try hard to compute a stable root identifier usable as kernel cmdline root=...
    Returns something like UUID=..., PARTUUID=..., LABEL=..., etc.
    """
    root_dev = getattr(self, "root_dev", None)
    if not root_dev:
        return None

    # root_dev might be "btrfsvol:..." in some flows; normalize
    if isinstance(root_dev, str) and root_dev.startswith("btrfsvol:"):
        dev, _sv = parse_btrfsvol_spec(root_dev)
        root_dev = dev.strip()

    # by-* inside guest: attempt guestfs realpath
    if isinstance(root_dev, str) and root_dev.startswith("/dev/disk/by-"):
        try:
            rp = U.to_text(g.realpath(root_dev)).strip()
            if rp.startswith("/dev/"):
                root_dev = rp
        except Exception:
            pass

    if not isinstance(root_dev, str) or not root_dev.startswith("/dev/"):
        return None

    # Ident expects a specific device; for LVM, dm-*, etc it should still work if blkid logic is good.
    blk = Ident.g_blkid_map(g, root_dev)
    stable = Ident.choose_stable(blk)

    # If not found, try one extra trick: sometimes root_dev is the filesystem dev, but blkid map code
    # only knows partitions. If it's a disk, try first partition. If it's a partition, try parent disk.
    if not stable:
        try:
            # /dev/sda2 -> /dev/sda ; /dev/vda1 -> /dev/vda
            parent = re.sub(r"p?\d+$", "", root_dev)
            if parent != root_dev and parent.startswith("/dev/"):
                blk2 = Ident.g_blkid_map(g, parent)
                stable2 = Ident.choose_stable(blk2)
                if stable2:
                    stable = stable2
        except Exception:
            pass

    return stable


def update_grub_root(self, g: guestfs.GuestFS) -> int:
    """
    Best-effort root= update across:
      - /boot/grub2/grub.cfg
      - /boot/grub/grub.cfg
      - /etc/default/grub
    """
    if not getattr(self, "update_grub", False):
        return 0

    stable = _stable_root_id(self, g)
    if not stable:
        self.logger.warning("GRUB: could not find stable ID for root device; skipping root= update.")
        return 0

    new_root = f"root={stable}"
    self.logger.info(f"GRUB: setting {new_root}")

    targets = ["/boot/grub2/grub.cfg", "/boot/grub/grub.cfg", "/etc/default/grub"]
    changed = 0

    with Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Updating GRUB files", total=len(targets))
        for p in targets:
            try:
                if not g.is_file(p):
                    progress.update(task, advance=1)
                    continue

                old = U.to_text(g.read_file(p))

                # Replace all root=... tokens (best-effort).
                # Works for linux/linuxefi lines and for GRUB_CMDLINE_LINUX too.
                new = re.sub(r"\broot=\S+", new_root, old)

                if new == old:
                    progress.update(task, advance=1)
                    continue

                self.logger.info(f"Updated root= in {p}" + (" (dry-run)" if self.dry_run else ""))
                changed += 1

                if not self.dry_run:
                    self.backup_file(g, p)
                    g.write(p, new.encode("utf-8"))
            except Exception as e:
                self.logger.warning(f"Failed updating {p}: {e}")

            progress.update(task, advance=1)

    return changed


# ---------------------------
# initramfs + grub regeneration
# ---------------------------

def regen(self, g: guestfs.GuestFS) -> Dict[str, Any]:
    """
    Linux-only initramfs + GRUB regen.
    Windows handling stays in windows_fixer.py.
    """
    if not getattr(self, "regen_initramfs", False):
        return {"enabled": False}

    # If this is Windows, don't touch initramfs/grub.
    try:
        if getattr(self, "inspect_root", None) and (U.to_text(g.inspect_get_type(self.inspect_root)).lower() == "windows"):
            self.logger.info("regen(): Windows guest detected; skipping Linux initramfs/grub regeneration.")
            return {"enabled": True, "skipped": "windows"}
    except Exception:
        pass

    distro = ""
    version = ""
    if getattr(self, "inspect_root", None):
        try:
            distro = (U.to_text(g.inspect_get_distro(self.inspect_root)) or "").lower()
            product = U.to_text(g.inspect_get_product_name(self.inspect_root)) or ""
            version = product.split()[-1] if product else ""
        except Exception:
            pass

    if distro in ("debian", "ubuntu"):
        family = "debian"
    elif distro == "arch":
        family = "arch"
    else:
        family = "rpm/dracut"

    info: Dict[str, Any] = {"enabled": True, "distro": distro, "version": version, "family": family}

    if getattr(self, "dry_run", False):
        self.logger.info("DRY-RUN: skipping initramfs/grub regeneration.")
        info["dry_run"] = True
        return info

    self.logger.info(f"Initramfs plan: distro={distro} version={version} family={family}")
    self.logger.info("🛠️ Regenerating initramfs and GRUB...")

    def run_guest(cmd: List[str]) -> Tuple[bool, str]:
        try:
            self.logger.info(f"Running (guestfs): {' '.join(cmd)}")
            out = g.command(cmd)
            return True, U.to_text(out)
        except Exception as e:
            return False, str(e)

    guest_kvers: List[str] = []
    try:
        if g.is_dir("/lib/modules"):
            guest_kvers = [U.to_text(x) for x in g.ls("/lib/modules") if U.to_text(x).strip()]
    except Exception:
        guest_kvers = []

    # initramfs
    if family == "debian":
        ok, err = run_guest(["update-initramfs", "-u", "-k", "all"])
        if not ok:
            self.logger.warning(f"Initramfs cmd failed: update-initramfs -u -k all: {err}")
            run_guest(["update-initramfs", "-u"])
    elif family == "arch":
        ok, err = run_guest(["mkinitcpio", "-P"])
        if not ok:
            self.logger.warning(f"Initramfs cmd failed: mkinitcpio -P: {err}")
    else:
        ok, err = run_guest(["dracut", "-f"])
        if not ok and ("Cannot find module directory /lib/modules/" in err or "--no-kernel" in err):
            self.logger.warning(f"Initramfs cmd failed: dracut -f: {err}")
            if guest_kvers:
                kver = sorted(guest_kvers)[-1]
                self.logger.info(f"dracut workaround: using guest kver={kver}")
                ok2, err2 = run_guest(["dracut", "-f", "--kver", kver])
                if not ok2:
                    self.logger.warning(f"Initramfs cmd failed: dracut -f --kver {kver}: {err2}")
            run_guest(["dracut", "-f", "--regenerate-all"])

    # grub config regen
    if family == "debian":
        run_guest(["update-grub"])
    else:
        run_guest(["grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"])
        if g.is_file("/boot/grub/grub.cfg"):
            run_guest(["grub-mkconfig", "-o", "/boot/grub/grub.cfg"])

    info["guest_kernels"] = guest_kvers
    return info


# ---------------------------
# Optional: wire methods onto OfflineFSFix so existing self.* calls work.
# ---------------------------

def wire_into(cls: type) -> type:
    """
    Monkey-patch these helpers as instance methods:
      - remove_stale_device_map
      - update_grub_root
      - regen

    Usage (once, e.g. at bottom of offline_fixer.py or in fixers/__init__.py):
      from . import grub_fixer
      grub_fixer.wire_into(OfflineFSFix)
    """
    setattr(cls, "remove_stale_device_map", remove_stale_device_map)
    setattr(cls, "update_grub_root", update_grub_root)
    setattr(cls, "regen", regen)
    return cls
