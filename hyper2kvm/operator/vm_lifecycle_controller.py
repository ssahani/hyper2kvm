"""
VM Lifecycle Controller for handling eviction strategies and automatic live migrations.

Watches VirtualMachineInstance events and:
- Detects node cordoning/draining
- Triggers live migrations based on evictionStrategy
- Enforces MigrationPolicy parallelism limits
- Coordinates migrations during node maintenance
"""

import logging
import kopf
from kubernetes import client
from datetime import datetime
from typing import Dict, Any, Optional
import asyncio

logger = logging.getLogger(__name__)

# Global metrics instance
_metrics = None


def set_metrics(metrics):
    """Set the global metrics instance."""
    global _metrics
    _metrics = metrics


async def get_migration_policy(
    custom_api: client.CustomObjectsApi,
    namespace: str,
    vm_name: str
) -> Optional[Dict[str, Any]]:
    """
    Get the MigrationPolicy for a VM.

    Args:
        custom_api: Kubernetes API client
        namespace: VM namespace
        vm_name: VM name

    Returns:
        MigrationPolicy spec or None
    """
    try:
        # First check if VM has a policy annotation
        vm = custom_api.get_namespaced_custom_object(
            group='kubevirt.io',
            version='v1',
            namespace=namespace,
            plural='virtualmachines',
            name=vm_name
        )

        policy_name = vm.get('metadata', {}).get('annotations', {}).get('hyper2kvm.io/migration-policy')

        if policy_name:
            # Get the referenced policy
            policy = custom_api.get_cluster_custom_object(
                group='hyper2kvm.io',
                version='v1alpha1',
                plural='migrationpolicies',
                name=policy_name
            )
            return policy.get('spec', {})

        # Otherwise, find default policy or policy matching VM labels
        policies = custom_api.list_cluster_custom_object(
            group='hyper2kvm.io',
            version='v1alpha1',
            plural='migrationpolicies'
        )

        vm_labels = vm.get('metadata', {}).get('labels', {})

        for policy in policies.get('items', []):
            spec = policy.get('spec', {})
            vm_selector = spec.get('vmSelector', {})

            if not vm_selector:
                # Default policy (no selector)
                return spec

            # Check if VM labels match selector
            match_labels = vm_selector.get('matchLabels', {})
            if match_labels:
                if all(vm_labels.get(k) == v for k, v in match_labels.items()):
                    return spec

        return None

    except client.ApiException as e:
        if e.status == 404:
            return None
        logger.warning(f"Failed to get migration policy: {e}")
        return None


async def count_active_migrations(
    custom_api: client.CustomObjectsApi,
    namespace: str,
    node_name: Optional[str] = None
) -> int:
    """
    Count active migrations (cluster-wide or per-node).

    Args:
        custom_api: Kubernetes API client
        namespace: Namespace to count in (or None for all)
        node_name: Count only migrations from this source node

    Returns:
        Number of active migrations
    """
    try:
        if namespace:
            vmims = custom_api.list_namespaced_custom_object(
                group='kubevirt.io',
                version='v1',
                namespace=namespace,
                plural='virtualmachineinstancemigrations'
            )
        else:
            vmims = custom_api.list_cluster_custom_object(
                group='kubevirt.io',
                version='v1',
                plural='virtualmachineinstancemigrations'
            )

        active_count = 0
        for vmim in vmims.get('items', []):
            status = vmim.get('status', {})
            phase = status.get('phase', '')

            # Count as active if Running or Scheduling
            if phase in ['Running', 'Scheduling', 'Pending']:
                if node_name:
                    # Filter by source node
                    source_node = status.get('migrationState', {}).get('sourceNode')
                    if source_node == node_name:
                        active_count += 1
                else:
                    active_count += 1

        return active_count

    except client.ApiException as e:
        logger.warning(f"Failed to count active migrations: {e}")
        return 0


