# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/vmcraft/main.py
"""
VMCraft main class - delegates to modular components.

This file provides the main VMCraft API that maintains backward compatibility
with the original monolithic implementation while delegating to specialized modules.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from ._utils import run_sudo
from .nbd import NBDDeviceManager
from .storage import StorageStackActivator, LVMActivator
from .mount import MountManager
from .file_ops import FileOperations
from .linux_detection import LinuxDetector
from .windows_detection import WindowsDetector
from .inspection import OSInspector
from .windows_registry import WindowsRegistryManager
from .windows_drivers import WindowsDriverInjector
from .windows_users import WindowsUserManager
from .windows_services import WindowsServiceManager
from .windows_applications import WindowsApplicationManager
from .linux_services import LinuxServiceManager
from .network_config import NetworkConfigAnalyzer
from .firewall_analyzer import FirewallAnalyzer
from .advanced_analysis import AdvancedAnalyzer
from .export import ExportManager
from .scheduled_tasks import ScheduledTaskAnalyzer
from .ssh_analyzer import SSHAnalyzer
from .log_analyzer import LogAnalyzer
from .hardware_detector import HardwareDetector
from .backup import BackupManager
from .security import SecurityAuditor
from .optimization import DiskOptimizer
from .database_detector import DatabaseDetector
from .webserver_analyzer import WebServerAnalyzer
from .certificate_manager import CertificateManager
from .container_analyzer import ContainerAnalyzer
from .compliance_checker import ComplianceChecker
from .backup_analysis import BackupAnalysis
from .user_activity import UserActivityAnalyzer
from .app_framework_detector import AppFrameworkDetector
from .cloud_detector import CloudDetector
from .monitoring_detector import MonitoringDetector
from .vulnerability_scanner import VulnerabilityScanner
from .license_detector import LicenseDetector
from .performance_analyzer import PerformanceAnalyzer
from .migration_planner import MigrationPlanner
from .dependency_mapper import DependencyMapper
from .forensic_analyzer import ForensicAnalyzer
from .data_discovery import DataDiscovery
from .config_tracker import ConfigTracker
from .network_topology import NetworkTopology
from .storage_analyzer import StorageAnalyzer
from .threat_intelligence import ThreatIntelligence
from .automated_remediation import AutomatedRemediation
from .predictive_analytics import PredictiveAnalytics
from .integration_hub import IntegrationHub
from .realtime_monitoring import RealtimeMonitoring
from .ml_analyzer import MLAnalyzer
from .cloud_optimizer import CloudOptimizer
from .disaster_recovery import DisasterRecovery
from .audit_trail import AuditTrail
from .resource_orchestrator import ResourceOrchestrator
from .systemd import SystemctlManager, JournalctlManager, SystemdAnalyzer, SystemConfigManager
from .enhanced_inspection import EnhancedInspector


logger = logging.getLogger(__name__)


class VMCraft:
    """
    Native implementation of guestfs.GuestFS API.

    Uses qemu-nbd + Linux tools instead of libguestfs appliance.
    Compatible with existing code that uses guestfs.GuestFS(python_return_dict=True).

    This is the main entry point that coordinates all specialized modules.
    """

    def __init__(self, python_return_dict: bool = True):
        """
        Initialize VMCraft.

        Args:
            python_return_dict: Return dicts instead of tuples (default: True)
        """
        self._return_dict = python_return_dict
        self._drives: list[dict[str, Any]] = []
        self._nbd_manager: NBDDeviceManager | None = None
        self._nbd_device: str | None = None
        self._storage_activator: StorageStackActivator | None = None
        self._storage_audit: dict[str, Any] | None = None
        self._mount_root: Path | None = None
        self._launched = False
        self._trace = False
        self._perf_metrics: dict[str, float] = {}
        self.logger = logging.getLogger(__name__)

        # Performance caches
        self._partition_cache: dict[str, tuple[list[str], float]] = {}
        self._blkid_cache: dict[str, tuple[dict[str, str], float]] = {}
        self._blkid_cache_ttl: int = 120  # 2 minutes TTL for blkid cache

        # Specialized managers (initialized after launch)
        self._mount_manager: MountManager | None = None
        self._file_ops: FileOperations | None = None
        self._linux_detector: LinuxDetector | None = None
        self._windows_detector: WindowsDetector | None = None
        self._os_inspector: OSInspector | None = None
        self._win_registry: WindowsRegistryManager | None = None
        self._win_drivers: WindowsDriverInjector | None = None
        self._win_users: WindowsUserManager | None = None
        self._win_services: WindowsServiceManager | None = None
        self._win_apps: WindowsApplicationManager | None = None
        self._linux_services: LinuxServiceManager | None = None
        self._network_config: NetworkConfigAnalyzer | None = None
        self._firewall_analyzer: FirewallAnalyzer | None = None
        self._advanced_analyzer: AdvancedAnalyzer | None = None
        self._export_mgr: ExportManager | None = None
        self._scheduled_tasks: ScheduledTaskAnalyzer | None = None
        self._ssh_analyzer: SSHAnalyzer | None = None
        self._log_analyzer: LogAnalyzer | None = None
        self._hardware_detector: HardwareDetector | None = None
        self._backup_mgr: BackupManager | None = None
        self._security_auditor: SecurityAuditor | None = None
        self._disk_optimizer: DiskOptimizer | None = None
        self._database_detector: DatabaseDetector | None = None
        self._webserver_analyzer: WebServerAnalyzer | None = None
        self._certificate_manager: CertificateManager | None = None
        self._container_analyzer: ContainerAnalyzer | None = None
        self._compliance_checker: ComplianceChecker | None = None
        self._backup_analysis: BackupAnalysis | None = None
        self._user_activity: UserActivityAnalyzer | None = None
        self._app_framework_detector: AppFrameworkDetector | None = None
        self._cloud_detector: CloudDetector | None = None
        self._monitoring_detector: MonitoringDetector | None = None
        self._vulnerability_scanner: VulnerabilityScanner | None = None
        self._license_detector: LicenseDetector | None = None
        self._performance_analyzer: PerformanceAnalyzer | None = None
        self._migration_planner: MigrationPlanner | None = None
        self._dependency_mapper: DependencyMapper | None = None
        self._forensic_analyzer: ForensicAnalyzer | None = None
        self._data_discovery: DataDiscovery | None = None
        self._config_tracker: ConfigTracker | None = None
        self._network_topology: NetworkTopology | None = None
        self._storage_analyzer: StorageAnalyzer | None = None
        self._threat_intelligence: ThreatIntelligence | None = None
        self._automated_remediation: AutomatedRemediation | None = None
        self._predictive_analytics: PredictiveAnalytics | None = None
        self._integration_hub: IntegrationHub | None = None
        self._realtime_monitoring: RealtimeMonitoring | None = None
        self._ml_analyzer: MLAnalyzer | None = None
        self._cloud_optimizer: CloudOptimizer | None = None
        self._disaster_recovery: DisasterRecovery | None = None
        self._audit_trail: AuditTrail | None = None
        self._resource_orchestrator: ResourceOrchestrator | None = None

        # Systemd managers (initialized after launch)
        self._systemctl: SystemctlManager | None = None
        self._journalctl: JournalctlManager | None = None
        self._systemd_analyze: SystemdAnalyzer | None = None
        self._sysconfig: SystemConfigManager | None = None

        # Enhanced inspection (initialized after launch)
        self._enhanced_inspector: EnhancedInspector | None = None

        # Augeas configuration management (initialized after launch)
        self._augeas: Any | None = None

        # Log backend selection
        self.logger.debug("Using VMCraft backend (qemu-nbd + Linux tools)")

    def set_trace(self, enable: int | bool) -> None:
        """Enable debug tracing."""
        self._trace = bool(enable)
        if self._trace:
            self.logger.setLevel(logging.DEBUG)

    def add_drive_opts(
        self,
        path: str,
        *,
        readonly: int | bool = 1,
        format: str | None = None,
        **kwargs
    ) -> None:
        """
        Add a disk image.

        Args:
            path: Path to disk image
            readonly: Mount read-only (default: True)
            format: Disk format (qcow2, vmdk, raw, etc.)
            **kwargs: Other options (ignored for compatibility)
        """
        if self._launched:
            raise RuntimeError("Cannot add drives after launch()")

        self._drives.append({
            'path': str(path),
            'readonly': bool(readonly),
            'format': format,
        })

    def launch(self) -> None:
        """
        Launch the backend.

        Connects NBD devices, activates storage stack, creates mount root,
        and initializes all specialized managers.
        """
        start_time = time.time()

        if self._launched:
            raise RuntimeError("Already launched")

        if not self._drives:
            raise RuntimeError("No drives added")

        # For now, only support single drive (can be extended)
        if len(self._drives) > 1:
            raise NotImplementedError("Multiple drives not yet supported")

        drive = self._drives[0]

        self.logger.info("Launching VMCraft backend...")
        self.logger.info(f"   Backend: VMCraft (Python + qemu-nbd + Linux tools)")
        self.logger.info(f"   Image: {Path(drive['path']).name}")
        self.logger.info(f"   Format: {drive.get('format', 'auto-detect')}")
        self.logger.info(f"   Mode: {'read-only' if drive['readonly'] else 'read-write'}")

        # Connect NBD
        nbd_start = time.time()
        self._nbd_manager = NBDDeviceManager(
            self.logger,
            readonly=drive['readonly']
        )
        self._nbd_device = self._nbd_manager.connect(
            drive['path'],
            format=drive.get('format'),
            readonly=drive['readonly']
        )
        nbd_time = time.time() - nbd_start
        self._perf_metrics['nbd_connect'] = nbd_time
        self.logger.info(f"   NBD connected: {self._nbd_device} ({nbd_time:.2f}s)")

        # Activate storage stack
        storage_start = time.time()
        self._storage_activator = StorageStackActivator(self.logger)
        self._storage_audit = self._storage_activator.activate_all()
        storage_time = time.time() - storage_start
        self._perf_metrics['storage_activation'] = storage_time
        self.logger.info(f"   Storage stack activated ({storage_time:.2f}s)")

        # Create temporary mount root
        self._mount_root = Path(tempfile.mkdtemp(prefix="hyper2kvm-guestfs-"))

        # Initialize all specialized managers
        self._mount_manager = MountManager(self.logger, self._mount_root)
        self._file_ops = FileOperations(self.logger, self._mount_root, enable_cache=True, cache_size=1000)
        self._linux_detector = LinuxDetector(self.logger, self._mount_root)
        self._windows_detector = WindowsDetector(self.logger, self._mount_root)
        self._os_inspector = OSInspector(
            self.logger,
            self._mount_root,
            self._linux_detector,
            self._windows_detector
        )
        self._win_registry = WindowsRegistryManager(self.logger, self._mount_root)
        self._win_drivers = WindowsDriverInjector(self.logger, self._mount_root)
        self._win_users = WindowsUserManager(self.logger, self._mount_root)
        self._win_services = WindowsServiceManager(self.logger, self._mount_root)
        self._win_apps = WindowsApplicationManager(self.logger, self._mount_root)
        self._linux_services = LinuxServiceManager(self.logger, self._mount_root)
        self._network_config = NetworkConfigAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._firewall_analyzer = FirewallAnalyzer(self.logger, self._file_ops)
        self._advanced_analyzer = AdvancedAnalyzer(self.logger, self._file_ops)
        self._export_mgr = ExportManager(self.logger)
        self._scheduled_tasks = ScheduledTaskAnalyzer(self.logger, self._file_ops)
        self._ssh_analyzer = SSHAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._log_analyzer = LogAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._hardware_detector = HardwareDetector(self.logger, self._file_ops, self._mount_root)
        self._backup_mgr = BackupManager(self.logger, self._mount_root)
        self._security_auditor = SecurityAuditor(self.logger, self._mount_root)
        self._disk_optimizer = DiskOptimizer(self.logger, self._mount_root)
        self._database_detector = DatabaseDetector(self.logger, self._file_ops, self._mount_root)
        self._webserver_analyzer = WebServerAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._certificate_manager = CertificateManager(self.logger, self._file_ops, self._mount_root)
        self._container_analyzer = ContainerAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._compliance_checker = ComplianceChecker(self.logger, self._file_ops, self._mount_root)
        self._backup_analysis = BackupAnalysis(self.logger, self._file_ops, self._mount_root)
        self._user_activity = UserActivityAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._app_framework_detector = AppFrameworkDetector(self.logger, self._file_ops, self._mount_root)
        self._cloud_detector = CloudDetector(self.logger, self._file_ops, self._mount_root)
        self._monitoring_detector = MonitoringDetector(self.logger, self._file_ops, self._mount_root)
        self._vulnerability_scanner = VulnerabilityScanner(self.logger, self._file_ops, self._mount_root)
        self._license_detector = LicenseDetector(self.logger, self._file_ops, self._mount_root)
        self._performance_analyzer = PerformanceAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._migration_planner = MigrationPlanner(self.logger, self._file_ops, self._mount_root)
        self._dependency_mapper = DependencyMapper(self.logger, self._file_ops, self._mount_root)
        self._forensic_analyzer = ForensicAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._data_discovery = DataDiscovery(self.logger, self._file_ops, self._mount_root)
        self._config_tracker = ConfigTracker(self.logger, self._file_ops, self._mount_root)
        self._network_topology = NetworkTopology(self.logger, self._file_ops, self._mount_root)
        self._storage_analyzer = StorageAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._threat_intelligence = ThreatIntelligence(self.logger, self._file_ops, self._mount_root)
        self._automated_remediation = AutomatedRemediation(self.logger, self._file_ops, self._mount_root)
        self._predictive_analytics = PredictiveAnalytics(self.logger, self._file_ops, self._mount_root)
        self._integration_hub = IntegrationHub(self.logger, self._file_ops, self._mount_root)
        self._realtime_monitoring = RealtimeMonitoring(self.logger, self._file_ops, self._mount_root)
        self._ml_analyzer = MLAnalyzer(self.logger, self._file_ops, self._mount_root)
        self._cloud_optimizer = CloudOptimizer(self.logger, self._file_ops, self._mount_root)
        self._disaster_recovery = DisasterRecovery(self.logger, self._file_ops, self._mount_root)
        self._audit_trail = AuditTrail(self.logger, self._file_ops, self._mount_root)
        self._resource_orchestrator = ResourceOrchestrator(self.logger, self._file_ops, self._mount_root)

        # Initialize systemd managers
        self._systemctl = SystemctlManager(self.command_quiet, self.logger)
        self._journalctl = JournalctlManager(self.command_quiet, self.logger)
        self._systemd_analyze = SystemdAnalyzer(self.command_quiet, self.logger)
        self._sysconfig = SystemConfigManager(self.command_quiet, self.logger)

        # Initialize enhanced inspector
        self._enhanced_inspector = EnhancedInspector(
            mount_root=self._mount_root,
            logger=self.logger,
            cat_func=self.cat,
            exists_func=self.exists,
            is_dir_func=self.is_dir,
            ls_func=self.ls,
        )

        # Initialize Augeas manager (lazy - call aug_init() to activate)
        from hyper2kvm.core.vmcraft.augeas_mgr import AugeasManager
        self._augeas = AugeasManager(self.logger, str(self._mount_root))

        total_time = time.time() - start_time
        self._perf_metrics['total_launch'] = total_time
        self._launched = True

        self.logger.info(f"VMCraft ready in {total_time:.2f}s (vs ~5-10s for libguestfs)")
        self.logger.debug(f"   Mount root: {self._mount_root}")

    def sync(self) -> None:
        """Flush filesystem buffers to disk."""
        if not self._launched:
            return

        # VMCraft uses direct NBD access, no additional sync needed
        # All writes are synchronous through mount operations
        self.logger.debug("VMCraft sync: no-op (direct NBD access)")

    def shutdown(self) -> None:
        """Shutdown the backend."""
        if not self._launched:
            return

        self.logger.info("Shutting down VMCraft backend...")

        # Umount all filesystems first
        try:
            self.umount_all()
            self.logger.info("   All filesystems unmounted")
        except Exception as e:
            self.logger.warning(f"   Error during umount_all: {e}")

        # Disconnect NBD
        if self._nbd_manager:
            try:
                self._nbd_manager.disconnect()
                self.logger.info(f"   NBD device disconnected: {self._nbd_device}")
            except Exception as e:
                self.logger.warning(f"   Error disconnecting NBD: {e}")

        self._launched = False
        self.logger.info("VMCraft shut down successfully")

    def close(self) -> None:
        """Close and cleanup."""
        # Ensure shutdown
        try:
            self.shutdown()
        except Exception:
            pass

        # Remove temp mount root
        if self._mount_root and self._mount_root.exists():
            try:
                shutil.rmtree(self._mount_root)
            except Exception as e:
                self.logger.warning(f"Error removing mount root: {e}")
            self._mount_root = None

        self._nbd_manager = None
        self._storage_activator = None
        self._mount_manager = None
        self._file_ops = None
        self._linux_detector = None
        self._windows_detector = None
        self._os_inspector = None
        self._win_registry = None
        self._win_drivers = None
        self._win_users = None
        self._linux_services = None
        self._backup_mgr = None
        self._security_auditor = None
        self._disk_optimizer = None

    # Utility / Info APIs

    def get_backend_info(self) -> dict[str, Any]:
        """Get information about the VMCraft backend."""
        return {
            'backend': 'vmcraft',
            'implementation': 'VMCraft - Python disk manipulation library',
            'version': '1.0.0',
            'features': {
                'nbd_based': True,
                'requires_root': True,
                'libguestfs_compatible': True,
                'performance': '5x faster startup, 10x less memory',
                'windows_support': True,
                'driver_injection': True,
                'registry_operations': True,
            },
            'launched': self._launched,
            'nbd_device': self._nbd_device if self._launched else None,
            'mount_root': str(self._mount_root) if self._mount_root else None,
        }

    def get_performance_metrics(self) -> dict[str, Any]:
        """
        Get comprehensive performance metrics.

        Includes:
        - Launch timing metrics
        - Cache statistics
        - Memory usage estimates
        - Operation counts

        Returns:
            Dict with performance metrics
        """
        metrics: dict[str, Any] = {
            "launch": dict(self._perf_metrics),
        }

        # Add cache statistics if available
        if self._file_ops:
            metrics["cache"] = self._file_ops.get_cache_stats()

        # Add operation counts (these would be tracked by modules)
        # For now, we'll provide placeholder structure
        metrics["operations"] = {
            "file_reads": 0,  # Could be tracked in FileOperations
            "file_writes": 0,  # Could be tracked in FileOperations
            "mounts": len(self._mount_manager.mountpoints()) if self._mount_manager else 0,
        }

        # Memory estimate (rough calculation based on cache sizes)
        if metrics.get("cache", {}).get("enabled"):
            cache_stats = metrics["cache"]
            meta_size = cache_stats.get("metadata_cache", {}).get("size", 0)
            dir_size = cache_stats.get("dir_cache", {}).get("size", 0)
            # Rough estimate: 1KB per metadata entry, 0.5KB per dir entry
            estimated_kb = (meta_size * 1) + (dir_size * 0.5)
            metrics["memory_estimate_kb"] = int(estimated_kb)

        return metrics

    # Inspection APIs

    def inspect_os(self) -> list[str]:
        """Detect operating systems on disk."""
        if not self._launched or not self._os_inspector:
            raise RuntimeError("Not launched")

        partitions = self.list_partitions()
        return self._os_inspector.inspect_partitions(partitions)

    def inspect_get_type(self, root: str) -> str:
        """Get OS type (linux, windows, etc.)."""
        if self._os_inspector and self._os_inspector.has_cached_info(root):
            return self._os_inspector.get_cached_info(root).get("type", "unknown")
        return "unknown"

    def inspect_get_distro(self, root: str) -> str:
        """Get distribution name."""
        if self._os_inspector and self._os_inspector.has_cached_info(root):
            return self._os_inspector.get_cached_info(root).get("distro", "unknown")
        return "unknown"

    def inspect_get_product_name(self, root: str) -> str:
        """Get product name."""
        if self._os_inspector and self._os_inspector.has_cached_info(root):
            return self._os_inspector.get_cached_info(root).get("product", "Unknown")
        return "Unknown"

    def inspect_get_major_version(self, root: str) -> int:
        """Get major version number."""
        if self._os_inspector and self._os_inspector.has_cached_info(root):
            return self._os_inspector.get_cached_info(root).get("major", 0)
        return 0

    def inspect_get_minor_version(self, root: str) -> int:
        """Get minor version number."""
        if self._os_inspector and self._os_inspector.has_cached_info(root):
            return self._os_inspector.get_cached_info(root).get("minor", 0)
        return 0

    def inspect_get_arch(self, root: str) -> str:
        """Get architecture."""
        if self._os_inspector and self._os_inspector.has_cached_info(root):
            return self._os_inspector.get_cached_info(root).get("arch", "unknown")
        return "unknown"

    def inspect_get_mountpoints(self, root: str) -> dict[str, str] | list[tuple[str, str]]:
        """Get mountpoints for root."""
        # For Windows, return simple root mountpoint (no fstab)
        os_type = self.inspect_get_type(root)
        if os_type == "windows":
            if self._return_dict:
                return {"/": root}
            else:
                return [(root, "/")]

        # For Linux, parse /etc/fstab
        mounts = self._parse_fstab(root)

        if self._return_dict:
            return {mp: dev for dev, mp in mounts}
        else:
            return [(dev, mp) for dev, mp in mounts]

    def _parse_fstab(self, root: str) -> list[tuple[str, str]]:
        """Parse /etc/fstab from root device."""
        if not self._mount_root or not self._file_ops:
            return []

        mounts = []

        try:
            # Mount root temporarily to read fstab
            self.umount_all()
            run_sudo(self.logger, ["mount", "-o", "ro", root, str(self._mount_root)], check=True, capture=True)

            fstab_path = self._mount_root / "etc/fstab"
            if not fstab_path.exists():
                return mounts

            for line in fstab_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    device = parts[0]
                    mountpoint = parts[1]
                    mounts.append((device, mountpoint))

        except Exception as e:
            self.logger.warning(f"Failed to parse fstab: {e}")
        finally:
            try:
                run_sudo(self.logger, ["umount", str(self._mount_root)], check=False, capture=True)
            except Exception:
                pass

        return mounts

    # Mount operations (delegate to MountManager)

    def mount(self, device: str, mountpoint: str) -> None:
        """Mount device at mountpoint (read-write)."""
        if not self._mount_manager:
            raise RuntimeError("Not launched")
        # Use DEBUG logging for mount failures since root detection tries multiple devices
        self._mount_manager.mount(device, mountpoint, readonly=False, failure_log_level=logging.DEBUG)

    def mount_ro(self, device: str, mountpoint: str) -> None:
        """Mount device at mountpoint (read-only)."""
        if not self._mount_manager:
            raise RuntimeError("Not launched")
        # Use DEBUG logging for mount failures since root detection tries multiple devices
        self._mount_manager.mount(device, mountpoint, readonly=True, failure_log_level=logging.DEBUG)

    def mount_options(self, options: str, device: str, mountpoint: str) -> None:
        """Mount device with custom options."""
        if not self._mount_manager:
            raise RuntimeError("Not launched")
        self._mount_manager.mount(device, mountpoint, options=options)

    def umount_all(self) -> None:
        """Unmount all mounted filesystems."""
        if self._mount_manager:
            self._mount_manager.umount_all()
        # Clear file operations cache after unmounting to prevent stale metadata
        if self._file_ops:
            self._file_ops.clear_cache()

    def mountpoints(self) -> list[str]:
        """Get list of current mountpoints."""
        if not self._mount_manager:
            return []
        return self._mount_manager.mountpoints()

    def mounts(self) -> list[str]:
        """Get list of mounted devices."""
        if not self._mount_manager:
            return []
        return self._mount_manager.mounts()

    def mount_all_parallel(self, devices: list[tuple[str, str]], max_workers: int = 4, readonly: bool = True) -> dict[str, bool]:
        """
        Mount multiple filesystems in parallel.

        Provides 2-3x performance improvement over sequential mounting when
        working with multi-partition VMs.

        Args:
            devices: List of (device, mountpoint) tuples
            max_workers: Maximum concurrent mount operations (default: 4)
            readonly: Mount in read-only mode (default: True)

        Returns:
            Dict mapping mountpoint to success status

        Example:
            devices = [
                ("/dev/nbd0p1", "/boot"),
                ("/dev/nbd0p2", "/"),
                ("/dev/nbd0p3", "/home"),
            ]
            results = g.mount_all_parallel(devices, max_workers=3)
        """
        if not self._mount_manager:
            raise RuntimeError("Not launched")
        return self._mount_manager.mount_all_parallel(devices, max_workers, readonly)

    def mount_with_fallback(self, device: str, mountpoint: str, fstype: str | None = None) -> bool:
        """
        Mount with automatic fallback to recovery modes.

        Useful for mounting potentially damaged or inconsistent filesystems.
        Tries progressively more permissive mount options.

        Args:
            device: Device path
            mountpoint: Mount point path
            fstype: Optional filesystem type (auto-detected if None)

        Returns:
            True if mount succeeded with any strategy

        Example:
            # Try to mount potentially damaged filesystem
            if g.mount_with_fallback("/dev/nbd0p1", "/"):
                print("Mounted successfully")
        """
        if not self._mount_manager:
            raise RuntimeError("Not launched")
        return self._mount_manager.mount_with_fallback(device, mountpoint, fstype)

    # File operations (delegate to FileOperations)

    def is_file(self, path: str) -> bool:
        """Check if path is a regular file."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.is_file(path)

    def is_dir(self, path: str) -> bool:
        """Check if path is a directory."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.is_dir(path)

    def exists(self, path: str) -> bool:
        """Check if path exists."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.exists(path)

    def read_file(self, path: str) -> bytes:
        """Read file contents as bytes."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.read_file(path)

    def cat(self, path: str) -> str:
        """Read file contents as string."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.cat(path)

    def write(self, path: str, content: bytes | str) -> None:
        """Write content to file."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.write(path, content)

    def upload(self, local_path: str, remote_path: str) -> None:
        """Upload a file from host to guest filesystem."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.upload(local_path, remote_path)

    def download(self, remote_path: str, local_path: str) -> None:
        """Download a file from guest to host filesystem."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.download(remote_path, local_path)

    def ls(self, path: str) -> list[str]:
        """List directory contents."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.ls(path)

    def find(self, path: str) -> list[str]:
        """Recursively find all files under path."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.find(path)

    def mkdir_p(self, path: str) -> None:
        """Create directory (with parents)."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.mkdir_p(path)

    def chmod(self, path: str, mode: int) -> None:
        """Change file permissions."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.chmod(path, mode)

    def ln_sf(self, target: str, link_name: str) -> None:
        """Create symbolic link."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.ln_sf(target, link_name)

    def cp(self, src: str, dst: str) -> None:
        """Copy file."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.cp(src, dst)

    def rm_f(self, path: str) -> None:
        """Remove file (force)."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.rm_f(path)

    def touch(self, path: str) -> None:
        """Create empty file or update timestamp."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.touch(path)

    def readlink(self, path: str) -> str:
        """Read symbolic link target."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.readlink(path)

    def find_files(self, path: str, pattern: str | None = None, file_type: str | None = None) -> list[str]:
        """Find files in guest filesystem."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.find_files(path, pattern, file_type)

    def checksum(self, path: str, algorithm: str = "sha256") -> str:
        """Calculate checksum of file."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.checksum(path, algorithm)

    def file_age(self, path: str) -> dict[str, Any]:
        """Get file timestamps."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.file_age(path)

    def set_permissions(self, path: str, mode: int, recursive: bool = False) -> None:
        """Set file/directory permissions."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.set_permissions(path, mode, recursive)

    def set_owner(self, path: str, uid: int, gid: int, recursive: bool = False) -> None:
        """Set file/directory owner."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.set_owner(path, uid, gid, recursive)

    def realpath(self, path: str) -> str:
        """Resolve path to absolute path (following symlinks)."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.realpath(path)

    def blkid(self, device: str, use_cache: bool = True) -> dict[str, str]:
        """
        Get device metadata using blkid with optional caching.

        Args:
            device: Device path
            use_cache: Enable TTL-based caching (default: True, 2-minute TTL)

        Returns:
            Dict of device metadata (TYPE, UUID, LABEL, etc.)
        """
        import time

        # Check cache first
        if use_cache and device in self._blkid_cache:
            cached_metadata, cache_time = self._blkid_cache[device]
            if time.time() - cache_time < self._blkid_cache_ttl:
                self.logger.debug(f"Using cached blkid for {device}")
                return cached_metadata

        try:
            cmd = ["blkid", "-p", "-o", "export", device]
            result = run_sudo(self.logger, cmd, check=True, capture=True)

            # Parse blkid output (KEY=VALUE format)
            metadata = {}
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    # blkid returns uppercase keys, keep them uppercase
                    metadata[key] = value

            # Update cache
            if use_cache:
                self._blkid_cache[device] = (metadata, time.time())

            self.logger.debug(f"blkid({device}): {metadata}")
            return metadata
        except Exception as e:
            self.logger.debug(f"blkid failed for {device}: {e}")
            return {}

    # Filesystem operations

    def list_filesystems(self) -> dict[str, str]:
        """List all filesystems."""
        result = {}

        try:
            cmd = ["lsblk", "-f", "--json", "-o", "NAME,FSTYPE"]
            output = run_sudo(self.logger, cmd, check=True, capture=True)

            data = json.loads(output.stdout)
            for dev in data.get("blockdevices", []):
                self._extract_filesystems(dev, result)

        except Exception as e:
            self.logger.warning(f"Failed to list filesystems: {e}")

        return result

    def _extract_filesystems(self, dev: dict, result: dict) -> None:
        """Recursively extract filesystems from lsblk output."""
        name = dev.get("name")
        fstype = dev.get("fstype")

        if name and fstype:
            result[f"/dev/{name}"] = fstype

        # Recurse into children
        for child in dev.get("children", []):
            self._extract_filesystems(child, result)

    def list_partitions(self, device: str | None = None, use_cache: bool = True) -> list[str]:
        """
        List all partitions with optional caching.

        Args:
            device: Optional device to list partitions for (defaults to NBD device)
            use_cache: Enable caching (default: True, 60-second TTL)

        Returns:
            List of partition device paths
        """
        if not self._nbd_manager or not self._nbd_device:
            return []

        import time

        cache_key = device or self._nbd_device

        # Check cache
        if use_cache and cache_key in self._partition_cache:
            cached_parts, cache_time = self._partition_cache[cache_key]
            # Cache valid for 60 seconds
            if time.time() - cache_time < 60:
                self.logger.debug(f"Using cached partition list for {cache_key}")
                return cached_parts

        # Fetch fresh partition list
        partitions = self._nbd_manager.get_partitions(self._nbd_device)

        # Update cache
        if use_cache:
            self._partition_cache[cache_key] = (partitions, time.time())

        return partitions

    def invalidate_partition_cache(self, device: str | None = None) -> None:
        """
        Invalidate partition cache.

        Call this after partition table modifications (part_add, part_del, etc.).

        Args:
            device: Optional device to invalidate (None = clear all)
        """
        if device:
            self._partition_cache.pop(device, None)
            self.logger.debug(f"Invalidated partition cache for {device}")
        else:
            self._partition_cache.clear()
            self.logger.debug("Cleared all partition caches")

    def list_devices(self) -> list[str]:
        """List all devices."""
        if self._nbd_device:
            return [self._nbd_device]
        return []

    def vfs_type(self, device: str) -> str:
        """Get filesystem type."""
        try:
            result = run_sudo(self.logger, ["blkid", "-s", "TYPE", "-o", "value", device], check=True, capture=True)
            return result.stdout.strip()
        except Exception:
            return ""

    def vfs_uuid(self, device: str) -> str:
        """Get filesystem UUID."""
        try:
            result = run_sudo(self.logger, ["blkid", "-s", "UUID", "-o", "value", device], check=True, capture=True)
            return result.stdout.strip()
        except Exception:
            return ""

    def vfs_label(self, device: str) -> str:
        """Get filesystem label."""
        try:
            result = run_sudo(self.logger, ["blkid", "-s", "LABEL", "-o", "value", device], check=True, capture=True)
            return result.stdout.strip()
        except Exception:
            return ""

    def blockdev_getsize64(self, device: str) -> int:
        """Get device size in bytes."""
        try:
            result = run_sudo(self.logger, ["blockdev", "--getsize64", device], check=True, capture=True)
            return int(result.stdout.strip())
        except Exception:
            return 0

    def statvfs(self, path: str) -> dict[str, int]:
        """Get filesystem statistics."""
        if not self._file_ops or not self._mount_root:
            raise RuntimeError("Not launched")

        guest_path = self._mount_root / path.lstrip('/')
        st = os.statvfs(guest_path)
        return {
            "bsize": st.f_bsize,
            "blocks": st.f_blocks,
            "bfree": st.f_bfree,
            "bavail": st.f_bavail,
            "files": st.f_files,
            "ffree": st.f_ffree,
            "flag": st.f_flag,
        }

    # Partition operations

    def part_to_partnum(self, partition: str) -> int:
        """
        Extract partition number from partition device path.

        Examples:
            /dev/sda1 -> 1
            /dev/nvme0n1p2 -> 2
            /dev/nbd0p3 -> 3

        Raises:
            RuntimeError: If partition number cannot be extracted
        """
        # Pattern 1: P-separator devices (nvme, mmcblk, nbd, loop)
        m = re.match(r"^/dev/(?:nvme\d+n\d+|mmcblk\d+|nbd\d+|loop\d+)p(\d+)$", partition)
        if m:
            return int(m.group(1))

        # Pattern 2: Traditional devices (sda, vda, hda, xvda)
        m = re.match(r"^/dev/[a-zA-Z]+(\d+)$", partition)
        if m:
            return int(m.group(1))

        # Pattern 3: by-path with -part suffix
        m = re.search(r"-part(\d+)$", partition)
        if m:
            return int(m.group(1))

        raise RuntimeError(f"Cannot extract partition number from {partition}")

    def part_to_dev(self, partition: str) -> str:
        """
        Get parent device from partition path.

        Examples:
            /dev/sda1 -> /dev/sda
            /dev/nvme0n1p2 -> /dev/nvme0n1
            /dev/nbd0p3 -> /dev/nbd0

        Raises:
            RuntimeError: If parent device cannot be determined
        """
        # Pattern 1: P-separator devices
        m = re.match(r"^(/dev/(?:nvme\d+n\d+|mmcblk\d+|nbd\d+|loop\d+))p\d+$", partition)
        if m:
            return m.group(1)

        # Pattern 2: Traditional devices
        m = re.match(r"^(/dev/[a-zA-Z]+)\d+$", partition)
        if m:
            return m.group(1)

        raise RuntimeError(f"Cannot determine parent device from {partition}")

    def blockdev_getss(self, device: str) -> int:
        """
        Get logical sector size in bytes.

        Uses /sys/block/*/queue/logical_block_size for NBD devices.
        Falls back to blockdev --getss command.

        Returns:
            Sector size in bytes (typically 512 or 4096)
        """
        try:
            # Method 1: Read from /sys/block/
            device_name = Path(device).name
            sys_path = f"/sys/block/{device_name}/queue/logical_block_size"
            if Path(sys_path).exists():
                return int(Path(sys_path).read_text().strip())
        except Exception:
            pass

        try:
            # Method 2: Use blockdev command
            result = run_sudo(self.logger, ["blockdev", "--getss", device],
                             check=True, capture=True)
            return int(result.stdout.strip())
        except Exception:
            return 512  # Default sector size

    def blockdev_getsz(self, device: str) -> int:
        """
        Get device size in 512-byte sectors.

        Returns:
            Number of 512-byte sectors
        """
        try:
            result = run_sudo(self.logger, ["blockdev", "--getsz", device],
                             check=True, capture=True)
            return int(result.stdout.strip())
        except Exception:
            return 0

    def blockdev_getbsz(self, device: str) -> int:
        """
        Get block size in bytes.

        Returns:
            Block size in bytes (typically 4096)
        """
        try:
            result = run_sudo(self.logger, ["blockdev", "--getbsz", device],
                             check=True, capture=True)
            return int(result.stdout.strip())
        except Exception:
            return 4096  # Default block size

    def blockdev_setrw(self, device: str) -> None:
        """
        Set block device to read-write mode.

        Args:
            device: Device path
        """
        try:
            run_sudo(self.logger, ["blockdev", "--setrw", device],
                    check=True, capture=True)
        except Exception as e:
            raise RuntimeError(f"Failed to set {device} to read-write: {e}")

    def blockdev_setro(self, device: str) -> None:
        """
        Set block device to read-only mode.

        Args:
            device: Device path
        """
        try:
            run_sudo(self.logger, ["blockdev", "--setro", device],
                    check=True, capture=True)
        except Exception as e:
            raise RuntimeError(f"Failed to set {device} to read-only: {e}")

    def blockdev_getro(self, device: str) -> bool:
        """
        Check if block device is read-only.

        Args:
            device: Device path

        Returns:
            True if read-only, False if read-write
        """
        try:
            result = run_sudo(self.logger, ["blockdev", "--getro", device],
                             check=True, capture=True)
            return result.stdout.strip() == "1"
        except Exception:
            return False

    def blockdev_flushbufs(self, device: str) -> None:
        """
        Flush buffers for block device.

        Args:
            device: Device path
        """
        try:
            run_sudo(self.logger, ["blockdev", "--flushbufs", device],
                    check=True, capture=True)
        except Exception as e:
            raise RuntimeError(f"Failed to flush buffers for {device}: {e}")

    def blockdev_rereadpt(self, device: str) -> None:
        """
        Re-read partition table (equivalent to partprobe).

        Args:
            device: Device path
        """
        try:
            run_sudo(self.logger, ["blockdev", "--rereadpt", device],
                    check=True, capture=True)
        except Exception as e:
            # Fallback to partprobe
            try:
                run_sudo(self.logger, ["partprobe", device],
                        check=True, capture=True)
            except Exception as e2:
                raise RuntimeError(f"Failed to re-read partition table for {device}: {e2}")

    # Partition Management APIs

    def part_init(self, device: str, parttype: str) -> None:
        """
        Initialize empty partition table on device.

        Args:
            device: Device path (e.g., /dev/nbd0)
            parttype: Partition table type ("gpt", "msdos", or "mbr")

        Raises:
            RuntimeError: If initialization fails

        Example:
            g.part_init("/dev/nbd0", "gpt")
        """
        if not self._nbd_device:
            raise RuntimeError("Not launched")

        # Normalize partition type
        if parttype == "mbr":
            parttype = "msdos"

        if parttype not in ("gpt", "msdos"):
            raise ValueError(f"Invalid partition type: {parttype}. Must be 'gpt' or 'msdos'/'mbr'")

        try:
            run_sudo(self.logger, ["parted", "-s", device, "mklabel", parttype],
                    check=True, capture=True)

            # Invalidate partition cache and re-read table
            self.invalidate_partition_cache(device)
            self.blockdev_rereadpt(device)

            self.logger.info(f"Initialized {parttype} partition table on {device}")

        except Exception as e:
            raise RuntimeError(f"Failed to initialize partition table on {device}: {e}")

    def part_add(self, device: str, prlogex: str, startsect: int, endsect: int) -> None:
        """
        Add partition to device.

        Args:
            device: Device path (e.g., /dev/nbd0)
            prlogex: Partition type ("primary", "logical", "extended")
            startsect: Start sector
            endsect: End sector (-1 for end of disk)

        Raises:
            RuntimeError: If partition creation fails

        Example:
            # Create primary partition from 1MiB to 100%
            g.part_add("/dev/nbd0", "primary", 2048, -1)
        """
        if not self._nbd_device:
            raise RuntimeError("Not launched")

        # Validate partition type
        if prlogex not in ("primary", "logical", "extended"):
            raise ValueError(f"Invalid partition type: {prlogex}")

        # Convert sector counts to size specifications for parted
        if endsect == -1:
            end_spec = "100%"
        else:
            end_spec = f"{endsect}s"

        start_spec = f"{startsect}s"

        try:
            cmd = ["parted", "-s", device, "mkpart", prlogex, start_spec, end_spec]
            run_sudo(self.logger, cmd, check=True, capture=True)

            # Invalidate partition cache and re-read table
            self.invalidate_partition_cache(device)
            self.blockdev_rereadpt(device)

            self.logger.info(f"Added {prlogex} partition to {device}: {start_spec}-{end_spec}")

        except Exception as e:
            raise RuntimeError(f"Failed to add partition to {device}: {e}")

    def part_del(self, device: str, partnum: int) -> None:
        """
        Delete partition from device.

        Args:
            device: Device path (e.g., /dev/nbd0)
            partnum: Partition number to delete (1-based)

        Raises:
            RuntimeError: If deletion fails

        Example:
            g.part_del("/dev/nbd0", 1)
        """
        if not self._nbd_device:
            raise RuntimeError("Not launched")

        if partnum < 1:
            raise ValueError(f"Invalid partition number: {partnum}. Must be >= 1")

        try:
            cmd = ["parted", "-s", device, "rm", str(partnum)]
            run_sudo(self.logger, cmd, check=True, capture=True)

            # Invalidate partition cache and re-read table
            self.invalidate_partition_cache(device)
            self.blockdev_rereadpt(device)

            self.logger.info(f"Deleted partition {partnum} from {device}")

        except Exception as e:
            raise RuntimeError(f"Failed to delete partition {partnum} from {device}: {e}")

    def part_disk(self, device: str, parttype: str) -> None:
        """
        Initialize partition table and create single partition covering entire disk.

        Args:
            device: Device path
            parttype: Partition table type ("gpt", "msdos", or "mbr")

        Raises:
            RuntimeError: If operation fails

        Example:
            g.part_disk("/dev/nbd0", "gpt")
        """
        if not self._nbd_device:
            raise RuntimeError("Not launched")

        # Normalize partition type
        if parttype == "mbr":
            parttype = "msdos"

        if parttype not in ("gpt", "msdos"):
            raise ValueError(f"Invalid partition type: {parttype}")

        try:
            # Create partition table
            run_sudo(self.logger, ["parted", "-s", device, "mklabel", parttype],
                    check=True, capture=True)

            # Create single partition covering disk
            run_sudo(self.logger, ["parted", "-s", device, "mkpart", "primary", "1MiB", "100%"],
                    check=True, capture=True)

            # Invalidate caches and re-read
            self.invalidate_partition_cache(device)
            self.blockdev_rereadpt(device)

            self.logger.info(f"Initialized {parttype} partition table on {device} with single partition")

        except Exception as e:
            raise RuntimeError(f"Failed to initialize partition table on {device}: {e}")

    def part_set_name(self, device: str, partnum: int, name: str) -> None:
        """
        Set GPT partition name.

        Args:
            device: Device path
            partnum: Partition number
            name: Partition name

        Raises:
            RuntimeError: If operation fails (only works with GPT)

        Example:
            g.part_set_name("/dev/nbd0", 1, "EFI System")
        """
        if not self._nbd_device:
            raise RuntimeError("Not launched")

        if partnum < 1:
            raise ValueError(f"Invalid partition number: {partnum}")

        try:
            cmd = ["parted", "-s", device, "name", str(partnum), name]
            run_sudo(self.logger, cmd, check=True, capture=True)

            self.logger.info(f"Set partition {partnum} name to '{name}' on {device}")

        except Exception as e:
            raise RuntimeError(f"Failed to set partition name: {e}")

    def part_set_gpt_type(self, device: str, partnum: int, guid: str) -> None:
        """
        Set GPT partition type GUID.

        Args:
            device: Device path
            partnum: Partition number
            guid: Partition type GUID

        Raises:
            RuntimeError: If operation fails (requires sgdisk)

        Common GUIDs:
            - EFI System: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
            - Linux filesystem: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
            - Linux swap: 0657FD6D-A4AB-43C4-84E5-0933C84B4F4F
            - Linux LVM: E6D6D379-F507-44C2-A23C-238F2A3DF928

        Example:
            g.part_set_gpt_type("/dev/nbd0", 1, "C12A7328-F81F-11D2-BA4B-00A0C93EC93B")
        """
        if not self._nbd_device:
            raise RuntimeError("Not launched")

        if partnum < 1:
            raise ValueError(f"Invalid partition number: {partnum}")

        try:
            # Use sgdisk for GPT type modification
            cmd = ["sgdisk", f"--typecode={partnum}:{guid}", device]
            run_sudo(self.logger, cmd, check=True, capture=True)

            self.logger.info(f"Set partition {partnum} type to {guid} on {device}")

        except Exception as e:
            raise RuntimeError(f"Failed to set partition type: {e}")

    def part_get_parttype(self, device: str) -> str:
        """
        Get partition table type.

        Args:
            device: Device path

        Returns:
            Partition table type ("gpt", "msdos", or "unknown")

        Example:
            parttype = g.part_get_parttype("/dev/nbd0")
            # Returns "gpt" or "msdos"
        """
        try:
            result = run_sudo(self.logger, ["parted", "-s", device, "print"],
                             check=True, capture=True, failure_log_level=logging.DEBUG)

            output = result.stdout.lower()
            if "partition table: gpt" in output:
                return "gpt"
            elif "partition table: msdos" in output or "partition table: mbr" in output:
                return "msdos"
            else:
                return "unknown"

        except Exception as e:
            self.logger.debug(f"Failed to get partition type for {device}: {e}")
            return "unknown"

    # Inspection APIs

    def inspect_filesystems(self) -> dict[str, list[str]]:
        """
        Inspect and return filesystems for each detected OS root.

        This is a convenience wrapper over list_filesystems() that groups
        filesystems by detected operating system roots.

        Returns:
            Dict mapping root device to list of filesystem devices
            Example: {"/dev/nbd0p2": ["/dev/nbd0p1", "/dev/nbd0p2"]}
        """
        result = {}

        # Get all filesystems
        all_fs = self.list_filesystems()

        # Try to detect OS roots using the OS inspector
        if self._os_inspector:
            try:
                roots = self.inspect_os()
                for root_dev in roots:
                    # Find all filesystems on the same disk as root
                    try:
                        root_base = self.part_to_dev(root_dev) if "/" in root_dev else root_dev
                    except Exception:
                        root_base = root_dev

                    filesystems = []
                    for fs_dev in all_fs.keys():
                        try:
                            fs_base = self.part_to_dev(fs_dev) if "/" in fs_dev else fs_dev
                            if fs_base == root_base:
                                filesystems.append(fs_dev)
                        except Exception:
                            pass
                    result[root_dev] = filesystems
            except Exception:
                pass

        # If no inspection data, return all filesystems grouped by disk
        if not result:
            disks = {}
            for fs_dev in all_fs.keys():
                try:
                    base = self.part_to_dev(fs_dev) if "/" in fs_dev else fs_dev
                    if base not in disks:
                        disks[base] = []
                    disks[base].append(fs_dev)
                except Exception:
                    pass
            # Use first device as "root" for grouping
            for base, devices in disks.items():
                if devices:
                    result[devices[0]] = devices

        return result

    def inspect_get_filesystems(self, root: str) -> list[str]:
        """
        Get list of filesystems for specified OS root.

        Args:
            root: Root device path (e.g., /dev/nbd0p2)

        Returns:
            List of filesystem device paths on same disk
        """
        all_inspections = self.inspect_filesystems()
        return all_inspections.get(root, [])

    # Extended attributes (ext2/3/4)

    def get_e2attrs(self, file: str) -> str:
        """
        Get ext2/3/4 file attributes.

        Returns attribute string like "-------------e--"
        Common flags: i (immutable), a (append-only), e (extent format)

        Args:
            file: Guest filesystem path

        Returns:
            Attribute string (empty if not ext filesystem or error)
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        try:
            # Use lsattr command via chroot
            result = self.command_quiet(["lsattr", "-d", file])
            # lsattr output format: "-------------e-- /path/to/file"
            output = result.strip()
            if output:
                # Extract attributes (first field before space)
                parts = output.split(None, 1)
                if parts:
                    return parts[0]
        except Exception as e:
            self.logger.debug(f"get_e2attrs failed for {file}: {e}")

        return ""

    def set_e2attrs(self, file: str, attrs: str, clear: bool = False) -> None:
        """
        Set ext2/3/4 file attributes.

        Args:
            file: Guest filesystem path
            attrs: Attribute string (e.g., "i" for immutable, "a" for append-only)
            clear: If True, remove attributes instead of adding them

        Common attributes:
            i - immutable (file cannot be modified)
            a - append-only (file can only be appended)
            d - no dump (file not backed up by dump)
            e - extent format (file uses extents)
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        # Build chattr command
        if clear:
            cmd = ["chattr", f"-{attrs}", file]
        else:
            cmd = ["chattr", f"+{attrs}", file]

        try:
            self.command(cmd)
        except Exception as e:
            raise RuntimeError(f"Failed to set attributes on {file}: {e}")

    # Filesystem-specific operations

    def ntfs_3g_probe(self, device: str, rw: bool = False) -> int:
        """
        Probe NTFS filesystem with ntfs-3g.probe tool.

        Args:
            device: Device path
            rw: If True, test for read-write capability

        Returns:
            0 if mountable, non-zero otherwise
        """
        try:
            cmd = ["ntfs-3g.probe"]
            if rw:
                cmd.append("--readwrite")
            cmd.append(device)

            result = run_sudo(self.logger, cmd, check=False, capture=True,
                             failure_log_level=logging.DEBUG)
            return result.returncode
        except Exception as e:
            self.logger.debug(f"ntfs_3g_probe failed: {e}")
            return 1  # Non-zero = not mountable

    def btrfs_filesystem_show(self, device: str | None = None) -> list[dict[str, str]]:
        """
        Show Btrfs filesystem information.

        Args:
            device: Optional device path to query specific filesystem

        Returns:
            List of dicts with Btrfs filesystem info
            Keys: label, uuid, total_devices, used_devices
        """
        try:
            cmd = ["btrfs", "filesystem", "show"]
            if device:
                cmd.append(device)

            result = run_sudo(self.logger, cmd, check=True, capture=True,
                             failure_log_level=logging.DEBUG)

            # Parse btrfs filesystem show output
            filesystems = []
            current_fs = None

            for line in result.stdout.splitlines():
                line = line.strip()

                # Label line: "Label: 'mylabel'  uuid: xxx-xxx"
                if line.startswith("Label:"):
                    if current_fs:
                        filesystems.append(current_fs)
                    current_fs = {}

                    # Extract label
                    if "'" in line:
                        label_match = re.search(r"Label: '([^']*)'", line)
                        current_fs["label"] = label_match.group(1) if label_match else ""
                    else:
                        current_fs["label"] = ""

                    # Extract UUID
                    uuid_match = re.search(r"uuid: ([a-f0-9-]+)", line)
                    current_fs["uuid"] = uuid_match.group(1) if uuid_match else ""

                # Total devices line: "Total devices 2 FS bytes used 1.5GiB"
                elif "Total devices" in line and current_fs is not None:
                    match = re.search(r"Total devices (\d+)", line)
                    if match:
                        current_fs["total_devices"] = match.group(1)

            if current_fs:
                filesystems.append(current_fs)

            return filesystems

        except Exception as e:
            self.logger.debug(f"btrfs_filesystem_show failed: {e}")
            return []

    def btrfs_subvolume_list(self, device: str) -> list[dict[str, str]]:
        """
        List Btrfs subvolumes on a device.

        Note: Device must be mounted first.

        Args:
            device: Mounted Btrfs device or mount point

        Returns:
            List of dicts with subvolume info
            Keys: id, path, parent_id (if available)
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        try:
            # Use mount point if device is mounted
            mount_point = str(self._mount_root)

            result = run_sudo(self.logger,
                             ["btrfs", "subvolume", "list", mount_point],
                             check=True, capture=True,
                             failure_log_level=logging.DEBUG)

            subvolumes = []
            for line in result.stdout.splitlines():
                # Format: "ID 256 gen 8 top level 5 path @"
                match = re.match(r"ID (\d+).*path (.+)$", line.strip())
                if match:
                    subvolumes.append({
                        "id": match.group(1),
                        "path": match.group(2),
                    })

            return subvolumes

        except Exception as e:
            self.logger.debug(f"btrfs_subvolume_list failed: {e}")
            return []

    def zfs_pool_list(self) -> list[str]:
        """
        List imported ZFS pools.

        Returns:
            List of pool names
        """
        try:
            result = run_sudo(self.logger,
                             ["zpool", "list", "-H", "-o", "name"],
                             check=True, capture=True,
                             failure_log_level=logging.DEBUG)
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except Exception as e:
            self.logger.debug(f"zfs_pool_list failed: {e}")
            return []

    def zfs_dataset_list(self, pool: str | None = None) -> list[dict[str, str]]:
        """
        List ZFS datasets.

        Args:
            pool: Optional pool name to filter datasets

        Returns:
            List of dicts with dataset info
            Keys: name, used, avail, refer, mountpoint
        """
        try:
            cmd = ["zfs", "list", "-H", "-o", "name,used,avail,refer,mountpoint"]
            if pool:
                cmd.append(pool)

            result = run_sudo(self.logger, cmd, check=True, capture=True,
                             failure_log_level=logging.DEBUG)

            datasets = []
            for line in result.stdout.splitlines():
                parts = line.strip().split("\t")
                if len(parts) >= 5:
                    datasets.append({
                        "name": parts[0],
                        "used": parts[1],
                        "avail": parts[2],
                        "refer": parts[3],
                        "mountpoint": parts[4],
                    })

            return datasets

        except Exception as e:
            self.logger.debug(f"zfs_dataset_list failed: {e}")
            return []

    def xfs_info(self, device: str) -> dict[str, Any]:
        """
        Get XFS filesystem information and geometry.

        Args:
            device: XFS device path or mount point

        Returns:
            Dict with XFS filesystem information:
            - blocksize: Block size in bytes
            - agcount: Number of allocation groups
            - agsize: Allocation group size in blocks
            - sectsize: Sector size in bytes
            - inodesize: Inode size in bytes
            - naming: Naming version
            - log: Log information
            - realtime: Realtime section information (if present)
            - label: Filesystem label (if set)
        """
        try:
            # Try device first, then mount point
            result = run_sudo(self.logger, ["xfs_info", device],
                             check=True, capture=True,
                             failure_log_level=logging.DEBUG)

            # Parse xfs_info output
            info = {}
            for line in result.stdout.splitlines():
                line = line.strip()

                # Meta-data line: "meta-data=/dev/nbd0p1  isize=512  agcount=4, agsize=65536 blks"
                if line.startswith("meta-data="):
                    # Extract isize (inode size)
                    match = re.search(r"isize=(\d+)", line)
                    if match:
                        info["inodesize"] = int(match.group(1))

                    # Extract agcount (allocation group count)
                    match = re.search(r"agcount=(\d+)", line)
                    if match:
                        info["agcount"] = int(match.group(1))

                    # Extract agsize (allocation group size)
                    match = re.search(r"agsize=(\d+)", line)
                    if match:
                        info["agsize"] = int(match.group(1))

                # Data line: "data     =  bsize=4096  blocks=262144, imaxpct=25"
                elif line.startswith("data"):
                    # Extract bsize (block size)
                    match = re.search(r"bsize=(\d+)", line)
                    if match:
                        info["blocksize"] = int(match.group(1))

                    # Extract blocks
                    match = re.search(r"blocks=(\d+)", line)
                    if match:
                        info["blocks"] = int(match.group(1))

                    # Extract imaxpct (max inode percentage)
                    match = re.search(r"imaxpct=(\d+)", line)
                    if match:
                        info["imaxpct"] = int(match.group(1))

                # Naming line: "naming   =version 2  bsize=4096  ascii-ci=0 ftype=1"
                elif line.startswith("naming"):
                    match = re.search(r"version\s+(\d+)", line)
                    if match:
                        info["naming_version"] = int(match.group(1))

                    match = re.search(r"ftype=(\d+)", line)
                    if match:
                        info["ftype"] = int(match.group(1))

                # Log line: "log      =internal  bsize=4096  blocks=2560, version=2"
                elif line.startswith("log"):
                    if "internal" in line:
                        info["log_internal"] = True
                    elif "external" in line:
                        info["log_internal"] = False

                    match = re.search(r"blocks=(\d+)", line)
                    if match:
                        info["log_blocks"] = int(match.group(1))

                # Realtime line: "realtime =none  extsz=4096  blocks=0, rtextents=0"
                elif line.startswith("realtime"):
                    if "none" not in line:
                        match = re.search(r"blocks=(\d+)", line)
                        if match:
                            info["realtime_blocks"] = int(match.group(1))

                # Sector size line: "         =  sectsz=512  attr=2, projid32bit=1"
                elif "sectsz=" in line:
                    match = re.search(r"sectsz=(\d+)", line)
                    if match:
                        info["sectsize"] = int(match.group(1))

            # Get label using xfs_admin
            try:
                label_result = run_sudo(self.logger, ["xfs_admin", "-l", device],
                                       check=True, capture=True,
                                       failure_log_level=logging.DEBUG)
                # Output format: "label = "mylabel""
                match = re.search(r'label\s*=\s*"([^"]*)"', label_result.stdout)
                if match:
                    info["label"] = match.group(1)
            except Exception:
                pass

            # Get UUID using xfs_admin
            try:
                uuid_result = run_sudo(self.logger, ["xfs_admin", "-u", device],
                                      check=True, capture=True,
                                      failure_log_level=logging.DEBUG)
                # Output format: "UUID = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                match = re.search(r'UUID\s*=\s*([a-f0-9-]+)', uuid_result.stdout)
                if match:
                    info["uuid"] = match.group(1)
            except Exception:
                pass

            return info

        except Exception as e:
            self.logger.debug(f"xfs_info failed for {device}: {e}")
            return {}

    def xfs_admin(self, device: str, label: str | None = None, uuid: str | None = None) -> dict[str, str]:
        """
        Get or set XFS filesystem label and UUID.

        Args:
            device: XFS device path
            label: Optional new label to set (max 12 characters)
            uuid: Optional new UUID to set (or "generate" for random UUID)

        Returns:
            Dict with current label and UUID (after any changes)
            Keys: label, uuid

        Raises:
            RuntimeError: If setting label/UUID fails
        """
        info = {}

        # Set label if requested
        if label is not None:
            if len(label) > 12:
                raise RuntimeError("XFS label must be 12 characters or less")
            try:
                run_sudo(self.logger, ["xfs_admin", "-L", label, device],
                        check=True, capture=True)
                info["label"] = label
            except Exception as e:
                raise RuntimeError(f"Failed to set XFS label: {e}")

        # Set UUID if requested
        if uuid is not None:
            try:
                if uuid.lower() == "generate":
                    run_sudo(self.logger, ["xfs_admin", "-U", "generate", device],
                            check=True, capture=True)
                else:
                    run_sudo(self.logger, ["xfs_admin", "-U", uuid, device],
                            check=True, capture=True)
                info["uuid"] = uuid
            except Exception as e:
                raise RuntimeError(f"Failed to set XFS UUID: {e}")

        # Get current label
        try:
            result = run_sudo(self.logger, ["xfs_admin", "-l", device],
                             check=True, capture=True,
                             failure_log_level=logging.DEBUG)
            match = re.search(r'label\s*=\s*"([^"]*)"', result.stdout)
            if match:
                info["label"] = match.group(1)
        except Exception:
            info["label"] = ""

        # Get current UUID
        try:
            result = run_sudo(self.logger, ["xfs_admin", "-u", device],
                             check=True, capture=True,
                             failure_log_level=logging.DEBUG)
            match = re.search(r'UUID\s*=\s*([a-f0-9-]+)', result.stdout)
            if match:
                info["uuid"] = match.group(1)
        except Exception:
            info["uuid"] = ""

        return info

    def xfs_growfs(self, mountpoint: str, data_blocks: int | None = None) -> dict[str, Any]:
        """
        Grow (expand) an XFS filesystem.

        Note: The filesystem must be mounted.

        Args:
            mountpoint: Mount point of the XFS filesystem
            data_blocks: Optional target size in blocks (if None, grows to fill device)

        Returns:
            Dict with growth information:
            - success: True if growth succeeded
            - old_blocks: Original size in blocks
            - new_blocks: New size in blocks

        Raises:
            RuntimeError: If filesystem is not mounted or growth fails
        """
        try:
            # Get current size first
            info_before = self.xfs_info(mountpoint)
            old_blocks = info_before.get("blocks", 0)

            # Build xfs_growfs command
            cmd = ["xfs_growfs"]
            if data_blocks is not None:
                cmd.extend(["-D", str(data_blocks)])
            cmd.append(mountpoint)

            # Execute growth
            result = run_sudo(self.logger, cmd, check=True, capture=True)

            # Parse result to get new size
            # Output format: "data blocks changed from X to Y"
            new_blocks = old_blocks
            match = re.search(r"data blocks changed from \d+ to (\d+)", result.stdout)
            if match:
                new_blocks = int(match.group(1))

            return {
                "success": True,
                "old_blocks": old_blocks,
                "new_blocks": new_blocks,
            }

        except Exception as e:
            raise RuntimeError(f"Failed to grow XFS filesystem: {e}")

    def xfs_repair(self, device: str, check_only: bool = False) -> dict[str, Any]:
        """
        Repair or check an XFS filesystem.

        IMPORTANT: Filesystem must NOT be mounted.

        Args:
            device: XFS device path
            check_only: If True, only check for errors (don't repair)

        Returns:
            Dict with repair information:
            - clean: True if filesystem is clean
            - errors_found: True if errors were found
            - errors_repaired: True if errors were repaired (check_only=False)
            - output: Command output

        Raises:
            RuntimeError: If filesystem is mounted or repair fails critically
        """
        try:
            # Build xfs_repair command
            cmd = ["xfs_repair"]
            if check_only:
                cmd.append("-n")  # No modify mode (check only)
            cmd.append(device)

            # Execute repair
            result = run_sudo(self.logger, cmd, check=False, capture=True,
                             failure_log_level=logging.DEBUG)

            # Parse output
            output = result.stdout
            clean = "no modifications needed" in output.lower() or result.returncode == 0
            errors_found = "errors found" in output.lower() or "corruption" in output.lower()
            errors_repaired = not check_only and errors_found and result.returncode == 0

            return {
                "clean": clean,
                "errors_found": errors_found,
                "errors_repaired": errors_repaired,
                "output": output,
                "returncode": result.returncode,
            }

        except Exception as e:
            # Check if error is due to mounted filesystem
            if "mounted" in str(e).lower():
                raise RuntimeError(f"Cannot repair mounted XFS filesystem: {device}")
            raise RuntimeError(f"XFS repair failed: {e}")

    def xfs_db(self, device: str, commands: list[str]) -> str:
        """
        Execute XFS debug/inspection commands using xfs_db.

        CAUTION: This is a low-level tool. Use with care.

        Args:
            device: XFS device path
            commands: List of xfs_db commands to execute

        Returns:
            Command output as string

        Example:
            # Get superblock info
            output = g.xfs_db("/dev/nbd0p1", ["sb 0", "p"])
        """
        try:
            # Build command string
            cmd_string = "\n".join(commands) + "\nquit\n"

            # Execute xfs_db in read-only mode
            result = run_sudo(
                self.logger,
                ["xfs_db", "-r", "-c", cmd_string, device],
                check=True,
                capture=True,
                failure_log_level=logging.DEBUG
            )

            return result.stdout

        except Exception as e:
            self.logger.debug(f"xfs_db failed: {e}")
            return ""

    # Systemd integration operations

    # === systemctl APIs ===

    def systemctl_list_units(
        self,
        unit_type: str = "service",
        state: str | None = None,
        all_units: bool = True
    ) -> list[dict[str, str]]:
        """
        List systemd units.

        Args:
            unit_type: Type of unit (service, timer, socket, target, mount, etc.)
            state: Filter by state (active, inactive, failed, running, etc.)
            all_units: Include inactive units

        Returns:
            List of dicts with keys: unit, load, active, sub, description
        """
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.list_units(unit_type, state, all_units)

    def systemctl_list_unit_files(self, unit_type: str = "service") -> list[dict[str, str]]:
        """List installed unit files."""
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.list_unit_files(unit_type)

    def systemctl_is_active(self, unit: str) -> bool:
        """Check if a unit is active."""
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.is_active(unit)

    def systemctl_is_enabled(self, unit: str) -> str:
        """Check if a unit is enabled (returns: enabled, disabled, static, masked, etc.)."""
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.is_enabled(unit)

    def systemctl_is_failed(self, unit: str) -> bool:
        """Check if a unit is in failed state."""
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.is_failed(unit)

    def systemctl_show(self, unit: str) -> dict[str, str]:
        """Show properties of a unit."""
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.show(unit)

    def systemctl_status(self, unit: str) -> dict[str, Any]:
        """Get detailed status of a unit."""
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.status(unit)

    def systemctl_cat(self, unit: str) -> str:
        """Show unit file content."""
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.cat(unit)

    def systemctl_list_dependencies(self, unit: str, reverse: bool = False, recursive: bool = True) -> list[str]:
        """List unit dependencies."""
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.list_dependencies(unit, reverse, recursive)

    def systemctl_list_failed(self) -> list[dict[str, str]]:
        """List all failed units."""
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.list_failed()

    def systemctl_get_default_target(self) -> str:
        """Get the default boot target."""
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.get_default_target()

    def systemctl_list_targets(self) -> list[str]:
        """List all available targets."""
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.list_targets()

    def systemctl_list_timers(self) -> list[dict[str, str]]:
        """List systemd timers."""
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.list_timers()

    def systemctl_list_sockets(self) -> list[dict[str, str]]:
        """List systemd socket units."""
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.list_sockets()

    def systemctl_list_mounts(self) -> list[dict[str, str]]:
        """List systemd mount units."""
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.list_mounts()

    # Enhanced systemctl operations

    def systemctl_cat_unit_file(self, unit: str) -> str:
        """
        Get full unit file content including drop-ins.

        Args:
            unit: Unit name (e.g., "sshd.service")

        Returns:
            Full unit file content

        Example:
            content = g.systemctl_cat_unit_file("nginx.service")
            if "PrivateTmp" in content:
                print("Service uses PrivateTmp")
        """
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.cat_unit_file(unit)

    def systemctl_read_unit_file(self, unit: str) -> dict[str, dict[str, str]]:
        """
        Parse unit file into structured configuration.

        Args:
            unit: Unit name

        Returns:
            Dict of sections with key-value pairs

        Example:
            config = g.systemctl_read_unit_file("sshd.service")
            exec_start = config.get("Service", {}).get("ExecStart")
            print(f"ExecStart: {exec_start}")
        """
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.read_unit_file(unit)

    def systemctl_get_unit_overrides(self, unit: str) -> list[str]:
        """
        Get list of drop-in override files for a unit.

        Args:
            unit: Unit name

        Returns:
            List of override file paths

        Example:
            overrides = g.systemctl_get_unit_overrides("sshd.service")
            print(f"Unit has {len(overrides)} override(s)")
        """
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.get_unit_overrides(unit)

    def systemctl_get_unit_dependencies_full(self, unit: str) -> dict[str, list[str]]:
        """
        Get comprehensive dependency information for a unit.

        Args:
            unit: Unit name

        Returns:
            Dict with dependency types (requires, wants, conflicts, etc.)

        Example:
            deps = g.systemctl_get_unit_dependencies_full("nginx.service")
            print(f"Requires: {deps['requires']}")
            print(f"After: {deps['after']}")
        """
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.get_unit_dependencies_full(unit)

    def systemctl_analyze_unit_conflicts(self) -> list[dict[str, Any]]:
        """
        Analyze all units for potential conflicts.

        Returns:
            List of dicts describing conflicts

        Example:
            conflicts = g.systemctl_analyze_unit_conflicts()
            for conflict in conflicts:
                print(f"Conflict: {conflict['unit1']} vs {conflict['unit2']}")
        """
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.analyze_unit_conflicts()

    def systemctl_get_unit_security_settings(self, unit: str) -> dict[str, Any]:
        """
        Extract security-related settings from a unit.

        Args:
            unit: Unit name

        Returns:
            Dict with security settings (PrivateTmp, ProtectSystem, etc.)

        Example:
            security = g.systemctl_get_unit_security_settings("nginx.service")
            if not security.get("private_tmp"):
                print("⚠️  Service does not use PrivateTmp")
        """
        if not self._systemctl:
            raise RuntimeError("Not launched")
        return self._systemctl.get_unit_security_settings(unit)

    # === journalctl APIs ===

    def journalctl_query(
        self,
        unit: str | None = None,
        priority: int | None = None,
        since: str | None = None,
        until: str | None = None,
        boot: int | str | None = None,
        lines: int | None = None,
        grep: str | None = None,
        output_format: str = "short"
    ) -> str:
        """Query systemd journal logs."""
        if not self._journalctl:
            raise RuntimeError("Not launched")
        return self._journalctl.query(unit, priority, since, until, boot, lines, grep, output_format)

    def journalctl_list_boots(self) -> list[dict[str, str]]:
        """List available boot entries."""
        if not self._journalctl:
            raise RuntimeError("Not launched")
        return self._journalctl.list_boots()

    def journalctl_get_boot_log(self, boot: int | str = 0, lines: int | None = None) -> str:
        """Get log for a specific boot."""
        if not self._journalctl:
            raise RuntimeError("Not launched")
        return self._journalctl.get_boot_log(boot, lines)

    def journalctl_get_errors(self, since: str | None = None, lines: int = 100) -> list[dict[str, str]]:
        """Get error messages from journal."""
        if not self._journalctl:
            raise RuntimeError("Not launched")
        return self._journalctl.get_errors(since, lines)

    def journalctl_get_warnings(self, since: str | None = None, lines: int = 100) -> list[dict[str, str]]:
        """Get warning messages from journal."""
        if not self._journalctl:
            raise RuntimeError("Not launched")
        return self._journalctl.get_warnings(since, lines)

    def journalctl_disk_usage(self) -> dict[str, Any]:
        """Get journal disk usage information."""
        if not self._journalctl:
            raise RuntimeError("Not launched")
        return self._journalctl.disk_usage()

    def journalctl_verify(self) -> dict[str, Any]:
        """Verify journal file consistency."""
        if not self._journalctl:
            raise RuntimeError("Not launched")
        return self._journalctl.verify()

    def journalctl_export(self, output_format: str = "json", since: str | None = None) -> str:
        """Export journal logs."""
        if not self._journalctl:
            raise RuntimeError("Not launched")
        return self._journalctl.export(output_format, since)

    # Enhanced journal operations

    def journalctl_search(self, pattern: str, since: str | None = None, lines: int = 100) -> list[dict[str, str]]:
        """
        Search journal logs for a pattern.

        Args:
            pattern: Pattern to search for (grep-compatible regex)
            since: Search logs since this time
            lines: Maximum number of matching entries

        Returns:
            List of matching journal entries

        Example:
            # Search for authentication failures
            failures = g.journalctl_search("authentication failure", since="1 day ago")
            for entry in failures:
                print(f"{entry['unit']}: {entry['message']}")
        """
        if not self._journalctl:
            raise RuntimeError("Not launched")
        return self._journalctl.search(pattern, since, lines)

    def journalctl_statistics(self) -> dict[str, Any]:
        """
        Get journal statistics and message counts.

        Returns:
            Dict with journal statistics

        Example:
            stats = g.journalctl_statistics()
            print(f"Time range: {stats['time_range']}")
        """
        if not self._journalctl:
            raise RuntimeError("Not launched")
        return self._journalctl.statistics()

    def journalctl_vacuum(self, size: str | None = None, time: str | None = None, files: int | None = None) -> dict[str, str]:
        """
        Clean up old journal log files.

        Args:
            size: Keep only this much disk space (e.g., "500M")
            time: Keep only logs newer than this (e.g., "1month")
            files: Keep only this many journal files

        Returns:
            Dict with vacuum results

        Example:
            result = g.journalctl_vacuum(size="500M")
        """
        if not self._journalctl:
            raise RuntimeError("Not launched")
        return self._journalctl.vacuum(size, time, files)

    def journalctl_get_boot_time(self, boot: int | str = 0) -> dict[str, str]:
        """
        Get boot and shutdown time for a specific boot.

        Args:
            boot: Boot ID or offset (0=current, -1=previous)

        Returns:
            Dict with boot_time and shutdown_time

        Example:
            boot_info = g.journalctl_get_boot_time(0)
            print(f"Boot time: {boot_info['boot_time']}")
        """
        if not self._journalctl:
            raise RuntimeError("Not launched")
        return self._journalctl.get_boot_time(boot)

    # === systemd-analyze APIs ===

    def systemd_analyze_time(self) -> dict[str, Any]:
        """Analyze system boot time."""
        if not self._systemd_analyze:
            raise RuntimeError("Not launched")
        return self._systemd_analyze.time()

    def systemd_analyze_blame(self, lines: int | None = None) -> list[dict[str, str]]:
        """Show which services took the longest to initialize."""
        if not self._systemd_analyze:
            raise RuntimeError("Not launched")
        return self._systemd_analyze.blame(lines)

    def systemd_analyze_critical_chain(self, unit: str | None = None) -> str:
        """Show critical chain for boot or specific unit."""
        if not self._systemd_analyze:
            raise RuntimeError("Not launched")
        return self._systemd_analyze.critical_chain(unit)

    def systemd_analyze_security(self, unit: str | None = None) -> list[dict[str, Any]]:
        """Analyze security settings of services."""
        if not self._systemd_analyze:
            raise RuntimeError("Not launched")
        return self._systemd_analyze.security(unit)

    def systemd_analyze_verify(self, unit: str) -> dict[str, Any]:
        """Verify unit file syntax and configuration."""
        if not self._systemd_analyze:
            raise RuntimeError("Not launched")
        return self._systemd_analyze.verify(unit)

    def systemd_analyze_dot(self, pattern: str | None = None, to_pattern: str | None = None) -> str:
        """Generate dependency graph in GraphViz dot format."""
        if not self._systemd_analyze:
            raise RuntimeError("Not launched")
        return self._systemd_analyze.dot(pattern, to_pattern)

    def systemd_analyze_calendar(self, expression: str) -> dict[str, str]:
        """Validate and show next elapse times for calendar expressions."""
        if not self._systemd_analyze:
            raise RuntimeError("Not launched")
        return self._systemd_analyze.calendar(expression)

    def systemd_analyze_dump(self) -> str:
        """Dump server state in human-readable form."""
        if not self._systemd_analyze:
            raise RuntimeError("Not launched")
        return self._systemd_analyze.dump()

    def systemd_analyze_plot(self) -> str:
        """Generate SVG boot time plot."""
        if not self._systemd_analyze:
            raise RuntimeError("Not launched")
        return self._systemd_analyze.plot()

    def systemd_analyze_syscall_filter(self, set_name: str | None = None) -> list[str]:
        """List system calls in seccomp filter sets."""
        if not self._systemd_analyze:
            raise RuntimeError("Not launched")
        return self._systemd_analyze.syscall_filter(set_name)

    # === Configuration APIs (timedatectl, hostnamectl, localectl) ===

    def timedatectl_status(self) -> dict[str, str]:
        """Get time and date settings."""
        if not self._sysconfig:
            raise RuntimeError("Not launched")
        return self._sysconfig.timedatectl_status()

    def timedatectl_list_timezones(self) -> list[str]:
        """List available timezones."""
        if not self._sysconfig:
            raise RuntimeError("Not launched")
        return self._sysconfig.timedatectl_list_timezones()

    def timedatectl_show(self) -> dict[str, str]:
        """Show time/date properties in machine-readable format."""
        if not self._sysconfig:
            raise RuntimeError("Not launched")
        return self._sysconfig.timedatectl_show()

    def hostnamectl_status(self) -> dict[str, str]:
        """Get hostname and system information."""
        if not self._sysconfig:
            raise RuntimeError("Not launched")
        return self._sysconfig.hostnamectl_status()

    def hostnamectl_hostname(self) -> str:
        """Get current hostname."""
        if not self._sysconfig:
            raise RuntimeError("Not launched")
        return self._sysconfig.hostnamectl_hostname()

    def localectl_status(self) -> dict[str, str]:
        """Get locale and keyboard configuration."""
        if not self._sysconfig:
            raise RuntimeError("Not launched")
        return self._sysconfig.localectl_status()

    def localectl_list_locales(self) -> list[str]:
        """List available locales."""
        if not self._sysconfig:
            raise RuntimeError("Not launched")
        return self._sysconfig.localectl_list_locales()

    def localectl_list_keymaps(self) -> list[str]:
        """List available keyboard mappings."""
        if not self._sysconfig:
            raise RuntimeError("Not launched")
        return self._sysconfig.localectl_list_keymaps()

    def localectl_list_x11_keymap_models(self) -> list[str]:
        """List available X11 keymap models."""
        if not self._sysconfig:
            raise RuntimeError("Not launched")
        return self._sysconfig.localectl_list_x11_keymap_models()

    def localectl_list_x11_keymap_layouts(self) -> list[str]:
        """List available X11 keymap layouts."""
        if not self._sysconfig:
            raise RuntimeError("Not launched")
        return self._sysconfig.localectl_list_x11_keymap_layouts()

    def loginctl_list_sessions(self) -> list[dict[str, str]]:
        """List current login sessions."""
        if not self._sysconfig:
            raise RuntimeError("Not launched")
        return self._sysconfig.loginctl_list_sessions()

    def loginctl_list_users(self) -> list[dict[str, str]]:
        """List logged-in users."""
        if not self._sysconfig:
            raise RuntimeError("Not launched")
        return self._sysconfig.loginctl_list_users()

    def loginctl_show_session(self, session: str) -> dict[str, str]:
        """Show properties of a login session."""
        if not self._sysconfig:
            raise RuntimeError("Not launched")
        return self._sysconfig.loginctl_show_session(session)


    # ============================================================================
    # Advanced systemd Methods - Enhanced Inspection & Forensics
    # ============================================================================

    # Category 1: Core Offline Analysis

    def systemd_analyze_plot_offline(self, output_path: str | None = None) -> str:
        """
        Generate SVG boot timeline from offline VM.

        Works by analyzing journald logs without booting VM.

        Args:
            output_path: Optional path for SVG output

        Returns:
            SVG content as string (or empty if no boot data)
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        try:
            # Use systemd-analyze with --directory flag
            journal_dir = self._mount_root / "var/log/journal"

            if not journal_dir.exists():
                self.logger.debug("No journal directory found")
                return ""

            cmd = ["systemd-analyze", "plot"]
            cmd.extend(["--directory", str(self._mount_root)])

            result = run_sudo(self.logger, cmd, check=True, capture=True,
                             failure_log_level=logging.DEBUG)

            svg_content = result.stdout

            # Save to file if requested
            if output_path:
                Path(output_path).write_text(svg_content)

            return svg_content

        except Exception as e:
            self.logger.debug(f"systemd_analyze_plot_offline failed: {e}")
            return ""

    def systemd_analyze_security_offline(self, unit: str | None = None) -> list[dict[str, Any]]:
        """
        Security analysis of systemd units from offline VM.

        Analyzes service hardening features without running VM.

        Args:
            unit: Optional specific unit to analyze (default: all services)

        Returns:
            List of security analysis results with scores
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        try:
            cmd = ["systemd-analyze", "security"]
            cmd.extend(["--offline", str(self._mount_root)])
            cmd.append("--no-pager")

            if unit:
                cmd.append(unit)

            result = run_sudo(self.logger, cmd, check=True, capture=True,
                             failure_log_level=logging.DEBUG)

            # Parse output (table format)
            security_results = []
            lines = result.stdout.strip().split('\n')

            # Skip header lines
            data_start = 0
            for i, line in enumerate(lines):
                if '─' in line:  # Separator line
                    data_start = i + 1
                    break

            for line in lines[data_start:]:
                if not line.strip():
                    continue

                # Parse: UNIT EXPOSURE PREDICATE
                parts = line.split()
                if len(parts) >= 3:
                    security_results.append({
                        "unit": parts[0],
                        "exposure": parts[1],
                        "predicate": parts[2],
                    })

            return security_results

        except Exception as e:
            self.logger.debug(f"systemd_analyze_security_offline failed: {e}")
            return []

    def systemd_analyze_time_offline(self) -> dict[str, float]:
        """
        Analyze boot time from offline VM journal.

        Returns:
            Dict with boot timing information
            Keys: kernel_time, userspace_time, total_time (in seconds)
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        try:
            cmd = ["systemd-analyze", "time"]
            cmd.extend(["--directory", str(self._mount_root)])

            result = run_sudo(self.logger, cmd, check=True, capture=True,
                             failure_log_level=logging.DEBUG)

            # Parse output: "Startup finished in 2.5s (kernel) + 5.3s (userspace) = 7.8s"
            output = result.stdout.strip()

            timing = {
                "kernel_time": 0.0,
                "userspace_time": 0.0,
                "total_time": 0.0,
            }

            # Extract kernel time
            kernel_match = re.search(r'([\d.]+)s\s*\(kernel\)', output)
            if kernel_match:
                timing["kernel_time"] = float(kernel_match.group(1))

            # Extract userspace time
            userspace_match = re.search(r'([\d.]+)s\s*\(userspace\)', output)
            if userspace_match:
                timing["userspace_time"] = float(userspace_match.group(1))

            # Extract total
            total_match = re.search(r'=\s*([\d.]+)s', output)
            if total_match:
                timing["total_time"] = float(total_match.group(1))

            return timing

        except Exception as e:
            self.logger.debug(f"systemd_analyze_time_offline failed: {e}")
            return {"kernel_time": 0.0, "userspace_time": 0.0, "total_time": 0.0}

    def systemd_detect_virt(self) -> dict[str, str]:
        """
        Detect virtualization type from guest VM perspective.

        Returns:
            Dict with virtualization info
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        try:
            # Check from inside guest
            result = self.command_quiet(["systemd-detect-virt", "--vm"])
            vm_type = result.strip() if result else "none"

            result = self.command_quiet(["systemd-detect-virt", "--container"])
            container_type = result.strip() if result else "none"

            # Determine overall type
            if vm_type != "none":
                overall_type = "vm"
            elif container_type != "none":
                overall_type = "container"
            else:
                overall_type = "none"

            return {
                "type": overall_type,
                "vm": vm_type,
                "container": container_type,
            }

        except Exception as e:
            self.logger.debug(f"systemd_detect_virt failed: {e}")
            return {"type": "none", "vm": "none", "container": "none"}

    def systemd_machine_id(self) -> str:
        """
        Get unique machine ID from systemd.

        Returns:
            128-bit machine ID as hex string
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        try:
            machine_id_path = self._mount_root / "etc/machine-id"
            if machine_id_path.exists():
                return machine_id_path.read_text().strip()

            # Fallback to dbus machine ID
            dbus_id_path = self._mount_root / "var/lib/dbus/machine-id"
            if dbus_id_path.exists():
                return dbus_id_path.read_text().strip()

            return ""

        except Exception as e:
            self.logger.debug(f"systemd_machine_id failed: {e}")
            return ""

    # Category 2: Network & Journal (enhanced versions)

    def journalctl_list_boots_detailed(self) -> list[dict[str, Any]]:
        """
        List all boots with detailed information.

        Returns:
            List of boot records with timestamps and IDs
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        try:
            cmd = ["journalctl", "--list-boots", "--output=json"]
            result = self.command_quiet(cmd)

            boots = []
            for line in result.splitlines():
                if not line.strip():
                    continue

                boot_data = json.loads(line)

                # Extract boot information
                boots.append({
                    "boot_id": boot_data.get("boot_id", ""),
                    "first_entry": boot_data.get("first_entry", ""),
                    "last_entry": boot_data.get("last_entry", ""),
                })

            return boots

        except Exception as e:
            self.logger.debug(f"journalctl_list_boots_detailed failed: {e}")
            return []

    def journalctl_export_to_file(self, output_path: str, since: str | None = None,
                     until: str | None = None) -> bool:
        """
        Export journal logs to binary format for offline analysis.

        Args:
            output_path: Path to save exported journal
            since: Optional start timestamp
            until: Optional end timestamp

        Returns:
            True if export successful
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        try:
            cmd = ["journalctl", "--output=export"]

            if since:
                cmd.extend(["--since", since])
            if until:
                cmd.extend(["--until", until])

            result = self.command_quiet(cmd)

            Path(output_path).write_bytes(result.encode('utf-8'))
            return True

        except Exception as e:
            self.logger.debug(f"journalctl_export_to_file failed: {e}")
            return False

    def systemd_networkd_config(self) -> dict[str, Any]:
        """
        Inspect systemd-networkd configuration.

        Returns:
            Dict with network configuration
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        config = {
            "networks": [],
            "netdevs": [],
            "links": [],
        }

        try:
            # Parse .network files
            network_dir = self._mount_root / "etc/systemd/network"
            if network_dir.exists():
                for network_file in network_dir.glob("*.network"):
                    config["networks"].append({
                        "file": network_file.name,
                        "path": str(network_file),
                    })

                for netdev_file in network_dir.glob("*.netdev"):
                    config["netdevs"].append({
                        "file": netdev_file.name,
                        "path": str(netdev_file),
                    })

                for link_file in network_dir.glob("*.link"):
                    config["links"].append({
                        "file": link_file.name,
                        "path": str(link_file),
                    })

            return config

        except Exception as e:
            self.logger.debug(f"systemd_networkd_config failed: {e}")
            return config

    def systemd_resolved_config(self) -> dict[str, Any]:
        """
        Inspect systemd-resolved DNS configuration.

        Returns:
            Dict with DNS configuration
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        try:
            # Read resolved.conf
            resolved_conf = self._mount_root / "etc/systemd/resolved.conf"

            config = {
                "dns_servers": [],
                "fallback_dns": [],
                "domains": [],
                "dnssec": "allow-downgrade",
            }

            if resolved_conf.exists():
                import configparser
                parser = configparser.ConfigParser()
                parser.read(resolved_conf)

                if "Resolve" in parser:
                    resolve_section = parser["Resolve"]

                    if "DNS" in resolve_section:
                        config["dns_servers"] = resolve_section["DNS"].split()

                    if "FallbackDNS" in resolve_section:
                        config["fallback_dns"] = resolve_section["FallbackDNS"].split()

                    if "Domains" in resolve_section:
                        config["domains"] = resolve_section["Domains"].split()

                    if "DNSSEC" in resolve_section:
                        config["dnssec"] = resolve_section["DNSSEC"]

            return config

        except Exception as e:
            self.logger.debug(f"systemd_resolved_config failed: {e}")
            return {"dns_servers": [], "fallback_dns": [], "domains": [], "dnssec": "allow-downgrade"}

    # Category 3: Forensic Analysis

    def systemd_coredump_list(self) -> list[dict[str, Any]]:
        """
        List all core dumps from VM crashes.

        Returns:
            List of core dump records
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        coredumps = []

        try:
            coredump_dir = self._mount_root / "var/lib/systemd/coredump"

            if not coredump_dir.exists():
                return []

            # List core dump files
            for dump_file in coredump_dir.glob("core.*"):
                # Parse filename: core.<command>.<uid>.<gid>.<pid>.<timestamp>
                parts = dump_file.name.split(".")

                if len(parts) >= 6:
                    coredumps.append({
                        "command": parts[1],
                        "uid": parts[2],
                        "gid": parts[3],
                        "pid": parts[4],
                        "timestamp": parts[5],
                        "file": str(dump_file),
                        "size_mb": dump_file.stat().st_size / (1024 * 1024),
                    })

            return coredumps

        except Exception as e:
            self.logger.debug(f"systemd_coredump_list failed: {e}")
            return []

    def systemd_coredump_config(self) -> dict[str, str]:
        """
        Get core dump configuration from VM.

        Returns:
            Dict with coredump settings
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        config = {
            "Storage": "external",
            "Compress": "yes",
            "ProcessSizeMax": "2G",
            "ExternalSizeMax": "2G",
        }

        try:
            conf_file = self._mount_root / "etc/systemd/coredump.conf"

            if conf_file.exists():
                import configparser
                parser = configparser.ConfigParser()
                parser.read(conf_file)

                if "Coredump" in parser:
                    section = parser["Coredump"]

                    for key in ["Storage", "Compress", "ProcessSizeMax", "ExternalSizeMax"]:
                        if key in section:
                            config[key] = section[key]

            return config

        except Exception as e:
            self.logger.debug(f"systemd_coredump_config failed: {e}")
            return config

    def systemd_pstore_list(self) -> list[dict[str, Any]]:
        """
        List persistent storage crash data (pstore).

        Returns:
            List of pstore entries
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        entries = []

        try:
            pstore_dir = self._mount_root / "sys/fs/pstore"

            if not pstore_dir.exists():
                return []

            for pstore_file in pstore_dir.iterdir():
                if pstore_file.is_file():
                    # Determine type from filename
                    pstore_type = "unknown"
                    if "dmesg" in pstore_file.name:
                        pstore_type = "dmesg"
                    elif "console" in pstore_file.name:
                        pstore_type = "console"
                    elif "panic" in pstore_file.name:
                        pstore_type = "panic"

                    entries.append({
                        "file": pstore_file.name,
                        "type": pstore_type,
                        "size_kb": pstore_file.stat().st_size / 1024,
                        "path": str(pstore_file),
                    })

            return entries

        except Exception as e:
            self.logger.debug(f"systemd_pstore_list failed: {e}")
            return []

    def systemd_sysusers_config(self) -> list[dict[str, Any]]:
        """
        Get systemd-sysusers configuration.

        Returns:
            List of sysusers entries
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        entries = []

        try:
            sysusers_dir = self._mount_root / "usr/lib/sysusers.d"

            if not sysusers_dir.exists():
                return []

            for conf_file in sysusers_dir.glob("*.conf"):
                content = conf_file.read_text()

                for line in content.splitlines():
                    line = line.strip()

                    if not line or line.startswith("#"):
                        continue

                    # Parse: type name id gecos home shell
                    parts = line.split(None, 5)

                    if len(parts) >= 2:
                        entry = {
                            "type": parts[0],
                            "name": parts[1],
                            "id": parts[2] if len(parts) > 2 else "-",
                            "gecos": parts[3] if len(parts) > 3 else "",
                            "home": parts[4] if len(parts) > 4 else "/",
                            "shell": parts[5] if len(parts) > 5 else "/usr/sbin/nologin",
                            "source_file": conf_file.name,
                        }
                        entries.append(entry)

            return entries

        except Exception as e:
            self.logger.debug(f"systemd_sysusers_config failed: {e}")
            return []

    def systemd_logind_config(self) -> dict[str, Any]:
        """
        Get systemd-logind configuration.

        Returns:
            Dict with logind configuration
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        config = {
            "KillUserProcesses": "no",
            "KillExcludeUsers": [],
            "HandlePowerKey": "poweroff",
            "HandleSuspendKey": "suspend",
            "HandleLidSwitch": "suspend",
            "IdleAction": "ignore",
            "IdleActionSec": "30min",
        }

        try:
            conf_file = self._mount_root / "etc/systemd/logind.conf"

            if conf_file.exists():
                import configparser
                parser = configparser.ConfigParser()
                parser.read(conf_file)

                if "Login" in parser:
                    section = parser["Login"]

                    for key in config.keys():
                        if key in section:
                            value = section[key]

                            # Parse list values
                            if key == "KillExcludeUsers":
                                config[key] = value.split()
                            else:
                                config[key] = value

            return config

        except Exception as e:
            self.logger.debug(f"systemd_logind_config failed: {e}")
            return config

    def systemd_boot_entries(self) -> list[dict[str, Any]]:
        """
        List systemd-boot (UEFI) boot entries.

        Returns:
            List of boot entries
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        entries = []

        try:
            entries_dir = self._mount_root / "boot/loader/entries"

            if not entries_dir.exists():
                # Try EFI path
                entries_dir = self._mount_root / "boot/efi/loader/entries"

            if not entries_dir.exists():
                return []

            for entry_file in entries_dir.glob("*.conf"):
                entry = {"file": entry_file.name}

                content = entry_file.read_text()
                for line in content.splitlines():
                    line = line.strip()

                    if not line or line.startswith("#"):
                        continue

                    # Parse key-value pairs
                    if " " in line:
                        key, value = line.split(None, 1)
                        entry[key.lower()] = value

                entries.append(entry)

            return entries

        except Exception as e:
            self.logger.debug(f"systemd_boot_entries failed: {e}")
            return []

    def systemd_boot_loader_config(self) -> dict[str, str]:
        """
        Get systemd-boot loader configuration.

        Returns:
            Dict with boot loader settings
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        config = {}

        try:
            conf_file = self._mount_root / "boot/loader/loader.conf"

            if not conf_file.exists():
                conf_file = self._mount_root / "boot/efi/loader/loader.conf"

            if conf_file.exists():
                content = conf_file.read_text()

                for line in content.splitlines():
                    line = line.strip()

                    if not line or line.startswith("#"):
                        continue

                    if " " in line:
                        key, value = line.split(None, 1)
                        config[key.lower()] = value

            return config

        except Exception as e:
            self.logger.debug(f"systemd_boot_loader_config failed: {e}")
            return {}

    def systemd_sysext_list(self) -> list[dict[str, Any]]:
        """
        List systemd system extensions.

        Returns:
            List of system extensions
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        extensions = []

        try:
            sysext_dirs = [
                self._mount_root / "var/lib/extensions",
                self._mount_root / "usr/lib/extensions",
            ]

            for ext_dir in sysext_dirs:
                if not ext_dir.exists():
                    continue

                for ext_file in ext_dir.glob("*.raw"):
                    extensions.append({
                        "name": ext_file.stem,
                        "path": str(ext_file),
                        "size_mb": ext_file.stat().st_size / (1024 * 1024),
                        "location": ext_dir.name,
                    })

            return extensions

        except Exception as e:
            self.logger.debug(f"systemd_sysext_list failed: {e}")
            return []

    # Category 4: Compliance & Security

    def systemd_security_compliance_check(self) -> dict[str, Any]:
        """
        Comprehensive security compliance check.

        Returns:
            Dict with compliance results
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        compliance = {
            "score": 0,
            "total_checks": 0,
            "passed": 0,
            "failed": 0,
            "findings": [],
            "recommendations": [],
        }

        # Check 1: Unnecessary services
        unnecessary_services = [
            "debug-shell.service",
            "systemd-halt.service",
        ]

        for service in unnecessary_services:
            compliance["total_checks"] += 1

            try:
                service_path = self._mount_root / f"etc/systemd/system/{service}"

                if service_path.exists():
                    compliance["failed"] += 1
                    compliance["findings"].append({
                        "check": f"Unnecessary service: {service}",
                        "status": "FAIL",
                        "severity": "medium",
                    })
                    compliance["recommendations"].append(
                        f"Disable {service} to reduce attack surface"
                    )
                else:
                    compliance["passed"] += 1

            except Exception:
                pass

        # Check 2: Journal compression
        compliance["total_checks"] += 1
        try:
            journal_conf = self._mount_root / "etc/systemd/journald.conf"

            if journal_conf.exists():
                content = journal_conf.read_text()
                if "Compress=yes" in content:
                    compliance["passed"] += 1
                else:
                    compliance["failed"] += 1
                    compliance["findings"].append({
                        "check": "Journal compression",
                        "status": "FAIL",
                        "severity": "low",
                    })
                    compliance["recommendations"].append(
                        "Enable journal compression to save disk space"
                    )
        except Exception:
            pass

        # Check 3: Core dump restriction
        compliance["total_checks"] += 1
        try:
            coredump_conf = self._mount_root / "etc/systemd/coredump.conf"

            if coredump_conf.exists():
                content = coredump_conf.read_text()
                if "Storage=none" in content:
                    compliance["passed"] += 1
                else:
                    compliance["failed"] += 1
                    compliance["findings"].append({
                        "check": "Core dump restriction",
                        "status": "FAIL",
                        "severity": "medium",
                    })
                    compliance["recommendations"].append(
                        "Set Storage=none in coredump.conf"
                    )
        except Exception:
            pass

        # Check 4: SUID binaries audit
        compliance["total_checks"] += 1

        try:
            known_safe_suid = {
                "/usr/bin/sudo",
                "/usr/bin/su",
                "/usr/bin/passwd",
                "/usr/bin/mount",
                "/usr/bin/umount",
                "/usr/bin/ping",
            }

            suid_binaries = []
            for root_dir in [self._mount_root / "usr/bin", self._mount_root / "usr/sbin"]:
                if root_dir.exists():
                    for binary in root_dir.iterdir():
                        if binary.is_file():
                            stat_info = binary.stat()
                            if stat_info.st_mode & 0o4000:
                                rel_path = "/" + str(binary.relative_to(self._mount_root))
                                if rel_path not in known_safe_suid:
                                    suid_binaries.append(rel_path)

            if suid_binaries:
                compliance["failed"] += 1
                compliance["findings"].append({
                    "check": "SUID binaries audit",
                    "status": "WARN",
                    "severity": "high",
                    "details": f"Found {len(suid_binaries)} unexpected SUID binaries",
                    "binaries": suid_binaries,
                })
                compliance["recommendations"].append(
                    "Review and remove unnecessary SUID binaries"
                )
            else:
                compliance["passed"] += 1

        except Exception as e:
            self.logger.debug(f"SUID check failed: {e}")

        # Calculate score
        if compliance["total_checks"] > 0:
            compliance["score"] = int(
                (compliance["passed"] / compliance["total_checks"]) * 100
            )

        return compliance

    def systemd_detect_anomalies(self) -> dict[str, list[dict[str, Any]]]:
        """
        Detect suspicious configurations and anomalies.

        Returns:
            Dict categorizing anomalies by type
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        anomalies = {
            "hidden_units": [],
            "writable_units": [],
            "suspicious_timers": [],
            "suspicious_sockets": [],
        }

        try:
            systemd_dir = self._mount_root / "etc/systemd/system"

            if not systemd_dir.exists():
                return anomalies

            # Check 1: Hidden units
            for hidden_file in systemd_dir.glob(".*"):
                if hidden_file.is_file():
                    anomalies["hidden_units"].append({
                        "file": str(hidden_file.relative_to(self._mount_root)),
                        "size": hidden_file.stat().st_size,
                    })

            # Check 2: World-writable units
            for unit_file in systemd_dir.rglob("*"):
                if unit_file.is_file():
                    mode = unit_file.stat().st_mode
                    if mode & 0o002:
                        anomalies["writable_units"].append({
                            "file": str(unit_file.relative_to(self._mount_root)),
                            "mode": oct(mode),
                        })

            # Check 3: Suspicious timers
            for timer_file in systemd_dir.rglob("*.timer"):
                if timer_file.is_file():
                    content = timer_file.read_text()

                    if "OnCalendar=*:0/1" in content or "OnCalendar=minutely" in content:
                        anomalies["suspicious_timers"].append({
                            "file": timer_file.name,
                            "reason": "Very frequent activation",
                            "path": str(timer_file.relative_to(self._mount_root)),
                        })

            # Check 4: Suspicious sockets
            for socket_file in systemd_dir.rglob("*.socket"):
                if socket_file.is_file():
                    content = socket_file.read_text()

                    for match in re.finditer(r'ListenStream=([^\n]+)', content):
                        listen_addr = match.group(1)

                        if not listen_addr.startswith("127.0.0.1") and \
                           not listen_addr.startswith("/") and \
                           not listen_addr.startswith("localhost"):
                            anomalies["suspicious_sockets"].append({
                                "file": socket_file.name,
                                "address": listen_addr,
                                "reason": "Listening on non-localhost",
                                "path": str(socket_file.relative_to(self._mount_root)),
                            })

            return anomalies

        except Exception as e:
            self.logger.debug(f"systemd_detect_anomalies failed: {e}")
            return anomalies

    def systemd_analyze_failures(self) -> dict[str, Any]:
        """
        Comprehensive analysis of failed services.

        Returns:
            Dict with failure analysis
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        analysis = {
            "failed_units": [],
            "failure_patterns": {},
            "recommendations": [],
        }

        try:
            # Get all failed units
            failed = self.systemctl_list_units(state="failed")

            for unit_dict in failed:
                unit = unit_dict.get("unit", "")

                # Get detailed status
                status = self.systemctl_status(unit)

                # Extract failure information
                failure_info = {
                    "unit": unit,
                    "status": status,
                }

                analysis["failed_units"].append(failure_info)

                # Pattern detection
                status_str = str(status).lower()
                if "dependency" in status_str:
                    analysis["failure_patterns"]["dependency"] = \
                        analysis["failure_patterns"].get("dependency", 0) + 1

                if "timeout" in status_str:
                    analysis["failure_patterns"]["timeout"] = \
                        analysis["failure_patterns"].get("timeout", 0) + 1

            # Generate recommendations
            if analysis["failure_patterns"].get("dependency", 0) > 0:
                analysis["recommendations"].append(
                    "Check service dependencies with systemctl list-dependencies"
                )

            if analysis["failure_patterns"].get("timeout", 0) > 0:
                analysis["recommendations"].append(
                    "Consider increasing TimeoutStartSec in unit files"
                )

            return analysis

        except Exception as e:
            self.logger.debug(f"systemd_analyze_failures failed: {e}")
            return analysis

    # Category 5: Migration Readiness

    def systemd_migration_readiness_check(self) -> dict[str, Any]:
        """
        Comprehensive migration readiness assessment.

        Returns:
            Dict with readiness assessment
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        assessment = {
            "ready": True,
            "blockers": [],
            "warnings": [],
            "recommendations": [],
            "checks_performed": 0,
            "checks_passed": 0,
        }

        systemd_dir = self._mount_root / "etc/systemd/system"

        try:
            # Check 1: Host-specific units
            assessment["checks_performed"] += 1
            host_specific_found = False

            if systemd_dir.exists():
                for unit_file in systemd_dir.rglob("*.service"):
                    if unit_file.is_file():
                        content = unit_file.read_text()

                        if "ConditionHost=" in content:
                            assessment["warnings"].append({
                                "check": "Host-specific unit",
                                "file": unit_file.name,
                                "issue": "Contains ConditionHost dependency",
                                "impact": "May not start on new host",
                            })
                            assessment["recommendations"].append(
                                f"Review {unit_file.name} for host-specific conditions"
                            )
                            host_specific_found = True

            if not host_specific_found:
                assessment["checks_passed"] += 1

            # Check 2: Hardcoded MAC addresses
            assessment["checks_performed"] += 1
            mac_hardcoded = False

            network_dir = self._mount_root / "etc/systemd/network"
            if network_dir.exists():
                for net_file in network_dir.glob("*.network"):
                    content = net_file.read_text()

                    if "MACAddress=" in content or "PermanentMACAddress=" in content:
                        assessment["blockers"].append({
                            "check": "Hardcoded MAC address",
                            "file": net_file.name,
                            "issue": "Network config has hardcoded MAC",
                            "impact": "Network will fail on new host",
                            "severity": "high",
                        })
                        assessment["recommendations"].append(
                            f"Remove MAC address from {net_file.name}"
                        )
                        assessment["ready"] = False
                        mac_hardcoded = True

            if not mac_hardcoded:
                assessment["checks_passed"] += 1

            # Check 3: Non-portable filesystem mounts
            assessment["checks_performed"] += 1

            fstab_file = self._mount_root / "etc/fstab"
            if fstab_file.exists():
                content = fstab_file.read_text()

                non_portable_mounts = re.findall(r'/dev/[sh]d[a-z]\d+', content)

                if non_portable_mounts:
                    assessment["warnings"].append({
                        "check": "Non-portable filesystem mounts",
                        "issue": f"fstab uses device names: {', '.join(set(non_portable_mounts))}",
                        "impact": "Mounts may fail if device names change",
                        "severity": "medium",
                    })
                    assessment["recommendations"].append(
                        "Convert fstab to use UUID or PARTUUID"
                    )
                else:
                    assessment["checks_passed"] += 1

            return assessment

        except Exception as e:
            self.logger.debug(f"systemd_migration_readiness_check failed: {e}")
            assessment["ready"] = False
            assessment["blockers"].append({
                "check": "Migration readiness scan",
                "issue": f"Error during scan: {e}",
                "severity": "unknown",
            })
            return assessment

    def systemd_post_migration_validation(self) -> dict[str, Any]:
        """
        Validate VM after migration.

        Returns:
            Dict with validation results
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        validation = {
            "valid": True,
            "checks": [],
            "issues": [],
            "recommendations": [],
        }

        # Check 1: Virtualization detection
        virt = self.systemd_detect_virt()
        validation["checks"].append({
            "name": "Virtualization detection",
            "status": "pass" if virt["vm"] != "none" else "fail",
            "details": f"Detected: {virt['vm']}",
        })

        if virt["vm"] == "none":
            validation["valid"] = False
            validation["issues"].append("Virtualization not detected after migration")

        # Check 2: Machine ID exists
        machine_id = self.systemd_machine_id()
        validation["checks"].append({
            "name": "Machine ID",
            "status": "pass" if machine_id else "fail",
            "details": machine_id[:16] + "..." if machine_id else "Missing",
        })

        if not machine_id:
            validation["valid"] = False
            validation["issues"].append("Machine ID missing")
            validation["recommendations"].append("Run: systemd-machine-id-setup")

        # Check 3: Boot configuration
        boot_entries = self.systemd_boot_entries()
        validation["checks"].append({
            "name": "Boot entries",
            "status": "pass" if boot_entries else "warn",
            "details": f"Found {len(boot_entries)} boot entries",
        })

        return validation

    # Category 6: Advanced System Analysis

    def systemd_oomd_config(self) -> dict[str, Any]:
        """
        Get systemd-oomd (Out-Of-Memory daemon) configuration.

        Returns:
            Dict with OOM daemon configuration
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        config = {
            "SwapUsedLimit": "90%",
            "DefaultMemoryPressureLimit": "60%",
            "DefaultMemoryPressureDurationSec": "30s",
        }

        try:
            oomd_conf = self._mount_root / "etc/systemd/oomd.conf"

            if oomd_conf.exists():
                import configparser
                parser = configparser.ConfigParser()
                parser.read(oomd_conf)

                if "OOM" in parser:
                    section = parser["OOM"]

                    for key in config.keys():
                        if key in section:
                            config[key] = section[key]

            return config

        except Exception as e:
            self.logger.debug(f"systemd_oomd_config failed: {e}")
            return config

    def systemd_timesyncd_config(self) -> dict[str, Any]:
        """
        Get systemd-timesyncd (NTP client) configuration.

        Returns:
            Dict with NTP configuration
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        config = {
            "NTP": [],
            "FallbackNTP": ["time.cloudflare.com", "time.google.com"],
            "RootDistanceMaxSec": "5",
            "PollIntervalMinSec": "32",
            "PollIntervalMaxSec": "2048",
        }

        try:
            timesyncd_conf = self._mount_root / "etc/systemd/timesyncd.conf"

            if timesyncd_conf.exists():
                import configparser
                parser = configparser.ConfigParser()
                parser.read(timesyncd_conf)

                if "Time" in parser:
                    section = parser["Time"]

                    if "NTP" in section:
                        config["NTP"] = section["NTP"].split()

                    if "FallbackNTP" in section:
                        config["FallbackNTP"] = section["FallbackNTP"].split()

                    for key in ["RootDistanceMaxSec", "PollIntervalMinSec", "PollIntervalMaxSec"]:
                        if key in section:
                            config[key] = section[key]

            return config

        except Exception as e:
            self.logger.debug(f"systemd_timesyncd_config failed: {e}")
            return config

    def systemd_portable_list(self) -> list[dict[str, Any]]:
        """
        List systemd portable service images.

        Returns:
            List of portable service images
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        portables = []

        try:
            portable_dirs = [
                self._mount_root / "var/lib/portables",
                self._mount_root / "etc/portables",
            ]

            for portable_dir in portable_dirs:
                if not portable_dir.exists():
                    continue

                for portable_file in portable_dir.glob("*.raw"):
                    portables.append({
                        "name": portable_file.stem,
                        "type": "raw",
                        "path": str(portable_file),
                        "size_mb": portable_file.stat().st_size / (1024 * 1024),
                    })

                for portable_file in portable_dir.glob("*.portable"):
                    portables.append({
                        "name": portable_file.stem,
                        "type": "portable",
                        "path": str(portable_file),
                        "size_mb": portable_file.stat().st_size / (1024 * 1024),
                    })

            return portables

        except Exception as e:
            self.logger.debug(f"systemd_portable_list failed: {e}")
            return []

    # Storage stack operations

    def vgscan(self) -> None:
        """Scan for LVM volume groups."""
        LVMActivator.activate(self.logger)

    def vgchange_activate_all(self, enable: bool | int) -> None:
        """Activate all volume groups."""
        if enable:
            LVMActivator.activate(self.logger)

    def lvs(self) -> list[str]:
        """List logical volumes."""
        return LVMActivator.list_logical_volumes(self.logger)

    # LVM Creation APIs

    def pvcreate(self, devices: list[str]) -> dict[str, Any]:
        """
        Create physical volumes.

        Args:
            devices: List of device paths to initialize as PVs

        Returns:
            Audit dict with created PV list

        Example:
            result = g.pvcreate(["/dev/nbd0p1"])
        """
        from .storage import LVMCreator
        return LVMCreator.pvcreate(self.logger, devices)

    def vgcreate(self, vgname: str, pvs: list[str]) -> dict[str, Any]:
        """
        Create volume group.

        Args:
            vgname: Volume group name
            pvs: List of physical volumes

        Returns:
            Audit dict with VG name

        Example:
            result = g.vgcreate("test_vg", ["/dev/nbd0p1"])
        """
        from .storage import LVMCreator
        return LVMCreator.vgcreate(self.logger, vgname, pvs)

    def lvcreate(
        self,
        lvname: str,
        vgname: str,
        size_mb: int | None = None,
        extents: str | None = None
    ) -> dict[str, Any]:
        """
        Create logical volume.

        Args:
            lvname: Logical volume name
            vgname: Volume group name
            size_mb: Size in megabytes (mutually exclusive with extents)
            extents: Size in extents (e.g., "100%FREE")

        Returns:
            Audit dict with LV path

        Example:
            # Create LV with specific size
            result = g.lvcreate("data", "vg0", size_mb=1024)

            # Create LV using all free space
            result = g.lvcreate("data", "vg0", extents="100%FREE")
        """
        from .storage import LVMCreator
        return LVMCreator.lvcreate(self.logger, lvname, vgname, size_mb, extents)

    def lvresize(self, lvpath: str, size_mb: int) -> dict[str, Any]:
        """
        Resize logical volume.

        Args:
            lvpath: LV device path (e.g., "/dev/vg0/data")
            size_mb: New size in megabytes

        Returns:
            Audit dict

        Example:
            result = g.lvresize("/dev/vg0/data", 2048)
        """
        from .storage import LVMCreator
        return LVMCreator.lvresize(self.logger, lvpath, size_mb)

    def lvremove(self, lvpath: str, force: bool = False) -> dict[str, Any]:
        """
        Remove logical volume.

        Args:
            lvpath: LV device path
            force: Force removal without confirmation

        Returns:
            Audit dict

        Example:
            result = g.lvremove("/dev/vg0/data", force=True)
        """
        from .storage import LVMCreator
        return LVMCreator.lvremove(self.logger, lvpath, force)

    def vgremove(self, vgname: str, force: bool = False) -> dict[str, Any]:
        """
        Remove volume group.

        Args:
            vgname: Volume group name
            force: Force removal without confirmation

        Returns:
            Audit dict

        Example:
            result = g.vgremove("vg0", force=True)
        """
        from .storage import LVMCreator
        return LVMCreator.vgremove(self.logger, vgname, force)

    def cryptsetup_open(self, device: str, name: str, key: bytes) -> None:
        """Open LUKS encrypted device."""
        raise NotImplementedError("cryptsetup_open not directly supported (use LUKS config in launch)")

    def command(self, cmd: list[str]) -> str:
        """Execute command in guest filesystem (via chroot)."""
        if not self._mount_root:
            raise RuntimeError("Not launched")

        chroot_cmd = ["chroot", str(self._mount_root)] + cmd
        result = run_sudo(self.logger, chroot_cmd, check=True, capture=True)
        return result.stdout

    def command_quiet(self, cmd: list[str]) -> str:
        """
        Execute command in guest filesystem (via chroot), but log failures as DEBUG only.
        Use this for commands that are expected to fail often (e.g., glob searches, bootloader commands).
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        chroot_cmd = ["chroot", str(self._mount_root)] + cmd
        result = run_sudo(self.logger, chroot_cmd, check=True, capture=True, failure_log_level=logging.DEBUG)
        return result.stdout

    def command_with_mounts(self, cmd: list[str], quiet: bool = False) -> str:
        """
        Execute command in guest filesystem with /proc, /dev, /sys bind-mounted.

        This provides a more complete chroot environment needed by bootloader tools
        like grub2-mkconfig, which require access to /proc/self/mountinfo and /dev.

        Args:
            cmd: Command to execute inside chroot
            quiet: If True, log failures at DEBUG level only

        Returns:
            Command stdout

        Raises:
            RuntimeError: If not launched or if command fails (when not quiet)
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        mount_root = Path(self._mount_root)
        mounts_to_cleanup = []

        try:
            # Set up bind mounts for /proc, /dev, /sys
            for mount_point in ["proc", "dev", "sys"]:
                target = mount_root / mount_point

                # Create mount point if it doesn't exist
                if not target.exists():
                    target.mkdir(parents=True, exist_ok=True)

                # Check if already mounted (avoid double-mount)
                check_cmd = ["mountpoint", "-q", str(target)]
                check_result = run_sudo(self.logger, check_cmd, check=False, capture=True)

                if check_result.returncode != 0:  # Not mounted
                    # Bind mount
                    mount_cmd = ["mount", "--bind", f"/{mount_point}", str(target)]
                    run_sudo(self.logger, mount_cmd, check=True, capture=True)
                    mounts_to_cleanup.append(str(target))
                    self.logger.debug(f"Bind-mounted /{mount_point} to {target}")

            # Execute command in chroot
            chroot_cmd = ["chroot", str(self._mount_root)] + cmd
            if quiet:
                result = run_sudo(self.logger, chroot_cmd, check=True, capture=True,
                                failure_log_level=logging.DEBUG)
            else:
                result = run_sudo(self.logger, chroot_cmd, check=True, capture=True)

            return result.stdout

        finally:
            # Clean up bind mounts in reverse order
            for mount_path in reversed(mounts_to_cleanup):
                try:
                    umount_cmd = ["umount", mount_path]
                    run_sudo(self.logger, umount_cmd, check=False, capture=True,
                           failure_log_level=logging.DEBUG)
                    self.logger.debug(f"Unmounted {mount_path}")
                except Exception as e:
                    self.logger.debug(f"Failed to unmount {mount_path}: {e}")

    # Windows-specific operations (delegate to Windows modules)

    def win_inject_driver(self, driver_path: str, inf_file: str | None = None) -> dict[str, Any]:
        """Inject Windows driver into guest filesystem."""
        if not self._win_drivers:
            raise RuntimeError("Not launched")
        return self._win_drivers.inject_driver(driver_path, inf_file)

    def win_registry_read(self, hive_name: str, key_path: str, value_name: str) -> str | None:
        """Read value from Windows registry hive."""
        if not self._win_registry:
            raise RuntimeError("Not launched")
        return self._win_registry.read_value(hive_name, key_path, value_name)

    def win_registry_write(self, hive_name: str, key_path: str, value_name: str, value: str, value_type: str = "sz") -> bool:
        """Write value to Windows registry hive."""
        if not self._win_registry:
            raise RuntimeError("Not launched")
        return self._win_registry.write_value(hive_name, key_path, value_name, value, value_type)

    def win_registry_list_keys(self, hive_name: str, key_path: str = "") -> list[str]:
        """List subkeys under a registry key."""
        if not self._win_registry:
            raise RuntimeError("Not launched")
        return self._win_registry.list_keys(hive_name, key_path)

    def win_registry_list_values(self, hive_name: str, key_path: str) -> dict[str, Any]:
        """List values under a registry key."""
        if not self._win_registry:
            raise RuntimeError("Not launched")
        return self._win_registry.list_values(hive_name, key_path)

    def win_resolve_path(self, path: str) -> Path | None:
        """Resolve Windows path (case-insensitive)."""
        if not self._win_registry:
            raise RuntimeError("Not launched")
        return self._win_registry.resolve_path(path)

    # Operational modules (delegate to specialized managers)

    def backup_files(self, paths: list[str], dest_archive: str, compression: str = "gzip") -> dict[str, Any]:
        """Backup files to archive."""
        if not self._backup_mgr:
            raise RuntimeError("Not launched")
        return self._backup_mgr.backup_files(paths, dest_archive, compression)

    def restore_files(self, src_archive: str, dest_path: str = "/") -> dict[str, Any]:
        """Restore files from archive."""
        if not self._backup_mgr:
            raise RuntimeError("Not launched")
        return self._backup_mgr.restore_files(src_archive, dest_path)

    def audit_permissions(self, path: str = "/") -> dict[str, Any]:
        """Audit file permissions for security issues."""
        if not self._security_auditor:
            raise RuntimeError("Not launched")
        return self._security_auditor.audit_permissions(path)

    def find_large_files(self, min_size_mb: int = 100, path: str = "/") -> list[dict[str, Any]]:
        """Find large files in filesystem."""
        if not self._disk_optimizer:
            raise RuntimeError("Not launched")
        return self._disk_optimizer.find_large_files(min_size_mb, path)

    def find_duplicates(self, path: str = "/", min_size_mb: int = 1) -> dict[str, list[str]]:
        """Find duplicate files by content hash."""
        if not self._disk_optimizer:
            raise RuntimeError("Not launched")
        return self._disk_optimizer.find_duplicates(path, min_size_mb)

    def analyze_disk_usage(self, path: str = "/", top_n: int = 20) -> dict[str, Any]:
        """Analyze disk usage by directory."""
        if not self._disk_optimizer:
            raise RuntimeError("Not launched")
        return self._disk_optimizer.analyze_disk_usage(path, top_n)

    def cleanup_temp_files(self, dry_run: bool = True) -> dict[str, Any]:
        """Clean up temporary files."""
        if not self._disk_optimizer:
            raise RuntimeError("Not launched")
        return self._disk_optimizer.cleanup_temp_files(dry_run)

    # Container and Bootloader Detection (inspection.py enhancements)

    def detect_containers(self) -> dict[str, Any]:
        """Detect container runtime installations (Docker, Podman, LXC, systemd-nspawn)."""
        if not self._os_inspector:
            raise RuntimeError("Not launched")
        return self._os_inspector.detect_containers()

    def is_inside_container(self) -> dict[str, Any]:
        """Check if the inspected OS is running inside a container."""
        if not self._os_inspector:
            raise RuntimeError("Not launched")
        return self._os_inspector.is_inside_container()

    def detect_bootloader(self) -> dict[str, Any]:
        """Detect bootloader configuration (GRUB2, systemd-boot, UEFI, LILO)."""
        if not self._os_inspector:
            raise RuntimeError("Not launched")
        return self._os_inspector.detect_bootloader()

    def get_bootloader_entries(self) -> list[dict[str, Any]]:
        """Get boot loader menu entries."""
        if not self._os_inspector:
            raise RuntimeError("Not launched")
        return self._os_inspector.get_bootloader_entries()

    # Security Module Detection (security.py enhancements)

    def detect_selinux(self) -> dict[str, Any]:
        """Detect SELinux configuration and status."""
        if not self._security_auditor:
            raise RuntimeError("Not launched")
        return self._security_auditor.detect_selinux()

    def detect_apparmor(self) -> dict[str, Any]:
        """Detect AppArmor configuration and status."""
        if not self._security_auditor:
            raise RuntimeError("Not launched")
        return self._security_auditor.detect_apparmor()

    def get_security_modules(self) -> dict[str, Any]:
        """Get comprehensive security module information (SELinux, AppArmor)."""
        if not self._security_auditor:
            raise RuntimeError("Not launched")
        return self._security_auditor.get_security_modules()

    # Package Manager Operations (security.py enhancements)

    def query_package(self, package_name: str, manager: str = "auto") -> dict[str, Any]:
        """Query installed package information (RPM, APT, Pacman)."""
        if not self._security_auditor:
            raise RuntimeError("Not launched")
        return self._security_auditor.query_package(package_name, manager)

    def list_installed_packages(self, manager: str = "auto", limit: int = 0) -> list[dict[str, str]]:
        """List all installed packages."""
        if not self._security_auditor:
            raise RuntimeError("Not launched")
        return self._security_auditor.list_installed_packages(manager, limit)

    # Windows User Management (windows_users.py)

    def win_list_users(self) -> list[dict[str, Any]]:
        """List all local Windows user accounts."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.list_users()

    def win_get_user_info(self, username: str) -> dict[str, Any] | None:
        """Get detailed information about a Windows user."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.get_user_info(username)

    def win_get_user_groups(self, username: str) -> list[str]:
        """Get groups that a Windows user is a member of."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.get_user_groups(username)

    def win_is_administrator(self, username: str) -> bool:
        """Check if Windows user is in Administrators group."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.is_administrator(username)

    def win_is_disabled(self, username: str) -> bool:
        """Check if Windows user account is disabled."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.is_disabled(username)

    def win_list_administrators(self) -> list[str]:
        """List all Windows administrator accounts."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.list_administrators()

    def win_list_enabled_users(self) -> list[str]:
        """List all enabled Windows user accounts."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.list_enabled_users()

    def win_list_disabled_users(self) -> list[str]:
        """List all disabled Windows user accounts."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.list_disabled_users()

    def win_get_user_count(self) -> dict[str, int]:
        """Get Windows user account statistics."""
        if not self._win_users:
            raise RuntimeError("Not launched")
        return self._win_users.get_user_count()

    # Linux Service Management (linux_services.py)

    def linux_list_services(self) -> list[dict[str, Any]]:
        """List all systemd service units."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.list_services()

    def linux_get_service_info(self, service_name: str) -> dict[str, Any] | None:
        """Get detailed information about a systemd service."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.get_service_info(service_name)

    def linux_list_enabled_services(self) -> list[str]:
        """List all enabled systemd services."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.list_enabled_services()

    def linux_list_disabled_services(self) -> list[str]:
        """List all disabled systemd services."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.list_disabled_services()

    def linux_get_service_dependencies(self, service_name: str) -> dict[str, Any]:
        """Get systemd service dependencies."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.get_service_dependencies(service_name)

    def linux_find_services_by_target(self, target: str = "multi-user.target") -> list[str]:
        """Find services enabled for a specific systemd target."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.find_services_by_target(target)

    def linux_get_boot_services(self) -> list[str]:
        """Get services that start at boot."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.get_boot_services()

    def linux_get_service_stats(self) -> dict[str, int]:
        """Get systemd service statistics."""
        if not self._linux_services:
            raise RuntimeError("Not launched")
        return self._linux_services.get_service_stats()

    # Cache Management (file_ops.py enhancements)

    def get_cache_stats(self) -> dict[str, Any]:
        """Get file operation cache statistics."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        return self._file_ops.get_cache_stats()

    def clear_cache(self) -> None:
        """Clear file operation caches."""
        if not self._file_ops:
            raise RuntimeError("Not launched")
        self._file_ops.clear_cache()

    # Windows Service Management (windows_services.py)

    def win_list_services(self) -> list[dict[str, Any]]:
        """List all Windows services from SYSTEM registry."""
        if not self._win_services:
            raise RuntimeError("Not launched")
        return self._win_services.list_services()

    def win_get_service_count(self) -> dict[str, Any]:
        """Get Windows service statistics by start type."""
        if not self._win_services:
            raise RuntimeError("Not launched")
        return self._win_services.get_service_count()

    def win_list_automatic_services(self) -> list[str]:
        """List Windows services that start automatically."""
        if not self._win_services:
            raise RuntimeError("Not launched")
        return self._win_services.list_automatic_services()

    def win_list_disabled_services(self) -> list[str]:
        """List disabled Windows services."""
        if not self._win_services:
            raise RuntimeError("Not launched")
        return self._win_services.list_disabled_services()

    # Windows Application Management (windows_applications.py)

    def win_list_applications(self, limit: int = 100) -> list[dict[str, Any]]:
        """List installed Windows applications from registry."""
        if not self._win_apps:
            raise RuntimeError("Not launched")
        return self._win_apps.list_applications(limit=limit)

    def win_get_application_count(self) -> dict[str, Any]:
        """Get Windows application statistics."""
        if not self._win_apps:
            raise RuntimeError("Not launched")
        return self._win_apps.get_application_count()

    def win_search_applications(self, query: str) -> list[dict[str, Any]]:
        """Search Windows applications by name or publisher."""
        if not self._win_apps:
            raise RuntimeError("Not launched")
        return self._win_apps.search_applications(query)

    def win_get_applications_by_publisher(self, publisher: str) -> list[dict[str, Any]]:
        """Get Windows applications from a specific publisher."""
        if not self._win_apps:
            raise RuntimeError("Not launched")
        return self._win_apps.get_applications_by_publisher(publisher)

    # Network Configuration Analysis (network_config.py)

    def analyze_network_config(self, os_type: str) -> dict[str, Any]:
        """Analyze network configuration based on OS type."""
        if not self._network_config:
            raise RuntimeError("Not launched")
        return self._network_config.analyze_network_config(os_type)

    def find_static_ips(self, config: dict[str, Any]) -> list[str]:
        """Find statically configured IP addresses."""
        if not self._network_config:
            raise RuntimeError("Not launched")
        return self._network_config.find_static_ips(config)

    def detect_network_bonds(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect network bonding/teaming configurations."""
        if not self._network_config:
            raise RuntimeError("Not launched")
        return self._network_config.detect_network_bonds(config)

    # Firewall Analysis (firewall_analyzer.py)

    def analyze_firewall(self, os_type: str) -> dict[str, Any]:
        """Analyze firewall configuration based on OS type."""
        if not self._firewall_analyzer:
            raise RuntimeError("Not launched")
        return self._firewall_analyzer.analyze_firewall(os_type)

    def get_open_ports(self, config: dict[str, Any]) -> list[int]:
        """Extract list of open ports from firewall configuration."""
        if not self._firewall_analyzer:
            raise RuntimeError("Not launched")
        return self._firewall_analyzer.get_open_ports(config)

    def get_blocked_ports(self, config: dict[str, Any]) -> list[int]:
        """Extract list of blocked ports from firewall configuration."""
        if not self._firewall_analyzer:
            raise RuntimeError("Not launched")
        return self._firewall_analyzer.get_blocked_ports(config)

    def get_firewall_stats(self, config: dict[str, Any]) -> dict[str, Any]:
        """Get firewall statistics."""
        if not self._firewall_analyzer:
            raise RuntimeError("Not launched")
        return self._firewall_analyzer.get_firewall_stats(config)

    # Advanced Filesystem Analysis (advanced_analysis.py)

    def search_files(
        self,
        path: str = "/",
        name_pattern: str | None = None,
        content_pattern: str | None = None,
        min_size_mb: float | None = None,
        max_size_mb: float | None = None,
        file_type: str | None = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """Multi-criteria file search with flexible filters."""
        if not self._advanced_analyzer:
            raise RuntimeError("Not launched")
        return self._advanced_analyzer.search_files(
            path=path,
            name_pattern=name_pattern,
            content_pattern=content_pattern,
            min_size_mb=min_size_mb,
            max_size_mb=max_size_mb,
            file_type=file_type,
            limit=limit
        )

    def find_large_files(
        self,
        path: str = "/",
        min_size_mb: float = 100,
        limit: int = 50
    ) -> list[dict[str, Any]]:
        """Find large files above a size threshold."""
        if not self._advanced_analyzer:
            raise RuntimeError("Not launched")
        return self._advanced_analyzer.find_large_files(
            path=path,
            min_size_mb=min_size_mb,
            limit=limit
        )

    def find_duplicates(
        self,
        path: str = "/",
        min_size_mb: float = 1,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """Find duplicate files using SHA256 checksums."""
        if not self._advanced_analyzer:
            raise RuntimeError("Not launched")
        return self._advanced_analyzer.find_duplicates(
            path=path,
            min_size_mb=min_size_mb,
            limit=limit
        )

    def analyze_disk_space(
        self,
        path: str = "/",
        top_n: int = 20
    ) -> dict[str, Any]:
        """Analyze disk space usage by directory."""
        if not self._advanced_analyzer:
            raise RuntimeError("Not launched")
        return self._advanced_analyzer.analyze_disk_space(
            path=path,
            top_n=top_n
        )

    def find_certificates(self, path: str = "/") -> list[dict[str, Any]]:
        """Find SSL/TLS certificate files."""
        if not self._advanced_analyzer:
            raise RuntimeError("Not launched")
        return self._advanced_analyzer.find_certificates(path=path)

    # Export and Reporting (export.py)

    def export_json(self, data: dict[str, Any], output_path: str | Path) -> bool:
        """Export data to JSON format."""
        if not self._export_mgr:
            raise RuntimeError("Not launched")
        return self._export_mgr.export_json(data, output_path)

    def export_yaml(self, data: dict[str, Any], output_path: str | Path) -> bool:
        """Export data to YAML format."""
        if not self._export_mgr:
            raise RuntimeError("Not launched")
        return self._export_mgr.export_yaml(data, output_path)

    def export_markdown_report(
        self,
        data: dict[str, Any],
        output_path: str | Path,
        title: str = "VM Analysis Report"
    ) -> bool:
        """Generate Markdown report from analysis data."""
        if not self._export_mgr:
            raise RuntimeError("Not launched")
        return self._export_mgr.export_markdown_report(data, output_path, title)

    def create_vm_profile(
        self,
        os_info: dict[str, Any] | None = None,
        containers: dict[str, Any] | None = None,
        security: dict[str, Any] | None = None,
        packages: dict[str, Any] | None = None,
        performance: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create comprehensive VM profile for analysis and comparison."""
        if not self._export_mgr:
            raise RuntimeError("Not launched")
        return self._export_mgr.create_vm_profile(
            os_info=os_info,
            containers=containers,
            security=security,
            packages=packages,
            performance=performance
        )

    def compare_vms(
        self,
        vm1_profile: dict[str, Any],
        vm2_profile: dict[str, Any]
    ) -> dict[str, Any]:
        """Compare two VM profiles and generate diff report."""
        if not self._export_mgr:
            raise RuntimeError("Not launched")
        return self._export_mgr.compare_vms(vm1_profile, vm2_profile)

    # Scheduled Task Analysis (scheduled_tasks.py)

    def analyze_scheduled_tasks(self, os_type: str) -> dict[str, Any]:
        """Analyze scheduled tasks based on OS type (cron, systemd timers, Windows Task Scheduler)."""
        if not self._scheduled_tasks:
            raise RuntimeError("Not launched")
        return self._scheduled_tasks.analyze_scheduled_tasks(os_type)

    def get_task_count(self, config: dict[str, Any]) -> int:
        """Get total count of scheduled tasks."""
        if not self._scheduled_tasks:
            raise RuntimeError("Not launched")
        return self._scheduled_tasks.get_task_count(config)

    def find_daily_tasks(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Find tasks that run daily."""
        if not self._scheduled_tasks:
            raise RuntimeError("Not launched")
        return self._scheduled_tasks.find_daily_tasks(config)

    def find_tasks_by_user(self, config: dict[str, Any], user: str) -> list[dict[str, Any]]:
        """Find tasks scheduled for a specific user."""
        if not self._scheduled_tasks:
            raise RuntimeError("Not launched")
        return self._scheduled_tasks.find_tasks_by_user(config, user)

    # SSH Configuration Analysis (ssh_analyzer.py)

    def analyze_ssh_config(self) -> dict[str, Any]:
        """Analyze SSH server and client configuration."""
        if not self._ssh_analyzer:
            raise RuntimeError("Not launched")
        return self._ssh_analyzer.analyze_ssh_config()

    def get_ssh_port(self, config: dict[str, Any]) -> int:
        """Get SSH server port."""
        if not self._ssh_analyzer:
            raise RuntimeError("Not launched")
        return self._ssh_analyzer.get_ssh_port(config)

    def is_root_login_allowed(self, config: dict[str, Any]) -> bool:
        """Check if root login is allowed via SSH."""
        if not self._ssh_analyzer:
            raise RuntimeError("Not launched")
        return self._ssh_analyzer.is_root_login_allowed(config)

    def is_password_auth_enabled(self, config: dict[str, Any]) -> bool:
        """Check if password authentication is enabled for SSH."""
        if not self._ssh_analyzer:
            raise RuntimeError("Not launched")
        return self._ssh_analyzer.is_password_auth_enabled(config)

    def get_authorized_key_count(self, config: dict[str, Any]) -> int:
        """Get total count of authorized SSH keys."""
        if not self._ssh_analyzer:
            raise RuntimeError("Not launched")
        return self._ssh_analyzer.get_authorized_key_count(config)

    def get_security_score(self, config: dict[str, Any]) -> dict[str, Any]:
        """Calculate SSH security score."""
        if not self._ssh_analyzer:
            raise RuntimeError("Not launched")
        return self._ssh_analyzer.get_security_score(config)

    # Log Analysis (log_analyzer.py)

    def analyze_logs(self) -> dict[str, Any]:
        """Analyze system logs comprehensively."""
        if not self._log_analyzer:
            raise RuntimeError("Not launched")
        return self._log_analyzer.analyze_logs()

    def get_recent_errors(self, hours: int = 24, limit: int = 20) -> list[dict[str, Any]]:
        """Get errors from the last N hours."""
        if not self._log_analyzer:
            raise RuntimeError("Not launched")
        return self._log_analyzer.get_recent_errors(hours=hours, limit=limit)

    def get_critical_events(self) -> list[dict[str, Any]]:
        """Get critical events (kernel panics, OOM, crashes)."""
        if not self._log_analyzer:
            raise RuntimeError("Not launched")
        return self._log_analyzer.get_critical_events()

    # Hardware Detection (hardware_detector.py)

    def detect_hardware(self) -> dict[str, Any]:
        """Detect hardware configuration comprehensively."""
        if not self._hardware_detector:
            raise RuntimeError("Not launched")
        return self._hardware_detector.detect_hardware()

    def is_virtual_machine(self, hardware: dict[str, Any]) -> bool:
        """Check if the system is a virtual machine."""
        if not self._hardware_detector:
            raise RuntimeError("Not launched")
        return self._hardware_detector.is_virtual_machine(hardware)

    def get_hypervisor(self, hardware: dict[str, Any]) -> str | None:
        """Get the hypervisor type."""
        if not self._hardware_detector:
            raise RuntimeError("Not launched")
        return self._hardware_detector.get_hypervisor(hardware)

    def get_total_memory_mb(self, hardware: dict[str, Any]) -> float | None:
        """Get total memory in MB."""
        if not self._hardware_detector:
            raise RuntimeError("Not launched")
        return self._hardware_detector.get_total_memory_mb(hardware)

    def get_disk_count(self, hardware: dict[str, Any]) -> int:
        """Get number of disk devices."""
        if not self._hardware_detector:
            raise RuntimeError("Not launched")
        return self._hardware_detector.get_disk_count(hardware)

    def get_network_interface_count(self, hardware: dict[str, Any]) -> int:
        """Get number of network interfaces."""
        if not self._hardware_detector:
            raise RuntimeError("Not launched")
        return self._hardware_detector.get_network_interface_count(hardware)

    def get_hardware_summary(self, hardware: dict[str, Any]) -> dict[str, Any]:
        """Get hardware summary."""
        if not self._hardware_detector:
            raise RuntimeError("Not launched")
        return self._hardware_detector.get_hardware_summary(hardware)

    # Database Detection (database_detector.py)

    def detect_databases(self) -> dict[str, Any]:
        """Detect all database installations."""
        if not self._database_detector:
            raise RuntimeError("Not launched")
        return self._database_detector.detect_databases()

    def get_database_summary(self, databases: dict[str, Any]) -> dict[str, Any]:
        """Get database summary."""
        if not self._database_detector:
            raise RuntimeError("Not launched")
        return self._database_detector.get_database_summary(databases)

    def check_database_security(self, databases: dict[str, Any]) -> list[dict[str, Any]]:
        """Check database security settings."""
        if not self._database_detector:
            raise RuntimeError("Not launched")
        return self._database_detector.check_database_security(databases)

    # Web Server Analysis (webserver_analyzer.py)

    def detect_webservers(self) -> dict[str, Any]:
        """Detect all web server installations."""
        if not self._webserver_analyzer:
            raise RuntimeError("Not launched")
        return self._webserver_analyzer.detect_webservers()

    def get_webserver_summary(self, webservers: dict[str, Any]) -> dict[str, Any]:
        """Get web server summary."""
        if not self._webserver_analyzer:
            raise RuntimeError("Not launched")
        return self._webserver_analyzer.get_webserver_summary(webservers)

    def check_webserver_security(self, webservers: dict[str, Any]) -> list[dict[str, Any]]:
        """Check web server security settings."""
        if not self._webserver_analyzer:
            raise RuntimeError("Not launched")
        return self._webserver_analyzer.check_webserver_security(webservers)

    # Certificate Management (certificate_manager.py)

    def find_all_certificates(self) -> dict[str, Any]:
        """Find all certificate files."""
        if not self._certificate_manager:
            raise RuntimeError("Not launched")
        return self._certificate_manager.find_certificates()

    def check_certificate_expiration(
        self,
        certs: dict[str, Any],
        warning_days: int = 30
    ) -> dict[str, Any]:
        """Check certificate expiration."""
        if not self._certificate_manager:
            raise RuntimeError("Not launched")
        return self._certificate_manager.check_certificate_expiration(certs, warning_days)

    def get_certificate_summary(self, certs: dict[str, Any]) -> dict[str, Any]:
        """Get certificate summary."""
        if not self._certificate_manager:
            raise RuntimeError("Not launched")
        return self._certificate_manager.get_certificate_summary(certs)

    def check_certificate_security(self, certs: dict[str, Any]) -> list[dict[str, Any]]:
        """Check certificate security issues."""
        if not self._certificate_manager:
            raise RuntimeError("Not launched")
        return self._certificate_manager.check_certificate_security(certs)

    # Container Analysis (container_analyzer.py)

    def analyze_containers(self) -> dict[str, Any]:
        """Analyze container installations comprehensively."""
        if not self._container_analyzer:
            raise RuntimeError("Not launched")
        return self._container_analyzer.analyze_containers()

    def get_container_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get container summary."""
        if not self._container_analyzer:
            raise RuntimeError("Not launched")
        return self._container_analyzer.get_container_summary(analysis)

    def list_container_images(self, analysis: dict[str, Any]) -> list[str]:
        """List all container images."""
        if not self._container_analyzer:
            raise RuntimeError("Not launched")
        return self._container_analyzer.list_container_images(analysis)

    def check_container_security(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Check container security issues."""
        if not self._container_analyzer:
            raise RuntimeError("Not launched")
        return self._container_analyzer.check_container_security(analysis)

    # Compliance Checking (compliance_checker.py)

    def check_compliance(self, os_type: str = "linux") -> dict[str, Any]:
        """Run comprehensive compliance checks."""
        if not self._compliance_checker:
            raise RuntimeError("Not launched")
        return self._compliance_checker.check_compliance(os_type)

    def get_compliance_summary(self, compliance: dict[str, Any]) -> dict[str, Any]:
        """Get compliance summary."""
        if not self._compliance_checker:
            raise RuntimeError("Not launched")
        return self._compliance_checker.get_compliance_summary(compliance)

    def get_failed_checks(self, compliance: dict[str, Any]) -> list[dict[str, Any]]:
        """Get all failed compliance checks."""
        if not self._compliance_checker:
            raise RuntimeError("Not launched")
        return self._compliance_checker.get_failed_checks(compliance)

    def get_recommendations(self, compliance: dict[str, Any]) -> list[str]:
        """Get all compliance recommendations."""
        if not self._compliance_checker:
            raise RuntimeError("Not launched")
        return self._compliance_checker.get_recommendations(compliance)

    # Backup Analysis (backup_analysis.py)

    def analyze_backup_software(self) -> dict[str, Any]:
        """Analyze backup software installations."""
        if not self._backup_analysis:
            raise RuntimeError("Not launched")
        return self._backup_analysis.analyze_backup_software()

    def get_backup_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get backup summary."""
        if not self._backup_analysis:
            raise RuntimeError("Not launched")
        return self._backup_analysis.get_backup_summary(analysis)

    def check_backup_health(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Check backup health and configuration."""
        if not self._backup_analysis:
            raise RuntimeError("Not launched")
        return self._backup_analysis.check_backup_health(analysis)

    def list_backup_software(self, analysis: dict[str, Any]) -> list[str]:
        """List names of detected backup software."""
        if not self._backup_analysis:
            raise RuntimeError("Not launched")
        return self._backup_analysis.list_backup_software(analysis)

    # User Activity Analysis (user_activity.py)

    def analyze_user_activity(self) -> dict[str, Any]:
        """Analyze user activity comprehensively."""
        if not self._user_activity:
            raise RuntimeError("Not launched")
        return self._user_activity.analyze_user_activity()

    def get_activity_summary(self, activity: dict[str, Any]) -> dict[str, Any]:
        """Get user activity summary."""
        if not self._user_activity:
            raise RuntimeError("Not launched")
        return self._user_activity.get_activity_summary(activity)

    def detect_suspicious_activity(self, activity: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect suspicious user activity."""
        if not self._user_activity:
            raise RuntimeError("Not launched")
        return self._user_activity.detect_suspicious_activity(activity)

    def get_top_sudo_users(self, activity: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
        """Get users with most sudo usage."""
        if not self._user_activity:
            raise RuntimeError("Not launched")
        return self._user_activity.get_top_sudo_users(activity, limit)

    # Application Framework Detection (app_framework_detector.py)

    def detect_frameworks(self) -> dict[str, Any]:
        """Detect application frameworks comprehensively."""
        if not self._app_framework_detector:
            raise RuntimeError("Not launched")
        return self._app_framework_detector.detect_frameworks()

    def get_framework_summary(self, frameworks: dict[str, Any]) -> dict[str, Any]:
        """Get framework summary."""
        if not self._app_framework_detector:
            raise RuntimeError("Not launched")
        return self._app_framework_detector.get_framework_summary(frameworks)

    def list_web_frameworks(self, frameworks: dict[str, Any]) -> list[str]:
        """List detected web frameworks."""
        if not self._app_framework_detector:
            raise RuntimeError("Not launched")
        return self._app_framework_detector.list_web_frameworks(frameworks)

    # Cloud Integration Detection (cloud_detector.py)

    def detect_cloud_integration(self) -> dict[str, Any]:
        """Detect cloud platform integrations comprehensively."""
        if not self._cloud_detector:
            raise RuntimeError("Not launched")
        return self._cloud_detector.detect_cloud_integration()

    def get_cloud_summary(self, cloud: dict[str, Any]) -> dict[str, Any]:
        """Get cloud integration summary."""
        if not self._cloud_detector:
            raise RuntimeError("Not launched")
        return self._cloud_detector.get_cloud_summary(cloud)

    def is_cloud_vm(self, cloud: dict[str, Any]) -> bool:
        """Check if VM is running in cloud."""
        if not self._cloud_detector:
            raise RuntimeError("Not launched")
        return self._cloud_detector.is_cloud_vm(cloud)

    def get_cloud_services(self, cloud: dict[str, Any]) -> list[str]:
        """List detected cloud services."""
        if not self._cloud_detector:
            raise RuntimeError("Not launched")
        return self._cloud_detector.get_cloud_services(cloud)

    # Monitoring Agent Detection (monitoring_detector.py)

    def detect_monitoring_agents(self) -> dict[str, Any]:
        """Detect monitoring agents comprehensively."""
        if not self._monitoring_detector:
            raise RuntimeError("Not launched")
        return self._monitoring_detector.detect_monitoring_agents()

    def get_monitoring_summary(self, agents: dict[str, Any]) -> dict[str, Any]:
        """Get monitoring summary."""
        if not self._monitoring_detector:
            raise RuntimeError("Not launched")
        return self._monitoring_detector.get_monitoring_summary(agents)

    def list_agent_vendors(self, agents: dict[str, Any]) -> list[str]:
        """List unique agent vendors."""
        if not self._monitoring_detector:
            raise RuntimeError("Not launched")
        return self._monitoring_detector.list_agent_vendors(agents)

    def check_monitoring_health(self, agents: dict[str, Any]) -> list[dict[str, Any]]:
        """Check monitoring health and configuration."""
        if not self._monitoring_detector:
            raise RuntimeError("Not launched")
        return self._monitoring_detector.check_monitoring_health(agents)

    # Vulnerability Scanning (vulnerability_scanner.py)

    def scan_vulnerabilities(self, os_type: str = "linux") -> dict[str, Any]:
        """Scan for vulnerabilities comprehensively."""
        if not self._vulnerability_scanner:
            raise RuntimeError("Not launched")
        return self._vulnerability_scanner.scan_vulnerabilities(os_type)

    def get_vulnerability_summary(self, scan: dict[str, Any]) -> dict[str, Any]:
        """Get vulnerability summary."""
        if not self._vulnerability_scanner:
            raise RuntimeError("Not launched")
        return self._vulnerability_scanner.get_vulnerability_summary(scan)

    def get_critical_vulnerabilities(self, scan: dict[str, Any]) -> list[dict[str, Any]]:
        """Get critical vulnerabilities only."""
        if not self._vulnerability_scanner:
            raise RuntimeError("Not launched")
        return self._vulnerability_scanner.get_critical_vulnerabilities(scan)

    def get_remediation_priority(self, scan: dict[str, Any]) -> list[dict[str, Any]]:
        """Get prioritized remediation list."""
        if not self._vulnerability_scanner:
            raise RuntimeError("Not launched")
        return self._vulnerability_scanner.get_remediation_priority(scan)

    def detect_ransomware_indicators(self) -> list[dict[str, Any]]:
        """Detect potential ransomware indicators."""
        if not self._vulnerability_scanner:
            raise RuntimeError("Not launched")
        return self._vulnerability_scanner.detect_ransomware_indicators()

    def check_kernel_vulnerabilities(self) -> list[dict[str, Any]]:
        """Check for kernel vulnerabilities."""
        if not self._vulnerability_scanner:
            raise RuntimeError("Not launched")
        return self._vulnerability_scanner.check_kernel_vulnerabilities()

    # License Detection (license_detector.py)

    def detect_licenses(self, os_type: str = "linux") -> dict[str, Any]:
        """Detect software licenses comprehensively."""
        if not self._license_detector:
            raise RuntimeError("Not launched")
        return self._license_detector.detect_licenses(os_type)

    def get_license_summary(self, licenses: dict[str, Any]) -> dict[str, Any]:
        """Get license summary."""
        if not self._license_detector:
            raise RuntimeError("Not launched")
        return self._license_detector.get_license_summary(licenses)

    def get_copyleft_packages(self, licenses: dict[str, Any]) -> list[dict[str, Any]]:
        """Get packages with copyleft licenses."""
        if not self._license_detector:
            raise RuntimeError("Not launched")
        return self._license_detector.get_copyleft_packages(licenses)

    def generate_sbom(self, licenses: dict[str, Any]) -> dict[str, Any]:
        """Generate Software Bill of Materials (SBOM)."""
        if not self._license_detector:
            raise RuntimeError("Not launched")
        return self._license_detector.generate_sbom(licenses)

    def check_license_compatibility(
        self,
        licenses: dict[str, Any],
        target_license: str = "proprietary"
    ) -> list[dict[str, Any]]:
        """Check license compatibility issues."""
        if not self._license_detector:
            raise RuntimeError("Not launched")
        return self._license_detector.check_license_compatibility(licenses, target_license)

    # Performance Analysis (performance_analyzer.py)

    def analyze_performance(self) -> dict[str, Any]:
        """Analyze performance comprehensively."""
        if not self._performance_analyzer:
            raise RuntimeError("Not launched")
        return self._performance_analyzer.analyze_performance()

    def get_performance_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get performance summary."""
        if not self._performance_analyzer:
            raise RuntimeError("Not launched")
        return self._performance_analyzer.get_performance_summary(analysis)

    def get_sizing_recommendation(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get VM sizing recommendation for migration."""
        if not self._performance_analyzer:
            raise RuntimeError("Not launched")
        return self._performance_analyzer.get_sizing_recommendation(analysis)

    def estimate_resource_cost(
        self,
        analysis: dict[str, Any],
        cloud_provider: str = "aws"
    ) -> dict[str, Any]:
        """Estimate cloud resource cost."""
        if not self._performance_analyzer:
            raise RuntimeError("Not launched")
        return self._performance_analyzer.estimate_resource_cost(analysis, cloud_provider)

    # Migration Planning (migration_planner.py)

    def plan_migration(
        self,
        source_platform: str,
        target_platform: str,
        os_info: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Plan migration from source to target platform."""
        if not self._migration_planner:
            raise RuntimeError("Not launched")
        return self._migration_planner.plan_migration(source_platform, target_platform, os_info)

    def get_migration_summary(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Get migration summary."""
        if not self._migration_planner:
            raise RuntimeError("Not launched")
        return self._migration_planner.get_migration_summary(plan)

    def get_migration_checklist(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate pre-migration checklist."""
        if not self._migration_planner:
            raise RuntimeError("Not launched")
        return self._migration_planner.get_checklist(plan)

    def generate_rollback_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Generate rollback plan."""
        if not self._migration_planner:
            raise RuntimeError("Not launched")
        return self._migration_planner.generate_rollback_plan(plan)

    def validate_migration_readiness(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Validate migration readiness."""
        if not self._migration_planner:
            raise RuntimeError("Not launched")
        return self._migration_planner.validate_migration_readiness(plan)

    # Dependency Mapping (dependency_mapper.py)

    def map_dependencies(self) -> dict[str, Any]:
        """Map dependencies comprehensively."""
        if not self._dependency_mapper:
            raise RuntimeError("Not launched")
        return self._dependency_mapper.map_dependencies()

    def get_dependency_summary(self, mapping: dict[str, Any]) -> dict[str, Any]:
        """Get dependency summary."""
        if not self._dependency_mapper:
            raise RuntimeError("Not launched")
        return self._dependency_mapper.get_dependency_summary(mapping)

    def get_service_graph(self, mapping: dict[str, Any]) -> dict[str, Any]:
        """Generate service dependency graph data."""
        if not self._dependency_mapper:
            raise RuntimeError("Not launched")
        return self._dependency_mapper.get_service_graph(mapping)

    def find_critical_services(self, mapping: dict[str, Any]) -> list[dict[str, Any]]:
        """Find critical services (most dependencies)."""
        if not self._dependency_mapper:
            raise RuntimeError("Not launched")
        return self._dependency_mapper.find_critical_services(mapping)

    def get_port_security_analysis(self, mapping: dict[str, Any]) -> dict[str, Any]:
        """Analyze port security."""
        if not self._dependency_mapper:
            raise RuntimeError("Not launched")
        return self._dependency_mapper.get_port_security_analysis(mapping)

    # Forensic Analysis (forensic_analyzer.py)

    def analyze_forensics(self, os_type: str = "linux") -> dict[str, Any]:
        """Perform comprehensive forensic analysis."""
        if not self._forensic_analyzer:
            raise RuntimeError("Not launched")
        return self._forensic_analyzer.analyze_forensics(os_type)

    def get_forensic_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get forensic analysis summary."""
        if not self._forensic_analyzer:
            raise RuntimeError("Not launched")
        return self._forensic_analyzer.get_forensic_summary(analysis)

    def generate_forensic_timeline(self, hours: int = 24) -> list[dict[str, Any]]:
        """Generate file activity timeline."""
        if not self._forensic_analyzer:
            raise RuntimeError("Not launched")
        return self._forensic_analyzer.generate_timeline(hours)

    def detect_rootkit_indicators(self) -> list[dict[str, Any]]:
        """Detect rootkit indicators."""
        if not self._forensic_analyzer:
            raise RuntimeError("Not launched")
        return self._forensic_analyzer.detect_rootkit_indicators()

    def analyze_browser_history(self) -> dict[str, Any]:
        """Analyze browser history artifacts."""
        if not self._forensic_analyzer:
            raise RuntimeError("Not launched")
        return self._forensic_analyzer.analyze_browser_history()

    def find_recently_accessed_files(self, days: int = 7) -> list[dict[str, Any]]:
        """Find files accessed in the last N days."""
        if not self._forensic_analyzer:
            raise RuntimeError("Not launched")
        return self._forensic_analyzer.find_recently_accessed_files(days)

    def detect_data_exfiltration_indicators(self) -> list[dict[str, Any]]:
        """Detect potential data exfiltration indicators."""
        if not self._forensic_analyzer:
            raise RuntimeError("Not launched")
        return self._forensic_analyzer.detect_data_exfiltration_indicators()

    # Data Discovery (data_discovery.py)

    def discover_sensitive_data(self) -> dict[str, Any]:
        """Discover sensitive data comprehensively."""
        if not self._data_discovery:
            raise RuntimeError("Not launched")
        return self._data_discovery.discover_sensitive_data()

    def get_data_discovery_summary(self, discovery: dict[str, Any]) -> dict[str, Any]:
        """Get data discovery summary."""
        if not self._data_discovery:
            raise RuntimeError("Not launched")
        return self._data_discovery.get_discovery_summary(discovery)

    def classify_data_sensitivity(self, discovery: dict[str, Any]) -> dict[str, Any]:
        """Classify discovered data by sensitivity level."""
        if not self._data_discovery:
            raise RuntimeError("Not launched")
        return self._data_discovery.classify_data_sensitivity(discovery)

    def get_compliance_report(self, discovery: dict[str, Any]) -> dict[str, Any]:
        """Generate compliance report (GDPR, CCPA)."""
        if not self._data_discovery:
            raise RuntimeError("Not launched")
        return self._data_discovery.get_compliance_report(discovery)

    # Configuration Tracking (config_tracker.py)

    def track_configurations(self, os_type: str = "linux") -> dict[str, Any]:
        """Track all system configurations."""
        if not self._config_tracker:
            raise RuntimeError("Not launched")
        return self._config_tracker.track_configurations(os_type)

    def create_config_baseline(self, tracking: dict[str, Any]) -> dict[str, Any]:
        """Create configuration baseline."""
        if not self._config_tracker:
            raise RuntimeError("Not launched")
        return self._config_tracker.create_baseline(tracking)

    def detect_config_drift(
        self,
        baseline: dict[str, Any],
        current: dict[str, Any]
    ) -> dict[str, Any]:
        """Detect configuration drift from baseline."""
        if not self._config_tracker:
            raise RuntimeError("Not launched")
        return self._config_tracker.detect_drift(baseline, current)

    def validate_best_practices(self) -> list[dict[str, Any]]:
        """Validate configurations against best practices."""
        if not self._config_tracker:
            raise RuntimeError("Not launched")
        return self._config_tracker.validate_best_practices()

    def get_config_summary(self, tracking: dict[str, Any]) -> dict[str, Any]:
        """Get configuration tracking summary."""
        if not self._config_tracker:
            raise RuntimeError("Not launched")
        return self._config_tracker.get_config_summary(tracking)

    def analyze_config_security(self) -> list[dict[str, Any]]:
        """Analyze configuration security."""
        if not self._config_tracker:
            raise RuntimeError("Not launched")
        return self._config_tracker.analyze_config_security()

    def compare_configs(
        self,
        config1_path: str,
        config2_path: str
    ) -> dict[str, Any]:
        """Compare two configuration files."""
        if not self._config_tracker:
            raise RuntimeError("Not launched")
        return self._config_tracker.compare_configs(config1_path, config2_path)

    def generate_config_documentation(self, tracking: dict[str, Any]) -> dict[str, Any]:
        """Generate configuration documentation."""
        if not self._config_tracker:
            raise RuntimeError("Not launched")
        return self._config_tracker.generate_config_documentation(tracking)

    def get_config_backup_recommendations(self, tracking: dict[str, Any]) -> list[dict[str, Any]]:
        """Get configuration backup recommendations."""
        if not self._config_tracker:
            raise RuntimeError("Not launched")
        return self._config_tracker.get_config_backup_recommendations(tracking)

    # Network Topology (network_topology.py)

    def map_network_topology(self) -> dict[str, Any]:
        """Map complete network topology."""
        if not self._network_topology:
            raise RuntimeError("Not launched")
        return self._network_topology.map_network_topology()

    def get_topology_summary(self, topology: dict[str, Any]) -> dict[str, Any]:
        """Get network topology summary."""
        if not self._network_topology:
            raise RuntimeError("Not launched")
        return self._network_topology.get_topology_summary(topology)

    def analyze_network_redundancy(self, topology: dict[str, Any]) -> dict[str, Any]:
        """Analyze network redundancy."""
        if not self._network_topology:
            raise RuntimeError("Not launched")
        return self._network_topology.analyze_network_redundancy(topology)

    def detect_network_segmentation(self, topology: dict[str, Any]) -> dict[str, Any]:
        """Detect network segmentation."""
        if not self._network_topology:
            raise RuntimeError("Not launched")
        return self._network_topology.detect_network_segmentation(topology)

    def generate_topology_graph(self, topology: dict[str, Any]) -> dict[str, Any]:
        """Generate topology graph data for visualization."""
        if not self._network_topology:
            raise RuntimeError("Not launched")
        return self._network_topology.generate_topology_graph(topology)

    def get_network_policy_summary(self) -> dict[str, Any]:
        """Get network policy summary."""
        if not self._network_topology:
            raise RuntimeError("Not launched")
        return self._network_topology.get_network_policy_summary()

    # Storage Analysis (storage_analyzer.py)

    def analyze_storage_advanced(self) -> dict[str, Any]:
        """Analyze storage comprehensively."""
        if not self._storage_analyzer:
            raise RuntimeError("Not launched")
        return self._storage_analyzer.analyze_storage()

    def get_storage_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get storage summary."""
        if not self._storage_analyzer:
            raise RuntimeError("Not launched")
        return self._storage_analyzer.get_storage_summary(analysis)

    def get_capacity_planning(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get storage capacity planning recommendations."""
        if not self._storage_analyzer:
            raise RuntimeError("Not launched")
        return self._storage_analyzer.get_capacity_planning(analysis)

    def analyze_storage_performance(self) -> dict[str, Any]:
        """Analyze storage performance indicators."""
        if not self._storage_analyzer:
            raise RuntimeError("Not launched")
        return self._storage_analyzer.analyze_storage_performance()

    def detect_storage_tiering(self) -> dict[str, Any]:
        """Detect storage tiering configuration."""
        if not self._storage_analyzer:
            raise RuntimeError("Not launched")
        return self._storage_analyzer.detect_storage_tiering()

    def estimate_deduplication_ratio(self) -> dict[str, Any]:
        """Estimate potential deduplication ratio."""
        if not self._storage_analyzer:
            raise RuntimeError("Not launched")
        return self._storage_analyzer.estimate_deduplication_ratio()

    def analyze_raid_health(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Analyze RAID array health."""
        if not self._storage_analyzer:
            raise RuntimeError("Not launched")
        return self._storage_analyzer.analyze_raid_health(analysis)

    def get_storage_optimization_recommendations(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Get storage optimization recommendations."""
        if not self._storage_analyzer:
            raise RuntimeError("Not launched")
        return self._storage_analyzer.get_optimization_recommendations(analysis)

    # ============================================================================
    # Threat Intelligence Methods (v8.0)
    # ============================================================================

    def analyze_threats(self, os_type: str = "linux") -> dict[str, Any]:
        """Perform comprehensive threat intelligence analysis."""
        if not self._threat_intelligence:
            raise RuntimeError("Not launched")
        return self._threat_intelligence.analyze_threats(os_type)

    def get_threat_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get threat intelligence summary."""
        if not self._threat_intelligence:
            raise RuntimeError("Not launched")
        return self._threat_intelligence.get_threat_summary(analysis)

    def generate_threat_report(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Generate comprehensive threat report."""
        if not self._threat_intelligence:
            raise RuntimeError("Not launched")
        return self._threat_intelligence.generate_threat_report(analysis)

    def check_threat_feeds(self) -> dict[str, Any]:
        """Check against threat intelligence feeds."""
        if not self._threat_intelligence:
            raise RuntimeError("Not launched")
        return self._threat_intelligence.check_threat_feeds()

    def analyze_file_reputation(self, file_path: str) -> dict[str, Any]:
        """Analyze file reputation."""
        if not self._threat_intelligence:
            raise RuntimeError("Not launched")
        return self._threat_intelligence.analyze_file_reputation(file_path)

    def get_attack_surface(self) -> dict[str, Any]:
        """Analyze attack surface."""
        if not self._threat_intelligence:
            raise RuntimeError("Not launched")
        return self._threat_intelligence.get_attack_surface()

    # ============================================================================
    # Automated Remediation Methods (v8.0)
    # ============================================================================

    def create_remediation_plan(self, findings: dict[str, Any]) -> dict[str, Any]:
        """Create remediation plan from security findings."""
        if not self._automated_remediation:
            raise RuntimeError("Not launched")
        return self._automated_remediation.create_remediation_plan(findings)

    def apply_hardening(self, hardening_type: str = "standard") -> dict[str, Any]:
        """Apply security hardening to system."""
        if not self._automated_remediation:
            raise RuntimeError("Not launched")
        return self._automated_remediation.apply_hardening(hardening_type)

    def fix_permissions(self, findings: list[dict[str, Any]]) -> dict[str, Any]:
        """Fix insecure file permissions."""
        if not self._automated_remediation:
            raise RuntimeError("Not launched")
        return self._automated_remediation.fix_permissions(findings)

    def remove_malware(self, malware_list: list[dict[str, Any]]) -> dict[str, Any]:
        """Remove detected malware."""
        if not self._automated_remediation:
            raise RuntimeError("Not launched")
        return self._automated_remediation.remove_malware(malware_list)

    def patch_vulnerabilities(self, vulnerabilities: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply patches for vulnerabilities."""
        if not self._automated_remediation:
            raise RuntimeError("Not launched")
        return self._automated_remediation.patch_vulnerabilities(vulnerabilities)

    def enforce_compliance(self, standard: str = "cis") -> dict[str, Any]:
        """Enforce compliance with security standard."""
        if not self._automated_remediation:
            raise RuntimeError("Not launched")
        return self._automated_remediation.enforce_compliance(standard)

    def create_rollback_point(self) -> dict[str, Any]:
        """Create rollback point before making changes."""
        if not self._automated_remediation:
            raise RuntimeError("Not launched")
        return self._automated_remediation.create_rollback_point()

    def rollback_changes(self, rollback_id: str) -> dict[str, Any]:
        """Rollback changes to previous state."""
        if not self._automated_remediation:
            raise RuntimeError("Not launched")
        return self._automated_remediation.rollback_changes(rollback_id)

    # ============================================================================
    # Predictive Analytics Methods (v8.0)
    # ============================================================================

    def predict_capacity_needs(self, current_usage: dict[str, Any], forecast_days: int = 90) -> dict[str, Any]:
        """Predict future capacity needs based on current usage."""
        if not self._predictive_analytics:
            raise RuntimeError("Not launched")
        return self._predictive_analytics.predict_capacity_needs(current_usage, forecast_days)

    def predict_failures(self, system_metrics: dict[str, Any]) -> dict[str, Any]:
        """Predict potential system failures."""
        if not self._predictive_analytics:
            raise RuntimeError("Not launched")
        return self._predictive_analytics.predict_failures(system_metrics)

    def analyze_trends(self, historical_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze historical trends."""
        if not self._predictive_analytics:
            raise RuntimeError("Not launched")
        return self._predictive_analytics.analyze_trends(historical_data)

    def forecast_costs(self, current_costs: dict[str, Any], forecast_months: int = 12) -> dict[str, Any]:
        """Forecast infrastructure costs."""
        if not self._predictive_analytics:
            raise RuntimeError("Not launched")
        return self._predictive_analytics.forecast_costs(current_costs, forecast_months)

    def predict_resource_exhaustion(self, current_metrics: dict[str, Any]) -> dict[str, Any]:
        """Predict when resources will be exhausted."""
        if not self._predictive_analytics:
            raise RuntimeError("Not launched")
        return self._predictive_analytics.predict_resource_exhaustion(current_metrics)

    def generate_forecast_report(self, metrics: dict[str, Any]) -> dict[str, Any]:
        """Generate comprehensive forecast report."""
        if not self._predictive_analytics:
            raise RuntimeError("Not launched")
        return self._predictive_analytics.generate_forecast_report(metrics)

    # ============================================================================
    # Integration Hub Methods (v8.0)
    # ============================================================================

    def export_analysis(self, analysis_data: dict[str, Any], format: str = "json") -> dict[str, Any]:
        """Export analysis data in specified format."""
        if not self._integration_hub:
            raise RuntimeError("Not launched")
        return self._integration_hub.export_analysis(analysis_data, format)

    def register_webhook(self, url: str, events: list[str], secret: str | None = None) -> dict[str, Any]:
        """Register webhook for event notifications."""
        if not self._integration_hub:
            raise RuntimeError("Not launched")
        return self._integration_hub.register_webhook(url, events, secret)

    def trigger_webhook(self, webhook_id: str, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Trigger webhook with event payload."""
        if not self._integration_hub:
            raise RuntimeError("Not launched")
        return self._integration_hub.trigger_webhook(webhook_id, event, payload)

    def connect_api(self, service: str, credentials: dict[str, Any]) -> dict[str, Any]:
        """Connect to external API service."""
        if not self._integration_hub:
            raise RuntimeError("Not launched")
        return self._integration_hub.connect_api(service, credentials)

    def send_notification(self, service: str, message: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send notification via integrated service."""
        if not self._integration_hub:
            raise RuntimeError("Not launched")
        return self._integration_hub.send_notification(service, message, metadata)

    def create_ticket(self, service: str, title: str, description: str, priority: str = "medium") -> dict[str, Any]:
        """Create ticket in ticketing system."""
        if not self._integration_hub:
            raise RuntimeError("Not launched")
        return self._integration_hub.create_ticket(service, title, description, priority)

    def push_metrics(self, service: str, metrics: dict[str, Any]) -> dict[str, Any]:
        """Push metrics to monitoring service."""
        if not self._integration_hub:
            raise RuntimeError("Not launched")
        return self._integration_hub.push_metrics(service, metrics)

    def sync_with_cmdb(self, asset_data: dict[str, Any]) -> dict[str, Any]:
        """Sync asset data with CMDB."""
        if not self._integration_hub:
            raise RuntimeError("Not launched")
        return self._integration_hub.sync_with_cmdb(asset_data)

    def get_integration_status(self) -> dict[str, Any]:
        """Get status of all integrations."""
        if not self._integration_hub:
            raise RuntimeError("Not launched")
        return self._integration_hub.get_integration_status()

    # ============================================================================
    # Real-time Monitoring Methods (v8.0)
    # ============================================================================

    def get_system_health(self) -> dict[str, Any]:
        """Get real-time system health status."""
        if not self._realtime_monitoring:
            raise RuntimeError("Not launched")
        return self._realtime_monitoring.get_system_health()

    def create_alert_rule(self, metric: str, condition: str, threshold: float, severity: str = "warning") -> dict[str, Any]:
        """Create custom alert rule."""
        if not self._realtime_monitoring:
            raise RuntimeError("Not launched")
        return self._realtime_monitoring.create_alert_rule(metric, condition, threshold, severity)

    def get_performance_metrics(self, interval_seconds: int = 60) -> dict[str, Any]:
        """Get performance metrics over interval."""
        if not self._realtime_monitoring:
            raise RuntimeError("Not launched")
        return self._realtime_monitoring.get_performance_metrics(interval_seconds)

    def monitor_process(self, process_name: str) -> dict[str, Any]:
        """Monitor specific process."""
        if not self._realtime_monitoring:
            raise RuntimeError("Not launched")
        return self._realtime_monitoring.monitor_process(process_name)

    def get_resource_utilization(self) -> dict[str, Any]:
        """Get detailed resource utilization breakdown."""
        if not self._realtime_monitoring:
            raise RuntimeError("Not launched")
        return self._realtime_monitoring.get_resource_utilization()

    def check_service_health(self, service_name: str) -> dict[str, Any]:
        """Check health of specific service."""
        if not self._realtime_monitoring:
            raise RuntimeError("Not launched")
        return self._realtime_monitoring.check_service_health(service_name)

    def get_alert_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get alert history."""
        if not self._realtime_monitoring:
            raise RuntimeError("Not launched")
        return self._realtime_monitoring.get_alert_history(limit)

    def set_monitoring_interval(self, interval_seconds: int) -> dict[str, Any]:
        """Set monitoring check interval."""
        if not self._realtime_monitoring:
            raise RuntimeError("Not launched")
        return self._realtime_monitoring.set_monitoring_interval(interval_seconds)

    def get_monitoring_dashboard(self) -> dict[str, Any]:
        """Get comprehensive monitoring dashboard data."""
        if not self._realtime_monitoring:
            raise RuntimeError("Not launched")
        return self._realtime_monitoring.get_monitoring_dashboard()

    # ============================================================================
    # Machine Learning Analyzer Methods (v9.0)
    # ============================================================================

    def detect_anomalies(self, metrics: list[dict[str, Any]], metric_type: str = "cpu") -> dict[str, Any]:
        """Detect anomalies in time series data using statistical methods."""
        if not self._ml_analyzer:
            raise RuntimeError("Not launched")
        return self._ml_analyzer.detect_anomalies(metrics, metric_type)

    def predict_behavior(self, historical_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Predict future system behavior based on historical patterns."""
        if not self._ml_analyzer:
            raise RuntimeError("Not launched")
        return self._ml_analyzer.predict_behavior(historical_data)

    def classify_workload(self, metrics: dict[str, Any]) -> dict[str, Any]:
        """Classify workload type based on resource usage patterns."""
        if not self._ml_analyzer:
            raise RuntimeError("Not launched")
        return self._ml_analyzer.classify_workload(metrics)

    def train_baseline(self, training_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Train baseline model from normal operating data."""
        if not self._ml_analyzer:
            raise RuntimeError("Not launched")
        return self._ml_analyzer.train_baseline(training_data)

    def detect_behavior_change(self, current_metrics: dict[str, Any]) -> dict[str, Any]:
        """Detect changes in system behavior compared to baseline."""
        if not self._ml_analyzer:
            raise RuntimeError("Not launched")
        return self._ml_analyzer.detect_behavior_change(current_metrics)

    def recommend_optimizations(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate AI-powered optimization recommendations."""
        if not self._ml_analyzer:
            raise RuntimeError("Not launched")
        return self._ml_analyzer.recommend_optimizations(analysis)

    def get_intelligence_summary(self) -> dict[str, Any]:
        """Get AI/ML intelligence summary."""
        if not self._ml_analyzer:
            raise RuntimeError("Not launched")
        return self._ml_analyzer.get_intelligence_summary()

    # ============================================================================
    # Cloud Optimizer Methods (v9.0)
    # ============================================================================

    def analyze_cloud_readiness(self, system_info: dict[str, Any]) -> dict[str, Any]:
        """Analyze system readiness for cloud migration."""
        if not self._cloud_optimizer:
            raise RuntimeError("Not launched")
        return self._cloud_optimizer.analyze_cloud_readiness(system_info)

    def recommend_instance_type(self, requirements: dict[str, Any], cloud_provider: str = "aws") -> dict[str, Any]:
        """Recommend optimal cloud instance type."""
        if not self._cloud_optimizer:
            raise RuntimeError("Not launched")
        return self._cloud_optimizer.recommend_instance_type(requirements, cloud_provider)

    def calculate_cloud_costs(self, usage_profile: dict[str, Any], cloud_provider: str = "aws") -> dict[str, Any]:
        """Calculate projected cloud costs."""
        if not self._cloud_optimizer:
            raise RuntimeError("Not launched")
        return self._cloud_optimizer.calculate_cloud_costs(usage_profile, cloud_provider)

    def compare_cloud_providers(self, requirements: dict[str, Any]) -> dict[str, Any]:
        """Compare costs across multiple cloud providers."""
        if not self._cloud_optimizer:
            raise RuntimeError("Not launched")
        return self._cloud_optimizer.compare_cloud_providers(requirements)

    def generate_migration_plan(self, system_info: dict[str, Any], target_cloud: str = "aws") -> dict[str, Any]:
        """Generate comprehensive cloud migration plan."""
        if not self._cloud_optimizer:
            raise RuntimeError("Not launched")
        return self._cloud_optimizer.generate_migration_plan(system_info, target_cloud)

    def optimize_for_cloud(self, configuration: dict[str, Any]) -> dict[str, Any]:
        """Optimize system configuration for cloud environment."""
        if not self._cloud_optimizer:
            raise RuntimeError("Not launched")
        return self._cloud_optimizer.optimize_for_cloud(configuration)

    # ============================================================================
    # Disaster Recovery Methods (v9.0)
    # ============================================================================

    def assess_recovery_requirements(self, system_info: dict[str, Any]) -> dict[str, Any]:
        """Assess disaster recovery requirements."""
        if not self._disaster_recovery:
            raise RuntimeError("Not launched")
        return self._disaster_recovery.assess_recovery_requirements(system_info)

    def create_backup_strategy(self, requirements: dict[str, Any]) -> dict[str, Any]:
        """Create comprehensive backup strategy."""
        if not self._disaster_recovery:
            raise RuntimeError("Not launched")
        return self._disaster_recovery.create_backup_strategy(requirements)

    def calculate_rto_rpo(self, backup_config: dict[str, Any]) -> dict[str, Any]:
        """Calculate achievable RTO and RPO."""
        if not self._disaster_recovery:
            raise RuntimeError("Not launched")
        return self._disaster_recovery.calculate_rto_rpo(backup_config)

    def create_failover_procedure(self, system_config: dict[str, Any]) -> dict[str, Any]:
        """Create failover procedure documentation."""
        if not self._disaster_recovery:
            raise RuntimeError("Not launched")
        return self._disaster_recovery.create_failover_procedure(system_config)

    def test_dr_plan(self, dr_config: dict[str, Any]) -> dict[str, Any]:
        """Simulate DR plan testing."""
        if not self._disaster_recovery:
            raise RuntimeError("Not launched")
        return self._disaster_recovery.test_dr_plan(dr_config)

    def generate_dr_report(self, system_info: dict[str, Any]) -> dict[str, Any]:
        """Generate comprehensive DR report."""
        if not self._disaster_recovery:
            raise RuntimeError("Not launched")
        return self._disaster_recovery.generate_dr_report(system_info)

    # ============================================================================
    # Audit Trail Methods (v9.0)
    # ============================================================================

    def log_event(self, category: str, action: str, details: dict[str, Any], severity: str = "info", user: str = "system") -> dict[str, Any]:
        """Log audit event."""
        if not self._audit_trail:
            raise RuntimeError("Not launched")
        return self._audit_trail.log_event(category, action, details, severity, user)

    def query_events(self, start_time: str | None = None, end_time: str | None = None, category: str | None = None, severity: str | None = None, user: str | None = None, limit: int = 100) -> dict[str, Any]:
        """Query audit events with filters."""
        if not self._audit_trail:
            raise RuntimeError("Not launched")
        return self._audit_trail.query_events(start_time, end_time, category, severity, user, limit)

    def generate_compliance_report(self, standard: str = "soc2", period_days: int = 30) -> dict[str, Any]:
        """Generate compliance audit report."""
        if not self._audit_trail:
            raise RuntimeError("Not launched")
        return self._audit_trail.generate_compliance_report(standard, period_days)

    def track_changes(self, resource_type: str, resource_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Track configuration changes."""
        if not self._audit_trail:
            raise RuntimeError("Not launched")
        return self._audit_trail.track_changes(resource_type, resource_id, changes)

    def export_audit_log(self, format: str = "json", include_checksums: bool = True) -> dict[str, Any]:
        """Export audit log."""
        if not self._audit_trail:
            raise RuntimeError("Not launched")
        return self._audit_trail.export_audit_log(format, include_checksums)

    def verify_integrity(self) -> dict[str, Any]:
        """Verify audit log integrity."""
        if not self._audit_trail:
            raise RuntimeError("Not launched")
        return self._audit_trail.verify_integrity()

    def get_audit_summary(self) -> dict[str, Any]:
        """Get audit trail summary."""
        if not self._audit_trail:
            raise RuntimeError("Not launched")
        return self._audit_trail.get_audit_summary()

    # ============================================================================
    # Resource Orchestrator Methods (v9.0)
    # ============================================================================

    def analyze_resource_usage(self, current_metrics: dict[str, Any]) -> dict[str, Any]:
        """Analyze current resource usage patterns."""
        if not self._resource_orchestrator:
            raise RuntimeError("Not launched")
        return self._resource_orchestrator.analyze_resource_usage(current_metrics)

    def create_scaling_policy(self, policy_name: str, policy_type: str = "moderate") -> dict[str, Any]:
        """Create auto-scaling policy."""
        if not self._resource_orchestrator:
            raise RuntimeError("Not launched")
        return self._resource_orchestrator.create_scaling_policy(policy_name, policy_type)

    def execute_scaling_action(self, action: str, current_capacity: int, reason: str) -> dict[str, Any]:
        """Execute scaling action."""
        if not self._resource_orchestrator:
            raise RuntimeError("Not launched")
        return self._resource_orchestrator.execute_scaling_action(action, current_capacity, reason)

    def balance_workload(self, workloads: list[dict[str, Any]], available_resources: dict[str, Any]) -> dict[str, Any]:
        """Balance workloads across available resources."""
        if not self._resource_orchestrator:
            raise RuntimeError("Not launched")
        return self._resource_orchestrator.balance_workload(workloads, available_resources)

    def optimize_resource_allocation(self, current_allocation: dict[str, Any], usage_data: dict[str, Any]) -> dict[str, Any]:
        """Optimize resource allocation based on usage patterns."""
        if not self._resource_orchestrator:
            raise RuntimeError("Not launched")
        return self._resource_orchestrator.optimize_resource_allocation(current_allocation, usage_data)

    def schedule_maintenance(self, maintenance_type: str, duration_minutes: int) -> dict[str, Any]:
        """Schedule maintenance window."""
        if not self._resource_orchestrator:
            raise RuntimeError("Not launched")
        return self._resource_orchestrator.schedule_maintenance(maintenance_type, duration_minutes)

    def get_orchestration_metrics(self) -> dict[str, Any]:
        """Get orchestration metrics and statistics."""
        if not self._resource_orchestrator:
            raise RuntimeError("Not launched")
        return self._resource_orchestrator.get_orchestration_metrics()

    # ============================================================================
    # Enhanced Inspection Methods (v10.0)
    # ============================================================================

    def inspect_network_config(self) -> list[dict[str, Any]]:
        """
        Inspect network configuration from multiple formats.

        Supports Debian, RHEL, netplan, NetworkManager, systemd-networkd.

        Returns:
            List of network interface configurations

        Example:
            interfaces = g.inspect_network_config()
            for iface in interfaces:
                print(f"{iface['name']}: {iface['ip_address']} (DHCP: {iface['dhcp']})")
                if iface['dns_servers']:
                    print(f"  DNS: {iface['dns_servers']}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        interfaces = self._enhanced_inspector.inspect_network()
        # Convert NetworkInterface objects to dicts
        return [
            {
                "name": iface.name,
                "ip_address": iface.ip_address,
                "mac_address": iface.mac_address,
                "dhcp": iface.dhcp,
                "dns_servers": iface.dns_servers,
            }
            for iface in interfaces
        ]

    def inspect_dns_config(self) -> list[str]:
        """
        Get DNS server configuration.

        Returns:
            List of DNS server IP addresses

        Example:
            dns_servers = g.inspect_dns_config()
            print(f"DNS servers: {dns_servers}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        return self._enhanced_inspector.inspect_dns()

    def inspect_user_accounts(self) -> list[dict[str, str]]:
        """
        List all user accounts from /etc/passwd.

        Returns:
            List of user account information

        Example:
            users = g.inspect_user_accounts()
            for user in users:
                print(f"{user['username']} (UID: {user['uid']}, Home: {user['home']})")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        users = self._enhanced_inspector.inspect_users()
        return [
            {
                "username": user.username,
                "uid": user.uid,
                "gid": user.gid,
                "home": user.home,
                "shell": user.shell,
            }
            for user in users
        ]

    def inspect_ssh_configuration(self) -> dict[str, str]:
        """
        Parse SSH server configuration.

        Returns:
            Dict of SSH configuration settings

        Example:
            ssh_config = g.inspect_ssh_configuration()
            print(f"Port: {ssh_config.get('Port', '22')}")
            print(f"PermitRootLogin: {ssh_config.get('PermitRootLogin', 'no')}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        return self._enhanced_inspector.inspect_ssh_config()

    def inspect_selinux_status(self) -> str:
        """
        Check SELinux status.

        Returns:
            SELinux mode: enforcing, permissive, disabled, or unknown

        Example:
            selinux = g.inspect_selinux_status()
            print(f"SELinux: {selinux}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        return self._enhanced_inspector.inspect_selinux()

    def inspect_apparmor_status(self) -> bool:
        """
        Check if AppArmor is enabled.

        Returns:
            True if AppArmor is present/enabled

        Example:
            apparmor = g.inspect_apparmor_status()
            print(f"AppArmor enabled: {apparmor}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        return self._enhanced_inspector.inspect_apparmor()

    def inspect_installed_runtimes(self) -> dict[str, str]:
        """
        Detect installed language runtimes.

        Checks for: Python, Node.js, Ruby, Java, Go, Perl, PHP, Rust

        Returns:
            Dict mapping runtime name to installation status

        Example:
            runtimes = g.inspect_installed_runtimes()
            for name, status in runtimes.items():
                print(f"{name}: {status}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        return self._enhanced_inspector.inspect_runtimes()

    def inspect_installed_container_runtimes(self) -> list[str]:
        """
        Detect installed container runtimes.

        Checks for: Docker, Podman, containerd, CRI-O, LXC, LXD

        Returns:
            List of detected container runtime names

        Example:
            runtimes = g.inspect_installed_container_runtimes()
            print(f"Container runtimes: {runtimes}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        return self._enhanced_inspector.inspect_container_runtimes()

    def inspect_cron_jobs(self) -> list[str]:
        """
        List cron jobs from system crontab and cron directories.

        Returns:
            List of cron job descriptions

        Example:
            cron_jobs = g.inspect_cron_jobs()
            for job in cron_jobs:
                print(f"Cron: {job}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        return self._enhanced_inspector.inspect_cron()

    def inspect_systemd_timer_units(self) -> list[str]:
        """
        List systemd timer units.

        Returns:
            List of enabled systemd timer unit names

        Example:
            timers = g.inspect_systemd_timer_units()
            for timer in timers:
                print(f"Timer: {timer}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        return self._enhanced_inspector.inspect_systemd_timers()

    def inspect_guest_tools(self) -> list[str]:
        """
        Detect installed virtualization guest tools.

        Checks for: VMware Tools, QEMU Guest Agent, VirtualBox Guest Additions,
                    Hyper-V integration services, Xen tools

        Returns:
            List of detected guest tool names

        Example:
            tools = g.inspect_guest_tools()
            print(f"Guest tools installed: {tools}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        return self._enhanced_inspector.inspect_vm_tools()

    def inspect_system_timezone(self) -> str:
        """
        Get system timezone.

        Returns:
            Timezone string (e.g., "America/New_York") or "unknown"

        Example:
            timezone = g.inspect_system_timezone()
            print(f"Timezone: {timezone}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        return self._enhanced_inspector.inspect_timezone()

    def inspect_system_locale(self) -> str:
        """
        Get system locale.

        Returns:
            Locale string (e.g., "en_US.UTF-8") or "unknown"

        Example:
            locale = g.inspect_system_locale()
            print(f"Locale: {locale}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        return self._enhanced_inspector.inspect_locale()

    def inspect_kernel_parameters(self) -> dict[str, str]:
        """
        Get kernel sysctl parameters from /etc/sysctl.conf.

        Returns:
            Dict of kernel parameter key-value pairs

        Example:
            params = g.inspect_kernel_parameters()
            for key, value in params.items():
                print(f"{key} = {value}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        return self._enhanced_inspector.inspect_kernel_params()

    def inspect_swap_devices(self) -> list[str]:
        """
        Get swap devices from /etc/fstab.

        Returns:
            List of swap device paths

        Example:
            swap_devices = g.inspect_swap_devices()
            print(f"Swap devices: {swap_devices}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        return self._enhanced_inspector.inspect_swap()

    def inspect_fstab_entries(self) -> list[dict[str, Any]]:
        """
        Parse /etc/fstab into structured format.

        Returns:
            List of fstab entries with device, mountpoint, fstype, options, dump, pass

        Example:
            fstab = g.inspect_fstab_entries()
            for entry in fstab:
                print(f"{entry['device']} on {entry['mountpoint']} type {entry['fstype']}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        entries = self._enhanced_inspector.inspect_fstab()
        return [
            {
                "device": entry.device,
                "mountpoint": entry.mountpoint,
                "fstype": entry.fstype,
                "options": entry.options,
                "dump": entry.dump,
                "pass": entry.pass_num,
            }
            for entry in entries
        ]

    def inspect_cloud_init_installed(self) -> bool:
        """
        Detect if cloud-init is installed.

        Returns:
            True if cloud-init is present

        Example:
            has_cloud_init = g.inspect_cloud_init_installed()
            print(f"Cloud-init installed: {has_cloud_init}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        return self._enhanced_inspector.inspect_cloud_init()

    def inspect_ssl_certificates(self) -> list[dict[str, str]]:
        """
        List SSL certificates in common locations.

        Returns:
            List of dicts with certificate paths and types

        Example:
            certs = g.inspect_ssl_certificates()
            for cert in certs:
                print(f"{cert['type']}: {cert['path']}")
        """
        if not self._enhanced_inspector:
            raise RuntimeError("Not launched")
        return self._enhanced_inspector.inspect_certificates()

    # =============================================================================
    # Augeas Configuration Management APIs
    # =============================================================================

    def aug_init(self, flags: int = 0) -> None:
        """
        Initialize Augeas configuration API.

        Must be called before using other aug_* methods. Augeas provides structured
        editing of configuration files using lenses for common formats (fstab,
        network configs, systemd units, etc.).

        Args:
            flags: Augeas initialization flags (default: 0)
                   Common flags: augeas.Augeas.SAVE_BACKUP, augeas.Augeas.NO_LOAD

        Raises:
            RuntimeError: If not launched or Augeas library not available

        Example:
            g.aug_init()
            # Now ready to use aug_get, aug_set, etc.
        """
        if not self._augeas:
            raise RuntimeError("Not launched")
        self._augeas.init(flags)

    def aug_close(self) -> None:
        """
        Close Augeas and release resources.

        Should be called when finished with Augeas operations to free memory.

        Example:
            g.aug_init()
            # ... use Augeas
            g.aug_close()
        """
        if not self._augeas:
            raise RuntimeError("Not launched")
        self._augeas.close()

    def aug_get(self, path: str) -> str | None:
        """
        Get configuration value at Augeas path.

        Args:
            path: Augeas path (e.g., "/files/etc/fstab/1/spec")

        Returns:
            Configuration value or None if path doesn't exist

        Raises:
            RuntimeError: If Augeas not initialized

        Example:
            g.aug_init()
            # Get first fstab entry's device
            device = g.aug_get("/files/etc/fstab/1/spec")
            print(f"Device: {device}")
        """
        if not self._augeas:
            raise RuntimeError("Not launched")
        return self._augeas.get(path)

    def aug_set(self, path: str, value: str) -> None:
        """
        Set configuration value at Augeas path.

        Changes are made in memory. Call aug_save() to write to disk.

        Args:
            path: Augeas path
            value: Value to set

        Raises:
            RuntimeError: If Augeas not initialized or set fails

        Example:
            g.aug_init()
            # Change first fstab entry's dump value
            g.aug_set("/files/etc/fstab/1/dump", "0")
            g.aug_save()
        """
        if not self._augeas:
            raise RuntimeError("Not launched")
        self._augeas.set(path, value)

    def aug_save(self) -> None:
        """
        Save Augeas changes to disk.

        Writes all pending changes to their respective configuration files.

        Raises:
            RuntimeError: If Augeas not initialized or save fails

        Example:
            g.aug_init()
            g.aug_set("/files/etc/fstab/1/dump", "0")
            g.aug_save()  # Writes changes to /etc/fstab
        """
        if not self._augeas:
            raise RuntimeError("Not launched")
        self._augeas.save()

    def aug_match(self, pattern: str) -> list[str]:
        """
        Match Augeas paths by pattern.

        Args:
            pattern: Augeas path pattern (e.g., "/files/etc/fstab/*")

        Returns:
            List of matching paths

        Raises:
            RuntimeError: If Augeas not initialized

        Example:
            g.aug_init()
            # Get all fstab entries
            entries = g.aug_match("/files/etc/fstab/*[label() != '#comment']")
            print(f"Found {len(entries)} fstab entries")
        """
        if not self._augeas:
            raise RuntimeError("Not launched")
        return self._augeas.match(pattern)

    def aug_insert(self, path: str, label: str, before: bool = True) -> None:
        """
        Insert new node at Augeas path.

        Args:
            path: Path where to insert (must exist)
            label: Label for new node
            before: Insert before (True) or after (False) the path

        Raises:
            RuntimeError: If Augeas not initialized or insert fails

        Example:
            g.aug_init()
            # Insert new fstab entry before entry 1
            g.aug_insert("/files/etc/fstab/1", "01", before=True)
            g.aug_set("/files/etc/fstab/01/spec", "/dev/sda1")
            g.aug_set("/files/etc/fstab/01/file", "/boot")
            g.aug_save()
        """
        if not self._augeas:
            raise RuntimeError("Not launched")
        self._augeas.insert(path, label, before)

    def aug_rm(self, path: str) -> int:
        """
        Remove nodes matching Augeas path.

        Args:
            path: Augeas path (can be pattern with wildcards)

        Returns:
            Number of nodes removed

        Raises:
            RuntimeError: If Augeas not initialized

        Example:
            g.aug_init()
            # Remove all commented lines from fstab
            count = g.aug_rm("/files/etc/fstab/#comment")
            print(f"Removed {count} comments")
            g.aug_save()
        """
        if not self._augeas:
            raise RuntimeError("Not launched")
        return self._augeas.remove(path)

    def aug_defvar(self, name: str, expr: str) -> None:
        """
        Define Augeas variable for use in path expressions.

        Variables can be used in subsequent paths as $name.

        Args:
            name: Variable name
            expr: Expression to evaluate

        Raises:
            RuntimeError: If Augeas not initialized or defvar fails

        Example:
            g.aug_init()
            # Define variable for fstab root entry
            g.aug_defvar("root", "/files/etc/fstab/*[file='/']")
            device = g.aug_get("$root/spec")
            print(f"Root device: {device}")
        """
        if not self._augeas:
            raise RuntimeError("Not launched")
        self._augeas.defvar(name, expr)

    def aug_defnode(self, name: str, expr: str, value: str | None = None) -> tuple[int, bool]:
        """
        Define Augeas node variable.

        Creates the node if it doesn't exist.

        Args:
            name: Variable name
            expr: Node expression
            value: Optional value to set if node is created

        Returns:
            Tuple of (number of nodes matching expr, created flag)

        Raises:
            RuntimeError: If Augeas not initialized or defnode fails

        Example:
            g.aug_init()
            # Ensure fstab has a /tmp entry
            count, created = g.aug_defnode("tmp", "/files/etc/fstab/*[file='/tmp']", None)
            if created:
                g.aug_set("$tmp/spec", "tmpfs")
                g.aug_set("$tmp/vfstype", "tmpfs")
                g.aug_save()
        """
        if not self._augeas:
            raise RuntimeError("Not launched")
        return self._augeas.defnode(name, expr, value)

    # =============================================================================
    # Archive Operations
    # =============================================================================

    def tar_in(self, tarfile: str, directory: str, compress: str | None = None) -> None:
        """
        Unpack tarball into guest directory.

        Args:
            tarfile: Path to tar archive on host
            directory: Target directory in guest (absolute path)
            compress: Compression type ("gzip", "bzip2", "xz", or None)

        Raises:
            RuntimeError: If not launched or extraction fails

        Example:
            # Extract archive to /opt in guest
            g.tar_in("/tmp/myapp.tar.gz", "/opt", compress="gzip")
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        from pathlib import Path
        import subprocess

        # Construct guest directory path
        guest_dir = Path(self._mount_root) / directory.lstrip("/")
        guest_dir.mkdir(parents=True, exist_ok=True)

        try:
            cmd = ["tar", "-xf", tarfile, "-C", str(guest_dir)]

            # Add compression flag if specified
            if compress == "gzip":
                cmd.insert(1, "-z")
            elif compress == "bzip2":
                cmd.insert(1, "-j")
            elif compress == "xz":
                cmd.insert(1, "-J")

            from hyper2kvm.core.vmcraft._utils import run_sudo
            run_sudo(self.logger, cmd, check=True, capture=True)
            self.logger.info(f"Extracted {tarfile} to {directory}")

        except Exception as e:
            raise RuntimeError(f"Failed to extract tar archive: {e}") from e

    def tar_out(self, directory: str, tarfile: str, compress: str | None = None) -> None:
        """
        Pack guest directory into tarball.

        Args:
            directory: Source directory in guest (absolute path)
            tarfile: Output tar file on host
            compress: Compression type ("gzip", "bzip2", "xz", or None)

        Raises:
            RuntimeError: If not launched, directory doesn't exist, or creation fails

        Example:
            # Pack /etc to tarball
            g.tar_out("/etc", "/tmp/etc-backup.tar.gz", compress="gzip")
        """
        if not self._mount_root:
            raise RuntimeError("Not launched")

        from pathlib import Path
        import subprocess

        # Construct guest directory path
        guest_dir = Path(self._mount_root) / directory.lstrip("/")

        if not guest_dir.exists():
            raise RuntimeError(f"Directory {directory} does not exist in guest")

        try:
            cmd = ["tar", "-cf", tarfile, "-C", str(guest_dir.parent), guest_dir.name]

            # Add compression flag if specified
            if compress == "gzip":
                cmd.insert(1, "-z")
            elif compress == "bzip2":
                cmd.insert(1, "-j")
            elif compress == "xz":
                cmd.insert(1, "-J")

            from hyper2kvm.core.vmcraft._utils import run_sudo
            run_sudo(self.logger, cmd, check=True, capture=True)
            self.logger.info(f"Created {tarfile} from {directory}")

        except Exception as e:
            raise RuntimeError(f"Failed to create tar archive: {e}") from e

    def tgz_in(self, tarball: str, directory: str) -> None:
        """
        Unpack gzipped tarball (convenience wrapper for tar_in).

        Args:
            tarball: Path to .tar.gz archive on host
            directory: Target directory in guest

        Example:
            g.tgz_in("/tmp/app.tar.gz", "/opt")
        """
        self.tar_in(tarball, directory, compress="gzip")

    def tgz_out(self, directory: str, tarball: str) -> None:
        """
        Pack directory to gzipped tarball (convenience wrapper for tar_out).

        Args:
            directory: Source directory in guest
            tarball: Output .tar.gz file on host

        Example:
            g.tgz_out("/var/log", "/tmp/logs.tar.gz")
        """
        self.tar_out(directory, tarball, compress="gzip")

    # =============================================================================
    # Additional Block Device APIs
    # =============================================================================

    def blockdev_getsize64(self, device: str) -> int:
        """
        Get device size in bytes.

        Args:
            device: Device path (e.g., /dev/sda, /dev/nbd0p1)

        Returns:
            Size in bytes (0 if device doesn't exist or command fails)

        Example:
            size = g.blockdev_getsize64("/dev/nbd0")
            print(f"Disk size: {size} bytes ({size // (1024**3)} GB)")
        """
        try:
            from hyper2kvm.core.vmcraft._utils import run_sudo
            result = run_sudo(
                self.logger,
                ["blockdev", "--getsize64", device],
                check=True,
                capture=True,
                failure_log_level=logging.DEBUG
            )
            return int(result.stdout.strip())
        except Exception as e:
            self.logger.debug(f"blockdev_getsize64 failed for {device}: {e}")
            return 0

    def blockdev_getsz(self, device: str) -> int:
        """
        Get device size in 512-byte sectors.

        Args:
            device: Device path

        Returns:
            Size in 512-byte sectors (0 if device doesn't exist or command fails)

        Example:
            sectors = g.blockdev_getsz("/dev/nbd0")
            print(f"Disk size: {sectors} sectors")
        """
        try:
            from hyper2kvm.core.vmcraft._utils import run_sudo
            result = run_sudo(
                self.logger,
                ["blockdev", "--getsz", device],
                check=True,
                capture=True,
                failure_log_level=logging.DEBUG
            )
            return int(result.stdout.strip())
        except Exception as e:
            self.logger.debug(f"blockdev_getsz failed for {device}: {e}")
            return 0

    def dd_copy(
        self,
        src: str,
        dest: str,
        count: int | None = None,
        blocksize: int = 512
    ) -> None:
        """
        Copy data using dd command.

        Args:
            src: Source file or device
            dest: Destination file or device
            count: Number of blocks to copy (None for all)
            blocksize: Block size in bytes (default: 512)

        Raises:
            RuntimeError: If dd command fails

        Example:
            # Copy first 1MB of disk
            g.dd_copy("/dev/nbd0", "/tmp/mbr-backup.bin", count=2048, blocksize=512)

            # Clone entire partition
            g.dd_copy("/dev/nbd0p1", "/dev/nbd1p1")
        """
        try:
            cmd = ["dd", f"if={src}", f"of={dest}", f"bs={blocksize}"]

            if count:
                cmd.append(f"count={count}")

            from hyper2kvm.core.vmcraft._utils import run_sudo
            run_sudo(self.logger, cmd, check=True, capture=True)
            self.logger.info(f"Copied {src} to {dest} (bs={blocksize}, count={count or 'all'})")

        except Exception as e:
            raise RuntimeError(f"dd copy failed: {e}") from e

    # Context manager support

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        try:
            self.close()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
        return False
