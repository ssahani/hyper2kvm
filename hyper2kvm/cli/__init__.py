# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/cli/__init__.py
"""
Enhanced CLI framework.

Provides modern command-line interface with interactive wizards,
progress tracking, and rich output formatting.
"""

from .wizard import (
    MigrationWizard,
    WizardStep,
    WizardResult,
)
from .progress import (
    ProgressTracker,
    ProgressBar,
    Spinner,
)
from .formatter import (
    OutputFormatter,
    OutputStyle,
    Table,
)
from .config import (
    ConfigManager,
    MigrationConfig,
)

__all__ = [
    "MigrationWizard",
    "WizardStep",
    "WizardResult",
    "ProgressTracker",
    "ProgressBar",
    "Spinner",
    "OutputFormatter",
    "OutputStyle",
    "Table",
    "ConfigManager",
    "MigrationConfig",
]
