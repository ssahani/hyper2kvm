# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/metrics.py
"""
Prometheus metrics for hyper2kvm.

Provides comprehensive metrics for monitoring VM migrations, disk conversions,
VMware API calls, and system health.

All metrics use stdlib prometheus_client - no optional dependencies needed!
RHEL 10 compatible.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

try:
    from prometheus_client import Counter, Gauge, Histogram, Summary, Info, CollectorRegistry, REGISTRY

    PROMETHEUS_AVAILABLE = True
except ImportError:
    # Fallback - metrics become no-ops
    PROMETHEUS_AVAILABLE = False

    # Stub classes for when prometheus_client is not available
    class Counter:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

        def inc(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

    class Gauge:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

        def inc(self, *args, **kwargs):
            pass

        def dec(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

    class Histogram:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

        def time(self):
            """Return a no-op context manager."""
            import contextlib

            return contextlib.nullcontext()

    class Summary:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

    class Info:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

        def info(self, *args, **kwargs):
            pass

    REGISTRY = None  # type: ignore


# Use default registry if available
registry = REGISTRY if PROMETHEUS_AVAILABLE else None

# ============================================================================
# Migration Metrics
# ============================================================================

migrations_total = Counter(
    "hyper2kvm_migrations_total",
    "Total number of VM migrations",
    ["hypervisor", "status"],  # status: success, failed
    registry=registry,
)

migrations_active = Gauge(
    "hyper2kvm_migrations_active", "Number of currently active migrations", registry=registry
)

migration_duration_seconds = Histogram(
    "hyper2kvm_migration_duration_seconds",
    "Migration duration in seconds",
    ["hypervisor", "vm_name"],
    buckets=[60, 300, 900, 1800, 3600, 7200, 14400, 28800],  # 1m, 5m, 15m, 30m, 1h, 2h, 4h, 8h
    registry=registry,
)

# ============================================================================
# Disk Conversion Metrics
# ============================================================================

disk_conversion_bytes_total = Counter(
    "hyper2kvm_disk_conversion_bytes_total",
    "Total bytes converted across all migrations",
    ["source_format", "target_format"],
    registry=registry,
)

disk_conversion_duration_seconds = Histogram(
    "hyper2kvm_disk_conversion_duration_seconds",
    "Disk conversion duration in seconds",
    ["source_format", "target_format"],
    buckets=[10, 30, 60, 300, 600, 1800, 3600, 7200],  # 10s, 30s, 1m, 5m, 10m, 30m, 1h, 2h
    registry=registry,
)

disk_conversion_throughput_mbps = Histogram(
    "hyper2kvm_disk_conversion_throughput_mbps",
    "Disk conversion throughput in MB/s",
    ["source_format", "target_format"],
    buckets=[10, 50, 100, 200, 500, 1000, 2000],
    registry=registry,
)

# ============================================================================
# Network/Fixer Metrics
# ============================================================================

network_fixes_total = Counter(
    "hyper2kvm_network_fixes_total",
    "Number of network configuration fixes applied",
    ["os_type", "fix_type"],  # os_type: linux, windows; fix_type: ifcfg, netplan, etc
    registry=registry,
)

bootloader_fixes_total = Counter(
    "hyper2kvm_bootloader_fixes_total",
    "Number of bootloader fixes applied",
    ["os_type", "fix_type"],
    registry=registry,
)

windows_fixes_total = Counter(
    "hyper2kvm_windows_fixes_total",
    "Number of Windows-specific fixes applied",
    ["fix_type"],  # virtio_injection, registry_edit, etc
    registry=registry,
)

# ============================================================================
# VMware API Metrics
# ============================================================================

vmware_api_calls_total = Counter(
    "hyper2kvm_vmware_api_calls_total",
    "Total VMware API calls",
    ["operation", "status"],  # operation: connect, get_vm, export, etc; status: success, error
    registry=registry,
)

vmware_api_duration_seconds = Histogram(
    "hyper2kvm_vmware_api_duration_seconds",
    "VMware API call duration in seconds",
    ["operation"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
    registry=registry,
)

vmware_downloads_bytes_total = Counter(
    "hyper2kvm_vmware_downloads_bytes_total", "Total bytes downloaded from VMware", registry=registry
)

# ============================================================================
# Error Metrics
# ============================================================================

errors_total = Counter(
    "hyper2kvm_errors_total",
    "Total errors encountered",
    ["error_type", "component"],  # error_type: NetworkError, ValidationError, etc
    registry=registry,
)

# ============================================================================
# System Metrics
# ============================================================================

process_start_time_seconds = Gauge(
    "hyper2kvm_process_start_time_seconds", "Unix timestamp when process started", registry=registry
)

# Set start time
import time

if PROMETHEUS_AVAILABLE:
    process_start_time_seconds.set(time.time())

# ============================================================================
# Build Info
# ============================================================================

build_info = Info("hyper2kvm_build", "Build information", registry=registry)

if PROMETHEUS_AVAILABLE:
    build_info.info(
        {
            "version": "0.1.0",
            "python_version": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
            "commit": os.getenv("GIT_COMMIT", "unknown"),
        }
    )

# ============================================================================
# Validation Metrics
# ============================================================================

validations_total = Counter(
    "hyper2kvm_validations_total",
    "Total validation checks performed",
    ["validation_type", "status"],  # validation_type: config, disk, boot; status: success, failed
    registry=registry,
)

# ============================================================================
# Batch/Manifest Processing Metrics
# ============================================================================

manifests_processed_total = Counter(
    "hyper2kvm_manifests_processed_total",
    "Total manifest files processed",
    ["status"],  # status: success, failed
    registry=registry,
)

manifest_vms_total = Counter(
    "hyper2kvm_manifest_vms_total",
    "Total VMs processed from manifests",
    ["status"],
    registry=registry,
)

# ============================================================================
# Helper Functions
# ============================================================================


def get_metrics() -> bytes:
    """
    Get current metrics in Prometheus format.

    Returns:
        Metrics in text format (bytes)
    """
    if not PROMETHEUS_AVAILABLE:
        return b"# Prometheus client not available\n"

    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

    return generate_latest(registry)


def is_metrics_enabled() -> bool:
    """Check if metrics collection is enabled."""
    return PROMETHEUS_AVAILABLE


# Export commonly used metrics for convenience
__all__ = [
    "PROMETHEUS_AVAILABLE",
    "migrations_total",
    "migrations_active",
    "migration_duration_seconds",
    "disk_conversion_bytes_total",
    "disk_conversion_duration_seconds",
    "disk_conversion_throughput_mbps",
    "network_fixes_total",
    "bootloader_fixes_total",
    "windows_fixes_total",
    "vmware_api_calls_total",
    "vmware_api_duration_seconds",
    "vmware_downloads_bytes_total",
    "errors_total",
    "validations_total",
    "manifests_processed_total",
    "manifest_vms_total",
    "get_metrics",
    "is_metrics_enabled",
]
