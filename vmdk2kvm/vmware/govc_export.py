# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# vmdk2kvm/vsphere/govc_export.py
from __future__ import annotations

"""
govc export workflow wrapper.

Single source of truth for:
  - CD/DVD removal before export
  - VM shutdown/power-off policy
  - Progress reporting (PTY + Rich if available)
  - Output directory cleanup
  - OVA packaging (when mode='ova')

Design: callers pass a GovcExportSpec; this module runs the workflow.
"""

import os
import sys
import time
import shutil
import tarfile
import logging
import tempfile
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List

from ..core.exceptions import VMwareError

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    from rich.text import Text

    RICH_AVAILABLE = True
except Exception:  # pragma: no cover
    Console = None  # type: ignore
    Progress = None  # type: ignore
    SpinnerColumn = None  # type: ignore
    TextColumn = None  # type: ignore
    TimeElapsedColumn = None  # type: ignore
    Text = None  # type: ignore
    RICH_AVAILABLE = False


@dataclass
class GovcExportSpec:
    """All parameters needed for a govc export operation."""
    vm: str
    outdir: Path
    mode: str  # "ovf" or "ova"

    # govc configuration
    govc_bin: str = "govc"
    env: Optional[Dict[str, str]] = None

    # VM preparation
    remove_cdroms: bool = True
    show_vm_info: bool = True
    shutdown: bool = False
    shutdown_timeout_s: float = 300.0
    shutdown_poll_s: float = 5.0
    power_off: bool = False

    # Output handling
    clean_outdir: bool = False
    ova_filename: Optional[str] = None  # only for mode="ova"

    # Progress/UI
    show_progress: bool = True
    prefer_pty: bool = True


class GovcExportError(VMwareError):
    """Specialized error for govc export failures."""
    pass


def _log(logger: Any, level: str, msg: str, *args: Any) -> None:
    """Safe logging wrapper."""
    try:
        getattr(logger, level)(msg % args if args else msg)
    except Exception:
        print(f"[{level.upper()}] {msg % args if args else msg}")


def _is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _run_govc_with_rich(
    cmd: List[str],
    env: Dict[str, str],
    logger: Any,
    *,
    title: str = "govc running",
) -> subprocess.CompletedProcess:
    """
    Run govc while showing a Rich spinner + elapsed time.

    We *also* tail the last non-empty line from govc output (best-effort) and show it in the UI.
    This is intentionally robust and low-assumption (govc output formats vary).

    Returns CompletedProcess on success. Raises GovcExportError on failure.
    """
    full_env = dict(os.environ)
    full_env.update(env)

    if not (RICH_AVAILABLE and _is_tty()):
        # Fallback: capture output
        return _run_govc_simple(cmd, env, logger, capture_output=True)

    console = Console(stderr=False)

    # We capture output so we can:
    # - show a simple progress spinner
    # - include useful context in exceptions
    # - still not rely on govc's TTY progress
    proc = subprocess.Popen(
        cmd,
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    output_lines: List[str] = []
    last_line: str = ""

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task_id = progress.add_task(title, total=None)

            # Stream output while process runs
            assert proc.stdout is not None
            while True:
                line = proc.stdout.readline()
                if line:
                    s = line.rstrip("\n")
                    output_lines.append(s)
                    if s.strip():
                        last_line = s.strip()
                        # keep it short to avoid UI spam
                        shown = last_line
                        if len(shown) > 140:
                            shown = shown[:140] + "…"
                        progress.update(task_id, description=f"{title} • {shown}")
                else:
                    if proc.poll() is not None:
                        break
                    time.sleep(0.05)

        rc = proc.wait()
        stdout = "\n".join(output_lines).strip()

        if rc != 0:
            tail = "\n".join(output_lines[-30:]).strip()
            msg = f"govc failed with exit code {rc}"
            if tail:
                msg += f":\n{tail}"
            raise GovcExportError(msg)

        return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr="")

    except GovcExportError:
        raise
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        tail = "\n".join(output_lines[-30:]).strip()
        msg = f"Failed to run govc: {e}"
        if tail:
            msg += f"\nLast output:\n{tail}"
        raise GovcExportError(msg) from e


