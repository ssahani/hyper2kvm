# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Tests for network configuration injection.
"""
import importlib

import pytest
from fakes.fake_guestfs import FakeGuestFS
from fakes.fake_logger import FakeLogger


@pytest.fixture
def network_injector_module():
    """Import network_config_injector module"""
    try:
        return importlib.import_module("hyper2kvm.fixers.network_config_injector")
    except Exception as e:
        pytest.skip(f"Cannot import network_config_injector: {e}")


class TestNetworkConfigInjector:
    """Test suite for network configuration injection"""

    def test_inject_no_config(self, network_injector_module):
        """Test that injection is skipped when no config provided"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()

        result = network_injector_module.inject_network_config(obj, g)

        assert result["injected"] is False
        assert result["reason"] == "no_config"

    def test_inject_invalid_config_type(self, network_injector_module):
        """Test that invalid config type is handled"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.network_config_inject = "not_a_dict"

        result = network_injector_module.inject_network_config(obj, g)

        assert result["injected"] is False
        assert result["reason"] == "invalid_config"

    def test_inject_no_files(self, network_injector_module):
        """Test that config with no files is handled"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.network_config_inject = {}

        result = network_injector_module.inject_network_config(obj, g)

        assert result["injected"] is False
        assert result["reason"] == "no_files"

    def test_inject_systemd_network_file(self, network_injector_module):
        """Test injection of systemd-networkd .network file"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.network_config_inject = {
            "network_files": [
                {
                    "name": "eth0",
                    "type": "network",
                    "priority": 10,
                    "content": "[Match]\nName=eth0\n\n[Network]\nAddress=192.168.1.100/24\n"
                }
            ]
        }

        result = network_injector_module.inject_network_config(obj, g)

        assert result["injected"] is True
        assert result["dry_run"] is False
        assert len(result["files_created"]) == 1
        assert result["files_created"][0]["path"] == "/etc/systemd/network/10-eth0.network"
        assert result["files_created"][0]["type"] == "network"

    def test_inject_systemd_netdev_file(self, network_injector_module):
        """Test injection of systemd-networkd .netdev file"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.network_config_inject = {
            "network_files": [
                {
                    "name": "br0",
                    "type": "netdev",
                    "priority": 10,
                    "content": "[NetDev]\nName=br0\nKind=bridge\n"
                }
            ]
        }

        result = network_injector_module.inject_network_config(obj, g)

        assert result["injected"] is True
        assert len(result["files_created"]) == 1
        assert result["files_created"][0]["path"] == "/etc/systemd/network/10-br0.netdev"
        assert result["files_created"][0]["type"] == "netdev"

    def test_inject_multiple_network_files(self, network_injector_module):
        """Test injection of multiple systemd-networkd files"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.network_config_inject = {
            "network_files": [
                {
                    "name": "eth0",
                    "type": "network",
                    "priority": 10,
                    "content": "[Match]\nName=eth0\n"
                },
                {
                    "name": "eth1",
                    "type": "network",
                    "priority": 20,
                    "content": "[Match]\nName=eth1\n"
                }
            ]
        }

        result = network_injector_module.inject_network_config(obj, g)

        assert result["injected"] is True
        assert len(result["files_created"]) == 2
        assert any("eth0" in f["path"] for f in result["files_created"])
        assert any("eth1" in f["path"] for f in result["files_created"])

    def test_inject_nm_connection(self, network_injector_module):
        """Test injection of NetworkManager connection"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.network_config_inject = {
            "nm_connections": [
                {
                    "name": "eth0",
                    "content": "[connection]\nid=eth0\ntype=ethernet\n"
                }
            ]
        }

        result = network_injector_module.inject_network_config(obj, g)

        assert result["injected"] is True
        assert len(result["files_created"]) == 1
        assert result["files_created"][0]["path"] == "/etc/NetworkManager/system-connections/eth0.nmconnection"
        assert result["files_created"][0]["type"] == "nmconnection"

    def test_inject_multiple_nm_connections(self, network_injector_module):
        """Test injection of multiple NetworkManager connections"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.network_config_inject = {
            "nm_connections": [
                {
                    "name": "Management",
                    "content": "[connection]\nid=Management\n"
                },
                {
                    "name": "Storage",
                    "content": "[connection]\nid=Storage\n"
                }
            ]
        }

        result = network_injector_module.inject_network_config(obj, g)

        assert result["injected"] is True
        assert len(result["files_created"]) == 2

    def test_inject_hybrid_config(self, network_injector_module):
        """Test injection of both systemd-networkd and NetworkManager files"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.network_config_inject = {
            "network_files": [
                {
                    "name": "br0",
                    "type": "netdev",
                    "priority": 10,
                    "content": "[NetDev]\nName=br0\n"
                }
            ],
            "nm_connections": [
                {
                    "name": "eth0",
                    "content": "[connection]\nid=eth0\n"
                }
            ]
        }

        result = network_injector_module.inject_network_config(obj, g)

        assert result["injected"] is True
        assert len(result["files_created"]) == 2
        assert any(f["type"] == "netdev" for f in result["files_created"])
        assert any(f["type"] == "nmconnection" for f in result["files_created"])

    def test_inject_dry_run(self, network_injector_module):
        """Test dry-run mode"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = True
        obj.network_config_inject = {
            "network_files": [
                {
                    "name": "eth0",
                    "type": "network",
                    "priority": 10,
                    "content": "[Match]\nName=eth0\n"
                }
            ]
        }

        result = network_injector_module.inject_network_config(obj, g)

        assert result["injected"] is True
        assert result["dry_run"] is True
        assert len(result["files_created"]) > 0
        assert all("bytes" in f for f in result["files_created"])

    def test_inject_skip_empty_name(self, network_injector_module):
        """Test that files without names are skipped"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.network_config_inject = {
            "network_files": [
                {
                    # Missing name
                    "type": "network",
                    "content": "[Match]\nName=eth0\n"
                },
                {
                    "name": "eth1",
                    "type": "network",
                    "content": "[Match]\nName=eth1\n"
                }
            ]
        }

        result = network_injector_module.inject_network_config(obj, g)

        assert result["injected"] is True
        assert len(result["files_created"]) == 1
        assert "eth1" in result["files_created"][0]["path"]

    def test_inject_skip_empty_content(self, network_injector_module):
        """Test that files without content are skipped"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.network_config_inject = {
            "network_files": [
                {
                    "name": "eth0",
                    "type": "network",
                    # Missing content
                },
                {
                    "name": "eth1",
                    "type": "network",
                    "content": "[Match]\nName=eth1\n"
                }
            ]
        }

        result = network_injector_module.inject_network_config(obj, g)

        assert result["injected"] is True
        assert len(result["files_created"]) == 1
        assert "eth1" in result["files_created"][0]["path"]

    def test_inject_skip_invalid_type(self, network_injector_module):
        """Test that files with invalid type are skipped"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.network_config_inject = {
            "network_files": [
                {
                    "name": "eth0",
                    "type": "invalid",
                    "content": "[Match]\nName=eth0\n"
                },
                {
                    "name": "eth1",
                    "type": "network",
                    "content": "[Match]\nName=eth1\n"
                }
            ]
        }

        result = network_injector_module.inject_network_config(obj, g)

        assert result["injected"] is True
        assert len(result["files_created"]) == 1
        assert "eth1" in result["files_created"][0]["path"]

    def test_priority_in_filename(self, network_injector_module):
        """Test that priority is correctly included in filename"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.network_config_inject = {
            "network_files": [
                {
                    "name": "eth0",
                    "type": "network",
                    "priority": 5,
                    "content": "[Match]\nName=eth0\n"
                }
            ]
        }

        result = network_injector_module.inject_network_config(obj, g)

        assert result["injected"] is True
        assert result["files_created"][0]["path"] == "/etc/systemd/network/05-eth0.network"

    def test_default_priority(self, network_injector_module):
        """Test that default priority is 50 when not specified"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.network_config_inject = {
            "network_files": [
                {
                    "name": "eth0",
                    "type": "network",
                    # No priority specified
                    "content": "[Match]\nName=eth0\n"
                }
            ]
        }

        result = network_injector_module.inject_network_config(obj, g)

        assert result["injected"] is True
        assert result["files_created"][0]["path"] == "/etc/systemd/network/50-eth0.network"


