#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
# test_vmcraft_v9.py
"""
Test VMCraft v9.0 API completeness.

This test verifies that all v9.0 methods are available in the VMCraft class.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from hyper2kvm.core.vmcraft import VMCraft


def test_v9_ml_analyzer_methods():
    """Test ML Analyzer methods are available."""
    print("Testing ML Analyzer API...")

    methods = [
        'detect_anomalies',
        'predict_behavior',
        'classify_workload',
        'train_baseline',
        'detect_behavior_change',
        'recommend_optimizations',
        'get_intelligence_summary',
    ]

    g = VMCraft()
    missing = []

    for method in methods:
        if not hasattr(g, method):
            missing.append(method)
            print(f"  ✗ {method} - MISSING")
        else:
            print(f"  ✓ {method}")

    if missing:
        print(f"\n❌ FAILED: {len(missing)} methods missing")
        return False
    else:
        print(f"\n✅ PASSED: All {len(methods)} ML Analyzer methods available")
        return True


def test_v9_cloud_optimizer_methods():
    """Test Cloud Optimizer methods are available."""
    print("\nTesting Cloud Optimizer API...")

    methods = [
        'analyze_cloud_readiness',
        'recommend_instance_type',
        'calculate_cloud_costs',
        'compare_cloud_providers',
        'generate_migration_plan',
        'optimize_for_cloud',
    ]

    g = VMCraft()
    missing = []

    for method in methods:
        if not hasattr(g, method):
            missing.append(method)
            print(f"  ✗ {method} - MISSING")
        else:
            print(f"  ✓ {method}")

    if missing:
        print(f"\n❌ FAILED: {len(missing)} methods missing")
        return False
    else:
        print(f"\n✅ PASSED: All {len(methods)} Cloud Optimizer methods available")
        return True


def test_v9_disaster_recovery_methods():
    """Test Disaster Recovery methods are available."""
    print("\nTesting Disaster Recovery API...")

    methods = [
        'assess_recovery_requirements',
        'create_backup_strategy',
        'calculate_rto_rpo',
        'create_failover_procedure',
        'test_dr_plan',
        'generate_dr_report',
    ]

    g = VMCraft()
    missing = []

    for method in methods:
        if not hasattr(g, method):
            missing.append(method)
            print(f"  ✗ {method} - MISSING")
        else:
            print(f"  ✓ {method}")

    if missing:
        print(f"\n❌ FAILED: {len(missing)} methods missing")
        return False
    else:
        print(f"\n✅ PASSED: All {len(methods)} Disaster Recovery methods available")
        return True


def test_v9_audit_trail_methods():
    """Test Audit Trail methods are available."""
    print("\nTesting Audit Trail API...")

    methods = [
        'log_event',
        'query_events',
        'generate_compliance_report',
        'track_changes',
        'export_audit_log',
        'verify_integrity',
        'get_audit_summary',
    ]

    g = VMCraft()
    missing = []

    for method in methods:
        if not hasattr(g, method):
            missing.append(method)
            print(f"  ✗ {method} - MISSING")
        else:
            print(f"  ✓ {method}")

    if missing:
        print(f"\n❌ FAILED: {len(missing)} methods missing")
        return False
    else:
        print(f"\n✅ PASSED: All {len(methods)} Audit Trail methods available")
        return True


def test_v9_resource_orchestrator_methods():
    """Test Resource Orchestrator methods are available."""
    print("\nTesting Resource Orchestrator API...")

    methods = [
        'analyze_resource_usage',
        'create_scaling_policy',
        'execute_scaling_action',
        'balance_workload',
        'optimize_resource_allocation',
        'schedule_maintenance',
        'get_orchestration_metrics',
    ]

    g = VMCraft()
    missing = []

    for method in methods:
        if not hasattr(g, method):
            missing.append(method)
            print(f"  ✗ {method} - MISSING")
        else:
            print(f"  ✓ {method}")

    if missing:
        print(f"\n❌ FAILED: {len(missing)} methods missing")
        return False
    else:
        print(f"\n✅ PASSED: All {len(methods)} Resource Orchestrator methods available")
        return True


def test_total_method_count():
    """Test total public method count."""
    print("\nCounting total public methods...")

    g = VMCraft()
    public_methods = [m for m in dir(g) if not m.startswith('_') and callable(getattr(g, m))]

    # Expected: 274 (v8.0) + 33 (v9.0) = 307 methods
    expected_min = 305

    print(f"  Total public methods: {len(public_methods)}")
    print(f"  Expected minimum: {expected_min}")

    if len(public_methods) >= expected_min:
        print(f"\n✅ PASSED: Method count meets expectations")
        return True
    else:
        print(f"\n❌ FAILED: Expected at least {expected_min} methods, got {len(public_methods)}")
        return False


def main():
    """Run all tests."""
    print("=" * 80)
    print("VMCraft v9.0 API Completeness Test")
    print("=" * 80)

    results = []

    # Test each module
    results.append(("ML Analyzer", test_v9_ml_analyzer_methods()))
    results.append(("Cloud Optimizer", test_v9_cloud_optimizer_methods()))
    results.append(("Disaster Recovery", test_v9_disaster_recovery_methods()))
    results.append(("Audit Trail", test_v9_audit_trail_methods()))
    results.append(("Resource Orchestrator", test_v9_resource_orchestrator_methods()))
    results.append(("Total Method Count", test_total_method_count()))

    # Summary
    print("\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {name}")

    print("\n" + "=" * 80)
    if passed == total:
        print(f"🎉 ALL TESTS PASSED ({passed}/{total})")
        print("=" * 80)
        sys.exit(0)
    else:
        print(f"❌ SOME TESTS FAILED ({passed}/{total} passed)")
        print("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
