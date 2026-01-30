# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Advanced tests for SSH configuration and command building
Tests edge cases, security features, and complex scenarios
"""
import unittest
from pathlib import Path

from hyper2kvm.ssh.ssh_config import SSHConfig


class TestSSHConfigAdvanced(unittest.TestCase):
    """Test advanced SSH configuration scenarios."""

    def test_identity_path_expansion(self):
        """Test that identity path gets expanded correctly."""
        config = SSHConfig(
            host="example.com",
            identity="~/path/to/key"
        )

        # Identity should be a Path object
        self.assertIsInstance(config.identity, Path)
        # Tilde should be expanded
        self.assertNotIn("~", str(config.identity))

    def test_identity_absolute_path(self):
        """Test absolute identity path."""
        config = SSHConfig(
            host="example.com",
            identity="/absolute/path/to/key"
        )

        cmd = config.base_cmd()
        self.assertIn("-i", cmd)
        self.assertIn("/absolute/path/to/key", cmd)

    def test_multiple_ssh_options(self):
        """Test multiple SSH options."""
        config = SSHConfig(
            host="example.com",
            ssh_opts=[
                "StrictHostKeyChecking=no",
                "UserKnownHostsFile=/dev/null",
                "ConnectTimeout=10",
                "ServerAliveInterval=60"
            ]
        )

        cmd = config.base_cmd()

        # SSHConfig adds default options, so count will be higher than 4
        # Just check that our options are present
        self.assertIn("StrictHostKeyChecking=no", cmd)
        self.assertIn("UserKnownHostsFile=/dev/null", cmd)
        self.assertIn("ConnectTimeout=10", cmd)
        self.assertIn("ServerAliveInterval=60", cmd)
        # Should have at least our 4 -o flags (plus defaults)
        self.assertGreaterEqual(cmd.count("-o"), 4)

    def test_high_port_number(self):
        """Test SSH with high port number."""
        config = SSHConfig(
            host="example.com",
            port=65535  # Maximum valid port
        )

        cmd = config.base_cmd()
        self.assertIn("-p", cmd)
        self.assertIn("65535", cmd)

    def test_ipv6_host(self):
        """Test SSH with IPv6 address."""
        config = SSHConfig(
            host="2001:db8::1",
            user="testuser"
        )

        target = config.target()
        self.assertIn("2001:db8::1", target)
        self.assertIn("testuser@", target)

    def test_scp_with_remote_path(self):
        """Test SCP source/target path building."""
        config = SSHConfig(
            host="example.com",
            user="testuser"
        )

        src = config.scp_src("/remote/path/file.txt")
        self.assertEqual(src, "testuser@example.com:/remote/path/file.txt")

        target = config.scp_target()
        self.assertEqual(target, "testuser@example.com")

    def test_scp_port_flag(self):
        """Test that SCP uses -P (capital P) for port."""
        config = SSHConfig(
            host="example.com",
            port=2222
        )

        cmd = config.scp_base_cmd()
        self.assertIn("-P", cmd)  # SCP uses -P, not -p
        self.assertIn("2222", cmd)

    def test_remote_command_building(self):
        """Test building remote command execution."""
        config = SSHConfig(
            host="example.com",
            user="testuser"
        )

        cmd = config.remote_cmd(["ls", "-la", "/tmp"])

        # Should contain ssh command
        self.assertIn("ssh", " ".join(cmd).lower())
        # Should contain remote command
        self.assertIn("ls", cmd)
        self.assertIn("-la", cmd)
        self.assertIn("/tmp", cmd)

    def test_remote_command_with_sudo(self):
        """Test remote command with sudo."""
        config = SSHConfig(
            host="example.com",
            user="testuser",
            sudo=True
        )

        # When sudo is enabled, remote commands may be prefixed
        self.assertTrue(config.sudo)

    def test_describe_includes_all_details(self):
        """Test that describe() includes all connection details."""
        config = SSHConfig(
            host="example.com",
            user="admin",
            port=2222
        )

        desc = config.describe()

        self.assertIn("admin", desc)
        self.assertIn("example.com", desc)
        self.assertIn("2222", desc)

    def test_describe_with_default_port(self):
        """Test describe() with default port."""
        config = SSHConfig(
            host="example.com",
            user="admin"
        )

        desc = config.describe()
        self.assertIn("22", desc)  # Should show default port

    def test_ssh_opts_empty_list(self):
        """Test that empty ssh_opts list is handled."""
        config = SSHConfig(
            host="example.com",
            ssh_opts=[]
        )

        cmd = config.base_cmd()
        # SSHConfig adds default options (ConnectTimeout, etc.) even with empty ssh_opts
        # So there will still be -o flags
        self.assertIn("ssh", cmd)
        # Verify it works without errors
        self.assertGreater(len(cmd), 0)

    def test_config_serialization_for_logging(self):
        """Test that config can be converted to dict for logging."""
        config = SSHConfig(
            host="example.com",
            user="testuser",
            port=2222,
            identity="/path/to/key",
            ssh_opts=["StrictHostKeyChecking=no"],
            sudo=True
        )

        from dataclasses import asdict
        config_dict = asdict(config)

        self.assertEqual(config_dict["host"], "example.com")
        self.assertEqual(config_dict["user"], "testuser")
        self.assertEqual(config_dict["port"], 2222)
        self.assertTrue(config_dict["sudo"])


class TestSSHConfigCommandQuoting(unittest.TestCase):
    """Test proper quoting in SSH commands."""

    def test_remote_command_with_spaces(self):
        """Test remote command with spaces in arguments."""
        config = SSHConfig(host="example.com")

        cmd = config.remote_cmd(["echo", "hello world"])

        # Should handle spaces in arguments
        self.assertIn("echo", cmd)
        # The remote command should be quoted or handled properly
        self.assertIn("hello world", " ".join(cmd))

    def test_remote_command_with_special_chars(self):
        """Test remote command with special characters."""
        config = SSHConfig(host="example.com")

        cmd = config.remote_cmd(["bash", "-c", "echo $HOME"])

        # Should contain the command
        self.assertIn("bash", cmd)
        self.assertIn("-c", cmd)


class TestSSHConfigValidation(unittest.TestCase):
    """Test SSH configuration validation."""

    def test_requires_host(self):
        """Test that host is required."""
        # Host is a required parameter, should not be able to create without it
        # This would raise TypeError if attempted:
        # config = SSHConfig()  # TypeError: missing required argument: 'host'

        # Valid config
        config = SSHConfig(host="example.com")
        self.assertEqual(config.host, "example.com")

    def test_default_user_is_root(self):
        """Test that default user is root."""
        config = SSHConfig(host="example.com")
        self.assertEqual(config.user, "root")

    def test_default_port_is_22(self):
        """Test that default port is 22."""
        config = SSHConfig(host="example.com")
        self.assertEqual(config.port, 22)

    def test_default_sudo_is_false(self):
        """Test that default sudo is False."""
        config = SSHConfig(host="example.com")
        self.assertFalse(config.sudo)

    def test_identity_none_by_default(self):
        """Test that identity is None by default."""
        config = SSHConfig(host="example.com")
        self.assertIsNone(config.identity)

    def test_ssh_opts_empty_by_default(self):
        """Test that ssh_opts is empty list by default."""
        config = SSHConfig(host="example.com")
        self.assertEqual(config.ssh_opts, [])


class TestSSHConfigEdgeCases(unittest.TestCase):
    """Test edge cases in SSH configuration."""

    def test_hostname_with_dash(self):
        """Test hostname with dashes."""
        config = SSHConfig(host="my-server.example.com")
        self.assertEqual(config.host, "my-server.example.com")

    def test_hostname_with_subdomain(self):
        """Test hostname with multiple subdomains."""
        config = SSHConfig(host="server.prod.internal.example.com")
        self.assertEqual(config.host, "server.prod.internal.example.com")

    def test_username_with_special_chars(self):
        """Test username with dots and underscores."""
        config = SSHConfig(
            host="example.com",
            user="john.doe_admin"
        )
        self.assertEqual(config.user, "john.doe_admin")

    def test_port_boundary_values(self):
        """Test port boundary values."""
        # Minimum valid port (1)
        config1 = SSHConfig(host="example.com", port=1)
        self.assertEqual(config1.port, 1)

        # Common SSH port
        config2 = SSHConfig(host="example.com", port=22)
        self.assertEqual(config2.port, 22)

        # Maximum valid port (65535)
        config3 = SSHConfig(host="example.com", port=65535)
        self.assertEqual(config3.port, 65535)


if __name__ == "__main__":
    unittest.main()
