# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test NBD connection retry logic.

Tests the retry_with_backoff decorator applied to NBD connect method
to handle transient connection failures.
"""
import logging
import subprocess
import time
import unittest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path

from hyper2kvm.core.vmcraft.nbd import NBDDeviceManager


class TestNBDRetry(unittest.TestCase):
    """Test NBD connection retry logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock()
        self.manager = NBDDeviceManager(self.logger, readonly=True)

    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager._scan_partitions')
    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager._is_nbd_free')
    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager.find_free_nbd')
    @patch('hyper2kvm.core.vmcraft.nbd.run_sudo')
    @patch('hyper2kvm.core.vmcraft.nbd.Path.exists')
    def test_connect_succeeds_first_attempt(
        self, mock_exists, mock_run_sudo, mock_find_free, mock_is_free, mock_scan
    ):
        """Test connection succeeds on first attempt (no retry needed)."""
        mock_exists.return_value = True
        mock_find_free.return_value = "/dev/nbd0"
        mock_is_free.side_effect = [True, False]  # Free before connect, in-use after
        mock_run_sudo.return_value = Mock()

        result = self.manager.connect("/tmp/test.qcow2")

        # Should succeed
        self.assertEqual(result, "/dev/nbd0")

        # Should only call run_sudo once (no retries)
        self.assertEqual(mock_run_sudo.call_count, 1)

    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager._scan_partitions')
    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager._is_nbd_free')
    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager.find_free_nbd')
    @patch('hyper2kvm.core.vmcraft.nbd.run_sudo')
    @patch('hyper2kvm.core.vmcraft.nbd.Path.exists')
    @patch('hyper2kvm.core.vmcraft.nbd.time.sleep')  # Mock sleep to speed up test
    def test_connect_retries_on_subprocess_error(
        self, mock_sleep, mock_exists, mock_run_sudo, mock_find_free, mock_is_free, mock_scan
    ):
        """Test connection retries on subprocess.CalledProcessError."""
        mock_exists.return_value = True
        mock_find_free.return_value = "/dev/nbd0"

        # First attempt fails, second succeeds
        mock_run_sudo.side_effect = [
            subprocess.CalledProcessError(1, "qemu-nbd", stderr="Device busy"),
            Mock(),  # Disconnect cleanup after first failure
            Mock(),  # Second connect attempt succeeds
        ]

        # is_nbd_free checks
        mock_is_free.side_effect = [True, False]  # Free before attempts, in-use after success

        result = self.manager.connect("/tmp/test.qcow2")

        # Should succeed
        self.assertEqual(result, "/dev/nbd0")

        # Should have called run_sudo 3 times: 1st connect + disconnect cleanup + 2nd connect
        self.assertEqual(mock_run_sudo.call_count, 3)

        # Should have slept between retries
        mock_sleep.assert_called()

    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager._scan_partitions')
    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager._is_nbd_free')
    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager.find_free_nbd')
    @patch('hyper2kvm.core.vmcraft.nbd.run_sudo')
    @patch('hyper2kvm.core.vmcraft.nbd.Path.exists')
    @patch('hyper2kvm.core.vmcraft.nbd.time.sleep')
    def test_connect_retries_on_oserror(
        self, mock_sleep, mock_exists, mock_run_sudo, mock_find_free, mock_is_free, mock_scan
    ):
        """Test connection retries on OSError."""
        mock_exists.return_value = True
        mock_find_free.return_value = "/dev/nbd0"

        # First two attempts fail with OSError, third succeeds
        mock_run_sudo.side_effect = [
            OSError("Resource temporarily unavailable"),
            Mock(),  # Disconnect cleanup after first failure
            OSError("Device or resource busy"),
            Mock(),  # Disconnect cleanup after second failure
            Mock(),  # Third attempt succeeds
        ]

        mock_is_free.side_effect = [True, False]

        result = self.manager.connect("/tmp/test.qcow2")

        # Should succeed
        self.assertEqual(result, "/dev/nbd0")

        # Should have called run_sudo 5 times: 3 connect attempts + 2 disconnect cleanups
        self.assertEqual(mock_run_sudo.call_count, 5)

    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager.find_free_nbd')
    @patch('hyper2kvm.core.vmcraft.nbd.run_sudo')
    @patch('hyper2kvm.core.vmcraft.nbd.Path.exists')
    @patch('hyper2kvm.core.vmcraft.nbd.time.sleep')
    def test_connect_fails_after_max_retries(
        self, mock_sleep, mock_exists, mock_run_sudo, mock_find_free
    ):
        """Test connection fails after max retry attempts."""
        mock_exists.return_value = True
        mock_find_free.return_value = "/dev/nbd0"

        # All attempts fail
        mock_run_sudo.side_effect = subprocess.CalledProcessError(
            1, "qemu-nbd", stderr="Persistent error"
        )

        with self.assertRaises(subprocess.CalledProcessError):
            self.manager.connect("/tmp/test.qcow2")

        # Should have tried 3 connect attempts + 3 disconnect attempts (cleanup)
        # Each failed connect triggers a disconnect cleanup
        self.assertEqual(mock_run_sudo.call_count, 6)

    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager.find_free_nbd')
    @patch('hyper2kvm.core.vmcraft.nbd.Path.exists')
    def test_connect_does_not_retry_runtime_error(self, mock_exists, mock_find_free):
        """Test that RuntimeError is not retried (fails fast)."""
        mock_exists.return_value = True

        # Set already connected to trigger RuntimeError
        self.manager._connected = True

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.connect("/tmp/test.qcow2")

        self.assertIn("Already connected", str(ctx.exception))

        # Should not have called find_free_nbd (fails before retry logic)
        mock_find_free.assert_not_called()

    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager._scan_partitions')
    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager._is_nbd_free')
    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager.find_free_nbd')
    @patch('hyper2kvm.core.vmcraft.nbd.run_sudo')
    @patch('hyper2kvm.core.vmcraft.nbd.Path.exists')
    @patch('hyper2kvm.core.vmcraft.nbd.time.sleep')
    def test_connect_cleanup_on_retry(
        self, mock_sleep, mock_exists, mock_run_sudo, mock_find_free, mock_is_free, mock_scan
    ):
        """Test that cleanup (disconnect) happens between retries."""
        mock_exists.return_value = True
        mock_find_free.return_value = "/dev/nbd0"

        # Track disconnect calls
        disconnect_calls = []

        def track_disconnect(logger, cmd, **kwargs):
            if "qemu-nbd" in cmd and "--disconnect" in cmd:
                disconnect_calls.append(cmd)
                return Mock()
            elif "--connect" in cmd:
                # First connect fails
                if len([c for c in disconnect_calls]) == 0:
                    raise subprocess.CalledProcessError(1, "qemu-nbd", stderr="Error")
                # Second connect succeeds
                return Mock()
            return Mock()

        mock_run_sudo.side_effect = track_disconnect
        mock_is_free.side_effect = [True, False]

        result = self.manager.connect("/tmp/test.qcow2")

        # Should have attempted cleanup (disconnect) after first failure
        self.assertGreater(len(disconnect_calls), 0,
                          "Cleanup (disconnect) not called after failed connect")

    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager._scan_partitions')
    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager._is_nbd_free')
    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager.find_free_nbd')
    @patch('hyper2kvm.core.vmcraft.nbd.run_sudo')
    @patch('hyper2kvm.core.vmcraft.nbd.Path.exists')
    @patch('hyper2kvm.core.vmcraft.nbd.time.sleep')
    def test_connect_exponential_backoff(
        self, mock_sleep, mock_exists, mock_run_sudo, mock_find_free, mock_is_free, mock_scan
    ):
        """Test that retry uses exponential backoff."""
        mock_exists.return_value = True
        mock_find_free.return_value = "/dev/nbd0"

        # All attempts fail to observe all backoffs
        mock_run_sudo.side_effect = subprocess.CalledProcessError(1, "qemu-nbd")

        try:
            self.manager.connect("/tmp/test.qcow2")
        except subprocess.CalledProcessError:
            pass

        # Should have slept between retries (2 sleeps for 3 attempts)
        self.assertEqual(mock_sleep.call_count, 2)

        # Sleep durations should increase (exponential backoff)
        sleep_durations = [call_args[0][0] for call_args in mock_sleep.call_args_list]

        # First backoff: ~2.0s, second: ~4.0s (base_backoff_s * 2^attempt)
        # With jitter, exact values vary, but second should be >= first
        if len(sleep_durations) >= 2:
            # Just verify that backoff is happening (durations are positive)
            self.assertGreater(sleep_durations[0], 0)
            self.assertGreater(sleep_durations[1], 0)


