# SPDX-License-Identifier: LGPL-3.0-or-later
"""Hook runner for executing pre/post conversion hooks."""

from __future__ import annotations

import logging
from typing import Any

from ..core.logger import Log
from .hook_types import (
    BaseHook,
    HookError,
    HookResult,
    HookTimeoutError,
    create_hook,
)
from .template_engine import create_hook_context


class HookRunner:
    """
    Orchestrates execution of hooks at various pipeline stages.

    Hook Stages:
    - pre_extraction: Before disk extraction
    - post_extraction: After extraction, before fixes
    - pre_fix: Before offline fixes
    - post_fix: After fixes, before conversion
    - pre_convert: Before format conversion
    - post_convert: After conversion, before validation
    - post_validate: After validation complete
    """

    SUPPORTED_STAGES = [
        "pre_extraction",
        "post_extraction",
        "pre_fix",
        "post_fix",
        "pre_convert",
        "post_convert",
        "post_validate",
    ]

    def __init__(
        self,
        hooks_config: dict[str, Any],
        logger: logging.Logger | None = None,
    ):
        """
        Initialize hook runner.

        Args:
            hooks_config: Hooks configuration from manifest
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.hooks_config = hooks_config
        self.results: dict[str, list[HookResult]] = {}

    def execute_stage_hooks(
        self,
        stage: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """
        Execute all hooks for a given stage.

        Args:
            stage: Stage name (e.g., "pre_fix", "post_convert")
            context: Context variables for template substitution

        Returns:
            True if all hooks succeeded, False if any failed

        Raises:
            HookError: If a non-continue-on-error hook fails
        """
        if stage not in self.SUPPORTED_STAGES:
            self.logger.warning(
                f"Unknown hook stage: {stage}. Supported: {self.SUPPORTED_STAGES}"
            )
            return True

        # Get hooks for this stage
        stage_hooks = self.hooks_config.get(stage, [])
        if not stage_hooks:
            Log.trace(self.logger, f"No hooks configured for stage: {stage}")
            return True

        if not isinstance(stage_hooks, list):
            self.logger.error(
                f"Hooks for stage '{stage}' must be a list, got: {type(stage_hooks)}"
            )
            return True

        self.logger.info(f"🪝 Executing {len(stage_hooks)} hook(s) for stage: {stage}")

        # Initialize results for this stage
        self.results[stage] = []

        # Merge context with stage information
        full_context = context or {}
        if "stage" not in full_context:
            full_context["stage"] = stage

        all_succeeded = True

        for idx, hook_config in enumerate(stage_hooks):
            hook_id = f"{stage}[{idx}]"

            try:
                # Create and execute hook
                hook = create_hook(hook_config, full_context, self.logger)
                result = self._execute_single_hook(hook, hook_id)

                # Store result
                self.results[stage].append(result)

                if not result.success:
                    all_succeeded = False

                    # Check if we should continue
                    if not hook.continue_on_error:
                        raise HookError(
                            f"Hook {hook_id} failed and continue_on_error=False"
                        )

            except HookTimeoutError as e:
                self.logger.error(f"⏱️ Hook {hook_id} timed out: {e}")
                self.results[stage].append(
                    HookResult(success=False, duration=0.0, error=str(e))
                )
                all_succeeded = False

                # Check continue_on_error
                if not hook_config.get("continue_on_error", False):
                    raise

            except HookError as e:
                self.logger.error(f"💥 Hook {hook_id} failed: {e}")
                self.results[stage].append(
                    HookResult(success=False, duration=0.0, error=str(e))
                )
                all_succeeded = False

                # Check continue_on_error
                if not hook_config.get("continue_on_error", False):
                    raise

            except Exception as e:
                self.logger.error(f"💥 Unexpected error in hook {hook_id}: {e}")
                Log.trace(self.logger, f"Hook {hook_id} exception", exc_info=True)
                self.results[stage].append(
                    HookResult(success=False, duration=0.0, error=str(e))
                )
                all_succeeded = False

                # Always stop on unexpected errors
                raise HookError(f"Unexpected error in hook {hook_id}: {e}") from e

        # Summary
        succeeded_count = sum(1 for r in self.results[stage] if r.success)
        failed_count = len(self.results[stage]) - succeeded_count

        if all_succeeded:
            self.logger.info(
                f"✅ All {len(stage_hooks)} hook(s) for '{stage}' completed successfully"
            )
        else:
            self.logger.warning(
                f"⚠️ Stage '{stage}': {succeeded_count} succeeded, {failed_count} failed"
            )

        return all_succeeded

    def _execute_single_hook(
        self, hook: BaseHook, hook_id: str
    ) -> HookResult:
        """
        Execute a single hook with logging.

        Args:
            hook: Hook instance to execute
            hook_id: Hook identifier for logging

        Returns:
            HookResult with execution details
        """
        hook_type = hook.__class__.__name__.replace("Hook", "").lower()
        self.logger.info(f"  ⚡ Executing {hook_type} hook: {hook_id}")

        Log.trace(
            self.logger,
            "Hook %s: type=%s timeout=%d continue_on_error=%s",
            hook_id,
            hook_type,
            hook.timeout,
            hook.continue_on_error,
        )

        result = hook.execute()

        if result.success:
            self.logger.info(
                f"  ✅ Hook {hook_id} succeeded in {result.duration:.2f}s"
            )
        else:
            self.logger.error(f"  ❌ Hook {hook_id} failed in {result.duration:.2f}s")
            if result.error:
                Log.trace(self.logger, f"Hook {hook_id} error: {result.error}")

        return result

    def get_stage_results(self, stage: str) -> list[HookResult]:
        """Get results for a specific stage."""
        return self.results.get(stage, [])

    def get_all_results(self) -> dict[str, list[HookResult]]:
        """Get all hook results."""
        return self.results.copy()

    def has_hooks_for_stage(self, stage: str) -> bool:
        """Check if there are hooks configured for a stage."""
        return bool(self.hooks_config.get(stage))

    @classmethod
    def from_manifest(
        cls, manifest: dict[str, Any], logger: logging.Logger | None = None
    ) -> HookRunner | None:
        """
        Create HookRunner from an Artifact Manifest v1.

        Args:
            manifest: Artifact Manifest dictionary
            logger: Logger instance

        Returns:
            HookRunner instance if hooks are present, else None
        """
        hooks_config = manifest.get("hooks", {})

        if not hooks_config:
            return None

        # Check if there are any actual hooks configured
        has_hooks = any(
            hooks_config.get(stage) for stage in cls.SUPPORTED_STAGES
        )

        if not has_hooks:
            return None

        return cls(hooks_config, logger)
