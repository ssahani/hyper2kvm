# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/bootloader/grub.py
# -*- coding: utf-8 -*-
# GRUB/root= stabilization + device.map cleanup + initramfs + bootloader regen
# Linux-only. Windows logic stays in windows_fixer.py.
#
# Philosophy (keep this file "boot stuff only"):
#   - Anything that mutates kernel cmdline / bootloader config / initramfs belongs here.
#   - Hypervisor tools removal + QGA firstboot scheduling are *not* bootloader concerns;
#     they fit better in OfflineFSFix orchestration (or a dedicated hv_tools_fixer.py).
#
# Operational constraints:
#   - We operate offline via libguestfs, not a real booted system.
#   - Avoid workflows that require efivars/proc/sys being mounted.
#   - Best-effort: failures must not hard-fail the overall conversion.
#
# Strong practical fix:
#   - Many guests have a separate /boot (and /boot/efi). If we regenerate initramfs
#     or grub.cfg without mounting them, we "succeed" but write into the rootfs /
#     directory, producing broken boots. So: mount /boot and /boot/efi temporarily
#     (from /etc/fstab) before regen, then unmount.

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...

from ...core.utils import U, guest_has_cmd
from ..filesystem.fstab import Ident, parse_btrfsvol_spec

# tiny helpers

def _logger(self):
    return getattr(self, "logger", None)


def _log_info(self, msg: str) -> None:
    lg = _logger(self)
    if lg:
        lg.info(msg)
    else:
        print(msg)


def _log_warn(self, msg: str) -> None:
    lg = _logger(self)
    if lg:
        lg.warning(msg)
    else:
        print(f"WARNING: {msg}")


def _log_debug(self, msg: str) -> None:
    lg = _logger(self)
    if lg:
        lg.debug(msg)


