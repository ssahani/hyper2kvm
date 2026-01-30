# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# vmdk2kvm/vsphere/ovftool_client.py
from __future__ import annotations

"""
ovftool wrapper client for vmdk2kvm.

This module provides a **thin, defensive, no-threads** wrapper around Broadcom/VMware
OVF Tool ("ovftool") to export/import OVF/OVA from/to vSphere endpoints.

Design goals:
  - Self-contained: stdlib only (optional Rich for nicer progress)
  - Defensive parsing: treat ovftool output as human text that may change
  - Stable orchestration: callers decide policy; this module exposes primitives
  - Logging-first: emit the exact command shape (with secrets masked)
  - No background threads: single flow, blocking subprocess, streaming output
  - Practical: handles the usual flags (noSSLVerify, thumbprint, acceptAllEulas, etc.)

Notes:
  - ovftool is proprietary and must be installed by the user.
  - It can export from:
      - vCenter / ESXi: vi://user:pass@host/...
      - local: OVF/OVA to local, or deploy local OVF/OVA to vi://
  - ovftool accepts both OVF directory and OVA file outputs depending on destination.
"""

import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union


# --------------------------------------------------------------------------------------
# Optional Rich UI
# --------------------------------------------------------------------------------------
try:  # pragma: no cover
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

    RICH_AVAILABLE = True
except Exception:  # pragma: no cover
    Console = None  # type: ignore
    Progress = None  # type: ignore
    SpinnerColumn = None  # type: ignore
    TextColumn = None  # type: ignore
    BarColumn = None  # type: ignore
    TimeElapsedColumn = None  # type: ignore
    RICH_AVAILABLE = False


# --------------------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------------------
class OvfToolError(RuntimeError):
    """Generic ovftool failure."""


class OvfToolNotFound(OvfToolError):
    """Raised when ovftool binary cannot be found."""


class OvfToolAuthError(OvfToolError):
    """Likely authentication/permission failure (best-effort classification)."""


class OvfToolSslError(OvfToolError):
    """Likely SSL/certificate/handshake failure (best-effort classification)."""


# --------------------------------------------------------------------------------------
# Regex helpers for parsing output
# --------------------------------------------------------------------------------------
_PROGRESS_RE = re.compile(r"^\s*Progress:\s*(\d+)\s*%\s*$", re.IGNORECASE)
_VERSION_RE = re.compile(r"^\s*VMware\s+OVF\s+Tool\s+([\w\.\-\+]+)", re.IGNORECASE)
# Some ovftool builds print "Error:" lines; keep it loose.
_ERROR_HINT_RE = re.compile(r"\b(error|failed|exception)\b", re.IGNORECASE)

# Very common strings you might see; used only for *best-effort* error typing
_SSL_HINTS = (
    "SSL",
    "CERTIFICATE",
    "handshake",
    "thumbprint",
    "noSSLVerify",
    "PKIX",
    "x509",
)
_AUTH_HINTS = (
    "authentication",
    "permission",
    "not authorized",
    "unauthorized",
    "invalid login",
    "denied",
)


# --------------------------------------------------------------------------------------
# Config dataclasses
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class OvfToolPaths:
    """Resolved ovftool binary path."""
    ovftool_bin: str


@dataclass(frozen=True)
class OvfExportOptions:
    """
    Export options for ovftool.

    Many flags are "pass-through"; if you need something not modeled here,
    use extra_args.
    """
    # TLS / endpoint
    no_ssl_verify: bool = True
    thumbprint: Optional[str] = None  # e.g. "AA:BB:..."; used with vi:// endpoints

    # Legal / UX
    accept_all_eulas: bool = True
    quiet: bool = False
    verbose: bool = False

    # Output shape
    # - if destination is ".ova", ovftool typically emits a single OVA
    # - if destination is a directory, it emits OVF + VMDKs, etc.
    overwrite: bool = False

    # VM / disk behavior (commonly useful for deploy/import, harmless on export)
    disk_mode: Optional[str] = None  # "thin" | "thick" | "eagerZeroedThick" (depends on target)

    # Optional retry wrapper (our wrapper, not ovftool internal)
    retries: int = 0
    retry_backoff_s: float = 2.0

    # Extra raw args appended last (advanced escape hatch)
    extra_args: Tuple[str, ...] = ()


