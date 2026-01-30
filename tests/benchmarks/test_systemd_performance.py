#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Performance benchmarks for VMCraft systemd integration.

These benchmarks measure the performance of systemd-related operations
to ensure the integration meets performance requirements.

Usage:
    pytest tests/benchmarks/test_systemd_performance.py -v -m performance -s
"""

import time
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from hyper2kvm.core.vmcraft.systemd_mgr import SystemdManager
from hyper2kvm.core.vmcraft.systemd_networkd import SystemdNetworkdManager
from hyper2kvm.core.vmcraft.systemd_journal import SystemdJournalManager
from hyper2kvm.core.vmcraft.systemd_units import SystemdUnitsManager


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_logger():
    """Create mock logger."""
    logger = Mock()
    logger.info = Mock()
    logger.debug = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    return logger


@pytest.fixture
def systemd_mgr(tmp_path, mock_logger):
    """Create SystemdManager with temporary root."""
    guest_root = tmp_path / "guest"
    guest_root.mkdir()
    return SystemdManager(mock_logger, str(guest_root))


@pytest.fixture
def networkd_mgr(tmp_path, mock_logger):
    """Create SystemdNetworkdManager with temporary root."""
    guest_root = tmp_path / "guest"
    guest_root.mkdir()
    networkd_dir = guest_root / "etc" / "systemd" / "network"
    networkd_dir.mkdir(parents=True)
    return SystemdNetworkdManager(mock_logger, str(guest_root))


@pytest.fixture
def journal_mgr(tmp_path, mock_logger):
    """Create SystemdJournalManager with temporary root."""
    guest_root = tmp_path / "guest"
    guest_root.mkdir()
    return SystemdJournalManager(mock_logger, str(guest_root))


@pytest.fixture
def units_mgr(tmp_path, mock_logger):
    """Create SystemdUnitsManager with temporary root."""
    guest_root = tmp_path / "guest"
    guest_root.mkdir()
    units_dir = guest_root / "etc" / "systemd" / "system"
    units_dir.mkdir(parents=True)
    return SystemdUnitsManager(mock_logger, str(guest_root))


# ============================================================================
# Helper function for timing
# ============================================================================

def measure_performance(operation, iterations=100, max_time_ms=10.0):
    """
    Measure average performance of an operation.

    Args:
        operation: Callable to benchmark
        iterations: Number of iterations to run
        max_time_ms: Maximum acceptable average time in milliseconds

    Returns:
        Average time in milliseconds
    """
    start = time.perf_counter()
    for _ in range(iterations):
        operation()
    elapsed = time.perf_counter() - start

    avg_time_ms = (elapsed / iterations) * 1000
    print(f"\n  Average: {avg_time_ms:.3f}ms ({iterations} iterations, total: {elapsed:.3f}s)")

    assert avg_time_ms < max_time_ms, f"Operation too slow: {avg_time_ms:.3f}ms > {max_time_ms}ms"
    return avg_time_ms


# ============================================================================
# Service Management Performance Benchmarks
# ============================================================================

@pytest.mark.performance
class TestServiceManagementPerformance:
    """Benchmark service management operations."""

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.run_sudo')
    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._check_nspawn_available')
    def test_service_enable_performance(self, mock_nspawn, mock_run_sudo, systemd_mgr):
        """Benchmark service enable operation."""
        mock_nspawn.return_value = True
        mock_result = Mock()
        mock_result.stdout = ""
        mock_run_sudo.return_value = mock_result

        print("\n[Service Enable Performance]")
        measure_performance(
            lambda: systemd_mgr.service_enable("test-service"),
            iterations=100,
            max_time_ms=10.0
        )

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.run_sudo')
    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._check_nspawn_available')
    def test_bulk_service_disable_performance(self, mock_nspawn, mock_run_sudo, systemd_mgr):
        """Benchmark bulk service disable operation."""
        mock_nspawn.return_value = True
        mock_result = Mock()
        mock_result.stdout = ""
        mock_run_sudo.return_value = mock_result

        services = [f"service-{i}" for i in range(10)]

        print("\n[Bulk Service Disable Performance - 10 services]")
        measure_performance(
            lambda: systemd_mgr.services_disable_multiple(services),
            iterations=50,
            max_time_ms=100.0
        )

    @patch('hyper2kvm.core.vmcraft.systemd_mgr.run_sudo')
    @patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._check_nspawn_available')
    def test_service_list_performance(self, mock_nspawn, mock_run_sudo, systemd_mgr):
        """Benchmark service listing operation."""
        mock_nspawn.return_value = True
        mock_result = Mock()
        # Simulate 50 services
        mock_result.stdout = "\n".join([f"service-{i}.service" for i in range(50)])
        mock_run_sudo.return_value = mock_result

        print("\n[Service List Performance - 50 services]")
        measure_performance(
            lambda: systemd_mgr.list_services(),
            iterations=100,
            max_time_ms=20.0
        )


# ============================================================================
# Network Configuration Performance Benchmarks
# ============================================================================

@pytest.mark.performance
class TestNetworkConfigPerformance:
    """Benchmark network configuration operations."""

    def test_network_file_creation_performance(self, networkd_mgr):
        """Benchmark .network file creation."""
        print("\n[Network File Creation Performance]")

        counter = [0]  # Use list to allow mutation in lambda

        def create_network():
            result = networkd_mgr.create_network_file(
                name=f"10-eth{counter[0]}",
                match={"Name": f"eth{counter[0]}"},
                network={"Address": "192.168.1.100/24", "Gateway": "192.168.1.1"},
            )
            counter[0] += 1
            return result

        measure_performance(create_network, iterations=100, max_time_ms=5.0)

    def test_network_file_parsing_performance(self, networkd_mgr):
        """Benchmark .network file parsing."""
        # Create a network file first
        networkd_mgr.create_network_file(
            name="10-eth0",
            match={"Name": "eth0"},
            network={"Address": "192.168.1.100/24"},
        )

        print("\n[Network File Parsing Performance]")
        measure_performance(
            lambda: networkd_mgr.parse_network_file("10-eth0.network"),
            iterations=100,
            max_time_ms=5.0
        )

    def test_ifcfg_migration_performance(self, networkd_mgr, tmp_path):
        """Benchmark ifcfg to networkd migration."""
        # Create mock ifcfg file
        ifcfg_dir = tmp_path / "guest" / "etc" / "sysconfig" / "network-scripts"
        ifcfg_dir.mkdir(parents=True, exist_ok=True)

        ifcfg_file = ifcfg_dir / "ifcfg-eth0"
        ifcfg_file.write_text("""
