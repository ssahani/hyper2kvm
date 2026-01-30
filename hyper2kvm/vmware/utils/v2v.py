# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# hyper2kvm/vmware/utils/v2v.py
from __future__ import annotations

"""
virt-v2v orchestration for VMware VM conversion
"""

import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote

# Optional: Rich progress UI (TTY friendly). Falls back to plain logs if Rich not available.
try:  # pragma: no cover
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    RICH_AVAILABLE = True
except Exception:  # pragma: no cover
    Progress = None  # type: ignore
    SpinnerColumn = None  # type: ignore
    TextColumn = None  # type: ignore
    TimeElapsedColumn = None  # type: ignore
    RICH_AVAILABLE = False

# Optional: non-blocking pump
try:  # pragma: no cover
    import select  # type: ignore

    SELECT_AVAILABLE = True
except Exception:  # pragma: no cover
    select = None  # type: ignore
    SELECT_AVAILABLE = False

# Import VMwareError from http_client or fallback
try:
    from ..transports.http_client import VMwareError
except Exception:  # pragma: no cover
    try:
        from ...core.exceptions import VMwareError  # type: ignore
    except Exception:  # pragma: no cover

        class VMwareError(RuntimeError):
            pass


# Import V2VExportOptions from vmware_client
try:
    from ..clients.client import V2VExportOptions
except Exception:  # pragma: no cover
    # For standalone usage, define a minimal version
    from dataclasses import dataclass
    from typing import Tuple

    @dataclass
    class V2VExportOptions:  # type: ignore
        vm_name: str
        export_mode: str = "ovf_export"
        datacenter: str = "auto"
        compute: str = "auto"
        transport: str = "vddk"
        no_verify: bool = False
        vddk_libdir: Optional[Path] = None
        vddk_thumbprint: Optional[str] = None
        vddk_snapshot_moref: Optional[str] = None
        vddk_transports: Optional[str] = None
        output_dir: Path = Path("./out")
        output_format: str = "qcow2"
        extra_args: Tuple[str, ...] = ()


def _vpx_uri(client: Any, *, datacenter: str, compute: str, no_verify: bool) -> str:
    q = "?no_verify=1" if no_verify else ""
    user_enc = quote(client.user or "", safe="")
    host = (client.host or "").strip()
    dc_enc = quote((datacenter or "").strip(), safe="")
    compute_norm = (compute or "").strip().lstrip("/")
    compute_enc = quote(compute_norm, safe="/-_.")
    return f"vpx://{user_enc}@{host}/{dc_enc}/{compute_enc}{q}"


def _write_password_file(client: Any, base_dir: Path) -> Path:
    pw = (client.password or "").strip()
    if not pw:
        raise VMwareError(
            "Missing vSphere password for virt-v2v (-ip). "
            "Set vs_password or vs_password_env (or vc_password/vc_password_env as fallback)."
        )
    base_dir = client._ensure_output_dir(base_dir)
    pwfile = base_dir / f".v2v-pass-{os.getpid()}.txt"
    pwfile.write_text(pw + "\n", encoding="utf-8")
    try:
        os.chmod(pwfile, 0o600)
    except Exception:
        pass
    return pwfile


def _build_virt_v2v_cmd(client: Any, opt: V2VExportOptions, *, password_file: Path) -> List[str]:
    if not opt.vm_name:
        raise VMwareError("V2VExportOptions.vm_name is required")
    if not client.si:
        raise VMwareError("Not connected to vSphere; cannot export. Call connect() first.")

    resolved_dc = client.resolve_datacenter_for_vm(opt.vm_name, opt.datacenter)
    resolved_compute = client.resolve_compute_for_vm(opt.vm_name, opt.compute)

    transport = (opt.transport or "").strip().lower()
    if transport not in ("vddk", "ssh"):
        raise VMwareError(f"Unsupported virt-v2v transport: {transport!r} (expected 'vddk' or 'ssh')")

    argv: List[str] = [
        "virt-v2v",
        "-i",
        "libvirt",
        "-ic",
        _vpx_uri(client, datacenter=resolved_dc, compute=resolved_compute, no_verify=opt.no_verify),
        "-it",
        transport,
        "-ip",
        str(password_file),
    ]

    if transport == "vddk":
        if opt.vddk_libdir:
            argv += ["-io", f"vddk-libdir={str(Path(opt.vddk_libdir))}"]
        if opt.vddk_thumbprint:
            argv += ["-io", f"vddk-thumbprint={str(opt.vddk_thumbprint)}"]
        if opt.vddk_snapshot_moref:
            argv += ["-io", f"vddk-snapshot={opt.vddk_snapshot_moref}"]
        if opt.vddk_transports:
            argv += ["-io", f"vddk-transports={opt.vddk_transports}"]

    argv.append(opt.vm_name)
    client._ensure_output_dir(opt.output_dir)
    argv += ["-o", "local", "-os", str(opt.output_dir), "-of", opt.output_format]
    argv += list(opt.extra_args)
    return argv


