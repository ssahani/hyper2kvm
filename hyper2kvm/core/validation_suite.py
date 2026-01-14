# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import multiprocessing as mp
import os
import pickle
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple


# ---------------------------
# Types
# ---------------------------

CheckFunc = Callable[[Dict[str, Any]], Any]
SkipIfFunc = Callable[[Dict[str, Any]], bool]
ContextSanitizer = Callable[[Dict[str, Any]], Dict[str, Any]]


class SupportsRichConsole(Protocol):
    # minimal protocol so we don't hard-depend on rich Console types
    def print(self, *args: Any, **kwargs: Any) -> Any: ...


# ---------------------------
# Exit codes (CLI-friendly)
# ---------------------------

class ExitCodes:
    """
    Structured exit codes for shell/CI/systemd.

      0 = all ok
      1 = failures present (non-critical only)
      2 = critical failures present
      3 = suite internal error (runner crashed)
      4 = invalid config / misuse (e.g., no checks)
    """

    OK = 0
    FAIL = 1
    CRITICAL = 2
    INTERNAL = 3
    INVALID = 4

    @staticmethod
    def from_payload(payload: Dict[str, Any]) -> int:
        if not isinstance(payload, dict):
            return ExitCodes.INTERNAL
        stats = payload.get("stats") or {}
        total = int(stats.get("total", 0) or 0)
        if total <= 0:
            return ExitCodes.INVALID
        if payload.get("failed_critical", False):
            return ExitCodes.CRITICAL
        ok = bool(payload.get("ok", False))
        return ExitCodes.OK if ok else ExitCodes.FAIL


# ---------------------------
# Spec + result
# ---------------------------

@dataclass
class CheckSpec:
    """
    A single validation check.

    Timeouts:
      - If timeout_s is set and the check is run in a subprocess, timeout is HARD:
        the child process is terminated.
      - If timeout_s is set but the check runs in-process, timeout is SOFT:
        we mark it failed if it exceeded the budget.

    Subprocess mode requirements:
      - spec.func must be pickleable (top-level functions are safest).
      - context must be pickleable *after sanitization* (see suite context_sanitizer).

    Dependencies:
      - depends_on lists check names that must have PASSED for this check to run.
        If any dependency did not pass, this check is skipped with reason.

    Retries:
      - retries > 0 repeats the check if it fails. Attempts count is recorded.
        (By default retries apply to non-critical checks; can be overridden by retry_critical.)

    Parallelism:
      - If tagged "parallel_safe" and suite parallelism is enabled, this check may run
        concurrently in its own process (never threads).
    """

    name: str
    func: CheckFunc

    # semantics
    critical: bool = False
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    # execution controls
    timeout_s: Optional[float] = None          # hard in subprocess, soft in-process
    run_in_process: bool = False               # prefer subprocess
    skip_if: Optional[SkipIfFunc] = None       # extra skip predicate
    depends_on: List[str] = field(default_factory=list)

    # reliability controls
    retries: int = 0
    retry_delay_s: float = 0.0
    retry_backoff: float = 1.0
    retry_critical: bool = False

    # safety controls
    max_result_repr_len: int = 20000           # cap to avoid gigantic payloads
    redact_keys: List[str] = field(default_factory=list)  # extra per-check redact keys


@dataclass
class CheckResult:
    name: str
    passed: bool
    critical: bool
    duration_s: float

    # payload
    result: Any = None
    error: Optional[str] = None
    traceback: Optional[str] = None

    # meta
    skipped: bool = False
    skip_reason: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    description: Optional[str] = None
    timed_out: bool = False
    terminated: bool = False
    mode: str = "inprocess"  # "inprocess" | "subprocess" | "parallel" | "skipped"

    # retry/meta
    attempts: int = 1
    result_truncated: bool = False


# ---------------------------
# Small helpers: redaction + capping
# ---------------------------

def _is_mapping(x: Any) -> bool:
    return isinstance(x, dict)


def _is_sequence(x: Any) -> bool:
    return isinstance(x, (list, tuple))


def _redact_in_obj(obj: Any, redact_keys: "set[str]") -> Any:
    """
    Best-effort recursive redaction. Non-destructive (returns new structures where possible).
    """
    try:
        if _is_mapping(obj):
            out: Dict[str, Any] = {}
            for k, v in obj.items():
                ks = str(k)
                if ks.lower() in redact_keys:
                    out[k] = "***REDACTED***"
                else:
                    out[k] = _redact_in_obj(v, redact_keys)
            return out
        if _is_sequence(obj):
            return obj.__class__(_redact_in_obj(v, redact_keys) for v in obj)  # type: ignore[misc]
        return obj
    except Exception:
        # If redaction fails for weird objects, fall back to repr-safe
        return obj


def _cap_result(obj: Any, max_repr_len: int) -> Tuple[Any, bool]:
    """
    Cap large results by using repr() truncation. Returns (possibly_modified_obj, truncated_flag).
    """
    if max_repr_len <= 0:
        return obj, False
    try:
        s = repr(obj)
        if len(s) <= max_repr_len:
            return obj, False
        # Keep a preview string only (avoid huge payload)
        preview = s[: max_repr_len - 3] + "..."
        return {"_truncated_repr": preview}, True
    except Exception:
        return {"_truncated_repr": "<unreprable-result>"}, True


def _sleep_with_backoff(base_delay: float, backoff: float, attempt_idx: int) -> None:
    if base_delay <= 0:
        return
    mult = 1.0
    if attempt_idx > 0 and backoff and backoff > 1.0:
        mult = (backoff ** attempt_idx)
    time.sleep(base_delay * mult)


# ---------------------------
# Multiprocessing child plumbing
# ---------------------------

