#!/usr/bin/env python3
"""
NBD Preparation Daemon for OfflineFixJob.

Runs as DaemonSet on NBD-capable nodes. Watches node annotations and:
1. Attaches disk images to NBD devices
2. Mounts guest filesystems
3. Updates node annotations when ready
4. Cleans up on job completion

Architecture:
  Controller annotates node → This daemon sees annotation →
  Attach NBD + mount FS → Update node annotation →
  Controller creates VM → VM runs fixers →
  Controller signals cleanup → Daemon unmounts + disconnects
"""

import os
import sys
import time
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from kubernetes import client, config, watch

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

NBD_BASE_PATH = "/dev/nbd"
MOUNT_BASE_PATH = "/var/lib/kubevirt-offline"
IMPORTS_PATH = "/var/lib/imports"


class NBDPrepDaemon:
    """NBD preparation daemon."""

    def __init__(self, node_name: str):
        self.node_name = node_name
        self.api = None
        self.active_jobs = {}  # job_ref -> {device, mount_path}

    def run(self):
        """Main daemon loop."""
        logger.info(f"NBD Prep Daemon starting on node: {self.node_name}")

        # Load Kubernetes config
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except config.ConfigException:
            config.load_kube_config()
            logger.info("Loaded kubeconfig from ~/.kube/config")

        self.api = client.CoreV1Api()

        # Load NBD module once
        self.load_nbd_module()

        # Watch node annotations
        self.watch_node()

    def load_nbd_module(self):
        """Load NBD kernel module."""
        logger.info("Loading NBD kernel module")
        try:
            subprocess.run(
                ["modprobe", "nbd", "max_part=16"],
                check=True,
                capture_output=True
            )
            logger.info("NBD module loaded successfully")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to load NBD module: {e}")
            sys.exit(1)

    def watch_node(self):
        """Watch this node for annotation changes."""
        w = watch.Watch()

        while True:
            try:
                for event in w.stream(
                    self.api.list_node,
                    field_selector=f"metadata.name={self.node_name}",
                    timeout_seconds=30
                ):
                    if event['type'] in ['ADDED', 'MODIFIED']:
                        node = event['object']
                        self.handle_node_update(node)

            except Exception as e:
                logger.error(f"Watch error: {e}")
                time.sleep(5)

    def handle_node_update(self, node):
        """Handle node update event."""
        annotations = node.metadata.annotations or {}

        # Check for job annotation
        job_ref = annotations.get(ANNOTATION_OFFLINE_FIX_JOB)
        cleanup = annotations.get(ANNOTATION_CLEANUP) == 'true'

        if cleanup and job_ref:
            # Cleanup requested
            self.cleanup_job(job_ref)

        elif job_ref:
            # Check if already processed
            nbd_ready = annotations.get(ANNOTATION_NBD_READY) == 'true'

            if not nbd_ready and job_ref not in self.active_jobs:
                # New job, process it
                self.setup_nbd(job_ref)

    def setup_nbd(self, job_ref: str):
        """
        Set up NBD for a job.

        Args:
            job_ref: Namespace/name of the OfflineFixJob
        """
        logger.info(f"Setting up NBD for job: {job_ref}")

        nbd_device = None  # Track for cleanup on error
        mount_path = None

        try:
            # Parse job ref
            namespace, job_name = job_ref.split('/')

            # Get job to read disk spec
            # For now, use hardcoded path (production would query the CRD)
            disk_path = Path(IMPORTS_PATH) / f"{job_name}.qcow2"

            if not disk_path.exists():
                # Try common patterns
                for ext in ['.qcow2', '.vmdk', '.img']:
                    candidate = Path(IMPORTS_PATH) / f"{job_name}{ext}"
                    if candidate.exists():
                        disk_path = candidate
                        break

            if not disk_path.exists():
                raise FileNotFoundError(f"Disk image not found for job {job_name}")

            # Find free NBD device
            nbd_device = self.find_free_nbd_device()
            if not nbd_device:
                raise Exception("No free NBD device available")

            # Attach disk to NBD
            self.attach_disk_to_nbd(str(disk_path), nbd_device)

            # Wait for partitions
            time.sleep(2)
            self.probe_partitions(nbd_device)

            # Activate LVM if present
            self.activate_lvm()

            # Mount root partition
            mount_path = self.mount_root_partition(nbd_device, job_name)

            # Mount boot partition if separate
            self.mount_boot_partition(nbd_device, mount_path)

            # Update node annotations
            self.update_node_annotations(job_ref, nbd_device, mount_path)

            # Track active job
            self.active_jobs[job_ref] = {
                'device': nbd_device,
                'mount_path': mount_path
            }

            logger.info(f"NBD setup complete: device={nbd_device}, mount={mount_path}")

        except Exception as e:
            logger.error(f"NBD setup failed for {job_ref}: {e}")
            logger.debug(f"NBD setup error details", exc_info=True)

            # Cleanup: Disconnect NBD if it was attached
            if nbd_device:
                try:
                    logger.info(f"Cleaning up failed setup: disconnecting {nbd_device}")
                    self.disconnect_nbd(nbd_device)
                except Exception as cleanup_error:
                    logger.error(f"Cleanup failed: {cleanup_error}")

            # Cleanup: Unmount if mounted
            if mount_path and self.is_mount_point(mount_path):
                try:
                    self.unmount(mount_path)
                except:
                    pass

            # Update node annotation with error
            try:
                error_msg = str(e)[:200]  # Truncate if too long
                body = {
                    "metadata": {
                        "annotations": {
                            ANNOTATION_NBD_READY: 'false',
                            "offlinefix.hyper2kvm.io/nbd-error": error_msg
                        }
                    }
                }
                self.api.patch_node(self.node_name, body)
                logger.info(f"Updated node annotations with error for {job_ref}")
            except Exception as patch_error:
                logger.error(f"Failed to update node with error: {patch_error}")

            # Don't crash the daemon - just log and continue watching
            # The controller will see the error annotation and can retry or fail the job

    def cleanup_job(self, job_ref: str):
        """
        Cleanup NBD for a job.

        Args:
            job_ref: Namespace/name of the OfflineFixJob
        """
        logger.info(f"Cleaning up NBD for job: {job_ref}")

        if job_ref not in self.active_jobs:
            logger.warning(f"Job {job_ref} not in active jobs")
            return

        job_info = self.active_jobs[job_ref]
        nbd_device = job_info['device']
        mount_path = job_info['mount_path']

        try:
            # Unmount boot
            boot_mount = Path(mount_path) / "boot"
            if self.is_mount_point(str(boot_mount)):
                self.unmount(str(boot_mount))

            # Unmount root
            if self.is_mount_point(mount_path):
                self.unmount(mount_path)

            # Deactivate LVM
            self.deactivate_lvm()

            # Disconnect NBD
            self.disconnect_nbd(nbd_device)

            # Remove mount directory
            if Path(mount_path).exists():
                Path(mount_path).rmdir()

            # Remove from active jobs
            del self.active_jobs[job_ref]

            # Clear node annotations
            self.clear_node_annotations(job_ref)

            logger.info(f"Cleanup complete for job: {job_ref}")

        except Exception as e:
            logger.error(f"Cleanup failed for {job_ref}: {e}")

    def find_free_nbd_device(self) -> Optional[str]:
        """Find an unused NBD device."""
        for i in range(16):
            device = f"{NBD_BASE_PATH}{i}"

            # Method 1: Check if device exists
            if not Path(device).exists():
                logger.debug(f"{device} does not exist, skipping")
                continue

            # Method 2: Check /sys/block/nbdX/pid for active connection (if available)
            # Note: This may not exist on all kernel versions
            pid_file = Path(f"/sys/block/nbd{i}/pid")
            if pid_file.exists():
                try:
                    pid_str = pid_file.read_text().strip()
                    if pid_str:  # File has content
                        pid = int(pid_str)
                        if pid > 0:
                            logger.debug(f"{device} is in use (pid={pid})")
                            continue
                except (ValueError, OSError) as e:
                    logger.debug(f"{device} pid check failed: {e}")

            # Method 3: Check with lsblk (most reliable)
            # Use -b for bytes (more reliable than human-readable) and -o SIZE to get just size
            result = subprocess.run(
                ["lsblk", "-n", "-b", "-o", "SIZE", device],
                capture_output=True,
                text=True
            )

            # If lsblk shows the device with size > 0, it's connected
            if result.returncode == 0 and result.stdout.strip():
                try:
                    size_bytes = int(result.stdout.strip())
                    if size_bytes == 0:
                        # Size is 0 bytes - device is free
                        logger.debug(f"{device} is free (size=0)")
                        return device
                    else:
                        # Device has a size - it's connected
                        logger.debug(f"{device} is in use (size={size_bytes} bytes)")
                        continue
                except ValueError:
                    # Can't parse size - assume free
                    logger.debug(f"{device} has unparseable size, assuming free")
                    return device
            else:
                # lsblk failed - assume free
                logger.debug(f"{device} lsblk failed, assuming free")
                return device

        logger.error("No free NBD devices found")
        return None

    def attach_disk_to_nbd(self, disk_path: str, nbd_device: str):
        """Attach disk image to NBD device."""
        logger.info(f"Attaching {disk_path} to {nbd_device}")

        # First, ensure device is disconnected (in case of previous failed attempt)
        logger.debug(f"Ensuring {nbd_device} is disconnected before attach")
        subprocess.run(
            ["qemu-nbd", "--disconnect", nbd_device],
            capture_output=True,
            # Don't check=True - it's ok if disconnect fails (device not connected)
        )

        # Small delay to let kernel release the device
        time.sleep(0.5)

        # Now attach the disk
        result = subprocess.run(
            ["qemu-nbd", f"--connect={nbd_device}", disk_path],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            # Log stderr for debugging
            stderr = result.stderr.strip()
            logger.error(f"qemu-nbd connect failed (exit {result.returncode}): {stderr}")
            raise subprocess.CalledProcessError(
                result.returncode,
                result.args,
                output=result.stdout,
                stderr=result.stderr
            )

    def probe_partitions(self, nbd_device: str):
        """Force kernel to detect partitions."""
        subprocess.run(
            ["partprobe", nbd_device],
            capture_output=True
        )

    def activate_lvm(self):
        """Activate LVM volume groups."""
        subprocess.run(
            ["vgchange", "-ay"],
            capture_output=True
        )

    def deactivate_lvm(self):
        """Deactivate LVM volume groups."""
        subprocess.run(
            ["vgchange", "-an"],
            capture_output=True
        )

    def mount_root_partition(self, nbd_device: str, job_name: str) -> str:
        """Find and mount root partition."""
        # Find largest partition (heuristic for root)
        # Use -l for list mode (no tree characters), -p for full paths
        result = subprocess.run(
            [
                "sh", "-c",
                f"lsblk -n -l -p -o NAME,SIZE {nbd_device} | grep {Path(nbd_device).name}p | "
                f"sort -k2 -hr | head -1 | awk '{{print $1}}'"
            ],
            capture_output=True,
            text=True,
            check=True
        )

        root_part = result.stdout.strip()
        if not root_part:
            raise Exception("No partitions found")

        logger.info(f"Selected root partition: {root_part}")

        # Create mount point
        mount_path = Path(MOUNT_BASE_PATH) / job_name
        mount_path.mkdir(parents=True, exist_ok=True)

        # Mount partition
        logger.info(f"Mounting {root_part} to {mount_path}")
        subprocess.run(
            ["mount", root_part, str(mount_path)],
            check=True,
            capture_output=True
        )

        # Verify /etc exists
        etc_path = mount_path / "etc"
        if not etc_path.is_dir():
            subprocess.run(["umount", str(mount_path)])
            raise Exception("Mounted partition does not contain /etc")

        return str(mount_path)

    def mount_boot_partition(self, nbd_device: str, root_mount_path: str):
        """Mount /boot if it's a separate partition."""
        boot_part = f"{nbd_device}p1"

        if not Path(boot_part).exists():
            return

        # Check if it's a filesystem
        result = subprocess.run(
            ["blkid", "-s", "TYPE", "-o", "value", boot_part],
            capture_output=True,
            text=True
        )

        if result.returncode != 0 or not result.stdout.strip():
            return

        # Create boot mount point
        boot_mount = Path(root_mount_path) / "boot"
        boot_mount.mkdir(parents=True, exist_ok=True)

        # Mount boot partition
        logger.info(f"Mounting boot partition {boot_part} to {boot_mount}")
        subprocess.run(
            ["mount", boot_part, str(boot_mount)],
            capture_output=True
        )

    def is_mount_point(self, path: str) -> bool:
        """Check if path is a mount point."""
        result = subprocess.run(
            ["mountpoint", "-q", path],
            capture_output=True
        )
        return result.returncode == 0

    def unmount(self, mount_path: str):
        """Unmount a filesystem."""
        logger.info(f"Unmounting {mount_path}")
        subprocess.run(
            ["umount", mount_path],
            check=True,
            capture_output=True
        )

    def disconnect_nbd(self, nbd_device: str):
        """Disconnect NBD device."""
        logger.info(f"Disconnecting {nbd_device}")
        subprocess.run(
            ["qemu-nbd", "--disconnect", nbd_device],
            capture_output=True
        )

    def update_node_annotations(self, job_ref: str, nbd_device: str, mount_path: str):
        """Update node annotations with NBD ready status."""
        body = {
            "metadata": {
                "annotations": {
                    ANNOTATION_NBD_READY: 'true',
                    ANNOTATION_NBD_DEVICE: nbd_device,
                    ANNOTATION_MOUNT_PATH: mount_path
                }
            }
        }

        self.api.patch_node(self.node_name, body)
        logger.info(f"Updated node annotations for {job_ref}")

    def clear_node_annotations(self, job_ref: str):
        """Clear NBD annotations from node."""
        body = {
            "metadata": {
                "annotations": {
                    ANNOTATION_OFFLINE_FIX_JOB: None,
                    ANNOTATION_NBD_READY: None,
                    ANNOTATION_NBD_DEVICE: None,
                    ANNOTATION_MOUNT_PATH: None,
                    ANNOTATION_CLEANUP: None
                }
            }
        }

        self.api.patch_node(self.node_name, body)
        logger.info(f"Cleared node annotations for {job_ref}")


def main():
    """Main entry point."""
    node_name = os.environ.get('NODE_NAME')
    if not node_name:
        logger.error("NODE_NAME environment variable not set")
        sys.exit(1)

    daemon = NBDPrepDaemon(node_name)
    daemon.run()


if __name__ == "__main__":
    main()
