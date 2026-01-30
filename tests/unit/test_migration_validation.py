# SPDX-License-Identifier: LGPL-3.0-or-later
# tests/unit/test_validation.py
"""
Unit tests for migration validation framework.
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from hyper2kvm.validation import (
    HealthChecker,
    HealthCheckStatus,
    ServiceValidator,
    NetworkValidator,
    DatabaseValidator,
    PerformanceValidator,
    ValidationOrchestrator,
)


@pytest.fixture
def logger():
    """Create test logger."""
    return logging.getLogger("test")


@pytest.fixture
def mock_vmcraft():
    """Create mock VMCraft instance."""
    vmcraft = MagicMock()

    # Mock file existence
    def exists_side_effect(path):
        existing_files = [
            "/",
            "/boot/grub/grub.cfg",
            "/etc/fstab",
            "/lib/modules",
            "/etc/systemd/system/sshd.service",
            "/etc/systemd/system/multi-user.target.wants/sshd.service",
            "/etc/network/interfaces",
            "/etc/resolv.conf",
            "/var/lib/postgresql/data",
            "/var/lib/postgresql/data/postgresql.conf",
            "/proc/cpuinfo",
            "/proc/meminfo",
        ]
        return path in existing_files

    vmcraft.exists = Mock(side_effect=exists_side_effect)

    # Mock file reading
    def read_file_side_effect(path):
        if path == "/etc/fstab":
            return """# /etc/fstab
UUID=abc123 / ext4 defaults 0 1
UUID=def456 /boot ext4 defaults 0 2
"""
        elif path == "/etc/resolv.conf":
            return """nameserver 8.8.8.8
