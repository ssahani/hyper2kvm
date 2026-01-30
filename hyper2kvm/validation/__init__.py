# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/validation/__init__.py
"""
Migration validation framework.

Provides comprehensive pre- and post-migration validation to ensure successful VM migrations.
"""

from .health_checker import (
    HealthCheckType,
    HealthCheckResult,
    HealthCheckStatus,
    HealthChecker,
)
from .service_validator import (
    ServiceValidator,
    ServiceCheckResult,
)
from .network_validator import (
    NetworkValidator,
    NetworkCheckResult,
)
from .database_validator import (
    DatabaseValidator,
    DatabaseCheckResult,
)
from .performance_validator import (
    PerformanceValidator,
    PerformanceMetric,
    PerformanceBenchmark,
)
from .orchestrator import (
    ValidationOrchestrator,
    ValidationReport,
)
from .vmdk_inspector import (
    VMDKInspector,
    VMDKInspectionResult,
    RiskLevel,
    BootMode,
    Risk,
)
from .validation_framework import (
    ValidationSeverity,
    ValidationResult,
    BaseValidator,
    DiskValidator,
    XMLValidator,
    ValidationRunner,
)

__all__ = [
    "HealthCheckType",
    "HealthCheckResult",
    "HealthCheckStatus",
    "HealthChecker",
    "ServiceValidator",
    "ServiceCheckResult",
    "NetworkValidator",
    "NetworkCheckResult",
    "DatabaseValidator",
    "DatabaseCheckResult",
    "PerformanceValidator",
    "PerformanceMetric",
    "PerformanceBenchmark",
    "ValidationOrchestrator",
    "ValidationReport",
    "VMDKInspector",
    "VMDKInspectionResult",
    "RiskLevel",
    "BootMode",
    "Risk",
    "ValidationSeverity",
    "ValidationResult",
    "BaseValidator",
    "DiskValidator",
    "XMLValidator",
    "ValidationRunner",
]
