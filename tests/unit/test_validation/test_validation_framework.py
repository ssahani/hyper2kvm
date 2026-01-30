# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for validation framework."""

import tempfile
from pathlib import Path

import pytest

from hyper2kvm.validation import (
    BaseValidator,
    DiskValidator,
    ValidationReport,
    ValidationResult,
    ValidationRunner,
    ValidationSeverity,
    XMLValidator,
)


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_result_creation(self):
        """Test creating a validation result."""
        result = ValidationResult(
            check_name="test_check",
            severity=ValidationSeverity.ERROR,
            passed=False,
            message="Test failed",
        )

        assert result.check_name == "test_check"
        assert result.severity == ValidationSeverity.ERROR
        assert result.passed is False
        assert result.message == "Test failed"
        assert result.details == {}
        assert result.suggestions == []

    def test_result_with_details(self):
        """Test result with details and suggestions."""
        result = ValidationResult(
            check_name="size_check",
            severity=ValidationSeverity.WARNING,
            passed=False,
            message="Disk too small",
            details={"actual": 100, "expected": 200},
            suggestions=["Increase disk size", "Check source VM"],
        )

        assert result.details == {"actual": 100, "expected": 200}
        assert len(result.suggestions) == 2

    def test_result_repr(self):
        """Test result string representation."""
        result = ValidationResult(
            check_name="test",
            severity=ValidationSeverity.INFO,
            passed=True,
            message="OK",
        )

        repr_str = repr(result)
        assert "ValidationResult" in repr_str
        assert "test" in repr_str


class TestValidationReport:
    """Test ValidationReport functionality."""

    def test_report_creation(self):
        """Test creating a validation report."""
        report = ValidationReport(validator_name="TestValidator")

        assert report.validator_name == "TestValidator"
        assert report.total_checks == 0
        assert report.passed_checks == 0
        assert report.failed_checks == 0
        assert len(report.results) == 0

    def test_add_result_passed(self):
        """Test adding passed result."""
        report = ValidationReport(validator_name="Test")

        result = ValidationResult(
            check_name="test",
            severity=ValidationSeverity.INFO,
            passed=True,
            message="OK",
        )

        report.add_result(result)

        assert report.total_checks == 1
        assert report.passed_checks == 1
        assert report.failed_checks == 0

    def test_add_result_failed(self):
        """Test adding failed result."""
        report = ValidationReport(validator_name="Test")

        result = ValidationResult(
            check_name="test",
            severity=ValidationSeverity.ERROR,
            passed=False,
            message="Failed",
        )

        report.add_result(result)

        assert report.total_checks == 1
        assert report.passed_checks == 0
        assert report.failed_checks == 1

    def test_has_errors(self):
        """Test has_errors detection."""
        report = ValidationReport(validator_name="Test")

        # No errors initially
        assert not report.has_errors()

        # Add warning (not an error)
        report.add_result(
            ValidationResult(
                "warn", ValidationSeverity.WARNING, False, "Warning"
            )
        )
        assert not report.has_errors()

        # Add error
        report.add_result(
            ValidationResult(
                "error", ValidationSeverity.ERROR, False, "Error"
            )
        )
        assert report.has_errors()

    def test_has_warnings(self):
        """Test has_warnings detection."""
        report = ValidationReport(validator_name="Test")

        assert not report.has_warnings()

        report.add_result(
            ValidationResult(
                "warn", ValidationSeverity.WARNING, False, "Warning"
            )
        )

        assert report.has_warnings()

    def test_get_issues_by_severity(self):
        """Test filtering issues by severity."""
        report = ValidationReport(validator_name="Test")

        report.add_result(
            ValidationResult("e1", ValidationSeverity.ERROR, False, "Error 1")
        )
        report.add_result(
            ValidationResult("w1", ValidationSeverity.WARNING, False, "Warn 1")
        )
        report.add_result(
            ValidationResult("e2", ValidationSeverity.ERROR, False, "Error 2")
        )
        report.add_result(
            ValidationResult("c1", ValidationSeverity.CRITICAL, False, "Critical")
        )

        errors = report.get_issues_by_severity(ValidationSeverity.ERROR)
        assert len(errors) == 2

        warnings = report.get_issues_by_severity(ValidationSeverity.WARNING)
        assert len(warnings) == 1

        critical = report.get_issues_by_severity(ValidationSeverity.CRITICAL)
        assert len(critical) == 1

    def test_get_summary(self):
        """Test getting report summary."""
        report = ValidationReport(validator_name="TestValidator")
        report.duration = 1.5

        report.add_result(
            ValidationResult("pass", ValidationSeverity.INFO, True, "OK")
        )
        report.add_result(
            ValidationResult("fail", ValidationSeverity.ERROR, False, "Error")
        )

        summary = report.get_summary()

        assert summary["validator"] == "TestValidator"
        assert summary["total_checks"] == 2
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert summary["has_errors"] is True
        assert summary["duration"] == 1.5


