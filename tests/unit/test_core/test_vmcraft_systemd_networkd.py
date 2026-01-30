# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Unit tests for VMCraft systemd-networkd management (Phase 2).

Tests the SystemdNetworkdManager class and network configuration management.
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
import pytest

from hyper2kvm.core.vmcraft.systemd_networkd import SystemdNetworkdManager


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    return logging.getLogger("test")


@pytest.fixture
def temp_guest_root(tmp_path):
    """Create a temporary guest root directory."""
    guest_root = tmp_path / "guest_root"
    guest_root.mkdir()
    return guest_root


@pytest.fixture
def networkd_mgr(mock_logger, temp_guest_root):
    """Create SystemdNetworkdManager instance."""
    return SystemdNetworkdManager(mock_logger, str(temp_guest_root))


# ==================================================================================
# Network File Creation Tests
# ==================================================================================

class TestNetworkFileCreation:
    """Test .network file creation."""

    def test_create_network_file_dhcp(self, networkd_mgr):
        """Test creating DHCP network configuration."""
        result = networkd_mgr.create_network_file(
            name="10-eth0",
            match={"Name": "eth0"},
            network={},
            dhcp="yes"
        )

        assert result["ok"] is True
        assert result["file"] == "10-eth0.network"
        assert "path" in result

        # Verify file was created
        network_file = Path(result["path"])
        assert network_file.exists()

        # Verify content
        content = network_file.read_text()
        assert "[Match]" in content
        assert "Name=eth0" in content
        assert "[Network]" in content
        assert "DHCP=yes" in content

    def test_create_network_file_static(self, networkd_mgr):
        """Test creating static IP configuration."""
        result = networkd_mgr.create_network_file(
            name="10-eth0",
            match={"Name": "eth0"},
            network={
                "Address": "192.168.1.100/24",
                "Gateway": "192.168.1.1",
                "DNS": "8.8.8.8"
            }
        )

        assert result["ok"] is True

        # Verify content
        network_file = Path(result["path"])
        content = network_file.read_text()
        assert "Address=192.168.1.100/24" in content
        assert "Gateway=192.168.1.1" in content
        assert "DNS=8.8.8.8" in content

    def test_create_network_file_multiple_dns(self, networkd_mgr):
        """Test creating configuration with multiple DNS servers."""
        result = networkd_mgr.create_network_file(
            name="10-eth0",
            match={"Name": "eth0"},
            network={
                "Address": "192.168.1.100/24",
                "Gateway": "192.168.1.1",
                "DNS": ["8.8.8.8", "8.8.4.4"]
            }
        )

        assert result["ok"] is True

        content = Path(result["path"]).read_text()
        assert "DNS=8.8.8.8" in content
        assert "DNS=8.8.4.4" in content

    def test_create_network_file_auto_extension(self, networkd_mgr):
        """Test automatic .network extension."""
        result = networkd_mgr.create_network_file(
            name="10-eth0",  # No .network extension
            match={"Name": "eth0"},
            network={},
            dhcp="yes"
        )

        assert result["ok"] is True
        assert result["path"].endswith(".network")


# ==================================================================================
# Netdev File Creation Tests
# ==================================================================================

class TestNetdevFileCreation:
    """Test .netdev file creation for virtual devices."""

    def test_create_bridge_netdev(self, networkd_mgr):
        """Test creating bridge netdev."""
        result = networkd_mgr.create_netdev_file(
            name="br0",
            kind="bridge",
            netdev_config={"STP": "yes"}
        )

        assert result["ok"] is True
        assert "path" in result

        # Verify content
        content = Path(result["path"]).read_text()
        assert "[NetDev]" in content
        assert "Name=br0" in content
        assert "Kind=bridge" in content
        assert "[Bridge]" in content
        assert "STP=yes" in content

    def test_create_bond_netdev(self, networkd_mgr):
        """Test creating bond netdev."""
        result = networkd_mgr.create_netdev_file(
            name="bond0",
            kind="bond",
            netdev_config={"Mode": "802.3ad"}
        )

        assert result["ok"] is True

        content = Path(result["path"]).read_text()
        assert "Kind=bond" in content
        assert "[Bond]" in content
        assert "Mode=802.3ad" in content

    def test_create_vlan_netdev(self, networkd_mgr):
        """Test creating VLAN netdev."""
        result = networkd_mgr.create_netdev_file(
            name="vlan100",
            kind="vlan",
            netdev_config={"Id": "100"}
        )

        assert result["ok"] is True

        content = Path(result["path"]).read_text()
        assert "Kind=vlan" in content
        assert "[VLAN]" in content
        assert "Id=100" in content


