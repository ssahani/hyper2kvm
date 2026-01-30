# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/converters/fetch.py
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import posixpath
import re
import shlex
import time
from pathlib import Path

from ..core.utils import U
from ..ssh.ssh_client import SSHClient
from ..vmware.utils.vmdk_parser import VMDK

# Path + naming helpers

# allow subdirs; sanitize other chars
_REL_SAFE_RE = re.compile(r"[^A-Za-z0-9._/-]+")


def _normalize_remote_path(p: str) -> str:
    """Normalize remote path to POSIX form."""
    p = (p or "").strip().replace("\\", "/")
    # keep leading '/' if present, normpath will keep it
    return posixpath.normpath(p)


def _posix_join_norm(base_dir: str, rel_or_abs: str) -> str:
    """Join (if relative) then normpath, POSIX semantics."""
    base_dir = _normalize_remote_path(base_dir or "")
    rel_or_abs = _normalize_remote_path(rel_or_abs)
    if rel_or_abs.startswith("/"):
        return posixpath.normpath(rel_or_abs)
    return posixpath.normpath(posixpath.join(base_dir, rel_or_abs))


def _is_under_remote_root(path: str, root: str) -> bool:
    """
    True if remote 'path' is inside 'root' directory tree (POSIX).
    root may be '' (disabled).
    """
    if not root:
        return True
    path = _normalize_remote_path(path)
    root = _normalize_remote_path(root)
    # ensure root is treated as directory boundary
    if root == "/":
        return True
    if path == root:
        return True
    return path.startswith(root.rstrip("/") + "/")