class TestDiskValidator:
    """Test DiskValidator."""

    def test_validate_disk_exists(self, tmp_path):
        """Test validating disk that exists."""
        disk_path = tmp_path / "disk.qcow2"
        disk_path.write_bytes(b"x" * 1024 * 1024)  # 1MB disk

        validator = DiskValidator()
        context = {"output_path": str(disk_path), "format": "qcow2"}

        report = validator.validate(context)

        assert report.total_checks > 0
        assert report.passed_checks > 0
        assert not report.has_errors()

    def test_validate_disk_missing(self, tmp_path):
        """Test validating disk that doesn't exist."""
        disk_path = tmp_path / "nonexistent.qcow2"

        validator = DiskValidator()
        context = {"output_path": str(disk_path), "format": "qcow2"}

        report = validator.validate(context)

        assert report.has_errors()
        critical_issues = report.get_issues_by_severity(ValidationSeverity.CRITICAL)
        assert len(critical_issues) > 0
        assert "not found" in critical_issues[0].message.lower()

    def test_validate_disk_empty(self, tmp_path):
        """Test validating empty disk file."""
        disk_path = tmp_path / "empty.qcow2"
        disk_path.write_bytes(b"")  # Empty file

        validator = DiskValidator()
        context = {"output_path": str(disk_path), "format": "qcow2"}

        report = validator.validate(context)

        assert report.has_errors()
        # Should have critical error about empty disk
        critical_issues = report.get_issues_by_severity(ValidationSeverity.CRITICAL)
        assert len(critical_issues) > 0

    def test_validate_disk_minimum_size(self, tmp_path):
        """Test validating disk minimum size."""
        disk_path = tmp_path / "small.qcow2"
        disk_path.write_bytes(b"x" * 100)  # 100 bytes

        validator = DiskValidator()
        context = {
            "output_path": str(disk_path),
            "format": "qcow2",
            "minimum_size": 1024 * 1024,  # Require 1MB
        }

        report = validator.validate(context)

        # Should have error about disk being too small
        errors = report.get_issues_by_severity(ValidationSeverity.ERROR)
        assert len(errors) > 0
        assert any("too small" in e.message.lower() for e in errors)


class TestXMLValidator:
    """Test XMLValidator."""

    def test_validate_valid_xml(self, tmp_path):
        """Test validating valid domain XML."""
        xml_content = """<?xml version="1.0"?>
<domain type="kvm">
  <name>test-vm</name>
  <memory>1048576</memory>
  <vcpu>2</vcpu>
  <devices>
    <disk type="file" device="disk">
      <source file="/var/lib/libvirt/images/test.qcow2"/>
      <target dev="vda" bus="virtio"/>
    </disk>
  </devices>
</domain>
"""
        xml_path = tmp_path / "domain.xml"
        xml_path.write_text(xml_content)

        validator = XMLValidator()
        context = {"xml_path": str(xml_path)}

        report = validator.validate(context)

        assert report.total_checks > 0
        assert report.passed_checks > 0
        assert not report.has_errors()

    def test_validate_xml_missing(self, tmp_path):
        """Test validating missing XML file."""
        xml_path = tmp_path / "nonexistent.xml"

        validator = XMLValidator()
        context = {"xml_path": str(xml_path)}

        report = validator.validate(context)

        assert report.has_errors()
        critical_issues = report.get_issues_by_severity(ValidationSeverity.CRITICAL)
        assert len(critical_issues) > 0

    def test_validate_xml_malformed(self, tmp_path):
        """Test validating malformed XML."""
        xml_content = "<?xml version='1.0'?><domain><unclosed>"
        xml_path = tmp_path / "bad.xml"
        xml_path.write_text(xml_content)

        validator = XMLValidator()
        context = {"xml_path": str(xml_path)}

        report = validator.validate(context)

        assert report.has_errors()

    def test_validate_xml_no_disks(self, tmp_path):
        """Test validating XML with no disks."""
        xml_content = """<?xml version="1.0"?>
<domain type="kvm">
  <name>test-vm</name>
  <memory>1048576</memory>
  <devices>
    <!-- No disks -->
  </devices>
</domain>
"""
        xml_path = tmp_path / "nodisks.xml"
        xml_path.write_text(xml_content)

        validator = XMLValidator()
        context = {"xml_path": str(xml_path)}

        report = validator.validate(context)

        # Should have error about no disks
        errors = report.get_issues_by_severity(ValidationSeverity.ERROR)
        assert len(errors) > 0
        assert any("no disks" in e.message.lower() for e in errors)