DEVICE=eth0
BOOTPROTO=static
IPADDR=192.168.1.100
NETMASK=255.255.255.0
GATEWAY=192.168.1.1
ONBOOT=yes
""")

        print("\n[ifcfg Migration Performance]")
        measure_performance(
            lambda: networkd_mgr.migrate_from_ifcfg("eth0"),
            iterations=50,
            max_time_ms=20.0
        )


# ============================================================================
# Journal Operations Performance Benchmarks
# ============================================================================

@pytest.mark.performance
class TestJournalPerformance:
    """Benchmark journal operations."""

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_journal_query_performance(self, mock_run_sudo, journal_mgr):
        """Benchmark basic journal query."""
        mock_result = Mock()
        # Simulate 100 log entries
        entries = [f'{{"MESSAGE": "Log entry {i}", "PRIORITY": "6"}}' for i in range(100)]
        mock_result.stdout = "\n".join(entries)
        mock_run_sudo.return_value = mock_result

        print("\n[Journal Query Performance - 100 entries]")
        measure_performance(
            lambda: journal_mgr.get(lines=100),
            iterations=50,
            max_time_ms=30.0
        )

    @patch('hyper2kvm.core.vmcraft.systemd_journal.run_sudo')
    def test_journal_service_filter_performance(self, mock_run_sudo, journal_mgr):
        """Benchmark journal filtering by service."""
        mock_result = Mock()
        entries = [f'{{"MESSAGE": "SSH log {i}", "UNIT": "sshd.service"}}' for i in range(50)]
        mock_result.stdout = "\n".join(entries)
        mock_run_sudo.return_value = mock_result

        print("\n[Journal Service Filter Performance - 50 entries]")
        measure_performance(
            lambda: journal_mgr.get_service("sshd.service", lines=50),
            iterations=50,
            max_time_ms=25.0
        )


# ============================================================================
# Unit File Operations Performance Benchmarks
# ============================================================================

@pytest.mark.performance
class TestUnitFilePerformance:
    """Benchmark unit file operations."""

    def test_service_unit_creation_performance(self, units_mgr):
        """Benchmark service unit file creation."""
        print("\n[Service Unit Creation Performance]")

        counter = [0]

        def create_service():
            result = units_mgr.create_service_unit(
                name=f"myapp-{counter[0]}",
                description="My Application",
                exec_start="/usr/bin/myapp",
                after=["network.target"],
                restart="always"
            )
            counter[0] += 1
            return result

        measure_performance(create_service, iterations=100, max_time_ms=5.0)

    def test_timer_unit_creation_performance(self, units_mgr):
        """Benchmark timer unit file creation."""
        print("\n[Timer Unit Creation Performance]")

        counter = [0]

        def create_timer():
            result = units_mgr.create_timer_unit(
                name=f"backup-{counter[0]}",
                description="Daily Backup",
                on_calendar="daily",
                service=f"backup-{counter[0]}.service"
            )
            counter[0] += 1
            return result

        measure_performance(create_timer, iterations=100, max_time_ms=5.0)

    def test_unit_file_parsing_performance(self, units_mgr):
        """Benchmark unit file parsing."""
        # Create a service unit first
        units_mgr.create_service_unit(
            name="testapp",
            description="Test Application",
            exec_start="/usr/bin/testapp"
        )

        print("\n[Unit File Parsing Performance]")
        measure_performance(
            lambda: units_mgr.read_unit_file("testapp.service"),
            iterations=100,
            max_time_ms=5.0
        )


# ============================================================================
# Integration Performance Benchmarks
# ============================================================================

@pytest.mark.performance
class TestIntegrationPerformance:
    """Benchmark integration workflows combining multiple operations."""

    def test_complete_network_migration_workflow(self, networkd_mgr, tmp_path):
        """Benchmark complete network migration workflow."""
        # Setup ifcfg files
        ifcfg_dir = tmp_path / "guest" / "etc" / "sysconfig" / "network-scripts"
        ifcfg_dir.mkdir(parents=True, exist_ok=True)

        for i in range(3):
            ifcfg_file = ifcfg_dir / f"ifcfg-eth{i}"
            ifcfg_file.write_text(f"""