# ==================================================================================
# Link File Creation Tests
# ==================================================================================

class TestLinkFileCreation:
    """Test .link file creation."""

    def test_create_link_file(self, networkd_mgr):
        """Test creating link file for persistent naming."""
        result = networkd_mgr.create_link_file(
            name="10-persistent-net",
            match={"MACAddress": "00:11:22:33:44:55"},
            link={"Name": "eth0"}
        )

        assert result["ok"] is True

        content = Path(result["path"]).read_text()
        assert "[Match]" in content
        assert "MACAddress=00:11:22:33:44:55" in content
        assert "[Link]" in content
        assert "Name=eth0" in content


# ==================================================================================
# File Management Tests
# ==================================================================================

class TestFileManagement:
    """Test network file management operations."""

    def test_remove_network_file(self, networkd_mgr):
        """Test removing network file."""
        # Create a file first
        create_result = networkd_mgr.create_network_file(
            name="10-eth0",
            match={"Name": "eth0"},
            network={},
            dhcp="yes"
        )
        assert create_result["ok"] is True

        # Remove it
        remove_result = networkd_mgr.remove_network_file("10-eth0")
        assert remove_result["ok"] is True

        # Verify it's gone
        assert not Path(create_result["path"]).exists()

    def test_remove_nonexistent_file(self, networkd_mgr):
        """Test removing non-existent file."""
        result = networkd_mgr.remove_network_file("nonexistent")
        assert result["ok"] is False
        assert result["error"] == "file_not_found"

    def test_list_network_files(self, networkd_mgr):
        """Test listing network files."""
        # Create multiple files
        networkd_mgr.create_network_file("10-eth0", {"Name": "eth0"}, {}, dhcp="yes")
        networkd_mgr.create_netdev_file("br0", "bridge", {})
        networkd_mgr.create_link_file("10-link", {"MACAddress": "00:11:22:33:44:55"}, {"Name": "eth0"})

        files = networkd_mgr.list_network_files()

        assert len(files) == 3
        assert any(f["type"] == "network" for f in files)
        assert any(f["type"] == "netdev" for f in files)
        assert any(f["type"] == "link" for f in files)

    def test_list_network_files_empty(self, networkd_mgr):
        """Test listing when no files exist."""
        files = networkd_mgr.list_network_files()
        assert files == []

    def test_parse_network_file(self, networkd_mgr):
        """Test parsing existing network file."""
        # Create a file
        networkd_mgr.create_network_file(
            name="10-eth0",
            match={"Name": "eth0", "MACAddress": "00:11:22:33:44:55"},
            network={"Address": "192.168.1.100/24", "Gateway": "192.168.1.1"}
        )

        # Parse it
        result = networkd_mgr.parse_network_file("10-eth0")

        assert result["ok"] is True
        assert "sections" in result
        assert "Match" in result["sections"]
        assert "Network" in result["sections"]
        assert result["sections"]["Match"]["Name"] == "eth0"
        assert result["sections"]["Network"]["Address"] == "192.168.1.100/24"

    def test_parse_nonexistent_file(self, networkd_mgr):
        """Test parsing non-existent file."""
        result = networkd_mgr.parse_network_file("nonexistent")
        assert result["ok"] is False
        assert result["error"] == "file_not_found"


# ==================================================================================
# Migration Tests
# ==================================================================================