async def trigger_live_migration(
    custom_api: client.CustomObjectsApi,
    namespace: str,
    vmi_name: str,
    policy: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Trigger a live migration for a VirtualMachineInstance.

    Args:
        custom_api: Kubernetes API client
        namespace: VMI namespace
        vmi_name: VMI name
        policy: MigrationPolicy spec (optional)

    Returns:
        VMIM name or None if migration couldn't be started
    """
    try:
        # Check parallelism limits
        if policy:
            max_cluster = policy.get('maxParallelMigrationsPerCluster', 5)
            active_cluster = await count_active_migrations(custom_api, None)

            if active_cluster >= max_cluster:
                logger.warning(
                    f"Cannot start migration for {vmi_name}: "
                    f"cluster limit reached ({active_cluster}/{max_cluster})"
                )
                if _metrics:
                    _metrics.record_migration_policy_violation(
                        namespace,
                        policy.get('name', 'default'),
                        'max_parallel_cluster'
                    )
                return None

            # Check per-node limit
            max_per_node = policy.get('maxParallelMigrationsPerNode', 2)

            # Get VMI to find source node
            vmi = custom_api.get_namespaced_custom_object(
                group='kubevirt.io',
                version='v1',
                namespace=namespace,
                plural='virtualmachineinstances',
                name=vmi_name
            )

            source_node = vmi.get('status', {}).get('nodeName')
            if source_node:
                active_on_node = await count_active_migrations(custom_api, None, source_node)
                if active_on_node >= max_per_node:
                    logger.warning(
                        f"Cannot start migration for {vmi_name}: "
                        f"node limit reached ({active_on_node}/{max_per_node} on {source_node})"
                    )
                    if _metrics:
                        _metrics.record_migration_policy_violation(
                            namespace,
                            policy.get('name', 'default'),
                            'max_parallel_node'
                        )
                    return None

        # Create VirtualMachineInstanceMigration
        vmim_name = f"{vmi_name}-migration-{int(datetime.utcnow().timestamp())}"

        vmim = {
            'apiVersion': 'kubevirt.io/v1',
            'kind': 'VirtualMachineInstanceMigration',
            'metadata': {
                'name': vmim_name,
                'namespace': namespace,
                'labels': {
                    'hyper2kvm.io/auto-triggered': 'true'
                }
            },
            'spec': {
                'vmiName': vmi_name
            }
        }

        custom_api.create_namespaced_custom_object(
            group='kubevirt.io',
            version='v1',
            namespace=namespace,
            plural='virtualmachineinstancemigrations',
            body=vmim
        )

        logger.info(f"✅ Triggered live migration for {vmi_name}: {vmim_name}")

        # Emit event
        try:
            core_api = client.CoreV1Api()
            event = client.V1Event(
                metadata=client.V1ObjectMeta(
                    name=f"{vmi_name}.auto-migration",
                    namespace=namespace
                ),
                involved_object=client.V1ObjectReference(
                    api_version='kubevirt.io/v1',
                    kind='VirtualMachineInstance',
                    name=vmi_name,
                    namespace=namespace
                ),
                reason='AutoMigrationTriggered',
                message=f'Automatic live migration triggered for {vmi_name}',
                type='Normal',
                first_timestamp=datetime.utcnow(),
                last_timestamp=datetime.utcnow(),
                count=1,
                source=client.V1EventSource(component='hyper2kvm-operator')
            )
            core_api.create_namespaced_event(namespace, event)
        except Exception as e:
            logger.warning(f"Failed to create event: {e}")

        return vmim_name

    except client.ApiException as e:
        logger.error(f"Failed to trigger live migration for {vmi_name}: {e}")
        return None


@kopf.on.event('kubevirt.io', 'v1', 'virtualmachineinstances')
async def on_vmi_event(type, event, **kwargs):
    """
    Handle VirtualMachineInstance events.

    Monitors for:
    - VMI on cordoned nodes (trigger migration if evictionStrategy allows)
    - Node eviction events
    """
    if type not in ['ADDED', 'MODIFIED']:
        return

    obj = event.get('object', {})
    metadata = obj.get('metadata', {})
    spec = obj.get('spec', {})
    status = obj.get('status', {})

    vmi_name = metadata.get('name')
    namespace = metadata.get('namespace')
    node_name = status.get('nodeName')

    if not vmi_name or not namespace or not node_name:
        return

    # Get eviction strategy
    eviction_strategy = spec.get('evictionStrategy')

    if eviction_strategy not in ['LiveMigrate', 'LiveMigrateIfPossible']:
        return

    # Check if VMI is running
    phase = status.get('phase')
    if phase != 'Running':
        return

    # Check if already migrating
    migration_state = status.get('migrationState')
    if migration_state and migration_state.get('migrationUid'):
        return

    # Check if node is cordoned
    try:
        core_api = client.CoreV1Api()
        node = core_api.read_node(node_name)

        is_cordoned = node.spec.unschedulable

        if is_cordoned:
            logger.info(
                f"VMI {vmi_name} is on cordoned node {node_name} "
                f"with evictionStrategy={eviction_strategy}"
            )

            # Get migration policy
            custom_api = client.CustomObjectsApi()
            policy = await get_migration_policy(custom_api, namespace, vmi_name)

            # Trigger migration
            vmim_name = await trigger_live_migration(
                custom_api,
                namespace,
                vmi_name,
                policy
            )

            if vmim_name:
                logger.info(f"Started automatic migration: {vmim_name}")
            else:
                logger.warning(f"Could not start migration for {vmi_name} (policy limits?)")

    except client.ApiException as e:
        if e.status != 404:
            logger.warning(f"Failed to check node status: {e}")
    except Exception as e:
        logger.error(f"Error handling VMI event: {e}")
