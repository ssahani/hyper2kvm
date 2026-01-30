# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/converters/flatten.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import codecs
import json
import logging
import os
import re
import selectors
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from hyper2kvm.ssh.ssh_client import SSHClient

from ..core.utils import U
from ..vmware.utils.vmdk_parser import VMDK

# Helpers


@dataclass(frozen=True)
class _ProgressPolicy:
    # UI update cadence / thresholds
    ui_interval_s: float = 0.25
    ui_min_step_pct: float = 1.0

    # log cadence / thresholds
    log_interval_s: float = 10.0
    log_min_step_pct: float = 5.0

    # poll cadence for IO (stderr reads)
    io_poll_s: float = 0.20

    # safety rails
    timeout_s: float | None = None  # hard timeout for qemu-img convert
    debug_rate_limit_s: float = 1.0  # rate-limit qemu-img stderr debug spam


def _atomic_tmp(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".part")


def _unlink_quiet(p: Path) -> None:
    try:
        if p.exists():
            p.unlink()
    except Exception:
        pass


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _is_within_dir(child: Path, parent_dir: Path) -> bool:
    """
    True if child resolves under parent_dir (both resolved).
    """
    try:
        child_r = child.resolve()
        parent_r = parent_dir.resolve()
        child_r.relative_to(parent_r)
        return True
    except Exception:
        return False


def _norm_rel_path(p: str) -> str:
    """
    Normalize a VMDK-ish relative path:
      - backslashes -> slashes
      - strip leading slashes
      - collapse '.' and '..' via normpath
    """
    s = (p or "").strip().replace("\\", "/")
    s = s.lstrip("/")
    s = os.path.normpath(s).replace("\\", "/")
    if s in (".", ""):
        return ""
    return s


def _safe_join_remote(base_dir: str, rel: str) -> str:
    """
    Join a remote base directory and a relative path, preventing traversal outside base_dir.

    Returns a normalized remote path.

    IMPORTANT: rel must be a non-empty relative file path. Empty/"." is rejected.
    """
    base = os.path.normpath(base_dir).rstrip(os.sep)
    rel_n = _norm_rel_path(rel)
    if not rel_n:
        raise ValueError(f"Empty/invalid relative path: {rel!r}")

    candidate = os.path.normpath(os.path.join(base, rel_n))
    if candidate != base and not candidate.startswith(base + os.sep):
        raise ValueError(f"Remote path escapes base dir: base={base!r} rel={rel!r} => {candidate!r}")
    return candidate


def _safe_join_local(outdir: Path, rel: str) -> Path:
    """
    Join outdir and a relative path, preventing writes outside outdir.

    IMPORTANT: rel must be a non-empty relative file path. Empty/"." is rejected.
    """
    outdir = Path(outdir)
    rel_n = _norm_rel_path(rel)
    if not rel_n:
        raise ValueError(f"Empty/invalid relative path: {rel!r}")

    cand = outdir / rel_n
    if not _is_within_dir(cand, outdir):
        raise ValueError(f"Local path escapes outdir: outdir={outdir} rel={rel!r} => {cand}")
    return cand


def _sleep_backoff(attempt: int, base: float = 0.75, cap: float = 8.0) -> None:
    # attempt is 1-based
    t = min(cap, base * (2 ** max(0, attempt - 1)))
    time.sleep(t)


def _quote_remote(path: str) -> str:
    return shlex.quote(path)


# Flatten