class TestIfcfgMigration:
    """Test migration from ifcfg files."""

    def test_migrate_from_ifcfg_dhcp(self, networkd_mgr):
        """Test migrating DHCP ifcfg configuration."""
        # Create ifcfg file
        sysconfig_dir = networkd_mgr.sysconfig_dir
        sysconfig_dir.mkdir(parents=True, exist_ok=True)

        ifcfg_content = """DEVICE=eth0
BOOTPROTO=dhcp
ONBOOT=yes
"""
        ifcfg_file = sysconfig_dir / "ifcfg-eth0"
        ifcfg_file.write_text(ifcfg_content)

        # Migrate
        result = networkd_mgr.migrate_from_ifcfg("eth0")

        assert result["ok"] is True
        assert result["interface"] == "eth0"
        assert "networkd_file" in result

        # Verify networkd file was created
        networkd_file = Path(result["networkd_file"])
        assert networkd_file.exists()

        content = networkd_file.read_text()
        assert "DHCP=yes" in content

    def test_migrate_from_ifcfg_static(self, networkd_mgr):
        """Test migrating static IP ifcfg configuration."""
        # Create ifcfg file
        sysconfig_dir = networkd_mgr.sysconfig_dir
        sysconfig_dir.mkdir(parents=True, exist_ok=True)

        ifcfg_content = """DEVICE=eth0
BOOTPROTO=none
IPADDR=192.168.1.100
PREFIX=24
GATEWAY=192.168.1.1
DNS1=8.8.8.8
ONBOOT=yes
"""
        ifcfg_file = sysconfig_dir / "ifcfg-eth0"
        ifcfg_file.write_text(ifcfg_content)

        # Migrate
        result = networkd_mgr.migrate_from_ifcfg("eth0")

        assert result["ok"] is True

        content = Path(result["networkd_file"]).read_text()
        assert "Address=192.168.1.100/24" in content
        assert "Gateway=192.168.1.1" in content
        assert "DNS=8.8.8.8" in content

    def test_migrate_from_ifcfg_not_found(self, networkd_mgr):
        """Test migrating when ifcfg file doesn't exist."""
        result = networkd_mgr.migrate_from_ifcfg("eth0")

        assert result["ok"] is False
        assert result["error"] == "ifcfg_not_found"

    def test_migrate_from_ifcfg_with_netmask(self, networkd_mgr):
        """Test migrating with netmask instead of PREFIX."""
        sysconfig_dir = networkd_mgr.sysconfig_dir
        sysconfig_dir.mkdir(parents=True, exist_ok=True)

        ifcfg_content = """DEVICE=eth0
BOOTPROTO=static
IPADDR=192.168.1.100
NETMASK=255.255.255.0
GATEWAY=192.168.1.1
"""
        ifcfg_file = sysconfig_dir / "ifcfg-eth0"
        ifcfg_file.write_text(ifcfg_content)

        result = networkd_mgr.migrate_from_ifcfg("eth0")

        assert result["ok"] is True

        content = Path(result["networkd_file"]).read_text()
        # Should convert 255.255.255.0 to /24
        assert "Address=192.168.1.100/24" in content


class TestNetworkManagerMigration:
    """Test migration from NetworkManager."""

    def test_migrate_from_networkmanager(self, networkd_mgr):
        """Test migrating NetworkManager connections."""
        # Create NetworkManager connections directory with a connection
        nm_dir = networkd_mgr.guest_root / "etc/NetworkManager/system-connections"
        nm_dir.mkdir(parents=True, exist_ok=True)

        # Create a dummy connection file
        conn_file = nm_dir / "eth0.nmconnection"
        conn_file.write_text("[connection]\nid=eth0\n")

        result = networkd_mgr.migrate_from_networkmanager()

        assert result["ok"] is True
        assert result["count"] == 1
        assert "eth0" in result["migrated"]

    def test_migrate_from_networkmanager_not_found(self, networkd_mgr):
        """Test when NetworkManager connections don't exist."""
        result = networkd_mgr.migrate_from_networkmanager()

        assert result["ok"] is False
        assert result["error"] == "nm_connections_not_found"


# ==================================================================================
# Helper Method Tests
# ==================================================================================

