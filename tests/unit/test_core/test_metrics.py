# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Tests for Prometheus metrics.

Tests metrics collection and HTTP endpoint.
"""

import pytest
from hyper2kvm.core.metrics import (
    PROMETHEUS_AVAILABLE,
    migrations_total,
    migrations_active,
    disk_conversion_bytes_total,
    get_metrics,
    is_metrics_enabled,
)


class TestMetricsAvailability:
    """Test metrics availability detection."""

    def test_prometheus_flag_is_boolean(self):
        """Test that PROMETHEUS_AVAILABLE is a boolean."""
        assert isinstance(PROMETHEUS_AVAILABLE, bool)

    def test_is_metrics_enabled(self):
        """Test is_metrics_enabled function."""
        result = is_metrics_enabled()
        assert isinstance(result, bool)
        assert result == PROMETHEUS_AVAILABLE


class TestMetricsBasicOperations:
    """Test basic metrics operations."""

    def test_counter_increment(self):
        """Test that counters can be incremented."""
        # Should not raise even if prometheus_client not available
        migrations_total.labels(hypervisor="vmware", status="success").inc()
        migrations_total.labels(hypervisor="vmware", status="failed").inc()

    def test_gauge_operations(self):
        """Test gauge inc/dec/set operations."""
        # Should not raise even if prometheus_client not available
        migrations_active.inc()
        migrations_active.dec()
        migrations_active.set(5)

    def test_histogram_observe(self):
        """Test histogram observation."""
        from hyper2kvm.core.metrics import migration_duration_seconds

        # Should not raise
        migration_duration_seconds.labels(hypervisor="vmware", vm_name="test").observe(123.45)

    def test_counter_with_bytes(self):
        """Test counter with large byte values."""
        # Should not raise
        disk_conversion_bytes_total.labels(source_format="vmdk", target_format="qcow2").inc(1024 * 1024 * 1024)


class TestMetricsContextManager:
    """Test metrics context managers."""

    def test_histogram_time_context(self):
        """Test histogram time() context manager."""
        from hyper2kvm.core.metrics import migration_duration_seconds
        import time

        # Should not raise
        with migration_duration_seconds.labels(hypervisor="vmware", vm_name="test").time():
            time.sleep(0.01)


class TestGetMetrics:
    """Test get_metrics function."""

    def test_get_metrics_returns_bytes(self):
        """Test that get_metrics returns bytes."""
        metrics = get_metrics()
        assert isinstance(metrics, bytes)

    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not available")
    def test_get_metrics_contains_data(self):
        """Test that metrics contain actual data when available."""
        # Increment some metrics
        migrations_total.labels(hypervisor="test", status="success").inc()

        metrics = get_metrics().decode("utf-8")

        # Should contain metric name
        assert "hyper2kvm" in metrics

    def test_get_metrics_works_without_prometheus(self):
        """Test that get_metrics works even without prometheus_client."""
        # Should not raise regardless of PROMETHEUS_AVAILABLE
        metrics = get_metrics()
        assert isinstance(metrics, bytes)


class TestMetricsLabels:
    """Test metrics with different label combinations."""

    def test_multiple_hypervisors(self):
        """Test metrics for different hypervisors."""
        # Should not raise
        migrations_total.labels(hypervisor="vmware", status="success").inc()
        migrations_total.labels(hypervisor="hyperv", status="success").inc()
        migrations_total.labels(hypervisor="aws", status="success").inc()

    def test_disk_format_combinations(self):
        """Test disk conversion metrics with various formats."""
        from hyper2kvm.core.metrics import disk_conversion_bytes_total

        formats = [("vmdk", "qcow2"), ("vhd", "raw"), ("ova", "qcow2")]

        for source, target in formats:
            disk_conversion_bytes_total.labels(source_format=source, target_format=target).inc(1000)

    def test_error_types(self):
        """Test error metrics with different types."""
        from hyper2kvm.core.metrics import errors_total

        error_types = ["NetworkError", "ValidationError", "ConversionError"]
        components = ["orchestrator", "converter", "fixer"]

        for error_type in error_types:
            for component in components:
                errors_total.labels(error_type=error_type, component=component).inc()


class TestMetricsRealism:
    """Test realistic metrics scenarios."""

    def test_complete_migration_metrics(self):
        """Test a complete migration workflow with metrics."""
        from hyper2kvm.core.metrics import (
            migrations_total,
            migrations_active,
            migration_duration_seconds,
            disk_conversion_bytes_total,
        )

        # Start migration
        migrations_active.inc()

        # Record disk conversion
        disk_conversion_bytes_total.labels(source_format="vmdk", target_format="qcow2").inc(5 * 1024**3)

        # Record duration
        migration_duration_seconds.labels(hypervisor="vmware", vm_name="web-01").observe(1234.56)

        # End migration
        migrations_active.dec()
        migrations_total.labels(hypervisor="vmware", status="success").inc()

        # No assertions needed - just verify no exceptions

    def test_batch_processing_metrics(self):
        """Test metrics for batch processing."""
        from hyper2kvm.core.metrics import manifests_processed_total, manifest_vms_total

        # Process manifest with 5 VMs
        manifests_processed_total.labels(status="success").inc()

        for _ in range(5):
            manifest_vms_total.labels(status="success").inc()

    def test_vmware_api_metrics(self):
        """Test VMware API call metrics."""
        from hyper2kvm.core.metrics import vmware_api_calls_total, vmware_api_duration_seconds

        operations = ["connect", "get_vm", "export", "download"]

        for op in operations:
            vmware_api_calls_total.labels(operation=op, status="success").inc()
            vmware_api_duration_seconds.labels(operation=op).observe(1.23)
