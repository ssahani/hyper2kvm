# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/bootloader/post_conversion.py
# -*- coding: utf-8 -*-
"""
Post-conversion boot hardening for Linux guests.

Implements the "3 Golden Fixes" for reliable KVM boot after VM migration:
1. Fstab hardening - Add nofail flags to prevent boot hangs
2. Generic initramfs - Rebuild with all virtio drivers
3. GRUB regeneration - Fix config and rebuild

These fixes prevent the most common post-migration boot failures:
- "Reached target Paths" hang (missing devices in fstab)
- Kernel panic (missing virtio drivers in initramfs)
- GRUB config errors (malformed cmdline)
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...

from ...core.utils import U


class PostConversionBootFixer:
    """
    Post-conversion boot hardening for Linux VMs.

    Automatically applies production-grade fixes to prevent common boot failures
    after VMware → KVM migration.
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self.stats: dict[str, Any] = {
            "attempted": False,
            "fstab_hardened": False,
            "initramfs_rebuilt": False,
            "grub_regenerated": False,
            "errors": [],
        }

    def apply_golden_fixes(
        self,
        g: guestfs.GuestFS,
        *,
        harden_fstab: bool = True,
        rebuild_initramfs: bool = True,
        regenerate_grub: bool = True,
    ) -> dict[str, Any]:
        """
        Apply the 3 golden fixes for reliable KVM boot.

        Args:
            g: GuestFS instance (must be mounted)
            harden_fstab: Add nofail flags to non-root mounts
            rebuild_initramfs: Rebuild generic initramfs with all drivers
            regenerate_grub: Fix and regenerate GRUB config

        Returns:
            Stats dict with results of each fix
        """
        self.stats["attempted"] = True

        # Fix 1: Harden fstab
        if harden_fstab:
            self.logger.info("🔧 Fix 1/3: Hardening fstab with nofail flags")
            self._harden_fstab(g)

        # Fix 2: Rebuild generic initramfs
        if rebuild_initramfs:
            self.logger.info("🔧 Fix 2/3: Rebuilding generic initramfs")
            self._rebuild_initramfs(g)

        # Fix 3: Regenerate GRUB config
        if regenerate_grub:
            self.logger.info("🔧 Fix 3/3: Regenerating GRUB configuration")
            self._regenerate_grub(g)

        return self.stats

    def _harden_fstab(self, g: guestfs.GuestFS) -> None:
        """
        Add nofail and device-timeout flags to non-root mounts in fstab.

        This prevents systemd from blocking boot if non-critical filesystems
        (like /home, /boot) are temporarily unavailable or have UUID mismatches.
        """
        try:
            if not g.is_file("/etc/fstab"):
                self.logger.debug("No /etc/fstab found, skipping")
                return

            fstab_content = g.read_file("/etc/fstab")
            if isinstance(fstab_content, bytes):
                fstab_content = fstab_content.decode('utf-8', errors='replace')

            lines = fstab_content.splitlines()
            modified = False
            new_lines = []

            for line in lines:
                # Skip comments and empty lines
                if line.strip().startswith('#') or not line.strip():
                    new_lines.append(line)
                    continue

                # Parse fstab entry
                parts = line.split()
                if len(parts) < 4:
                    new_lines.append(line)
                    continue

                device, mountpoint, fstype, options = parts[0], parts[1], parts[2], parts[3]

                # Only harden non-root, non-swap filesystems
                if mountpoint in ('/', 'none') or fstype == 'swap':
                    new_lines.append(line)
                    continue

                # Add nofail and timeout if not already present
                if 'nofail' not in options:
                    # Add after existing options
                    if 'x-systemd.device-timeout' not in options:
                        new_options = f"{options},nofail,x-systemd.device-timeout=5s"
                    else:
                        new_options = f"{options},nofail"

                    # Reconstruct line
                    new_line = f"{device}\t{mountpoint}\t{fstype}\t{new_options}"
                    if len(parts) >= 5:
                        new_line += f"\t{parts[4]}"
                    if len(parts) >= 6:
                        new_line += f"\t{parts[5]}"

                    new_lines.append(new_line)
                    modified = True
                    self.logger.info(f"  ✓ Hardened: {mountpoint} ({device})")
                else:
                    new_lines.append(line)

            if modified:
                new_fstab = '\n'.join(new_lines) + '\n'
                g.write("/etc/fstab", new_fstab.encode('utf-8'))
                self.stats["fstab_hardened"] = True
                self.logger.info("  ✓ fstab hardening complete")
            else:
                self.logger.debug("  fstab already hardened or no non-root mounts found")

        except Exception as e:
            error = f"fstab hardening failed: {e}"
            self.logger.warning(f"  ⚠️  {error}")
            self.stats["errors"].append(error)

    def _rebuild_initramfs(self, g: guestfs.GuestFS) -> None:
        """
        Rebuild initramfs without hostonly mode to include all drivers.

        Generic initramfs includes:
        - virtio_blk, virtio_scsi, virtio_net
        - All LVM/dm/md drivers
        - All filesystem drivers

        This prevents kernel panic when disk controller changes from VMware to KVM.
        """
        try:
            # Detect kernel version
            if not g.is_dir("/lib/modules"):
                self.logger.debug("No /lib/modules found, skipping initramfs rebuild")
                return

            kvers = sorted([U.to_text(x) for x in g.ls("/lib/modules") if U.to_text(x).strip()])
            if not kvers:
                self.logger.warning("  ⚠️  No kernel versions found in /lib/modules")
                return

            latest_kver = kvers[-1]
            self.logger.info(f"  Detected kernel: {latest_kver}")

            # Check for dracut (RHEL/CentOS/Fedora)
            has_dracut = False
            try:
                result = g.sh("which dracut 2>/dev/null || echo ''")
                has_dracut = bool(result.strip())
            except Exception:
                pass

            if has_dracut:
                self.logger.info(f"  Rebuilding with: dracut -f --no-hostonly --kver {latest_kver}")
                try:
                    # Use sh instead of command to handle complex shell syntax
                    output = g.sh(f"dracut -f --no-hostonly --kver {latest_kver} 2>&1")
                    self.stats["initramfs_rebuilt"] = True
                    self.logger.info("  ✓ initramfs rebuilt successfully")
                    if output.strip():
                        self.logger.debug(f"  dracut output: {output[:200]}")
                except Exception as e:
                    error = f"dracut execution failed: {e}"
                    self.logger.warning(f"  ⚠️  {error}")
                    self.stats["errors"].append(error)
            else:
                # Check for update-initramfs (Debian/Ubuntu)
                has_update_initramfs = False
                try:
                    result = g.sh("which update-initramfs 2>/dev/null || echo ''")
                    has_update_initramfs = bool(result.strip())
                except Exception:
                    pass

                if has_update_initramfs:
                    self.logger.info(f"  Rebuilding with: update-initramfs -u -k {latest_kver}")
                    try:
                        output = g.sh(f"update-initramfs -u -k {latest_kver} 2>&1")
                        self.stats["initramfs_rebuilt"] = True
                        self.logger.info("  ✓ initramfs rebuilt successfully")
                    except Exception as e:
                        error = f"update-initramfs execution failed: {e}"
                        self.logger.warning(f"  ⚠️  {error}")
                        self.stats["errors"].append(error)
                else:
                    self.logger.debug("  No initramfs tool found (dracut or update-initramfs)")

        except Exception as e:
            error = f"initramfs rebuild failed: {e}"
            self.logger.warning(f"  ⚠️  {error}")
            self.stats["errors"].append(error)

    def _regenerate_grub(self, g: guestfs.GuestFS) -> None:
        """
        Fix GRUB config and regenerate.

        Fixes common issues:
        - Malformed GRUB_CMDLINE_LINUX (missing closing quote)
        - Outdated kernel references
        - Wrong root device
        """
        try:
            # Check for GRUB config file
            grub_default = "/etc/default/grub"
            if not g.is_file(grub_default):
                self.logger.debug("No /etc/default/grub found, skipping")
                return

            # Read and validate GRUB_CMDLINE_LINUX
            content = g.read_file(grub_default)
            if isinstance(content, bytes):
                content = content.decode('utf-8', errors='replace')

            # Fix malformed GRUB_CMDLINE_LINUX (missing closing quote)
            fixed_content = self._fix_grub_cmdline(content)

            if fixed_content != content:
                self.logger.info("  Fixing malformed GRUB_CMDLINE_LINUX")
                g.write(grub_default, fixed_content.encode('utf-8'))

            # Regenerate GRUB config
            grub_cfg = None
            if g.is_file("/boot/grub2/grub.cfg"):
                grub_cfg = "/boot/grub2/grub.cfg"
                grub_cmd = f"grub2-mkconfig -o {grub_cfg}"
            elif g.is_file("/boot/grub/grub.cfg"):
                grub_cfg = "/boot/grub/grub.cfg"
                grub_cmd = f"grub-mkconfig -o {grub_cfg}"
            else:
                self.logger.debug("  No GRUB config file found")
                return

            self.logger.info(f"  Regenerating: {grub_cmd}")
            try:
                output = g.sh(f"{grub_cmd} 2>&1")
                self.stats["grub_regenerated"] = True
                self.logger.info("  ✓ GRUB config regenerated successfully")
                if "error" in output.lower():
                    self.logger.debug(f"  GRUB output: {output[:200]}")
            except Exception as e:
                error = f"GRUB regeneration failed: {e}"
                self.logger.warning(f"  ⚠️  {error}")
                self.stats["errors"].append(error)

        except Exception as e:
            error = f"GRUB regeneration failed: {e}"
            self.logger.warning(f"  ⚠️  {error}")
            self.stats["errors"].append(error)

    def _fix_grub_cmdline(self, content: str) -> str:
        """
        Fix malformed GRUB_CMDLINE_LINUX entries.

        Common issue: Missing closing quote causes shell syntax error.
        Example:
            GRUB_CMDLINE_LINUX="... root=UUID=xxx
            GRUB_DISABLE_RECOVERY="true"

        Fix: Add closing quote before newline.
        """
        lines = content.splitlines()
        fixed_lines = []

        for i, line in enumerate(lines):
            # Check for GRUB_CMDLINE_LINUX without closing quote
            if line.startswith('GRUB_CMDLINE_LINUX='):
                # Count quotes
                quote_count = line.count('"')

                # If odd number of quotes, line is malformed
                if quote_count % 2 == 1:
                    # Add closing quote at end
                    line = line.rstrip() + '"'
                    self.logger.debug(f"  Fixed line {i+1}: added closing quote")

            fixed_lines.append(line)

        return '\n'.join(fixed_lines) + '\n'