class TestValidationRunner:
    """Test ValidationRunner."""

    def test_runner_creation(self):
        """Test creating validation runner."""
        runner = ValidationRunner()
        assert len(runner.validators) == 0

    def test_add_validator(self):
        """Test adding validators."""
        runner = ValidationRunner()

        validator1 = DiskValidator()
        validator2 = XMLValidator()

        runner.add_validator(validator1)
        runner.add_validator(validator2)

        assert len(runner.validators) == 2

    def test_run_all_validators(self, tmp_path):
        """Test running all validators."""
        # Create test files
        disk_path = tmp_path / "disk.qcow2"
        disk_path.write_bytes(b"x" * 1024 * 1024)

        xml_content = """<?xml version="1.0"?>
<domain type="kvm">
  <name>test-vm</name>
  <devices>
    <disk type="file" device="disk">
      <source file="/disk.qcow2"/>
      <target dev="vda" bus="virtio"/>
    </disk>
  </devices>
</domain>
"""
        xml_path = tmp_path / "domain.xml"
        xml_path.write_text(xml_content)

        # Setup runner
        runner = ValidationRunner()
        runner.add_validator(DiskValidator())
        runner.add_validator(XMLValidator())

        # Run validators
        context = {
            "output_path": str(disk_path),
            "format": "qcow2",
            "xml_path": str(xml_path),
        }

        reports = runner.run_all(context)

        assert len(reports) == 2
        assert all(isinstance(r, ValidationReport) for r in reports)

    def test_aggregate_summary(self, tmp_path):
        """Test getting aggregate summary."""
        disk_path = tmp_path / "disk.qcow2"
        disk_path.write_bytes(b"x" * 1024)

        runner = ValidationRunner()
        runner.add_validator(DiskValidator())

        context = {"output_path": str(disk_path), "format": "qcow2"}
        reports = runner.run_all(context)

        summary = runner.get_aggregate_summary(reports)

        assert summary["total_validators"] == 1
        assert summary["total_checks"] > 0
        assert "passed" in summary
        assert "failed" in summary
        assert "validator_summaries" in summary


class TestCustomValidator:
    """Test creating custom validators."""

    def test_custom_validator(self):
        """Test implementing custom validator."""

        class CustomValidator(BaseValidator):
            def validate(self, context: dict):
                self._add_result(
                    check_name="custom_check",
                    passed=True,
                    severity=ValidationSeverity.INFO,
                    message="Custom check passed",
                )
                return self.report

        validator = CustomValidator()
        report = validator.validate({})

        assert report.total_checks == 1
        assert report.passed_checks == 1

    def test_custom_validator_with_context(self):
        """Test custom validator using context."""

        class ContextValidator(BaseValidator):
            def validate(self, context: dict):
                value = context.get("test_value", 0)

                if value > 100:
                    self._add_result(
                        "value_check",
                        True,
                        ValidationSeverity.INFO,
                        f"Value is acceptable: {value}",
                    )
                else:
                    self._add_result(
                        "value_check",
                        False,
                        ValidationSeverity.WARNING,
                        f"Value too low: {value}",
                        suggestions=["Increase test_value to > 100"],
                    )

                return self.report

        # Test with low value
        validator1 = ContextValidator()
        report1 = validator1.validate({"test_value": 50})
        assert report1.has_warnings()

        # Test with high value
        validator2 = ContextValidator()
        report2 = validator2.validate({"test_value": 200})
        assert not report2.has_warnings()
