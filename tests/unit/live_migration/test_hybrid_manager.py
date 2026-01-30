"""Unit tests for Hybrid Migration Manager."""

import logging
import pytest

from hyper2kvm.live_migration.hybrid_manager import HybridMigrationManager


class TestHybridMigrationManager:
    """Test Hybrid Migration Manager functionality."""

    @pytest.fixture
    def hybrid_mgr(self):
        """Create HybridMigrationManager instance."""
        logger = logging.getLogger("test")
        return HybridMigrationManager(logger)

    def test_init(self, hybrid_mgr):
        """Test HybridMigrationManager initialization."""
        assert hybrid_mgr is not None
        assert hybrid_mgr.logger is not None
        assert hybrid_mgr.hypersdk is not None

    def test_estimate_hybrid_migration_time(self, hybrid_mgr):
        """Test hybrid migration time estimation."""
        vm_info = {
            "memory_mb": 8192,
            "disk_size_gb": 100,
        }

        estimate = hybrid_mgr.estimate_hybrid_migration_time(
            vm_info, offline_fixes=["bootloader", "network"]
        )

        assert "live_migration_seconds" in estimate
        assert "offline_fixes_seconds" in estimate
        assert "total_seconds" in estimate
        assert "total_downtime_seconds" in estimate

        # Total should be sum of components
        assert estimate["total_seconds"] >= estimate["live_migration_seconds"]
        assert estimate["total_seconds"] >= estimate["offline_fixes_seconds"]

    def test_estimate_with_no_fixes(self, hybrid_mgr):
        """Test estimation with no offline fixes."""
        vm_info = {"memory_mb": 4096}

        estimate = hybrid_mgr.estimate_hybrid_migration_time(vm_info, offline_fixes=[])

        # No offline fixes means zero offline time
        assert estimate["offline_fixes_seconds"] == 0.0
        # But live migration still takes time
        assert estimate["live_migration_seconds"] > 0.0

    def test_estimate_scales_with_memory(self, hybrid_mgr):
        """Test that estimation scales with VM memory."""
        small_vm = {"memory_mb": 2048}
        large_vm = {"memory_mb": 32768}

        small_estimate = hybrid_mgr.estimate_hybrid_migration_time(
            small_vm, offline_fixes=[]
        )
        large_estimate = hybrid_mgr.estimate_hybrid_migration_time(
            large_vm, offline_fixes=[]
        )

        # Larger VM should take longer
        assert large_estimate["live_migration_seconds"] > small_estimate[
            "live_migration_seconds"
        ]

    def test_estimate_includes_power_cycle_overhead(self, hybrid_mgr):
        """Test that offline fixes include power cycle overhead."""
        vm_info = {"memory_mb": 4096}

        # With fixes
        estimate_with_fixes = hybrid_mgr.estimate_hybrid_migration_time(
            vm_info, offline_fixes=["bootloader"]
        )

        # Should include 20s overhead for power cycling
        assert estimate_with_fixes["offline_fixes_seconds"] >= 20.0
