"""
Retry Manager for Failed Jobs.

Implements advanced retry logic with exponential backoff, retry budgets,
and failure threshold tracking.
"""

import logging
import math
from typing import Dict, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class BackoffStrategy(str, Enum):
    """Retry backoff strategies."""
    EXPONENTIAL = "exponential"  # 2^n seconds
    LINEAR = "linear"             # n * base_delay
    FIXED = "fixed"               # constant delay


class RetryManager:
    """
    Manages job retry logic and policies.

    Handles:
    - Retry decision making
    - Backoff calculation
    - Retry budget tracking
    - Failure threshold monitoring
    """

    def __init__(self):
        """Initialize retry manager."""
        self.retry_history: Dict[str, List[Dict[str, Any]]] = {}

    def should_retry(
        self,
        job_name: str,
        current_retries: int,
        max_retries: int,
        failure_reason: str,
        retry_policy: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if a failed job should be retried.

        Args:
            job_name: Name of the job
            current_retries: Number of retries so far
            max_retries: Maximum allowed retries
            failure_reason: Reason for failure
            retry_policy: Retry policy configuration

        Returns:
            Tuple of (should_retry, reason)
        """
        # Check retry budget
        if current_retries >= max_retries:
            return False, f"Retry budget exhausted ({current_retries}/{max_retries})"

        # Check for non-retryable errors
        non_retryable = retry_policy.get('nonRetryableErrors', [])
        for pattern in non_retryable:
            if pattern.lower() in failure_reason.lower():
                return False, f"Non-retryable error: {pattern}"

        # Check failure threshold
        failure_threshold = retry_policy.get('failureThreshold', {})
        if failure_threshold:
            is_below_threshold, threshold_reason = self._check_failure_threshold(
                job_name,
                failure_threshold
            )
            if not is_below_threshold:
                return False, threshold_reason

        return True, None

    def _check_failure_threshold(
        self,
        job_name: str,
        threshold_config: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if job is below failure threshold.

        Args:
            job_name: Name of the job
            threshold_config: Threshold configuration

        Returns:
            Tuple of (is_below_threshold, reason)
        """
        window_minutes = threshold_config.get('windowMinutes', 60)
        max_failures = threshold_config.get('maxFailures', 3)

        # Get retry history for this job
        history = self.retry_history.get(job_name, [])

        # Count failures in time window
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=window_minutes)

        failures_in_window = sum(
            1 for retry in history
            if datetime.fromisoformat(retry['timestamp']) > window_start
        )

        if failures_in_window >= max_failures:
            return False, (
                f"Failure threshold exceeded: {failures_in_window} failures "
                f"in last {window_minutes} minutes (max: {max_failures})"
            )

        return True, None

    def calculate_backoff_delay(
        self,
        retry_count: int,
        backoff_strategy: BackoffStrategy,
        base_delay_seconds: int = 10,
        max_delay_seconds: int = 3600
    ) -> int:
        """
        Calculate delay before next retry.

        Args:
            retry_count: Current retry attempt number (0-indexed)
            backoff_strategy: Backoff strategy to use
            base_delay_seconds: Base delay for calculation
            max_delay_seconds: Maximum delay cap

        Returns:
            Delay in seconds before retry
        """
        if backoff_strategy == BackoffStrategy.EXPONENTIAL:
            delay = base_delay_seconds * (2 ** retry_count)

        elif backoff_strategy == BackoffStrategy.LINEAR:
            delay = base_delay_seconds * (retry_count + 1)

        elif backoff_strategy == BackoffStrategy.FIXED:
            delay = base_delay_seconds

        else:
            delay = base_delay_seconds

        # Cap at max delay
        delay = min(delay, max_delay_seconds)

        # Add jitter (±20%)
        jitter = delay * 0.2
        import random
        delay = delay + random.uniform(-jitter, jitter)

        return int(delay)

    def get_next_retry_time(
        self,
        retry_count: int,
        retry_policy: Dict[str, Any]
    ) -> datetime:
        """
        Calculate when the next retry should occur.

        Args:
            retry_count: Current retry attempt number
            retry_policy: Retry policy configuration

        Returns:
            Datetime for next retry
        """
        backoff_str = retry_policy.get('backoff', 'exponential')
        backoff_strategy = BackoffStrategy(backoff_str)

        base_delay = retry_policy.get('baseDelaySeconds', 10)
        max_delay = retry_policy.get('maxDelaySeconds', 3600)

        delay = self.calculate_backoff_delay(
            retry_count=retry_count,
            backoff_strategy=backoff_strategy,
            base_delay_seconds=base_delay,
            max_delay_seconds=max_delay
        )

        return datetime.now(timezone.utc) + timedelta(seconds=delay)

    def record_retry(
        self,
        job_name: str,
        retry_count: int,
        failure_reason: str
    ):
        """
        Record a retry attempt.

        Args:
            job_name: Name of the job
            retry_count: Retry attempt number
            failure_reason: Reason for failure
        """
        if job_name not in self.retry_history:
            self.retry_history[job_name] = []

        self.retry_history[job_name].append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'retry_count': retry_count,
            'failure_reason': failure_reason
        })

        # Keep last 100 retries per job
        self.retry_history[job_name] = self.retry_history[job_name][-100:]

    def get_retry_stats(self, job_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get retry statistics.

        Args:
            job_name: Optional job name to filter stats

        Returns:
            Dictionary with retry statistics
        """
        if job_name:
            history = self.retry_history.get(job_name, [])
            return {
                'job_name': job_name,
                'total_retries': len(history),
                'recent_retries': history[-10:] if history else []
            }

        # Global stats
        total_jobs_with_retries = len(self.retry_history)
        total_retries = sum(len(h) for h in self.retry_history.values())

        return {
            'total_jobs_with_retries': total_jobs_with_retries,
            'total_retries': total_retries,
            'average_retries_per_job': (
                total_retries / total_jobs_with_retries
                if total_jobs_with_retries > 0 else 0
            )
        }

    def get_default_retry_policy(self) -> Dict[str, Any]:
        """
        Get default retry policy.

        Returns:
            Default retry policy configuration
        """
        return {
            'maxRetries': 3,
            'backoff': BackoffStrategy.EXPONENTIAL.value,
            'baseDelaySeconds': 10,
            'maxDelaySeconds': 3600,
            'nonRetryableErrors': [
                'invalid vmdk',
                'permission denied',
                'quota exceeded',
                'circular dependency'
            ],
            'failureThreshold': {
                'windowMinutes': 60,
                'maxFailures': 5
            }
        }

    def merge_retry_policy(
        self,
        job_policy: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Merge job-specific policy with defaults.

        Args:
            job_policy: Job-specific retry policy

        Returns:
            Merged retry policy
        """
        default = self.get_default_retry_policy()

        if not job_policy:
            return default

        # Merge policies (job policy overrides defaults)
        merged = default.copy()
        merged.update(job_policy)

        return merged

    def should_retry_immediately(
        self,
        failure_reason: str,
        retry_policy: Dict[str, Any]
    ) -> bool:
        """
        Check if retry should happen immediately (no backoff).

        Args:
            failure_reason: Reason for failure
            retry_policy: Retry policy configuration

        Returns:
            True if immediate retry recommended
        """
        immediate_retry_errors = retry_policy.get('immediateRetryErrors', [
            'worker unavailable',
            'temporary network error',
            'resource temporarily unavailable'
        ])

        for pattern in immediate_retry_errors:
            if pattern.lower() in failure_reason.lower():
                return True

        return False

    def calculate_retry_budget_remaining(
        self,
        current_retries: int,
        max_retries: int,
        time_window_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Calculate remaining retry budget.

        Args:
            current_retries: Current retry count
            max_retries: Maximum retries allowed
            time_window_hours: Time window for budget calculation

        Returns:
            Dictionary with budget information
        """
        remaining = max_retries - current_retries
        percentage_used = (current_retries / max_retries * 100) if max_retries > 0 else 0

        return {
            'remaining': remaining,
            'used': current_retries,
            'total': max_retries,
            'percentage_used': round(percentage_used, 2),
            'time_window_hours': time_window_hours,
            'is_exhausted': remaining <= 0
        }
