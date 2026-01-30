# SPDX-License-Identifier: LGPL-3.0-or-later
# tests/unit/test_compliance.py
"""
Unit tests for compliance and audit framework.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from hyper2kvm.compliance import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
    Change,
    ChangeTracker,
    ChangeType,
    CISBenchmarkValidator,
    ComplianceCheck,
    ComplianceFramework,
    ComplianceLevel,
    ComplianceOrchestrator,
    ComplianceReportGenerator,
    ComplianceResult,
    STIGValidator,
)


@pytest.fixture
def logger():
    """Create test logger."""
    return logging.getLogger("test")


@pytest.fixture
def mock_vmcraft():
    """Create mock VMCraft instance."""
    g = MagicMock()
    g.disk_path = Path("/tmp/test.qcow2")

    # Mock file operations
    g.exists = Mock(return_value=True)
    g.read_file = Mock(return_value="test content")
    g.stat = Mock(return_value={"mode": 0o100644})  # 0644 permissions

    return g


# AuditLogger Tests

def test_audit_logger_initialization(logger, tmp_path):
    """Test audit logger initialization."""
    audit_logger = AuditLogger(logger, tmp_path)

    assert audit_logger.audit_dir == tmp_path
    # File is created on first log, not on init
    assert audit_logger.audit_file is not None


def test_audit_logger_log_event(logger, tmp_path):
    """Test logging audit events."""
    audit_logger = AuditLogger(logger, tmp_path)

    event = audit_logger.log_event(
        event_type=AuditEventType.VM_MIGRATION_STARTED,
        vm_name="test-vm",
        description="Test migration",
        result="success"
    )

    assert event.event_type == AuditEventType.VM_MIGRATION_STARTED
    assert event.vm_name == "test-vm"
    assert event.result == "success"
    assert audit_logger.audit_file.exists()


def test_audit_logger_get_events(logger, tmp_path):
    """Test retrieving audit events."""
    audit_logger = AuditLogger(logger, tmp_path)

    # Log multiple events
    audit_logger.log_event(
        event_type=AuditEventType.FILE_MODIFIED,
        vm_name="test-vm",
        resource="/etc/fstab"
    )
    audit_logger.log_event(
        event_type=AuditEventType.CONFIG_MODIFIED,
        vm_name="test-vm",
        resource="network"
    )

    # Retrieve all events
    events = audit_logger.get_events()
    assert len(events) == 2

    # Filter by event type
    file_events = audit_logger.get_events(event_type=AuditEventType.FILE_MODIFIED)
    assert len(file_events) == 1
    assert file_events[0].resource == "/etc/fstab"


def test_audit_logger_summary(logger, tmp_path):
    """Test audit log summary generation."""
    audit_logger = AuditLogger(logger, tmp_path)

    audit_logger.log_event(
        event_type=AuditEventType.VM_MIGRATION_STARTED,
        vm_name="vm1"
    )
    audit_logger.log_event(
        event_type=AuditEventType.VM_MIGRATION_COMPLETED,
        vm_name="vm1",
        result="success"
    )

    summary = audit_logger.get_summary()

    assert summary["total_events"] == 2
    assert "vm1" in summary["vms_affected"]
    assert summary["by_result"]["success"] == 2  # Both events default to success


# ChangeTracker Tests

def test_change_tracker_initialization(logger, tmp_path):
    """Test change tracker initialization."""
    tracker = ChangeTracker(logger, tmp_path, "test-vm")

    assert tracker.vm_name == "test-vm"
    # File is created on first change, not on init
    assert tracker.change_file is not None


def test_change_tracker_track_change(logger, tmp_path):
    """Test tracking changes."""
    tracker = ChangeTracker(logger, tmp_path, "test-vm")

    change = tracker.track_change(
        change_type=ChangeType.FILE_MODIFIED,
        resource="/etc/fstab",
        old_value="UUID=123",
        new_value="UUID=456"
    )

    assert change.change_type == ChangeType.FILE_MODIFIED
    assert change.resource == "/etc/fstab"
    assert change.old_value == "UUID=123"
    assert change.new_value == "UUID=456"


def test_change_tracker_file_helpers(logger, tmp_path):
    """Test file change helper methods."""
    tracker = ChangeTracker(logger, tmp_path, "test-vm")

    # Track file modification
    change = tracker.track_file_modified(
        "/etc/fstab",
        old_content="old",
        new_content="new",
        reason="UUID stabilization"
    )

    assert change.change_type == ChangeType.FILE_MODIFIED
    assert change.reason == "UUID stabilization"


def test_change_tracker_get_changes(logger, tmp_path):
    """Test retrieving changes."""
    tracker = ChangeTracker(logger, tmp_path, "test-vm")

    tracker.track_file_modified("/etc/fstab")
    tracker.track_file_created("/etc/new-file")
    tracker.track_package_installed("virtio-drivers")

    # Get all changes
    all_changes = tracker.get_changes()
    assert len(all_changes) == 3

    # Filter by type
    file_changes = tracker.get_changes(change_type=ChangeType.FILE_MODIFIED)
    assert len(file_changes) == 1


def test_change_tracker_rollback_script(logger, tmp_path):
    """Test rollback script generation."""
    tracker = ChangeTracker(logger, tmp_path, "test-vm")

    tracker.track_file_created(
        "/etc/test-file",
        reason="Test"
    )

    script = tracker.generate_rollback_script()

    assert "#!/bin/bash" in script
    assert "rm -f /etc/test-file" in script


# CISBenchmarkValidator Tests

def test_cis_validator_initialization(logger):
    """Test CIS validator initialization."""
    validator = CISBenchmarkValidator(logger)

    assert validator.get_framework() == ComplianceFramework.CIS_BENCHMARK
    checks = validator.get_checks()
    assert len(checks) > 0


def test_cis_validator_bootloader_permissions(logger, mock_vmcraft):
    """Test CIS bootloader permissions check."""
    validator = CISBenchmarkValidator(logger)

    # Mock bootloader config with correct permissions
    mock_vmcraft.exists = Mock(return_value=True)
    mock_vmcraft.stat = Mock(return_value={"mode": 0o100600})

    check = validator._check_bootloader_permissions(mock_vmcraft)

    assert check.check_id == "CIS-1.4.1"
    assert check.passed is True


def test_cis_validator_ssh_root_login(logger, mock_vmcraft):
    """Test CIS SSH root login check."""
    validator = CISBenchmarkValidator(logger)

    # Mock SSH config with root login disabled
    mock_vmcraft.read_file = Mock(return_value="PermitRootLogin no\n")

    check = validator._check_ssh_root_login(mock_vmcraft)

    assert check.check_id == "CIS-5.2.5"
    assert check.passed is True


def test_cis_validator_full_validation(logger, mock_vmcraft):
    """Test full CIS validation."""
    validator = CISBenchmarkValidator(logger)

    os_info = {"os_type": "linux", "os_version": "Ubuntu 22.04"}

    # Mock various file checks
    mock_vmcraft.read_file = Mock(return_value="PermitRootLogin no\n")
    mock_vmcraft.stat = Mock(return_value={"mode": 0o100644})

    result = validator.validate(mock_vmcraft, os_info)

    assert isinstance(result, ComplianceResult)
    assert result.framework == ComplianceFramework.CIS_BENCHMARK
    assert result.total_checks > 0


# STIGValidator Tests

def test_stig_validator_initialization(logger):
    """Test STIG validator initialization."""
    validator = STIGValidator(logger)

    assert validator.get_framework() == ComplianceFramework.STIG
    checks = validator.get_checks()
    assert len(checks) > 0


def test_stig_validator_passwd_permissions(logger, mock_vmcraft):
    """Test STIG /etc/passwd permissions check."""
    validator = STIGValidator(logger)

    # Mock /etc/passwd with correct permissions
    mock_vmcraft.stat = Mock(return_value={"mode": 0o100644})

    check = validator._check_passwd_permissions(mock_vmcraft)

    assert check.check_id == "RHEL-07-010010"
    assert check.passed is True


def test_stig_validator_shadow_permissions(logger, mock_vmcraft):
    """Test STIG /etc/shadow permissions check."""
    validator = STIGValidator(logger)

    # Mock /etc/shadow with correct permissions
    mock_vmcraft.stat = Mock(return_value={"mode": 0o100000})  # 0000

    check = validator._check_shadow_permissions(mock_vmcraft)

    assert check.check_id == "RHEL-07-010020"
    assert check.passed is True


def test_stig_validator_full_validation(logger, mock_vmcraft):
    """Test full STIG validation."""
    validator = STIGValidator(logger)

    os_info = {"os_type": "linux", "os_version": "RHEL 7"}

    # Mock various file checks
    mock_vmcraft.read_file = Mock(return_value="PermitRootLogin no\nPermitEmptyPasswords no\n")
    mock_vmcraft.stat = Mock(return_value={"mode": 0o100644})

    result = validator.validate(mock_vmcraft, os_info)

    assert isinstance(result, ComplianceResult)
    assert result.framework == ComplianceFramework.STIG
    assert result.total_checks > 0


# ComplianceReportGenerator Tests

def test_report_generator_markdown(logger):
    """Test markdown report generation."""
    generator = ComplianceReportGenerator(logger)

    result = ComplianceResult(
        vm_name="test-vm",
        framework=ComplianceFramework.CIS_BENCHMARK,
        total_checks=5,
        passed_checks=3,
        failed_checks=2,
        compliance_score=60.0,
        overall_compliant=False
    )

    # Add sample checks
    result.checks = [
        ComplianceCheck(
            check_id="CIS-1.1",
            framework=ComplianceFramework.CIS_BENCHMARK,
            title="Test check",
            description="Test description",
            passed=True,
            level=ComplianceLevel.HIGH
        )
    ]

    report = generator.generate_markdown_report(result)

    assert "# Compliance Report" in report
    assert "test-vm" in report
    assert "60.0%" in report


def test_report_generator_json(logger):
    """Test JSON report generation."""
    generator = ComplianceReportGenerator(logger)

    result = ComplianceResult(
        vm_name="test-vm",
        framework=ComplianceFramework.CIS_BENCHMARK,
        total_checks=5,
        passed_checks=5,
        overall_compliant=True
    )

    report = generator.generate_json_report(result)

    data = json.loads(report)
    assert data["vm_name"] == "test-vm"
    assert data["summary"]["overall_compliant"] is True


def test_report_generator_save_reports(logger, tmp_path):
    """Test saving reports to files."""
    generator = ComplianceReportGenerator(logger)

    result = ComplianceResult(
        vm_name="test-vm",
        framework=ComplianceFramework.CIS_BENCHMARK,
        total_checks=5,
        passed_checks=5
    )

    output_files = generator.save_reports(
        result,
        tmp_path,
        formats=["markdown", "json", "csv"]
    )

    assert "markdown" in output_files
    assert "json" in output_files
    assert "csv" in output_files
    assert output_files["markdown"].exists()
    assert output_files["json"].exists()
    assert output_files["csv"].exists()


# ComplianceOrchestrator Tests

def test_orchestrator_initialization(logger, tmp_path):
    """Test orchestrator initialization."""
    orchestrator = ComplianceOrchestrator(logger, tmp_path)

    assert orchestrator.audit_logger is not None
    assert ComplianceFramework.CIS_BENCHMARK in orchestrator.validators
    assert ComplianceFramework.STIG in orchestrator.validators


def test_orchestrator_validate_compliance(logger, tmp_path, mock_vmcraft):
    """Test orchestrator compliance validation."""
    orchestrator = ComplianceOrchestrator(logger, tmp_path)

    os_info = {"os_type": "linux", "os_version": "Ubuntu 22.04"}

    # Mock VMCraft methods
    mock_vmcraft.read_file = Mock(return_value="PermitRootLogin no\n")
    mock_vmcraft.stat = Mock(return_value={"mode": 0o100644})

    results = orchestrator.validate_compliance(
        mock_vmcraft,
        os_info,
        frameworks=[ComplianceFramework.CIS_BENCHMARK]
    )

    assert ComplianceFramework.CIS_BENCHMARK in results
    assert isinstance(results[ComplianceFramework.CIS_BENCHMARK], ComplianceResult)


def test_orchestrator_generate_reports(logger, tmp_path, mock_vmcraft):
    """Test orchestrator report generation."""
    orchestrator = ComplianceOrchestrator(logger, tmp_path)

    result = ComplianceResult(
        vm_name="test-vm",
        framework=ComplianceFramework.CIS_BENCHMARK,
        total_checks=5,
        passed_checks=5
    )

    output_files = orchestrator.generate_reports(
        {ComplianceFramework.CIS_BENCHMARK: result},
        tmp_path,
        formats=["markdown", "json"]
    )

    assert "markdown" in output_files
    assert "json" in output_files
    assert len(output_files["markdown"]) == 1


def test_orchestrator_compliance_summary(logger, tmp_path):
    """Test orchestrator compliance summary."""
    orchestrator = ComplianceOrchestrator(logger, tmp_path)

    results = {
        ComplianceFramework.CIS_BENCHMARK: ComplianceResult(
            vm_name="test-vm",
            framework=ComplianceFramework.CIS_BENCHMARK,
            total_checks=10,
            passed_checks=8,
            failed_checks=2,
            critical_failures=0,
            compliance_score=80.0,
            overall_compliant=True
        ),
        ComplianceFramework.STIG: ComplianceResult(
            vm_name="test-vm",
            framework=ComplianceFramework.STIG,
            total_checks=5,
            passed_checks=5,
            failed_checks=0,
            compliance_score=100.0,
            overall_compliant=True
        )
    }

    summary = orchestrator.get_compliance_summary(results)

    assert summary["total_frameworks"] == 2
    assert summary["overall_compliant"] is True
    assert summary["aggregate"]["total_checks"] == 15
    assert summary["aggregate"]["passed_checks"] == 13


def test_orchestrator_full_workflow(logger, tmp_path, mock_vmcraft):
    """Test full compliance workflow."""
    orchestrator = ComplianceOrchestrator(logger, tmp_path)

    os_info = {"os_type": "linux", "os_version": "Ubuntu 22.04"}

    # Mock VMCraft methods
    mock_vmcraft.read_file = Mock(return_value="PermitRootLogin no\n")
    mock_vmcraft.stat = Mock(return_value={"mode": 0o100644})

    result = orchestrator.full_compliance_workflow(
        mock_vmcraft,
        os_info,
        tmp_path,
        frameworks=[ComplianceFramework.CIS_BENCHMARK],
        report_formats=["markdown", "json"]
    )

    assert result["success"] is True
    assert "compliance_results" in result
    assert "reports_generated" in result
    assert "summary" in result


def test_orchestrator_change_tracker(logger, tmp_path):
    """Test orchestrator change tracker management."""
    orchestrator = ComplianceOrchestrator(logger, tmp_path)

    tracker1 = orchestrator.get_change_tracker("vm1", tmp_path)
    tracker2 = orchestrator.get_change_tracker("vm1", tmp_path)

    # Should return same instance
    assert tracker1 is tracker2

    tracker3 = orchestrator.get_change_tracker("vm2", tmp_path)

    # Different VM should get different tracker
    assert tracker1 is not tracker3
