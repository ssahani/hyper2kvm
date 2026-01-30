# SPDX-License-Identifier: LGPL-3.0-or-later
"""Integration tests for batch progress tracking."""

import json
import threading
import time
from pathlib import Path

import pytest

from hyper2kvm.manifest.batch_progress import (
    BatchProgress,
    ProgressTracker,
    VMProgress,
    VMStatus,
)


class TestProgressTrackingIntegration:
    """Integration tests for progress tracking in batch workflows."""

    def test_progress_tracking_lifecycle(self, tmp_path):
        """Test complete lifecycle of progress tracking."""
        progress_file = tmp_path / "progress.json"

        # Initialize tracker
        tracker = ProgressTracker(
            progress_file=progress_file,
            batch_id="test-batch",
            total_vms=3,
        )

        # Progress file should be created immediately
        assert progress_file.exists()

        # Process VM 1
        tracker.start_vm("vm1")
        tracker.update_vm_stage("vm1", "extraction")
        time.sleep(0.1)
        tracker.update_vm_stage("vm1", "conversion")
        tracker.complete_vm("vm1", success=True)

        # Process VM 2 (with failure)
        tracker.start_vm("vm2")
        tracker.update_vm_stage("vm2", "extraction")
        tracker.complete_vm("vm2", success=False, error="Disk read error")

        # Process VM 3
        tracker.start_vm("vm3")
        tracker.complete_vm("vm3", success=True)

        # Complete batch
        tracker.complete_batch()

        # Verify final progress
        progress = tracker.get_progress()
        assert progress.batch_id == "test-batch"
        assert progress.total_vms == 3
        assert progress.completed_at is not None

        counts = progress.get_counts()
        assert counts["completed"] == 2
        assert counts["failed"] == 1

    def test_progress_persistence(self, tmp_path):
        """Test that progress is persisted to disk and can be reloaded."""
        progress_file = tmp_path / "progress.json"

        # Create and update tracker
        tracker1 = ProgressTracker(progress_file, "test-batch", 5)
        tracker1.start_vm("vm1")
        tracker1.complete_vm("vm1", success=True)
        tracker1.start_vm("vm2")
        tracker1.update_vm_stage("vm2", "extraction")

        # Load progress from file
        loaded = ProgressTracker.load_progress(progress_file)

        assert loaded is not None
        assert loaded.batch_id == "test-batch"
        assert loaded.total_vms == 5
        assert "vm1" in loaded.vms
        assert loaded.vms["vm1"].status == VMStatus.COMPLETED
        assert "vm2" in loaded.vms
        assert loaded.vms["vm2"].status == VMStatus.IN_PROGRESS
        assert loaded.vms["vm2"].current_stage == "extraction"

    def test_progress_real_time_updates(self, tmp_path):
        """Test that progress file is updated in real-time."""
        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file, "test-batch", 2)

        # Start VM
        tracker.start_vm("vm1")

        # Read file directly
        with open(progress_file) as f:
            data = json.load(f)

        assert "vm1" in data["vms"]
        assert data["vms"]["vm1"]["status"] == "in_progress"

        # Update stage
        tracker.update_vm_stage("vm1", "conversion")

        # Read file again
        with open(progress_file) as f:
            data = json.load(f)

        assert data["vms"]["vm1"]["current_stage"] == "conversion"

    def test_progress_completion_percentage(self, tmp_path):
        """Test progress completion percentage calculation."""
        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file, "test-batch", 10)

        # 0% initially
        progress = tracker.get_progress()
        assert progress.get_completion_percentage() == 0.0

        # Complete 3 VMs
        for i in range(1, 4):
            tracker.start_vm(f"vm{i}")
            tracker.complete_vm(f"vm{i}", success=True)

        progress = tracker.get_progress()
        assert progress.get_completion_percentage() == 30.0

        # Fail 2 more (5 total processed)
        for i in range(4, 6):
            tracker.start_vm(f"vm{i}")
            tracker.complete_vm(f"vm{i}", success=False, error="Test")

        progress = tracker.get_progress()
        assert progress.get_completion_percentage() == 50.0

    def test_progress_time_estimation(self, tmp_path):
        """Test estimated time remaining calculation."""
        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file, "test-batch", 10)

        # No estimate without completed VMs
        progress = tracker.get_progress()
        assert progress.get_estimated_time_remaining() is None

        # Complete 2 VMs with known durations
        for i in range(1, 3):
            tracker.start_vm(f"vm{i}")
            # Manually set duration for testing
            tracker.progress.vms[f"vm{i}"].started_at = time.time() - 100
            tracker.complete_vm(f"vm{i}", success=True)

        progress = tracker.get_progress()
        estimate = progress.get_estimated_time_remaining()

        # Should have estimate based on average duration
        assert estimate is not None
        # 8 VMs remaining, ~100s average = ~800s
        assert estimate > 0

    def test_progress_skip_vm(self, tmp_path):
        """Test skipping VMs in progress tracking."""
        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file, "test-batch", 5)

        # Skip VM (e.g., from checkpoint)
        tracker.skip_vm("vm1", "Already completed in previous run")
        tracker.skip_vm("vm2", "Failed in previous run")

        # Process remaining VMs
        tracker.start_vm("vm3")
        tracker.complete_vm("vm3", success=True)

        progress = tracker.get_progress()
        counts = progress.get_counts()

        assert counts["skipped"] == 2
        assert counts["completed"] == 1

    def test_progress_concurrent_updates(self, tmp_path):
        """Test progress tracking with concurrent VM processing."""
        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file, "test-batch", 20)

        def process_vm(vm_id):
            tracker.start_vm(vm_id)
            time.sleep(0.01)  # Simulate work
            tracker.update_vm_stage(vm_id, "extraction")
            time.sleep(0.01)
            tracker.update_vm_stage(vm_id, "conversion")
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

        # Verify all VMs completed
        progress = tracker.get_progress()
        assert len(progress.vms) == 10
        assert all(vm.status == VMStatus.COMPLETED for vm in progress.vms.values())

    def test_progress_file_cleanup(self, tmp_path):
        """Test progress file cleanup after batch completion."""
        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file, "test-batch", 1)

        tracker.start_vm("vm1")
        tracker.complete_vm("vm1", success=True)
        tracker.complete_batch()

        assert progress_file.exists()

        # Cleanup
        tracker.cleanup()
        assert not progress_file.exists()

    def test_progress_atomic_writes(self, tmp_path):
        """Test that progress writes are atomic."""
        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file, "test-batch", 5)

        # Make multiple rapid updates
        for i in range(1, 6):
            tracker.start_vm(f"vm{i}")
            tracker.complete_vm(f"vm{i}", success=True)

        # No temp files should exist
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

        # File should be valid JSON
        with open(progress_file) as f:
            data = json.load(f)

        assert data["batch_id"] == "test-batch"


