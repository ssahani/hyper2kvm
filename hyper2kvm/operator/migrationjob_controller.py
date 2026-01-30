"""
Kubernetes Operator Controller for MigrationJob CRD.

This operator watches MigrationJob resources and orchestrates:
- VMDK upload to source PVC (if needed)
- NBD preparation via DaemonSet
- Migration pod creation and execution
- VM creation (optional)

Architecture:
  Controller (this) -> Creates source PVC -> Uploads VMDK ->
  Annotates node -> DaemonSet prepares NBD ->
  Controller creates migration Pod -> Pod runs hyper2kvm ->
  Controller creates VM (optional) -> Status updated
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import kopf
import kubernetes
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
ANNOTATION_MIGRATION_JOB = "migration.hyper2kvm.io/job"
ANNOTATION_NBD_READY = "migration.hyper2kvm.io/nbd-ready"
ANNOTATION_NBD_DEVICE = "migration.hyper2kvm.io/nbd-device"
ANNOTATION_MOUNT_PATH = "migration.hyper2kvm.io/mount-path"
ANNOTATION_CLEANUP = "migration.hyper2kvm.io/cleanup"

LABEL_NBD_CAPABLE = "hyper2kvm.io/nbd-capable"
LABEL_MIGRATION_JOB = "migration.hyper2kvm.io/job"

# Migration container image
MIGRATION_IMAGE = "ghcr.io/hyper2kvm/migration:latest"


@kopf.on.create('hyper2kvm.io', 'v1alpha1', 'migrationjobs')
async def create_migration_job(
    name: str,
    namespace: str,
    spec: Dict[str, Any],
    status: Dict[str, Any],
    **kwargs
):
    """
    Handle MigrationJob creation.

    Workflow:
    1. Validate spec
    2. Create source PVC (if needed)
    3. Upload VMDK (if URL source)
    4. Create destination PVC
    5. Select node for migration
    6. Trigger NBD preparation
    7. Create migration pod
    8. Monitor completion
    9. Create VM (if enabled)
    10. Update status
    """
    logger.info(f"🚀 Creating MigrationJob: {namespace}/{name}")

    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    core_api = client.CoreV1Api()
    custom_api = client.CustomObjectsApi()

    # Parse spec
    source = spec.get('source', {})
    migration = spec.get('migration', {})
    destination = spec.get('destination', {})
    create_vm_spec = spec.get('createVM', {})

    # Initialize status
    await update_status(
        custom_api, namespace, name,
        phase='Pending',
        message='Migration job created, preparing resources...'
    )

    # Step 1: Create source PVC if needed
    source_pvc_name = await ensure_source_pvc(
        core_api, custom_api, namespace, name, source
    )

    # Step 2: Create destination PVC
    dest_pvc_name = await create_destination_pvc(
        core_api, custom_api, namespace, name, destination
    )

    # Step 3: Select node for migration
    node_name = await select_migration_node(core_api, spec.get('migration', {}).get('nodeSelector'))

    if not node_name:
        await update_status(
            custom_api, namespace, name,
            phase='Failed',
            message='No NBD-capable node found'
        )
        return

    logger.info(f"✅ Selected node: {node_name}")

    # Step 4: Annotate node to trigger NBD preparation
    await annotate_node_for_nbd(
        core_api, node_name, name, source_pvc_name
    )

    # Step 5: Wait for NBD preparation
    await update_status(
        custom_api, namespace, name,
        phase='Preparing',
        message=f'Preparing NBD device on node {node_name}...'
    )

    nbd_device, mount_path = await wait_for_nbd_ready(
        core_api, node_name, name, timeout=300
    )

    if not nbd_device:
        await update_status(
            custom_api, namespace, name,
            phase='Failed',
            message='NBD preparation failed or timed out'
        )
        return

    logger.info(f"✅ NBD ready: {nbd_device} at {mount_path}")

    # Step 6: Create migration pod
    await update_status(
        custom_api, namespace, name,
        phase='Migrating',
        message='Running migration...'
    )

    migration_pod_name = await create_migration_pod(
        core_api, namespace, name, node_name,
        source_pvc_name, dest_pvc_name, nbd_device, mount_path,
        migration, destination
    )

    # Step 7: Monitor migration pod
    success = await wait_for_pod_completion(
        core_api, namespace, migration_pod_name, timeout=3600
    )

    if not success:
        await update_status(
            custom_api, namespace, name,
            phase='Failed',
            message='Migration pod failed'
        )
        return

    logger.info(f"✅ Migration completed successfully")

    # Step 8: Create VM if enabled
    vm_name = None
    if create_vm_spec.get('enabled', False):
        await update_status(
            custom_api, namespace, name,
            phase='Creating',
            message='Creating VirtualMachine...'
        )

        vm_name = await create_virtual_machine(
            custom_api, namespace, name, dest_pvc_name, create_vm_spec
        )

        logger.info(f"✅ Created VM: {vm_name}")

    # Step 9: Cleanup if needed
    cleanup_policy = spec.get('cleanupPolicy', 'OnSuccess')
    if cleanup_policy in ['Always', 'OnSuccess']:
        await cleanup_resources(
            core_api, custom_api, namespace, node_name, name,
            source_pvc_name, migration_pod_name
        )

    # Step 10: Update final status
    await update_status(
        custom_api, namespace, name,
        phase='Completed',
        message='Migration completed successfully',
        destination_pvc=dest_pvc_name,
        vm_name=vm_name,
        completion_time=datetime.now(timezone.utc).isoformat()
    )

    logger.info(f"🎉 MigrationJob {namespace}/{name} completed!")


async def ensure_source_pvc(
    core_api: client.CoreV1Api,
    custom_api: client.CustomObjectsApi,
    namespace: str,
    job_name: str,
    source: Dict[str, Any]
) -> str:
    """
    Ensure source PVC exists.

    If source is URL, create PVC and upload.
    If source is PVC, return existing name.
    """
    source_type = source.get('type', 'vmdk-url')

    if source_type == 'vmdk-url':
        # Create source PVC and upload VMDK
        vmdk_spec = source.get('vmdk', {})
        url = vmdk_spec.get('url')

        if not url:
            raise ValueError("VMDK URL is required for vmdk-url source type")

        # Create source PVC
        pvc_name = f"{job_name}-source"

        # Estimate size from URL (or use default)
        # TODO: HEAD request to get Content-Length
        size = "10Gi"  # Default

        pvc = client.V1PersistentVolumeClaim(
            metadata=client.V1ObjectMeta(
                name=pvc_name,
                labels={LABEL_MIGRATION_JOB: job_name}
            ),
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=['ReadWriteOnce'],
                storage_class_name='local-path',  # TODO: Make configurable
                resources=client.V1ResourceRequirements(
                    requests={'storage': size}
                )
            )
        )

        try:
            core_api.create_namespaced_persistent_volume_claim(namespace, pvc)
            logger.info(f"✅ Created source PVC: {pvc_name}")
        except ApiException as e:
            if e.status != 409:  # Already exists
                raise

        # Update status
        await update_status(
            custom_api, namespace, job_name,
            phase='Uploading',
            message=f'Uploading VMDK from {url}...',
            source_pvc=pvc_name
        )

        # Create uploader pod to download VMDK
        await upload_vmdk_to_pvc(core_api, namespace, pvc_name, url)

        return pvc_name

    elif source_type == 'vmdk-pvc':
        # Use existing PVC
        pvc_name = source.get('vmdk', {}).get('pvcName')
        if not pvc_name:
            raise ValueError("PVC name is required for vmdk-pvc source type")
        return pvc_name

    elif source_type == 'pvc':
        # Use existing PVC directly
        pvc_name = source.get('pvc', {}).get('name')
        if not pvc_name:
            raise ValueError("PVC name is required for pvc source type")
        return pvc_name

    else:
        raise ValueError(f"Unknown source type: {source_type}")


async def upload_vmdk_to_pvc(
    core_api: client.CoreV1Api,
    namespace: str,
    pvc_name: str,
    url: str
):
    """Upload VMDK from URL to PVC using a temporary pod."""
    pod_name = f"uploader-{pvc_name}"

    pod = client.V1Pod(
        metadata=client.V1ObjectMeta(name=pod_name),
        spec=client.V1PodSpec(
            restart_policy='Never',
            containers=[
                client.V1Container(
                    name='uploader',
                    image='alpine:latest',
                    command=[
                        'sh', '-c',
                        f'apk add --no-cache curl && '
                        f'curl -L -o /data/disk.vmdk "{url}" && '
                        f'echo "Upload complete"'
                    ],
                    volume_mounts=[
                        client.V1VolumeMount(
                            name='data',
                            mount_path='/data'
                        )
                    ]
                )
            ],
            volumes=[
                client.V1Volume(
                    name='data',
                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                        claim_name=pvc_name
                    )
                )
            ]
        )
    )

    try:
        core_api.create_namespaced_pod(namespace, pod)
        logger.info(f"✅ Created uploader pod: {pod_name}")
    except ApiException as e:
        if e.status != 409:
            raise

    # Wait for upload completion
    await wait_for_pod_completion(core_api, namespace, pod_name, timeout=1800)

    # Cleanup uploader pod
    core_api.delete_namespaced_pod(
        pod_name, namespace,
        body=client.V1DeleteOptions(grace_period_seconds=0)
    )


async def create_destination_pvc(
    core_api: client.CoreV1Api,
    custom_api: client.CustomObjectsApi,
    namespace: str,
    job_name: str,
    destination: Dict[str, Any]
) -> str:
    """Create destination PVC for migrated image."""
    pvc_name = destination.get('pvcName', f"{job_name}-disk")
    size = destination.get('size', '10Gi')
    storage_class = destination.get('storageClass', 'local-path')
    access_modes = destination.get('accessModes', ['ReadWriteOnce'])

    pvc = client.V1PersistentVolumeClaim(
        metadata=client.V1ObjectMeta(
            name=pvc_name,
            labels={LABEL_MIGRATION_JOB: job_name}
        ),
        spec=client.V1PersistentVolumeClaimSpec(
            access_modes=access_modes,
            storage_class_name=storage_class,
            resources=client.V1ResourceRequirements(
                requests={'storage': size}
            )
        )
    )

    try:
        core_api.create_namespaced_persistent_volume_claim(namespace, pvc)
        logger.info(f"✅ Created destination PVC: {pvc_name}")
    except ApiException as e:
        if e.status != 409:
            raise

    await update_status(
        custom_api, namespace, job_name,
        destination_pvc=pvc_name
    )

    return pvc_name


async def select_migration_node(
    core_api: client.CoreV1Api,
    node_selector: Optional[Dict[str, str]] = None
) -> Optional[str]:
    """Select a node capable of NBD operations."""
    label_selector = f"{LABEL_NBD_CAPABLE}=true"

    if node_selector:
        for k, v in node_selector.items():
            label_selector += f",{k}={v}"

    nodes = core_api.list_node(label_selector=label_selector)

    if not nodes.items:
        logger.error("❌ No NBD-capable nodes found")
        return None

    # Select first ready node
    for node in nodes.items:
        for condition in node.status.conditions:
            if condition.type == 'Ready' and condition.status == 'True':
                return node.metadata.name

    return None


async def annotate_node_for_nbd(
    core_api: client.CoreV1Api,
    node_name: str,
    job_name: str,
    pvc_name: str
):
    """Annotate node to trigger NBD preparation by DaemonSet."""
    body = {
        'metadata': {
            'annotations': {
                ANNOTATION_MIGRATION_JOB: job_name,
                'migration.hyper2kvm.io/source-pvc': pvc_name
            }
        }
    }

    core_api.patch_node(node_name, body)
    logger.info(f"✅ Annotated node {node_name} for NBD preparation")


async def wait_for_nbd_ready(
    core_api: client.CoreV1Api,
    node_name: str,
    job_name: str,
    timeout: int = 300
) -> tuple[Optional[str], Optional[str]]:
    """Wait for NBD device to be ready on node."""
    start_time = asyncio.get_event_loop().time()

    while (asyncio.get_event_loop().time() - start_time) < timeout:
        node = core_api.read_node(node_name)
        annotations = node.metadata.annotations or {}

        if annotations.get(ANNOTATION_NBD_READY) == 'true':
            nbd_device = annotations.get(ANNOTATION_NBD_DEVICE)
            mount_path = annotations.get(ANNOTATION_MOUNT_PATH)
            return nbd_device, mount_path

        await asyncio.sleep(5)

    logger.error("❌ NBD preparation timed out")
    return None, None


async def create_migration_pod(
    core_api: client.CoreV1Api,
    namespace: str,
    job_name: str,
    node_name: str,
    source_pvc: str,
    dest_pvc: str,
    nbd_device: str,
    mount_path: str,
    migration_spec: Dict[str, Any],
    destination_spec: Dict[str, Any]
) -> str:
    """Create migration pod to run hyper2kvm."""
    pod_name = f"migration-{job_name}"

    # Build migration command
    offline_fixes = migration_spec.get('offlineFixes', {})
    conversion = migration_spec.get('conversion', {})

    # Build config for migration
    config_yaml = {
        'cmd': 'local',
        'vmdk': f'{mount_path}/disk.vmdk',
        'output_dir': '/output',
        'to_output': 'disk.img',
        'out_format': conversion.get('format', 'qcow2'),
        'compress': conversion.get('compress', True),
        'fstab_fixes_enable': True,
        'fstab_mode': offline_fixes.get('fstabMode', 'stabilize-all'),
        'fstab_prefer_partuuid': offline_fixes.get('fstabPreferPartuuid', False),
        'grub_fixes_enable': offline_fixes.get('grubFixes', True),
        'initramfs_regen_enable': offline_fixes.get('initramfsRegen', True),
        'initramfs_modules': offline_fixes.get('initramfsModules', [
            'virtio_blk', 'virtio_scsi', 'virtio_net', 'virtio_pci'
        ]),
        'network_fixes_enable': offline_fixes.get('networkFixes', True),
    }

    import yaml
    config_content = yaml.dump(config_yaml)

    pod = client.V1Pod(
        metadata=client.V1ObjectMeta(
            name=pod_name,
            labels={LABEL_MIGRATION_JOB: job_name}
        ),
        spec=client.V1PodSpec(
            node_name=node_name,
            restart_policy='Never',
            containers=[
                client.V1Container(
                    name='migration',
                    image=MIGRATION_IMAGE,
                    command=[
                        'sh', '-c',
                        f'echo \'{config_content}\' > /tmp/config.yaml && '
                        f'h2kvmctl --config /tmp/config.yaml'
                    ],
                    security_context=client.V1SecurityContext(
                        privileged=True
                    ),
                    volume_mounts=[
                        client.V1VolumeMount(
                            name='source',
                            mount_path=mount_path,
                            read_only=True
                        ),
                        client.V1VolumeMount(
                            name='output',
                            mount_path='/output'
                        ),
                        client.V1VolumeMount(
                            name='dev',
                            mount_path='/dev'
                        )
                    ]
                )
            ],
            volumes=[
                client.V1Volume(
                    name='source',
                    empty_dir={}  # NBD device is already mounted
                ),
                client.V1Volume(
                    name='output',
                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                        claim_name=dest_pvc
                    )
                ),
                client.V1Volume(
                    name='dev',
                    host_path=client.V1HostPathVolumeSource(path='/dev')
                )
            ]
        )
    )

    try:
        core_api.create_namespaced_pod(namespace, pod)
        logger.info(f"✅ Created migration pod: {pod_name}")
    except ApiException as e:
        if e.status != 409:
            raise

    return pod_name


async def wait_for_pod_completion(
    core_api: client.CoreV1Api,
    namespace: str,
    pod_name: str,
    timeout: int = 3600
) -> bool:
    """Wait for pod to complete."""
    start_time = asyncio.get_event_loop().time()

    while (asyncio.get_event_loop().time() - start_time) < timeout:
        try:
            pod = core_api.read_namespaced_pod(pod_name, namespace)
            phase = pod.status.phase

            if phase == 'Succeeded':
                logger.info(f"✅ Pod {pod_name} completed successfully")
                return True
            elif phase == 'Failed':
                logger.error(f"❌ Pod {pod_name} failed")
                return False

            await asyncio.sleep(10)
        except ApiException:
            await asyncio.sleep(10)

    logger.error(f"❌ Pod {pod_name} timed out")
    return False


async def create_virtual_machine(
    custom_api: client.CustomObjectsApi,
    namespace: str,
    job_name: str,
    pvc_name: str,
    create_vm_spec: Dict[str, Any]
) -> str:
    """Create KubeVirt VirtualMachine."""
    vm_name = create_vm_spec.get('name', job_name)
    cpu = create_vm_spec.get('cpu', '2')
    memory = create_vm_spec.get('memory', '2Gi')
    auto_start = create_vm_spec.get('autoStart', False)
    network_type = create_vm_spec.get('networkType', 'masquerade')

    vm = {
        'apiVersion': 'kubevirt.io/v1',
        'kind': 'VirtualMachine',
        'metadata': {
            'name': vm_name,
            'labels': {LABEL_MIGRATION_JOB: job_name}
        },
        'spec': {
            'running': auto_start,
            'template': {
                'metadata': {
                    'labels': {'kubevirt.io/vm': vm_name}
                },
                'spec': {
                    'domain': {
                        'devices': {
                            'disks': [{
                                'name': 'rootdisk',
                                'disk': {'bus': 'virtio'}
                            }],
                            'interfaces': [{
                                'name': 'default',
                                network_type: {}
                            }]
                        },
                        'resources': {
                            'requests': {
                                'memory': memory,
                                'cpu': cpu
                            }
                        }
                    },
                    'networks': [{'name': 'default', 'pod': {}}],
                    'volumes': [{
                        'name': 'rootdisk',
                        'persistentVolumeClaim': {'claimName': pvc_name}
                    }]
                }
            }
        }
    }

    try:
        custom_api.create_namespaced_custom_object(
            group='kubevirt.io',
            version='v1',
            namespace=namespace,
            plural='virtualmachines',
            body=vm
        )
        logger.info(f"✅ Created VirtualMachine: {vm_name}")
    except ApiException as e:
        if e.status != 409:
            raise

    return vm_name


async def cleanup_resources(
    core_api: client.CoreV1Api,
    custom_api: client.CustomObjectsApi,
    namespace: str,
    node_name: str,
    job_name: str,
    source_pvc: str,
    migration_pod: str
):
    """Cleanup temporary resources."""
    logger.info(f"🧹 Cleaning up resources for {job_name}")

    # Cleanup node annotation
    try:
        body = {
            'metadata': {
                'annotations': {
                    ANNOTATION_CLEANUP: 'true'
                }
            }
        }
        core_api.patch_node(node_name, body)
    except Exception as e:
        logger.warning(f"Failed to cleanup node annotation: {e}")

    # Delete migration pod
    try:
        core_api.delete_namespaced_pod(
            migration_pod, namespace,
            body=client.V1DeleteOptions(grace_period_seconds=0)
        )
    except Exception as e:
        logger.warning(f"Failed to delete migration pod: {e}")

    # Delete source PVC if it was created by us
    if source_pvc.endswith('-source'):
        try:
            core_api.delete_namespaced_persistent_volume_claim(
                source_pvc, namespace
            )
        except Exception as e:
            logger.warning(f"Failed to delete source PVC: {e}")


async def update_status(
    custom_api: client.CustomObjectsApi,
    namespace: str,
    name: str,
    **kwargs
):
    """Update MigrationJob status."""
    status_update = {}

    if 'phase' in kwargs:
        status_update['phase'] = kwargs['phase']
    if 'message' in kwargs:
        status_update['message'] = kwargs['message']
    if 'source_pvc' in kwargs:
        status_update['sourcePVC'] = kwargs['source_pvc']
    if 'destination_pvc' in kwargs:
        status_update['destinationPVC'] = kwargs['destination_pvc']
    if 'vm_name' in kwargs:
        status_update['vmName'] = kwargs['vm_name']
    if 'completion_time' in kwargs:
        status_update['completionTime'] = kwargs['completion_time']

    if 'startTime' not in status_update and kwargs.get('phase') == 'Uploading':
        status_update['startTime'] = datetime.now(timezone.utc).isoformat()

    body = {'status': status_update}

    try:
        custom_api.patch_namespaced_custom_object_status(
            group='hyper2kvm.io',
            version='v1alpha1',
            namespace=namespace,
            plural='migrationjobs',
            name=name,
            body=body
        )
    except ApiException as e:
        logger.error(f"Failed to update status: {e}")
