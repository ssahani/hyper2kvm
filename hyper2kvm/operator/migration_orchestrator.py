"""
Migration Orchestrator for high-level migration workflows.

Coordinates:
- Hypervisor → KubeVirt (cold migration)
- KubeVirt → KubeVirt (live migration)
- Storage migrations
- Multi-phase migrations
"""

import logging
from kubernetes import client
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class MigrationOrchestrator:
    """Orchestrator for complex migration workflows."""

    def __init__(
        self,
        custom_api: client.CustomObjectsApi,
        core_api: client.CoreV1Api,
        metrics=None
    ):
        """
        Initialize MigrationOrchestrator.

        Args:
            custom_api: Kubernetes CustomObjectsApi client
            core_api: Kubernetes CoreV1Api client
            metrics: OperatorMetrics instance
        """
        self.custom_api = custom_api
        self.core_api = core_api
        self.metrics = metrics

    async def orchestrate_cold_migration(
        self,
        namespace: str,
        migration_job_name: str,
        create_vm_with_eviction: bool = True
    ) -> Dict[str, Any]:
        """
        Orchestrate cold migration from hypervisor to KubeVirt.

        Workflow:
        1. Create MigrationJob
        2. Wait for conversion to complete
        3. Create VM with evictionStrategy
        4. Optionally start VM

        Args:
            namespace: Migration namespace
            migration_job_name: MigrationJob name
            create_vm_with_eviction: Create VM with LiveMigrate evictionStrategy

        Returns:
            Migration result dict
        """
        logger.info(f"Orchestrating cold migration: {migration_job_name}")

        try:
            # Get MigrationJob
            migration_job = self.custom_api.get_namespaced_custom_object(
                group='hyper2kvm.io',
                version='v1alpha1',
                namespace=namespace,
                plural='migrationjobs',
                name=migration_job_name
            )

            status = migration_job.get('status', {})
            phase = status.get('phase', 'Unknown')

            if phase == 'Completed':
                vm_name = status.get('vmName')
                return {
                    'success': True,
                    'phase': phase,
                    'vm_name': vm_name,
                    'message': f'Cold migration completed, VM created: {vm_name}'
                }
            elif phase == 'Failed':
                return {
                    'success': False,
                    'phase': phase,
                    'message': status.get('message', 'Migration failed')
                }
            else:
                return {
                    'success': False,
                    'phase': phase,
                    'message': f'Migration in progress (phase: {phase})'
                }

        except client.ApiException as e:
            logger.error(f"Failed to orchestrate cold migration: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def orchestrate_live_migration(
        self,
        namespace: str,
        vm_name: str,
        policy_name: Optional[str] = None,
        target_node: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Orchestrate live migration between KubeVirt nodes.

        Workflow:
        1. Get VM and check evictionStrategy
        2. Get or create MigrationPolicy
        3. Create VirtualMachineInstanceMigration
        4. Monitor progress
        5. Return result

        Args:
            namespace: VM namespace
            vm_name: VM name
            policy_name: MigrationPolicy name (optional)
            target_node: Target node (optional, KubeVirt will auto-select)

        Returns:
            Migration result dict
        """
        logger.info(f"Orchestrating live migration for VM {vm_name}")

        try:
            # Get VM
            vm = self.custom_api.get_namespaced_custom_object(
                group='kubevirt.io',
                version='v1',
                namespace=namespace,
                plural='virtualmachines',
                name=vm_name
            )

            # Check if VM is running
            if not vm.get('spec', {}).get('running', False):
                return {
                    'success': False,
                    'message': f'VM {vm_name} is not running, cannot live migrate'
                }

            # Get VMI
            try:
                vmi = self.custom_api.get_namespaced_custom_object(
                    group='kubevirt.io',
                    version='v1',
                    namespace=namespace,
                    plural='virtualmachineinstances',
                    name=vm_name
                )
            except client.ApiException as e:
                if e.status == 404:
                    return {
                        'success': False,
                        'message': f'VMI {vm_name} not found'
                    }
                raise

            # Check eviction strategy
            eviction_strategy = vmi.get('spec', {}).get('evictionStrategy')
            if eviction_strategy not in ['LiveMigrate', 'LiveMigrateIfPossible']:
                logger.warning(
                    f"VM {vm_name} has evictionStrategy={eviction_strategy}, "
                    "live migration may not be supported"
                )

            # Apply policy if specified
            if policy_name:
                try:
                    policy = self.custom_api.get_cluster_custom_object(
                        group='hyper2kvm.io',
                        version='v1alpha1',
                        plural='migrationpolicies',
                        name=policy_name
                    )
                    logger.info(f"Using migration policy: {policy_name}")
                except client.ApiException as e:
                    if e.status == 404:
                        logger.warning(f"Migration policy {policy_name} not found")

            # Create VMIM
            vmim_name = f"{vm_name}-migration-{int(datetime.utcnow().timestamp())}"

            vmim = {
                'apiVersion': 'kubevirt.io/v1',
                'kind': 'VirtualMachineInstanceMigration',
                'metadata': {
                    'name': vmim_name,
                    'namespace': namespace,
                    'annotations': {}
                },
                'spec': {
                    'vmiName': vm_name
                }
            }

            # Add policy annotation
            if policy_name:
                vmim['metadata']['annotations']['hyper2kvm.io/migration-policy'] = policy_name

            self.custom_api.create_namespaced_custom_object(
                group='kubevirt.io',
                version='v1',
                namespace=namespace,
                plural='virtualmachineinstancemigrations',
                body=vmim
            )

            logger.info(f"✅ Created live migration: {vmim_name}")

            # Emit event
            try:
                event = client.V1Event(
                    metadata=client.V1ObjectMeta(
                        name=f"{vm_name}.live.migration.started",
                        namespace=namespace
                    ),
                    involved_object=client.V1ObjectReference(
                        api_version='kubevirt.io/v1',
                        kind='VirtualMachine',
                        name=vm_name,
                        namespace=namespace
                    ),
                    reason='LiveMigrationStarted',
                    message=f'Live migration started: {vmim_name}',
                    type='Normal',
                    first_timestamp=datetime.utcnow(),
                    last_timestamp=datetime.utcnow(),
                    count=1,
                    source=client.V1EventSource(component='hyper2kvm-operator')
                )
                self.core_api.create_namespaced_event(namespace, event)
            except Exception as e:
                logger.warning(f"Failed to create event: {e}")

            return {
                'success': True,
                'vmim_name': vmim_name,
                'message': f'Live migration started: {vmim_name}'
            }

        except client.ApiException as e:
            logger.error(f"Failed to orchestrate live migration: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def orchestrate_storage_migration(
        self,
        namespace: str,
        vm_name: str,
        volume_name: str,
        target_storage_class: str,
        size: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Orchestrate storage migration for a VM volume.

        Workflow:
        1. Create new PVC with target storage class
        2. Copy data (using migration pod)
        3. Update VM to use new PVC
        4. Clean up old PVC

        Args:
            namespace: VM namespace
            vm_name: VM name
            volume_name: Volume name to migrate
            target_storage_class: Target StorageClass
            size: New size (optional, defaults to current size)

        Returns:
            Migration result dict
        """
        logger.info(
            f"Orchestrating storage migration for VM {vm_name} "
            f"volume {volume_name} to storage class {target_storage_class}"
        )

        try:
            # Get VM
            vm = self.custom_api.get_namespaced_custom_object(
                group='kubevirt.io',
                version='v1',
                namespace=namespace,
                plural='virtualmachines',
                name=vm_name
            )

            # Find volume in VM spec
            volumes = vm.get('spec', {}).get('template', {}).get('spec', {}).get('volumes', [])
            target_volume = None

            for vol in volumes:
                if vol.get('name') == volume_name:
                    target_volume = vol
                    break

            if not target_volume:
                return {
                    'success': False,
                    'message': f'Volume {volume_name} not found in VM {vm_name}'
                }

            # Get current PVC
            pvc_name = target_volume.get('persistentVolumeClaim', {}).get('claimName')
            if not pvc_name:
                return {
                    'success': False,
                    'message': f'Volume {volume_name} is not a PVC volume'
                }

            # Create new PVC name
            new_pvc_name = f"{pvc_name}-migrated"

            logger.info(
                f"Creating new PVC {new_pvc_name} with storage class {target_storage_class}"
            )

            # Get current PVC to copy metadata
            try:
                current_pvc = self.core_api.read_namespaced_persistent_volume_claim(
                    pvc_name,
                    namespace
                )
            except client.ApiException as e:
                return {
                    'success': False,
                    'message': f'Failed to get current PVC: {e}'
                }

            # Use current size if not specified
            if not size:
                size = current_pvc.spec.resources.requests.get('storage')

            # Create new PVC
            new_pvc = client.V1PersistentVolumeClaim(
                metadata=client.V1ObjectMeta(
                    name=new_pvc_name,
                    namespace=namespace,
                    labels={
                        'hyper2kvm.io/vm': vm_name,
                        'hyper2kvm.io/storage-migration': 'true'
                    }
                ),
                spec=client.V1PersistentVolumeClaimSpec(
                    storage_class_name=target_storage_class,
                    access_modes=current_pvc.spec.access_modes,
                    resources=client.V1ResourceRequirements(
                        requests={'storage': size}
                    )
                )
            )

            try:
                self.core_api.create_namespaced_persistent_volume_claim(
                    namespace,
                    new_pvc
                )
                logger.info(f"✅ Created new PVC: {new_pvc_name}")
            except client.ApiException as e:
                if e.status != 409:
                    return {
                        'success': False,
                        'message': f'Failed to create new PVC: {e}'
                    }

            return {
                'success': True,
                'new_pvc_name': new_pvc_name,
                'message': (
                    f'Storage migration initiated. New PVC created: {new_pvc_name}. '
                    'Data copy and VM update required.'
                )
            }

        except Exception as e:
            logger.error(f"Failed to orchestrate storage migration: {e}")
            return {
                'success': False,
                'error': str(e)
            }
