# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test VMCraft Augeas configuration management APIs.

Tests the 10 Augeas methods:
- aug_init: Initialize Augeas
- aug_close: Close Augeas
- aug_get: Get configuration value
- aug_set: Set configuration value
- aug_save: Save changes to disk
- aug_match: Match paths by pattern
- aug_insert: Insert new node
- aug_rm: Remove nodes
- aug_defvar: Define variable
- aug_defnode: Define node variable
"""
import unittest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path

from hyper2kvm.core.vmcraft.main import VMCraft


class TestAugInit(unittest.TestCase):
    """Test aug_init method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_init_success(self, mock_augeas_module):
        """Test successful Augeas initialization."""
        # Set up VMCraft as launched with Augeas manager
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        # Mock the Augeas instance
        mock_aug_instance = Mock()
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        # Initialize Augeas
        self.vmcraft.aug_init()

        # Verify Augeas was initialized
        mock_augeas_module.Augeas.assert_called_once_with(root="/tmp/test-root", flags=0)

    def test_aug_init_not_launched(self):
        """Test that aug_init raises if not launched."""
        self.vmcraft._augeas = None

        with self.assertRaises(RuntimeError) as ctx:
            self.vmcraft.aug_init()

        self.assertIn("Not launched", str(ctx.exception))

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', False)
    def test_aug_init_library_not_available(self):
        """Test aug_init when Augeas library not available."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        with self.assertRaises(RuntimeError) as ctx:
            self.vmcraft.aug_init()

        self.assertIn("Augeas library not available", str(ctx.exception))

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_init_with_flags(self, mock_augeas_module):
        """Test Augeas initialization with flags."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        # Initialize with SAVE_BACKUP flag (value 1)
        self.vmcraft.aug_init(flags=1)

        mock_augeas_module.Augeas.assert_called_once_with(root="/tmp/test-root", flags=1)


class TestAugClose(unittest.TestCase):
    """Test aug_close method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_close_success(self, mock_augeas_module):
        """Test successful Augeas close."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        # Initialize and close
        self.vmcraft.aug_init()
        self.vmcraft.aug_close()

        # Verify close was called
        mock_aug_instance.close.assert_called_once()

    def test_aug_close_not_launched(self):
        """Test that aug_close raises if not launched."""
        self.vmcraft._augeas = None

        with self.assertRaises(RuntimeError) as ctx:
            self.vmcraft.aug_close()

        self.assertIn("Not launched", str(ctx.exception))


