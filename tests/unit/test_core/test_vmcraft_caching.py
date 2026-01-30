# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test VMCraft caching mechanisms.

Tests partition list and blkid caching to verify reduced system calls
and performance improvements.
"""
import time
import unittest
from unittest.mock import Mock, MagicMock, patch

from hyper2kvm.core.vmcraft.main import VMCraft


class TestPartitionCaching(unittest.TestCase):
    """Test partition list caching."""

    def setUp(self):
        """Set up test fixtures."""
        self.vmcraft = VMCraft()
        self.vmcraft._nbd_device = "/dev/nbd0"
        self.vmcraft._nbd_manager = Mock()

    def test_partition_cache_miss(self):
        """Test cache miss on first call."""
        self.vmcraft._nbd_manager.get_partitions.return_value = [
            "/dev/nbd0p1",
            "/dev/nbd0p2",
        ]

        partitions = self.vmcraft.list_partitions(use_cache=True)

        # Should call get_partitions
        self.vmcraft._nbd_manager.get_partitions.assert_called_once()
        self.assertEqual(partitions, ["/dev/nbd0p1", "/dev/nbd0p2"])

    def test_partition_cache_hit(self):
        """Test cache hit on subsequent call."""
        self.vmcraft._nbd_manager.get_partitions.return_value = [
            "/dev/nbd0p1",
            "/dev/nbd0p2",
        ]

        # First call - cache miss
        partitions1 = self.vmcraft.list_partitions(use_cache=True)

        # Second call - cache hit
        partitions2 = self.vmcraft.list_partitions(use_cache=True)

        # Should only call get_partitions once
        self.assertEqual(self.vmcraft._nbd_manager.get_partitions.call_count, 1)

        # Results should be the same
        self.assertEqual(partitions1, partitions2)

    def test_partition_cache_ttl_expiration(self):
        """Test cache expiration after TTL."""
        self.vmcraft._nbd_manager.get_partitions.return_value = [
            "/dev/nbd0p1",
        ]

        # First call
        partitions1 = self.vmcraft.list_partitions(use_cache=True)

        # Manually expire cache by setting old timestamp
        import time
        cache_key = "/dev/nbd0"
        old_time = time.time() - 61  # 61 seconds ago (> 60s TTL)
        self.vmcraft._partition_cache[cache_key] = (["/dev/nbd0p1"], old_time)

        # Second call should fetch fresh data
        self.vmcraft._nbd_manager.get_partitions.return_value = [
            "/dev/nbd0p1",
            "/dev/nbd0p2",
        ]
        partitions2 = self.vmcraft.list_partitions(use_cache=True)

        # Should have called get_partitions twice (cache expired)
        self.assertEqual(self.vmcraft._nbd_manager.get_partitions.call_count, 2)
        self.assertEqual(len(partitions2), 2)

    def test_partition_cache_disabled(self):
        """Test caching can be disabled."""
        self.vmcraft._nbd_manager.get_partitions.return_value = [
            "/dev/nbd0p1",
        ]

        # Multiple calls with cache disabled
        partitions1 = self.vmcraft.list_partitions(use_cache=False)
        partitions2 = self.vmcraft.list_partitions(use_cache=False)

        # Should call get_partitions every time
        self.assertEqual(self.vmcraft._nbd_manager.get_partitions.call_count, 2)

    def test_invalidate_partition_cache_specific_device(self):
        """Test invalidating cache for specific device."""
        # Populate cache
        self.vmcraft._partition_cache["/dev/nbd0"] = (
            ["/dev/nbd0p1"],
            time.time()
        )
        self.vmcraft._partition_cache["/dev/nbd1"] = (
            ["/dev/nbd1p1"],
            time.time()
        )

        # Invalidate specific device
        self.vmcraft.invalidate_partition_cache("/dev/nbd0")

        # /dev/nbd0 should be removed, /dev/nbd1 should remain
        self.assertNotIn("/dev/nbd0", self.vmcraft._partition_cache)
        self.assertIn("/dev/nbd1", self.vmcraft._partition_cache)

    def test_invalidate_partition_cache_all(self):
        """Test invalidating all partition caches."""
        # Populate cache
        self.vmcraft._partition_cache["/dev/nbd0"] = (
            ["/dev/nbd0p1"],
            time.time()
        )
        self.vmcraft._partition_cache["/dev/nbd1"] = (
            ["/dev/nbd1p1"],
            time.time()
        )

        # Invalidate all
        self.vmcraft.invalidate_partition_cache()

        # Cache should be empty
        self.assertEqual(len(self.vmcraft._partition_cache), 0)

    def test_partition_cache_device_parameter(self):
        """Test caching with custom device parameter."""
        self.vmcraft._nbd_manager.get_partitions.return_value = [
            "/dev/nbd1p1",
        ]

        # Call with custom device
        partitions = self.vmcraft.list_partitions(device="/dev/nbd1", use_cache=True)

        # Cache should use custom device as key
        self.assertIn("/dev/nbd1", self.vmcraft._partition_cache)
        self.assertEqual(partitions, ["/dev/nbd1p1"])


class TestBlkidCaching(unittest.TestCase):
    """Test blkid output caching."""

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_blkid_cache_miss(self, mock_run_sudo):
        """Test cache miss on first blkid call."""
        mock_result = Mock()
        mock_result.stdout = "UUID=test-uuid\nTYPE=ext4\n"
        mock_run_sudo.return_value = mock_result

        vmcraft = VMCraft()

        metadata = vmcraft.blkid("/dev/nbd0p1", use_cache=True)

        # Should call run_sudo
        mock_run_sudo.assert_called_once()
        self.assertEqual(metadata["UUID"], "test-uuid")
        self.assertEqual(metadata["TYPE"], "ext4")

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_blkid_cache_hit(self, mock_run_sudo):
        """Test cache hit on subsequent blkid call."""
        mock_result = Mock()
        mock_result.stdout = "UUID=test-uuid\nTYPE=ext4\n"
        mock_run_sudo.return_value = mock_result

        vmcraft = VMCraft()

        # First call - cache miss
        metadata1 = vmcraft.blkid("/dev/nbd0p1", use_cache=True)

        # Second call - cache hit
        metadata2 = vmcraft.blkid("/dev/nbd0p1", use_cache=True)

        # Should only call run_sudo once
        self.assertEqual(mock_run_sudo.call_count, 1)

        # Results should be the same
        self.assertEqual(metadata1, metadata2)

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_blkid_cache_ttl_expiration(self, mock_run_sudo):
        """Test blkid cache expiration after TTL (120 seconds)."""
        mock_result = Mock()
        mock_result.stdout = "UUID=test-uuid\nTYPE=ext4\n"
        mock_run_sudo.return_value = mock_result

        vmcraft = VMCraft()

        # First call
        metadata1 = vmcraft.blkid("/dev/nbd0p1", use_cache=True)

        # Manually expire cache
        old_time = time.time() - 121  # 121 seconds ago (> 120s TTL)
        vmcraft._blkid_cache["/dev/nbd0p1"] = (metadata1, old_time)

        # Second call should fetch fresh data
        metadata2 = vmcraft.blkid("/dev/nbd0p1", use_cache=True)

        # Should have called run_sudo twice (cache expired)
        self.assertEqual(mock_run_sudo.call_count, 2)

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_blkid_cache_disabled(self, mock_run_sudo):
        """Test blkid with caching disabled."""
        mock_result = Mock()
        mock_result.stdout = "UUID=test-uuid\nTYPE=ext4\n"
        mock_run_sudo.return_value = mock_result

        vmcraft = VMCraft()

        # Multiple calls with cache disabled
        metadata1 = vmcraft.blkid("/dev/nbd0p1", use_cache=False)
        metadata2 = vmcraft.blkid("/dev/nbd0p1", use_cache=False)

        # Should call run_sudo every time
        self.assertEqual(mock_run_sudo.call_count, 2)

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_blkid_cache_multiple_devices(self, mock_run_sudo):
        """Test blkid caching with multiple devices."""
        def mock_blkid_side_effect(logger, cmd, **kwargs):
            device = cmd[-1]
            result = Mock()
            if device == "/dev/nbd0p1":
                result.stdout = "UUID=uuid1\nTYPE=ext4\n"
            else:
                result.stdout = "UUID=uuid2\nTYPE=btrfs\n"
            return result

        mock_run_sudo.side_effect = mock_blkid_side_effect

        vmcraft = VMCraft()

        # Call for different devices
        metadata1 = vmcraft.blkid("/dev/nbd0p1", use_cache=True)
        metadata2 = vmcraft.blkid("/dev/nbd0p2", use_cache=True)

        # Repeat calls should use cache
        metadata1_cached = vmcraft.blkid("/dev/nbd0p1", use_cache=True)
        metadata2_cached = vmcraft.blkid("/dev/nbd0p2", use_cache=True)

        # Should only call run_sudo twice (once per device)
        self.assertEqual(mock_run_sudo.call_count, 2)

        # Verify cached results
        self.assertEqual(metadata1, metadata1_cached)
        self.assertEqual(metadata2, metadata2_cached)

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_blkid_cache_ttl_configurable(self, mock_run_sudo):
        """Test that blkid cache TTL is configurable."""
        vmcraft = VMCraft()

        # Verify default TTL is 120 seconds
        self.assertEqual(vmcraft._blkid_cache_ttl, 120)

        # TTL can be changed
        vmcraft._blkid_cache_ttl = 60
        self.assertEqual(vmcraft._blkid_cache_ttl, 60)


class TestCachePerformance(unittest.TestCase):
    """Test cache performance improvements."""

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_blkid_cache_reduces_calls(self, mock_run_sudo):
        """Verify caching reduces system calls."""
        mock_result = Mock()
        mock_result.stdout = "UUID=test\nTYPE=ext4\n"
        mock_run_sudo.return_value = mock_result

        vmcraft = VMCraft()

        # Call blkid 10 times with caching
        for _ in range(10):
            vmcraft.blkid("/dev/nbd0p1", use_cache=True)

        # Should only call run_sudo once
        self.assertEqual(mock_run_sudo.call_count, 1)

    def test_partition_cache_reduces_nbd_calls(self):
        """Verify partition caching reduces NBD manager calls."""
        vmcraft = VMCraft()
        vmcraft._nbd_device = "/dev/nbd0"
        vmcraft._nbd_manager = Mock()
        vmcraft._nbd_manager.get_partitions.return_value = ["/dev/nbd0p1"]

        # Call list_partitions 10 times with caching
        for _ in range(10):
            vmcraft.list_partitions(use_cache=True)

        # Should only call get_partitions once
        self.assertEqual(vmcraft._nbd_manager.get_partitions.call_count, 1)


if __name__ == "__main__":
    unittest.main()
