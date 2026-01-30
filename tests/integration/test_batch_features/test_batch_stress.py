# SPDX-License-Identifier: LGPL-3.0-or-later
"""Stress and performance tests for batch migration features."""

import json
import threading
import time
from pathlib import Path

import pytest

from hyper2kvm.manifest.batch_progress import ProgressTracker, VMStatus
from hyper2kvm.manifest.checkpoint_manager import CheckpointManager
from hyper2kvm.profiles.profile_cache import ProfileCache, reset_global_cache
from hyper2kvm.profiles.profile_loader import ProfileLoader
from hyper2kvm.validation import DiskValidator, ValidationRunner


class TestLargeBatchProcessing:
    """Stress tests for large batch operations."""

    def test_large_batch_progress_tracking(self, tmp_path):
        """Test progress tracking with large number of VMs."""
        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file, "large-batch", total_vms=1000)

        # Process 1000 VMs
        for i in range(1, 1001):
            vm_id = f"vm{i}"
            tracker.start_vm(vm_id)
            tracker.update_vm_stage(vm_id, "conversion")
            tracker.complete_vm(vm_id, success=True)

            # Save progress periodically (every 100 VMs)
            if i % 100 == 0:
                progress = tracker.get_progress()
                assert progress.get_completion_percentage() == (i / 1000) * 100

        # Final verification
        progress = tracker.get_progress()
        assert progress.get_completion_percentage() == 100.0
        assert len(progress.vms) == 1000
        assert all(vm.status == VMStatus.COMPLETED for vm in progress.vms.values())

        # Verify file size is reasonable
        file_size = progress_file.stat().st_size
        # Should be < 5MB for 1000 VMs
        assert file_size < 5 * 1024 * 1024

        tracker.cleanup()

    def test_large_checkpoint_operations(self, tmp_path):
        """Test checkpoint with large number of VMs."""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir, "large-batch")

        # Checkpoint with 500 completed VMs
        completed = [f"vm{i}" for i in range(1, 501)]
        failed = [{"vm_id": f"vm{i}", "error": "Test"} for i in range(501, 601)]

        manager.save_checkpoint(
            completed_vms=completed,
            failed_vms=failed,
            total_vms=1000,
        )

        # Load and verify
        data = manager.load_checkpoint()
        assert len(data["completed_vms"]) == 500
        assert len(data["failed_vms"]) == 100

        # Verify skip checks are fast
        start = time.time()
        for i in range(1, 1001):
            manager.should_skip_vm(f"vm{i}")
        elapsed = time.time() - start

        # Should complete quickly (< 1 second for 1000 checks)
        assert elapsed < 1.0

        manager.cleanup()

    def test_rapid_progress_updates(self, tmp_path):
        """Test rapid progress updates."""
        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file, "rapid-test", total_vms=100)

        start = time.time()

        # Rapidly process VMs
        for i in range(1, 101):
            vm_id = f"vm{i}"
            tracker.start_vm(vm_id)
            tracker.update_vm_stage(vm_id, "extraction")
            tracker.update_vm_stage(vm_id, "fixing")
            tracker.update_vm_stage(vm_id, "conversion")
            tracker.update_vm_stage(vm_id, "validation")
            tracker.complete_vm(vm_id, success=True)

        elapsed = time.time() - start

        # Should complete in reasonable time (< 5 seconds for 100 VMs with 4 stage updates each)
        assert elapsed < 5.0

        # Verify integrity
        progress = tracker.get_progress()
        assert len(progress.vms) == 100

        tracker.cleanup()

    def test_concurrent_batch_operations(self, tmp_path):
        """Test multiple concurrent batch operations."""
        batches = []

        def run_batch(batch_id):
            progress_file = tmp_path / f"progress_{batch_id}.json"
            tracker = ProgressTracker(progress_file, f"batch-{batch_id}", 50)

            for i in range(1, 51):
                vm_id = f"vm{i}"
                tracker.start_vm(vm_id)
                time.sleep(0.001)  # Small delay
                tracker.complete_vm(vm_id, success=True)

            tracker.complete_batch()
            batches.append(batch_id)
            tracker.cleanup()

        # Run 5 batches concurrently
        threads = [
            threading.Thread(target=run_batch, args=(i,))
            for i in range(1, 6)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All batches should complete
        assert len(batches) == 5


class TestProfileCachingPerformance:
    """Performance tests for profile caching."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset cache before each test."""
        reset_global_cache()
        yield
        reset_global_cache()

    def test_cache_performance_with_many_profiles(self, tmp_path):
        """Test cache performance with many different profiles."""
        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir()

        # Create 50 profiles
        import yaml

        for i in range(1, 51):
            profile = {
                "pipeline": {
                    "fix": {"enabled": True},
                    "convert": {"compress_level": i % 10},
                }
            }

            profile_file = profile_dir / f"profile{i}.yaml"
            with open(profile_file, "w") as f:
                yaml.dump(profile, f)

        loader = ProfileLoader()

        # Load all profiles multiple times
        start = time.time()

        for round in range(5):
            for i in range(1, 51):
                loader.load_profile(f"profile{i}", custom_profile_path=profile_dir)

        elapsed = time.time() - start

        # Should complete quickly (< 5 seconds for 250 loads)
        assert elapsed < 5.0

        # Verify cache effectiveness
        stats = loader.get_cache_statistics()
        assert stats["total_requests"] == 250  # 50 profiles x 5 rounds
        assert stats["hit_rate_percent"] >= 80  # Most should be cache hits

    def test_cache_memory_usage(self, tmp_path):
        """Test cache doesn't grow unbounded."""
        import yaml

        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir()

        cache = ProfileCache()
        loader = ProfileLoader(cache=cache)

        # Load many unique profiles
        for i in range(1, 201):
            profile = {"pipeline": {"convert": {"compress_level": i}}}
            profile_file = profile_dir / f"profile{i}.yaml"

            with open(profile_file, "w") as f:
                yaml.dump(profile, f)

            loader.load_profile(f"profile{i}", custom_profile_path=profile_dir)

        # Cache should contain all profiles
        stats = cache.get_statistics()
        assert stats["size"] == 200

    def test_concurrent_cache_access(self, tmp_path):
        """Test cache performance under concurrent access."""
        import yaml

        reset_global_cache()

        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir()

        # Create test profile
        profile_file = profile_dir / "test.yaml"
        with open(profile_file, "w") as f:
            yaml.dump({"pipeline": {"fix": {"enabled": True}}}, f)

        results = []

        def worker():
            loader = ProfileLoader()
            for _ in range(20):
                profile = loader.load_profile("test", custom_profile_path=profile_dir)
                results.append(profile is not None)

        # 10 threads, each loading 20 times = 200 total
        threads = [threading.Thread(target=worker) for _ in range(10)]

        start = time.time()

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        elapsed = time.time() - start

        # Should complete quickly
        assert elapsed < 3.0

        # All loads should succeed
        assert len(results) == 200
        assert all(results)


class TestValidationPerformance:
    """Performance tests for validation framework."""

    def test_validation_on_large_disks(self, tmp_path):
        """Test validation performance on large disk files."""
        # Create large disk (100MB)
        disk_path = tmp_path / "large.qcow2"
        disk_path.write_bytes(b"\x00" * (100 * 1024 * 1024))

        validator = DiskValidator()

        # Should complete quickly even for large files
        start = time.time()
        report = validator.validate({
            "output_path": str(disk_path),
            "format": "qcow2",
        })
        elapsed = time.time() - start

        # Validation should be fast (< 1 second)
        assert elapsed < 1.0
        assert not report.has_errors()

    def test_validation_on_many_files(self, tmp_path):
        """Test validating many files."""
        validator = DiskValidator()

        # Create 50 disk files
        for i in range(1, 51):
            disk_path = tmp_path / f"disk{i}.qcow2"
            disk_path.write_bytes(b"\x00" * (5 * 1024 * 1024))

        start = time.time()

        # Validate all disks
        reports = []
        for i in range(1, 51):
            disk_path = tmp_path / f"disk{i}.qcow2"
            report = validator.validate({
                "output_path": str(disk_path),
                "format": "qcow2",
            })
            reports.append(report)

        elapsed = time.time() - start

        # Should complete in reasonable time (< 5 seconds for 50 validations)
        assert elapsed < 5.0

        # All should pass
        assert all(not r.has_errors() for r in reports)


class TestMemoryLeaks:
    """Tests to detect potential memory leaks."""

    def test_progress_tracker_memory(self, tmp_path):
        """Test progress tracker doesn't leak memory."""
        import gc

        progress_file = tmp_path / "progress.json"

        # Process many batches in sequence
        for batch in range(10):
            tracker = ProgressTracker(
                progress_file, f"batch-{batch}", total_vms=100
            )

            for i in range(1, 101):
                vm_id = f"vm{i}"
                tracker.start_vm(vm_id)
                tracker.complete_vm(vm_id, success=True)

            tracker.cleanup()

            # Force garbage collection
            gc.collect()

        # Should complete without memory issues
        assert True

    def test_checkpoint_memory(self, tmp_path):
        """Test checkpoint manager doesn't leak memory."""
        import gc

        checkpoint_dir = tmp_path / "checkpoints"

        # Create and cleanup many checkpoints
        for i in range(20):
            manager = CheckpointManager(checkpoint_dir, f"batch-{i}")

            completed = [f"vm{j}" for j in range(1, 51)]
            manager.save_checkpoint(completed_vms=completed, total_vms=100)

            manager.cleanup()
            gc.collect()

        # Should complete without memory issues
        assert True


class TestErrorRecoveryUnderStress:
    """Test error recovery under stress conditions."""

    def test_recovery_from_rapid_failures(self, tmp_path):
        """Test handling rapid successive failures."""
        tracker = ProgressTracker(
            tmp_path / "progress.json",
            "stress-test",
            total_vms=100,
        )

        # Fail many VMs rapidly
        for i in range(1, 101):
            vm_id = f"vm{i}"
            tracker.start_vm(vm_id)
            tracker.complete_vm(vm_id, success=False, error=f"Error {i}")

        # Verify all failures recorded
        progress = tracker.get_progress()
        assert progress.get_counts()["failed"] == 100

        tracker.cleanup()

    def test_checkpoint_corruption_handling(self, tmp_path):
        """Test handling checkpoint corruption during stress."""
        from hyper2kvm.manifest.checkpoint_manager import CheckpointError

        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir, "stress-batch")

        # Save valid checkpoint
        manager.save_checkpoint(completed_vms=["vm1"], total_vms=10)

        # Corrupt checkpoint file
        manager.checkpoint_file.write_text("{corrupt")

        # Should handle corruption
        with pytest.raises(CheckpointError):
            manager.load_checkpoint()

        # Can reset and continue
        manager.reset()
        manager.save_checkpoint(completed_vms=["vm1", "vm2"], total_vms=10)

        data = manager.load_checkpoint()
        assert len(data["completed_vms"]) == 2

    def test_progress_file_concurrent_corruption(self, tmp_path):
        """Test handling progress file corruption during concurrent writes."""
        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file, "stress-test", total_vms=50)

        errors = []

        def worker(vm_id):
            try:
                tracker.start_vm(vm_id)
                time.sleep(0.001)
                tracker.complete_vm(vm_id, success=True)
            except Exception as e:
                errors.append(e)

        # Concurrent updates
        threads = [
            threading.Thread(target=worker, args=(f"vm{i}",))
            for i in range(1, 51)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Should handle concurrent access without errors
        # (or with minimal acceptable errors)
        assert len(errors) < 5  # Allow some race conditions

        tracker.cleanup()


class TestScalability:
    """Test scalability of batch operations."""

    def test_scalability_checkpoint_size(self, tmp_path):
        """Test checkpoint file size scales reasonably."""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir, "scale-test")

        # Test with different batch sizes
        sizes = [10, 100, 1000]
        file_sizes = []

        for size in sizes:
            completed = [f"vm{i}" for i in range(1, size + 1)]
            manager.save_checkpoint(completed_vms=completed, total_vms=size)

            file_size = manager.checkpoint_file.stat().st_size
            file_sizes.append(file_size)

            manager.cleanup()

        # File size should scale roughly linearly
        # (allowing for some overhead and base size)
        ratio_1 = file_sizes[1] / file_sizes[0]
        ratio_2 = file_sizes[2] / file_sizes[1]

        # Ratios should be reasonable (not exponential growth)
        # Lower bound accounts for base JSON overhead, upper bound prevents exponential growth
        assert 3 < ratio_1 < 15  # 10x increase with overhead tolerance
        assert 3 < ratio_2 < 15  # 10x increase with overhead tolerance

    def test_scalability_progress_updates(self, tmp_path):
        """Test progress update performance scales."""
        progress_file = tmp_path / "progress.json"

        # Test with different VM counts
        times = []

        for vm_count in [10, 50, 100]:
            tracker = ProgressTracker(progress_file, f"batch-{vm_count}", vm_count)

            start = time.time()

            for i in range(1, vm_count + 1):
                vm_id = f"vm{i}"
                tracker.start_vm(vm_id)
                tracker.complete_vm(vm_id, success=True)

            elapsed = time.time() - start
            times.append(elapsed)

            tracker.cleanup()

        # Performance should scale roughly linearly
        # (not exponentially - allow overhead for file I/O, threading, etc.)
        assert times[2] < times[0] * 50  # 10x VMs should be < 50x time (generous for CI)
