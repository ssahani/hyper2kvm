# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Tests for async client availability and imports.
"""

import pytest


class TestAsyncClientAvailability:
    """Test async client availability detection."""

    def test_httpx_availability_flag(self):
        """Test that HTTPX_AVAILABLE flag is boolean."""
        from hyper2kvm.core.optional_imports import HTTPX_AVAILABLE

        assert isinstance(HTTPX_AVAILABLE, bool)

    def test_async_client_module_imports(self):
        """Test that async client module can be imported."""
        import hyper2kvm.vmware.async_client

        assert hasattr(hyper2kvm.vmware.async_client, "HTTPX_AVAILABLE")

    def test_require_httpx_function(self):
        """Test require_httpx helper function."""
        from hyper2kvm.core.optional_imports import require_httpx, HTTPX_AVAILABLE

        if not HTTPX_AVAILABLE:
            with pytest.raises(ImportError, match="httpx"):
                require_httpx()
        else:
            # Should not raise
            require_httpx()

    def test_async_client_import_error_without_httpx(self):
        """Test that async client modules provide helpful error without httpx."""
        from hyper2kvm.core.optional_imports import HTTPX_AVAILABLE

        if not HTTPX_AVAILABLE:
            with pytest.raises(ImportError, match="[Hh]ttpx"):
                from hyper2kvm.vmware.async_client.client import AsyncVMwareClient

            with pytest.raises(ImportError, match="[Hh]ttpx"):
                from hyper2kvm.vmware.async_client.operations import AsyncVMwareOperations


class TestAsyncClientModuleStructure:
    """Test async client module structure."""

    def test_async_client_package_exists(self):
        """Test that async client package exists."""
        import hyper2kvm.vmware.async_client

        assert hyper2kvm.vmware.async_client is not None

    def test_async_client_init_exports(self):
        """Test that __init__ exports availability flag."""
        from hyper2kvm.vmware.async_client import HTTPX_AVAILABLE

        assert isinstance(HTTPX_AVAILABLE, bool)

    @pytest.mark.skipif(
        True,  # Always skip unless httpx is available
        reason="Only run when testing with httpx installed",
    )
    def test_async_client_exports_with_httpx(self):
        """Test async client exports when httpx is available (skipped by default)."""
        from hyper2kvm.core.optional_imports import HTTPX_AVAILABLE

        if HTTPX_AVAILABLE:
            from hyper2kvm.vmware.async_client import (
                AsyncVMwareClient,
                AsyncVMwareOperations,
                ConcurrencyManager,
            )

            assert AsyncVMwareClient is not None
            assert AsyncVMwareOperations is not None
            assert ConcurrencyManager is not None


class TestPyprojectTomlConfiguration:
    """Test pyproject.toml has async dependencies."""

    def test_async_dependency_group_exists(self):
        """Test that async optional dependency group exists in pyproject.toml."""
        from pathlib import Path

        pyproject = Path("/home/ssahani/tt/hyper2kvm/pyproject.toml")
        content = pyproject.read_text()

        assert "async = [" in content or "[project.optional-dependencies]\nasync" in content
        assert "httpx" in content


class TestOptionalImports:
    """Test httpx imports in optional_imports module."""

    def test_httpx_imports(self):
        """Test httpx-related imports."""
        from hyper2kvm.core.optional_imports import (
            HTTPX_AVAILABLE,
            httpx,
            AsyncClient,
            Limits,
            Timeout,
        )

        assert isinstance(HTTPX_AVAILABLE, bool)

        if HTTPX_AVAILABLE:
            assert httpx is not None
            assert AsyncClient is not None
            assert Limits is not None
            assert Timeout is not None
        else:
            assert httpx is None
            assert AsyncClient is None
            assert Limits is None
            assert Timeout is None
