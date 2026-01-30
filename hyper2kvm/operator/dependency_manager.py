"""
Dependency Manager for MigrationJob resources.

Manages job dependencies, validates DAGs, and determines execution readiness.
"""

import logging
from typing import Dict, List, Optional, Any
from kubernetes import client

from hyper2kvm.operator.dag_validator import DAGValidator, CyclicDependencyError

logger = logging.getLogger(__name__)


class DependencyManager:
    """
    Manages dependencies between MigrationJob resources.

    Tracks job dependencies, validates DAG constraints, and determines
    which jobs are ready for execution.
    """

    def __init__(self):
        """Initialize dependency manager."""
        self.validator = DAGValidator()
        self.custom_api = client.CustomObjectsApi()

    async def register_job(
        self,
        namespace: str,
        job_name: str,
        depends_on: List[str],
        state: str = "Created"
    ) -> tuple[bool, Optional[str]]:
        """
        Register a job and its dependencies.

        Args:
            namespace: Kubernetes namespace
            job_name: Name of the job
            depends_on: List of job names this job depends on
            state: Current state of the job

        Returns:
            Tuple of (success, error_message)
        """
        # Validate dependency references
        for dep_name in depends_on:
            if not await self._job_exists(namespace, dep_name):
                return False, f"Dependency not found: {dep_name}"

        # Validate DAG constraints (no cycles)
        is_valid, error = self.validator.validate(job_name, depends_on)
        if not is_valid:
            return False, error

        # Add to validator graph
        self.validator.add_job(job_name, depends_on, state)

        logger.info(f"Registered job {job_name} with {len(depends_on)} dependencies")
        return True, None

    async def _job_exists(self, namespace: str, job_name: str) -> bool:
        """
        Check if a MigrationJob exists.

        Args:
            namespace: Kubernetes namespace
            job_name: Name of the job

        Returns:
            True if job exists, False otherwise
        """
        try:
            self.custom_api.get_namespaced_custom_object(
                group="hyper2kvm.io",
                version="v1alpha1",
                namespace=namespace,
                plural="migrationjobs",
                name=job_name
            )
            return True
        except client.rest.ApiException as e:
            if e.status == 404:
                return False
            raise

    def can_execute(self, job_name: str) -> tuple[bool, Optional[str]]:
        """
        Check if a job can execute based on dependencies.

        Args:
            job_name: Name of the job

        Returns:
            Tuple of (can_execute, reason)
        """
        return self.validator.can_execute(job_name)

    def update_job_state(self, job_name: str, new_state: str):
        """
        Update the state of a job.

        Args:
            job_name: Name of the job
            new_state: New state value
        """
        self.validator.update_job_state(job_name, new_state)

        # Check if any dependent jobs are now ready
        dependents = self.validator.get_dependents(job_name)
        if dependents and new_state == "Completed":
            logger.info(f"Job {job_name} completed, checking {len(dependents)} dependent jobs")

    def get_ready_jobs(self) -> List[str]:
        """
        Get list of jobs ready for execution.

        Returns:
            List of job names ready to execute
        """
        return self.validator.get_ready_jobs()

    def get_blocked_jobs(self) -> Dict[str, List[str]]:
        """
        Get jobs blocked by dependencies.

        Returns:
            Dict mapping job names to blocking dependencies
        """
        return self.validator.get_blocked_jobs()

    def get_dependency_status(self, job_name: str) -> Dict[str, Any]:
        """
        Get dependency status for a job.

        Args:
            job_name: Name of the job

        Returns:
            Dictionary with dependency status
        """
        dependencies = self.validator.get_dependencies(job_name)

        if not dependencies:
            return {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "blocking": []
            }

        completed = []
        failed = []
        blocking = []

        for dep in dependencies:
            dep_state = self.validator.job_states.get(dep, "Unknown")

            if dep_state == "Completed":
                completed.append(dep)
            elif dep_state in ["Failed", "Cancelled"]:
                failed.append(dep)
            else:
                blocking.append(dep)

        return {
            "total": len(dependencies),
            "completed": len(completed),
            "failed": len(failed),
            "blocking": blocking
        }

    def get_execution_plan(self) -> List[List[str]]:
        """
        Get execution plan showing parallelizable job levels.

        Returns:
            List of job name lists (each list can execute in parallel)

        Raises:
            CyclicDependencyError: If graph contains cycles
        """
        return self.validator.get_execution_plan()

    def get_critical_path(self) -> List[str]:
        """
        Get the critical path through the job DAG.

        Returns:
            List of job names on the critical path
        """
        return self.validator.get_critical_path()

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the job DAG.

        Returns:
            Dictionary with DAG statistics
        """
        return self.validator.get_stats()

    async def propagate_failure(
        self,
        namespace: str,
        failed_job: str
    ) -> List[str]:
        """
        Propagate failure to dependent jobs.

        When a job fails, optionally fail all jobs that depend on it.

        Args:
            namespace: Kubernetes namespace
            failed_job: Name of the failed job

        Returns:
            List of jobs that were also failed due to propagation
        """
        dependents = self.validator.get_dependents(failed_job)
        failed_jobs = []

        for dep_job in dependents:
            dep_state = self.validator.job_states.get(dep_job, "Unknown")

            # Only fail jobs that haven't started yet
            if dep_state in ["Created", "Validated", "Queued"]:
                logger.warning(
                    f"Failing {dep_job} due to dependency failure: {failed_job}"
                )

                # Update state in validator
                self.validator.update_job_state(dep_job, "Failed")
                failed_jobs.append(dep_job)

                # Recursively propagate
                transitive_failures = await self.propagate_failure(namespace, dep_job)
                failed_jobs.extend(transitive_failures)

        return failed_jobs

    def remove_job(self, job_name: str):
        """
        Remove a job from the dependency graph.

        Args:
            job_name: Name of the job to remove
        """
        if job_name in self.validator.graph:
            del self.validator.graph[job_name]

        if job_name in self.validator.reverse_graph:
            del self.validator.reverse_graph[job_name]

        if job_name in self.validator.job_states:
            del self.validator.job_states[job_name]

        # Remove from other jobs' dependency lists
        for deps in self.validator.graph.values():
            deps.discard(job_name)

        logger.debug(f"Removed job {job_name} from dependency graph")

    async def load_all_jobs(self, namespace: str):
        """
        Load all MigrationJobs from Kubernetes and rebuild dependency graph.

        Args:
            namespace: Kubernetes namespace
        """
        try:
            jobs = self.custom_api.list_namespaced_custom_object(
                group="hyper2kvm.io",
                version="v1alpha1",
                namespace=namespace,
                plural="migrationjobs"
            )

            # Reset validator
            self.validator = DAGValidator()

            # Add all jobs
            for job in jobs.get('items', []):
                job_name = job['metadata']['name']
                spec = job.get('spec', {})
                status = job.get('status', {})

                depends_on = spec.get('dependsOn', [])
                state = status.get('state', 'Created')

                # Add to graph (skip validation on load)
                self.validator.add_job(job_name, depends_on, state)

            logger.info(
                f"Loaded {len(jobs.get('items', []))} jobs into dependency graph"
            )

        except client.rest.ApiException as e:
            logger.error(f"Error loading jobs: {e}")