def _run_govc_with_pty(
    cmd: List[str],
    env: Dict[str, str],
    logger: Any,
    show_progress: bool = True,
) -> bool:
    """
    Run govc command with PTY-ish behavior for proper progress display.

    Notes:
    - govc itself often prints a progress bar only when attached to a TTY.
    - If Rich is available AND we're in a TTY, we prefer a Rich spinner UI
      (more consistent across environments), and still stream output for errors.
    - Otherwise, we run govc directly in TTY mode (so govc can do its own progress),
      or capture output in non-TTY mode.

    Returns True if successful, raises GovcExportError otherwise.
    """
    full_env = dict(os.environ)
    full_env.update(env)

    _log(logger, "debug", "Running govc: %s", " ".join(cmd))

    try:
        # If we can do Rich, do Rich. It's cleaner than fighting with PTY details.
        if show_progress and RICH_AVAILABLE and _is_tty():
            _run_govc_with_rich(cmd, env, logger, title="Exporting via govc")
            return True

        # Otherwise: let govc render its own TTY progress if we have a TTY.
        if show_progress and _is_tty():
            result = subprocess.run(
                cmd,
                env=full_env,
                check=True,
            )
            return result.returncode == 0

        # Non-TTY: capture output
        result = subprocess.run(
            cmd,
            env=full_env,
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stdout:
            _log(logger, "info", result.stdout.strip())
        return True

    except subprocess.CalledProcessError as e:
        error_msg = f"govc failed with exit code {e.returncode}"
        stderr = ""
        try:
            stderr = (e.stderr or "").strip()
        except Exception:
            stderr = ""
        if stderr:
            error_msg += f": {stderr[:500]}"
        raise GovcExportError(error_msg) from e
    except Exception as e:
        raise GovcExportError(f"Failed to run govc: {e}") from e


def _run_govc_simple(
    cmd: List[str],
    env: Dict[str, str],
    logger: Any,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    """Simple govc runner without PTY."""
    full_env = dict(os.environ)
    full_env.update(env)

    _log(logger, "debug", "Running govc: %s", " ".join(cmd))

    try:
        return subprocess.run(
            cmd,
            env=full_env,
            capture_output=capture_output,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        error_msg = f"govc failed with exit code {e.returncode}"
        if e.stderr:
            error_msg += f": {e.stderr.strip()[:500]}"
        raise GovcExportError(error_msg) from e


def _remove_cdrom_devices(spec: GovcExportSpec, logger: Any) -> None:
    """Remove CD/DVD devices from VM before export."""
    if not spec.remove_cdroms:
        return

    try:
        _log(logger, "info", "Removing CD/DVD devices...")

        # List all devices
        result = _run_govc_simple(
            [spec.govc_bin, "device.ls", "-vm", spec.vm],
            spec.env or {},
            logger,
        )

        cdroms = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if "cdrom" in line.lower() and line:
                parts = line.split()
                if parts:
                    cdroms.append(parts[0])

        if not cdroms:
            _log(logger, "debug", "No CD/DVD devices found")
            return

        for device in cdroms:
            _log(logger, "debug", "  Removing device: %s", device)
            try:
                _run_govc_simple(
                    [spec.govc_bin, "device.remove", "-vm", spec.vm, device],
                    spec.env or {},
                    logger,
                    capture_output=False,
                )
            except Exception as e:
                _log(logger, "warning", "Failed to remove device %s: %s", device, e)
                # Try eject as fallback
                try:
                    _run_govc_simple(
                        [spec.govc_bin, "device.cdrom.eject", "-vm", spec.vm],
                        spec.env or {},
                        logger,
                        capture_output=False,
                    )
                except Exception:
                    pass

    except Exception as e:
        _log(logger, "warning", "CD/DVD removal failed (continuing): %s", e)


def _show_vm_info(spec: GovcExportSpec, logger: Any) -> None:
    """Display VM information before export."""
    if not spec.show_vm_info:
        return

    try:
        _log(logger, "info", "VM Information:")
        result = _run_govc_simple(
            [spec.govc_bin, "vm.info", spec.vm],
            spec.env or {},
            logger,
        )

        # Parse and display key info
        info_lines = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and any(
                keyword in line.lower()
                for keyword in ["name:", "power state:", "storage:", "path:", "guest os:", "memory:", "cpu:"]
            ):
                info_lines.append(f"  {line}")

        if info_lines:
            for line in info_lines:
                _log(logger, "info", line)
        else:
            _log(logger, "info", "  (No detailed info available)")

    except Exception as e:
        _log(logger, "debug", "Could not get VM info: %s", e)


def _prepare_vm_power_state(spec: GovcExportSpec, logger: Any) -> None:
    """Handle VM power state (shutdown/power off) before export."""
    if spec.shutdown:
        _log(logger, "info", "Shutting down VM (graceful)...")
        try:
            _run_govc_simple(
                [spec.govc_bin, "vm.power", "-s", spec.vm],
                spec.env or {},
                logger,
                capture_output=False,
            )

            # Wait for shutdown
            start_time = time.time()
            while time.time() - start_time < spec.shutdown_timeout_s:
                try:
                    result = _run_govc_simple(
                        [spec.govc_bin, "vm.info", spec.vm],
                        spec.env or {},
                        logger,
                    )
                    if "poweredOff" in result.stdout:
                        _log(logger, "info", "VM is now powered off")
                        return
                except Exception:
                    pass  # VM might be in transition

                time.sleep(spec.shutdown_poll_s)

            _log(logger, "warning", "VM shutdown timeout exceeded")

        except Exception as e:
            _log(logger, "warning", "Shutdown failed: %s", e)

    elif spec.power_off:
        _log(logger, "info", "Powering off VM...")
        try:
            _run_govc_simple(
                [spec.govc_bin, "vm.power", "-off", spec.vm],
                spec.env or {},
                logger,
                capture_output=False,
            )
        except Exception as e:
            _log(logger, "warning", "Power off failed: %s", e)


def _create_ova_from_ovf(ovf_dir: Path, ova_file: Path, logger: Any) -> None:
    """Create OVA file from OVF directory."""
    _log(logger, "info", "Creating OVA archive from OVF files...")

    try:
        # List files being added
        files = list(ovf_dir.rglob("*"))
        _log(logger, "debug", "Found %d files in OVF directory", len(files))

        with tarfile.open(ova_file, "w") as tar:
            for file_path in files:
                if file_path.is_file():
                    arcname = file_path.relative_to(ovf_dir.parent)
                    tar.add(file_path, arcname=arcname)
                    _log(logger, "debug", "  Added: ./%s", arcname)

        # Verify the OVA was created
        if ova_file.exists():
            size_bytes = ova_file.stat().st_size
            size_mb = size_bytes / (1024 * 1024)
            size_gb = size_bytes / (1024 * 1024 * 1024)

            if size_gb >= 1:
                _log(logger, "info", "OVA created: %s (%.2f GB)", ova_file.name, size_gb)
            else:
                _log(logger, "info", "OVA created: %s (%.2f MB)", ova_file.name, size_mb)
        else:
            raise GovcExportError("OVA file was not created after tar creation")

    except Exception as e:
        raise GovcExportError(f"Failed to create OVA: {e}") from e


def _clean_output_directory(outdir: Path, logger: Any) -> None:
    """Clean output directory before export."""
    if outdir.exists():
        _log(logger, "info", "Cleaning output directory: %s", outdir)
        try:
            # Remove all files and subdirectories
            for item in outdir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            _log(logger, "debug", "Output directory cleaned")
        except Exception as e:
            _log(logger, "warning", "Failed to clean output directory: %s", e)


def export_vm_govc(logger: Any, spec: GovcExportSpec) -> None:
    """
    Main export workflow.

    Steps:
    1. Show VM info (optional)
    2. Remove CD/DVD devices (optional)
    3. Handle VM power state (optional)
    4. Clean output directory (optional)
    5. Run govc export
    6. Package OVA if mode='ova'
    """
    # Validate inputs
    if spec.mode not in ("ovf", "ova"):
        raise GovcExportError(f"Invalid export mode: {spec.mode}. Must be 'ovf' or 'ova'")

    # Set default OVA filename if not provided
    if spec.mode == "ova" and not spec.ova_filename:
        spec.ova_filename = f"{spec.vm}.ova"

    # Create output directory
    spec.outdir.mkdir(parents=True, exist_ok=True)

    # Clean output directory if requested
    if spec.clean_outdir:
        _clean_output_directory(spec.outdir, logger)

    # Show VM info
    _show_vm_info(spec, logger)

    # Remove CD/DVD devices
    _remove_cdrom_devices(spec, logger)

    # Handle power state
    _prepare_vm_power_state(spec, logger)

    # Run export
    _log(logger, "info", "\nStarting %s export...", spec.mode.upper())
    _log(logger, "info", "This may take several minutes depending on disk size...")

    start_time = time.time()

    if spec.mode == "ovf":
        # Export to OVF
        export_cmd = [spec.govc_bin, "export.ovf", "-vm", spec.vm, str(spec.outdir)]

        try:
            success = _run_govc_with_pty(
                export_cmd,
                spec.env or {},
                logger,
                show_progress=spec.show_progress,
            )

            if not success:
                raise GovcExportError("OVF export failed")

            # Find the created OVF directory
            ovf_dir = None
            for item in spec.outdir.iterdir():
                if item.is_dir() and spec.vm in item.name:
                    ovf_dir = item
                    break

            if not ovf_dir:
                # Try to find any directory
                for item in spec.outdir.iterdir():
                    if item.is_dir():
                        ovf_dir = item
                        break

            if ovf_dir:
                elapsed = time.time() - start_time
                minutes = int(elapsed // 60)
                seconds = int(elapsed % 60)
                _log(logger, "info", "\nOVF export completed in %dm %ds: %s", minutes, seconds, ovf_dir)
            else:
                _log(logger, "warning", "Could not find OVF directory after export")
                _log(logger, "info", "Contents of output directory:")
                for item in spec.outdir.iterdir():
                    _log(logger, "info", "  %s", item.name)

        except Exception as e:
            elapsed = time.time() - start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            raise GovcExportError(f"OVF export failed after {minutes}m {seconds}s: {e}") from e

    elif spec.mode == "ova":
        # For OVA mode, we need to export to a temp directory first
        with tempfile.TemporaryDirectory(prefix=f"govc_export_{spec.vm}_") as tmpdir:
            tmp_path = Path(tmpdir)

            _log(logger, "info", "Exporting to temporary directory: %s", tmp_path)

            # Export to OVF in temp directory
            export_cmd = [spec.govc_bin, "export.ovf", "-vm", spec.vm, str(tmp_path)]

            try:
                success = _run_govc_with_pty(
                    export_cmd,
                    spec.env or {},
                    logger,
                    show_progress=spec.show_progress,
                )

                if not success:
                    raise GovcExportError("OVF export to temp directory failed")

                # Find the OVF directory in temp location
                ovf_dir = None
                for item in tmp_path.iterdir():
                    if item.is_dir() and spec.vm in item.name:
                        ovf_dir = item
                        break

                if not ovf_dir:
                    # Try to find any directory
                    for item in tmp_path.iterdir():
                        if item.is_dir():
                            ovf_dir = item
                            break

                if not ovf_dir:
                    raise GovcExportError(f"Could not find OVF directory in temp location: {tmp_path}")

                _log(logger, "info", "Found OVF directory: %s", ovf_dir.name)

                # Create OVA file from OVF directory
                ova_file = spec.outdir / spec.ova_filename
                _create_ova_from_ovf(ovf_dir, ova_file, logger)

                elapsed = time.time() - start_time
                minutes = int(elapsed // 60)
                seconds = int(elapsed % 60)
                _log(logger, "info", "\nOVA export completed in %dm %ds: %s", minutes, seconds, ova_file)

            except Exception as e:
                elapsed = time.time() - start_time
                minutes = int(elapsed // 60)
                seconds = int(elapsed % 60)
                raise GovcExportError(f"OVA export failed after {minutes}m {seconds}s: {e}") from e

    _log(logger, "info", "\nExport completed successfully!")
