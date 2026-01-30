# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test VMCraft mount fallback strategies.

Tests the mount_with_fallback method that tries multiple mount strategies
to handle damaged or problematic filesystems.
"""
import logging
import unittest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path

from hyper2kvm.core.vmcraft.mount import MountManager
from hyper2kvm.core.vmcraft.main import VMCraft


class TestMountFallback(unittest.TestCase):
    """Test mount fallback strategies."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock()
        self.mount_root = Path("/tmp/test-mount-root")
        self.manager = MountManager(self.logger, self.mount_root)

    @patch('hyper2kvm.core.vmcraft.mount.MountManager.mount')
    @patch('hyper2kvm.core.vmcraft.mount.MountManager._detect_fstype')
    def test_mount_fallback_normal_mount_succeeds(self, mock_detect, mock_mount):
        """Test fallback when normal mount succeeds immediately."""
        mock_detect.return_value = "ext4"
        mock_mount.return_value = None  # Success

        result = self.manager.mount_with_fallback("/dev/nbd0p1", "/")

        # Should succeed on first strategy
        self.assertTrue(result)

        # Should only try normal mount
        mock_mount.assert_called_once_with("/dev/nbd0p1", "/", readonly=False)

    @patch('hyper2kvm.core.vmcraft.mount.run_sudo')
    @patch('hyper2kvm.core.vmcraft.mount.MountManager.mount')
    @patch('hyper2kvm.core.vmcraft.mount.MountManager._detect_fstype')
    def test_mount_fallback_second_strategy(self, mock_detect, mock_mount, mock_run_sudo):
        """Test fallback to second strategy."""
        mock_detect.return_value = "ext4"

        # First strategy (normal mount) fails
        mock_mount.side_effect = RuntimeError("Normal mount failed")

        # Second strategy (ro,norecovery) succeeds
        mock_run_sudo.return_value = Mock()

        result = self.manager.mount_with_fallback("/dev/nbd0p1", "/")

        # Should succeed
        self.assertTrue(result)

        # Should have tried normal mount
        mock_mount.assert_called_once()

        # Should have tried ro,norecovery
        self.assertTrue(any(
            "ro,norecovery" in str(call_args)
            for call_args in mock_run_sudo.call_args_list
        ))

    @patch('hyper2kvm.core.vmcraft.mount.run_sudo')
    @patch('hyper2kvm.core.vmcraft.mount.MountManager.mount')
    @patch('hyper2kvm.core.vmcraft.mount.MountManager._detect_fstype')
    def test_mount_fallback_all_strategies_fail(self, mock_detect, mock_mount, mock_run_sudo):
        """Test when all fallback strategies fail."""
        mock_detect.return_value = "ext4"

        # All strategies fail
        mock_mount.side_effect = RuntimeError("Mount failed")
        mock_run_sudo.side_effect = Exception("Mount failed")

        result = self.manager.mount_with_fallback("/dev/nbd0p1", "/")

        # Should fail
        self.assertFalse(result)

        # Should have tried multiple strategies
        self.assertGreater(mock_run_sudo.call_count, 1)

    @patch('hyper2kvm.core.vmcraft.mount.run_sudo')
    @patch('hyper2kvm.core.vmcraft.mount.MountManager.mount')
    @patch('hyper2kvm.core.vmcraft.mount.MountManager._detect_fstype')
    def test_mount_fallback_ntfs_has_force_option(self, mock_detect, mock_mount, mock_run_sudo):
        """Test that NTFS has force mount as fallback strategy."""
        mock_detect.return_value = "ntfs"

        # First three strategies fail
        mock_mount.side_effect = RuntimeError("Mount failed")
        mock_run_sudo.side_effect = [
            Exception("ro,norecovery failed"),
            Exception("ro,noload failed"),
            Mock(),  # force succeeds
        ]

        result = self.manager.mount_with_fallback("/dev/nbd0p1", "/")

        # Should succeed with force option
        self.assertTrue(result)

        # Verify force option was tried
        force_called = any(
            "force" in str(call_args)
            for call_args in mock_run_sudo.call_args_list
        )
        self.assertTrue(force_called, "NTFS force option not tried")

    @patch('hyper2kvm.core.vmcraft.mount.run_sudo')
    @patch('hyper2kvm.core.vmcraft.mount.MountManager.mount')
    @patch('hyper2kvm.core.vmcraft.mount.MountManager._detect_fstype')
    def test_mount_fallback_creates_mountpoint(self, mock_detect, mock_mount, mock_run_sudo):
        """Test that fallback creates mountpoint directory."""
        mock_detect.return_value = "ext4"
        mock_mount.side_effect = RuntimeError("Normal mount failed")
        mock_run_sudo.return_value = Mock()

        # Use a unique mount path
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mount_root = Path(tmpdir) / "mount-root"
            manager = MountManager(self.logger, mount_root)

            result = manager.mount_with_fallback("/dev/nbd0p1", "/test", fstype="ext4")

            # Mountpoint should be created
            expected_path = mount_root / "test"
            self.assertTrue(expected_path.exists())

    @patch('hyper2kvm.core.vmcraft.mount.run_sudo')
    @patch('hyper2kvm.core.vmcraft.mount.MountManager.mount')
    @patch('hyper2kvm.core.vmcraft.mount.MountManager._detect_fstype')
    def test_mount_fallback_with_explicit_fstype(self, mock_detect, mock_mount, mock_run_sudo):
        """Test fallback with explicitly provided filesystem type."""
        # When fstype is provided, _detect_fstype should not be called
        # However, the first strategy calls mount() which may detect fstype internally
        mock_mount.side_effect = RuntimeError("Normal mount failed")
        mock_run_sudo.return_value = Mock()

        result = self.manager.mount_with_fallback(
            "/dev/nbd0p1", "/", fstype="btrfs"
        )

        # First strategy tries normal mount (which may call _detect_fstype internally)
        # But mount_with_fallback itself should not call _detect_fstype
        # if fstype is provided (line 263-264 in mount.py)
        # The detection only happens if fstype is None

        # Should use provided fstype in mount command for fallback strategies
        self.assertTrue(result)
        mount_command_called = any(
            "btrfs" in str(call_args)
            for call_args in mock_run_sudo.call_args_list
        )
        self.assertTrue(mount_command_called)

    @patch('hyper2kvm.core.vmcraft.mount.run_sudo')
    @patch('hyper2kvm.core.vmcraft.mount.MountManager.mount')
    @patch('hyper2kvm.core.vmcraft.mount.MountManager._detect_fstype')
    def test_mount_fallback_logs_strategies(self, mock_detect, mock_mount, mock_run_sudo):
        """Test that fallback logs each strategy attempt."""
        mock_detect.return_value = "ext4"
        mock_mount.side_effect = RuntimeError("Normal mount failed")
        mock_run_sudo.side_effect = [
            Exception("Strategy 1 failed"),
            Mock(),  # Strategy 2 succeeds
        ]

        result = self.manager.mount_with_fallback("/dev/nbd0p1", "/")

        # Should log debug messages for each strategy
        debug_calls = [
            call_args for call_args in self.logger.debug.call_args_list
            if "strategy" in str(call_args).lower()
        ]
        self.assertGreater(len(debug_calls), 0, "No strategy debug messages logged")

        # Should log info on success
        info_calls = [
            call_args for call_args in self.logger.info.call_args_list
            if "succeeded" in str(call_args).lower()
        ]
        self.assertGreater(len(info_calls), 0, "No success info message logged")


