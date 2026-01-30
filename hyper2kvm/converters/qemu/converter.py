# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/converters/qemu/converter.py
from __future__ import annotations

import json
import logging
import os
import re
import selectors
import subprocess
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from ...core.utils import U


class Convert:
    """
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
        threads: int | None = None  # -m N
        compression_type: str | None = "zstd"  # zstd|zlib|None (omit)
        compression_level: int | None = None  # compression_level=...
        preallocation: str | None = None  # preallocation=metadata, ...

        def short(self) -> str:
            return (
                f"cache={self.cache_mode or 'off'} "
                f"threads={self.threads or 'off'} "
                f"ctype={self.compression_type or 'omit'} "
                f"clevel={self.compression_level if self.compression_level is not None else 'omit'} "
                f"prealloc={self.preallocation or 'omit'}"
            )

    # Public API

    @staticmethod
    def convert_image_with_progress(
        logger: logging.Logger,
        src: Path,
        dst: Path,
        *,
        out_format: str,
        compress: bool,
        compress_level: int | None = None,
        compression_type: str | None = "zstd",
        progress_callback: Callable[[float], None] | None = None,
        in_format: str | None = None,
        preallocation: str | None = None,
        atomic: bool = True,
        cache_mode: str = "none",
        threads: int | None = None,
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

        last_error: subprocess.CalledProcessError | None = None

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
            logger.debug(f"[attempt {attempt_no}/{len(plan)}] cmd: {' '.join(cmd)}")

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
        if last_error is None:
            raise RuntimeError("Conversion failed but error not captured")
        raise last_error

    @staticmethod
    def convert_image(
        logger: logging.Logger,
        src: Path,
        dst: Path,
        *,
        out_format: str,
        compress: bool,
        compress_level: int | None = None,
        in_format: str | None = None,
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

    # Fallback Policy (deduped)

    @staticmethod
    def _fallback_plan(
        base: ConvertOptions,
        *,
        out_format: str,
        compress: bool,
    ) -> Iterable[ConvertOptions]:
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

            emit(
                Convert.ConvertOptions(
                    cache_mode=base.cache_mode,
                    threads=None,
                    compression_type=None,
                    compression_level=base.compression_level,
                    preallocation=base.preallocation,
                )
            )

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

        emit(
            Convert.ConvertOptions(
                cache_mode="",
                threads=None,
                compression_type=None,
                compression_level=None,
                preallocation=None,
            )
        )

        yield from ordered

    # Core runner (progress + stderr capture)

    @staticmethod
    def _run_convert_process(
        logger: logging.Logger,
        cmd: list[str],
        *,
        tmp_dst: Path,
        virt_size: int,
        ui_poll_s: float,
        progress_callback: Callable[[float], None] | None,
        callback_min_delta: float = 0.001,  # 0.1%
        size_poll_s: float = 0.50,
        log_every_s: float = 30.0,  # liveness logging even if % flat (non-interactive)
        ui_desc_every_s: float = 2.0,  # throttle description changes
        ui_desc_min_step_pct: float = 0.5,  # throttle description changes on tiny pct changes
        ui_max_refresh_hz: float = 4.0,  # cap Rich redraw rate
    ) -> tuple[int, list[str]]:
        start = time.time()
        stderr_lines: list[str] = []

        # If we're not attached to an interactive terminal, Rich live redraw often turns into spam.
        interactive = bool(sys.stderr.isatty() and sys.stdout.isatty())

        proc = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=False,
            bufsize=0,
        )
        if proc.stderr is None:
            raise RuntimeError("Process stderr unexpectedly None")

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

        last_seen_pct: float | None = None
        best_pct = 0.0
        processed_lines = 0
        last_io_tick = time.time()

        saw_real_pct = False
        just_snapped_to_truth = False  # one-shot event flag

        def clamp_pct(p: float) -> float:
            # NaN-safe clamp
            if p != p:
                return 0.0
            return max(0.0, min(100.0, p))

        def update_best(pct: float) -> None:
            nonlocal best_pct
            pct = clamp_pct(pct)
            if pct > best_pct:
                best_pct = pct

        def parse_progress_pct(line: str) -> float | None:
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

            # Tightened bare "NN%" parsing: require strong progress-ish context
            ss = s.lower()
            looks_like_progress = (
                "progress" in ss
                or "converting" in ss
                or "converted" in ss
                or "copying" in ss
                or "copied" in ss
            )
            if looks_like_progress:
                m = Convert._RE_PERCENT.search(s)
                if m:
                    try:
                        v = float(m.group(1))
                        return v if 0.0 <= v <= 100.0 else None
                    except Exception:
                        return None

            return None

        def parse_new_lines() -> None:
            nonlocal processed_lines, last_seen_pct, saw_real_pct, best_pct, just_snapped_to_truth
            if processed_lines >= len(stderr_lines):
                return
            new_lines = stderr_lines[processed_lines:]
            processed_lines = len(stderr_lines)
            for line in new_lines:
                pct = parse_progress_pct(line)
                if pct is None:
                    continue
                pct = clamp_pct(pct)
                last_seen_pct = pct
                if not saw_real_pct:
                    best_pct = pct  # snap to truth once
                    saw_real_pct = True
                    just_snapped_to_truth = True
                else:
                    update_best(pct)

        def tmp_written_bytes() -> int | None:
            try:
                if not tmp_dst.exists():
                    return None
                return int(tmp_dst.stat().st_size)
            except Exception:
                return None

        def maybe_advance_pct_from_written(written_b: int | None) -> None:
            nonlocal best_pct
            if last_seen_pct is not None:
                return
            if virt_size <= 0 or written_b is None:
                return
            est = 100.0 * float(written_b) / float(virt_size)
            # never claim "done" from file size; qemu may still be finishing metadata
            if est > 99.0:
                est = 99.0
            best_pct = max(best_pct, clamp_pct(est))

        last_cb_frac = -1.0

        def maybe_callback(frac: float) -> None:
            nonlocal last_cb_frac
            if progress_callback is None:
                return
            frac = max(0.0, min(1.0, frac))
            if last_cb_frac < 0:
                last_cb_frac = frac
                Convert._safe_progress_callback(progress_callback, frac, logger=logger)
                return
            if (frac - last_cb_frac) >= callback_min_delta:
                last_cb_frac = frac
                Convert._safe_progress_callback(progress_callback, frac, logger=logger)

        last_size_poll = 0.0
        cached_written: int | None = None

        # --- dynamic log throttling (prevents spam while Rich is live) ---
        last_emit_t = start
        last_emit_pct = 0.0

        def _clamp(v: float, lo: float, hi: float) -> float:
            return max(lo, min(hi, v))

        def should_emit_progress(now: float) -> bool:
            nonlocal last_emit_t, last_emit_pct

            base_target_s = 20.0 if interactive else 45.0
            max_silence_s = 60.0 if interactive else 120.0

            dt = max(1e-6, now - last_emit_t)
            dp = max(0.0, best_pct - last_emit_pct)
            pct_rate = dp / dt  # % per second since last emit

            dyn_min_delta = _clamp(pct_rate * base_target_s, 0.5, 5.0)

            time_due = (now - last_emit_t) >= base_target_s
            progressed_enough = (best_pct - last_emit_pct) >= dyn_min_delta
            too_silent = (now - last_emit_t) >= max_silence_s

            if (time_due and progressed_enough) or too_silent:
                last_emit_t = now
                last_emit_pct = best_pct
                return True
            return False

        def poll_io(sel: selectors.BaseSelector) -> None:
            nonlocal last_io_tick
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

        def update_caches(now: float) -> None:
            nonlocal last_size_poll, cached_written
            if (now - last_size_poll) >= size_poll_s:
                cached_written = tmp_written_bytes()
                last_size_poll = now

        def compute_best(now: float) -> None:
            nonlocal best_pct, just_snapped_to_truth, last_emit_t, last_emit_pct
            maybe_advance_pct_from_written(cached_written)
            best_pct = clamp_pct(best_pct)

            if just_snapped_to_truth:
                logger.info("qemu-img progress detected; switching from estimation to true percent reporting.")
                # Reset emit gate so we don't immediately spam after snapping.
                last_emit_t = now
                last_emit_pct = best_pct
                just_snapped_to_truth = False

        def log_progress(now: float) -> None:
            nonlocal last_emit_t, last_emit_pct

            # Interactive: bar/spinner is the UI; keep logs rare.
            if interactive and not should_emit_progress(now):
                return

            # Non-interactive: gentle heartbeat regardless.
            if (not interactive) and (now - last_emit_t) < log_every_s:
                return

            if virt_size > 0 and last_seen_pct is not None:
                pct_for_rate = last_seen_pct  # truth-phase
                est_bytes = (pct_for_rate / 100.0) * float(virt_size)
                mb_s = (est_bytes / max(1e-6, (now - start))) / 1024 / 1024
                logger.info(f"⏳ Conversion progress: {best_pct:.1f}% (~{mb_s:.1f} MB/s avg)")
            else:
                # In estimation/unknown phase: keep this line short (avoid noise)
                logger.info(f"⏳ Conversion progress: {best_pct:.1f}%")

            # Keep emit state aligned for both modes.
            last_emit_t = now
            last_emit_pct = best_pct

        try:
            with selectors.DefaultSelector() as sel:
                sel.register(proc.stderr, selectors.EVENT_READ)

                # Non-interactive mode: NO Rich progress bar.
                if not interactive:
                    while True:
                        poll_io(sel)
                        now = time.time()
                        update_caches(now)
                        compute_best(now)
                        log_progress(now)
                        maybe_callback(best_pct / 100.0)
                        if proc.poll() is not None:
                            break

                    rc = proc.wait()
                    drain_remaining()
                    parse_new_lines()
                    if rc == 0:
                        best_pct = 100.0
                        maybe_callback(1.0)
                    return rc, stderr_lines

                # Interactive mode: Rich spinner until qemu-img emits real %, then progress bar.
                refresh_per_second = max(1, int(_clamp(ui_max_refresh_hz, 1.0, 20.0)))

                with Progress(
                    SpinnerColumn(),
                    TextColumn("{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    TimeElapsedColumn(),
                    TimeRemainingColumn(),
                    refresh_per_second=refresh_per_second,
                ) as progress:
                    spinner_task = progress.add_task("Converting (waiting for qemu-img)", total=None, start=True)
                    bar_task = progress.add_task("Converting", total=100.0, start=False)

                    last_desc_t = 0.0
                    last_desc_pct = -999.0
                    last_desc_phase = ""

                    bar_started = False

                    def maybe_update_desc(now: float) -> None:
                        nonlocal last_desc_t, last_desc_pct, last_desc_phase
                        phase = "qemu-img" if last_seen_pct is not None else "estimating"
                        if (
                            (now - last_desc_t) < ui_desc_every_s
                            and abs(best_pct - last_desc_pct) < ui_desc_min_step_pct
                            and phase == last_desc_phase
                        ):
                            return
                        last_desc_t = now
                        last_desc_pct = best_pct
                        last_desc_phase = phase

                        if not bar_started:
                            # Keep spinner message short and honest
                            progress.update(spinner_task, description="Converting (waiting for qemu-img)")
                        else:
                            progress.update(bar_task, description="Converting")

                    while True:
                        poll_io(sel)
                        now = time.time()
                        update_caches(now)
                        compute_best(now)

                        # Switch UI mode once, when real qemu-img percent arrives.
                        if (not bar_started) and (last_seen_pct is not None):
                            bar_started = True
                            progress.stop_task(spinner_task)
                            progress.start_task(bar_task)
                            progress.update(bar_task, completed=best_pct)

                        if bar_started:
                            progress.update(bar_task, completed=best_pct)
                        else:
                            # Spinner phase: nothing to "complete"
                            progress.update(spinner_task)

                        maybe_update_desc(now)

                        log_progress(now)
                        maybe_callback(best_pct / 100.0)

                        if proc.poll() is not None:
                            break

                    rc = proc.wait()
                    drain_remaining()
                    parse_new_lines()

                    if rc == 0:
                        best_pct = 100.0
                        if bar_started:
                            progress.update(bar_task, completed=best_pct)
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

    # Cmd builder / helpers

    @staticmethod
    def _build_convert_cmd(
        *,
        src: Path,
        dst: Path,
        in_format: str | None,
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
    def _qemu_img_info(logger: logging.Logger, src: Path) -> tuple[int, str | None]:
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

    # Small helpers

    @staticmethod
    def _safe_progress_callback(
        cb: Callable[[float], None] | None,
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
