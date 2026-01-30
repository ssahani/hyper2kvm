#!/usr/bin/env python3
"""
Test VMCraft v4.0 with Windows 10 VM.

Tests all v4.0 enterprise features:
- Database detection
- Web server analysis
- Certificate management
- Container analysis
- Compliance checking
"""

import sys
import logging
from pathlib import Path

# Add hyper2kvm to path
sys.path.insert(0, str(Path(__file__).parent))

from hyper2kvm.core.vmcraft import VMCraft

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def test_database_detection(g: VMCraft):
    """Test database detection on Windows 10."""
    print("\n=== Test 1: Database Detection ===")

    try:
        databases = g.detect_databases()
        print(f"Detected databases:")
        print(f"  MySQL: {databases.get('mysql', {}).get('installed', False)}")
        print(f"  PostgreSQL: {databases.get('postgresql', {}).get('installed', False)}")
        print(f"  MongoDB: {databases.get('mongodb', {}).get('installed', False)}")
        print(f"  Redis: {databases.get('redis', {}).get('installed', False)}")
        print(f"  MS SQL: {databases.get('mssql', {}).get('installed', False)}")
        print(f"  SQLite files: {len(databases.get('sqlite_files', []))}")

        summary = g.get_database_summary(databases)
        print(f"\nSummary: {summary}")

        security = g.check_database_security(databases)
        print(f"Security issues: {len(security)}")

        print("✓ Database detection test passed")
        return True
    except Exception as e:
        print(f"✗ Database detection test failed: {e}")
        return False


def test_webserver_detection(g: VMCraft):
    """Test web server detection on Windows 10."""
    print("\n=== Test 2: Web Server Detection ===")

    try:
        webservers = g.detect_webservers()
        print(f"Detected web servers:")
        print(f"  Apache: {webservers.get('apache', {}).get('installed', False)}")
        print(f"  Nginx: {webservers.get('nginx', {}).get('installed', False)}")
        print(f"  IIS: {webservers.get('iis', {}).get('installed', False)}")
        print(f"  Lighttpd: {webservers.get('lighttpd', {}).get('installed', False)}")
        print(f"  Tomcat: {webservers.get('tomcat', {}).get('installed', False)}")
        print(f"  Total detected: {webservers.get('detected_count', 0)}")

        summary = g.get_webserver_summary(webservers)
        print(f"\nSummary: {summary}")

        security = g.check_webserver_security(webservers)
        print(f"Security issues: {len(security)}")

        print("✓ Web server detection test passed")
        return True
    except Exception as e:
        print(f"✗ Web server detection test failed: {e}")
        return False


def test_certificate_management(g: VMCraft):
    """Test certificate management on Windows 10."""
    print("\n=== Test 3: Certificate Management ===")

    try:
        certs = g.find_all_certificates()
        print(f"Found certificates:")
        print(f"  Certificates: {len(certs.get('certificates', []))}")
        print(f"  Private keys: {len(certs.get('private_keys', []))}")
        print(f"  Keystores: {len(certs.get('keystores', []))}")

        summary = g.get_certificate_summary(certs)
        print(f"\nSummary: {summary}")

        security = g.check_certificate_security(certs)
        print(f"Security issues: {len(security)}")

        expiration = g.check_certificate_expiration(certs, warning_days=30)
        print(f"Expiration: {expiration.get('note', 'N/A')}")

        print("✓ Certificate management test passed")
        return True
    except Exception as e:
        print(f"✗ Certificate management test failed: {e}")
        return False


def test_container_analysis(g: VMCraft):
    """Test container analysis on Windows 10."""
    print("\n=== Test 4: Container Analysis ===")

    try:
        containers = g.analyze_containers()
        print(f"Container runtimes:")
        print(f"  Docker: {containers.get('docker', {}).get('installed', False)}")
        print(f"  Podman: {containers.get('podman', {}).get('installed', False)}")
        print(f"  Containerd: {containers.get('containerd', {}).get('installed', False)}")

        summary = g.get_container_summary(containers)
        print(f"\nSummary: {summary}")

        images = g.list_container_images(containers)
        print(f"Container images: {len(images)}")

        security = g.check_container_security(containers)
        print(f"Security issues: {len(security)}")

        print("✓ Container analysis test passed")
        return True
    except Exception as e:
        print(f"✗ Container analysis test failed: {e}")
        return False


