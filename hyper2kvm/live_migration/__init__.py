"""
Live migration support module.

This module provides live VM migration capabilities with minimal downtime using
HyperSDK for multi-provider support (VMware, Hyper-V, KVM, AWS, Azure, GCP).

Components:
- Live Migration Analyzer: Determines VM migration feasibility
- HyperSDK Integration: Interfaces with HyperSDK for provider abstraction
- Hybrid Migration Manager: Combines live migration with offline fixes
- Live Migration Orchestrator: Coordinates the entire live migration workflow
"""

from hyper2kvm.live_migration.analyzer import LiveMigrationAnalyzer
from hyper2kvm.live_migration.hypersdk_integration import HyperSDKIntegration
from hyper2kvm.live_migration.hybrid_manager import HybridMigrationManager
from hyper2kvm.live_migration.orchestrator import LiveMigrationOrchestrator

__all__ = [
    "LiveMigrationAnalyzer",
    "HyperSDKIntegration",
    "HybridMigrationManager",
    "LiveMigrationOrchestrator",
]