def _dedup_keep_order(xs: list[str]) -> list[str]:
    seen = set()
    out: list[str] = []
    for x in xs:
        s = (x or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _read_text(g: guestfs.GuestFS, path: str) -> str:
    try:
        return U.to_text(g.read_file(path)) if g.is_file(path) else ""
    except Exception:
        return ""


def _write_text(self, g: guestfs.GuestFS, path: str, text: str) -> None:
    if getattr(self, "dry_run", False):
        return
    if hasattr(self, "backup_file"):
        try:
            self.backup_file(g, path)
        except Exception:
            pass
    g.write(path, text.encode("utf-8"))


def _append_text(self, g: guestfs.GuestFS, path: str, text: str) -> None:
    if getattr(self, "dry_run", False):
        return
    cur = _read_text(g, path) if g.is_file(path) else ""
    if hasattr(self, "backup_file") and g.is_file(path):
        try:
            self.backup_file(g, path)
        except Exception:
            pass
    g.write(path, (cur + text).encode("utf-8"))


def _file_exists(g: guestfs.GuestFS, p: str) -> bool:
    try:
        return g.is_file(p)
    except Exception:
        return False


def _dir_exists(g: guestfs.GuestFS, p: str) -> bool:
    try:
        return g.is_dir(p)
    except Exception:
        return False


def _glob(g: guestfs.GuestFS, pattern: str) -> list[str]:
    try:
        return [U.to_text(x) for x in g.glob_expand(pattern)]
    except Exception:
        return []


def _run_guestfs_cmd(self, g: guestfs.GuestFS, cmd: list[str]) -> tuple[bool, str]:
    """
    Best-effort command execution via libguestfs appliance.

    For bootloader commands (grub2-mkconfig, update-grub, etc.), uses command_with_mounts
    to provide /proc, /dev, /sys access. Falls back to command_quiet for other commands.

    Note: Bootloader commands need /proc/self/mountinfo and /dev to work properly.
    Failures are logged at DEBUG level only.
    """
    try:
        _log_info(self, f"Running (guestfs): {' '.join(cmd)}")

        # Bootloader commands that need /proc, /dev, /sys mounted
        bootloader_commands = [
            "grub2-mkconfig", "grub-mkconfig", "update-grub", "update-grub2",
            "grub2-install", "grub-install", "grub2-probe", "grub-probe"
        ]

        # Check if this is a bootloader command
        is_bootloader_cmd = any(cmd[0] == bc for bc in bootloader_commands) if cmd else False

        # Try command_with_mounts for bootloader commands (VMCraft only)
        if is_bootloader_cmd and hasattr(g, 'command_with_mounts'):
            _log_debug(self, f"Using enhanced chroot with bind mounts for {cmd[0]}")
            out = g.command_with_mounts(cmd, quiet=True)
            return True, U.to_text(out)

        # Fall back to standard command_quiet
        if hasattr(g, 'command_quiet'):
            out = g.command_quiet(cmd)
        else:
            out = g.command(cmd)
        return True, U.to_text(out)

    except Exception as e:
        # Failure is expected in offline mode; already logged at DEBUG level
        return False, str(e)


# distro / family hints

def _inspect_distro_major(self, g: guestfs.GuestFS) -> tuple[str, int]:
    distro = ""
    major = 0
    try:
        if getattr(self, "inspect_root", None):
            distro = (U.to_text(g.inspect_get_distro(self.inspect_root)) or "").lower()
            major = int(g.inspect_get_major_version(self.inspect_root) or 0)
    except Exception:
        pass

    # Extra: Photon sometimes comes back as "photon" or unknown; /etc/os-release is reliable.
    if not distro:
        osr = _read_text(g, "/etc/os-release")
        m = re.search(r'(?m)^\s*ID="?([^"\n]+)"?\s*$', osr)
        if m:
            distro = m.group(1).strip().lower()
    return distro, major


def _detect_family(distro: str) -> str:
    d = (distro or "").lower()

    # RHEL-ish (+ common derivatives and cloud distros)
    if d in (
        "fedora", "rhel", "centos", "circle", "scientificlinux", "redhat-based",
        "oraclelinux", "rocky", "almalinux",
        "amzn", "amazon", "amazonlinux",      # Amazon Linux
        "mariner", "cbl-mariner",             # Microsoft CBL-Mariner
        "mageia", "openmandriva",             # rpm-ish
        "photon",                             # VMware Photon (tdnf + dracut)
    ):
        return "rhel"

    # SUSE-ish
    if d in ("sles", "sled", "suse-based", "opensuse", "opensuse-leap", "opensuse-tumbleweed"):
        return "suse"

    # Debian-ish
    if d in (
        "debian", "ubuntu", "linuxmint", "kalilinux", "kali",
        "raspbian", "pop", "popos", "elementary", "zorin", "deepin",
    ):
        return "debian"

    # Arch-ish
    if d in ("arch", "manjaro", "endeavouros", "garuda"):
        return "arch"

    # Alpine
    if d in ("alpine",):
        return "alpine"

    # Gentoo-ish
    if d in ("gentoo", "funtoo"):
        return "gentoo"

    # Void
    if d in ("void",):
        return "void"

    # NixOS
    if d in ("nixos",):
        return "nixos"

    return "other"


# Boot layout heuristics (offline)

def _guest_looks_uefi(g: guestfs.GuestFS) -> bool:
    # Strong: presence of an EFI tree with .efi binaries
    try:
        for base in ("/boot/efi", "/efi"):
            if _dir_exists(g, base) and _dir_exists(g, f"{base}/EFI"):
                try:
                    for x in g.find(f"{base}/EFI"):
                        p = U.to_text(x)
                        if p.lower().endswith(".efi"):
                            return True
                except Exception:
                    try:
                        return bool(g.ls(f"{base}/EFI"))
                    except Exception:
                        pass
    except Exception:
        pass

    # Weak: fstab has /boot/efi vfat
    try:
        fstab = _read_text(g, "/etc/fstab")
        if re.search(r"^\S+\s+/(boot/efi|efi)\s+vfat\b", fstab, flags=re.M):
            return True
    except Exception:
        pass

    return False


def _guest_has_bls(g: guestfs.GuestFS) -> bool:
    return _dir_exists(g, "/boot/loader/entries")


# root= stabilization

def _stable_root_id(self, g: guestfs.GuestFS) -> str | None:
    """
    Compute a stable root identifier usable as kernel cmdline root=...
    Returns UUID=... / PARTUUID=... / LABEL=... best-effort.
    """
    root_dev = getattr(self, "root_dev", None)
    if not root_dev:
        return None

    # btrfsvol: underlying device
    if isinstance(root_dev, str) and root_dev.startswith("btrfsvol:"):
        dev, _sv = parse_btrfsvol_spec(root_dev)
        root_dev = dev.strip()

    # /dev/disk/by-* -> resolve to /dev/..
    if isinstance(root_dev, str) and root_dev.startswith("/dev/disk/by-"):
        try:
            rp = U.to_text(g.realpath(root_dev)).strip()
            if rp.startswith("/dev/"):
                root_dev = rp
        except Exception:
            pass

    if not isinstance(root_dev, str) or not root_dev.startswith("/dev/"):
        return None

    blk = Ident.g_blkid_map(g, root_dev)
    stable = Ident.choose_stable(blk)

    # Sometimes root is a DM or btrfs wrapper; try "parent-ish" heuristic
    if not stable:
        try:
            parent = re.sub(r"p?\d+$", "", root_dev)
            if parent != root_dev and parent.startswith("/dev/"):
                blk2 = Ident.g_blkid_map(g, parent)
                stable2 = Ident.choose_stable(blk2)
                if stable2:
                    stable = stable2
        except Exception:
            pass

    return stable


def _replace_root_tokens(text: str, new_root_token: str) -> str:
    """
    Replace any existing root=... in a cmdline-ish string with new_root_token.
    If no root= exists, append it (conservatively).
    """
    if re.search(r"\broot=\S+", text):
        return re.sub(r"\broot=\S+", new_root_token, text)

    # Append into GRUB_CMDLINE_* assignment lines or plain cmdline files.
    if text.strip() and not text.endswith("\n"):
        text += "\n"
    # best-effort: append root= at end of each non-comment line if it's a cmdline file
    if "\n" not in text.strip():
        return text.strip() + " " + new_root_token + "\n"
    return text


def _update_file_cmdline(self, g: guestfs.GuestFS, path: str, new_root_token: str) -> bool:
    old = _read_text(g, path)
    if not old:
        return False
    new = _replace_root_tokens(old, new_root_token)
    if new == old:
        return False
    _log_info(self, f"Updated root= in {path}" + (" (dry-run)" if self.dry_run else ""))
    if not getattr(self, "dry_run", False):
        _write_text(self, g, path, new)
    return True


def _update_bls_root(self, g: guestfs.GuestFS, new_root_token: str) -> int:
    changed = 0
    if not _dir_exists(g, "/boot/loader/entries"):
        return 0
    try:
        for ent in g.ls("/boot/loader/entries"):
            ent_s = U.to_text(ent).strip()
            if not ent_s.endswith(".conf"):
                continue
            p = f"/boot/loader/entries/{ent_s}"
            # BLS uses: options ...
            old = _read_text(g, p)
            if not old:
                continue
            lines = old.splitlines(True)
            out: list[str] = []
            did = False
            for ln in lines:
                if ln.lstrip().startswith("options "):
                    if re.search(r"\broot=\S+", ln):
                        ln2 = re.sub(r"\broot=\S+", new_root_token, ln)
                    else:
                        ln2 = ln.rstrip("\n") + " " + new_root_token + "\n"
                    did = did or (ln2 != ln)
                    out.append(ln2)
                else:
                    out.append(ln)
            new = "".join(out)
            if did and new != old:
                _log_info(self, f"Updated root= in {p}" + (" (dry-run)" if self.dry_run else ""))
                changed += 1
                if not getattr(self, "dry_run", False):
                    _write_text(self, g, p, new)
    except Exception as e:
        _log_warn(self, f"BLS update failed: {e}")
    return changed


def _update_default_grub(self, g: guestfs.GuestFS, new_root_token: str) -> int:
    """
    Update GRUB_CMDLINE_LINUX* in /etc/default/grub (if present).
    """
    p = "/etc/default/grub"
    if not _file_exists(g, p):
        return 0
    old = _read_text(g, p)
    if not old:
        return 0

    def repl(m: re.Match[str]) -> str:
        line = m.group(0)
        # Replace root= inside quotes
        if re.search(r"\broot=\S+", line):
            return re.sub(r"\broot=\S+", new_root_token, line)
        # Otherwise append root= before closing quote if present
        q = '"' if '"' in line else "'"
        if q in line:
            return re.sub(rf"({re.escape(q)}\s*)$", f" {new_root_token}\\1", line)
        return line.rstrip("\n") + " " + new_root_token + "\n"

    new = re.sub(r"(?m)^\s*GRUB_CMDLINE_LINUX(?:_DEFAULT)?=.*$", repl, old)
    if new == old:
        return 0

    _log_info(self, f"Updated root= in {p}" + (" (dry-run)" if self.dry_run else ""))
    if not getattr(self, "dry_run", False):
        _write_text(self, g, p, new)
    return 1


def _update_kernel_cmdline_file(self, g: guestfs.GuestFS, new_root_token: str) -> int:
    # systemd kernel-install uses /etc/kernel/cmdline on some distros
    p = "/etc/kernel/cmdline"
    if _file_exists(g, p) and _update_file_cmdline(self, g, p, new_root_token):
        return 1
    return 0


def _update_grub_cfg_fallback(self, g: guestfs.GuestFS, new_root_token: str) -> int:
    """
    Fallback only: treat grub.cfg as generated output. Still useful when users ship static cfg.
    """
    changed = 0
    for p in ("/boot/grub2/grub.cfg", "/boot/grub/grub.cfg"):
        if _file_exists(g, p) and _update_file_cmdline(self, g, p, new_root_token):
            changed += 1
    return changed


def _update_extlinux_syslinux_fallback(self, g: guestfs.GuestFS, new_root_token: str) -> int:
    changed = 0
    candidates = (
        "/boot/extlinux/extlinux.conf",
        "/extlinux/extlinux.conf",
        "/boot/syslinux/syslinux.cfg",
        "/syslinux/syslinux.cfg",
    )
    for p in candidates:
        if _file_exists(g, p) and _update_file_cmdline(self, g, p, new_root_token):
            changed += 1
    return changed


def update_grub_root(self, g: guestfs.GuestFS) -> int:
    """
    Public API used by OfflineFSFix:
      - respects self.update_grub boolean
      - rewrites root= to stable token in BLS, /etc/kernel/cmdline, /etc/default/grub
      - falls back to grub.cfg and extlinux/syslinux configs
    """
    if not getattr(self, "update_grub", False):
        return 0

    stable = _stable_root_id(self, g)
    if not stable:
        _log_warn(self, "boot: could not find stable ID for root device; skipping root= update.")
        return 0

    new_root_token = f"root={stable}"
    looks_uefi = _guest_looks_uefi(g)
    has_bls = _guest_has_bls(g)
    _log_info(self, f"Boot heuristics: {'UEFI' if looks_uefi else 'BIOS'}; BLS={'yes' if has_bls else 'no'}")
    _log_info(self, f"Setting kernel cmdline {new_root_token}")

    changed = 0
    if has_bls:
        changed += _update_bls_root(self, g, new_root_token)
    changed += _update_kernel_cmdline_file(self, g, new_root_token)
    changed += _update_default_grub(self, g, new_root_token)
    changed += _update_grub_cfg_fallback(self, g, new_root_token)
    changed += _update_extlinux_syslinux_fallback(self, g, new_root_token)
    return changed


# GRUB device.map cleanup

def remove_stale_device_map(self, g: guestfs.GuestFS) -> int:
    """
    Removes stale GRUB device.map files that often break after controller/bus changes.
    """
    removed = 0
    for p in ("/boot/grub2/device.map", "/boot/grub/device.map", "/etc/grub2-device.map"):
        try:
            if _file_exists(g, p):
                txt = _read_text(g, p)
                # any content is suspect; but keep heuristic to avoid nuking custom ones
                if "hd0" in txt or "sda" in txt or "vda" in txt or "nvme" in txt:
                    _log_info(self, f"GRUB: removing stale device.map: {p}" + (" (dry-run)" if self.dry_run else ""))
                    removed += 1
                    if not getattr(self, "dry_run", False):
                        g.rm_f(p)
        except Exception:
            continue
    return removed


# initramfs driver injection (boot-relevant, keep here)

def _get_initramfs_add_drivers(self) -> list[str]:
    """
    Knob sources (highest → lowest):
      1) self.initramfs_add_drivers (list[str] or "a b c")
      2) self.regen_add_drivers (legacy alias)
      3) sane defaults (virtio-ish + common crypto mode)
    """
    val = getattr(self, "initramfs_add_drivers", None) or getattr(self, "regen_add_drivers", None)
    if val:
        if isinstance(val, str):
            drivers = [x for x in val.split() if x.strip()]
        else:
            drivers = [str(x).strip() for x in list(val) if str(x).strip()]
        return _dedup_keep_order(drivers)

    return _dedup_keep_order(
        [
            "virtio",
            "virtio_ring",
            "virtio_blk",
            "virtio_scsi",
            "virtio_net",
            "virtio_pci",
            "nvme",
            "ahci",
            "sd_mod",
            "dm_mod",
            "dm_crypt",
            "xts",
        ]
    )


def _write_modules_linefile(self, g: guestfs.GuestFS, path: str, drivers: list[str]) -> dict[str, Any]:
    drivers = _dedup_keep_order(drivers)
    if not drivers:
        return {"path": path, "changed": False, "reason": "no_drivers"}

    before = _read_text(g, path)
    before_lines = [ln.strip() for ln in before.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    missing = [d for d in drivers if d not in before_lines]
    if not missing:
        return {"path": path, "changed": False, "reason": "already_present"}

    new = before.rstrip() + ("\n" if before and not before.endswith("\n") else "")
    new += "# Added by hyper2kvm (initramfs driver injection)\n"
    for d in missing:
        new += f"{d}\n"

    if getattr(self, "dry_run", False):
        return {"path": path, "changed": True, "dry_run": True, "added": missing}

    _write_text(self, g, path, new)
    return {"path": path, "changed": True, "added": missing}


def _patch_mkinitcpio_modules(self, g: guestfs.GuestFS, drivers: list[str]) -> dict[str, Any]:
    path = "/etc/mkinitcpio.conf"
    drivers = _dedup_keep_order(drivers)
    if not drivers:
        return {"path": path, "changed": False, "reason": "no_drivers"}
    if not _file_exists(g, path):
        return {"path": path, "changed": False, "reason": "missing"}

    old = _read_text(g, path)
    m = re.search(r"(?m)^\s*MODULES=\((.*?)\)\s*$", old)
    if not m:
        insert = "MODULES=(" + " ".join(drivers) + ")\n"
        new = old.rstrip() + "\n\n" + insert
        if getattr(self, "dry_run", False):
            return {"path": path, "changed": True, "dry_run": True, "added": drivers, "note": "MODULES_line_added"}
        _write_text(self, g, path, new)
        return {"path": path, "changed": True, "added": drivers, "note": "MODULES_line_added"}

    inner = m.group(1).strip()
    cur = [x for x in inner.split() if x.strip()]
    merged = _dedup_keep_order(cur + drivers)
    if merged == cur:
        return {"path": path, "changed": False, "reason": "already_present"}

    new_line = "MODULES=(" + " ".join(merged) + ")"
    new = re.sub(r"(?m)^\s*MODULES=\(.*?\)\s*$", new_line, old, count=1)
    if getattr(self, "dry_run", False):
        return {"path": path, "changed": True, "dry_run": True, "added": [d for d in drivers if d not in cur]}

    _write_text(self, g, path, new)
    return {"path": path, "changed": True, "added": [d for d in drivers if d not in cur]}


def _patch_suse_sysconfig_initrd_modules(self, g: guestfs.GuestFS, drivers: list[str]) -> dict[str, Any]:
    path = "/etc/sysconfig/kernel"
    drivers = _dedup_keep_order(drivers)
    if not drivers:
        return {"path": path, "changed": False, "reason": "no_drivers"}
    if not _file_exists(g, path):
        return {"path": path, "changed": False, "reason": "missing"}

    old = _read_text(g, path)
    if re.search(r'(?m)^\s*INITRD_MODULES=', old):

        def _repl(m: re.Match[str]) -> str:
            cur_s = (m.group(1) or "").strip()
            cur = [x for x in cur_s.split() if x.strip()]
            merged = _dedup_keep_order(cur + drivers)
            return f'INITRD_MODULES="{" ".join(merged)}"'

        new = re.sub(r'(?m)^\s*INITRD_MODULES="([^"]*)"\s*$', _repl, old, count=1)
    else:
        new = old.rstrip() + '\nINITRD_MODULES="' + " ".join(drivers) + '"\n'

    if new == old:
        return {"path": path, "changed": False, "reason": "already_present"}

    if getattr(self, "dry_run", False):
        return {"path": path, "changed": True, "dry_run": True, "note": "suse_sysconfig"}

    _write_text(self, g, path, new)
    return {"path": path, "changed": True, "note": "suse_sysconfig"}


def _patch_modules_load_d(self, g: guestfs.GuestFS, drivers: list[str]) -> dict[str, Any]:
    """
    Cross-distro fallback: ensure modules are loaded at boot via modules-load.d.
    This does NOT guarantee availability in early initramfs, but helps for some guests.
    """
    path = "/etc/modules-load.d/hyper2kvm.conf"
    drivers = _dedup_keep_order(drivers)
    if not drivers:
        return {"path": path, "changed": False, "reason": "no_drivers"}

    existing = _read_text(g, path) if _file_exists(g, path) else ""
    existing_lines = {ln.strip() for ln in existing.splitlines() if ln.strip() and not ln.strip().startswith("#")}

    missing = [d for d in drivers if d not in existing_lines]
    if not missing:
        return {"path": path, "changed": False, "reason": "already_present"}

    new = existing.rstrip() + ("\n" if existing and not existing.endswith("\n") else "")
    new += "# Added by hyper2kvm (modules-load.d fallback)\n"
    for d in missing:
        new += f"{d}\n"

    if getattr(self, "dry_run", False):
        return {"path": path, "changed": True, "dry_run": True, "added": missing}

    _write_text(self, g, path, new)
    return {"path": path, "changed": True, "added": missing, "note": "modules_load_d_fallback"}


def _maybe_add_dracut_drivers(cmd: list[str], drivers: list[str]) -> list[str]:
    if not cmd or cmd[0] != "dracut":
        return cmd
    if not drivers:
        return cmd
    # If caller already set add-drivers, don't stomp.
    if "--add-drivers" in cmd:
        return cmd
    return cmd + ["--add-drivers", " ".join(drivers)]


# fstab-based /boot, /boot/efi mounting (critical for correct regen)

@dataclass
class _MountSpec:
    spec: str
    mountpoint: str
    fstype: str
    options: str


def _parse_fstab_mounts(g: guestfs.GuestFS) -> list[_MountSpec]:
    txt = _read_text(g, "/etc/fstab")
    out: list[_MountSpec] = []
    for ln in txt.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        cols = s.split()
        if len(cols) < 4:
            continue
        out.append(_MountSpec(spec=cols[0], mountpoint=cols[1], fstype=cols[2], options=cols[3]))
    return out


def _resolve_spec_to_dev(self, g: guestfs.GuestFS, spec: str) -> str | None:
    """
    Convert fstab spec to a /dev/... node (best-effort):
      - /dev/* direct
      - UUID= / LABEL= via guestfs findfs helpers
      - PARTUUID= via blkid scan (Ident)
      - /dev/disk/by-* via realpath
      - btrfsvol:... unwrap device
    """
    if not spec:
        return None

    if spec.startswith("btrfsvol:"):
        dev, _sv = parse_btrfsvol_spec(spec)
        spec = dev.strip()

    if spec.startswith("/dev/disk/by-"):
        try:
            rp = U.to_text(g.realpath(spec)).strip()
            if rp.startswith("/dev/"):
                return rp
        except Exception:
            return None

    if spec.startswith("/dev/"):
        return spec

    m = re.match(r"^(UUID|LABEL|PARTUUID)=(.+)$", spec)
    if not m:
        return None

    kind = m.group(1)
    val = m.group(2).strip().strip('"').strip("'")

    try:
        if kind == "UUID" and hasattr(g, "findfs_uuid"):
            dev = U.to_text(g.findfs_uuid(val)).strip()
            return dev if dev.startswith("/dev/") else None
        if kind == "LABEL" and hasattr(g, "findfs_label"):
            dev = U.to_text(g.findfs_label(val)).strip()
            return dev if dev.startswith("/dev/") else None
    except Exception:
        pass

    if kind == "PARTUUID":
        # brute-force: scan candidates from list_filesystems + partitions, match PARTUUID
        candidates: list[str] = []
        try:
            candidates.extend([U.to_text(p) for p in (g.list_partitions() or [])])
        except Exception:
            pass
        try:
            fsmap = g.list_filesystems() or {}
            for d in fsmap.keys():
                dd = U.to_text(d)
                if dd.startswith("/dev/"):
                    candidates.append(dd)
        except Exception:
            pass

        for dev in _dedup_keep_order(candidates):
            try:
                blk = Ident.g_blkid_map(g, dev)
                if (blk.get("PARTUUID") or "").strip() == val:
                    return dev
            except Exception:
                continue

    return None


def _mount_boot_partitions_best_effort(self, g: guestfs.GuestFS) -> dict[str, Any]:
    """
    Mount /boot and /boot/efi (or /efi) from fstab if present.
    Returns audit + list of mounted mountpoints to unmount later.
    """
    audit: dict[str, Any] = {"attempted": True, "mounted": [], "errors": []}
    if not _file_exists(g, "/etc/fstab"):
        audit["attempted"] = False
        audit["reason"] = "no_fstab"
        return audit

    want = {"/boot", "/boot/efi", "/efi"}
    entries = [m for m in _parse_fstab_mounts(g) if m.mountpoint in want]

    # Ensure parent dirs exist (some minimal images are weird)
    for mp in sorted({m.mountpoint for m in entries}, key=len):
        try:
            if not _dir_exists(g, mp):
                if not getattr(self, "dry_run", False):
                    g.mkdir_p(mp)
        except Exception:
            pass

    # Mount in dependency order: /boot first, then EFI dirs
    entries_sorted = sorted(entries, key=lambda x: 0 if x.mountpoint == "/boot" else 1)

    for m in entries_sorted:
        dev = _resolve_spec_to_dev(self, g, m.spec)
        if not dev:
            audit["errors"].append({"mountpoint": m.mountpoint, "spec": m.spec, "error": "spec_unresolvable"})
            continue
        try:
            if getattr(self, "dry_run", False):
                # Prefer ro on dry-run
                opts = m.options or "defaults"
                if "ro" not in opts.split(","):
                    opts = "ro," + opts
                g.mount_options(opts, dev, m.mountpoint)
            else:
                # Respect options (best-effort) but avoid "nofail" semantics; irrelevant offline
                opts = m.options or "defaults"
                g.mount_options(opts, dev, m.mountpoint)
            audit["mounted"].append({"mountpoint": m.mountpoint, "dev": dev, "opts": m.options, "fstype": m.fstype})
            _log_info(self, f"Mounted {m.mountpoint} ({dev}) for boot regen")
        except Exception as e:
            audit["errors"].append({"mountpoint": m.mountpoint, "dev": dev, "error": str(e)})

    return audit


def _umount_boot_partitions_best_effort(self, g: guestfs.GuestFS, mounted: list[dict[str, Any]]) -> None:
    # Unmount in reverse: EFI first, then /boot
    mps = [x.get("mountpoint") for x in mounted if x.get("mountpoint")]
    for mp in sorted(mps, key=len, reverse=True):
        try:
            g.umount(mp)
        except Exception:
            pass


# initramfs + bootloader regeneration

def regen(self, g: guestfs.GuestFS) -> dict[str, Any]:
    """
    Linux-only initramfs + bootloader regen.

    Expected knobs on self:
      - regen_initramfs: bool
      - update_grub: bool (root= stabilization)
      - initramfs_add_drivers / regen_add_drivers: list[str] or "a b c"
      - dry_run: bool
    """
    if not getattr(self, "regen_initramfs", False):
        return {"enabled": False}

    # Skip Windows.
    try:
        if getattr(self, "inspect_root", None):
            if (U.to_text(g.inspect_get_type(self.inspect_root)).lower() == "windows"):
                _log_info(self, "regen(): Windows guest detected; skipping Linux regen.")
                return {"enabled": True, "skipped": "windows"}
    except Exception:
        pass

    distro, major = _inspect_distro_major(self, g)
    family = _detect_family(distro)
    looks_uefi = _guest_looks_uefi(g)
    has_bls = _guest_has_bls(g)

    info: dict[str, Any] = {
        "enabled": True,
        "distro": distro,
        "major": major,
        "family": family,
        "guest_boot": "uefi" if looks_uefi else "bios",
        "bls": has_bls,
        "dry_run": bool(getattr(self, "dry_run", False)),
    }

    # root= stabilization (optional)
    try:
        info["root_update_changed"] = update_grub_root(self, g)
    except Exception as e:
        info["root_update_error"] = str(e)

    # device.map cleanup (optional)
    try:
        info["device_map_removed"] = remove_stale_device_map(self, g)
    except Exception as e:
        info["device_map_error"] = str(e)

    add_drivers = _get_initramfs_add_drivers(self)
    info["initramfs_add_drivers"] = add_drivers

    # Mount /boot, /boot/efi for correct output location (critical)
    boot_mount_audit: dict[str, Any] = {"attempted": False}
    mounted_boot: list[dict[str, Any]] = []
    try:
        boot_mount_audit = _mount_boot_partitions_best_effort(self, g)
        mounted_boot = boot_mount_audit.get("mounted", []) or []
    except Exception as e:  
        boot_mount_audit = {"attempted": True, "mounted": [], "errors": [str(e)]}
    info["boot_mounts"] = boot_mount_audit

    # If dry-run: do not run heavy regen tools (but we *can* report what we'd do)
    if getattr(self, "dry_run", False):
        _log_info(self, "DRY-RUN: skipping initramfs/bootloader regeneration commands.")
        if mounted_boot:
            _umount_boot_partitions_best_effort(self, g, mounted_boot)
        return info

    # Driver injection edits (best-effort; these are boot-related config changes)
    inject_audit: dict[str, Any] = {"drivers": add_drivers, "actions": [], "warnings": []}
    try:
        # Debian/Ubuntu initramfs-tools
        if guest_has_cmd(g, "update-initramfs") and _dir_exists(g, "/etc/initramfs-tools"):
            inject_audit["actions"].append(_write_modules_linefile(self, g, "/etc/initramfs-tools/modules", add_drivers))

        # Arch mkinitcpio
        if guest_has_cmd(g, "mkinitcpio") and _file_exists(g, "/etc/mkinitcpio.conf"):
            inject_audit["actions"].append(_patch_mkinitcpio_modules(self, g, add_drivers))

        # SUSE sysconfig kernel
        if _file_exists(g, "/etc/sysconfig/kernel"):
            inject_audit["actions"].append(_patch_suse_sysconfig_initrd_modules(self, g, add_drivers))

        # dracut config drop-in (RHEL/Fedora/Photon/etc.) — deterministic and clean
        if guest_has_cmd(g, "dracut"):
            drop = "/etc/dracut.conf.d/hyper2kvm-drivers.conf"
            line = f'add_drivers+=" {" ".join(add_drivers)} "\n'
            # Only write if not already matching
            old = _read_text(g, drop)
            if line.strip() not in old:
                _write_text(self, g, drop, "# Added by hyper2kvm\n" + line)
                inject_audit["actions"].append({"path": drop, "changed": True, "note": "dracut_dropin"})
            else:
                inject_audit["actions"].append({"path": drop, "changed": False, "note": "dracut_dropin_already_present"})

        # Alpine mkinitfs: config differs per image; warn only
        if guest_has_cmd(g, "mkinitfs"):
            inject_audit["warnings"].append("mkinitfs_detected: no deterministic module-injection implemented (config varies)")

        # Cross-distro fallback (Void/Gentoo/minimal images): try modules-load.d
        inject_audit["actions"].append(_patch_modules_load_d(self, g, add_drivers))
    except Exception as e:
        inject_audit["warnings"].append(f"driver_injection_failed:{e}")

    info["initramfs_driver_injection"] = inject_audit

    # Determine guest kernels
    guest_kvers: list[str] = []
    try:
        if _dir_exists(g, "/lib/modules"):
            guest_kvers = sorted([U.to_text(x) for x in g.ls("/lib/modules") if U.to_text(x).strip()])
    except Exception:
        guest_kvers = []
    info["guest_kernels"] = guest_kvers

    # Initramfs regen attempts (highest success probability first)
    initramfs_attempts: list[list[str]] = []

    if guest_has_cmd(g, "update-initramfs"):
        initramfs_attempts += [["update-initramfs", "-u", "-k", "all"], ["update-initramfs", "-u"]]

    if guest_has_cmd(g, "mkinitcpio"):
        initramfs_attempts += [["mkinitcpio", "-P"]]

    # booster (used by some modern/immutable-ish distros; best-effort)
    if guest_has_cmd(g, "booster"):
        initramfs_attempts += [["booster", "build"]]

    if guest_has_cmd(g, "dracut"):
        # Prefer regenerate-all; it handles multiple kernels cleanly on many distros
        initramfs_attempts += [
            _maybe_add_dracut_drivers(["dracut", "-f", "--regenerate-all"], add_drivers),
        ]
        # Then a specific latest-kernel attempt if we can guess
        if guest_kvers:
            initramfs_attempts.insert(0, _maybe_add_dracut_drivers(["dracut", "-f", "--kver", guest_kvers[-1]], add_drivers))
        initramfs_attempts += [
            _maybe_add_dracut_drivers(["dracut", "-f"], add_drivers),
        ]

    if guest_has_cmd(g, "mkinitrd"):
        initramfs_attempts += [["mkinitrd"]]

    if guest_has_cmd(g, "mkinitfs") and guest_kvers:
        initramfs_attempts += [["mkinitfs", "-b", "/", guest_kvers[-1]]]
        if _file_exists(g, "/etc/mkinitfs/mkinitfs.conf"):
            initramfs_attempts.insert(0, ["mkinitfs", "-c", "/etc/mkinitfs/mkinitfs.conf", "-b", "/", guest_kvers[-1]])

    if guest_has_cmd(g, "genkernel"):
        initramfs_attempts += [["genkernel", "--install", "initramfs"]]

    if guest_has_cmd(g, "kernel-install") and guest_kvers:
        k = guest_kvers[-1]
        for vml in (f"/boot/vmlinuz-{k}", "/boot/vmlinuz", f"/lib/modules/{k}/vmlinuz"):
            if _file_exists(g, vml):
                initramfs_attempts += [["kernel-install", "add", k, vml]]
                break

    # Dedup attempts
    seen = set()
    deduped: list[list[str]] = []
    for c in initramfs_attempts:
        t = tuple(c)
        if t not in seen:
            seen.add(t)
            deduped.append(c)
    initramfs_attempts = deduped

    initramfs_ran: list[dict[str, Any]] = []
    did_initramfs = False
    for cmd in initramfs_attempts:
        ok, out = _run_guestfs_cmd(self, g, cmd)
        initramfs_ran.append({"cmd": cmd, "ok": ok, "out": out[-3000:]})
        if ok:
            did_initramfs = True
            break
    info["initramfs"] = {"attempts": initramfs_ran, "success": did_initramfs}

    # Bootloader regen attempts
    boot_attempts: list[list[str]] = []

    if guest_has_cmd(g, "update-grub"):
        boot_attempts.append(["update-grub"])

    grub_cfg_targets: list[str] = []
    if _dir_exists(g, "/boot/grub2"):
        grub_cfg_targets.append("/boot/grub2/grub.cfg")
    if _dir_exists(g, "/boot/grub"):
        grub_cfg_targets.append("/boot/grub/grub.cfg")

    if guest_has_cmd(g, "grub2-mkconfig"):
        if not grub_cfg_targets:
            grub_cfg_targets = ["/boot/grub2/grub.cfg"]
        for tgt in grub_cfg_targets:
            boot_attempts.append(["grub2-mkconfig", "-o", tgt])

    if guest_has_cmd(g, "grub-mkconfig"):
        if not grub_cfg_targets:
            grub_cfg_targets = ["/boot/grub/grub.cfg"]
        for tgt in grub_cfg_targets:
            boot_attempts.append(["grub-mkconfig", "-o", tgt])

    # Best-effort GRUB reinstall attempts (non-fatal, often fixes "grub prompt" cases)
    # NOTE: offline environment may lack device nodes; we try only when commands exist.
    if guest_has_cmd(g, "grub2-install"):
        # BIOS install (may fail offline; that's OK)
        boot_attempts.append(["grub2-install", "--recheck"])

        # UEFI install attempt (only if ESP likely present)
        if looks_uefi and (_dir_exists(g, "/boot/efi") or _dir_exists(g, "/efi")):
            # Avoid assuming distro path layout; try common EFI directory locations.
            efi_dir = "/boot/efi" if _dir_exists(g, "/boot/efi") else "/efi"
            boot_attempts.append(["grub2-install", "--target=x86_64-efi", f"--efi-directory={efi_dir}", "--recheck"])

    if guest_has_cmd(g, "grub-install"):
        boot_attempts.append(["grub-install", "--recheck"])
        if looks_uefi and (_dir_exists(g, "/boot/efi") or _dir_exists(g, "/efi")):
            efi_dir = "/boot/efi" if _dir_exists(g, "/boot/efi") else "/efi"
            boot_attempts.append(["grub-install", "--target=x86_64-efi", f"--efi-directory={efi_dir}", "--recheck"])

    # systemd-boot: update is safe-ish, but only meaningful if ESP is mounted
    if guest_has_cmd(g, "bootctl"):
        boot_attempts.append(["bootctl", "status"])
        if looks_uefi and (bool(mounted_boot) or _dir_exists(g, "/boot/efi") or _dir_exists(g, "/efi")):
            boot_attempts.append(["bootctl", "update"])

    # Dedup
    seen = set()
    deduped = []
    for c in boot_attempts:
        t = tuple(c)
        if t not in seen:
            seen.add(t)
            deduped.append(c)
    boot_attempts = deduped

    boot_ran: list[dict[str, Any]] = []
    did_boot = False
    for cmd in boot_attempts:
        ok, out = _run_guestfs_cmd(self, g, cmd)
        boot_ran.append({"cmd": cmd, "ok": ok, "out": out[-3000:]})
        if ok:
            did_boot = True
            # If we ran mkconfig, continue to run the next mkconfig target (multi-target)
            if cmd and cmd[0] not in ("grub2-mkconfig", "grub-mkconfig"):
                break

    info["bootloader"] = {"attempts": boot_ran, "success": did_boot}

    # Unmount boot mounts if we mounted them
    try:
        if mounted_boot:
            _umount_boot_partitions_best_effort(self, g, mounted_boot)
    except Exception:
        pass

    # Sanity listing
    sanity: dict[str, Any] = {"boot": {}}
    try:
        if _dir_exists(g, "/boot"):
            sanity["boot"]["boot_ls"] = sorted([U.to_text(x) for x in g.ls("/boot")])[-80:]
    except Exception:
        pass
    if _dir_exists(g, "/boot/loader/entries"):
        try:
            sanity["boot"]["loader_entries"] = sorted([U.to_text(x) for x in g.ls("/boot/loader/entries")])
        except Exception:
            pass
    info["sanity"] = sanity

    return info


# Optional: compatibility wiring (not used in your OfflineFSFix, but kept)

def wire_into(cls: type) -> type:
    """
    Monkey-patch these helpers as instance methods:
      - remove_stale_device_map
      - update_grub_root
      - regen
    """
    cls.remove_stale_device_map = remove_stale_device_map
    cls.update_grub_root = update_grub_root
    cls.regen = regen
    return cls
