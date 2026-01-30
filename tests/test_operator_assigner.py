"""
Unit tests for job assigner and worker registry.
"""

import pytest
from hyper2kvm.operator.worker_registry import WorkerRegistry
from hyper2kvm.operator.job_assigner import JobAssigner


class TestWorkerRegistry:
    """Test worker registry functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.registry = WorkerRegistry()

    def test_register_worker(self):
        """Test registering a worker."""
        self.registry.register_worker(
            worker_id='worker-1',
            capabilities={'operations': ['convert', 'inspect']},
            node='node-1',
            pod_ip='10.42.0.5'
        )

        worker = self.registry.get_worker('worker-1')
        assert worker is not None
        assert worker['id'] == 'worker-1'
        assert worker['node'] == 'node-1'
        assert worker['active_jobs'] == 0

    def test_mark_worker_busy(self):
        """Test marking worker as busy."""
        self.registry.register_worker(
            worker_id='worker-1',
            capabilities={},
            node='node-1'
        )

        self.registry.mark_worker_busy('worker-1')

        worker = self.registry.get_worker('worker-1')
        assert worker['active_jobs'] == 1
        assert worker['total_jobs'] == 1

    def test_mark_worker_available(self):
        """Test marking worker as available."""
        self.registry.register_worker(
            worker_id='worker-1',
            capabilities={},
            node='node-1'
        )

        # Mark busy then available
        self.registry.mark_worker_busy('worker-1')
        self.registry.mark_worker_busy('worker-1')
        self.registry.mark_worker_available('worker-1')

        worker = self.registry.get_worker('worker-1')
        assert worker['active_jobs'] == 1
        assert worker['total_jobs'] == 2

    def test_list_available_workers(self):
        """Test listing only available workers."""
        self.registry.register_worker('worker-1', {}, 'node-1')
        self.registry.register_worker('worker-2', {}, 'node-2')
        self.registry.register_worker('worker-3', {}, 'node-3')

        # Mark worker-2 as busy
        self.registry.mark_worker_busy('worker-2')

        available = self.registry.list_workers(available_only=True)
        assert len(available) == 2
        assert all(w['active_jobs'] == 0 for w in available)

    def test_list_workers_by_node(self):
        """Test filtering workers by node."""
        self.registry.register_worker('worker-1', {}, 'node-1')
        self.registry.register_worker('worker-2', {}, 'node-2')
        self.registry.register_worker('worker-3', {}, 'node-1')

        node1_workers = self.registry.list_workers(node='node-1')
        assert len(node1_workers) == 2
        assert all(w['node'] == 'node-1' for w in node1_workers)

    def test_remove_worker(self):
        """Test removing a worker."""
        self.registry.register_worker('worker-1', {}, 'node-1')
        assert self.registry.get_worker('worker-1') is not None

        self.registry.remove_worker('worker-1')
        assert self.registry.get_worker('worker-1') is None

    def test_get_stats(self):
        """Test getting registry statistics."""
        self.registry.register_worker('worker-1', {}, 'node-1')
        self.registry.register_worker('worker-2', {}, 'node-2')
        self.registry.mark_worker_busy('worker-1')

        stats = self.registry.get_stats()

        assert stats['total_workers'] == 2
        assert stats['available_workers'] == 1
        assert stats['busy_workers'] == 1
        assert stats['total_active_jobs'] == 1

    def test_clear_registry(self):
        """Test clearing all workers."""
        self.registry.register_worker('worker-1', {}, 'node-1')
        self.registry.register_worker('worker-2', {}, 'node-2')

        self.registry.clear()

        assert len(self.registry.list_workers()) == 0


class TestJobAssigner:
    """Test job assignment logic."""

    def setup_method(self):
        """Setup test fixtures."""
        self.registry = WorkerRegistry()
        self.assigner = JobAssigner(self.registry)

    @pytest.mark.asyncio
    async def test_assign_to_idle_worker(self):
        """Test job is assigned to idle worker."""
        # Register workers
        self.registry.register_worker('worker-1', {}, 'node-1')
        self.registry.register_worker('worker-2', {}, 'node-2')

        # Mark worker-1 as busy
        self.registry.mark_worker_busy('worker-1')

        workers = [
            {'name': 'worker-1', 'ready': True},
            {'name': 'worker-2', 'ready': True}
        ]

        spec = {
            'operation': 'convert',
            'image': {'format': 'vmdk'},
            'priority': 50
        }

        best_worker = await self.assigner.find_suitable_worker(spec, workers)

        # Should prefer idle worker-2
        assert best_worker is not None
        assert best_worker['name'] == 'worker-2'

    @pytest.mark.asyncio
    async def test_no_workers_available(self):
        """Test assignment when no workers available."""
        spec = {
            'operation': 'convert',
            'image': {'format': 'vmdk'},
            'priority': 50
        }

        best_worker = await self.assigner.find_suitable_worker(spec, [])

        assert best_worker is None

    @pytest.mark.asyncio
    async def test_worker_not_ready(self):
        """Test unready workers are rejected."""
        workers = [
            {'name': 'worker-1', 'ready': False}  # Not ready
        ]

        spec = {
            'operation': 'convert',
            'image': {'format': 'vmdk'},
            'priority': 50
        }

        best_worker = await self.assigner.find_suitable_worker(spec, workers)

        assert best_worker is None

    @pytest.mark.asyncio
    async def test_high_priority_prefers_idle(self):
        """Test high priority job prefers completely idle worker."""
        self.registry.register_worker('worker-1', {}, 'node-1')
        self.registry.register_worker('worker-2', {}, 'node-2')

        # Worker-1 has 1 job, worker-2 is idle
        self.registry.mark_worker_busy('worker-1')

        workers = [
            {'name': 'worker-1', 'ready': True},
            {'name': 'worker-2', 'ready': True}
        ]

        spec = {
            'operation': 'convert',
            'image': {'format': 'vmdk'},
            'priority': 90  # High priority
        }

        best_worker = await self.assigner.find_suitable_worker(spec, workers)

        # Should strongly prefer idle worker for high priority
        assert best_worker['name'] == 'worker-2'

    def test_scoring_algorithm(self):
        """Test worker scoring algorithm."""
        # Test with idle worker
        score = self.assigner._score_worker(
            worker={'name': 'worker-1', 'ready': True},
            operation='convert',
            image_format='vmdk',
            priority=50,
            worker_selector={}
        )

        # Should get:
        # - Capabilities: 40
        # - Load (idle): 30
        # - Priority: ~10
        # - Affinity: ~5
        # Total: ~85

        assert score >= 80
        assert score <= 100

    def test_scoring_busy_worker(self):
        """Test scoring for busy worker."""
        self.registry.register_worker('worker-1', {}, 'node-1')
        self.registry.mark_worker_busy('worker-1')
        self.registry.mark_worker_busy('worker-1')

        score = self.assigner._score_worker(
            worker={'name': 'worker-1', 'ready': True},
            operation='convert',
            image_format='vmdk',
            priority=50,
            worker_selector={}
        )

        # Busy worker should score lower (no load points)
        assert score < 70

    def test_scoring_unready_worker(self):
        """Test unready worker scores 0."""
        score = self.assigner._score_worker(
            worker={'name': 'worker-1', 'ready': False},
            operation='convert',
            image_format='vmdk',
            priority=50,
            worker_selector={}
        )

        assert score == 0

    def test_assign_job_to_worker(self):
        """Test assigning job updates registry."""
        self.registry.register_worker('worker-1', {}, 'node-1')

        self.assigner.assign_job_to_worker('worker-1', 'job-123')

        worker = self.registry.get_worker('worker-1')
        assert worker['active_jobs'] == 1
        assert worker['total_jobs'] == 1

    def test_complete_job_on_worker(self):
        """Test completing job updates registry."""
        self.registry.register_worker('worker-1', {}, 'node-1')
        self.registry.mark_worker_busy('worker-1')

        self.assigner.complete_job_on_worker('worker-1', 'job-123')

        worker = self.registry.get_worker('worker-1')
        assert worker['active_jobs'] == 0


class TestScoringScenarios:
    """Test realistic scoring scenarios."""

    def setup_method(self):
        """Setup test fixtures."""
        self.registry = WorkerRegistry()
        self.assigner = JobAssigner(self.registry)

    def test_three_worker_scenario(self):
        """Test scoring with three workers in different states."""
        # Register workers with different loads
        self.registry.register_worker('worker-1', {}, 'node-1')  # Idle
        self.registry.register_worker('worker-2', {}, 'node-2')  # 1 job
        self.registry.register_worker('worker-3', {}, 'node-3')  # 2 jobs

        self.registry.mark_worker_busy('worker-2')
        self.registry.mark_worker_busy('worker-3')
        self.registry.mark_worker_busy('worker-3')

        workers = [
            {'name': 'worker-1', 'ready': True},
            {'name': 'worker-2', 'ready': True},
            {'name': 'worker-3', 'ready': True}
        ]

        # Score each worker for high-priority job
        scores = {}
        for worker in workers:
            score = self.assigner._score_worker(
                worker=worker,
                operation='convert',
                image_format='vmdk',
                priority=90,
                worker_selector={}
            )
            scores[worker['name']] = score

        # Idle worker should score highest
        assert scores['worker-1'] > scores['worker-2']
        assert scores['worker-2'] > scores['worker-3']

    def test_low_priority_job_accepts_busy_worker(self):
        """Test low priority job can use busy workers."""
        self.registry.register_worker('worker-1', {}, 'node-1')
        self.registry.mark_worker_busy('worker-1')

        score = self.assigner._score_worker(
            worker={'name': 'worker-1', 'ready': True},
            operation='convert',
            image_format='vmdk',
            priority=20,  # Low priority
            worker_selector={}
        )

        # Should still get reasonable score
        # Capabilities: 40, Load: 20, Priority: 10, Affinity: ~5
        assert score >= 60
