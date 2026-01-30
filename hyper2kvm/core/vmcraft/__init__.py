# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/vmcraft/__init__.py
"""
VMCraft: Python library for VM disk image manipulation.

Drop-in replacement for libguestfs that uses:
- qemu-nbd for disk image access
- Native Linux tools (mount, lvm, cryptsetup, etc.)
- Python file I/O for guest filesystem operations

This module provides a modular, maintainable architecture while preserving
complete backward compatibility with the original monolithic implementation.
"""

# Export main VMCraft class for backward compatibility
from .main import VMCraft

# Export custom exception classes
from ._utils import (
    VMCraftError,
    MountError,
    DeviceError,
    FileSystemError,
    RegistryError,
    DetectionError,
    CacheError,
)

# Export specialized modules (for advanced usage)
from .windows_users import WindowsUserManager
from .linux_services import LinuxServiceManager
from .windows_services import WindowsServiceManager
from .windows_applications import WindowsApplicationManager
from .network_config import NetworkConfigAnalyzer
from .firewall_analyzer import FirewallAnalyzer
from .advanced_analysis import AdvancedAnalyzer
from .export import ExportManager
from .scheduled_tasks import ScheduledTaskAnalyzer
from .ssh_analyzer import SSHAnalyzer
from .log_analyzer import LogAnalyzer
from .hardware_detector import HardwareDetector
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

__all__ = [
    # Main API
    "VMCraft",
    # Exception classes
    "VMCraftError",
    "MountError",
    "DeviceError",
    "FileSystemError",
    "RegistryError",
    "DetectionError",
    "CacheError",
    # Specialized modules
    "WindowsUserManager",
    "LinuxServiceManager",
    "WindowsServiceManager",
    "WindowsApplicationManager",
    "NetworkConfigAnalyzer",
    "FirewallAnalyzer",
    "AdvancedAnalyzer",
    "ExportManager",
    "ScheduledTaskAnalyzer",
    "SSHAnalyzer",
    "LogAnalyzer",
    "HardwareDetector",
    "DatabaseDetector",
    "WebServerAnalyzer",
    "CertificateManager",
    "ContainerAnalyzer",
    "ComplianceChecker",
    "BackupAnalysis",
    "UserActivityAnalyzer",
    "AppFrameworkDetector",
    "CloudDetector",
    "MonitoringDetector",
    "VulnerabilityScanner",
    "LicenseDetector",
    "PerformanceAnalyzer",
    "MigrationPlanner",
    "DependencyMapper",
    "ForensicAnalyzer",
    "DataDiscovery",
    "ConfigTracker",
    "NetworkTopology",
    "StorageAnalyzer",
    "ThreatIntelligence",
    "AutomatedRemediation",
    "PredictiveAnalytics",
    "IntegrationHub",
    "RealtimeMonitoring",
    "MLAnalyzer",
    "CloudOptimizer",
    "DisasterRecovery",
    "AuditTrail",
    "ResourceOrchestrator",
]
