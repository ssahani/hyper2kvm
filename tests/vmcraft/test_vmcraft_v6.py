#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
# test_vmcraft_v6.py
"""
Test VMCraft v6.0 API completeness.

This test verifies that all v6.0 methods are available in the VMCraft class.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from hyper2kvm.core.vmcraft import VMCraft


def test_v6_vulnerability_scanner_methods():
    """Test Vulnerability Scanner methods are available."""
    print("Testing Vulnerability Scanner API...")

    methods = [
        'scan_vulnerabilities',
        'get_vulnerability_summary',
        'get_critical_vulnerabilities',
        'get_remediation_priority',
        'detect_ransomware_indicators',
        'check_kernel_vulnerabilities',
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
        print(f"\n✅ PASSED: All {len(methods)} Vulnerability Scanner methods available")
        return True


def test_v6_license_detector_methods():
    """Test License Detector methods are available."""
    print("\nTesting License Detector API...")

    methods = [
        'detect_licenses',
        'get_license_summary',
        'get_copyleft_packages',
        'generate_sbom',
        'check_license_compatibility',
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
        print(f"\n✅ PASSED: All {len(methods)} License Detector methods available")
        return True


def test_v6_performance_analyzer_methods():
    """Test Performance Analyzer methods are available."""
    print("\nTesting Performance Analyzer API...")

    methods = [
        'analyze_performance',
        'get_performance_summary',
        'get_sizing_recommendation',
        'estimate_resource_cost',
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
        print(f"\n✅ PASSED: All {len(methods)} Performance Analyzer methods available")
        return True


def test_v6_migration_planner_methods():
    """Test Migration Planner methods are available."""
    print("\nTesting Migration Planner API...")

    methods = [
        'plan_migration',
        'get_migration_summary',
        'get_migration_checklist',
        'generate_rollback_plan',
        'validate_migration_readiness',
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
        print(f"\n✅ PASSED: All {len(methods)} Migration Planner methods available")
        return True


def test_v6_dependency_mapper_methods():
    """Test Dependency Mapper methods are available."""
    print("\nTesting Dependency Mapper API...")

    methods = [
        'map_dependencies',
        'get_dependency_summary',
        'get_service_graph',
        'find_critical_services',
        'get_port_security_analysis',
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
        print(f"\n✅ PASSED: All {len(methods)} Dependency Mapper methods available")
        return True


def test_total_method_count():
    """Test total public method count."""
    print("\nCounting total public methods...")

    g = VMCraft()
    public_methods = [m for m in dir(g) if not m.startswith('_') and callable(getattr(g, m))]

    # Expected: 178 (v5.0) + 25 (v6.0) = 203 methods
    expected_min = 200

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
    print("VMCraft v6.0 API Completeness Test")
    print("=" * 80)

    results = []

    # Test each module
    results.append(("Vulnerability Scanner", test_v6_vulnerability_scanner_methods()))
    results.append(("License Detector", test_v6_license_detector_methods()))
    results.append(("Performance Analyzer", test_v6_performance_analyzer_methods()))
    results.append(("Migration Planner", test_v6_migration_planner_methods()))
    results.append(("Dependency Mapper", test_v6_dependency_mapper_methods()))
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
