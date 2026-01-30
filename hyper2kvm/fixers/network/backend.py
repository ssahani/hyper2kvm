# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/network/backend.py
"""
Backend-specific network configuration fixers for VMware -> KVM migration.

This module contains NetworkFixersBackend class with all backend-specific
fix methods for different network configuration formats:
- ifcfg (RHEL/CentOS/SUSE)
- netplan (Ubuntu/modern systems)
- /etc/network/interfaces (Debian)
- systemd-networkd
- NetworkManager
- Wicked (SUSE)
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ...config.config_loader import YAML_AVAILABLE, yaml
from .model import (
    DeviceKind,
    FixLevel,
    FixResult,
    IfcfgKV,
    NetworkConfig,
    TopoEdge,
    TopologyGraph,
    ifcfg_kind_and_links,
)


class NetworkFixersBackend:
    """
    Backend-specific network configuration fixers.

    This class contains all the per-backend fix methods for different
    network configuration formats found in Linux distributions.
    """

    def __init__(
        self,
        logger: logging.Logger,
        fix_level: FixLevel,
        vmware_drivers: dict[str, str],
        mac_pinning_patterns: list[tuple[str, str]],
    ):
        """
        Initialize the backend fixers.

        Args:
            logger: Logger instance for output
            fix_level: Fix aggressiveness level (CONSERVATIVE, MODERATE, AGGRESSIVE)
            vmware_drivers: Dictionary mapping VMware driver names to regex patterns
            mac_pinning_patterns: List of (regex, tag) tuples for MAC pinning detection
        """
        self.logger = logger
        self.fix_level = fix_level
        self.vmware_drivers = vmware_drivers
        self.mac_pinning_patterns = mac_pinning_patterns

    # Edge helpers (topology safety)

    def _edge_touches(self, e: TopoEdge, name: str) -> bool:
        """Check if an edge touches a given interface name."""
        return (e.src == name) or (e.dst == name)

    def _is_lower_layer_member_edge(self, e: TopoEdge, name: str) -> bool:
        """
        Check if edge indicates interface is a lower-layer member.

        Orientation-agnostic: if either side is the interface and kind indicates
        membership, treat it as "lower layer" (do not auto-add L3/DHCP).
        """
        return e.kind in ("slave", "port", "vlan") and self._edge_touches(e, name)

    def _is_lower_layer_member(self, name: str, edges: list[TopoEdge]) -> bool:
        """Check if interface is a lower-layer member (slave/port/vlan)."""
        return any(self._is_lower_layer_member_edge(e, name) for e in edges)

    # Compatibility helpers

    def _ifcfg_kind_and_links(self, ifcfg: IfcfgKV) -> Any:
        """
        Wrapper for ifcfg_kind_and_links() from network_model.

        Older code called self._ifcfg_kind_and_links(); real implementation is
        network_model.ifcfg_kind_and_links(). Keep wrapper for compatibility.
        """
        try:
            return ifcfg_kind_and_links(ifcfg)
        except Exception as e:
            self.logger.debug("Topology: ifcfg_kind_and_links parse failed: %s", e)
            return (DeviceKind.UNKNOWN, [])

    # Intent helpers

    def _ifcfg_has_static_intent(self, ifcfg: IfcfgKV) -> bool:
        """
        Check if ifcfg file has static IP configuration intent.

        Returns True if any static IP keys are present or BOOTPROTO=static.
        """
        static_keys = ["IPADDR", "IPADDR0", "PREFIX", "NETMASK", "GATEWAY", "DNS1", "DNS2", "IPV6ADDR", "IPV6_DEFAULTGW"]
        if any(ifcfg.has(k) for k in static_keys):
            return True
        bp = (ifcfg.get("BOOTPROTO") or "").strip().lower()
        return bp in ("static",)

    def _netplan_iface_has_static_intent(self, iface_cfg: dict[str, Any]) -> bool:
        """
        Check if netplan interface config has static IP configuration intent.

        Returns True if any static networking keys are present.
        """
        return any(k in iface_cfg for k in ("addresses", "gateway4", "gateway6", "routes", "routing-policy", "nameservers"))

    # Netplan helpers

    def _netplan_collect_member_refs(self, nw: dict[str, Any]) -> set[str]:
        """
        Collect all interface names that are members of bonds/bridges/vlans.

        Returns a set of interface names that should not have L3 config.
        """
        members: set[str] = set()

        bonds = nw.get("bonds")
        if isinstance(bonds, dict):
            for _bname, bcfg in bonds.items():
                if isinstance(bcfg, dict):
                    ifaces = bcfg.get("interfaces")
                    if isinstance(ifaces, list):
                        for x in ifaces:
                            if isinstance(x, str):
                                members.add(x)

        bridges = nw.get("bridges")
        if isinstance(bridges, dict):
            for _brname, brcfg in bridges.items():
                if isinstance(brcfg, dict):
                    ifaces = brcfg.get("interfaces")
                    if isinstance(ifaces, list):
                        for x in ifaces:
                            if isinstance(x, str):
                                members.add(x)

        vlans = nw.get("vlans")
        if isinstance(vlans, dict):
            for _vname, vcfg in vlans.items():
                if isinstance(vcfg, dict):
                    link = vcfg.get("link")
                    if isinstance(link, str) and link.strip():
                        members.add(link.strip())

        return members

    def _netplan_collect_setname_aliases(self, nw: dict[str, Any]) -> dict[str, str]:
        """
        Collect set-name aliases from netplan ethernet configs.

        Returns a dict mapping match-name -> set-name for renamed interfaces.
        """
        aliases: dict[str, str] = {}
        eths = nw.get("ethernets")
        if isinstance(eths, dict):
            for ifname, icfg in eths.items():
                if isinstance(icfg, dict):
                    sn = icfg.get("set-name")
                    if isinstance(sn, str) and sn.strip():
                        aliases[str(ifname)] = sn.strip()
        return aliases

    # Interfaces helper

    def _interfaces_block_has_address(self, block_lines: list[str]) -> bool:
        """
        Check if an interfaces(5) block has an address directive.

        Used to determine if 'inet static' is legitimate or should be DHCP.
        """
        for ln in block_lines:
            if re.match(r"^\s*address\s+\S+", ln):
                return True
        return False

    # Backend-specific fixers

    def fix_ifcfg_rh(
        self,
        config: NetworkConfig,
        *,
        topo: TopologyGraph | None = None,
        rename_map: dict[str, str] | None = None,
    ) -> FixResult:
        """
        Fix ifcfg files (RHEL-ish and SUSE-ish).

        Fixes applied:
        - Remove MAC pinning (MODERATE+)
        - Comment out VMware-ish driver tokens on DEVICE/TYPE lines (conservative too)
        - Remove VMware-ish params (comment out)
        - In AGGRESSIVE mode: rename DEVICE/NAME + propagate to PHYSDEV/MASTER/BRIDGE where applicable
        - DHCP normalization ONLY when safe:
            - no static intent
            - not a slave/port/vlan-member of bond/bridge/vlan
            - and BOOTPROTO is invalid/weird

        Args:
            config: NetworkConfig object to fix
            topo: Optional topology graph for context
            rename_map: Optional interface rename map (AGGRESSIVE mode)

        Returns:
            FixResult with new content and applied fixes
        """
        fixes_applied: list[str] = []
        warnings: list[str] = []
        ifcfg = IfcfgKV.parse(config.content)

        dev = (ifcfg.get("DEVICE") or "").strip()
        if not dev:
            return FixResult(config=config, new_content=config.content, applied_fixes=[], validation_errors=["Missing DEVICE="])

        kind, edges = self._ifcfg_kind_and_links(ifcfg)
        topo_kind = topo.infer_kind(dev) if topo else kind

        topo_edges: list[TopoEdge] = topo.edges if topo else []
        local_edges: list[TopoEdge] = list(edges) if edges else []

        # --- remove MAC pinning keys
        if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
            for k in ("HWADDR", "MACADDR", "MACADDRESS", "CLONED_MAC"):
                if ifcfg.has(k):
                    ifcfg.delete(k, "MAC pinning removed by hyper2kvm")
                    fixes_applied.append(f"removed-mac-pinning-{k.lower()}")

        # --- VMware driver token cleanup
        new_lines: list[str] = []
        for ln in ifcfg.lines:
            changed = False
            for driver_name, pattern in self.vmware_drivers.items():
                if re.search(pattern, ln, re.IGNORECASE):
                    if re.match(r"^\s*(DEVICE|TYPE|ETHTOOL_OPTS|OPTIONS|DRIVER)\s*=", ln, re.IGNORECASE):
                        if not ln.lstrip().startswith("#"):
                            new_lines.append(f"# {ln}  # VMware token removed by hyper2kvm")
                            fixes_applied.append(f"removed-vmware-driver-token-{driver_name}")
                            changed = True
                    break
            if changed:
                continue
            new_lines.append(ln)
        ifcfg.lines = new_lines

        # --- VMware-ish params
        vmware_params = ["VMWARE_", "VMXNET_", "SCSIDEVICE", "SUBCHANNELS"]
        new_lines2: list[str] = []
        for ln in ifcfg.lines:
            u = ln.upper()
            if any(p in u for p in vmware_params) and not ln.lstrip().startswith("#"):
                new_lines2.append(f"# {ln}  # VMware-specific parameter removed by hyper2kvm")
                for p in vmware_params:
                    if p in u:
                        fixes_applied.append(f"removed-vmware-param-{p.lower()}")
                continue
            new_lines2.append(ln)
        ifcfg.lines = new_lines2

        # --- Aggressive renaming (DEVICE/NAME + references)
        rm = rename_map or {}
        renamed = False
        if self.fix_level == FixLevel.AGGRESSIVE and rm:
            if dev in rm:
                new_dev = rm[dev]
                ifcfg.set("DEVICE", new_dev)
                fixes_applied.append("renamed-device")
                dev = new_dev
                renamed = True

            namev = (ifcfg.get("NAME") or "").strip().strip('"\'')
            if namev and namev in rm:
                ifcfg.set("NAME", rm[namev])
                fixes_applied.append("renamed-name")
                renamed = True

            phys = (ifcfg.get("PHYSDEV") or "").strip()
            if phys and phys in rm:
                ifcfg.set("PHYSDEV", rm[phys])
                fixes_applied.append("renamed-physdev")
                renamed = True

            master = (ifcfg.get("MASTER") or "").strip()
            if master and master in rm:
                ifcfg.set("MASTER", rm[master])
                fixes_applied.append("renamed-master-ref")
                renamed = True

            br = (ifcfg.get("BRIDGE") or "").strip()
            if br and br in rm:
                ifcfg.set("BRIDGE", rm[br])
                fixes_applied.append("renamed-bridge-ref")
                renamed = True

        # IMPORTANT: if we renamed identifiers, recompute edges/kind from the updated content
        if renamed:
            kind, edges = self._ifcfg_kind_and_links(ifcfg)
            topo_kind = topo.infer_kind(dev) if topo else kind
            local_edges = list(edges) if edges else []

        all_edges: list[TopoEdge] = topo_edges + local_edges

        # --- DHCP normalization (careful!)
        is_lower_member = self._is_lower_layer_member(dev, all_edges)
        bootproto = (ifcfg.get("BOOTPROTO") or "").strip().strip('"\'').lower()

        if bootproto and bootproto not in ("dhcp", "static", "none", "bootp"):
            if not self._ifcfg_has_static_intent(ifcfg) and not is_lower_member:
                ifcfg.set("BOOTPROTO", "dhcp")
                fixes_applied.append("normalized-bootproto->dhcp")
        elif bootproto == "none" and self.fix_level == FixLevel.AGGRESSIVE:
            if not self._ifcfg_has_static_intent(ifcfg) and not is_lower_member and topo_kind == DeviceKind.ETHERNET:
                ifcfg.set("BOOTPROTO", "dhcp")
                fixes_applied.append("normalized-bootproto-none->dhcp")

        # --- warn on risky layout: IP on a bridge port
        if kind == DeviceKind.ETHERNET and (ifcfg.has("BRIDGE") or any(e.kind == "port" for e in local_edges)):
            if self._ifcfg_has_static_intent(ifcfg):
                warnings.append(
                    f"{config.path}: IP/static config appears on a bridge port ({dev}). "
                    "Often the IP should live on the bridge device, not the port. Not auto-moving."
                )

        new_content = ifcfg.render()
        return FixResult(config=config, new_content=new_content, applied_fixes=fixes_applied, warnings=warnings)

    def fix_netplan(
        self,
        config: NetworkConfig,
        *,
        topo: TopologyGraph | None = None,
        rename_map: dict[str, str] | None = None,
    ) -> FixResult:
        """
        Fix netplan YAML configuration files.

        Fixes applied:
        - Remove MAC pinning (match.macaddress, macaddress, cloned-mac-address)
        - Remove VMware driver hints
        - Rename interface references (AGGRESSIVE mode)
        - Enable DHCP on interfaces without static config (AGGRESSIVE mode only, not for NetworkManager renderer)
        - Propagate renames through bonds/bridges/vlans

        Args:
            config: NetworkConfig object to fix
            topo: Optional topology graph for context
            rename_map: Optional interface rename map (AGGRESSIVE mode)

        Returns:
            FixResult with new content and applied fixes
        """
        if not YAML_AVAILABLE:
            return FixResult(
                config=config,
                new_content=config.content,
                applied_fixes=[],
                validation_errors=["YAML support not available"],
            )

        fixes_applied: list[str] = []
        warnings: list[str] = []
        rm = rename_map or {}

        try:
            data = yaml.safe_load(config.content) or {}
            if not isinstance(data, dict):
                return FixResult(config=config, new_content=config.content, applied_fixes=[], validation_errors=["Netplan YAML is not a dict"])

            nw = data.get("network")
            if not isinstance(nw, dict):
                return FixResult(config=config, new_content=config.content, applied_fixes=[], validation_errors=["Missing 'network:' section"])

            renderer = str(nw.get("renderer") or "").lower()

            # Conservative: only enable DHCP automatically in AGGRESSIVE mode,
            # and never when renderer=NetworkManager (netplan generates NM profiles).
            allow_auto_dhcp = (self.fix_level == FixLevel.AGGRESSIVE) and (renderer != "networkmanager")

            netplan_members = self._netplan_collect_member_refs(nw)
            setname_alias = self._netplan_collect_setname_aliases(nw)
            topo_edges: list[TopoEdge] = topo.edges if topo else []

            def is_member(name: str) -> bool:
                if name in netplan_members:
                    return True
                alias = setname_alias.get(name)
                if alias and alias in netplan_members:
                    return True
                for k, v in setname_alias.items():
                    if v == name and k in netplan_members:
                        return True
                return self._is_lower_layer_member(name, topo_edges)

            def scrub_mac(d: dict[str, Any], *, prefix: str) -> None:
                if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                    match_cfg = d.get("match")
                    if isinstance(match_cfg, dict) and "macaddress" in match_cfg:
                        del match_cfg["macaddress"]
                        fixes_applied.append(f"{prefix}-removed-match-mac")
                        if not match_cfg:
                            del d["match"]
                            fixes_applied.append(f"{prefix}-removed-empty-match")

                    for k in ("macaddress", "cloned-mac-address"):
                        if k in d:
                            del d[k]
                            fixes_applied.append(f"{prefix}-removed-{k}")

            def rename_list(lst: Any) -> Any:
                if not isinstance(lst, list):
                    return lst
                out: list[Any] = []
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

            def rename_ref(x: Any, tag: str) -> Any:
                if isinstance(x, str) and x in rm:
                    fixes_applied.append(tag)
                    return rm[x]
                return x

            eths = nw.get("ethernets")
            if isinstance(eths, dict):
                for ifname, icfg in list(eths.items()):
                    if not isinstance(icfg, dict):
                        continue
                    scrub_mac(icfg, prefix=f"eth-{ifname}")

                    if "driver" in icfg:
                        drv = str(icfg.get("driver") or "")
                        for vmware_driver in self.vmware_drivers:
                            if vmware_driver in drv.lower():
                                del icfg["driver"]
                                fixes_applied.append(f"eth-{ifname}-removed-vmware-driver-{vmware_driver}")
                                break

                    has_static = self._netplan_iface_has_static_intent(icfg)

                    set_name = icfg.get("set-name")
                    names_to_check = [str(ifname)]
                    if isinstance(set_name, str) and set_name.strip():
                        names_to_check.append(set_name.strip())

                    member = any(is_member(n) for n in names_to_check)

                    if allow_auto_dhcp and (not has_static) and ("dhcp4" not in icfg) and (not member):
                        icfg["dhcp4"] = True
                        fixes_applied.append(f"eth-{ifname}-enabled-dhcp4")

            bonds = nw.get("bonds")
            if isinstance(bonds, dict):
                for bname, bcfg in bonds.items():
                    if not isinstance(bcfg, dict):
                        continue
                    scrub_mac(bcfg, prefix=f"bond-{bname}")
                    if "interfaces" in bcfg:
                        bcfg["interfaces"] = rename_list(bcfg.get("interfaces"))

                    has_static = self._netplan_iface_has_static_intent(bcfg)
                    is_port = False
                    if topo is not None:
                        is_port = any(e.kind == "port" and (e.src == bname or e.dst == bname) for e in topo.edges)

                    if allow_auto_dhcp and (not has_static) and ("dhcp4" not in bcfg) and (not is_port):
                        bcfg["dhcp4"] = True
                        fixes_applied.append(f"bond-{bname}-enabled-dhcp4")

            bridges = nw.get("bridges")
            if isinstance(bridges, dict):
                for brname, brcfg in bridges.items():
                    if not isinstance(brcfg, dict):
                        continue
                    scrub_mac(brcfg, prefix=f"bridge-{brname}")
                    if "interfaces" in brcfg:
                        brcfg["interfaces"] = rename_list(brcfg.get("interfaces"))

                    has_static = self._netplan_iface_has_static_intent(brcfg)
                    if allow_auto_dhcp and (not has_static) and ("dhcp4" not in brcfg):
                        brcfg["dhcp4"] = True
                        fixes_applied.append(f"bridge-{brname}-enabled-dhcp4")

            vlans = nw.get("vlans")
            if isinstance(vlans, dict):
                for vname, vcfg in vlans.items():
                    if not isinstance(vcfg, dict):
                        continue
                    scrub_mac(vcfg, prefix=f"vlan-{vname}")
                    if "link" in vcfg:
                        vcfg["link"] = rename_ref(vcfg.get("link"), "netplan-renamed-vlan-link")

                    has_static = self._netplan_iface_has_static_intent(vcfg)
                    if allow_auto_dhcp and (not has_static) and ("dhcp4" not in vcfg):
                        vcfg["dhcp4"] = True
                        fixes_applied.append(f"vlan-{vname}-enabled-dhcp4")

            new_content = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)

            if renderer == "networkmanager" and any("enabled-dhcp4" in f for f in fixes_applied):
                warnings.append(f"{config.path}: renderer=NetworkManager detected; DHCP changes may be overridden by NM profiles.")

            return FixResult(config=config, new_content=new_content, applied_fixes=fixes_applied, warnings=warnings)

        except Exception as e:
            return FixResult(
                config=config,
                new_content=config.content,
                applied_fixes=[],
                validation_errors=[f"YAML parse error: {e}"],
            )

    def fix_interfaces(self, config: NetworkConfig) -> FixResult:
        """
        Fix /etc/network/interfaces (Debian-style) configuration.

        Fixes applied:
        - Remove VMware driver tokens
        - Remove hwaddress ether MAC pinning (MODERATE+)
        - Change 'inet static' to 'inet dhcp' when no address directive present (MODERATE+)

        Args:
            config: NetworkConfig object to fix

        Returns:
            FixResult with new content and applied fixes
        """
        content = config.content
        fixes_applied: list[str] = []
        warnings: list[str] = []

        lines = content.split("\n")
        new_lines: list[str] = []

        current_iface: str | None = None
        iface_block_lines: list[str] = []
        in_iface_block = False

        def flush_block() -> None:
            nonlocal iface_block_lines, current_iface, in_iface_block
            if not in_iface_block or not current_iface:
                iface_block_lines = []
                current_iface = None
                in_iface_block = False
                return

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

            if in_iface_block:
                for driver_name, pattern in self.vmware_drivers.items():
                    if re.search(pattern, line, re.IGNORECASE):
                        line = f"# {line}  # VMware token removed by hyper2kvm"
                        fixes_applied.append(f"removed-vmware-token-{driver_name}")
                        break

                if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                    if re.match(r"(?im)^\s*hwaddress\s+ether\s+.*$", line):
                        line = f"# {line}  # MAC pinning removed by hyper2kvm"
                        fixes_applied.append("removed-hwaddress")

                iface_block_lines.append(line)
            else:
                for driver_name, pattern in self.vmware_drivers.items():
                    if re.search(pattern, line, re.IGNORECASE):
                        line = f"# {line}  # VMware token removed by hyper2kvm"
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
        rename_map: dict[str, str] | None = None,
    ) -> FixResult:
        """
        Fix systemd-networkd .network files.

        Fixes applied:
        - Remove MACAddress matching (MODERATE+)
        - Rename interface names in [Match] Name= (AGGRESSIVE mode)
        - Remove VMware driver tokens
        - Normalize DHCP= values
        - Add DHCP=yes when no static config present (AGGRESSIVE mode)

        Args:
            config: NetworkConfig object to fix
            rename_map: Optional interface rename map (AGGRESSIVE mode)

        Returns:
            FixResult with new content and applied fixes
        """
        content = config.content
        fixes_applied: list[str] = []
        warnings: list[str] = []
        rm = rename_map or {}

        lines = content.split("\n")
        new_lines: list[str] = []

        sec = None
        saw_network_section = False
        in_network_section = False
        in_match_section = False
        saw_dhcp = False
        saw_static = False

        def is_static_key(ln: str) -> bool:
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
                        new_lines.append(f"# {line}  # MAC pinning removed by hyper2kvm")
                        fixes_applied.append("removed-mac-match")
                        continue

                if self.fix_level == FixLevel.AGGRESSIVE and rm:
                    m = re.match(r"^\s*Name\s*=\s*(.+)\s*$", line, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip()
                        parts = re.split(r"\s+", val)
                        changed = False
                        out_parts: list[str] = []
                        for p in parts:
                            if p in rm and not any(ch in p for ch in "*?[]"):
                                out_parts.append(rm[p])
                                changed = True
                            else:
                                out_parts.append(p)
                        if changed:
                            line = re.sub(
                                r"(?:^(\s*Name\s*=\s*)).*$",
                                r"\1" + " ".join(out_parts),
                                line,
                                flags=re.IGNORECASE,
                            )
                            fixes_applied.append("renamed-networkd-match-name")

            for driver_name, pattern in self.vmware_drivers.items():
                if re.search(pattern, line, re.IGNORECASE) and not line.lstrip().startswith("#"):
                    new_lines.append(f"# {line}  # VMware token removed by hyper2kvm")
                    fixes_applied.append(f"removed-vmware-token-{driver_name}")
                    break
            else:
                if in_network_section:
                    if re.match(r"^\s*DHCP\s*=", line, re.IGNORECASE):
                        saw_dhcp = True
                        if not re.search(r"(?i)=\s*(yes|true|ipv4|ipv6|both)\b", line):
                            line = "DHCP=yes"
                            fixes_applied.append("normalized-dhcp")
                    if is_static_key(line):
                        saw_static = True

                new_lines.append(line)

        if self.fix_level == FixLevel.AGGRESSIVE and saw_network_section and not saw_dhcp and not saw_static:
            out: list[str] = []
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
        rename_map: dict[str, str] | None = None,
    ) -> FixResult:
        """
        Fix NetworkManager connection profiles (.nmconnection).

        Fixes applied:
        - Remove MAC pinning (mac-address, cloned-mac-address, mac-address-blacklist)
        - Rename interface-name (AGGRESSIVE mode)
        - Rename VLAN parent (AGGRESSIVE mode)
        - Remove VMware driver hints

        Args:
            config: NetworkConfig object to fix
            rename_map: Optional interface rename map (AGGRESSIVE mode)

        Returns:
            FixResult with new content and applied fixes
        """
        content = config.content
        fixes_applied: list[str] = []
        warnings: list[str] = []
        rm = rename_map or {}

        lines = content.split("\n")
        new_lines: list[str] = []
        sec = None

        def has_vmware_token(val: str) -> bool:
            for _dn, pat in self.vmware_drivers.items():
                if re.search(pat, val, re.IGNORECASE):
                    return True
            return bool(re.search(r"(?i)\bvmware\b", val))

        for line in lines:
            s = line.strip()
            msec = re.match(r"^\s*\[(.+)\]\s*$", s)
            if msec:
                sec = msec.group(1).strip().lower()
                new_lines.append(line)
                continue

            if self.fix_level in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
                if re.match(r"^\s*(mac-address|cloned-mac-address|mac-address-blacklist)\s*=", line, re.IGNORECASE):
                    new_lines.append(f"# {line}  # MAC pinning removed by hyper2kvm")
                    fixes_applied.append("removed-nm-mac")
                    continue

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

            if re.match(r"^\s*driver\s*=", line, re.IGNORECASE) and not line.lstrip().startswith("#"):
                m = re.match(r"^\s*driver\s*=\s*(.+?)\s*$", line, re.IGNORECASE)
                if m and has_vmware_token(m.group(1)):
                    new_lines.append(f"# {line}  # VMware driver hint removed by hyper2kvm")
                    fixes_applied.append("removed-nm-driver-hint")
                    continue

            new_lines.append(line)

        new_content = "\n".join(new_lines)
        return FixResult(config=config, new_content=new_content, applied_fixes=fixes_applied, warnings=warnings)

    def fix_wicked_xml(self, config: NetworkConfig) -> FixResult:
        """
        Fix Wicked XML configuration files (SUSE).

        Fixes applied:
        - Remove <mac-address> tags (MODERATE+)
        - Remove <match><mac-address> tags (MODERATE+)

        Args:
            config: NetworkConfig object to fix

        Returns:
            FixResult with new content and applied fixes
        """
        content = config.content
        fixes_applied: list[str] = []

        if self.fix_level not in (FixLevel.MODERATE, FixLevel.AGGRESSIVE):
            return FixResult(config=config, new_content=content, applied_fixes=[])

        new_content = content
        patterns = [
            (r"(?is)<\s*mac-address\s*>[^<]+<\s*/\s*mac-address\s*>", "wicked-mac-address"),
            (r"(?is)<\s*match\s*>.*?<\s*mac-address\s*>.*?</\s*mac-address\s*>.*?</\s*match\s*>", "wicked-match-mac"),
        ]
        for pat, tag in patterns:
            if re.search(pat, new_content):
                new_content = re.sub(pat, "<!-- removed by hyper2kvm -->", new_content)
                fixes_applied.append(f"removed-mac-pinning-{tag}")

        return FixResult(config=config, new_content=new_content, applied_fixes=fixes_applied)


__all__ = ["NetworkFixersBackend"]
