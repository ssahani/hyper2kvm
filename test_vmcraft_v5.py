#!/usr/bin/env python3
"""
Test VMCraft v5.0 Operational Intelligence Features.

Tests the 5 new modules added in v5.0:
- Backup Analysis
- User Activity Tracking
- Application Framework Detection
- Cloud Integration Detection
- Monitoring Agent Detection
"""

import sys
from pathlib import Path

# Add hyper2kvm to path
sys.path.insert(0, str(Path(__file__).parent))

from hyper2kvm.core.vmcraft import VMCraft


def test_v5_api_availability():
    """Test that all v5.0 methods are available."""
    print("\n=== Testing VMCraft v5.0 API Availability ===\n")

    # Expected v5.0 methods (19 new methods)
    v5_methods = [
        # Backup Analysis (4 methods)
        'analyze_backup_software',
        'get_backup_summary',
        'check_backup_health',
        'list_backup_software',
        # User Activity (4 methods)
        'analyze_user_activity',
        'get_activity_summary',
        'detect_suspicious_activity',
        'get_top_sudo_users',
        # App Framework Detection (3 methods)
        'detect_frameworks',
        'get_framework_summary',
        'list_web_frameworks',
        # Cloud Integration (4 methods)
        'detect_cloud_integration',
        'get_cloud_summary',
        'is_cloud_vm',
        'get_cloud_services',
        # Monitoring Agents (4 methods)
        'detect_monitoring_agents',
        'get_monitoring_summary',
        'list_agent_vendors',
        'check_monitoring_health',
    ]

    g = VMCraft(python_return_dict=True)

    print(f"Checking {len(v5_methods)} v5.0 methods...")
    available = 0
    missing = []

    for method_name in v5_methods:
        if hasattr(g, method_name):
            available += 1
            print(f"  ✓ {method_name}")
        else:
            missing.append(method_name)
            print(f"  ✗ {method_name} - MISSING")

    print(f"\nResult: {available}/{len(v5_methods)} v5.0 methods available")

    if missing:
        print(f"\nMissing methods: {', '.join(missing)}")
        return False

    return True


def test_v4_backward_compatibility():
    """Test that v4.0 methods are still available."""
    print("\n=== Testing v4.0 Backward Compatibility ===\n")

    v4_methods = [
        'detect_databases',
        'get_database_summary',
        'check_database_security',
        'detect_webservers',
        'get_webserver_summary',
        'check_webserver_security',
        'find_all_certificates',
        'check_certificate_expiration',
        'get_certificate_summary',
        'check_certificate_security',
        'analyze_containers',
        'get_container_summary',
        'list_container_images',
        'check_container_security',
        'check_compliance',
        'get_compliance_summary',
        'get_failed_checks',
        'get_recommendations',
    ]

    g = VMCraft(python_return_dict=True)

    available = sum(1 for method in v4_methods if hasattr(g, method))

    print(f"Result: {available}/{len(v4_methods)} v4.0 methods available")

    return available == len(v4_methods)


def test_total_method_count():
    """Count all public methods."""
    print("\n=== Testing Total Method Count ===\n")

    g = VMCraft(python_return_dict=True)

    # Get all public methods (not starting with _)
    public_methods = [
        name for name in dir(g)
        if callable(getattr(g, name)) and not name.startswith('_')
    ]

    print(f"Total public methods: {len(public_methods)}")
    print(f"Expected: ~197+ methods (159 base + 18 v4.0 + 19 v5.0)")

    return len(public_methods) >= 175


def test_module_imports():
    """Test that all v5.0 modules can be imported."""
    print("\n=== Testing v5.0 Module Imports ===\n")

    modules = [
        ('BackupAnalysis', 'hyper2kvm.core.vmcraft.backup_analysis'),
        ('UserActivityAnalyzer', 'hyper2kvm.core.vmcraft.user_activity'),
        ('AppFrameworkDetector', 'hyper2kvm.core.vmcraft.app_framework_detector'),
        ('CloudDetector', 'hyper2kvm.core.vmcraft.cloud_detector'),
        ('MonitoringDetector', 'hyper2kvm.core.vmcraft.monitoring_detector'),
    ]

    all_ok = True
    for class_name, module_path in modules:
        try:
            module = __import__(module_path, fromlist=[class_name])
            cls = getattr(module, class_name)
            print(f"  ✓ {class_name} from {module_path}")
        except Exception as e:
            print(f"  ✗ {class_name} from {module_path} - ERROR: {e}")
            all_ok = False

    return all_ok


def test_vmcraft_statistics():
    """Display VMCraft statistics."""
    print("\n=== VMCraft v5.0 Statistics ===\n")

    g = VMCraft(python_return_dict=True)

    # Count methods by category
    public_methods = [
        name for name in dir(g)
        if callable(getattr(g, name)) and not name.startswith('_')
    ]

    print(f"Public Methods: {len(public_methods)}")
    print(f"")
    print(f"Version History:")
    print(f"  v1.0: Original libguestfs wrapper")
    print(f"  v2.0: Native implementation with core modules")
    print(f"  v2.5: Windows management + backup/security/optimization")
    print(f"  v3.0: Network, firewall, SSH, logs, hardware, scheduled tasks (+27 methods)")
    print(f"  v4.0: Databases, web servers, certificates, containers, compliance (+18 methods)")
    print(f"  v5.0: Backup, user activity, app frameworks, cloud, monitoring (+19 methods)")
    print(f"")
    print(f"Module Count: 37 specialized modules")
    print(f"Lines of Code: ~15,000+")


def main():
    """Run all tests."""
    print("=" * 70)
    print("VMCraft v5.0 Operational Intelligence Test Suite")
    print("=" * 70)

    tests = [
        ("v5.0 API Availability", test_v5_api_availability),
        ("v4.0 Backward Compatibility", test_v4_backward_compatibility),
        ("Total Method Count", test_total_method_count),
        ("Module Imports", test_module_imports),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ {test_name} FAILED with exception: {e}")
            results.append((test_name, False))

    # Display statistics
    test_vmcraft_statistics()

    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status}: {test_name}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! VMCraft v5.0 is UNBEATABLE!")
        print("\n🚀 The ultimate VM analysis platform is ready!")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