@dataclass(frozen=True)
class OvfDeployOptions:
    """
    Deploy options for importing OVF/OVA to vSphere via ovftool.

    This is a minimal starter set; ovftool has a huge surface area.
    """
    no_ssl_verify: bool = True
    thumbprint: Optional[str] = None
    accept_all_eulas: bool = True

    overwrite: bool = False
    power_on: bool = False

    # Placement knobs (some are expressed as --prop:, --net:, etc; keep generic)
    name: Optional[str] = None  # --name=...
    datastore: Optional[str] = None  # --datastore=...
    network_map: Tuple[Tuple[str, str], ...] = ()  # (src_net, dst_net) -> --net:"src"="dst"

    # Disk / provisioning
    disk_mode: Optional[str] = None  # "thin" etc.

    quiet: bool = False
    verbose: bool = False

    retries: int = 0
    retry_backoff_s: float = 2.0
    extra_args: Tuple[str, ...] = ()


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------
def find_ovftool(explicit_path: Optional[str] = None) -> OvfToolPaths:
    """
    Resolve ovftool binary.

    Search order:
      1) explicit_path if provided
      2) $OVFTOOL or $OVFTOOL_BIN
      3) PATH via shutil.which("ovftool")
      4) common install locations (best-effort)
    """
    candidates: List[str] = []

    if explicit_path:
        candidates.append(explicit_path)

    env_bin = os.environ.get("OVFTOOL") or os.environ.get("OVFTOOL_BIN")
    if env_bin:
        candidates.append(env_bin)

    which = shutil.which("ovftool")
    if which:
        candidates.append(which)

    # Common locations (Linux)
    candidates.extend(
        [
            "/usr/bin/ovftool",
            "/usr/local/bin/ovftool",
            "/opt/vmware/ovftool/ovftool",
            "/opt/vmware/ovf-tool/ovftool",
            "/opt/ovftool/ovftool",
        ]
    )

    for c in candidates:
        p = Path(c).expanduser()
        if p.is_file() and os.access(str(p), os.X_OK):
            return OvfToolPaths(ovftool_bin=str(p))

    raise OvfToolNotFound(
        "ovftool binary not found. Install OVF Tool and ensure 'ovftool' is in PATH, "
        "or set OVFTOOL=/path/to/ovftool."
    )


def ovftool_version(paths: OvfToolPaths) -> Optional[str]:
    """
    Return ovftool version string if detected, else None.
    """
    rc, out, _err = _run_capture([paths.ovftool_bin, "--version"])
    if rc != 0:
        return None
    for line in out.splitlines():
        m = _VERSION_RE.search(line)
        if m:
            return m.group(1)
    # Some builds just output a version number; fallback to first non-empty line
    for line in out.splitlines():
        s = line.strip()
        if s:
            return s
    return None


def export_to_ovf_or_ova(
    *,
    paths: OvfToolPaths,
    source: str,
    destination: Union[str, Path],
    options: Optional[OvfExportOptions] = None,
    env: Optional[Dict[str, str]] = None,
    log_prefix: str = "ovftool",
) -> None:
    """
    Export from a vSphere endpoint (or other ovftool-supported source) to OVF directory or OVA file.

    Examples:
      source: "vi://administrator@vsphere.local:pass@vcenter.example/DC/vm/MyVM"
      destination: "/var/tmp/MyVM.ova"   (OVA)
      destination: "/var/tmp/MyVM-ovf/"  (OVF dir)

    Important:
      - Do NOT embed passwords in logs. This module masks vi:// credentials on logging.
    """
    opt = options or OvfExportOptions()
    dest = str(Path(destination).expanduser())

    cmd = [paths.ovftool_bin]
    cmd.extend(_common_flags(no_ssl_verify=opt.no_ssl_verify, thumbprint=opt.thumbprint))
    if opt.accept_all_eulas:
        cmd.append("--acceptAllEulas")
    if opt.quiet:
        cmd.append("--quiet")
    if opt.verbose:
        cmd.append("--X:logLevel=verbose")  # best-effort; harmless if ignored

    if opt.overwrite:
        cmd.append("--overwrite")

    if opt.disk_mode:
        # Not always meaningful for export, but some environments expect it.
        cmd.append(f"--diskMode={opt.disk_mode}")

    cmd.extend(opt.extra_args)

    cmd.append(source)
    cmd.append(dest)

    _run_with_retries(
        cmd=cmd,
        retries=opt.retries,
        backoff_s=opt.retry_backoff_s,
        env=env,
        log_prefix=log_prefix,
    )


