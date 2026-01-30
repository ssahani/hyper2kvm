"""Windows application compatibility detection and reporting.

This module provides tools for detecting applications and configurations that
may have compatibility issues after VM migration, including:

- Hardware-dependent applications (CAD, graphics, engineering software)
- License manager services (FlexLM, RLM, HASP)
- Hardware dongles and dongle drivers
- SQL Server instances and configuration
"""

from .detector import (
    detect_hardware_dependent_apps,
    detect_license_services,
    detect_dongle_drivers,
    AppCompatFinding,
    RiskLevel,
)
from .sqlserver import (
    detect_sql_server_instances,
    generate_sql_reconfiguration_script,
    SQLServerInstance,
)
from .reporter import (
    generate_compatibility_report,
    CompatibilityReport,
)

__all__ = [
    "detect_hardware_dependent_apps",
    "detect_license_services",
    "detect_dongle_drivers",
    "detect_sql_server_instances",
    "generate_sql_reconfiguration_script",
    "generate_compatibility_report",
    "AppCompatFinding",
    "RiskLevel",
    "SQLServerInstance",
    "CompatibilityReport",
]
