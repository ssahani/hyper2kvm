"""
Priority Manager for Job Preemption.

Manages job priorities, preemption policies, and priority-based scheduling.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from enum import IntEnum
from kubernetes import client

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    """Job priority levels (higher value = higher priority)."""
    CRITICAL = 100    # Critical jobs, preempt anything
    HIGH = 75         # High priority, preempt medium and low
    NORMAL = 50       # Normal priority (default)
    LOW = 25          # Low priority, can be preempted
    BACKGROUND = 0    # Background jobs, preempted first


class PreemptionPolicy(IntEnum):
    """Preemption behavior policies."""
    NEVER = 0          # Never preempt (default)
    LOWER = 1          # Preempt lower priority jobs
    SAME_OR_LOWER = 2  # Preempt same or lower priority jobs
    ALWAYS = 3         # Preempt any job (for CRITICAL only)


class PriorityManager:
    """
    Manages job priorities and preemption logic.

    Handles:
    - Priority assignment and validation
    - Preemption candidate selection
    - Preemption execution
    - Priority-based queue ordering
    """

    def __init__(self):
        """Initialize priority manager."""
        self.custom_api = client.CustomObjectsApi()
        self.preemption_history: List[Dict[str, Any]] = []

    def get_priority(self, job_spec: Dict[str, Any]) -> int:
        """
        Get effective priority for a job.

        Args:
            job_spec: Job specification

        Returns:
            Priority value (0-100)
        """
        return job_spec.get('priority', Priority.NORMAL)

    def can_preempt(
        self,
        new_job_priority: int,
        running_job_priority: int,
        preemption_policy: PreemptionPolicy = PreemptionPolicy.LOWER
    ) -> bool:
        """
        Check if a new job can preempt a running job.

        Args:
            new_job_priority: Priority of new job
            running_job_priority: Priority of currently running job
            preemption_policy: Preemption policy

        Returns:
            True if preemption is allowed
        """
        if preemption_policy == PreemptionPolicy.NEVER:
            return False

        if preemption_policy == PreemptionPolicy.ALWAYS:
            return True

        if preemption_policy == PreemptionPolicy.LOWER:
            return new_job_priority > running_job_priority

        if preemption_policy == PreemptionPolicy.SAME_OR_LOWER:
            return new_job_priority >= running_job_priority

        return False

    async def find_preemption_candidates(
        self,
        namespace: str,
        new_job_name: str,
        new_job_priority: int,
        required_slots: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Find running jobs that can be preempted.

        Args:
            namespace: Kubernetes namespace
            new_job_name: Name of job requesting resources
            new_job_priority: Priority of new job
            required_slots: Number of worker slots needed

        Returns:
            List of jobs that can be preempted (sorted by priority, lowest first)
        """
        candidates = []

        try:
            # Get all running jobs
            jobs = self.custom_api.list_namespaced_custom_object(
                group="hyper2kvm.io",
                version="v1alpha1",
                namespace=namespace,
                plural="migrationjobs"
            )

            for job in jobs.get('items', []):
                job_name = job['metadata']['name']
                spec = job.get('spec', {})
                status = job.get('status', {})

                # Skip self
                if job_name == new_job_name:
                    continue

                # Only consider running jobs
                if status.get('state') not in ['Running', 'Progressing']:
                    continue

                job_priority = self.get_priority(spec)
                preemption_policy = spec.get('preemptionPolicy', PreemptionPolicy.LOWER)

                # Check if this job can be preempted
                if self.can_preempt(new_job_priority, job_priority, preemption_policy):
                    candidates.append({
                        'name': job_name,
                        'priority': job_priority,
                        'worker': status.get('assignedWorker'),
                        'started_at': status.get('startTime'),
                        'progress': status.get('progress', {}).get('percentage', 0)
                    })

        except Exception as e:
            logger.error(f"Error finding preemption candidates: {e}")

        # Sort by priority (lowest first), then by progress (least first)
        candidates.sort(key=lambda x: (x['priority'], x['progress']))

        return candidates[:required_slots]

    async def preempt_job(
        self,
        namespace: str,
        job_name: str,
        preempted_by: str,
        reason: str = "Preempted by higher priority job"
    ) -> bool:
        """
        Preempt a running job.

        Args:
            namespace: Kubernetes namespace
            job_name: Name of job to preempt
            preempted_by: Name of job causing preemption
            reason: Reason for preemption

        Returns:
            True if preemption successful
        """
        try:
            # Get current job
            job = self.custom_api.get_namespaced_custom_object(
                group="hyper2kvm.io",
                version="v1alpha1",
                namespace=namespace,
                plural="migrationjobs",
                name=job_name
            )

            # Update status to Cancelled with preemption info
            status = job.get('status', {})
            status['state'] = 'Cancelled'
            status['completionTime'] = datetime.now(timezone.utc).isoformat()
            status['result'] = {
                'success': False,
                'errorMessage': f"{reason}: {preempted_by}"
            }
            status['preempted'] = {
                'preemptedBy': preempted_by,
                'preemptedAt': datetime.now(timezone.utc).isoformat(),
                'reason': reason
            }

            # Add condition
            conditions = status.get('conditions', [])
            conditions.append({
                'type': 'Preempted',
                'status': 'True',
                'lastTransitionTime': datetime.now(timezone.utc).isoformat(),
                'reason': 'HigherPriorityJob',
                'message': f"Preempted by {preempted_by}"
            })
            status['conditions'] = conditions[-10:]

            job['status'] = status

            # Update job
            self.custom_api.patch_namespaced_custom_object_status(
                group="hyper2kvm.io",
                version="v1alpha1",
                namespace=namespace,
                plural="migrationjobs",
                name=job_name,
                body=job
            )

            # Record preemption event
            self.preemption_history.append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'preempted_job': job_name,
                'preempted_by': preempted_by,
                'namespace': namespace
            })

            logger.info(f"Preempted job {job_name} for {preempted_by}")
            return True

        except Exception as e:
            logger.error(f"Error preempting job {job_name}: {e}")
            return False

    async def try_preempt_for_job(
        self,
        namespace: str,
        job_name: str,
        job_priority: int,
        required_slots: int = 1
    ) -> List[str]:
        """
        Try to preempt jobs to make room for a new job.

        Args:
            namespace: Kubernetes namespace
            job_name: Name of new job
            job_priority: Priority of new job
            required_slots: Number of worker slots needed

        Returns:
            List of jobs that were preempted
        """
        candidates = await self.find_preemption_candidates(
            namespace=namespace,
            new_job_name=job_name,
            new_job_priority=job_priority,
            required_slots=required_slots
        )

        if not candidates:
            logger.debug(f"No preemption candidates found for job {job_name}")
            return []

        preempted = []
        for candidate in candidates:
            success = await self.preempt_job(
                namespace=namespace,
                job_name=candidate['name'],
                preempted_by=job_name,
                reason=f"Preempted by higher priority job (priority: {job_priority} > {candidate['priority']})"
            )

            if success:
                preempted.append(candidate['name'])

        return preempted

    def get_queue_order(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Order jobs by priority for queue processing.

        Args:
            jobs: List of job dictionaries with 'name', 'spec', 'status'

        Returns:
            Jobs ordered by priority (highest first)
        """
        def priority_key(job):
            priority = self.get_priority(job.get('spec', {}))
            created_time = job.get('metadata', {}).get('creationTimestamp', '')
            # Sort by priority (desc), then creation time (asc)
            return (-priority, created_time)

        return sorted(jobs, key=priority_key)

    def get_preemption_stats(self) -> Dict[str, Any]:
        """
        Get preemption statistics.

        Returns:
            Dictionary with preemption stats
        """
        total_preemptions = len(self.preemption_history)

        if total_preemptions == 0:
            return {
                'total_preemptions': 0,
                'recent_preemptions': []
            }

        # Get last 10 preemptions
        recent = self.preemption_history[-10:]

        return {
            'total_preemptions': total_preemptions,
            'recent_preemptions': recent
        }

    def validate_priority(self, priority: int) -> Tuple[bool, Optional[str]]:
        """
        Validate priority value.

        Args:
            priority: Priority value to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(priority, int):
            return False, "Priority must be an integer"

        if priority < 0 or priority > 100:
            return False, "Priority must be between 0 and 100"

        return True, None

    def get_priority_class(self, priority: int) -> str:
        """
        Get priority class name for a priority value.

        Args:
            priority: Priority value (0-100)

        Returns:
            Priority class name
        """
        if priority >= Priority.CRITICAL:
            return "critical"
        elif priority >= Priority.HIGH:
            return "high"
        elif priority >= Priority.NORMAL:
            return "normal"
        elif priority >= Priority.LOW:
            return "low"
        else:
            return "background"
