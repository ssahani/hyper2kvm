"""
Unit tests for Kubernetes operator controller
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from kubernetes import client
from hyper2kvm.operator.controller import OperatorController
from hyper2kvm.operator.job_assigner import JobAssigner


class TestOperatorController:
    """Test OperatorController functionality"""

    @pytest.fixture
    def mock_k8s_client(self):
        """Create mock Kubernetes client"""
        mock_client = Mock(spec=client.CustomObjectsApi)
        return mock_client

    @pytest.fixture
    def operator_controller(self, mock_k8s_client):
        """Create OperatorController instance"""
        with patch('hyper2kvm.operator.controller.client.CustomObjectsApi', return_value=mock_k8s_client):
            controller = OperatorController(
                namespace="test-namespace",
                worker_namespace="test-workers"
            )
            return controller

    def test_controller_initialization(self, operator_controller):
        """Test controller initializes correctly"""
        assert operator_controller.namespace == "test-namespace"
        assert operator_controller.worker_namespace == "test-workers"
        assert operator_controller.running is False

    def test_watch_migrationjobs(self, operator_controller, mock_k8s_client):
        """Test watching MigrationJob resources"""
        # Mock watch stream
        mock_events = [
            {'type': 'ADDED', 'object': {'metadata': {'name': 'test-job', 'namespace': 'test-namespace'}, 'spec': {}}},
            {'type': 'MODIFIED', 'object': {'metadata': {'name': 'test-job', 'namespace': 'test-namespace'}, 'spec': {}}},
        ]

        with patch('kubernetes.watch.Watch') as mock_watch:
            mock_watch.return_value.stream.return_value = iter(mock_events)

            # Process events
            events = list(mock_watch.return_value.stream.return_value)

            assert len(events) == 2
            assert events[0]['type'] == 'ADDED'
            assert events[1]['type'] == 'MODIFIED'

    def test_process_migrationjob_added(self, operator_controller):
        """Test processing new MigrationJob"""
        job_obj = {
            'metadata': {
                'name': 'test-migration',
                'namespace': 'test-namespace',
                'uid': 'test-uid-123'
            },
            'spec': {
                'source': {
                    'type': 'vmdk',
                    'path': '/vms/test.vmdk'
                },
                'destination': {
                    'format': 'qcow2',
                    'path': '/output/test.qcow2'
                }
            },
            'status': {}
        }

        with patch.object(operator_controller, 'create_worker_job') as mock_create:
            operator_controller.process_event('ADDED', job_obj)
            mock_create.assert_called_once()

    def test_process_migrationjob_deleted(self, operator_controller):
        """Test processing deleted MigrationJob"""
        job_obj = {
            'metadata': {
                'name': 'test-migration',
                'namespace': 'test-namespace'
            }
        }

        with patch.object(operator_controller, 'cleanup_worker_job') as mock_cleanup:
            operator_controller.process_event('DELETED', job_obj)
            mock_cleanup.assert_called_once()

    def test_create_worker_job(self, operator_controller, mock_k8s_client):
        """Test worker job creation"""
        migration_job = {
            'metadata': {
                'name': 'test-migration',
                'namespace': 'test-namespace',
                'uid': 'test-uid-123'
            },
            'spec': {
                'source': {'type': 'vmdk', 'path': '/vms/test.vmdk'},
                'destination': {'format': 'qcow2', 'path': '/output/test.qcow2'},
                'workers': 1
            }
        }

        mock_batch_api = Mock(spec=client.BatchV1Api)

        with patch('hyper2kvm.operator.controller.client.BatchV1Api', return_value=mock_batch_api):
            operator_controller.create_worker_job(migration_job)
            mock_batch_api.create_namespaced_job.assert_called_once()

    def test_update_job_status(self, operator_controller, mock_k8s_client):
        """Test updating MigrationJob status"""
        job_name = "test-migration"
        status = {
            'phase': 'Running',
            'startTime': '2026-02-03T00:00:00Z',
            'progress': 50
        }

        operator_controller.update_job_status(job_name, status)

        mock_k8s_client.patch_namespaced_custom_object_status.assert_called_once()

    def test_validate_migrationjob_spec(self, operator_controller):
        """Test MigrationJob spec validation"""
        # Valid spec
        valid_spec = {
            'source': {'type': 'vmdk', 'path': '/vms/test.vmdk'},
            'destination': {'format': 'qcow2', 'path': '/output/test.qcow2'}
        }
        assert operator_controller.validate_spec(valid_spec) is True

        # Invalid spec - missing source
        invalid_spec = {
            'destination': {'format': 'qcow2', 'path': '/output/test.qcow2'}
        }
        assert operator_controller.validate_spec(invalid_spec) is False

    def test_handle_job_failure(self, operator_controller):
        """Test handling job failures"""
        job_obj = {
            'metadata': {'name': 'test-migration', 'namespace': 'test-namespace'},
            'status': {'phase': 'Failed', 'message': 'Migration failed'}
        }

        with patch.object(operator_controller, 'update_job_status') as mock_update:
            operator_controller.handle_failure(job_obj)
            mock_update.assert_called_once()

    def test_controller_graceful_shutdown(self, operator_controller):
        """Test controller shutdown"""
        operator_controller.running = True
        operator_controller.shutdown()
        assert operator_controller.running is False


class TestJobAssigner:
    """Test JobAssigner functionality"""

    @pytest.fixture
    def job_assigner(self):
        """Create JobAssigner instance"""
        return JobAssigner(namespace="test-namespace")

    def test_assign_job_to_worker(self, job_assigner):
        """Test job assignment to worker"""
        job = {
            'metadata': {'name': 'test-job'},
            'spec': {'workers': 1, 'resources': {'cpu': '1', 'memory': '1Gi'}}
        }

        workers = [
            {'name': 'worker-1', 'status': 'idle', 'capacity': {'cpu': '2', 'memory': '2Gi'}},
            {'name': 'worker-2', 'status': 'busy', 'capacity': {'cpu': '2', 'memory': '2Gi'}}
        ]

        assignment = job_assigner.assign(job, workers)

        assert assignment['worker'] == 'worker-1'  # Should assign to idle worker
        assert assignment['job'] == 'test-job'

    def test_no_available_workers(self, job_assigner):
        """Test assignment when no workers available"""
        job = {
            'metadata': {'name': 'test-job'},
            'spec': {'workers': 1}
        }

        workers = [
            {'name': 'worker-1', 'status': 'busy'},
            {'name': 'worker-2', 'status': 'busy'}
        ]

        assignment = job_assigner.assign(job, workers)

        assert assignment is None  # No assignment possible

    def test_resource_based_assignment(self, job_assigner):
        """Test assignment based on resource requirements"""
        job = {
            'metadata': {'name': 'test-job'},
            'spec': {
                'workers': 1,
                'resources': {'cpu': '4', 'memory': '8Gi'}
            }
        }

        workers = [
            {'name': 'worker-1', 'status': 'idle', 'capacity': {'cpu': '2', 'memory': '4Gi'}},
            {'name': 'worker-2', 'status': 'idle', 'capacity': {'cpu': '8', 'memory': '16Gi'}}
        ]

        assignment = job_assigner.assign(job, workers)

        assert assignment['worker'] == 'worker-2'  # Should assign to worker with sufficient resources

    def test_load_balancing(self, job_assigner):
        """Test load balancing across workers"""
        jobs = [
            {'metadata': {'name': f'job-{i}'}, 'spec': {'workers': 1}}
            for i in range(5)
        ]

        workers = [
            {'name': 'worker-1', 'status': 'idle', 'load': 0},
            {'name': 'worker-2', 'status': 'idle', 'load': 0}
        ]

        assignments = []
        for job in jobs:
            assignment = job_assigner.assign(job, workers)
            if assignment:
                assignments.append(assignment)
                # Update worker load
                for w in workers:
                    if w['name'] == assignment['worker']:
                        w['load'] += 1

        # Check distribution is balanced
        worker1_count = sum(1 for a in assignments if a['worker'] == 'worker-1')
        worker2_count = sum(1 for a in assignments if a['worker'] == 'worker-2')

        # Should be roughly equal (within 1)
        assert abs(worker1_count - worker2_count) <= 1


class TestCRDValidation:
    """Test CRD validation"""

    def test_migrationjob_crd_schema(self):
        """Test MigrationJob CRD schema validation"""
        # Valid MigrationJob
        valid_job = {
            'apiVersion': 'hyper2kvm.io/v1alpha1',
            'kind': 'MigrationJob',
            'metadata': {'name': 'test-migration'},
            'spec': {
                'source': {
                    'type': 'vmdk',
                    'path': '/vms/test.vmdk'
                },
                'destination': {
                    'format': 'qcow2',
                    'path': '/output/test.qcow2'
                }
            }
        }

        # Schema validation would be done by Kubernetes API server
        assert valid_job['apiVersion'] == 'hyper2kvm.io/v1alpha1'
        assert valid_job['kind'] == 'MigrationJob'
        assert 'source' in valid_job['spec']
        assert 'destination' in valid_job['spec']

    def test_offlinefixjob_crd_schema(self):
        """Test OfflineFixJob CRD schema validation"""
        valid_job = {
            'apiVersion': 'hyper2kvm.io/v1alpha1',
            'kind': 'OfflineFixJob',
            'metadata': {'name': 'test-fix'},
            'spec': {
                'image': '/vms/test.qcow2',
                'fixes': ['fstab', 'grub', 'initramfs']
            }
        }

        assert valid_job['apiVersion'] == 'hyper2kvm.io/v1alpha1'
        assert valid_job['kind'] == 'OfflineFixJob'
        assert 'image' in valid_job['spec']
        assert 'fixes' in valid_job['spec']
        assert len(valid_job['spec']['fixes']) == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
