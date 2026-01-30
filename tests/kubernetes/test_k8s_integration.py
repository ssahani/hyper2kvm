"""
Integration tests for Kubernetes operator
Requires a running Kubernetes cluster with operator deployed
"""

import pytest
import time
import subprocess
from kubernetes import client, config
from kubernetes.client.rest import ApiException


class TestKubernetesIntegration:
    """Integration tests for Kubernetes operator"""

    @pytest.fixture(scope="class", autouse=True)
    def setup_k8s(self):
        """Setup Kubernetes client"""
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()

        self.api = client.CustomObjectsApi()
        self.core_api = client.CoreV1Api()
        self.batch_api = client.BatchV1Api()

        self.group = "hyper2kvm.io"
        self.version = "v1alpha1"
        self.namespace = "hyper2kvm-test"
        self.plural = "migrationjobs"

        # Create test namespace
        try:
            self.core_api.create_namespace(
                client.V1Namespace(metadata=client.V1ObjectMeta(name=self.namespace))
            )
        except ApiException as e:
            if e.status != 409:  # Already exists
                raise

        yield

        # Cleanup
        try:
            self.core_api.delete_namespace(self.namespace)
        except:
            pass

    def test_create_migrationjob(self):
        """Test creating a MigrationJob resource"""
        migration_job = {
            "apiVersion": f"{self.group}/{self.version}",
            "kind": "MigrationJob",
            "metadata": {
                "name": "test-migration",
                "namespace": self.namespace
            },
            "spec": {
                "source": {
                    "type": "vmdk",
                    "path": "/vms/test.vmdk"
                },
                "destination": {
                    "format": "qcow2",
                    "path": "/output/test.qcow2"
                }
            }
        }

        # Create resource
        response = self.api.create_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=self.namespace,
            plural=self.plural,
            body=migration_job
        )

        assert response['metadata']['name'] == 'test-migration'
        assert response['spec']['source']['type'] == 'vmdk'

        # Cleanup
        self.api.delete_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=self.namespace,
            plural=self.plural,
            name='test-migration'
        )

    def test_migrationjob_lifecycle(self):
        """Test complete MigrationJob lifecycle"""
        job_name = "test-lifecycle"

        migration_job = {
            "apiVersion": f"{self.group}/{self.version}",
            "kind": "MigrationJob",
            "metadata": {
                "name": job_name,
                "namespace": self.namespace
            },
            "spec": {
                "source": {
                    "type": "vmdk",
                    "path": "/vms/test.vmdk"
                },
                "destination": {
                    "format": "qcow2",
                    "path": "/output/test.qcow2"
                }
            }
        }

        # 1. Create
        response = self.api.create_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=self.namespace,
            plural=self.plural,
            body=migration_job
        )
        assert response['metadata']['name'] == job_name

        # 2. Wait for worker job creation
        time.sleep(5)

        # Check if worker job was created
        jobs = self.batch_api.list_namespaced_job(namespace=self.namespace)
        worker_jobs = [j for j in jobs.items if job_name in j.metadata.name]
        assert len(worker_jobs) > 0, "Worker job should be created"

        # 3. Check status
        response = self.api.get_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=self.namespace,
            plural=self.plural,
            name=job_name
        )

        # Status should be updated
        assert 'status' in response

        # 4. Delete
        self.api.delete_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=self.namespace,
            plural=self.plural,
            name=job_name
        )

    def test_multiple_migrationjobs(self):
        """Test creating multiple MigrationJobs concurrently"""
        job_names = [f"test-multi-{i}" for i in range(3)]

        # Create multiple jobs
        for job_name in job_names:
            migration_job = {
                "apiVersion": f"{self.group}/{self.version}",
                "kind": "MigrationJob",
                "metadata": {
                    "name": job_name,
                    "namespace": self.namespace
                },
                "spec": {
                    "source": {
                        "type": "vmdk",
                        "path": f"/vms/test-{job_name}.vmdk"
                    },
                    "destination": {
                        "format": "qcow2",
                        "path": f"/output/test-{job_name}.qcow2"
                    }
                }
            }

            self.api.create_namespaced_custom_object(
                group=self.group,
                version=self.version,
                namespace=self.namespace,
                plural=self.plural,
                body=migration_job
            )

        # Wait for processing
        time.sleep(5)

        # Check all jobs exist
        jobs = self.api.list_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=self.namespace,
            plural=self.plural
        )

        job_list = [j['metadata']['name'] for j in jobs['items']]
        for job_name in job_names:
            assert job_name in job_list

        # Cleanup
        for job_name in job_names:
            try:
                self.api.delete_namespaced_custom_object(
                    group=self.group,
                    version=self.version,
                    namespace=self.namespace,
                    plural=self.plural,
                    name=job_name
                )
            except:
                pass

    def test_job_with_resources(self):
        """Test MigrationJob with resource requests/limits"""
        job_name = "test-resources"

        migration_job = {
            "apiVersion": f"{self.group}/{self.version}",
            "kind": "MigrationJob",
            "metadata": {
                "name": job_name,
                "namespace": self.namespace
            },
            "spec": {
                "source": {
                    "type": "vmdk",
                    "path": "/vms/test.vmdk"
                },
                "destination": {
                    "format": "qcow2",
                    "path": "/output/test.qcow2"
                },
                "resources": {
                    "requests": {
                        "cpu": "500m",
                        "memory": "1Gi"
                    },
                    "limits": {
                        "cpu": "1",
                        "memory": "2Gi"
                    }
                }
            }
        }

        response = self.api.create_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=self.namespace,
            plural=self.plural,
            body=migration_job
        )

        assert response['spec']['resources']['requests']['cpu'] == '500m'

        # Cleanup
        self.api.delete_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=self.namespace,
            plural=self.plural,
            name=job_name
        )

    def test_offlinefixjob_creation(self):
        """Test creating an OfflineFixJob resource"""
        job_name = "test-fix"

        fix_job = {
            "apiVersion": f"{self.group}/{self.version}",
            "kind": "OfflineFixJob",
            "metadata": {
                "name": job_name,
                "namespace": self.namespace
            },
            "spec": {
                "image": "/vms/test.qcow2",
                "fixes": ["fstab", "grub", "initramfs"]
            }
        }

        response = self.api.create_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=self.namespace,
            plural="offlinefixjobs",
            body=fix_job
        )

        assert response['metadata']['name'] == job_name
        assert len(response['spec']['fixes']) == 3

        # Cleanup
        self.api.delete_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=self.namespace,
            plural="offlinefixjobs",
            name=job_name
        )

    def test_job_dependency(self):
        """Test job dependency using dependsOn"""
        job1_name = "test-dep-1"
        job2_name = "test-dep-2"

        # Create first job
        job1 = {
            "apiVersion": f"{self.group}/{self.version}",
            "kind": "MigrationJob",
            "metadata": {
                "name": job1_name,
                "namespace": self.namespace
            },
            "spec": {
                "source": {"type": "vmdk", "path": "/vms/test1.vmdk"},
                "destination": {"format": "qcow2", "path": "/output/test1.qcow2"}
            }
        }

        self.api.create_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=self.namespace,
            plural=self.plural,
            body=job1
        )

        # Create second job with dependency
        job2 = {
            "apiVersion": f"{self.group}/{self.version}",
            "kind": "MigrationJob",
            "metadata": {
                "name": job2_name,
                "namespace": self.namespace
            },
            "spec": {
                "source": {"type": "vmdk", "path": "/vms/test2.vmdk"},
                "destination": {"format": "qcow2", "path": "/output/test2.qcow2"},
                "dependsOn": [job1_name]
            }
        }

        self.api.create_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=self.namespace,
            plural=self.plural,
            body=job2
        )

        # Job2 should wait for job1
        time.sleep(2)

        job2_status = self.api.get_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=self.namespace,
            plural=self.plural,
            name=job2_name
        )

        # Should be waiting or pending
        if 'status' in job2_status:
            assert job2_status['status'].get('phase') in ['Pending', 'Waiting', None]

        # Cleanup
        for name in [job1_name, job2_name]:
            try:
                self.api.delete_namespaced_custom_object(
                    group=self.group,
                    version=self.version,
                    namespace=self.namespace,
                    plural=self.plural,
                    name=name
                )
            except:
                pass


