from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(eq=False)
class Vmdk2KvmError(Exception):
    """
    Base error for the project.
    Keeps a stable structure for reporting + JSON serialization.
    """
    code: int = 1
    msg: str = "error"
    cause: Optional[BaseException] = None
    context: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        # Exception's message is its string representation; keep it aligned.
        super().__init__(self.msg)
        self.code = int(self.code)

    def with_context(self, **ctx: Any) -> "Vmdk2KvmError":
        if self.context is None:
            self.context = {}
        self.context.update(ctx)
        return self

    def to_dict(self, *, include_cause: bool = False) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "type": self.__class__.__name__,
            "code": self.code,
            "message": self.msg,
            "context": self.context or {},
        }
        if include_cause and self.cause is not None:
            d["cause"] = {"type": type(self.cause).__name__, "message": str(self.cause)}
        return d


class Fatal(Vmdk2KvmError):
    """
    User-facing fatal error. Use for hard failures where we want an exit code.

    Typical usage:
        raise Fatal(2, "Missing required tool: qemu-img").with_context(tool="qemu-img")
    """
    pass


class VMwareError(Vmdk2KvmError):
    """
    vSphere/vCenter operation failed.
    Use for pyvmomi / SDK / ESXi errors.
    """
    pass


def wrap_fatal(code: int, msg: str, exc: Optional[BaseException] = None, **context: Any) -> Fatal:
    e = Fatal(code=code, msg=msg, cause=exc, context=context or None)
    return e


def wrap_vmware(msg: str, exc: Optional[BaseException] = None, code: int = 50, **context: Any) -> VMwareError:
    e = VMwareError(code=code, msg=msg, cause=exc, context=context or None)
    return e