def _popen_text(client: Any, argv: Sequence[str], *, env: Optional[Dict[str, str]] = None) -> subprocess.Popen:
    client.logger.info("Running: %s", " ".join(shlex.quote(a) for a in argv))
    proc = subprocess.Popen(
        list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        bufsize=1,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None
    if SELECT_AVAILABLE:
        try:
            os.set_blocking(proc.stdout.fileno(), False)  # type: ignore[attr-defined]
            os.set_blocking(proc.stderr.fileno(), False)  # type: ignore[attr-defined]
        except Exception:
            pass
    return proc


def _pump_lines_blocking(client: Any, proc: subprocess.Popen) -> List[str]:
    assert proc.stdout is not None
    assert proc.stderr is not None
    lines: List[str] = []
    out_line = proc.stdout.readline()
    err_line = proc.stderr.readline()
    if out_line:
        lines.append(out_line.rstrip("\n"))
    if err_line:
        lines.append(err_line.rstrip("\n"))
    return lines


def _pump_lines_select(client: Any, proc: subprocess.Popen, *, timeout_s: float = 0.20) -> List[str]:
    assert proc.stdout is not None
    assert proc.stderr is not None
    rlist = [proc.stdout, proc.stderr]
    try:
        ready, _, _ = select.select(rlist, [], [], timeout_s)  # type: ignore[union-attr]
    except Exception:
        ready = rlist

    lines: List[str] = []
    for s in ready:
        try:
            chunk = s.read()
        except Exception:
            chunk = ""
        if not chunk:
            continue
        for ln in chunk.splitlines():
            lines.append(ln.rstrip("\n"))
    return lines


def _use_rich_progress(client: Any) -> bool:
    return bool(
        RICH_AVAILABLE
        and client._rich_console is not None
        and hasattr(client._rich_console, "is_terminal")
        and client._rich_console.is_terminal  # type: ignore[attr-defined]
        and Progress is not None
        and SpinnerColumn is not None
        and TextColumn is not None
        and TimeElapsedColumn is not None
    )


def _drain_remaining_output(client: Any, proc: subprocess.Popen, *, max_rounds: int = 10) -> None:
    for _ in range(0, max_rounds):
        lines = _pump_lines_select(client, proc, timeout_s=0.05) if SELECT_AVAILABLE else _pump_lines_blocking(client, proc)
        if not lines:
            break
        for ln in lines:
            s = ln.strip()
            if s:
                client.logger.info("%s", s)


def _run_logged_subprocess(client: Any, argv: Sequence[str], *, env: Optional[Dict[str, str]] = None) -> int:
    proc = _popen_text(client, argv, env=env)

    def pump() -> List[str]:
        if SELECT_AVAILABLE:
            return _pump_lines_select(client, proc)
        return _pump_lines_blocking(client, proc)

    if _use_rich_progress(client):
        assert client._rich_console is not None
        assert Progress is not None
        assert SpinnerColumn is not None
        assert TextColumn is not None
        assert TimeElapsedColumn is not None

        last_line = ""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=client._rich_console,  # type: ignore[arg-type]
            transient=True,
        ) as progress:
            task_id = progress.add_task("virt-v2v running…", total=None)
            while True:
                for ln in pump():
                    last_line = ln.strip()
                    if last_line:
                        client.logger.info("%s", last_line)
                        show = last_line[:117] + "..." if len(last_line) > 120 else last_line
                        progress.update(task_id, description=f"virt-v2v running… {show}")

                if proc.poll() is not None:
                    _drain_remaining_output(client, proc, max_rounds=10)
                    break

            rc = int(proc.wait())
            progress.update(task_id, description=f"virt-v2v finished (rc={rc})")
            return rc

    # Plain logger loop
    while True:
        lines = pump()
        for ln in lines:
            s = ln.strip()
            if s:
                client.logger.info("%s", s)
        if (not lines) and (proc.poll() is not None):
            break

    _drain_remaining_output(client, proc, max_rounds=10)
    return int(proc.wait())


def v2v_export_vm(client: Any, opt: V2VExportOptions) -> Path:
    if shutil.which("virt-v2v") is None:
        raise VMwareError("virt-v2v not found in PATH. Install virt-v2v/libguestfs tooling.")
    if not client.si:
        raise VMwareError("Not connected to vSphere; cannot export. Call connect() first.")

    pwfile = _write_password_file(client, opt.output_dir)
    try:
        argv = _build_virt_v2v_cmd(client, opt, password_file=pwfile)
        rc = _run_logged_subprocess(client, argv, env=os.environ.copy())
        if rc != 0:
            raise VMwareError(f"virt-v2v export failed (rc={rc})")
        client.logger.info("virt-v2v export finished OK -> %s", opt.output_dir)
        return opt.output_dir
    finally:
        try:
            pwfile.unlink()
        except FileNotFoundError:
            pass
        except Exception as e:
            client.logger.warning("Failed to remove password file %s: %s", pwfile, e)