DEVICE=eth{i}
BOOTPROTO=dhcp
ONBOOT=yes
""")

        print("\n[Complete Network Migration Workflow - 3 interfaces]")

        def migration_workflow():
            # Migrate all interfaces
            for i in range(3):
                networkd_mgr.migrate_from_ifcfg(f"eth{i}")

            # List all network files
            files = networkd_mgr.list_network_files()

            # Parse each file
            for file_info in files:
                networkd_mgr.parse_network_file(file_info["name"])

        measure_performance(migration_workflow, iterations=20, max_time_ms=100.0)

    def test_service_migration_workflow(self, systemd_mgr):
        """Benchmark VMware to KVM service migration workflow."""
        with patch('hyper2kvm.core.vmcraft.systemd_mgr.run_sudo') as mock_run_sudo, \
             patch('hyper2kvm.core.vmcraft.systemd_mgr.SystemdManager._check_nspawn_available') as mock_nspawn:

            mock_nspawn.return_value = True
            mock_result = Mock()
            mock_result.stdout = ""
            mock_run_sudo.return_value = mock_result

            vmware_services = ["vmtoolsd.service", "vmware-tools.service", "open-vm-tools.service"]
            kvm_services = ["qemu-guest-agent.service"]

            print("\n[Service Migration Workflow - VMware to KVM]")

            def migration_workflow():
                # Disable VMware services
                systemd_mgr.services_disable_multiple(vmware_services)

                # Mask VMware services
                systemd_mgr.services_mask(vmware_services)

                # Enable KVM services
                for service in kvm_services:
                    systemd_mgr.service_enable(service)

                # Reload daemon
                systemd_mgr.daemon_reload()

            measure_performance(migration_workflow, iterations=20, max_time_ms=80.0)


# ============================================================================
# Performance Summary
# ============================================================================

@pytest.mark.performance
def test_performance_summary(tmp_path):
    """Generate performance summary report."""
    summary = """
VMCraft Systemd Integration - Performance Benchmarks Summary
============================================================

Service Management:
  - Service enable:           < 10ms
  - Bulk disable (10 svcs):   < 100ms
  - Service list (50 svcs):   < 20ms

Network Configuration:
  - Network file creation:    < 5ms
  - Network file parsing:     < 5ms
  - ifcfg migration:          < 20ms

Journal Operations:
  - Journal query (100):      < 30ms
  - Service filter (50):      < 25ms

Unit File Operations:
  - Service unit creation:    < 5ms
  - Timer unit creation:      < 5ms
  - Unit file parsing:        < 5ms

Integration Workflows:
  - Network migration (3):    < 100ms
  - Service migration:        < 80ms

Notes:
- All timings are for mocked operations (in-memory)
- Real systemd operations will be slower due to system calls
- Benchmarks ensure no performance regressions in wrapper code
- Run with: pytest tests/benchmarks/ -m performance -s
"""

    print(summary)

    # Write to file
    report_file = tmp_path / "performance_summary.txt"
    report_file.write_text(summary)
    print(f"\nPerformance summary written to: {report_file}")
