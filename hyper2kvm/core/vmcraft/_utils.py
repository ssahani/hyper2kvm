# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/vmcraft/_utils.py
"""
Shared utilities for VMCraft modules.

Provides common helper functions used across all VMCraft submodules.
"""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Any

from ..utils import U


# Custom Exception Classes


class VMCraftError(Exception):
    """Base exception for all VMCraft errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        """
        Initialize VMCraft error.

        Args:
            message: Error message
            context: Additional context information
        """
        super().__init__(message)
        self.context = context or {}

    def __str__(self) -> str:
        """Format error with context."""
        msg = super().__str__()
        if self.context:
            ctx_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{msg} ({ctx_str})"
        return msg


class MountError(VMCraftError):
    """Error during mount/unmount operations."""
    pass


class DeviceError(VMCraftError):
    """Error with device operations (NBD, LVM, etc.)."""
    pass


class FileSystemError(VMCraftError):
    """Error with filesystem operations."""
    pass


class RegistryError(VMCraftError):
    """Error with Windows registry operations."""
    pass


class DetectionError(VMCraftError):
    """Error during OS/component detection."""
    pass


class CacheError(VMCraftError):
    """Error with cache operations."""
    pass


# Retry logic


def retry_on_failure(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (subprocess.CalledProcessError, OSError)
) -> Any:
    """
    Decorator to retry function on failure.

    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay between attempts (seconds)
        backoff: Backoff multiplier for delay
        exceptions: Tuple of exceptions to catch

    Returns:
        Decorated function
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    # Don't sleep on last attempt
                    if attempt < max_attempts:
                        # Get logger if available
                        logger = None
                        if args and hasattr(args[0], 'logger'):
                            logger = args[0].logger
                        elif 'logger' in kwargs:
                            logger = kwargs['logger']

                        if logger:
                            logger.warning(
                                f"Attempt {attempt}/{max_attempts} failed: {e}. "
                                f"Retrying in {current_delay:.1f}s..."
                            )

                        time.sleep(current_delay)
                        current_delay *= backoff

            # All attempts failed
            raise last_exception

        return wrapper
    return decorator


def run_sudo(
    logger: logging.Logger,
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    retry: bool = False,
    max_retries: int = 3,
    failure_log_level: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """
    Run command with sudo and enhanced error handling.

    Uses simple pattern: prepend 'sudo' to command.
    For consistency with existing code patterns.

    Args:
        logger: Logger instance for output
        cmd: Command and arguments to execute
        check: Raise on non-zero exit (default: True)
        capture: Capture stdout/stderr (default: True)
        retry: Enable retry on failure (default: False)
        max_retries: Maximum retry attempts if retry=True (default: 3)
        failure_log_level: Log level for failures (default: ERROR, can be WARNING or DEBUG)

    Returns:
        CompletedProcess with command results

    Raises:
        DeviceError: If command fails and check=True

    Example:
        result = run_sudo(logger, ["mount", "/dev/sda1", "/mnt"], retry=True)
    """
    sudo_cmd = ["sudo", *cmd]

    try:
        if retry:
            # Use retry logic
            @retry_on_failure(max_attempts=max_retries)
            def _run_with_retry():
                return U.run_cmd(logger, sudo_cmd, check=check, capture=capture, failure_log_level=failure_log_level)

            return _run_with_retry()
        else:
            return U.run_cmd(logger, sudo_cmd, check=check, capture=capture, failure_log_level=failure_log_level)

    except subprocess.CalledProcessError as e:
        # Enhance error with context
        cmd_str = " ".join(sudo_cmd)
        context = {
            "command": cmd_str,
            "returncode": e.returncode,
            "stdout": e.stdout[:200] if e.stdout else None,  # Limit output
            "stderr": e.stderr[:200] if e.stderr else None,
        }

        if check:
            raise DeviceError(
                f"Command failed: {cmd_str}",
                context=context
            ) from e
        else:
            logger.debug(f"Command failed (check=False): {cmd_str}, rc={e.returncode}")
            # Return CompletedProcess even on failure when check=False
            return subprocess.CompletedProcess(
                args=sudo_cmd,
                returncode=e.returncode,
                stdout=e.stdout or "",
                stderr=e.stderr or ""
            )


def validate_path(path: str, must_exist: bool = False, must_be_file: bool = False, must_be_dir: bool = False) -> None:
    """
    Validate path with helpful error messages.

    Args:
        path: Path to validate
        must_exist: Path must exist
        must_be_file: Path must be a file
        must_be_dir: Path must be a directory

    Raises:
        FileSystemError: If validation fails
    """
    from pathlib import Path

    p = Path(path)

    if must_exist and not p.exists():
        raise FileSystemError(
            f"Path does not exist: {path}",
            context={"path": path, "absolute": str(p.absolute())}
        )

    if must_be_file and not p.is_file():
        raise FileSystemError(
            f"Path is not a file: {path}",
            context={"path": path, "exists": p.exists(), "is_dir": p.is_dir()}
        )

    if must_be_dir and not p.is_dir():
        raise FileSystemError(
            f"Path is not a directory: {path}",
            context={"path": path, "exists": p.exists(), "is_file": p.is_file()}
        )
