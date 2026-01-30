"""Unit tests for Windows application compatibility detection."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from hyper2kvm.fixers.windows.appcompat.detector import (
    detect_hardware_dependent_apps,
    detect_license_services,
    detect_dongle_drivers,
    AppCompatFinding,
    RiskLevel,
    _check_vendor,
)
from hyper2kvm.fixers.windows.appcompat.sqlserver import (
    detect_sql_server_instances,
    generate_sql_reconfiguration_script,
    SQLServerInstance,
)
from hyper2kvm.fixers.windows.appcompat.reporter import (
    generate_compatibility_report,
    CompatibilityReport,
)


class TestAppCompatFinding:
    """Test AppCompatFinding dataclass."""

    def test_finding_to_dict(self):
        """Test Finding serialization to dict."""
        finding = AppCompatFinding(
            finding_type="app",
            name="AutoCAD 2022",
            vendor="Autodesk",
            version="24.1",
            risk_level=RiskLevel.HIGH,
            recommendations=["Reactivate license after migration"],
            details={"install_location": "C:\\Program Files\\Autodesk"},
        )

        result = finding.to_dict()

        assert result["type"] == "app"
        assert result["name"] == "AutoCAD 2022"
        assert result["vendor"] == "Autodesk"
        assert result["version"] == "24.1"
        assert result["risk_level"] == "HIGH"
        assert len(result["recommendations"]) == 1
        assert result["details"]["install_location"] == "C:\\Program Files\\Autodesk"


class TestVendorDetection:
    """Test hardware-dependent vendor detection."""

    def test_detect_autodesk_vendor(self):
        """Test Autodesk vendor detection."""
        vendor_info = _check_vendor("Autodesk, Inc.")

        assert vendor_info is not None
        assert vendor_info["risk"] == RiskLevel.HIGH
        assert "hardware" in vendor_info["reason"].lower()

    def test_detect_adobe_vendor(self):
        """Test Adobe vendor detection."""
        vendor_info = _check_vendor("Adobe Systems Incorporated")

        assert vendor_info is not None
        assert vendor_info["risk"] == RiskLevel.HIGH

    def test_detect_unknown_vendor(self):
        """Test unknown vendor returns None."""
        vendor_info = _check_vendor("Unknown Vendor Corp")

        assert vendor_info is None

    def test_detect_vendor_case_insensitive(self):
        """Test vendor detection is case-insensitive."""
        vendor_info = _check_vendor("AUTODESK")

        assert vendor_info is not None

    def test_detect_vendor_partial_match(self):
        """Test vendor detection with partial match."""
        vendor_info = _check_vendor("Autodesk North America")

        assert vendor_info is not None


class TestHardwareDependentApps:
    """Test hardware-dependent application detection."""

    def test_detect_apps_basic(self):
        """Test basic app detection (integration test)."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        # Just verify it returns a list without crashing
        result = detect_hardware_dependent_apps(mock_guestfs, root)
        assert isinstance(result, list)

    def test_detect_apps_no_software_hive(self):
        """Test handling when SOFTWARE hive not found."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        with patch(
            "hyper2kvm.fixers.windows.registry.io.detect_windows_hive",
            return_value=None,
        ):
            result = detect_hardware_dependent_apps(mock_guestfs, root)
            assert result == []


class TestLicenseServices:
    """Test license service detection."""

    def test_detect_license_services_basic(self):
        """Test basic license service detection."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        # Just verify it returns a list
        result = detect_license_services(mock_guestfs, root)
        assert isinstance(result, list)

    def test_detect_license_services_no_system_hive(self):
        """Test handling when SYSTEM hive not found."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        with patch(
            "hyper2kvm.fixers.windows.registry.io.detect_windows_hive",
            return_value=None,
        ):
            result = detect_license_services(mock_guestfs, root)
            assert result == []


class TestDongleDrivers:
    """Test hardware dongle driver detection."""

    def test_detect_dongle_drivers_found(self):
        """Test dongle driver detection when driver exists."""
        mock_guestfs = Mock()
        mock_guestfs.exists.return_value = True
        root = "/mnt/windows"

        result = detect_dongle_drivers(mock_guestfs, root)

        # Should find 6 drivers (number of DONGLE_DRIVERS entries)
        assert len(result) == 6
        assert all(f.finding_type == "dongle_driver" for f in result)
        assert all(f.risk_level == RiskLevel.CRITICAL or f.risk_level == RiskLevel.HIGH for f in result)

    def test_detect_dongle_drivers_not_found(self):
        """Test dongle driver detection when no drivers exist."""
        mock_guestfs = Mock()
        mock_guestfs.exists.return_value = False
        root = "/mnt/windows"

        result = detect_dongle_drivers(mock_guestfs, root)

        # Should find no drivers since exists() returns False
        assert len(result) == 0

    def test_detect_specific_dongle_driver(self):
        """Test detection of specific dongle driver."""
        mock_guestfs = Mock()

        # Only akshasp.sys exists
        def exists_side_effect(path):
            return "akshasp" in path

        mock_guestfs.exists.side_effect = exists_side_effect
        root = "/mnt/windows"

        result = detect_dongle_drivers(mock_guestfs, root)

        assert len(result) == 1
        assert "HASP" in result[0].name
        assert result[0].risk_level == RiskLevel.CRITICAL


class TestSQLServerInstance:
    """Test SQLServerInstance dataclass."""

    def test_instance_to_dict(self):
        """Test SQLServerInstance serialization."""
        instance = SQLServerInstance(
            name="MSSQLSERVER",
            instance_id="MSSQL15.MSSQLSERVER",
            version="15.0.2000.5",
            edition="Enterprise Edition",
            data_path="C:\\Program Files\\Microsoft SQL Server\\MSSQL15\\Data",
            log_path="C:\\Program Files\\Microsoft SQL Server\\MSSQL15\\Log",
            backup_path="C:\\Program Files\\Microsoft SQL Server\\MSSQL15\\Backup",
            tcp_port=1433,
            service_account="NT Service\\MSSQLSERVER",
            is_clustered=False,
            is_availability_group=False,
        )

        result = instance.to_dict()

        assert result["name"] == "MSSQLSERVER"
        assert result["version"] == "15.0.2000.5"
        assert result["edition"] == "Enterprise Edition"
        assert result["tcp_port"] == 1433
        assert result["service_account"] == "NT Service\\MSSQLSERVER"


class TestSQLServerDetection:
    """Test SQL Server instance detection."""

    def test_detect_sql_instances_basic(self):
        """Test basic SQL Server detection."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        # Just verify it returns a list
        result = detect_sql_server_instances(mock_guestfs, root)
        assert isinstance(result, list)

    def test_detect_sql_instances_no_software_hive(self):
        """Test handling when SOFTWARE hive not found."""
        mock_guestfs = Mock()
        root = "/mnt/windows"

        with patch(
            "hyper2kvm.fixers.windows.registry.io.detect_windows_hive",
            return_value=None,
        ):
            result = detect_sql_server_instances(mock_guestfs, root)
            assert result == []


