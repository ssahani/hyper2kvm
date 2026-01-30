"""
Kubernetes Operator Controller for OfflineFixJob CRD.

This operator watches OfflineFixJob resources and orchestrates:
- Node selection for NBD operations
- NBD preparation via DaemonSet
- KubeVirt VM creation for offline fixes
- Result collection and status updates

Architecture:
  Controller (this) -> Annotates node -> DaemonSet prepares NBD ->
  Controller creates VM -> VM runs fixers -> Controller collects results
"""

import asyncio
import json
import logging
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
ANNOTATION_OFFLINE_FIX_JOB = "offlinefix.hyper2kvm.io/job"
ANNOTATION_NBD_READY = "offlinefix.hyper2kvm.io/nbd-ready"
ANNOTATION_NBD_DEVICE = "offlinefix.hyper2kvm.io/nbd-device"
ANNOTATION_MOUNT_PATH = "offlinefix.hyper2kvm.io/mount-path"
ANNOTATION_CLEANUP = "offlinefix.hyper2kvm.io/cleanup"

LABEL_NBD_CAPABLE = "hyper2kvm.io/nbd-capable"


@kopf.on.create('hyper2kvm.io', 'v1alpha1', 'offlinefixjobs')
async def create_offline_fix_job(
    name: str,
    namespace: str,
    spec: Dict[str, Any],
    status: Dict[str, Any],
    **kwargs
):
    """
    Handle creation of OfflineFixJob resource.

    Initializes the job and transitions to Pending state.
    """
    logger.info(f"OfflineFixJob created: {namespace}/{name}")

    try:
        # Validate spec
        source = spec.get('source', {})
        disk = source.get('disk', {})
        fixes = spec.get('fixes', [])

        if not disk.get('type'):
            raise ValueError("Missing disk type in source.disk")

        if not fixes:
            raise ValueError("No fixes specified")

        # Initialize status
        return {
            'phase': 'Pending',
            'startedAt': datetime.now(timezone.utc).isoformat(),
            'conditions': [{
                'type': 'Initialized',
                'status': 'True',
                'lastTransitionTime': datetime.now(timezone.utc).isoformat(),
                'reason': 'JobCreated',
                'message': f'OfflineFixJob created with {len(fixes)} fixes'
            }]
        }

    except Exception as e:
        logger.error(f"Failed to create job {name}: {e}")
        return {
            'phase': 'Failed',
            'conditions': [{
                'type': 'Failed',
                'status': 'True',
                'lastTransitionTime': datetime.now(timezone.utc).isoformat(),
                'reason': 'ValidationFailed',
                'message': str(e)
            }]
        }


@kopf.on.field('hyper2kvm.io', 'v1alpha1', 'offlinefixjobs', field='status.phase', new='Pending')
async def handle_pending(
    name: str,
    namespace: str,
    spec: Dict[str, Any],
    status: Dict[str, Any],
    patch: kopf.Patch,
    **kwargs
):
    """
    Handle Pending phase: Select node and trigger NBD setup.
    """
    logger.info(f"Handling Pending phase for {namespace}/{name}")

    try:
        # Load Kubernetes config
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        api = client.CoreV1Api()

        # Select NBD-capable node
        node_selector = spec.get('nodeSelector', {})
        node_selector[LABEL_NBD_CAPABLE] = 'true'

        nodes = api.list_node(label_selector=','.join([f"{k}={v}" for k, v in node_selector.items()]))

        if not nodes.items:
            raise Exception("No NBD-capable nodes found")

        # Select first available node
        node = nodes.items[0]
        node_name = node.metadata.name

        logger.info(f"Selected node: {node_name}")

        # Annotate node to trigger DaemonSet
        job_ref = f"{namespace}/{name}"

        # Update node annotations
        body = {
            "metadata": {
                "annotations": {
                    ANNOTATION_OFFLINE_FIX_JOB: job_ref
                }
            }
        }

        api.patch_node(node_name, body)

        logger.info(f"Annotated node {node_name} for job {job_ref}")

        # Update job status
        patch.status['node'] = node_name
        patch.status['conditions'] = status.get('conditions', []) + [{
            'type': 'NodeSelected',
            'status': 'True',
            'lastTransitionTime': datetime.now(timezone.utc).isoformat(),
            'reason': 'NodeAnnotated',
            'message': f'Node {node_name} selected for NBD setup'
        }]

        # Schedule check for NBD readiness
        await asyncio.sleep(5)
        await check_nbd_ready(name, namespace, spec, status, patch, node_name, api)

    except Exception as e:
        logger.error(f"Failed to handle Pending phase: {e}")
        patch.status['phase'] = 'Failed'
        patch.status['conditions'] = status.get('conditions', []) + [{
            'type': 'Failed',
            'status': 'True',
            'lastTransitionTime': datetime.now(timezone.utc).isoformat(),
            'reason': 'NodeSelectionFailed',
            'message': str(e)
        }]


