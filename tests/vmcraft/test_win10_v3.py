#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test VMCraft v3.0 features with Windows 10 VM.

Tests all new v3.0 features against a real Windows 10 VM disk.
"""

import sys
from pathlib import Path
from hyper2kvm.core.vmcraft import VMCraft


def test_windows_network_analysis(g):
    """Test network configuration analysis on Windows."""
    print("\n" + "=" * 70)
    print("1. Network Configuration Analysis (Windows)")
    print("=" * 70)

    try:
        network = g.analyze_network_config(os_type="windows")

        print(f"✓ Network analysis completed")
        print(f"  Note: {network.get('note', 'N/A')}")
        print(f"  Hostname: {network.get('hostname', 'N/A')}")
        print(f"  DNS servers: {network.get('dns_servers', [])}")
        print(f"  Interfaces: {len(network.get('interfaces', []))}")

        return True
    except Exception as e:
        print(f"✗ Network analysis failed: {e}")
        return False


def test_windows_firewall_analysis(g):
    """Test firewall analysis on Windows."""
    print("\n" + "=" * 70)
    print("2. Windows Firewall Analysis")
    print("=" * 70)

    try:
        firewall = g.analyze_firewall(os_type="windows")

        print(f"✓ Firewall analysis completed")
        print(f"  Firewall type: {firewall.get('firewall_type', 'N/A')}")
        print(f"  Note: {firewall.get('note', 'N/A')}")
        print(f"  Enabled: {firewall.get('enabled', 'Unknown')}")
        print(f"  Total tasks: {len(firewall.get('tasks', []))}")

        return True
    except Exception as e:
        print(f"✗ Firewall analysis failed: {e}")
        return False


def test_windows_scheduled_tasks(g):
    """Test scheduled task analysis on Windows."""
    print("\n" + "=" * 70)
    print("3. Windows Scheduled Tasks Analysis")
    print("=" * 70)

    try:
        tasks = g.analyze_scheduled_tasks(os_type="windows")

        print(f"✓ Scheduled task analysis completed")
        print(f"  Note: {tasks.get('note', 'N/A')}")
        print(f"  Total tasks: {tasks.get('total_count', 0)}")
        print(f"  Tasks found: {len(tasks.get('tasks', []))}")

        # Show first few tasks
        if tasks.get('tasks'):
            print(f"\n  Sample tasks:")
            for task in tasks['tasks'][:5]:
                print(f"    - {task.get('name', 'Unknown')}")
                print(f"      Path: {task.get('path', 'N/A')}")

        return True
    except Exception as e:
        print(f"✗ Scheduled task analysis failed: {e}")
        return False


def test_hardware_detection(g):
    """Test hardware detection."""
    print("\n" + "=" * 70)
    print("4. Hardware Detection")
    print("=" * 70)

    try:
        hardware = g.detect_hardware()

        print(f"✓ Hardware detection completed")

        # Check virtualization
        is_vm = g.is_virtual_machine(hardware)
        print(f"  Is Virtual Machine: {is_vm}")

        if is_vm:
            hypervisor = g.get_hypervisor(hardware)
            print(f"  Hypervisor: {hypervisor}")

        # Get summary
        summary = g.get_hardware_summary(hardware)
        print(f"  Manufacturer: {summary.get('manufacturer', 'N/A')}")
        print(f"  Product: {summary.get('product', 'N/A')}")
        print(f"  CPU Model: {summary.get('cpu_model', 'N/A')}")
        print(f"  CPU Cores: {summary.get('cpu_cores', 0)}")
        print(f"  Disk Count: {summary.get('disk_count', 0)}")
        print(f"  Network Interfaces: {summary.get('network_interfaces', 0)}")

        # Test individual methods
        memory = g.get_total_memory_mb(hardware)
        disks = g.get_disk_count(hardware)
        nics = g.get_network_interface_count(hardware)

        print(f"\n  Detailed info:")
        print(f"    Total Memory: {memory if memory else 'N/A'} MB")
        print(f"    Disk Count: {disks}")
        print(f"    NIC Count: {nics}")

        return True
    except Exception as e:
        print(f"✗ Hardware detection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_windows_services(g):
    """Test Windows service enumeration (v2.5 feature)."""
    print("\n" + "=" * 70)
    print("5. Windows Services (v2.5 feature)")
    print("=" * 70)

    try:
        # Get service statistics
        stats = g.win_get_service_count()

        print(f"✓ Windows service analysis completed")
        print(f"  Total services: {stats.get('total', 0)}")
        print(f"  Automatic: {stats.get('automatic', 0)}")
        print(f"  Manual: {stats.get('manual', 0)}")
        print(f"  Disabled: {stats.get('disabled', 0)}")
        print(f"  Boot: {stats.get('boot', 0)}")
        print(f"  System: {stats.get('system', 0)}")

        # List some automatic services
        auto_services = g.win_list_automatic_services()
        print(f"\n  Auto-start services ({len(auto_services)} total):")
        for svc in auto_services[:10]:
            print(f"    - {svc}")

        return True
    except Exception as e:
        print(f"✗ Windows service analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_windows_applications(g):
    """Test Windows application enumeration (v2.5 feature)."""
    print("\n" + "=" * 70)
    print("6. Windows Applications (v2.5 feature)")
    print("=" * 70)

    try:
        # Get application statistics
        stats = g.win_get_application_count()

        print(f"✓ Windows application analysis completed")
        print(f"  Total applications: {stats.get('total', 0)}")
        print(f"  Total size: {stats.get('total_size_mb', 0):.2f} MB")

        # List some applications
        apps = g.win_list_applications(limit=10)
        print(f"\n  Installed applications ({len(apps)} shown):")
        for app in apps:
            print(f"    - {app.get('name', 'Unknown')}")
            if app.get('version'):
                print(f"      Version: {app['version']}")
            if app.get('publisher'):
                print(f"      Publisher: {app['publisher']}")
            if app.get('size_mb'):
                print(f"      Size: {app['size_mb']} MB")

        return True
    except Exception as e:
        print(f"✗ Windows application analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests on Windows 10 VM."""
    print("\n" + "=" * 70)
    print("VMCraft v3.0 - Windows 10 VM Test")
    print("=" * 70)

    vm_path = Path("win10/win10.vmdk")

    if not vm_path.exists():
        print(f"✗ VM disk not found: {vm_path}")
        return 1

    print(f"\nTesting with: {vm_path}")
    print(f"Size: {vm_path.stat().st_size / (1024**3):.2f} GB")

    results = {
        'network': False,
        'firewall': False,
        'tasks': False,
        'hardware': False,
        'services': False,
        'applications': False,
    }

    try:
        print("\nLaunching VMCraft...")
        with VMCraft() as g:
            g.add_drive_opts(str(vm_path), readonly=True, format="vmdk")
            g.launch()

            print("✓ VMCraft launched successfully")

            # Inspect OS
            print("\nInspecting OS...")
            roots = g.inspect_os()
            if not roots:
                print("✗ No OS detected")
                return 1

            root = roots[0]
            os_type = g.inspect_get_type(root)
            product = g.inspect_get_product_name(root)
            version = f"{g.inspect_get_major_version(root)}.{g.inspect_get_minor_version(root)}"

            print(f"✓ OS detected: {product} ({os_type} {version})")

            # Run v3.0 tests
            results['network'] = test_windows_network_analysis(g)
            results['firewall'] = test_windows_firewall_analysis(g)
            results['tasks'] = test_windows_scheduled_tasks(g)
            results['hardware'] = test_hardware_detection(g)

            # Run v2.5 tests (Windows-specific)
            results['services'] = test_windows_services(g)
            results['applications'] = test_windows_applications(g)

    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Print summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {test_name}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All tests passed!")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
