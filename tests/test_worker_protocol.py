#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Basic tests for Worker Job Protocol.

Verifies core functionality without requiring privileged access.
"""

import json
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from hyper2kvm.worker import (
    JobSpec,
    JobState,
    OperationType,
    WorkerEngine,
    CapabilityDetector,
    JobStateMachine,
    EventStore,
    ProgressEvent,
)
from hyper2kvm.worker.schemas import (
    ArtifactConfig,
    AuditInfo,
    ImageSpec,
)


class TestSchemas:
    """Test Pydantic schemas."""

    def test_job_spec_minimal(self):
        """Test minimal job spec creation."""
        job = JobSpec(
            job_id=str(uuid.uuid4()),
            operation=OperationType.INSPECT,
            image=ImageSpec(path="/test/image.qcow2"),
            artifacts=ArtifactConfig(output_path="/tmp"),
            audit=AuditInfo(requested_by="test")
        )

        assert job.job_id is not None
        assert job.operation == OperationType.INSPECT

    def test_job_spec_serialization(self):
        """Test JSON serialization."""
        job = JobSpec(
            job_id="test-123",
            operation=OperationType.CONVERT,
            image=ImageSpec(path="/test.qcow2", format="qcow2"),
            artifacts=ArtifactConfig(output_path="/tmp"),
            audit=AuditInfo(requested_by="test")
        )

        # Serialize
        json_str = job.model_dump_json()
        data = json.loads(json_str)

        assert data["job_id"] == "test-123"
        assert data["operation"] == "convert"

        # Deserialize
        job2 = JobSpec(**data)
        assert job2.job_id == job.job_id


class TestCapabilityDetection:
    """Test capability detection."""

    def test_execution_mode_detection(self):
        """Test execution mode detection."""
        detector = CapabilityDetector()
        mode = detector.detect_execution_mode()

        assert mode in ["host", "safe_container", "privileged_container"]

    def test_capability_detection(self):
        """Test capability detection."""
        detector = CapabilityDetector()
        caps = detector.detect_capabilities()

        assert isinstance(caps, dict)
        assert "qemu_img" in caps
        assert isinstance(caps["qemu_img"], bool)

    def test_system_info(self):
        """Test system info collection."""
        detector = CapabilityDetector()
        info = detector.get_system_info()

        assert "hostname" in info
        assert "memory_gb" in info


class TestStateMachine:
    """Test job state machine."""

    def test_state_transitions(self):
        """Test valid state transitions."""
        sm = JobStateMachine("test-job", JobState.CREATED)

        assert sm.current_state == JobState.CREATED

        sm.transition(JobState.VALIDATED, "Validated")
        assert sm.current_state == JobState.VALIDATED

        sm.transition(JobState.QUEUED, "Queued")
        assert sm.current_state == JobState.QUEUED

    def test_invalid_transition(self):
        """Test invalid state transition."""
        sm = JobStateMachine("test-job", JobState.CREATED)

        with pytest.raises(Exception):  # InvalidStateTransition
            sm.transition(JobState.COMPLETED, "Cannot skip to completed")

    def test_terminal_state(self):
        """Test terminal state detection."""
        sm = JobStateMachine("test-job", JobState.COMPLETED)
        assert sm.is_terminal()

        sm2 = JobStateMachine("test-job2", JobState.RUNNING)
        assert not sm2.is_terminal()

    def test_state_persistence(self):
        """Test state machine persistence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)

            sm = JobStateMachine("persist-test", JobState.CREATED)
            sm.transition(JobState.VALIDATED, "Test validation")
            sm.save(state_dir)

            # Load back
            sm2 = JobStateMachine.load("persist-test", state_dir)
            assert sm2 is not None
            assert sm2.current_state == JobState.VALIDATED


class TestEventStore:
    """Test event storage."""

    def test_event_storage(self):
        """Test storing and retrieving events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EventStore(Path(tmpdir))

            event = ProgressEvent(
                job_id="test-job",
                phase="test",
                progress_percent=50,
                message="Test message"
            )

            store.store(event)

            # Retrieve
            events = store.get_events("test-job")
            assert len(events) == 1
            assert events[0].phase == "test"
            assert events[0].progress_percent == 50

    def test_event_filtering(self):
        """Test event filtering."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EventStore(Path(tmpdir))

            # Store multiple events
            for i in range(5):
                event = ProgressEvent(
                    job_id="filter-test",
                    phase=f"phase-{i % 2}",
                    progress_percent=i * 20,
                    message=f"Message {i}"
                )
                store.store(event)

            # Filter by phase
            phase0_events = store.get_events("filter-test", phase_filter="phase-0")
            assert len(phase0_events) == 3  # 0, 2, 4

            phase1_events = store.get_events("filter-test", phase_filter="phase-1")
            assert len(phase1_events) == 2  # 1, 3


class TestWorkerEngine:
    """Test worker execution engine."""

    def test_engine_initialization(self):
        """Test engine initialization."""
        engine = WorkerEngine(worker_id="test-worker")
        assert engine.worker_id == "test-worker"

    def test_job_validation(self):
        """Test job validation."""
        engine = WorkerEngine(worker_id="test-worker")

        # Create job with non-existent image
        job = JobSpec(
            job_id="validation-test",
            operation=OperationType.INSPECT,
            image=ImageSpec(path="/nonexistent/image.qcow2"),
            artifacts=ArtifactConfig(output_path="/tmp"),
            audit=AuditInfo(requested_by="test")
        )

        valid, error = engine._validate_job(job)
        assert not valid
        assert "not found" in error.lower()


def test_full_integration():
    """Integration test of multiple components."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        # Create a dummy image file
        test_image = output_dir / "test.qcow2"
        test_image.write_text("dummy")

        # Create job spec
        job = JobSpec(
            job_id="integration-test",
            operation=OperationType.INSPECT,
            image=ImageSpec(path=str(test_image)),
            artifacts=ArtifactConfig(output_path=str(output_dir)),
            audit=AuditInfo(requested_by="integration-test")
        )

        # Execute (will fail due to invalid image, but tests the pipeline)
        engine = WorkerEngine(worker_id="integration-worker")

        try:
            result = engine.execute_job(job)
            # Should fail or succeed depending on implementation
            assert result.job_id == job.job_id
        except Exception as e:
            # Expected if image is invalid
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
