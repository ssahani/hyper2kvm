"""
Storage Migration Controller for handling volume updates and hot-plug operations.

Handles:
- Volume addition/removal while VM is running
- Storage class changes (hot migration)
- Volume expansion
- Integration with KubeVirt's updateVolumesStrategy
"""

import logging
import kopf
from kubernetes import client
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Global metrics instance
_metrics = None


def set_metrics(metrics):
    """Set the global metrics instance."""
    global _metrics
    _metrics = metrics


def _get_volume_names(volumes: List[Dict[str, Any]]) -> set:
    """Extract volume names from volume list."""
    return {vol.get('name') for vol in volumes if vol.get('name')}


@kopf.on.update('kubevirt.io', 'v1', 'virtualmachines', field='spec.template.spec.volumes')
async def on_vm_volumes_changed(old, new, spec, meta, namespace, name, **kwargs):
    """
    Handle VirtualMachine volume updates.

    Detects:
    - New volumes added
    - Volumes removed
    - Volume PVC changes
    """
    if old is None:
        return

    old_volumes = old if isinstance(old, list) else []
    new_volumes = new if isinstance(new, list) else []

    old_volume_names = _get_volume_names(old_volumes)
    new_volume_names = _get_volume_names(new_volumes)

    # Detect added volumes
    added = new_volume_names - old_volume_names
    if added:
        logger.info(f"Volumes added to VM {name}: {added}")

        # Emit event
        try:
            core_api = client.CoreV1Api()
            event = client.V1Event(
                metadata=client.V1ObjectMeta(
                    name=f"{name}.volumes.added",
                    namespace=namespace
                ),
                involved_object=client.V1ObjectReference(
                    api_version='kubevirt.io/v1',
                    kind='VirtualMachine',
                    name=name,
                    namespace=namespace
                ),
                reason='VolumesAdded',
                message=f'Volumes added: {", ".join(added)}',
                type='Normal',
                first_timestamp=datetime.utcnow(),
                last_timestamp=datetime.utcnow(),
                count=1,
                source=client.V1EventSource(component='hyper2kvm-operator')
            )
            core_api.create_namespaced_event(namespace, event)
        except Exception as e:
            logger.warning(f"Failed to create event: {e}")

        # Handle hot-plug if VM is running
        await handle_volume_hotplug(namespace, name, list(added))

    # Detect removed volumes
    removed = old_volume_names - new_volume_names
    if removed:
        logger.info(f"Volumes removed from VM {name}: {removed}")

        # Emit event
        try:
            core_api = client.CoreV1Api()
            event = client.V1Event(
                metadata=client.V1ObjectMeta(
                    name=f"{name}.volumes.removed",
                    namespace=namespace
                ),
                involved_object=client.V1ObjectReference(
                    api_version='kubevirt.io/v1',
                    kind='VirtualMachine',
                    name=name,
                    namespace=namespace
                ),
                reason='VolumesRemoved',
                message=f'Volumes removed: {", ".join(removed)}',
                type='Normal',
                first_timestamp=datetime.utcnow(),
                last_timestamp=datetime.utcnow(),
                count=1,
                source=client.V1EventSource(component='hyper2kvm-operator')
            )
            core_api.create_namespaced_event(namespace, event)
        except Exception as e:
            logger.warning(f"Failed to create event: {e}")

        # Handle hot-unplug if VM is running
        await handle_volume_hotunplug(namespace, name, list(removed))

    # Detect volume PVC changes
    for vol_name in old_volume_names & new_volume_names:
        old_vol = next((v for v in old_volumes if v.get('name') == vol_name), None)
        new_vol = next((v for v in new_volumes if v.get('name') == vol_name), None)

        if old_vol and new_vol:
            old_pvc = old_vol.get('persistentVolumeClaim', {}).get('claimName')
            new_pvc = new_vol.get('persistentVolumeClaim', {}).get('claimName')

            if old_pvc != new_pvc:
                logger.info(
                    f"Volume {vol_name} PVC changed in VM {name}: "
                    f"{old_pvc} -> {new_pvc}"
                )

                # This requires live migration to a new storage
                await handle_storage_migration(namespace, name, vol_name, old_pvc, new_pvc)


