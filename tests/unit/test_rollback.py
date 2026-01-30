# SPDX-License-Identifier: LGPL-3.0-or-later
# tests/unit/test_rollback.py
"""
Unit tests for rollback framework.
"""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from hyper2kvm.rollback import (
    SnapshotManager,
    SnapshotType,
    StateTracker,
    MigrationState,
    RollbackExecutor,
    RollbackAction,
    RollbackValidator,
    ValidationStatus,
    RollbackOrchestrator,
    RollbackStrategy,
)


@pytest.fixture
def logger():
    """Create test logger."""
    return logging.getLogger("test")


@pytest.fixture
def snapshot_dir(tmp_path):
    """Create temporary snapshot directory."""
    return tmp_path / "snapshots"


@pytest.fixture
def test_disk_image(tmp_path):
    """Create test disk image."""
    img_path = tmp_path / "test-disk.qcow2"
    img_path.write_bytes(b"test disk image content" * 1000)
    return img_path


# SnapshotManager Tests

def test_snapshot_manager_initialization(logger, snapshot_dir):
    """Test snapshot manager initialization."""
    manager = SnapshotManager(logger, snapshot_dir)

    assert manager.snapshot_dir == snapshot_dir
    assert snapshot_dir.exists()


def test_snapshot_manager_create_full_snapshot(logger, snapshot_dir, test_disk_image):
    """Test creating full snapshot."""
    manager = SnapshotManager(logger, snapshot_dir)

    snapshot = manager.create_snapshot(
        test_disk_image,
        snapshot_type=SnapshotType.FULL,
        compute_checksum=False,
    )

    assert snapshot.snapshot_type == SnapshotType.FULL
    assert snapshot.source_path == str(test_disk_image)
    assert Path(snapshot.snapshot_path).exists()
    assert snapshot.size_bytes > 0


def test_snapshot_manager_list_snapshots(logger, snapshot_dir, test_disk_image):
    """Test listing snapshots."""
    manager = SnapshotManager(logger, snapshot_dir)

    # Create multiple snapshots
    snapshot1 = manager.create_snapshot(test_disk_image, SnapshotType.FULL)
    import time; time.sleep(0.01)  # Ensure different timestamps
    snapshot2 = manager.create_snapshot(test_disk_image, SnapshotType.FULL)

    snapshots = manager.list_snapshots()

    assert len(snapshots) == 2
    assert snapshot1.snapshot_id in [s.snapshot_id for s in snapshots]
    assert snapshot2.snapshot_id in [s.snapshot_id for s in snapshots]


def test_snapshot_manager_get_snapshot(logger, snapshot_dir, test_disk_image):
    """Test getting snapshot by ID."""
    manager = SnapshotManager(logger, snapshot_dir)

    snapshot = manager.create_snapshot(test_disk_image, SnapshotType.FULL)
    retrieved = manager.get_snapshot(snapshot.snapshot_id)

    assert retrieved is not None
    assert retrieved.snapshot_id == snapshot.snapshot_id


def test_snapshot_manager_delete_snapshot(logger, snapshot_dir, test_disk_image):
    """Test deleting snapshot."""
    manager = SnapshotManager(logger, snapshot_dir)

    snapshot = manager.create_snapshot(test_disk_image, SnapshotType.FULL)
    snapshot_path = Path(snapshot.snapshot_path)

    assert snapshot_path.exists()

    manager.delete_snapshot(snapshot.snapshot_id)

    assert not snapshot_path.exists()
    assert manager.get_snapshot(snapshot.snapshot_id) is None


# StateTracker Tests

def test_state_tracker_initialization(logger, tmp_path):
    """Test state tracker initialization."""
    state_file = tmp_path / "state.json"
    tracker = StateTracker(logger, state_file)

    assert tracker.get_current_state() == MigrationState.NOT_STARTED
    assert len(tracker.get_checkpoints()) == 0


def test_state_tracker_checkpoint(logger, tmp_path):
    """Test creating checkpoint."""
    state_file = tmp_path / "state.json"
    tracker = StateTracker(logger, state_file)

    tracker.checkpoint(
        MigrationState.SNAPSHOT_CREATED,
        "Snapshot created",
        snapshot_id="test-snapshot",
    )

    assert tracker.get_current_state() == MigrationState.SNAPSHOT_CREATED
    assert len(tracker.get_checkpoints()) == 1

    checkpoint = tracker.get_checkpoints()[0]
    assert checkpoint.state == MigrationState.SNAPSHOT_CREATED
    assert checkpoint.data["snapshot_id"] == "test-snapshot"


