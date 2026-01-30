#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
# test_vmcraft_v7.py
"""
Test VMCraft v7.0 API completeness.

This test verifies that all v7.0 methods are available in the VMCraft class.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from hyper2kvm.core.vmcraft import VMCraft


def test_v7_forensic_analyzer_methods():
    """Test Forensic Analyzer methods are available."""
    print("Testing Forensic Analyzer API...")

    methods = [
        'analyze_forensics',
        'get_forensic_summary',
        'generate_forensic_timeline',
        'detect_rootkit_indicators',
        'analyze_browser_history',
        'find_recently_accessed_files',
        'detect_data_exfiltration_indicators',
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
        print(f"\n✅ PASSED: All {len(methods)} Forensic Analyzer methods available")
        return True


def test_v7_data_discovery_methods():
    """Test Data Discovery methods are available."""
    print("\nTesting Data Discovery API...")

    methods = [
        'discover_sensitive_data',
        'get_data_discovery_summary',
        'classify_data_sensitivity',
        'get_compliance_report',
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
        print(f"\n✅ PASSED: All {len(methods)} Data Discovery methods available")
        return True


def test_v7_config_tracker_methods():
    """Test Configuration Tracker methods are available."""
    print("\nTesting Configuration Tracker API...")

    methods = [
        'track_configurations',
        'create_config_baseline',
        'detect_config_drift',
        'validate_best_practices',
        'get_config_summary',
        'analyze_config_security',
        'compare_configs',
        'generate_config_documentation',
        'get_config_backup_recommendations',
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
        print(f"\n✅ PASSED: All {len(methods)} Configuration Tracker methods available")
        return True


def test_v7_network_topology_methods():
    """Test Network Topology methods are available."""
    print("\nTesting Network Topology API...")

    methods = [
        'map_network_topology',
        'get_topology_summary',
        'analyze_network_redundancy',
        'detect_network_segmentation',
        'generate_topology_graph',
        'get_network_policy_summary',
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
        print(f"\n✅ PASSED: All {len(methods)} Network Topology methods available")
        return True


def test_v7_storage_analyzer_methods():
    """Test Storage Analyzer methods are available."""
    print("\nTesting Storage Analyzer API...")

    methods = [
        'analyze_storage_advanced',
        'get_storage_summary',
        'get_capacity_planning',
        'analyze_storage_performance',
        'detect_storage_tiering',
        'estimate_deduplication_ratio',
        'analyze_raid_health',
        'get_storage_optimization_recommendations',
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
        print(f"\n✅ PASSED: All {len(methods)} Storage Analyzer methods available")
        return True


def test_total_method_count():
    """Test total public method count."""
    print("\nCounting total public methods...")

    g = VMCraft()
    public_methods = [m for m in dir(g) if not m.startswith('_') and callable(getattr(g, m))]

    # Expected: 203 (v6.0) + 34 (v7.0) = 237 methods
    expected_min = 235

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
    print("VMCraft v7.0 API Completeness Test")
    print("=" * 80)

    results = []

    # Test each module
    results.append(("Forensic Analyzer", test_v7_forensic_analyzer_methods()))
    results.append(("Data Discovery", test_v7_data_discovery_methods()))
    results.append(("Configuration Tracker", test_v7_config_tracker_methods()))
    results.append(("Network Topology", test_v7_network_topology_methods()))
    results.append(("Storage Analyzer", test_v7_storage_analyzer_methods()))
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
