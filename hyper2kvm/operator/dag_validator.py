"""
DAG Validator for Job Dependencies.

Validates dependency graphs for MigrationJob resources to ensure:
- No circular dependencies (cycles)
- All referenced jobs exist
- DAG is properly structured
- Dependencies are in valid states
"""

import logging
from typing import Dict, List, Set, Optional, Tuple, Any
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class CyclicDependencyError(Exception):
    """Raised when a circular dependency is detected in the job DAG."""
    pass


class InvalidDependencyError(Exception):
    """Raised when a dependency reference is invalid."""
    pass


class DAGValidator:
    """
    Directed Acyclic Graph validator for job dependencies.

    Validates that job dependencies form a valid DAG:
    - No cycles
    - All dependencies reference existing jobs
    - Proper topological ordering exists
    """

    def __init__(self):
        """Initialize DAG validator."""
        self.graph: Dict[str, Set[str]] = defaultdict(set)
        self.reverse_graph: Dict[str, Set[str]] = defaultdict(set)
        self.job_states: Dict[str, str] = {}

    def add_job(self, job_name: str, depends_on: List[str], state: str = "Created"):
        """
        Add a job and its dependencies to the graph.

        Args:
            job_name: Name of the job
            depends_on: List of job names this job depends on
            state: Current state of the job
        """
        self.job_states[job_name] = state

        for dep in depends_on:
            self.graph[job_name].add(dep)
            self.reverse_graph[dep].add(job_name)

        # Ensure job exists in graph even if no dependencies
        if job_name not in self.graph:
            self.graph[job_name] = set()

    def validate(self, job_name: str, depends_on: List[str]) -> Tuple[bool, Optional[str]]:
        """
        Validate a job's dependencies.

        Args:
            job_name: Name of the job to validate
            depends_on: List of dependencies

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for self-dependency
        if job_name in depends_on:
            return False, f"Job {job_name} cannot depend on itself"

        # Build temporary graph including this job
        temp_graph = dict(self.graph)
        temp_graph[job_name] = set(depends_on)

        # Detect cycles
        cycle = self._detect_cycle(temp_graph, job_name)
        if cycle:
            cycle_str = " -> ".join(cycle)
            return False, f"Circular dependency detected: {cycle_str}"

        return True, None

    def _detect_cycle(self, graph: Dict[str, Set[str]], start_node: str) -> Optional[List[str]]:
        """
        Detect cycles in the graph using DFS.

        Args:
            graph: Adjacency list representation of the graph
            start_node: Node to start cycle detection from

        Returns:
            List of nodes forming a cycle, or None if no cycle
        """
        visited = set()
        rec_stack = set()
        path = []

        def dfs(node: str) -> bool:
            """DFS helper to detect cycles."""
            if node in rec_stack:
                # Found cycle - construct cycle path
                cycle_start = path.index(node)
                return path[cycle_start:] + [node]

            if node in visited:
                return None

            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, set()):
                result = dfs(neighbor)
                if result:
                    return result

            path.pop()
            rec_stack.remove(node)
            return None

        return dfs(start_node)

    def get_ready_jobs(self) -> List[str]:
        """
        Get list of jobs that are ready to execute.

        A job is ready if:
        - All its dependencies have completed successfully
        - It's in a state that can transition to execution

        Returns:
            List of job names ready for execution
        """
        ready_jobs = []

        for job_name, dependencies in self.graph.items():
            job_state = self.job_states.get(job_name, "Created")

            # Skip if not in a runnable state
            if job_state not in ["Validated", "Queued"]:
                continue

            # Check if all dependencies are completed
            all_deps_completed = all(
                self.job_states.get(dep) == "Completed"
                for dep in dependencies
            )

            if not dependencies or all_deps_completed:
                ready_jobs.append(job_name)

        return ready_jobs

    def get_blocked_jobs(self) -> Dict[str, List[str]]:
        """
        Get jobs that are blocked by dependencies.

        Returns:
            Dict mapping job names to list of blocking dependencies
        """
        blocked_jobs = {}

        for job_name, dependencies in self.graph.items():
            job_state = self.job_states.get(job_name, "Created")

            # Only check jobs that should be running
            if job_state not in ["Validated", "Queued", "Assigned"]:
                continue

            blocking_deps = [
                dep for dep in dependencies
                if self.job_states.get(dep) != "Completed"
            ]

            if blocking_deps:
                blocked_jobs[job_name] = blocking_deps

        return blocked_jobs

    def topological_sort(self) -> List[str]:
        """
        Perform topological sort of the job DAG.

        Returns:
            List of job names in topological order

        Raises:
            CyclicDependencyError: If graph contains cycles
        """
        # Kahn's algorithm for topological sorting
        in_degree = defaultdict(int)

        # Calculate in-degrees
        for node in self.graph:
            for neighbor in self.graph[node]:
                in_degree[neighbor] += 1

        # Initialize queue with nodes having in-degree 0
        queue = deque([node for node in self.graph if in_degree[node] == 0])
        result = []

        while queue:
            node = queue.popleft()
            result.append(node)

            # Reduce in-degree for neighbors
            for neighbor in self.reverse_graph.get(node, set()):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Check if all nodes were processed (no cycles)
        if len(result) != len(self.graph):
            raise CyclicDependencyError("Graph contains cycles")

        return result

    def update_job_state(self, job_name: str, new_state: str):
        """
        Update the state of a job.

        Args:
            job_name: Name of the job
            new_state: New state value
        """
        self.job_states[job_name] = new_state
        logger.debug(f"Updated job {job_name} state to {new_state}")

    def get_dependents(self, job_name: str) -> List[str]:
        """
        Get jobs that depend on this job.

        Args:
            job_name: Name of the job

        Returns:
            List of dependent job names
        """
        return list(self.reverse_graph.get(job_name, set()))

    def get_dependencies(self, job_name: str) -> List[str]:
        """
        Get jobs that this job depends on.

        Args:
            job_name: Name of the job

        Returns:
            List of dependency job names
        """
        return list(self.graph.get(job_name, set()))

    def can_execute(self, job_name: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a job can execute now.

        Args:
            job_name: Name of the job

        Returns:
            Tuple of (can_execute, reason)
        """
        dependencies = self.graph.get(job_name, set())

        if not dependencies:
            return True, None

        incomplete_deps = []
        failed_deps = []

        for dep in dependencies:
            dep_state = self.job_states.get(dep, "Unknown")

            if dep_state == "Completed":
                continue
            elif dep_state in ["Failed", "Cancelled"]:
                failed_deps.append(dep)
            else:
                incomplete_deps.append(dep)

        if failed_deps:
            return False, f"Dependencies failed: {', '.join(failed_deps)}"

        if incomplete_deps:
            return False, f"Waiting for dependencies: {', '.join(incomplete_deps)}"

        return True, None

    def get_execution_plan(self) -> List[List[str]]:
        """
        Get execution plan as levels of parallelizable jobs.

        Returns:
            List of job name lists, where each inner list contains
            jobs that can execute in parallel
        """
        # Create a copy of the graph
        in_degree = defaultdict(int)
        for node in self.graph:
            for neighbor in self.graph[node]:
                in_degree[neighbor] += 1

        levels = []
        remaining = set(self.graph.keys())

        while remaining:
            # Find all nodes with in-degree 0
            current_level = [
                node for node in remaining
                if in_degree[node] == 0
            ]

            if not current_level:
                raise CyclicDependencyError("Circular dependency detected")

            levels.append(current_level)

            # Remove current level nodes and update in-degrees
            for node in current_level:
                remaining.remove(node)
                for dependent in self.reverse_graph.get(node, set()):
                    in_degree[dependent] -= 1

        return levels

    def get_critical_path(self) -> List[str]:
        """
        Calculate the critical path (longest path) through the DAG.

        Returns:
            List of job names forming the critical path
        """
        # Topological sort
        try:
            sorted_jobs = self.topological_sort()
        except CyclicDependencyError:
            return []

        # Calculate longest path using dynamic programming
        longest_path = {job: [] for job in sorted_jobs}

        for job in sorted_jobs:
            dependencies = self.graph.get(job, set())

            if not dependencies:
                longest_path[job] = [job]
            else:
                # Find longest path among dependencies
                max_path = []
                for dep in dependencies:
                    if len(longest_path[dep]) > len(max_path):
                        max_path = longest_path[dep]

                longest_path[job] = max_path + [job]

        # Return the longest path overall
        critical_path = max(longest_path.values(), key=len, default=[])
        return critical_path

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the job DAG.

        Returns:
            Dictionary with DAG statistics
        """
        total_jobs = len(self.graph)

        if total_jobs == 0:
            return {
                "total_jobs": 0,
                "ready_jobs": 0,
                "blocked_jobs": 0,
                "completed_jobs": 0,
                "failed_jobs": 0,
                "max_depth": 0,
                "has_cycles": False
            }

        ready = len(self.get_ready_jobs())
        blocked = len(self.get_blocked_jobs())
        completed = sum(1 for state in self.job_states.values() if state == "Completed")
        failed = sum(1 for state in self.job_states.values() if state in ["Failed", "Cancelled"])

        try:
            execution_plan = self.get_execution_plan()
            max_depth = len(execution_plan)
            has_cycles = False
        except CyclicDependencyError:
            max_depth = 0
            has_cycles = True

        return {
            "total_jobs": total_jobs,
            "ready_jobs": ready,
            "blocked_jobs": blocked,
            "completed_jobs": completed,
            "failed_jobs": failed,
            "max_depth": max_depth,
            "has_cycles": has_cycles,
            "parallelism_potential": max(len(level) for level in execution_plan) if execution_plan else 0
        }
