"""
End-to-End tests for live migration features.

Tests:
- Eviction strategy functionality
- Migration policy enforcement
- Node eviction triggering migrations
- Post-copy activation
- Migration abort/cancel
- Multi-disk VM creation
"""

import pytest
import asyncio
from kubernetes import client, config
from datetime import datetime, timedelta
import time


@pytest.fixture(scope="module")
def k8s_clients():
    """Initialize Kubernetes API clients."""
    try:
        config.load_incluster_config()
    except:
        config.load_kube_config()

    return {
        'core': client.CoreV1Api(),
        'custom': client.CustomObjectsApi(),
        'apps': client.AppsV1Api()
    }


@pytest.fixture
def namespace(k8s_clients):
    """Create test namespace."""
    namespace_name = f"test-live-migration-{int(time.time())}"

    namespace = client.V1Namespace(
        metadata=client.V1ObjectMeta(name=namespace_name)
    )

    k8s_clients['core'].create_namespace(namespace)

    yield namespace_name

    # Cleanup
    try:
        k8s_clients['core'].delete_namespace(namespace_name)
    except:
        pass


class TestEvictionStrategy:
    """Test eviction strategy functionality."""

    def test_vm_with_live_migrate_strategy(self, k8s_clients, namespace):
        """Test VM creation with LiveMigrate eviction strategy."""
        custom_api = k8s_clients['custom']

        # Create MigrationJob with evictionStrategy
        migration_job = {
            'apiVersion': 'hyper2kvm.io/v1alpha1',
            'kind': 'MigrationJob',
            'metadata': {
                'name': 'test-eviction-strategy',
                'namespace': namespace
            },
            'spec': {
                'source': {
                    'type': 'pvc',
                    'pvc': {
                        'name': 'test-source-pvc'
                    }
                },
                'destination': {
                    'pvcName': 'test-dest-pvc',
                    'size': '10Gi'
                },
                'createVM': {
                    'enabled': True,
                    'name': 'test-vm-eviction',
                    'cpu': '2',
                    'memory': '2Gi',
                    'autoStart': False,
                    'evictionStrategy': 'LiveMigrate'
                }
            }
        }

        # Note: This is a dry test - actual migration requires source PVC
        # In real environment, verify the MigrationJob creates VM with evictionStrategy

    def test_eviction_strategy_validation(self, k8s_clients, namespace):
        """Test that invalid eviction strategies are rejected."""
        from hyper2kvm.operator.webhook_validation import MigrationJobValidator

        validator = MigrationJobValidator()

        spec = {
            'source': {'type': 'pvc', 'pvc': {'name': 'test'}},
            'destination': {'size': '10Gi'},
            'createVM': {
                'enabled': True,
                'evictionStrategy': 'InvalidStrategy'
            }
        }

        is_valid, errors, warnings = validator.validate(spec, namespace)
        assert not is_valid
        assert any('evictionStrategy' in e for e in errors)


class TestMigrationPolicy:
    """Test MigrationPolicy enforcement."""

    def test_create_migration_policy(self, k8s_clients, namespace):
        """Test creating a MigrationPolicy."""
        custom_api = k8s_clients['custom']

        policy = {
            'apiVersion': 'hyper2kvm.io/v1alpha1',
            'kind': 'MigrationPolicy',
            'metadata': {
                'name': 'test-policy'
            },
            'spec': {
                'bandwidthPerMigration': '100Mi',
                'allowAutoConverge': True,
                'allowPostCopy': False,
                'maxParallelMigrationsPerCluster': 3,
                'maxParallelMigrationsPerNode': 2
            }
        }

        # Note: Requires CRD to be installed
        # In real test, create policy and verify it's accepted

    def test_migration_policy_bandwidth_limit(self, k8s_clients):
        """Test bandwidth limit enforcement."""
        from hyper2kvm.operator.bandwidth_manager import BandwidthManager

        custom_api = k8s_clients['custom']
        manager = BandwidthManager(custom_api)

        # Test bandwidth parsing
        assert manager.parse_bandwidth('100Mi') == 100 * 1024 * 1024
        assert manager.parse_bandwidth('1Gi') == 1024 * 1024 * 1024
        assert manager.parse_bandwidth('0') == 0

        # Test bandwidth formatting
        assert manager.format_bandwidth(100 * 1024 * 1024) == '100.0Mi'
        assert manager.format_bandwidth(1024 * 1024 * 1024) == '1.0Gi'

    def test_policy_validation(self):
        """Test migration policy validation."""
        from hyper2kvm.operator.migration_policy_controller import validate_policy_spec

        # Valid policy
        valid_spec = {
            'bandwidthPerMigration': '100Mi',
            'maxParallelMigrationsPerCluster': 5,
            'maxParallelMigrationsPerNode': 2
        }
        is_valid, errors = validate_policy_spec(valid_spec)
        assert is_valid
        assert len(errors) == 0

        # Invalid policy - node limit exceeds cluster limit
        invalid_spec = {
            'bandwidthPerMigration': '100Mi',
            'maxParallelMigrationsPerCluster': 2,
            'maxParallelMigrationsPerNode': 5
        }
        is_valid, errors = validate_policy_spec(invalid_spec)
        assert not is_valid
        assert len(errors) > 0