async def check_nbd_ready(
    name: str,
    namespace: str,
    spec: Dict[str, Any],
    status: Dict[str, Any],
    patch: kopf.Patch,
    node_name: str,
    api: client.CoreV1Api
):
    """
    Check if NBD is ready on the node.
    """
    max_attempts = 60  # 5 minutes with 5-second intervals
    attempts = 0

    while attempts < max_attempts:
        try:
            # Get node
            node = api.read_node(node_name)
            annotations = node.metadata.annotations or {}

            # Check if NBD is ready
            if annotations.get(ANNOTATION_NBD_READY) == 'true':
                logger.info(f"NBD ready on node {node_name}")

                # Extract NBD info
                nbd_device = annotations.get(ANNOTATION_NBD_DEVICE)
                mount_path = annotations.get(ANNOTATION_MOUNT_PATH)

                # Update status
                patch.status['nbdDevice'] = nbd_device
                patch.status['mountPath'] = mount_path
                patch.status['phase'] = 'NBDPrepared'
                patch.status['conditions'] = status.get('conditions', []) + [{
                    'type': 'NBDPrepared',
                    'status': 'True',
                    'lastTransitionTime': datetime.now(timezone.utc).isoformat(),
                    'reason': 'NBDMounted',
                    'message': f'NBD device {nbd_device} mounted at {mount_path}'
                }]

                # Create VM
                await create_fixer_vm(name, namespace, spec, status, patch, nbd_device, mount_path, node_name)
                return

        except Exception as e:
            logger.warning(f"Error checking NBD readiness: {e}")

        attempts += 1
        await asyncio.sleep(5)

    # Timeout
    logger.error(f"NBD preparation timed out for {namespace}/{name}")
    patch.status['phase'] = 'Failed'
    patch.status['conditions'] = status.get('conditions', []) + [{
        'type': 'Failed',
        'status': 'True',
        'lastTransitionTime': datetime.now(timezone.utc).isoformat(),
        'reason': 'NBDTimeout',
        'message': 'NBD preparation timed out after 5 minutes'
    }]


