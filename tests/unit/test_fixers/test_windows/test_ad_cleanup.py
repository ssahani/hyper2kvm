"""Unit tests for Active Directory computer object cleanup."""

import pytest
from unittest.mock import Mock, patch
from hyper2kvm.fixers.windows.activedirectory.cleanup import (
    generate_cleanup_script,
    stage_cleanup_script,
    get_cleanup_command,
    CleanupMethod,
)


class TestCleanupScriptGeneration:
    """Test AD cleanup script generation."""

    def test_generate_powershell_script(self):
        """Test PowerShell script generation."""
        script = generate_cleanup_script(
            old_computer_name="OLD-SERVER",
            domain="example.com",
            method=CleanupMethod.POWERSHELL_SCRIPT,
        )

        assert isinstance(script, str)
        assert "OLD-SERVER" in script
        assert "example.com" in script
        assert "Get-ADComputer" in script
        assert "Remove-ADComputer" in script
        assert "#Requires -Modules ActiveDirectory" in script

    def test_generate_powershell_script_with_ou(self):
        """Test PowerShell script with OU path."""
        script = generate_cleanup_script(
            old_computer_name="OLD-SERVER",
            domain="example.com",
            method=CleanupMethod.POWERSHELL_SCRIPT,
            ou_path="OU=Servers,DC=example,DC=com",
        )

        assert "OU=Servers,DC=example,DC=com" in script
        assert "-SearchBase" in script

    def test_generate_netdom_script(self):
        """Test netdom script generation."""
        script = generate_cleanup_script(
            old_computer_name="OLD-SERVER",
            domain="example.com",
            method=CleanupMethod.NETDOM,
        )

        assert "OLD-SERVER" in script
        assert "example.com" in script
        assert "netdom remove" in script
        assert "Get-Credential" in script

    def test_generate_manual_instructions(self):
        """Test manual instructions generation."""
        script = generate_cleanup_script(
            old_computer_name="OLD-SERVER",
            domain="example.com",
            method=CleanupMethod.MANUAL,
        )

        assert "OLD-SERVER" in script
        assert "example.com" in script
        assert "dsa.msc" in script
        assert "MANUAL CLEANUP STEPS" in script

    def test_manual_instructions_with_ou(self):
        """Test manual instructions with OU path."""
        script = generate_cleanup_script(
            old_computer_name="OLD-SERVER",
            domain="example.com",
            method=CleanupMethod.MANUAL,
            ou_path="OU=Servers,DC=example,DC=com",
        )

        assert "OU=Servers,DC=example,DC=com" in script


class TestCleanupScriptStaging:
    """Test AD cleanup script staging."""

    def test_stage_cleanup_script(self):
        """Test staging cleanup script in guest."""
        mock_guestfs = Mock()
        mock_guestfs.mkdir_p.return_value = None
        mock_guestfs.write.return_value = None

        result = stage_cleanup_script(
            g=mock_guestfs,
            root="/mnt/windows",
            old_computer_name="OLD-SERVER",
            domain="example.com",
            method=CleanupMethod.POWERSHELL_SCRIPT,
        )

        assert result["success"] is True
        assert result["script_path"] == "/mnt/windows/hyper2kvm/activedirectory/ad-cleanup.ps1"
        assert result["method"] == "powershell"
        assert len(result["warnings"]) == 0

        # Verify guestfs calls
        mock_guestfs.mkdir_p.assert_called_once_with("/mnt/windows/hyper2kvm/activedirectory")
        mock_guestfs.write.assert_called_once()

    def test_stage_cleanup_script_with_ou(self):
        """Test staging with OU path."""
        mock_guestfs = Mock()
        mock_guestfs.mkdir_p.return_value = None
        mock_guestfs.write.return_value = None

        result = stage_cleanup_script(
            g=mock_guestfs,
            root="/mnt/windows",
            old_computer_name="OLD-SERVER",
            domain="example.com",
            method=CleanupMethod.POWERSHELL_SCRIPT,
            ou_path="OU=Servers,DC=example,DC=com",
        )

        assert result["success"] is True
        mock_guestfs.write.assert_called_once()

        # Verify OU path in script content
        call_args = mock_guestfs.write.call_args
        script_content = call_args[0][1].decode("utf-8")
        assert "OU=Servers,DC=example,DC=com" in script_content

    def test_stage_manual_instructions(self):
        """Test staging manual instructions."""
        mock_guestfs = Mock()
        mock_guestfs.mkdir_p.return_value = None
        mock_guestfs.write.return_value = None

        result = stage_cleanup_script(
            g=mock_guestfs,
            root="/mnt/windows",
            old_computer_name="OLD-SERVER",
            domain="example.com",
            method=CleanupMethod.MANUAL,
        )

        assert result["success"] is True
        assert result["method"] == "manual"

    def test_stage_netdom_script(self):
        """Test staging netdom script."""
        mock_guestfs = Mock()
        mock_guestfs.mkdir_p.return_value = None
        mock_guestfs.write.return_value = None

        result = stage_cleanup_script(
            g=mock_guestfs,
            root="/mnt/windows",
            old_computer_name="OLD-SERVER",
            domain="example.com",
            method=CleanupMethod.NETDOM,
        )

        assert result["success"] is True
        assert result["method"] == "netdom"

    def test_stage_cleanup_script_error_handling(self):
        """Test error handling during staging."""
        mock_guestfs = Mock()
        mock_guestfs.mkdir_p.side_effect = Exception("Filesystem error")

        result = stage_cleanup_script(
            g=mock_guestfs,
            root="/mnt/windows",
            old_computer_name="OLD-SERVER",
            domain="example.com",
        )

        assert result["success"] is False
        assert len(result["warnings"]) > 0
        assert "Staging failed" in result["warnings"][0]