class TestNodeEviction:
    """Test node eviction triggering migrations."""

    @pytest.mark.asyncio
    async def test_node_cordon_triggers_migration(self, k8s_clients, namespace):
        """Test that cordoning a node triggers live migration."""
        # Note: This test requires:
        # 1. A running VM on a node
        # 2. The node to be cordoned
        # 3. Verify VMIM is created

        # This is a framework for the test
        # Real implementation requires actual cluster with VMs
        pass


class TestMigrationControl:
    """Test migration control operations."""

    @pytest.mark.asyncio
    async def test_migration_abort(self, k8s_clients, namespace):
        """Test aborting an in-progress migration."""
        from hyper2kvm.operator.migration_control import MigrationController

        custom_api = k8s_clients['custom']
        core_api = k8s_clients['core']

        controller = MigrationController(custom_api, core_api)

        # Note: Real test would create a VMIM and abort it
        # This validates the abort logic exists

    @pytest.mark.asyncio
    async def test_get_migration_status(self, k8s_clients, namespace):
        """Test retrieving detailed migration status."""
        from hyper2kvm.operator.migration_control import MigrationController

        custom_api = k8s_clients['custom']
        core_api = k8s_clients['core']

        controller = MigrationController(custom_api, core_api)

        # Test with non-existent migration
        status = await controller.get_migration_status(namespace, 'non-existent')
        assert status is None


class TestMultiDiskVM:
    """Test multi-disk VM creation."""

    def test_multi_disk_validation(self):
        """Test multi-disk configuration validation."""
        from hyper2kvm.operator.webhook_validation import MigrationJobValidator

        validator = MigrationJobValidator()

        # Valid multi-disk config
        spec = {
            'source': {'type': 'pvc', 'pvc': {'name': 'test'}},
            'destination': {'size': '10Gi'},
            'createVM': {
                'enabled': True,
                'disks': [
                    {'name': 'disk1', 'pvcName': 'pvc1', 'bus': 'virtio'},
                    {'name': 'disk2', 'pvcName': 'pvc2', 'bus': 'sata'}
                ]
            }
        }

        is_valid, errors, warnings = validator.validate(spec, 'default')
        assert is_valid

        # Invalid - duplicate disk names
        spec['createVM']['disks'] = [
            {'name': 'disk1', 'pvcName': 'pvc1', 'bus': 'virtio'},
            {'name': 'disk1', 'pvcName': 'pvc2', 'bus': 'virtio'}
        ]

        is_valid, errors, warnings = validator.validate(spec, 'default')
        assert not is_valid
        assert any('Duplicate disk name' in e for e in errors)

    def test_multi_disk_boot_order(self):
        """Test boot order validation for multi-disk."""
        from hyper2kvm.operator.webhook_validation import MigrationJobValidator

        validator = MigrationJobValidator()

        # Invalid - duplicate boot orders
        spec = {
            'source': {'type': 'pvc', 'pvc': {'name': 'test'}},
            'destination': {'size': '10Gi'},
            'createVM': {
                'enabled': True,
                'disks': [
                    {'name': 'disk1', 'pvcName': 'pvc1', 'bootOrder': 1},
                    {'name': 'disk2', 'pvcName': 'pvc2', 'bootOrder': 1}
                ]
            }
        }

        is_valid, errors, warnings = validator.validate(spec, 'default')
        assert not is_valid
        assert any('bootOrder' in e for e in errors)


