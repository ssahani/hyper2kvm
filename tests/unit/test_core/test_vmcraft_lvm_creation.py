# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test VMCraft LVM creation APIs.

Tests the 6 LVM creation methods:
- pvcreate: Create physical volumes
- vgcreate: Create volume group
- lvcreate: Create logical volume
- lvresize: Resize logical volume
- lvremove: Remove logical volume
- vgremove: Remove volume group
"""
import unittest
from unittest.mock import Mock, MagicMock, patch

from hyper2kvm.core.vmcraft.storage import LVMCreator
from hyper2kvm.core.vmcraft.main import VMCraft


class TestPVCreate(unittest.TestCase):
    """Test pvcreate method."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock()

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    @patch('hyper2kvm.core.vmcraft.storage.run_sudo')
    def test_pvcreate_success(self, mock_run_sudo, mock_has_command):
        """Test successful PV creation."""
        mock_has_command.return_value = True
        mock_run_sudo.return_value = Mock()

        result = LVMCreator.pvcreate(self.logger, ["/dev/nbd0p1"])

        # Should succeed
        self.assertTrue(result["attempted"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["pvs"], ["/dev/nbd0p1"])

        # Verify command
        mock_run_sudo.assert_called_once()
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("pvcreate", cmd)
        self.assertIn("/dev/nbd0p1", cmd)

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    def test_pvcreate_no_lvm_tools(self, mock_has_command):
        """Test PV creation when LVM tools not available."""
        mock_has_command.return_value = False

        result = LVMCreator.pvcreate(self.logger, ["/dev/nbd0p1"])

        self.assertFalse(result["attempted"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "lvm_tools_not_available")

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    def test_pvcreate_no_devices(self, mock_has_command):
        """Test PV creation with empty device list."""
        mock_has_command.return_value = True

        result = LVMCreator.pvcreate(self.logger, [])

        self.assertFalse(result["attempted"])
        self.assertEqual(result["error"], "no_devices_provided")

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    @patch('hyper2kvm.core.vmcraft.storage.run_sudo')
    def test_pvcreate_multiple_devices(self, mock_run_sudo, mock_has_command):
        """Test creating multiple PVs at once."""
        mock_has_command.return_value = True
        mock_run_sudo.return_value = Mock()

        devices = ["/dev/nbd0p1", "/dev/nbd0p2"]
        result = LVMCreator.pvcreate(self.logger, devices)

        self.assertTrue(result["ok"])
        self.assertEqual(result["pvs"], devices)


class TestVGCreate(unittest.TestCase):
    """Test vgcreate method."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock()

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    @patch('hyper2kvm.core.vmcraft.storage.run_sudo')
    def test_vgcreate_success(self, mock_run_sudo, mock_has_command):
        """Test successful VG creation."""
        mock_has_command.return_value = True
        mock_run_sudo.return_value = Mock()

        result = LVMCreator.vgcreate(self.logger, "test_vg", ["/dev/nbd0p1"])

        self.assertTrue(result["attempted"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["vg"], "test_vg")

        # Verify command
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("vgcreate", cmd)
        self.assertIn("test_vg", cmd)
        self.assertIn("/dev/nbd0p1", cmd)

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    def test_vgcreate_no_lvm_tools(self, mock_has_command):
        """Test VG creation when LVM tools not available."""
        mock_has_command.return_value = False

        result = LVMCreator.vgcreate(self.logger, "test_vg", ["/dev/nbd0p1"])

        self.assertFalse(result["attempted"])
        self.assertEqual(result["error"], "lvm_tools_not_available")

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    def test_vgcreate_invalid_parameters(self, mock_has_command):
        """Test VG creation with invalid parameters."""
        mock_has_command.return_value = True

        # Empty VG name
        result = LVMCreator.vgcreate(self.logger, "", ["/dev/nbd0p1"])
        self.assertEqual(result["error"], "invalid_parameters")

        # Empty PV list
        result = LVMCreator.vgcreate(self.logger, "test_vg", [])
        self.assertEqual(result["error"], "invalid_parameters")


class TestLVCreate(unittest.TestCase):
    """Test lvcreate method."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock()

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    @patch('hyper2kvm.core.vmcraft.storage.run_sudo')
    def test_lvcreate_with_size_mb(self, mock_run_sudo, mock_has_command):
        """Test LV creation with size in MB."""
        mock_has_command.return_value = True
        mock_run_sudo.return_value = Mock()

        result = LVMCreator.lvcreate(self.logger, "test_lv", "test_vg", size_mb=1024)

        self.assertTrue(result["ok"])
        self.assertEqual(result["lv"], "/dev/test_vg/test_lv")

        # Verify command
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("lvcreate", cmd)
        self.assertIn("-L", cmd)
        self.assertIn("1024M", cmd)

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    @patch('hyper2kvm.core.vmcraft.storage.run_sudo')
    def test_lvcreate_with_extents(self, mock_run_sudo, mock_has_command):
        """Test LV creation with extents."""
        mock_has_command.return_value = True
        mock_run_sudo.return_value = Mock()

        result = LVMCreator.lvcreate(self.logger, "test_lv", "test_vg", extents="100%FREE")

        self.assertTrue(result["ok"])

        # Verify command uses extents
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("-l", cmd)
        self.assertIn("100%FREE", cmd)

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    def test_lvcreate_no_size_or_extents(self, mock_has_command):
        """Test that size_mb or extents is required."""
        mock_has_command.return_value = True

        result = LVMCreator.lvcreate(self.logger, "test_lv", "test_vg")

        self.assertEqual(result["error"], "size_mb or extents required")

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    def test_lvcreate_mutually_exclusive(self, mock_has_command):
        """Test that size_mb and extents are mutually exclusive."""
        mock_has_command.return_value = True

        result = LVMCreator.lvcreate(
            self.logger, "test_lv", "test_vg",
            size_mb=1024, extents="100%FREE"
        )

        self.assertEqual(result["error"], "size_mb and extents are mutually exclusive")


class TestLVResize(unittest.TestCase):
    """Test lvresize method."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock()

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    @patch('hyper2kvm.core.vmcraft.storage.run_sudo')
    def test_lvresize_success(self, mock_run_sudo, mock_has_command):
        """Test successful LV resize."""
        mock_has_command.return_value = True
        mock_run_sudo.return_value = Mock()

        result = LVMCreator.lvresize(self.logger, "/dev/test_vg/test_lv", 2048)

        self.assertTrue(result["ok"])

        # Verify command
        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("lvresize", cmd)
        self.assertIn("-L", cmd)
        self.assertIn("2048M", cmd)

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    def test_lvresize_invalid_size(self, mock_has_command):
        """Test resize with invalid size."""
        mock_has_command.return_value = True

        result = LVMCreator.lvresize(self.logger, "/dev/test_vg/test_lv", 0)
        self.assertEqual(result["error"], "invalid_parameters")

        result = LVMCreator.lvresize(self.logger, "/dev/test_vg/test_lv", -100)
        self.assertEqual(result["error"], "invalid_parameters")


class TestLVRemove(unittest.TestCase):
    """Test lvremove method."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock()

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    @patch('hyper2kvm.core.vmcraft.storage.run_sudo')
    def test_lvremove_success(self, mock_run_sudo, mock_has_command):
        """Test successful LV removal."""
        mock_has_command.return_value = True
        mock_run_sudo.return_value = Mock()

        result = LVMCreator.lvremove(self.logger, "/dev/test_vg/test_lv")

        self.assertTrue(result["ok"])

        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("lvremove", cmd)
        self.assertIn("/dev/test_vg/test_lv", cmd)

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    @patch('hyper2kvm.core.vmcraft.storage.run_sudo')
    def test_lvremove_with_force(self, mock_run_sudo, mock_has_command):
        """Test LV removal with force flag."""
        mock_has_command.return_value = True
        mock_run_sudo.return_value = Mock()

        result = LVMCreator.lvremove(self.logger, "/dev/test_vg/test_lv", force=True)

        self.assertTrue(result["ok"])

        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("-f", cmd)


class TestVGRemove(unittest.TestCase):
    """Test vgremove method."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock()

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    @patch('hyper2kvm.core.vmcraft.storage.run_sudo')
    def test_vgremove_success(self, mock_run_sudo, mock_has_command):
        """Test successful VG removal."""
        mock_has_command.return_value = True
        mock_run_sudo.return_value = Mock()

        result = LVMCreator.vgremove(self.logger, "test_vg")

        self.assertTrue(result["ok"])

        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("vgremove", cmd)
        self.assertIn("test_vg", cmd)

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    @patch('hyper2kvm.core.vmcraft.storage.run_sudo')
    def test_vgremove_with_force(self, mock_run_sudo, mock_has_command):
        """Test VG removal with force flag."""
        mock_has_command.return_value = True
        mock_run_sudo.return_value = Mock()

        result = LVMCreator.vgremove(self.logger, "test_vg", force=True)

        self.assertTrue(result["ok"])

        cmd = mock_run_sudo.call_args[0][1]
        self.assertIn("-f", cmd)


class TestLVMWorkflows(unittest.TestCase):
    """Test complete LVM workflows."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock()

    @patch('hyper2kvm.core.vmcraft.storage._has_command')
    @patch('hyper2kvm.core.vmcraft.storage.run_sudo')
    def test_lvm_stack_creation_workflow(self, mock_run_sudo, mock_has_command):
        """Test complete LVM stack creation."""
        mock_has_command.return_value = True
        mock_run_sudo.return_value = Mock()

        # Create PV
        pv_result = LVMCreator.pvcreate(self.logger, ["/dev/nbd0p1"])
        self.assertTrue(pv_result["ok"])

        # Create VG
        vg_result = LVMCreator.vgcreate(self.logger, "test_vg", ["/dev/nbd0p1"])
        self.assertTrue(vg_result["ok"])

        # Create LV
        lv_result = LVMCreator.lvcreate(self.logger, "test_lv", "test_vg", extents="100%FREE")
        self.assertTrue(lv_result["ok"])
        self.assertEqual(lv_result["lv"], "/dev/test_vg/test_lv")

        # Resize LV
        resize_result = LVMCreator.lvresize(self.logger, "/dev/test_vg/test_lv", 2048)
        self.assertTrue(resize_result["ok"])

        # Remove LV
        lv_remove_result = LVMCreator.lvremove(self.logger, "/dev/test_vg/test_lv", force=True)
        self.assertTrue(lv_remove_result["ok"])

        # Remove VG
        vg_remove_result = LVMCreator.vgremove(self.logger, "test_vg", force=True)
        self.assertTrue(vg_remove_result["ok"])


class TestVMCraftLVMWrappers(unittest.TestCase):
    """Test VMCraft LVM creation wrapper methods."""

    @patch('hyper2kvm.core.vmcraft.storage.LVMCreator.pvcreate')
    def test_vmcraft_pvcreate(self, mock_pvcreate):
        """Test VMCraft pvcreate wrapper."""
        vmcraft = VMCraft()
        mock_pvcreate.return_value = {"ok": True, "pvs": ["/dev/nbd0p1"]}

        result = vmcraft.pvcreate(["/dev/nbd0p1"])

        mock_pvcreate.assert_called_once()
        self.assertTrue(result["ok"])

    @patch('hyper2kvm.core.vmcraft.storage.LVMCreator.vgcreate')
    def test_vmcraft_vgcreate(self, mock_vgcreate):
        """Test VMCraft vgcreate wrapper."""
        vmcraft = VMCraft()
        mock_vgcreate.return_value = {"ok": True, "vg": "test_vg"}

        result = vmcraft.vgcreate("test_vg", ["/dev/nbd0p1"])

        mock_vgcreate.assert_called_once()
        self.assertTrue(result["ok"])

    @patch('hyper2kvm.core.vmcraft.storage.LVMCreator.lvcreate')
    def test_vmcraft_lvcreate(self, mock_lvcreate):
        """Test VMCraft lvcreate wrapper."""
        vmcraft = VMCraft()
        mock_lvcreate.return_value = {"ok": True, "lv": "/dev/test_vg/test_lv"}

        result = vmcraft.lvcreate("test_lv", "test_vg", size_mb=1024)

        mock_lvcreate.assert_called_once()
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
