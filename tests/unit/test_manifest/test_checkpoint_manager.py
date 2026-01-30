# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for CheckpointManager."""

import json
import tempfile
import time
from pathlib import Path

import pytest

from hyper2kvm.manifest.checkpoint_manager import CheckpointError, CheckpointManager


class TestCheckpointManager:
    """Test CheckpointManager functionality."""

    def test_initialization(self, tmp_path):
        """Test CheckpointManager initialization."""
        manager = CheckpointManager(
            checkpoint_dir=tmp_path,
            batch_id="test-batch",
        )
        assert manager.checkpoint_dir == tmp_path.resolve()
        assert manager.batch_id == "test-batch"
        assert tmp_path.exists()

    def test_sanitize_filename(self):
        """Test filename sanitization."""
        result = CheckpointManager._sanitize_filename("my-batch/with:special*chars")
        assert "/" not in result
        assert ":" not in result
        assert "*" not in result
        assert result == "my-batch-with-special-chars"

    def test_sanitize_filename_length_limit(self):
        """Test filename length is limited."""
        long_name = "a" * 200
        result = CheckpointManager._sanitize_filename(long_name)
        assert len(result) <= 100

    def test_no_checkpoint_initially(self, tmp_path):
        """Test has_checkpoint returns False initially."""
        manager = CheckpointManager(tmp_path, "test-batch")
        assert not manager.has_checkpoint()

    def test_save_and_load_checkpoint(self, tmp_path):
        """Test saving and loading checkpoint."""
        manager = CheckpointManager(tmp_path, "test-batch")

        # Save checkpoint
        completed = ["vm1", "vm2"]
        failed = [{"vm_id": "vm3", "error": "Test error"}]
        manager.save_checkpoint(
            completed_vms=completed,
            failed_vms=failed,
            total_vms=5,
        )

        assert manager.has_checkpoint()

        # Load checkpoint
        data = manager.load_checkpoint()
        assert data["batch_id"] == "test-batch"
        assert data["completed_vms"] == completed
        assert data["failed_vms"] == failed
        assert data["total_vms"] == 5
        assert data["resume_from"] == 3  # 2 completed + 1 failed
        assert "timestamp" in data
        assert "timestamp_iso" in data

    def test_load_nonexistent_checkpoint(self, tmp_path):
        """Test loading checkpoint that doesn't exist."""
        manager = CheckpointManager(tmp_path, "test-batch")

        with pytest.raises(CheckpointError, match="No checkpoint found"):
            manager.load_checkpoint()

    def test_checkpoint_atomic_write(self, tmp_path):
        """Test checkpoint uses atomic write (temp + replace)."""
        manager = CheckpointManager(tmp_path, "test-batch")

        manager.save_checkpoint(
            completed_vms=["vm1"],
            total_vms=2,
        )

        # Verify no temp file left behind
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

        # Verify checkpoint file exists
        assert manager.checkpoint_file.exists()

    def test_get_completed_vm_ids(self, tmp_path):
        """Test getting completed VM IDs."""
        manager = CheckpointManager(tmp_path, "test-batch")

        # No checkpoint initially
        assert manager.get_completed_vm_ids() == set()

        # Save checkpoint
        manager.save_checkpoint(
            completed_vms=["vm1", "vm2", "vm3"],
            total_vms=5,
        )

        # Get completed IDs
        completed = manager.get_completed_vm_ids()
        assert completed == {"vm1", "vm2", "vm3"}

    def test_get_failed_vm_ids(self, tmp_path):
        """Test getting failed VM IDs."""
        manager = CheckpointManager(tmp_path, "test-batch")

        # No checkpoint initially
        assert manager.get_failed_vm_ids() == set()

        # Save checkpoint
        manager.save_checkpoint(
            completed_vms=["vm1"],
            failed_vms=[
                {"vm_id": "vm2", "error": "Error 1"},
                {"vm_id": "vm3", "error": "Error 2"},
            ],
            total_vms=5,
        )

        # Get failed IDs
        failed = manager.get_failed_vm_ids()
        assert failed == {"vm2", "vm3"}

    def test_should_skip_vm(self, tmp_path):
        """Test should_skip_vm logic."""
        manager = CheckpointManager(tmp_path, "test-batch")

        manager.save_checkpoint(
            completed_vms=["vm1", "vm2"],
            failed_vms=[{"vm_id": "vm3", "error": "Test"}],
            total_vms=5,
        )

        # Completed and failed VMs should be skipped
        assert manager.should_skip_vm("vm1")
        assert manager.should_skip_vm("vm2")
        assert manager.should_skip_vm("vm3")

        # Unprocessed VMs should not be skipped
        assert not manager.should_skip_vm("vm4")
        assert not manager.should_skip_vm("vm5")

    def test_cleanup(self, tmp_path):
        """Test checkpoint cleanup."""
        manager = CheckpointManager(tmp_path, "test-batch")

        # Save checkpoint
        manager.save_checkpoint(completed_vms=["vm1"], total_vms=2)
        assert manager.has_checkpoint()

        # Cleanup
        manager.cleanup()
        assert not manager.has_checkpoint()

    def test_reset(self, tmp_path):
        """Test checkpoint reset."""
        manager = CheckpointManager(tmp_path, "test-batch")

        # Save checkpoint
        manager.save_checkpoint(completed_vms=["vm1"], total_vms=2)
        assert manager.has_checkpoint()

        # Reset
        manager.reset()
        assert not manager.has_checkpoint()

    def test_get_progress_percentage(self, tmp_path):
        """Test progress percentage calculation."""
        manager = CheckpointManager(tmp_path, "test-batch")

        # No checkpoint
        assert manager.get_progress_percentage() == 0.0

        # 2 completed out of 10 = 20%
        manager.save_checkpoint(
            completed_vms=["vm1", "vm2"],
            total_vms=10,
        )
        assert manager.get_progress_percentage() == 20.0

        # 3 completed + 2 failed out of 10 = 50%
        manager.save_checkpoint(
            completed_vms=["vm1", "vm2", "vm3"],
            failed_vms=[
                {"vm_id": "vm4", "error": "Test"},
                {"vm_id": "vm5", "error": "Test"},
            ],
            total_vms=10,
        )
        assert manager.get_progress_percentage() == 50.0

        # All complete = 100%
        manager.save_checkpoint(
            completed_vms=["vm1", "vm2", "vm3", "vm4", "vm5"],
            total_vms=5,
        )
        assert manager.get_progress_percentage() == 100.0

    def test_checkpoint_with_metadata(self, tmp_path):
        """Test checkpoint with custom metadata."""
        manager = CheckpointManager(tmp_path, "test-batch")

        metadata = {
            "parallel_limit": 4,
            "continue_on_error": True,
            "custom_field": "custom_value",
        }

        manager.save_checkpoint(
            completed_vms=["vm1"],
            total_vms=5,
            metadata=metadata,
        )

        data = manager.load_checkpoint()
        assert data["metadata"] == metadata

    def test_checkpoint_batch_id_mismatch_warning(self, tmp_path, caplog):
        """Test warning when checkpoint batch_id doesn't match."""
        # Save checkpoint with one batch_id
        manager1 = CheckpointManager(tmp_path, "batch-1")
        manager1.save_checkpoint(completed_vms=["vm1"], total_vms=5)

        # Load with different batch_id (same checkpoint file)
        manager2 = CheckpointManager(tmp_path, "batch-2")

        # Force same checkpoint file
        manager2.checkpoint_file = manager1.checkpoint_file

        data = manager2.load_checkpoint()

        # Should load but warn about mismatch
        assert data["batch_id"] == "batch-1"
        assert "batch_id mismatch" in caplog.text.lower()

    def test_invalid_checkpoint_json(self, tmp_path):
        """Test loading invalid JSON checkpoint."""
        manager = CheckpointManager(tmp_path, "test-batch")

        # Write invalid JSON
        manager.checkpoint_file.write_text("invalid json{")

        with pytest.raises(CheckpointError, match="Invalid checkpoint JSON"):
            manager.load_checkpoint()

    def test_checkpoint_missing_required_fields(self, tmp_path):
        """Test loading checkpoint with missing required fields."""
        manager = CheckpointManager(tmp_path, "test-batch")

        # Write checkpoint missing required field
        invalid_data = {
            "batch_id": "test-batch",
            "timestamp": time.time(),
            # Missing 'completed_vms' field
        }

        with open(manager.checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(invalid_data, f)

        with pytest.raises(CheckpointError, match="missing 'completed_vms' field"):
            manager.load_checkpoint()

    def test_checkpoint_directory_creation_failure(self):
        """Test error when checkpoint directory creation fails."""
        # Try to create checkpoint in invalid location
        with pytest.raises(CheckpointError, match="Failed to create checkpoint directory"):
            CheckpointManager(
                checkpoint_dir="/invalid/readonly/path/that/cannot/be/created",
                batch_id="test-batch",
            )

    def test_checkpoint_save_with_empty_lists(self, tmp_path):
        """Test checkpoint save with empty VM lists."""
        manager = CheckpointManager(tmp_path, "test-batch")

        manager.save_checkpoint(
            completed_vms=[],
            failed_vms=[],
            total_vms=0,
        )

        data = manager.load_checkpoint()
        assert data["completed_vms"] == []
        assert data["failed_vms"] == []
        assert data["total_vms"] == 0
        assert data["resume_from"] == 0

    def test_multiple_checkpoint_updates(self, tmp_path):
        """Test updating checkpoint multiple times."""
        manager = CheckpointManager(tmp_path, "test-batch")

        # First update
        manager.save_checkpoint(completed_vms=["vm1"], total_vms=5)
        data1 = manager.load_checkpoint()
        assert len(data1["completed_vms"]) == 1

        # Second update
        manager.save_checkpoint(completed_vms=["vm1", "vm2"], total_vms=5)
        data2 = manager.load_checkpoint()
        assert len(data2["completed_vms"]) == 2

        # Third update
        manager.save_checkpoint(completed_vms=["vm1", "vm2", "vm3"], total_vms=5)
        data3 = manager.load_checkpoint()
        assert len(data3["completed_vms"]) == 3

        # Verify timestamps are different
        assert data3["timestamp"] >= data2["timestamp"] >= data1["timestamp"]
