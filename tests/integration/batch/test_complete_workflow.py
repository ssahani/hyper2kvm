# SPDX-License-Identifier: LGPL-3.0-or-later
"""End-to-end integration tests combining all batch migration features.

This module tests the integration of:
- Checkpoint/resume functionality
- Progress tracking
- Hook retry logic
- Profile caching
- Validation framework
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hyper2kvm.manifest.batch_progress import ProgressTracker, VMStatus
from hyper2kvm.manifest.checkpoint_manager import CheckpointManager
from hyper2kvm.profiles.profile_cache import reset_global_cache
from hyper2kvm.profiles.profile_loader import ProfileLoader
from hyper2kvm.validation import DiskValidator, ValidationRunner, XMLValidator


class TestCompleteWorkflowIntegration:
    """End-to-end tests combining all features."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset global profile cache."""
        reset_global_cache()
        yield
        reset_global_cache()

    @pytest.fixture
    def workflow_setup(self, tmp_path):
        """Setup complete workflow environment."""
        # Create directories
        checkpoint_dir = tmp_path / "checkpoints"
        checkpoint_dir.mkdir()

        progress_dir = tmp_path / "progress"
        progress_dir.mkdir()

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir()

        # Create custom profile
        import yaml

        profile_content = {
            "pipeline": {
                "fix": {"enabled": True},
                "convert": {"compress": True, "compress_level": 6},
                "validate": {"enabled": True},
            },
            "hooks": {
                "pre_extraction": [
                    {
                        "type": "script",
                        "path": "/bin/true",
                        "retry": {"max_retries": 2, "initial_delay": 0.1},
                    }
                ],
            },
        }

        profile_file = profile_dir / "workflow.yaml"
        with open(profile_file, "w") as f:
            yaml.dump(profile_content, f)

        return {
            "checkpoint_dir": checkpoint_dir,
            "progress_dir": progress_dir,
            "output_dir": output_dir,
            "profile_dir": profile_dir,
            "tmp_path": tmp_path,
        }

    def test_complete_batch_workflow_success(self, workflow_setup):
        """Test complete successful batch workflow with all features."""
        setup = workflow_setup

        # Initialize components
        checkpoint = CheckpointManager(setup["checkpoint_dir"], "test-batch")
        progress_file = setup["progress_dir"] / "progress.json"
        tracker = ProgressTracker(progress_file, "test-batch", total_vms=3)
        loader = ProfileLoader()
        validator_runner = ValidationRunner()
        validator_runner.add_validator(DiskValidator())

        # Simulate batch processing
        vm_ids = ["vm1", "vm2", "vm3"]
        completed_vms = []

        for vm_id in vm_ids:
            # Load profile (with caching)
            profile = loader.load_profile(
                "workflow", custom_profile_path=setup["profile_dir"]
            )
            assert profile is not None

            # Start VM in progress tracker
            tracker.start_vm(vm_id)

            # Simulate processing stages
            tracker.update_vm_stage(vm_id, "extraction")
            time.sleep(0.01)

            tracker.update_vm_stage(vm_id, "fixing")
            time.sleep(0.01)

            tracker.update_vm_stage(vm_id, "conversion")
            time.sleep(0.01)

            # Create output disk for validation
            disk_path = setup["output_dir"] / f"{vm_id}.qcow2"
            disk_path.write_bytes(b"\x00" * (5 * 1024 * 1024))

            # Validate
            tracker.update_vm_stage(vm_id, "validation")
            validation_context = {
                "output_path": str(disk_path),
                "format": "qcow2",
            }
            validation_reports = validator_runner.run_all(validation_context)

            # Check validation passed
            validation_passed = not any(r.has_errors() for r in validation_reports)
            assert validation_passed

            # Complete VM
            tracker.complete_vm(vm_id, success=True)
            completed_vms.append(vm_id)

            # Update checkpoint
            checkpoint.save_checkpoint(
                completed_vms=completed_vms,
                total_vms=3,
            )

        # Complete batch
        tracker.complete_batch()

        # Verify final state
        progress = tracker.get_progress()
        assert progress.get_completion_percentage() == 100.0
        assert progress.get_counts()["completed"] == 3

        # Verify profile cache was used
        cache_stats = loader.get_cache_statistics()
        assert cache_stats["hits"] == 2  # 3 loads - 1 miss = 2 hits

        # Verify checkpoint
        checkpoint_data = checkpoint.load_checkpoint()
        assert len(checkpoint_data["completed_vms"]) == 3

        # Cleanup
        tracker.cleanup()
        checkpoint.cleanup()

    def test_batch_workflow_with_resume(self, workflow_setup):
        """Test batch workflow with interruption and resume."""
        setup = workflow_setup

        # === First run: Process 2 VMs then "crash" ===
        checkpoint1 = CheckpointManager(setup["checkpoint_dir"], "test-batch")
        progress_file = setup["progress_dir"] / "progress.json"
        tracker1 = ProgressTracker(progress_file, "test-batch", total_vms=5)

        # Process VM 1 and 2
        for i in range(1, 3):
            vm_id = f"vm{i}"
            tracker1.start_vm(vm_id)
            tracker1.update_vm_stage(vm_id, "conversion")
            time.sleep(0.01)
            tracker1.complete_vm(vm_id, success=True)

        # Save checkpoint
        checkpoint1.save_checkpoint(
            completed_vms=["vm1", "vm2"],
            total_vms=5,
        )

        # Verify progress
        progress1 = tracker1.get_progress()
        assert progress1.get_completion_percentage() == 40.0

        # === Second run: Resume from checkpoint ===
        checkpoint2 = CheckpointManager(setup["checkpoint_dir"], "test-batch")
        tracker2 = ProgressTracker(progress_file, "test-batch", total_vms=5)

        # Load checkpoint
        checkpoint_data = checkpoint2.load_checkpoint()
        assert checkpoint_data["resume_from"] == 2

        # Skip completed VMs in progress
        for vm_id in checkpoint_data["completed_vms"]:
            tracker2.skip_vm(vm_id, "From checkpoint")

        # Process remaining VMs
        for i in range(3, 6):
            vm_id = f"vm{i}"

            # Check if should skip
            if checkpoint2.should_skip_vm(vm_id):
                continue

            tracker2.start_vm(vm_id)
            tracker2.update_vm_stage(vm_id, "conversion")
            time.sleep(0.01)
            tracker2.complete_vm(vm_id, success=True)

        # Complete batch
        tracker2.complete_batch()

        # Verify final progress
        progress2 = tracker2.get_progress()
        # Completion includes completed + failed, not skipped
        # We have 3 completed + 2 skipped = 5 total VMs processed
        # But completion % only counts completed + failed
        assert progress2.get_completion_percentage() == 60.0  # 3/5 completed

        counts = progress2.get_counts()
        assert counts["completed"] == 3
        assert counts["skipped"] == 2

        # Cleanup
        tracker2.cleanup()
        checkpoint2.cleanup()

    def test_batch_workflow_with_failures(self, workflow_setup):
        """Test batch workflow with VM failures and retries."""
        setup = workflow_setup

        checkpoint = CheckpointManager(setup["checkpoint_dir"], "test-batch")
        progress_file = setup["progress_dir"] / "progress.json"
        tracker = ProgressTracker(progress_file, "test-batch", total_vms=5)

        completed = []
        failed = []

        # Simulate batch with some failures
        for i in range(1, 6):
            vm_id = f"vm{i}"
            tracker.start_vm(vm_id)

            # VM 2 and 4 fail
            success = i not in [2, 4]

            tracker.update_vm_stage(vm_id, "conversion")
            time.sleep(0.01)

            if success:
                tracker.complete_vm(vm_id, success=True)
                completed.append(vm_id)
            else:
                error = f"Simulated failure for {vm_id}"
                tracker.complete_vm(vm_id, success=False, error=error)
                failed.append({"vm_id": vm_id, "error": error})

        # Save checkpoint
        checkpoint.save_checkpoint(
            completed_vms=completed,
            failed_vms=failed,
            total_vms=5,
        )

        # Complete batch
        tracker.complete_batch()

        # Verify results
        progress = tracker.get_progress()
        counts = progress.get_counts()

        assert counts["completed"] == 3
        assert counts["failed"] == 2
        assert progress.get_completion_percentage() == 100.0  # All processed

        # Verify checkpoint recorded failures
        checkpoint_data = checkpoint.load_checkpoint()
        assert len(checkpoint_data["failed_vms"]) == 2

        # Cleanup
        tracker.cleanup()

    def test_batch_workflow_with_validation_failures(self, workflow_setup):
        """Test batch workflow with validation failures."""
        setup = workflow_setup

        tracker = ProgressTracker(
            setup["progress_dir"] / "progress.json",
            "test-batch",
            total_vms=2,
        )
        validator_runner = ValidationRunner()
        validator_runner.add_validator(DiskValidator())

        # VM 1: Valid disk
        tracker.start_vm("vm1")
        disk1 = setup["output_dir"] / "vm1.qcow2"
        disk1.write_bytes(b"\x00" * (5 * 1024 * 1024))

        reports = validator_runner.run_all({
            "output_path": str(disk1),
            "format": "qcow2",
        })

        validation_passed = not any(r.has_errors() for r in reports)
        tracker.complete_vm("vm1", success=validation_passed)

        # VM 2: Empty disk (validation failure)
        tracker.start_vm("vm2")
        disk2 = setup["output_dir"] / "vm2.qcow2"
        disk2.write_bytes(b"")  # Empty

        validator_runner2 = ValidationRunner()
        validator_runner2.add_validator(DiskValidator())

        reports2 = validator_runner2.run_all({
            "output_path": str(disk2),
            "format": "qcow2",
        })

        validation_passed2 = not any(r.has_errors() for r in reports2)
        tracker.complete_vm("vm2", success=validation_passed2, error="Validation failed")

        # Verify results
        progress = tracker.get_progress()
        counts = progress.get_counts()

        assert counts["completed"] == 1
        assert counts["failed"] == 1

        # Cleanup
        tracker.cleanup()

    def test_profile_cache_across_batch(self, workflow_setup):
        """Test that profile cache is effective across batch processing."""
        setup = workflow_setup
        loader = ProfileLoader()

        # Simulate loading profile for multiple VMs
        load_times = []

        for i in range(10):
            start = time.time()
            profile = loader.load_profile(
                "workflow", custom_profile_path=setup["profile_dir"]
            )
            elapsed = time.time() - start
            load_times.append(elapsed)

            assert profile is not None

        # Verify caching effectiveness
        cache_stats = loader.get_cache_statistics()

        assert cache_stats["total_requests"] == 10
        assert cache_stats["hits"] == 9  # First is miss, rest are hits
        assert cache_stats["misses"] == 1
        assert cache_stats["hit_rate_percent"] == 90.0

        # Later loads should be faster on average
        avg_first_half = sum(load_times[:5]) / 5
        avg_second_half = sum(load_times[5:]) / 5

        # Second half should be equal or faster
        assert avg_second_half <= avg_first_half * 1.5