class TestHelperMethods:
    """Test convenience helper methods."""

    def test_create_dhcp_network(self, networkd_mgr):
        """Test DHCP network helper."""
        result = networkd_mgr.create_dhcp_network("eth0")

        assert result["ok"] is True

        content = Path(result["path"]).read_text()
        assert "Name=eth0" in content
        assert "DHCP=yes" in content

    def test_create_static_network(self, networkd_mgr):
        """Test static network helper."""
        result = networkd_mgr.create_static_network(
            interface="eth0",
            address="192.168.1.100/24",
            gateway="192.168.1.1",
            dns=["8.8.8.8", "8.8.4.4"]
        )

        assert result["ok"] is True

        content = Path(result["path"]).read_text()
        assert "Address=192.168.1.100/24" in content
        assert "Gateway=192.168.1.1" in content
        assert "DNS=8.8.8.8" in content
        assert "DNS=8.8.4.4" in content

    def test_create_static_network_no_dns(self, networkd_mgr):
        """Test static network without DNS."""
        result = networkd_mgr.create_static_network(
            interface="eth0",
            address="192.168.1.100/24",
            gateway="192.168.1.1"
        )

        assert result["ok"] is True

        content = Path(result["path"]).read_text()
        assert "DNS" not in content

    def test_create_bridge_network(self, networkd_mgr):
        """Test bridge network creation."""
        result = networkd_mgr.create_bridge_network(
            bridge_name="br0",
            interfaces=["eth0", "eth1"]
        )

        assert result["ok"] is True
        assert result["bridge"] == "br0"
        assert len(result["files_created"]) == 4  # netdev + bridge network + 2 slave networks

        # Verify files exist
        for file_path in result["files_created"]:
            assert Path(file_path).exists()

    def test_enable_networkd(self, networkd_mgr):
        """Test enabling systemd-networkd."""
        result = networkd_mgr.enable_networkd()

        assert result["ok"] is True

        # Verify symlink was created
        symlink = (
            networkd_mgr.guest_root /
            "etc/systemd/system/multi-user.target.wants/systemd-networkd.service"
        )
        assert symlink.exists()


# ==================================================================================
# Utility Function Tests
# ==================================================================================

class TestUtilityFunctions:
    """Test internal utility functions."""

    def test_netmask_to_cidr(self, networkd_mgr):
        """Test netmask to CIDR conversion."""
        assert networkd_mgr._netmask_to_cidr("255.255.255.0") == 24
        assert networkd_mgr._netmask_to_cidr("255.255.0.0") == 16
        assert networkd_mgr._netmask_to_cidr("255.255.255.128") == 25
        assert networkd_mgr._netmask_to_cidr("255.0.0.0") == 8

    def test_netmask_to_cidr_invalid(self, networkd_mgr):
        """Test netmask to CIDR with invalid input."""
        # Should return default /24
        assert networkd_mgr._netmask_to_cidr("invalid") == 24


# ==================================================================================
# Integration Tests
# ==================================================================================

class TestIntegrationWorkflows:
    """Test complete migration workflows."""

    def test_full_rhel_migration_workflow(self, networkd_mgr):
        """Test complete RHEL migration workflow."""
        # Setup: Create RHEL-style ifcfg files
        sysconfig_dir = networkd_mgr.sysconfig_dir
        sysconfig_dir.mkdir(parents=True, exist_ok=True)

        ifcfg_content = """DEVICE=eth0
BOOTPROTO=static
IPADDR=192.168.1.100
PREFIX=24
GATEWAY=192.168.1.1
DNS1=8.8.8.8
DNS2=8.8.4.4
ONBOOT=yes
"""
        (sysconfig_dir / "ifcfg-eth0").write_text(ifcfg_content)

        # Migrate
        result = networkd_mgr.migrate_from_ifcfg("eth0")
        assert result["ok"] is True

        # Enable networkd
        enable_result = networkd_mgr.enable_networkd()
        assert enable_result["ok"] is True

        # Verify configuration
        parsed = networkd_mgr.parse_network_file("10-eth0")
        assert parsed["ok"] is True
        assert parsed["sections"]["Network"]["Address"] == "192.168.1.100/24"

    def test_bridge_for_kvm_workflow(self, networkd_mgr):
        """Test creating bridge for KVM networking."""
        # Create bridge
        result = networkd_mgr.create_bridge_network("br0", ["eth0"])
        assert result["ok"] is True

        # Verify bridge configuration
        files = networkd_mgr.list_network_files()
        assert len(files) == 3  # netdev + bridge network + eth0 slave

        # Parse bridge network file
        parsed = networkd_mgr.parse_network_file("10-br0")
        assert parsed["ok"] is True
        assert parsed["sections"]["Network"]["DHCP"] == "yes"