def test_compliance_checking(g: VMCraft):
    """Test compliance checking on Windows 10."""
    print("\n=== Test 5: Compliance Checking ===")

    try:
        # Windows compliance (basic)
        compliance = g.check_compliance(os_type="windows")
        print(f"Compliance results:")
        print(f"  Total checks: {len(compliance.get('checks', []))}")
        print(f"  Passed: {compliance.get('passed', 0)}")
        print(f"  Failed: {compliance.get('failed', 0)}")
        print(f"  Warnings: {compliance.get('warnings', 0)}")
        print(f"  Score: {compliance.get('score', 0)}")
        print(f"  Grade: {compliance.get('grade', 'N/A')}")

        summary = g.get_compliance_summary(compliance)
        print(f"\nSummary: {summary}")

        failed = g.get_failed_checks(compliance)
        print(f"Failed checks: {len(failed)}")

        recommendations = g.get_recommendations(compliance)
        print(f"Recommendations: {len(recommendations)}")

        print("✓ Compliance checking test passed")
        return True
    except Exception as e:
        print(f"✗ Compliance checking test failed: {e}")
        return False


def test_comprehensive_scan(g: VMCraft):
    """Run comprehensive v4.0 scan."""
    print("\n=== Test 6: Comprehensive v4.0 Enterprise Scan ===")

    try:
        results = {
            'databases': g.detect_databases(),
            'webservers': g.detect_webservers(),
            'certificates': g.find_all_certificates(),
            'containers': g.analyze_containers(),
            'compliance': g.check_compliance(os_type="windows"),
        }

        # Count detected items
        db_count = results['databases'].get('detected_count', 0)
        ws_count = results['webservers'].get('detected_count', 0)
        cert_count = len(results['certificates'].get('certificates', []))
        container_count = results['containers'].get('total_containers', 0)
        compliance_score = results['compliance'].get('score', 0)

        print(f"\nComprehensive Scan Results:")
        print(f"  Databases detected: {db_count}")
        print(f"  Web servers detected: {ws_count}")
        print(f"  Certificates found: {cert_count}")
        print(f"  Containers found: {container_count}")
        print(f"  Compliance score: {compliance_score}%")

        print("✓ Comprehensive scan test passed")
        return True
    except Exception as e:
        print(f"✗ Comprehensive scan test failed: {e}")
        return False


def main():
    """Run all v4.0 tests with Windows 10 VM."""
    print("=" * 70)
    print("VMCraft v4.0 Enterprise Features - Windows 10 Integration Test")
    print("=" * 70)

    # Find Windows 10 VM
    vm_path = Path("win10.vhdx")
    if not vm_path.exists():
        # Try alternate locations
        alt_paths = [
            Path("/home/ssahani/by-path/win10.vhdx"),
            Path("../win10.vhdx"),
        ]
        for alt_path in alt_paths:
            if alt_path.exists():
                vm_path = alt_path
                break

    if not vm_path.exists():
        print(f"✗ Windows 10 VM not found at {vm_path}")
        print("Please ensure win10.vhdx is in the current directory")
        return 1

    print(f"Using Windows 10 VM: {vm_path}")

    # Initialize VMCraft
    g = VMCraft(python_return_dict=True)
    g.add_drive_opts(str(vm_path), readonly=1, format="vhdx")

    try:
        g.launch()
        print("✓ VMCraft launched successfully")

        # Mount root filesystem (best effort)
        try:
            roots = g.inspect_os()
            if roots:
                root = roots[0]
                mps = g.inspect_get_mountpoints(root)
                # Try to mount Windows C: drive
                for mp, dev in sorted(mps.items()):
                    if mp == "/":
                        try:
                            g.mount_ro(dev, "/")
                            print(f"✓ Mounted {dev} at /")
                            break
                        except Exception as e:
                            print(f"Note: Could not mount {dev}: {e}")
        except Exception as e:
            print(f"Note: Guest filesystem not fully accessible: {e}")
            print("Continuing with available tests...")

        # Run all v4.0 tests
        tests = [
            ("Database Detection", test_database_detection),
            ("Web Server Detection", test_webserver_detection),
            ("Certificate Management", test_certificate_management),
            ("Container Analysis", test_container_analysis),
            ("Compliance Checking", test_compliance_checking),
            ("Comprehensive Scan", test_comprehensive_scan),
        ]

        results = []
        for test_name, test_func in tests:
            try:
                result = test_func(g)
                results.append((test_name, result))
            except Exception as e:
                print(f"\n✗ {test_name} FAILED with exception: {e}")
                results.append((test_name, False))

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
            print("\n🎉 All v4.0 tests passed with Windows 10 VM!")
            return_code = 0
        else:
            print("\n⚠️  Some tests failed. Please review the output above.")
            return_code = 1

    finally:
        try:
            g.close()
            print("\n✓ VMCraft closed successfully")
        except Exception as e:
            print(f"\n✗ Error closing VMCraft: {e}")

    return return_code


if __name__ == "__main__":
    sys.exit(main())
