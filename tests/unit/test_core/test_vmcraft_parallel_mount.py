# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test VMCraft parallel mount operations.

Tests the parallel mounting capability added to improve performance
on multi-partition VMs (2-3x speedup).
"""
import time
import unittest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path

from hyper2kvm.core.vmcraft.mount import MountManager


class TestParallelMount(unittest.TestCase):
    """Test parallel mount operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock()
        self.mount_root = Path("/tmp/test-mount-root")
        self.manager = MountManager(self.logger, self.mount_root)

    @patch('hyper2kvm.core.vmcraft.mount.MountManager.mount')
    def test_mount_all_parallel_success(self, mock_mount):
        """Test successful parallel mounting of multiple devices."""
        devices = [
            ("/dev/nbd0p1", "/boot"),
            ("/dev/nbd0p2", "/"),
            ("/dev/nbd0p3", "/home"),
        ]

        # Mount should succeed for all devices
        mock_mount.return_value = None

        results = self.manager.mount_all_parallel(devices, max_workers=3, readonly=True)

        # All mounts should succeed
        self.assertEqual(len(results), 3)
        self.assertTrue(results["/boot"])
        self.assertTrue(results["/"])
        self.assertTrue(results["/home"])

        # Verify mount was called for each device
        self.assertEqual(mock_mount.call_count, 3)

    @patch('hyper2kvm.core.vmcraft.mount.MountManager.mount')
    def test_mount_all_parallel_partial_failure(self, mock_mount):
        """Test parallel mounting with some failures."""
        devices = [
            ("/dev/nbd0p1", "/boot"),
            ("/dev/nbd0p2", "/"),
            ("/dev/nbd0p3", "/home"),
        ]

        # Second mount fails
        def mock_mount_side_effect(device, mountpoint, readonly=True):
            if device == "/dev/nbd0p2":
                raise RuntimeError("Mount failed")

        mock_mount.side_effect = mock_mount_side_effect

        results = self.manager.mount_all_parallel(devices, max_workers=3, readonly=True)

        # Two should succeed, one should fail
        self.assertEqual(len(results), 3)
        self.assertTrue(results["/boot"])
        self.assertFalse(results["/"])
        self.assertTrue(results["/home"])

    @patch('hyper2kvm.core.vmcraft.mount.MountManager.mount')
    def test_mount_all_parallel_concurrency(self, mock_mount):
        """Test that mounts actually run in parallel."""
        devices = [
            ("/dev/nbd0p1", "/boot"),
            ("/dev/nbd0p2", "/"),
            ("/dev/nbd0p3", "/home"),
            ("/dev/nbd0p4", "/var"),
        ]

        # Each mount takes 0.2 seconds
        def slow_mount(device, mountpoint, readonly=True):
            time.sleep(0.2)

        mock_mount.side_effect = slow_mount

        start = time.time()
        results = self.manager.mount_all_parallel(devices, max_workers=4, readonly=True)
        duration = time.time() - start

        # With 4 workers and 4 devices taking 0.2s each:
        # Sequential would take ~0.8s
        # Parallel should take ~0.2s (plus overhead)
        # Allow up to 0.5s for parallel execution (generous margin for CI)
        self.assertLess(duration, 0.5, f"Parallel mount took {duration:.2f}s, expected < 0.5s")

        # All should succeed
        self.assertEqual(len(results), 4)
        self.assertTrue(all(results.values()))

    @patch('hyper2kvm.core.vmcraft.mount.MountManager.mount')
    def test_mount_all_parallel_respects_max_workers(self, mock_mount):
        """Test that max_workers parameter is respected."""
        devices = [
            ("/dev/nbd0p1", "/p1"),
            ("/dev/nbd0p2", "/p2"),
            ("/dev/nbd0p3", "/p3"),
            ("/dev/nbd0p4", "/p4"),
            ("/dev/nbd0p5", "/p5"),
            ("/dev/nbd0p6", "/p6"),
        ]

        # Track concurrent executions
        concurrent_count = 0
        max_concurrent = 0
        lock = __import__('threading').Lock()

        def track_concurrency(device, mountpoint, readonly=True):
            nonlocal concurrent_count, max_concurrent
            with lock:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
            time.sleep(0.1)
            with lock:
                concurrent_count -= 1

        mock_mount.side_effect = track_concurrency

        results = self.manager.mount_all_parallel(devices, max_workers=2, readonly=True)

        # Max concurrent should not exceed max_workers
        self.assertLessEqual(max_concurrent, 2, f"Max concurrent {max_concurrent} exceeded max_workers=2")

        # All should succeed
        self.assertTrue(all(results.values()))

    @patch('hyper2kvm.core.vmcraft.mount.MountManager.mount')
    def test_mount_single_helper(self, mock_mount):
        """Test _mount_single helper method."""
        # Successful mount
        mock_mount.return_value = None
        result = self.manager._mount_single("/dev/nbd0p1", "/boot", readonly=True)
        self.assertTrue(result)

        # Failed mount
        mock_mount.side_effect = RuntimeError("Mount failed")
        result = self.manager._mount_single("/dev/nbd0p2", "/", readonly=False)
        self.assertFalse(result)

    def test_mount_all_parallel_empty_list(self):
        """Test parallel mount with empty device list."""
        results = self.manager.mount_all_parallel([], max_workers=4, readonly=True)
        self.assertEqual(results, {})

    @patch('hyper2kvm.core.vmcraft.mount.MountManager.mount')
    def test_mount_all_parallel_single_device(self, mock_mount):
        """Test parallel mount with single device."""
        devices = [("/dev/nbd0p1", "/")]

        mock_mount.return_value = None

        results = self.manager.mount_all_parallel(devices, max_workers=4, readonly=True)

        self.assertEqual(len(results), 1)
        self.assertTrue(results["/"])


class TestVMCraftParallelMountWrapper(unittest.TestCase):
    """Test VMCraft's mount_all_parallel wrapper."""

    def test_vmcraft_mount_all_parallel(self):
        """Test that VMCraft.mount_all_parallel delegates correctly."""
        from hyper2kvm.core.vmcraft.main import VMCraft

        vmcraft = VMCraft()

        # Create a mock mount manager and attach it
        mock_mount_manager = Mock()
        vmcraft._mount_manager = mock_mount_manager

        devices = [("/dev/nbd0p1", "/boot"), ("/dev/nbd0p2", "/")]
        mock_mount_manager.mount_all_parallel.return_value = {"/boot": True, "/": True}

        results = vmcraft.mount_all_parallel(devices, max_workers=2, readonly=True)

        # Verify delegation (arguments passed positionally)
        mock_mount_manager.mount_all_parallel.assert_called_once_with(
            devices, 2, True
        )
        self.assertEqual(results, {"/boot": True, "/": True})

    def test_vmcraft_mount_all_parallel_not_launched(self):
        """Test that mount_all_parallel raises if not launched."""
        from hyper2kvm.core.vmcraft.main import VMCraft

        vmcraft = VMCraft()
        vmcraft._mount_manager = None

        with self.assertRaises(RuntimeError) as ctx:
            vmcraft.mount_all_parallel([("/dev/nbd0p1", "/")])

        self.assertIn("Not launched", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
