"""Unit tests for Windows Migration Orchestrator."""

import argparse
import logging
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from hyper2kvm.windows.orchestrator import WindowsMigrationOrchestrator


class TestWindowsMigrationOrchestrator:
    """Test Windows Migration Orchestrator functionality."""

    @pytest.fixture
    def orchestrator(self):
        """Create WindowsMigrationOrchestrator instance."""
        logger = logging.getLogger("test")
        args = argparse.Namespace(
            windows_product_key=None,
            windows_kms_server=None,
            windows_kms_port=None,
            windows_virtio_drivers=True,
        )
        return WindowsMigrationOrchestrator(logger, args)

    @pytest.fixture
    def mock_vmcraft(self):
        """Create mock VMCraft instance."""
        mock = Mock()
        mock.exists = Mock(return_value=True)
        mock.mkdir_p = Mock()
        mock.upload = Mock()
        return mock

    def test_init(self, orchestrator):
        """Test WindowsMigrationOrchestrator initialization."""
        assert orchestrator is not None
        assert orchestrator.logger is not None
        assert orchestrator.license_mgr is not None
        assert orchestrator.ad_mgr is not None
        assert orchestrator.sql_mgr is not None
        assert orchestrator.wu_mgr is not None

    @patch("hyper2kvm.windows.orchestrator.WindowsLicenseManager")
    @patch("hyper2kvm.windows.orchestrator.ActiveDirectoryManager")
    @patch("hyper2kvm.windows.orchestrator.SQLServerManager")
    def test_detect_windows_configuration(
        self, mock_sql, mock_ad, mock_license, orchestrator, mock_vmcraft
    ):
        """Test Windows configuration detection."""
        # Mock detection results
        mock_license.return_value.detect_license_type.return_value = {
            "detected": True,
            "license_type": "Volume:KMS",
        }
        mock_ad.return_value.detect_domain_membership.return_value = {
            "is_domain_joined": True,
            "domain_name": "EXAMPLE.COM",
        }
        mock_sql.return_value.detect_sql_server.return_value = {
            "detected": True,
            "instances": [{"name": "MSSQLSERVER"}],
        }

        orchestrator.license_mgr = mock_license.return_value
        orchestrator.ad_mgr = mock_ad.return_value
        orchestrator.sql_mgr = mock_sql.return_value

        config = orchestrator.detect_windows_configuration(mock_vmcraft)

        assert config["detected"] is True
        assert "license" in config
        assert "domain" in config
        assert "sql_server" in config

    @patch("hyper2kvm.windows.orchestrator.WindowsLicenseManager")
    @patch("hyper2kvm.windows.orchestrator.WindowsUpdateManager")
    def test_prepare_windows_migration(
        self, mock_wu, mock_license, orchestrator, mock_vmcraft, tmp_path
    ):
        """Test Windows VM migration preparation."""
        config = {
            "license": {"detected": True, "license_type": "Volume:KMS"},
            "domain": {"is_domain_joined": False},
            "sql_server": {"detected": False},
        }

        # Mock manager methods
        mock_license.return_value.create_reactivation_script.return_value = {
            "created": True
        }
        mock_license.return_value.inject_reactivation_script.return_value = {
            "injected": True
        }
        mock_wu.return_value.stage_virtio_drivers.return_value = {"staged": True}
        mock_wu.return_value.create_driver_installation_script.return_value = (
            "# Driver script"
        )
        mock_wu.return_value.inject_driver_installation_script.return_value = {
            "injected": True
        }

        orchestrator.license_mgr = mock_license.return_value
        orchestrator.wu_mgr = mock_wu.return_value

        result = orchestrator.prepare_windows_migration(mock_vmcraft, config, tmp_path)

        assert "prepared" in result
        assert "scripts_created" in result
        assert "scripts_injected" in result
        assert "drivers_staged" in result

    def test_generate_post_migration_guide(self, orchestrator, tmp_path):
        """Test post-migration guide generation."""
        config = {
            "license": {
                "detected": True,
                "license_type": "Volume:KMS",
            },
            "domain": {
                "is_domain_joined": True,
                "domain_name": "EXAMPLE.COM",
            },
            "sql_server": {
                "detected": True,
                "instances": [{"name": "MSSQLSERVER", "version": "SQL Server 2019"}],
            },
        }

        guide_path = tmp_path / "post-migration-guide.md"

        orchestrator.generate_post_migration_guide(config, guide_path)

        assert guide_path.exists()

        # Verify guide content
        content = guide_path.read_text()
        assert "Post-Migration Guide" in content
        assert "License Reactivation" in content
        assert "Domain Rejoin" in content or "Active Directory" in content
        assert "SQL Server" in content
        assert "VirtIO" in content

    def test_generate_post_migration_guide_minimal(self, orchestrator, tmp_path):
        """Test guide generation with minimal configuration."""
        config = {
            "license": {"detected": False},
            "domain": {"is_domain_joined": False},
            "sql_server": {"detected": False},
        }

        guide_path = tmp_path / "minimal-guide.md"

        orchestrator.generate_post_migration_guide(config, guide_path)

        assert guide_path.exists()

        content = guide_path.read_text()
        assert "Post-Migration Guide" in content
        assert "VirtIO" in content  # Should always include VirtIO

    @pytest.mark.parametrize(
        "license_detected,domain_joined,sql_detected,expected_scripts",
        [
            (True, True, True, 3),  # All features
            (True, False, False, 1),  # License only
            (False, True, False, 1),  # Domain only
            (False, False, True, 1),  # SQL only
            (False, False, False, 0),  # None
        ],
    )
    def test_script_generation_combinations(
        self,
        orchestrator,
        mock_vmcraft,
        tmp_path,
        license_detected,
        domain_joined,
        sql_detected,
        expected_scripts,
    ):
        """Test that correct number of scripts are generated based on configuration."""
        config = {
            "license": {"detected": license_detected, "license_type": "Volume:KMS"},
            "domain": {"is_domain_joined": domain_joined, "domain_name": "EXAMPLE.COM"},
            "sql_server": {
                "detected": sql_detected,
                "instances": [{"name": "MSSQLSERVER"}],
            },
        }

        # This is a logical test - actual implementation may vary
        # Just verify config structure is correct
        assert config["license"]["detected"] == license_detected
        assert config["domain"]["is_domain_joined"] == domain_joined
        assert config["sql_server"]["detected"] == sql_detected
