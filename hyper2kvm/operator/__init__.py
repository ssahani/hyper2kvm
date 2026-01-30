"""
Hyper2KVM Kubernetes Operator.

Production-grade operator for automated migration job orchestration.
Includes controllers for MigrationJob and OfflineFixJob CRDs.
"""

__version__ = "1.5.0"

# Import worker-based components (for OfflineFixJob)
from hyper2kvm.operator.worker_registry import WorkerRegistry
from hyper2kvm.operator.job_assigner import JobAssigner

# OfflineFixJob controller (worker-based model)
from hyper2kvm.operator import offlinefixjob_controller  # noqa: F401

# MigrationJob controller (K8s-native model - replaces old controller.py)
from hyper2kvm.operator import migrationjob_controller  # noqa: F401

# Live migration and lifecycle controllers
from hyper2kvm.operator import live_migration_controller  # noqa: F401
from hyper2kvm.operator import vm_lifecycle_controller  # noqa: F401
from hyper2kvm.operator import migration_policy_controller  # noqa: F401
from hyper2kvm.operator import storage_migration_controller  # noqa: F401

__all__ = [
    'WorkerRegistry',
    'JobAssigner',
]
