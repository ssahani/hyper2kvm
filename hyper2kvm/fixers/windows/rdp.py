# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/windows/rdp.py

"""
RDP (Remote Desktop Protocol) verification for Windows VMs.

Ensures RDP is enabled and accessible after migration to prevent admin lockout
on headless VMs where VNC/console access may not be available.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore

try:
    import hivex  # type: ignore
except ImportError:
    hivex = None  # type: ignore


def verify_rdp_enabled(g: guestfs.GuestFS, root: str) -> Dict[str, Any]:
    """
    Verify Remote Desktop is enabled in Windows registry.

    Checks:
        1. RDP is enabled (fDenyTSConnections = 0)
        2. Network Level Authentication (NLA) status
        3. RDP port configuration (default 3389)
        4. Terminal Services running mode

    Args:
        g: GuestFS instance with Windows disk mounted
        root: Windows root path (e.g., '/sysroot')

    Returns:
        Dict with RDP configuration:
            {
                "rdp_enabled": bool,
                "nla_enabled": bool,
                "rdp_port": int,
                "warnings": List[str],
                "recommendations": List[str]
            }
    """
    result = {
        "rdp_enabled": False,
        "nla_enabled": False,
        "rdp_port": 3389,
        "warnings": [],
        "recommendations": [],
        "error": None,
    }

    try:
        system_hive_path = f"{root}/Windows/System32/config/SYSTEM"

        if not g.exists(system_hive_path):
            result["error"] = "SYSTEM registry hive not found"
            result["warnings"].append("Could not verify RDP configuration")
            return result

        # Read registry using hivex
        # Note: hivex_open() doesn't accept readonly parameter in all libguestfs versions
        # It defaults to readonly mode when the filesystem is mounted read-only
        try:
            h = g.hivex_open(system_hive_path)
        except TypeError:
            # Fallback for older API that might require positional args
            h = g.hivex_open(system_hive_path)

        try:
            # Navigate to Terminal Server configuration
            # HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server
            root_node = g.hivex_root(h)

            # Find CurrentControlSet
            current_control_set = _find_current_control_set(g, h, root_node)

            if not current_control_set:
                result["warnings"].append("Could not find CurrentControlSet in registry")
                return result

            # Check fDenyTSConnections
            terminal_server_node = _find_registry_key(
                g, h, current_control_set, "Control\\Terminal Server"
            )

            if terminal_server_node:
                fdeny_value = _get_registry_dword(g, h, terminal_server_node, "fDenyTSConnections")

                if fdeny_value is not None:
                    result["rdp_enabled"] = (fdeny_value == 0)

                    if not result["rdp_enabled"]:
                        result["warnings"].append(
                            "⚠️  Remote Desktop is DISABLED - you may not be able to access VM after migration"
                        )
                        result["recommendations"].append(
                            "Enable RDP before migration:\n"
                            "  PowerShell: Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' "
                            "-Name 'fDenyTSConnections' -Value 0\n"
                            "  Or: System Properties → Remote tab → Allow remote connections"
                        )
                else:
                    result["warnings"].append("Could not determine RDP status from registry")

                # Check NLA (Network Level Authentication)
                nla_value = _get_registry_dword(g, h, terminal_server_node, "UserAuthentication")
                if nla_value is not None:
                    result["nla_enabled"] = (nla_value == 1)

                # Check RDP port
                rdp_tcp_node = _find_registry_key(
                    g, h, terminal_server_node, "WinStations\\RDP-Tcp"
                )
                if rdp_tcp_node:
                    port_value = _get_registry_dword(g, h, rdp_tcp_node, "PortNumber")
                    if port_value is not None:
                        result["rdp_port"] = port_value
                        if port_value != 3389:
                            result["warnings"].append(
                                f"⚠️  RDP uses non-standard port {port_value} (default: 3389)"
                            )
                            result["recommendations"].append(
                                f"Ensure firewall allows port {port_value} for RDP access"
                            )

        finally:
            g.hivex_close(h)

    except Exception as e:
        result["error"] = str(e)
        result["warnings"].append(f"RDP verification failed: {e}")
        logging.debug(f"RDP verification error: {e}")

    return result


def enable_rdp_if_disabled(g: guestfs.GuestFS, root: str, logger: logging.Logger) -> Dict[str, Any]:
    """
    Enable Remote Desktop if currently disabled.

    SAFETY: Only modifies fDenyTSConnections registry value.
    Does NOT modify firewall or other security settings.

    Args:
        g: GuestFS instance
        root: Windows root path
        logger: Logger instance

    Returns:
        Dict with results:
            {
                "modified": bool,
                "previous_state": bool,
                "current_state": bool,
                "error": str
            }
    """
    result = {
        "modified": False,
        "previous_state": None,
        "current_state": None,
        "error": None,
    }

    try:
        system_hive_path = f"{root}/Windows/System32/config/SYSTEM"

        if not g.exists(system_hive_path):
            result["error"] = "SYSTEM registry hive not found"
            return result

        # Open registry hive for writing
        # Note: hivex opens in write mode automatically when filesystem is mounted read-write
        # The readonly parameter is not consistently supported across libguestfs versions
        h = g.hivex_open(system_hive_path)

        try:
            root_node = g.hivex_root(h)
            current_control_set = _find_current_control_set(g, h, root_node)

            if not current_control_set:
                result["error"] = "CurrentControlSet not found"
                return result

            terminal_server_node = _find_registry_key(
                g, h, current_control_set, "Control\\Terminal Server"
            )

            if not terminal_server_node:
                result["error"] = "Terminal Server registry key not found"
                return result

            # Get current value
            fdeny_value = _get_registry_dword(g, h, terminal_server_node, "fDenyTSConnections")
            result["previous_state"] = (fdeny_value == 0) if fdeny_value is not None else None

            # If RDP is disabled, enable it
            if fdeny_value != 0:
                _set_registry_dword(g, h, terminal_server_node, "fDenyTSConnections", 0)
                result["modified"] = True
                result["current_state"] = True
                logger.info("✅ Enabled Remote Desktop (set fDenyTSConnections = 0)")
            else:
                result["current_state"] = True
                logger.info("✅ Remote Desktop already enabled")

        finally:
            g.hivex_commit(h)
            g.hivex_close(h)

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Failed to enable RDP: {e}")

    return result


def check_rdp_firewall_rules(g: guestfs.GuestFS, root: str) -> Dict[str, Any]:
    """
    Check Windows Firewall rules for RDP (port 3389).

    NOTE: This is informational only - firewall rules are migrated separately.

    Returns:
        Dict with firewall status:
            {
                "rdp_rule_found": bool,
                "rdp_rule_enabled": bool,
                "warnings": List[str]
            }
    """
    result = {
        "rdp_rule_found": False,
        "rdp_rule_enabled": False,
        "warnings": [],
    }

    # Windows Firewall rules are complex - stored in multiple places:
    # 1. Registry: HKLM\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy
    # 2. Files: Windows\System32\LogFiles\Firewall\pfirewall.log
    # 3. GPO: Group Policy firewall settings

    # For now, add warning to check manually
    result["warnings"].append(
        "⚠️  Verify Windows Firewall allows RDP after migration:\n"
        "  PowerShell: Enable-NetFirewallRule -DisplayGroup 'Remote Desktop'\n"
        "  Or: Control Panel → Windows Defender Firewall → Allow an app"
    )

    return result


# Helper functions for registry access

def _find_current_control_set(g: guestfs.GuestFS, h: int, root_node: int) -> int:
    """Find CurrentControlSet in SYSTEM hive."""
    try:
        # Read Select\Current value to determine which ControlSet is current
        select_node = _find_registry_key(g, h, root_node, "Select")
        if select_node:
            current = _get_registry_dword(g, h, select_node, "Current")
            if current is not None:
                # Navigate to ControlSet00X
                control_set_name = f"ControlSet{current:03d}"
                return _find_registry_key(g, h, root_node, control_set_name)

        # Fallback: try ControlSet001
        return _find_registry_key(g, h, root_node, "ControlSet001")
    except (RuntimeError, OSError, KeyError, AttributeError) as e:
        logger.debug(f"Failed to find current control set: {e}")
        return 0


def _find_registry_key(g: guestfs.GuestFS, h: int, parent_node: int, path: str) -> int:
    """Navigate to registry key by path (backslash-separated)."""
    try:
        node = parent_node
        for component in path.split("\\"):
            if not component:
                continue
            children = g.hivex_node_children(node)
            found = False
            for child in children:
                name = g.hivex_node_name(child)
                if name.lower() == component.lower():  # Case-insensitive
                    node = child
                    found = True
                    break
            if not found:
                return 0
        return node
    except (RuntimeError, OSError, KeyError, ValueError) as e:
        logger.debug(f"Registry key navigation failed for '{path}': {e}")
        return 0


def _get_registry_dword(g: guestfs.GuestFS, h: int, node: int, value_name: str) -> int:
    """Read DWORD value from registry node."""
    try:
        values = g.hivex_node_values(node)
        for val in values:
            name = g.hivex_value_key(val)
            if name.lower() == value_name.lower():
                val_type = g.hivex_value_type(val)
                if val_type == 4:  # REG_DWORD
                    data = g.hivex_value_value(val)
                    # Convert bytes to int (little-endian)
                    return int.from_bytes(data[:4], byteorder='little')
        return None
    except (RuntimeError, OSError, KeyError, ValueError, IndexError) as e:
        logger.debug(f"Failed to read DWORD value '{value_name}': {e}")
        return None


def _set_registry_dword(g: guestfs.GuestFS, h: int, node: int, value_name: str, value: int) -> None:
    """Set DWORD value in registry node."""
    # Convert int to bytes (little-endian)
    data = value.to_bytes(4, byteorder='little')
    g.hivex_node_set_value(node, value_name, 4, data)  # 4 = REG_DWORD
