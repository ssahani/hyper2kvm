"""
Live Migration Controller for KubeVirt VirtualMachineInstanceMigration resources.

Watches VMIM resources and:
- Tracks migration progress
- Emits Kubernetes events
- Updates Prometheus metrics
- Detects migration failures
- Monitors policy violations
- Records migration statistics
"""

import logging
import kopf
from kubernetes import client
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Global metrics instance (injected by main operator)
_metrics = None


def set_metrics(metrics):
    """Set the global metrics instance."""
    global _metrics
    _metrics = metrics


def _parse_data_size(size_str: str) -> int:
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


def _parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse ISO 8601 timestamp."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


@kopf.on.create('kubevirt.io', 'v1', 'virtualmachineinstancemigrations')
async def on_vmim_created(spec, meta, namespace, name, **kwargs):
    """Handle VirtualMachineInstanceMigration creation."""
    vmi_name = spec.get('vmiName', 'unknown')

    logger.info(f"Live migration started for VMI {vmi_name}: {name}")

    # Emit Kubernetes event
    try:
        core_api = client.CoreV1Api()
        event = client.V1Event(
            metadata=client.V1ObjectMeta(
                name=f"{name}.migration.started",
                namespace=namespace
            ),
            involved_object=client.V1ObjectReference(
                api_version='kubevirt.io/v1',
                kind='VirtualMachineInstanceMigration',
                name=name,
                namespace=namespace
            ),
            reason='MigrationStarted',
            message=f'Live migration started for VM instance {vmi_name}',
            type='Normal',
            first_timestamp=datetime.utcnow(),
            last_timestamp=datetime.utcnow(),
            count=1,
            source=client.V1EventSource(component='hyper2kvm-operator')
        )
        core_api.create_namespaced_event(namespace, event)
    except Exception as e:
        logger.warning(f"Failed to create event: {e}")

    # Update metrics - we'll get node info from status updates
    if _metrics:
        _metrics.update_active_live_migrations(namespace, 'Pending', 1)


@kopf.on.field('kubevirt.io', 'v1', 'virtualmachineinstancemigrations', field='status.phase')
async def on_vmim_phase_change(old, new, spec, status, meta, namespace, name, **kwargs):
    """Handle VirtualMachineInstanceMigration phase changes."""
    vmi_name = spec.get('vmiName', 'unknown')

    logger.info(f"Live migration {name} phase changed: {old} -> {new}")

    # Emit Kubernetes event
    try:
        core_api = client.CoreV1Api()
        event = client.V1Event(
            metadata=client.V1ObjectMeta(
                name=f"{name}.migration.{new.lower()}",
                namespace=namespace
            ),
            involved_object=client.V1ObjectReference(
                api_version='kubevirt.io/v1',
                kind='VirtualMachineInstanceMigration',
                name=name,
                namespace=namespace
            ),
            reason=f'Migration{new}',
            message=f'Live migration for {vmi_name} is now {new}',
            type='Normal' if new in ['Running', 'Succeeded'] else 'Warning',
            first_timestamp=datetime.utcnow(),
            last_timestamp=datetime.utcnow(),
            count=1,
            source=client.V1EventSource(component='hyper2kvm-operator')
        )
        core_api.create_namespaced_event(namespace, event)
    except Exception as e:
        logger.warning(f"Failed to create event: {e}")

    # Update metrics
    if _metrics:
        if old:
            _metrics.update_active_live_migrations(namespace, old, -1)
        _metrics.update_active_live_migrations(namespace, new, 1)

        # Record completion
        if new == 'Succeeded':
            # Calculate duration
            start_time = _parse_timestamp(status.get('migrationState', {}).get('startTimestamp'))
            end_time = _parse_timestamp(status.get('migrationState', {}).get('endTimestamp'))
            duration = 0
            if start_time and end_time:
                duration = (end_time - start_time).total_seconds()

            # Get data transferred
            migration_state = status.get('migrationState', {})
            data_transferred_str = migration_state.get('dataTransferred', '0')
            data_transferred = _parse_data_size(data_transferred_str)

            # Get downtime (if available)
            downtime_ms = 0

            _metrics.record_live_migration_succeeded(
                namespace,
                duration,
                data_transferred,
                downtime_ms
            )

            logger.info(f"✅ Live migration {name} completed successfully in {duration:.1f}s")

        elif new == 'Failed':
            reason = status.get('migrationState', {}).get('failureReason', 'Unknown')
            _metrics.record_live_migration_failed(namespace, reason)
            logger.error(f"❌ Live migration {name} failed: {reason}")


