# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/offline_spec_converter.py
# -*- coding: utf-8 -*-
"""
Device identifier and fstab/crypttab spec conversion utilities.

This module provides device identifier stabilization logic for converting
potentially unstable device paths (like /dev/sda1 or by-path references)
to stable identifiers (UUID, PARTUUID, LABEL).

Extracted from offline_fixer.py to provide single-responsibility module
for spec conversion logic.
"""
from __future__ import annotations

from typing import Optional, Tuple

import guestfs  # type: ignore

from ..core.utils import U
from .fstab_rewriter import (
    _BYPATH_PREFIX,
    FstabMode,
    Ident,
    parse_btrfsvol_spec,
)


class SpecConverter:
    """
    Device spec converter for stabilizing device identifiers.

    Converts unstable device references to stable identifiers based on:
    - FstabMode policy (NOOP, BYPATH_ONLY, STABILIZE_ALL)
    - Device type (btrfsvol, by-path, /dev/*)
    - Available blkid metadata
    """

    def __init__(
        self,
        fstab_mode: FstabMode,
        root_dev: Optional[str] = None,
    ):
        """
        Initialize spec converter.

        Args:
            fstab_mode: Conversion policy (NOOP, BYPATH_ONLY, STABILIZE_ALL)
            root_dev: Optional root device for by-path inference
        """
        self.fstab_mode = fstab_mode
        self.root_dev = root_dev

    def convert_spec(self, g: guestfs.GuestFS, spec: str) -> Tuple[str, str]:
        """
        Convert a device spec to stable identifier if needed.

        Args:
            g: GuestFS handle with system mounted
            spec: Original device spec (e.g., /dev/sda1, UUID=..., by-path/...)

        Returns:
            Tuple of (converted_spec, reason) where reason describes what happened:
            - "already-stable": spec is already stable (UUID, LABEL, etc.)
            - "by-path-unresolved": by-path couldn't be resolved
            - "mapped:<dev>": by-path was mapped to device
            - "mapped:<dev> no-id": mapped but no stable ID found
            - "blkid:<dev>": converted via blkid
            - "dev-no-id": /dev/* but no stable ID found
            - "unchanged": no conversion needed or possible
        """
        original = spec

        # btrfsvol:/dev/XXX//@/path -> treat stable mapping for underlying dev
        if spec.startswith("btrfsvol:"):
            dev, _sv = parse_btrfsvol_spec(spec)
            spec = dev.strip()

        # Already stable (UUID=, LABEL=, PARTUUID=, etc.)
        if Ident.is_stable(spec):
            return original, "already-stable"

        # by-path -> real dev -> stable
        if spec.startswith(_BYPATH_PREFIX):
            return self._stabilize_bypath(g, spec, original)

        # STABILIZE_ALL: rewrite any /dev/* to stable
        if self.fstab_mode == FstabMode.STABILIZE_ALL and spec.startswith("/dev/"):
            return self._stabilize_dev(g, spec, original)

        return original, "unchanged"

    def _stabilize_bypath(
        self,
        g: guestfs.GuestFS,
        spec: str,
        original: str,
    ) -> Tuple[str, str]:
        """
        Stabilize by-path reference to stable ID.

        Args:
            g: GuestFS handle
            spec: by-path spec (e.g., /dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part1)
            original: Original spec before any processing

        Returns:
            Tuple of (converted_spec, reason)
        """
        mapped: Optional[str] = None

        # Try realpath first
        try:
            rp = U.to_text(g.realpath(spec)).strip()
            if rp.startswith("/dev/"):
                mapped = rp
        except Exception:
            mapped = None

        # If still not mapped, try inference helper (root_dev optional)
        if not mapped:
            mapped = (
                Ident.infer_partition_from_bypath(spec, self.root_dev)
                if self.root_dev
                else None
            )

        if not mapped:
            return original, "by-path-unresolved"

        # Get blkid info and choose stable ID
        blk = Ident.g_blkid_map(g, mapped)
        stable = Ident.choose_stable(blk)
        if stable:
            return stable, f"mapped:{mapped}"

        return original, f"mapped:{mapped} no-id"

    def _stabilize_dev(
        self,
        g: guestfs.GuestFS,
        spec: str,
        original: str,
    ) -> Tuple[str, str]:
        """
        Stabilize /dev/* reference to stable ID.

        Args:
            g: GuestFS handle
            spec: /dev/* spec (e.g., /dev/sda1)
            original: Original spec before any processing

        Returns:
            Tuple of (converted_spec, reason)
        """
        blk = Ident.g_blkid_map(g, spec)
        stable = Ident.choose_stable(blk)
        if stable:
            return stable, f"blkid:{spec}"

        return original, "dev-no-id"


__all__ = ["SpecConverter"]
