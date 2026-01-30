# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/file_ops.py
"""
Atomic file operation utilities.

Provides utilities for safe file operations including atomic writes with
temporary files and automatic cleanup.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def atomic_write(
    target_path: Path,
    *,
    mode: str = "wb",
    suffix: str = ".part",
    dir: Path | None = None,
    delete_on_error: bool = True,
) -> Generator[Path, None, None]:
    """
    Context manager for atomic file writes using temporary file + rename.

    Creates a temporary file, yields its path for writing, then atomically
    renames it to the target path on success. Cleans up temp file on failure.

    Args:
        target_path: Final destination path
        mode: File open mode (default: "wb" for binary write)
        suffix: Suffix for temporary file (default: ".part")
        dir: Directory for temp file (default: target_path.parent)
        delete_on_error: Delete temp file if exception occurs (default: True)

    Yields:
        Path to temporary file for writing

    Example:
        with atomic_write(Path("/output/file.vmdk")) as temp_path:
            # Write to temp_path
            with open(temp_path, "wb") as f:
                f.write(data)
        # Now /output/file.vmdk exists atomically

    Raises:
        Any exception from the context block (after cleanup)
    """
    target_path = Path(target_path)
    temp_dir = Path(dir) if dir else target_path.parent

    # Ensure parent directory exists
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Create temporary file in same directory as target (for atomic rename)
    fd, temp_name = tempfile.mkstemp(
        suffix=suffix,
        prefix=f".{target_path.name}.",
        dir=str(temp_dir),
    )
    temp_path = Path(temp_name)

    try:
        os.close(fd)  # Close the file descriptor (caller will open temp_path)
        yield temp_path

        # Success: atomically rename temp to target
        os.replace(temp_path, target_path)

    except Exception:
        # Failure: clean up temp file
        if delete_on_error:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass  # Best effort cleanup
        raise


def safe_unlink(path: Path, missing_ok: bool = True) -> None:
    """
    Safely delete a file, optionally ignoring if it doesn't exist.

    Args:
        path: Path to file to delete
        missing_ok: Don't raise error if file doesn't exist (default: True)

    Example:
        safe_unlink(Path("/tmp/tempfile.part"))
    """
    try:
        Path(path).unlink(missing_ok=missing_ok)
    except Exception:
        if not missing_ok:
            raise


def ensure_parent_dir(path: Path) -> None:
    """
    Ensure parent directory of a path exists, creating if necessary.

    Args:
        path: File path whose parent should exist

    Example:
        ensure_parent_dir(Path("/output/subdir/file.vmdk"))
        # Creates /output/subdir/ if it doesn't exist
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
