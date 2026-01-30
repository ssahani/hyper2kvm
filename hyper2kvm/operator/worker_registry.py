"""
Worker Registry for tracking available workers and their capabilities.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class WorkerRegistry:
    """
    Registry for tracking worker pods and their capabilities.

    Maintains an in-memory cache of discovered workers with
    their capabilities, load, and availability status.
    """

    def __init__(self):
        self.workers: Dict[str, Dict[str, Any]] = {}
        self.last_update: Optional[datetime] = None

    def register_worker(
        self,
        worker_id: str,
        capabilities: Dict[str, Any],
        node: Optional[str] = None,
        pod_ip: Optional[str] = None
    ):
        """
        Register a worker with its capabilities.

        Args:
            worker_id: Unique worker identifier (pod name)
            capabilities: Worker capability information
            node: Kubernetes node name
            pod_ip: Pod IP address
        """
        self.workers[worker_id] = {
            'id': worker_id,
            'capabilities': capabilities,
            'node': node,
            'pod_ip': pod_ip,
            'registered_at': datetime.now(timezone.utc),
            'last_seen': datetime.now(timezone.utc),
            'active_jobs': 0,
            'total_jobs': 0,
            'available': True
        }

        logger.info(f"Registered worker: {worker_id} on node {node}")

    def update_worker_heartbeat(self, worker_id: str):
        """Update worker last seen timestamp."""
        if worker_id in self.workers:
            self.workers[worker_id]['last_seen'] = datetime.now(timezone.utc)

    def mark_worker_busy(self, worker_id: str):
        """Mark worker as busy (job assigned)."""
        if worker_id in self.workers:
            self.workers[worker_id]['active_jobs'] += 1
            self.workers[worker_id]['total_jobs'] += 1
            logger.debug(f"Worker {worker_id} now has {self.workers[worker_id]['active_jobs']} active jobs")

    def mark_worker_available(self, worker_id: str):
        """Mark worker as available (job completed)."""
        if worker_id in self.workers:
            if self.workers[worker_id]['active_jobs'] > 0:
                self.workers[worker_id]['active_jobs'] -= 1
            logger.debug(f"Worker {worker_id} now has {self.workers[worker_id]['active_jobs']} active jobs")

    def get_worker(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get worker information by ID."""
        return self.workers.get(worker_id)

    def list_workers(
        self,
        available_only: bool = False,
        node: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List workers matching criteria.

        Args:
            available_only: Only return workers with active_jobs == 0
            node: Filter by node name

        Returns:
            List of worker information dictionaries
        """
        workers = list(self.workers.values())

        if available_only:
            workers = [w for w in workers if w['active_jobs'] == 0 and w['available']]

        if node:
            workers = [w for w in workers if w['node'] == node]

        return workers

    def remove_worker(self, worker_id: str):
        """Remove worker from registry."""
        if worker_id in self.workers:
            logger.info(f"Removed worker: {worker_id}")
            del self.workers[worker_id]

    def clear(self):
        """Clear all workers from registry."""
        self.workers.clear()
        logger.info("Worker registry cleared")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dictionary with worker counts and job statistics
        """
        total_workers = len(self.workers)
        available_workers = len([w for w in self.workers.values() if w['active_jobs'] == 0])
        total_active_jobs = sum(w['active_jobs'] for w in self.workers.values())
        total_jobs_processed = sum(w['total_jobs'] for w in self.workers.values())

        return {
            'total_workers': total_workers,
            'available_workers': available_workers,
            'busy_workers': total_workers - available_workers,
            'total_active_jobs': total_active_jobs,
            'total_jobs_processed': total_jobs_processed,
            'last_update': self.last_update.isoformat() if self.last_update else None
        }
