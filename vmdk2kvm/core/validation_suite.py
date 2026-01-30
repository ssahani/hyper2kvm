# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Union

from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

# A check can either return a result (anything JSON-serializable is nice),
# or raise to indicate failure.
CheckFunc = Callable[[Dict[str, Any]], Any]


class SupportsRichConsole(Protocol):
    # minimal protocol so we don't hard-depend on rich Console types
    def print(self, *args: Any, **kwargs: Any) -> Any: ...


@dataclass
class CheckSpec:
    name: str
    func: CheckFunc
    critical: bool = False
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    timeout_s: Optional[float] = None  # soft timeout: we mark as failed if exceeded


@dataclass
class CheckResult:
    name: str
    passed: bool
    critical: bool
    duration_s: float
    result: Any = None
    error: Optional[str] = None
    traceback: Optional[str] = None
    skipped: bool = False
    tags: List[str] = field(default_factory=list)


class ValidationSuite:
    """
    Enhanced validation runner:
      - typed CheckSpec/CheckResult
      - per-check duration timing (+ optional soft timeout)
      - skip support via context flags (e.g., context["skip_tags"] = {"network"})
      - critical failure can stop the suite early (stop_on_critical=True)
      - richer progress text: shows current check name
      - optional summary logging
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.checks: List[CheckSpec] = []

    def add_check(
        self,
        name: str,
        check_func: CheckFunc,
        critical: bool = False,
        *,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        timeout_s: Optional[float] = None,
    ) -> None:
        self.checks.append(
            CheckSpec(
                name=name,
                func=check_func,
                critical=critical,
                description=description,
                tags=tags or [],
                timeout_s=timeout_s,
            )
        )

    def _should_skip(self, spec: CheckSpec, context: Dict[str, Any]) -> bool:
        # Supported skip mechanisms:
        #   context["skip_checks"] = {"name1", "name2"}
        #   context["skip_tags"]   = {"network", "slow"}
        skip_checks = set(context.get("skip_checks", []) or [])
        skip_tags = set(context.get("skip_tags", []) or [])
        if spec.name in skip_checks:
            return True
        if spec.tags and (set(spec.tags) & skip_tags):
            return True
        return False

    def run_all(
        self,
        context: Dict[str, Any],
        *,
        stop_on_critical: bool = True,
        show_tracebacks: bool = False,
        log_summary: bool = True,
    ) -> Dict[str, Any]:
        """
        Returns a dict suitable for JSON:
          {
            "ok": bool,
            "failed_critical": bool,
            "results": {name: {...}},
            "stats": {...}
          }
        """
        started = time.monotonic()
        results_by_name: Dict[str, Dict[str, Any]] = {}
        failed_critical = False
        passed_count = 0
        failed_count = 0
        skipped_count = 0

        total = len(self.checks)

        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Running validations", total=total)

            for spec in self.checks:
                # Update UI to show what we're doing
                desc = spec.description or spec.name
                progress.update(task, description=f"Validating: {desc}")

                if self._should_skip(spec, context):
                    r = CheckResult(
                        name=spec.name,
                        passed=True,
                        critical=spec.critical,
                        duration_s=0.0,
                        skipped=True,
                        tags=list(spec.tags),
                        result="skipped",
                    )
                    results_by_name[spec.name] = self._result_to_json(r, show_tracebacks=False)
                    self.logger.debug("Validation skipped: %s", spec.name)
                    skipped_count += 1
                    progress.update(task, advance=1)
                    continue

                t0 = time.monotonic()
                try:
                    out = spec.func(context)
                    dur = time.monotonic() - t0

                    # Soft timeout: we can't stop the function without threads/signals,
                    # but we can fail if it exceeded the budget.
                    if spec.timeout_s is not None and dur > spec.timeout_s:
                        raise TimeoutError(f"Check exceeded timeout ({dur:.2f}s > {spec.timeout_s:.2f}s)")

                    r = CheckResult(
                        name=spec.name,
                        passed=True,
                        critical=spec.critical,
                        duration_s=dur,
                        result=out,
                        tags=list(spec.tags),
                    )
                    results_by_name[spec.name] = self._result_to_json(r, show_tracebacks=show_tracebacks)
                    passed_count += 1
                    self.logger.debug("Validation passed: %s (%.2fs)", spec.name, dur)

                except Exception as e:
                    dur = time.monotonic() - t0
                    tb = traceback.format_exc()

                    r = CheckResult(
                        name=spec.name,
                        passed=False,
                        critical=spec.critical,
                        duration_s=dur,
                        error=str(e),
                        traceback=tb,
                        tags=list(spec.tags),
                    )
                    results_by_name[spec.name] = self._result_to_json(r, show_tracebacks=show_tracebacks)
                    failed_count += 1

                    msg = f"Validation failed: {spec.name} ({dur:.2f}s) - {e}"
                    if spec.critical:
                        failed_critical = True
                        self.logger.error(msg)
                        if show_tracebacks:
                            self.logger.error(tb.rstrip())
                        if stop_on_critical:
                            progress.update(task, advance=1)
                            break
                    else:
                        self.logger.warning(msg)
                        if show_tracebacks:
                            self.logger.warning(tb.rstrip())

                progress.update(task, advance=1)

        total_dur = time.monotonic() - started
        ok = (failed_count == 0) if stop_on_critical else (not failed_critical)

        payload = {
            "ok": ok,
            "failed_critical": failed_critical,
            "results": results_by_name,
            "stats": {
                "total": total,
                "passed": passed_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "duration_s": round(total_dur, 3),
            },
        }

        if log_summary:
            self._log_summary(payload)

        return payload

    @staticmethod
    def _result_to_json(r: CheckResult, *, show_tracebacks: bool) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "passed": r.passed,
            "critical": r.critical,
            "duration_s": round(r.duration_s, 3),
            "skipped": r.skipped,
            "tags": list(r.tags),
        }
        if r.passed:
            d["result"] = r.result
        else:
            d["error"] = r.error or "unknown error"
            if show_tracebacks and r.traceback:
                d["traceback"] = r.traceback
        return d

    def _log_summary(self, payload: Dict[str, Any]) -> None:
        stats = payload.get("stats", {})
        self.logger.info(
            "Validation summary: total=%s passed=%s failed=%s skipped=%s duration=%.2fs ok=%s",
            stats.get("total", "?"),
            stats.get("passed", "?"),
            stats.get("failed", "?"),
            stats.get("skipped", "?"),
            float(stats.get("duration_s", 0.0)),
            payload.get("ok", False),
        )

        if payload.get("failed_critical"):
            self.logger.error("One or more CRITICAL validations failed.")

        # List failures compactly
        results = payload.get("results", {}) or {}
        failed = [name for name, r in results.items() if not r.get("passed", True)]
        if failed:
            self.logger.warning("Failed validations: %s", ", ".join(failed))