class TestSQLReconfigurationScript:
    """Test SQL Server reconfiguration script generation."""

    def test_generate_script_no_instances(self):
        """Test script generation with no instances."""
        instances = []

        script = generate_sql_reconfiguration_script(instances)

        assert "No SQL Server instances detected" in script

    def test_generate_script_single_instance(self):
        """Test script generation with single instance."""
        instances = [
            SQLServerInstance(
                name="MSSQLSERVER",
                instance_id="MSSQL15.MSSQLSERVER",
                version="15.0.2000.5",
                edition="Enterprise Edition",
                tcp_port=1433,
            )
        ]

        script = generate_sql_reconfiguration_script(instances)

        assert "Instance: MSSQLSERVER" in script
        assert "Version: 15.0.2000.5" in script
        assert "Edition: Enterprise Edition" in script
        # Without hostname params, basic guidance is included
        assert "Service Broker" in script or "broker" in script.lower()

    def test_generate_script_with_hostname_substitution(self):
        """Test script generation with hostname substitution."""
        instances = [
            SQLServerInstance(
                name="MSSQLSERVER",
                instance_id="MSSQL15.MSSQLSERVER",
            )
        ]

        script = generate_sql_reconfiguration_script(
            instances, old_hostname="OLD-SERVER", new_hostname="NEW-SERVER"
        )

        assert "OLD-SERVER" in script
        assert "NEW-SERVER" in script

    def test_generate_script_includes_common_tasks(self):
        """Test script includes common post-migration tasks."""
        instances = [
            SQLServerInstance(
                name="MSSQLSERVER",
                instance_id="MSSQL15.MSSQLSERVER",
            )
        ]

        # Generate with hostnames to get full script
        script = generate_sql_reconfiguration_script(
            instances, old_hostname="OLD", new_hostname="NEW"
        )

        script_lower = script.lower()

        # Check for common post-migration guidance
        assert "sp_updatestats" in script_lower or "updatestats" in script_lower
        assert "replication" in script_lower
        assert "service broker" in script_lower or "broker" in script_lower
        # General post-migration tasks section
        assert "compatibility level" in script_lower


