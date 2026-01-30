# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/offline/spec_converter.py
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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...

from ...core.utils import U
from ..filesystem.fstab import (
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
        root_dev: str | None = None,
    ):
        """
        Initialize spec converter.

        Args:
            fstab_mode: Conversion policy (NOOP, BYPATH_ONLY, STABILIZE_ALL)
            root_dev: Optional root device for by-path inference
        """
        self.fstab_mode = fstab_mode
        self.root_dev = root_dev

    def convert_spec(self, g: guestfs.GuestFS, spec: str) -> tuple[str, str]:
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
        import logging
        logger = logging.getLogger("hyper2kvm.spec_converter")
        logger.info(f"🎯 convert_spec: spec={spec!r}, fstab_mode={self.fstab_mode!r}")

        original = spec

        # btrfsvol:/dev/XXX//@/path -> treat stable mapping for underlying dev
        if spec.startswith("btrfsvol:"):
            dev, _sv = parse_btrfsvol_spec(spec)
            spec = dev.strip()
            logger.info(f"  Parsed btrfsvol: {original} -> dev={dev}")

        # Already stable (UUID=, LABEL=, PARTUUID=, etc.)
        if Ident.is_stable(spec):
            logger.info(f"  Already stable: {spec}")
            return original, "already-stable"

        # by-path -> real dev -> stable
        if spec.startswith(_BYPATH_PREFIX):
            logger.info(f"  Detected by-path device, calling _stabilize_bypath")
            return self._stabilize_bypath(g, spec, original)

        # STABILIZE_ALL: rewrite any /dev/* to stable
        if self.fstab_mode == FstabMode.STABILIZE_ALL and spec.startswith("/dev/"):
            logger.info(f"  STABILIZE_ALL mode, calling _stabilize_dev for {spec}")
            return self._stabilize_dev(g, spec, original)

        logger.info(f"  Unchanged: {spec}")
        return original, "unchanged"

    def _stabilize_bypath(
        self,
        g: guestfs.GuestFS,
        spec: str,
        original: str,
    ) -> tuple[str, str]:
        """
        Stabilize by-path reference to stable ID.

        Args:
            g: GuestFS handle
            spec: by-path spec (e.g., /dev/disk/by-path/pci-0000:00:10.0-scsi-0:0:0:0-part1)
            original: Original spec before any processing

        Returns:
            Tuple of (converted_spec, reason)
        """
        import logging
        logger = logging.getLogger("hyper2kvm.spec_converter")
        logger.info(f"🔧 _stabilize_bypath: spec={spec!r}, root_dev={self.root_dev!r}")

        mapped: str | None = None

        # CRITICAL FIX: For VMCraft backend, by-path devices are on the HOST, not in guest filesystem
        # Use host-level symlink resolution first, fall back to guestfs realpath
        try:
            import os
            if os.path.exists(spec) and os.path.islink(spec):
                # Resolve symlink on host system
                real_dev = os.readlink(spec)
                # Handle relative symlinks
                if not real_dev.startswith("/"):
                    real_dev = os.path.normpath(os.path.join(os.path.dirname(spec), real_dev))
                if real_dev.startswith("/dev/"):
                    mapped = real_dev
                    logger.info(f"  ✓ Resolved via host symlink: {spec} -> {mapped}")
        except Exception as e:
            logger.debug(f"  Host symlink resolution failed: {e}")

        # Try guestfs realpath if host resolution didn't work
        if not mapped:
            try:
                rp = U.to_text(g.realpath(spec)).strip()
                # Only accept realpath result if it actually resolved to a DIFFERENT device
                if rp.startswith("/dev/") and rp != spec:
                    mapped = rp
                    logger.info(f"  ✓ Resolved via guestfs realpath: {spec} -> {mapped}")
                elif rp == spec:
                    logger.debug(f"  Guestfs realpath returned same path (no resolution): {spec}")
            except Exception as e:
                logger.debug(f"  Guestfs realpath failed: {e}")

        # If still not mapped, try inference helper (root_dev optional)
        if not mapped:
            mapped = (
                Ident.infer_partition_from_bypath(spec, self.root_dev)
                if self.root_dev
                else None
            )
            if mapped:
                logger.info(f"  ✓ Inferred from by-path: {spec} -> {mapped} (root_dev={self.root_dev})")
            elif self.root_dev:
                logger.warning(f"  ✗ Inference failed despite root_dev={self.root_dev}")
            else:
                logger.warning(f"  ✗ Inference skipped: root_dev is None")

        if not mapped:
            logger.error(f"  ✗ FAILED to map by-path device: {spec}")
            return original, "by-path-unresolved"

        # Get blkid info and choose stable ID
        logger.info(f"  🔍 Running blkid on mapped device: {mapped}")
        blk = Ident.g_blkid_map(g, mapped)
        logger.info(f"  📋 Blkid result: {blk}")
        stable = Ident.choose_stable(blk)
        if stable:
            logger.info(f"  ✅ Converted: {spec} -> {stable}")
            return stable, f"mapped:{mapped}"

        logger.warning(f"  ⚠️ No stable ID found for {mapped}")
        return original, f"mapped:{mapped} no-id"

    def _stabilize_dev(
        self,
        g: guestfs.GuestFS,
        spec: str,
        original: str,
    ) -> tuple[str, str]:
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