class TestProgressTrackingWithCheckpoint:
    """Test progress tracking integrated with checkpoint functionality."""

    def test_progress_and_checkpoint_together(self, tmp_path):
        """Test using both progress tracking and checkpoints."""
        from hyper2kvm.manifest.checkpoint_manager import CheckpointManager

        progress_file = tmp_path / "progress.json"
        checkpoint_dir = tmp_path / "checkpoints"

        tracker = ProgressTracker(progress_file, "test-batch", 5)
        checkpoint = CheckpointManager(checkpoint_dir, "test-batch")

        completed = []
        failed = []

        # Process VMs 1-3
        for i in range(1, 4):
            tracker.start_vm(f"vm{i}")
            success = i != 2  # VM 2 fails
            tracker.complete_vm(f"vm{i}", success=success, error=None if success else "Error")

            if success:
                completed.append(f"vm{i}")
            else:
                failed.append({"vm_id": f"vm{i}", "error": "Error"})

        # Save checkpoint
        checkpoint.save_checkpoint(
            completed_vms=completed,
            failed_vms=failed,
            total_vms=5,
        )

        # Verify both files exist
        assert progress_file.exists()
        assert checkpoint.has_checkpoint()

        # Load and verify consistency
        progress = tracker.get_progress()
        checkpoint_data = checkpoint.load_checkpoint()

        assert len(completed) == 2
        assert len(failed) == 1
        assert progress.get_counts()["completed"] == 2
        assert progress.get_counts()["failed"] == 1

    def test_resume_with_progress_tracking(self, tmp_path):
        """Test resuming batch with progress tracking."""
        from hyper2kvm.manifest.checkpoint_manager import CheckpointManager

        progress_file = tmp_path / "progress.json"
        checkpoint_dir = tmp_path / "checkpoints"

        # First run - process 2 VMs
        tracker1 = ProgressTracker(progress_file, "test-batch", 5)
        checkpoint1 = CheckpointManager(checkpoint_dir, "test-batch")

        tracker1.start_vm("vm1")
        tracker1.complete_vm("vm1", success=True)
        tracker1.start_vm("vm2")
        tracker1.complete_vm("vm2", success=True)

        checkpoint1.save_checkpoint(
            completed_vms=["vm1", "vm2"],
            total_vms=5,
        )

        # Resume - load progress and skip completed VMs
        loaded_progress = ProgressTracker.load_progress(progress_file)
        checkpoint2 = CheckpointManager(checkpoint_dir, "test-batch")

        assert loaded_progress is not None
        assert checkpoint2.should_skip_vm("vm1")
        assert checkpoint2.should_skip_vm("vm2")
        assert not checkpoint2.should_skip_vm("vm3")

        # Continue processing
        tracker2 = ProgressTracker(progress_file, "test-batch", 5)
        tracker2.skip_vm("vm1", "From checkpoint")
        tracker2.skip_vm("vm2", "From checkpoint")
        tracker2.start_vm("vm3")
        tracker2.complete_vm("vm3", success=True)

        progress = tracker2.get_progress()
        assert progress.get_counts()["completed"] == 1
        assert progress.get_counts()["skipped"] == 2


