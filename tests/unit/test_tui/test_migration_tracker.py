# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Unit tests for migration tracker.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from hyper2kvm.tui.migration_tracker import (
    MigrationRecord,
    MigrationStatus,
    MigrationTracker,
    create_migration_id,
)


class TestMigrationRecord:
    """Tests for MigrationRecord dataclass."""

    def test_record_creation(self):
        """Test creating a migration record."""
        record = MigrationRecord(
            id="mig_001",
            vm_name="test-vm",
            source_type="vsphere",
            status=MigrationStatus.PENDING,
            start_time="2026-01-26T10:00:00",
        )

        assert record.id == "mig_001"
        assert record.vm_name == "test-vm"
        assert record.source_type == "vsphere"
        assert record.status == MigrationStatus.PENDING
        assert record.start_time == "2026-01-26T10:00:00"
        assert record.progress == 0.0
        assert record.end_time is None

    def test_record_to_dict(self):
        """Test converting record to dict."""
        record = MigrationRecord(
            id="mig_001",
            vm_name="test-vm",
            source_type="local",
            status=MigrationStatus.RUNNING,
            start_time="2026-01-26T10:00:00",
            progress=50.0,
        )

        data = record.to_dict()

        assert isinstance(data, dict)
        assert data["id"] == "mig_001"
        assert data["vm_name"] == "test-vm"
        assert data["progress"] == 50.0

    def test_record_from_dict(self):
        """Test creating record from dict."""
        data = {
            "id": "mig_001",
            "vm_name": "test-vm",
            "source_type": "hyperv",
            "status": "completed",
            "start_time": "2026-01-26T10:00:00",
            "end_time": "2026-01-26T11:00:00",
            "progress": 100.0,
            "error_message": None,
            "output_path": "/tmp/output",
            "source_path": None,
            "size_mb": 1024.5,
            "metadata": {},
        }

        record = MigrationRecord.from_dict(data)

        assert record.id == "mig_001"
        assert record.status == MigrationStatus.COMPLETED
        assert record.size_mb == 1024.5

    def test_is_active(self):
        """Test is_active method."""
        pending = MigrationRecord(
            id="1", vm_name="test", source_type="local",
            status=MigrationStatus.PENDING, start_time="2026-01-26T10:00:00"
        )
        running = MigrationRecord(
            id="2", vm_name="test", source_type="local",
            status=MigrationStatus.RUNNING, start_time="2026-01-26T10:00:00"
        )
        paused = MigrationRecord(
            id="3", vm_name="test", source_type="local",
            status=MigrationStatus.PAUSED, start_time="2026-01-26T10:00:00"
        )
        completed = MigrationRecord(
            id="4", vm_name="test", source_type="local",
            status=MigrationStatus.COMPLETED, start_time="2026-01-26T10:00:00"
        )

        assert pending.is_active() is True
        assert running.is_active() is True
        assert paused.is_active() is True
        assert completed.is_active() is False

    def test_is_completed(self):
        """Test is_completed method."""
        completed = MigrationRecord(
            id="1", vm_name="test", source_type="local",
            status=MigrationStatus.COMPLETED, start_time="2026-01-26T10:00:00"
        )
        failed = MigrationRecord(
            id="2", vm_name="test", source_type="local",
            status=MigrationStatus.FAILED, start_time="2026-01-26T10:00:00"
        )

        assert completed.is_completed() is True
        assert failed.is_completed() is False

    def test_is_failed(self):
        """Test is_failed method."""
        failed = MigrationRecord(
            id="1", vm_name="test", source_type="local",
            status=MigrationStatus.FAILED, start_time="2026-01-26T10:00:00",
            error_message="Test error"
        )
        completed = MigrationRecord(
            id="2", vm_name="test", source_type="local",
            status=MigrationStatus.COMPLETED, start_time="2026-01-26T10:00:00"
        )

        assert failed.is_failed() is True
        assert completed.is_failed() is False

    def test_duration_seconds(self):
        """Test duration calculation."""
        record = MigrationRecord(
            id="1", vm_name="test", source_type="local",
            status=MigrationStatus.COMPLETED,
            start_time="2026-01-26T10:00:00",
            end_time="2026-01-26T10:05:30",
        )

        duration = record.duration_seconds()
        assert duration == 330.0  # 5 minutes 30 seconds

    def test_duration_seconds_no_end_time(self):
        """Test duration when migration not finished."""
        record = MigrationRecord(
            id="1", vm_name="test", source_type="local",
            status=MigrationStatus.RUNNING,
            start_time="2026-01-26T10:00:00",
        )

        assert record.duration_seconds() is None


