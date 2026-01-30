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
        self.assertIsNone(config.user)
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
            ssh_opt=["-o", "StrictHostKeyChecking=no"],
        )
        self.assertEqual(config.host, "example.com")
        self.assertEqual(config.user, "testuser")
        self.assertEqual(config.port, 2222)
        self.assertEqual(config.identity, "/path/to/key")
        self.assertTrue(config.sudo)
        self.assertEqual(config.ssh_opt, ["-o", "StrictHostKeyChecking=no"])

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
        cmd = config.build_ssh_command()

        self.assertIn("ssh", cmd)
        self.assertIn("example.com", cmd)

    def test_builds_ssh_command_with_user(self):
        """Test building SSH command with user."""
        config = SSHConfig(host="example.com", user="testuser")
        cmd = config.build_ssh_command()

        self.assertIn("testuser@example.com", cmd)

    def test_builds_ssh_command_with_port(self):
        """Test building SSH command with custom port."""
        config = SSHConfig(host="example.com", port=2222)
        cmd = config.build_ssh_command()

        self.assertIn("-p", cmd)
        self.assertIn("2222", cmd)

    def test_builds_ssh_command_with_identity(self):
        """Test building SSH command with identity file."""
        config = SSHConfig(host="example.com", identity="/path/to/key")
        cmd = config.build_ssh_command()

        self.assertIn("-i", cmd)
        self.assertIn("/path/to/key", cmd)

    def test_builds_ssh_command_with_options(self):
        """Test building SSH command with custom options."""
        config = SSHConfig(
            host="example.com",
            ssh_opt=["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"],
        )
        cmd = config.build_ssh_command()

        self.assertIn("-o", cmd)
        self.assertIn("StrictHostKeyChecking=no", cmd)

    def test_builds_ssh_command_complete(self):
        """Test building complete SSH command with all options."""
        config = SSHConfig(
            host="example.com",
            user="testuser",
            port=2222,
            identity="/path/to/key",
            ssh_opt=["-o", "StrictHostKeyChecking=no"],
        )
        cmd = config.build_ssh_command()

        self.assertIn("ssh", cmd)
        self.assertIn("testuser@example.com", cmd)
        self.assertIn("-p", cmd)
        self.assertIn("2222", cmd)
        self.assertIn("-i", cmd)
        self.assertIn("/path/to/key", cmd)
        self.assertIn("-o", cmd)

    def test_builds_scp_command_basic(self):
        """Test building basic SCP command."""
        config = SSHConfig(host="example.com")
        cmd = config.build_scp_command("/local/file", "/remote/file")

        self.assertIn("scp", cmd)
        self.assertIn("/local/file", cmd)
        self.assertIn("example.com:/remote/file", cmd)

    def test_builds_scp_command_with_user(self):
        """Test building SCP command with user."""
        config = SSHConfig(host="example.com", user="testuser")
        cmd = config.build_scp_command("/local/file", "/remote/file")

        self.assertIn("testuser@example.com:/remote/file", cmd)

    def test_builds_scp_command_with_port(self):
        """Test building SCP command with custom port."""
        config = SSHConfig(host="example.com", port=2222)
        cmd = config.build_scp_command("/local/file", "/remote/file")

        self.assertIn("-P", cmd)  # SCP uses -P not -p
        self.assertIn("2222", cmd)

    def test_connection_string(self):
        """Test connection string generation."""
        config = SSHConfig(host="example.com", user="testuser", port=2222)
        conn_str = config.connection_string()

        self.assertEqual(conn_str, "testuser@example.com:2222")

    def test_connection_string_no_user(self):
        """Test connection string without user."""
        config = SSHConfig(host="example.com", port=2222)
        conn_str = config.connection_string()

        self.assertEqual(conn_str, "example.com:2222")

    def test_connection_string_default_port(self):
        """Test connection string with default port."""
        config = SSHConfig(host="example.com", user="testuser")
        conn_str = config.connection_string()

        self.assertEqual(conn_str, "testuser@example.com:22")


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