@pytest.mark.integration
class TestOperatorMetrics:
    """Test operator metrics collection"""

    @pytest.fixture(scope="class", autouse=True)
    def setup_k8s(self):
        """Setup Kubernetes client"""
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()

        self.core_api = client.CoreV1Api()
        self.namespace = "hyper2kvm-system"

        yield

    def test_metrics_endpoint(self):
        """Test metrics endpoint is accessible"""
        # Get operator pod
        pods = self.core_api.list_namespaced_pod(
            namespace=self.namespace,
            label_selector="app=hyper2kvm-operator"
        )

        if len(pods.items) == 0:
            pytest.skip("Operator pod not found")

        pod_name = pods.items[0].metadata.name

        # Check if metrics port is exposed
        pod = self.core_api.read_namespaced_pod(
            name=pod_name,
            namespace=self.namespace
        )

        # Find metrics port
        metrics_port = None
        for container in pod.spec.containers:
            for port in (container.ports or []):
                if port.name == "metrics":
                    metrics_port = port.container_port
                    break

        assert metrics_port is not None, "Metrics port should be exposed"

    def test_health_endpoints(self):
        """Test health and readiness endpoints"""
        pods = self.core_api.list_namespaced_pod(
            namespace=self.namespace,
            label_selector="app=hyper2kvm-operator"
        )

        if len(pods.items) == 0:
            pytest.skip("Operator pod not found")

        pod = pods.items[0]

        # Check liveness probe
        assert pod.spec.containers[0].liveness_probe is not None

        # Check readiness probe
        assert pod.spec.containers[0].readiness_probe is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-m', 'integration'])
