# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/rollback/__init__.py
"""
Rollback framework for migration recovery.

Provides comprehensive rollback capabilities for failed migrations.
"""

from .snapshot_manager import (
    SnapshotManager,
    Snapshot,
    SnapshotType,
)
from .state_tracker import (
    StateTracker,
    MigrationState,
    StateCheckpoint,
)
from .rollback_executor import (
    RollbackExecutor,
    RollbackAction,
    RollbackResult,
)
from .rollback_validator import (
    ValidationStatus,
    RollbackValidator,
    ValidationResult,
)
from .orchestrator import (
    RollbackOrchestrator,
    RollbackReport,
    RollbackStrategy,
)

__all__ = [
    "SnapshotManager",
    "Snapshot",
    "SnapshotType",
    "StateTracker",
    "MigrationState",
    "StateCheckpoint",
    "RollbackExecutor",
    "RollbackAction",
    "RollbackResult",
    "RollbackValidator",
    "ValidationStatus",
    "ValidationResult",
    "RollbackOrchestrator",
    "RollbackReport",
    "RollbackStrategy",
]
