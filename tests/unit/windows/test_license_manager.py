"""Unit tests for Windows License Manager."""

import logging
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from hyper2kvm.windows.license import WindowsLicenseManager


class TestWindowsLicenseManager:
    """Test Windows License Manager functionality."""

    @pytest.fixture
    def license_manager(self):
        """Create WindowsLicenseManager instance."""
        logger = logging.getLogger("test")
        return WindowsLicenseManager(logger)

    @pytest.fixture
    def mock_vmcraft(self):
        """Create mock VMCraft instance."""
        mock = Mock()
        mock.exists = Mock(return_value=True)
        mock.mkdir_p = Mock()
        mock.upload = Mock()
        return mock

    def test_init(self, license_manager):
        """Test WindowsLicenseManager initialization."""
        assert license_manager is not None
        assert license_manager.logger is not None

    def test_detect_license_type_windows_vm(self, license_manager, mock_vmcraft):
        """Test license detection on Windows VM."""
        # Mock Windows VM detection
        mock_vmcraft.exists.side_effect = lambda path: (
            path == "/Windows/System32/config/SOFTWARE"
            or path == "/Windows/System32/ServerManager.exe"
            or path == "/Windows/System32/slmgr.vbs"
            or path == "/Windows/ServiceProfiles"
        )

        result = license_manager.detect_license_type(mock_vmcraft)

        assert result["detected"] is True
        assert "license_type" in result
        assert "product_name" in result

    def test_detect_license_type_non_windows_vm(self, license_manager, mock_vmcraft):
        """Test license detection on non-Windows VM."""
        # Mock non-Windows VM
        mock_vmcraft.exists.return_value = False

        result = license_manager.detect_license_type(mock_vmcraft)

        assert result["detected"] is False
        assert result["error"] is not None

    def test_create_reactivation_script_kms(self, license_manager, tmp_path):
        """Test KMS reactivation script generation."""
        license_info = {
            "license_type": WindowsLicenseManager.LICENSE_TYPE_VOLUME_KMS,
            "kms_server": "kms.example.com",
            "kms_port": 1688,
        }

        output_path = tmp_path / "reactivate.ps1"

        result = license_manager.create_reactivation_script(
            license_info,
            str(output_path),
            kms_server="kms.example.com",
            kms_port=1688,
        )

        assert result["created"] is True
        assert output_path.exists()

        # Verify script content
        content = output_path.read_text(encoding="utf-16-le")
        assert "KMS" in content
        assert "kms.example.com" in content
        assert "slmgr.vbs" in content

    def test_create_reactivation_script_mak(self, license_manager, tmp_path):
        """Test MAK reactivation script generation."""
        license_info = {
            "license_type": WindowsLicenseManager.LICENSE_TYPE_VOLUME_MAK,
        }

        output_path = tmp_path / "reactivate-mak.ps1"
        product_key = "XXXXX-XXXXX-XXXXX-XXXXX-XXXXX"

        result = license_manager.create_reactivation_script(
            license_info, str(output_path), product_key=product_key
        )

        assert result["created"] is True
        assert output_path.exists()

        content = output_path.read_text(encoding="utf-16-le")
        assert "MAK" in content
        assert product_key in content

    def test_create_reactivation_script_oem(self, license_manager, tmp_path):
        """Test OEM reactivation script generation."""
        license_info = {
            "license_type": WindowsLicenseManager.LICENSE_TYPE_OEM,
        }

        output_path = tmp_path / "reactivate-oem.ps1"

        result = license_manager.create_reactivation_script(
            license_info, str(output_path)
        )

        assert result["created"] is True
        assert output_path.exists()

        content = output_path.read_text(encoding="utf-16-le")
        assert "OEM" in content

    def test_create_reactivation_script_retail(self, license_manager, tmp_path):
        """Test Retail reactivation script generation."""
        license_info = {
            "license_type": WindowsLicenseManager.LICENSE_TYPE_RETAIL,
        }

        output_path = tmp_path / "reactivate-retail.ps1"
        product_key = "XXXXX-XXXXX-XXXXX-XXXXX-XXXXX"

        result = license_manager.create_reactivation_script(
            license_info, str(output_path), product_key=product_key
        )

        assert result["created"] is True
        assert output_path.exists()

        content = output_path.read_text(encoding="utf-16-le")
        assert "Retail" in content

    def test_create_reactivation_script_unknown_type(self, license_manager, tmp_path):
        """Test script generation with unknown license type."""
        license_info = {
            "license_type": "Unknown",
        }

        output_path = tmp_path / "reactivate.ps1"

        result = license_manager.create_reactivation_script(
            license_info, str(output_path)
        )

        assert result["created"] is False
        assert result["error"] is not None

    def test_inject_reactivation_script(self, license_manager, mock_vmcraft, tmp_path):
        """Test script injection into Windows VM."""
        # Create test script
        script_path = tmp_path / "test-reactivate.ps1"
        script_path.write_text("# Test script", encoding="utf-16-le")

        result = license_manager.inject_reactivation_script(
            mock_vmcraft, str(script_path), run_on_boot=True
        )

        assert result["injected"] is True
        assert result["scheduled"] is True

        # Verify VMCraft methods were called
        mock_vmcraft.mkdir_p.assert_called()
        mock_vmcraft.upload.assert_called()

    def test_inject_reactivation_script_no_boot(
        self, license_manager, mock_vmcraft, tmp_path
    ):
        """Test script injection without boot scheduling."""
        script_path = tmp_path / "test-reactivate.ps1"
        script_path.write_text("# Test script", encoding="utf-16-le")

        result = license_manager.inject_reactivation_script(
            mock_vmcraft, str(script_path), run_on_boot=False
        )

        assert result["injected"] is True
        assert result["scheduled"] is False

    @pytest.mark.parametrize(
        "license_type,expected_in_script",
        [
            (WindowsLicenseManager.LICENSE_TYPE_VOLUME_KMS, "KMS"),
            (WindowsLicenseManager.LICENSE_TYPE_VOLUME_MAK, "MAK"),
            (WindowsLicenseManager.LICENSE_TYPE_OEM, "OEM"),
            (WindowsLicenseManager.LICENSE_TYPE_RETAIL, "Retail"),
        ],
    )
    def test_script_generation_content(
        self, license_manager, tmp_path, license_type, expected_in_script
    ):
        """Test that generated scripts contain appropriate content."""
        license_info = {"license_type": license_type}
        output_path = tmp_path / f"{license_type}.ps1"

        result = license_manager.create_reactivation_script(
            license_info,
            str(output_path),
            product_key="XXXXX-XXXXX-XXXXX-XXXXX-XXXXX",
            kms_server="kms.example.com",
        )

        if license_type != "Unknown":
            assert result["created"] is True
            content = output_path.read_text(encoding="utf-16-le")
            assert expected_in_script in content
            assert "slmgr.vbs" in content or "Activation" in content
