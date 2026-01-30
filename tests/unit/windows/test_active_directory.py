"""Unit tests for Active Directory Manager."""

import logging
import pytest
from pathlib import Path
from unittest.mock import Mock

from hyper2kvm.windows.active_directory import ActiveDirectoryManager


class TestActiveDirectoryManager:
    """Test Active Directory Manager functionality."""

    @pytest.fixture
    def ad_manager(self):
        """Create ActiveDirectoryManager instance."""
        logger = logging.getLogger("test")
        return ActiveDirectoryManager(logger)

    @pytest.fixture
    def mock_vmcraft(self):
        """Create mock VMCraft instance."""
        mock = Mock()
        mock.exists = Mock(return_value=True)
        mock.mkdir_p = Mock()
        mock.upload = Mock()
        mock.download = Mock()
        return mock

    def test_init(self, ad_manager):
        """Test ActiveDirectoryManager initialization."""
        assert ad_manager is not None
        assert ad_manager.logger is not None

    def test_detect_domain_membership_joined(self, ad_manager, mock_vmcraft):
        """Test domain membership detection for domain-joined VM."""
        # Mock domain-joined indicators
        mock_vmcraft.exists.side_effect = lambda path: (
            "/GroupPolicy/Machine" in path or "netlogon.dll" in path
        )

        result = ad_manager.detect_domain_membership(mock_vmcraft)

        assert "is_domain_joined" in result
        assert "computer_name" in result
        assert "domain_name" in result

    def test_detect_domain_membership_workgroup(self, ad_manager, mock_vmcraft):
        """Test domain membership detection for workgroup VM."""
        # Mock workgroup (no domain)
        mock_vmcraft.exists.return_value = False

        result = ad_manager.detect_domain_membership(mock_vmcraft)

        assert result["is_domain_joined"] is False

    def test_create_domain_rejoin_script_with_creds(self, ad_manager):
        """Test domain rejoin script generation with credentials."""
        domain_info = {
            "domain_name": "EXAMPLE.COM",
            "computer_name": "WIN-SERVER01",
            "ou_path": "OU=Servers,DC=example,DC=com",
        }

        credentials = {
            "username": "EXAMPLE\\admin",
            "password": "SecurePassword123",
        }

        script = ad_manager.create_domain_rejoin_script(
            domain_info, credentials=credentials, force_rejoin=True
        )

        assert "EXAMPLE.COM" in script
        assert "WIN-SERVER01" in script
        assert "Add-Computer" in script
        assert "EXAMPLE\\admin" in script

    def test_create_domain_rejoin_script_interactive(self, ad_manager):
        """Test domain rejoin script generation for interactive mode."""
        domain_info = {
            "domain_name": "EXAMPLE.COM",
            "computer_name": "WIN-SERVER01",
        }

        script = ad_manager.create_domain_rejoin_script(
            domain_info, credentials=None, force_rejoin=False
        )

        assert "EXAMPLE.COM" in script
        assert "Get-Credential" in script
        assert "interactive" in script.lower()

    def test_inject_domain_rejoin_script(self, ad_manager, mock_vmcraft):
        """Test domain rejoin script injection."""
        script_content = "# Test domain rejoin script"

        # Mock the scripts.ini existence check
        mock_vmcraft.exists.return_value = False  # No existing scripts.ini

        result = ad_manager.inject_domain_rejoin_script(
            mock_vmcraft, script_content, run_on_boot=True
        )

        assert result["injected"] is True
        assert result["scheduled"] is True

        # Verify VMCraft methods were called
        mock_vmcraft.mkdir_p.assert_called()
        mock_vmcraft.upload.assert_called()

    def test_cleanup_old_computer_object(self, ad_manager):
        """Test AD computer object cleanup script generation."""
        domain_info = {
            "computer_name": "WIN-SERVER01",
            "domain_name": "EXAMPLE.COM",
        }

        credentials = {
            "username": "EXAMPLE\\admin",
            "password": "SecurePassword123",
        }

        result = ad_manager.cleanup_old_computer_object(domain_info, credentials)

        assert result["script_generated"] is True
        assert result["script_content"] is not None
        assert result["instructions"] is not None

        # Verify script content
        script = result["script_content"]
        assert "WIN-SERVER01" in script
        assert "Get-ADComputer" in script
        assert "Remove-ADComputer" in script

    def test_cleanup_without_computer_name(self, ad_manager):
        """Test cleanup script generation fails without computer name."""
        domain_info = {"domain_name": "EXAMPLE.COM"}
        credentials = {"username": "admin", "password": "pass"}

        result = ad_manager.cleanup_old_computer_object(domain_info, credentials)

        assert result["script_generated"] is False
        assert result["error"] is not None

    @pytest.mark.parametrize(
        "force_rejoin,expected_in_script",
        [
            (True, "Remove-Computer"),
            (False, "# Force rejoin disabled"),
        ],
    )
    def test_force_rejoin_option(self, ad_manager, force_rejoin, expected_in_script):
        """Test force rejoin option in script generation."""
        domain_info = {
            "domain_name": "EXAMPLE.COM",
            "computer_name": "WIN-SERVER01",
        }

        credentials = {"username": "admin", "password": "pass"}

        script = ad_manager.create_domain_rejoin_script(
            domain_info, credentials=credentials, force_rejoin=force_rejoin
        )

        assert expected_in_script in script
