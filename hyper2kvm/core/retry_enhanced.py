# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/retry_enhanced.py
"""
Enhanced retry utilities with optional tenacity support.

Uses tenacity if available (for advanced features), falls back to
existing retry.py implementation for RHEL 10 compatibility.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from .optional_imports import TENACITY_AVAILABLE

# Import based on availability
if TENACITY_AVAILABLE:
    from .optional_imports import (
        retry as tenacity_retry,
        stop_after_attempt,
        wait_exponential,
        wait_fixed,
        retry_if_exception_type,
        before_sleep_log,
        RetryError,
    )

# Always import our fallback
from .retry import retry_with_backoff as stdlib_retry

T = TypeVar("T")

logger = logging.getLogger(__name__)


def retry_network_operation(
    max_attempts: int = 5,
    min_wait: float = 2.0,
    max_wait: float = 30.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Retry decorator for network operations.

    Uses tenacity if available, otherwise falls back to stdlib implementation.

    Args:
        max_attempts: Maximum number of retry attempts
        min_wait: Minimum wait time between retries (seconds)
        max_wait: Maximum wait time between retries (seconds)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_network_operation(max_attempts=3)
        def download_file(url):
            response = requests.get(url)
            response.raise_for_status()
            return response.content
    """
    # Network-related exceptions
    try:
        from requests.exceptions import RequestException, ConnectionError, Timeout

        exceptions = (RequestException, ConnectionError, Timeout, OSError)
    except ImportError:
        # requests not available, just use OSError
        exceptions = (OSError, ConnectionError, TimeoutError)  # type: ignore

    if TENACITY_AVAILABLE:
        # Use tenacity for advanced retry logic
        return tenacity_retry(  # type: ignore
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            retry=retry_if_exception_type(exceptions),
            before_sleep=before_sleep_log(logger, logging.WARNING),
        )
    else:
        # Fall back to stdlib implementation
        return stdlib_retry(
            max_attempts=max_attempts,
            base_backoff_s=min_wait,
            max_backoff_s=max_wait,
            exceptions=exceptions,
            logger=logger,
        )


def retry_vmware_api(
    max_attempts: int = 3,
    min_wait: float = 4.0,
    max_wait: float = 10.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Retry decorator for VMware API calls.

    Args:
        max_attempts: Maximum number of retry attempts
        min_wait: Minimum wait time between retries (seconds)
        max_wait: Maximum wait time between retries (seconds)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_vmware_api(max_attempts=3)
        def get_vm_info(vm_name):
            return vmware_client.get_vm_by_name(vm_name)
    """
    from .optional_imports import PYVMOMI_AVAILABLE

    if PYVMOMI_AVAILABLE:
        from .optional_imports import vim

        exceptions = (vim.fault.NotAuthenticated, ConnectionError, OSError)  # type: ignore
    else:
        exceptions = (ConnectionError, OSError)

    if TENACITY_AVAILABLE:
        return tenacity_retry(  # type: ignore
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=2, min=min_wait, max=max_wait),
            retry=retry_if_exception_type(exceptions),
            before_sleep=before_sleep_log(logger, logging.WARNING),
        )
    else:
        return stdlib_retry(
            max_attempts=max_attempts,
            base_backoff_s=min_wait,
            max_backoff_s=max_wait,
            exceptions=exceptions,
            logger=logger,
        )


def retry_file_operation(
    max_attempts: int = 3,
    wait_time: float = 1.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Retry decorator for file operations.

    Args:
        max_attempts: Maximum number of retry attempts
        wait_time: Fixed wait time between retries (seconds)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_file_operation(max_attempts=3)
        def write_file(path, content):
            with open(path, 'w') as f:
                f.write(content)
    """
    exceptions = (OSError, IOError)

    if TENACITY_AVAILABLE:
        return tenacity_retry(  # type: ignore
            stop=stop_after_attempt(max_attempts),
            wait=wait_fixed(wait_time),
            retry=retry_if_exception_type(exceptions),
            before_sleep=before_sleep_log(logger, logging.ERROR),
        )
    else:
        return stdlib_retry(
            max_attempts=max_attempts,
            base_backoff_s=wait_time,
            max_backoff_s=wait_time,  # Fixed wait
            jitter_s=0.0,  # No jitter for file ops
            exceptions=exceptions,
            logger=logger,
        )


# Context manager for retry (works with either implementation)
class RetryContext:
    """
    Context manager for retry logic.

    Example:
        with RetryContext(max_attempts=3) as retry:
            for attempt in retry:
                try:
                    result = risky_operation()
                    break  # Success
                except Exception as e:
                    if attempt.is_last:
                        raise
                    logger.warning(f"Attempt {attempt.number} failed: {e}")
    """

    def __init__(
        self,
        max_attempts: int = 3,
        wait_time: float = 2.0,
        exceptions: tuple[type[Exception], ...] = (Exception,),
    ):
        self.max_attempts = max_attempts
        self.wait_time = wait_time
        self.exceptions = exceptions
        self.current_attempt = 0

    def __enter__(self) -> RetryContext:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def __iter__(self):
        """Iterate through retry attempts."""
        for i in range(1, self.max_attempts + 1):
            self.current_attempt = i
            yield RetryAttempt(i, i == self.max_attempts)
            if i < self.max_attempts:
                import time

                time.sleep(self.wait_time)


class RetryAttempt:
    """Represents a single retry attempt."""

    def __init__(self, number: int, is_last: bool):
        self.number = number
        self.is_last = is_last

    def __repr__(self) -> str:
        return f"RetryAttempt(number={self.number}, is_last={self.is_last})"