nameserver 8.8.4.4
"""
        return ""

    vmcraft.read_file = Mock(side_effect=read_file_side_effect)

    return vmcraft


# HealthChecker Tests

def test_health_checker_system_boot_pass(logger, mock_vmcraft):
    """Test system boot check passes when bootloader found."""
    checker = HealthChecker(logger)

    result = checker.check_system_boot(mock_vmcraft)

    assert result.status == HealthCheckStatus.PASS
    assert "bootloader" in result.message.lower()
    assert result.check_id == "system_boot"


def test_health_checker_fstab_valid(logger, mock_vmcraft):
    """Test fstab validation passes."""
    checker = HealthChecker(logger)

    result = checker.check_fstab_valid(mock_vmcraft)

    assert result.status == HealthCheckStatus.PASS
    assert result.details["entries"] == 2


def test_health_checker_kernel_modules(logger, mock_vmcraft):
    """Test kernel modules check."""
    checker = HealthChecker(logger)

    result = checker.check_kernel_modules(mock_vmcraft)

    assert result.status == HealthCheckStatus.PASS
    assert "modules" in result.message.lower()


def test_health_checker_run_all(logger, mock_vmcraft):
    """Test running all health checks."""
    checker = HealthChecker(logger)

    results = checker.run_all_checks(mock_vmcraft)

    assert len(results) == 3
    assert all(r.status in [HealthCheckStatus.PASS, HealthCheckStatus.WARN] for r in results)

    summary = checker.get_summary()
    assert summary["total"] == 3
    assert summary["pass"] >= 0


# ServiceValidator Tests

def test_service_validator_check_enabled(logger, mock_vmcraft):
    """Test service enabled check."""
    validator = ServiceValidator(logger)

    result = validator.check_service_enabled(mock_vmcraft, "sshd")

    assert result.service_name == "sshd"
    assert result.enabled is True
    assert result.status == HealthCheckStatus.PASS


def test_service_validator_check_not_found(logger, mock_vmcraft):
    """Test service not found."""
    validator = ServiceValidator(logger)

    result = validator.check_service_enabled(mock_vmcraft, "nonexistent")

    assert result.service_name == "nonexistent"
    assert result.enabled is False
    assert result.status == HealthCheckStatus.WARN


def test_service_validator_validate_critical(logger, mock_vmcraft):
    """Test critical services validation."""
    validator = ServiceValidator(logger)

    result = validator.validate_critical_services(mock_vmcraft, services=["sshd"])

    assert result.status in [HealthCheckStatus.PASS, HealthCheckStatus.WARN]
    assert result.check_id == "critical_services"
    assert "services" in result.details


# NetworkValidator Tests

def test_network_validator_check_interfaces(logger, mock_vmcraft):
    """Test network interface check."""
    validator = NetworkValidator(logger)

    result = validator.check_network_interfaces(mock_vmcraft)

    assert result.status == HealthCheckStatus.PASS
    assert result.check_id == "network_interfaces"


def test_network_validator_check_dns(logger, mock_vmcraft):
    """Test DNS configuration check."""
    validator = NetworkValidator(logger)

    result = validator.check_dns_configuration(mock_vmcraft)

    assert result.status == HealthCheckStatus.PASS
    assert "nameservers" in result.details


def test_network_validator_validate_all(logger, mock_vmcraft):
    """Test all network validation checks."""
    validator = NetworkValidator(logger)

    results = validator.validate_network(mock_vmcraft)

    assert len(results) == 2
    assert all(r.status == HealthCheckStatus.PASS for r in results)


# DatabaseValidator Tests

def test_database_validator_postgresql(logger, mock_vmcraft):
    """Test PostgreSQL configuration check."""
    validator = DatabaseValidator(logger)

    result = validator.check_postgresql_config(mock_vmcraft)

    assert result.status == HealthCheckStatus.PASS
    assert result.check_id == "postgresql_config"
    assert result.details["data_dir"] == "/var/lib/postgresql/data"


def test_database_validator_mysql_not_found(logger, mock_vmcraft):
    """Test MySQL not found."""
    validator = DatabaseValidator(logger)

    result = validator.check_mysql_config(mock_vmcraft)

    assert result.status == HealthCheckStatus.SKIP
    assert "not detected" in result.message.lower()


def test_database_validator_validate_all(logger, mock_vmcraft):
    """Test all database validation checks."""
    validator = DatabaseValidator(logger)

    results = validator.validate_databases(mock_vmcraft)

    assert len(results) == 2
    assert any(r.status == HealthCheckStatus.PASS for r in results)  # PostgreSQL passes
    assert any(r.status == HealthCheckStatus.SKIP for r in results)  # MySQL skipped


# PerformanceValidator Tests

def test_performance_validator_disk(logger, mock_vmcraft):
    """Test disk performance benchmark."""
    validator = PerformanceValidator(logger)

    result = validator.benchmark_disk_performance(mock_vmcraft)

    assert result.status == HealthCheckStatus.PASS
    assert result.check_id == "disk_performance"


def test_performance_validator_resources(logger, mock_vmcraft):
    """Test system resources check."""
    validator = PerformanceValidator(logger)

    result = validator.check_system_resources(mock_vmcraft)

    assert result.status == HealthCheckStatus.PASS
    assert result.check_id == "system_resources"
    assert "cpu_info" in result.details


def test_performance_validator_validate_all(logger, mock_vmcraft):
    """Test all performance validation checks."""
    validator = PerformanceValidator(logger)

    results = validator.validate_performance(mock_vmcraft)

    assert len(results) == 2
    assert all(r.status == HealthCheckStatus.PASS for r in results)


# ValidationOrchestrator Tests

def test_orchestrator_validate_migration(logger, mock_vmcraft):
    """Test complete migration validation."""
    orchestrator = ValidationOrchestrator(logger)

    report = orchestrator.validate_migration(mock_vmcraft)

    assert report.success is True  # All checks should pass with mock
    assert report.total_checks > 0
    assert report.passed > 0
    assert len(report.checks) == report.total_checks


def test_orchestrator_validate_selective(logger, mock_vmcraft):
    """Test selective validation (only certain check types)."""
    orchestrator = ValidationOrchestrator(logger)

    report = orchestrator.validate_migration(
        mock_vmcraft,
        check_services=True,
        check_network=False,
        check_databases=False,
        check_performance=False,
    )

    # Should have system health checks + service check
    assert report.total_checks >= 4


def test_orchestrator_markdown_report(logger, mock_vmcraft):
    """Test Markdown report generation."""
    orchestrator = ValidationOrchestrator(logger)

    report = orchestrator.validate_migration(mock_vmcraft)
    markdown = orchestrator.generate_markdown_report(report)

    assert "# Migration Validation Report" in markdown
    assert "## Summary" in markdown
    assert "## Detailed Results" in markdown


def test_orchestrator_json_report(logger, mock_vmcraft):
    """Test JSON report generation."""
    orchestrator = ValidationOrchestrator(logger)

    report = orchestrator.validate_migration(mock_vmcraft)
    json_str = report.to_json()

    assert "success" in json_str
    assert "total_checks" in json_str
    assert "checks" in json_str


def test_orchestrator_save_reports(logger, mock_vmcraft, tmp_path):
    """Test saving validation reports to files."""
    orchestrator = ValidationOrchestrator(logger)

    report = orchestrator.validate_migration(mock_vmcraft)
    saved_files = orchestrator.save_report(report, tmp_path)

    assert "json" in saved_files
    assert "markdown" in saved_files

    json_file = Path(saved_files["json"])
    md_file = Path(saved_files["markdown"])

    assert json_file.exists()
    assert md_file.exists()

    # Verify content
    json_content = json_file.read_text()
    md_content = md_file.read_text()

    assert "success" in json_content
    assert "# Migration Validation Report" in md_content


def test_orchestrator_summary_by_type(logger, mock_vmcraft):
    """Test summary by check type."""
    orchestrator = ValidationOrchestrator(logger)

    report = orchestrator.validate_migration(mock_vmcraft)

    assert "system" in report.summary_by_type
    assert report.summary_by_type["system"]["total"] > 0
