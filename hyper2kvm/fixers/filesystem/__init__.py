# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/filesystem/__init__.py
"""
Filesystem fixing modules for VMware -> KVM migration.

This package provides filesystem-related fixes:
- fixer: Filesystem detection and fixing
- fstab: fstab and crypttab rewriting (legacy)
- universal_rewriter: Production-grade rewriter (NEW)
"""

from .universal_rewriter import (
    DevInfo,
    build_inventory,
    find_by_spec,
    rewrite_crypttab,
    rewrite_fstab,
    stable_spec,
)

__all__ = [
    "DevInfo",
    "build_inventory",
    "find_by_spec",
    "rewrite_crypttab",
    "rewrite_fstab",
    "stable_spec",
    "stabilize_guest_fstab",
]


def stabilize_guest_fstab(g, *, detect_btrfs: bool = True, fstab_path: str = "/etc/fstab"):
    """
    One-shot helper: stabilize fstab using universal rewriter.

    Usage in offline_fixer.py:
    ```python
    from ..filesystem import stabilize_guest_fstab

    result = stabilize_guest_fstab(g)
    print(f"Converted: {result['fstab_stats']['converted']} entries")
    ```

    Args:
        g: GuestFS instance (must be launched and root mounted)
        detect_btrfs: Auto-detect Btrfs subvolume layout
        fstab_path: Path to fstab in guest

    Returns:
        Result dict with stats
    """
    import logging

    logger = logging.getLogger(__name__)

    result = {
        "success": False,
        "inventory_size": 0,
        "fstab_stats": {},
        "crypttab_stats": {},
        "btrfs_subvols": {},
        "errors": [],
    }

    try:
        # 1. Build device inventory
        devices = []

        # Get partitions
        try:
            devices.extend(g.list_partitions() or [])
        except Exception as e:
            logger.warning(f"Failed to list partitions: {e}")

        # Get logical volumes
        try:
            if hasattr(g, "lvs"):
                devices.extend(g.lvs() or [])
        except Exception as e:
            logger.warning(f"Failed to list LVs: {e}")

        # Get filesystem map devices (includes /dev/mapper/*)
        try:
            fsmap = g.list_filesystems() or {}
            for dev in fsmap.keys():
                if dev not in devices:
                    devices.append(dev)
        except Exception as e:
            logger.warning(f"Failed to list filesystems: {e}")

        logger.info(f"Building inventory for {len(devices)} devices...")
        inv = build_inventory(g, devices)
        result["inventory_size"] = len(inv)

        # 2. Detect Btrfs subvolumes if requested
        btrfs_map = {}
        if detect_btrfs:
            try:
                # Simple heuristic: if root is btrfs, check for common subvolumes
                if g.is_dir("/") and g.exists("/etc/fstab"):
                    # Read current fstab to see if subvolumes are in use
                    fstab_content = g.read_file(fstab_path)
                    if isinstance(fstab_content, bytes):
                        fstab_content = fstab_content.decode("utf-8", errors="replace")

                    # Look for subvol= options in current fstab
                    import re
                    for line in fstab_content.splitlines():
                        if "subvol=" in line and not line.strip().startswith("#"):
                            parts = line.split()
                            if len(parts) >= 4:
                                mp = parts[1]
                                opts = parts[3]
                                # Extract subvol value
                                match = re.search(r"subvol=([^,\s]+)", opts)
                                if match:
                                    subvol = match.group(1)
                                    btrfs_map[mp] = subvol
                                    logger.info(f"Detected Btrfs subvol: {mp} → {subvol}")

                result["btrfs_subvols"] = btrfs_map
            except Exception as e:
                logger.warning(f"Btrfs subvolume detection failed: {e}")

        # 3. Rewrite fstab
        fstab_stats = rewrite_fstab(g, fstab_path, inv, btrfs_subvol_map=btrfs_map)
        result["fstab_stats"] = fstab_stats

        # 4. Rewrite crypttab if it exists
        crypttab_path = "/etc/crypttab"
        if g.is_file(crypttab_path):
            crypttab_stats = rewrite_crypttab(g, crypttab_path, inv)
            result["crypttab_stats"] = crypttab_stats

        result["success"] = True
        return result

    except Exception as e:
        result["errors"].append(str(e))
        logger.error(f"Filesystem stabilization failed: {e}")
        return result