def test_state_tracker_save_and_load(logger, tmp_path):
    """Test saving and loading state."""
    state_file = tmp_path / "state.json"

    # Create tracker and add checkpoints
    tracker1 = StateTracker(logger, state_file)
    tracker1.checkpoint(MigrationState.SNAPSHOT_CREATED, "Test")
    tracker1.set_metadata("test_key", "test_value")

    # Create new tracker (should load saved state)
    tracker2 = StateTracker(logger, state_file)

    assert tracker2.get_current_state() == MigrationState.SNAPSHOT_CREATED
    assert len(tracker2.get_checkpoints()) == 1
    assert tracker2.get_metadata("test_key") == "test_value"


def test_state_tracker_rollback_plan(logger, tmp_path):
    """Test generating rollback plan."""
    tracker = StateTracker(logger)

    tracker.checkpoint(MigrationState.SNAPSHOT_CREATED, "Snapshot", reversible=True)
    tracker.checkpoint(MigrationState.PRE_MIGRATION_CHECKS, "Checks", reversible=True)
    tracker.checkpoint(MigrationState.STORAGE_ACTIVATED, "Storage", reversible=False)
    tracker.checkpoint(MigrationState.BOOTLOADER_FIXED, "Bootloader", reversible=True)

    rollback_plan = tracker.get_rollback_plan()

    # Should only include reversible checkpoints after last irreversible
    assert len(rollback_plan) == 1
    assert rollback_plan[0].state == MigrationState.BOOTLOADER_FIXED


# RollbackExecutor Tests

def test_rollback_executor_initialization(logger):
    """Test rollback executor initialization."""
    executor = RollbackExecutor(logger)

    assert len(executor.get_results()) == 0


def test_rollback_executor_revert_file(logger, tmp_path):
    """Test file revert operation."""
    executor = RollbackExecutor(logger)

    # Create test files
    file_path = tmp_path / "test.txt"
    backup_path = tmp_path / "test.txt.backup"

    file_path.write_text("modified content")
    backup_path.write_text("original content")

    result = executor.execute_revert_file(file_path, backup_path)

    assert result.success is True
    assert result.action == RollbackAction.REVERT_FILE
    assert file_path.read_text() == "original content"


def test_rollback_executor_remove_file(logger, tmp_path):
    """Test file removal operation."""
    executor = RollbackExecutor(logger)

    file_path = tmp_path / "test.txt"
    file_path.write_text("test content")

    result = executor.execute_remove_file(file_path)

    assert result.success is True
    assert result.action == RollbackAction.REMOVE_FILE
    assert not file_path.exists()


def test_rollback_executor_custom_action(logger):
    """Test custom action execution."""
    executor = RollbackExecutor(logger)

    executed = {"flag": False}

    def custom_action():
        executed["flag"] = True

    result = executor.execute_custom_action(custom_action, "test_action")

    assert result.success is True
    assert result.action == RollbackAction.CUSTOM
    assert executed["flag"] is True


def test_rollback_executor_summary(logger, tmp_path):
    """Test execution summary."""
    executor = RollbackExecutor(logger)

    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"

    file1.write_text("test")
    file2.write_text("test")

    executor.execute_remove_file(file1)
    executor.execute_remove_file(file2)

    summary = executor.get_summary()

    assert summary["total_actions"] == 2
    assert summary["successful"] == 2
    assert summary["failed"] == 0
    assert summary["success_rate"] == 100.0


# RollbackValidator Tests

def test_rollback_validator_initialization(logger):
    """Test rollback validator initialization."""
    validator = RollbackValidator(logger)

    assert len(validator.get_results()) == 0


def test_rollback_validator_file_restored(logger, tmp_path):
    """Test file restoration validation."""
    validator = RollbackValidator(logger)

    file_path = tmp_path / "test.txt"
    file_path.write_text("test")

    result = validator.validate_file_restored(file_path, expected_exists=True)

    assert result.status == ValidationStatus.PASS
    assert result.check_name == "file_restored"