class Flatten:
    """
    Flatten snapshot chain into a single self-contained image.

    IMPORTANT CHANGE (fix for Photon Azure VHD / any non-VMDK):
      - We DO NOT hardcode '-f vmdk' anymore.
      - We detect the real input format via 'qemu-img info --output=json'
        and use '-f <format>' when known (vpc/vmdk/raw/qcow2/...).
      - If detection fails, we omit '-f' and let qemu-img autodetect.

    Everything else (fast FLAT path, retry ladder, progress, logging, atomic output) stays.
    """

    _RE_PAREN = re.compile(r"\((\d+(?:\.\d+)?)/100%\)")
    _RE_PERCENT = re.compile(r"(\d+(?:\.\d+)?)%")
    _RE_PROGRESS = re.compile(r"(?:progress|Progress)\s*[:=]\s*(\d+(?:\.\d+)?)")

    # VMDK descriptor FLAT line:
    # RW <sectors> FLAT "disk-flat.vmdk" 0
    _RE_VMDK_FLAT = re.compile(r'^\s*RW\s+\d+\s+FLAT\s+"([^"]+)"\s+\d+\s*$', re.MULTILINE)

    # Public entry

    @staticmethod
    def to_working(logger: logging.Logger, src: Path, outdir: Path, fmt: str) -> Path:
        if U.which("qemu-img") is None:
            U.die(logger, "qemu-img not found (install qemu-utils).", 1)

        src = Path(src)
        outdir = Path(outdir)

        if not src.exists():
            U.die(logger, f"Input image not found: {src}", 1)

        U.ensure_dir(outdir)

        # 0) VMDK-descriptor-only fast path (harmless for VHD; it will just return None)
        fast = Flatten._fast_path_flat(logger, src, outdir, fmt)
        if fast is not None:
            return fast

        final_dst = outdir / f"working-flattened-{U.now_ts()}.{fmt}"
        tmp_dst = _atomic_tmp(final_dst)
        _unlink_quiet(tmp_dst)

        U.banner(logger, "Flatten snapshot chain")
        logger.info("Flattening via qemu-img convert (single self-contained image)…")

        # 1) Detect input format + virtual size once (fixes VHD/VPC vs VMDK)
        info = Flatten._qemu_img_info(logger, src)
        in_fmt = (info.get("format") or "").strip() or None
        virt_size = int(info.get("virtual-size", 0) or 0)

        if in_fmt:
            logger.info(f"Detected input format: {in_fmt}")
        else:
            logger.warning("Could not detect input format; will rely on qemu-img autodetect (no -f).")

        policy = _ProgressPolicy(timeout_s=None)
        attempts = Flatten._flatten_cmd_attempts(src=src, tmp_dst=tmp_dst, fmt=fmt, in_fmt=in_fmt)

        last_err: subprocess.CalledProcessError | None = None
        for i, cmd in enumerate(attempts, start=1):
            _unlink_quiet(tmp_dst)
            logger.debug(f"[flatten attempt {i}/{len(attempts)}] {' '.join(cmd)}")

            rc, stderr_lines = Flatten._run_qemu_img_with_live_progress(
                logger,
                cmd,
                tmp_dst=tmp_dst,
                virt_size=virt_size,
                policy=policy,
                task_label="Flattening",
            )

            if rc == 0:
                tmp_dst.replace(final_dst)
                logger.info(f"Flatten output: {final_dst}")
                return final_dst

            tail = "\n".join(stderr_lines[-160:]) if stderr_lines else ""
            logger.error(f"Flatten attempt {i} failed (rc={rc})")
            if tail:
                logger.error("qemu-img stderr (tail):\n" + tail)

            last_err = subprocess.CalledProcessError(rc, cmd)

        _unlink_quiet(tmp_dst)
        if last_err is None:
            raise RuntimeError("Conversion failed but error not captured")
        raise last_err

    # Attempts (NO --target-is-zero)
    @staticmethod
    def _flatten_cmd_attempts(*, src: Path, tmp_dst: Path, fmt: str, in_fmt: str | None) -> list[list[str]]:
        """
        Build retry commands.
          - Prefer cache-bypass (-t/-T none) first.
          - Use -f <in_fmt> if known; otherwise omit -f (autodetect).
        """
        base_fast = ["qemu-img", "convert", "-p", "-t", "none", "-T", "none"]
        base_compat = ["qemu-img", "convert", "-p"]

        if in_fmt:
            base_fast += ["-f", in_fmt]
            base_compat += ["-f", in_fmt]

        return [
            base_fast + ["-O", fmt, str(src), str(tmp_dst)],
            base_compat + ["-O", fmt, str(src), str(tmp_dst)],
        ]

    @staticmethod
    def _raw_to_fmt_cmd_attempts(*, raw_src: Path, tmp_dst: Path, fmt: str) -> list[list[str]]:
        # Avoid --target-is-zero (requires -n and breaks across qemu versions)
        return [
            ["qemu-img", "convert", "-p", "-t", "none", "-T", "none", "-f", "raw", "-O", fmt, str(raw_src), str(tmp_dst)],
            ["qemu-img", "convert", "-p", "-f", "raw", "-O", fmt, str(raw_src), str(tmp_dst)],
        ]

    # Fast FLAT path (descriptor->extent byte copy)
    @staticmethod
    def _fast_path_flat(logger: logging.Logger, src: Path, outdir: Path, fmt: str) -> Path | None:
        # Only makes sense for tiny VMDK descriptors
        try:
            if src.stat().st_size > 2 * 1024 * 1024:
                return None
            txt = src.read_text(errors="replace")
        except Exception:
            return None

        m = Flatten._RE_VMDK_FLAT.search(txt)
        if not m:
            return None

        href = m.group(1)
        href_norm = _norm_rel_path(href)
        if not href_norm:
            return None

        extent = src.parent / href_norm
        if not _is_within_dir(extent, src.parent):
            logger.warning(f"FLAT extent path escapes descriptor dir; refusing fast path: {href!r}")
            return None

        extent_r = extent.resolve()
        if not extent_r.exists():
            logger.warning(f"FLAT extent referenced but not found: {extent_r}")
            return None

        U.banner(logger, "Fast FLAT flatten")
        logger.info(f"Detected FLAT extent; using byte-copy fast path: {extent_r}")

        raw_dst = outdir / f"working-flat-{U.now_ts()}.raw"
        raw_tmp = _atomic_tmp(raw_dst)
        _unlink_quiet(raw_tmp)

        if U.which("cp") is not None:
            try:
                subprocess.run(
                    ["cp", "--reflink=auto", "--sparse=always", str(extent_r), str(raw_tmp)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                Flatten._copy_with_progress(logger, extent_r, raw_tmp)
        else:
            Flatten._copy_with_progress(logger, extent_r, raw_tmp)

        raw_tmp.replace(raw_dst)

        if fmt.lower() == "raw":
            logger.info(f"Fast FLAT output (raw): {raw_dst}")
            return raw_dst

        # raw -> fmt with progress + retries
        final_dst = outdir / f"working-flattened-{U.now_ts()}.{fmt}"
        tmp_dst = _atomic_tmp(final_dst)
        _unlink_quiet(tmp_dst)

        virt_size = raw_dst.stat().st_size
        policy = _ProgressPolicy(timeout_s=None)
        attempts = Flatten._raw_to_fmt_cmd_attempts(raw_src=raw_dst, tmp_dst=tmp_dst, fmt=fmt)

        last_err: subprocess.CalledProcessError | None = None
        for i, cmd in enumerate(attempts, start=1):
            _unlink_quiet(tmp_dst)
            logger.debug(f"[raw->fmt attempt {i}/{len(attempts)}] {' '.join(cmd)}")

            rc, stderr_lines = Flatten._run_qemu_img_with_live_progress(
                logger,
                cmd,
                tmp_dst=tmp_dst,
                virt_size=virt_size,
                policy=policy,
                task_label=f"Converting raw -> {fmt}",
            )

            if rc == 0:
                tmp_dst.replace(final_dst)
                logger.info(f"Fast FLAT output: {final_dst}")
                return final_dst

            tail = "\n".join(stderr_lines[-160:]) if stderr_lines else ""
            logger.error(f"raw->fmt attempt {i} failed (rc={rc})")
            if tail:
                logger.error("qemu-img stderr (tail):\n" + tail)

            last_err = subprocess.CalledProcessError(rc, cmd)

        _unlink_quiet(tmp_dst)
        if last_err is None:
            raise RuntimeError("Conversion failed but error not captured")
        raise last_err

    # qemu-img runner (robust stderr)

    @staticmethod
    def _run_qemu_img_with_live_progress(
        logger: logging.Logger,
        cmd: list[str],
        *,
        tmp_dst: Path,
        virt_size: int,
        policy: _ProgressPolicy,
        task_label: str,
    ) -> tuple[int, list[str]]:
        """
        Robust stderr reader:
          - non-blocking reads (avoid readline() stalls)
          - handles CR-updated progress lines
          - drains remaining stderr after process exit
          - supports optional hard timeout
          - rate-limits debug spam (but always logs first stderr line in debug)
          - uses incremental UTF-8 decoding to avoid split multibyte artifacts
        """
        stderr_lines: list[str] = []

        process = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=False,
            bufsize=0,
        )
        if process.stderr is None:
            raise RuntimeError("Process stderr unexpectedly None")

        fd = process.stderr.fileno()
        try:
            os.set_blocking(fd, False)
        except Exception:
            pass

        sel = selectors.DefaultSelector()
        sel.register(fd, selectors.EVENT_READ)

        use_bytes = virt_size > 0
        total = float(virt_size) if use_bytes else 100.0

        best_completed = 0.0
        last_seen_pct: float | None = None
        last_io_tick = time.monotonic()

        last_ui_t = 0.0
        last_ui_pct = -1.0
        last_log_t = 0.0
        last_log_pct = -1.0

        start_t = time.monotonic()
        timed_out = False

        # Handle CR-based progress updates
        split_re = re.compile(r"[\r\n]+")
        line_buf = ""

        # incremental decoder for UTF-8-ish streams
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

        # debug gating: log first stderr line always, then rate limit
        saw_any_stderr = False
        last_dbg_t = 0.0

        def parse_progress_pct(line: str) -> float | None:
            s = (line or "").strip()
            if not s:
                return None

            if s.startswith("{") and s.endswith("}"):
                try:
                    o = json.loads(s)
                    if isinstance(o, dict):
                        for k in ("progress", "percent", "pct"):
                            if k in o:
                                v = float(o[k])
                                return v if 0.0 <= v <= 100.0 else None
                except Exception:
                    return None

            m = Flatten._RE_PAREN.search(s)
            if m:
                try:
                    return float(m.group(1))
                except Exception:
                    return None

            m = Flatten._RE_PROGRESS.search(s)
            if m:
                try:
                    v = float(m.group(1))
                    return v if 0.0 <= v <= 100.0 else None
                except Exception:
                    return None

            m = Flatten._RE_PERCENT.search(s)
            if m:
                try:
                    v = float(m.group(1))
                    return v if 0.0 <= v <= 100.0 else None
                except Exception:
                    return None

            return None

        def pct_to_completed(pct: float) -> float:
            if use_bytes and virt_size > 0:
                return (pct / 100.0) * float(virt_size)
            return pct

        def size_based_completed() -> float | None:
            if not use_bytes or virt_size <= 0:
                return None
            try:
                if not tmp_dst.exists():
                    return None
                out_sz = tmp_dst.stat().st_size
            except Exception:
                return None
            return float(out_sz if out_sz < virt_size else virt_size)

        def update_best(v: float) -> None:
            nonlocal best_completed
            if v > best_completed:
                best_completed = v

        def feed_line(line: str) -> None:
            nonlocal last_seen_pct, last_io_tick, saw_any_stderr, last_dbg_t
            last_io_tick = time.monotonic()

            line_clean = (line or "").rstrip("\n")
            if not line_clean:
                return

            stderr_lines.append(line_clean)

            now = time.monotonic()
            if logger.isEnabledFor(logging.DEBUG):
                if not saw_any_stderr:
                    logger.debug(f"qemu-img: {line_clean}")
                    saw_any_stderr = True
                    last_dbg_t = now
                elif (now - last_dbg_t) >= policy.debug_rate_limit_s:
                    logger.debug(f"qemu-img: {line_clean}")
                    last_dbg_t = now

            pct = parse_progress_pct(line_clean)
            if pct is None:
                return
            last_seen_pct = pct
            update_best(pct_to_completed(pct))

        def _consume_text(text: str) -> None:
            nonlocal line_buf
            if not text:
                return
            line_buf += text
            parts = split_re.split(line_buf)

            # if buffer doesn't end with separator, last part is partial
            if line_buf and not (line_buf.endswith("\n") or line_buf.endswith("\r")):
                line_buf = parts.pop() if parts else line_buf
            else:
                line_buf = ""

            for p in parts:
                if p:
                    feed_line(p)

        def _consume_bytes(chunk: bytes) -> None:
            if not chunk:
                return
            text = decoder.decode(chunk)
            _consume_text(text)

        def read_available() -> None:
            try:
                chunk = os.read(fd, 64 * 1024)
            except BlockingIOError:
                return
            except Exception:
                return
            if chunk:
                _consume_bytes(chunk)

        def drain_after_exit(deadline_s: float = 0.5) -> None:
            end = time.monotonic() + max(0.0, deadline_s)
            while time.monotonic() < end:
                try:
                    chunk = os.read(fd, 64 * 1024)
                except BlockingIOError:
                    time.sleep(0.02)
                    continue
                except Exception:
                    break
                if not chunk:
                    break
                _consume_bytes(chunk)

            # flush decoder and any partial buffer
            try:
                tail = decoder.decode(b"", final=True)
            except Exception:
                tail = ""
            if tail:
                _consume_text(tail)
            if line_buf:
                feed_line(line_buf)

        try:
            with Progress(
                TextColumn("{task.description}"),
                BarColumn(),
                (DownloadColumn() if use_bytes else TaskProgressColumn()),
                (TransferSpeedColumn() if use_bytes else TextColumn("")),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
            ) as progress:
                task = progress.add_task(task_label, total=total)

                while True:
                    if policy.timeout_s is not None:
                        elapsed = time.monotonic() - start_t
                        if elapsed > policy.timeout_s:
                            timed_out = True
                            logger.error(f"{task_label} timed out after {elapsed:.1f}s; terminating qemu-img")
                            try:
                                process.terminate()
                            except Exception:
                                pass
                            try:
                                process.wait(timeout=3.0)
                            except Exception:
                                try:
                                    process.kill()
                                except Exception:
                                    pass
                            break

                    events = sel.select(timeout=policy.io_poll_s)
                    if events:
                        read_available()

                    b = size_based_completed()
                    if b is not None:
                        update_best(b)

                    now = time.monotonic()
                    shown_pct = (best_completed / float(virt_size)) * 100.0 if (use_bytes and virt_size > 0) else best_completed
                    shown_pct = _clamp(shown_pct)

                    if (
                        (now - last_ui_t) >= policy.ui_interval_s
                        or (shown_pct - last_ui_pct) >= policy.ui_min_step_pct
                        or shown_pct >= 100.0
                    ):
                        progress.update(task, completed=best_completed)
                        quiet_for = now - last_io_tick
                        if last_seen_pct is not None:
                            progress.update(task, description=f"{task_label} (qemu-img {last_seen_pct:.1f}% | quiet {quiet_for:.1f}s)")
                        else:
                            progress.update(task, description=f"{task_label} (stderr quiet {quiet_for:.1f}s)")
                        last_ui_t = now
                        last_ui_pct = shown_pct

                    if (
                        (now - last_log_t) >= policy.log_interval_s
                        or (shown_pct - last_log_pct) >= policy.log_min_step_pct
                        or shown_pct >= 100.0
                    ):
                        logger.info(f"{task_label} progress: {shown_pct:.1f}%")
                        last_log_t = now
                        last_log_pct = shown_pct

                    if process.poll() is not None:
                        break

            drain_after_exit(deadline_s=0.5)
            rc = process.wait()

            if timed_out:
                rc = 124  # consistent timeout rc

            return rc, stderr_lines
        finally:
            try:
                sel.unregister(fd)
            except Exception:
                pass
            try:
                sel.close()
            except Exception:
                pass
            try:
                process.stderr.close()  # type: ignore[union-attr]
            except Exception:
                pass

    # Misc

    @staticmethod
    def _qemu_img_info(logger: logging.Logger, src: Path) -> dict:
        """
        Detect input format + virtual size once.
        Returns {} on failure (caller can omit -f and keep virt_size=0).
        """
        try:
            cp = subprocess.run(
                ["qemu-img", "info", "--output=json", str(src)],
                check=True,
                capture_output=True,
                text=True,
            )
            info = json.loads(cp.stdout or "{}")
            if not isinstance(info, dict):
                return {}
            fmt = (info.get("format") or "").strip()
            vsz = info.get("virtual-size", 0)
            logger.debug(f"qemu-img info: format={fmt or 'unknown'} virtual-size={vsz}")
            return info
        except Exception as e:
            logger.debug(f"Could not determine qemu-img info via qemu-img info: {e}")
            return {}

    @staticmethod
    def _qemu_img_virtual_size(logger: logging.Logger, src: Path) -> int:
        # Kept for compatibility: other callers might use it.
        try:
            info = Flatten._qemu_img_info(logger, src)
            return int(info.get("virtual-size", 0) or 0)
        except Exception as e:
            logger.debug(f"Could not determine virtual size via qemu-img info: {e}")
            return 0

    @staticmethod
    def _copy_with_progress(logger: logging.Logger, src: Path, dst: Path, *, chunk_mb: int = 16) -> None:
        total = src.stat().st_size
        chunk = max(1, chunk_mb) * 1024 * 1024

        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task(f"Copying {src.name}", total=total)
            with open(src, "rb") as rf, open(dst, "wb") as wf:
                while True:
                    b = rf.read(chunk)
                    if not b:
                        break
                    wf.write(b)
                    progress.update(task, advance=len(b))


# Fetch (remote ESXi fetch helper)


class Fetch:
    @staticmethod
    def fetch_descriptor_and_extent(
        logger: logging.Logger,
        sshc: SSHClient,
        remote_desc: str,
        outdir: Path,
        fetch_all: bool,
    ) -> Path:
        U.banner(logger, "Fetch VMDK from remote")
        outdir = Path(outdir)
        U.ensure_dir(outdir)

        sshc.check()

        remote_desc_n = os.path.normpath(remote_desc)
        if not sshc.exists(remote_desc_n):
            U.die(logger, f"Remote descriptor not found: {remote_desc_n}", 1)

        remote_dir = os.path.dirname(remote_desc_n)

        local_desc = outdir / os.path.basename(remote_desc_n)
        logger.info(f"Copying descriptor: {remote_desc_n} -> {local_desc}")
        Fetch._scp_from_atomic(logger, sshc, remote_desc_n, local_desc)

        Fetch._fetch_extent_for_descriptor(logger, sshc, remote_dir, local_desc, outdir)

        if fetch_all:
            seen: set[str] = set()
            cur_local_desc = local_desc
            cur_remote_dir = remote_dir

            while True:
                parent_hint = VMDK.parse_parent(logger, cur_local_desc)
                if not parent_hint:
                    break

                try:
                    parent_remote = _safe_join_remote(cur_remote_dir, parent_hint)
                except Exception as e:
                    logger.warning(f"Unsafe parent hint {parent_hint!r} (from {cur_local_desc.name}): {e}")
                    break

                if parent_remote in seen:
                    logger.warning(f"Parent loop detected at {parent_remote}, stopping fetch")
                    break
                seen.add(parent_remote)

                if not sshc.exists(parent_remote):
                    logger.warning(f"Parent descriptor missing: {parent_remote}")
                    break

                try:
                    local_parent_desc = _safe_join_local(outdir, parent_hint)
                    U.ensure_dir(local_parent_desc.parent)
                except Exception:
                    local_parent_desc = outdir / os.path.basename(parent_hint)

                logger.info(f"Copying parent descriptor: {parent_remote} -> {local_parent_desc}")
                Fetch._scp_from_atomic(logger, sshc, parent_remote, local_parent_desc)

                parent_remote_dir = os.path.dirname(parent_remote)
                Fetch._fetch_extent_for_descriptor(logger, sshc, parent_remote_dir, local_parent_desc, outdir)

                cur_local_desc = local_parent_desc
                cur_remote_dir = parent_remote_dir

        return local_desc

    @staticmethod
    def _fetch_extent_for_descriptor(
        logger: logging.Logger,
        sshc: SSHClient,
        remote_dir: str,
        local_desc: Path,
        outdir: Path,
    ) -> Path | None:
        extent_rel = VMDK.parse_extent(logger, local_desc)

        if extent_rel:
            try:
                remote_extent = _safe_join_remote(remote_dir, extent_rel)
            except Exception as e:
                logger.warning(f"Unsafe extent path {extent_rel!r} (from {local_desc.name}): {e}")
                return None

            try:
                local_extent = _safe_join_local(outdir, extent_rel)
                U.ensure_dir(local_extent.parent)
            except Exception:
                local_extent = outdir / os.path.basename(remote_extent)
        else:
            stem = local_desc.stem
            remote_extent = os.path.normpath(os.path.join(remote_dir, f"{stem}-flat.vmdk"))
            local_extent = outdir / os.path.basename(remote_extent)

        if not sshc.exists(remote_extent):
            logger.warning(f"Extent not found remotely: {remote_extent}")
            return None

        logger.info(f"Copying extent: {remote_extent} -> {local_extent}")
        Fetch._scp_from_atomic(logger, sshc, remote_extent, local_extent)
        return local_extent

    @staticmethod
    def _remote_size_best_effort(logger: logging.Logger, sshc: SSHClient, remote: str) -> int | None:
        """
        Best-effort remote size. Uses sshc.run() if available; otherwise returns None.
        """
        run = getattr(sshc, "run", None)
        if run is None:
            return None

        cmds = [
            f"stat -c %s {_quote_remote(remote)}",
            f"stat -f %z {_quote_remote(remote)}",
            f"wc -c < {_quote_remote(remote)}",
        ]
        for c in cmds:
            try:
                cp = run(c)  # type: ignore[misc]
                out = getattr(cp, "stdout", None)
                if out is None:
                    if isinstance(cp, tuple) and len(cp) >= 2:
                        out = cp[1]
                    elif isinstance(cp, str):
                        out = cp
                if out is None:
                    continue
                s = str(out).strip().splitlines()[-1].strip()
                if not s:
                    continue
                return int(s)
            except Exception as e:
                logger.debug(f"Remote size probe failed ({c!r}): {e}")
                continue
        return None

    @staticmethod
    def _scp_from_atomic(logger: logging.Logger, sshc: SSHClient, remote: str, local: Path) -> None:
        """
        Atomic scp with retries and integrity checks.

        - Skip ONLY when we can prove local size == remote size.
        - Retries + backoff for transient ESXi/network hiccups.
        - Always download into <file>.part then rename.
        """
        local = Path(local)
        U.ensure_dir(local.parent)

        remote_size = Fetch._remote_size_best_effort(logger, sshc, remote)

        if remote_size is not None:
            try:
                if local.exists() and local.stat().st_size == remote_size:
                    logger.debug(f"Local file already present with matching size; skipping: {local}")
                    return
            except Exception:
                pass

        tmp = _atomic_tmp(local)
        _unlink_quiet(tmp)

        max_tries = 4
        last_err: Exception | None = None

        for attempt in range(1, max_tries + 1):
            _unlink_quiet(tmp)
            try:
                sshc.scp_from(remote, tmp)

                if not tmp.exists():
                    raise RuntimeError(f"scp completed but temp file missing: {tmp}")

                sz = tmp.stat().st_size
                if sz == 0:
                    raise RuntimeError(f"scp produced empty file: {tmp}")

                if remote_size is not None and sz != remote_size:
                    raise RuntimeError(f"scp size mismatch: got={sz} expected={remote_size} for {remote}")

                tmp.replace(local)
                return
            except Exception as e:
                last_err = e
                logger.warning(f"SCP attempt {attempt}/{max_tries} failed for {remote} -> {local}: {e}")
                _sleep_backoff(attempt)

        _unlink_quiet(tmp)
        if last_err is None:
            raise RuntimeError("SCP download failed but error not captured")
        raise last_err
