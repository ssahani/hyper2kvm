"""
Cost and SLA Tracker for Migration Jobs.

Tracks resource costs, SLA compliance, and performance metrics.
"""

import logging
from typing import Dict, Optional, Any, List
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class JobCost:
    """Cost breakdown for a migration job."""
    job_name: str
    compute_cost: float       # CPU/Memory cost
    storage_cost: float       # Storage I/O cost
    network_cost: float       # Network transfer cost
    total_cost: float         # Total cost
    duration_seconds: float   # Job duration
    cost_per_second: float    # Cost efficiency


@dataclass
class SLAConfig:
    """SLA configuration for jobs."""
    max_duration_minutes: int
    target_success_rate: float  # 0.0 - 1.0
    max_retries: int
    priority_threshold: int


class CostTracker:
    """
    Tracks job costs and SLA compliance.

    Handles:
    - Resource cost calculation
    - SLA definition and monitoring
    - Performance tracking
    - Cost optimization recommendations
    """

    def __init__(self):
        """Initialize cost tracker."""
        self.job_costs: Dict[str, JobCost] = {}
        self.sla_configs: Dict[str, SLAConfig] = {}

        # Cost rates (per second)
        self.cpu_cost_per_core_second = 0.00001  # $0.036/hour per core
        self.memory_cost_per_gb_second = 0.000001  # $0.0036/hour per GB
        self.storage_io_cost_per_gb = 0.0001  # $0.10/GB transferred
        self.network_cost_per_gb = 0.00005  # $0.05/GB transferred

    def calculate_job_cost(
        self,
        job_name: str,
        duration_seconds: float,
        cpu_cores: float = 2.0,
        memory_gb: float = 4.0,
        storage_io_gb: float = 0.0,
        network_transfer_gb: float = 0.0
    ) -> JobCost:
        """
        Calculate cost for a job.

        Args:
            job_name: Name of the job
            duration_seconds: Job execution time in seconds
            cpu_cores: CPU cores used
            memory_gb: Memory used in GB
            storage_io_gb: Storage I/O in GB
            network_transfer_gb: Network transfer in GB

        Returns:
            JobCost object
        """
        # Compute cost (CPU + Memory)
        cpu_cost = cpu_cores * duration_seconds * self.cpu_cost_per_core_second
        memory_cost = memory_gb * duration_seconds * self.memory_cost_per_gb_second
        compute_cost = cpu_cost + memory_cost

        # Storage I/O cost
        storage_cost = storage_io_gb * self.storage_io_cost_per_gb

        # Network transfer cost
        network_cost = network_transfer_gb * self.network_cost_per_gb

        # Total cost
        total_cost = compute_cost + storage_cost + network_cost

        # Cost efficiency
        cost_per_second = total_cost / duration_seconds if duration_seconds > 0 else 0

        cost = JobCost(
            job_name=job_name,
            compute_cost=round(compute_cost, 6),
            storage_cost=round(storage_cost, 6),
            network_cost=round(network_cost, 6),
            total_cost=round(total_cost, 6),
            duration_seconds=duration_seconds,
            cost_per_second=round(cost_per_second, 8)
        )

        self.job_costs[job_name] = cost
        return cost

    def get_job_cost(self, job_name: str) -> Optional[JobCost]:
        """Get cost for a specific job."""
        return self.job_costs.get(job_name)

    def get_total_costs(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, float]:
        """
        Get total costs across all jobs.

        Args:
            start_time: Optional start time filter
            end_time: Optional end time filter

        Returns:
            Dictionary with cost breakdown
        """
        total_compute = 0.0
        total_storage = 0.0
        total_network = 0.0

        for cost in self.job_costs.values():
            total_compute += cost.compute_cost
            total_storage += cost.storage_cost
            total_network += cost.network_cost

        return {
            'compute_cost': round(total_compute, 6),
            'storage_cost': round(total_storage, 6),
            'network_cost': round(total_network, 6),
            'total_cost': round(total_compute + total_storage + total_network, 6),
            'job_count': len(self.job_costs)
        }

    def define_sla(
        self,
        name: str,
        max_duration_minutes: int,
        target_success_rate: float,
        max_retries: int = 3,
        priority_threshold: int = 50
    ):
        """
        Define an SLA configuration.

        Args:
            name: SLA name/identifier
            max_duration_minutes: Maximum allowed duration
            target_success_rate: Target success rate (0.0 - 1.0)
            max_retries: Maximum retry attempts
            priority_threshold: Minimum priority for SLA
        """
        self.sla_configs[name] = SLAConfig(
            max_duration_minutes=max_duration_minutes,
            target_success_rate=target_success_rate,
            max_retries=max_retries,
            priority_threshold=priority_threshold
        )

        logger.info(f"Defined SLA '{name}': max_duration={max_duration_minutes}min, "
                   f"target_success_rate={target_success_rate}")

    def check_sla_compliance(
        self,
        sla_name: str,
        job_duration_minutes: float,
        job_success: bool,
        job_retries: int,
        job_priority: int
    ) -> Dict[str, Any]:
        """
        Check if a job meets SLA requirements.

        Args:
            sla_name: SLA to check against
            job_duration_minutes: Job duration in minutes
            job_success: Whether job succeeded
            job_retries: Number of retries
            job_priority: Job priority

        Returns:
            Dictionary with compliance status
        """
        sla = self.sla_configs.get(sla_name)
        if not sla:
            return {
                'compliant': False,
                'reason': f"SLA '{sla_name}' not found"
            }

        violations = []

        # Check duration
        if job_duration_minutes > sla.max_duration_minutes:
            violations.append(
                f"Duration exceeded: {job_duration_minutes:.2f}min > "
                f"{sla.max_duration_minutes}min"
            )

        # Check retries
        if job_retries > sla.max_retries:
            violations.append(
                f"Retry limit exceeded: {job_retries} > {sla.max_retries}"
            )

        # Check priority
        if job_priority < sla.priority_threshold:
            violations.append(
                f"Priority too low: {job_priority} < {sla.priority_threshold}"
            )

        # Success is binary
        if not job_success:
            violations.append("Job failed")

        return {
            'compliant': len(violations) == 0,
            'violations': violations,
            'sla_name': sla_name
        }

    def calculate_sla_metrics(
        self,
        job_results: List[Dict[str, Any]],
        sla_name: str
    ) -> Dict[str, Any]:
        """
        Calculate SLA metrics for a set of jobs.

        Args:
            job_results: List of job result dictionaries
            sla_name: SLA to evaluate against

        Returns:
            Dictionary with SLA metrics
        """
        sla = self.sla_configs.get(sla_name)
        if not sla:
            return {'error': f"SLA '{sla_name}' not found"}

        total_jobs = len(job_results)
        if total_jobs == 0:
            return {
                'total_jobs': 0,
                'success_rate': 0.0,
                'average_duration_minutes': 0.0,
                'sla_compliance_rate': 0.0
            }

        successful_jobs = sum(1 for j in job_results if j.get('success', False))
        compliant_jobs = 0
        total_duration = 0.0

        for job in job_results:
            duration_min = job.get('duration_minutes', 0)
            total_duration += duration_min

            compliance = self.check_sla_compliance(
                sla_name=sla_name,
                job_duration_minutes=duration_min,
                job_success=job.get('success', False),
                job_retries=job.get('retries', 0),
                job_priority=job.get('priority', 50)
            )

            if compliance['compliant']:
                compliant_jobs += 1

        success_rate = successful_jobs / total_jobs
        compliance_rate = compliant_jobs / total_jobs
        avg_duration = total_duration / total_jobs

        return {
            'total_jobs': total_jobs,
            'successful_jobs': successful_jobs,
            'success_rate': round(success_rate, 4),
            'compliant_jobs': compliant_jobs,
            'sla_compliance_rate': round(compliance_rate, 4),
            'average_duration_minutes': round(avg_duration, 2),
            'target_success_rate': sla.target_success_rate,
            'meets_target': success_rate >= sla.target_success_rate
        }

    def get_cost_optimization_recommendations(
        self,
        job_name: str,
        job_cost: JobCost
    ) -> List[str]:
        """
        Generate cost optimization recommendations.

        Args:
            job_name: Name of the job
            job_cost: Job cost breakdown

        Returns:
            List of recommendations
        """
        recommendations = []

        # High compute cost
        if job_cost.compute_cost > job_cost.total_cost * 0.7:
            recommendations.append(
                "High compute cost detected. Consider optimizing CPU/memory usage "
                "or using lower-spec workers for this job type."
            )

        # High storage I/O cost
        if job_cost.storage_cost > job_cost.total_cost * 0.3:
            recommendations.append(
                "High storage I/O cost. Consider using local SSD or optimizing "
                "disk access patterns."
            )

        # High network cost
        if job_cost.network_cost > job_cost.total_cost * 0.2:
            recommendations.append(
                "High network transfer cost. Consider co-locating workers "
                "with storage or using data compression."
            )

        # Low efficiency (high cost per second)
        if job_cost.cost_per_second > 0.001:
            recommendations.append(
                f"High cost per second ({job_cost.cost_per_second:.6f}). "
                "Review job efficiency and resource allocation."
            )

        if not recommendations:
            recommendations.append("Cost profile is optimal.")

        return recommendations

    def get_cost_stats(self) -> Dict[str, Any]:
        """
        Get overall cost statistics.

        Returns:
            Dictionary with cost statistics
        """
        if not self.job_costs:
            return {
                'total_jobs': 0,
                'total_cost': 0.0
            }

        costs = list(self.job_costs.values())
        total_cost = sum(c.total_cost for c in costs)
        avg_cost = total_cost / len(costs)

        # Find most/least expensive
        most_expensive = max(costs, key=lambda c: c.total_cost)
        least_expensive = min(costs, key=lambda c: c.total_cost)

        return {
            'total_jobs': len(costs),
            'total_cost': round(total_cost, 6),
            'average_cost_per_job': round(avg_cost, 6),
            'most_expensive_job': {
                'name': most_expensive.job_name,
                'cost': most_expensive.total_cost
            },
            'least_expensive_job': {
                'name': least_expensive.job_name,
                'cost': least_expensive.total_cost
            },
            'cost_breakdown': self.get_total_costs()
        }
