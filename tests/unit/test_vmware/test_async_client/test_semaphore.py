# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Tests for concurrency management.
"""

import pytest

pytest.importorskip("pytest_asyncio", reason="pytest-asyncio not installed")

import asyncio

from hyper2kvm.vmware.async_client.semaphore import (
    ConcurrencyManager,
    ConcurrencyLimits,
)

pytestmark = pytest.mark.asyncio


class TestConcurrencyLimits:
    """Test ConcurrencyLimits dataclass."""

    def test_default_limits(self):
        """Test default concurrency limits."""
        limits = ConcurrencyLimits()

        assert limits.max_concurrent_vms == 5
        assert limits.max_concurrent_exports == 3
        assert limits.max_api_calls_per_second == 10
        assert limits.max_connections == 10

    def test_custom_limits(self):
        """Test custom concurrency limits."""
        limits = ConcurrencyLimits(
            max_concurrent_vms=10,
            max_concurrent_exports=5,
            max_api_calls_per_second=20,
            max_connections=15,
        )

        assert limits.max_concurrent_vms == 10
        assert limits.max_concurrent_exports == 5
        assert limits.max_api_calls_per_second == 20
        assert limits.max_connections == 15


class TestConcurrencyManager:
    """Test ConcurrencyManager."""

    def test_manager_creation(self):
        """Test creating concurrency manager."""
        manager = ConcurrencyManager(max_concurrent_vms=5)

        assert manager.limits.max_concurrent_vms == 5
        assert manager._vm_semaphore._value == 5

    def test_manager_custom_limits(self):
        """Test manager with custom limits."""
        manager = ConcurrencyManager(
            max_concurrent_vms=10,
            max_concurrent_exports=5,
        )

        assert manager.limits.max_concurrent_vms == 10
        assert manager.limits.max_concurrent_exports == 5

    async def test_vm_slot_limits_concurrency(self):
        """Test that VM slot limits concurrency."""
        manager = ConcurrencyManager(max_concurrent_vms=2)

        active_count = 0
        max_active = 0

        async def task():
            nonlocal active_count, max_active
            async with manager.vm_slot():
                active_count += 1
                max_active = max(max_active, active_count)
                await asyncio.sleep(0.1)
                active_count -= 1

        # Run 5 tasks, but only 2 should run concurrently
        await asyncio.gather(*[task() for _ in range(5)])

        assert max_active == 2

    async def test_export_slot_limits_concurrency(self):
        """Test that export slot limits concurrency."""
        manager = ConcurrencyManager(max_concurrent_exports=3)

        active_count = 0
        max_active = 0

        async def task():
            nonlocal active_count, max_active
            async with manager.export_slot():
                active_count += 1
                max_active = max(max_active, active_count)
                await asyncio.sleep(0.1)
                active_count -= 1

        # Run 10 tasks, but only 3 should run concurrently
        await asyncio.gather(*[task() for _ in range(10)])

        assert max_active == 3

    async def test_api_rate_limiting(self):
        """Test API rate limiting."""
        manager = ConcurrencyManager(max_api_calls_per_second=5)

        start_time = asyncio.get_event_loop().time()

        # Make 10 API calls
        for _ in range(10):
            await manager.api_call()

        elapsed = asyncio.get_event_loop().time() - start_time

        # With rate limit of 5/sec, 10 calls should take ~2 seconds
        assert elapsed >= 1.5  # Allow some margin

    async def test_stats_tracking(self):
        """Test statistics tracking."""
        manager = ConcurrencyManager(max_concurrent_vms=5)

        async def vm_task():
            async with manager.vm_slot():
                await asyncio.sleep(0.1)

        # Run some tasks
        await asyncio.gather(*[vm_task() for _ in range(3)])

        stats = manager.get_stats()

        assert stats["vms_active"] == 0  # All completed
        assert stats["vm_slots_available"] == 5

    def test_manager_repr(self):
        """Test string representation."""
        manager = ConcurrencyManager(max_concurrent_vms=5)

        repr_str = repr(manager)

        assert "ConcurrencyManager" in repr_str
        assert "vms_active" in repr_str
        assert "5" in repr_str  # max_concurrent_vms


class TestSemaphoreContext:
    """Test semaphore context manager."""

    async def test_context_increments_stats(self):
        """Test that context manager increments stats."""
        manager = ConcurrencyManager()

        assert manager._stats["vms_active"] == 0

        async with manager.vm_slot():
            assert manager._stats["vms_active"] == 1

        assert manager._stats["vms_active"] == 0

    async def test_context_releases_on_exception(self):
        """Test that semaphore is released even on exception."""
        manager = ConcurrencyManager()

        try:
            async with manager.vm_slot():
                assert manager._stats["vms_active"] == 1
                raise ValueError("Test error")
        except ValueError:
            pass

        # Should be released even after exception
        assert manager._stats["vms_active"] == 0
