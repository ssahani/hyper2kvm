# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/deployers/kubernetes.py
"""
Kubernetes/k3s deployment module for hyper2kvm.

Automatically deploys migrated VMs to Kubernetes clusters with KubeVirt.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
    HAS_KUBERNETES = True
except ImportError:
    HAS_KUBERNETES = False


class KubernetesDeployer:
    """Deploy migrated VMs to Kubernetes with KubeVirt."""

    def __init__(self, logger, args):
        """
        Initialize Kubernetes deployer.

        Args:
            logger: Logger instance
            args: Parsed arguments with k8s deployment options
        """
        self.logger = logger
        self.args = args

        if not HAS_KUBERNETES:
            raise RuntimeError(
                "kubernetes Python package not installed. "
                "Install with: pip install kubernetes"
            )

        # K8s deployment options
        self.namespace = getattr(args, 'k8s_namespace', 'default')
        self.vm_name = getattr(args, 'k8s_vm_name', None)
        self.pvc_name = getattr(args, 'k8s_pvc_name', None)
        self.storage_class = getattr(args, 'k8s_storage_class', 'local-path')
        self.pvc_size = getattr(args, 'k8s_pvc_size', '10Gi')
        self.cpu_cores = getattr(args, 'k8s_cpu', '2')
        self.memory = getattr(args, 'k8s_memory', '2Gi')
        self.auto_start = getattr(args, 'k8s_auto_start', False)
        self.wait_ready = getattr(args, 'k8s_wait_ready', True)

        # Initialize k8s client
        try:
            config.load_incluster_config()
            self.logger.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            try:
                config.load_kube_config()
                self.logger.info("Loaded Kubernetes config from kubeconfig")
            except config.ConfigException as e:
                raise RuntimeError(f"Failed to load Kubernetes config: {e}")

        self.core_api = client.CoreV1Api()
        self.custom_api = client.CustomObjectsApi()

    def deploy(self, qcow2_path: str) -> Dict[str, Any]:
        """
        Deploy QCOW2 image to Kubernetes cluster.

        Args:
            qcow2_path: Path to the migrated QCOW2 image

        Returns:
            Dict with deployment details (namespace, vm_name, pvc_name, etc.)
        """
        self.logger.info("━" * 80)
        self.logger.info("🚀 Deploying to Kubernetes/k3s")
        self.logger.info("━" * 80)

        # Validate image exists
        if not Path(qcow2_path).exists():
            raise FileNotFoundError(f"QCOW2 image not found: {qcow2_path}")

        # Set defaults if not provided
        if not self.vm_name:
            self.vm_name = Path(qcow2_path).stem
        if not self.pvc_name:
            self.pvc_name = f"{self.vm_name}-disk"

        self.logger.info(f"Namespace: {self.namespace}")
        self.logger.info(f"VM Name: {self.vm_name}")
        self.logger.info(f"PVC Name: {self.pvc_name}")
        self.logger.info(f"Storage Class: {self.storage_class}")

        # Step 1: Validate cluster
        self._validate_cluster()

        # Step 2: Create namespace if needed
        self._ensure_namespace()

        # Step 3: Create PVC
        self._create_pvc()

        # Step 4: Upload QCOW2 to PVC
        self._upload_image(qcow2_path)

        # Step 5: Create VirtualMachine resource
        vm_created = self._create_vm()

        # Step 6: Optionally start and wait
        if self.auto_start:
            self._start_vm()
            if self.wait_ready:
                self._wait_for_vm()

        self.logger.info("━" * 80)
        self.logger.info("✅ Kubernetes deployment complete")
        self.logger.info("━" * 80)

        return {
            'namespace': self.namespace,
            'vm_name': self.vm_name,
            'pvc_name': self.pvc_name,
            'vm_created': vm_created,
            'vm_started': self.auto_start,
        }

    def _validate_cluster(self):
        """Validate Kubernetes cluster is accessible."""
        self.logger.info("➡️ Validating Kubernetes cluster")

        try:
            version = self.core_api.get_api_resources()
            self.logger.info("✅ Cluster is accessible")
        except Exception as e:
            raise RuntimeError(f"Cannot access Kubernetes cluster: {e}")

        # Check for KubeVirt CRDs
        try:
            self.custom_api.get_api_resources(
                group='kubevirt.io',
                version='v1'
            )
            self.logger.info("✅ KubeVirt CRDs found")
        except ApiException:
            self.logger.warning("⚠️  KubeVirt CRDs not found - VM creation may fail")
            self.logger.warning("   Install KubeVirt: kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/v1.1.0/kubevirt-operator.yaml")

    def _ensure_namespace(self):
        """Create namespace if it doesn't exist."""
        self.logger.info(f"➡️ Ensuring namespace: {self.namespace}")

        try:
            self.core_api.read_namespace(self.namespace)
            self.logger.info(f"✅ Namespace exists: {self.namespace}")
        except ApiException as e:
            if e.status == 404:
                # Create namespace
                ns = client.V1Namespace(
                    metadata=client.V1ObjectMeta(name=self.namespace)
                )
                self.core_api.create_namespace(ns)
                self.logger.info(f"✅ Created namespace: {self.namespace}")
            else:
                raise

    def _create_pvc(self):
        """Create PersistentVolumeClaim for VM disk."""
        self.logger.info(f"➡️ Creating PVC: {self.pvc_name}")

        pvc = client.V1PersistentVolumeClaim(
            metadata=client.V1ObjectMeta(name=self.pvc_name),
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=['ReadWriteOnce'],
                storage_class_name=self.storage_class,
                resources=client.V1ResourceRequirements(
                    requests={'storage': self.pvc_size}
                )
            )
        )

        try:
            self.core_api.create_namespaced_persistent_volume_claim(
                namespace=self.namespace,
                body=pvc
            )
            self.logger.info(f"✅ Created PVC: {self.pvc_name}")
        except ApiException as e:
            if e.status == 409:
                self.logger.info(f"✅ PVC already exists: {self.pvc_name}")
            else:
                raise

    def _upload_image(self, qcow2_path: str):
        """Upload QCOW2 image to PVC using a temporary pod."""
        self.logger.info(f"➡️ Uploading image to PVC")

        # Create uploader pod
        uploader_name = f"uploader-{self.vm_name}"
        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(name=uploader_name),
            spec=client.V1PodSpec(
                restart_policy='Never',
                containers=[
                    client.V1Container(
                        name='uploader',
                        image='alpine',
                        command=['sleep', '3600'],
                        volume_mounts=[
                            client.V1VolumeMount(
                                name='disk',
                                mount_path='/disk'
                            )
                        ]
                    )
                ],
                volumes=[
                    client.V1Volume(
                        name='disk',
                        persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                            claim_name=self.pvc_name
                        )
                    )
                ]
            )
        )

        try:
            self.core_api.create_namespaced_pod(
                namespace=self.namespace,
                body=pod
            )
            self.logger.info(f"Created uploader pod: {uploader_name}")
        except ApiException as e:
            if e.status == 409:
                self.logger.info(f"Uploader pod already exists: {uploader_name}")
            else:
                raise

        # Wait for pod to be ready
        self.logger.info("Waiting for uploader pod to be ready...")
        for i in range(60):
            try:
                pod_status = self.core_api.read_namespaced_pod_status(
                    name=uploader_name,
                    namespace=self.namespace
                )
                if pod_status.status.phase == 'Running':
                    self.logger.info("✅ Uploader pod is ready")
                    break
            except ApiException:
                pass
            time.sleep(2)
        else:
            raise RuntimeError("Uploader pod did not become ready in time")

        # Copy QCOW2 to pod
        self.logger.info(f"Copying {Path(qcow2_path).name} to PVC (this may take a while)...")
        cmd = [
            'kubectl', 'cp',
            qcow2_path,
            f'{self.namespace}/{uploader_name}:/disk/disk.img'
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to upload image: {result.stderr}")

        self.logger.info("✅ Image uploaded to PVC")

        # Delete uploader pod
        try:
            self.core_api.delete_namespaced_pod(
                name=uploader_name,
                namespace=self.namespace
            )
            self.logger.info("Cleaned up uploader pod")
        except ApiException:
            pass

    def _create_vm(self) -> bool:
        """Create KubeVirt VirtualMachine resource."""
        self.logger.info(f"➡️ Creating VirtualMachine: {self.vm_name}")

        vm = {
            'apiVersion': 'kubevirt.io/v1',
            'kind': 'VirtualMachine',
            'metadata': {
                'name': self.vm_name,
                'namespace': self.namespace,
                'labels': {
                    'app': self.vm_name,
                    'hyper2kvm.io/migrated': 'true'
                }
            },
            'spec': {
                'running': False,  # Don't auto-start unless requested
                'template': {
                    'metadata': {
                        'labels': {
                            'kubevirt.io/vm': self.vm_name
                        }
                    },
                    'spec': {
                        'domain': {
                            'devices': {
                                'disks': [
                                    {
                                        'name': 'rootdisk',
                                        'disk': {
                                            'bus': 'virtio'
                                        }
                                    }
                                ],
                                'interfaces': [
                                    {
                                        'name': 'default',
                                        'masquerade': {}
                                    }
                                ]
                            },
                            'resources': {
                                'requests': {
                                    'memory': self.memory,
                                    'cpu': self.cpu_cores
                                }
                            }
                        },
                        'networks': [
                            {
                                'name': 'default',
                                'pod': {}
                            }
                        ],
                        'volumes': [
                            {
                                'name': 'rootdisk',
                                'persistentVolumeClaim': {
                                    'claimName': self.pvc_name
                                }
                            }
                        ]
                    }
                }
            }
        }

        try:
            self.custom_api.create_namespaced_custom_object(
                group='kubevirt.io',
                version='v1',
                namespace=self.namespace,
                plural='virtualmachines',
                body=vm
            )
            self.logger.info(f"✅ Created VirtualMachine: {self.vm_name}")
            return True
        except ApiException as e:
            if e.status == 409:
                self.logger.info(f"✅ VirtualMachine already exists: {self.vm_name}")
                return False
            else:
                raise

    def _start_vm(self):
        """Start the VirtualMachine."""
        self.logger.info(f"➡️ Starting VM: {self.vm_name}")

        # Patch VM to set running=true
        patch = {'spec': {'running': True}}
        try:
            self.custom_api.patch_namespaced_custom_object(
                group='kubevirt.io',
                version='v1',
                namespace=self.namespace,
                plural='virtualmachines',
                name=self.vm_name,
                body=patch
            )
            self.logger.info(f"✅ VM started: {self.vm_name}")
        except ApiException as e:
            self.logger.error(f"Failed to start VM: {e}")
            raise

    def _wait_for_vm(self, timeout=300):
        """Wait for VM to be ready."""
        self.logger.info(f"➡️ Waiting for VM to be ready (timeout: {timeout}s)")

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                vmi = self.custom_api.get_namespaced_custom_object(
                    group='kubevirt.io',
                    version='v1',
                    namespace=self.namespace,
                    plural='virtualmachineinstances',
                    name=self.vm_name
                )

                phase = vmi.get('status', {}).get('phase', '')
                if phase == 'Running':
                    # Check ready condition
                    conditions = vmi.get('status', {}).get('conditions', [])
                    for cond in conditions:
                        if cond.get('type') == 'Ready' and cond.get('status') == 'True':
                            ip = vmi.get('status', {}).get('interfaces', [{}])[0].get('ipAddress', 'N/A')
                            self.logger.info(f"✅ VM is ready!")
                            self.logger.info(f"   Phase: {phase}")
                            self.logger.info(f"   IP: {ip}")
                            return True

                self.logger.info(f"   VM phase: {phase}, waiting...")
                time.sleep(5)

            except ApiException as e:
                if e.status != 404:
                    raise
                # VMI not created yet, keep waiting
                time.sleep(5)

        self.logger.warning(f"⚠️  VM did not become ready within {timeout}s")
        return False


def deploy_to_kubernetes(logger, args, qcow2_path: str) -> Dict[str, Any]:
    """
    Deploy migrated VM to Kubernetes/k3s.

    Args:
        logger: Logger instance
        args: Parsed arguments
        qcow2_path: Path to the QCOW2 image

    Returns:
        Deployment details dictionary
    """
    deployer = KubernetesDeployer(logger, args)
    return deployer.deploy(qcow2_path)
