from __future__ import annotations

import datetime as _dt
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Optional: colors
try:
    from termcolor import colored as _colored  # type: ignore
except Exception:  # pragma: no cover
    _colored = None

_LEVEL_EMOJI = {
    "DEBUG": "🔍",
    "INFO": "✅",
    "WARNING": "⚠️",
    "ERROR": "💥",
    "CRITICAL": "🧨",
}
_LEVEL_COLOR = {
    "DEBUG": "blue",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "red",
}

def _is_tty() -> bool:
    try:
        return sys.stderr.isatty()
    except Exception:
        return False

def c(text: str, color: Optional[str] = None, attrs: Optional[List[str]] = None, *, enable: bool = True) -> str:
    """Colorize text if termcolor is available and enabled."""
    if not enable or _colored is None or not color:
        return text
    try:
        return _colored(text, color=color, attrs=attrs or [])
    except Exception:
        return text

@dataclass(frozen=True)
class LogStyle:
    color: bool = True
    show_ms: bool = False
    show_src: bool = False   # module:line
    utc: bool = False

class EmojiFormatter(logging.Formatter):
    def __init__(self, style: LogStyle):
        super().__init__()
        self._style = style

    def _now(self, created: float) -> str:
        dt = _dt.datetime.fromtimestamp(created, tz=_dt.timezone.utc) if self._style.utc else _dt.datetime.fromtimestamp(created)
        return dt.strftime("%H:%M:%S.%f")[:-3] if self._style.show_ms else dt.strftime("%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        ts = self._now(record.created)
        emoji = _LEVEL_EMOJI.get(record.levelname, "•")

        lvl = record.levelname
        msg = record.getMessage()

        color_ok = self._style.color and _is_tty()

        lvl = c(lvl, _LEVEL_COLOR.get(record.levelname), enable=color_ok)
        if record.levelno >= logging.WARNING:
            msg = c(msg, _LEVEL_COLOR.get(record.levelname), attrs=["bold"], enable=color_ok)

        src = ""
        if self._style.show_src:
            # record.pathname can be long; module is cleaner
            src = f" {record.module}:{record.lineno}"

        # If exception info exists, include the formatted traceback.
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            return f"{ts} {emoji} {lvl:<8}{src} {msg}\n{exc_text}"

        return f"{ts} {emoji} {lvl:<8}{src} {msg}"

class Log:
    @staticmethod
    def _level_from_flags(verbose: int, quiet: int) -> int:
        """
        Typical CLI mapping:
          quiet=0: default INFO
          -q: WARNING
          -qq: ERROR
          -v: INFO (same as default, but kept for compatibility)
          -vv: DEBUG
        Quiet wins over verbose if both are set.
        """
        if quiet >= 2:
            return logging.ERROR
        if quiet == 1:
            return logging.WARNING
        if verbose >= 2:
            return logging.DEBUG
        return logging.INFO

    @staticmethod
    def setup(
        verbose: int = 0,
        log_file: Optional[str] = None,
        *,
        quiet: int = 0,
        color: Optional[bool] = None,
        show_ms: bool = False,
        utc: bool = False,
        logger_name: str = "vmdk2kvm",
    ) -> logging.Logger:
        """
        Create/refresh logger:
          - Avoids handler duplication on repeated setup()
          - Stream handler always goes to stderr (CLI-friendly)
          - Optional file handler (no ANSI color, but with more context if desired)
        """
        logger = logging.getLogger(logger_name)
        logger.propagate = False

        level = Log._level_from_flags(verbose, quiet)
        logger.setLevel(level)

        # Decide coloring: default on when termcolor exists, but only if TTY.
        if color is None:
            color = True

        style = LogStyle(
            color=bool(color),
            show_ms=bool(show_ms or verbose >= 3),
            show_src=bool(verbose >= 3),
            utc=bool(utc),
        )

        stream_fmt = EmojiFormatter(style)

        # Clear existing handlers safely (prevents dupes)
        for h in list(logger.handlers):
            logger.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass

        sh = logging.StreamHandler(stream=sys.stderr)
        sh.setLevel(level)
        sh.setFormatter(stream_fmt)
        logger.addHandler(sh)

        if log_file:
            fp = Path(log_file).expanduser().resolve()
            fp.parent.mkdir(parents=True, exist_ok=True)

            # File format: disable color; include ms + source for better forensics.
            file_style = LogStyle(color=False, show_ms=True, show_src=True, utc=style.utc)
            fh = logging.FileHandler(fp, encoding="utf-8")
            fh.setLevel(level)
            fh.setFormatter(EmojiFormatter(file_style))
            logger.addHandler(fh)

        # Optional: emit a debug line only if enabled
        logger.debug("Logger initialized (level=%s, pid=%s)", logging.getLevelName(level), os.getpid())
        return logger
