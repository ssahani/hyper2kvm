# SPDX-License-Identifier: LGPL-3.0-or-later
"""Integration tests for validation framework."""

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


class TestValidationWorkflow:
    """Integration tests for validation workflows."""

    def test_complete_validation_workflow(self, tmp_path):
        """Test complete validation workflow with multiple validators."""
        # Create test disk
        disk_path = tmp_path / "converted.qcow2"
        disk_path.write_bytes(b"QCOW" + b"\x00" * (10 * 1024 * 1024))  # 10MB

        # Create test XML
        xml_content = """<?xml version="1.0"?>
<domain type="kvm">
  <name>test-vm</name>
  <uuid>12345678-1234-1234-1234-123456789012</uuid>
  <memory unit="GiB">2</memory>
  <vcpu>2</vcpu>
  <os>
    <type arch="x86_64">hvm</type>
  </os>
  <devices>
    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2"/>
      <source file="/var/lib/libvirt/images/disk.qcow2"/>
      <target dev="vda" bus="virtio"/>
    </disk>
    <interface type="bridge">
      <source bridge="br0"/>
      <model type="virtio"/>
    </interface>
  </devices>
</domain>"""

        xml_path = tmp_path / "domain.xml"
        xml_path.write_text(xml_content)

        # Setup validation runner
        runner = ValidationRunner()
        runner.add_validator(DiskValidator())
        runner.add_validator(XMLValidator())

        # Run all validators
        context = {
            "output_path": str(disk_path),
            "format": "qcow2",
            "xml_path": str(xml_path),
        }

        reports = runner.run_all(context)

        # Verify results
        assert len(reports) == 2
        assert all(isinstance(r, ValidationReport) for r in reports)

        # Get aggregate summary
        summary = runner.get_aggregate_summary(reports)

        assert summary["total_validators"] == 2
        assert summary["total_checks"] > 0
        assert not summary["has_errors"]

    def test_validation_with_errors(self, tmp_path):
        """Test validation workflow with errors."""
        # Create empty disk (should fail)
        disk_path = tmp_path / "empty.qcow2"
        disk_path.write_bytes(b"")

        # Create invalid XML
        xml_path = tmp_path / "invalid.xml"
        xml_path.write_text("not valid xml{")

        runner = ValidationRunner()
        runner.add_validator(DiskValidator())
        runner.add_validator(XMLValidator())

        context = {
            "output_path": str(disk_path),
            "format": "qcow2",
            "xml_path": str(xml_path),
        }

        reports = runner.run_all(context)

        # Both validators should report errors
        assert len(reports) == 2
        assert all(r.has_errors() for r in reports)

        summary = runner.get_aggregate_summary(reports)
        assert summary["has_errors"] is True

    def test_validation_with_warnings(self, tmp_path):
        """Test validation with warnings but no critical errors."""
        # Create valid disk
        disk_path = tmp_path / "disk.qcow2"
        disk_path.write_bytes(b"\x00" * (1024 * 1024))

        # Create XML without name (warning)
        xml_content = """<?xml version="1.0"?>
<domain type="kvm">
  <memory>1048576</memory>
  <devices>
    <disk type="file" device="disk">
      <source file="/disk.qcow2"/>
      <target dev="vda" bus="virtio"/>
    </disk>
  </devices>
</domain>"""

        xml_path = tmp_path / "domain.xml"
        xml_path.write_text(xml_content)

        runner = ValidationRunner()
        runner.add_validator(XMLValidator())

        reports = runner.run_all({"xml_path": str(xml_path)})

        assert len(reports) == 1
        assert reports[0].has_warnings()
        assert not reports[0].has_errors()

    def test_validation_missing_files(self, tmp_path):
        """Test validation with missing files."""
        runner = ValidationRunner()
        runner.add_validator(DiskValidator())
        runner.add_validator(XMLValidator())

        context = {
            "output_path": str(tmp_path / "nonexistent.qcow2"),
            "format": "qcow2",
            "xml_path": str(tmp_path / "nonexistent.xml"),
        }

        reports = runner.run_all(context)

        # Both should have critical errors
        assert all(r.has_errors() for r in reports)

        # Check for critical severity
        for report in reports:
            critical_issues = report.get_issues_by_severity(
                ValidationSeverity.CRITICAL
            )
            assert len(critical_issues) > 0

    def test_validation_disk_size_requirements(self, tmp_path):
        """Test disk validation with minimum size requirements."""
        # Create small disk
        disk_path = tmp_path / "small.qcow2"
        disk_path.write_bytes(b"\x00" * 100)  # 100 bytes

        validator = DiskValidator()

        # Require 1MB minimum
        context = {
            "output_path": str(disk_path),
            "format": "qcow2",
            "minimum_size": 1024 * 1024,
        }

        report = validator.validate(context)

        # Should have error about disk being too small
        assert report.has_errors()
        errors = report.get_issues_by_severity(ValidationSeverity.ERROR)
        assert any("too small" in e.message.lower() for e in errors)


