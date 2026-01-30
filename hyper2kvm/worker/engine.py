# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/worker/engine.py
"""
Worker Execution Engine.

Executes disk operation jobs with progress tracking, error handling, and
artifact generation.
"""

from __future__ import annotations

import json
import logging
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .capabilities import CapabilityDetector, get_detector
from .schemas import (
    ErrorInfo,
    JobMetrics,
    JobOutput,
    JobResult,
    JobSpec,
    JobState,
    OperationType,
    ProgressEvent,
)
from .state_machine import InvalidStateTransition, JobRegistry, JobStateMachine

try:
    from .metrics import WorkerMetrics
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)


class WorkerEngine:
    """
    Worker execution engine for disk operations.

    Responsible for:
    - Job validation against worker capabilities
    - Job execution with progress tracking
    - Error handling and retries
    - Artifact generation and cleanup
    - Progress event streaming
    """

    def __init__(
        self,
        worker_id: str,
        capability_detector: Optional[CapabilityDetector] = None,
        job_registry: Optional[JobRegistry] = None,
        event_callback: Optional[Callable[[ProgressEvent], None]] = None,
        metrics: Optional['WorkerMetrics'] = None,
    ):
        """
        Initialize worker engine.

        Args:
            worker_id: Unique worker identifier
            capability_detector: Capability detector (default: global instance)
            job_registry: Job registry for state management
            event_callback: Optional callback for progress events
            metrics: Optional metrics collector for Prometheus
        """
        self.worker_id = worker_id
        self.detector = capability_detector or get_detector()
        self.registry = job_registry or JobRegistry()
        self.event_callback = event_callback
        self.metrics = metrics

        self.logger = logging.getLogger(f"{__name__}.{worker_id}")
        self.current_job_id: Optional[str] = None

    def _emit_event(self, event: ProgressEvent) -> None:
        """Emit progress event."""
        self.logger.info(
            f"[{event.job_id}] {event.phase}: {event.progress_percent}% - {event.message}"
        )

        if self.event_callback:
            try:
                self.event_callback(event)
            except Exception as e:
                self.logger.error(f"Event callback failed: {e}")

    def _validate_job(self, job_spec: JobSpec) -> tuple[bool, Optional[str]]:
        """
        Validate job against worker capabilities.

        Args:
            job_spec: Job specification

        Returns:
            Tuple of (valid, error_message)
        """
        # Check capability requirements
        capabilities = self.detector.detect_capabilities()
        requirements = {
            "nbd": job_spec.capability_requirements.needs_nbd,
            "lvm": job_spec.capability_requirements.needs_lvm,
            "mount": job_spec.capability_requirements.needs_mount,
            "selinux": job_spec.capability_requirements.needs_selinux_tools,
        }

        can_execute, reason = self.detector.can_execute_job(requirements)
        if not can_execute:
            return False, f"Worker cannot execute job: {reason}"

        # Check if image exists
        image_path = Path(job_spec.image.path)
        if not image_path.exists():
            return False, f"Image not found: {job_spec.image.path}"

        # Check output directory is writable
        output_path = Path(job_spec.artifacts.output_path)
        if not output_path.exists():
            try:
                output_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return False, f"Cannot create output directory: {e}"

        return True, None

    def execute_job(self, job_spec: JobSpec) -> JobResult:
        """
        Execute a job.

        Args:
            job_spec: Job specification

        Returns:
            JobResult with execution outcome
        """
        start_time = time.time()
        self.current_job_id = job_spec.job_id
        operation = job_spec.operation.value

        # Record migration start in metrics
        if self.metrics:
            self.metrics.record_migration_start(operation)

        # Register job
        state_machine = self.registry.register(job_spec)

        try:
            # Validate job
            self._emit_event(ProgressEvent(
                job_id=job_spec.job_id,
                phase="validation",
                progress_percent=0,
                message="Validating job specification"
            ))

            valid, error_msg = self._validate_job(job_spec)
            if not valid:
                state_machine.transition(JobState.FAILED, error_msg)
                return self._create_error_result(
                    job_spec,
                    "validation",
                    "VALIDATION_FAILED",
                    error_msg,
                    start_time
                )

            state_machine.transition(JobState.VALIDATED, "Job validated")
            state_machine.transition(JobState.QUEUED, "Immediately queued for execution")
            state_machine.transition(JobState.ASSIGNED, f"Assigned to worker {self.worker_id}")
            state_machine.transition(JobState.RUNNING, "Execution started")

            # Execute operation based on type
            operation_result = self._execute_operation(job_spec, state_machine)

            # Mark as completed
            state_machine.transition(JobState.COMPLETED, "Job completed successfully")

            execution_time = int(time.time() - start_time)

            # Record successful migration in metrics
            if self.metrics:
                self.metrics.record_migration_complete(
                    operation=operation,
                    duration=execution_time,
                    success=True
                )

            self._emit_event(ProgressEvent(
                job_id=job_spec.job_id,
                phase="completed",
                progress_percent=100,
                message=f"Job completed in {execution_time}s"
            ))

            return JobResult(
                job_id=job_spec.job_id,
                status=JobState.COMPLETED,
                outputs=operation_result["outputs"],
                metrics=JobMetrics(
                    execution_seconds=execution_time,
                    **operation_result.get("metrics", {})
                ),
                worker_id=self.worker_id
            )

        except Exception as e:
            # Handle unexpected errors
            self.logger.error(f"Job {job_spec.job_id} failed with exception: {e}")
            self.logger.debug(traceback.format_exc())

            execution_time = int(time.time() - start_time)
            error_type = type(e).__name__

            # Record failed migration in metrics
            if self.metrics:
                self.metrics.record_migration_complete(
                    operation=operation,
                    duration=execution_time,
                    success=False,
                    error_type=error_type
                )

            try:
                state_machine.transition(JobState.FAILED, str(e))
            except InvalidStateTransition:
                pass  # Already in failed state

            return self._create_error_result(
                job_spec,
                "execution",
                "EXECUTION_FAILED",
                str(e),
                start_time,
                traceback=traceback.format_exc()
            )

        finally:
            self.current_job_id = None

    def _execute_operation(
        self,
        job_spec: JobSpec,
        state_machine: JobStateMachine
    ) -> Dict:
        """
        Execute job operation based on type.

        Args:
            job_spec: Job specification
            state_machine: Job state machine

        Returns:
            Dictionary with outputs and metrics
        """
        operation_map = {
            OperationType.INSPECT: self._op_inspect,
            OperationType.CONVERT: self._op_convert,
            OperationType.OFFLINE_FIX: self._op_offline_fix,
            OperationType.BOOT_REPAIR: self._op_boot_repair,
            OperationType.SELINUX_PREP: self._op_selinux_prep,
            OperationType.LVM_REPAIR: self._op_lvm_repair,
            OperationType.FS_REPAIR: self._op_fs_repair,
            OperationType.INITRAMFS_REGEN: self._op_initramfs_regen,
        }

        operation_func = operation_map.get(job_spec.operation)
        if not operation_func:
            raise ValueError(f"Unsupported operation: {job_spec.operation}")

        return operation_func(job_spec, state_machine)

    def _op_inspect(
        self,
        job_spec: JobSpec,
        state_machine: JobStateMachine
    ) -> Dict:
        """Execute inspect operation."""
        state_machine.transition(JobState.PROGRESSING, "Starting inspection")

        self._emit_event(ProgressEvent(
            job_id=job_spec.job_id,
            phase="inspection",
            progress_percent=20,
            message=f"Inspecting {job_spec.image.path}"
        ))

        # Import here to avoid circular dependencies
        from ..inspector import DiskInspector

        inspector = DiskInspector()

        start_time = time.time()
        inspection_result = inspector.inspect(job_spec.image.path)
        inspect_time = int(time.time() - start_time)

        # Save inspection report
        output_path = Path(job_spec.artifacts.output_path)
        report_file = output_path / f"{job_spec.job_id}_inspection.json"

        with open(report_file, 'w') as f:
            json.dump(inspection_result, f, indent=2, default=str)

        self._emit_event(ProgressEvent(
            job_id=job_spec.job_id,
            phase="inspection",
            progress_percent=100,
            message="Inspection completed"
        ))

        return {
            "outputs": JobOutput(
                report=str(report_file),
                logs=None
            ),
            "metrics": {
                "inspection_seconds": inspect_time
            }
        }

    def _op_convert(
        self,
        job_spec: JobSpec,
        state_machine: JobStateMachine
    ) -> Dict:
        """Execute convert operation."""
        state_machine.transition(JobState.PROGRESSING, "Starting conversion")

        self._emit_event(ProgressEvent(
            job_id=job_spec.job_id,
            phase="conversion",
            progress_percent=10,
            message="Preparing for conversion"
        ))

        # Get conversion parameters
        output_format = job_spec.parameters.get("output_format", "qcow2")
        compress = job_spec.parameters.get("compress", True)

        # Import conversion utilities
        import subprocess

        input_path = job_spec.image.path
        output_path = Path(job_spec.artifacts.output_path)
        output_file = output_path / f"{Path(input_path).stem}.{output_format}"

        self._emit_event(ProgressEvent(
            job_id=job_spec.job_id,
            phase="conversion",
            progress_percent=20,
            message=f"Converting to {output_format}"
        ))

        # Build qemu-img convert command
        cmd = ["qemu-img", "convert", "-p", "-O", output_format]

        if compress and output_format == "qcow2":
            cmd.append("-c")  # Enable compression for qcow2

        cmd.extend([input_path, str(output_file)])

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=job_spec.execution_policy.timeout_seconds
            )
            convert_time = int(time.time() - start_time)

            self._emit_event(ProgressEvent(
                job_id=job_spec.job_id,
                phase="conversion",
                progress_percent=100,
                message=f"Conversion completed in {convert_time}s"
            ))

            return {
                "outputs": JobOutput(
                    fixed_image=str(output_file),
                    logs=None
                ),
                "metrics": {
                    "conversion_seconds": convert_time
                }
            }

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Conversion timed out after {job_spec.execution_policy.timeout_seconds}s")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Conversion failed: {e.stderr}")

    def _op_offline_fix(
        self,
        job_spec: JobSpec,
        state_machine: JobStateMachine
    ) -> Dict:
        """Execute offline_fix operation (NBD + guest fixes)."""
        state_machine.transition(JobState.PROGRESSING, "Starting offline fixes")

        # This would integrate with existing hyper2kvm offline fixer
        # For now, return placeholder

        self._emit_event(ProgressEvent(
            job_id=job_spec.job_id,
            phase="offline_fix",
            progress_percent=50,
            message="Running offline fixes"
        ))

        # TODO: Integrate with OfflineFSFix
        # from ..fixers.offline_fixer import OfflineFSFix

        return {
            "outputs": JobOutput(
                fixed_image=job_spec.image.path,
                logs=None
            ),
            "metrics": {}
        }

    def _op_boot_repair(self, job_spec: JobSpec, state_machine: JobStateMachine) -> Dict:
        """Execute boot_repair operation."""
        # Placeholder - would integrate with boot repair logic
        return {"outputs": JobOutput(), "metrics": {}}

    def _op_selinux_prep(self, job_spec: JobSpec, state_machine: JobStateMachine) -> Dict:
        """Execute selinux_prep operation."""
        # Placeholder - would integrate with SELinux relabel logic
        return {"outputs": JobOutput(), "metrics": {}}

    def _op_lvm_repair(self, job_spec: JobSpec, state_machine: JobStateMachine) -> Dict:
        """Execute lvm_repair operation."""
        # Placeholder - would integrate with LVM repair logic
        return {"outputs": JobOutput(), "metrics": {}}

    def _op_fs_repair(self, job_spec: JobSpec, state_machine: JobStateMachine) -> Dict:
        """Execute fs_repair operation."""
        # Placeholder - would integrate with fsck logic
        return {"outputs": JobOutput(), "metrics": {}}

    def _op_initramfs_regen(self, job_spec: JobSpec, state_machine: JobStateMachine) -> Dict:
        """Execute initramfs_regenerate operation."""
        # Placeholder - would integrate with initramfs regeneration
        return {"outputs": JobOutput(), "metrics": {}}

    def _create_error_result(
        self,
        job_spec: JobSpec,
        phase: str,
        error_code: str,
        error_message: str,
        start_time: float,
        traceback: Optional[str] = None
    ) -> JobResult:
        """Create error result for failed job."""
        execution_time = int(time.time() - start_time)

        self._emit_event(ProgressEvent(
            job_id=job_spec.job_id,
            phase="failed",
            progress_percent=0,
            message=f"Job failed: {error_message}"
        ))

        return JobResult(
            job_id=job_spec.job_id,
            status=JobState.FAILED,
            error=ErrorInfo(
                phase=phase,
                code=error_code,
                message=error_message,
                stack_trace=traceback
            ),
            metrics=JobMetrics(execution_seconds=execution_time),
            worker_id=self.worker_id
        )


def create_sample_job_spec(
    image_path: str,
    output_dir: str,
    operation: OperationType = OperationType.INSPECT
) -> JobSpec:
    """
    Create a sample job specification for testing.

    Args:
        image_path: Path to disk image
        output_dir: Output directory path
        operation: Operation type

    Returns:
        JobSpec instance
    """
    from .schemas import ArtifactConfig, AuditInfo, ImageSpec

    return JobSpec(
        job_id=str(uuid.uuid4()),
        operation=operation,
        image=ImageSpec(
            path=image_path,
            format="qcow2"
        ),
        artifacts=ArtifactConfig(
            output_path=output_dir
        ),
        audit=AuditInfo(
            requested_by="test-user"
        )
    )
