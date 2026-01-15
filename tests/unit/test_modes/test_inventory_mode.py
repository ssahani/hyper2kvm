# SPDX-License-Identifier: LGPL-3.0-or-later
import unittest
from unittest.mock import Mock, patch

from hyper2kvm.modes.inventory_mode import InventoryMode


class TestInventoryMode(unittest.TestCase):
    """Test inventory discovery mode."""

    def setUp(self):
        self.logger = Mock()

    @patch('hyper2kvm.vmware.clients.vsphere_client.VSphereClient')
    def test_discovers_vms(self, mock_client_class):
        """Test VM discovery."""
        mock_client = Mock()
        mock_client.list_vms.return_value = [
            {"name": "vm1", "power_state": "poweredOn"},
            {"name": "vm2", "power_state": "poweredOff"},
        ]
        mock_client_class.return_value = mock_client

        mode = InventoryMode(self.logger)
        vms = mode.discover(host="vcenter.example.com", user="admin", password="secret")

        self.assertEqual(len(vms), 2)
        self.assertTrue(mock_client.list_vms.called)

    def test_formats_vm_list(self):
        """Test VM list formatting."""
        vms = [
            {"name": "vm1", "power_state": "poweredOn", "cpus": 2, "memory_mb": 2048},
            {"name": "vm2", "power_state": "poweredOff", "cpus": 4, "memory_mb": 4096},
        ]

        mode = InventoryMode(self.logger)
        output = mode.format_inventory(vms)

        self.assertIn("vm1", output)
        self.assertIn("vm2", output)
        self.assertIsInstance(output, str)

    def test_filters_by_power_state(self):
        """Test filtering VMs by power state."""
        vms = [
            {"name": "vm1", "power_state": "poweredOn"},
            {"name": "vm2", "power_state": "poweredOff"},
            {"name": "vm3", "power_state": "poweredOn"},
        ]

        mode = InventoryMode(self.logger)
        powered_on = mode.filter_by_state(vms, "poweredOn")

        self.assertEqual(len(powered_on), 2)
        self.assertTrue(all(vm["power_state"] == "poweredOn" for vm in powered_on))

    def test_exports_to_yaml(self):
        """Test exporting inventory to YAML."""
        vms = [
            {"name": "vm1", "power_state": "poweredOn"},
            {"name": "vm2", "power_state": "poweredOff"},
        ]

        mode = InventoryMode(self.logger)
        yaml_output = mode.export_yaml(vms)

        self.assertIn("vm1", yaml_output)
        self.assertIn("vm2", yaml_output)
        self.assertIsInstance(yaml_output, str)


class TestInventoryModeFiltering(unittest.TestCase):
    """Test inventory filtering capabilities."""

    def setUp(self):
        self.logger = Mock()

    def test_filters_by_name_pattern(self):
        """Test filtering VMs by name pattern."""
        vms = [
            {"name": "prod-vm1"},
            {"name": "prod-vm2"},
            {"name": "test-vm1"},
            {"name": "dev-vm1"},
        ]

        mode = InventoryMode(self.logger)
        prod_vms = mode.filter_by_pattern(vms, pattern="prod-*")

        self.assertEqual(len(prod_vms), 2)

    def test_filters_by_resource_pool(self):
        """Test filtering VMs by resource pool."""
        vms = [
            {"name": "vm1", "resource_pool": "production"},
            {"name": "vm2", "resource_pool": "development"},
            {"name": "vm3", "resource_pool": "production"},
        ]

        mode = InventoryMode(self.logger)
        prod_vms = mode.filter_by_resource_pool(vms, "production")

        self.assertEqual(len(prod_vms), 2)


if __name__ == "__main__":
    unittest.main()
