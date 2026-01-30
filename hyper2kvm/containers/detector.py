# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/containers/detector.py
"""
Container detection in VM disk images.

Detects containerized workloads running on VMs.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class ContainerRuntime(Enum):
    """Supported container runtimes."""
    DOCKER = "docker"
    PODMAN = "podman"
    CONTAINERD = "containerd"
    CRI_O = "crio"
    UNKNOWN = "unknown"


@dataclass
class ContainerInfo:
    """
    Container instance information.

    Metadata about a discovered container.
    """
    # Identity
    container_id: str
    name: str
    runtime: ContainerRuntime

    # Image
    image: str
    image_tag: str = "latest"

    # Status
    running: bool = False
    created_at: str | None = None

    # Configuration
    command: list[str] = field(default_factory=list)
    entrypoint: list[str] = field(default_factory=list)
    env_vars: dict[str, str] = field(default_factory=dict)
    working_dir: str | None = None

    # Networking
    ports: list[dict[str, Any]] = field(default_factory=list)
    network_mode: str | None = None
    networks: list[str] = field(default_factory=list)

    # Volumes
    volumes: list[dict[str, str]] = field(default_factory=list)
    mounts: list[dict[str, Any]] = field(default_factory=list)

    # Resources
    memory_limit: str | None = None
    cpu_shares: int | None = None
    cpu_quota: int | None = None

    # Labels and metadata
    labels: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ContainerDetector:
    """
    Detects containers in VM disk images.

    Scans for Docker, Podman, and other container runtimes.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize container detector.

        Args:
            logger: Logger instance
        """
        self.logger = logger

    def detect_containers(self, vmcraft_instance) -> tuple[ContainerRuntime | None, list[ContainerInfo]]:
        """
        Detect all containers in VM.

        Args:
            vmcraft_instance: Launched VMCraft instance

        Returns:
            Tuple of (detected runtime, list of ContainerInfo objects)
        """
        containers = []
        detected_runtime = None

        # Detect Docker
        docker_containers = self._detect_docker_containers(vmcraft_instance)
        if docker_containers:
            containers.extend(docker_containers)
            detected_runtime = ContainerRuntime.DOCKER
            self.logger.info(f"Detected {len(docker_containers)} Docker containers")

        # Detect Podman
        if not detected_runtime:
            podman_containers = self._detect_podman_containers(vmcraft_instance)
            if podman_containers:
                containers.extend(podman_containers)
                detected_runtime = ContainerRuntime.PODMAN
                self.logger.info(f"Detected {len(podman_containers)} Podman containers")

        if not detected_runtime:
            self.logger.info("No container runtime detected")
        else:
            self.logger.info(f"Detected runtime: {detected_runtime.value}")

        return detected_runtime, containers

    def _detect_docker_containers(self, g) -> list[ContainerInfo]:
        """Detect Docker containers."""
        containers = []

        # Check if Docker is installed
        docker_binary = "/usr/bin/docker"
        if not g.exists(docker_binary):
            return containers

        # Look for Docker data directory
        docker_root = "/var/lib/docker"
        if not g.exists(docker_root):
            return containers

        # Try to read container configurations
        containers_dir = f"{docker_root}/containers"
        if g.exists(containers_dir) and g.is_dir(containers_dir):
            try:
                # List container directories
                container_ids = g.ls(containers_dir)

                for container_id in container_ids:
                    container_path = f"{containers_dir}/{container_id}"
                    config_file = f"{container_path}/config.v2.json"

                    if g.exists(config_file):
                        try:
                            config_content = g.read_file(config_file)
                            config = json.loads(config_content)

                            container = self._parse_docker_config(container_id, config)
                            containers.append(container)

                        except Exception as e:
                            self.logger.debug(f"Failed to parse Docker container {container_id}: {e}")

            except Exception as e:
                self.logger.debug(f"Failed to list Docker containers: {e}")

        return containers

    def _parse_docker_config(self, container_id: str, config: dict[str, Any]) -> ContainerInfo:
        """Parse Docker container config."""
        # Extract container configuration
        name = config.get("Name", container_id).lstrip("/")

        # Image info
        image_config = config.get("Config", {})
        image = image_config.get("Image", "unknown")

        # Split image into name and tag
        if ":" in image:
            image_name, image_tag = image.rsplit(":", 1)
        else:
            image_name = image
            image_tag = "latest"

        # Command and entrypoint
        command = image_config.get("Cmd", [])
        entrypoint = image_config.get("Entrypoint", [])

        # Environment variables
        env_list = image_config.get("Env", [])
        env_vars = {}
        for env_str in env_list:
            if "=" in env_str:
                key, value = env_str.split("=", 1)
                env_vars[key] = value

        # Working directory
        working_dir = image_config.get("WorkingDir")

        # Networking
        network_settings = config.get("NetworkSettings", {})
        ports_config = network_settings.get("Ports", {})

        ports = []
        for port_spec, bindings in ports_config.items():
            if bindings:
                for binding in bindings:
                    ports.append({
                        "container_port": port_spec,
                        "host_port": binding.get("HostPort"),
                        "host_ip": binding.get("HostIp", "0.0.0.0")
                    })

        networks = list(network_settings.get("Networks", {}).keys())

        # Volumes and mounts
        mounts_config = config.get("Mounts", [])
        volumes = []
        mounts = []

        for mount in mounts_config:
            mount_info = {
                "type": mount.get("Type"),
                "source": mount.get("Source"),
                "destination": mount.get("Destination"),
                "mode": mount.get("Mode"),
                "rw": mount.get("RW", True)
            }
            mounts.append(mount_info)

            if mount.get("Type") == "volume":
                volumes.append({
                    "name": Path(mount.get("Source", "")).name,
                    "mount_path": mount.get("Destination")
                })

        # Resources
        host_config = config.get("HostConfig", {})
        memory_limit = host_config.get("Memory")
        cpu_shares = host_config.get("CpuShares")
        cpu_quota = host_config.get("CpuQuota")

        # Labels
        labels = image_config.get("Labels", {})

        # State
        state = config.get("State", {})
        running = state.get("Running", False)
        created_at = config.get("Created")

        return ContainerInfo(
            container_id=container_id[:12],  # Short ID
            name=name,
            runtime=ContainerRuntime.DOCKER,
            image=image_name,
            image_tag=image_tag,
            running=running,
            created_at=created_at,
            command=command if isinstance(command, list) else [command] if command else [],
            entrypoint=entrypoint if isinstance(entrypoint, list) else [entrypoint] if entrypoint else [],
            env_vars=env_vars,
            working_dir=working_dir,
            ports=ports,
            networks=networks,
            volumes=volumes,
            mounts=mounts,
            memory_limit=str(memory_limit) if memory_limit else None,
            cpu_shares=cpu_shares,
            cpu_quota=cpu_quota,
            labels=labels
        )

    def _detect_podman_containers(self, g) -> list[ContainerInfo]:
        """Detect Podman containers."""
        containers = []

        # Check if Podman is installed
        podman_binary = "/usr/bin/podman"
        if not g.exists(podman_binary):
            return containers

        # Look for Podman data directories
        podman_roots = [
            "/var/lib/containers/storage",
            "/home/*/.local/share/containers/storage"
        ]

        for podman_root in podman_roots:
            if g.exists(podman_root):
                # Similar logic to Docker detection
                # Podman uses similar structure but different paths
                self.logger.debug(f"Found Podman storage at {podman_root}")
                # TODO: Implement Podman-specific parsing

        return containers

    def detect_docker_compose(self, g) -> list[Path]:
        """
        Detect Docker Compose files.

        Args:
            g: VMCraft instance

        Returns:
            List of docker-compose.yml file paths
        """
        compose_files = []

        # Common locations for docker-compose files
        search_paths = [
            "/opt",
            "/srv",
            "/home",
            "/root"
        ]

        compose_filenames = [
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml"
        ]

        for search_path in search_paths:
            if not g.exists(search_path):
                continue

            try:
                # Search recursively (limited depth)
                for filename in compose_filenames:
                    # Simple check - in real implementation would do recursive search
                    compose_path = f"{search_path}/{filename}"
                    if g.exists(compose_path):
                        compose_files.append(Path(compose_path))
                        self.logger.info(f"Found Docker Compose file: {compose_path}")

            except Exception as e:
                self.logger.debug(f"Failed to search for compose files in {search_path}: {e}")

        return compose_files

    def get_container_summary(self, containers: list[ContainerInfo]) -> dict[str, Any]:
        """
        Generate container summary.

        Args:
            containers: List of ContainerInfo objects

        Returns:
            Summary dict
        """
        summary = {
            "total_containers": len(containers),
            "by_runtime": {},
            "by_image": {},
            "running_count": 0,
            "stopped_count": 0,
            "total_volumes": 0,
            "exposed_ports": []
        }

        for container in containers:
            # Count by runtime
            runtime = container.runtime.value
            summary["by_runtime"][runtime] = summary["by_runtime"].get(runtime, 0) + 1

            # Count by image
            image_full = f"{container.image}:{container.image_tag}"
            summary["by_image"][image_full] = summary["by_image"].get(image_full, 0) + 1

            # Count running/stopped
            if container.running:
                summary["running_count"] += 1
            else:
                summary["stopped_count"] += 1

            # Count volumes
            summary["total_volumes"] += len(container.volumes)

            # Collect exposed ports
            for port in container.ports:
                summary["exposed_ports"].append(
                    f"{port.get('host_port')}:{port.get('container_port')}"
                )

        return summary