class TestAugGet(unittest.TestCase):
    """Test aug_get method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_get_success(self, mock_augeas_module):
        """Test getting configuration value."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_aug_instance.get.return_value = "/dev/sda1"
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        self.vmcraft.aug_init()
        value = self.vmcraft.aug_get("/files/etc/fstab/1/spec")

        self.assertEqual(value, "/dev/sda1")
        mock_aug_instance.get.assert_called_once_with("/files/etc/fstab/1/spec")

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_get_nonexistent_path(self, mock_augeas_module):
        """Test getting nonexistent path returns None."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_aug_instance.get.return_value = None
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        self.vmcraft.aug_init()
        value = self.vmcraft.aug_get("/files/etc/fstab/999/spec")

        self.assertIsNone(value)

    def test_aug_get_not_launched(self):
        """Test that aug_get raises if not launched."""
        self.vmcraft._augeas = None

        with self.assertRaises(RuntimeError) as ctx:
            self.vmcraft.aug_get("/files/etc/fstab/1/spec")

        self.assertIn("Not launched", str(ctx.exception))


class TestAugSet(unittest.TestCase):
    """Test aug_set method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_set_success(self, mock_augeas_module):
        """Test setting configuration value."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        self.vmcraft.aug_init()
        self.vmcraft.aug_set("/files/etc/fstab/1/dump", "0")

        mock_aug_instance.set.assert_called_once_with("/files/etc/fstab/1/dump", "0")

    def test_aug_set_not_launched(self):
        """Test that aug_set raises if not launched."""
        self.vmcraft._augeas = None

        with self.assertRaises(RuntimeError) as ctx:
            self.vmcraft.aug_set("/files/etc/fstab/1/dump", "0")

        self.assertIn("Not launched", str(ctx.exception))


class TestAugSave(unittest.TestCase):
    """Test aug_save method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_save_success(self, mock_augeas_module):
        """Test saving Augeas changes."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        self.vmcraft.aug_init()
        self.vmcraft.aug_save()

        mock_aug_instance.save.assert_called_once()

    def test_aug_save_not_launched(self):
        """Test that aug_save raises if not launched."""
        self.vmcraft._augeas = None

        with self.assertRaises(RuntimeError) as ctx:
            self.vmcraft.aug_save()

        self.assertIn("Not launched", str(ctx.exception))


class TestAugMatch(unittest.TestCase):
    """Test aug_match method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_match_success(self, mock_augeas_module):
        """Test matching Augeas paths."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_aug_instance.match.return_value = [
            "/files/etc/fstab/1",
            "/files/etc/fstab/2",
            "/files/etc/fstab/3"
        ]
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        self.vmcraft.aug_init()
        matches = self.vmcraft.aug_match("/files/etc/fstab/*")

        self.assertEqual(len(matches), 3)
        self.assertIn("/files/etc/fstab/1", matches)

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_match_no_results(self, mock_augeas_module):
        """Test matching with no results."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_aug_instance.match.return_value = []
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        self.vmcraft.aug_init()
        matches = self.vmcraft.aug_match("/files/etc/nonexistent/*")

        self.assertEqual(matches, [])

    def test_aug_match_not_launched(self):
        """Test that aug_match raises if not launched."""
        self.vmcraft._augeas = None

        with self.assertRaises(RuntimeError) as ctx:
            self.vmcraft.aug_match("/files/etc/fstab/*")

        self.assertIn("Not launched", str(ctx.exception))


class TestAugInsert(unittest.TestCase):
    """Test aug_insert method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_insert_before(self, mock_augeas_module):
        """Test inserting node before existing path."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        self.vmcraft.aug_init()
        self.vmcraft.aug_insert("/files/etc/fstab/1", "01", before=True)

        mock_aug_instance.insert.assert_called_once_with("/files/etc/fstab/1", "01", True)

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_insert_after(self, mock_augeas_module):
        """Test inserting node after existing path."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        self.vmcraft.aug_init()
        self.vmcraft.aug_insert("/files/etc/fstab/1", "02", before=False)

        mock_aug_instance.insert.assert_called_once_with("/files/etc/fstab/1", "02", False)

    def test_aug_insert_not_launched(self):
        """Test that aug_insert raises if not launched."""
        self.vmcraft._augeas = None

        with self.assertRaises(RuntimeError) as ctx:
            self.vmcraft.aug_insert("/files/etc/fstab/1", "01", before=True)

        self.assertIn("Not launched", str(ctx.exception))


class TestAugRm(unittest.TestCase):
    """Test aug_rm method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_rm_success(self, mock_augeas_module):
        """Test removing nodes."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_aug_instance.remove.return_value = 3
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        self.vmcraft.aug_init()
        count = self.vmcraft.aug_rm("/files/etc/fstab/#comment")

        self.assertEqual(count, 3)
        mock_aug_instance.remove.assert_called_once_with("/files/etc/fstab/#comment")

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_rm_no_matches(self, mock_augeas_module):
        """Test removing with no matches."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_aug_instance.remove.return_value = 0
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        self.vmcraft.aug_init()
        count = self.vmcraft.aug_rm("/files/etc/nonexistent/*")

        self.assertEqual(count, 0)

    def test_aug_rm_not_launched(self):
        """Test that aug_rm raises if not launched."""
        self.vmcraft._augeas = None

        with self.assertRaises(RuntimeError) as ctx:
            self.vmcraft.aug_rm("/files/etc/fstab/#comment")

        self.assertIn("Not launched", str(ctx.exception))