class TestEnableService:
    """Test _enable_service helper function"""

    def test_enable_service_exists(self, network_injector_module):
        """Test enabling a service that exists"""
        g = FakeGuestFS()
        logger = FakeLogger()

        # Add service file to fake filesystem
        g.fs["/usr/lib/systemd/system/systemd-networkd.service"] = b""

        result = network_injector_module._enable_service(g, logger, "systemd-networkd.service")

        assert result is True
        assert g.exists("/etc/systemd/system/multi-user.target.wants/systemd-networkd.service")

    def test_enable_service_not_found(self, network_injector_module):
        """Test enabling a service that doesn't exist"""
        g = FakeGuestFS()
        logger = FakeLogger()

        result = network_injector_module._enable_service(g, logger, "nonexistent.service")

        assert result is False

    def test_enable_service_already_enabled(self, network_injector_module):
        """Test enabling a service that's already enabled"""
        g = FakeGuestFS()
        logger = FakeLogger()

        # Add service file and symlink
        g.fs["/usr/lib/systemd/system/NetworkManager.service"] = b""
        g.mkdir_p("/etc/systemd/system/multi-user.target.wants")
        g.fs["/etc/systemd/system/multi-user.target.wants/NetworkManager.service"] = b"link->/usr/lib/systemd/system/NetworkManager.service"

        result = network_injector_module._enable_service(g, logger, "NetworkManager.service")

        assert result is True