class TestMigrationTracker:
    """Tests for MigrationTracker class."""

    def test_tracker_creation(self, tmp_path):
        """Test creating a migration tracker."""
        history_path = tmp_path / "history.json"
        tracker = MigrationTracker(history_path=history_path)

        assert tracker.history_path == history_path
        assert tracker.migrations == {}

    def test_tracker_with_logger(self, tmp_path):
        """Test creating tracker with custom logger."""
        history_path = tmp_path / "history.json"
        logger = logging.getLogger("test")
        tracker = MigrationTracker(history_path=history_path, logger=logger)

        assert tracker.logger == logger

    def test_load_nonexistent_file(self, tmp_path):
        """Test loading from nonexistent history file."""
        history_path = tmp_path / "nonexistent.json"
        tracker = MigrationTracker(history_path=history_path)

        migrations = tracker.load()
        assert migrations == {}

    def test_load_valid_history(self, tmp_path):
        """Test loading valid history file."""
        history_path = tmp_path / "history.json"
        test_data = {
            "mig_001": {
                "id": "mig_001",
                "vm_name": "test-vm",
                "source_type": "vsphere",
                "status": "completed",
                "start_time": "2026-01-26T10:00:00",
                "end_time": "2026-01-26T11:00:00",
                "progress": 100.0,
                "error_message": None,
                "output_path": None,
                "source_path": None,
                "size_mb": None,
                "metadata": {},
            }
        }
        history_path.write_text(json.dumps(test_data))

        tracker = MigrationTracker(history_path=history_path)
        migrations = tracker.load()

        assert len(migrations) == 1
        assert "mig_001" in migrations
        assert migrations["mig_001"].vm_name == "test-vm"

    def test_load_invalid_json(self, tmp_path):
        """Test loading invalid JSON returns empty dict."""
        history_path = tmp_path / "invalid.json"
        history_path.write_text("{ invalid json }")

        tracker = MigrationTracker(history_path=history_path)
        migrations = tracker.load()

        assert migrations == {}

    def test_save_creates_directory(self, tmp_path):
        """Test save creates parent directory."""
        history_path = tmp_path / "subdir" / "history.json"
        tracker = MigrationTracker(history_path=history_path)

        tracker.migrations["mig_001"] = MigrationRecord(
            id="mig_001",
            vm_name="test",
            source_type="local",
            status=MigrationStatus.COMPLETED,
            start_time="2026-01-26T10:00:00",
        )

        result = tracker.save()

        assert result is True
        assert history_path.exists()
        assert history_path.parent.exists()

    def test_save_and_load_roundtrip(self, tmp_path):
        """Test save and load preserves data."""
        history_path = tmp_path / "history.json"
        tracker = MigrationTracker(history_path=history_path)

        record = MigrationRecord(
            id="mig_001",
            vm_name="test-vm",
            source_type="vsphere",
            status=MigrationStatus.COMPLETED,
            start_time="2026-01-26T10:00:00",
            end_time="2026-01-26T11:00:00",
            progress=100.0,
            size_mb=2048.5,
        )
        tracker.migrations["mig_001"] = record
        tracker.save()

        # Load with new tracker
        tracker2 = MigrationTracker(history_path=history_path)
        tracker2.load()

        assert len(tracker2.migrations) == 1
        loaded = tracker2.migrations["mig_001"]
        assert loaded.vm_name == "test-vm"
        assert loaded.size_mb == 2048.5

    def test_add_migration(self, tmp_path):
        """Test adding a migration record."""
        history_path = tmp_path / "history.json"
        tracker = MigrationTracker(history_path=history_path)

        record = MigrationRecord(
            id="mig_001",
            vm_name="test-vm",
            source_type="local",
            status=MigrationStatus.RUNNING,
            start_time="2026-01-26T10:00:00",
        )

        result = tracker.add_migration(record)

        assert result is True
        assert "mig_001" in tracker.migrations
        assert history_path.exists()

    def test_update_migration(self, tmp_path):
        """Test updating a migration record."""
        history_path = tmp_path / "history.json"
        tracker = MigrationTracker(history_path=history_path)

        record = MigrationRecord(
            id="mig_001",
            vm_name="test-vm",
            source_type="local",
            status=MigrationStatus.RUNNING,
            start_time="2026-01-26T10:00:00",
            progress=0.0,
        )
        tracker.migrations["mig_001"] = record

        result = tracker.update_migration(
            "mig_001",
            status=MigrationStatus.COMPLETED,
            progress=100.0,
            end_time="2026-01-26T11:00:00"
        )

        assert result is True
        updated = tracker.migrations["mig_001"]
        assert updated.status == MigrationStatus.COMPLETED
        assert updated.progress == 100.0
        assert updated.end_time == "2026-01-26T11:00:00"

    def test_update_nonexistent_migration(self, tmp_path):
        """Test updating nonexistent migration returns False."""
        history_path = tmp_path / "history.json"
        tracker = MigrationTracker(history_path=history_path)

        result = tracker.update_migration("nonexistent", status=MigrationStatus.COMPLETED)

        assert result is False

    def test_get_migration(self, tmp_path):
        """Test getting a migration by ID."""
        history_path = tmp_path / "history.json"
        tracker = MigrationTracker(history_path=history_path)

        record = MigrationRecord(
            id="mig_001",
            vm_name="test-vm",
            source_type="local",
            status=MigrationStatus.COMPLETED,
            start_time="2026-01-26T10:00:00",
        )
        tracker.migrations["mig_001"] = record

        retrieved = tracker.get_migration("mig_001")

        assert retrieved is not None
        assert retrieved.id == "mig_001"
        assert tracker.get_migration("nonexistent") is None

    def test_get_active_migrations(self, tmp_path):
        """Test getting active migrations."""
        history_path = tmp_path / "history.json"
        tracker = MigrationTracker(history_path=history_path)

        tracker.migrations["mig_001"] = MigrationRecord(
            id="mig_001", vm_name="vm1", source_type="local",
            status=MigrationStatus.RUNNING, start_time="2026-01-26T10:00:00"
        )
        tracker.migrations["mig_002"] = MigrationRecord(
            id="mig_002", vm_name="vm2", source_type="local",
            status=MigrationStatus.COMPLETED, start_time="2026-01-26T10:00:00"
        )
        tracker.migrations["mig_003"] = MigrationRecord(
            id="mig_003", vm_name="vm3", source_type="local",
            status=MigrationStatus.PENDING, start_time="2026-01-26T10:00:00"
        )

        active = tracker.get_active_migrations()

        assert len(active) == 2
        assert any(m.id == "mig_001" for m in active)
        assert any(m.id == "mig_003" for m in active)

    def test_get_completed_today(self, tmp_path):
        """Test getting migrations completed today."""
        history_path = tmp_path / "history.json"
        tracker = MigrationTracker(history_path=history_path)

        today = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)

        tracker.migrations["mig_today"] = MigrationRecord(
            id="mig_today", vm_name="vm-today", source_type="local",
            status=MigrationStatus.COMPLETED,
            start_time=today.isoformat(),
            end_time=today.replace(hour=11).isoformat(),
        )
        tracker.migrations["mig_yesterday"] = MigrationRecord(
            id="mig_yesterday", vm_name="vm-yesterday", source_type="local",
            status=MigrationStatus.COMPLETED,
            start_time=yesterday.isoformat(),
            end_time=yesterday.replace(hour=11).isoformat(),
        )

        completed_today = tracker.get_completed_today()

        assert len(completed_today) == 1
        assert completed_today[0].id == "mig_today"

    def test_get_statistics_empty(self, tmp_path):
        """Test getting statistics with no migrations."""
        history_path = tmp_path / "history.json"
        tracker = MigrationTracker(history_path=history_path)

        stats = tracker.get_statistics()

        assert stats["total_migrations"] == 0
        assert stats["active_migrations"] == 0
        assert stats["completed_today"] == 0
        assert stats["success_rate"] == 100.0

    def test_get_statistics_with_migrations(self, tmp_path):
        """Test getting statistics with various migrations."""
        history_path = tmp_path / "history.json"
        tracker = MigrationTracker(history_path=history_path)

        today = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)

        # Add various migrations
        tracker.migrations["mig_001"] = MigrationRecord(
            id="mig_001", vm_name="vm1", source_type="local",
            status=MigrationStatus.RUNNING, start_time=today.isoformat()
        )
        tracker.migrations["mig_002"] = MigrationRecord(
            id="mig_002", vm_name="vm2", source_type="local",
            status=MigrationStatus.COMPLETED,
            start_time=today.isoformat(),
            end_time=today.replace(hour=11).isoformat(),
        )
        tracker.migrations["mig_003"] = MigrationRecord(
            id="mig_003", vm_name="vm3", source_type="local",
            status=MigrationStatus.FAILED,
            start_time=today.isoformat(),
            end_time=today.replace(hour=11).isoformat(),
            error_message="Test error"
        )

        stats = tracker.get_statistics()

        assert stats["total_migrations"] == 3
        assert stats["active_migrations"] == 1
        assert stats["total_completed"] == 1
        assert stats["total_failed"] == 1
        assert stats["success_rate"] == 50.0  # 1 completed, 1 failed

    def test_cleanup_old_records(self, tmp_path):
        """Test cleaning up old migration records."""
        history_path = tmp_path / "history.json"
        tracker = MigrationTracker(history_path=history_path)

        now = datetime.now()
        old = now - timedelta(days=40)

        # Add old and recent migrations
        tracker.migrations["mig_old"] = MigrationRecord(
            id="mig_old", vm_name="vm-old", source_type="local",
            status=MigrationStatus.COMPLETED,
            start_time=old.isoformat(),
            end_time=old.replace(hour=11).isoformat(),
        )
        tracker.migrations["mig_recent"] = MigrationRecord(
            id="mig_recent", vm_name="vm-recent", source_type="local",
            status=MigrationStatus.COMPLETED,
            start_time=now.isoformat(),
            end_time=now.replace(hour=11).isoformat(),
        )

        removed = tracker.cleanup_old_records(days=30)

        assert removed == 1
        assert "mig_old" not in tracker.migrations
        assert "mig_recent" in tracker.migrations

    def test_max_history_enforcement(self, tmp_path):
        """Test max history limit is enforced."""
        history_path = tmp_path / "history.json"
        tracker = MigrationTracker(history_path=history_path, max_history=5)

        # Add 10 migrations
        for i in range(10):
            tracker.migrations[f"mig_{i:03d}"] = MigrationRecord(
                id=f"mig_{i:03d}",
                vm_name=f"vm-{i}",
                source_type="local",
                status=MigrationStatus.COMPLETED,
                start_time=datetime.now().isoformat(),
            )

        tracker.save()

        # Should only keep 5 most recent
        assert len(tracker.migrations) == 5


class TestCreateMigrationId:
    """Tests for create_migration_id function."""

    def test_create_migration_id(self):
        """Test creating a migration ID."""
        migration_id = create_migration_id("test-vm")

        assert migration_id.startswith("mig_")
        assert "test_vm" in migration_id or "test-vm" in migration_id
        assert len(migration_id) > 10

    def test_create_migration_id_special_chars(self):
        """Test creating ID with special characters."""
        migration_id = create_migration_id("vm@#$%name!")

        # Special chars should be replaced with underscores
        assert migration_id.startswith("mig_")
        assert "@" not in migration_id
        assert "#" not in migration_id

    def test_create_migration_id_unique(self):
        """Test that IDs are unique."""
        id1 = create_migration_id("test-vm")
        id2 = create_migration_id("test-vm")

        # Should be different due to timestamp
        assert id1 != id2
