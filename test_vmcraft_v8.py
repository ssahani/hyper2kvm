#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
# test_vmcraft_v8.py
"""
Test VMCraft v8.0 API completeness.

This test verifies that all v8.0 methods are available in the VMCraft class.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from hyper2kvm.core.vmcraft import VMCraft


def test_v8_threat_intelligence_methods():
    """Test Threat Intelligence methods are available."""
    print("Testing Threat Intelligence API...")

    methods = [
        'analyze_threats',
        'get_threat_summary',
        'generate_threat_report',
        'check_threat_feeds',
        'analyze_file_reputation',
        'get_attack_surface',
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
        print(f"\n✅ PASSED: All {len(methods)} Threat Intelligence methods available")
        return True


def test_v8_automated_remediation_methods():
    """Test Automated Remediation methods are available."""
    print("\nTesting Automated Remediation API...")

    methods = [
        'create_remediation_plan',
        'apply_hardening',
        'fix_permissions',
        'remove_malware',
        'patch_vulnerabilities',
        'enforce_compliance',
        'create_rollback_point',
        'rollback_changes',
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
        print(f"\n✅ PASSED: All {len(methods)} Automated Remediation methods available")
        return True


def test_v8_predictive_analytics_methods():
    """Test Predictive Analytics methods are available."""
    print("\nTesting Predictive Analytics API...")

    methods = [
        'predict_capacity_needs',
        'predict_failures',
        'analyze_trends',
        'forecast_costs',
        'predict_resource_exhaustion',
        'generate_forecast_report',
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
        print(f"\n✅ PASSED: All {len(methods)} Predictive Analytics methods available")
        return True


def test_v8_integration_hub_methods():
    """Test Integration Hub methods are available."""
    print("\nTesting Integration Hub API...")

    methods = [
        'export_analysis',
        'register_webhook',
        'trigger_webhook',
        'connect_api',
        'send_notification',
        'create_ticket',
        'push_metrics',
        'sync_with_cmdb',
        'get_integration_status',
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
        print(f"\n✅ PASSED: All {len(methods)} Integration Hub methods available")
        return True


def test_v8_realtime_monitoring_methods():
    """Test Real-time Monitoring methods are available."""
    print("\nTesting Real-time Monitoring API...")

    methods = [
        'get_system_health',
        'create_alert_rule',
        'get_performance_metrics',
        'monitor_process',
        'get_resource_utilization',
        'check_service_health',
        'get_alert_history',
        'set_monitoring_interval',
        'get_monitoring_dashboard',
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
        print(f"\n✅ PASSED: All {len(methods)} Real-time Monitoring methods available")
        return True


def test_total_method_count():
    """Test total public method count."""
    print("\nCounting total public methods...")

    g = VMCraft()
    public_methods = [m for m in dir(g) if not m.startswith('_') and callable(getattr(g, m))]

    # Expected: 237 (v7.0) + 38 (v8.0) = 275 methods
    expected_min = 273

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
    print("VMCraft v8.0 API Completeness Test")
    print("=" * 80)

    results = []

    # Test each module
    results.append(("Threat Intelligence", test_v8_threat_intelligence_methods()))
    results.append(("Automated Remediation", test_v8_automated_remediation_methods()))
    results.append(("Predictive Analytics", test_v8_predictive_analytics_methods()))
    results.append(("Integration Hub", test_v8_integration_hub_methods()))
    results.append(("Real-time Monitoring", test_v8_realtime_monitoring_methods()))
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
