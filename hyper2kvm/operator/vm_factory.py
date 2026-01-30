"""
VMFactory for creating KubeVirt VirtualMachine resources with advanced features.

Supports:
- Eviction strategies (LiveMigrate, None, etc.)
- Multi-disk VMs
- Firmware configuration (BIOS, UEFI, UEFI Secure Boot)
- Advanced CPU topology (cores, sockets, threads)
- Resource requests and limits
- Multiple network interfaces
- Migration policy integration
"""

import logging
from typing import Dict, Any, List, Optional
from kubernetes import client

logger = logging.getLogger(__name__)

LABEL_MIGRATION_JOB = 'hyper2kvm.io/migration-job'


class VMFactory:
    """Factory for creating KubeVirt VirtualMachine resources."""

    def __init__(self, custom_api: client.CustomObjectsApi, metrics=None):
        """
        Initialize VMFactory.

        Args:
            custom_api: Kubernetes CustomObjectsApi client
            metrics: OperatorMetrics instance for recording VM creation
        """
        self.custom_api = custom_api
        self.metrics = metrics

    async def create_virtual_machine(
        self,
        namespace: str,
        job_name: str,
        pvc_name: str,
        create_vm_spec: Dict[str, Any]
    ) -> str:
        """
        Create KubeVirt VirtualMachine with advanced features.

        Args:
            namespace: Kubernetes namespace
            job_name: Migration job name (for labels)
            pvc_name: Primary PVC name for root disk
            create_vm_spec: VM creation specification from MigrationJob CRD

        Returns:
            VM name

        Raises:
            ApiException: If VM creation fails
        """
        vm_name = create_vm_spec.get('name', job_name)
        auto_start = create_vm_spec.get('autoStart', False)

        # Build VM spec
        vm = {
            'apiVersion': 'kubevirt.io/v1',
            'kind': 'VirtualMachine',
            'metadata': {
                'name': vm_name,
                'labels': {
                    LABEL_MIGRATION_JOB: job_name,
                    'kubevirt.io/vm': vm_name
                }
            },
            'spec': {
                'running': auto_start,
                'template': {
                    'metadata': {
                        'labels': {'kubevirt.io/vm': vm_name}
                    },
                    'spec': {
                        'domain': self._build_domain_spec(create_vm_spec, pvc_name),
                        'networks': self._build_networks_spec(create_vm_spec),
                        'volumes': self._build_volumes_spec(create_vm_spec, pvc_name)
                    }
                }
            }
        }

        # Add eviction strategy if specified
        eviction_strategy = create_vm_spec.get('evictionStrategy', 'LiveMigrate')
        if eviction_strategy and eviction_strategy != 'None':
            vm['spec']['template']['spec']['evictionStrategy'] = eviction_strategy

        try:
            self.custom_api.create_namespaced_custom_object(
                group='kubevirt.io',
                version='v1',
                namespace=namespace,
                plural='virtualmachines',
                body=vm
            )
            logger.info(f"✅ Created VirtualMachine: {vm_name} with evictionStrategy={eviction_strategy}")

            # Record metrics
            if self.metrics:
                self.metrics.record_vm_created(namespace, auto_start)

        except client.ApiException as e:
            if e.status == 409:
                logger.warning(f"VirtualMachine {vm_name} already exists")
            else:
                logger.error(f"Failed to create VirtualMachine {vm_name}: {e}")
                raise

        return vm_name

    def _build_domain_spec(self, create_vm_spec: Dict[str, Any], pvc_name: str) -> Dict[str, Any]:
        """Build domain specification with CPU, memory, firmware, devices."""
        domain = {
            'devices': {
                'disks': self._build_disks_spec(create_vm_spec, pvc_name),
                'interfaces': self._build_interfaces_spec(create_vm_spec)
            },
            'resources': self._build_resources_spec(create_vm_spec)
        }

        # Add firmware configuration
        firmware_spec = create_vm_spec.get('firmware')
        if firmware_spec:
            domain['firmware'] = self._build_firmware_spec(firmware_spec)

        # Add CPU configuration
        cpu_config = create_vm_spec.get('cpuConfig')
        if cpu_config:
            domain['cpu'] = self._build_cpu_spec(cpu_config)

        return domain

    def _build_disks_spec(self, create_vm_spec: Dict[str, Any], pvc_name: str) -> List[Dict[str, Any]]:
        """Build disks specification (root disk + additional disks)."""
        disks = [{
            'name': 'rootdisk',
            'disk': {'bus': 'virtio'},
            'bootOrder': 1
        }]

        # Add additional disks
        additional_disks = create_vm_spec.get('disks', [])
        for disk in additional_disks:
            disk_spec = {
                'name': disk['name'],
                'disk': {'bus': disk.get('bus', 'virtio')}
            }
            if 'bootOrder' in disk:
                disk_spec['bootOrder'] = disk['bootOrder']
            disks.append(disk_spec)

        return disks

    def _build_interfaces_spec(self, create_vm_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build network interfaces specification."""
        # Default interface
        network_type = create_vm_spec.get('networkType', 'masquerade')
        interfaces = [{
            'name': 'default',
            network_type: {}
        }]

        # Add additional interfaces
        additional_interfaces = create_vm_spec.get('interfaces', [])
        for iface in additional_interfaces:
            iface_spec = {
                'name': iface['name'],
                iface['type']: {}
            }
            if 'macAddress' in iface:
                iface_spec['macAddress'] = iface['macAddress']
            interfaces.append(iface_spec)

        return interfaces

    def _build_networks_spec(self, create_vm_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build networks specification."""
        networks = [{'name': 'default', 'pod': {}}]

        # Add additional networks
        additional_interfaces = create_vm_spec.get('interfaces', [])
        for iface in additional_interfaces:
            network_spec = {'name': iface['name']}
            if 'networkName' in iface:
                network_spec['multus'] = {'networkName': iface['networkName']}
            else:
                network_spec['pod'] = {}
            networks.append(network_spec)

        return networks

    def _build_volumes_spec(self, create_vm_spec: Dict[str, Any], pvc_name: str) -> List[Dict[str, Any]]:
        """Build volumes specification."""
        volumes = [{
            'name': 'rootdisk',
            'persistentVolumeClaim': {'claimName': pvc_name}
        }]

        # Add additional volumes
        additional_disks = create_vm_spec.get('disks', [])
        for disk in additional_disks:
            volumes.append({
                'name': disk['name'],
                'persistentVolumeClaim': {'claimName': disk['pvcName']}
            })

        return volumes

    def _build_resources_spec(self, create_vm_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Build resource requests and limits."""
        # Start with basic cpu/memory from createVM spec
        cpu = create_vm_spec.get('cpu', '2')
        memory = create_vm_spec.get('memory', '2Gi')

        resources = {
            'requests': {
                'memory': memory,
                'cpu': cpu
            }
        }

        # Override with advanced resources if provided
        advanced_resources = create_vm_spec.get('resources')
        if advanced_resources:
            if 'requests' in advanced_resources:
                resources['requests'].update(advanced_resources['requests'])
            if 'limits' in advanced_resources:
                resources['limits'] = advanced_resources['limits']

        return resources

    def _build_firmware_spec(self, firmware_config: Dict[str, Any]) -> Dict[str, Any]:
        """Build firmware specification."""
        firmware = {}
        bootloader = firmware_config.get('bootloader', 'bios')

        if bootloader == 'bios':
            firmware['bootloader'] = {'bios': {}}
        elif bootloader in ['uefi', 'uefi-secure']:
            efi_spec = {}
            if firmware_config.get('secureBoot', False) or bootloader == 'uefi-secure':
                efi_spec['secureBoot'] = True
            firmware['bootloader'] = {'efi': efi_spec}

        return firmware

    def _build_cpu_spec(self, cpu_config: Dict[str, Any]) -> Dict[str, Any]:
        """Build CPU topology and features specification."""
        cpu = {}

        # CPU topology
        cores = cpu_config.get('cores', 1)
        sockets = cpu_config.get('sockets', 1)
        threads = cpu_config.get('threads', 1)

        cpu['cores'] = cores
        cpu['sockets'] = sockets
        cpu['threads'] = threads

        # Dedicated CPU placement
        if cpu_config.get('dedicatedCpuPlacement', False):
            cpu['dedicatedCpuPlacement'] = True

        # CPU features
        features = cpu_config.get('features', [])
        if features:
            cpu['features'] = [{'name': feature, 'policy': 'require'} for feature in features]

        return cpu

    async def apply_migration_policy(
        self,
        namespace: str,
        vm_name: str,
        policy_name: str
    ):
        """
        Apply migration policy to a VM by adding annotations.

        Args:
            namespace: Kubernetes namespace
            vm_name: VM name
            policy_name: MigrationPolicy CR name
        """
        try:
            # Patch VM with policy annotation
            patch = {
                'metadata': {
                    'annotations': {
                        'hyper2kvm.io/migration-policy': policy_name
                    }
                }
            }

            self.custom_api.patch_namespaced_custom_object(
                group='kubevirt.io',
                version='v1',
                namespace=namespace,
                plural='virtualmachines',
                name=vm_name,
                body=patch
            )
            logger.info(f"Applied migration policy {policy_name} to VM {vm_name}")

        except client.ApiException as e:
            logger.error(f"Failed to apply migration policy to VM {vm_name}: {e}")
            raise