class TestErrorRecovery:
    """Test error recovery scenarios."""

    def test_recovery_from_corrupt_progress_file(self, tmp_path):
        """Test recovery when progress file is corrupted."""
        progress_file = tmp_path / "progress.json"

        # Create valid progress
        tracker1 = ProgressTracker(progress_file, "test-batch", 3)
        tracker1.start_vm("vm1")
        tracker1.complete_vm("vm1", success=True)

        # Corrupt the file
        progress_file.write_text("{corrupt json")

        # Try to load - should return None
        loaded = ProgressTracker.load_progress(progress_file)
        assert loaded is None

        # Can start fresh tracker
        tracker2 = ProgressTracker(progress_file, "test-batch", 3)
        assert tracker2 is not None

    def test_recovery_from_missing_checkpoint(self, tmp_path):
        """Test recovery when checkpoint is missing."""
        from hyper2kvm.manifest.checkpoint_manager import CheckpointError

        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir, "test-batch")

        # Try to load non-existent checkpoint
        with pytest.raises(CheckpointError):
            manager.load_checkpoint()

        # Can start fresh
        manager.save_checkpoint(completed_vms=[], total_vms=5)
        assert manager.has_checkpoint()


class TestConcurrentOperations:
    """Test concurrent operations in batch processing."""

    def test_concurrent_progress_updates(self, tmp_path):
        """Test concurrent progress updates from multiple workers."""
        import threading

        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file, "test-batch", total_vms=20)

        def process_vm(vm_id):
            tracker.start_vm(vm_id)
            time.sleep(0.01)
            tracker.update_vm_stage(vm_id, "conversion")
            time.sleep(0.01)
            tracker.complete_vm(vm_id, success=True)

        # Process 10 VMs concurrently
        threads = [
            threading.Thread(target=process_vm, args=(f"vm{i}",))
            for i in range(1, 11)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Verify all completed
        progress = tracker.get_progress()
        assert len(progress.vms) == 10
        assert all(vm.status == VMStatus.COMPLETED for vm in progress.vms.values())

        # Cleanup
        tracker.cleanup()

    def test_concurrent_profile_loads(self, tmp_path):
        """Test concurrent profile loading with caching."""
        import threading

        from hyper2kvm.profiles.profile_cache import reset_global_cache

        reset_global_cache()

        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir()

        import yaml

        profile_file = profile_dir / "test.yaml"
        with open(profile_file, "w") as f:
            yaml.dump({"pipeline": {"fix": {"enabled": True}}}, f)

        def load_profile():
            loader = ProfileLoader()
            for _ in range(5):
                loader.load_profile("test", custom_profile_path=profile_dir)

        # Multiple threads loading same profile
        threads = [threading.Thread(target=load_profile) for _ in range(5)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Verify cache worked correctly
        from hyper2kvm.profiles.profile_cache import get_global_cache

        cache = get_global_cache()
        stats = cache.get_statistics()

        # Should have high hit rate
        assert stats["total_requests"] == 25  # 5 threads x 5 loads
        assert stats["hit_rate_percent"] >= 80  # Most should be hits
