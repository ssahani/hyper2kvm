# SPDX-License-Identifier: LGPL-3.0-or-later
"""Integration tests for checkpoint/resume functionality in batch workflows."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hyper2kvm.manifest.batch_orchestrator import BatchOrchestrator
from hyper2kvm.manifest.checkpoint_manager import CheckpointManager


class TestCheckpointResumeIntegration:
    """Integration tests for checkpoint and resume functionality."""

    @pytest.fixture
    def batch_manifest(self, tmp_path):
        """Create a sample batch manifest."""
        # Create individual VM manifests
        vm_manifests = []
        for i in range(1, 4):
            vm_dir = tmp_path / f"vm{i}"
            vm_dir.mkdir()

            # Create dummy disk
            disk_path = vm_dir / "disk.qcow2"
            disk_path.write_bytes(b"\x00" * 1024)

            manifest = {
                "manifest_version": "1.0",
                "source": {
                    "provider": "test",
                    "vm_id": f"vm{i}",
                    "vm_name": f"test-vm{i}",
                },
                "disks": [
                    {
                        "id": "boot",
                        "source_format": "qcow2",
                        "local_path": str(disk_path),
                        "bytes": 1024,
                        "disk_type": "boot",
                    }
                ],
                "pipeline": {
                    "inspect": {"enabled": False},
                    "fix": {"enabled": False},
                    "convert": {"enabled": False},
                    "validate": {"enabled": False},
                },
                "output": {
                    "directory": str(tmp_path / f"output{i}"),
                    "format": "qcow2",
                },
            }

            manifest_path = vm_dir / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)

            vm_manifests.append(str(manifest_path))

        # Create batch manifest
        batch = {
            "batch_version": "1.0",
            "batch_metadata": {
                "batch_id": "test-checkpoint",
                "parallel_limit": 1,
                "continue_on_error": True,
                "checkpoint": {
                    "enabled": True,
                    "directory": str(tmp_path / "checkpoints"),
                },
            },
            "vms": [
                {"id": f"vm{i}", "manifest": m}
                for i, m in enumerate(vm_manifests, 1)
            ],
        }

        batch_path = tmp_path / "batch.json"
        with open(batch_path, "w") as f:
            json.dump(batch, f, indent=2)

        return batch_path

    def test_checkpoint_saves_progress(self, tmp_path):
        """Test that checkpoint saves progress correctly."""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir, "test-batch")

        # Simulate processing VMs
        manager.save_checkpoint(
            completed_vms=["vm1", "vm2"],
            failed_vms=[{"vm_id": "vm3", "error": "Test error"}],
            total_vms=5,
        )

        # Verify checkpoint was created
        assert manager.has_checkpoint()

        # Load and verify
        data = manager.load_checkpoint()
        assert data["batch_id"] == "test-batch"
        assert len(data["completed_vms"]) == 2
        assert len(data["failed_vms"]) == 1
        assert data["total_vms"] == 5

    def test_resume_from_checkpoint(self, tmp_path):
        """Test resuming batch from checkpoint."""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir, "test-batch")

        # Save initial checkpoint
        manager.save_checkpoint(
            completed_vms=["vm1"],
            failed_vms=[],
            total_vms=3,
        )

        # Create new manager instance (simulating restart)
        manager2 = CheckpointManager(checkpoint_dir, "test-batch")

        # Load checkpoint
        data = manager2.load_checkpoint()

        # Verify resume point
        assert data["resume_from"] == 1
        assert "vm1" in manager2.get_completed_vm_ids()

    def test_checkpoint_skip_logic(self, tmp_path):
        """Test that checkpoint correctly identifies VMs to skip."""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir, "test-batch")

        # Save checkpoint with some completed and failed VMs
        manager.save_checkpoint(
            completed_vms=["vm1", "vm2"],
            failed_vms=[{"vm_id": "vm3", "error": "Failed"}],
            total_vms=5,
        )

        # Test skip logic
        assert manager.should_skip_vm("vm1") is True
        assert manager.should_skip_vm("vm2") is True
        assert manager.should_skip_vm("vm3") is True
        assert manager.should_skip_vm("vm4") is False
        assert manager.should_skip_vm("vm5") is False

    def test_checkpoint_cleanup_on_success(self, tmp_path):
        """Test that checkpoint is cleaned up on successful completion."""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir, "test-batch")

        # Save checkpoint
        manager.save_checkpoint(completed_vms=["vm1"], total_vms=1)
        assert manager.has_checkpoint()

        # Cleanup
        manager.cleanup()
        assert not manager.has_checkpoint()

    def test_checkpoint_with_metadata(self, tmp_path):
        """Test checkpoint preserves batch metadata."""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir, "test-batch")

        metadata = {
            "parallel_limit": 4,
            "continue_on_error": True,
            "profile": "production",
        }

        manager.save_checkpoint(
            completed_vms=["vm1"],
            total_vms=5,
            metadata=metadata,
        )

        data = manager.load_checkpoint()
        assert data["metadata"]["parallel_limit"] == 4
        assert data["metadata"]["continue_on_error"] is True
        assert data["metadata"]["profile"] == "production"

    def test_checkpoint_progress_percentage(self, tmp_path):
        """Test checkpoint progress percentage calculation."""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir, "test-batch")

        # 0% progress
        assert manager.get_progress_percentage() == 0.0

        # 40% progress (2 completed + 2 failed out of 10)
        manager.save_checkpoint(
            completed_vms=["vm1", "vm2"],
            failed_vms=[
                {"vm_id": "vm3", "error": "E1"},
                {"vm_id": "vm4", "error": "E2"},
            ],
            total_vms=10,
        )
        assert manager.get_progress_percentage() == 40.0

        # 100% progress
        manager.save_checkpoint(
            completed_vms=[f"vm{i}" for i in range(1, 11)],
            total_vms=10,
        )
        assert manager.get_progress_percentage() == 100.0

    def test_multiple_checkpoint_updates(self, tmp_path):
        """Test updating checkpoint multiple times during batch."""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir, "test-batch")

        # Simulate incremental progress
        for i in range(1, 6):
            completed = [f"vm{j}" for j in range(1, i + 1)]
            manager.save_checkpoint(completed_vms=completed, total_vms=10)

            data = manager.load_checkpoint()
            assert len(data["completed_vms"]) == i
            assert data["resume_from"] == i

    def test_checkpoint_recovery_after_failure(self, tmp_path):
        """Test recovering from checkpoint after batch failure."""
        checkpoint_dir = tmp_path / "checkpoints"

        # First attempt - process some VMs then "fail"
        manager1 = CheckpointManager(checkpoint_dir, "test-batch")
        manager1.save_checkpoint(
            completed_vms=["vm1", "vm2"],
            failed_vms=[{"vm_id": "vm3", "error": "Network timeout"}],
            total_vms=5,
        )

        # Second attempt - resume from checkpoint
        manager2 = CheckpointManager(checkpoint_dir, "test-batch")
        data = manager2.load_checkpoint()

        # Should resume from VM 4 (skip vm1, vm2, vm3)
        assert data["resume_from"] == 3
        assert not manager2.should_skip_vm("vm4")
        assert not manager2.should_skip_vm("vm5")

    def test_checkpoint_atomic_writes(self, tmp_path):
        """Test that checkpoint writes are atomic (no partial writes)."""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir, "test-batch")

        # Save checkpoint
        manager.save_checkpoint(completed_vms=["vm1", "vm2"], total_vms=5)

        # Verify no temp files remain
        temp_files = list(checkpoint_dir.glob("*.tmp"))
        assert len(temp_files) == 0

        # Verify checkpoint file is valid JSON
        data = manager.load_checkpoint()
        assert data["batch_id"] == "test-batch"


class TestCheckpointErrorHandling:
    """Test error handling in checkpoint operations."""

    def test_load_nonexistent_checkpoint(self, tmp_path):
        """Test loading checkpoint that doesn't exist."""
        from hyper2kvm.manifest.checkpoint_manager import CheckpointError

        manager = CheckpointManager(tmp_path, "nonexistent")

        with pytest.raises(CheckpointError, match="No checkpoint found"):
            manager.load_checkpoint()

    def test_load_corrupt_checkpoint(self, tmp_path):
        """Test loading corrupted checkpoint file."""
        from hyper2kvm.manifest.checkpoint_manager import CheckpointError

        manager = CheckpointManager(tmp_path, "test-batch")

        # Write invalid JSON
        manager.checkpoint_file.write_text("{invalid json")

        with pytest.raises(CheckpointError, match="Invalid checkpoint JSON"):
            manager.load_checkpoint()

    def test_load_checkpoint_missing_fields(self, tmp_path):
        """Test loading checkpoint with missing required fields."""
        from hyper2kvm.manifest.checkpoint_manager import CheckpointError

        manager = CheckpointManager(tmp_path, "test-batch")

        # Write checkpoint missing required field
        invalid_data = {
            "batch_id": "test-batch",
            "timestamp": time.time(),
            # Missing 'completed_vms'
        }

        with open(manager.checkpoint_file, "w") as f:
            json.dump(invalid_data, f)

        with pytest.raises(CheckpointError, match="missing 'completed_vms'"):
            manager.load_checkpoint()

    def test_checkpoint_batch_id_mismatch(self, tmp_path, caplog):
        """Test warning when checkpoint batch_id doesn't match."""
        # Create checkpoint with batch-1
        manager1 = CheckpointManager(tmp_path, "batch-1")
        manager1.save_checkpoint(completed_vms=["vm1"], total_vms=5)

        # Try to load with batch-2 (same file)
        manager2 = CheckpointManager(tmp_path, "batch-2")
        manager2.checkpoint_file = manager1.checkpoint_file

        data = manager2.load_checkpoint()

        # Should load but warn
        assert data["batch_id"] == "batch-1"
        assert "batch_id mismatch" in caplog.text.lower()
