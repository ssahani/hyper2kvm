"""
Hyper2KVM Kubernetes Operator.

Production-grade operator for automated migration job orchestration.
Includes controllers for MigrationJob and OfflineFixJob CRDs.
"""

__version__ = "1.5.0"

from hyper2kvm.operator.controller import (
    create_migration_job,
    update_migration_job,
    delete_migration_job,
    reconcile_migration_job
)
from hyper2kvm.operator.worker_registry import WorkerRegistry
from hyper2kvm.operator.job_assigner import JobAssigner

# OfflineFixJob controller is registered via kopf decorators
# Import to ensure handlers are registered
from hyper2kvm.operator import offlinefixjob_controller  # noqa: F401

# MigrationJob controller (new K8s-native migration)
from hyper2kvm.operator import migrationjob_controller  # noqa: F401

__all__ = [
    'create_migration_job',
    'update_migration_job',
    'delete_migration_job',
    'reconcile_migration_job',
    'WorkerRegistry',
    'JobAssigner',
]