class TestCustomValidators:
    """Test creating and using custom validators."""

    def test_custom_validator_integration(self):
        """Test integrating custom validator into workflow."""

        class NetworkValidator(BaseValidator):
            """Custom validator for network configuration."""

            def validate(self, context):
                network_count = context.get("network_count", 0)

                if network_count == 0:
                    self._add_result(
                        "has_networks",
                        False,
                        ValidationSeverity.WARNING,
                        "VM has no network interfaces",
                        suggestions=["Add at least one network interface"],
                    )
                else:
                    self._add_result(
                        "has_networks",
                        True,
                        ValidationSeverity.INFO,
                        f"VM has {network_count} network interface(s)",
                    )

                return self.report

        runner = ValidationRunner()
        runner.add_validator(NetworkValidator())

        # Test with no networks
        report1 = runner.run_all({"network_count": 0})
        assert report1[0].has_warnings()

        # Test with networks
        runner2 = ValidationRunner()
        runner2.add_validator(NetworkValidator())
        report2 = runner2.run_all({"network_count": 2})
        assert not report2[0].has_warnings()

    def test_validator_with_multiple_checks(self):
        """Test validator with multiple validation checks."""

        class MemoryValidator(BaseValidator):
            """Validator for memory configuration."""

            def validate(self, context):
                memory_mb = context.get("memory_mb", 0)

                # Check 1: Has memory
                if memory_mb == 0:
                    self._add_result(
                        "has_memory",
                        False,
                        ValidationSeverity.CRITICAL,
                        "VM has no memory allocated",
                    )
                    return self.report

                self._add_result(
                    "has_memory",
                    True,
                    ValidationSeverity.INFO,
                    f"Memory: {memory_mb}MB",
                )

                # Check 2: Minimum memory
                if memory_mb < 512:
                    self._add_result(
                        "minimum_memory",
                        False,
                        ValidationSeverity.WARNING,
                        f"Memory {memory_mb}MB is less than recommended 512MB",
                        suggestions=["Increase memory to at least 512MB"],
                    )
                else:
                    self._add_result(
                        "minimum_memory",
                        True,
                        ValidationSeverity.INFO,
                        "Memory meets minimum requirements",
                    )

                # Check 3: Power of 2 alignment
                if memory_mb & (memory_mb - 1) != 0:
                    self._add_result(
                        "memory_alignment",
                        False,
                        ValidationSeverity.INFO,
                        "Memory not power-of-2 aligned",
                        details={"memory_mb": memory_mb},
                    )
                else:
                    self._add_result(
                        "memory_alignment",
                        True,
                        ValidationSeverity.INFO,
                        "Memory is power-of-2 aligned",
                    )

                return self.report

        validator = MemoryValidator()

        # Test with valid memory
        report = validator.validate({"memory_mb": 2048})
        assert report.total_checks == 3
        assert not report.has_errors()

        # Test with low memory
        validator2 = MemoryValidator()
        report2 = validator2.validate({"memory_mb": 256})
        assert report2.has_warnings()


