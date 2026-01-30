# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for hook retry logic."""

import time
from unittest.mock import MagicMock, patch

import pytest

from hyper2kvm.hooks.hook_runner import HookRunner
from hyper2kvm.hooks.hook_types import HookResult, HookTimeoutError


class TestHookRetry:
    """Test hook retry functionality."""

    def test_no_retry_on_success(self):
        """Test that successful hooks don't retry."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/true",
                    "retry": {
                        "max_retries": 3,
                        "initial_delay": 0.1,
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_execute:
            mock_execute.return_value = HookResult(success=True, duration=0.1)

            result = runner.execute_stage_hooks("pre_extraction", {})

            # Should only execute once (no retries on success)
            assert mock_execute.call_count == 1
            assert result is True

    def test_retry_on_failure_exponential(self):
        """Test exponential backoff retry on failure."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/false",
                    "continue_on_error": True,
                    "retry": {
                        "max_retries": 3,
                        "initial_delay": 0.1,
                        "strategy": "exponential",
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_execute:
            # Fail all attempts
            mock_execute.return_value = HookResult(success=False, duration=0.1, error="Failed")

            start_time = time.time()
            result = runner.execute_stage_hooks("pre_extraction", {})
            elapsed = time.time() - start_time

            # Should execute 4 times (initial + 3 retries)
            assert mock_execute.call_count == 4

            # Check that exponential backoff was applied
            # Delays: 0.1, 0.2, 0.4 = 0.7s minimum
            assert elapsed >= 0.7
            assert result is False  # All hooks failed, even with continue_on_error=True

    def test_retry_on_failure_linear(self):
        """Test linear backoff retry on failure."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/false",
                    "continue_on_error": True,
                    "retry": {
                        "max_retries": 3,
                        "initial_delay": 0.1,
                        "strategy": "linear",
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_execute:
            mock_execute.return_value = HookResult(success=False, duration=0.1, error="Failed")

            start_time = time.time()
            result = runner.execute_stage_hooks("pre_extraction", {})
            elapsed = time.time() - start_time

            # Should execute 4 times
            assert mock_execute.call_count == 4

            # Linear delays: 0.1, 0.2, 0.3 = 0.6s minimum
            assert elapsed >= 0.6

    def test_retry_on_failure_constant(self):
        """Test constant delay retry on failure."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/false",
                    "continue_on_error": True,
                    "retry": {
                        "max_retries": 3,
                        "initial_delay": 0.1,
                        "strategy": "constant",
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_execute:
            mock_execute.return_value = HookResult(success=False, duration=0.1, error="Failed")

            start_time = time.time()
            result = runner.execute_stage_hooks("pre_extraction", {})
            elapsed = time.time() - start_time

            # Should execute 4 times
            assert mock_execute.call_count == 4

            # Constant delays: 0.1, 0.1, 0.1 = 0.3s minimum
            assert elapsed >= 0.3

    def test_success_on_retry(self):
        """Test hook succeeding after retry."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/test",
                    "retry": {
                        "max_retries": 3,
                        "initial_delay": 0.05,
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_execute:
            # Fail twice, succeed on third attempt
            mock_execute.side_effect = [
                HookResult(success=False, duration=0.1, error="Failed 1"),
                HookResult(success=False, duration=0.1, error="Failed 2"),
                HookResult(success=True, duration=0.1),
            ]

            result = runner.execute_stage_hooks("pre_extraction", {})

            # Should execute 3 times (2 failures + 1 success)
            assert mock_execute.call_count == 3
            assert result is True

    def test_max_delay_cap(self):
        """Test that max_delay caps the retry delay."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/false",
                    "continue_on_error": True,
                    "retry": {
                        "max_retries": 5,
                        "initial_delay": 0.1,
                        "strategy": "exponential",
                        "max_delay": 0.2,  # Cap at 0.2s
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_execute:
            mock_execute.return_value = HookResult(success=False, duration=0.1, error="Failed")

            start_time = time.time()
            result = runner.execute_stage_hooks("pre_extraction", {})
            elapsed = time.time() - start_time

            # Should execute 6 times (initial + 5 retries)
            assert mock_execute.call_count == 6

            # With max_delay=0.2, delays should be: 0.1, 0.2, 0.2, 0.2, 0.2 = 0.9s
            # Without cap, would be: 0.1, 0.2, 0.4, 0.8, 1.6 = 3.1s
            assert elapsed >= 0.9
            assert elapsed < 1.5  # Much less than uncapped 3.1s

    def test_retry_on_timeout_enabled(self):
        """Test retry on timeout when enabled."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/sleep",
                    "timeout": 1,
                    "continue_on_error": True,
                    "retry": {
                        "max_retries": 2,
                        "initial_delay": 0.05,
                        "retry_on_timeout": True,
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_execute:
            # Timeout twice, then succeed
            mock_execute.side_effect = [
                HookTimeoutError("Timeout 1"),
                HookTimeoutError("Timeout 2"),
                HookResult(success=True, duration=0.1),
            ]

            result = runner.execute_stage_hooks("pre_extraction", {})

            # Should retry on timeouts and eventually succeed
            assert mock_execute.call_count == 3
            assert result is True

    def test_retry_on_timeout_disabled(self):
        """Test no retry on timeout when disabled."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/sleep",
                    "timeout": 1,
                    "continue_on_error": True,
                    "retry": {
                        "max_retries": 3,
                        "initial_delay": 0.05,
                        "retry_on_timeout": False,
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_execute:
            mock_execute.side_effect = HookTimeoutError("Timeout")

            result = runner.execute_stage_hooks("pre_extraction", {})

            # Should not retry on timeout
            assert mock_execute.call_count == 1
            assert result is False  # Hook failed (timeout), even with continue_on_error=True

    def test_no_retry_by_default(self):
        """Test that hooks don't retry by default (backward compatibility)."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/false",
                    "continue_on_error": True,
                    # No retry config
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_execute:
            mock_execute.return_value = HookResult(success=False, duration=0.1, error="Failed")

            result = runner.execute_stage_hooks("pre_extraction", {})

            # Should execute only once (no retries by default)
            assert mock_execute.call_count == 1

    def test_zero_max_retries(self):
        """Test explicit max_retries=0 means no retries."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/false",
                    "continue_on_error": True,
                    "retry": {
                        "max_retries": 0,
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_execute:
            mock_execute.return_value = HookResult(success=False, duration=0.1, error="Failed")

            result = runner.execute_stage_hooks("pre_extraction", {})

            # Should execute only once
            assert mock_execute.call_count == 1

    def test_continue_on_error_false_stops_retries(self):
        """Test that continue_on_error=False raises exception after retries."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/false",
                    "continue_on_error": False,
                    "retry": {
                        "max_retries": 3,
                        "initial_delay": 0.05,
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_execute:
            mock_execute.return_value = HookResult(success=False, duration=0.1, error="Failed")

            # Should raise HookError after all retries exhausted
            from hyper2kvm.hooks.hook_types import HookError

            with pytest.raises(HookError, match="failed and continue_on_error=False"):
                runner.execute_stage_hooks("pre_extraction", {})

            # Should execute 4 times (initial + 3 retries) before raising
            assert mock_execute.call_count == 4

    def test_multiple_hooks_with_different_retry_configs(self):
        """Test multiple hooks with different retry configurations."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/hook1",
                    "continue_on_error": True,
                    "retry": {
                        "max_retries": 1,
                    },
                },
                {
                    "type": "script",
                    "path": "/hook2",
                    "continue_on_error": True,
                    "retry": {
                        "max_retries": 2,
                    },
                },
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_execute:
            # All hooks fail
            mock_execute.return_value = HookResult(success=False, duration=0.1, error="Failed")

            result = runner.execute_stage_hooks("pre_extraction", {})

            # Hook 1: 2 executions (initial + 1 retry)
            # Hook 2: 3 executions (initial + 2 retries)
            # Total: 5 executions
            assert mock_execute.call_count == 5
            assert result is False  # All hooks failed, even with continue_on_error=True

    def test_retry_with_custom_delays(self):
        """Test retry with custom delay values."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/false",
                    "continue_on_error": True,
                    "retry": {
                        "max_retries": 2,
                        "initial_delay": 0.2,
                        "strategy": "constant",
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_execute:
            mock_execute.return_value = HookResult(success=False, duration=0.1, error="Failed")

            start_time = time.time()
            result = runner.execute_stage_hooks("pre_extraction", {})
            elapsed = time.time() - start_time

            # Should execute 3 times (initial + 2 retries)
            assert mock_execute.call_count == 3

            # Constant delays: 0.2, 0.2 = 0.4s minimum
            assert elapsed >= 0.4
