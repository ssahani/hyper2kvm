# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/worker/capabilities.py
"""
Runtime Capability Detection.

Detects execution environment (container vs host) and available capabilities
for privileged disk operations.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ExecutionMode:
    """Execution mode constants."""

    HOST = "host"
    SAFE_CONTAINER = "safe_container"
    PRIVILEGED_CONTAINER = "privileged_container"


class CapabilityDetector:
    """
    Detects runtime capabilities for disk operations.

    Checks:
    - Container vs host execution
    - NBD device availability
    - LVM tools and permissions
    - Mount capabilities
    - SELinux tools
    - Available system resources
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._mode: Optional[str] = None
        self._capabilities: Optional[Dict[str, bool]] = None

    def detect_execution_mode(self) -> str:
        """
        Detect execution mode.

        Returns:
            One of: "host", "safe_container", "privileged_container"
        """
        if self._mode:
            return self._mode

        # Check if running in container
        if not self._is_in_container():
            self._mode = ExecutionMode.HOST
            self.logger.info(f"Detected execution mode: {self._mode}")
            return self._mode

        # In container - check if privileged
        if self._has_nbd_access():
            self._mode = ExecutionMode.PRIVILEGED_CONTAINER
        else:
            self._mode = ExecutionMode.SAFE_CONTAINER

        self.logger.info(f"Detected execution mode: {self._mode}")
        return self._mode

    def _is_in_container(self) -> bool:
        """Check if running inside a container."""

        # Method 1: Check /.dockerenv
        if Path("/.dockerenv").exists():
            self.logger.debug("Container detected: /.dockerenv exists")
            return True

        # Method 2: Check /proc/1/cgroup for container runtime
        try:
            with open("/proc/1/cgroup", "r") as f:
                content = f.read()
                if "docker" in content or "lxc" in content or "kubepods" in content:
                    self.logger.debug(f"Container detected: cgroup contains container runtime")
                    return True
        except Exception as e:
            self.logger.debug(f"Could not check /proc/1/cgroup: {e}")

        # Method 3: Check if running as PID 1 with minimal process tree
        # (containers typically have very few processes)
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                process_count = len(result.stdout.strip().split('\n'))
                # Host typically has 100+ processes, containers have <20
                if process_count < 30:
                    self.logger.debug(f"Container likely detected: only {process_count} processes")
                    return True
        except Exception as e:
            self.logger.debug(f"Could not check process count: {e}")

        self.logger.debug("Not detected as container")
        return False

    def _has_nbd_access(self) -> bool:
        """Check if NBD devices are accessible."""

        # Check if /dev/nbd0 exists
        if not Path("/dev/nbd0").exists():
            self.logger.debug("NBD not available: /dev/nbd0 doesn't exist")
            return False

        # Check if we can read device metadata
        try:
            # Try to read size from sysfs
            size_file = Path("/sys/block/nbd0/size")
            if size_file.exists():
                size = size_file.read_text().strip()
                self.logger.debug(f"NBD device accessible: /dev/nbd0 (size={size})")
                return True
        except PermissionError:
            self.logger.debug("NBD not accessible: permission denied on /sys/block/nbd0/size")
            return False
        except Exception as e:
            self.logger.debug(f"NBD access check failed: {e}")

        return False

    def _check_lvm_available(self) -> bool:
        """Check if LVM tools are available and functional."""

        # Check if LVM commands exist
        for cmd in ["pvs", "vgs", "lvs", "vgchange"]:
            try:
                result = subprocess.run(
                    ["which", cmd],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode != 0:
                    self.logger.debug(f"LVM tool not found: {cmd}")
                    return False
            except Exception as e:
                self.logger.debug(f"LVM tool check failed for {cmd}: {e}")
                return False

        # Check if we can list volume groups (requires device mapper access)
        try:
            result = subprocess.run(
                ["vgs", "--noheadings"],
                capture_output=True,
                text=True,
                timeout=10
            )
            self.logger.debug(f"LVM functional: vgs returned {result.returncode}")
            return result.returncode == 0
        except Exception as e:
            self.logger.debug(f"LVM functionality check failed: {e}")
            return False

    def _check_mount_available(self) -> bool:
        """Check if mount/umount operations are permitted."""

        # Check if running as root or has CAP_SYS_ADMIN
        if os.geteuid() != 0:
            self.logger.debug("Mount not available: not running as root")
            return False

        # Check if mount command exists
        try:
            result = subprocess.run(
                ["which", "mount"],
                capture_output=True,
                timeout=5
            )
            if result.returncode != 0:
                self.logger.debug("Mount not available: mount command not found")
                return False
        except Exception as e:
            self.logger.debug(f"Mount check failed: {e}")
            return False

        # TODO: Could try a test mount to tmpfs to verify capability
        # For now, assume if we're root and have the command, we can mount
        return True

    def _check_selinux_tools(self) -> bool:
        """Check if SELinux tools are available."""

        for cmd in ["restorecon", "semanage", "chcon"]:
            try:
                result = subprocess.run(
                    ["which", cmd],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode != 0:
                    self.logger.debug(f"SELinux tool not found: {cmd}")
                    return False
            except Exception:
                return False

        return True

    def _check_qemu_img(self) -> bool:
        """Check if qemu-img is available."""

        try:
            result = subprocess.run(
                ["qemu-img", "--version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def detect_capabilities(self) -> Dict[str, bool]:
        """
        Detect all available capabilities.

        Returns:
            Dictionary of capability name -> availability
        """
        if self._capabilities:
            return self._capabilities

        self._capabilities = {
            "nbd": self._has_nbd_access(),
            "lvm": self._check_lvm_available(),
            "mount": self._check_mount_available(),
            "selinux": self._check_selinux_tools(),
            "qemu_img": self._check_qemu_img(),
        }

        self.logger.info(f"Detected capabilities: {self._capabilities}")
        return self._capabilities

    def get_system_info(self) -> Dict[str, any]:
        """Get system information for worker registration."""

        import psutil

        info = {
            "hostname": platform.node(),
            "os": platform.system(),
            "os_release": platform.release(),
            "kernel_version": platform.release(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
        }

        # Get memory info
        try:
            mem = psutil.virtual_memory()
            info["memory_gb"] = int(mem.total / (1024**3))
            info["memory_available_gb"] = int(mem.available / (1024**3))
        except Exception as e:
            self.logger.debug(f"Could not get memory info: {e}")
            info["memory_gb"] = 0

        # Get disk info
        try:
            disk = psutil.disk_usage('/')
            info["disk_space_gb"] = int(disk.total / (1024**3))
            info["disk_available_gb"] = int(disk.free / (1024**3))
        except Exception as e:
            self.logger.debug(f"Could not get disk info: {e}")
            info["disk_space_gb"] = 0

        return info

    def can_execute_job(self, job_requirements: Dict[str, bool]) -> tuple[bool, Optional[str]]:
        """
        Check if current environment can execute job with given requirements.

        Args:
            job_requirements: Dictionary of required capabilities

        Returns:
            Tuple of (can_execute, reason_if_cannot)
        """
        capabilities = self.detect_capabilities()

        for capability, required in job_requirements.items():
            if required and not capabilities.get(capability, False):
                return False, f"Missing required capability: {capability}"

        return True, None

    def suggest_execution_mode(self, job_requirements: Dict[str, bool]) -> str:
        """
        Suggest execution mode for job requirements.

        Args:
            job_requirements: Dictionary of required capabilities

        Returns:
            Suggested mode: "host", "privileged_container", or "safe_container"
        """
        needs_privileged = any([
            job_requirements.get("nbd", False),
            job_requirements.get("lvm", False),
            job_requirements.get("mount", False),
        ])

        if needs_privileged:
            current_mode = self.detect_execution_mode()
            if current_mode == ExecutionMode.SAFE_CONTAINER:
                return ExecutionMode.PRIVILEGED_CONTAINER
            elif current_mode == ExecutionMode.PRIVILEGED_CONTAINER:
                return ExecutionMode.PRIVILEGED_CONTAINER
            else:
                return ExecutionMode.HOST
        else:
            return ExecutionMode.SAFE_CONTAINER


# Global detector instance
_detector: Optional[CapabilityDetector] = None


def get_detector() -> CapabilityDetector:
    """Get global capability detector instance."""
    global _detector
    if _detector is None:
        _detector = CapabilityDetector()
    return _detector