def test_rollback_validator_file_missing(logger, tmp_path):
    """Test validation of missing file."""
    validator = RollbackValidator(logger)

    file_path = tmp_path / "nonexistent.txt"

    result = validator.validate_file_restored(file_path, expected_exists=False)

    assert result.status == ValidationStatus.PASS


def test_rollback_validator_state(logger, tmp_path):
    """Test state validation."""
    validator = RollbackValidator(logger)
    tracker = StateTracker(logger)

    tracker.checkpoint(MigrationState.ROLLED_BACK, "Rolled back")

    result = validator.validate_state(tracker, MigrationState.ROLLED_BACK)

    assert result.status == ValidationStatus.PASS


def test_rollback_validator_summary(logger):
    """Test validation summary."""
    validator = RollbackValidator(logger)
    tracker = StateTracker(logger)

    tracker.checkpoint(MigrationState.ROLLED_BACK, "Test")

    validator.validate_state(tracker, MigrationState.ROLLED_BACK)
    validator.validate_state(tracker, MigrationState.COMPLETED)  # Will fail

    summary = validator.get_summary()

    assert summary["total_checks"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["success"] is False


# RollbackOrchestrator Tests

def test_orchestrator_initialization(logger, tmp_path):
    """Test orchestrator initialization."""
    orchestrator = RollbackOrchestrator(
        logger,
        snapshot_dir=tmp_path / "snapshots",
        state_file=tmp_path / "state.json",
    )

    assert orchestrator.snapshot_manager is not None
    assert orchestrator.state_tracker is not None
    assert orchestrator.executor is not None
    assert orchestrator.validator is not None


def test_orchestrator_partial_rollback(logger, tmp_path):
    """Test partial rollback."""
    orchestrator = RollbackOrchestrator(
        logger,
        snapshot_dir=tmp_path / "snapshots",
    )

    # Create test files
    file_path = tmp_path / "test.txt"
    backup_path = tmp_path / "test.txt.backup"
    remove_file = tmp_path / "remove.txt"

    file_path.write_text("modified")
    backup_path.write_text("original")
    remove_file.write_text("to remove")

    report = orchestrator.execute_partial_rollback(
        revert_files=[(str(file_path), str(backup_path))],
        remove_files=[str(remove_file)],
        validate=True,
    )

    assert report.success is True
    assert report.strategy == RollbackStrategy.PARTIAL
    assert report.actions_executed == 2
    assert file_path.read_text() == "original"
    assert not remove_file.exists()


def test_orchestrator_markdown_report(logger, tmp_path):
    """Test Markdown report generation."""
    orchestrator = RollbackOrchestrator(
        logger,
        snapshot_dir=tmp_path / "snapshots",
    )

    file_path = tmp_path / "test.txt"
    backup_path = tmp_path / "test.txt.backup"

    file_path.write_text("modified")
    backup_path.write_text("original")

    report = orchestrator.execute_partial_rollback(
        revert_files=[(str(file_path), str(backup_path))],
    )

    markdown = orchestrator.generate_markdown_report(report)

    assert "# Rollback Report" in markdown
    assert "## Summary" in markdown
    assert report.rollback_id in markdown


def test_orchestrator_save_reports(logger, tmp_path):
    """Test saving rollback reports."""
    orchestrator = RollbackOrchestrator(
        logger,
        snapshot_dir=tmp_path / "snapshots",
    )

    file_path = tmp_path / "test.txt"
    backup_path = tmp_path / "test.txt.backup"

    file_path.write_text("modified")
    backup_path.write_text("original")

    report = orchestrator.execute_partial_rollback(
        revert_files=[(str(file_path), str(backup_path))],
    )

    output_dir = tmp_path / "reports"
    saved_files = orchestrator.save_report(report, output_dir)

    assert "json" in saved_files
    assert "markdown" in saved_files

    json_file = Path(saved_files["json"])
    md_file = Path(saved_files["markdown"])

    assert json_file.exists()
    assert md_file.exists()

    # Verify content
    json_content = json.loads(json_file.read_text())
    md_content = md_file.read_text()

    assert json_content["rollback_id"] == report.rollback_id
    assert "# Rollback Report" in md_content
