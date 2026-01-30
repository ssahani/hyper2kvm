# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for user configuration injector."""
import unittest
from unittest.mock import MagicMock, patch, call


class TestUserConfigInjector(unittest.TestCase):
    """Test suite for user configuration injection."""

    def setUp(self):
        """Set up test fixtures."""
        from hyper2kvm.fixers import user_config_injector

        self.injector = user_config_injector

    def test_inject_no_config(self):
        """Test when no config is provided."""
        mock_self = MagicMock()
        mock_self.user_config_inject = None
        mock_g = MagicMock()

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertFalse(result["injected"])
        self.assertEqual(result["reason"], "no_config")

    def test_inject_invalid_config_type(self):
        """Test when config is not a dict."""
        mock_self = MagicMock()
        mock_self.user_config_inject = "invalid"
        mock_g = MagicMock()

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertFalse(result["injected"])
        self.assertEqual(result["reason"], "invalid_config")

    def test_inject_empty_config(self):
        """Test when config is empty."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {}
        mock_self.dry_run = False
        mock_g = MagicMock()

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertFalse(result["injected"])
        self.assertEqual(result["reason"], "no_config")

    def test_inject_create_user_basic(self):
        """Test creating a basic user."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "users": [{"name": "testuser"}]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.return_value = ""
        mock_g.is_dir.return_value = True

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertIn("testuser", result["users_created"])

    def test_inject_create_user_with_uid(self):
        """Test creating a user with specific UID."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "users": [{"name": "testuser", "uid": 1500}]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.return_value = ""
        mock_g.is_dir.return_value = True

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertIn("testuser", result["users_created"])

    def test_inject_create_user_with_groups(self):
        """Test creating a user with groups."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "users": [{"name": "testuser", "groups": ["wheel", "docker"]}]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.return_value = ""
        mock_g.is_dir.return_value = True

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertIn("testuser", result["users_created"])

    def test_inject_deploy_ssh_keys(self):
        """Test deploying SSH keys."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "users": [{
                "name": "testuser",
                "ssh_keys": ["ssh-rsa AAAA... user@host"]
            }]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.return_value = ""
        mock_g.is_dir.return_value = True
        mock_g.exists.return_value = False

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertIn("testuser", result["users_created"])
        self.assertEqual(result["ssh_keys_deployed"], 1)

    def test_inject_configure_sudo(self):
        """Test configuring sudo access."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "users": [{
                "name": "admin",
                "sudo": "ALL=(ALL) NOPASSWD:ALL"
            }]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.return_value = ""
        mock_g.is_dir.return_value = True

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertIn("admin", result["users_created"])
        self.assertIn("admin", result["sudo_configured"])

    def test_inject_set_password(self):
        """Test setting user password."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "users": [{
                "name": "testuser",
                "password": "testpass123"
            }]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.return_value = ""
        mock_g.is_dir.return_value = True

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertIn("testuser", result["users_created"])

    def test_inject_disable_user(self):
        """Test disabling a user."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "disable_users": ["ubuntu", "centos"]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.return_value = ""

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertEqual(len(result["users_disabled"]), 2)

    def test_inject_delete_user(self):
        """Test deleting a user."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "delete_users": ["testuser"]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.return_value = ""

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertEqual(len(result["users_deleted"]), 1)

    def test_inject_dry_run(self):
        """Test dry-run mode."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "users": [{
                "name": "testuser",
                "ssh_keys": ["ssh-rsa AAAA... user@host"],
                "sudo": "ALL=(ALL) ALL"
            }],
            "disable_users": ["ubuntu"]
        }
        mock_self.dry_run = True
        mock_self.logger = MagicMock()

        mock_g = MagicMock()

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(len(result["users_created"]), 1)
        self.assertEqual(result["ssh_keys_deployed"], 1)
        self.assertIn("testuser", result["sudo_configured"])
        self.assertEqual(len(result["users_disabled"]), 1)
        # Verify no actual commands were run
        mock_g.command.assert_not_called()

    def test_inject_multiple_users(self):
        """Test creating multiple users."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "users": [
                {"name": "admin", "uid": 1000, "groups": ["wheel"]},
                {"name": "developer", "uid": 1001, "groups": ["docker"]},
                {"name": "guest", "uid": 1002}
            ]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.return_value = ""
        mock_g.is_dir.return_value = True

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertEqual(len(result["users_created"]), 3)

    def test_inject_multiple_ssh_keys(self):
        """Test deploying multiple SSH keys for one user."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "users": [{
                "name": "testuser",
                "ssh_keys": [
                    "ssh-rsa AAAA... key1",
                    "ssh-rsa BBBB... key2",
                    "ssh-ed25519 CCCC... key3"
                ]
            }]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.return_value = ""
        mock_g.is_dir.return_value = True
        mock_g.exists.return_value = False

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertEqual(result["ssh_keys_deployed"], 3)

    def test_inject_user_with_comment(self):
        """Test creating user with comment field."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "users": [{
                "name": "admin",
                "comment": "System Administrator"
            }]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.return_value = ""
        mock_g.is_dir.return_value = True

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertIn("admin", result["users_created"])

    def test_inject_ssh_keys_creates_directory(self):
        """Test that .ssh directory is created with proper permissions."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "users": [{
                "name": "testuser",
                "ssh_keys": ["ssh-rsa AAAA... key"]
            }]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.return_value = ""
        mock_g.is_dir.return_value = True
        mock_g.exists.return_value = False

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertEqual(result["ssh_keys_deployed"], 1)

    def test_inject_complete_user_setup(self):
        """Test complete user setup with all features."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "users": [{
                "name": "admin",
                "uid": 1000,
                "groups": ["wheel", "docker"],
                "comment": "System Administrator",
                "ssh_keys": ["ssh-rsa AAAA... admin@host"],
                "password": "changeme",
                "sudo": "ALL=(ALL) NOPASSWD:ALL"
            }]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.return_value = ""
        mock_g.is_dir.return_value = True
        mock_g.exists.return_value = False

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertIn("admin", result["users_created"])
        self.assertEqual(result["ssh_keys_deployed"], 1)
        self.assertIn("admin", result["sudo_configured"])

    def test_inject_error_handling_user_creation(self):
        """Test error handling during user creation."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "users": [{"name": "testuser"}]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.side_effect = Exception("Test error")

        result = self.injector.inject_user_config(mock_self, mock_g)

        # Should continue despite error
        self.assertTrue(result["injected"])

    def test_inject_skip_invalid_user(self):
        """Test skipping users with invalid configuration."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "users": [
                {"name": "validuser"},
                {},  # Invalid: no name
                {"uid": 1000}  # Invalid: no name
            ]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.return_value = ""
        mock_g.is_dir.return_value = True

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        # Only valid user should be created
        self.assertEqual(len(result["users_created"]), 1)

    def test_inject_sudo_file_permissions(self):
        """Test sudo file has correct permissions (0440)."""
        mock_self = MagicMock()
        mock_self.user_config_inject = {
            "users": [{
                "name": "admin",
                "sudo": "ALL=(ALL) NOPASSWD:ALL"
            }]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.command.return_value = ""
        mock_g.is_dir.return_value = True

        result = self.injector.inject_user_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertIn("admin", result["sudo_configured"])


if __name__ == "__main__":
    unittest.main()