def _child_run_check(func: CheckFunc, context: Dict[str, Any], conn: Any) -> None:
    """
    Child process entry: run func(context), send ("ok", result) or ("err", (err, tb)).
    Uses a one-shot Pipe (simpler than Queue, fewer flush-at-exit edge cases).
    """
    try:
        res = func(context)
        conn.send(("ok", res))
    except Exception as e:
        tb = traceback.format_exc()
        conn.send(("err", (str(e), tb)))
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _exitcode_hint(exitcode: Optional[int]) -> str:
    if exitcode is None:
        return "exitcode=None"
    if exitcode < 0:
        return f"exitcode={exitcode} (signal={-exitcode})"
    return f"exitcode={exitcode}"


def _can_pickle(obj: Any) -> Tuple[bool, Optional[str]]:
    try:
        pickle.dumps(obj)
        return True, None
    except Exception as e:
        return False, str(e)


# ---------------------------
# Main suite
# ---------------------------

class ValidationSuite:
    """
    Process-first validation runner (no threads):

      - typed CheckSpec/CheckResult
      - per-check duration timing
      - skip support via context flags + per-check skip predicate
      - dependency-aware skipping
      - retries with backoff
      - per-check and global redaction + result size caps
      - subprocess execution for hard timeouts
      - process-based parallel execution for checks tagged "parallel_safe"
      - JSON-friendly output + stats (by tag + slowest)
      - structured exit codes helper (ExitCodes.from_payload)

    Payload semantics:
      - ok == True only if *no checks failed* (critical or non-critical)
      - failed_critical reports whether any critical checks failed
      - stop_on_critical only affects how far we run, not what ok means
    """

    def __init__(
        self,
        logger: logging.Logger,
        *,
        console: Optional[SupportsRichConsole] = None,
        default_use_processes: bool = False,
        mp_start_method: str = "spawn",
        context_sanitizer: Optional[ContextSanitizer] = None,
    ):
        self.logger = logger
        self.console = console
        self.checks: List[CheckSpec] = []
        self.default_use_processes = bool(default_use_processes)
        self.mp_start_method = mp_start_method
        self.context_sanitizer = context_sanitizer
        self._logged_mp_start_method = False

    def add_check(
        self,
        name: str,
        check_func: CheckFunc,
        critical: bool = False,
        *,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        timeout_s: Optional[float] = None,
        run_in_process: bool = False,
        skip_if: Optional[SkipIfFunc] = None,
        depends_on: Optional[List[str]] = None,
        retries: int = 0,
        retry_delay_s: float = 0.0,
        retry_backoff: float = 1.0,
        retry_critical: bool = False,
        max_result_repr_len: int = 20000,
        redact_keys: Optional[List[str]] = None,
    ) -> None:
        self.checks.append(
            CheckSpec(
                name=name,
                func=check_func,
                critical=critical,
                description=description,
                tags=tags or [],
                timeout_s=timeout_s,
                run_in_process=run_in_process,
                skip_if=skip_if,
                depends_on=depends_on or [],
                retries=int(retries or 0),
                retry_delay_s=float(retry_delay_s or 0.0),
                retry_backoff=float(retry_backoff or 1.0),
                retry_critical=bool(retry_critical),
                max_result_repr_len=int(max_result_repr_len or 20000),
                redact_keys=redact_keys or [],
            )
        )

    # ---------------------------
    # Skip + dependency logic
    # ---------------------------

    def _should_skip(self, spec: CheckSpec, context: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        # Supported skip mechanisms:
        #   context["skip_checks"] = {"name1", "name2"}
        #   context["skip_tags"]   = {"network", "slow"}
        skip_checks = set(context.get("skip_checks", []) or [])
        skip_tags = set(context.get("skip_tags", []) or [])

        if spec.name in skip_checks:
            return True, "user:skip_checks"
        if spec.tags and (set(spec.tags) & skip_tags):
            # return which tag matched (first)
            hit = next(iter(set(spec.tags) & skip_tags))
            return True, f"user:skip_tags:{hit}"
        if spec.skip_if is not None:
            try:
                if bool(spec.skip_if(context)):
                    return True, "skip_if:true"
            except Exception as e:
                self.logger.debug("skip_if predicate errored for %s: %s", spec.name, e)
        return False, None

    def _dependency_ok(self, spec: CheckSpec, results_json: Dict[str, Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
        if not spec.depends_on:
            return True, None
        for dep in spec.depends_on:
            dep_r = results_json.get(dep)
            if not dep_r:
                return False, f"dependency_missing:{dep}"
            if not bool(dep_r.get("passed", False)):
                return False, f"dependency_failed:{dep}"
        return True, None

    # ---------------------------
    # Context sanitization + redaction configuration
    # ---------------------------

    def _sanitize_context_for_child(self, context: Dict[str, Any], *, allow_keys: Optional[Sequence[str]]) -> Dict[str, Any]:
        """
        Reduce/clean context for child processes.
        - If allow_keys is provided, only those keys are included.
        - Else, if context_sanitizer is set, it is applied.
        - Else, context is passed as-is.
        """
        ctx = context
        if allow_keys:
            out: Dict[str, Any] = {}
            for k in allow_keys:
                if k in ctx:
                    out[k] = ctx[k]
            ctx = out

        if self.context_sanitizer is not None:
            try:
                ctx = self.context_sanitizer(ctx)
            except Exception as e:
                # Sanitizer should not explode the run; fall back to current ctx
                self.logger.debug("context_sanitizer errored: %s", e)

        return ctx

    def _effective_redact_keys(self, spec: CheckSpec, context: Dict[str, Any]) -> "set[str]":
        base = set(str(k).lower() for k in (context.get("redact_keys", []) or []))
        extra = set(str(k).lower() for k in (spec.redact_keys or []))
        # Some sane defaults
        base |= {"password", "passwd", "token", "secret", "apikey", "api_key", "authorization"}
        return base | extra

    # ---------------------------
    # Core execution: in-process + subprocess with retries
    # ---------------------------

    def _run_check_inprocess_once(self, spec: CheckSpec, context: Dict[str, Any], *, show_tracebacks: bool) -> CheckResult:
        t0 = time.monotonic()
        mode = "inprocess"
        try:
            out = spec.func(context)
            dur = time.monotonic() - t0

            if spec.timeout_s is not None and dur > spec.timeout_s:
                return CheckResult(
                    name=spec.name,
                    passed=False,
                    critical=spec.critical,
                    duration_s=dur,
                    error=f"Check exceeded soft timeout ({dur:.2f}s > {spec.timeout_s:.2f}s)",
                    traceback=None,
                    skipped=False,
                    skip_reason=None,
                    tags=list(spec.tags),
                    description=spec.description,
                    timed_out=True,
                    terminated=False,
                    mode=mode,
                )

            return CheckResult(
                name=spec.name,
                passed=True,
                critical=spec.critical,
                duration_s=dur,
                result=out,
                tags=list(spec.tags),
                description=spec.description,
                mode=mode,
            )

        except Exception as e:
            dur = time.monotonic() - t0
            tb = traceback.format_exc()
            return CheckResult(
                name=spec.name,
                passed=False,
                critical=spec.critical,
                duration_s=dur,
                error=str(e),
                traceback=(tb if show_tracebacks else None),
                tags=list(spec.tags),
                description=spec.description,
                mode=mode,
            )

    def _run_check_subprocess_once(
        self,
        spec: CheckSpec,
        context: Dict[str, Any],
        *,
        show_tracebacks: bool,
        strict_process_checks: bool,
        allow_context_keys: Optional[Sequence[str]],
    ) -> CheckResult:
        t0 = time.monotonic()
        mode = "subprocess"

        child_ctx = self._sanitize_context_for_child(context, allow_keys=allow_context_keys)

        ok_f, why_f = _can_pickle(spec.func)
        ok_c, why_c = _can_pickle(child_ctx)
        if not ok_f or not ok_c:
            why = []
            if not ok_f:
                why.append(f"func not pickleable: {why_f}")
            if not ok_c:
                why.append(f"context not pickleable: {why_c}")
            msg = "; ".join(why) or "cannot pickle for subprocess"

            if strict_process_checks:
                dur = time.monotonic() - t0
                return CheckResult(
                    name=spec.name,
                    passed=False,
                    critical=spec.critical,
                    duration_s=dur,
                    error=f"Cannot run in subprocess (strict mode): {msg}",
                    tags=list(spec.tags),
                    description=spec.description,
                    mode=mode,
                )
            raise RuntimeError(msg)

        try:
            ctx = mp.get_context(self.mp_start_method)
        except Exception:
            ctx = mp.get_context("spawn")

        parent_conn, child_conn = ctx.Pipe(duplex=False)
        p = ctx.Process(target=_child_run_check, args=(spec.func, child_ctx, child_conn), daemon=True)
        p.start()

        timed_out = False
        terminated = False
        err_s: Optional[str] = None
        tb_s: Optional[str] = None
        result: Any = None
        passed = False

        timeout = spec.timeout_s
        if timeout is None:
            p.join()
        else:
            p.join(timeout)

        if p.is_alive():
            timed_out = True
            terminated = True
            try:
                p.terminate()
            finally:
                p.join(2.0)

        dur = time.monotonic() - t0

        try:
            child_conn.close()
        except Exception:
            pass

        if timed_out:
            passed = False
            err_s = f"Check timed out after {timeout:.2f}s"
        else:
            try:
                if parent_conn.poll(0.0):
                    kind, payload = parent_conn.recv()
                else:
                    kind, payload = None, None
            except EOFError:
                kind, payload = None, None
            except Exception as e:
                kind, payload = None, None
                err_s = f"Failed to read subprocess result: {e}"

            if kind == "ok":
                passed = True
                result = payload
            elif kind == "err":
                passed = False
                try:
                    err_s, tb_s = payload
                except Exception:
                    err_s = "Subprocess reported error, but payload was malformed"
                    tb_s = None
            else:
                passed = False
                hint = _exitcode_hint(p.exitcode)
                if err_s is None:
                    err_s = f"Check subprocess exited without result ({hint})"

        try:
            parent_conn.close()
        except Exception:
            pass

        return CheckResult(
            name=spec.name,
            passed=passed,
            critical=spec.critical,
            duration_s=dur,
            result=result,
            error=err_s,
            traceback=(tb_s if show_tracebacks else None),
            tags=list(spec.tags),
            description=spec.description,
            timed_out=timed_out,
            terminated=terminated,
            mode=mode,
        )

    def _apply_redaction_and_caps(self, spec: CheckSpec, context: Dict[str, Any], r: CheckResult) -> CheckResult:
        # Only touch "result" (errors/tracebacks are left as-is)
        if not r.passed:
            return r

        redact_keys = self._effective_redact_keys(spec, context)
        redacted = _redact_in_obj(r.result, redact_keys)
        capped, truncated = _cap_result(redacted, spec.max_result_repr_len)

        r.result = capped
        r.result_truncated = bool(truncated)
        return r

    def _run_with_retries(
        self,
        spec: CheckSpec,
        context: Dict[str, Any],
        *,
        executor: Callable[[], CheckResult],
    ) -> CheckResult:
        attempts = 0
        last: Optional[CheckResult] = None
        max_attempts = 1 + max(0, int(spec.retries or 0))

        # Default: do not retry critical unless explicitly allowed
        allow_retry = (not spec.critical) or bool(spec.retry_critical)

        for i in range(max_attempts):
            attempts += 1
            r = executor()
            r.attempts = attempts
            last = r

            if r.passed:
                return r

            if not allow_retry:
                return r

            # last attempt: stop
            if i >= max_attempts - 1:
                return r

            # delay/backoff before retry
            _sleep_with_backoff(spec.retry_delay_s, spec.retry_backoff, i)

        return last or CheckResult(name=spec.name, passed=False, critical=spec.critical, duration_s=0.0, error="unknown")

    # ---------------------------
    # JSON serialization + stats
    # ---------------------------

    @staticmethod
    def _result_to_json(r: CheckResult, *, show_tracebacks: bool) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "passed": r.passed,
            "critical": r.critical,
            "duration_s": round(r.duration_s, 3),
            "skipped": r.skipped,
            "skip_reason": r.skip_reason,
            "tags": list(r.tags),
            "timed_out": r.timed_out,
            "terminated": r.terminated,
            "mode": r.mode,
            "attempts": int(r.attempts or 1),
            "result_truncated": bool(r.result_truncated),
        }
        if r.description:
            d["description"] = r.description
        if r.passed:
            d["result"] = r.result
        else:
            d["error"] = r.error or "unknown error"
            if show_tracebacks and r.traceback:
                d["traceback"] = r.traceback
        return d

    def _compute_tag_stats(self, results_json: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {}
        for name, r in results_json.items():
            tags = r.get("tags") or []
            if not tags:
                tags = ["_untagged"]
            for t in tags:
                d = out.setdefault(str(t), {"passed": 0, "failed": 0, "skipped": 0, "total": 0})
                d["total"] += 1
                if bool(r.get("skipped", False)):
                    d["skipped"] += 1
                elif bool(r.get("passed", False)):
                    d["passed"] += 1
                else:
                    d["failed"] += 1
        return out

    def _compute_slowest(self, results_json: Dict[str, Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
        items: List[Tuple[str, float, str]] = []
        for name, r in results_json.items():
            try:
                dur = float(r.get("duration_s", 0.0) or 0.0)
            except Exception:
                dur = 0.0
            mode = str(r.get("mode", "") or "")
            items.append((name, dur, mode))
        items.sort(key=lambda x: x[1], reverse=True)
        out = [{"name": n, "duration_s": round(d, 3), "mode": m} for (n, d, m) in items[: max(1, int(top_n or 10))]]
        return out

    # ---------------------------
    # Parallel runner (process-based)
    # ---------------------------

    def _parallel_candidate(self, spec: CheckSpec) -> bool:
        return "parallel_safe" in set(spec.tags or [])

    def _parallel_worker_entry(
        self,
        spec: CheckSpec,
        context: Dict[str, Any],
        show_tracebacks: bool,
        strict_process_checks: bool,
        allow_context_keys: Optional[Sequence[str]],
        use_subprocess: bool,
    ) -> CheckResult:
        """
        Executed inside the *parallel worker process* (one process per check).
        If use_subprocess=True, that worker will spawn a child process for hard timeout.
        Yes, that’s process-in-process; ugly but correct and keeps hard timeout semantics.
        """
        # In a worker, we can run in-process (fast) OR enforce hard timeout by spawning a child.
        if use_subprocess:
            # In worker process, we still use subprocess-once to enforce hard timeout.
            return self._run_check_subprocess_once(
                spec,
                context,
                show_tracebacks=show_tracebacks,
                strict_process_checks=strict_process_checks,
                allow_context_keys=allow_context_keys,
            )
        return self._run_check_inprocess_once(spec, context, show_tracebacks=show_tracebacks)

    # ---------------------------
    # Public API
    # ---------------------------

    def run_all(
        self,
        context: Dict[str, Any],
        *,
        stop_on_critical: bool = True,
        show_tracebacks: bool = False,
        log_summary: bool = True,
        use_processes: Optional[bool] = None,
        parallel: bool = False,
        max_workers: Optional[int] = None,
        top_slowest: int = 10,
    ) -> Dict[str, Any]:
        """
        Returns JSON-friendly payload:
          {
            "ok": bool,
            "failed_critical": bool,
            "results": {name: {...}},
            "stats": {
              "total": int,
              "passed": int,
              "failed": int,
              "skipped": int,
              "duration_s": float,
              "by_tag": {...},
              "slowest": [...],
            },
            "exit_code": int
          }

        Context policy knobs:
          - strict_process_checks: bool
              If True, subprocess-required checks FAIL (not fallback) when pickle/subprocess fails.
          - process_context_keys: [str,...]
              If provided, only these keys are passed into child processes (helps pickling).
          - missing_required_tools: [str,...]
              If set + non-empty, suite can fail-fast or skip expensive checks (see below).
          - fail_fast_on_missing_required_tools: bool (default True)
              If missing_required_tools and this is True, suite stops early (no noisy checks).
          - expensive_tags: [str,...] default ["expensive","guestfs"]
              If not failing fast, checks matching these tags are skipped when required tools missing.
          - redact_keys: [str,...]
              Global redaction keys for result payloads.
        """
        started = time.monotonic()

        total = len(self.checks)
        if total <= 0:
            payload = {
                "ok": False,
                "failed_critical": False,
                "results": {},
                "stats": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "duration_s": 0.0},
                "exit_code": ExitCodes.INVALID,
                "error": "No checks registered",
            }
            if log_summary:
                self._log_summary(payload)
            return payload

        use_procs = self.default_use_processes if use_processes is None else bool(use_processes)
        strict_process_checks = bool(context.get("strict_process_checks", False))
        allow_context_keys = context.get("process_context_keys")
        if allow_context_keys is not None and not isinstance(allow_context_keys, (list, tuple)):
            allow_context_keys = None

        # Missing required tools policy
        missing_required = list(context.get("missing_required_tools", []) or [])
        fail_fast_missing = bool(context.get("fail_fast_on_missing_required_tools", True))
        expensive_tags = set(context.get("expensive_tags", ["expensive", "guestfs"]) or ["expensive", "guestfs"])

        # Log mp start method once
        if not self._logged_mp_start_method:
            try:
                _ = mp.get_context(self.mp_start_method)
                method = self.mp_start_method
            except Exception:
                method = "spawn"
            self.logger.debug("ValidationSuite multiprocessing start method: %s", method)
            self._logged_mp_start_method = True

        results_json: Dict[str, Dict[str, Any]] = {}
        failed_critical = False
        passed_count = 0
        failed_count = 0
        skipped_count = 0

        # If required tools missing: either fail fast, or skip expensive checks automatically
        if missing_required and fail_fast_missing:
            # Mark a synthetic failure result to explain
            msg = f"Missing required tools: {', '.join(missing_required)}"
            self.logger.error(msg)

            # Skip everything (fast + deterministic), but report per-check skipped with reason
            for spec in self.checks:
                r = CheckResult(
                    name=spec.name,
                    passed=False if spec.critical else True,  # do not pretend pass; mark skipped
                    critical=spec.critical,
                    duration_s=0.0,
                    skipped=True,
                    skip_reason="missing_required_tools:fail_fast",
                    tags=list(spec.tags),
                    description=spec.description,
                    mode="skipped",
                    attempts=0,
                )
                results_json[spec.name] = self._result_to_json(r, show_tracebacks=False)
                skipped_count += 1

            total_dur = time.monotonic() - started
            payload = {
                "ok": False,
                "failed_critical": any(spec.critical for spec in self.checks),
                "results": results_json,
                "stats": {
                    "total": total,
                    "passed": 0,
                    "failed": 0,
                    "skipped": skipped_count,
                    "duration_s": round(total_dur, 3),
                    "by_tag": self._compute_tag_stats(results_json),
                    "slowest": self._compute_slowest(results_json, top_n=top_slowest),
                },
                "exit_code": ExitCodes.CRITICAL if any(spec.critical for spec in self.checks) else ExitCodes.FAIL,
                "error": msg,
            }
            if log_summary:
                self._log_summary(payload)
            return payload

        # Otherwise: auto-skip expensive checks if missing_required_tools is set
        # (and let cheap checks run, so user still gets useful info)
        # Also: parallel scheduling must preserve stop_on_critical semantics, so we do:
        #   - sequential for criticals (and dependencies)
        #   - parallel only for eligible non-critical independent checks
        #
        # Implementation plan:
        #   Phase A: sequential pass that respects dependencies and critical stop.
        #            We run checks that are NOT parallel candidates, OR are critical, OR have deps.
        #   Phase B: parallel batch for remaining eligible checks (no deps, non-critical, parallel_safe).
        #
        # This keeps behavior predictable and avoids "critical failed but other checks kept running".

        # Build lookup for specs by name and preserve original order
        specs_by_name: Dict[str, CheckSpec] = {s.name: s for s in self.checks}

        def already_done(name: str) -> bool:
            return name in results_json

        def mark_skipped(spec: CheckSpec, reason: str) -> None:
            nonlocal skipped_count
            r = CheckResult(
                name=spec.name,
                passed=True,  # skipped counts as neither pass nor fail in human terms
                critical=spec.critical,
                duration_s=0.0,
                skipped=True,
                skip_reason=reason,
                tags=list(spec.tags),
                description=spec.description,
                mode="skipped",
                attempts=0,
            )
            results_json[spec.name] = self._result_to_json(r, show_tracebacks=False)
            skipped_count += 1

        # ---------------------------
        # Phase A: sequential checks
        # ---------------------------

        for spec in self.checks:
            if already_done(spec.name):
                continue

            # Auto-skip expensive checks if required tools missing
            if missing_required and (set(spec.tags or []) & expensive_tags):
                mark_skipped(spec, "missing_required_tools:skip_expensive")
                continue

            # Skip requested?
            sk, sk_reason = self._should_skip(spec, context)
            if sk:
                mark_skipped(spec, sk_reason or "skipped")
                continue

            # Dependencies satisfied?
            dep_ok, dep_reason = self._dependency_ok(spec, results_json)
            if not dep_ok:
                mark_skipped(spec, dep_reason or "dependency_failed")
                continue

            # Decide if this should run in Phase A or Phase B
            is_parallel_candidate = parallel and self._parallel_candidate(spec)
            has_deps = bool(spec.depends_on)
            if is_parallel_candidate and (not spec.critical) and (not has_deps):
                # defer to Phase B
                continue

            # Decide execution mode for Phase A
            # - If spec.run_in_process: subprocess
            # - Else if use_procs and spec.timeout_s: subprocess (hard timeout)
            # - Else: in-process
            run_sub = bool(spec.run_in_process) or (use_procs and spec.timeout_s is not None)

            def exec_once() -> CheckResult:
                if run_sub:
                    return self._run_check_subprocess_once(
                        spec,
                        context,
                        show_tracebacks=show_tracebacks,
                        strict_process_checks=strict_process_checks,
                        allow_context_keys=allow_context_keys,
                    )
                return self._run_check_inprocess_once(spec, context, show_tracebacks=show_tracebacks)

            try:
                r = self._run_with_retries(spec, context, executor=exec_once)
            except Exception as e:
                if strict_process_checks:
                    r = CheckResult(
                        name=spec.name,
                        passed=False,
                        critical=spec.critical,
                        duration_s=0.0,
                        error=f"Execution failed (strict mode): {e}",
                        traceback=(traceback.format_exc() if show_tracebacks else None),
                        tags=list(spec.tags),
                        description=spec.description,
                        mode="subprocess" if run_sub else "inprocess",
                        attempts=1,
                    )
                else:
                    # Best effort: if subprocess exploded, fallback to in-process once (no retry loop here)
                    self.logger.debug("Execution error for %s (%s); best-effort fallback to in-process", spec.name, e)
                    r = self._run_check_inprocess_once(spec, context, show_tracebacks=show_tracebacks)

            r = self._apply_redaction_and_caps(spec, context, r)
            results_json[spec.name] = self._result_to_json(r, show_tracebacks=show_tracebacks)

            if r.skipped:
                skipped_count += 1
            elif r.passed:
                passed_count += 1
                self.logger.debug("Validation passed: %s (%.2fs) [%s]", spec.name, r.duration_s, r.mode)
            else:
                failed_count += 1
                msg = f"Validation failed: {spec.name} ({r.duration_s:.2f}s) [{r.mode}] - {r.error or 'error'}"
                if r.critical:
                    failed_critical = True
                    self.logger.error(msg)
                    if show_tracebacks and r.traceback:
                        self.logger.error((r.traceback or "").rstrip())
                    if stop_on_critical:
                        break
                else:
                    self.logger.warning(msg)
                    if show_tracebacks and r.traceback:
                        self.logger.warning((r.traceback or "").rstrip())

        # If we stopped early on critical, skip Phase B entirely
        if failed_critical and stop_on_critical:
            total_dur = time.monotonic() - started
            ok = (failed_count == 0)
            payload = {
                "ok": ok,
                "failed_critical": failed_critical,
                "results": results_json,
                "stats": {
                    "total": total,
                    "passed": passed_count,
                    "failed": failed_count,
                    "skipped": skipped_count,
                    "duration_s": round(total_dur, 3),
                    "by_tag": self._compute_tag_stats(results_json),
                    "slowest": self._compute_slowest(results_json, top_n=top_slowest),
                },
            }
            payload["exit_code"] = ExitCodes.from_payload(payload)
            if log_summary:
                self._log_summary(payload)
            return payload

        # ---------------------------
        # Phase B: parallel checks (process-based, no threads)
        # ---------------------------

        if parallel:
            # Gather remaining candidates
            candidates: List[CheckSpec] = []
            for spec in self.checks:
                if already_done(spec.name):
                    continue

                if missing_required and (set(spec.tags or []) & expensive_tags):
                    mark_skipped(spec, "missing_required_tools:skip_expensive")
                    continue

                sk, sk_reason = self._should_skip(spec, context)
                if sk:
                    mark_skipped(spec, sk_reason or "skipped")
                    continue

                dep_ok, dep_reason = self._dependency_ok(spec, results_json)
                if not dep_ok:
                    mark_skipped(spec, dep_reason or "dependency_failed")
                    continue

                if spec.critical:
                    # keep critical sequential for predictable stop behavior
                    # run now (Phase A-style)
                    run_sub = bool(spec.run_in_process) or (use_procs and spec.timeout_s is not None)

                    def exec_once_crit() -> CheckResult:
                        if run_sub:
                            return self._run_check_subprocess_once(
                                spec,
                                context,
                                show_tracebacks=show_tracebacks,
                                strict_process_checks=strict_process_checks,
                                allow_context_keys=allow_context_keys,
                            )
                        return self._run_check_inprocess_once(spec, context, show_tracebacks=show_tracebacks)

                    try:
                        r = self._run_with_retries(spec, context, executor=exec_once_crit)
                    except Exception as e:
                        if strict_process_checks:
                            r = CheckResult(
                                name=spec.name,
                                passed=False,
                                critical=spec.critical,
                                duration_s=0.0,
                                error=f"Execution failed (strict mode): {e}",
                                traceback=(traceback.format_exc() if show_tracebacks else None),
                                tags=list(spec.tags),
                                description=spec.description,
                                mode="subprocess" if run_sub else "inprocess",
                                attempts=1,
                            )
                        else:
                            self.logger.debug(
                                "Execution error for %s (%s); best-effort fallback to in-process",
                                spec.name,
                                e,
                            )
                            r = self._run_check_inprocess_once(spec, context, show_tracebacks=show_tracebacks)

                    r = self._apply_redaction_and_caps(spec, context, r)
                    results_json[spec.name] = self._result_to_json(r, show_tracebacks=show_tracebacks)

                    if r.passed:
                        passed_count += 1
                    else:
                        failed_count += 1
                        failed_critical = True
                        self.logger.error(
                            "Validation failed: %s (%.2fs) [%s] - %s",
                            spec.name,
                            r.duration_s,
                            r.mode,
                            r.error or "error",
                        )
                        if show_tracebacks and r.traceback:
                            self.logger.error((r.traceback or "").rstrip())
                        if stop_on_critical:
                            # skip remaining not-yet-run checks
                            break

                    continue

                # Only parallel-safe checks go here
                if not self._parallel_candidate(spec):
                    # Non-parallel-safe: run sequentially now
                    run_sub = bool(spec.run_in_process) or (use_procs and spec.timeout_s is not None)

                    def exec_once_seq() -> CheckResult:
                        if run_sub:
                            return self._run_check_subprocess_once(
                                spec,
                                context,
                                show_tracebacks=show_tracebacks,
                                strict_process_checks=strict_process_checks,
                                allow_context_keys=allow_context_keys,
                            )
                        return self._run_check_inprocess_once(spec, context, show_tracebacks=show_tracebacks)

                    try:
                        r = self._run_with_retries(spec, context, executor=exec_once_seq)
                    except Exception as e:
                        if strict_process_checks:
                            r = CheckResult(
                                name=spec.name,
                                passed=False,
                                critical=spec.critical,
                                duration_s=0.0,
                                error=f"Execution failed (strict mode): {e}",
                                traceback=(traceback.format_exc() if show_tracebacks else None),
                                tags=list(spec.tags),
                                description=spec.description,
                                mode="subprocess" if run_sub else "inprocess",
                                attempts=1,
                            )
                        else:
                            self.logger.debug(
                                "Execution error for %s (%s); best-effort fallback to in-process",
                                spec.name,
                                e,
                            )
                            r = self._run_check_inprocess_once(spec, context, show_tracebacks=show_tracebacks)

                    r = self._apply_redaction_and_caps(spec, context, r)
                    results_json[spec.name] = self._result_to_json(r, show_tracebacks=show_tracebacks)

                    if r.passed:
                        passed_count += 1
                    else:
                        failed_count += 1

                    continue

                candidates.append(spec)

            # If we already hit critical stop during candidate gathering, mark rest skipped
            if failed_critical and stop_on_critical:
                for spec in self.checks:
                    if not already_done(spec.name):
                        mark_skipped(spec, "stopped_on_critical")
                candidates = []

            if candidates:
                # Determine worker count
                cpu = os.cpu_count() or 2
                mw = int(max_workers or 0) or int(context.get("max_workers", 0) or 0) or min(4, cpu)
                mw = max(1, min(mw, cpu))

                # Important: context must be pickleable for worker processes too.
                # Use same sanitization for worker context.
                worker_ctx = self._sanitize_context_for_child(context, allow_keys=allow_context_keys)
                ok_ctx, why_ctx = _can_pickle(worker_ctx)
                if not ok_ctx:
                    # If we can't pickle even sanitized context, parallelism must be disabled (deterministic)
                    self.logger.warning("Parallel disabled: worker context not pickleable: %s", why_ctx)
                    # fall back to sequential for candidates
                    for spec in candidates:
                        run_sub = bool(spec.run_in_process) or (use_procs and spec.timeout_s is not None)

                        def exec_once_fallback() -> CheckResult:
                            if run_sub:
                                return self._run_check_subprocess_once(
                                    spec,
                                    context,
                                    show_tracebacks=show_tracebacks,
                                    strict_process_checks=strict_process_checks,
                                    allow_context_keys=allow_context_keys,
                                )
                            return self._run_check_inprocess_once(spec, context, show_tracebacks=show_tracebacks)

                        r = self._run_with_retries(spec, context, executor=exec_once_fallback)
                        r.mode = "inprocess" if not run_sub else "subprocess"
                        r = self._apply_redaction_and_caps(spec, context, r)
                        results_json[spec.name] = self._result_to_json(r, show_tracebacks=show_tracebacks)
                        if r.passed:
                            passed_count += 1
                        else:
                            failed_count += 1
                else:
                    # ProcessPool for parallel checks
                    try:
                        ctxmp = mp.get_context(self.mp_start_method)
                    except Exception:
                        ctxmp = mp.get_context("spawn")

                    # Strategy:
                    # - Each candidate runs in its own *worker process* (pool).
                    # - Inside worker, if hard timeout required (timeout_s set & use_procs),
                    #   worker spawns a child process to enforce hard timeout.
                    #   (Yes, nested processes; but no threads, and timeouts remain hard.)
                    #
                    # NOTE: For heavy checks, this is fine. For micro checks, overhead exists.
                    from concurrent.futures import ProcessPoolExecutor, as_completed  # stdlib

                    # We need a top-level pickleable callable for pool. We'll ship a small function
                    # via module scope wrapper by using a staticmethod-like pattern isn't enough
                    # because 'self' isn't pickleable in a robust way across start methods.
                    #
                    # So: we run parallel checks using a helper function that re-implements the
                    # child execution logic without capturing self.
                    #
                    # This means: in parallel mode, "context_sanitizer" is not applied inside worker
                    # except by pre-sanitizing worker_ctx here.
                    #
                    # (If you want sanitizer inside workers too, make it a top-level function.)

                    def _parallel_run_one(
                        spec: CheckSpec,
                        worker_ctx_in: Dict[str, Any],
                        show_tracebacks_in: bool,
                        strict_process_checks_in: bool,
                        mp_start_method_in: str,
                        use_hard_timeout_in: bool,
                    ) -> CheckResult:
                        # Minimal clone of inprocess/subprocess once + retries + caps/redaction handled in parent.
                        def run_inproc_once() -> CheckResult:
                            t0 = time.monotonic()
                            try:
                                out = spec.func(worker_ctx_in)
                                dur = time.monotonic() - t0
                                if spec.timeout_s is not None and dur > spec.timeout_s:
                                    return CheckResult(
                                        name=spec.name,
                                        passed=False,
                                        critical=spec.critical,
                                        duration_s=dur,
                                        error=f"Check exceeded soft timeout ({dur:.2f}s > {spec.timeout_s:.2f}s)",
                                        timed_out=True,
                                        mode="parallel",
                                        tags=list(spec.tags),
                                        description=spec.description,
                                    )
                                return CheckResult(
                                    name=spec.name,
                                    passed=True,
                                    critical=spec.critical,
                                    duration_s=dur,
                                    result=out,
                                    mode="parallel",
                                    tags=list(spec.tags),
                                    description=spec.description,
                                )
                            except Exception as e:
                                dur = time.monotonic() - t0
                                tb = traceback.format_exc()
                                return CheckResult(
                                    name=spec.name,
                                    passed=False,
                                    critical=spec.critical,
                                    duration_s=dur,
                                    error=str(e),
                                    traceback=(tb if show_tracebacks_in else None),
                                    mode="parallel",
                                    tags=list(spec.tags),
                                    description=spec.description,
                                )

                        def run_subproc_once() -> CheckResult:
                            t0 = time.monotonic()
                            mode = "parallel"
                            ok_f, why_f = _can_pickle(spec.func)
                            ok_c, why_c = _can_pickle(worker_ctx_in)
                            if not ok_f or not ok_c:
                                msg = []
                                if not ok_f:
                                    msg.append(f"func not pickleable: {why_f}")
                                if not ok_c:
                                    msg.append(f"context not pickleable: {why_c}")
                                err = "; ".join(msg) or "cannot pickle for subprocess"
                                if strict_process_checks_in:
                                    return CheckResult(
                                        name=spec.name,
                                        passed=False,
                                        critical=spec.critical,
                                        duration_s=time.monotonic() - t0,
                                        error=f"Cannot run hard-timeout subprocess (strict): {err}",
                                        mode=mode,
                                        tags=list(spec.tags),
                                        description=spec.description,
                                    )
                                # fallback to inproc in worker
                                return run_inproc_once()

                            try:
                                ctxx = mp.get_context(mp_start_method_in)
                            except Exception:
                                ctxx = mp.get_context("spawn")

                            parent_conn, child_conn = ctxx.Pipe(duplex=False)
                            p = ctxx.Process(target=_child_run_check, args=(spec.func, worker_ctx_in, child_conn), daemon=True)
                            p.start()

                            timed_out = False
                            terminated = False
                            err_s: Optional[str] = None
                            tb_s: Optional[str] = None
                            result: Any = None
                            passed = False

                            timeout = spec.timeout_s
                            if timeout is None:
                                p.join()
                            else:
                                p.join(timeout)

                            if p.is_alive():
                                timed_out = True
                                terminated = True
                                try:
                                    p.terminate()
                                finally:
                                    p.join(2.0)

                            dur = time.monotonic() - t0

                            try:
                                child_conn.close()
                            except Exception:
                                pass

                            if timed_out:
                                passed = False
                                err_s = f"Check timed out after {timeout:.2f}s"
                            else:
                                try:
                                    if parent_conn.poll(0.0):
                                        kind, payload = parent_conn.recv()
                                    else:
                                        kind, payload = None, None
                                except Exception as e:
                                    kind, payload = None, None
                                    err_s = f"Failed to read subprocess result: {e}"

                                if kind == "ok":
                                    passed = True
                                    result = payload
                                elif kind == "err":
                                    passed = False
                                    try:
                                        err_s, tb_s = payload
                                    except Exception:
                                        err_s = "Subprocess reported error, but payload malformed"
                                else:
                                    passed = False
                                    err_s = f"Check subprocess exited without result ({_exitcode_hint(p.exitcode)})"

                            try:
                                parent_conn.close()
                            except Exception:
                                pass

                            return CheckResult(
                                name=spec.name,
                                passed=passed,
                                critical=spec.critical,
                                duration_s=dur,
                                result=result,
                                error=err_s,
                                traceback=(tb_s if show_tracebacks_in else None),
                                timed_out=timed_out,
                                terminated=terminated,
                                mode=mode,
                                tags=list(spec.tags),
                                description=spec.description,
                            )

                        # retries loop (same policy as suite)
                        attempts = 0
                        max_attempts = 1 + max(0, int(spec.retries or 0))
                        allow_retry = (not spec.critical) or bool(spec.retry_critical)

                        last: Optional[CheckResult] = None
                        for i in range(max_attempts):
                            attempts += 1
                            if use_hard_timeout_in and spec.timeout_s is not None:
                                rr = run_subproc_once()
                            else:
                                rr = run_inproc_once()
                            rr.attempts = attempts
                            last = rr
                            if rr.passed:
                                return rr
                            if not allow_retry:
                                return rr
                            if i >= max_attempts - 1:
                                return rr
                            _sleep_with_backoff(spec.retry_delay_s, spec.retry_backoff, i)

                        return last or CheckResult(name=spec.name, passed=False, critical=spec.critical, duration_s=0.0, error="unknown", mode="parallel")

                    use_hard_timeout = bool(use_procs)  # hard timeouts only meaningful if we allow subprocesses

                    with ProcessPoolExecutor(max_workers=mw, mp_context=ctxmp) as ex:
                        futs = {
                            ex.submit(
                                _parallel_run_one,
                                spec,
                                worker_ctx,
                                show_tracebacks,
                                strict_process_checks,
                                self.mp_start_method,
                                use_hard_timeout,
                            ): spec
                            for spec in candidates
                        }

                        for fut in as_completed(futs):
                            spec = futs[fut]
                            try:
                                r: CheckResult = fut.result()
                            except Exception as e:
                                r = CheckResult(
                                    name=spec.name,
                                    passed=False,
                                    critical=spec.critical,
                                    duration_s=0.0,
                                    error=f"Parallel worker crashed: {e}",
                                    traceback=(traceback.format_exc() if show_tracebacks else None),
                                    tags=list(spec.tags),
                                    description=spec.description,
                                    mode="parallel",
                                    attempts=1,
                                )

                            # Parent applies redaction + caps (consistent + uses global keys)
                            r = self._apply_redaction_and_caps(spec, context, r)
                            results_json[spec.name] = self._result_to_json(r, show_tracebacks=show_tracebacks)

                            if r.passed:
                                passed_count += 1
                            else:
                                failed_count += 1
                                # Non-critical only should appear here; but keep safe.
                                if r.critical:
                                    failed_critical = True

        # Any not-yet-run checks (due to ordering / critical stop) => skipped
        for spec in self.checks:
            if spec.name not in results_json:
                reason = "not_executed"
                if failed_critical and stop_on_critical:
                    reason = "stopped_on_critical"
                mark_skipped(spec, reason)

        total_dur = time.monotonic() - started
        ok = (failed_count == 0)

        payload = {
            "ok": ok,
            "failed_critical": failed_critical,
            "results": results_json,
            "stats": {
                "total": total,
                "passed": passed_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "duration_s": round(total_dur, 3),
                "by_tag": self._compute_tag_stats(results_json),
                "slowest": self._compute_slowest(results_json, top_n=top_slowest),
            },
        }
        payload["exit_code"] = ExitCodes.from_payload(payload)

        if log_summary:
            self._log_summary(payload)

        return payload

    # ---------------------------
    # Logging
    # ---------------------------

    def _log_summary(self, payload: Dict[str, Any]) -> None:
        stats = payload.get("stats", {}) or {}
        self.logger.info(
            "Validation summary: total=%s passed=%s failed=%s skipped=%s duration=%.2fs ok=%s exit_code=%s",
            stats.get("total", "?"),
            stats.get("passed", "?"),
            stats.get("failed", "?"),
            stats.get("skipped", "?"),
            float(stats.get("duration_s", 0.0)),
            bool(payload.get("ok", False)),
            payload.get("exit_code", "?"),
        )

        if payload.get("failed_critical"):
            self.logger.error("One or more CRITICAL validations failed.")

        results = payload.get("results", {}) or {}
        failed = [name for name, r in results.items() if not r.get("passed", True) and not r.get("skipped", False)]
        if failed:
            self.logger.warning("Failed validations: %s", ", ".join(failed))
