# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/exceptions.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _safe_int(x: Any, default: int = 1) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _clamp_exit_code(code: int) -> int:
    # Exit codes must be 0..255
    try:
        if code < 0 or code > 255:
            raise ValueError(f"Exit code must be in range 0-255, got {code}")
        return code
    except TypeError:
        raise ValueError(f"Exit code must be an integer, got {type(code).__name__}") from None


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


def _format_context_compact(ctx: dict[str, Any]) -> str:
    # Stable order, redaction, single-line.
    parts = []
    for k in sorted(ctx.keys()):
        v = ctx.get(k)
        if _is_secret_key(str(k)):
            parts.append(f"{k}=<redacted>")
        else:
            parts.append(f"{k}={v!r}")
    return ", ".join(parts)


def _redact_secrets(obj: Any) -> Any:
    """
    Recursively redact secrets in dictionaries.
    Returns a new object with secrets replaced by '***REDACTED***'.
    """
    if isinstance(obj, dict):
        return {
            k: "***REDACTED***" if _is_secret_key(str(k)) else _redact_secrets(v)
            for k, v in obj.items()
        }
    elif isinstance(obj, (list, tuple)):
        return type(obj)(_redact_secrets(item) for item in obj)
    else:
        return obj


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
    cause: BaseException | None = None
    context: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.code = _clamp_exit_code(_safe_int(self.code, default=1))
        self.msg = _one_line(self.msg) or self.__class__.__name__
        if self.context is None:
            self.context = {}
        super().__init__(self.msg)
        # Some tooling inspects Exception.args directly.
        self.args = (self.msg,)

    def with_context(self, **ctx: Any) -> Hyper2KvmError:
        if self.context is None:
            self.context = {}
        self.context.update(ctx)
        return self

    def user_message(self, *, include_context: bool = False, include_cause: bool = False) -> str:
        """
        Human-friendly message for CLI output/logs.

        If context contains 'solutions', 'causes', or 'doc_link', they are formatted
        as helpful guidance rather than as compact key=value pairs.
        """
        base = self.msg or self.__class__.__name__
        parts = [base]

        if include_context and self.context:
            # Extract helpful fields for special formatting
            solutions = self.context.get("solutions")
            causes = self.context.get("causes")
            doc_link = self.context.get("doc_link")

            # Remaining context (excluding helpful fields)
            remaining_ctx = {
                k: v
                for k, v in self.context.items()
                if k not in ("solutions", "causes", "doc_link")
            }

            # Add solutions if present
            if solutions:
                parts.append("\n\nSolutions:")
                for i, solution in enumerate(solutions, 1):
                    parts.append(f"\n  {i}. {solution}")

            # Add common causes if present
            if causes:
                parts.append("\n\nCommon causes:")
                for i, cause in enumerate(causes, 1):
                    parts.append(f"\n  {i}. {cause}")

            # Add documentation link if present
            if doc_link:
                parts.append(f"\n\nDocumentation: {doc_link}")

            # Add remaining context as compact format
            if remaining_ctx:
                parts.append(f"\n[{_one_line(_format_context_compact(remaining_ctx), limit=600)}]")

        if include_cause and self.cause is not None:
            parts.append(f"\n(cause: {type(self.cause).__name__}: {_one_line(str(self.cause))})")

        return "".join(parts)

    def __str__(self) -> str:
        # Default string should be clean and user-facing
        return self.user_message(include_context=False, include_cause=False)

    def to_dict(self, *, include_cause: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.__class__.__name__,
            "code": self.code,
            "message": self.msg,
            "context": _redact_secrets(self.context or {}),
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


class VMwareError(Hyper2KvmError):
    """
    vSphere/vCenter operation failed.
    Use for pyvmomi / SDK / ESXi errors.
    """


def wrap_fatal(msg: str, exc: BaseException | None = None, code: int = 1, **context: Any) -> Fatal:
    return Fatal(code=code, msg=msg, cause=exc, context=context or None)


def wrap_vmware(msg: str, exc: BaseException | None = None, code: int = 50, **context: Any) -> VMwareError:
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


# Enhanced error creation helpers

def create_helpful_error(
    error_type: type[Hyper2KvmError],
    message: str,
    *,
    code: int = 1,
    solutions: list[str] | None = None,
    causes: list[str] | None = None,
    doc_link: str | None = None,
    **context: Any
) -> Hyper2KvmError:
    """
    Create an error with helpful context including solutions and documentation links.

    Args:
        error_type: The exception class (Fatal, VMwareError, etc.)
        message: The main error message
        code: Exit code
        solutions: List of actionable solutions
        causes: List of common causes
        doc_link: Documentation link (relative to docs/)
        **context: Additional context key-value pairs

    Returns:
        Enhanced error instance

    Example:
        >>> err = create_helpful_error(
        ...     Fatal,
        ...     "VM not found: my-vm",
        ...     solutions=["Verify VM name with: govc ls /DC/vm/"],
        ...     doc_link="30-vSphere-Export.md#troubleshooting"
        ... )
    """
    # Add enhanced context
    if solutions:
        context["solutions"] = solutions
    if causes:
        context["causes"] = causes
    if doc_link:
        context["doc_link"] = f"https://github.com/hyper2kvm/hyper2kvm/blob/main/docs/{doc_link}"

    return error_type(code=code, msg=message, context=context or None)
