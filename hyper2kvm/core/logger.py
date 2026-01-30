# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/logger.py
from __future__ import annotations

import datetime as _dt
import json
import logging
import multiprocessing as _mp
import os
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..vmware.utils.utils import is_tty

# Optional: colors
try:
    from termcolor import colored as _colored  # type: ignore
except Exception:  # pragma: no cover
    _colored = None

# TRACE level (additive)

TRACE = 5
if not hasattr(logging, "TRACE"):
    logging.TRACE = TRACE  # type: ignore[attr-defined]
    logging.addLevelName(TRACE, "TRACE")


def _logger_trace(self: logging.Logger, msg: str, *args, **kwargs) -> None:
    if self.isEnabledFor(TRACE):
        self._log(TRACE, msg, args, **kwargs)


if not hasattr(logging.Logger, "trace"):
    logging.Logger.trace = _logger_trace  # type: ignore[attr-defined]

_LEVEL_EMOJI = {
    "TRACE": "🧬",
    "DEBUG": "🔍",
    "INFO": "✅",
    "WARNING": "⚠️",
    "ERROR": "💥",
    "CRITICAL": "🧨",
}
_LEVEL_COLOR = {
    "TRACE": "cyan",
    "DEBUG": "blue",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "red",
}


def _is_tty() -> bool:
    """Check if stderr is a TTY (for logging output)."""
    return is_tty(sys.stderr)


def _supports_unicode() -> bool:
    """
    Best-effort check: if the stream encoding can't handle emoji, degrade gracefully.
    """
    try:
        enc = getattr(sys.stderr, "encoding", None) or "utf-8"
        "✅".encode(enc)
        return True
    except Exception:
        return False


def c(
    text: str,
    color: str | None = None,
    attrs: list[str] | None = None,
    *,
    enable: bool = True,
) -> str:
    """Colorize text if termcolor is available and enabled."""
    if not enable or _colored is None or not color:
        return text
    try:
        return _colored(text, color=color, attrs=attrs or [])
    except Exception:
        return text


# Context helpers

Ctx = Mapping[str, Any]


def _safe_str(v: Any, *, max_len: int = 240) -> str:
    try:
        s = str(v)
    except Exception:
        s = repr(v)
    s = s.replace("\n", "\\n").replace("\r", "\\r")
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s


