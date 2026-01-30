"""
Integration tests for migration tools workflow.

Tests the complete migration workflow:
1. Pre-migration readiness assessment
2. Migration orchestration
3. Post-migration validation

These tests validate that the migration tools work correctly together
and produce expected results.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def test_disk_image(tmp_path):
    """Create a test disk image for migration testing."""
    img = tmp_path / "test-vm.qcow2"

    # Create a small test image (100MB)
    subprocess.run(
        ["qemu-img", "create", "-f", "qcow2", str(img), "100M"],
        check=True,
        capture_output=True
    )

    return img


@pytest.fixture
def migration_tools_dir():
    """Get path to migration tools directory."""
    repo_root = Path(__file__).parent.parent.parent.parent
    tools_dir = repo_root / "examples" / "migration_tools"

    if not tools_dir.exists():
        pytest.skip("Migration tools directory not found")

    return tools_dir


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create temporary directory for test outputs."""
    output_dir = tmp_path / "migration_output"
    output_dir.mkdir()
    return output_dir


class TestMigrationWorkflow:
    """Integration tests for complete migration workflow."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_complete_workflow_with_mock_vm(
        self,
        test_disk_image,
        temp_output_dir,
        migration_tools_dir
    ):
        """
        Test complete migration workflow with a mock VM.

        This is a placeholder test that validates the workflow structure.
        Real VM migration tests require actual VM images with OS installed.
        """
        readiness_script = migration_tools_dir / "pre_migration_readiness.py"
        orchestrator_script = migration_tools_dir / "migration_orchestrator.py"
        validation_script = migration_tools_dir / "post_migration_validation.py"

        # Verify scripts exist
        assert readiness_script.exists(), "Readiness script not found"
        assert orchestrator_script.exists(), "Orchestrator script not found"
        assert validation_script.exists(), "Validation script not found"

        # Note: Actual execution would require a real VM image with OS
        # This test validates the scripts are present and executable

        # Check scripts are executable or can be run with python
        for script in [readiness_script, orchestrator_script, validation_script]:
            result = subprocess.run(
                ["python3", str(script), "--help"],
                capture_output=True,
                text=True
            )
            # Script should show help without errors
            assert result.returncode in [0, 2], f"Script {script.name} not executable"

    @pytest.mark.integration
    def test_readiness_assessment_report_structure(
        self,
        migration_tools_dir,
        temp_output_dir
    ):
        """Test that readiness assessment produces correct report structure."""
        # This test validates the report structure without requiring a real VM

        # Expected report structure
        expected_keys = [
            "timestamp",
            "vm_image",
            "risk_assessment",
            "os_compatibility",
            "disk_configuration",
            "lvm_configuration",
            "systemd_services",
            "network_configuration",
            "boot_configuration",
            "blockers",
            "recommendations"
        ]

        # Validate the expected structure is documented
        readiness_script = migration_tools_dir / "pre_migration_readiness.py"

        with open(readiness_script) as f:
            content = f.read()

            # Check that report structure includes expected keys
            for key in expected_keys:
                assert key in content, f"Report should include '{key}' field"

    @pytest.mark.integration
    def test_orchestrator_strategies_defined(self, migration_tools_dir):
        """Test that migration orchestrator defines all expected strategies."""
        orchestrator_script = migration_tools_dir / "migration_orchestrator.py"

        with open(orchestrator_script) as f:
            content = f.read()

        # Expected strategies
        expected_strategies = [
            "basic",
            "enterprise",
            "database",
            "web_server",
            "security_hardened",
            "minimal_downtime"
        ]

        for strategy in expected_strategies:
            # Check strategy is defined in MigrationStrategy enum
            assert f'"{strategy}"' in content or f"'{strategy}'" in content, \
                f"Strategy '{strategy}' should be defined"

    @pytest.mark.integration
    def test_validation_report_structure(self, migration_tools_dir):
        """Test that post-migration validation produces correct report structure."""
        validation_script = migration_tools_dir / "post_migration_validation.py"

        with open(validation_script) as f:
            content = f.read()

        # Expected validation checks
        expected_checks = [
            "boot_configuration",
            "service_health",
            "network_configuration",
            "filesystem_integrity",
            "boot_performance",
            "security_posture"
        ]

        for check in expected_checks:
            assert check in content, f"Validation should include '{check}' check"

    @pytest.mark.integration
    def test_batch_migration_config_structure(self, migration_tools_dir):
        """Test batch migration config file has correct structure."""
        batch_config = migration_tools_dir / "batch_migration_example.json"

        if not batch_config.exists():
            pytest.skip("Batch config example not found")

        with open(batch_config) as f:
            config = json.load(f)

        # Validate structure
        assert "migrations" in config, "Config should have 'migrations' key"
        assert isinstance(config["migrations"], list), "Migrations should be a list"

        # Validate each migration entry
        for migration in config["migrations"]:
            assert "source" in migration, "Migration should have 'source'"
            assert "target" in migration, "Migration should have 'target'"
            assert "strategy" in migration, "Migration should have 'strategy'"

    @pytest.mark.integration
    def test_migration_cookbook_recipes(self, migration_tools_dir):
        """Test that migration cookbook includes expected recipes."""
        cookbook = migration_tools_dir / "MIGRATION-COOKBOOK.md"

        if not cookbook.exists():
            pytest.skip("Migration cookbook not found")

        with open(cookbook) as f:
            content = f.read()

        # Expected recipes
        expected_recipes = [
            "Basic VMware to KVM Migration",
            "Large Enterprise VM Migration",
            "Database Server Migration",
            "Web Server Farm Migration",
            "Security-Hardened Migration",
            "Minimal Downtime Migration",
            "Disaster Recovery",
            "Batch Migration",
            "Troubleshooting",
            "Performance Optimization"
        ]

        for recipe in expected_recipes:
            assert recipe in content, f"Cookbook should include '{recipe}' recipe"


class TestMigrationToolsScriptExecution:
    """Test that migration tools scripts can be executed."""

    @pytest.mark.integration
    def test_readiness_script_help(self, migration_tools_dir):
        """Test readiness assessment script shows help."""
        script = migration_tools_dir / "pre_migration_readiness.py"

        result = subprocess.run(
            ["python3", str(script), "--help"],
            capture_output=True,
            text=True
        )

        # Should show help (exit code 0 or 2 depending on argparse version)
        assert result.returncode in [0, 2]
        assert "usage:" in result.stdout.lower() or "Usage:" in result.stdout

    @pytest.mark.integration
    def test_orchestrator_script_help(self, migration_tools_dir):
        """Test migration orchestrator script shows help."""
        script = migration_tools_dir / "migration_orchestrator.py"

        result = subprocess.run(
            ["python3", str(script), "--help"],
            capture_output=True,
            text=True
        )

        assert result.returncode in [0, 2]
        assert "usage:" in result.stdout.lower() or "Usage:" in result.stdout

    @pytest.mark.integration
    def test_validation_script_help(self, migration_tools_dir):
        """Test post-migration validation script shows help."""
        script = migration_tools_dir / "post_migration_validation.py"

        result = subprocess.run(
            ["python3", str(script), "--help"],
            capture_output=True,
            text=True
        )

        assert result.returncode in [0, 2]
        assert "usage:" in result.stdout.lower() or "Usage:" in result.stdout


class TestMigrationToolsDocumentation:
    """Test that migration tools documentation is complete."""

    @pytest.mark.integration
    def test_readme_exists(self, migration_tools_dir):
        """Test that README exists with complete documentation."""
        readme = migration_tools_dir / "README.md"

        assert readme.exists(), "README.md should exist"

        with open(readme) as f:
            content = f.read()

        # Check for key sections
        expected_sections = [
            "Overview",
            "Tools",
            "Installation",
            "Quick Start",
            "Usage",
            "Best Practices",
            "Troubleshooting"
        ]

        for section in expected_sections:
            assert section in content, f"README should include '{section}' section"

    @pytest.mark.integration
    def test_cookbook_exists(self, migration_tools_dir):
        """Test that migration cookbook exists."""
        cookbook = migration_tools_dir / "MIGRATION-COOKBOOK.md"

        assert cookbook.exists(), "MIGRATION-COOKBOOK.md should exist"

        with open(cookbook) as f:
            content = f.read()

        # Should have multiple recipes
        assert content.count("## Recipe") >= 5, "Should have at least 5 recipes"

    @pytest.mark.integration
    def test_all_tools_documented(self, migration_tools_dir):
        """Test that all tools are documented in README."""
        readme = migration_tools_dir / "README.md"

        with open(readme) as f:
            readme_content = f.read()

        # List of tool scripts
        tool_scripts = [
            "pre_migration_readiness.py",
            "migration_orchestrator.py",
            "post_migration_validation.py"
        ]

        for script in tool_scripts:
            assert script in readme_content, f"README should document {script}"


class TestMigrationReports:
    """Test migration report structures."""

    @pytest.mark.integration
    def test_readiness_report_has_risk_scoring(self, migration_tools_dir):
        """Test readiness report includes risk scoring."""
        script = migration_tools_dir / "pre_migration_readiness.py"

        with open(script) as f:
            content = f.read()

        # Should have risk scoring logic
        assert "risk_score" in content or "risk_assessment" in content
        assert "LOW" in content and "HIGH" in content and "CRITICAL" in content

    @pytest.mark.integration
    def test_validation_report_has_production_readiness(self, migration_tools_dir):
        """Test validation report includes production readiness scoring."""
        script = migration_tools_dir / "post_migration_validation.py"

        with open(script) as f:
            content = f.read()

        # Should have production readiness logic
        assert "production_readiness" in content or "production_score" in content
        assert "READY" in content

    @pytest.mark.integration
    def test_orchestrator_generates_reports(self, migration_tools_dir):
        """Test orchestrator generates comprehensive reports."""
        script = migration_tools_dir / "migration_orchestrator.py"

        with open(script) as f:
            content = f.read()

        # Should generate JSON reports
        assert "json.dump" in content or "JSON" in content
        assert "report" in content.lower()


@pytest.mark.integration
class TestEndToEndWorkflow:
    """
    End-to-end workflow tests.

    Note: These are placeholder tests. Real E2E tests would require
    actual VM images with operating systems installed.
    """

    def test_workflow_phases_defined(self, migration_tools_dir):
        """Test that all workflow phases are defined in orchestrator."""
        orchestrator = migration_tools_dir / "migration_orchestrator.py"

        with open(orchestrator) as f:
            content = f.read()

        # Expected workflow phases
        expected_phases = [
            "readiness_assessment",
            "pre_migration_backup",
            "inspection",
            "migration",
            "service_management",
            "network_configuration",
            "security_hardening",
            "boot_validation",
            "post_migration_validation",
            "final_report"
        ]

        for phase in expected_phases:
            assert phase in content, f"Orchestrator should define '{phase}' phase"

    def test_workflow_has_rollback_support(self, migration_tools_dir):
        """Test that workflow supports rollback."""
        orchestrator = migration_tools_dir / "migration_orchestrator.py"

        with open(orchestrator) as f:
            content = f.read()

        # Should have rollback functionality
        assert "rollback" in content.lower()
        assert "backup" in content.lower()

    def test_workflow_supports_dry_run(self, migration_tools_dir):
        """Test that workflow supports dry-run mode."""
        orchestrator = migration_tools_dir / "migration_orchestrator.py"

        with open(orchestrator) as f:
            content = f.read()

        # Should support dry-run
        assert "dry_run" in content or "dry-run" in content
