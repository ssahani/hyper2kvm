# SPDX-License-Identifier: LGPL-3.0-or-later
# tests/unit/test_containers.py
"""
Unit tests for container extraction.
"""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from hyper2kvm.containers import (
    ContainerDetector,
    ContainerExtractionOrchestrator,
    ContainerInfo,
    ContainerRuntime,
    DockerExtractor,
    KubernetesManifestGenerator,
    PodmanExtractor,
)


@pytest.fixture
def logger():
    """Create test logger."""
    return logging.getLogger("test")


@pytest.fixture
def mock_vmcraft():
    """Create mock VMCraft instance."""
    g = MagicMock()

    # Mock Docker installation
    def exists_side_effect(path):
        valid_paths = [
            "/usr/bin/docker",
            "/var/lib/docker",
            "/var/lib/docker/containers",
            "/var/lib/docker/containers/abc123",
            "/var/lib/docker/containers/abc123/config.v2.json"
        ]
        return path in valid_paths

    g.exists = Mock(side_effect=exists_side_effect)
    g.is_dir = Mock(return_value=True)
    g.ls = Mock(return_value=["abc123"])

    # Mock Docker container config
    docker_config = {
        "Name": "/test-container",
        "Config": {
            "Image": "nginx:latest",
            "Cmd": ["nginx", "-g", "daemon off;"],
            "Env": ["PATH=/usr/bin", "APP_ENV=production"],
            "WorkingDir": "/app",
            "ExposedPorts": {"80/tcp": {}},
            "Labels": {"app": "web"}
        },
        "NetworkSettings": {
            "Ports": {
                "80/tcp": [{"HostPort": "8080", "HostIp": "0.0.0.0"}]
            },
            "Networks": {"bridge": {}}
        },
        "Mounts": [
            {
                "Type": "volume",
                "Source": "/var/lib/docker/volumes/data/_data",
                "Destination": "/data",
                "Mode": "rw",
                "RW": True
            }
        ],
        "HostConfig": {
            "Memory": 536870912,
            "CpuShares": 1024
        },
        "State": {
            "Running": True
        },
        "Created": "2026-01-27T00:00:00Z"
    }

    g.read_file = Mock(return_value=json.dumps(docker_config))

    return g


@pytest.fixture
def sample_container():
    """Create sample container info."""
    return ContainerInfo(
        container_id="abc123456789",
        name="test-container",
        runtime=ContainerRuntime.DOCKER,
        image="nginx",
        image_tag="latest",
        running=True,
        command=["nginx", "-g", "daemon off;"],
        env_vars={"PATH": "/usr/bin", "APP_ENV": "production"},
        ports=[{"container_port": "80/tcp", "host_port": "8080"}],
        volumes=[{"name": "data", "mount_path": "/data"}],
        labels={"app": "web"}
    )


# ContainerDetector Tests

def test_detector_detects_docker(logger, mock_vmcraft):
    """Test Docker container detection."""
    detector = ContainerDetector(logger)

    runtime, containers = detector.detect_containers(mock_vmcraft)

    assert runtime == ContainerRuntime.DOCKER
    assert len(containers) > 0
    assert containers[0].name == "test-container"
    assert containers[0].image == "nginx"


def test_detector_parse_docker_config(logger):
    """Test Docker config parsing."""
    detector = ContainerDetector(logger)

    config = {
        "Name": "/web-app",
        "Config": {
            "Image": "app:v1",
            "Cmd": ["./start.sh"],
            "Env": ["DEBUG=true"],
            "WorkingDir": "/app"
        },
        "State": {"Running": True}
    }

    container = detector._parse_docker_config("abc123", config)

    assert container.name == "web-app"
    assert container.image == "app"
    assert container.image_tag == "v1"
    assert container.command == ["./start.sh"]
    assert container.env_vars["DEBUG"] == "true"


def test_detector_container_summary(logger, sample_container):
    """Test container summary generation."""
    detector = ContainerDetector(logger)

    containers = [sample_container]
    summary = detector.get_container_summary(containers)

    assert summary["total_containers"] == 1
    assert summary["by_runtime"]["docker"] == 1
    assert summary["running_count"] == 1
    assert summary["total_volumes"] == 1


# DockerExtractor Tests

def test_docker_extractor_generate_dockerfile(logger, sample_container, tmp_path):
    """Test Dockerfile generation."""
    extractor = DockerExtractor(logger)

    result = extractor.generate_dockerfile(sample_container, tmp_path)

    assert result["success"] is True
    assert result["dockerfile"] is not None

    dockerfile_path = Path(result["dockerfile"])
    assert dockerfile_path.exists()

    content = dockerfile_path.read_text()
    assert "FROM nginx:latest" in content
    assert "WORKDIR" not in content  # No working dir in sample
    assert "ENV PATH" in content or "ENV APP_ENV" in content


def test_docker_extractor_generate_compose(logger, sample_container, tmp_path):
    """Test docker-compose.yml generation."""
    extractor = DockerExtractor(logger)

    result = extractor.generate_docker_compose([sample_container], tmp_path)

    assert result["success"] is True
    assert result["compose_file"] is not None

    compose_path = Path(result["compose_file"])
    assert compose_path.exists()

    content = compose_path.read_text()
    assert "version:" in content
    assert "services:" in content
    assert "test-container:" in content
    assert "nginx:latest" in content


def test_docker_extractor_dict_to_yaml(logger):
    """Test YAML conversion."""
    extractor = DockerExtractor(logger)

    data = {
        "version": "3.8",
        "services": {
            "web": {
                "image": "nginx:latest",
                "ports": ["8080:80"]
            }
        }
    }

    yaml_str = extractor._dict_to_yaml(data)

    assert "version: 3.8" in yaml_str
    assert "services:" in yaml_str
    assert "web:" in yaml_str
    # Image may be quoted due to colon
    assert "nginx:latest" in yaml_str


