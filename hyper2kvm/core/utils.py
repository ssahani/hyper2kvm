# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/utils.py
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import os
import shlex
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .exceptions import Fatal

if TYPE_CHECKING:  # pragma: no cover
    import guestfs  # type: ignore

try:
    from rich.progress import (
        BarColumn,
        Progress,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
    )
except Exception:  # pragma: no cover
    Progress = None  # type: ignore


class U:
    @staticmethod
    def die(logger: logging.Logger | None, msg: str, code: int = 1) -> None:
        if logger:
            logger.error(msg)
        raise Fatal(code, msg)

    @staticmethod
    def ensure_dir(p: Path) -> None:
        p.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def which(prog: str) -> str | None:
        from shutil import which as _which
        return _which(prog)

    @staticmethod
    def now_ts() -> str:
        return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")

    @staticmethod
    def json_dump(obj: Any) -> str:
        try:
            return json.dumps(obj, indent=2, sort_keys=True, default=str)
        except Exception:
            return repr(obj)

    @staticmethod
    def human_bytes(n: int | None) -> str:
        if n is None:
            return "unknown"
        x = float(n)
        for unit in ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]:
            if x < 1024 or unit == "PiB":
                return f"{x:.2f} {unit}" if unit != "B" else f"{int(x)} {unit}"
            x /= 1024
        return f"{n} B"

    @staticmethod
    def banner(logger: logging.Logger | None, title: str) -> None:
        if not logger:
            return
        line = "─" * max(10, len(title) + 2)
        logger.info(line)
        logger.info(f" {title}")
        logger.info(line)

    @staticmethod
    def _pretty_cmd(cmd: list[str]) -> str:
        return " ".join(shlex.quote(x) for x in cmd)

    @staticmethod
    def run_cmd(
        logger: logging.Logger,
        cmd: list[str],
        *,
        check: bool = True,
        capture: bool = False,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
        cwd: str | Path | None = None,
        input_text: str | None = None,
        stream: bool = False,
        fatal: bool = False,
        failure_log_level: int | None = None,
    ) -> subprocess.CompletedProcess:
        """
        Run a command.

        - capture=True uses subprocess.run(capture_output=True, text=True)
        - stream=True streams stdout/stderr to logger in realtime (forces capture=False)
        - fatal=True wraps failures into Fatal (otherwise re-raises subprocess exceptions)
        - failure_log_level=level controls log level for failures (default: ERROR, can be WARNING or DEBUG)
        """
        pretty = U._pretty_cmd(cmd)
        logger.debug("Running: %s", pretty)

        try:
            if stream:
                # Realtime streaming (best for long qemu-img/qemu-nbd etc)
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                    cwd=str(cwd) if cwd is not None else None,
                )
                if proc.stdout is None:
                    raise RuntimeError("Process stdout unexpectedly None")
                out_lines: list[str] = []
                for line in proc.stdout:
                    line = line.rstrip("\n")
                    out_lines.append(line)
                    logger.info(line)
                rc = proc.wait(timeout=timeout)
                stdout = "\n".join(out_lines) if out_lines else ""
                cp = subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr="")
                if check and rc != 0:
                    raise subprocess.CalledProcessError(rc, cmd, output=stdout, stderr="")
                return cp

            # Non-streaming path
            cp = subprocess.run(
                cmd,
                check=check,
                capture_output=capture,
                text=True,
                env=env,
                timeout=timeout,
                cwd=str(cwd) if cwd is not None else None,
                input=input_text,
            )
            return cp

        except subprocess.CalledProcessError as e:
            stdout = (e.stdout or e.output or "").strip()
            stderr = (e.stderr or "").strip()

            # Determine log level: use failure_log_level if specified, otherwise ERROR
            log_level = failure_log_level if failure_log_level is not None else logging.ERROR

            # Only log if not DEBUG level or if logger is at DEBUG level
            if log_level != logging.DEBUG or logger.isEnabledFor(logging.DEBUG):
                if stdout or stderr:
                    logger.log(
                        log_level,
                        "Command failed: %s%s%s",
                        pretty,
                        f"\nstdout:\n{stdout}" if stdout else "",
                        f"\nstderr:\n{stderr}" if stderr else "",
                    )
                else:
                    logger.log(log_level, "Command failed: %s (no output)", pretty)

            if fatal:
                raise Fatal(e.returncode or 1, f"Command failed: {pretty}") from e
            raise

        except subprocess.TimeoutExpired as e:
            logger.error("Command timed out: %s (timeout=%ss)", pretty, timeout)
            if fatal:
                raise Fatal(124, f"Command timed out: {pretty}") from e
            raise

        except Exception as e:
            logger.error("Command error: %s (%s)", pretty, e)
            if fatal:
                raise Fatal(1, f"Command error: {pretty}: {e}") from e
            raise

    @staticmethod
    def require_root_if_needed(logger: logging.Logger, write_actions: bool) -> None:
        if not write_actions:
            return
        if os.geteuid() != 0:
            U.die(logger, "This operation requires root. Re-run with sudo.", 1)

    @staticmethod
    def checksum(path: Path, algo: str = "sha256") -> str:
        h = hashlib.new(algo)
        total_size = path.stat().st_size
        chunk = 1024 * 1024

        def _iter_blocks(f) -> Iterable[bytes]:
            while True:
                b = f.read(chunk)
                if not b:
                    break
                yield b

        # If Rich isn't available or not a TTY, do it quietly.
        rich_ok = Progress is not None and getattr(__import__("sys").stderr, "isatty", lambda: False)()

        if not rich_ok:
            with open(path, "rb") as f:
                for blk in _iter_blocks(f):
                    h.update(blk)
            return h.hexdigest()

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TransferSpeedColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Computing checksum", total=total_size)
            with open(path, "rb") as f:
                for blk in _iter_blocks(f):
                    h.update(blk)
                    progress.update(task, advance=len(blk))
        return h.hexdigest()

    @staticmethod
    def safe_unlink(p: Path, *, missing_ok: bool = True) -> None:
        try:
            p.unlink()
        except FileNotFoundError:
            if not missing_ok:
                raise
        except Exception:
            # deliberately quiet (callers can log if they care)
            pass

    @staticmethod
    def to_text(x: Any) -> str:
        if x is None:
            return ""
        if isinstance(x, bytes):
            return x.decode("utf-8", "replace")
        return str(x)

    @staticmethod
    def human_to_bytes(s: str) -> int:
        """
        Parse human sizes:
          - "10G", "10GiB", "10GB"
          - "512M", "512MiB"
          - "1024" (bytes)
        """
        raw = s.strip()
        if not raw:
            raise ValueError("empty size")

        t = raw.upper().replace(" ", "")
        # normalize common suffixes
        t = t.replace("KIB", "KI").replace("MIB", "MI").replace("GIB", "GI").replace("TIB", "TI").replace("PIB", "PI")
        t = t.replace("KB", "K").replace("MB", "M").replace("GB", "G").replace("TB", "T").replace("PB", "P")
        t = t.rstrip("B")

        multipliers = {
            "": 1,
            "K": 1024,
            "KI": 1024,
            "M": 1024**2,
            "MI": 1024**2,
            "G": 1024**3,
            "GI": 1024**3,
            "T": 1024**4,
            "TI": 1024**4,
            "P": 1024**5,
            "PI": 1024**5,
        }

        # split numeric and suffix
        num = ""
        suf = ""
        for i, ch in enumerate(t):
            if (ch.isdigit() or ch == "." or ch == "-"):
                num += ch
            else:
                suf = t[i:]
                break

        if suf not in multipliers:
            raise ValueError(f"unknown size suffix: {suf!r} in {raw!r}")

        return int(float(num) * multipliers[suf])