async def create_fixer_vm(
    name: str,
    namespace: str,
    spec: Dict[str, Any],
    status: Dict[str, Any],
    patch: kopf.Patch,
    nbd_device: str,
    mount_path: str,
    node_name: str
):
    """
    Create privileged Pod for offline fixes.

    Note: Currently uses privileged Pod for NBD device access.
    TODO: Migrate to KubeVirt HostDisk for production.
    """
    logger.info(f"Creating fixer Pod for {namespace}/{name}")

    try:
        # Load Kubernetes config
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        core_api = client.CoreV1Api()
        api = client.CustomObjectsApi()

        # Get execution settings
        execution = spec.get('execution', {})
        vm_image = execution.get('vmImage', 'quay.io/hyper2kvm/offline-fix-vm:v1.0.0')
        resources = execution.get('resources', {})
        memory = resources.get('memory', '2Gi')
        cpu = resources.get('cpu', '2')

        # Create job spec ConfigMap
        spec_cm_name = f'offline-fix-spec-{name}'
        job_spec = {
            'job_id': name,
            'fixes': spec.get('fixes', []),
            'parameters': spec.get('parameters', {}),
            'safety': spec.get('safety', {'readOnly': False})
        }

        spec_cm = {
            'apiVersion': 'v1',
            'kind': 'ConfigMap',
            'metadata': {
                'name': spec_cm_name,
                'namespace': namespace
            },
            'data': {
                'spec.json': json.dumps(job_spec, indent=2)
            }
        }

        try:
            core_api = client.CoreV1Api()
            core_api.create_namespaced_config_map(namespace, spec_cm)
        except ApiException as e:
            if e.status != 409:  # Ignore if already exists
                raise

        # Create privileged Pod for offline fixes
        # TODO: Migrate to KubeVirt HostDisk approach for production
        pod_name = f'offline-fix-{name}'
        pod = {
            'apiVersion': 'v1',
            'kind': 'Pod',
            'metadata': {
                'name': pod_name,
                'namespace': namespace,
                'labels': {
                    'app': 'offline-fix',
                    'job': name
                }
            },
            'spec': {
                'restartPolicy': 'Never',
                'nodeSelector': {
                    'kubernetes.io/hostname': node_name
                },
                'containers': [
                    {
                        'name': 'fixer',
                        'image': vm_image,
                        'imagePullPolicy': 'IfNotPresent',
                        'securityContext': {
                            'privileged': True
                        },
                        'resources': {
                            'requests': {
                                'memory': memory,
                                'cpu': cpu
                            },
                            'limits': {
                                'memory': memory,
                                'cpu': cpu
                            }
                        },
                        'volumeMounts': [
                            {
                                'name': 'vmroot',
                                'mountPath': '/vmroot'
                            },
                            {
                                'name': 'config',
                                'mountPath': '/config'
                            },
                            {
                                'name': 'dev',
                                'mountPath': '/dev'
                            }
                        ],
                        'env': [
                            {
                                'name': 'JOB_SPEC',
                                'value': '/config/spec.json'
                            },
                            {
                                'name': 'NBD_DEVICE',
                                'value': nbd_device
                            },
                            {
                                'name': 'MOUNT_PATH',
                                'value': mount_path
                            }
                        ]
                    }
                ],
                'volumes': [
                    {
                        'name': 'vmroot',
                        'hostPath': {
                            'path': mount_path,
                            'type': 'Directory'
                        }
                    },
                    {
                        'name': 'config',
                        'configMap': {
                            'name': spec_cm_name
                        }
                    },
                    {
                        'name': 'dev',
                        'hostPath': {
                            'path': '/dev',
                            'type': 'Directory'
                        }
                    }
                ]
            }
        }

        # Create Pod
        core_api.create_namespaced_pod(namespace, pod)

        logger.info(f"Created fixer Pod {pod_name}")

        # Update status
        patch.status['podName'] = pod_name
        patch.status['phase'] = 'Fixing'
        patch.status['conditions'] = status.get('conditions', []) + [{
            'type': 'PodCreated',
            'status': 'True',
            'lastTransitionTime': datetime.now(timezone.utc).isoformat(),
            'reason': 'FixerPodStarted',
            'message': f'Fixer Pod {pod_name} created'
        }]

    except Exception as e:
        logger.error(f"Failed to create fixer Pod: {e}")
        patch.status['phase'] = 'Failed'
        patch.status['conditions'] = status.get('conditions', []) + [{
            'type': 'Failed',
            'status': 'True',
            'lastTransitionTime': datetime.now(timezone.utc).isoformat(),
            'reason': 'PodCreationFailed',
            'message': str(e)
        }]


@kopf.on.delete('hyper2kvm.io', 'v1alpha1', 'offlinefixjobs')
async def delete_offline_fix_job(
    name: str,
    namespace: str,
    status: Dict[str, Any],
    **kwargs
):
    """
    Handle deletion of OfflineFixJob.

    Cleanup:
    - Delete fixer Pod
    - Signal DaemonSet to cleanup NBD
    - Remove node annotations
    """
    logger.info(f"OfflineFixJob deleted: {namespace}/{name}")

    try:
        # Load Kubernetes config
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        core_api = client.CoreV1Api()

        # Delete fixer Pod if exists
        pod_name = status.get('podName')
        if pod_name:
            try:
                core_api.delete_namespaced_pod(
                    name=pod_name,
                    namespace=namespace
                )
                logger.info(f"Deleted fixer Pod {pod_name}")
            except ApiException as e:
                if e.status != 404:
                    logger.warning(f"Failed to delete Pod: {e}")

        # Signal cleanup to DaemonSet via node annotation
        node_name = status.get('node')
        if node_name:
            try:
                body = {
                    "metadata": {
                        "annotations": {
                            ANNOTATION_CLEANUP: 'true',
                            ANNOTATION_OFFLINE_FIX_JOB: None,  # Remove
                            ANNOTATION_NBD_READY: None  # Remove
                        }
                    }
                }
                core_api.patch_node(node_name, body)
                logger.info(f"Signaled cleanup to node {node_name}")
            except Exception as e:
                logger.warning(f"Failed to update node: {e}")

    except Exception as e:
        logger.error(f"Failed to cleanup job {name}: {e}")


if __name__ == "__main__":
    # This would be run as part of the main operator
    pass