def export_to_ova(
    *,
    paths: OvfToolPaths,
    source: str,
    ova_path: Union[str, Path],
    options: Optional[OvfExportOptions] = None,
    env: Optional[Dict[str, str]] = None,
    log_prefix: str = "ovftool",
) -> None:
    """
    Convenience wrapper to export explicitly to an .ova file.
    """
    p = Path(ova_path).expanduser()
    if p.suffix.lower() != ".ova":
        raise ValueError(f"ova_path must end with .ova, got: {p}")
    export_to_ovf_or_ova(
        paths=paths,
        source=source,
        destination=p,
        options=options,
        env=env,
        log_prefix=log_prefix,
    )


def deploy_ovf_or_ova(
    *,
    paths: OvfToolPaths,
    source_ovf_or_ova: Union[str, Path],
    target_vi: str,
    options: Optional[OvfDeployOptions] = None,
    env: Optional[Dict[str, str]] = None,
    log_prefix: str = "ovftool",
) -> None:
    """
    Deploy/import an OVF directory or OVA file to a vSphere target.

    source_ovf_or_ova:
      - "/path/to/vm.ova"
      - "/path/to/vm.ovf"
      - "/path/to/ovf-dir/" (contains .ovf)

    target_vi example:
      - "vi://administrator@vsphere.local:pass@vcenter.example/DC/host/Cluster/Resources"
      - Sometimes you deploy to a specific host or folder; ovftool URL shapes vary.

    This wrapper models only a small set of common knobs; use extra_args for the rest.
    """
    opt = options or OvfDeployOptions()
    src = str(Path(source_ovf_or_ova).expanduser())

    cmd = [paths.ovftool_bin]
    cmd.extend(_common_flags(no_ssl_verify=opt.no_ssl_verify, thumbprint=opt.thumbprint))
    if opt.accept_all_eulas:
        cmd.append("--acceptAllEulas")
    if opt.quiet:
        cmd.append("--quiet")
    if opt.verbose:
        cmd.append("--X:logLevel=verbose")

    if opt.overwrite:
        cmd.append("--overwrite")
    if opt.power_on:
        cmd.append("--powerOn")

    if opt.name:
        cmd.append(f"--name={opt.name}")

    if opt.datastore:
        cmd.append(f"--datastore={opt.datastore}")

    if opt.disk_mode:
        cmd.append(f"--diskMode={opt.disk_mode}")

    for src_net, dst_net in opt.network_map:
        # ovftool expects quoting around names containing spaces; we pass raw and let subprocess handle.
        cmd.append(f'--net:{src_net}={dst_net}')

    cmd.extend(opt.extra_args)

    cmd.append(src)
    cmd.append(target_vi)

    _run_with_retries(
        cmd=cmd,
        retries=opt.retries,
        backoff_s=opt.retry_backoff_s,
        env=env,
        log_prefix=log_prefix,
    )


# --------------------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------------------
def _common_flags(*, no_ssl_verify: bool, thumbprint: Optional[str]) -> List[str]:
    flags: List[str] = []
    if no_ssl_verify:
        flags.append("--noSSLVerify")
    if thumbprint:
        flags.append(f"--thumbprint={thumbprint}")
    return flags


def _mask_vi_credentials(s: str) -> str:
    """
    Mask vi://user:pass@host style credentials.

    This is best-effort and intentionally conservative: we mask anything between
    'vi://' and '@' if it contains ':'.
    """
    # vi://user:pass@host/... -> vi://user:****@host/...
    return re.sub(r"(vi://[^/@:]+:)([^@]+)(@)", r"\1****\3", s)


def _fmt_cmd_for_log(cmd: Sequence[str]) -> str:
    # Quote for shell-like readability, mask secrets on each token
    toks = [_mask_vi_credentials(t) for t in cmd]
    return " ".join(shlex.quote(t) for t in toks)


def _classify_error(stderr: str, stdout: str) -> Optional[type]:
    blob = (stdout + "\n" + stderr).lower()
    if any(h.lower() in blob for h in _SSL_HINTS):
        return OvfToolSslError
    if any(h.lower() in blob for h in _AUTH_HINTS):
        return OvfToolAuthError
    return None