class TestProgressErrorHandling:
    """Test error handling in progress tracking."""

    def test_progress_write_error_handling(self, tmp_path):
        """Test handling of write errors in progress tracking."""
        # Create progress tracker
        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file, "test-batch", 2)

        # Make file read-only to trigger write error
        progress_file.chmod(0o444)

        # Update should not crash
        tracker.start_vm("vm1")
        tracker.complete_vm("vm1", success=True)

        # Restore permissions
        progress_file.chmod(0o644)

    def test_load_corrupt_progress_file(self, tmp_path):
        """Test loading corrupted progress file."""
        progress_file = tmp_path / "progress.json"

        # Write invalid JSON
        progress_file.write_text("{invalid json")

        # Should return None on error
        loaded = ProgressTracker.load_progress(progress_file)
        assert loaded is None

    def test_load_nonexistent_progress_file(self, tmp_path):
        """Test loading non-existent progress file."""
        progress_file = tmp_path / "nonexistent.json"

        loaded = ProgressTracker.load_progress(progress_file)
        assert loaded is None


class TestProgressStageTracking:
    """Test tracking of VM processing stages."""

    def test_stage_tracking(self, tmp_path):
        """Test tracking stages within VM processing."""
        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file, "test-batch", 1)

        tracker.start_vm("vm1")

        # Track stages
        stages = ["extraction", "inspection", "fixing", "conversion", "validation"]
        for stage in stages:
            tracker.update_vm_stage("vm1", stage)

        tracker.complete_vm("vm1", success=True)

        # Verify all stages tracked
        progress = tracker.get_progress()
        vm_progress = progress.vms["vm1"]

        assert vm_progress.current_stage == "validation"
        assert len(vm_progress.stages_completed) == 5
        assert all(stage in vm_progress.stages_completed for stage in stages)

    def test_stage_deduplication(self, tmp_path):
        """Test that stages are not duplicated."""
        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file, "test-batch", 1)

        tracker.start_vm("vm1")

        # Update same stage multiple times
        tracker.update_vm_stage("vm1", "extraction")
        tracker.update_vm_stage("vm1", "extraction")
        tracker.update_vm_stage("vm1", "extraction")

        progress = tracker.get_progress()
        vm_progress = progress.vms["vm1"]

        # Should only appear once
        assert vm_progress.stages_completed.count("extraction") == 1
