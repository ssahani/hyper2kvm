# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/vmcraft/resource_orchestrator.py
"""
Resource Orchestrator Module for VMCraft.

Provides automated resource management, scaling policies, workload balancing,
and resource optimization.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class ResourceOrchestrator:
    """Automated resource orchestration and management."""

    # Scaling policies
    SCALING_POLICIES = {
        "aggressive": {"scale_up_threshold": 60, "scale_down_threshold": 30, "cooldown_minutes": 5},
        "moderate": {"scale_up_threshold": 75, "scale_down_threshold": 40, "cooldown_minutes": 10},
        "conservative": {"scale_up_threshold": 85, "scale_down_threshold": 50, "cooldown_minutes": 15},
    }

    def __init__(
        self,
        logger: logging.Logger,
        file_ops: Any,
        mount_root: Path,
    ) -> None:
        """Initialize resource orchestrator."""
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root
        self.scaling_history = []
        self.resource_pools = {}

    def analyze_resource_usage(
        self, current_metrics: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Analyze current resource usage patterns.

        Args:
            current_metrics: Current system metrics

        Returns:
            Resource usage analysis
        """
        self.logger.info("Analyzing resource usage patterns")

        cpu_usage = current_metrics.get("cpu_percent", 0)
        memory_usage = current_metrics.get("memory_percent", 0)
        disk_usage = current_metrics.get("disk_percent", 0)
        network_usage = current_metrics.get("network_percent", 0)

        # Identify bottlenecks
        bottlenecks = []
        if cpu_usage > 80:
            bottlenecks.append({"resource": "CPU", "usage": cpu_usage, "severity": "high"})
        if memory_usage > 85:
            bottlenecks.append({"resource": "Memory", "usage": memory_usage, "severity": "high"})
        if disk_usage > 90:
            bottlenecks.append({"resource": "Disk", "usage": disk_usage, "severity": "critical"})

        # Calculate efficiency
        total_usage = (cpu_usage + memory_usage + disk_usage + network_usage) / 4
        efficiency_score = self._calculate_efficiency(
            cpu_usage, memory_usage, disk_usage
        )

        return {
            "current_usage": {
                "cpu_percent": cpu_usage,
                "memory_percent": memory_usage,
                "disk_percent": disk_usage,
                "network_percent": network_usage,
            },
            "average_usage": round(total_usage, 2),
            "efficiency_score": efficiency_score,
            "bottlenecks": bottlenecks,
            "utilization_level": self._classify_utilization(total_usage),
            "recommendations": self._get_usage_recommendations(
                cpu_usage, memory_usage, efficiency_score
            ),
        }

    def _calculate_efficiency(
        self, cpu: float, memory: float, disk: float
    ) -> float:
        """Calculate resource efficiency score (0-100)."""
        # Balanced usage is more efficient
        ideal_usage = 70  # Target 70% utilization
        deviations = [
            abs(cpu - ideal_usage),
            abs(memory - ideal_usage),
            abs(disk - ideal_usage),
        ]
        avg_deviation = sum(deviations) / len(deviations)

        # Convert to efficiency score
        efficiency = 100 - min(avg_deviation, 100)
        return round(efficiency, 2)

    def _classify_utilization(self, usage: float) -> str:
        """Classify utilization level."""
        if usage > 85:
            return "overutilized"
        elif usage > 70:
            return "optimal"
        elif usage > 40:
            return "underutilized"
        else:
            return "significantly_underutilized"

    def _get_usage_recommendations(
        self, cpu: float, memory: float, efficiency: float
    ) -> list[str]:
        """Get recommendations based on usage."""
        recommendations = []

        if cpu > 85 or memory > 85:
            recommendations.append("Consider scaling up resources")
        elif cpu < 30 and memory < 30:
            recommendations.append("Consider scaling down to reduce costs")

        if efficiency < 60:
            recommendations.append("Resource allocation is unbalanced - optimize")

        return recommendations

    def create_scaling_policy(
        self, policy_name: str, policy_type: str = "moderate"
    ) -> dict[str, Any]:
        """
        Create auto-scaling policy.

        Args:
            policy_name: Name for the policy
            policy_type: Policy type (aggressive, moderate, conservative)

        Returns:
            Scaling policy configuration
        """
        self.logger.info(f"Creating scaling policy: {policy_name}")

        if policy_type not in self.SCALING_POLICIES:
            return {"error": f"Invalid policy type: {policy_type}"}

        template = self.SCALING_POLICIES[policy_type]

        policy = {
            "policy_name": policy_name,
            "policy_type": policy_type,
            "scale_up_threshold": template["scale_up_threshold"],
            "scale_down_threshold": template["scale_down_threshold"],
            "cooldown_minutes": template["cooldown_minutes"],
            "min_instances": 1,
            "max_instances": 10,
            "scaling_step": 1,
            "enabled": True,
            "created_at": datetime.now().isoformat(),
        }

        return policy

    def execute_scaling_action(
        self, action: str, current_capacity: int, reason: str
    ) -> dict[str, Any]:
        """
        Execute scaling action.

        Args:
            action: Scaling action (scale_up, scale_down)
            current_capacity: Current instance count
            reason: Reason for scaling

        Returns:
            Scaling action result
        """
        self.logger.info(f"Executing scaling action: {action}")

        if action == "scale_up":
            new_capacity = current_capacity + 1
            action_type = "increase"
        elif action == "scale_down":
            new_capacity = max(1, current_capacity - 1)
            action_type = "decrease"
        else:
            return {"error": f"Invalid action: {action}"}

        scaling_event = {
            "event_id": f"SCALE-{len(self.scaling_history) + 1:06d}",
            "timestamp": datetime.now().isoformat(),
            "action": action_type,
            "old_capacity": current_capacity,
            "new_capacity": new_capacity,
            "reason": reason,
            "status": "completed",
        }

        self.scaling_history.append(scaling_event)

        return scaling_event

    def balance_workload(
        self, workloads: list[dict[str, Any]], available_resources: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Balance workloads across available resources.

        Args:
            workloads: List of workloads to balance
            available_resources: Available resource capacity

        Returns:
            Workload distribution plan
        """
        self.logger.info(f"Balancing {len(workloads)} workloads")

        total_cpu_required = sum(w.get("cpu_required", 1) for w in workloads)
        total_memory_required = sum(w.get("memory_gb_required", 1) for w in workloads)

        available_cpu = available_resources.get("cpu_cores", 4)
        available_memory_gb = available_resources.get("memory_gb", 8)

        # Check if balancing is possible
        if total_cpu_required > available_cpu or total_memory_required > available_memory_gb:
            return {
                "status": "insufficient_resources",
                "required": {
                    "cpu": total_cpu_required,
                    "memory_gb": total_memory_required,
                },
                "available": {
                    "cpu": available_cpu,
                    "memory_gb": available_memory_gb,
                },
                "recommendation": "Scale up resources or reduce workload",
            }

        # Simple workload distribution (bin packing)
        distribution = []
        for workload in workloads:
            distribution.append(
                {
                    "workload_id": workload.get("id", "unknown"),
                    "workload_name": workload.get("name", "unknown"),
                    "assigned_cpu": workload.get("cpu_required", 1),
                    "assigned_memory_gb": workload.get("memory_gb_required", 1),
                    "priority": workload.get("priority", "normal"),
                }
            )

        return {
            "status": "balanced",
            "total_workloads": len(workloads),
            "distribution": distribution,
            "resource_utilization": {
                "cpu_percent": round((total_cpu_required / available_cpu) * 100, 2),
                "memory_percent": round(
                    (total_memory_required / available_memory_gb) * 100, 2
                ),
            },
        }

    def optimize_resource_allocation(
        self, current_allocation: dict[str, Any], usage_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Optimize resource allocation based on usage patterns.

        Args:
            current_allocation: Current resource allocation
            usage_data: Historical usage data

        Returns:
            Optimization recommendations
        """
        self.logger.info("Optimizing resource allocation")

        current_cpu = current_allocation.get("cpu_cores", 2)
        current_memory_gb = current_allocation.get("memory_gb", 4)

        avg_cpu_usage = usage_data.get("avg_cpu_percent", 50)
        avg_memory_usage = usage_data.get("avg_memory_percent", 60)
        peak_cpu_usage = usage_data.get("peak_cpu_percent", 80)
        peak_memory_usage = usage_data.get("peak_memory_percent", 85)

        optimizations = []

        # CPU optimization
        if avg_cpu_usage < 30 and peak_cpu_usage < 60:
            recommended_cpu = max(1, current_cpu - 1)
            optimizations.append(
                {
                    "resource": "CPU",
                    "current": current_cpu,
                    "recommended": recommended_cpu,
                    "reason": "Low average and peak CPU usage",
                    "potential_savings": f"{((current_cpu - recommended_cpu) / current_cpu) * 100:.0f}%",
                }
            )
        elif avg_cpu_usage > 70 or peak_cpu_usage > 90:
            recommended_cpu = current_cpu + 1
            optimizations.append(
                {
                    "resource": "CPU",
                    "current": current_cpu,
                    "recommended": recommended_cpu,
                    "reason": "High CPU usage detected",
                    "potential_benefit": "Improved performance and headroom",
                }
            )

        # Memory optimization
        if avg_memory_usage < 40 and peak_memory_usage < 70:
            recommended_memory = max(1, current_memory_gb - 2)
            optimizations.append(
                {
                    "resource": "Memory",
                    "current": current_memory_gb,
                    "recommended": recommended_memory,
                    "reason": "Low memory usage",
                    "potential_savings": f"{((current_memory_gb - recommended_memory) / current_memory_gb) * 100:.0f}%",
                }
            )
        elif avg_memory_usage > 75 or peak_memory_usage > 90:
            recommended_memory = current_memory_gb + 2
            optimizations.append(
                {
                    "resource": "Memory",
                    "current": current_memory_gb,
                    "recommended": recommended_memory,
                    "reason": "High memory usage detected",
                    "potential_benefit": "Prevent OOM and improve stability",
                }
            )

        if not optimizations:
            optimizations.append(
                {
                    "resource": "Overall",
                    "recommendation": "Current allocation is optimal",
                    "reason": "Resource usage is well-balanced",
                }
            )

        return {
            "current_allocation": current_allocation,
            "usage_analysis": usage_data,
            "optimizations": optimizations,
            "optimization_count": len([o for o in optimizations if "recommended" in o]),
        }

    def schedule_maintenance(
        self, maintenance_type: str, duration_minutes: int
    ) -> dict[str, Any]:
        """
        Schedule maintenance window.

        Args:
            maintenance_type: Type of maintenance
            duration_minutes: Expected duration

        Returns:
            Maintenance schedule
        """
        self.logger.info(f"Scheduling {maintenance_type} maintenance")

        # Find optimal maintenance window (low-traffic hours)
        current_time = datetime.now()
        if current_time.hour >= 2 and current_time.hour < 6:
            # Already in optimal window
            scheduled_time = current_time + timedelta(hours=1)
        else:
            # Schedule for next 2 AM
            next_2am = current_time.replace(hour=2, minute=0, second=0, microsecond=0)
            if current_time.hour >= 2:
                next_2am += timedelta(days=1)
            scheduled_time = next_2am

        return {
            "maintenance_id": f"MAINT-{int(scheduled_time.timestamp())}",
            "maintenance_type": maintenance_type,
            "scheduled_start": scheduled_time.isoformat(),
            "scheduled_end": (scheduled_time + timedelta(minutes=duration_minutes)).isoformat(),
            "duration_minutes": duration_minutes,
            "status": "scheduled",
            "impact": "Service may be temporarily unavailable",
            "notification_sent": False,
        }

    def get_orchestration_metrics(self) -> dict[str, Any]:
        """Get orchestration metrics and statistics."""
        return {
            "total_scaling_events": len(self.scaling_history),
            "recent_scaling_events": self.scaling_history[-10:] if self.scaling_history else [],
            "resource_pools": len(self.resource_pools),
            "orchestration_status": "active",
            "last_optimization": datetime.now().isoformat(),
            "capabilities": [
                "Auto-scaling",
                "Workload balancing",
                "Resource optimization",
                "Maintenance scheduling",
            ],
        }
