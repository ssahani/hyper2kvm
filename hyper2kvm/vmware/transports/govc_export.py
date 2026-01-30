# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/vmware/transports/govc_export.py
from __future__ import annotations

"""
govc export workflow wrapper.

Single source of truth for:
  - CD/DVD removal before export
  - VM shutdown/power-off policy
  - Progress reporting (TTY + Rich if available)
  - Output directory cleanup
  - OVA packaging (when mode='ova')

Design: callers pass a GovcExportSpec; this module runs the workflow.
"""

import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core.exceptions import VMwareError
from ..utils.utils import is_tty as _is_tty

try:  # pragma: no cover
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
        TransferSpeedColumn,
    )
    from rich.text import Text

    RICH_AVAILABLE = True
except Exception:  # pragma: no cover
    Console = None  # type: ignore
    Panel = None  # type: ignore
    Progress = None  # type: ignore
    SpinnerColumn = None  # type: ignore
    BarColumn = None  # type: ignore
    TextColumn = None  # type: ignore
    TimeElapsedColumn = None  # type: ignore
    TransferSpeedColumn = None  # type: ignore
    TaskProgressColumn = None  # type: ignore
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
    env: dict[str, str] | None = None

    # VM preparation
    remove_cdroms: bool = True
    show_vm_info: bool = True
    shutdown: bool = False
    shutdown_timeout_s: float = 300.0
    shutdown_poll_s: float = 5.0
    power_off: bool = False

    # Output handling
    clean_outdir: bool = False
    ova_filename: str | None = None  # only for mode="ova"

    # Progress/UI
    show_progress: bool = True
    prefer_pty: bool = True


class GovcExportError(VMwareError):
    """Specialized error for govc export failures."""


# UI helpers (Rich if possible, otherwise plain prints)
def _console(logger: Any) -> Any | None:
    """Create Rich Console if available and running in TTY. Logger param kept for API compat."""
    if not (RICH_AVAILABLE and _is_tty()):
        return None
    try:
        return Console(stderr=False)
    except Exception:
        return None


def _print_panel(logger: Any, title: str, body: str = "") -> None:
    con = _console(logger)
    if con and Panel:
        con.print(Panel(body, title=title, expand=True))
        return

    # Plain fallback (keeps the “boxy” vibe)
    line = "─" * max(57, len(title) + 10)
    print(f"╭{line}╮")
    t = title[: max(0, len(line) - 2)]
    print(f"│ {t:<{len(line)-2}} │")
    if body.strip():
        for bl in body.splitlines():
            print(f"│ {bl:<{len(line)-2}} │")
    print(f"╰{line}╯")


def _info(logger: Any, msg: str) -> None:
    try:
        logger.info(msg)
    except Exception:
        print(msg)


def _debug(logger: Any, msg: str) -> None:
    try:
        logger.debug(msg)
    except Exception:
        pass


def _warn(logger: Any, msg: str) -> None:
    try:
        logger.warning(msg)
    except Exception:
        print(f"WARNING: {msg}")


def _ok_line(logger: Any, msg: str) -> None:
    # Prefer printing a clean check line (matches your sample).
    _info(logger, f" ✓ {msg}")