def guest_has_cmd(g: guestfs.GuestFS, cmd: str) -> bool:
    """
    Replacement for g.available() checks.
    Uses a shell inside the appliance in a way that avoids injection.

    Note: Uses command_quiet() if available (VMCraft) to suppress error logging
    since these checks often fail (e.g., checking for mdadm/zpool in minimal guests).
    """
    try:
        # Pass cmd as $1 so it isn't interpolated into the shell string.
        # Use command_quiet if available (VMCraft) to suppress error logging for expected failures
        if hasattr(g, 'command_quiet'):
            out = g.command_quiet([
                "sh", "-lc",
                'command -v "$1" >/dev/null 2>&1 && echo YES || echo NO',
                "sh", cmd,
            ])
        else:
            out = g.command([
                "sh", "-lc",
                'command -v "$1" >/dev/null 2>&1 && echo YES || echo NO',
                "sh", cmd,
            ])
        return U.to_text(out).strip() == "YES"
    except Exception:
        return False


def guest_ls_glob(g: guestfs.GuestFS, pattern: str) -> list[str]:
    """
    Replacement for g.glob().
    Uses shell glob expansion but passes pattern as an argument to avoid injection.

    NOTE: Still depends on shell glob semantics; returns matches that exist.
    """
    try:
        # We want glob expansion, but we don't want pattern injection.
        # So: eval "set -- $pat" where $pat is *data*.
        # Then print each resolved path safely.
        script = r'''
pat="$1"
# Expand globs into positional params:
# shellcheck disable=SC2086
eval "set -- $pat"
# If no matches, set -- will keep literal pat; guard with -e checks.
for p in "$@"; do
  [ -e "$p" ] && printf '%s\n' "$p"
done
'''
        # Use command_quiet if available (VMCraft) to suppress error logging for expected failures
        if hasattr(g, 'command_quiet'):
            out = g.command_quiet(["sh", "-lc", script, "sh", pattern])
        else:
            out = g.command(["sh", "-lc", script, "sh", pattern])

        lines = [ln.strip() for ln in U.to_text(out).splitlines() if ln.strip()]
        # extra paranoia: verify inside guestfs API
        res: list[str] = []
        for p in lines:
            try:
                if g.is_file(p) or g.is_dir(p):
                    res.append(p)
            except Exception:
                pass
        return res
    except Exception:
        return []


def blinking_progress(logger: logging.Logger, label: str, interval: float = 0.12):
    """Tiny spinner context manager for long-running external commands.
    Avoids drawing if stderr isn't a TTY (so CI logs don't become hieroglyphs).
    """
    import contextlib
    import itertools
    import sys
    import threading
    import time

    @contextlib.contextmanager
    def _cm():
        is_tty = getattr(sys.stderr, "isatty", lambda: False)()
        if not is_tty:
            logger.debug("%s ...", label)
            yield
            logger.debug("%s done", label)
            return

        stop = threading.Event()
        spinner = itertools.cycle(["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"])

        def run():
            while not stop.is_set():
                ch = next(spinner)
                sys.stderr.write(f"\r{ch} {label}")
                sys.stderr.flush()
                time.sleep(interval)
            sys.stderr.write(f"\r✅ {label}\n")
            sys.stderr.flush()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        try:
            yield
        finally:
            stop.set()
            t.join(timeout=1.0)

    return _cm()