class TestValidationReporting:
    """Test validation reporting and summaries."""

    def test_validation_report_summary(self, tmp_path):
        """Test validation report summary generation."""
        disk_path = tmp_path / "disk.qcow2"
        disk_path.write_bytes(b"\x00" * (5 * 1024 * 1024))

        validator = DiskValidator()
        report = validator.validate({
            "output_path": str(disk_path),
            "format": "qcow2",
        })

        summary = report.get_summary()

        assert "validator" in summary
        assert summary["validator"] == "DiskValidator"
        assert "total_checks" in summary
        assert "passed" in summary
        assert "failed" in summary
        assert "duration" in summary
        assert summary["duration"] >= 0

    def test_validation_issues_by_severity(self, tmp_path):
        """Test filtering validation issues by severity."""
        # Create test files
        disk_path = tmp_path / "disk.qcow2"
        disk_path.write_bytes(b"\x00" * 100)  # Too small

        xml_path = tmp_path / "domain.xml"
        xml_path.write_text("invalid")

        runner = ValidationRunner()
        runner.add_validator(DiskValidator())
        runner.add_validator(XMLValidator())

        context = {
            "output_path": str(disk_path),
            "format": "qcow2",
            "minimum_size": 1024 * 1024,
            "xml_path": str(xml_path),
        }

        reports = runner.run_all(context)

        # Collect issues by severity
        all_critical = []
        all_errors = []
        all_warnings = []

        for report in reports:
            all_critical.extend(
                report.get_issues_by_severity(ValidationSeverity.CRITICAL)
            )
            all_errors.extend(
                report.get_issues_by_severity(ValidationSeverity.ERROR)
            )
            all_warnings.extend(
                report.get_issues_by_severity(ValidationSeverity.WARNING)
            )

        assert len(all_critical) > 0  # XML parse error
        assert len(all_errors) > 0  # Disk too small

    def test_validation_with_suggestions(self, tmp_path):
        """Test that validation provides actionable suggestions."""
        # Missing disk
        validator = DiskValidator()
        report = validator.validate({
            "output_path": str(tmp_path / "missing.qcow2"),
            "format": "qcow2",
        })

        critical_issues = report.get_issues_by_severity(ValidationSeverity.CRITICAL)
        assert len(critical_issues) > 0

        # Should have suggestions
        for issue in critical_issues:
            if "not found" in issue.message:
                assert len(issue.suggestions) > 0


class TestValidationPerformance:
    """Test validation performance characteristics."""

    def test_validation_duration_tracking(self, tmp_path):
        """Test that validation tracks execution duration."""
        disk_path = tmp_path / "disk.qcow2"
        disk_path.write_bytes(b"\x00" * (10 * 1024 * 1024))

        validator = DiskValidator()
        report = validator.validate({
            "output_path": str(disk_path),
            "format": "qcow2",
        })

        assert report.duration > 0
        assert report.duration < 10  # Should be fast

    def test_multiple_validators_timing(self, tmp_path):
        """Test timing with multiple validators."""
        # Create test files
        disk_path = tmp_path / "disk.qcow2"
        disk_path.write_bytes(b"\x00" * (5 * 1024 * 1024))

        xml_content = """<?xml version="1.0"?>
<domain type="kvm">
  <name>test</name>
  <devices>
    <disk type="file" device="disk">
      <source file="/disk.qcow2"/>
      <target dev="vda" bus="virtio"/>
    </disk>
  </devices>
</domain>"""

        xml_path = tmp_path / "domain.xml"
        xml_path.write_text(xml_content)

        runner = ValidationRunner()
        runner.add_validator(DiskValidator())
        runner.add_validator(XMLValidator())

        import time

        start = time.time()
        reports = runner.run_all({
            "output_path": str(disk_path),
            "format": "qcow2",
            "xml_path": str(xml_path),
        })
        elapsed = time.time() - start

        # All validators should complete quickly
        assert elapsed < 5
        assert all(r.duration > 0 for r in reports)
