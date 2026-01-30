# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/backup_sources/__init__.py
"""
Backup integration for VM import from backup solutions.

Enables VM migration from enterprise backup formats:
- Veeam Backup & Replication (VBK/VIB)
- Commvault (MediaAgent exports)
- Proxmox Backup Server (PBS)
- Acronis Backup (TIB)
- Restic/Borg archives

Use cases:
- DR testing (restore backups to KVM for validation)
- Backup-based migrations (when live migration not feasible)
- Archive recovery (restore legacy backups)
- Compliance testing (verify backup integrity)
"""

from .base import BackupSource, BackupVMInfo, RestoreProgress
from .veeam import VeeamBackupSource
from .proxmox import ProxmoxBackupSource
from .generic import GenericBackupSource
from .orchestrator import BackupRestoreOrchestrator

__all__ = [
    "BackupSource",
    "BackupVMInfo",
    "RestoreProgress",
    "VeeamBackupSource",
    "ProxmoxBackupSource",
    "GenericBackupSource",
    "BackupRestoreOrchestrator",
]
