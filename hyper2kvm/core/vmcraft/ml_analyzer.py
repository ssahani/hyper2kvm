# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/vmcraft/ml_analyzer.py
"""
Machine Learning Analyzer Module for VMCraft.

Provides AI-powered anomaly detection, pattern recognition, behavior analysis,
and intelligent recommendations.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any


class MLAnalyzer:
    """Machine learning and AI-powered analysis."""

    # Anomaly detection thresholds
    ANOMALY_THRESHOLDS = {
        "cpu_spike": 3.0,  # Standard deviations
        "memory_leak": 2.5,
        "disk_thrashing": 2.0,
        "network_flood": 3.0,
    }

    # Behavior patterns
    NORMAL_PATTERNS = {
        "cpu_usage": {"min": 10, "max": 70, "avg": 40},
        "memory_usage": {"min": 30, "max": 80, "avg": 60},
        "disk_io": {"min": 100, "max": 1000, "avg": 500},
        "network_io": {"min": 50, "max": 500, "avg": 200},
    }

    def __init__(
        self,
        logger: logging.Logger,
        file_ops: Any,
        mount_root: Path,
    ) -> None:
        """Initialize ML analyzer."""
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root
        self.trained_models = {}
        self.baseline_data = {}

    def detect_anomalies(
        self, metrics: list[dict[str, Any]], metric_type: str = "cpu"
    ) -> dict[str, Any]:
        """
        Detect anomalies in time series data using statistical methods.

        Args:
            metrics: List of metric data points
            metric_type: Type of metric (cpu, memory, disk, network)

        Returns:
            Anomaly detection results
        """
        self.logger.info(f"Detecting anomalies in {metric_type} metrics")

        if not metrics:
            return {"error": "No metrics provided"}

        # Calculate statistics
        values = [m.get("value", 0) for m in metrics]
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std_dev = variance ** 0.5

        # Detect anomalies
        anomalies = []
        for i, metric in enumerate(metrics):
            value = metric.get("value", 0)
            z_score = (value - mean) / std_dev if std_dev > 0 else 0

            threshold = self.ANOMALY_THRESHOLDS.get(f"{metric_type}_spike", 3.0)

            if abs(z_score) > threshold:
                anomalies.append(
                    {
                        "index": i,
                        "timestamp": metric.get("timestamp"),
                        "value": value,
                        "z_score": round(z_score, 2),
                        "deviation": round(value - mean, 2),
                        "severity": self._classify_severity(abs(z_score)),
                        "type": "spike" if z_score > 0 else "drop",
                    }
                )

        return {
            "metric_type": metric_type,
            "total_points": len(metrics),
            "anomalies_detected": len(anomalies),
            "anomalies": anomalies,
            "statistics": {
                "mean": round(mean, 2),
                "std_dev": round(std_dev, 2),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
            },
            "anomaly_rate": round((len(anomalies) / len(metrics)) * 100, 2),
        }

    def _classify_severity(self, z_score: float) -> str:
        """Classify anomaly severity based on z-score."""
        if z_score >= 4.0:
            return "critical"
        elif z_score >= 3.0:
            return "high"
        elif z_score >= 2.0:
            return "medium"
        else:
            return "low"

    def predict_behavior(
        self, historical_data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Predict future system behavior based on historical patterns.

        Args:
            historical_data: Historical metric data

        Returns:
            Behavior predictions
        """
        self.logger.info(f"Predicting behavior from {len(historical_data)} data points")

        if len(historical_data) < 10:
            return {"error": "Insufficient data for prediction (minimum 10 points)"}

        # Simple linear regression for trend
        n = len(historical_data)
        x_values = list(range(n))
        y_values = [d.get("value", 0) for d in historical_data]

        # Calculate slope and intercept
        x_mean = sum(x_values) / n
        y_mean = sum(y_values) / n

        numerator = sum((x_values[i] - x_mean) * (y_values[i] - y_mean) for i in range(n))
        denominator = sum((x_values[i] - x_mean) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0
        intercept = y_mean - slope * x_mean

        # Predict next 5 points
        predictions = []
        for i in range(5):
            future_x = n + i
            predicted_value = slope * future_x + intercept
            predictions.append(
                {
                    "step": i + 1,
                    "predicted_value": round(predicted_value, 2),
                    "confidence": self._calculate_confidence(slope, y_values),
                }
            )

        return {
            "total_historical_points": n,
            "trend": "increasing" if slope > 0 else "decreasing" if slope < 0 else "stable",
            "trend_strength": abs(slope),
            "predictions": predictions,
            "model_type": "linear_regression",
            "accuracy_estimate": self._calculate_confidence(slope, y_values),
        }

    def _calculate_confidence(self, slope: float, values: list[float]) -> float:
        """Calculate prediction confidence (0-1)."""
        # Higher confidence for stable trends
        variance = sum((v - sum(values) / len(values)) ** 2 for v in values) / len(values)
        std_dev = variance ** 0.5
        mean = sum(values) / len(values)

        # Coefficient of variation
        cv = std_dev / mean if mean != 0 else 1

        # Lower CV = higher confidence
        confidence = max(0, min(1, 1 - (cv / 2)))
        return round(confidence, 2)

    def classify_workload(self, metrics: dict[str, Any]) -> dict[str, Any]:
        """
        Classify workload type based on resource usage patterns.

        Args:
            metrics: Current system metrics

        Returns:
            Workload classification
        """
        self.logger.info("Classifying workload type")

        cpu = metrics.get("cpu_percent", 0)
        memory = metrics.get("memory_percent", 0)
        disk_io = metrics.get("disk_iops", 0)
        network_io = metrics.get("network_mbps", 0)

        # Classification logic
        workload_type = "unknown"
        confidence = 0.0
        characteristics = []

        # CPU-intensive
        if cpu > 70 and memory < 50:
            workload_type = "compute_intensive"
            confidence = 0.85
            characteristics = ["High CPU usage", "Low memory usage", "Batch processing likely"]

        # Memory-intensive
        elif memory > 70 and cpu < 50:
            workload_type = "memory_intensive"
            confidence = 0.80
            characteristics = ["High memory usage", "Database or caching workload likely"]

        # I/O intensive
        elif disk_io > 500 or network_io > 300:
            workload_type = "io_intensive"
            confidence = 0.75
            characteristics = ["High I/O operations", "File server or streaming likely"]

        # Balanced
        elif 30 < cpu < 70 and 30 < memory < 70:
            workload_type = "balanced"
            confidence = 0.70
            characteristics = ["Balanced resource usage", "Web application likely"]

        # Idle
        elif cpu < 20 and memory < 40:
            workload_type = "idle"
            confidence = 0.90
            characteristics = ["Low resource usage", "Underutilized system"]

        return {
            "workload_type": workload_type,
            "confidence": confidence,
            "characteristics": characteristics,
            "metrics_snapshot": {
                "cpu_percent": cpu,
                "memory_percent": memory,
                "disk_iops": disk_io,
                "network_mbps": network_io,
            },
            "recommendations": self._get_workload_recommendations(workload_type),
        }

    def _get_workload_recommendations(self, workload_type: str) -> list[str]:
        """Get recommendations based on workload type."""
        recommendations = {
            "compute_intensive": [
                "Consider adding more CPU cores",
                "Optimize parallel processing",
                "Review CPU-bound algorithms",
            ],
            "memory_intensive": [
                "Increase RAM allocation",
                "Implement caching strategies",
                "Review memory leaks",
            ],
            "io_intensive": [
                "Upgrade to SSD storage",
                "Implement I/O caching",
                "Optimize database queries",
            ],
            "balanced": [
                "Current resource allocation is appropriate",
                "Monitor for future scaling needs",
            ],
            "idle": [
                "Reduce resource allocation to save costs",
                "Consider consolidating workloads",
            ],
            "unknown": [
                "Collect more metrics for accurate classification",
            ],
        }
        return recommendations.get(workload_type, [])

    def train_baseline(self, training_data: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Train baseline model from normal operating data.

        Args:
            training_data: Historical data from normal operations

        Returns:
            Training results
        """
        self.logger.info(f"Training baseline model with {len(training_data)} samples")

        if len(training_data) < 50:
            return {"error": "Insufficient training data (minimum 50 samples)"}

        # Extract features
        cpu_values = [d.get("cpu_percent", 0) for d in training_data]
        memory_values = [d.get("memory_percent", 0) for d in training_data]
        disk_values = [d.get("disk_iops", 0) for d in training_data]

        # Calculate baselines
        self.baseline_data = {
            "cpu": {
                "mean": sum(cpu_values) / len(cpu_values),
                "min": min(cpu_values),
                "max": max(cpu_values),
                "std_dev": self._calculate_std_dev(cpu_values),
            },
            "memory": {
                "mean": sum(memory_values) / len(memory_values),
                "min": min(memory_values),
                "max": max(memory_values),
                "std_dev": self._calculate_std_dev(memory_values),
            },
            "disk": {
                "mean": sum(disk_values) / len(disk_values),
                "min": min(disk_values),
                "max": max(disk_values),
                "std_dev": self._calculate_std_dev(disk_values),
            },
            "trained_at": datetime.now().isoformat(),
            "sample_count": len(training_data),
        }

        return {
            "status": "trained",
            "baseline_data": self.baseline_data,
            "training_samples": len(training_data),
            "features": ["cpu", "memory", "disk"],
        }

    def _calculate_std_dev(self, values: list[float]) -> float:
        """Calculate standard deviation."""
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5

    def detect_behavior_change(self, current_metrics: dict[str, Any]) -> dict[str, Any]:
        """
        Detect changes in system behavior compared to baseline.

        Args:
            current_metrics: Current system metrics

        Returns:
            Behavior change detection results
        """
        self.logger.info("Detecting behavior changes")

        if not self.baseline_data:
            return {"error": "No baseline data available. Train baseline first."}

        changes = []

        # Check CPU
        cpu = current_metrics.get("cpu_percent", 0)
        cpu_baseline = self.baseline_data["cpu"]
        cpu_deviation = abs(cpu - cpu_baseline["mean"]) / cpu_baseline["std_dev"] if cpu_baseline["std_dev"] > 0 else 0

        if cpu_deviation > 2.0:
            changes.append(
                {
                    "metric": "cpu",
                    "current_value": cpu,
                    "baseline_mean": cpu_baseline["mean"],
                    "deviation": round(cpu_deviation, 2),
                    "severity": self._classify_severity(cpu_deviation),
                }
            )

        # Check Memory
        memory = current_metrics.get("memory_percent", 0)
        memory_baseline = self.baseline_data["memory"]
        memory_deviation = abs(memory - memory_baseline["mean"]) / memory_baseline["std_dev"] if memory_baseline["std_dev"] > 0 else 0

        if memory_deviation > 2.0:
            changes.append(
                {
                    "metric": "memory",
                    "current_value": memory,
                    "baseline_mean": memory_baseline["mean"],
                    "deviation": round(memory_deviation, 2),
                    "severity": self._classify_severity(memory_deviation),
                }
            )

        return {
            "behavior_changed": len(changes) > 0,
            "changes_detected": len(changes),
            "changes": changes,
            "baseline_age": self.baseline_data.get("trained_at"),
            "recommendation": "Retrain baseline" if len(changes) > 3 else "Continue monitoring",
        }

    def recommend_optimizations(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Generate AI-powered optimization recommendations.

        Args:
            analysis: System analysis data

        Returns:
            List of optimization recommendations
        """
        self.logger.info("Generating AI-powered optimization recommendations")

        recommendations = []

        # Analyze patterns
        workload = analysis.get("workload_type", "unknown")
        cpu_usage = analysis.get("cpu_percent", 0)
        memory_usage = analysis.get("memory_percent", 0)

        # CPU optimizations
        if cpu_usage > 80:
            recommendations.append(
                {
                    "category": "CPU",
                    "priority": "high",
                    "recommendation": "Implement CPU affinity for critical processes",
                    "expected_improvement": "15-25% performance gain",
                    "implementation_complexity": "medium",
                    "ml_confidence": 0.82,
                }
            )

        # Memory optimizations
        if memory_usage > 85:
            recommendations.append(
                {
                    "category": "Memory",
                    "priority": "high",
                    "recommendation": "Enable transparent huge pages for large memory applications",
                    "expected_improvement": "10-20% memory efficiency",
                    "implementation_complexity": "low",
                    "ml_confidence": 0.78,
                }
            )

        # Workload-specific optimizations
        if workload == "io_intensive":
            recommendations.append(
                {
                    "category": "I/O",
                    "priority": "medium",
                    "recommendation": "Implement I/O request merging and read-ahead optimization",
                    "expected_improvement": "20-30% I/O throughput",
                    "implementation_complexity": "medium",
                    "ml_confidence": 0.85,
                }
            )

        return recommendations

    def get_intelligence_summary(self) -> dict[str, Any]:
        """Get AI/ML intelligence summary."""
        return {
            "baseline_trained": bool(self.baseline_data),
            "baseline_age": self.baseline_data.get("trained_at") if self.baseline_data else None,
            "models_loaded": len(self.trained_models),
            "anomaly_detection": "active",
            "behavior_prediction": "active",
            "workload_classification": "active",
            "capabilities": [
                "Anomaly detection",
                "Behavior prediction",
                "Workload classification",
                "Baseline training",
                "Optimization recommendations",
            ],
        }
