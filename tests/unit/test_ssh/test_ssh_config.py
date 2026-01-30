# SPDX-License-Identifier: LGPL-3.0-or-later
import unittest
import tempfile
from pathlib import Path
from dataclasses import asdict

from hyper2kvm.ssh.ssh_config import SSHConfig


class TestSSHConfig(unittest.TestCase):
    """Test SSH configuration dataclass."""

    def test_default_config(self):
        """Test default SSH configuration."""
        config = SSHConfig(host="example.com")
        self.assertEqual(config.host, "example.com")
        self.assertEqual(config.port, 22)
        self.assertEqual(config.user, "root")  # Default user is root
        self.assertIsNone(config.identity)
        self.assertFalse(config.sudo)

    def test_custom_config(self):
        """Test custom SSH configuration."""
        config = SSHConfig(
            host="example.com",
            user="testuser",
            port=2222,
            identity="/path/to/key",
            sudo=True,
            ssh_opts=["StrictHostKeyChecking=no"],
        )
        self.assertEqual(config.host, "example.com")
        self.assertEqual(config.user, "testuser")
        self.assertEqual(config.port, 2222)
        self.assertEqual(str(config.identity), "/path/to/key")  # identity is converted to Path
        self.assertTrue(config.sudo)
        self.assertEqual(config.ssh_opts, ["StrictHostKeyChecking=no"])

    def test_config_serialization(self):
        """Test configuration can be serialized to dict."""
        config = SSHConfig(
            host="example.com",
            user="testuser",
            port=2222,
        )
        config_dict = asdict(config)
        self.assertIsInstance(config_dict, dict)
        self.assertEqual(config_dict["host"], "example.com")
        self.assertEqual(config_dict["user"], "testuser")
        self.assertEqual(config_dict["port"], 2222)

    def test_builds_ssh_command_basic(self):
        """Test building basic SSH command."""
        config = SSHConfig(host="example.com")
        cmd = config.base_cmd()

        self.assertIn("ssh", cmd)
        # example.com is part of root@example.com
        self.assertTrue(any("example.com" in str(item) for item in cmd))

    def test_builds_ssh_command_with_user(self):
        """Test building SSH command with user."""
        config = SSHConfig(host="example.com", user="testuser")
        cmd = config.base_cmd()

        # Check that target includes user@host
        target = config.target()
        self.assertIn("testuser@", target)
        self.assertIn("example.com", target)

    def test_builds_ssh_command_with_port(self):
        """Test building SSH command with custom port."""
        config = SSHConfig(host="example.com", port=2222)
        cmd = config.base_cmd()

        self.assertIn("-p", cmd)
        self.assertIn("2222", cmd)

    def test_builds_ssh_command_with_identity(self):
        """Test building SSH command with identity file."""
        config = SSHConfig(host="example.com", identity="/path/to/key")
        cmd = config.base_cmd()

        self.assertIn("-i", cmd)
        # Path gets expanded, so just check -i is present
        self.assertTrue(any("/path/to/key" in str(item) for item in cmd))

    def test_builds_ssh_command_with_options(self):
        """Test building SSH command with custom options."""
        config = SSHConfig(
            host="example.com",
            ssh_opts=["StrictHostKeyChecking=no", "UserKnownHostsFile=/dev/null"],
        )
        cmd = config.base_cmd()

        self.assertIn("-o", cmd)
        self.assertIn("StrictHostKeyChecking=no", cmd)

    def test_builds_ssh_command_complete(self):
        """Test building complete SSH command with all options."""
        config = SSHConfig(
            host="example.com",
            user="testuser",
            port=2222,
            identity="/path/to/key",
            ssh_opts=["StrictHostKeyChecking=no"],
        )
        cmd = config.base_cmd()

        self.assertIn("ssh", cmd)
        self.assertIn("-p", cmd)
        self.assertIn("2222", cmd)
        self.assertIn("-i", cmd)
        self.assertIn("-o", cmd)

    def test_builds_scp_command_basic(self):
        """Test building basic SCP command."""
        config = SSHConfig(host="example.com")
        cmd = config.scp_base_cmd()
        scp_src = config.scp_src("/remote/file")

        self.assertIn("scp", cmd)
        self.assertIn("example.com:/remote/file", scp_src)

    def test_builds_scp_command_with_user(self):
        """Test building SCP command with user."""
        config = SSHConfig(host="example.com", user="testuser")
        scp_target = config.scp_target()

        self.assertIn("testuser@", scp_target)
        self.assertIn("example.com", scp_target)

    def test_builds_scp_command_with_port(self):
        """Test building SCP command with custom port."""
        config = SSHConfig(host="example.com", port=2222)
        cmd = config.scp_base_cmd()

        self.assertIn("-P", cmd)  # SCP uses -P not -p
        self.assertIn("2222", cmd)

    def test_connection_string(self):
        """Test connection string generation."""
        config = SSHConfig(host="example.com", user="testuser", port=2222)
        desc = config.describe()

        self.assertIn("testuser@example.com", desc)
        self.assertIn("2222", desc)

    def test_connection_string_no_user(self):
        """Test connection string without user defaults to root."""
        config = SSHConfig(host="example.com", port=2222)
        desc = config.describe()

        self.assertIn("root@example.com", desc)  # Default user is root
        self.assertIn("2222", desc)

    def test_connection_string_default_port(self):
        """Test connection string with default port."""
        config = SSHConfig(host="example.com", user="testuser")
        desc = config.describe()

        self.assertIn("testuser@example.com", desc)
        self.assertIn("22", desc)


class TestSSHConfigValidation(unittest.TestCase):
    """Test SSH configuration validation."""

    def test_requires_host(self):
        """Test that host is required."""
        # Should not raise when host is provided
        config = SSHConfig(host="example.com")
        self.assertEqual(config.host, "example.com")

    def test_default_port_validation(self):
        """Test that port defaults to 22."""
        config = SSHConfig(host="example.com")
        self.assertEqual(config.port, 22)

    def test_custom_port_validation(self):
        """Test that custom port is accepted."""
        config = SSHConfig(host="example.com", port=8022)
        self.assertEqual(config.port, 8022)


if __name__ == "__main__":
    unittest.main()
