# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/migration_controller.py
"""
Migration control interface for managing active migrations.

Provides pause, resume, cancel operations for running migrations.
"""

from __future__ import annotations

import logging
import signal
from pathlib import Path
from typing import Optional, Dict, Any

from .migration_tracker import MigrationTracker, MigrationStatus


class MigrationController:
    """
    Controls active migration processes.

    Features:
    - Pause/resume migration processes
    - Cancel migrations gracefully
    - Query migration status
    - Send signals to migration processes
    """

    def __init__(self, tracker: MigrationTracker, logger: logging.Logger | None = None):
        """
        Initialize migration controller.

        Args:
            tracker: Migration tracker instance
            logger: Optional logger for debug output
        """
        self.tracker = tracker
        self.logger = logger or logging.getLogger(__name__)
        self._process_map: Dict[str, int] = {}  # migration_id -> PID

    def register_process(self, migration_id: str, pid: int) -> None:
        """
        Register a migration process PID.

        Args:
            migration_id: Migration ID
            pid: Process ID
        """
        self._process_map[migration_id] = pid
        self.logger.debug(f"Registered migration {migration_id} with PID {pid}")

    def unregister_process(self, migration_id: str) -> None:
        """
        Unregister a migration process.

        Args:
            migration_id: Migration ID
        """
        if migration_id in self._process_map:
            del self._process_map[migration_id]
            self.logger.debug(f"Unregistered migration {migration_id}")

    def get_process_pid(self, migration_id: str) -> Optional[int]:
        """
        Get PID for a migration.

        Args:
            migration_id: Migration ID

        Returns:
            Process ID or None if not found
        """
        return self._process_map.get(migration_id)

    def pause_migration(self, migration_id: str) -> bool:
        """
        Pause a running migration.

        Sends SIGSTOP to the migration process.

        Args:
            migration_id: Migration ID

        Returns:
            True if successful, False otherwise
        """
        pid = self.get_process_pid(migration_id)
        if pid is None:
            self.logger.warning(f"No process found for migration {migration_id}")
            return False

        try:
            # Send SIGSTOP to pause the process
            import os
            os.kill(pid, signal.SIGSTOP)

            # Update tracker
            self.tracker.update_migration(migration_id, status=MigrationStatus.PAUSED)

            self.logger.info(f"Paused migration {migration_id} (PID {pid})")
            return True

        except ProcessLookupError:
            self.logger.warning(f"Process {pid} not found for migration {migration_id}")
            self.unregister_process(migration_id)
            return False
        except PermissionError:
            self.logger.error(f"Permission denied to pause process {pid}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to pause migration {migration_id}: {e}")
            return False

    def resume_migration(self, migration_id: str) -> bool:
        """
        Resume a paused migration.

        Sends SIGCONT to the migration process.

        Args:
            migration_id: Migration ID

        Returns:
            True if successful, False otherwise
        """
        pid = self.get_process_pid(migration_id)
        if pid is None:
            self.logger.warning(f"No process found for migration {migration_id}")
            return False

        try:
            # Send SIGCONT to resume the process
            import os
            os.kill(pid, signal.SIGCONT)

            # Update tracker
            self.tracker.update_migration(migration_id, status=MigrationStatus.RUNNING)

            self.logger.info(f"Resumed migration {migration_id} (PID {pid})")
            return True

        except ProcessLookupError:
            self.logger.warning(f"Process {pid} not found for migration {migration_id}")
            self.unregister_process(migration_id)
            return False
        except PermissionError:
            self.logger.error(f"Permission denied to resume process {pid}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to resume migration {migration_id}: {e}")
            return False

    def cancel_migration(self, migration_id: str, force: bool = False) -> bool:
        """
        Cancel a migration.

        Sends SIGTERM (or SIGKILL if force=True) to the migration process.

        Args:
            migration_id: Migration ID
            force: If True, send SIGKILL instead of SIGTERM

        Returns:
            True if successful, False otherwise
        """
        pid = self.get_process_pid(migration_id)
        if pid is None:
            self.logger.warning(f"No process found for migration {migration_id}")
            # Still update tracker status
            self.tracker.update_migration(
                migration_id,
                status=MigrationStatus.CANCELLED,
                error_message="Process not found"
            )
            return False

        try:
            import os
            import time

            if force:
                # Immediate kill
                os.kill(pid, signal.SIGKILL)
                self.logger.warning(f"Force killed migration {migration_id} (PID {pid})")
            else:
                # Graceful termination
                os.kill(pid, signal.SIGTERM)
                self.logger.info(f"Sent SIGTERM to migration {migration_id} (PID {pid})")

                # Wait briefly for graceful shutdown
                time.sleep(0.5)

                # Check if process still exists
                try:
                    os.kill(pid, 0)  # Signal 0 just checks if process exists
                    # Process still running, might need force kill
                    self.logger.warning(f"Process {pid} still running after SIGTERM")
                except ProcessLookupError:
                    # Process terminated successfully
                    pass

            # Update tracker
            self.tracker.update_migration(
                migration_id,
                status=MigrationStatus.CANCELLED,
                error_message="Cancelled by user"
            )

            self.unregister_process(migration_id)
            return True

        except ProcessLookupError:
            self.logger.info(f"Process {pid} already terminated")
            self.unregister_process(migration_id)
            self.tracker.update_migration(
                migration_id,
                status=MigrationStatus.CANCELLED
            )
            return True
        except PermissionError:
            self.logger.error(f"Permission denied to cancel process {pid}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to cancel migration {migration_id}: {e}")
            return False

    def is_process_running(self, migration_id: str) -> bool:
        """
        Check if migration process is still running.

        Args:
            migration_id: Migration ID

        Returns:
            True if process is running, False otherwise
        """
        pid = self.get_process_pid(migration_id)
        if pid is None:
            return False

        try:
            import os
            os.kill(pid, 0)  # Signal 0 just checks if process exists
            return True
        except ProcessLookupError:
            return False
        except Exception:
            return False

    def cleanup_finished_processes(self) -> int:
        """
        Remove finished processes from the process map.

        Returns:
            Number of processes cleaned up
        """
        finished = []
        for migration_id, pid in self._process_map.items():
            if not self.is_process_running(migration_id):
                finished.append(migration_id)

        for migration_id in finished:
            self.unregister_process(migration_id)

        if finished:
            self.logger.debug(f"Cleaned up {len(finished)} finished processes")

        return len(finished)

    def get_active_processes(self) -> Dict[str, int]:
        """
        Get all active migration processes.

        Returns:
            Dict mapping migration_id to PID
        """
        self.cleanup_finished_processes()
        return self._process_map.copy()
