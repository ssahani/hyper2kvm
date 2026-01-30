# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/worker/__init__.py
"""
Worker Job Protocol for hyper2kvm.

Implements production-grade job orchestration for disk operations that require
privileged access (NBD, LVM, filesystem surgery).

Architecture:
    - Control Plane (Safe): Job submission, validation, monitoring
    - Data Plane (Privileged): Worker nodes executing disk operations

Components:
    - schemas: Pydantic models for job specs, events, results
    - engine: Worker execution engine
    - scheduler: Job queue and worker matching
    - events: Progress event streaming and storage
    - capabilities: Runtime environment detection
    - state_machine: Job lifecycle management
    - cli: Command-line interface
"""

from .schemas import (
    JobSpec,
    JobResult,
    ProgressEvent,
    WorkerCapabilities,
    JobState,
    OperationType,
)

from .engine import WorkerEngine
from .capabilities import CapabilityDetector, ExecutionMode, get_detector
from .state_machine import JobStateMachine, JobRegistry
from .events import EventStore, EventEmitter, ProgressTracker, get_event_store
from .scheduler import JobScheduler, JobQueue, WorkerRegistry, get_scheduler

__version__ = "1.0.0"

__all__ = [
    # Schemas
    "JobSpec",
    "JobResult",
    "ProgressEvent",
    "WorkerCapabilities",
    "JobState",
    "OperationType",
    # Engine
    "WorkerEngine",
    # Capabilities
    "CapabilityDetector",
    "ExecutionMode",
    "get_detector",
    # State Management
    "JobStateMachine",
    "JobRegistry",
    # Events
    "EventStore",
    "EventEmitter",
    "ProgressTracker",
    "get_event_store",
    # Scheduler
    "JobScheduler",
    "JobQueue",
    "WorkerRegistry",
    "get_scheduler",
    # REST API (requires fastapi installation)
    "api",
]
