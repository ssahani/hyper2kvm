# SPDX-License-Identifier: LGPL-3.0-or-later
"""Tests for exception handling and secret redaction."""
from __future__ import annotations

import pytest
from hyper2kvm.core.exceptions import Hyper2KvmError, Fatal, VMwareError


@pytest.mark.unit
class TestExceptionHierarchy:
    """Test exception class hierarchy and basic functionality."""

    def test_base_exception_creation(self):
        """Test creating base Hyper2KvmError."""
        err = Hyper2KvmError(code=1, msg="Test error")
        
        assert err.code == 1
        assert err.msg == "Test error"
        assert err.cause is None
        assert err.context == {}

    def test_fatal_exception(self):
        """Test Fatal exception subclass."""
        err = Fatal(code=2, msg="Fatal error")
        
        assert isinstance(err, Hyper2KvmError)
        assert err.code == 2
        assert err.msg == "Fatal error"

    def test_vmware_exception(self):
        """Test VMwareError subclass."""
        err = VMwareError(msg="vSphere connection failed")
        
        assert isinstance(err, Hyper2KvmError)
        assert "vSphere" in err.msg

    def test_exception_with_context(self):
        """Test exception context tracking."""
        err = Hyper2KvmError(code=1, msg="Error").with_context(
            vm_name="test-vm",
            operation="export"
        )
        
        assert err.context["vm_name"] == "test-vm"
        assert err.context["operation"] == "export"

    def test_exception_with_cause(self):
        """Test exception cause chaining."""
        cause = ValueError("Original error")
        err = Hyper2KvmError(code=1, msg="Wrapper", cause=cause)
        
        assert err.cause is cause
        assert isinstance(err.cause, ValueError)


@pytest.mark.security
class TestSecretRedaction:
    """Test that secrets are redacted from error contexts."""

    def test_password_redacted_in_context(self):
        """Test password field is redacted."""
        err = Hyper2KvmError(code=1, msg="Auth failed").with_context(
            username="admin",
            password="super_secret_123",
            host="vcenter.local"
        )
        
        # Convert to dict to check redaction
        err_dict = err.to_dict()
        
        # Password should be redacted
        assert err_dict["context"]["password"] == "***REDACTED***"
        # Other fields should be visible
        assert err_dict["context"]["username"] == "admin"
        assert err_dict["context"]["host"] == "vcenter.local"

    def test_multiple_secrets_redacted(self):
        """Test multiple secret fields are redacted."""
        err = Hyper2KvmError(code=1, msg="Error").with_context(
            api_key="secret-key-123",
            token="bearer-token-456",
            auth="basic-auth-789",
            normal_field="visible"
        )
        
        err_dict = err.to_dict()
        
        # All secret fields redacted
        assert err_dict["context"]["api_key"] == "***REDACTED***"
        assert err_dict["context"]["token"] == "***REDACTED***"
        assert err_dict["context"]["auth"] == "***REDACTED***"
        # Normal field visible
        assert err_dict["context"]["normal_field"] == "visible"

    def test_secret_in_nested_context(self):
        """Test secrets in nested context structures."""
        err = Hyper2KvmError(code=1, msg="Error").with_context(
            credentials={
                "password": "secret123",
                "username": "admin"
            }
        )
        
        err_dict = err.to_dict()
        
        # Nested password should be redacted
        assert err_dict["context"]["credentials"]["password"] == "***REDACTED***"
        assert err_dict["context"]["credentials"]["username"] == "admin"


@pytest.mark.unit
class TestExceptionExitCodes:
    """Test exception exit code validation."""

    def test_valid_exit_codes(self):
        """Test valid exit codes (0-255) are accepted."""
        for code in [0, 1, 2, 127, 255]:
            err = Hyper2KvmError(code=code, msg="Test")
            assert err.code == code

    def test_invalid_exit_code_raises(self):
        """Test invalid exit codes raise ValueError."""
        with pytest.raises(ValueError):
            Hyper2KvmError(code=256, msg="Test")
        
        with pytest.raises(ValueError):
            Hyper2KvmError(code=-1, msg="Test")

    def test_exit_code_in_range(self):
        """Test exit code must be 0-255."""
        # Boundary test
        Hyper2KvmError(code=0, msg="Min")
        Hyper2KvmError(code=255, msg="Max")
        
        # Out of bounds
        with pytest.raises(ValueError):
            Hyper2KvmError(code=256, msg="Too high")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