class TestCleanupCommands:
    """Test cleanup command generation."""

    def test_get_cleanup_command_powershell(self):
        """Test PowerShell cleanup command."""
        command = get_cleanup_command(CleanupMethod.POWERSHELL_SCRIPT)

        assert "PowerShell.exe" in command
        assert "-ExecutionPolicy Bypass" in command
        assert "ad-cleanup.ps1" in command

    def test_get_cleanup_command_netdom(self):
        """Test netdom cleanup command."""
        command = get_cleanup_command(CleanupMethod.NETDOM)

        assert "PowerShell.exe" in command
        assert "ad-cleanup.ps1" in command

    def test_get_cleanup_command_manual(self):
        """Test manual instructions command."""
        command = get_cleanup_command(CleanupMethod.MANUAL)

        assert "notepad" in command
        assert "ad-cleanup.ps1" in command


class TestScriptContent:
    """Test script content details."""

    def test_powershell_script_has_logging(self):
        """Test PowerShell script includes logging."""
        script = generate_cleanup_script(
            old_computer_name="TEST-PC",
            domain="test.local",
            method=CleanupMethod.POWERSHELL_SCRIPT,
        )

        assert "Write-Log" in script
        assert "$LogFile" in script
        assert "ad-cleanup.log" in script

    def test_powershell_script_has_confirmation(self):
        """Test PowerShell script requires confirmation."""
        script = generate_cleanup_script(
            old_computer_name="TEST-PC",
            domain="test.local",
            method=CleanupMethod.POWERSHELL_SCRIPT,
        )

        assert "Read-Host" in script
        assert "DELETE" in script
        assert "WARNING" in script

    def test_powershell_script_requires_ad_module(self):
        """Test PowerShell script requires AD module."""
        script = generate_cleanup_script(
            old_computer_name="TEST-PC",
            domain="test.local",
            method=CleanupMethod.POWERSHELL_SCRIPT,
        )

        assert "#Requires -Modules ActiveDirectory" in script
        assert "Import-Module ActiveDirectory" in script

    def test_netdom_script_has_credential_prompt(self):
        """Test netdom script prompts for credentials."""
        script = generate_cleanup_script(
            old_computer_name="TEST-PC",
            domain="test.local",
            method=CleanupMethod.NETDOM,
        )

        assert "Get-Credential" in script
        assert "domain administrator credentials" in script.lower()

    def test_manual_instructions_include_verification(self):
        """Test manual instructions include verification steps."""
        script = generate_cleanup_script(
            old_computer_name="TEST-PC",
            domain="test.local",
            method=CleanupMethod.MANUAL,
        )

        assert "dsquery" in script
        assert "Verify deletion" in script


class TestEnumValues:
    """Test CleanupMethod enum."""

    def test_cleanup_method_values(self):
        """Test CleanupMethod enum values."""
        assert CleanupMethod.MANUAL.value == "manual"
        assert CleanupMethod.POWERSHELL_SCRIPT.value == "powershell"
        assert CleanupMethod.NETDOM.value == "netdom"

    def test_cleanup_method_enum(self):
        """Test CleanupMethod is an enum."""
        from enum import Enum

        assert issubclass(CleanupMethod, Enum)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
