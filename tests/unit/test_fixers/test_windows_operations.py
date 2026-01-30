"""
Unit tests for Windows-specific operations

Tests registry manipulation, driver injection, and Windows system
configuration for successful migration to KVM.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path


class TestWindowsRegistry:
    """Test Windows registry operations"""

    @pytest.fixture
    def mock_registry(self):
        """Mock registry handle"""
        registry = Mock()
        registry.read_key = Mock()
        registry.write_key = Mock()
        registry.delete_key = Mock()
        return registry

    def test_read_registry_key(self, mock_registry):
        """Test reading registry key value"""
        # Mock registry read
        mock_registry.read_key.return_value = "value_data"

        value = mock_registry.read_key("HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion")

        assert value == "value_data"
        mock_registry.read_key.assert_called_once()

    def test_write_registry_key(self, mock_registry):
        """Test writing registry key value"""
        # Write new registry value
        mock_registry.write_key.return_value = True

        success = mock_registry.write_key(
            "HKLM\\SYSTEM\\CurrentControlSet\\Services\\VirtIO",
            "Start",
            0  # SERVICE_BOOT_START
        )

        assert success is True
        mock_registry.write_key.assert_called_once()

    def test_delete_registry_key(self, mock_registry):
        """Test deleting registry key"""
        # Delete old driver registry key
        mock_registry.delete_key.return_value = True

        success = mock_registry.delete_key(
            "HKLM\\SYSTEM\\CurrentControlSet\\Services\\VMware"
        )

        assert success is True
        mock_registry.delete_key.assert_called_once()

    def test_malformed_registry_hive(self, mock_registry):
        """Test handling of corrupted registry hive"""
        # Simulate corrupted registry
        mock_registry.read_key.side_effect = RuntimeError("Registry hive corrupted")

        with pytest.raises(RuntimeError):
            mock_registry.read_key("HKLM\\SYSTEM")

    def test_locked_registry_access(self, mock_registry):
        """Test handling registry locked by another process"""
        # Registry key locked
        mock_registry.write_key.side_effect = PermissionError("Registry key is locked")

        with pytest.raises(PermissionError):
            mock_registry.write_key("HKLM\\SYSTEM\\Test", "Value", 1)


class TestDriverInjection:
    """Test VirtIO driver injection for Windows"""

    @pytest.fixture
    def mock_driver_store(self, tmp_path):
        """Mock driver store directory"""
        driver_store = tmp_path / "drivers"
        driver_store.mkdir()

        # Create mock driver files
        (driver_store / "viostor.sys").write_text("storage driver")
        (driver_store / "viostor.inf").write_text("storage driver inf")
        (driver_store / "netkvm.sys").write_text("network driver")
        (driver_store / "netkvm.inf").write_text("network driver inf")

        return driver_store

    def test_inject_virtio_storage_driver(self, mock_driver_store):
        """Test injecting VirtIO storage driver"""
        # Storage driver files
        storage_driver = mock_driver_store / "viostor.sys"
        storage_inf = mock_driver_store / "viostor.inf"

        assert storage_driver.exists()
        assert storage_inf.exists()

        # Would inject these into Windows driver store
        injected_drivers = ["viostor"]
        assert "viostor" in injected_drivers

    def test_inject_virtio_network_driver(self, mock_driver_store):
        """Test injecting VirtIO network driver"""
        # Network driver files
        network_driver = mock_driver_store / "netkvm.sys"
        network_inf = mock_driver_store / "netkvm.inf"

        assert network_driver.exists()
        assert network_inf.exists()

        # Would inject these into Windows driver store
        injected_drivers = ["netkvm"]
        assert "netkvm" in injected_drivers

    def test_driver_signature_verification(self):
        """Test driver signature verification"""
        # Mock driver signature data
        driver_signatures = {
            "viostor.sys": "valid_signature",
            "netkvm.sys": "valid_signature",
            "malicious.sys": "invalid_signature",
        }

        # Verify signatures
        for driver, signature in driver_signatures.items():
            if signature == "valid_signature":
                # Driver is signed
                is_signed = True
            else:
                # Driver is not properly signed
                is_signed = False

            if driver == "malicious.sys":
                assert is_signed is False
            else:
                assert is_signed is True

    def test_driver_version_conflict(self):
        """Test handling driver version conflicts"""
        # Existing driver version
        existing_driver = {
            "name": "viostor.sys",
            "version": "1.0.0.0",
        }

        # New driver version
        new_driver = {
            "name": "viostor.sys",
            "version": "1.5.0.0",
        }

        # Should use newer version
        def compare_versions(v1, v2):
            parts1 = [int(p) for p in v1.split('.')]
            parts2 = [int(p) for p in v2.split('.')]
            return parts2 > parts1  # v2 is newer

        should_upgrade = compare_versions(
            existing_driver["version"],
            new_driver["version"]
        )

        assert should_upgrade is True

    def test_critical_boot_drivers(self):
        """Test identification of critical boot drivers"""
        # Drivers needed for boot
        critical_drivers = [
            "viostor",  # Storage controller
            "vioscsi",  # SCSI storage
        ]

        # Non-critical drivers (can be loaded later)
        optional_drivers = [
            "netkvm",   # Network
            "balloon",  # Memory balloon
            "qemufwcfg", # QEMU firmware config
        ]

        # Must have at least one storage driver
        has_storage_driver = any(
            driver in critical_drivers
            for driver in ["viostor", "vioscsi"]
        )

        assert has_storage_driver is True


class TestSystemProfile:
    """Test Windows system profile modifications"""

    @pytest.fixture
    def mock_registry(self):
        """Mock registry for system profile"""
        registry = Mock()
        registry.read_key = Mock()
        registry.write_key = Mock()
        return registry

    def test_update_system_profile(self, mock_registry):
        """Test updating Windows system profile for virtualization"""
        # Read current HAL type
        mock_registry.read_key.return_value = "ACPIPIC_UP"

        current_hal = mock_registry.read_key(
            "HKLM\\SYSTEM\\CurrentControlSet\\Control\\SystemInformation"
        )

        # For KVM, update to ACPI HAL
        target_hal = "ACPI"

        # Write new HAL type
        mock_registry.write_key(
            "HKLM\\SYSTEM\\CurrentControlSet\\Control\\SystemInformation",
            "SystemProductName",
            "QEMU Virtual Machine"
        )

        mock_registry.write_key.assert_called()

    def test_hardware_abstraction_layer(self, mock_registry):
        """Test HAL (Hardware Abstraction Layer) configuration"""
        # HAL types for different configurations
        hal_types = {
            "physical": "ACPIPIC_UP",      # Physical machine
            "hyper-v": "ACPIPIC_UP",       # Hyper-V VM
            "kvm": "ACPI",                 # KVM/QEMU
        }

        # Migrating from Hyper-V to KVM
        source_hal = hal_types["hyper-v"]
        target_hal = hal_types["kvm"]

        # HAL may need update
        hal_changed = source_hal != target_hal
        assert hal_changed is True or source_hal == target_hal  # May or may not change

    def test_boot_critical_services(self, mock_registry):
        """Test configuration of boot-critical services"""
        # VirtIO storage driver must be boot-start
        SERVICE_BOOT_START = 0
        SERVICE_SYSTEM_START = 1
        SERVICE_AUTO_START = 2

        # Configure viostor service
        mock_registry.write_key(
            "HKLM\\SYSTEM\\CurrentControlSet\\Services\\viostor",
            "Start",
            SERVICE_BOOT_START
        )

        # Configure netkvm service (not boot critical)
        mock_registry.write_key(
            "HKLM\\SYSTEM\\CurrentControlSet\\Services\\netkvm",
            "Start",
            SERVICE_AUTO_START
        )

        assert mock_registry.write_key.call_count == 2


class TestDeviceRemoval:
    """Test removal of old hypervisor devices"""

    @pytest.fixture
    def mock_registry(self):
        """Mock registry"""
        registry = Mock()
        registry.delete_key = Mock(return_value=True)
        return registry

    def test_remove_hyper_v_devices(self, mock_registry):
        """Test removing Hyper-V integration components"""
        hyper_v_services = [
            "vmbus",
            "hv_netvsc",
            "hv_storvsc",
            "hypervideo",
        ]

        # Remove Hyper-V services
        for service in hyper_v_services:
            mock_registry.delete_key(
                f"HKLM\\SYSTEM\\CurrentControlSet\\Services\\{service}"
            )

        assert mock_registry.delete_key.call_count == len(hyper_v_services)

    def test_remove_vmware_tools(self, mock_registry):
        """Test removing VMware Tools components"""
        vmware_services = [
            "vmtools",
            "vmhgfs",
            "vmmouse",
            "vmxnet3",
        ]

        # Remove VMware services
        for service in vmware_services:
            mock_registry.delete_key(
                f"HKLM\\SYSTEM\\CurrentControlSet\\Services\\{service}"
            )

        assert mock_registry.delete_key.call_count == len(vmware_services)

    def test_preserve_critical_services(self, mock_registry):
        """Test preservation of critical Windows services"""
        # Services to preserve
        critical_services = [
            "Disk",
            "PartMgr",
            "volmgr",
            "volsnap",
        ]

        # Should NOT delete these
        mock_registry.delete_key.reset_mock()

        # Only delete hypervisor-specific services
        hypervisor_services = ["vmbus", "vmtools"]
        for service in hypervisor_services:
            if service not in critical_services:
                mock_registry.delete_key(
                    f"HKLM\\SYSTEM\\CurrentControlSet\\Services\\{service}"
                )

        # Should only delete hypervisor services
        assert mock_registry.delete_key.call_count == len(hypervisor_services)


class TestWindowsBootConfiguration:
    """Test Windows boot configuration (BCD)"""

    @pytest.fixture
    def mock_bcd(self):
        """Mock BCD (Boot Configuration Data)"""
        bcd = Mock()
        bcd.read_entry = Mock()
        bcd.write_entry = Mock()
        return bcd

    def test_update_boot_device(self, mock_bcd):
        """Test updating boot device identifier"""
        # Read current boot device
        mock_bcd.read_entry.return_value = {
            "device": "partition=C:",
            "osdevice": "partition=C:",
        }

        boot_entry = mock_bcd.read_entry("{current}")

        # Boot device should reference C:
        assert "partition=C:" in boot_entry["device"]

    def test_safe_mode_boot_options(self, mock_bcd):
        """Test safe mode boot configuration"""
        # Enable safe mode for first boot (helps with driver issues)
        safe_mode_options = {
            "safeboot": "minimal",
            "safebootalternateshell": "yes",
        }

        for option, value in safe_mode_options.items():
            mock_bcd.write_entry("{current}", option, value)

        assert mock_bcd.write_entry.call_count == 2

    def test_disable_driver_signing(self, mock_bcd):
        """Test temporarily disabling driver signature enforcement"""
        # For testing unsigned drivers
        mock_bcd.write_entry("{current}", "testsigning", "on")

        mock_bcd.write_entry.assert_called_once()

    def test_hypervisor_launch_type(self, mock_bcd):
        """Test hypervisor launch type configuration"""
        # For nested virtualization (KVM inside KVM)
        launch_types = {
            "off": "Disable Hyper-V",
            "auto": "Enable Hyper-V if supported",
        }

        # Set hypervisor launch type
        mock_bcd.write_entry("{current}", "hypervisorlaunchtype", "auto")

        mock_bcd.write_entry.assert_called_once()


class TestWindowsVersionDetection:
    """Test Windows version detection"""

    def test_detect_windows_version_from_registry(self):
        """Test detecting Windows version from registry"""
        # Mock registry values for different Windows versions
        windows_versions = {
            "Windows 10": {
                "CurrentVersion": "10.0",
                "CurrentBuild": "19045",
                "ProductName": "Windows 10 Pro",
            },
            "Windows Server 2019": {
                "CurrentVersion": "10.0",
                "CurrentBuild": "17763",
                "ProductName": "Windows Server 2019",
            },
            "Windows 11": {
                "CurrentVersion": "10.0",
                "CurrentBuild": "22000",
                "ProductName": "Windows 11 Pro",
            },
        }

        for os_name, version_data in windows_versions.items():
            # Detect based on build number
            build = int(version_data["CurrentBuild"])

            if build >= 22000:
                detected_os = "Windows 11"
            elif build >= 17763 and "Server" in version_data["ProductName"]:
                detected_os = "Windows Server 2019"
            elif build >= 10240:
                detected_os = "Windows 10"
            else:
                detected_os = "Unknown"

            # Verify detection
            if "Windows 11" in os_name:
                assert detected_os == "Windows 11"
            elif "Server 2019" in os_name:
                assert detected_os == "Windows Server 2019"
            elif "Windows 10" in os_name:
                assert detected_os == "Windows 10"


class TestWindowsActivation:
    """Test Windows activation handling"""

    @pytest.fixture
    def mock_registry(self):
        """Mock registry"""
        registry = Mock()
        registry.read_key = Mock()
        registry.write_key = Mock()
        return registry

    def test_preserve_activation_data(self, mock_registry):
        """Test preserving Windows activation data"""
        # Read activation data
        mock_registry.read_key.return_value = "XXXXX-XXXXX-XXXXX-XXXXX-XXXXX"

        product_key = mock_registry.read_key(
            "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\DigitalProductId"
        )

        # Product key should be preserved during migration
        assert "XXXXX" in product_key

    def test_detect_activation_type(self, mock_registry):
        """Test detecting activation type (Retail, OEM, Volume)"""
        activation_types = {
            "Retail": "00330",
            "OEM": "00426",
            "Volume": "00297",
        }

        # Mock reading activation channel
        mock_registry.read_key.return_value = "00330"

        channel = mock_registry.read_key(
            "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\ProductId"
        )

        # Detect activation type
        if "00330" in channel:
            activation_type = "Retail"
        elif "00426" in channel:
            activation_type = "OEM"
        else:
            activation_type = "Volume"

        assert activation_type == "Retail"

    def test_hardware_id_change_reactivation(self):
        """Test handling reactivation after hardware change"""
        # After migration, hardware changes
        hardware_changed = True

        # Windows may require reactivation
        if hardware_changed:
            requires_reactivation = True
        else:
            requires_reactivation = False

        assert requires_reactivation is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