def _hash8(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()[:10]


def _safe_local_rel_from_remote(remote_abs_or_norm: str) -> str:
    """
    Produce a local relative path fragment derived from a normalized remote path.
    - Never contains '..'
    - Deterministic
    - Collision-resistant (adds short hash)
    """
    rp = _normalize_remote_path(remote_abs_or_norm)
    # strip leading '/' to make it relative-ish for naming
    rp_rel = rp.lstrip("/")
    rp_rel = _REL_SAFE_RE.sub("-", rp_rel)
    rp_rel = re.sub(r"/{2,}", "/", rp_rel).strip("/")
    # drop any accidental '.' segments
    parts = [p for p in rp_rel.split("/") if p not in ("", ".")]
    # hard block '..' (shouldn't exist after normpath, but defense)
    parts = [("__UP__" if p == ".." else p) for p in parts]
    if not parts:
        parts = ["unknown"]

    # Keep some structure but not infinitely deep:
    # last 3 components usually enough; preserve basename strongly
    tail = parts[-3:] if len(parts) > 3 else parts
    base = "/".join(tail)

    # Ensure basename isn't empty
    base = base or "unknown"

    # Add hash suffix before extension (or at end)
    h = _hash8(rp)
    stem, ext = os.path.splitext(base)
    if ext:
        return f"{stem}__{h}{ext}"
    return f"{base}__{h}"


# SSH subprocess helpers (no threads)

def _ssh_params_from_client(sshc: SSHClient) -> tuple[str, str, int, Path | None, list[str]]:
    """
    Extract connection info from SSHClient.
    Adjust this ONE function if your SSHClient differs.
    """
    cfg = getattr(sshc, "cfg", None)
    host = getattr(sshc, "host", None) or getattr(cfg, "host", None)
    user = getattr(sshc, "user", None) or getattr(cfg, "user", None) or "root"
    port = getattr(sshc, "port", None) or getattr(cfg, "port", None) or 22
    identity = getattr(sshc, "identity", None) or getattr(cfg, "identity", None)
    ssh_opts = getattr(sshc, "ssh_opts", None) or getattr(cfg, "ssh_opts", None) or []

    if not host:
        raise RuntimeError(
            "SSHClient must expose host/user/port/identity/ssh_opts (directly or via .cfg). "
            "Update _ssh_params_from_client() to match your SSHClient."
        )

    ident_path = Path(identity) if identity else None
    return str(host), str(user), int(port), ident_path, list(ssh_opts)


def _build_ssh_base_args(
    host: str,
    user: str,
    port: int,
    identity: Path | None,
    ssh_opts: list[str],
    *,
    hostkey_policy: str = "accept-new",  # "yes" | "accept-new" | "no"
) -> list[str]:
    args: list[str] = ["ssh", "-p", str(port)]
    if identity:
        args += ["-i", str(identity)]

    strict = hostkey_policy
    if strict not in ("yes", "accept-new", "no"):
        strict = "accept-new"

    args += [
        "-o",
        "BatchMode=yes",
        "-o",
        f"StrictHostKeyChecking={strict}",
        "-o",
        "ConnectTimeout=20",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
    ]
    for opt in ssh_opts:
        args.append(str(opt))
    args.append(f"{user}@{host}")
    return args


async def _run_capture(argv: list[str]) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out_b = await proc.stdout.read()  # type: ignore[union-attr]
    rc = await proc.wait()
    return rc, out_b.decode("utf-8", errors="replace")


async def _ssh_check(logger: logging.Logger, ssh_base: list[str]) -> None:
    rc, out = await _run_capture(ssh_base + ["true"])
    if rc != 0:
        raise RuntimeError(f"SSH check failed (rc={rc}). Output:\n{out}")


async def _ssh_exists(logger: logging.Logger, ssh_base: list[str], remote_path: str) -> bool:
    cmd = f"test -e {shlex.quote(remote_path)}"
    rc, _ = await _run_capture(ssh_base + ["sh", "-lc", cmd])
    return rc == 0


async def _ssh_size_bytes_best_effort(logger: logging.Logger, ssh_base: list[str], remote_path: str) -> int | None:
    cmd = f"wc -c < {shlex.quote(remote_path)}"
    rc, out = await _run_capture(ssh_base + ["sh", "-lc", cmd])
    if rc != 0:
        logger.debug(f"Size query failed for {remote_path} rc={rc}: {out.strip()}")
        return None
    s = out.strip().splitlines()[-1].strip() if out.strip() else ""
    try:
        return int(s)
    except Exception:
        logger.debug(f"Size parse failed for {remote_path}: {out!r}")
        return None


async def _ssh_stream_fetch_with_progress(
    logger: logging.Logger,
    ssh_base: list[str],
    remote_path: str,
    local: Path,
    *,
    progress_interval_s: float = 1.0,
    min_percent_step: float = 1.0,
    use_atomic: bool = True,
    read_chunk: int = 1024 * 256,
) -> None:
    """
    Stream remote file over ssh into local (atomic via .part). No threads.
    """
    tmp_local = local.with_suffix(local.suffix + ".part") if use_atomic else local
    U.ensure_dir(tmp_local.parent)

    if use_atomic and tmp_local.exists():
        tmp_local.unlink(missing_ok=True)

    size = await _ssh_size_bytes_best_effort(logger, ssh_base, remote_path)

    # Redirect stderr to stdout to avoid pipe-fill deadlocks; still can parse errors.
    cmd = f"cat {shlex.quote(remote_path)}"
    proc = await asyncio.create_subprocess_exec(
        *(ssh_base + ["sh", "-lc", cmd]),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    last_log_t = 0.0
    last_pct = -1.0
    sent = 0

    try:
        if proc.stdout is None:
            raise RuntimeError("Process stdout unexpectedly None")
        with tmp_local.open("wb") as f:
            while True:
                chunk = await proc.stdout.read(read_chunk)
                if not chunk:
                    break
                f.write(chunk)
                sent += len(chunk)

                now = time.monotonic()
                if size and size > 0:
                    pct = (sent / size) * 100.0
                    should = False
                    if now - last_log_t >= max(0.1, progress_interval_s):
                        should = True
                    if pct - last_pct >= max(0.1, min_percent_step):
                        should = True
                    if should:
                        logger.info(f"Progress for {local.name}: {sent}/{size} ({pct:.1f}%)")
                        last_log_t = now
                        last_pct = pct
                else:
                    if now - last_log_t >= max(0.5, progress_interval_s):
                        logger.info(f"Progress for {local.name}: {sent} bytes")
                        last_log_t = now

        rc = await proc.wait()
        if rc != 0:
            raise RuntimeError(f"SSH stream fetch failed (rc={rc}) for {remote_path} -> {local}")

        if use_atomic:
            tmp_local.replace(local)

        # Final log
        if size and size > 0:
            logger.info(f"Progress for {local.name}: {size}/{size} (100.0%)")
        else:
            try:
                logger.info(f"Fetched {local.name}: {local.stat().st_size} bytes")
            except Exception:
                logger.info(f"Fetched {local.name}")

    except asyncio.CancelledError:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            await proc.wait()
        except Exception:
            pass
        if use_atomic and tmp_local.exists():
            tmp_local.unlink(missing_ok=True)
        raise

    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            await proc.wait()
        except Exception:
            pass
        if use_atomic and tmp_local.exists():
            tmp_local.unlink(missing_ok=True)
        raise


# Fetch logic

class Fetch:
    @staticmethod
    async def fetch_descriptor_and_extent(
        logger: logging.Logger,
        sshc: SSHClient,
        remote_desc: str,
        outdir: Path,
        fetch_all: bool,
        *,
        remote_sandbox_root: str | None = None,
        hostkey_policy: str = "accept-new",
    ) -> Path:
        """
        Fetch a VMDK descriptor and its extent. If fetch_all=True, walk the parent chain
        and fetch each parent descriptor + its extent as well.

        Supports ../ in parents/extents.

        Prevents local path escape by NOT mirroring raw relpaths; instead uses a deterministic,
        collision-proof local name based on the resolved remote path (+ short hash).

        Optionally enforces a remote sandbox root directory: resolved parents/extents must remain
        inside that root (prevents '..' from escaping remotely).

        Returns the *local* path to the top-level descriptor.
        """
        U.banner(logger, "Fetch VMDK from remote")
        U.ensure_dir(outdir)

        host, user, port, identity, ssh_opts = _ssh_params_from_client(sshc)
        ssh_base = _build_ssh_base_args(host, user, port, identity, ssh_opts, hostkey_policy=hostkey_policy)

        await _ssh_check(logger, ssh_base)

        remote_desc = (remote_desc or "").strip()
        if not remote_desc:
            U.die(logger, "Remote descriptor path is empty", 1)

        remote_desc_norm = _normalize_remote_path(remote_desc)

        # Default sandbox root: directory containing the top descriptor (good safe default)
        sandbox = _normalize_remote_path(remote_sandbox_root) if remote_sandbox_root else posixpath.dirname(remote_desc_norm)

        if sandbox and not _is_under_remote_root(remote_desc_norm, sandbox):
            U.die(logger, f"Remote descriptor {remote_desc_norm} is outside sandbox root {sandbox}", 1)

        if not await asyncio.to_thread(lambda: True):  # no-op placeholder to preserve structure (no threads used elsewhere)
            pass

        if not await _ssh_exists(logger, ssh_base, remote_desc_norm):
            U.die(logger, f"Remote descriptor not found: {remote_desc_norm}", 1)

        local_desc = outdir / _safe_local_rel_from_remote(remote_desc_norm)
        U.ensure_dir(local_desc.parent)

        logger.info(f"Copying descriptor: {remote_desc_norm} -> {local_desc}")
        await _ssh_stream_fetch_with_progress(logger, ssh_base, remote_desc_norm, local_desc)

        # Fetch extent for the top descriptor
        await Fetch._fetch_extent_for_descriptor(
            logger=logger,
            ssh_base=ssh_base,
            remote_dir=posixpath.dirname(remote_desc_norm),
            local_desc=local_desc,
            outdir=outdir,
            sandbox_root=sandbox,
        )

        if fetch_all:
            cur_remote_desc = remote_desc_norm
            cur_local_desc = local_desc
            seen: set[str] = set()

            while True:
                try:
                    parent_rel = VMDK.parse_parent(logger, cur_local_desc)
                except Exception as e:
                    logger.error(f"Failed to parse parent from {cur_local_desc}: {e}")
                    break

                if not parent_rel:
                    break

                parent_rel_norm = _normalize_remote_path(parent_rel)

                # Resolve parent relative to current remote descriptor directory
                cur_remote_dir = posixpath.dirname(cur_remote_desc)
                remote_parent_desc = _posix_join_norm(cur_remote_dir, parent_rel_norm)

                # Remote sandbox enforcement
                if sandbox and not _is_under_remote_root(remote_parent_desc, sandbox):
                    logger.warning(
                        f"Parent escapes sandbox root; refusing. parent={remote_parent_desc} root={sandbox}"
                    )
                    break

                if remote_parent_desc in seen:
                    logger.warning(f"Parent loop detected at {remote_parent_desc}, stopping fetch")
                    break
                seen.add(remote_parent_desc)

                if not await _ssh_exists(logger, ssh_base, remote_parent_desc):
                    logger.warning(f"Parent descriptor missing: {remote_parent_desc}")
                    break

                local_parent_desc = outdir / _safe_local_rel_from_remote(remote_parent_desc)
                U.ensure_dir(local_parent_desc.parent)

                logger.info(f"Copying parent descriptor: {remote_parent_desc} -> {local_parent_desc}")
                await _ssh_stream_fetch_with_progress(logger, ssh_base, remote_parent_desc, local_parent_desc)

                await Fetch._fetch_extent_for_descriptor(
                    logger=logger,
                    ssh_base=ssh_base,
                    remote_dir=posixpath.dirname(remote_parent_desc),
                    local_desc=local_parent_desc,
                    outdir=outdir,
                    sandbox_root=sandbox,
                )

                cur_remote_desc = remote_parent_desc
                cur_local_desc = local_parent_desc

        return local_desc

    @staticmethod
    async def _fetch_extent_for_descriptor(
        *,
        logger: logging.Logger,
        ssh_base: list[str],
        remote_dir: str,
        local_desc: Path,
        outdir: Path,
        sandbox_root: str,
    ) -> Path | None:
        """
        Parse extent path from local descriptor and fetch it.
        Returns local extent path if found.
        """
        try:
            extent_rel = VMDK.parse_extent(logger, local_desc)
        except Exception as e:
            logger.error(f"Failed to parse extent from descriptor {local_desc}: {e}")
            raise RuntimeError(f"Parsing failed for {local_desc}: {e}") from e

        if extent_rel:
            extent_rel_norm = _normalize_remote_path(extent_rel)
            remote_extent = _posix_join_norm(remote_dir, extent_rel_norm)
        else:
            stem = local_desc.stem
            remote_extent = posixpath.normpath(posixpath.join(remote_dir, f"{stem}-flat.vmdk"))

        # Remote sandbox enforcement
        if sandbox_root and not _is_under_remote_root(remote_extent, sandbox_root):
            logger.warning(f"Extent escapes sandbox root; refusing. extent={remote_extent} root={sandbox_root}")
            return None

        if not await _ssh_exists(logger, ssh_base, remote_extent):
            logger.warning(f"Extent not found remotely: {remote_extent}")
            return None

        local_extent = outdir / _safe_local_rel_from_remote(remote_extent)
        U.ensure_dir(local_extent.parent)

        logger.info(f"Copying extent: {remote_extent} -> {local_extent}")
        await _ssh_stream_fetch_with_progress(logger, ssh_base, remote_extent, local_extent)
        return local_extent