@kopf.on.update('kubevirt.io', 'v1', 'virtualmachineinstancemigrations')
async def on_vmim_update(spec, status, meta, namespace, name, **kwargs):
    """Handle VirtualMachineInstanceMigration updates (progress tracking)."""
    vmi_name = spec.get('vmiName', 'unknown')
    migration_state = status.get('migrationState', {})

    # Track source and target nodes
    source_node = migration_state.get('sourceNode')
    target_node = migration_state.get('targetNode')

    if source_node and target_node and _metrics:
        # Record migration with nodes (only on first update with both nodes)
        phase = status.get('phase', 'Unknown')
        if phase == 'Running':
            _metrics.record_live_migration_started(namespace, source_node, target_node)

    # Track bandwidth and dirty rate
    if _metrics and migration_state:
        # Parse bandwidth
        bandwidth_str = migration_state.get('bandwidth', '0')
        bandwidth_bps = _parse_data_size(bandwidth_str)
        if bandwidth_bps > 0:
            _metrics.update_migration_bandwidth(namespace, vmi_name, float(bandwidth_bps))

        # Parse dirty rate
        dirty_rate_str = migration_state.get('memoryDirtyRate', '0')
        dirty_rate_bps = _parse_data_size(dirty_rate_str)
        if dirty_rate_bps > 0:
            _metrics.update_migration_dirty_rate(namespace, vmi_name, float(dirty_rate_bps))

    # Check for post-copy activation
    migration_config = status.get('migrationConfiguration', {})
    if migration_config.get('allowPostCopy') and _metrics:
        # Check if post-copy is active (implementation depends on KubeVirt version)
        if migration_state.get('mode') == 'PostCopy':
            _metrics.record_post_copy_activation(namespace)
            logger.info(f"Post-copy activated for migration {name}")

    # Check for auto-converge activation
    if migration_config.get('allowAutoConverge') and _metrics:
        # Check if auto-converge is active
        if migration_state.get('autoConverge') == 'true':
            _metrics.record_auto_converge_activation(namespace)
            logger.info(f"Auto-converge activated for migration {name}")


@kopf.on.delete('kubevirt.io', 'v1', 'virtualmachineinstancemigrations')
async def on_vmim_deleted(spec, status, meta, namespace, name, **kwargs):
    """Handle VirtualMachineInstanceMigration deletion."""
    vmi_name = spec.get('vmiName', 'unknown')
    phase = status.get('phase', 'Unknown')

    logger.info(f"Live migration {name} deleted (final phase: {phase})")

    # Update metrics - remove from active count
    if _metrics:
        _metrics.update_active_live_migrations(namespace, phase, -1)

    # Emit event
    try:
        core_api = client.CoreV1Api()
        event = client.V1Event(
            metadata=client.V1ObjectMeta(
                name=f"{name}.migration.deleted",
                namespace=namespace
            ),
            involved_object=client.V1ObjectReference(
                api_version='kubevirt.io/v1',
                kind='VirtualMachineInstanceMigration',
                name=name,
                namespace=namespace
            ),
            reason='MigrationDeleted',
            message=f'Live migration for {vmi_name} was deleted (phase: {phase})',
            type='Normal',
            first_timestamp=datetime.utcnow(),
            last_timestamp=datetime.utcnow(),
            count=1,
            source=client.V1EventSource(component='hyper2kvm-operator')
        )
        core_api.create_namespaced_event(namespace, event)
    except Exception as e:
        logger.warning(f"Failed to create event: {e}")
