"""
Unit tests for DAG Validator.

Tests dependency graph validation, cycle detection, and execution planning.
"""

import pytest
from hyper2kvm.operator.dag_validator import (
    DAGValidator,
    CyclicDependencyError,
    InvalidDependencyError
)


class TestDAGValidator:
    """Test DAG validator functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.validator = DAGValidator()

    def test_add_job_no_dependencies(self):
        """Test adding a job with no dependencies."""
        self.validator.add_job("job1", [], "Created")

        assert "job1" in self.validator.graph
        assert len(self.validator.graph["job1"]) == 0
        assert self.validator.job_states["job1"] == "Created"

    def test_add_job_with_dependencies(self):
        """Test adding a job with dependencies."""
        self.validator.add_job("job1", [], "Created")
        self.validator.add_job("job2", ["job1"], "Created")

        assert "job2" in self.validator.graph
        assert "job1" in self.validator.graph["job2"]
        assert "job2" in self.validator.reverse_graph["job1"]

    def test_validate_no_cycle(self):
        """Test validation with valid DAG (no cycle)."""
        self.validator.add_job("job1", [], "Created")
        self.validator.add_job("job2", ["job1"], "Created")

        is_valid, error = self.validator.validate("job3", ["job1", "job2"])

        assert is_valid is True
        assert error is None

    def test_validate_self_dependency(self):
        """Test validation fails for self-dependency."""
        is_valid, error = self.validator.validate("job1", ["job1"])

        assert is_valid is False
        assert "cannot depend on itself" in error

    def test_validate_direct_cycle(self):
        """Test detection of direct cycle (A -> B -> A)."""
        self.validator.add_job("job1", [], "Created")
        self.validator.add_job("job2", ["job1"], "Created")

        is_valid, error = self.validator.validate("job1", ["job2"])

        assert is_valid is False
        assert "Circular dependency" in error

    def test_validate_indirect_cycle(self):
        """Test detection of indirect cycle (A -> B -> C -> A)."""
        self.validator.add_job("job1", [], "Created")
        self.validator.add_job("job2", ["job1"], "Created")
        self.validator.add_job("job3", ["job2"], "Created")

        is_valid, error = self.validator.validate("job1", ["job3"])

        assert is_valid is False
        assert "Circular dependency" in error

    def test_get_ready_jobs_no_dependencies(self):
        """Test getting ready jobs with no dependencies."""
        self.validator.add_job("job1", [], "Queued")
        self.validator.add_job("job2", [], "Validated")

        ready = self.validator.get_ready_jobs()

        assert "job1" in ready
        assert "job2" in ready

    def test_get_ready_jobs_with_dependencies(self):
        """Test getting ready jobs when dependencies are met."""
        self.validator.add_job("job1", [], "Completed")
        self.validator.add_job("job2", ["job1"], "Queued")
        self.validator.add_job("job3", ["job1"], "Validated")

        ready = self.validator.get_ready_jobs()

        assert "job2" in ready
        assert "job3" in ready
        assert "job1" not in ready  # Already completed

    def test_get_ready_jobs_blocked(self):
        """Test jobs not ready when dependencies incomplete."""
        self.validator.add_job("job1", [], "Running")
        self.validator.add_job("job2", ["job1"], "Queued")

        ready = self.validator.get_ready_jobs()

        assert "job2" not in ready

    def test_get_blocked_jobs(self):
        """Test getting blocked jobs."""
        self.validator.add_job("job1", [], "Running")
        self.validator.add_job("job2", [], "Created")
        self.validator.add_job("job3", ["job1", "job2"], "Queued")

        blocked = self.validator.get_blocked_jobs()

        assert "job3" in blocked
        assert "job1" in blocked["job3"]
        assert "job2" in blocked["job3"]

    def test_topological_sort_linear(self):
        """Test topological sort on linear dependency chain."""
        self.validator.add_job("job1", [], "Created")
        self.validator.add_job("job2", ["job1"], "Created")
        self.validator.add_job("job3", ["job2"], "Created")

        sorted_jobs = self.validator.topological_sort()

        # Job1 must come before job2, job2 before job3
        assert sorted_jobs.index("job1") < sorted_jobs.index("job2")
        assert sorted_jobs.index("job2") < sorted_jobs.index("job3")

    def test_topological_sort_parallel(self):
        """Test topological sort with parallel branches."""
        self.validator.add_job("job1", [], "Created")
        self.validator.add_job("job2", ["job1"], "Created")
        self.validator.add_job("job3", ["job1"], "Created")
        self.validator.add_job("job4", ["job2", "job3"], "Created")

        sorted_jobs = self.validator.topological_sort()

        # Job1 must be first
        assert sorted_jobs[0] == "job1"
        # Job4 must be last
        assert sorted_jobs[-1] == "job4"
        # Job2 and job3 can be in any order

    def test_topological_sort_with_cycle(self):
        """Test topological sort fails with cycle."""
        self.validator.add_job("job1", ["job2"], "Created")
        self.validator.add_job("job2", ["job1"], "Created")

        with pytest.raises(CyclicDependencyError):
            self.validator.topological_sort()

    def test_update_job_state(self):
        """Test updating job state."""
        self.validator.add_job("job1", [], "Created")
        self.validator.update_job_state("job1", "Running")

        assert self.validator.job_states["job1"] == "Running"

    def test_get_dependents(self):
        """Test getting dependent jobs."""
        self.validator.add_job("job1", [], "Created")
        self.validator.add_job("job2", ["job1"], "Created")
        self.validator.add_job("job3", ["job1"], "Created")

        dependents = self.validator.get_dependents("job1")

        assert "job2" in dependents
        assert "job3" in dependents

    def test_get_dependencies(self):
        """Test getting job dependencies."""
        self.validator.add_job("job1", [], "Created")
        self.validator.add_job("job2", ["job1"], "Created")

        deps = self.validator.get_dependencies("job2")

        assert "job1" in deps

    def test_can_execute_no_dependencies(self):
        """Test can execute with no dependencies."""
        self.validator.add_job("job1", [], "Created")

        can_exec, reason = self.validator.can_execute("job1")

        assert can_exec is True
        assert reason is None

    def test_can_execute_dependencies_completed(self):
        """Test can execute when all dependencies completed."""
        self.validator.add_job("job1", [], "Completed")
        self.validator.add_job("job2", ["job1"], "Created")

        can_exec, reason = self.validator.can_execute("job2")

        assert can_exec is True
        assert reason is None

    def test_can_execute_dependencies_incomplete(self):
        """Test cannot execute when dependencies incomplete."""
        self.validator.add_job("job1", [], "Running")
        self.validator.add_job("job2", ["job1"], "Created")

        can_exec, reason = self.validator.can_execute("job2")

        assert can_exec is False
        assert "Waiting for dependencies" in reason

    def test_can_execute_dependencies_failed(self):
        """Test cannot execute when dependencies failed."""
        self.validator.add_job("job1", [], "Failed")
        self.validator.add_job("job2", ["job1"], "Created")

        can_exec, reason = self.validator.can_execute("job2")

        assert can_exec is False
        assert "Dependencies failed" in reason

    def test_get_execution_plan_simple(self):
        """Test execution plan for simple DAG."""
        self.validator.add_job("job1", [], "Created")
        self.validator.add_job("job2", ["job1"], "Created")

        plan = self.validator.get_execution_plan()

        assert len(plan) == 2
        assert plan[0] == ["job1"]
        assert plan[1] == ["job2"]

    def test_get_execution_plan_parallel(self):
        """Test execution plan with parallelizable jobs."""
        self.validator.add_job("job1", [], "Created")
        self.validator.add_job("job2", ["job1"], "Created")
        self.validator.add_job("job3", ["job1"], "Created")
        self.validator.add_job("job4", ["job2", "job3"], "Created")

        plan = self.validator.get_execution_plan()

        assert len(plan) == 3
        assert plan[0] == ["job1"]
        assert set(plan[1]) == {"job2", "job3"}
        assert plan[2] == ["job4"]

    def test_get_execution_plan_with_cycle(self):
        """Test execution plan fails with cycle."""
        self.validator.add_job("job1", ["job2"], "Created")
        self.validator.add_job("job2", ["job1"], "Created")

        with pytest.raises(CyclicDependencyError):
            self.validator.get_execution_plan()

    def test_get_critical_path_linear(self):
        """Test critical path on linear chain."""
        self.validator.add_job("job1", [], "Created")
        self.validator.add_job("job2", ["job1"], "Created")
        self.validator.add_job("job3", ["job2"], "Created")

        critical_path = self.validator.get_critical_path()

        assert critical_path == ["job1", "job2", "job3"]

    def test_get_critical_path_branching(self):
        """Test critical path with branches of different lengths."""
        self.validator.add_job("job1", [], "Created")
        # Short branch
        self.validator.add_job("job2", ["job1"], "Created")
        # Long branch
        self.validator.add_job("job3", ["job1"], "Created")
        self.validator.add_job("job4", ["job3"], "Created")
        self.validator.add_job("job5", ["job4"], "Created")

        critical_path = self.validator.get_critical_path()

        # Critical path should be the longest: job1 -> job3 -> job4 -> job5
        assert len(critical_path) == 4
        assert critical_path == ["job1", "job3", "job4", "job5"]

    def test_get_stats_empty(self):
        """Test getting stats for empty graph."""
        stats = self.validator.get_stats()

        assert stats["total_jobs"] == 0
        assert stats["ready_jobs"] == 0
        assert stats["blocked_jobs"] == 0

    def test_get_stats_complex_dag(self):
        """Test getting stats for complex DAG."""
        self.validator.add_job("job1", [], "Completed")
        self.validator.add_job("job2", ["job1"], "Queued")
        self.validator.add_job("job3", ["job1"], "Running")
        self.validator.add_job("job4", ["job2", "job3"], "Queued")

        stats = self.validator.get_stats()

        assert stats["total_jobs"] == 4
        assert stats["completed_jobs"] == 1
        assert stats["ready_jobs"] == 1  # job2 is ready
        assert stats["blocked_jobs"] == 1  # job4 is blocked
        assert stats["has_cycles"] is False

    def test_get_stats_with_cycle(self):
        """Test getting stats detects cycle."""
        self.validator.add_job("job1", ["job2"], "Created")
        self.validator.add_job("job2", ["job1"], "Created")

        stats = self.validator.get_stats()

        assert stats["has_cycles"] is True

    def test_complex_dag_scenario(self):
        """Test complex real-world DAG scenario."""
        # Build a complex DAG:
        #     job1
        #    /    \
        # job2    job3
        #   |      |  \
        # job4    job5 job6
        #    \      |  /
        #      \   job7
        #        \ /
        #       job8

        self.validator.add_job("job1", [], "Completed")
        self.validator.add_job("job2", ["job1"], "Completed")
        self.validator.add_job("job3", ["job1"], "Running")
        self.validator.add_job("job4", ["job2"], "Queued")
        self.validator.add_job("job5", ["job3"], "Queued")
        self.validator.add_job("job6", ["job3"], "Queued")
        self.validator.add_job("job7", ["job5", "job6"], "Queued")
        self.validator.add_job("job8", ["job4", "job7"], "Queued")

        # Validate structure
        assert self.validator.validate("job9", ["job8"])[0] is True

        # Check ready jobs (only job4 is ready, as job2 is completed)
        ready = self.validator.get_ready_jobs()
        assert "job4" in ready

        # Check blocked jobs
        blocked = self.validator.get_blocked_jobs()
        assert "job5" in blocked
        assert "job6" in blocked
        assert "job7" in blocked
        assert "job8" in blocked

        # Get critical path
        critical_path = self.validator.get_critical_path()
        assert len(critical_path) >= 4  # At least 4 levels deep

        # Get stats
        stats = self.validator.get_stats()
        assert stats["total_jobs"] == 8
        assert stats["has_cycles"] is False
        assert stats["max_depth"] > 0
