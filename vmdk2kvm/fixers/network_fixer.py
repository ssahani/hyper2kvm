# SPDX-License-Identifier: LGPL-3.0-or-later
# vmdk2kvm/fixers/network_fixer.py
"""
Comprehensive network configuration fixer for VMware -> KVM migration.

This file contains the engine (NetworkFixer):
- discovery (find configs)
- topology build
- per-backend fixers
- validation + apply + summary report
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

import guestfs  # type: ignore

from ..config.config_loader import YAML_AVAILABLE, yaml
from ..core.utils import U, guest_ls_glob

from .network_model import (
    DeviceKind,
    FixLevel,
    FixResult,
    IfcfgKV,
    NetworkConfig,
    NetworkConfigType,
    TopologyGraph,
    TopoEdge,
    ifcfg_kind_and_links,
)


class NetworkFixer:
    """Main network fixing class."""

    VMWARE_DRIVERS = {
        "vmxnet3": r"\bvmxnet3\b",
        "e1000": r"\be1000\b",
        "e1000e": r"\be1000e\b",
        "vmxnet": r"\bvmxnet\b",
        "vlance": r"\bvlance\b",
        "pvscsi": r"\bpvscsi\b",
        "vmw_pvscsi": r"\bvmw_pvscsi\b",
    }

    MAC_PINNING_PATTERNS = [
        (r"(?im)^\s*HWADDR\s*=.*$", "ifcfg-hwaddr"),
        (r"(?im)^\s*MACADDR\s*=.*$", "ifcfg-macaddr"),
        (r"(?im)^\s*MACADDRESS\s*=.*$", "ifcfg-macaddress"),
        (r"(?im)^\s*CLONED_MAC\s*=.*$", "ifcfg-cloned-mac"),
        (r"(?im)^\s*macaddress\s*:.*$", "netplan-macaddress"),
        (r"(?im)^\s*cloned-mac-address\s*:.*$", "netplan-cloned-mac"),
        (r"(?im)^\s*hwaddress\s+ether\s+.*$", "interfaces-hwaddress"),
        (r"(?im)^\s*MACAddress\s*=.*$", "systemd-macaddress"),
        (r"(?im)^\s*Match\s+MACAddress\s*=.*$", "systemd-match-mac"),
        (r"(?im)^\s*mac-address\s*=.*$", "nm-mac-address"),
        (r"(?im)^\s*cloned-mac-address\s*=.*$", "nm-cloned-mac"),
        (r"(?im)^\s*mac-address-blacklist\s*=.*$", "nm-mac-blacklist"),
    ]

    INTERFACE_NAME_PATTERNS = [
        (r"(?i)^ens(192|224|256|193|225)$", "vmware-ens-pattern"),
        (r"(?i)^vmnic\d+$", "vmware-vmnic"),
    ]

    CONFIG_PATTERNS = {
        NetworkConfigType.IFCONFIG_RH: [
            "/etc/sysconfig/network-scripts/ifcfg-*",
            "/etc/sysconfig/network/ifcfg-*",
        ],
        NetworkConfigType.NETPLAN: [
            "/etc/netplan/*.yaml",
            "/etc/netplan/*.yml",
        ],
        NetworkConfigType.INTERFACES: [
            "/etc/network/interfaces",
            "/etc/network/interfaces.d/*",
        ],
        NetworkConfigType.SYSTEMD_NETWORK: [
            "/etc/systemd/network/*.network",
        ],
        NetworkConfigType.SYSTEMD_NETDEV: [
            "/etc/systemd/network/*.netdev",
        ],
        NetworkConfigType.NETWORK_MANAGER: [
            "/etc/NetworkManager/system-connections/*.nmconnection",
            "/etc/NetworkManager/system-connections/*",
        ],
        NetworkConfigType.WICKED: [
            "/etc/wicked/ifconfig/*.xml",
            "/etc/wicked/ifconfig/*",
        ],
        NetworkConfigType.WICKED_IFCFG: [
            "/etc/sysconfig/network/ifcfg-*",
        ],
    }

    def __init__(
        self,
        logger: logging.Logger,
        fix_level: FixLevel = FixLevel.MODERATE,
        *,
        dry_run: bool = False,
        backup_suffix: Optional[str] = None,
    ):
        self.logger = logger
        self.fix_level = fix_level
        self.dry_run = dry_run
        self.backup_suffix = backup_suffix or f".vmdk2kvm_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # ---------------------------
    # Compatibility helpers
    # ---------------------------

    def _ifcfg_kind_and_links(self, ifcfg: IfcfgKV) -> Any:
        """
        Fix: this code calls self._ifcfg_kind_and_links(), but the implementation
        lives in network_model as ifcfg_kind_and_links().

        Keep a tiny wrapper so older call-sites remain valid.
        """
        try:
            return ifcfg_kind_and_links(ifcfg)
        except Exception as e:
            self.logger.debug("Topology: ifcfg_kind_and_links parse failed: %s", e)
            return (DeviceKind.UNKNOWN, [])

    # ---------------------------
    # IO helpers
    # ---------------------------

    def _get_mode_safe(self, g: guestfs.GuestFS, path: str) -> Optional[int]:
        try:
            st = g.stat(path)
            mode = int(st.get("mode", 0)) & 0o7777
            return mode if mode else None
        except Exception:
            return None

    def _chmod_safe(self, g: guestfs.GuestFS, path: str, mode: int) -> None:
        try:
            g.chmod(mode, path)
        except Exception as e:
            self.logger.debug("chmod(%s) failed for %s: %s", oct(mode), path, e)

    def _write_atomic(self, g: guestfs.GuestFS, path: str, data: bytes) -> None:
        tmp = f"{path}.tmp.vmdk2kvm"
        try:
            g.write(tmp, data)
            g.rename(tmp, path)
        except Exception:
            try:
                if g.exists(tmp):
                    g.rm_f(tmp)
            except Exception:
                pass
            g.write(path, data)

    def _write_with_mode(self, g: guestfs.GuestFS, path: str, content: str, *, prefer_mode: Optional[int] = None) -> None:
        old_mode = self._get_mode_safe(g, path)
        self._write_atomic(g, path, content.encode("utf-8"))
        if old_mode is not None:
            self._chmod_safe(g, path, old_mode)
        elif prefer_mode is not None:
            self._chmod_safe(g, path, prefer_mode)

    # ---------------------------
    # Detection / IO
    # ---------------------------

    def detect_config_type(self, path: str) -> NetworkConfigType:
        if "/etc/sysconfig/network-scripts/ifcfg-" in path:
            return NetworkConfigType.IFCONFIG_RH
        if "/etc/netplan/" in path and (path.endswith(".yaml") or path.endswith(".yml")):
            return NetworkConfigType.NETPLAN
        if "/etc/network/interfaces" in path:
            return NetworkConfigType.INTERFACES
        if "/etc/systemd/network/" in path:
            if path.endswith(".network"):
                return NetworkConfigType.SYSTEMD_NETWORK
            if path.endswith(".netdev"):
                return NetworkConfigType.SYSTEMD_NETDEV
        if "/etc/NetworkManager/system-connections/" in path:
            return NetworkConfigType.NETWORK_MANAGER
        if "/etc/wicked/" in path:
            return NetworkConfigType.WICKED
        if "/etc/sysconfig/network/ifcfg-" in path:
            return NetworkConfigType.WICKED_IFCFG
        return NetworkConfigType.UNKNOWN

    def _should_skip_path(self, path: str) -> bool:
        p = path or ""
        if self.backup_suffix and self.backup_suffix in p:
            return True
        if re.search(r"(\.bak|~|\.orig|\.rpmnew|\.rpmsave)$", p):
            return True
        base = p.split("/")[-1]
        if base in ("ifcfg-lo", "ifcfg-bonding_masters"):
            return True
        return False

    def create_backup(self, g: guestfs.GuestFS, path: str, content: str) -> str:
        backup_path = f"{path}{self.backup_suffix}"
        try:
            if hasattr(g, "cp_a"):
                try:
                    g.cp_a(path, backup_path)
                    self.logger.debug("🧷 backup (cp_a): %s", backup_path)
                    return backup_path
                except Exception:
                    pass

            try:
                g.copy_file_to_file(path, backup_path)
                self.logger.debug("🧷 backup (copy_file_to_file): %s", backup_path)
                return backup_path
            except Exception:
                pass

            g.write(backup_path, content.encode("utf-8"))
            self.logger.debug("🧷 backup (write): %s", backup_path)
            return backup_path
        except Exception as e:
            self.logger.warning("Failed to create backup for %s: %s", path, e)
            return ""

    def calculate_hash(self, content: str) -> str:
        h = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
        return h[:12]

    def read_config_file(self, g: guestfs.GuestFS, path: str) -> Optional[NetworkConfig]:
        try:
            if not g.is_file(path):
                return None
            content_bytes = g.read_file(path)
            content = U.to_text(content_bytes)
            config_type = self.detect_config_type(path)
            content_hash = self.calculate_hash(content)
            return NetworkConfig(path=path, content=content, type=config_type, original_hash=content_hash)
        except Exception as e:
            self.logger.error("Failed to read config file %s: %s", path, e)
            return None

    def find_network_configs(self, g: guestfs.GuestFS) -> List[NetworkConfig]:
        configs: List[NetworkConfig] = []
        seen: Set[str] = set()

        for _config_type, patterns in self.CONFIG_PATTERNS.items():
            for pattern in patterns:
                try:
                    files = guest_ls_glob(g, pattern)
                    for file_path in files:
                        if file_path in seen:
                            continue
                        if self._should_skip_path(file_path):
                            continue
                        seen.add(file_path)
                        cfg = self.read_config_file(g, file_path)
                        if cfg:
                            configs.append(cfg)
                except Exception as e:
                    self.logger.debug("glob failed (%s): %s", pattern, e)

        # extra “try anyway” locations
        for location in ("/etc/sysconfig/network/ifcfg-*", "/etc/ifcfg-*"):
            try:
                files = guest_ls_glob(g, location)
                for file_path in files:
                    if file_path in seen:
                        continue
                    if self._should_skip_path(file_path):
                        continue
                    seen.add(file_path)
                    cfg = self.read_config_file(g, file_path)
                    if cfg:
                        configs.append(cfg)
            except Exception:
                pass

        return configs

    # ---------------------------
    # Helpers: interface rename
    # ---------------------------

    def needs_interface_rename(self, interface_name: str) -> bool:
        name = (interface_name or "").strip()
        for pattern, _tag in self.INTERFACE_NAME_PATTERNS:
            if re.match(pattern, name, re.IGNORECASE):
                return True

        standard_patterns = [
            r"^eth\d+$",
            r"^en[opsx]\w+$",
            r"^ens\d+$",
            r"^eno\d+$",
            r"^enp\d+s\d+$",
        ]
        for pattern in standard_patterns:
            if re.match(pattern, name, re.IGNORECASE):
                return False

        return False

    def get_safe_interface_name(self, current_name: str) -> str:
        match = re.search(r"\d+", current_name or "")
        if match:
            return f"eth{match.group()}"
        return "eth0"

    # ---------------------------
    # Topology build
    # ---------------------------

    def _netplan_add_to_topology(self, graph: TopologyGraph, cfg: NetworkConfig, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            return
        nw = data.get("network")
        if not isinstance(nw, dict):
            return

        eths = nw.get("ethernets")
        if isinstance(eths, dict):
            for ifname, icfg in eths.items():
                graph.add_node(str(ifname), DeviceKind.ETHERNET, source=cfg.path)
                if isinstance(icfg, dict):
                    set_name = icfg.get("set-name")
                    if isinstance(set_name, str) and set_name.strip():
                        graph.add_node(set_name.strip(), DeviceKind.ETHERNET, source=cfg.path)

        bonds = nw.get("bonds")
        if isinstance(bonds, dict):
            for bname, bcfg in bonds.items():
                graph.add_node(str(bname), DeviceKind.BOND, source=cfg.path)
                if isinstance(bcfg, dict):
                    ifaces = bcfg.get("interfaces")
                    if isinstance(ifaces, list):
                        for m in ifaces:
                            if isinstance(m, str):
                                graph.add_node(m, DeviceKind.ETHERNET, source=cfg.path)
                                graph.add_edge(m, str(bname), "slave")

        bridges = nw.get("bridges")
        if isinstance(bridges, dict):
            for brname, brcfg in bridges.items():
                graph.add_node(str(brname), DeviceKind.BRIDGE, source=cfg.path)
                if isinstance(brcfg, dict):
                    ifaces = brcfg.get("interfaces")
                    if isinstance(ifaces, list):
                        for m in ifaces:
                            if isinstance(m, str):
                                graph.add_node(m, graph.infer_kind(m), source=cfg.path)
                                graph.add_edge(m, str(brname), "port")

        vlans = nw.get("vlans")
        if isinstance(vlans, dict):
            for vname, vcfg in vlans.items():
                graph.add_node(str(vname), DeviceKind.VLAN, source=cfg.path)
                if isinstance(vcfg, dict):
                    link = vcfg.get("link")
                    if isinstance(link, str) and link.strip():
                        graph.add_node(link.strip(), graph.infer_kind(link.strip()), source=cfg.path)
                        graph.add_edge(link.strip(), str(vname), "vlan")

    def _systemd_add_to_topology(self, graph: TopologyGraph, cfg: NetworkConfig) -> None:
        text = cfg.content
        sec = None
        match_names: List[str] = []
        bond_ref: Optional[str] = None
        bridge_ref: Optional[str] = None
        vlan_refs: List[str] = []

        for ln in text.splitlines():
            s = ln.strip()
            if not s or s.startswith("#") or s.startswith(";"):
                continue
            msec = re.match(r"^\s*\[(.+)\]\s*$", s)
            if msec:
                sec = msec.group(1).strip().lower()
                continue

            if sec == "match":
                m = re.match(r"^\s*Name\s*=\s*(.+)\s*$", ln, re.IGNORECASE)
                if m:
                    parts = re.split(r"\s+", m.group(1).strip())
                    for p in parts:
                        if p and not any(ch in p for ch in "*?[]"):
                            match_names.append(p)

            if sec == "network":
                m = re.match(r"^\s*Bond\s*=\s*(.+)\s*$", ln, re.IGNORECASE)
                if m:
                    bond_ref = m.group(1).strip()
                m = re.match(r"^\s*Bridge\s*=\s*(.+)\s*$", ln, re.IGNORECASE)
                if m:
                    bridge_ref = m.group(1).strip()
                m = re.match(r"^\s*VLAN\s*=\s*(.+)\s*$", ln, re.IGNORECASE)
                if m:
                    for p in re.split(r"\s+", m.group(1).strip()):
                        if p:
                            vlan_refs.append(p)

        for n in match_names:
            graph.add_node(n, DeviceKind.ETHERNET, source=cfg.path)
            if bond_ref:
                graph.add_node(bond_ref, DeviceKind.BOND, source=cfg.path)
                graph.add_edge(n, bond_ref, "slave")
            if bridge_ref:
                graph.add_node(bridge_ref, DeviceKind.BRIDGE, source=cfg.path)
                graph.add_edge(n, bridge_ref, "port")
            for vr in vlan_refs:
                graph.add_node(vr, DeviceKind.VLAN, source=cfg.path)
                graph.add_edge(n, vr, "vlan")

    def _nm_add_to_topology(self, graph: TopologyGraph, cfg: NetworkConfig) -> None:
        text = cfg.content
        sec = None
        conn_type = None
        iface_name = None
        vlan_parent = None

        for ln in text.splitlines():
            s = ln.strip()
            if not s or s.startswith("#") or s.startswith(";"):
                continue
            msec = re.match(r"^\s*\[(.+)\]\s*$", s)
            if msec:
                sec = msec.group(1).strip().lower()
                continue

            if sec == "connection":
                m = re.match(r"^\s*type\s*=\s*(.+?)\s*$", ln, re.IGNORECASE)
                if m:
                    conn_type = m.group(1).strip().lower()
                m = re.match(r"^\s*interface-name\s*=\s*(.+?)\s*$", ln, re.IGNORECASE)
                if m:
                    iface_name = m.group(1).strip()

            if sec == "vlan":
                m = re.match(r"^\s*parent\s*=\s*(.+?)\s*$", ln, re.IGNORECASE)
                if m:
                    vlan_parent = m.group(1).strip()

        kind = DeviceKind.UNKNOWN
        if conn_type in ("ethernet", "802-3-ethernet"):
            kind = DeviceKind.ETHERNET
        elif conn_type == "bond":
            kind = DeviceKind.BOND
        elif conn_type == "bridge":
            kind = DeviceKind.BRIDGE
        elif conn_type == "vlan":
            kind = DeviceKind.VLAN

        if iface_name:
            graph.add_node(iface_name, kind if kind != DeviceKind.UNKNOWN else graph.infer_kind(iface_name), source=cfg.path)

        if kind == DeviceKind.VLAN and iface_name and vlan_parent:
            graph.add_node(vlan_parent, graph.infer_kind(vlan_parent), source=cfg.path)
            graph.add_edge(vlan_parent, iface_name, "vlan")

    def build_topology(self, configs: List[NetworkConfig]) -> TopologyGraph:
        graph = TopologyGraph()
        backend_touch: Dict[str, Set[str]] = {}

        for cfg in configs:
            try:
                if cfg.type in (NetworkConfigType.IFCONFIG_RH, NetworkConfigType.WICKED_IFCFG):
                    ifcfg = IfcfgKV.parse(cfg.content)
                    dev = (ifcfg.get("DEVICE") or "").strip()
                    if dev:
                        kind, edges = ifcfg_kind_and_links(ifcfg)
                        graph.add_node(dev, kind, source=cfg.path)
                        for e in edges:
                            graph.add_node(e.src, graph.infer_kind(e.src), source=cfg.path)
                            graph.add_node(e.dst, graph.infer_kind(e.dst), source=cfg.path)
                            graph.add_edge(e.src, e.dst, e.kind)
                        backend_touch.setdefault(dev, set()).add(cfg.type.value)

                elif cfg.type == NetworkConfigType.NETPLAN and YAML_AVAILABLE:
                    try:
                        data = yaml.safe_load(cfg.content) or {}
                        if isinstance(data, dict):
                            self._netplan_add_to_topology(graph, cfg, data)
                    except Exception:
                        pass

                elif cfg.type == NetworkConfigType.SYSTEMD_NETWORK:
                    self._systemd_add_to_topology(graph, cfg)

                elif cfg.type == NetworkConfigType.NETWORK_MANAGER:
                    self._nm_add_to_topology(graph, cfg)

            except Exception as e:
                graph.warnings.append(f"Topology parse error for {cfg.path}: {e}")

        for dev, backends in backend_touch.items():
            if len(backends) > 1:
                graph.warnings.append(
                    f"Multiple backends appear to manage '{dev}': {sorted(backends)}. "
                    "This can cause race/conflicts after boot."
                )

        return graph

    # ---------------------------
    # Rename plan (aggressive)
    # ---------------------------

    def compute_rename_map(self, topo: TopologyGraph) -> Dict[str, str]:
        if self.fix_level != FixLevel.AGGRESSIVE:
            return {}

        rename: Dict[str, str] = {}
        used: Set[str] = set(topo.nodes.keys())

        for node in topo.nodes.values():
            if node.kind not in (DeviceKind.ETHERNET, DeviceKind.UNKNOWN):
                continue
            old = node.name
            if not self.needs_interface_rename(old):
                continue
            new = self.get_safe_interface_name(old)

            if new in used and new != old:
                base = "eth"
                num = 0
                m = re.match(r"^eth(\d+)$", new)
                if m:
                    num = int(m.group(1))
                for k in range(num, num + 32):
                    cand = f"{base}{k}"
                    if cand not in used:
                        new = cand
                        break

            if old != new:
                rename[old] = new
                used.add(new)

        return topo.rename_map_propagate(rename)

    # ---------------------------
    # Intent helpers
    # ---------------------------

    def _ifcfg_has_static_intent(self, ifcfg: IfcfgKV) -> bool:
        static_keys = ["IPADDR", "IPADDR0", "PREFIX", "NETMASK", "GATEWAY", "DNS1", "DNS2", "IPV6ADDR", "IPV6_DEFAULTGW"]
        if any(ifcfg.has(k) for k in static_keys):
            return True
        bp = (ifcfg.get("BOOTPROTO") or "").strip().lower()
        return bp in ("static",)

    def _netplan_iface_has_static_intent(self, iface_cfg: Dict[str, Any]) -> bool:
        return any(k in iface_cfg for k in ("addresses", "gateway4", "gateway6", "routes", "routing-policy", "nameservers"))

    # ---------------------------
    # Fixers
    # ---------------------------

    def fix_ifcfg_rh(
        self,
        config: NetworkConfig,
        *,
        topo: Optional[TopologyGraph] = None,
        rename_map: Optional[Dict[str, str]] = None,
    ) -> FixResult:
        """
        Fix ifcfg files (RHEL-ish and SUSE-ish):
        - Remove MAC pinning (MODERATE+)
        - Comment out VMware-ish driver tokens on DEVICE/TYPE lines (conservative too)
        - Remove VMware-ish params (comment out)
        - In AGGRESSIVE mode: rename DEVICE/NAME + propagate to PHYSDEV/MASTER/BRIDGE where applicable
        - DHCP normalization ONLY when safe:
            - no static intent
            - not a slave/port of bond/bridge
            - and BOOTPROTO is invalid/weird
        """
        fixes_applied: List[str] = []
        warnings: List[str] = []
        ifcfg = IfcfgKV.parse(config.content)

        dev = (ifcfg.get("DEVICE") or "").strip()
        if not dev:
            return FixResult(config=config, new_content=config.content, applied_fixes=[], validation_errors=["Missing DEVICE="])

        kind, edges = self._ifcfg_kind_and_links(ifcfg)
        topo_kind = topo.infer_kind(dev) if topo else kind

        # --- remove MAC pinning keys
        if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
            for k in ("HWADDR", "MACADDR", "MACADDRESS", "CLONED_MAC"):
                if ifcfg.has(k):
                    ifcfg.delete(k, "MAC pinning removed by vmdk2kvm")
                    fixes_applied.append(f"removed-mac-pinning-{k.lower()}")

        # --- VMware driver token cleanup (comment out lines containing vmxnet* etc when in DEVICE/TYPE context)
        # ifcfg parser doesn't preserve arbitrary matching, but we can do safe line-based comments:
        new_lines: List[str] = []
        for ln in ifcfg.lines:
            changed = False
            for driver_name, pattern in self.VMWARE_DRIVERS.items():
                if re.search(pattern, ln, re.IGNORECASE):
                    # Only comment out if it's a setting line (avoid nuking comments)
                    if re.match(r"^\s*(DEVICE|TYPE|ETHTOOL_OPTS|OPTIONS|DRIVER)\s*=", ln, re.IGNORECASE):
                        if not ln.lstrip().startswith("#"):
                            new_lines.append(f"# {ln}  # VMware token removed by vmdk2kvm")
                            fixes_applied.append(f"removed-vmware-driver-token-{driver_name}")
                            changed = True
                    break
            if changed:
                continue
            new_lines.append(ln)
        ifcfg.lines = new_lines  # keep kv map as-is; key edits below still OK (we mostly changed non-parsed lines)

        # --- VMware-ish params (comment out if present in any line)
        vmware_params = ["VMWARE_", "VMXNET_", "SCSIDEVICE", "SUBCHANNELS"]
        new_lines2: List[str] = []
        for ln in ifcfg.lines:
            u = ln.upper()
            if any(p in u for p in vmware_params) and not ln.lstrip().startswith("#"):
                new_lines2.append(f"# {ln}  # VMware-specific parameter removed by vmdk2kvm")
                for p in vmware_params:
                    if p in u:
                        fixes_applied.append(f"removed-vmware-param-{p.lower()}")
                continue
            new_lines2.append(ln)
        ifcfg.lines = new_lines2

        # --- Aggressive renaming (DEVICE/NAME + references)
        rm = rename_map or {}
        if self.fix_level == FixLevel.AGGRESSIVE and rm:
            # Rename DEVICE itself if needed
            if dev in rm:
                new_dev = rm[dev]
                ifcfg.set("DEVICE", new_dev)
                fixes_applied.append("renamed-device")
                dev = new_dev  # update local

            # NAME= might exist and can be used by NM; keep aligned
            namev = (ifcfg.get("NAME") or "").strip().strip('"\'')
            if namev and namev in rm:
                ifcfg.set("NAME", rm[namev])
                fixes_applied.append("renamed-name")

            # PHYSDEV (vlan parent)
            phys = (ifcfg.get("PHYSDEV") or "").strip()
            if phys and phys in rm:
                ifcfg.set("PHYSDEV", rm[phys])
                fixes_applied.append("renamed-physdev")

            # MASTER (bond master usually not renamed; but if it is, propagate)
            master = (ifcfg.get("MASTER") or "").strip()
            if master and master in rm:
                ifcfg.set("MASTER", rm[master])
                fixes_applied.append("renamed-master-ref")

            # BRIDGE ref (bridge usually not renamed; but if it is, propagate)
            br = (ifcfg.get("BRIDGE") or "").strip()
            if br and br in rm:
                ifcfg.set("BRIDGE", rm[br])
                fixes_applied.append("renamed-bridge-ref")

        # --- DHCP normalization (careful!)
        # Determine whether this device is a "lower layer" port/slave.
        is_slave_or_port = any(e.src == dev and e.kind in ("slave", "port") for e in edges)
        if topo is not None:
            # also use topology edges if available
            is_slave_or_port = is_slave_or_port or any(e.src == dev and e.kind in ("slave", "port") for e in topo.edges)

        bootproto = (ifcfg.get("BOOTPROTO") or "").strip().strip('"\'').lower()

        if bootproto and bootproto not in ("dhcp", "static", "none", "bootp"):
            # invalid -> set dhcp only if safe
            if not self._ifcfg_has_static_intent(ifcfg) and not is_slave_or_port:
                ifcfg.set("BOOTPROTO", "dhcp")
                fixes_applied.append("normalized-bootproto->dhcp")
        elif bootproto == "none" and self.fix_level == FixLevel.AGGRESSIVE:
            # do not force dhcp for slaves/ports or for logical masters that likely carry L3 elsewhere
            if not self._ifcfg_has_static_intent(ifcfg) and not is_slave_or_port and topo_kind == DeviceKind.ETHERNET:
                ifcfg.set("BOOTPROTO", "dhcp")
                fixes_applied.append("normalized-bootproto-none->dhcp")

        # --- warn on risky layout: IP on a bridge port (common "wrong" config)
        if kind == DeviceKind.ETHERNET and (ifcfg.has("BRIDGE") or any(e.kind == "port" for e in edges)):
            if self._ifcfg_has_static_intent(ifcfg):
                warnings.append(
                    f"{config.path}: IP/static config appears on a bridge port ({dev}). "
                    "Often the IP should live on the bridge device, not the port. Not auto-moving."
                )

        # finalize
        new_content = ifcfg.render()
        return FixResult(config=config, new_content=new_content, applied_fixes=fixes_applied, warnings=warnings)

    def fix_netplan(
        self,
        config: NetworkConfig,
        *,
        topo: Optional[TopologyGraph] = None,
        rename_map: Optional[Dict[str, str]] = None,
    ) -> FixResult:
        """Fix Ubuntu netplan YAML configuration with topology-aware behavior."""
        if not YAML_AVAILABLE:
            return FixResult(
                config=config,
                new_content=config.content,
                applied_fixes=[],
                validation_errors=["YAML support not available"],
            )

        fixes_applied: List[str] = []
        warnings: List[str] = []
        rm = rename_map or {}

        try:
            data = yaml.safe_load(config.content) or {}
            if not isinstance(data, dict):
                return FixResult(config=config, new_content=config.content, applied_fixes=[], validation_errors=["Netplan YAML is not a dict"])

            nw = data.get("network")
            if not isinstance(nw, dict):
                return FixResult(config=config, new_content=config.content, applied_fixes=[], validation_errors=["Missing 'network:' section"])

            renderer = str(nw.get("renderer") or "").lower()

            # Helper: remove mac pinning keys in a dict
            def scrub_mac(d: Dict[str, Any], *, prefix: str) -> None:
                if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                    # match.macaddress
                    match_cfg = d.get("match")
                    if isinstance(match_cfg, dict) and "macaddress" in match_cfg:
                        del match_cfg["macaddress"]
                        fixes_applied.append(f"{prefix}-removed-match-mac")
                        if not match_cfg:
                            del d["match"]
                            fixes_applied.append(f"{prefix}-removed-empty-match")

                    # direct keys
                    for k in ("macaddress", "cloned-mac-address"):
                        if k in d:
                            del d[k]
                            fixes_applied.append(f"{prefix}-removed-{k}")

            # Helper: apply rename for interface references lists
            def rename_list(lst: Any) -> Any:
                if not isinstance(lst, list):
                    return lst
                out: List[Any] = []
                changed = False
                for x in lst:
                    if isinstance(x, str) and x in rm:
                        out.append(rm[x])
                        changed = True
                    else:
                        out.append(x)
                if changed:
                    fixes_applied.append("netplan-renamed-interfaces-ref")
                return out

            # Helper: rename single ref string
            def rename_ref(x: Any, tag: str) -> Any:
                if isinstance(x, str) and x in rm:
                    fixes_applied.append(tag)
                    return rm[x]
                return x

            # Ethernets
            eths = nw.get("ethernets")
            if isinstance(eths, dict):
                for ifname, icfg in list(eths.items()):
                    if not isinstance(icfg, dict):
                        continue
                    scrub_mac(icfg, prefix=f"eth-{ifname}")

                    # Remove vmware driver hint if present
                    if "driver" in icfg:
                        drv = str(icfg.get("driver") or "")
                        for vmware_driver in self.VMWARE_DRIVERS:
                            if vmware_driver in drv.lower():
                                del icfg["driver"]
                                fixes_applied.append(f"eth-{ifname}-removed-vmware-driver-{vmware_driver}")
                                break

                    # Safe DHCP: only on L3 interfaces that are not used as lower-layer members
                    has_static = self._netplan_iface_has_static_intent(icfg)
                    is_member = False
                    # member if referenced by any bond/bridge as slave/port, or as VLAN link
                    # we detect by scanning netplan itself later; here best-effort using topology
                    if topo is not None:
                        is_member = any(e.src == ifname and e.kind in ("slave", "port") for e in topo.edges) or any(
                            e.src == ifname and e.kind == "vlan" for e in topo.edges
                        )

                    if not has_static and "dhcp4" not in icfg and renderer != "networkmanager":
                        if not is_member:
                            icfg["dhcp4"] = True
                            fixes_applied.append(f"eth-{ifname}-enabled-dhcp4")

                    # rename set-name (do NOT rename dict keys automatically)
                    if self.fix_level == FixLevel.AGGRESSIVE and "set-name" in icfg:
                        icfg["set-name"] = rename_ref(icfg["set-name"], "netplan-renamed-set-name")

            # Bonds
            bonds = nw.get("bonds")
            if isinstance(bonds, dict):
                for bname, bcfg in bonds.items():
                    if not isinstance(bcfg, dict):
                        continue
                    scrub_mac(bcfg, prefix=f"bond-{bname}")
                    if "interfaces" in bcfg:
                        bcfg["interfaces"] = rename_list(bcfg.get("interfaces"))

                    # DHCP behavior: bond is a candidate L3 interface, but only if no static intent and not bridged
                    has_static = self._netplan_iface_has_static_intent(bcfg)
                    is_port = False
                    if topo is not None:
                        is_port = any(e.src == bname and e.kind == "port" for e in topo.edges)

                    if not has_static and "dhcp4" not in bcfg and renderer != "networkmanager":
                        if not is_port:
                            bcfg["dhcp4"] = True
                            fixes_applied.append(f"bond-{bname}-enabled-dhcp4")

            # Bridges
            bridges = nw.get("bridges")
            if isinstance(bridges, dict):
                for brname, brcfg in bridges.items():
                    if not isinstance(brcfg, dict):
                        continue
                    scrub_mac(brcfg, prefix=f"bridge-{brname}")
                    if "interfaces" in brcfg:
                        brcfg["interfaces"] = rename_list(brcfg.get("interfaces"))

                    # If bridge has no static intent and no dhcp4, add dhcp4 (networkd only)
                    has_static = self._netplan_iface_has_static_intent(brcfg)
                    if not has_static and "dhcp4" not in brcfg and renderer != "networkmanager":
                        brcfg["dhcp4"] = True
                        fixes_applied.append(f"bridge-{brname}-enabled-dhcp4")

            # VLANs
            vlans = nw.get("vlans")
            if isinstance(vlans, dict):
                for vname, vcfg in vlans.items():
                    if not isinstance(vcfg, dict):
                        continue
                    scrub_mac(vcfg, prefix=f"vlan-{vname}")
                    if "link" in vcfg:
                        vcfg["link"] = rename_ref(vcfg.get("link"), "netplan-renamed-vlan-link")

                    has_static = self._netplan_iface_has_static_intent(vcfg)
                    if not has_static and "dhcp4" not in vcfg and renderer != "networkmanager":
                        vcfg["dhcp4"] = True
                        fixes_applied.append(f"vlan-{vname}-enabled-dhcp4")

            # Render
            new_content = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)

            # sanity warning: renderer=NetworkManager means netplan just generates NM profiles;
            # we should avoid being too clever.
            if renderer == "networkmanager" and any("enabled-dhcp4" in f for f in fixes_applied):
                warnings.append(
                    f"{config.path}: renderer=NetworkManager detected; DHCP changes may be overridden by NM profiles."
                )

            return FixResult(config=config, new_content=new_content, applied_fixes=fixes_applied, warnings=warnings)

        except Exception as e:
            return FixResult(
                config=config,
                new_content=config.content,
                applied_fixes=[],
                validation_errors=[f"YAML parse error: {e}"],
            )

    def _interfaces_block_has_address(self, block_lines: List[str]) -> bool:
        for ln in block_lines:
            if re.match(r"^\s*address\s+\S+", ln):
                return True
        return False

    def fix_interfaces(self, config: NetworkConfig) -> FixResult:
        """Fix Debian/Ubuntu interfaces file (minimal safe edits)."""
        content = config.content
        fixes_applied: List[str] = []
        warnings: List[str] = []

        lines = content.split("\n")
        new_lines: List[str] = []

        current_iface: Optional[str] = None
        iface_block_lines: List[str] = []
        in_iface_block = False

        def flush_block() -> None:
            nonlocal iface_block_lines, current_iface, in_iface_block
            if not in_iface_block or not current_iface:
                iface_block_lines = []
                current_iface = None
                in_iface_block = False
                return

            # If block says "static" but missing address -> likely intended DHCP
            if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                has_address = self._interfaces_block_has_address(iface_block_lines)
                for idx, ln in enumerate(iface_block_lines):
                    if re.match(r"^\s*iface\s+\S+\s+inet\s+static\b", ln) and not has_address:
                        iface_block_lines[idx] = re.sub(r"\bstatic\b", "dhcp", ln)
                        fixes_applied.append(f"iface-{current_iface}-static-without-address->dhcp")
                        break

            new_lines.extend(iface_block_lines)
            iface_block_lines = []
            current_iface = None
            in_iface_block = False

        for line in lines:
            if line.strip().startswith("iface "):
                flush_block()
                parts = line.split()
                if len(parts) >= 4:
                    current_iface = parts[1]
                    in_iface_block = True
                else:
                    current_iface = None
                    in_iface_block = False
                iface_block_lines = [line]
                continue

            if line.strip() and not line.startswith((" ", "\t")) and in_iface_block:
                flush_block()

            # Remove vmware tokens + MAC pinning lines
            if in_iface_block:
                # VMware tokens
                for driver_name, pattern in self.VMWARE_DRIVERS.items():
                    if re.search(pattern, line, re.IGNORECASE):
                        line = f"# {line}  # VMware token removed by vmdk2kvm"
                        fixes_applied.append(f"removed-vmware-token-{driver_name}")
                        break

                # MAC pinning
                if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                    if re.match(r"(?im)^\s*hwaddress\s+ether\s+.*$", line):
                        line = f"# {line}  # MAC pinning removed by vmdk2kvm"
                        fixes_applied.append("removed-hwaddress")

                iface_block_lines.append(line)
            else:
                # Outside block: only remove VMware tokens, don't mess with structure
                for driver_name, pattern in self.VMWARE_DRIVERS.items():
                    if re.search(pattern, line, re.IGNORECASE):
                        line = f"# {line}  # VMware token removed by vmdk2kvm"
                        fixes_applied.append(f"removed-vmware-token-{driver_name}")
                        break
                new_lines.append(line)

        flush_block()

        new_content = "\n".join(new_lines)
        return FixResult(config=config, new_content=new_content, applied_fixes=fixes_applied, warnings=warnings)

    def fix_systemd_network(
        self,
        config: NetworkConfig,
        *,
        rename_map: Optional[Dict[str, str]] = None,
    ) -> FixResult:
        """
        Fix systemd-networkd configuration (.network / .netdev):
        - Remove MAC pinning in [Match] (MODERATE+)
        - Remove vmware tokens in lines (comment out)
        - Validate DHCP= values; add DHCP=yes in aggressive mode if safe
        - Apply renaming to [Match] Name=... literals (aggressive)
        """
        content = config.content
        fixes_applied: List[str] = []
        warnings: List[str] = []
        rm = rename_map or {}

        lines = content.split("\n")
        new_lines: List[str] = []

        sec = None
        saw_network_section = False
        in_network_section = False
        in_match_section = False
        saw_dhcp = False
        saw_static = False

        def is_static_key(ln: str) -> bool:
            # Common static keys in networkd
            return bool(re.match(r"^\s*(Address|Gateway|DNS|Domains|Routes?|RoutingPolicyRule)\s*=", ln, re.IGNORECASE))

        for line in lines:
            stripped = line.strip()

            msec = re.match(r"^\s*\[(.+)\]\s*$", stripped)
            if msec:
                sec = msec.group(1).strip().lower()
                in_match_section = sec == "match"
                in_network_section = sec == "network"
                if in_network_section:
                    saw_network_section = True
                new_lines.append(line)
                continue

            if in_match_section:
                if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                    if re.match(r"^\s*MACAddress\s*=", line, re.IGNORECASE):
                        new_lines.append(f"# {line}  # MAC pinning removed by vmdk2kvm")
                        fixes_applied.append("removed-mac-match")
                        continue

                # Aggressive rename for Name= lines without globs
                if self.fix_level == FixLevel.AGGRESSIVE and rm:
                    m = re.match(r"^\s*Name\s*=\s*(.+)\s*$", line, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip()
                        parts = re.split(r"\s+", val)
                        changed = False
                        out_parts: List[str] = []
                        for p in parts:
                            if p in rm and not any(ch in p for ch in "*?[]"):
                                out_parts.append(rm[p])
                                changed = True
                            else:
                                out_parts.append(p)
                        if changed:
                            line = re.sub(r"(?:^(\s*Name\s*=\s*)).*$", r"\1" + " ".join(out_parts), line, flags=re.IGNORECASE)
                            fixes_applied.append("renamed-networkd-match-name")

            # VMware token removal
            for driver_name, pattern in self.VMWARE_DRIVERS.items():
                if re.search(pattern, line, re.IGNORECASE) and not line.lstrip().startswith("#"):
                    new_lines.append(f"# {line}  # VMware token removed by vmdk2kvm")
                    fixes_applied.append(f"removed-vmware-token-{driver_name}")
                    break
            else:
                # not broken out => no vmware token triggered
                if in_network_section:
                    if re.match(r"^\s*DHCP\s*=", line, re.IGNORECASE):
                        saw_dhcp = True
                        if not re.search(r"(?i)=\s*(yes|true|ipv4|ipv6|both)\b", line):
                            line = "DHCP=yes"
                            fixes_applied.append("normalized-dhcp")
                    if is_static_key(line):
                        saw_static = True

                new_lines.append(line)

        # Aggressive: add DHCP=yes only if safe (has [Network], no DHCP, no static hints)
        if self.fix_level == FixLevel.AGGRESSIVE and saw_network_section and not saw_dhcp and not saw_static:
            out: List[str] = []
            inserted = False
            for ln in new_lines:
                out.append(ln)
                if ln.strip().lower() == "[network]" and not inserted:
                    out.append("DHCP=yes")
                    fixes_applied.append("added-dhcp")
                    inserted = True
            new_lines = out

        new_content = "\n".join(new_lines)
        return FixResult(config=config, new_content=new_content, applied_fixes=fixes_applied, warnings=warnings)

    def fix_network_manager(
        self,
        config: NetworkConfig,
        *,
        rename_map: Optional[Dict[str, str]] = None,
    ) -> FixResult:
        """
        Fix NetworkManager connection profiles (ini-like):
        - Remove MAC pinning keys in any section (MODERATE+)
        - Comment out VMware-ish tokens
        - Aggressive rename: interface-name=... if it maps (only literal)
        - VLAN parent rename: [vlan] parent=...
        We intentionally do NOT rewrite master/slave topology here (too risky across NM versions).
        """
        content = config.content
        fixes_applied: List[str] = []
        warnings: List[str] = []
        rm = rename_map or {}

        lines = content.split("\n")
        new_lines: List[str] = []
        sec = None

        for line in lines:
            s = line.strip()
            msec = re.match(r"^\s*\[(.+)\]\s*$", s)
            if msec:
                sec = msec.group(1).strip().lower()
                new_lines.append(line)
                continue

            # MAC pinning
            if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                if re.match(r"^\s*(mac-address|cloned-mac-address|mac-address-blacklist)\s*=", line, re.IGNORECASE):
                    new_lines.append(f"# {line}  # MAC pinning removed by vmdk2kvm")
                    fixes_applied.append("removed-nm-mac")
                    continue

            # Aggressive rename
            if self.fix_level == FixLevel.AGGRESSIVE and rm:
                if re.match(r"^\s*interface-name\s*=", line, re.IGNORECASE):
                    m = re.match(r"^\s*interface-name\s*=\s*(.+?)\s*$", line, re.IGNORECASE)
                    if m:
                        cur = m.group(1).strip()
                        if cur in rm:
                            line = f"interface-name={rm[cur]}"
                            fixes_applied.append("renamed-nm-interface-name")

                if sec == "vlan" and re.match(r"^\s*parent\s*=", line, re.IGNORECASE):
                    m = re.match(r"^\s*parent\s*=\s*(.+?)\s*$", line, re.IGNORECASE)
                    if m:
                        cur = m.group(1).strip()
                        if cur in rm:
                            line = f"parent={rm[cur]}"
                            fixes_applied.append("renamed-nm-vlan-parent")

            # VMware token removal
            if re.search(r"(?i)vmware|vmxnet|e1000", line) and not line.lstrip().startswith("#"):
                new_lines.append(f"# {line}  # VMware token removed by vmdk2kvm")
                fixes_applied.append("removed-vmware-setting")
                continue

            new_lines.append(line)

        new_content = "\n".join(new_lines)
        return FixResult(config=config, new_content=new_content, applied_fixes=fixes_applied, warnings=warnings)

    def fix_wicked_xml(self, config: NetworkConfig) -> FixResult:
        """
        Best-effort wicked XML fixer: remove MAC pinning only, keep XML structure intact.
        """
        content = config.content
        fixes_applied: List[str] = []

        if self.fix_level not in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
            return FixResult(config=config, new_content=content, applied_fixes=[])

        new_content = content
        patterns = [
            (r"(?is)<\s*mac-address\s*>[^<]+<\s*/\s*mac-address\s*>", "wicked-mac-address"),
            (r"(?is)<\s*match\s*>.*?<\s*mac-address\s*>.*?</\s*mac-address\s*>.*?</\s*match\s*>", "wicked-match-mac"),
        ]
        for pat, tag in patterns:
            if re.search(pat, new_content):
                new_content = re.sub(pat, "<!-- removed by vmdk2kvm -->", new_content)
                fixes_applied.append(f"removed-mac-pinning-{tag}")

        return FixResult(config=config, new_content=new_content, applied_fixes=fixes_applied)

    def validate_fix(self, original: str, fixed: str, config_type: NetworkConfigType) -> List[str]:
        errors: List[str] = []

        if not fixed.strip():
            errors.append("Empty configuration after fix")

        if config_type == NetworkConfigType.NETPLAN and YAML_AVAILABLE:
            try:
                obj = yaml.safe_load(fixed)
                if obj is None:
                    errors.append("Netplan YAML became empty")
            except Exception as e:
                errors.append(f"Invalid YAML: {e}")

        essential_keywords = {
            NetworkConfigType.IFCONFIG_RH: ["DEVICE", "ONBOOT"],
            NetworkConfigType.WICKED_IFCFG: ["DEVICE", "ONBOOT"],
            NetworkConfigType.INTERFACES: ["iface"],
            NetworkConfigType.SYSTEMD_NETWORK: ["[Network]"],
            NetworkConfigType.SYSTEMD_NETDEV: ["[NetDev]"],
            NetworkConfigType.NETWORK_MANAGER: ["[connection]"],
        }
        if config_type in essential_keywords:
            for keyword in essential_keywords[config_type]:
                if keyword in original and keyword not in fixed:
                    errors.append(f"Missing essential keyword: {keyword}")

        return errors

    def apply_fix(self, g: guestfs.GuestFS, config: NetworkConfig, result: FixResult) -> bool:
        if result.new_content == config.content and not result.applied_fixes:
            return False

        validation_errors = self.validate_fix(config.content, result.new_content, config.type)
        if validation_errors:
            self.logger.warning("Validation errors for %s: %s", config.path, validation_errors)
            result.validation_errors.extend(validation_errors)
            return False

        backup_path = self.create_backup(g, config.path, config.content)

        if self.dry_run:
            self.logger.info("🧪 DRY-RUN: would update %s with fixes: %s", config.path, result.applied_fixes)
            config.modified = True
            config.backup_path = backup_path
            config.fixes_applied.extend(result.applied_fixes)
            return True

        try:
            prefer_mode = None
            if config.type == NetworkConfigType.NETWORK_MANAGER:
                prefer_mode = 0o600
            elif config.type in (NetworkConfigType.NETPLAN, NetworkConfigType.SYSTEMD_NETWORK, NetworkConfigType.SYSTEMD_NETDEV):
                prefer_mode = 0o644

            self._write_with_mode(g, config.path, result.new_content, prefer_mode=prefer_mode)

            self.logger.info("✅ Updated %s with fixes: %s", config.path, result.applied_fixes)
            config.modified = True
            config.backup_path = backup_path
            config.fixes_applied.extend(result.applied_fixes)
            return True

        except Exception as e:
            self.logger.error("Failed to write %s: %s", config.path, e)

            if backup_path and g.is_file(backup_path):
                try:
                    backup_content = g.read_file(backup_path)
                    g.write(config.path, backup_content)
                    self.logger.info("↩️ Restored %s from backup", config.path)
                except Exception as restore_error:
                    self.logger.error("Failed to restore backup: %s", restore_error)

            return False

    def fix_network_config(
        self,
        g: guestfs.GuestFS,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, Any]:
        self.logger.info("🌐 Starting network fixes (level=%s dry_run=%s)", self.fix_level.value, self.dry_run)

        configs = self.find_network_configs(g)
        self.logger.info("📄 Found %d network config file(s)", len(configs))

        topo = self.build_topology(configs)
        rename_map = self.compute_rename_map(topo)
        if rename_map:
            self.logger.info("🧷 Aggressive rename map: %s", rename_map)

        stats: Dict[str, Any] = {
            "total_files": len(configs),
            "files_modified": 0,
            "files_skipped": 0,
            "files_failed": 0,
            "total_fixes_applied": 0,
            "by_type": {},
            "details": [],
            "backups_created": 0,
            "dry_run": self.dry_run,
            "warnings": list(topo.warnings),
            "topology": topo.summarize(),
            "rename_map": rename_map,
        }

        fixer_map = {
            NetworkConfigType.IFCONFIG_RH: "ifcfg",
            NetworkConfigType.WICKED_IFCFG: "ifcfg",
            NetworkConfigType.NETPLAN: "netplan",
            NetworkConfigType.INTERFACES: "interfaces",
            NetworkConfigType.SYSTEMD_NETWORK: "systemd",
            NetworkConfigType.SYSTEMD_NETDEV: "systemd",
            NetworkConfigType.NETWORK_MANAGER: "nm",
            NetworkConfigType.WICKED: "wicked",
        }

        for i, config in enumerate(configs):
            if progress_callback:
                progress_callback(i, len(configs), f"Processing {config.path}")

            self.logger.debug("🔎 Processing %s (%s)", config.path, config.type.value)

            kind = fixer_map.get(config.type)
            if not kind:
                self.logger.warning("No fixer for %s; skipping %s", config.type.value, config.path)
                stats["files_skipped"] += 1
                continue

            try:
                if kind == "ifcfg":
                    result = self.fix_ifcfg_rh(config, topo=topo, rename_map=rename_map)
                elif kind == "netplan":
                    result = self.fix_netplan(config, topo=topo, rename_map=rename_map)
                elif kind == "interfaces":
                    result = self.fix_interfaces(config)
                elif kind == "systemd":
                    result = self.fix_systemd_network(config, rename_map=rename_map)
                elif kind == "nm":
                    result = self.fix_network_manager(config, rename_map=rename_map)
                elif kind == "wicked":
                    result = self.fix_wicked_xml(config)
                else:
                    stats["files_skipped"] += 1
                    continue

                success = False
                if result.applied_fixes:
                    success = self.apply_fix(g, config, result)
                elif result.validation_errors:
                    self.logger.warning("Validation errors for %s: %s", config.path, result.validation_errors)

                if result.warnings:
                    stats["warnings"].extend(
                        [f"{config.path}: {w}" if not w.startswith(config.path) else w for w in result.warnings]
                    )

                cts = config.type.value
                stats["by_type"].setdefault(cts, {"total": 0, "modified": 0, "fixes": 0})
                stats["by_type"][cts]["total"] += 1

                if result.applied_fixes:
                    if success:
                        stats["files_modified"] += 1
                        stats["by_type"][cts]["modified"] += 1
                        stats["total_fixes_applied"] += len(result.applied_fixes)
                        stats["by_type"][cts]["fixes"] += len(result.applied_fixes)
                        if config.backup_path:
                            stats["backups_created"] += 1
                    else:
                        stats["files_failed"] += 1

                stats["details"].append(
                    {
                        "path": config.path,
                        "type": config.type.value,
                        "modified": config.modified,
                        "fixes_applied": result.applied_fixes,
                        "validation_errors": result.validation_errors,
                        "warnings": result.warnings,
                        "backup": config.backup_path,
                        "original_hash": config.original_hash,
                        "new_hash": self.calculate_hash(result.new_content) if config.modified else config.original_hash,
                    }
                )

            except Exception as e:
                self.logger.error("Error fixing %s: %s", config.path, e)
                stats["files_failed"] += 1
                stats["details"].append({"path": config.path, "type": config.type.value, "modified": False, "error": str(e)})

        summary = {
            "fix_level": self.fix_level.value,
            "stats": stats,
            "recommendations": self.generate_recommendations(stats),
        }

        self.logger.info("🎉 Network fix complete: %d file(s) modified, %d fix(es) applied",
                         stats["files_modified"], stats["total_fixes_applied"])
        return summary

    def generate_recommendations(self, stats: Dict[str, Any]) -> List[str]:
        recommendations: List[str] = []

        if stats.get("dry_run"):
            recommendations.append("Dry-run enabled: no files were written. Review details and rerun with dry_run=False.")

        if stats.get("rename_map"):
            recommendations.append(
                "Aggressive interface renaming was computed. Ensure your libvirt domain XML uses virtio-net and "
                "verify the guest sees the expected interface name(s) after boot."
            )

        if stats["files_modified"] > 0:
            recommendations.append(
                f"Modified {stats['files_modified']} network configuration files. Review changes and test after boot."
            )
            if stats["total_fixes_applied"] > 0:
                recommendations.append(
                    f"Applied {stats['total_fixes_applied']} fixes (MAC pinning removal, VMware token cleanup, topology-aware DHCP, rename propagation)."
                )
            if stats["backups_created"] > 0:
                recommendations.append(
                    f"Created {stats['backups_created']} backup files with suffix '{self.backup_suffix}'."
                )

        if stats["files_failed"] > 0:
            recommendations.append(f"Failed to process {stats['files_failed']} files. Manual network config may be required.")

        topo = stats.get("topology") or {}
        if topo.get("warnings"):
            recommendations.append("Topology warnings detected. Review 'stats.warnings' and confirm bond/bridge/vlan intent.")

        if "ifcfg-rh" in stats["by_type"] or "wicked-ifcfg" in stats["by_type"]:
            recommendations.append("ifcfg-based system detected. After boot, restart network service (or reboot).")

        if "netplan" in stats["by_type"]:
            recommendations.append("Netplan detected. After boot, run 'netplan apply' (or reboot).")

        if "systemd-network" in stats["by_type"]:
            recommendations.append("systemd-networkd detected. After boot, restart systemd-networkd (or reboot).")

        if "network-manager" in stats["by_type"]:
            recommendations.append("NetworkManager profiles detected. After boot, toggle networking or reboot.")

        if stats["total_fixes_applied"] == 0 and stats["files_modified"] == 0:
            recommendations.append("No network configuration changes were needed. The existing config looks KVM-safe.")

        return recommendations


# -----------------------------------------------------------------------------
# Optional compatibility wrapper (for project style)
# -----------------------------------------------------------------------------

def fix_network_config(self, g: guestfs.GuestFS) -> Dict[str, Any]:
    """
    Compatibility entrypoint: call NetworkFixer directly.

    NOTE: no 'from .network_fixer import ...' here (that would self-import).
    """
    fix_level_str = getattr(self, "network_fix_level", "moderate")
    try:
        fix_level = FixLevel(fix_level_str)
    except Exception:
        fix_level = FixLevel.MODERATE

    fixer = NetworkFixer(
        logger=getattr(self, "logger", logging.getLogger(__name__)),
        fix_level=fix_level,
        dry_run=bool(getattr(self, "dry_run", False)),
    )

    result = fixer.fix_network_config(g, progress_callback=None)

    if hasattr(self, "report"):
        self.report.setdefault("network", {})
        self.report["network"] = result

    updated_files = [d["path"] for d in result["stats"]["details"] if d.get("modified", False)]
    return {"updated_files": updated_files, "count": len(updated_files), "analysis": result}