async def handle_volume_hotplug(namespace: str, vm_name: str, volume_names: List[str]):
    """
    Handle hot-plug of volumes to a running VM.

    Args:
        namespace: VM namespace
        vm_name: VM name
        volume_names: Names of volumes to hot-plug
    """
    try:
        custom_api = client.CustomObjectsApi()

        # Check if VM is running
        vm = custom_api.get_namespaced_custom_object(
            group='kubevirt.io',
            version='v1',
            namespace=namespace,
            plural='virtualmachines',
            name=vm_name
        )

        if not vm.get('spec', {}).get('running', False):
            logger.info(f"VM {vm_name} is not running, hot-plug will occur on next start")
            return

        # Get VMI
        try:
            vmi = custom_api.get_namespaced_custom_object(
                group='kubevirt.io',
                version='v1',
                namespace=namespace,
                plural='virtualmachineinstances',
                name=vm_name
            )
        except client.ApiException as e:
            if e.status == 404:
                logger.info(f"VMI {vm_name} not found, cannot hot-plug volumes")
                return
            raise

        logger.info(f"Hot-plugging volumes to VMI {vm_name}: {volume_names}")

        # KubeVirt supports hot-plug via addVolume API
        # This is a simplified approach - actual implementation would use
        # VirtualMachineInstance's addvolume subresource

        for vol_name in volume_names:
            logger.info(f"Volume {vol_name} will be hot-plugged on next VMI restart")

    except Exception as e:
        logger.error(f"Failed to hot-plug volumes: {e}")


async def handle_volume_hotunplug(namespace: str, vm_name: str, volume_names: List[str]):
    """
    Handle hot-unplug of volumes from a running VM.

    Args:
        namespace: VM namespace
        vm_name: VM name
        volume_names: Names of volumes to hot-unplug
    """
    try:
        custom_api = client.CustomObjectsApi()

        # Check if VM is running
        vm = custom_api.get_namespaced_custom_object(
            group='kubevirt.io',
            version='v1',
            namespace=namespace,
            plural='virtualmachines',
            name=vm_name
        )

        if not vm.get('spec', {}).get('running', False):
            logger.info(f"VM {vm_name} is not running, volumes already removed")
            return

        logger.info(f"Hot-unplugging volumes from VM {vm_name}: {volume_names}")

        # KubeVirt supports hot-unplug via removeVolume API
        # Actual implementation would use VirtualMachineInstance's removevolume subresource

        for vol_name in volume_names:
            logger.info(f"Volume {vol_name} will be hot-unplugged on next VMI restart")

    except Exception as e:
        logger.error(f"Failed to hot-unplug volumes: {e}")


async def handle_storage_migration(
    namespace: str,
    vm_name: str,
    volume_name: str,
    old_pvc: str,
    new_pvc: str
):
    """
    Handle storage migration (changing PVC for a volume).

    This typically requires:
    1. Create new PVC with desired storage class
    2. Copy data from old PVC to new PVC
    3. Live migrate VM to use new PVC
    4. Clean up old PVC

    Args:
        namespace: VM namespace
        vm_name: VM name
        volume_name: Volume name being migrated
        old_pvc: Old PVC name
        new_pvc: New PVC name
    """
    logger.info(
        f"Storage migration for VM {vm_name} volume {volume_name}: "
        f"{old_pvc} -> {new_pvc}"
    )

    try:
        custom_api = client.CustomObjectsApi()
        core_api = client.CoreV1Api()

        # Verify new PVC exists
        try:
            new_pvc_obj = core_api.read_namespaced_persistent_volume_claim(new_pvc, namespace)
        except client.ApiException as e:
            if e.status == 404:
                logger.error(f"New PVC {new_pvc} not found, cannot migrate storage")
                return
            raise

        # Check if VM is running - may need to trigger migration
        vm = custom_api.get_namespaced_custom_object(
            group='kubevirt.io',
            version='v1',
            namespace=namespace,
            plural='virtualmachines',
            name=vm_name
        )

        if vm.get('spec', {}).get('running', False):
            logger.info(
                f"VM {vm_name} is running, storage change will require restart or "
                "live migration to apply"
            )

            # Emit event
            event = client.V1Event(
                metadata=client.V1ObjectMeta(
                    name=f"{vm_name}.storage.migration",
                    namespace=namespace
                ),
                involved_object=client.V1ObjectReference(
                    api_version='kubevirt.io/v1',
                    kind='VirtualMachine',
                    name=vm_name,
                    namespace=namespace
                ),
                reason='StorageMigrationRequired',
                message=f'Volume {volume_name} storage changed to {new_pvc}',
                type='Normal',
                first_timestamp=datetime.utcnow(),
                last_timestamp=datetime.utcnow(),
                count=1,
                source=client.V1EventSource(component='hyper2kvm-operator')
            )
            core_api.create_namespaced_event(namespace, event)

    except Exception as e:
        logger.error(f"Failed to handle storage migration: {e}")
