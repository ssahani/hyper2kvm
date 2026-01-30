# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test configuration validation with and without pydantic.

These tests ensure RHEL 10 compatibility by testing both code paths.
"""

import pytest
from pathlib import Path
from hyper2kvm.config.validation import (
    NetworkConfig,
    VMwareSourceConfig,
    DiskConfig,
    ConfigValidationError,
)
from hyper2kvm.core.optional_imports import PYDANTIC_AVAILABLE


class TestNetworkConfigCompatibility:
    """Test network config works with or without pydantic."""

    def test_valid_network_config(self):
        """Valid config should work regardless of pydantic availability."""
        config = NetworkConfig(
            interface_name="eth0", mac_address="52:54:00:12:34:56", ip_address="192.168.1.10"
        )

        assert config.interface_name == "eth0"
        assert config.mac_address == "52:54:00:12:34:56"
        assert config.ip_address == "192.168.1.10"

    def test_minimal_network_config(self):
        """Minimal valid config with only interface name."""
        config = NetworkConfig(interface_name="eth0")

        assert config.interface_name == "eth0"
        assert config.mac_address is None
        assert config.ip_address is None

    def test_invalid_interface_name(self):
        """Invalid interface name should fail."""
        with pytest.raises((ConfigValidationError, Exception)):
            NetworkConfig(interface_name="0eth")

    def test_invalid_mac_address(self):
        """Invalid MAC address should fail."""
        with pytest.raises((ConfigValidationError, Exception)):
            NetworkConfig(interface_name="eth0", mac_address="invalid:mac")

    def test_invalid_ip_address(self):
        """Invalid IP address should fail."""
        with pytest.raises((ConfigValidationError, Exception)):
            NetworkConfig(interface_name="eth0", ip_address="256.1.1.1")

    def test_too_many_dns_servers(self):
        """Should reject more than 3 DNS servers."""
        with pytest.raises((ConfigValidationError, Exception)):
            NetworkConfig(interface_name="eth0", dns_servers=["8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1"])

    def test_config_dict_interface(self):
        """Config should have dict() method."""
        config = NetworkConfig(interface_name="eth0", ip_address="192.168.1.10")

        data = config.dict()
        assert isinstance(data, dict)
        assert data["interface_name"] == "eth0"

    @pytest.mark.parametrize(
        "ip_addr",
        [
            "192.168.1.1",
            "10.0.0.1",
            "172.16.0.1",
            "255.255.255.255",
        ],
    )
    def test_valid_ip_addresses(self, ip_addr):
        """Various valid IP addresses should pass."""
        config = NetworkConfig(interface_name="eth0", ip_address=ip_addr)
        assert config.ip_address == ip_addr

    @pytest.mark.parametrize(
        "invalid_ip",
        [
            "256.1.1.1",
            "192.168.1",
            "abc.def.ghi.jkl",
            "192.168.1.1.1",
        ],
    )
    def test_invalid_ip_addresses(self, invalid_ip):
        """Invalid IP addresses should fail."""
        with pytest.raises((ConfigValidationError, Exception)):
            NetworkConfig(interface_name="eth0", ip_address=invalid_ip)


class TestVMwareSourceConfigCompatibility:
    """Test VMware config works with or without pydantic."""

    def test_valid_config_with_vm_name(self):
        """Valid config with vm_name."""
        config = VMwareSourceConfig(host="vcenter.example.com", username="admin", password="secret", vm_name="test-vm")

        assert config.host == "vcenter.example.com"
        assert config.vm_name == "test-vm"
        assert config.port == 443  # Default

    def test_valid_config_with_vm_uuid(self):
        """Valid config with vm_uuid."""
        config = VMwareSourceConfig(
            host="vcenter.example.com",
            username="admin",
            password="secret",
            vm_uuid="502323e7-4de8-4b9e-9a0e-1234567890ab",
        )

        assert config.vm_uuid is not None

    def test_missing_vm_identifier(self):
        """Should fail without vm_name or vm_uuid."""
        with pytest.raises((ConfigValidationError, Exception)):
            VMwareSourceConfig(host="vcenter.example.com", username="admin", password="secret")

    def test_invalid_port(self):
        """Should fail with invalid port."""
        with pytest.raises((ConfigValidationError, Exception)):
            VMwareSourceConfig(
                host="vcenter.example.com", username="admin", password="secret", vm_name="test-vm", port=99999
            )

    def test_custom_port(self):
        """Can specify custom port."""
        config = VMwareSourceConfig(
            host="vcenter.example.com", username="admin", password="secret", vm_name="test-vm", port=8443
        )

        assert config.port == 8443

    def test_verify_ssl_default(self):
        """verify_ssl should default to True."""
        config = VMwareSourceConfig(host="vcenter.example.com", username="admin", password="secret", vm_name="test-vm")

        assert config.verify_ssl is True

    def test_verify_ssl_false(self):
        """Can disable SSL verification."""
        config = VMwareSourceConfig(
            host="vcenter.example.com", username="admin", password="secret", vm_name="test-vm", verify_ssl=False
        )

        assert config.verify_ssl is False

    @pytest.mark.skipif(not PYDANTIC_AVAILABLE, reason="pydantic not available")
    def test_password_not_in_repr_with_pydantic(self):
        """Password should not appear in repr when using pydantic."""
        config = VMwareSourceConfig(
            host="vcenter.example.com", username="admin", password="supersecret", vm_name="test-vm"
        )

        repr_str = repr(config)
        assert "supersecret" not in repr_str


class TestDiskConfigCompatibility:
    """Test disk config works with or without pydantic."""

    def test_valid_disk_config(self, tmp_path):
        """Valid disk configuration."""
        disk_file = tmp_path / "test.vmdk"
        disk_file.write_bytes(b"\x00" * 1024)

        config = DiskConfig(source_path=disk_file, output_format="qcow2")

        assert config.source_path == disk_file
        assert config.output_format == "qcow2"
        assert config.compression is True

    def test_disk_not_found(self, tmp_path):
        """Should fail if disk doesn't exist."""
        missing_disk = tmp_path / "missing.vmdk"

        with pytest.raises((ConfigValidationError, Exception)):
            DiskConfig(source_path=missing_disk)

    def test_disk_is_directory(self, tmp_path):
        """Should fail if path is a directory."""
        with pytest.raises((ConfigValidationError, Exception)):
            DiskConfig(source_path=tmp_path)

    def test_invalid_output_format(self, tmp_path):
        """Should fail with invalid output format."""
        disk_file = tmp_path / "test.vmdk"
        disk_file.write_bytes(b"\x00" * 1024)

        with pytest.raises((ConfigValidationError, Exception)):
            DiskConfig(source_path=disk_file, output_format="invalid")

    @pytest.mark.parametrize("format", ["qcow2", "raw", "vmdk", "vhd"])
    def test_valid_output_formats(self, tmp_path, format):
        """All valid output formats should work."""
        disk_file = tmp_path / "test.vmdk"
        disk_file.write_bytes(b"\x00" * 1024)

        config = DiskConfig(source_path=disk_file, output_format=format)
        assert config.output_format == format


class TestPydanticAvailability:
    """Test pydantic availability detection."""

    def test_pydantic_flag_is_boolean(self):
        """PYDANTIC_AVAILABLE should be a boolean."""
        assert isinstance(PYDANTIC_AVAILABLE, bool)

    def test_validation_works_either_way(self):
        """Validation should work with or without pydantic."""
        # This should not raise
        config = NetworkConfig(interface_name="eth0", ip_address="192.168.1.10")

        assert config.interface_name == "eth0"

    def test_error_messages_are_informative(self):
        """Error messages should be helpful."""
        try:
            NetworkConfig(interface_name="0invalid")
            pytest.fail("Should have raised validation error")
        except (ConfigValidationError, Exception) as e:
            error_msg = str(e)
            # Should mention the field that failed
            assert "interface" in error_msg.lower() or "name" in error_msg.lower()
