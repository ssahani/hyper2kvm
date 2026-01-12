# SPDX-License-Identifier: LGPL-3.0-or-later
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import traceback
from typing import Optional

from hyper2kvm.cli.argument_parser import parse_args_with_config
from hyper2kvm.orchestrator.orchestrator import Orchestrator as PipelineOrchestrator
from hyper2kvm.core.exceptions import Fatal


def _print_stderr(msg: str) -> None:
    print(msg, file=sys.stderr)


def _safe_log(logger, level: str, msg: str) -> None:
    """
    Best-effort logging without assuming logger exists or has a given method.
    """
    if logger is None:
        _print_stderr(msg)
        return

    fn = getattr(logger, level, None)
    if callable(fn):
        fn(msg)
    else:
        # Fallback: logger exists but missing expected method.
        _print_stderr(msg)


def main() -> None:
    logger: Optional[object] = None

    # Phase 1: parse (Fatal can happen here)
    try:
        args, _conf, logger = parse_args_with_config()
    except Fatal as e:
        # IMPORTANT: don't double-print.
        # Config loader / parse layer usually already logged via U.die(logger, ...).
        # Only print if we truly never got a logger.
        if logger is None:
            _print_stderr(f"💥 ERROR    {e}")
        raise SystemExit(getattr(e, "code", 1))
    except KeyboardInterrupt:
        _safe_log(logger, "warning", "Interrupted by user (Ctrl+C).")
        raise SystemExit(130)

    # Phase 2: run pipeline
    try:
        rc = PipelineOrchestrator(logger, args).run()
    except Fatal as e:
        # Orchestrator layer may raise Fatal without having logged it.
        # Here we DO log once.
        _safe_log(logger, "error", str(e))
        rc = getattr(e, "code", 1)
    except KeyboardInterrupt:
        _safe_log(logger, "warning", "Interrupted by user (Ctrl+C).")
        rc = 130
    except Exception as e:
        # Hard guardrail: unexpected exceptions should not fail silently.
        # Keep it concise by default; let the logger decide how much to show.
        _safe_log(logger, "error", f"💥 UNHANDLED {type(e).__name__}: {e}")
        # If your logger is configured for debug, this will land in logs.
        _safe_log(logger, "debug", traceback.format_exc())
        rc = 1

    raise SystemExit(rc)


if __name__ == "__main__":
    main()
