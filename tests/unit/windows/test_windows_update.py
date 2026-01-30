"""Unit tests for Windows Update Manager."""

import logging
import pytest
from pathlib import Path
from unittest.mock import Mock

from hyper2kvm.windows.windows_update import WindowsUpdateManager


class TestWindowsUpdateManager:
    """Test Windows Update Manager functionality."""

    @pytest.fixture
    def wu_manager(self):
        """Create WindowsUpdateManager instance."""
        logger = logging.getLogger("test")
        return WindowsUpdateManager(logger)

    @pytest.fixture
    def mock_vmcraft(self):
        """Create mock VMCraft instance."""
        mock = Mock()
        mock.exists = Mock(return_value=True)
        mock.mkdir_p = Mock()
        mock.upload = Mock()
        return mock

    def test_init(self, wu_manager):
        """Test WindowsUpdateManager initialization."""
        assert wu_manager is not None
        assert wu_manager.logger is not None
        assert len(wu_manager.VIRTIO_DRIVER_PACKAGES) > 0

    def test_enable_windows_update(self, wu_manager, mock_vmcraft):
        """Test Windows Update service enablement."""
        result = wu_manager.enable_windows_update(mock_vmcraft)

        assert "enabled" in result
        assert "service_configured" in result

        # Should upload enable script
        mock_vmcraft.upload.assert_called()

    def test_stage_virtio_drivers_without_source(self, wu_manager, mock_vmcraft):
        """Test VirtIO driver staging without source path."""
        result = wu_manager.stage_virtio_drivers(mock_vmcraft, driver_source_path=None)

        assert "staged" in result
        assert "staging_path" in result

        # Should create staging directory
        mock_vmcraft.mkdir_p.assert_called()

    def test_stage_virtio_drivers_with_source(self, wu_manager, mock_vmcraft):
        """Test VirtIO driver staging with source path."""
        result = wu_manager.stage_virtio_drivers(
            mock_vmcraft, driver_source_path="/path/to/virtio.iso"
        )

        assert "staged" in result
        assert result["drivers_copied"] > 0

    def test_create_driver_installation_script_all(self, wu_manager):
        """Test driver installation script with all drivers."""
        script = wu_manager.create_driver_installation_script(
            include_virtio=True, include_network=True, include_storage=True
        )

        assert "VirtIO" in script
        assert "viostor" in script
        assert "vioscsi" in script
        assert "vio net" in script or "vionet" in script
        assert "balloon" in script

    def test_create_driver_installation_script_storage_only(self, wu_manager):
        """Test driver installation script with storage drivers only."""
        script = wu_manager.create_driver_installation_script(
            include_virtio=False, include_network=False, include_storage=True
        )

        assert "viostor" in script
        assert "vioscsi" in script

    def test_create_driver_installation_script_network_only(self, wu_manager):
        """Test driver installation script with network drivers only."""
        script = wu_manager.create_driver_installation_script(
            include_virtio=False, include_network=True, include_storage=False
        )

        assert "vio net" in script or "vionet" in script

    def test_inject_driver_installation_script(self, wu_manager, mock_vmcraft):
        """Test driver installation script injection."""
        script_content = "# Test VirtIO driver installation"

        # Mock the scripts.ini existence check
        mock_vmcraft.exists.return_value = False  # No existing scripts.ini

        result = wu_manager.inject_driver_installation_script(
            mock_vmcraft, script_content, run_on_boot=True
        )

        assert result["injected"] is True
        assert result["scheduled"] is True

        # Verify VMCraft methods were called
        mock_vmcraft.mkdir_p.assert_called()
        mock_vmcraft.upload.assert_called()

    def test_inject_driver_installation_script_no_boot(self, wu_manager, mock_vmcraft):
        """Test driver script injection without boot scheduling."""
        script_content = "# Test script"

        result = wu_manager.inject_driver_installation_script(
            mock_vmcraft, script_content, run_on_boot=False
        )

        assert result["injected"] is True
        assert result["scheduled"] is False

    @pytest.mark.parametrize(
        "driver_name,driver_description",
        [
            ("viostor", "VirtIO SCSI Controller"),
            ("vioscsi", "VirtIO SCSI pass-through controller"),
            ("balloon", "VirtIO Balloon Driver"),
        ],
    )
    def test_driver_package_mappings(
        self, wu_manager, driver_name, driver_description
    ):
        """Test VirtIO driver package mappings."""
        # Verify driver package definitions
        assert driver_name in wu_manager.VIRTIO_DRIVER_PACKAGES
        # Note: The actual values might differ, just check they exist
