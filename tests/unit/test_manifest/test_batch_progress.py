# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for batch progress tracking."""

import json
import time
from pathlib import Path

import pytest

from hyper2kvm.manifest.batch_progress import (
    BatchProgress,
    ProgressTracker,
    VMProgress,
    VMStatus,
)


class TestVMStatus:
    """Test VMStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert VMStatus.PENDING.value == "pending"
        assert VMStatus.IN_PROGRESS.value == "in_progress"
        assert VMStatus.COMPLETED.value == "completed"
        assert VMStatus.FAILED.value == "failed"
        assert VMStatus.SKIPPED.value == "skipped"


class TestVMProgress:
    """Test VMProgress dataclass."""

    def test_creation(self):
        """Test creating VM progress."""
        progress = VMProgress(
            vm_id="vm1",
            status=VMStatus.IN_PROGRESS,
        )

        assert progress.vm_id == "vm1"
        assert progress.status == VMStatus.IN_PROGRESS
        assert progress.started_at is None
        assert progress.completed_at is None
        assert progress.duration == 0.0
        assert progress.error is None

    def test_to_dict(self):
        """Test converting to dictionary."""
        progress = VMProgress(
            vm_id="vm1",
            status=VMStatus.COMPLETED,
            started_at=100.0,
            completed_at=150.0,
            duration=50.0,
        )

        data = progress.to_dict()

        assert data["vm_id"] == "vm1"
        assert data["status"] == "completed"
        assert data["started_at"] == 100.0
        assert data["completed_at"] == 150.0
        assert data["duration"] == 50.0

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "vm_id": "vm1",
            "status": "in_progress",
            "started_at": 100.0,
            "current_stage": "extraction",
            "stages_completed": ["extraction"],
        }

        progress = VMProgress.from_dict(data)

        assert progress.vm_id == "vm1"
        assert progress.status == VMStatus.IN_PROGRESS
        assert progress.started_at == 100.0
        assert progress.current_stage == "extraction"


class TestBatchProgress:
    """Test BatchProgress dataclass."""

    def test_creation(self):
        """Test creating batch progress."""
        progress = BatchProgress(
            batch_id="batch-1",
            total_vms=10,
            started_at=time.time(),
            updated_at=time.time(),
        )

        assert progress.batch_id == "batch-1"
        assert progress.total_vms == 10
        assert len(progress.vms) == 0

    def test_get_counts(self):
        """Test getting VM counts by status."""
        progress = BatchProgress(
            batch_id="batch-1",
            total_vms=5,
            started_at=time.time(),
            updated_at=time.time(),
        )

        progress.vms["vm1"] = VMProgress("vm1", VMStatus.COMPLETED)
        progress.vms["vm2"] = VMProgress("vm2", VMStatus.COMPLETED)
        progress.vms["vm3"] = VMProgress("vm3", VMStatus.IN_PROGRESS)
        progress.vms["vm4"] = VMProgress("vm4", VMStatus.FAILED)
        progress.vms["vm5"] = VMProgress("vm5", VMStatus.PENDING)

        counts = progress.get_counts()

        assert counts["completed"] == 2
        assert counts["in_progress"] == 1
        assert counts["failed"] == 1
        assert counts["pending"] == 1

    def test_get_completion_percentage(self):
        """Test calculating completion percentage."""
        progress = BatchProgress(
            batch_id="batch-1",
            total_vms=10,
            started_at=time.time(),
            updated_at=time.time(),
        )

        # No VMs completed
        assert progress.get_completion_percentage() == 0.0

        # 5 completed
        for i in range(5):
            progress.vms[f"vm{i}"] = VMProgress(f"vm{i}", VMStatus.COMPLETED)

        assert progress.get_completion_percentage() == 50.0

        # 3 more failed (8 total done)
        for i in range(5, 8):
            progress.vms[f"vm{i}"] = VMProgress(f"vm{i}", VMStatus.FAILED)

        assert progress.get_completion_percentage() == 80.0

    def test_get_estimated_time_remaining(self):
        """Test estimating time remaining."""
        progress = BatchProgress(
            batch_id="batch-1",
            total_vms=10,
            started_at=time.time(),
            updated_at=time.time(),
        )

        # No completed VMs - no estimate
        assert progress.get_estimated_time_remaining() is None

        # Add completed VMs with durations
        progress.vms["vm1"] = VMProgress(
            "vm1", VMStatus.COMPLETED, duration=100.0
        )
        progress.vms["vm2"] = VMProgress(
            "vm2", VMStatus.COMPLETED, duration=200.0
        )

        # Average duration: 150s, 8 VMs remaining = 1200s
        estimated = progress.get_estimated_time_remaining()
        assert estimated == pytest.approx(1200.0, abs=0.1)

    def test_to_dict(self):
        """Test converting batch progress to dict."""
        progress = BatchProgress(
            batch_id="batch-1",
            total_vms=2,
            started_at=100.0,
            updated_at=150.0,
        )

        progress.vms["vm1"] = VMProgress("vm1", VMStatus.COMPLETED)

        data = progress.to_dict()

        assert data["batch_id"] == "batch-1"
        assert data["total_vms"] == 2
        assert "counts" in data
        assert "completion_percentage" in data
        assert "vms" in data
        assert "vm1" in data["vms"]

    def test_from_dict(self):
        """Test creating batch progress from dict."""
        data = {
            "batch_id": "batch-1",
            "total_vms": 2,
            "started_at": 100.0,
            "updated_at": 150.0,
            "vms": {
                "vm1": {
                    "vm_id": "vm1",
                    "status": "completed",
                    "started_at": 100.0,
                    "completed_at": 110.0,
                    "duration": 10.0,
                }
            },
        }

        progress = BatchProgress.from_dict(data)

        assert progress.batch_id == "batch-1"
        assert progress.total_vms == 2
        assert "vm1" in progress.vms
        assert progress.vms["vm1"].status == VMStatus.COMPLETED


class TestProgressTracker:
    """Test ProgressTracker."""

    def test_tracker_creation(self, tmp_path):
        """Test creating progress tracker."""
        progress_file = tmp_path / "progress.json"

        tracker = ProgressTracker(
            progress_file=progress_file,
            batch_id="batch-1",
            total_vms=5,
        )

        assert tracker.progress_file == progress_file
        assert tracker.progress.batch_id == "batch-1"
        assert tracker.progress.total_vms == 5

        # Progress file should be created
        assert progress_file.exists()

    def test_start_vm(self, tmp_path):
        """Test starting VM tracking."""
        tracker = ProgressTracker(
            progress_file=tmp_path / "progress.json",
            batch_id="batch-1",
            total_vms=2,
        )

        tracker.start_vm("vm1")

        assert "vm1" in tracker.progress.vms
        assert tracker.progress.vms["vm1"].status == VMStatus.IN_PROGRESS
        assert tracker.progress.vms["vm1"].started_at is not None

    def test_update_vm_stage(self, tmp_path):
        """Test updating VM stage."""
        tracker = ProgressTracker(
            progress_file=tmp_path / "progress.json",
            batch_id="batch-1",
            total_vms=2,
        )

        tracker.start_vm("vm1")
        tracker.update_vm_stage("vm1", "extraction")

        assert tracker.progress.vms["vm1"].current_stage == "extraction"
        assert "extraction" in tracker.progress.vms["vm1"].stages_completed

    def test_complete_vm_success(self, tmp_path):
        """Test completing VM successfully."""
        tracker = ProgressTracker(
            progress_file=tmp_path / "progress.json",
            batch_id="batch-1",
            total_vms=2,
        )

        tracker.start_vm("vm1")
        time.sleep(0.1)  # Small delay
        tracker.complete_vm("vm1", success=True)

        assert tracker.progress.vms["vm1"].status == VMStatus.COMPLETED
        assert tracker.progress.vms["vm1"].completed_at is not None
        assert tracker.progress.vms["vm1"].duration > 0
        assert tracker.progress.vms["vm1"].error is None

    def test_complete_vm_failure(self, tmp_path):
        """Test completing VM with failure."""
        tracker = ProgressTracker(
            progress_file=tmp_path / "progress.json",
            batch_id="batch-1",
            total_vms=2,
        )

        tracker.start_vm("vm1")
        tracker.complete_vm("vm1", success=False, error="Test error")

        assert tracker.progress.vms["vm1"].status == VMStatus.FAILED
        assert tracker.progress.vms["vm1"].error == "Test error"

    def test_skip_vm(self, tmp_path):
        """Test skipping VM."""
        tracker = ProgressTracker(
            progress_file=tmp_path / "progress.json",
            batch_id="batch-1",
            total_vms=2,
        )

        tracker.skip_vm("vm1", "Already processed")

        assert tracker.progress.vms["vm1"].status == VMStatus.SKIPPED
        assert tracker.progress.vms["vm1"].error == "Already processed"

    def test_complete_batch(self, tmp_path):
        """Test completing batch."""
        tracker = ProgressTracker(
            progress_file=tmp_path / "progress.json",
            batch_id="batch-1",
            total_vms=2,
        )

        tracker.complete_batch()

        assert tracker.progress.completed_at is not None

    def test_get_progress(self, tmp_path):
        """Test getting current progress."""
        tracker = ProgressTracker(
            progress_file=tmp_path / "progress.json",
            batch_id="batch-1",
            total_vms=2,
        )

        tracker.start_vm("vm1")

        progress = tracker.get_progress()

        assert isinstance(progress, BatchProgress)
        assert "vm1" in progress.vms

    def test_progress_persistence(self, tmp_path):
        """Test that progress is persisted to disk."""
        progress_file = tmp_path / "progress.json"

        tracker = ProgressTracker(
            progress_file=progress_file,
            batch_id="batch-1",
            total_vms=2,
        )

        tracker.start_vm("vm1")
        tracker.complete_vm("vm1", success=True)

        # Read file directly
        with open(progress_file, "r") as f:
            data = json.load(f)

        assert data["batch_id"] == "batch-1"
        assert "vm1" in data["vms"]
        assert data["vms"]["vm1"]["status"] == "completed"

    def test_load_progress(self, tmp_path):
        """Test loading progress from file."""
        progress_file = tmp_path / "progress.json"

        # Create tracker and add some progress
        tracker1 = ProgressTracker(
            progress_file=progress_file,
            batch_id="batch-1",
            total_vms=2,
        )
        tracker1.start_vm("vm1")
        tracker1.complete_vm("vm1", success=True)

        # Load progress
        loaded_progress = ProgressTracker.load_progress(progress_file)

        assert loaded_progress is not None
        assert loaded_progress.batch_id == "batch-1"
        assert "vm1" in loaded_progress.vms
        assert loaded_progress.vms["vm1"].status == VMStatus.COMPLETED

    def test_load_progress_nonexistent(self, tmp_path):
        """Test loading progress from nonexistent file."""
        progress_file = tmp_path / "nonexistent.json"

        loaded = ProgressTracker.load_progress(progress_file)

        assert loaded is None

    def test_cleanup(self, tmp_path):
        """Test cleaning up progress file."""
        progress_file = tmp_path / "progress.json"

        tracker = ProgressTracker(
            progress_file=progress_file,
            batch_id="batch-1",
            total_vms=2,
        )

        assert progress_file.exists()

        tracker.cleanup()

        assert not progress_file.exists()

    def test_thread_safety(self, tmp_path):
        """Test thread safety of progress tracker."""
        import threading

        tracker = ProgressTracker(
            progress_file=tmp_path / "progress.json",
            batch_id="batch-1",
            total_vms=100,
        )

        def worker(vm_id):
            tracker.start_vm(vm_id)
            tracker.update_vm_stage(vm_id, "extraction")
            tracker.complete_vm(vm_id, success=True)

        threads = [
            threading.Thread(target=worker, args=(f"vm{i}",))
            for i in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have all 10 VMs
        assert len(tracker.progress.vms) == 10
        assert all(
            vm.status == VMStatus.COMPLETED
            for vm in tracker.progress.vms.values()
        )

    def test_atomic_write(self, tmp_path):
        """Test that writes are atomic."""
        progress_file = tmp_path / "progress.json"

        tracker = ProgressTracker(
            progress_file=progress_file,
            batch_id="batch-1",
            total_vms=2,
        )

        tracker.start_vm("vm1")

        # No .tmp file should exist
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

        # Progress file should exist
        assert progress_file.exists()
