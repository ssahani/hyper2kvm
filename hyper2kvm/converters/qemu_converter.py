# SPDX-License-Identifier: LGPL-3.0-or-later
from __future__ import annotations

import json
import logging
import os
import re
import selectors
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Tuple

from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from ..core.utils import U


class Convert:
    """
    qemu-img convert wrapper with:
      ✅ reliable progress: uses qemu-img -p stderr percent when available
      ✅ non-stuck UI: if qemu-img percent is missing/delayed, estimates from written bytes UNTIL first % arrives
      ✅ liveness + stats: polls output size for "written MiB"
      ✅ robust error handling: auto-fallback across incompatible flags (zstd/-m/cache)
      ✅ atomic output (.part -> rename)
      ✅ flat VMDK descriptor preference
      ✅ full stderr tail capture (drains after exit)
      ✅ Ctrl+C safety (terminate/kill qemu-img)

    Notes:
      - We intentionally DO NOT expose/attempt --target-is-zero here.
        qemu-img requires -n (no-create) for --target-is-zero, which doesn't fit
        this fresh-file atomic workflow. If you later add a "precreate + -n"
        pathway (block/LV targets), implement that as a separate mode.
    """

    _RE_PAREN = re.compile(r"\((\d+(?:\.\d+)?)/100%\)")
    _RE_FRACTION = re.compile(r"(\d+(?:\.\d+)?)/100%")
    _RE_PROGRESS = re.compile(r"(?:progress|Progress)\s*[:=]\s*(\d+(?:\.\d+)?)")
    _RE_PERCENT = re.compile(r"(\d+(?:\.\d+)?)%")
    _RE_JSON = re.compile(r"^\s*\{.*\}\s*$")

    # stderr patterns that mean “this option set is incompatible / rejected”
    # Keep this tight so we don’t hide real IO failures.
    _RE_EXPECTED_FALLBACK = re.compile(
        r"("
        r"unknown option|unrecognized option|invalid option|"
        r"not supported|unsupported|"
        r"cannot be used with|mutually exclusive|"
        r"(?:compression_type|compression_level).*invalid"
        r")",
        re.IGNORECASE,
    )

    @dataclass(frozen=True)
    class ConvertOptions:
        cache_mode: str = "none"  # none|writeback|unsafe|"" (disabled)
        threads: Optional[int] = None  # -m N
        compression_type: Optional[str] = "zstd"  # zstd|zlib|None (omit)
        compression_level: Optional[int] = None  # compression_level=...
        preallocation: Optional[str] = None  # preallocation=metadata,...

        def short(self) -> str:
            return (
                f"cache={self.cache_mode or 'off'} "
                f"threads={self.threads or 'off'} "
                f"ctype={self.compression_type or 'omit'} "
                f"clevel={self.compression_level if self.compression_level is not None else 'omit'} "
                f"prealloc={self.preallocation or 'omit'}"
            )

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    @staticmethod
    def convert_image_with_progress(
        logger: logging.Logger,
        src: Path,
        dst: Path,
        *,
        out_format: str,
        compress: bool,
        compress_level: Optional[int] = None,
        compression_type: Optional[str] = "zstd",
        progress_callback: Optional[Callable[[float], None]] = None,
        in_format: Optional[str] = None,
        preallocation: Optional[str] = None,
        atomic: bool = True,
        cache_mode: str = "none",
        threads: Optional[int] = None,
        ui_poll_s: float = 0.20,
        max_stderr_tail: int = 200,
    ) -> None:
        src = Path(src)
        dst = Path(dst)

        if U.which("qemu-img") is None:
            U.die(logger, "qemu-img not found.", 1)

        src = Convert._prefer_descriptor_for_flat(logger, src)
        if not src.is_file():
            raise FileNotFoundError(f"Source image file not found: {src}")

        U.ensure_dir(dst.parent)

        final_dst = dst
        tmp_dst = dst.with_suffix(dst.suffix + ".part") if atomic else dst

        virt_size, detected_fmt = Convert._qemu_img_info(logger, src)
        if in_format is None:
            in_format = detected_fmt

        base = Convert.ConvertOptions(
            cache_mode=cache_mode,
            threads=threads,
            compression_type=compression_type,
            compression_level=compress_level,
            preallocation=preallocation,
        )

        plan = list(Convert._fallback_plan(base, out_format=out_format, compress=compress))

        U.banner(logger, f"Convert to {out_format.upper()}")
        logger.info(
            f"Converting: {src} -> {final_dst} "
            f"(in_format={in_format or 'auto'}, out_format={out_format}, compress={compress}, atomic={atomic})"
        )

        last_error: Optional[subprocess.CalledProcessError] = None

        for attempt_no, opt in enumerate(plan, start=1):
            if atomic and tmp_dst.exists():
                tmp_dst.unlink(missing_ok=True)

            cmd = Convert._build_convert_cmd(
                src=src,
                dst=tmp_dst,
                in_format=in_format,
                out_format=out_format,
                compress=compress,
                opt=opt,
            )

            logger.debug(f"[attempt {attempt_no}/{len(plan)}] opts: {opt.short()}")
            logger.debug(f"[attempt {attempt_no}/{len(plan)}] cmd:  {' '.join(cmd)}")

            try:
                rc, stderr_lines = Convert._run_convert_process(
                    logger,
                    cmd,
                    tmp_dst=tmp_dst,
                    virt_size=virt_size,
                    ui_poll_s=ui_poll_s,
                    progress_callback=progress_callback,
                )
            except KeyboardInterrupt:
                logger.warning("Interrupted; aborting conversion.")
                raise

            if rc == 0:
                if atomic:
                    tmp_dst.replace(final_dst)
                Convert._safe_progress_callback(progress_callback, 1.0, logger=logger)
                if stderr_lines:
                    logger.debug("qemu-img stderr (tail):\n" + "\n".join(stderr_lines[-80:]))
                return

            tail_lines = stderr_lines[-max_stderr_tail:] if stderr_lines else []
            tail = "\n".join(tail_lines) if tail_lines else ""

            match = Convert._RE_EXPECTED_FALLBACK.search(tail) if tail else None
            is_expected = match is not None

            if is_expected:
                snippet = Convert._extract_match_snippet(tail, match, radius=140)
                U.banner(logger, f"Fallback attempt {attempt_no}/{len(plan)} (options rejected)")
                logger.warning(f"Reason: {snippet}")
                logger.warning(f"Downgrading options. opts: {opt.short()}")
                if tail:
                    logger.debug("qemu-img stderr (tail):\n" + tail)
            else:
                logger.error(f"Conversion attempt {attempt_no} failed (rc={rc}). opts: {opt.short()}")
                if tail:
                    logger.error("qemu-img stderr (tail):\n" + tail)

            last_error = subprocess.CalledProcessError(rc, cmd)

        if atomic and tmp_dst.exists():
            try:
                tmp_dst.unlink()
            except Exception:
                pass
        assert last_error is not None
        raise last_error

    @staticmethod
    def convert_image(
        logger: logging.Logger,
        src: Path,
        dst: Path,
        *,
        out_format: str,
        compress: bool,
        compress_level: Optional[int] = None,
        in_format: Optional[str] = None,
    ) -> None:
        Convert.convert_image_with_progress(
            logger,
            src,
            dst,
            out_format=out_format,
            compress=compress,
            compress_level=compress_level,
            progress_callback=None,
            in_format=in_format,
        )

    @staticmethod
    def validate(logger: logging.Logger, path: Path) -> None:
        path = Convert._prefer_descriptor_for_flat(logger, Path(path))
        if not path.is_file():
            logger.warning(f"Image file not found for validation: {path}")
            return
        if U.which("qemu-img") is None:
            logger.warning("qemu-img not found, skipping validation.")
            return
        cmd = ["qemu-img", "check", str(path)]
        logger.debug(f"Executing validation command: {' '.join(cmd)}")
        cp = U.run_cmd(logger, cmd, check=False, capture=True)
        if cp.returncode == 0:
            logger.info("Image validation: OK (qemu-img check)")
        else:
            logger.warning("Image validation: WARNING (qemu-img check reported issues)")
            logger.debug(f"return code: {cp.returncode}")
            logger.debug("stdout:\n" + (cp.stdout or ""))
            logger.debug("stderr:\n" + (cp.stderr or ""))

    # ---------------------------------------------------------------------
    # Fallback Policy (deduped)
    # ---------------------------------------------------------------------

    @staticmethod
    def _fallback_plan(
        base: ConvertOptions,
        *,
        out_format: str,
        compress: bool,
    ) -> Iterable[ConvertOptions]:
        """
        Fast -> compatible ladder (deduplicated).
        """

        def key(o: Convert.ConvertOptions) -> tuple:
            return (
                o.cache_mode,
                o.threads,
                o.compression_type,
                o.compression_level,
                o.preallocation,
            )

        seen: set[tuple] = set()
        ordered: list[Convert.ConvertOptions] = []

        def emit(opt: Convert.ConvertOptions) -> None:
            k = key(opt)
            if k in seen:
                return
            seen.add(k)
            ordered.append(opt)

        emit(base)

        # Drop threads (-m)
        if base.threads:
            emit(
                Convert.ConvertOptions(
                    cache_mode=base.cache_mode,
                    threads=None,
                    compression_type=base.compression_type,
                    compression_level=base.compression_level,
                    preallocation=base.preallocation,
                )
            )

        # qcow2 compression ladder
        if out_format == "qcow2" and compress:
            if base.compression_type == "zstd":
                emit(
                    Convert.ConvertOptions(
                        cache_mode=base.cache_mode,
                        threads=None,
                        compression_type="zlib",
                        compression_level=base.compression_level,
                        preallocation=base.preallocation,
                    )
                )

            # omit compression_type
            emit(
                Convert.ConvertOptions(
                    cache_mode=base.cache_mode,
                    threads=None,
                    compression_type=None,
                    compression_level=base.compression_level,
                    preallocation=base.preallocation,
                )
            )

            # omit compression_level too
            if base.compression_level is not None:
                emit(
                    Convert.ConvertOptions(
                        cache_mode=base.cache_mode,
                        threads=None,
                        compression_type=None,
                        compression_level=None,
                        preallocation=base.preallocation,
                    )
                )

        # Disable cache flags (sometimes triggers weirdness)
        if base.cache_mode:
            emit(
                Convert.ConvertOptions(
                    cache_mode="",
                    threads=None,
                    compression_type=None if (out_format == "qcow2" and compress) else base.compression_type,
                    compression_level=None if (out_format == "qcow2" and compress) else base.compression_level,
                    preallocation=base.preallocation,
                )
            )

        # Final bare minimum
        emit(
            Convert.ConvertOptions(
                cache_mode="",
                threads=None,
                compression_type=None,
                compression_level=None,
                preallocation=None,
            )
        )

        for o in ordered:
            yield o

    # ---------------------------------------------------------------------
    # Core runner (progress + stderr capture)
    # ---------------------------------------------------------------------

    @staticmethod
    def _run_convert_process(
        logger: logging.Logger,
        cmd: list[str],
        *,
        tmp_dst: Path,
        virt_size: int,
        ui_poll_s: float,
        progress_callback: Optional[Callable[[float], None]],
        callback_min_delta: float = 0.001,  # 0.1%
        size_poll_s: float = 0.50,
    ) -> tuple[int, list[str]]:
        """
        Runs qemu-img convert with:
          - nonblocking stderr read (avoids readline blocking edge cases)
          - percent-based completion (robust even for sparse/compressed outputs)
          - BUT: if qemu-img percent is missing/delayed, we estimate percent from written bytes
                UNTIL the first real percent arrives (prevents "stuck at 0%" UX).
          - output-size polling as liveness + stats (not completion once real % exists)
          - drains stderr after exit so we don't miss the real error lines
          - parses drained lines too (so final % updates are seen)
          - opportunistic nonblocking read every loop when possible (reduces progress lag)
          - terminates qemu-img on Ctrl+C
        """
        start = time.time()
        stderr_lines: list[str] = []

        proc = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=False,
            bufsize=0,
        )
        assert proc.stderr is not None

        fd = proc.stderr.fileno()
        nonblocking_ok = False
        try:
            os.set_blocking(fd, False)
            nonblocking_ok = True
        except Exception:
            nonblocking_ok = False

        buf = b""

        def push_line(line_b: bytes) -> None:
            stderr_lines.append(line_b.decode("utf-8", errors="replace").rstrip("\n"))

        def read_available() -> int:
            nonlocal buf
            total = 0
            while True:
                try:
                    chunk = os.read(fd, 65536)
                except BlockingIOError:
                    return total
                except OSError:
                    return total
                if not chunk:
                    return total
                total += len(chunk)
                buf += chunk
                while True:
                    i = buf.find(b"\n")
                    if i < 0:
                        break
                    line = buf[: i + 1]
                    buf = buf[i + 1 :]
                    push_line(line)

        def drain_remaining() -> None:
            read_available()
            nonlocal buf
            if buf:
                push_line(buf)
                buf = b""

        last_seen_pct: Optional[float] = None
        best_pct = 0.0
        processed_lines = 0
        last_io_tick = time.time()

        def update_best(pct: float) -> None:
            nonlocal best_pct
            if pct > best_pct:
                best_pct = pct

        def parse_progress_pct(line: str) -> Optional[float]:
            s = (line or "").strip()
            if not s:
                return None

            if Convert._RE_JSON.match(s):
                try:
                    o = json.loads(s)
                    for k in ("progress", "percent", "pct"):
                        if k in o:
                            v = float(o[k])
                            return v if 0.0 <= v <= 100.0 else None
                except Exception:
                    return None

            m = Convert._RE_PAREN.search(s)
            if m:
                try:
                    return float(m.group(1))
                except Exception:
                    return None

            m = Convert._RE_FRACTION.search(s)
            if m:
                try:
                    v = float(m.group(1))
                    return v if 0.0 <= v <= 100.0 else None
                except Exception:
                    return None

            m = Convert._RE_PROGRESS.search(s)
            if m:
                try:
                    v = float(m.group(1))
                    return v if 0.0 <= v <= 100.0 else None
                except Exception:
                    return None

            m = Convert._RE_PERCENT.search(s)
            if m:
                try:
                    v = float(m.group(1))
                    return v if 0.0 <= v <= 100.0 else None
                except Exception:
                    return None

            return None

        def parse_new_lines() -> None:
            nonlocal processed_lines, last_seen_pct
            if processed_lines >= len(stderr_lines):
                return
            new_lines = stderr_lines[processed_lines:]
            processed_lines = len(stderr_lines)
            for line in new_lines:
                pct = parse_progress_pct(line)
                if pct is None:
                    continue
                last_seen_pct = pct
                update_best(pct)

        def tmp_written_bytes() -> Optional[int]:
            try:
                if not tmp_dst.exists():
                    return None
                return int(tmp_dst.stat().st_size)
            except Exception:
                return None

        def maybe_advance_pct_from_written(written_b: Optional[int]) -> None:
            """
            If qemu-img hasn't emitted % yet, use written bytes as a temporary estimate
            so the progressbar doesn't look stuck. Once we see real qemu % output,
            we stop using this estimate.
            """
            nonlocal best_pct
            if last_seen_pct is not None:
                return
            if virt_size <= 0 or written_b is None:
                return
            est = 100.0 * float(written_b) / float(virt_size)
            # Don't show 100% until rc==0
            if est > 99.0:
                est = 99.0
            if est > best_pct:
                best_pct = est

        last_cb_frac = -1.0

        def maybe_callback(frac: float) -> None:
            nonlocal last_cb_frac
            if progress_callback is None:
                return
            if last_cb_frac < 0:
                last_cb_frac = frac
                Convert._safe_progress_callback(progress_callback, frac, logger=logger)
                return
            if (frac - last_cb_frac) >= callback_min_delta:
                last_cb_frac = frac
                Convert._safe_progress_callback(progress_callback, frac, logger=logger)

        last_log_t = start
        last_log_pct = 0.0

        last_size_poll = 0.0
        cached_written: Optional[int] = None

        try:
            with selectors.DefaultSelector() as sel:
                sel.register(proc.stderr, selectors.EVENT_READ)

                with Progress(
                    TextColumn("{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    TimeElapsedColumn(),
                    TimeRemainingColumn(),
                ) as progress:
                    task = progress.add_task("Converting", total=100.0)

                    while True:
                        if nonblocking_ok:
                            n0 = read_available()
                            if n0 > 0:
                                last_io_tick = time.time()
                            parse_new_lines()

                        events = sel.select(timeout=ui_poll_s)
                        if events:
                            n = read_available()
                            if n > 0:
                                last_io_tick = time.time()
                            parse_new_lines()

                        now = time.time()
                        if (now - last_size_poll) >= size_poll_s:
                            cached_written = tmp_written_bytes()
                            last_size_poll = now

                        # ✅ keep bar moving until first real qemu %
                        maybe_advance_pct_from_written(cached_written)

                        progress.update(task, completed=best_pct)

                        silent_for = now - last_io_tick
                        written = cached_written

                        if last_seen_pct is not None:
                            if written is not None:
                                progress.update(
                                    task,
                                    description=(
                                        f"Converting (qemu-img {last_seen_pct:.1f}% | "
                                        f"written {written/1024/1024:.1f} MiB | quiet {silent_for:.1f}s)"
                                    ),
                                )
                            else:
                                progress.update(
                                    task,
                                    description=f"Converting (qemu-img {last_seen_pct:.1f}% | quiet {silent_for:.1f}s)",
                                )
                        else:
                            # No qemu % yet: be explicit that it's an estimate.
                            if written is not None:
                                progress.update(
                                    task,
                                    description=(
                                        f"Converting (estimating from written bytes | "
                                        f"written {written/1024/1024:.1f} MiB | quiet {silent_for:.1f}s)"
                                    ),
                                )
                            else:
                                progress.update(
                                    task,
                                    description=f"Converting (waiting for qemu-img % | stderr quiet {silent_for:.1f}s)",
                                )

                        if (now - last_log_t) >= 10.0 and best_pct > last_log_pct:
                            if virt_size > 0:
                                est_bytes = (best_pct / 100.0) * float(virt_size)
                                mb_s = (est_bytes / max(1e-6, (now - start))) / 1024 / 1024
                                logger.info(f"Conversion progress: {best_pct:.1f}% (~{mb_s:.1f} MB/s avg)")
                            else:
                                logger.info(f"Conversion progress: {best_pct:.1f}%")
                            last_log_t = now
                            last_log_pct = best_pct

                        maybe_callback(best_pct / 100.0)

                        if proc.poll() is not None:
                            break

                    rc = proc.wait()
                    drain_remaining()
                    parse_new_lines()

                    if rc == 0:
                        best_pct = 100.0
                        progress.update(task, completed=best_pct)
                        maybe_callback(1.0)

                    return rc, stderr_lines

        except KeyboardInterrupt:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=2.0)
                except Exception:
                    proc.kill()
            finally:
                try:
                    drain_remaining()
                    parse_new_lines()
                except Exception:
                    pass
                try:
                    proc.stderr.close()
                except Exception:
                    pass
            raise

        finally:
            try:
                if proc.poll() is not None:
                    drain_remaining()
            except Exception:
                pass
            try:
                proc.stderr.close()
            except Exception:
                pass

    # ---------------------------------------------------------------------
    # Cmd builder / helpers
    # ---------------------------------------------------------------------

    @staticmethod
    def _build_convert_cmd(
        *,
        src: Path,
        dst: Path,
        in_format: Optional[str],
        out_format: str,
        compress: bool,
        opt: ConvertOptions,
    ) -> list[str]:
        cmd: list[str] = ["qemu-img", "convert", "-p"]

        if opt.cache_mode:
            cmd += ["-t", opt.cache_mode, "-T", opt.cache_mode]

        if opt.threads and opt.threads > 0:
            cmd += ["-m", str(int(opt.threads))]

        if in_format:
            cmd += ["-f", in_format]

        cmd += ["-O", out_format]

        if out_format == "qcow2":
            opts: list[str] = []
            if opt.preallocation:
                opts.append(f"preallocation={opt.preallocation}")

            if compress:
                cmd.append("-c")
                if opt.compression_type:
                    opts.append(f"compression_type={opt.compression_type}")
                if opt.compression_level is not None:
                    opts.append(f"compression_level={int(opt.compression_level)}")

            if opts:
                cmd += ["-o", ",".join(opts)]

        cmd += [str(src), str(dst)]
        return cmd

    @staticmethod
    def _prefer_descriptor_for_flat(logger: logging.Logger, src: Path) -> Path:
        s = str(src)
        if s.endswith("-flat.vmdk"):
            descriptor = src.with_name(src.name.replace("-flat.vmdk", ".vmdk"))
            if descriptor.is_file():
                logger.info(f"Detected flat VMDK; using descriptor: {descriptor}")
                return descriptor
        return src

    @staticmethod
    def _qemu_img_info(logger: logging.Logger, src: Path) -> Tuple[int, Optional[str]]:
        info_cmd = ["qemu-img", "info", "--output=json", str(src)]
        logger.debug(f"Executing info command: {' '.join(info_cmd)}")
        try:
            info_result = subprocess.run(info_cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "").strip()
            stdout = (e.stdout or "").strip()
            msg = f"qemu-img info failed for {src}"
            if stderr:
                msg += f": {stderr}"
            elif stdout:
                msg += f": {stdout}"
            raise RuntimeError(msg) from e

        try:
            info = json.loads(info_result.stdout or "{}")
        except Exception as e:
            raise RuntimeError(f"qemu-img info returned non-JSON for {src}") from e

        virt = int(info.get("virtual-size", 0) or 0)
        fmt = info.get("format")
        if fmt is not None and not isinstance(fmt, str):
            fmt = None
        return virt, fmt

    # ---------------------------------------------------------------------
    # Small helpers
    # ---------------------------------------------------------------------

    @staticmethod
    def _safe_progress_callback(
        cb: Optional[Callable[[float], None]],
        frac: float,
        *,
        logger: logging.Logger,
    ) -> None:
        if cb is None:
            return
        try:
            cb(max(0.0, min(1.0, frac)))
        except Exception as e:
            logger.debug(f"progress_callback raised: {e}")

    @staticmethod
    def _extract_match_snippet(text: str, match: re.Match[str], *, radius: int = 140) -> str:
        """
        Extract a compact snippet around a regex match for UX logs.

        - Collapses whitespace
        - Adds "…" when truncated
        """
        if not text:
            return ""
        s = text.replace("\r", "\n")
        start = max(0, match.start() - radius)
        end = min(len(s), match.end() + radius)
        snippet = s[start:end]
        snippet = " ".join(snippet.split())
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(s) else ""
        return f"{prefix}{snippet}{suffix}"
