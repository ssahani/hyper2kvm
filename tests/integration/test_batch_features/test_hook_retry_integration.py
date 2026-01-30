# SPDX-License-Identifier: LGPL-3.0-or-later
"""Integration tests for hook retry logic."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hyper2kvm.hooks.hook_runner import HookRunner
from hyper2kvm.hooks.hook_types import HookResult, HookTimeoutError


class TestHookRetryIntegration:
    """Integration tests for hook retry in real workflows."""

    def test_hook_retry_success_after_failure(self, tmp_path):
        """Test hook succeeding after initial failures."""
        # Create a script that fails twice then succeeds
        script = tmp_path / "retry_script.sh"
        counter_file = tmp_path / "counter.txt"
        counter_file.write_text("0")

        script_content = f"""#!/bin/bash
COUNT=$(cat {counter_file})
NEW_COUNT=$((COUNT + 1))
echo $NEW_COUNT > {counter_file}

if [ $NEW_COUNT -lt 3 ]; then
    echo "Attempt $NEW_COUNT failed"
    exit 1
else
    echo "Attempt $NEW_COUNT succeeded"
    exit 0
fi
"""
        script.write_text(script_content)
        script.chmod(0o755)

        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": str(script),
                    "retry": {
                        "max_retries": 3,
                        "initial_delay": 0.1,
                        "strategy": "constant",
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        # Should succeed on 3rd attempt
        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_exec:
            # Simulate: fail, fail, succeed
            mock_exec.side_effect = [
                HookResult(success=False, duration=0.1, error="Failed 1"),
                HookResult(success=False, duration=0.1, error="Failed 2"),
                HookResult(success=True, duration=0.1),
            ]

            result = runner.execute_stage_hooks("pre_extraction", {})

            assert result is True
            assert mock_exec.call_count == 3

    def test_hook_retry_exhausted(self, tmp_path):
        """Test hook failing after all retries exhausted."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/false",
                    "continue_on_error": True,
                    "retry": {
                        "max_retries": 2,
                        "initial_delay": 0.05,
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_exec:
            mock_exec.return_value = HookResult(
                success=False, duration=0.1, error="Always fails"
            )

            result = runner.execute_stage_hooks("pre_extraction", {})

            # Should fail after all retries
            assert result is False
            # Initial + 2 retries = 3 attempts
            assert mock_exec.call_count == 3

    def test_hook_retry_exponential_backoff(self):
        """Test exponential backoff timing."""
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

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_exec:
            mock_exec.return_value = HookResult(
                success=False, duration=0.01, error="Fail"
            )

            start = time.time()
            runner.execute_stage_hooks("pre_extraction", {})
            elapsed = time.time() - start

            # Exponential: 0.1, 0.2, 0.4 = 0.7s minimum
            assert elapsed >= 0.7
            assert mock_exec.call_count == 4

    def test_hook_retry_linear_backoff(self):
        """Test linear backoff timing."""
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

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_exec:
            mock_exec.return_value = HookResult(
                success=False, duration=0.01, error="Fail"
            )

            start = time.time()
            runner.execute_stage_hooks("pre_extraction", {})
            elapsed = time.time() - start

            # Linear: 0.1, 0.2, 0.3 = 0.6s minimum
            assert elapsed >= 0.6
            assert mock_exec.call_count == 4

    def test_hook_retry_with_max_delay_cap(self):
        """Test max_delay caps retry delays."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/false",
                    "continue_on_error": True,
                    "retry": {
                        "max_retries": 4,
                        "initial_delay": 0.1,
                        "strategy": "exponential",
                        "max_delay": 0.2,
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_exec:
            mock_exec.return_value = HookResult(
                success=False, duration=0.01, error="Fail"
            )

            start = time.time()
            runner.execute_stage_hooks("pre_extraction", {})
            elapsed = time.time() - start

            # With cap: 0.1, 0.2, 0.2, 0.2 = 0.7s
            # Without cap: 0.1, 0.2, 0.4, 0.8 = 1.5s
            assert elapsed >= 0.7
            assert elapsed < 1.2  # Much less than uncapped
            assert mock_exec.call_count == 5

    def test_hook_retry_on_timeout(self):
        """Test retry behavior on timeout."""
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

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_exec:
            # Timeout twice, then succeed
            mock_exec.side_effect = [
                HookTimeoutError("Timeout 1"),
                HookTimeoutError("Timeout 2"),
                HookResult(success=True, duration=0.1),
            ]

            result = runner.execute_stage_hooks("pre_extraction", {})

            assert result is True
            assert mock_exec.call_count == 3

    def test_hook_no_retry_on_timeout_disabled(self):
        """Test no retry when retry_on_timeout is disabled."""
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

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_exec:
            mock_exec.side_effect = HookTimeoutError("Timeout")

            result = runner.execute_stage_hooks("pre_extraction", {})

            # Should not retry
            assert result is False
            assert mock_exec.call_count == 1


class TestHookRetryInBatchWorkflow:
    """Test hook retry in batch conversion workflows."""

    def test_hooks_retry_per_vm(self, tmp_path):
        """Test that hooks retry independently for each VM."""
        call_count = {"count": 0}

        def mock_hook_exec():
            call_count["count"] += 1
            # Fail first 2 times, succeed after
            if call_count["count"] <= 2:
                return HookResult(success=False, duration=0.1, error="Fail")
            return HookResult(success=True, duration=0.1)

        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/test/hook.sh",
                    "retry": {
                        "max_retries": 3,
                        "initial_delay": 0.05,
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch(
            "hyper2kvm.hooks.hook_types.ScriptHook.execute",
            side_effect=mock_hook_exec,
        ):
            # Process first VM
            result1 = runner.execute_stage_hooks("pre_extraction", {"vm_id": "vm1"})

            # Should succeed after retries
            assert result1 is True

            # Reset for second VM
            call_count["count"] = 0

            # Process second VM (independent retry counter)
            result2 = runner.execute_stage_hooks("pre_extraction", {"vm_id": "vm2"})
            assert result2 is True

    def test_hooks_different_retry_configs_per_stage(self):
        """Test different retry configs for different hook stages."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/hook1.sh",
                    "continue_on_error": True,
                    "retry": {"max_retries": 1, "initial_delay": 0.05},
                }
            ],
            "post_convert": [
                {
                    "type": "script",
                    "path": "/hook2.sh",
                    "continue_on_error": True,
                    "retry": {"max_retries": 3, "initial_delay": 0.05},
                }
            ],
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_exec:
            mock_exec.return_value = HookResult(
                success=False, duration=0.1, error="Fail"
            )

            # Pre-extraction: 1 + 1 retry = 2 attempts
            runner.execute_stage_hooks("pre_extraction", {})
            assert mock_exec.call_count == 2

            mock_exec.reset_mock()

            # Post-convert: 1 + 3 retries = 4 attempts
            runner.execute_stage_hooks("post_convert", {})
            assert mock_exec.call_count == 4


