"""
Job Assigner - Matches migration jobs to suitable workers based on capabilities.
"""

import logging
from typing import Dict, List, Optional, Any

from hyper2kvm.operator.worker_registry import WorkerRegistry

logger = logging.getLogger(__name__)


class JobAssigner:
    """
    Assigns migration jobs to workers based on:
    - Worker capabilities (NBD, LVM, formats supported)
    - Worker load (active jobs)
    - Job priority
    - Node affinity/anti-affinity
    """

    def __init__(self, worker_registry: WorkerRegistry):
        self.registry = worker_registry

    async def find_suitable_worker(
        self,
        spec: Dict[str, Any],
        workers: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Find the most suitable worker for a migration job.

        Args:
            spec: MigrationJob spec from CRD
            workers: List of available worker pods

        Returns:
            Worker pod info if suitable worker found, None otherwise
        """
        if not workers:
            logger.warning("No workers available for assignment")
            return None

        # Extract job requirements
        operation = spec.get('operation')
        image_format = spec.get('image', {}).get('format')
        priority = spec.get('priority', 50)
        worker_selector = spec.get('workerSelector', {})

        logger.debug(f"Finding worker for: operation={operation}, format={image_format}, priority={priority}")

        # Score each worker
        scored_workers = []
        for worker in workers:
            score = self._score_worker(
                worker=worker,
                operation=operation,
                image_format=image_format,
                priority=priority,
                worker_selector=worker_selector
            )

            if score > 0:
                scored_workers.append((worker, score))
                logger.debug(f"Worker {worker['name']}: score={score}")

        if not scored_workers:
            logger.warning("No suitable worker found (all workers scored 0)")
            return None

        # Sort by score (highest first) and return best match
        scored_workers.sort(key=lambda x: x[1], reverse=True)
        best_worker = scored_workers[0][0]

        logger.info(f"Selected worker {best_worker['name']} (score: {scored_workers[0][1]})")
        return best_worker

    def _score_worker(
        self,
        worker: Dict[str, Any],
        operation: str,
        image_format: Optional[str],
        priority: int,
        worker_selector: Dict[str, str]
    ) -> int:
        """
        Score a worker's suitability for a job (0-100).

        Scoring factors:
        - Capabilities match: 40 points
        - Load (fewer active jobs): 30 points
        - Priority match: 20 points
        - Node affinity: 10 points

        Args:
            worker: Worker pod information
            operation: Job operation type
            image_format: Source image format
            priority: Job priority (0-100)
            worker_selector: Label selector for worker affinity

        Returns:
            Score from 0-100 (0 = unsuitable)
        """
        score = 0

        # For discovered workers, we assume they all have basic capabilities
        # In a real implementation, we would query worker capabilities
        # For now, give basic capability score
        score += 40  # Assume all workers are capable

        # Load factor (30 points)
        # Check if worker is currently idle (no active jobs)
        worker_name = worker['name']
        worker_info = self.registry.get_worker(worker_name)

        if worker_info:
            active_jobs = worker_info.get('active_jobs', 0)
            if active_jobs == 0:
                score += 30
            elif active_jobs == 1:
                score += 20
            elif active_jobs == 2:
                score += 10
            # More than 2 jobs: 0 points
        else:
            # Worker not in registry, assume available
            score += 30

        # Priority factor (20 points)
        # Higher priority jobs prefer more available workers
        if priority > 75:
            # High priority - prefer completely idle workers
            if worker_info and worker_info.get('active_jobs', 0) == 0:
                score += 20
        elif priority > 50:
            # Medium priority
            if worker_info and worker_info.get('active_jobs', 0) <= 1:
                score += 15
        else:
            # Low priority - can go to any worker
            score += 10

        # Node affinity (10 points)
        # Check if worker labels match job's workerSelector
        if worker_selector:
            # In a real implementation, check pod labels
            # For now, give partial credit
            score += 5

        # Worker must be ready
        if not worker.get('ready', False):
            return 0  # Not ready = unsuitable

        return score

    def assign_job_to_worker(
        self,
        worker_id: str,
        job_id: str
    ):
        """
        Mark job as assigned to worker in registry.

        Args:
            worker_id: Worker identifier
            job_id: Job identifier
        """
        self.registry.mark_worker_busy(worker_id)
        logger.info(f"Assigned job {job_id} to worker {worker_id}")

    def complete_job_on_worker(
        self,
        worker_id: str,
        job_id: str
    ):
        """
        Mark job as completed on worker in registry.

        Args:
            worker_id: Worker identifier
            job_id: Job identifier
        """
        self.registry.mark_worker_available(worker_id)
        logger.info(f"Completed job {job_id} on worker {worker_id}")
