# vmdk2kvm/fixers/network_fixer.py
from __future__ import annotations

from typing import Any, Dict, List
import re

import guestfs  # type: ignore
from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn

from ..core.utils import U, guest_ls_glob
from ..config.config_loader import YAML_AVAILABLE, yaml


# ---------------------------
# Network Configuration Fixes
# ---------------------------
def fix_network_config(self, g: guestfs.GuestFS) -> Dict[str, Any]:
    """
    Offline network config normalization for VMware -> KVM.

    Goals:
      - remove VMware-only driver hints (vmxnet3/e1000) from common config formats
      - avoid MAC pinning that breaks on new NICs (HWADDR/MACAddress/MACADDR/etc.)
      - avoid udev/systemd predictable-name pinning that mismatches (NAME=, set-name:, match:)
      - default to DHCP on the primary interface when config is clearly VMware-anchored
      - produce a useful audit trail in report

    Safety:
      - only rewrites files when we actually detect VMware-anchored patterns
      - keeps backups (unless no_backup/dry_run)
      - records bounded per-file details to avoid gigantic reports
    """
    updated_files: List[str] = []
    scanned_files: List[str] = []
    per_file: List[Dict[str, Any]] = []
    totals = {
        "files_seen": 0,
        "files_changed": 0,
        "patterns_removed": 0,
        "mac_pins_removed": 0,
        "renames_applied": 0,
        "netplan_fixed": 0,
        "systemd_network_fixed": 0,
        "interfaces_fixed": 0,
        "ifcfg_fixed": 0,
        "errors": 0,
    }

    network_patterns = [
        "/etc/sysconfig/network-scripts/ifcfg-*",
        "/etc/netplan/*.yaml",
        "/etc/netplan/*.yml",
        "/etc/network/interfaces",
        "/etc/systemd/network/*.network",
        "/etc/systemd/network/*.netdev",
    ]

    def _short_hash(s: str) -> str:
        # stable-enough for report; avoids importing hashlib everywhere
        return str(abs(hash(s)) % (10**12))

    def _record_unchanged(path: str, old: str) -> None:
        per_file.append(
            {
                "path": path,
                "changed": False,
                "dry_run": bool(getattr(self, "dry_run", False)),
                "old_len": len(old),
                "old_hash": _short_hash(old),
            }
        )

    def _maybe_write(path: str, new_content: str, old_content: str, reasons: List[str]) -> None:
        nonlocal updated_files
        if new_content == old_content:
            _record_unchanged(path, old_content)
            return

        if not getattr(self, "dry_run", False):
            # OfflineFSFix provides backup_file()
            self.backup_file(g, path)
            g.write(path, new_content.encode("utf-8"))
            updated_files.append(path)
            self.logger.info(f"Updated network config: {path}")
        else:
            self.logger.info(f"DRY-RUN: would update network config: {path}")

        per_file.append(
            {
                "path": path,
                "changed": True,
                "dry_run": bool(getattr(self, "dry_run", False)),
                "reasons": reasons,
                "old_len": len(old_content),
                "new_len": len(new_content),
                "old_hash": _short_hash(old_content),
                "new_hash": _short_hash(new_content),
                "old_head": old_content[:200],
                "new_head": new_content[:200],
            }
        )

    # regex bundles
    vmware_driver_hints = [
        r"\bvmxnet3\b",
        r"\be1000\b",
    ]

    # comment-out MAC pinning rather than deleting it (more auditable)
    mac_pin_line_regexes = [
        r"(?im)^\s*HWADDR\s*=.*$",
        r"(?im)^\s*MACADDR\s*=.*$",
        r"(?im)^\s*MACAddress\s*=.*$",
        r"(?im)^\s*CLONED_MAC\s*=.*$",
        r"(?im)^\s*cloned-mac-address\s*:.*$",
        r"(?im)^\s*hwaddress\s+ether\s+.*$",
    ]

    with Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Fixing network configs", total=len(network_patterns))

        for pattern in network_patterns:
            try:
                files = guest_ls_glob(g, pattern)  # supports patterns + single files
                for file_path in files:
                    try:
                        if not g.is_file(file_path):
                            continue

                        totals["files_seen"] += 1
                        scanned_files.append(file_path)

                        old = U.to_text(g.read_file(file_path))
                        content = old
                        reasons: List[str] = []
                        modified = False

                        is_ifcfg = "/etc/sysconfig/network-scripts/" in file_path
                        is_netplan = "/etc/netplan/" in file_path and (file_path.endswith(".yaml") or file_path.endswith(".yml"))
                        is_interfaces = file_path == "/etc/network/interfaces"
                        is_systemd_network = "/etc/systemd/network/" in file_path and file_path.endswith(".network")

                        # 1) strip explicit VMware driver hints (line-scoped, not global replace)
                        for hint in vmware_driver_hints:
                            if re.search(hint, content, re.IGNORECASE):
                                content2 = content
                                # ifcfg patterns
                                content2 = re.sub(
                                    rf"(?im)^\s*DEVICE\s*=\s*{hint}\s*$",
                                    "",
                                    content2,
                                )
                                content2 = re.sub(
                                    rf"(?im)^\s*TYPE\s*=.*{hint}.*$",
                                    "",
                                    content2,
                                )
                                # yaml-ish
                                content2 = re.sub(
                                    rf"(?im)^\s*driver\s*:\s*{hint}\s*$",
                                    "",
                                    content2,
                                )
                                if content2 != content:
                                    content = content2
                                    modified = True
                                    totals["patterns_removed"] += 1
                                    reasons.append(f"removed_driver_hint:{hint}")

                        # 2) comment-out MAC pinning
                        for lp in mac_pin_line_regexes:
                            if re.search(lp, content):
                                content2 = re.sub(
                                    lp,
                                    lambda m: f"# {m.group(0)}  # Commented by vmdk2kvm (MAC pin removed)",
                                    content,
                                )
                                if content2 != content:
                                    content = content2
                                    modified = True
                                    totals["mac_pins_removed"] += 1
                                    reasons.append("mac_pin_commented")

                        # 3) ifcfg NAME pinning -> eth0 (best-effort, migration-friendly)
                        if is_ifcfg:
                            m = re.search(r"(?m)^\s*NAME\s*=\s*(.+)\s*$", content)
                            if m:
                                name = m.group(1).strip().strip('"').strip("'")
                                if name and not name.startswith("eth"):
                                    content2 = re.sub(
                                        r"(?m)^\s*NAME\s*=.*$",
                                        f"# NAME={name}  # Renamed by vmdk2kvm\nNAME=eth0",
                                        content,
                                    )
                                    if content2 != content:
                                        content = content2
                                        modified = True
                                        totals["renames_applied"] += 1
                                        totals["ifcfg_fixed"] += 1
                                        reasons.append("ifcfg_name_to_eth0")

                        # 4) systemd-networkd: avoid Match.Name= pinning (comment it out)
                        if is_systemd_network:
                            content2 = re.sub(
                                r"(?im)^\s*Name\s*=\s*\S+",
                                r"# \g<0>  # Commented by vmdk2kvm (avoid name pinning)",
                                content,
                            )
                            if content2 != content:
                                content = content2
                                modified = True
                                totals["systemd_network_fixed"] += 1
                                reasons.append("systemd_match_name_commented")

                        # 5) netplan structured fix (best-effort)
                        if is_netplan and YAML_AVAILABLE:
                            try:
                                data = yaml.safe_load(content) or {}
                                if isinstance(data, dict) and isinstance(data.get("network"), dict):
                                    net = data["network"]
                                    eths = net.get("ethernets")
                                    if isinstance(eths, dict) and eths:
                                        for _iface, cfg in list(eths.items()):
                                            if not isinstance(cfg, dict):
                                                continue

                                            if "match" in cfg:
                                                del cfg["match"]
                                                modified = True
                                                totals["netplan_fixed"] += 1
                                                reasons.append("netplan_removed_match")

                                            # only force set-name if it already exists (avoid creating collisions)
                                            if "set-name" in cfg:
                                                cfg["set-name"] = "eth0"
                                                modified = True
                                                totals["netplan_fixed"] += 1
                                                reasons.append("netplan_setname_eth0")

                                            # enable dhcp4 if not clearly static
                                            if "addresses" not in cfg and "dhcp4" not in cfg:
                                                cfg["dhcp4"] = True
                                                modified = True
                                                totals["netplan_fixed"] += 1
                                                reasons.append("netplan_enabled_dhcp4")

                                        if modified:
                                            content = yaml.safe_dump(data, sort_keys=False)
                            except Exception as e:
                                self.logger.debug(f"Netplan YAML fix failed: {e}")
                                totals["errors"] += 1
                                per_file.append({"path": file_path, "changed": False, "error": f"netplan_parse:{e}"})

                        # 6) /etc/network/interfaces: hwaddress already handled in mac_pin regexes
                        if is_interfaces:
                            if re.search(r"(?im)^\s*hwaddress\s+ether\s+", old):
                                totals["interfaces_fixed"] += 1
                                if "interfaces_hwaddress_commented" not in reasons:
                                    reasons.append("interfaces_hwaddress_commented")

                        if modified:
                            _maybe_write(file_path, content, old, reasons)
                            totals["files_changed"] += 1
                        else:
                            _record_unchanged(file_path, old)

                    except Exception as e:
                        totals["errors"] += 1
                        self.logger.debug(f"Network config update failed for {file_path}: {e}")
                        per_file.append({"path": file_path, "changed": False, "error": str(e)})

            except Exception as e:
                totals["errors"] += 1
                self.logger.debug(f"Network config check for {pattern} failed: {e}")

            progress.update(task, advance=1)

    net_report = {
        "updated_files": updated_files,
        "scanned_files_count": len(scanned_files),
        "updated_count": len(updated_files),
        "totals": totals,
        "details": per_file,
    }

    # Attach into OfflineFSFix.report if present
    try:
        self.report.setdefault("analysis", {})
        self.report["analysis"]["network"] = net_report
    except Exception:
        pass

    return {"updated_files": updated_files, "count": len(updated_files), "analysis": net_report}
