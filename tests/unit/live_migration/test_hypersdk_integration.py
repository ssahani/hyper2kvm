"""Unit tests for HyperSDK Integration."""

import logging
import pytest

from hyper2kvm.live_migration.hypersdk_integration import HyperSDKIntegration


class TestHyperSDKIntegration:
    """Test HyperSDK Integration functionality."""

    @pytest.fixture
    def hypersdk(self):
        """Create HyperSDKIntegration instance."""
        logger = logging.getLogger("test")
        return HyperSDKIntegration(logger)

    def test_init(self, hypersdk):
        """Test HyperSDKIntegration initialization."""
        assert hypersdk is not None
        assert hypersdk.logger is not None

    def test_is_available(self, hypersdk):
        """Test availability check."""
        # Should return False since HyperSDK is not installed in test environment
        assert isinstance(hypersdk.is_available(), bool)
        assert hypersdk.is_available() is False  # Not installed in test env

    def test_get_supported_providers(self, hypersdk):
        """Test supported providers list."""
        providers = hypersdk.get_supported_providers()

        assert isinstance(providers, list)
        assert "vmware" in providers
        assert "hyperv" in providers
        assert "kvm" in providers
        assert "aws" in providers
        assert "azure" in providers
        assert "gcp" in providers
        assert len(providers) == 6