class TestCompatibilityReport:
    """Test compatibility report generation."""

    def test_report_to_dict(self):
        """Test CompatibilityReport serialization."""
        report = CompatibilityReport(
            hostname="TEST-SERVER",
            total_findings=3,
            critical_findings=1,
            high_findings=2,
            medium_findings=0,
            low_findings=0,
        )

        result = report.to_dict()

        assert result["hostname"] == "TEST-SERVER"
        assert result["summary"]["total_findings"] == 3
        assert result["summary"]["risk_breakdown"]["critical"] == 1
        assert result["summary"]["risk_breakdown"]["high"] == 2

    def test_report_to_json(self):
        """Test JSON report generation."""
        report = CompatibilityReport(hostname="TEST-SERVER")

        json_str = report.to_json()

        assert "TEST-SERVER" in json_str
        assert "summary" in json_str

    def test_report_to_markdown(self):
        """Test Markdown report generation."""
        report = CompatibilityReport(
            hostname="TEST-SERVER",
            total_findings=2,
            critical_findings=1,
            high_findings=1,
        )

        md = report.to_markdown()

        assert "# Application Compatibility Report" in md
        assert "TEST-SERVER" in md
        assert "Total Findings**: 2" in md
        assert "Critical Risk**: 1" in md

    def test_report_with_findings(self):
        """Test report with actual findings."""
        hardware_apps = [
            AppCompatFinding(
                finding_type="app",
                name="AutoCAD 2022",
                vendor="Autodesk",
                version="24.1",
                risk_level=RiskLevel.HIGH,
                recommendations=["Reactivate license"],
            )
        ]

        dongle_drivers = [
            AppCompatFinding(
                finding_type="dongle_driver",
                name="Aladdin HASP",
                risk_level=RiskLevel.CRITICAL,
                recommendations=["USB passthrough required"],
                details={"driver_name": "akshasp"},
            )
        ]

        report = CompatibilityReport(
            hardware_apps=hardware_apps,
            dongle_drivers=dongle_drivers,
        )

        md = report.to_markdown()

        assert "AutoCAD 2022" in md
        assert "Autodesk" in md
        assert "Aladdin HASP" in md
        assert "USB passthrough" in md


class TestGenerateCompatibilityReport:
    """Test compatibility report generator function."""

    def test_generate_report_empty(self):
        """Test generating report with no findings."""
        report = generate_compatibility_report(
            hardware_apps=[],
            license_services=[],
            dongle_drivers=[],
            sql_instances=[],
        )

        assert report.total_findings == 0
        assert report.critical_findings == 0
        assert report.high_findings == 0

    def test_generate_report_with_findings(self):
        """Test generating report with findings."""
        hardware_apps = [
            AppCompatFinding(
                finding_type="app",
                name="AutoCAD",
                risk_level=RiskLevel.HIGH,
            )
        ]

        license_services = [
            AppCompatFinding(
                finding_type="license_service",
                name="FlexLM",
                risk_level=RiskLevel.HIGH,
            )
        ]

        dongle_drivers = [
            AppCompatFinding(
                finding_type="dongle_driver",
                name="HASP",
                risk_level=RiskLevel.CRITICAL,
            )
        ]

        report = generate_compatibility_report(
            hardware_apps=hardware_apps,
            license_services=license_services,
            dongle_drivers=dongle_drivers,
            sql_instances=[],
        )

        assert report.total_findings == 3
        assert report.critical_findings == 1
        assert report.high_findings == 2
        assert report.medium_findings == 0

    def test_generate_report_risk_calculation(self):
        """Test risk level calculation in report."""
        findings = [
            AppCompatFinding(
                finding_type="app", name="App1", risk_level=RiskLevel.CRITICAL
            ),
            AppCompatFinding(
                finding_type="app", name="App2", risk_level=RiskLevel.HIGH
            ),
            AppCompatFinding(
                finding_type="app", name="App3", risk_level=RiskLevel.MEDIUM
            ),
            AppCompatFinding(
                finding_type="app", name="App4", risk_level=RiskLevel.LOW
            ),
        ]

        report = generate_compatibility_report(
            hardware_apps=findings,
            license_services=[],
            dongle_drivers=[],
            sql_instances=[],
        )

        assert report.total_findings == 4
        assert report.critical_findings == 1
        assert report.high_findings == 1
        assert report.medium_findings == 1
        assert report.low_findings == 1

    def test_generate_report_with_sql_instances(self):
        """Test report generation with SQL Server instances."""
        sql_instances = [
            SQLServerInstance(
                name="MSSQLSERVER",
                instance_id="MSSQL15.MSSQLSERVER",
                version="15.0.2000.5",
            )
        ]

        report = generate_compatibility_report(
            hardware_apps=[],
            license_services=[],
            dongle_drivers=[],
            sql_instances=sql_instances,
        )

        assert len(report.sql_instances) == 1
        assert report.sql_instances[0].name == "MSSQLSERVER"

        # SQL instances don't count toward risk findings
        assert report.total_findings == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