class TestAugDefvar(unittest.TestCase):
    """Test aug_defvar method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_defvar_success(self, mock_augeas_module):
        """Test defining Augeas variable."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        self.vmcraft.aug_init()
        self.vmcraft.aug_defvar("root", "/files/etc/fstab/*[file='/']")

        mock_aug_instance.defvar.assert_called_once_with("root", "/files/etc/fstab/*[file='/']")

    def test_aug_defvar_not_launched(self):
        """Test that aug_defvar raises if not launched."""
        self.vmcraft._augeas = None

        with self.assertRaises(RuntimeError) as ctx:
            self.vmcraft.aug_defvar("root", "/files/etc/fstab/*[file='/']")

        self.assertIn("Not launched", str(ctx.exception))


class TestAugDefnode(unittest.TestCase):
    """Test aug_defnode method."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_defnode_existing(self, mock_augeas_module):
        """Test defining node variable for existing node."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_aug_instance.defnode.return_value = (1, False)  # 1 match, not created
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        self.vmcraft.aug_init()
        count, created = self.vmcraft.aug_defnode("tmp", "/files/etc/fstab/*[file='/tmp']", None)

        self.assertEqual(count, 1)
        self.assertFalse(created)
        mock_aug_instance.defnode.assert_called_once_with("tmp", "/files/etc/fstab/*[file='/tmp']", None)

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_aug_defnode_created(self, mock_augeas_module):
        """Test defining node variable that creates new node."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self.vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_aug_instance.defnode.return_value = (1, True)  # Node was created
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        self.vmcraft.aug_init()
        count, created = self.vmcraft.aug_defnode("newnode", "/files/etc/fstab/99", "value")

        self.assertEqual(count, 1)
        self.assertTrue(created)

    def test_aug_defnode_not_launched(self):
        """Test that aug_defnode raises if not launched."""
        self.vmcraft._augeas = None

        with self.assertRaises(RuntimeError) as ctx:
            self.vmcraft.aug_defnode("tmp", "/files/etc/fstab/*[file='/tmp']", None)

        self.assertIn("Not launched", str(ctx.exception))


class TestAugeasWorkflows(unittest.TestCase):
    """Test complete Augeas workflows."""

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_fstab_modification_workflow(self, mock_augeas_module):
        """Test modifying fstab entry."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        vmcraft = VMCraft()
        vmcraft._augeas = AugeasManager(Mock(), "/tmp/test-root")

        mock_aug_instance = Mock()
        mock_aug_instance.match.return_value = ["/files/etc/fstab/1"]
        mock_aug_instance.get.return_value = "/dev/sda1"
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        # Initialize
        vmcraft.aug_init()

        # Find entries
        entries = vmcraft.aug_match("/files/etc/fstab/*")
        self.assertEqual(len(entries), 1)

        # Get current value
        device = vmcraft.aug_get("/files/etc/fstab/1/spec")
        self.assertEqual(device, "/dev/sda1")

        # Modify dump value
        vmcraft.aug_set("/files/etc/fstab/1/dump", "0")

        # Save
        vmcraft.aug_save()

        # Close
        vmcraft.aug_close()

        # Verify calls
        mock_aug_instance.set.assert_called_once_with("/files/etc/fstab/1/dump", "0")
        mock_aug_instance.save.assert_called_once()
        mock_aug_instance.close.assert_called_once()

    @patch('hyper2kvm.core.vmcraft.augeas_mgr.HAS_AUGEAS', True)
    @patch('hyper2kvm.core.vmcraft.augeas_mgr.augeas')
    def test_context_manager_workflow(self, mock_augeas_module):
        """Test using Augeas manager as context manager."""
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager

        mock_aug_instance = Mock()
        mock_augeas_module.Augeas.return_value = mock_aug_instance

        # Use context manager
        aug_mgr = AugeasManager(Mock(), "/tmp/test-root")

        with aug_mgr:
            # Should be initialized
            self.assertTrue(aug_mgr.is_initialized())

        # Should be closed after exiting context
        mock_aug_instance.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
