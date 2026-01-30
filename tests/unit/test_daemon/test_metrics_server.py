# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Tests for Prometheus metrics HTTP server.
"""

import pytest
import time
from unittest.mock import Mock, patch
import urllib.request
import urllib.error

from hyper2kvm.daemon.metrics_server import (
    MetricsServer,
    start_metrics_server,
    stop_metrics_server,
    get_metrics_server,
)
from hyper2kvm.core.metrics import PROMETHEUS_AVAILABLE


class TestMetricsServer:
    """Test metrics HTTP server."""

    def test_server_starts_and_stops(self):
        """Test that server can start and stop."""
        server = MetricsServer(port=9092)  # Use non-standard port to avoid conflicts

        assert not server.is_running()

        server.start()
        time.sleep(0.5)  # Give server time to start
        assert server.is_running()

        server.stop()
        time.sleep(0.5)
        assert not server.is_running()

    def test_server_metrics_endpoint(self):
        """Test /metrics endpoint."""
        server = MetricsServer(port=9093)

        try:
            server.start()
            time.sleep(0.5)

            # Try to fetch metrics
            try:
                response = urllib.request.urlopen("http://localhost:9093/metrics", timeout=2)
                data = response.read()

                assert isinstance(data, bytes)
                assert len(data) > 0

                # If prometheus available, should contain metric data
                if PROMETHEUS_AVAILABLE:
                    assert b"hyper2kvm" in data or b"#" in data  # Prometheus format

            except urllib.error.URLError as e:
                pytest.fail(f"Failed to connect to metrics endpoint: {e}")

        finally:
            server.stop()

    def test_server_health_endpoint(self):
        """Test /health endpoint."""
        server = MetricsServer(port=9094)

        try:
            server.start()
            time.sleep(0.5)

            response = urllib.request.urlopen("http://localhost:9094/health", timeout=2)
            data = response.read()

            assert isinstance(data, bytes)
            assert b"OK" in data or b"Disabled" in data

        finally:
            server.stop()

    def test_server_index_endpoint(self):
        """Test / endpoint (index page)."""
        server = MetricsServer(port=9095)

        try:
            server.start()
            time.sleep(0.5)

            response = urllib.request.urlopen("http://localhost:9095/", timeout=2)
            data = response.read()

            assert isinstance(data, bytes)
            # Should contain HTML
            assert b"<html>" in data.lower() or b"<!doctype" in data.lower()
            assert b"metrics" in data.lower()

        finally:
            server.stop()

    def test_server_404_on_invalid_path(self):
        """Test that server returns 404 for invalid paths."""
        server = MetricsServer(port=9096)

        try:
            server.start()
            time.sleep(0.5)

            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen("http://localhost:9096/invalid", timeout=2)

            assert exc_info.value.code == 404

        finally:
            server.stop()

    def test_server_cannot_start_twice(self):
        """Test that server cannot start if already running."""
        server = MetricsServer(port=9097)

        try:
            server.start()
            time.sleep(0.5)

            # Try to start again - should log warning but not fail
            server.start()

            # Should still be running
            assert server.is_running()

        finally:
            server.stop()


class TestGlobalMetricsServer:
    """Test global metrics server functions."""

    def test_start_global_server(self):
        """Test starting global metrics server."""
        try:
            server = start_metrics_server(port=9098)
            time.sleep(0.5)

            assert server is not None
            assert server.is_running()

            # Get global server
            global_server = get_metrics_server()
            assert global_server is server

        finally:
            stop_metrics_server()
            time.sleep(0.5)

    def test_stop_global_server(self):
        """Test stopping global metrics server."""
        try:
            server = start_metrics_server(port=9099)
            time.sleep(0.5)
            assert server.is_running()

            stop_metrics_server()
            time.sleep(0.5)

            assert get_metrics_server() is None

        finally:
            # Cleanup in case test fails
            stop_metrics_server()

    def test_start_global_server_twice(self):
        """Test that starting global server twice returns same instance."""
        try:
            server1 = start_metrics_server(port=9100)
            time.sleep(0.5)

            server2 = start_metrics_server(port=9100)

            # Should be same instance
            assert server1 is server2

        finally:
            stop_metrics_server()


class TestMetricsServerPortConflict:
    """Test handling of port conflicts."""

    def test_port_already_in_use(self):
        """Test graceful handling when port is already in use."""
        # Start first server
        server1 = MetricsServer(port=9101)
        server1.start()
        time.sleep(0.5)

        try:
            # Try to start second server on same port
            server2 = MetricsServer(port=9101)

            with pytest.raises(OSError):
                server2.start()

        finally:
            server1.stop()