# govc runners
def _run_govc_simple(
    cmd: list[str],
    env: dict[str, str],
    logger: Any,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    """Simple govc runner without PTY."""
    full_env = dict(os.environ)
    full_env.update(env)

    _debug(logger, "Running govc: {}".format(" ".join(cmd)))

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
        if getattr(e, "stderr", None):
            error_msg += f": {(e.stderr or '').strip()[:800]}"
        raise GovcExportError(error_msg) from e
    except Exception as e:
        raise GovcExportError(f"Failed to run govc: {e}") from e


def _run_govc_with_rich_spinner(
    cmd: list[str],
    env: dict[str, str],
    logger: Any,
    *,
    title: str,
) -> subprocess.CompletedProcess:
    """
    Run govc while showing a Rich spinner + elapsed time and tailing last line.
    """
    full_env = dict(os.environ)
    full_env.update(env)

    con = _console(logger)
    if not (con and Progress and SpinnerColumn and TextColumn and TimeElapsedColumn):
        return _run_govc_simple(cmd, env, logger, capture_output=True)

    proc = subprocess.Popen(
        cmd,
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    output_lines: list[str] = []
    last_line: str = ""

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=con,
            transient=True,
        ) as progress:
            task_id = progress.add_task(title, total=None)

            if proc.stdout is None:
                raise RuntimeError("Process stdout unexpectedly None")
            while True:
                line = proc.stdout.readline()
                if line:
                    s = line.rstrip("\n")
                    output_lines.append(s)
                    if s.strip():
                        last_line = s.strip()
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
            tail = "\n".join(output_lines[-40:]).strip()
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
        tail = "\n".join(output_lines[-40:]).strip()
        msg = f"Failed to run govc: {e}"
        if tail:
            msg += f"\nLast output:\n{tail}"
        raise GovcExportError(msg) from e


def _run_govc_with_tty_passthrough(
    cmd: list[str],
    env: dict[str, str],
    logger: Any,
) -> None:
    """
    Let govc draw its own progress (best when attached to a real TTY).
    """
    full_env = dict(os.environ)
    full_env.update(env)

    _debug(logger, "Running govc (TTY passthrough): {}".format(" ".join(cmd)))

    try:
        subprocess.run(cmd, env=full_env, check=True)
    except subprocess.CalledProcessError as e:
        raise GovcExportError(f"govc failed with exit code {e.returncode}") from e
    except Exception as e:
        raise GovcExportError(f"Failed to run govc: {e}") from e


def _run_govc_export(
    cmd: list[str],
    env: dict[str, str],
    logger: Any,
    *,
    show_progress: bool,
    prefer_pty: bool,
    title: str,
) -> None:
    """
    Policy:
      - If not showing progress: capture output (best error context)
      - If showing progress and in TTY:
          - If Rich available: show spinner + tail (consistent UI)
          - Else: passthrough to govc so it can render its own bar
      - If not in TTY: capture output
    """
    if not show_progress:
        _run_govc_simple(cmd, env, logger, capture_output=True)
        return

    if _is_tty():
        if RICH_AVAILABLE:
            _run_govc_with_rich_spinner(cmd, env, logger, title=title)
            return
        if prefer_pty:
            _run_govc_with_tty_passthrough(cmd, env, logger)
            return

    _run_govc_simple(cmd, env, logger, capture_output=True)


# VM prep helpers
def _remove_cdrom_devices(spec: GovcExportSpec, logger: Any) -> list[str]:
    """Remove CD/DVD devices from VM before export. Returns removed device names."""
    removed: list[str] = []
    if not spec.remove_cdroms:
        return removed

    _info(logger, "Removing CD/DVD devices...")

    try:
        result = _run_govc_simple(
            [spec.govc_bin, "device.ls", "-vm", spec.vm],
            spec.env or {},
            logger,
        )

        cdroms: list[str] = []
        for line in (result.stdout or "").splitlines():
            s = line.strip()
            if s and "cdrom" in s.lower():
                parts = s.split()
                if parts:
                    cdroms.append(parts[0])

        if not cdroms:
            _debug(logger, "No CD/DVD devices found")
            return removed

        for dev in cdroms:
            try:
                _run_govc_simple(
                    [spec.govc_bin, "device.remove", "-vm", spec.vm, dev],
                    spec.env or {},
                    logger,
                    capture_output=False,
                )
                removed.append(dev)
                _ok_line(logger, f"Removed: {dev}")
            except Exception as e:
                _warn(logger, f"Failed to remove device {dev}: {e} (trying eject)")
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
        _warn(logger, f"CD/DVD removal failed (continuing): {e}")

    return removed


def _get_vm_info_lines(spec: GovcExportSpec, logger: Any) -> list[str]:
    """
    Extract a few useful vm.info lines and return them for printing in a panel.
    """
    try:
        result = _run_govc_simple(
            [spec.govc_bin, "vm.info", spec.vm],
            spec.env or {},
            logger,
        )
    except Exception as e:
        _debug(logger, f"Could not get VM info: {e}")
        return []

    want = ("name:", "power state:", "storage:", "path:", "guest os:", "memory:", "cpu:")
    out: list[str] = []
    for line in (result.stdout or "").splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if any(k in low for k in want):
            out.append(s)
    return out


def _show_vm_info(spec: GovcExportSpec, logger: Any) -> None:
    if not spec.show_vm_info:
        return

    title = f"VM Information: {spec.vm}"
    lines = _get_vm_info_lines(spec, logger)

    if not lines:
        _print_panel(logger, title, "(No detailed info available)")
        return

    body = "\n".join([f" {ln}" for ln in lines])
    _print_panel(logger, title, body)


def _prepare_vm_power_state(spec: GovcExportSpec, logger: Any) -> None:
    """Handle VM power state (shutdown/power off) before export."""
    if spec.shutdown:
        _info(logger, "Shutting down VM (graceful)...")
        try:
            _run_govc_simple(
                [spec.govc_bin, "vm.power", "-s", spec.vm],
                spec.env or {},
                logger,
                capture_output=False,
            )

            start_time = time.time()
            while time.time() - start_time < spec.shutdown_timeout_s:
                try:
                    result = _run_govc_simple(
                        [spec.govc_bin, "vm.info", spec.vm],
                        spec.env or {},
                        logger,
                    )
                    if "poweredOff" in (result.stdout or ""):
                        _ok_line(logger, "VM is now powered off")
                        return
                except Exception:
                    pass
                time.sleep(spec.shutdown_poll_s)

            _warn(logger, "VM shutdown timeout exceeded")
        except Exception as e:
            _warn(logger, f"Shutdown failed: {e}")

    elif spec.power_off:
        _info(logger, "Powering off VM...")
        try:
            _run_govc_simple(
                [spec.govc_bin, "vm.power", "-off", spec.vm],
                spec.env or {},
                logger,
                capture_output=False,
            )
            _ok_line(logger, "VM powered off")
        except Exception as e:
            _warn(logger, f"Power off failed: {e}")


# Output helpers
def _clean_output_directory(outdir: Path, logger: Any) -> None:
    if outdir.exists():
        _info(logger, f"Cleaning output directory: {outdir}")
        try:
            for item in outdir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            _debug(logger, "Output directory cleaned")
        except Exception as e:
            _warn(logger, f"Failed to clean output directory: {e}")


def _create_ova_from_ovf(ovf_dir: Path, ova_file: Path, logger: Any) -> None:
    """
    Create OVA file from OVF directory.

    Note: OVA is a TAR archive containing the OVF descriptor + disks + manifest.
    """
    _info(logger, "Creating OVA archive from OVF files...")

    files = [p for p in ovf_dir.rglob("*") if p.is_file()]
    if not files:
        raise GovcExportError(f"No files found under OVF directory: {ovf_dir}")

    con = _console(logger)
    use_rich = bool(con and Progress and BarColumn and TextColumn and TimeElapsedColumn and TaskProgressColumn)

    try:
        if use_rich:
            with Progress(
                TextColumn("▌ [progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                console=con,
                transient=True,
            ) as progress:
                task = progress.add_task("Packaging OVA files...", total=len(files))

                with tarfile.open(ova_file, "w") as tar:
                    for fp in files:
                        # Keep the exported folder name inside the tar (common OVA layout)
                        arcname = fp.relative_to(ovf_dir.parent)
                        tar.add(fp, arcname=arcname)
                        # Show a friendly “Adding:” line occasionally
                        progress.update(task, advance=1, description=f"Packaging OVA files... ({progress.tasks[0].completed+1:.0f}/{len(files)})")
        else:
            with tarfile.open(ova_file, "w") as tar:
                for fp in files:
                    arcname = fp.relative_to(ovf_dir.parent)
                    tar.add(fp, arcname=arcname)

        if not ova_file.exists():
            raise GovcExportError("OVA file was not created after tar creation")

        size_bytes = ova_file.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        size_gb = size_bytes / (1024 * 1024 * 1024)
        if size_gb >= 1:
            _ok_line(logger, f"OVA created: {ova_file} ({size_gb:.2f} GB)")
        else:
            _ok_line(logger, f"OVA created: {ova_file} ({size_mb:.2f} MB)")

    except Exception as e:
        raise GovcExportError(f"Failed to create OVA: {e}") from e


def _find_exported_ovf_dir(parent: Path, vm_name: str) -> Path | None:
    """
    govc export.ovf typically creates a subdir named after the VM.
    We try best-effort discovery.
    """
    if not parent.exists():
        return None
    # Prefer directory containing vm_name
    for item in parent.iterdir():
        if item.is_dir() and vm_name in item.name:
            return item
    # Otherwise first directory
    for item in parent.iterdir():
        if item.is_dir():
            return item
    return None


def _fmt_elapsed(start_time: float) -> tuple[int, int]:
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    return minutes, seconds


# Public entrypoint
def export_vm_govc(logger: Any, spec: GovcExportSpec) -> None:
    """
    Main export workflow.

    Steps:
    1. Banner
    2. Show VM info (optional)
    3. Remove CD/DVD devices (optional)
    4. Handle VM power state (optional)
    5. Clean output directory (optional)
    6. Run govc export.ovf
    7. Package OVA if mode='ova'
    8. Success panel
    """
    if spec.mode not in ("ovf", "ova"):
        raise GovcExportError(f"Invalid export mode: {spec.mode}. Must be 'ovf' or 'ova'")

    if spec.mode == "ova" and not spec.ova_filename:
        spec.ova_filename = f"{spec.vm}.ova"

    spec.outdir.mkdir(parents=True, exist_ok=True)
    if spec.clean_outdir:
        _clean_output_directory(spec.outdir, logger)

    # Banner (matches your sample vibe)
    banner_body = f"Mode: {spec.mode.upper()} | Output: {spec.outdir}"
    _print_panel(logger, f"Exporting VM: {spec.vm}", banner_body)

    # VM info panel
    _show_vm_info(spec, logger)

    # Remove CD/DVD devices
    _remove_cdrom_devices(spec, logger)

    # Handle power state
    _prepare_vm_power_state(spec, logger)

    # Start export
    _info(logger, f"\nStarting {spec.mode.upper()} export...")
    _info(logger, "This may take several minutes depending on disk size...\n")

    start_time = time.time()

    if spec.mode == "ovf":
        export_cmd = [spec.govc_bin, "export.ovf", "-vm", spec.vm, str(spec.outdir)]
        try:
            _run_govc_export(
                export_cmd,
                spec.env or {},
                logger,
                show_progress=spec.show_progress,
                prefer_pty=spec.prefer_pty,
                title="Exporting OVF...",
            )
        except Exception as e:
            m, s = _fmt_elapsed(start_time)
            raise GovcExportError(f"OVF export failed after {m}m {s}s: {e}") from e

        ovf_dir = _find_exported_ovf_dir(spec.outdir, spec.vm)
        m, s = _fmt_elapsed(start_time)
        if ovf_dir:
            _ok_line(logger, f"OVF export completed in {m}m {s}s")
            _info(logger, f"Output: {ovf_dir}")
        else:
            _warn(logger, "Could not find OVF directory after export")
            try:
                _info(logger, "Contents of output directory:")
                for item in spec.outdir.iterdir():
                    _info(logger, f" {item.name}")
            except Exception:
                pass

        _print_panel(logger, "✓ Export completed successfully!", "")

    else:
        # OVA mode: export OVF to temp, then tar it as OVA into spec.outdir
        with tempfile.TemporaryDirectory(prefix=f"govc_export_{spec.vm}_") as tmpdir:
            tmp_path = Path(tmpdir)

            try:
                export_cmd = [spec.govc_bin, "export.ovf", "-vm", spec.vm, str(tmp_path)]
                _run_govc_export(
                    export_cmd,
                    spec.env or {},
                    logger,
                    show_progress=spec.show_progress,
                    prefer_pty=spec.prefer_pty,
                    title="Exporting OVF for OVA...",
                )

                ovf_dir = _find_exported_ovf_dir(tmp_path, spec.vm)
                if not ovf_dir:
                    raise GovcExportError(f"Could not find OVF directory in temp location: {tmp_path}")

                ova_file = spec.outdir / (spec.ova_filename or f"{spec.vm}.ova")

                _info(logger, "▌ Creating OVA archive...")
                _create_ova_from_ovf(ovf_dir, ova_file, logger)

                m, s = _fmt_elapsed(start_time)
                _ok_line(logger, f"OVA export completed in {m}m {s}s")
                _info(logger, f"Output: {ova_file}\n")

                _print_panel(logger, "✓ Export completed successfully!", "")

            except Exception as e:
                m, s = _fmt_elapsed(start_time)
                raise GovcExportError(f"OVA export failed after {m}m {s}s: {e}") from e
