# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/exceptions.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


def _safe_int(x: Any, default: int = 1) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _clamp_exit_code(code: int) -> int:
    # Exit codes are typically 0..255; keep it safe and predictable.
    try:
        if code < 0:
            return 1
        if code > 255:
            return 255
        return code
    except Exception:
        return 1


def _one_line(s: str, limit: int = 600) -> str:
    s = (s or "").strip().replace("\r", " ").replace("\n", " ")
    s = " ".join(s.split())
    return s if len(s) <= limit else (s[: limit - 3] + "...")


_SECRET_KEY_PARTS = (
    "pass",
    "password",
    "passwd",
    "secret",
    "token",
    "apikey",
    "api_key",
    "auth",
    "cookie",
    "session",
    "bearer",
    "private",
    "key",
)


def _is_secret_key(k: str) -> bool:
    ks = (k or "").lower()
    return any(p in ks for p in _SECRET_KEY_PARTS)


def _format_context_compact(ctx: Dict[str, Any]) -> str:
    # Stable order, redaction, single-line.
    parts = []
    for k in sorted(ctx.keys()):
        v = ctx.get(k)
        if _is_secret_key(str(k)):
            parts.append(f"{k}=<redacted>")
        else:
            parts.append(f"{k}={v!r}")
    return ", ".join(parts)


@dataclass(eq=False)
class Hyper2KvmError(Exception):
    """
    Base project error with:
      - stable fields for reporting/JSON
      - readable __str__ (what users see)
      - safe code handling (never crashes on int())
    """
    code: int = 1
    msg: str = "error"
    cause: Optional[BaseException] = None
    context: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        self.code = _clamp_exit_code(_safe_int(self.code, default=1))
        self.msg = _one_line(self.msg) or self.__class__.__name__
        super().__init__(self.msg)
        # Some tooling inspects Exception.args directly.
        self.args = (self.msg,)

    def with_context(self, **ctx: Any) -> "Hyper2KvmError":
        if self.context is None:
            self.context = {}
        self.context.update(ctx)
        return self

    def user_message(self, *, include_context: bool = False, include_cause: bool = False) -> str:
        """
        Human-friendly message for CLI output/logs.
        """
        base = self.msg or self.__class__.__name__
        parts = [base]

        if include_context and self.context:
            parts.append(f"[{_one_line(_format_context_compact(self.context), limit=600)}]")

        if include_cause and self.cause is not None:
            parts.append(f"(cause: {type(self.cause).__name__}: {_one_line(str(self.cause))})")

        return " ".join(parts)

    def __str__(self) -> str:
        # Default string should be clean and user-facing
        return self.user_message(include_context=False, include_cause=False)

    def to_dict(self, *, include_cause: bool = False) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "type": self.__class__.__name__,
            "code": self.code,
            "message": self.msg,
            "context": self.context or {},
        }
        if include_cause and self.cause is not None:
            d["cause"] = {"type": type(self.cause).__name__, "message": _one_line(str(self.cause))}
        return d


# Backward-compat alias (old name kept so imports don’t explode)
Vmdk2KvmError = Hyper2KvmError


class Fatal(Hyper2KvmError):
    """
    User-facing fatal error (exit code should be honored by top-level main()).
    """
    pass


class VMwareError(Hyper2KvmError):
    """
    vSphere/vCenter operation failed.
    Use for pyvmomi / SDK / ESXi errors.
    """
    pass


def wrap_fatal(msg: str, exc: Optional[BaseException] = None, code: int = 1, **context: Any) -> Fatal:
    return Fatal(code=code, msg=msg, cause=exc, context=context or None)


def wrap_vmware(msg: str, exc: Optional[BaseException] = None, code: int = 50, **context: Any) -> VMwareError:
    return VMwareError(code=code, msg=msg, cause=exc, context=context or None)


def format_exception_for_cli(e: BaseException, *, verbose: int = 0) -> str:
    """
    One-liner output for CLI.

    verbose=0: just message
    verbose=1: message + compact context (if any)
    verbose>=2: message + context + cause
    """
    if isinstance(e, Hyper2KvmError):
        return e.user_message(
            include_context=(verbose >= 1),
            include_cause=(verbose >= 2),
        )

    # Non-project exceptions: keep them short unless verbose
    if verbose >= 2:
        return f"{type(e).__name__}: {_one_line(str(e))}"
    return _one_line(str(e)) or type(e).__name__