def _merge_ctx(base: Ctx | None, extra: Ctx | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if base:
        out.update(dict(base))
    if extra:
        out.update(dict(extra))
    return out


def _format_ctx_kv(ctx: Ctx | None) -> str:
    if not ctx:
        return ""
    try:
        items = sorted(ctx.items(), key=lambda kv: str(kv[0]))
    except Exception:
        items = list(ctx.items())
    parts: list[str] = []
    for k, v in items:
        key = _safe_str(k, max_len=80)
        parts.append(f"{key}={_safe_str(v)}")
    return " " + " ".join(parts) if parts else ""


class ContextLoggerAdapter(logging.LoggerAdapter):
    """
    LoggerAdapter that carries a persistent context dict.
    Call sites can also pass `extra={"ctx": {...}}` which merges on top.

    Usage:
      log = Log.bind(logger, vm="win10", stage="export")
      log.info("Starting")
      log.error("Failed", extra={"ctx": {"disk": 2}})
    """

    def __init__(self, logger: logging.Logger, ctx: Ctx | None = None):
        super().__init__(logger, extra={"ctx": dict(ctx or {})})

    def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        extra = kwargs.get("extra") or {}
        call_ctx = extra.get("ctx")
        merged = _merge_ctx(self.extra.get("ctx"), call_ctx)
        extra["ctx"] = merged
        kwargs["extra"] = extra
        return msg, kwargs

    def bind(self, **ctx: Any) -> ContextLoggerAdapter:
        merged = _merge_ctx(self.extra.get("ctx"), ctx)
        return ContextLoggerAdapter(self.logger, merged)


# Style (process-first; no thread support)

@dataclass(frozen=True)
class LogStyle:
    color: bool = True
    show_ms: bool = False
    show_src: bool = False  # module:line
    show_pid: bool = False
    show_ppid: bool = False
    show_proc: bool = True  # process name (multiprocessing)
    show_logger: bool = False  # logger name
    utc: bool = False
    indent_exceptions: bool = True
    exception_indent: int = 2
    align_level: int = 8  # width for level alignment (INFO/WARN/etc)
    unicode: bool = True  # emoji/unicode decorations
    progress_safe: bool = True  # keep output line-based + non-fancy


class EmojiFormatter(logging.Formatter):
    def __init__(self, style: LogStyle):
        super().__init__()
        self._style = style

    def _now(self, created: float) -> str:
        dt = (
            _dt.datetime.fromtimestamp(created, tz=_dt.timezone.utc)
            if self._style.utc
            else _dt.datetime.fromtimestamp(created)
        )
        return dt.strftime("%H:%M:%S.%f")[:-3] if self._style.show_ms else dt.strftime("%H:%M:%S")

    def _emoji(self, levelname: str) -> str:
        if not self._style.unicode:
            return "·"
        return _LEVEL_EMOJI.get(levelname, "•")

    def _prefix_bits(self, record: logging.LogRecord) -> str:
        bits: list[str] = []

        if self._style.show_pid:
            bits.append(f"pid={os.getpid()}")

        if self._style.show_ppid:
            try:
                bits.append(f"ppid={os.getppid()}")
            except Exception:
                bits.append("ppid=?")

        if self._style.show_proc:
            try:
                bits.append(f"proc={_mp.current_process().name}")
            except Exception:
                bits.append("proc=?")

        if self._style.show_logger:
            bits.append(record.name)

        if self._style.show_src:
            bits.append(f"{record.module}:{record.lineno}")

        return (" [" + " ".join(bits) + "]") if bits else ""

    def _format_exception_block(self, record: logging.LogRecord, color_ok: bool) -> str:
        # Exception info
        exc_text = self.formatException(record.exc_info) if record.exc_info else ""
        # stack_info support
        stack_text = record.stack_info if getattr(record, "stack_info", None) else ""
        if not exc_text and not stack_text:
            return ""

        parts: list[str] = []
        if exc_text:
            parts.append(exc_text)
        if stack_text:
            parts.append(stack_text)

        block_text = "\n".join(parts)

        if not self._style.indent_exceptions:
            out = "\n" + block_text
            return c(out, "red", enable=color_ok) if (color_ok and exc_text) else out

        indent = " " * max(0, int(self._style.exception_indent))
        lines = block_text.splitlines()
        indented = "\n".join(indent + ln for ln in lines)
        if color_ok and exc_text:
            indented = c(indented, "red", enable=True)
        return "\n" + indented

    def format(self, record: logging.LogRecord) -> str:
        ts = self._now(record.created)
        emoji = self._emoji(record.levelname)

        lvl = record.levelname
        msg = record.getMessage()

        color_ok = bool(self._style.color and _is_tty() and _colored is not None)

        lvl = c(lvl, _LEVEL_COLOR.get(record.levelname), enable=color_ok)
        if record.levelno >= logging.WARNING:
            msg = c(msg, _LEVEL_COLOR.get(record.levelname), attrs=["bold"], enable=color_ok)

        bits = self._prefix_bits(record)

        # Context (from adapter or `extra={"ctx": ...}`)
        ctx = getattr(record, "ctx", None)
        ctx_s = _format_ctx_kv(ctx)

        line = f"{ts} {emoji} {lvl:<{self._style.align_level}}{bits} {msg}{ctx_s}"
        line += self._format_exception_block(record, color_ok)
        return line


class JsonFormatter(logging.Formatter):
    """
    NDJSON formatter (one JSON object per line), good for CI/log shipping.

    Includes:
      ts (ISO8601), level, logger, msg, pid, ppid, proc, module, lineno, ctx
      plus exception fields when present.
    """

    def __init__(self, *, utc: bool = True, include_src: bool = True):
        super().__init__()
        self._utc = bool(utc)
        self._include_src = bool(include_src)

    def _iso(self, created: float) -> str:
        dt = _dt.datetime.fromtimestamp(created, tz=_dt.timezone.utc) if self._utc else _dt.datetime.fromtimestamp(created)
        return dt.isoformat(timespec="milliseconds")

    def format(self, record: logging.LogRecord) -> str:
        try:
            proc_name = _mp.current_process().name
        except Exception:
            proc_name = "?"

        try:
            ppid = os.getppid()
        except Exception:
            ppid = None

        obj: dict[str, Any] = {
            "ts": self._iso(record.created),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "pid": os.getpid(),
            "ppid": ppid,
            "proc": proc_name,
        }
        if self._include_src:
            obj.update({"module": record.module, "lineno": record.lineno})

        ctx = getattr(record, "ctx", None)
        if ctx:
            try:
                obj["ctx"] = dict(ctx)
            except Exception:
                obj["ctx"] = {"_ctx": _safe_str(ctx)}

        if record.exc_info:
            try:
                et = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
            except Exception:
                et = "Exception"
            obj["exc_type"] = et
            obj["traceback"] = self.formatException(record.exc_info)

        if getattr(record, "stack_info", None):
            obj["stack_info"] = record.stack_info

        try:
            return json.dumps(obj, ensure_ascii=False, sort_keys=False)
        except Exception:
            safe_obj = {k: _safe_str(v) for k, v in obj.items()}
            return json.dumps(safe_obj, ensure_ascii=False, sort_keys=False)


# Once / rate-limited warnings (per-process, by design)

_warn_once_keys: set[str] = set()
_warn_last: dict[str, float] = {}


def _warn_key(key: str | tuple[Any, ...]) -> str:
    if isinstance(key, str):
        return key
    try:
        return "|".join(_safe_str(x, max_len=160) for x in key)
    except Exception:
        return _safe_str(key, max_len=240)


# Public API

class Log:
    @staticmethod
    def _level_from_flags(verbose: int, quiet: int) -> int:
        """
        Typical CLI mapping:
          quiet=0: default INFO
          -q: WARNING
          -qq: ERROR
          -v: INFO
          -vv: DEBUG
          -vvv: TRACE
        Quiet wins over verbose if both are set.
        """
        if quiet >= 2:
            return logging.ERROR
        if quiet == 1:
            return logging.WARNING
        if verbose >= 3:
            return TRACE
        if verbose >= 2:
            return logging.DEBUG
        return logging.INFO

    @staticmethod
    def bind(logger: logging.Logger, **ctx: Any) -> ContextLoggerAdapter:
        """Return a LoggerAdapter that carries a persistent context dict."""
        return ContextLoggerAdapter(logger, ctx)

    @staticmethod
    def banner(logger: logging.Logger, title: str, *, char: str = "─") -> None:
        width = 72
        t = f" {title.strip()} "
        line = (char * max(8, (width - len(t)) // 2)) + t + (char * max(8, (width - len(t)) // 2))
        logger.info(line[:width])

    @staticmethod
    def step(logger: logging.Logger, msg: str, **ctx: Any) -> None:
        logger.info("➡️ %s", msg, extra={"ctx": ctx} if ctx else None)

    @staticmethod
    def ok(logger: logging.Logger, msg: str, **ctx: Any) -> None:
        logger.info("✅ %s", msg, extra={"ctx": ctx} if ctx else None)

    @staticmethod
    def warn(logger: logging.Logger, msg: str, **ctx: Any) -> None:
        logger.warning("⚠️ %s", msg, extra={"ctx": ctx} if ctx else None)

    @staticmethod
    def fail(logger: logging.Logger, msg: str, **ctx: Any) -> None:
        logger.error("💥 %s", msg, extra={"ctx": ctx} if ctx else None)

    @staticmethod
    def trace(logger: logging.Logger, msg: str, *args: Any, **ctx: Any) -> None:
        if ctx:
            logger.trace(msg, *args, extra={"ctx": ctx})  # type: ignore[attr-defined]
        else:
            logger.trace(msg, *args)  # type: ignore[attr-defined]

    @staticmethod
    def trace_kv(logger: logging.Logger, msg: str, **kv: Any) -> None:
        Log.trace(logger, msg, **kv)

    @staticmethod
    def warn_once(logger: logging.Logger, key: str | tuple[Any, ...], msg: str, **ctx: Any) -> bool:
        """
        Log a warning only once per-process for `key`.
        Returns True if it logged, False if suppressed.
        """
        k = _warn_key(key)
        if k in _warn_once_keys:
            return False
        _warn_once_keys.add(k)
        logger.warning("⚠️ %s", msg, extra={"ctx": ctx} if ctx else None)
        return True

    @staticmethod
    def warn_rl(
        logger: logging.Logger,
        key: str | tuple[Any, ...],
        msg: str,
        *,
        every_s: float = 60.0,
        **ctx: Any,
    ) -> bool:
        """
        Rate-limited warning: logs at most once per `every_s` seconds for a given key.
        Returns True if it logged, False if suppressed.
        """
        k = _warn_key(key)
        now = time.time()
        last = _warn_last.get(k, 0.0)
        if (now - last) < float(every_s):
            return False
        _warn_last[k] = now
        logger.warning("⚠️ %s", msg, extra={"ctx": ctx} if ctx else None)
        return True

    @staticmethod
    def setup(
        verbose: int = 0,
        log_file: str | None = None,
        *,
        quiet: int = 0,
        color: bool | None = None,
        show_ms: bool = False,
        utc: bool = False,
        show_pid: bool = False,
        show_ppid: bool = False,
        show_proc: bool = True,
        show_logger: bool = False,
        indent_exceptions: bool = True,
        logger_name: str = "hyper2kvm",
        json_logs: bool = False,
        progress_safe: bool = True,
        force: bool = False,
    ) -> logging.Logger:
        """
        Configure and return the project's logger.

        - Process-first: supports proc name + pid (+ optional ppid).
        - json_logs=True emits NDJSON on stderr (good for CI/log shipping).
        - force=True also clears handlers on the root logger (useful if something else
          configured logging before you).
        """
        logger = logging.getLogger(logger_name)
        logger.propagate = False

        level = Log._level_from_flags(verbose, quiet)
        logger.setLevel(level)

        if color is None:
            color = True

        unicode_ok = _supports_unicode()

        style = LogStyle(
            color=bool(color),
            show_ms=bool(show_ms or verbose >= 3),
            show_src=bool(verbose >= 3),
            show_pid=bool(show_pid or verbose >= 2),  # pid is useful in process mode
            show_ppid=bool(show_ppid),
            show_proc=bool(show_proc),
            show_logger=bool(show_logger),
            utc=bool(utc),
            indent_exceptions=bool(indent_exceptions),
            unicode=bool(unicode_ok),
            progress_safe=bool(progress_safe),
        )

        # Clear our logger handlers
        for h in list(logger.handlers):
            logger.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass

        # Optionally clear root handlers too (aggressive)
        if force:
            root = logging.getLogger()
            for h in list(root.handlers):
                root.removeHandler(h)
                try:
                    h.close()
                except Exception:
                    pass

        sh = logging.StreamHandler(stream=sys.stderr)
        sh.setLevel(level)
        if json_logs:
            sh.setFormatter(JsonFormatter(utc=bool(utc), include_src=True))
        else:
            sh.setFormatter(EmojiFormatter(style))
        logger.addHandler(sh)

        if log_file:
            fp = Path(log_file).expanduser().resolve()
            fp.parent.mkdir(parents=True, exist_ok=True)

            # File logs: prefer JSON if requested, otherwise use EmojiFormatter without colors
            if json_logs:
                fh_fmt: logging.Formatter = JsonFormatter(utc=bool(utc), include_src=True)
            else:
                file_style = LogStyle(
                    color=False,
                    show_ms=True,
                    show_src=True,
                    show_pid=True,
                    show_ppid=True,
                    show_proc=True,
                    show_logger=True,
                    utc=style.utc,
                    indent_exceptions=True,
                    unicode=style.unicode,
                    progress_safe=True,
                )
                fh_fmt = EmojiFormatter(file_style)

            fh = logging.FileHandler(fp, encoding="utf-8")
            fh.setLevel(level)
            fh.setFormatter(fh_fmt)
            logger.addHandler(fh)

        logger.debug("Logger initialized (level=%s, pid=%s, proc=%s)", logging.getLevelName(level), os.getpid(), _mp.current_process().name)
        logger.trace("TRACE enabled (verbose >= 3)")  # type: ignore[attr-defined]
        return logger
