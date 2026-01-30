# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/offline/config_rewriter.py
# -*- coding: utf-8 -*-
"""
In-guest configuration file rewriting (fstab, crypttab).

This module handles rewriting /etc/fstab and /etc/crypttab to use stable
device identifiers (UUID, PARTUUID, LABEL) instead of potentially unstable
names like /dev/sda1 or by-path references.

Extracted from offline_fixer.py to provide single-responsibility module
for configuration rewriting logic.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...

from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from ...core.utils import U
from ..filesystem.fstab import (
    _BYPATH_PREFIX,
    IGNORE_MOUNTPOINTS,
    Change,
    FstabMode,
    Ident,
)
from .spec_converter import SpecConverter


class FstabCrypttabRewriter:
    """
    Rewriter for /etc/fstab and /etc/crypttab files.

    Stabilizes device identifiers in configuration files to prevent boot failures
    when moving VMs between different hypervisors or hardware.
    """

    def __init__(
        self,
        logger: logging.Logger,
        spec_converter: SpecConverter,
        *,
        dry_run: bool = False,
        no_backup: bool = False,
        print_fstab: bool = False,
        fstab_mode: FstabMode = FstabMode.BYPATH_ONLY,
    ):
        """
        Initialize config rewriter.

        Args:
            logger: Logger instance
            spec_converter: SpecConverter instance for device ID conversion
            dry_run: If True, don't make actual changes
            no_backup: If True, skip backup creation
            print_fstab: If True, print fstab before/after to stdout
            fstab_mode: Conversion policy (NOOP, BYPATH_ONLY, STABILIZE_ALL)
        """
        self.logger = logger
        self.spec_converter = spec_converter
        self.dry_run = dry_run
        self.no_backup = no_backup
        self.print_fstab = print_fstab
        self.fstab_mode = fstab_mode

    def backup_file(self, g: guestfs.GuestFS, path: str) -> None:
        """
        Create timestamped backup of a file in the guest.

        Args:
            g: GuestFS handle
            path: Path to file in guest
        """
        if self.no_backup or self.dry_run:
            return

        try:
            if not g.is_file(path):
                return
        except Exception:
            return

        backup_path = f"{path}.backup.hyper2kvm.{U.now_ts()}"
        try:
            g.cp(path, backup_path)
            self.logger.debug(f"Backup: {path} -> {backup_path}")
        except Exception as e:
            self.logger.warning(f"Backup failed for {path}: {e}")

    def rewrite_fstab(self, g: guestfs.GuestFS) -> tuple[int, list[Change], dict[str, Any]]:
        """
        Rewrite /etc/fstab with stable device identifiers.

        Args:
            g: GuestFS handle with root filesystem mounted

        Returns:
            Tuple of (num_changes, change_list, audit_info) where:
            - num_changes: Number of lines changed
            - change_list: List of Change objects describing each change
            - audit_info: Dict with statistics (total_lines, entries, etc.)
        """
        fstab = "/etc/fstab"

        if self.fstab_mode == FstabMode.NOOP:
            self.logger.info("fstab: mode=noop (skipping)")
            return 0, [], {"reason": "noop"}

        try:
            if not g.is_file(fstab):
                self.logger.warning("fstab: /etc/fstab not found; skipping")
                return 0, [], {"reason": "missing"}
        except Exception:
            self.logger.warning("fstab: /etc/fstab check failed; skipping")
            return 0, [], {"reason": "missing"}

        before = U.to_text(g.read_file(fstab))

        # Always log original fstab
        self.logger.info(f"\n📄 Original /etc/fstab:")
        for line_num, line in enumerate(before.splitlines(), 1):
            self.logger.info(f"  {line_num:3d}: {line}")

        if self.print_fstab:
            print("\n--- /etc/fstab (before) ---\n" + before)

        lines = before.splitlines()
        out_lines: list[str] = []
        changes: list[Change] = []
        total = 0
        entries = 0
        bypath = 0

        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Processing fstab lines", total=len(lines))

            for idx, line in enumerate(lines, 1):
                total += 1
                s = line.strip()

                # Skip comments and empty lines
                if not s or s.startswith("#"):
                    out_lines.append(line)
                    progress.update(task, advance=1)
                    continue

                # Parse fstab entry
                cols = s.split()
                if len(cols) < 4:
                    out_lines.append(line)
                    progress.update(task, advance=1)
                    continue

                spec, mp = cols[0], cols[1]

                # Skip ignored mountpoints
                if mp in IGNORE_MOUNTPOINTS:
                    out_lines.append(line)
                    progress.update(task, advance=1)
                    continue

                entries += 1
                if spec.startswith(_BYPATH_PREFIX):
                    bypath += 1

                # BYPATH_ONLY: only convert by-path entries
                if self.fstab_mode == FstabMode.BYPATH_ONLY and not (
                    spec.startswith(_BYPATH_PREFIX) or spec.startswith("btrfsvol:")
                ):
                    out_lines.append(line)
                    progress.update(task, advance=1)
                    continue

                # Convert spec if needed
                new_spec, reason = self.spec_converter.convert_spec(g, spec)
                if new_spec != spec:
                    cols[0] = new_spec
                    out_lines.append("\t".join(cols))
                    changes.append(Change(idx, mp, spec, new_spec, reason))
                else:
                    out_lines.append(line)

                progress.update(task, advance=1)

        audit = {
            "total_lines": total,
            "entries": entries,
            "bypath_entries": bypath,
            "changed_entries": len(changes),
        }

        self.logger.info(
            f"fstab scan: total_lines={total} entries={entries} "
            f"bypath_entries={bypath} changed_entries={len(changes)}"
        )

        # /tmp sanity check (common for some minimal images)
        self._ensure_tmp_sanity(g)

        if not changes:
            if self.print_fstab:
                print("\n--- /etc/fstab (after - unchanged) ---\n" + before)
            return 0, [], audit

        # Log changes summary
        self.logger.info(f"\n📝 Fstab conversions summary:")
        for ch in changes:
            self.logger.info(f"  Line {ch.line_no:3d}: {ch.old:50s} -> {ch.new:50s} ({ch.mountpoint}) [{ch.reason}]")

        after = "\n".join(out_lines) + "\n"

        # Always log updated fstab
        self.logger.info(f"\n📄 Updated /etc/fstab:")
        for line_num, line in enumerate(out_lines, 1):
            self.logger.info(f"  {line_num:3d}: {line}")

        if self.print_fstab:
            print("\n--- /etc/fstab (after) ---\n" + after)

        if self.dry_run:
            self.logger.info(f"fstab: DRY-RUN: would apply {len(changes)} change(s).")
            return len(changes), changes, audit

        # Apply changes
        self.backup_file(g, fstab)
        g.write(fstab, after.encode("utf-8"))
        self.logger.info(f"/etc/fstab updated ({len(changes)} changes).")

        return len(changes), changes, audit

    def _ensure_tmp_sanity(self, g: guestfs.GuestFS) -> None:
        """
        Ensure /tmp directory exists and has correct permissions.

        Args:
            g: GuestFS handle
        """
        try:
            if not g.is_dir("/tmp"):
                self.logger.info("Fixing /tmp: creating directory inside guest")
                if not self.dry_run:
                    g.mkdir_p("/tmp")
                    try:
                        g.chmod(0o1777, "/tmp")
                    except Exception:
                        pass
        except Exception as e:
            self.logger.warning(f"/tmp sanity fix failed: {e}")

    def rewrite_crypttab(self, g: guestfs.GuestFS) -> int:
        """
        Rewrite /etc/crypttab with stable device identifiers.

        Args:
            g: GuestFS handle with root filesystem mounted

        Returns:
            Number of lines changed
        """
        path = "/etc/crypttab"

        try:
            if not g.is_file(path):
                return 0
        except Exception:
            return 0

        before = U.to_text(g.read_file(path))
        out: list[str] = []
        changed = 0
        lines = before.splitlines()

        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Processing crypttab lines", total=len(lines))

            for line in lines:
                s = line.strip()

                # Skip comments and empty lines
                if not s or s.startswith("#"):
                    out.append(line)
                    progress.update(task, advance=1)
                    continue

                # Parse crypttab entry
                cols = s.split()
                if len(cols) < 2:
                    out.append(line)
                    progress.update(task, advance=1)
                    continue

                name, spec = cols[0], cols[1]

                # Skip if already stable
                if Ident.is_stable(spec):
                    out.append(line)
                    progress.update(task, advance=1)
                    continue

                # BYPATH_ONLY: only convert by-path entries
                if self.fstab_mode == FstabMode.BYPATH_ONLY and not (
                    spec.startswith(_BYPATH_PREFIX) or spec.startswith("btrfsvol:")
                ):
                    out.append(line)
                    progress.update(task, advance=1)
                    continue

                # Convert spec if needed
                new_spec, reason = self.spec_converter.convert_spec(g, spec)
                if new_spec != spec:
                    cols[1] = new_spec
                    out.append(" ".join(cols))
                    changed += 1
                    self.logger.info(f"crypttab: {name}: {spec} -> {new_spec} [{reason}]")
                else:
                    out.append(line)

                progress.update(task, advance=1)

        if changed == 0:
            return 0

        after = "\n".join(out) + "\n"

        if self.dry_run:
            self.logger.info(f"crypttab: DRY-RUN: would apply {changed} change(s).")
            return changed

        # Apply changes
        self.backup_file(g, path)
        g.write(path, after.encode("utf-8"))
        self.logger.info(f"/etc/crypttab updated ({changed} changes).")

        return changed


__all__ = ["FstabCrypttabRewriter"]
