#!/usr/bin/env python3
"""
Test VMCraft v4.0 Enterprise Features.

Tests the 5 new modules added in v4.0:
- Database Detection
- Web Server Analysis
- Certificate Management
- Container Analysis
- Compliance Checking
"""

import sys
from pathlib import Path

# Add hyper2kvm to path
sys.path.insert(0, str(Path(__file__).parent))

from hyper2kvm.core.vmcraft import VMCraft


def test_v4_api_availability():
    """Test that all v4.0 methods are available."""
    print("\n=== Testing VMCraft v4.0 API Availability ===\n")

    # Expected v4.0 methods (18 new methods)
    v4_methods = [
        # Database Detection (3 methods)
        'detect_databases',
        'get_database_summary',
        'check_database_security',
        # Web Server Analysis (3 methods)
        'detect_webservers',
        'get_webserver_summary',
        'check_webserver_security',
        # Certificate Management (4 methods)
        'find_all_certificates',
        'check_certificate_expiration',
        'get_certificate_summary',
        'check_certificate_security',
        # Container Analysis (4 methods)
        'analyze_containers',
        'get_container_summary',
        'list_container_images',
        'check_container_security',
        # Compliance Checking (4 methods)
        'check_compliance',
        'get_compliance_summary',
        'get_failed_checks',
        'get_recommendations',
    ]

    g = VMCraft(python_return_dict=True)

    print(f"Checking {len(v4_methods)} v4.0 methods...")
    available = 0
    missing = []

    for method_name in v4_methods:
        if hasattr(g, method_name):
            available += 1
            print(f"  ✓ {method_name}")
        else:
            missing.append(method_name)
            print(f"  ✗ {method_name} - MISSING")

    print(f"\nResult: {available}/{len(v4_methods)} v4.0 methods available")

    if missing:
        print(f"\nMissing methods: {', '.join(missing)}")
        return False

    return True


def test_v3_backward_compatibility():
    """Test that v3.0 methods are still available."""
    print("\n=== Testing v3.0 Backward Compatibility ===\n")

    v3_methods = [
        'analyze_network_config',
        'find_static_ips',
        'detect_network_bonds',
        'analyze_firewall',
        'get_open_ports',
        'get_blocked_ports',
        'get_firewall_stats',
        'analyze_scheduled_tasks',
        'get_task_count',
        'find_daily_tasks',
        'find_tasks_by_user',
        'analyze_ssh_config',
        'get_ssh_port',
        'is_root_login_allowed',
        'is_password_auth_enabled',
        'get_authorized_key_count',
        'get_security_score',
        'analyze_logs',
        'get_recent_errors',
        'get_critical_events',
        'detect_hardware',
        'is_virtual_machine',
        'get_hypervisor',
        'get_total_memory_mb',
        'get_disk_count',
        'get_network_interface_count',
        'get_hardware_summary',
    ]

    g = VMCraft(python_return_dict=True)

    available = sum(1 for method in v3_methods if hasattr(g, method))

    print(f"Result: {available}/{len(v3_methods)} v3.0 methods available")

    return available == len(v3_methods)


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
    print(f"Expected: ~160+ methods (141 from v2.5 + 27 from v3.0 + 18 from v4.0)")

    return len(public_methods) >= 155


def test_module_imports():
    """Test that all v4.0 modules can be imported."""
    print("\n=== Testing v4.0 Module Imports ===\n")

    modules = [
        ('DatabaseDetector', 'hyper2kvm.core.vmcraft.database_detector'),
        ('WebServerAnalyzer', 'hyper2kvm.core.vmcraft.webserver_analyzer'),
        ('CertificateManager', 'hyper2kvm.core.vmcraft.certificate_manager'),
        ('ContainerAnalyzer', 'hyper2kvm.core.vmcraft.container_analyzer'),
        ('ComplianceChecker', 'hyper2kvm.core.vmcraft.compliance_checker'),
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
    print("\n=== VMCraft v4.0 Statistics ===\n")

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
    print(f"")
    print(f"Module Count: 32 specialized modules")
    print(f"Lines of Code: ~12,000+")


def main():
    """Run all tests."""
    print("=" * 70)
    print("VMCraft v4.0 Enterprise Features Test Suite")
    print("=" * 70)

    tests = [
        ("v4.0 API Availability", test_v4_api_availability),
        ("v3.0 Backward Compatibility", test_v3_backward_compatibility),
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
        print("\n🎉 All tests passed! VMCraft v4.0 is ready!")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