class TestVMCraftMountFallbackWrapper(unittest.TestCase):
    """Test VMCraft's mount_with_fallback wrapper."""

    def test_vmcraft_mount_with_fallback(self):
        """Test that VMCraft.mount_with_fallback delegates correctly."""
        vmcraft = VMCraft()

        # Create and attach mock mount manager
        mock_mount_manager = Mock()
        vmcraft._mount_manager = mock_mount_manager

        mock_mount_manager.mount_with_fallback.return_value = True

        result = vmcraft.mount_with_fallback("/dev/nbd0p1", "/", fstype="ext4")

        # Verify delegation
        mock_mount_manager.mount_with_fallback.assert_called_once_with(
            "/dev/nbd0p1", "/", "ext4"
        )
        self.assertTrue(result)

    def test_vmcraft_mount_with_fallback_not_launched(self):
        """Test that mount_with_fallback raises if not launched."""
        vmcraft = VMCraft()
        vmcraft._mount_manager = None

        with self.assertRaises(RuntimeError) as ctx:
            vmcraft.mount_with_fallback("/dev/nbd0p1", "/")

        self.assertIn("Not launched", str(ctx.exception))


class TestMountFallbackStrategies(unittest.TestCase):
    """Test specific fallback strategies in detail."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock()
        self.mount_root = Path("/tmp/test-mount-root")
        self.manager = MountManager(self.logger, self.mount_root)

    @patch('hyper2kvm.core.vmcraft.mount.run_sudo')
    @patch('hyper2kvm.core.vmcraft.mount.MountManager.mount')
    @patch('hyper2kvm.core.vmcraft.mount.MountManager._detect_fstype')
    def test_strategy_order(self, mock_detect, mock_mount, mock_run_sudo):
        """Test that strategies are tried in correct order."""
        mock_detect.return_value = "ext4"

        # Track which strategies were tried
        strategies_tried = []

        def track_strategy(*args, **kwargs):
            cmd = args[1] if len(args) > 1 else []
            if "-o" in cmd:
                opts_idx = cmd.index("-o")
                if opts_idx + 1 < len(cmd):
                    strategies_tried.append(cmd[opts_idx + 1])
            raise Exception("Force failure")

        mock_mount.side_effect = RuntimeError("Normal mount failed")
        mock_run_sudo.side_effect = track_strategy

        result = self.manager.mount_with_fallback("/dev/nbd0p1", "/")

        # Should fail (all strategies fail)
        self.assertFalse(result)

        # Verify strategies were tried in order
        # Expected order: ro,norecovery -> ro,noload
        self.assertIn("ro,norecovery", strategies_tried)
        self.assertIn("ro,noload", strategies_tried)

        # ro,norecovery should be tried before ro,noload
        if "ro,norecovery" in strategies_tried and "ro,noload" in strategies_tried:
            idx_norecovery = strategies_tried.index("ro,norecovery")
            idx_noload = strategies_tried.index("ro,noload")
            self.assertLess(idx_norecovery, idx_noload,
                          "Strategies not tried in correct order")


if __name__ == "__main__":
    unittest.main()
