# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/filesystem/fstab.py
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...

_BYPATH_PREFIX = "/dev/disk/by-path/"
RE_BTRFSVOL = re.compile(r"^btrfsvol:(.+?)(?://@/|//@/|//)?(.*)$")
IGNORE_MOUNTPOINTS = {"/proc", "/sys", "/dev", "/run", "/dev/pts", "/dev/shm", "/sys/fs/cgroup"}

_LOG = logging.getLogger("hyper2kvm.fstab")


def parse_btrfsvol_spec(spec: str) -> tuple[str, str | None]:
    """
    Parse libguestfs inspection btrfsvol: hints.
    Examples:
      btrfsvol:/dev/sda2//@
      btrfsvol:/dev/sda2//@/var
      btrfsvol:/dev/sda2//@/.snapshots/1/snapshot
    Return (device, subvol) where subvol is something like "@", "@/var", "@/.snapshots/..."
    """
    _LOG.debug("🧩 parse_btrfsvol_spec: input=%r", spec)

    if not spec.startswith("btrfsvol:"):
        _LOG.debug("⏭️ not a btrfsvol spec")
        return spec, None

    s = spec[len("btrfsvol:"):]
    if "//" not in s:
        dev = s.strip()
        _LOG.debug("📦 btrfsvol: device-only => dev=%r", dev)
        return dev, None

    dev, rest = s.split("//", 1)
    dev = dev.strip()
    rest = rest.strip().lstrip("/")

    if not rest:
        _LOG.debug("📦 btrfsvol: empty subvol => dev=%r", dev)
        return dev, None

    # normalize: libguestfs frequently encodes root subvol as "@"
    if not rest.startswith("@"):
        # If it’s not @-style, still allow (btrfs allows arbitrary subvol names)
        _LOG.debug("🌿 btrfsvol: non-@ subvol => dev=%r subvol=%r", dev, rest)
        return dev, rest

    _LOG.debug("🌿 btrfsvol: parsed => dev=%r subvol=%r", dev, rest)
    return dev, rest


class Ident:
    @staticmethod
    def is_stable(spec: str) -> bool:
        u = spec.upper()
        stable = u.startswith(("UUID=", "PARTUUID=", "LABEL=", "PARTLABEL="))
        _LOG.debug("🧷 is_stable: spec=%r => %s", spec, stable)
        return stable

    @staticmethod
    def g_blkid_map(g: guestfs.GuestFS, dev: str) -> dict[str, str]:
        _LOG.debug("🔎 blkid: probing dev=%r", dev)
        try:
            d = g.blkid(dev)
            out = {str(k).upper(): str(v) for k, v in d.items() if v is not None}
            _LOG.debug("🧾 blkid: dev=%r => keys=%s", dev, sorted(out.keys()))
            return out
        except Exception as e:
            # keep behavior: return {}
            _LOG.debug("⚠️ blkid failed: dev=%r err=%s", dev, e, exc_info=True)
            return {}

    @staticmethod
    def choose_stable(blk: dict[str, str]) -> str | None:
        # Order is intentional: preserve existing preference behavior.
        if blk.get("UUID"):
            chosen = f"UUID={blk['UUID']}"
            _LOG.debug("🎯 choose_stable: picked %s", chosen)
            return chosen
        if blk.get("PARTUUID"):
            chosen = f"PARTUUID={blk['PARTUUID']}"
            _LOG.debug("🎯 choose_stable: picked %s", chosen)
            return chosen
        if blk.get("LABEL"):
            chosen = f"LABEL={blk['LABEL']}"
            _LOG.debug("🎯 choose_stable: picked %s", chosen)
            return chosen
        if blk.get("PARTLABEL"):
            chosen = f"PARTLABEL={blk['PARTLABEL']}"
            _LOG.debug("🎯 choose_stable: picked %s", chosen)
            return chosen
        _LOG.debug("🫥 choose_stable: no stable identifier in blkid map")
        return None

    @staticmethod
    def root_dev_base(root_dev: str | None) -> str | None:
        _LOG.debug("🧱 root_dev_base: input=%r", root_dev)
        if not root_dev:
            return None

        # Match devices with 'p' separator: nvme0n1p1, mmcblk0p1, nbd0p1, loop0p1
        m = re.match(r"^(/dev/(?:nvme\d+n\d+|mmcblk\d+|nbd\d+|loop\d+))p\d+$", root_dev)
        if m:
            base = m.group(1)
            _LOG.debug("🧠 root_dev_base: nvme/mmc/nbd/loop => %r", base)
            return base

        # Match traditional devices: sda1, vda1, xvda1, hda1
        m = re.match(r"^(/dev/[a-zA-Z]+)\d+$", root_dev)
        if m:
            base = m.group(1)
            _LOG.debug("🧠 root_dev_base: sdX/vdX => %r", base)
            return base

        _LOG.debug("🫥 root_dev_base: could not infer base for %r", root_dev)
        return None

    @staticmethod
    def infer_partition_from_bypath(spec: str, root_dev: str | None) -> str | None:
        _LOG.debug("🧭 infer_partition_from_bypath: spec=%r root_dev=%r", spec, root_dev)

        if not root_dev or not spec.startswith(_BYPATH_PREFIX):
            _LOG.debug("⏭️ bypath inference skipped (no root_dev or not by-path)")
            return None

        m = re.search(r"-part(\d+)$", spec)
        if not m:
            _LOG.debug("🫥 bypath inference: no -partN suffix in %r", spec)
            return None

        partno = int(m.group(1))
        base = Ident.root_dev_base(root_dev)
        if not base:
            _LOG.debug("🫥 bypath inference: could not derive base from root_dev=%r", root_dev)
            return None

        # Devices that use 'p' separator: nvme, mmcblk, nbd, loop
        if re.match(r"^/dev/(nvme\d+n\d+|mmcblk\d+|nbd\d+|loop\d+)$", base):
            out = f"{base}p{partno}"
            _LOG.debug("🧩 bypath inference: %r + part%d => %r (with p separator)", base, partno, out)
            return out

        # Traditional devices: sda, vda, xvda, hda
        out = f"{base}{partno}"
        _LOG.debug("🧩 bypath inference: %r + part%d => %r (direct concat)", base, partno, out)
        return out


class FstabMode(str, Enum):
    STABILIZE_ALL = "stabilize-all"
    BYPATH_ONLY = "bypath-only"
    NOOP = "noop"


@dataclass
class Change:
    line_no: int
    mountpoint: str
    old: str
    new: str
    reason: str

    def __post_init__(self) -> None:
        # Additive visibility only; no behavior change.
        _LOG.debug(
            "📝 fstab change: line=%d mp=%r old=%r new=%r reason=%r",
            self.line_no,
            self.mountpoint,
            self.old,
            self.new,
            self.reason,
        )