def _run_capture(cmd: Sequence[str], env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
    p = subprocess.run(
        list(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_merged_env(env),
        check=False,
    )
    return p.returncode, p.stdout or "", p.stderr or ""


def _merged_env(env: Optional[Dict[str, str]]) -> Dict[str, str]:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return merged


def _run_with_retries(
    *,
    cmd: Sequence[str],
    retries: int,
    backoff_s: float,
    env: Optional[Dict[str, str]],
    log_prefix: str,
) -> None:
    attempts = 0
    last_err: Optional[BaseException] = None
    while True:
        attempts += 1
        try:
            _run_streaming(cmd=cmd, env=env, log_prefix=log_prefix)
            return
        except Exception as e:
            last_err = e
            if attempts > (retries + 1):
                raise
            sleep_s = backoff_s * (2 ** (attempts - 2)) if attempts >= 2 else backoff_s
            # Keep it simple and transparent
            print(f"{log_prefix}: attempt {attempts} failed: {e}")
            print(f"{log_prefix}: retrying in {sleep_s:.1f}s...")
            time.sleep(sleep_s)


def _run_streaming(
    *,
    cmd: Sequence[str],
    env: Optional[Dict[str, str]],
    log_prefix: str,
) -> None:
    """
    Run ovftool and stream output line-by-line.

    - Shows best-effort progress if lines like "Progress: 12%" appear.
    - Captures stdout/stderr for error classification without holding entire output forever:
      we keep a rolling tail.
    """
    cmd_list = list(cmd)
    print(f"{log_prefix}: exec: {_fmt_cmd_for_log(cmd_list)}")

    # Rolling tails for diagnostics
    tail_max = 300
    out_tail: List[str] = []
    err_tail: List[str] = []

    use_rich = bool(RICH_AVAILABLE and os.isatty(1))
    console = Console() if (use_rich and Console is not None) else None

    progress = None
    task_id = None
    last_pct: Optional[int] = None

    if use_rich and Progress is not None:
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        )
        progress.start()
        task_id = progress.add_task("ovftool", total=100)

    def _tail_push(buf: List[str], line: str) -> None:
        buf.append(line)
        if len(buf) > tail_max:
            del buf[0 : len(buf) - tail_max]

    try:
        p = subprocess.Popen(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=_merged_env(env),
        )
    except FileNotFoundError as e:
        if progress:
            progress.stop()
        raise OvfToolNotFound(str(e)) from e

    assert p.stdout is not None
    assert p.stderr is not None

    # Single-flow read: interleave by polling stderr/stdout via select if available,
    # but keep it dependency-free. We will do a simple alternating drain approach.
    # This is not perfect ordering, but it is robust and avoids threads.
    while True:
        stdout_line = p.stdout.readline()
        if stdout_line:
            s = stdout_line.rstrip("\n")
            _tail_push(out_tail, s)
            _maybe_update_progress(s, progress, task_id, last_pct_ref=[last_pct])
            # Only print noisy lines if they look interesting (or if no Rich)
            if not progress or _ERROR_HINT_RE.search(s):
                print(f"{log_prefix}: {s}")

        stderr_line = p.stderr.readline()
        if stderr_line:
            s = stderr_line.rstrip("\n")
            _tail_push(err_tail, s)
            _maybe_update_progress(s, progress, task_id, last_pct_ref=[last_pct])
            # stderr is usually useful
            print(f"{log_prefix}: {s}")

        rc = p.poll()
        if rc is not None:
            # Drain remaining output
            _drain_remaining(p.stdout, out_tail, log_prefix, is_stderr=False)
            _drain_remaining(p.stderr, err_tail, log_prefix, is_stderr=True)
            if progress:
                progress.stop()
            if rc != 0:
                stdout_txt = "\n".join(out_tail)
                stderr_txt = "\n".join(err_tail)
                klass = _classify_error(stderr_txt, stdout_txt) or OvfToolError
                raise klass(
                    f"ovftool failed rc={rc}\n"
                    f"cmd={_fmt_cmd_for_log(cmd_list)}\n"
                    f"--- stdout (tail) ---\n{stdout_txt}\n"
                    f"--- stderr (tail) ---\n{stderr_txt}\n"
                )
            return


def _drain_remaining(stream, tail: List[str], log_prefix: str, is_stderr: bool) -> None:
    while True:
        line = stream.readline()
        if not line:
            break
        s = line.rstrip("\n")
        tail.append(s)
        if len(tail) > 300:
            del tail[0 : len(tail) - 300]
        if is_stderr:
            print(f"{log_prefix}: {s}")
        else:
            # stdout often contains repeated "Progress:" spam; print only interesting lines
            if _ERROR_HINT_RE.search(s):
                print(f"{log_prefix}: {s}")


def _maybe_update_progress(line: str, progress, task_id, last_pct_ref: List[Optional[int]]) -> None:
    if not progress or task_id is None:
        return
    m = _PROGRESS_RE.match(line)
    if not m:
        return
    try:
        pct = int(m.group(1))
    except Exception:
        return
    pct = max(0, min(100, pct))
    last = last_pct_ref[0]
    if last is None or pct != last:
        progress.update(task_id, completed=pct)
        last_pct_ref[0] = pct