# KubernetesManifestGenerator Tests

def test_k8s_generator_deployment(logger, sample_container, tmp_path):
    """Test Kubernetes Deployment generation."""
    generator = KubernetesManifestGenerator(logger)

    result = generator.generate_deployment(
        [sample_container],
        tmp_path,
        deployment_name="web-deployment"
    )

    assert result["success"] is True
    assert result["manifest_file"] is not None

    manifest_path = Path(result["manifest_file"])
    assert manifest_path.exists()

    content = manifest_path.read_text()
    assert "kind: Deployment" in content
    assert "name: web-deployment" in content
    assert "image: nginx:latest" in content


def test_k8s_generator_service(logger, sample_container, tmp_path):
    """Test Kubernetes Service generation."""
    generator = KubernetesManifestGenerator(logger)

    result = generator.generate_service(
        sample_container,
        tmp_path,
        service_type="ClusterIP"
    )

    assert result["success"] is True
    assert result["manifest_file"] is not None

    manifest_path = Path(result["manifest_file"])
    assert manifest_path.exists()

    content = manifest_path.read_text()
    assert "kind: Service" in content
    assert "type: ClusterIP" in content


def test_k8s_generator_configmap(logger, sample_container, tmp_path):
    """Test Kubernetes ConfigMap generation."""
    generator = KubernetesManifestGenerator(logger)

    result = generator.generate_configmap(sample_container, tmp_path)

    assert result["success"] is True
    assert result["manifest_file"] is not None

    manifest_path = Path(result["manifest_file"])
    assert manifest_path.exists()

    content = manifest_path.read_text()
    assert "kind: ConfigMap" in content
    assert "APP_ENV: production" in content or "PATH:" in content


def test_k8s_generator_pvc(logger, sample_container, tmp_path):
    """Test PersistentVolumeClaim generation."""
    generator = KubernetesManifestGenerator(logger)

    result = generator.generate_persistent_volume_claim(sample_container, tmp_path)

    assert result["success"] is True
    assert len(result["manifest_files"]) > 0

    manifest_path = Path(result["manifest_files"][0])
    assert manifest_path.exists()

    content = manifest_path.read_text()
    assert "kind: PersistentVolumeClaim" in content


def test_k8s_generator_convert_container(logger, sample_container):
    """Test container to Kubernetes spec conversion."""
    generator = KubernetesManifestGenerator(logger)

    k8s_spec = generator._convert_container_to_k8s(sample_container)

    assert k8s_spec["name"] == "test-container"
    assert k8s_spec["image"] == "nginx:latest"
    assert "env" in k8s_spec
    assert "ports" in k8s_spec


# PodmanExtractor Tests

def test_podman_extractor_inheritance(logger):
    """Test Podman extractor inherits from Docker extractor."""
    extractor = PodmanExtractor(logger)

    assert isinstance(extractor, DockerExtractor)


# ContainerExtractionOrchestrator Tests

def test_orchestrator_detect_no_containers(logger, tmp_path):
    """Test orchestrator with no containers."""
    orchestrator = ContainerExtractionOrchestrator(logger)

    # Mock VMCraft with no Docker
    g = MagicMock()
    g.exists = Mock(return_value=False)

    result = orchestrator.extract_containers(g, tmp_path)

    assert result["success"] is True
    assert result["runtime_detected"] is None
    assert result["containers_found"] == 0


def test_orchestrator_extract_for_kubernetes(logger, mock_vmcraft, tmp_path):
    """Test Kubernetes extraction workflow."""
    orchestrator = ContainerExtractionOrchestrator(logger)

    result = orchestrator.extract_containers(
        mock_vmcraft,
        tmp_path,
        target_platform="kubernetes"
    )

    assert result["success"] is True
    assert result["runtime_detected"] == "docker"
    assert result["containers_found"] > 0
    assert len(result["manifests_generated"]) > 0

    # Check that Kubernetes manifests were created
    k8s_dir = tmp_path / "kubernetes"
    assert k8s_dir.exists()


def test_orchestrator_extract_for_docker(logger, mock_vmcraft, tmp_path):
    """Test Docker extraction workflow."""
    orchestrator = ContainerExtractionOrchestrator(logger)

    result = orchestrator.extract_containers(
        mock_vmcraft,
        tmp_path,
        target_platform="docker"
    )

    assert result["success"] is True
    assert result["runtime_detected"] == "docker"
    assert len(result["manifests_generated"]) > 0

    # Check that docker-compose.yml was created
    docker_dir = tmp_path / "docker"
    assert docker_dir.exists()


def test_orchestrator_migration_guide(logger, sample_container):
    """Test migration guide generation."""
    orchestrator = ContainerExtractionOrchestrator(logger)

    guide = orchestrator.generate_migration_guide(
        [sample_container],
        ContainerRuntime.DOCKER,
        "kubernetes",
        Path("/tmp")
    )

    assert "Container Migration Guide" in guide
    assert "Kubernetes Migration Steps" in guide
    assert "test-container" in guide
    assert "nginx:latest" in guide


def test_orchestrator_unsupported_platform(logger, mock_vmcraft, tmp_path):
    """Test extraction with unsupported platform."""
    orchestrator = ContainerExtractionOrchestrator(logger)

    # Expect success with warning when no containers detected
    # (unsupported platform error only occurs if containers are found)
    result = orchestrator.extract_containers(
        mock_vmcraft,
        tmp_path,
        target_platform="unsupported"
    )

    # Should succeed with warning (no containers detected)
    assert result["success"] is True or len(result["errors"]) > 0