class TestHookRetryErrorHandling:
    """Test error handling in hook retry scenarios."""

    def test_hook_retry_with_continue_on_error_false(self):
        """Test retry with continue_on_error=False raises after exhaustion."""
        from hyper2kvm.hooks.hook_types import HookError

        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/false",
                    "continue_on_error": False,
                    "retry": {
                        "max_retries": 2,
                        "initial_delay": 0.05,
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_exec:
            mock_exec.return_value = HookResult(
                success=False, duration=0.1, error="Failed"
            )

            # Should raise after all retries exhausted
            with pytest.raises(HookError):
                runner.execute_stage_hooks("pre_extraction", {})

            # Should have tried: initial + 2 retries = 3
            assert mock_exec.call_count == 3

    def test_hook_retry_partial_success_in_list(self):
        """Test retry with multiple hooks where some succeed and some fail."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/hook1.sh",
                    "continue_on_error": True,
                    "retry": {"max_retries": 1},
                },
                {
                    "type": "script",
                    "path": "/hook2.sh",
                    "continue_on_error": True,
                    "retry": {"max_retries": 1},
                },
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_exec:
            # First hook: fails all attempts
            # Second hook: succeeds on first attempt
            mock_exec.side_effect = [
                HookResult(success=False, duration=0.1, error="Fail 1"),
                HookResult(success=False, duration=0.1, error="Fail 1 retry"),
                HookResult(success=True, duration=0.1),
            ]

            result = runner.execute_stage_hooks("pre_extraction", {})

            # Overall should fail (one hook failed)
            assert result is False
            # Hook1: 2 attempts, Hook2: 1 attempt = 3 total
            assert mock_exec.call_count == 3


class TestHookRetryPerformance:
    """Test performance characteristics of hook retry."""

    def test_retry_delay_accuracy(self):
        """Test that retry delays are reasonably accurate."""
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

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_exec:
            mock_exec.return_value = HookResult(
                success=False, duration=0.01, error="Fail"
            )

            start = time.time()
            runner.execute_stage_hooks("pre_extraction", {})
            elapsed = time.time() - start

            # Expected: 2 delays of 0.2s = 0.4s
            # Allow some tolerance for execution overhead
            assert 0.4 <= elapsed <= 0.6

    def test_no_delay_overhead_on_success(self):
        """Test that successful hooks don't incur retry delay overhead."""
        hooks_config = {
            "pre_extraction": [
                {
                    "type": "script",
                    "path": "/bin/true",
                    "retry": {
                        "max_retries": 10,
                        "initial_delay": 1.0,  # Long delay (shouldn't be used)
                    },
                }
            ]
        }

        runner = HookRunner(hooks_config)

        with patch("hyper2kvm.hooks.hook_types.ScriptHook.execute") as mock_exec:
            mock_exec.return_value = HookResult(success=True, duration=0.01)

            start = time.time()
            runner.execute_stage_hooks("pre_extraction", {})
            elapsed = time.time() - start

            # Should complete quickly (no delays on success)
            assert elapsed < 0.5
            assert mock_exec.call_count == 1