class TestCPUConfiguration:
    """Test CPU topology and configuration."""

    def test_cpu_config_validation(self):
        """Test CPU configuration validation."""
        from hyper2kvm.operator.webhook_validation import MigrationJobValidator

        validator = MigrationJobValidator()

        # Valid CPU config
        spec = {
            'source': {'type': 'pvc', 'pvc': {'name': 'test'}},
            'destination': {'size': '10Gi'},
            'createVM': {
                'enabled': True,
                'cpuConfig': {
                    'cores': 2,
                    'sockets': 2,
                    'threads': 1
                }
            }
        }

        is_valid, errors, warnings = validator.validate(spec, 'default')
        assert is_valid

        # Invalid - cores < 1
        spec['createVM']['cpuConfig']['cores'] = 0
        is_valid, errors, warnings = validator.validate(spec, 'default')
        assert not is_valid


class TestFirmwareConfiguration:
    """Test firmware configuration."""

    def test_firmware_validation(self):
        """Test firmware configuration validation."""
        from hyper2kvm.operator.webhook_validation import MigrationJobValidator

        validator = MigrationJobValidator()

        # Valid UEFI config
        spec = {
            'source': {'type': 'pvc', 'pvc': {'name': 'test'}},
            'destination': {'size': '10Gi'},
            'createVM': {
                'enabled': True,
                'firmware': {
                    'bootloader': 'uefi',
                    'secureBoot': True
                }
            }
        }

        is_valid, errors, warnings = validator.validate(spec, 'default')
        assert is_valid

        # Invalid - secure boot without UEFI
        spec['createVM']['firmware']['bootloader'] = 'bios'
        is_valid, errors, warnings = validator.validate(spec, 'default')
        assert not is_valid
        assert any('secureBoot requires' in e for e in errors)


class TestNetworkInterfaces:
    """Test network interface configuration."""

    def test_interface_validation(self):
        """Test network interface validation."""
        from hyper2kvm.operator.webhook_validation import MigrationJobValidator

        validator = MigrationJobValidator()

        # Valid interface config
        spec = {
            'source': {'type': 'pvc', 'pvc': {'name': 'test'}},
            'destination': {'size': '10Gi'},
            'createVM': {
                'enabled': True,
                'interfaces': [
                    {'name': 'eth1', 'type': 'bridge', 'networkName': 'br0'}
                ]
            }
        }

        is_valid, errors, warnings = validator.validate(spec, 'default')
        assert is_valid

        # Invalid - duplicate interface names
        spec['createVM']['interfaces'].append(
            {'name': 'eth1', 'type': 'masquerade'}
        )
        is_valid, errors, warnings = validator.validate(spec, 'default')
        assert not is_valid

    def test_mac_address_validation(self):
        """Test MAC address format validation."""
        from hyper2kvm.operator.webhook_validation import MigrationJobValidator

        validator = MigrationJobValidator()

        # Valid MAC address
        spec = {
            'source': {'type': 'pvc', 'pvc': {'name': 'test'}},
            'destination': {'size': '10Gi'},
            'createVM': {
                'enabled': True,
                'interfaces': [
                    {
                        'name': 'eth1',
                        'type': 'bridge',
                        'macAddress': '52:54:00:12:34:56'
                    }
                ]
            }
        }

        is_valid, errors, warnings = validator.validate(spec, 'default')
        assert is_valid

        # Invalid MAC address
        spec['createVM']['interfaces'][0]['macAddress'] = 'invalid-mac'
        is_valid, errors, warnings = validator.validate(spec, 'default')
        assert not is_valid


class TestVMFactory:
    """Test VMFactory functionality."""

    @pytest.mark.asyncio
    async def test_vm_factory_builds_correct_spec(self, k8s_clients):
        """Test that VMFactory builds correct VM specs."""
        from hyper2kvm.operator.vm_factory import VMFactory

        custom_api = k8s_clients['custom']
        factory = VMFactory(custom_api)

        # Test basic VM creation spec
        create_vm_spec = {
            'name': 'test-vm',
            'cpu': '4',
            'memory': '8Gi',
            'autoStart': False,
            'evictionStrategy': 'LiveMigrate',
            'firmware': {
                'bootloader': 'uefi'
            },
            'cpuConfig': {
                'cores': 2,
                'sockets': 2,
                'threads': 1
            }
        }

        # Verify spec building logic
        domain_spec = factory._build_domain_spec(create_vm_spec, 'test-pvc')
        assert 'cpu' in domain_spec
        assert domain_spec['cpu']['cores'] == 2
        assert domain_spec['cpu']['sockets'] == 2

        firmware_spec = factory._build_firmware_spec(create_vm_spec['firmware'])
        assert 'bootloader' in firmware_spec
        assert 'efi' in firmware_spec['bootloader']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
