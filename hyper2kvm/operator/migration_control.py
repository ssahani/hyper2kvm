"""
Migration Control module for managing live migrations.

Provides:
- Migration abort/cancel functionality
- Detailed migration status retrieval
- Migration coordination
"""

import logging
from kubernetes import client
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class MigrationController:
    """Controller for managing live migrations."""

    def __init__(self, custom_api: client.CustomObjectsApi, core_api: client.CoreV1Api, metrics=None):
        """
        Initialize MigrationController.

        Args:
            custom_api: Kubernetes CustomObjectsApi client
            core_api: Kubernetes CoreV1Api client
            metrics: OperatorMetrics instance
        """
        self.custom_api = custom_api
        self.core_api = core_api
        self.metrics = metrics

    async def abort_migration(self, namespace: str, vmim_name: str, reason: str = "User requested") -> bool:
        """
        Abort an in-progress migration.

        Args:
            namespace: Migration namespace
            vmim_name: VirtualMachineInstanceMigration name
            reason: Reason for aborting

        Returns:
            True if aborted successfully, False otherwise
        """
        try:
            # Get current migration
            vmim = self.custom_api.get_namespaced_custom_object(
                group='kubevirt.io',
                version='v1',
                namespace=namespace,
                plural='virtualmachineinstancemigrations',
                name=vmim_name
            )

            status = vmim.get('status', {})
            phase = status.get('phase', 'Unknown')

            if phase not in ['Running', 'Scheduling', 'Pending']:
                logger.warning(f"Cannot abort migration {vmim_name} in phase {phase}")
                return False

            # Delete the VMIM resource to abort migration
            self.custom_api.delete_namespaced_custom_object(
                group='kubevirt.io',
                version='v1',
                namespace=namespace,
                plural='virtualmachineinstancemigrations',
                name=vmim_name
            )

            logger.info(f"✅ Aborted migration {vmim_name}: {reason}")

            # Emit event
            try:
                vmi_name = vmim.get('spec', {}).get('vmiName', 'unknown')
                event = client.V1Event(
                    metadata=client.V1ObjectMeta(
                        name=f"{vmim_name}.aborted",
                        namespace=namespace
                    ),
                    involved_object=client.V1ObjectReference(
                        api_version='kubevirt.io/v1',
                        kind='VirtualMachineInstanceMigration',
                        name=vmim_name,
                        namespace=namespace
                    ),
                    reason='MigrationAborted',
                    message=f'Migration aborted: {reason}',
                    type='Warning',
                    first_timestamp=datetime.utcnow(),
                    last_timestamp=datetime.utcnow(),
                    count=1,
                    source=client.V1EventSource(component='hyper2kvm-operator')
                )
                self.core_api.create_namespaced_event(namespace, event)
            except Exception as e:
                logger.warning(f"Failed to create event: {e}")

            # Update metrics
            if self.metrics:
                self.metrics.record_live_migration_failed(namespace, f"Aborted: {reason}")

            return True

        except client.ApiException as e:
            if e.status == 404:
                logger.warning(f"Migration {vmim_name} not found")
                return False
            logger.error(f"Failed to abort migration {vmim_name}: {e}")
            return False

    async def get_migration_status(self, namespace: str, vmim_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed migration status.

        Args:
            namespace: Migration namespace
            vmim_name: VirtualMachineInstanceMigration name

        Returns:
            Detailed status dict or None if not found
        """
        try:
            vmim = self.custom_api.get_namespaced_custom_object(
                group='kubevirt.io',
                version='v1',
                namespace=namespace,
                plural='virtualmachineinstancemigrations',
                name=vmim_name
            )

            spec = vmim.get('spec', {})
            status = vmim.get('status', {})
            migration_state = status.get('migrationState', {})

            # Parse progress data
            data_transferred = migration_state.get('dataTransferred', '0')
            data_remaining = migration_state.get('dataRemaining', '0')
            bandwidth = migration_state.get('bandwidth', '0')
            dirty_rate = migration_state.get('memoryDirtyRate', '0')

            # Calculate ETA if possible
            eta_seconds = None
            if data_remaining and bandwidth and bandwidth != '0':
                try:
                    remaining_bytes = self._parse_size(data_remaining)
                    bandwidth_bps = self._parse_size(bandwidth)
                    if bandwidth_bps > 0:
                        eta_seconds = remaining_bytes / bandwidth_bps
                except Exception:
                    pass

            return {
                'name': vmim_name,
                'namespace': namespace,
                'vmi_name': spec.get('vmiName'),
                'phase': status.get('phase', 'Unknown'),
                'source_node': migration_state.get('sourceNode'),
                'target_node': migration_state.get('targetNode'),
                'start_time': migration_state.get('startTimestamp'),
                'end_time': migration_state.get('endTimestamp'),
                'progress': {
                    'data_transferred': data_transferred,
                    'data_remaining': data_remaining,
                    'bandwidth': bandwidth,
                    'dirty_rate': dirty_rate,
                    'eta_seconds': eta_seconds
                },
                'mode': migration_state.get('mode', 'PreCopy'),
                'completed': migration_state.get('completed', False),
                'failed': migration_state.get('failed', False),
                'failure_reason': migration_state.get('failureReason'),
                'migration_uid': migration_state.get('migrationUid')
            }

        except client.ApiException as e:
            if e.status == 404:
                logger.warning(f"Migration {vmim_name} not found")
                return None
            logger.error(f"Failed to get migration status: {e}")
            return None

    def _parse_size(self, size_str: str) -> int:
        """Parse size string like '1.5Gi' to bytes."""
        if not size_str:
            return 0

        size_str = size_str.strip()
        multipliers = {
            'Ki': 1024,
            'Mi': 1024 * 1024,
            'Gi': 1024 * 1024 * 1024,
            'Ti': 1024 * 1024 * 1024 * 1024,
            'K': 1000,
            'M': 1000 * 1000,
            'G': 1000 * 1000 * 1000,
            'T': 1000 * 1000 * 1000 * 1000,
        }

        for suffix, multiplier in multipliers.items():
            if size_str.endswith(suffix):
                try:
                    value = float(size_str[:-len(suffix)])
                    return int(value * multiplier)
                except ValueError:
                    return 0

        try:
            return int(size_str)
        except ValueError:
            return 0

    async def list_active_migrations(self, namespace: Optional[str] = None) -> list[Dict[str, Any]]:
        """
        List all active migrations.

        Args:
            namespace: Namespace filter (None for all)

        Returns:
            List of migration status dicts
        """
        try:
            if namespace:
                vmims = self.custom_api.list_namespaced_custom_object(
                    group='kubevirt.io',
                    version='v1',
                    namespace=namespace,
                    plural='virtualmachineinstancemigrations'
                )
            else:
                vmims = self.custom_api.list_cluster_custom_object(
                    group='kubevirt.io',
                    version='v1',
                    plural='virtualmachineinstancemigrations'
                )

            active_migrations = []
            for vmim in vmims.get('items', []):
                status = vmim.get('status', {})
                phase = status.get('phase', '')

                if phase in ['Running', 'Scheduling', 'Pending']:
                    migration_status = await self.get_migration_status(
                        vmim['metadata']['namespace'],
                        vmim['metadata']['name']
                    )
                    if migration_status:
                        active_migrations.append(migration_status)

            return active_migrations

        except client.ApiException as e:
            logger.error(f"Failed to list migrations: {e}")
            return []
