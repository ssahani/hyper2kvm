# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test retry compatibility with and without tenacity.
"""

import pytest
import time
from unittest.mock import Mock
from hyper2kvm.core.retry_enhanced import (
    retry_network_operation,
    retry_vmware_api,
    retry_file_operation,
    RetryContext,
)
from hyper2kvm.core.optional_imports import TENACITY_AVAILABLE


class TestRetryCompatibility:
    """Test retry works with or without tenacity."""

    def test_retry_network_succeeds_after_retries(self):
        """Should retry and eventually succeed."""
        mock_func = Mock(side_effect=[ConnectionError("Failed"), ConnectionError("Failed"), "Success"])
        mock_func.__name__ = "test_func"  # Mock needs __name__ attribute

        decorated = retry_network_operation(max_attempts=5)(mock_func)
        result = decorated()

        assert result == "Success"
        assert mock_func.call_count == 3

    def test_retry_network_fails_after_max_attempts(self):
        """Should fail after max attempts."""
        mock_func = Mock(side_effect=ConnectionError("Persistent failure"))
        mock_func.__name__ = "test_func"  # Mock needs __name__ attribute

        decorated = retry_network_operation(max_attempts=3)(mock_func)

        with pytest.raises((ConnectionError, Exception)):
            decorated()

        assert mock_func.call_count == 3

    def test_retry_network_no_retry_on_success(self):
        """Should not retry on first success."""
        mock_func = Mock(return_value="Success")

        decorated = retry_network_operation(max_attempts=5)(mock_func)
        result = decorated()

        assert result == "Success"
        assert mock_func.call_count == 1

    def test_retry_vmware_api(self):
        """VMware API retry should work."""
        mock_func = Mock(side_effect=[ConnectionError("Network error"), "Success"])
        mock_func.__name__ = "test_func"  # Mock needs __name__ attribute

        decorated = retry_vmware_api(max_attempts=3)(mock_func)
        result = decorated()

        assert result == "Success"
        assert mock_func.call_count == 2

    def test_retry_file_operation(self):
        """File operation retry should work."""
        mock_func = Mock(side_effect=[OSError("File locked"), "Success"])
        mock_func.__name__ = "test_func"  # Mock needs __name__ attribute

        decorated = retry_file_operation(max_attempts=3)(mock_func)
        result = decorated()

        assert result == "Success"
        assert mock_func.call_count == 2

    def test_retry_with_different_exceptions(self):
        """Should only retry on specified exceptions."""
        # OSError should be retried
        mock_func1 = Mock(side_effect=[OSError("Error"), "Success"])
        mock_func1.__name__ = "test_func1"  # Mock needs __name__ attribute
        decorated1 = retry_file_operation(max_attempts=3)(mock_func1)
        result1 = decorated1()
        assert result1 == "Success"

        # ValueError should not be retried
        mock_func2 = Mock(side_effect=ValueError("Not retryable"))
        mock_func2.__name__ = "test_func2"  # Mock needs __name__ attribute
        decorated2 = retry_file_operation(max_attempts=3)(mock_func2)

        with pytest.raises(ValueError):
            decorated2()

        assert mock_func2.call_count == 1  # No retry


class TestRetryContext:
    """Test retry context manager."""

    def test_retry_context_manager(self):
        """Retry context manager should work."""
        attempts = []

        with RetryContext(max_attempts=3, wait_time=0.01) as retry:
            for attempt in retry:
                attempts.append(attempt.number)
                if attempt.number == 2:
                    break  # Success on second attempt

        assert len(attempts) == 2
        assert attempts == [1, 2]

    def test_retry_context_all_attempts(self):
        """Retry context should allow all attempts."""
        attempts = []

        with RetryContext(max_attempts=3, wait_time=0.01) as retry:
            for attempt in retry:
                attempts.append(attempt.number)
                # Never break - use all attempts

        assert len(attempts) == 3
        assert attempts == [1, 2, 3]

    def test_retry_context_is_last_flag(self):
        """is_last flag should be set correctly."""
        last_flags = []

        with RetryContext(max_attempts=3, wait_time=0.01) as retry:
            for attempt in retry:
                last_flags.append(attempt.is_last)

        assert last_flags == [False, False, True]

    def test_retry_context_with_exception(self):
        """Retry context should handle exceptions."""
        attempts = []

        with pytest.raises(ValueError):
            with RetryContext(max_attempts=3, wait_time=0.01) as retry:
                for attempt in retry:
                    attempts.append(attempt.number)
                    if attempt.is_last:
                        raise ValueError("Final attempt failed")

        assert len(attempts) == 3


class TestRetryWaitTimes:
    """Test retry wait/backoff behavior."""

    def test_retry_respects_wait_time(self):
        """Retry should wait between attempts."""
        call_times = []

        def record_time():
            call_times.append(time.time())
            if len(call_times) < 2:
                raise ConnectionError("Fail")
            return "Success"

        decorated = retry_network_operation(max_attempts=3, min_wait=0.1)(record_time)
        decorated()

        # Should have at least 2 calls
        assert len(call_times) >= 2

        # There should be some delay between calls (at least 0.05s)
        if len(call_times) >= 2:
            delay = call_times[1] - call_times[0]
            assert delay >= 0.05  # Allow some tolerance


class TestTenacityAvailability:
    """Test tenacity availability detection."""

    def test_tenacity_flag_is_boolean(self):
        """TENACITY_AVAILABLE should be a boolean."""
        assert isinstance(TENACITY_AVAILABLE, bool)

    def test_retry_decorators_work_either_way(self):
        """Retry decorators should work with or without tenacity."""

        @retry_network_operation(max_attempts=2)
        def test_func():
            return "OK"

        result = test_func()
        assert result == "OK"


class TestRetryWithRealExceptions:
    """Test retry with real exception scenarios."""

    def test_connection_error_retry(self):
        """Should retry on ConnectionError."""
        attempt_count = [0]

        def flaky_connection():
            attempt_count[0] += 1
            if attempt_count[0] < 3:
                raise ConnectionError("Connection failed")
            return "Connected"

        decorated = retry_network_operation(max_attempts=5)(flaky_connection)
        result = decorated()

        assert result == "Connected"
        assert attempt_count[0] == 3

    def test_os_error_retry(self):
        """Should retry on OSError."""
        attempt_count = [0]

        def flaky_file_op():
            attempt_count[0] += 1
            if attempt_count[0] < 2:
                raise OSError("File busy")
            return "Success"

        decorated = retry_file_operation(max_attempts=3, wait_time=0.01)(flaky_file_op)
        result = decorated()

        assert result == "Success"
        assert attempt_count[0] == 2


class TestRetryAttempt:
    """Test RetryAttempt class."""

    def test_retry_attempt_repr(self):
        """RetryAttempt should have useful repr."""
        from hyper2kvm.core.retry_enhanced import RetryAttempt

        attempt = RetryAttempt(number=2, is_last=False)
        repr_str = repr(attempt)

        assert "2" in repr_str
        assert "False" in repr_str
