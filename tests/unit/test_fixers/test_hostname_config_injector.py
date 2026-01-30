# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for hostname configuration injector."""
import unittest
from unittest.mock import MagicMock, call


class TestHostnameConfigInjector(unittest.TestCase):
    """Test suite for hostname configuration injection."""

    def setUp(self):
        """Set up test fixtures."""
        from hyper2kvm.fixers import hostname_config_injector

        self.injector = hostname_config_injector

    def test_inject_no_config(self):
        """Test when no config is provided."""
        mock_self = MagicMock()
        mock_self.hostname_config_inject = None
        mock_g = MagicMock()

        result = self.injector.inject_hostname_config(mock_self, mock_g)

        self.assertFalse(result["injected"])
        self.assertEqual(result["reason"], "no_config")

    def test_inject_invalid_config_type(self):
        """Test when config is not a dict."""
        mock_self = MagicMock()
        mock_self.hostname_config_inject = "invalid"
        mock_g = MagicMock()

        result = self.injector.inject_hostname_config(mock_self, mock_g)

        self.assertFalse(result["injected"])
        self.assertEqual(result["reason"], "invalid_config")

    def test_inject_empty_config(self):
        """Test when config is empty."""
        mock_self = MagicMock()
        mock_self.hostname_config_inject = {}
        mock_self.dry_run = False
        mock_g = MagicMock()

        result = self.injector.inject_hostname_config(mock_self, mock_g)

        self.assertFalse(result["injected"])
        self.assertEqual(result["reason"], "no_config")

    def test_inject_hostname_only(self):
        """Test setting hostname only."""
        mock_self = MagicMock()
        mock_self.hostname_config_inject = {"hostname": "webserver"}
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.is_file.return_value = True
        mock_g.read_file.return_value = b"127.0.0.1\tlocalhost\n"

        result = self.injector.inject_hostname_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertTrue(result["hostname_set"])
        # Verify hostname file was written
        write_calls = mock_g.write.call_args_list
        self.assertEqual(len(write_calls), 2)  # /etc/hostname and /etc/hosts

    def test_inject_hostname_with_domain(self):
        """Test setting hostname with domain."""
        mock_self = MagicMock()
        mock_self.hostname_config_inject = {
            "hostname": "webserver",
            "domain": "example.com"
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.is_file.return_value = True
        mock_g.read_file.return_value = b"127.0.0.1\tlocalhost\n"

        result = self.injector.inject_hostname_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertTrue(result["hostname_set"])

    def test_inject_hosts_entries(self):
        """Test adding custom hosts entries."""
        mock_self = MagicMock()
        mock_self.hostname_config_inject = {
            "hosts": {
                "192.168.1.10": "server1.local server1",
                "192.168.1.20": "server2.local server2"
            }
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.is_file.return_value = True
        mock_g.read_file.return_value = b"127.0.0.1\tlocalhost\n"

        result = self.injector.inject_hostname_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertEqual(result["hosts_entries_added"], 2)

    def test_inject_hostname_and_hosts(self):
        """Test setting hostname and adding hosts entries together."""
        mock_self = MagicMock()
        mock_self.hostname_config_inject = {
            "hostname": "webserver",
            "domain": "example.com",
            "hosts": {
                "192.168.1.10": "db.example.com db"
            }
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.is_file.return_value = True
        mock_g.read_file.return_value = b"127.0.0.1\tlocalhost\n"

        result = self.injector.inject_hostname_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertTrue(result["hostname_set"])
        self.assertEqual(result["hosts_entries_added"], 1)

    def test_inject_dry_run(self):
        """Test dry-run mode."""
        mock_self = MagicMock()
        mock_self.hostname_config_inject = {
            "hostname": "webserver",
            "hosts": {"192.168.1.10": "server1"}
        }
        mock_self.dry_run = True
        mock_self.logger = MagicMock()

        mock_g = MagicMock()

        result = self.injector.inject_hostname_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertTrue(result["dry_run"])
        self.assertTrue(result["hostname_set"])
        self.assertEqual(result["hosts_entries_added"], 1)
        # Verify no actual writes were made
        mock_g.write.assert_not_called()

    def test_inject_update_existing_127_0_1_1(self):
        """Test updating existing 127.0.1.1 entry."""
        mock_self = MagicMock()
        mock_self.hostname_config_inject = {"hostname": "newhost"}
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.is_file.return_value = True
        mock_g.read_file.return_value = b"127.0.0.1\tlocalhost\n127.0.1.1\toldhost\n"

        result = self.injector.inject_hostname_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertTrue(result["hostname_set"])

    def test_inject_add_127_0_1_1_if_missing(self):
        """Test adding 127.0.1.1 entry if not present."""
        mock_self = MagicMock()
        mock_self.hostname_config_inject = {"hostname": "webserver"}
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.is_file.return_value = True
        mock_g.read_file.return_value = b"127.0.0.1\tlocalhost\n"

        result = self.injector.inject_hostname_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertTrue(result["hostname_set"])

    def test_inject_hosts_file_missing(self):
        """Test when /etc/hosts doesn't exist."""
        mock_self = MagicMock()
        mock_self.hostname_config_inject = {
            "hosts": {"192.168.1.10": "server1"}
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.is_file.return_value = False

        result = self.injector.inject_hostname_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertEqual(result["hosts_entries_added"], 1)

    def test_inject_error_handling_hostname(self):
        """Test error handling during hostname setting."""
        mock_self = MagicMock()
        mock_self.hostname_config_inject = {"hostname": "webserver"}
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.write.side_effect = Exception("Test error")

        result = self.injector.inject_hostname_config(mock_self, mock_g)

        # Should continue despite error
        self.assertTrue(result["injected"])
        self.assertFalse(result["hostname_set"])

    def test_inject_error_handling_hosts(self):
        """Test error handling during hosts entry addition."""
        mock_self = MagicMock()
        mock_self.hostname_config_inject = {
            "hosts": {"192.168.1.10": "server1"}
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.is_file.side_effect = Exception("Test error")

        result = self.injector.inject_hostname_config(mock_self, mock_g)

        # Should continue despite error
        self.assertTrue(result["injected"])
        self.assertEqual(result["hosts_entries_added"], 0)

    def test_inject_fqdn_with_domain(self):
        """Test FQDN creation with domain."""
        mock_self = MagicMock()
        mock_self.hostname_config_inject = {
            "hostname": "web01",
            "domain": "prod.example.com"
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.is_file.return_value = False

        result = self.injector.inject_hostname_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertTrue(result["hostname_set"])

    def test_inject_multiple_hosts_entries(self):
        """Test adding multiple hosts entries."""
        mock_self = MagicMock()
        mock_self.hostname_config_inject = {
            "hosts": {
                "192.168.1.10": "db1.local",
                "192.168.1.11": "db2.local",
                "192.168.1.12": "db3.local",
                "192.168.1.20": "web.local"
            }
        }
        mock_self.dry_run = False
        mock_self.logger = MagicMock()

        mock_g = MagicMock()
        mock_g.is_file.return_value = True
        mock_g.read_file.return_value = b"127.0.0.1\tlocalhost\n"

        result = self.injector.inject_hostname_config(mock_self, mock_g)

        self.assertTrue(result["injected"])
        self.assertEqual(result["hosts_entries_added"], 4)


if __name__ == "__main__":
    unittest.main()
