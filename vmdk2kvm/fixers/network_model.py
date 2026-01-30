# SPDX-License-Identifier: LGPL-3.0-or-later
# vmdk2kvm/fixers/network_model.py
"""
Network model + topology helpers for VMware -> KVM network config fixing.

This file intentionally contains:
- Enums/dataclasses (NetworkConfig, FixResult, etc.)
- TopologyGraph (best-effort)
- IfcfgKV parser (loss-minimizing key=value editor)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------
# Enums / dataclasses
# ---------------------------

class NetworkConfigType(Enum):
    """Types of network configuration files."""
    IFCONFIG_RH = "ifcfg-rh"                 # RHEL-ish ifcfg files (also SUSE ifcfg works similarly)
    NETPLAN = "netplan"                     # Ubuntu netplan YAML
    INTERFACES = "interfaces"               # Debian interfaces
    SYSTEMD_NETWORK = "systemd-network"     # systemd-networkd .network
    SYSTEMD_NETDEV = "systemd-netdev"       # systemd-networkd .netdev
    NETWORK_MANAGER = "network-manager"     # NetworkManager profiles
    WICKED = "wicked"                       # SUSE wicked XML
    WICKED_IFCFG = "wicked-ifcfg"           # SUSE ifcfg files
    UNKNOWN = "unknown"


class FixLevel(Enum):
    """Level of fix aggressiveness."""
    CONSERVATIVE = "conservative"  # Minimal changes (VMware specifics only)
    MODERATE = "moderate"          # VMware + MAC pinning removal (recommended)
    AGGRESSIVE = "aggressive"      # Normalize naming + apply more "sane defaults"


@dataclass
class NetworkConfig:
    """Represents a network configuration file."""
    path: str
    content: str
    type: NetworkConfigType
    original_hash: str = ""
    modified: bool = False
    backup_path: str = ""
    error: Optional[str] = None
    fixes_applied: List[str] = field(default_factory=list)


@dataclass
class FixResult:
    """Result of fixing a network configuration."""
    config: NetworkConfig
    new_content: str
    applied_fixes: List[str]
    validation_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ---------------------------
# Topology model (best-effort)
# ---------------------------

class DeviceKind(Enum):
    ETHERNET = "ethernet"
    BOND = "bond"
    BRIDGE = "bridge"
    VLAN = "vlan"
    UNKNOWN = "unknown"


@dataclass
class TopoNode:
    name: str
    kind: DeviceKind
    sources: Set[str] = field(default_factory=set)  # config paths
    props: Dict[str, Any] = field(default_factory=dict)  # arbitrary parsed details


@dataclass
class TopoEdge:
    src: str
    dst: str
    kind: str  # "slave", "port", "vlan"


class TopologyGraph:
    """
    Minimal topology graph:
      - Nodes: devices (ethX / ens192 / bond0 / br0 / vlan100 or eth0.100)
      - Edges:
          ethernet -> bond   ("slave")
          ethernet -> bridge ("port")
          bond     -> bridge ("port")
          parent   -> vlan   ("vlan")
    """
    def __init__(self) -> None:
        self.nodes: Dict[str, TopoNode] = {}
        self.edges: List[TopoEdge] = []
        self.warnings: List[str] = []

    def add_node(self, name: str, kind: DeviceKind, *, source: Optional[str] = None, **props: Any) -> None:
        if not name:
            return
        n = self.nodes.get(name)
        if n is None:
            n = TopoNode(name=name, kind=kind)
            self.nodes[name] = n
        else:
            # Upgrade UNKNOWN -> known kind if new info arrives
            if n.kind == DeviceKind.UNKNOWN and kind != DeviceKind.UNKNOWN:
                n.kind = kind
        if source:
            n.sources.add(source)
        for k, v in props.items():
            n.props.setdefault(k, v)

    def add_edge(self, src: str, dst: str, kind: str) -> None:
        if not src or not dst:
            return
        self.edges.append(TopoEdge(src=src, dst=dst, kind=kind))

    def infer_kind(self, name: str) -> DeviceKind:
        if name in self.nodes:
            return self.nodes[name].kind
        # Heuristics
        if re.match(r"^bond\d+$", name):
            return DeviceKind.BOND
        if re.match(r"^(br|bridge)\d+$", name) or name.startswith("br"):
            return DeviceKind.BRIDGE
        if "." in name and re.match(r"^\w+\.\d+$", name):
            return DeviceKind.VLAN
        return DeviceKind.UNKNOWN

    def rename_map_propagate(self, rename_map: Dict[str, str]) -> Dict[str, str]:
        """
        Expand rename map across trivial VLAN names (eth0.100), if present.
        """
        out = dict(rename_map)
        for old, new in list(rename_map.items()):
            for n in list(self.nodes.keys()):
                if n.startswith(old + "."):
                    out[n] = n.replace(old + ".", new + ".", 1)
        return out

    def summarize(self) -> Dict[str, Any]:
        by_kind: Dict[str, List[str]] = {}
        for n in self.nodes.values():
            by_kind.setdefault(n.kind.value, []).append(n.name)
        for k in list(by_kind.keys()):
            by_kind[k] = sorted(set(by_kind[k]))
        edges = [{"src": e.src, "dst": e.dst, "kind": e.kind} for e in self.edges]
        return {"devices": by_kind, "edges": edges, "warnings": self.warnings}


# ---------------------------
# ifcfg parser (key=value preserving unknown lines/comments)
# ---------------------------

@dataclass
class IfcfgKV:
    """
    Simple ifcfg representation.
    - Preserves original lines order.
    - Parses KEY=VALUE (supports quoted values).
    - Allows rewriting keys while keeping comments/unknown lines intact.
    """
    lines: List[str]
    kv: Dict[str, str] = field(default_factory=dict)
    key_line_idx: Dict[str, int] = field(default_factory=dict)

    @staticmethod
    def parse(text: str) -> "IfcfgKV":
        lines = text.splitlines()
        kv: Dict[str, str] = {}
        idx: Dict[str, int] = {}

        for i, ln in enumerate(lines):
            m = re.match(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.*)\s*$", ln)
            if not m:
                continue
            key = m.group(1).strip()
            val = m.group(2).strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val2 = val[1:-1]
            else:
                val2 = val
            kv[key.upper()] = val2
            idx[key.upper()] = i

        return IfcfgKV(lines=lines, kv=kv, key_line_idx=idx)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.kv.get(key.upper(), default)

    def has(self, key: str) -> bool:
        return key.upper() in self.kv

    def set(self, key: str, value: str, *, quote: bool = False) -> None:
        k = key.upper()
        self.kv[k] = value
        out_val = f'"{value}"' if quote else value
        line = f"{k}={out_val}"

        if k in self.key_line_idx:
            self.lines[self.key_line_idx[k]] = line
        else:
            self.key_line_idx[k] = len(self.lines)
            self.lines.append(line)

    def comment_out(self, key: str, tag: str) -> bool:
        k = key.upper()
        if k not in self.key_line_idx:
            return False
        i = self.key_line_idx[k]
        ln = self.lines[i]
        if ln.lstrip().startswith("#"):
            return False
        self.lines[i] = f"# {ln}  # {tag}"
        return True

    def delete(self, key: str, tag: str) -> bool:
        # safer than removing
        return self.comment_out(key, tag)

    def render(self) -> str:
        # Keep a trailing newline for POSIX sanity
        out = "\n".join(self.lines)
        if not out.endswith("\n"):
            out += "\n"
        return out


def ifcfg_kind_and_links(ifcfg: IfcfgKV) -> Tuple[DeviceKind, List[TopoEdge]]:
    """
    Infer device kind and edges from an ifcfg file.
    """
    dev = (ifcfg.get("DEVICE") or "").strip()
    typ = (ifcfg.get("TYPE") or "").strip().lower()
    edges: List[TopoEdge] = []

    kind = DeviceKind.ETHERNET
    if ifcfg.get("BONDING_MASTER", "").lower() == "yes" or typ == "bond":
        kind = DeviceKind.BOND
    elif typ == "bridge" or dev.startswith("br"):
        kind = DeviceKind.BRIDGE
    elif ifcfg.get("VLAN", "").lower() == "yes" or "." in dev:
        kind = DeviceKind.VLAN

    if ifcfg.get("SLAVE", "").lower() == "yes" and ifcfg.has("MASTER"):
        master = (ifcfg.get("MASTER") or "").strip()
        if dev and master:
            edges.append(TopoEdge(src=dev, dst=master, kind="slave"))

    if ifcfg.has("BRIDGE"):
        br = (ifcfg.get("BRIDGE") or "").strip()
        if dev and br:
            edges.append(TopoEdge(src=dev, dst=br, kind="port"))

    phys = (ifcfg.get("PHYSDEV") or "").strip()
    if kind == DeviceKind.VLAN:
        if phys:
            edges.append(TopoEdge(src=phys, dst=dev, kind="vlan"))
        elif "." in dev:
            parent = dev.split(".", 1)[0]
            edges.append(TopoEdge(src=parent, dst=dev, kind="vlan"))

    return kind, edges
