# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for systemd service configuration injector."""
import unittest
from unittest.mock import MagicMock, call


class TestServiceConfigInjector(unittest.TestCase):
    """Test suite for systemd service configuration injection."""

    def setUp(self):
        """Set up test fixtures."""
        from hyper2kvm.fixers import service_config_injector

        self.injector = service_config_injector

    def test_inject_no_config(self):
        """Test when no config is provided."""
        mock_self = MagicMock()
        mock_self.service_config_inject = None
        mock_g = MagicMock()

        result = self.injector.inject_service_config(mock_self, mock_g)

        self.assertFalse(result["injected"])
        self.assertEqual(result["reason"], "no_config")

    def test_inject_invalid_config_type(self):
        """Test when config is not a dict."""
        mock_self = MagicMock()
        mock_self.service_config_inject = "invalid"
        mock_g = MagicMock()

        result = self.injector.inject_service_config(mock_self, mock_g)

        self.assertFalse(result["injected"])
        self.assertEqual(result["reason"], "invalid_config")

    def test_inject_empty_config(self):
        """Test when config is empty."""
        mock_self = MagicMock()
        mock_self.service_config_inject = {}
        mock_self.dry_run = False
        mock_g = MagicMock()

        result = self.injector.inject_service_config(mock_self, mock_g)

        self.assertFalse(result["injected"])
        self.assertEqual(result["reason"], "no_config")

    def test_inject_enable_service(self):
        """Test enabling a service."""
        mock_self = MagicMock()
        mock_self.service_config_inject = {"enable": ["sshd"]}
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.exists.return_value = True
        mock_g.is_dir.return_value = False

        result = self.injector.inject_service_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertIn("sshd.service", result["enabled"])
        mock_g.ln_sf.assert_called_once()

    def test_inject_enable_service_auto_suffix(self):
        """Test enabling a service without .service suffix."""
        mock_self = MagicMock()
        mock_self.service_config_inject = {"enable": ["sshd"]}
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.exists.return_value = True
        mock_g.is_dir.return_value = False

        result = self.injector.inject_service_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertIn("sshd.service", result["enabled"])

    def test_inject_disable_service(self):
        """Test disabling a service."""
        mock_self = MagicMock()
        mock_self.service_config_inject = {"disable": ["bluetooth"]}
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.exists.return_value = True

        result = self.injector.inject_service_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertIn("bluetooth.service", result["disabled"])
        mock_g.rm.assert_called_once()

    def test_inject_mask_service(self):
        """Test masking a service."""
        mock_self = MagicMock()
        mock_self.service_config_inject = {"mask": ["cups"]}
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()

        result = self.injector.inject_service_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertIn("cups.service", result["masked"])
        mock_g.ln_sf.assert_called_once_with("/dev/null", "/etc/systemd/system/cups.service")

    def test_inject_multiple_operations(self):
        """Test enabling, disabling, and masking services together."""
        mock_self = MagicMock()
        mock_self.service_config_inject = {
            "enable": ["sshd", "nginx"],
            "disable": ["bluetooth", "cups"],
            "mask": ["avahi-daemon"]
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.exists.return_value = True
        mock_g.is_dir.return_value = False

        result = self.injector.inject_service_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertEqual(len(result["enabled"]), 2)
        self.assertEqual(len(result["disabled"]), 2)
        self.assertEqual(len(result["masked"]), 1)

    def test_inject_dry_run(self):
        """Test dry-run mode."""
        mock_self = MagicMock()
        mock_self.service_config_inject = {
            "enable": ["sshd"],
            "disable": ["bluetooth"],
            "mask": ["cups"]
        }
        mock_self.dry_run = True
        mock_self.logger = MagicMock()

        mock_g = MagicMock()

        result = self.injector.inject_service_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertTrue(result["dry_run"])
        self.assertIn("sshd.service", result["enabled"])
        self.assertIn("bluetooth.service", result["disabled"])
        self.assertIn("cups.service", result["masked"])
        # Verify no actual modifications were made
        mock_g.ln_sf.assert_not_called()
        mock_g.rm.assert_not_called()

    def test_inject_enable_service_not_found(self):
        """Test enabling a service that doesn't exist."""
        mock_self = MagicMock()
        mock_self.service_config_inject = {"enable": ["nonexistent"]}
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.exists.return_value = False

        result = self.injector.inject_service_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertEqual(len(result["enabled"]), 0)

    def test_inject_disable_service_not_linked(self):
        """Test disabling a service that isn't enabled."""
        mock_self = MagicMock()
        mock_self.service_config_inject = {"disable": ["bluetooth"]}
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.exists.return_value = False

        result = self.injector.inject_service_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        # Service is still added to disabled list even if link doesn't exist
        self.assertEqual(len(result["disabled"]), 1)

    def test_inject_with_service_suffix(self):
        """Test with services that already have .service suffix."""
        mock_self = MagicMock()
        mock_self.service_config_inject = {"enable": ["sshd.service"]}
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.exists.return_value = True
        mock_g.is_dir.return_value = False

        result = self.injector.inject_service_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertIn("sshd.service", result["enabled"])

    def test_inject_creates_wants_directory(self):
        """Test that wants directory is created if missing."""
        mock_self = MagicMock()
        mock_self.service_config_inject = {"enable": ["sshd"]}
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.exists.return_value = True
        mock_g.is_dir.return_value = False

        result = self.injector.inject_service_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        mock_g.mkdir_p.assert_called_once_with("/etc/systemd/system/multi-user.target.wants")

    def test_inject_error_handling(self):
        """Test error handling during service operations."""
        mock_self = MagicMock()
        mock_self.service_config_inject = {"enable": ["sshd"]}
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.exists.side_effect = Exception("Test error")

        result = self.injector.inject_service_config(mock_self, mock_g)

        # Should continue despite errors
        self.assertTrue(result["injected"])


if __name__ == "__main__":
    unittest.main()
