"""
Hyper2KVM Kubernetes Operator.

Production-grade operator for automated migration job orchestration.
"""

__version__ = "1.4.0"

from hyper2kvm.operator.controller import (
    create_migration_job,
    update_migration_job,
    delete_migration_job,
    reconcile_migration_job
)
from hyper2kvm.operator.worker_registry import WorkerRegistry
from hyper2kvm.operator.job_assigner import JobAssigner

__all__ = [
    'create_migration_job',
    'update_migration_job',
    'delete_migration_job',
    'reconcile_migration_job',
    'WorkerRegistry',
    'JobAssigner',
]
