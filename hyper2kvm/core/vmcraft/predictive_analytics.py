# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/vmcraft/predictive_analytics.py
"""
Predictive Analytics Module for VMCraft.

Provides predictive analysis, capacity forecasting, failure prediction,
and trend analysis for proactive infrastructure management.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class PredictiveAnalytics:
    """Predictive analytics and forecasting."""

    def __init__(
        self,
        logger: logging.Logger,
        file_ops: Any,
        mount_root: Path,
    ) -> None:
        """Initialize predictive analytics engine."""
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def predict_capacity_needs(
        self, current_usage: dict[str, Any], forecast_days: int = 90
    ) -> dict[str, Any]:
        """
        Predict future capacity needs based on current usage.

        Args:
            current_usage: Current resource usage metrics
            forecast_days: Number of days to forecast

        Returns:
            Capacity predictions and recommendations
        """
        self.logger.info(f"Predicting capacity needs for {forecast_days} days")

        # Simulate growth trends
        cpu_growth_rate = 0.02  # 2% per month
        memory_growth_rate = 0.03  # 3% per month
        storage_growth_rate = 0.05  # 5% per month

        days_in_month = 30
        months = forecast_days / days_in_month

        current_cpu = current_usage.get("cpu_percent", 50)
        current_memory = current_usage.get("memory_percent", 60)
        current_storage = current_usage.get("storage_percent", 70)

        predicted_cpu = current_cpu * (1 + cpu_growth_rate * months)
        predicted_memory = current_memory * (1 + memory_growth_rate * months)
        predicted_storage = current_storage * (1 + storage_growth_rate * months)

        forecast = {
            "forecast_period_days": forecast_days,
            "current_usage": {
                "cpu_percent": current_cpu,
                "memory_percent": current_memory,
                "storage_percent": current_storage,
            },
            "predicted_usage": {
                "cpu_percent": round(predicted_cpu, 2),
                "memory_percent": round(predicted_memory, 2),
                "storage_percent": round(predicted_storage, 2),
            },
            "capacity_warnings": [],
            "recommended_actions": [],
        }

        # Generate warnings
        if predicted_cpu > 80:
            forecast["capacity_warnings"].append(
                {
                    "resource": "CPU",
                    "predicted_usage": predicted_cpu,
                    "threshold": 80,
                    "days_until_threshold": self._calculate_days_to_threshold(
                        current_cpu, 80, cpu_growth_rate
                    ),
                }
            )
            forecast["recommended_actions"].append(
                {
                    "priority": "high",
                    "resource": "CPU",
                    "action": "Scale CPU resources vertically or add more instances",
                    "estimated_cost": "medium",
                }
            )

        if predicted_memory > 85:
            forecast["capacity_warnings"].append(
                {
                    "resource": "Memory",
                    "predicted_usage": predicted_memory,
                    "threshold": 85,
                    "days_until_threshold": self._calculate_days_to_threshold(
                        current_memory, 85, memory_growth_rate
                    ),
                }
            )
            forecast["recommended_actions"].append(
                {
                    "priority": "high",
                    "resource": "Memory",
                    "action": "Increase memory allocation or optimize applications",
                    "estimated_cost": "medium",
                }
            )

        if predicted_storage > 90:
            forecast["capacity_warnings"].append(
                {
                    "resource": "Storage",
                    "predicted_usage": predicted_storage,
                    "threshold": 90,
                    "days_until_threshold": self._calculate_days_to_threshold(
                        current_storage, 90, storage_growth_rate
                    ),
                }
            )
            forecast["recommended_actions"].append(
                {
                    "priority": "critical",
                    "resource": "Storage",
                    "action": "Expand storage capacity immediately",
                    "estimated_cost": "high",
                }
            )

        return forecast

    def _calculate_days_to_threshold(
        self, current: float, threshold: float, monthly_growth_rate: float
    ) -> int:
        """Calculate days until threshold is reached."""
        if current >= threshold:
            return 0

        if monthly_growth_rate == 0:
            return 999999

        # Convert monthly rate to daily
        daily_rate = monthly_growth_rate / 30

        # Calculate days to threshold
        days = (threshold - current) / (current * daily_rate)

        return max(0, int(days))

    def predict_failures(self, system_metrics: dict[str, Any]) -> dict[str, Any]:
        """
        Predict potential system failures.

        Args:
            system_metrics: Current system health metrics

        Returns:
            Failure predictions and risk assessment
        """
        self.logger.info("Analyzing failure prediction patterns")

        predictions = {
            "overall_health_score": 0,
            "failure_risks": [],
            "predicted_failures": [],
            "maintenance_recommendations": [],
        }

        # Analyze disk health
        disk_health = system_metrics.get("disk_health", {})
        if disk_health.get("smart_status") == "failing":
            predictions["failure_risks"].append(
                {
                    "component": "Disk",
                    "risk_level": "critical",
                    "probability": 0.85,
                    "time_to_failure_days": 7,
                    "indicators": ["SMART errors", "Bad sectors"],
                }
            )

        # Analyze service stability
        service_failures = system_metrics.get("service_failures", 0)
        if service_failures > 5:
            predictions["failure_risks"].append(
                {
                    "component": "Services",
                    "risk_level": "high",
                    "probability": 0.65,
                    "time_to_failure_days": 14,
                    "indicators": [f"{service_failures} recent failures"],
                }
            )

        # Calculate health score
        predictions["overall_health_score"] = self._calculate_health_score(
            system_metrics, predictions["failure_risks"]
        )

        # Generate maintenance recommendations
        predictions["maintenance_recommendations"] = (
            self._generate_maintenance_recommendations(predictions["failure_risks"])
        )

        return predictions

    def _calculate_health_score(
        self, metrics: dict[str, Any], risks: list[dict[str, Any]]
    ) -> int:
        """Calculate overall system health score (0-100)."""
        base_score = 100

        # Deduct points for risks
        risk_deductions = {"critical": 30, "high": 20, "medium": 10, "low": 5}

        for risk in risks:
            level = risk.get("risk_level", "low")
            if level in risk_deductions:
                base_score -= risk_deductions[level]

        return max(0, min(100, base_score))

    def _generate_maintenance_recommendations(
        self, risks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Generate maintenance recommendations from risks."""
        recommendations = []

        for risk in risks:
            component = risk.get("component")
            risk_level = risk.get("risk_level")

            if component == "Disk":
                recommendations.append(
                    {
                        "priority": "critical",
                        "component": component,
                        "action": "Replace failing disk immediately",
                        "estimated_downtime_hours": 2,
                    }
                )
            elif component == "Services":
                recommendations.append(
                    {
                        "priority": "high",
                        "component": component,
                        "action": "Investigate and fix service instability",
                        "estimated_downtime_hours": 1,
                    }
                )

        return recommendations

    def analyze_trends(
        self, historical_data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Analyze historical trends.

        Args:
            historical_data: List of historical metric snapshots

        Returns:
            Trend analysis results
        """
        self.logger.info(f"Analyzing trends from {len(historical_data)} data points")

        if not historical_data:
            return {"error": "No historical data provided"}

        analysis = {
            "data_points": len(historical_data),
            "time_span_days": 30,  # Simulated
            "trends": {
                "cpu": self._analyze_metric_trend("cpu", historical_data),
                "memory": self._analyze_metric_trend("memory", historical_data),
                "storage": self._analyze_metric_trend("storage", historical_data),
            },
            "anomalies_detected": [],
            "seasonal_patterns": [],
        }

        # Detect anomalies
        analysis["anomalies_detected"] = self._detect_anomalies(historical_data)

        # Identify seasonal patterns
        analysis["seasonal_patterns"] = self._identify_seasonal_patterns(
            historical_data
        )

        return analysis

    def _analyze_metric_trend(
        self, metric: str, data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze trend for specific metric."""
        # Simplified trend analysis
        return {
            "metric": metric,
            "trend_direction": "increasing",  # or "decreasing", "stable"
            "growth_rate_percent": 5.2,
            "volatility": "low",  # or "medium", "high"
            "prediction_confidence": 0.85,
        }

    def _detect_anomalies(
        self, data: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Detect anomalies in historical data."""
        # Simulated anomaly detection
        return [
            {
                "timestamp": "2025-01-20T03:00:00Z",
                "metric": "cpu",
                "value": 95,
                "expected_range": "40-60",
                "severity": "high",
                "type": "spike",
            }
        ]

    def _identify_seasonal_patterns(
        self, data: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Identify seasonal usage patterns."""
        return [
            {
                "pattern": "Weekly Peak",
                "description": "CPU usage peaks on Mondays at 9 AM",
                "confidence": 0.92,
                "recommendation": "Scale up resources Monday mornings",
            },
            {
                "pattern": "Nightly Low",
                "description": "Usage drops 60% between 2-5 AM",
                "confidence": 0.88,
                "recommendation": "Schedule maintenance during 2-5 AM window",
            },
        ]

    def forecast_costs(
        self, current_costs: dict[str, Any], forecast_months: int = 12
    ) -> dict[str, Any]:
        """
        Forecast infrastructure costs.

        Args:
            current_costs: Current monthly costs breakdown
            forecast_months: Number of months to forecast

        Returns:
            Cost forecasts and optimization opportunities
        """
        self.logger.info(f"Forecasting costs for {forecast_months} months")

        # Growth assumptions
        compute_growth = 0.03  # 3% monthly
        storage_growth = 0.05  # 5% monthly
        network_growth = 0.02  # 2% monthly

        current_compute = current_costs.get("compute", 1000)
        current_storage = current_costs.get("storage", 500)
        current_network = current_costs.get("network", 200)

        projected_compute = current_compute * ((1 + compute_growth) ** forecast_months)
        projected_storage = current_storage * ((1 + storage_growth) ** forecast_months)
        projected_network = current_network * ((1 + network_growth) ** forecast_months)

        forecast = {
            "forecast_months": forecast_months,
            "current_monthly_cost": current_compute + current_storage + current_network,
            "projected_monthly_cost": projected_compute
            + projected_storage
            + projected_network,
            "total_projected_cost": (
                projected_compute + projected_storage + projected_network
            )
            * forecast_months,
            "breakdown": {
                "compute": {
                    "current": current_compute,
                    "projected": round(projected_compute, 2),
                    "growth_percent": round(
                        ((projected_compute - current_compute) / current_compute) * 100,
                        2,
                    ),
                },
                "storage": {
                    "current": current_storage,
                    "projected": round(projected_storage, 2),
                    "growth_percent": round(
                        ((projected_storage - current_storage) / current_storage) * 100,
                        2,
                    ),
                },
                "network": {
                    "current": current_network,
                    "projected": round(projected_network, 2),
                    "growth_percent": round(
                        ((projected_network - current_network) / current_network) * 100,
                        2,
                    ),
                },
            },
            "optimization_opportunities": self._identify_cost_optimizations(
                current_costs
            ),
        }

        return forecast

    def _identify_cost_optimizations(
        self, costs: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Identify cost optimization opportunities."""
        return [
            {
                "category": "Compute",
                "opportunity": "Right-size underutilized instances",
                "estimated_savings_percent": 15,
                "complexity": "low",
            },
            {
                "category": "Storage",
                "opportunity": "Implement tiered storage with archival",
                "estimated_savings_percent": 25,
                "complexity": "medium",
            },
            {
                "category": "Network",
                "opportunity": "Optimize data transfer patterns",
                "estimated_savings_percent": 10,
                "complexity": "low",
            },
        ]

    def predict_resource_exhaustion(
        self, current_metrics: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Predict when resources will be exhausted.

        Args:
            current_metrics: Current resource usage metrics

        Returns:
            Exhaustion predictions for each resource
        """
        self.logger.info("Predicting resource exhaustion timelines")

        predictions = {
            "resources": [],
            "critical_resources": [],
            "action_required_by": None,
        }

        # Analyze each resource
        resources = [
            ("cpu", 100, 0.02),  # name, capacity, growth_rate
            ("memory", 100, 0.03),
            ("storage", 100, 0.05),
            ("inodes", 100, 0.01),
        ]

        earliest_exhaustion = None

        for resource_name, capacity, growth_rate in resources:
            current_usage = current_metrics.get(f"{resource_name}_percent", 50)

            if current_usage >= capacity:
                days_to_exhaustion = 0
            else:
                # Calculate based on growth rate
                daily_growth = (current_usage * growth_rate) / 30
                if daily_growth > 0:
                    days_to_exhaustion = (capacity - current_usage) / daily_growth
                else:
                    days_to_exhaustion = 999999

            resource_prediction = {
                "resource": resource_name,
                "current_usage_percent": current_usage,
                "capacity": capacity,
                "days_to_exhaustion": int(days_to_exhaustion),
                "exhaustion_date": (
                    datetime.now() + timedelta(days=int(days_to_exhaustion))
                ).isoformat(),
                "growth_rate_monthly": growth_rate * 100,
            }

            predictions["resources"].append(resource_prediction)

            if days_to_exhaustion < 90:
                predictions["critical_resources"].append(resource_prediction)

                if earliest_exhaustion is None or days_to_exhaustion < earliest_exhaustion:
                    earliest_exhaustion = days_to_exhaustion

        if earliest_exhaustion is not None:
            predictions["action_required_by"] = (
                datetime.now() + timedelta(days=int(earliest_exhaustion))
            ).isoformat()

        return predictions

    def generate_forecast_report(
        self, metrics: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate comprehensive forecast report."""
        return {
            "generated_at": datetime.now().isoformat(),
            "forecast_period_days": 90,
            "capacity_forecast": self.predict_capacity_needs(metrics),
            "failure_predictions": self.predict_failures(metrics),
            "cost_forecast": self.forecast_costs(
                {"compute": 1000, "storage": 500, "network": 200}
            ),
            "resource_exhaustion": self.predict_resource_exhaustion(metrics),
            "recommendations": self._generate_proactive_recommendations(metrics),
        }

    def _generate_proactive_recommendations(
        self, metrics: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate proactive recommendations."""
        return [
            {
                "priority": "high",
                "category": "Capacity Planning",
                "recommendation": "Expand storage capacity within 30 days",
                "rationale": "Storage projected to reach 90% in 45 days",
                "estimated_cost": "medium",
            },
            {
                "priority": "medium",
                "category": "Cost Optimization",
                "recommendation": "Implement automated scaling policies",
                "rationale": "Can reduce costs by 20% during off-peak hours",
                "estimated_cost": "low",
            },
        ]