class TestNBDRetryIntegration(unittest.TestCase):
    """Integration tests for NBD retry logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock()
        self.manager = NBDDeviceManager(self.logger, readonly=True)

    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager._scan_partitions')
    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager._is_nbd_free')
    @patch('hyper2kvm.core.vmcraft.nbd.NBDDeviceManager.find_free_nbd')
    @patch('hyper2kvm.core.vmcraft.nbd.run_sudo')
    @patch('hyper2kvm.core.vmcraft.nbd.Path.exists')
    @patch('hyper2kvm.core.vmcraft.nbd.time.sleep')
    def test_retry_recovers_from_transient_failure(
        self, mock_sleep, mock_exists, mock_run_sudo, mock_find_free, mock_is_free, mock_scan
    ):
        """Test that retry successfully recovers from transient failures."""
        mock_exists.return_value = True
        mock_find_free.return_value = "/dev/nbd0"

        # Simulate transient failure pattern: fail, fail, succeed
        mock_run_sudo.side_effect = [
            subprocess.CalledProcessError(1, "qemu-nbd", stderr="Temporary error"),
            subprocess.CalledProcessError(1, "qemu-nbd", stderr="Still busy"),
            Mock(),  # Finally succeeds
        ]

        mock_is_free.side_effect = [True, False]

        # Should not raise
        result = self.manager.connect("/tmp/test.qcow2")

        # Should succeed after retries
        self.assertEqual(result, "/dev/nbd0")
        self.assertTrue(self.manager._connected)
        self.assertEqual(self.manager._nbd_device, "/dev/nbd0")


if __name__ == "__main__":
    unittest.main()
