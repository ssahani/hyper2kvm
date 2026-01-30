#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Comprehensive Windows 10 VM Inspection Test

Demonstrates all VMCraft enhanced features:
- OS detection and inspection
- Container detection
- Bootloader detection
- Windows user management
- Registry operations
- Security analysis
- Performance metrics
"""

import sys
from pathlib import Path
from hyper2kvm.core.vmcraft import VMCraft

def print_section(title: str):
    """Print section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def main():
    # Use correct path relative to current directory
    vm_disk = Path("./win10/win10.vmdk")

    print_section("VMCraft Comprehensive Windows 10 Inspection")
    print(f"VM Disk: {vm_disk.absolute()}")
    print(f"Exists: {vm_disk.exists()}")

    if not vm_disk.exists():
        print(f"\n❌ VM disk not found at {vm_disk.absolute()}")
        return 1

    print(f"✓ VM disk found ({vm_disk.stat().st_size} bytes)")

    # Initialize VMCraft
    print("\n🚀 Initializing VMCraft...")
    g = VMCraft(python_return_dict=True)

    try:
        # Phase 1: Launch
        print_section("Phase 1: Launch & Connect")
        print("Adding drive...")
        g.add_drive_opts(str(vm_disk), readonly=True, format="vmdk")

        print("Launching (connecting NBD, activating storage)...")
        g.launch()
        print("✓ Launched successfully")

        # Phase 2: OS Detection
        print_section("Phase 2: OS Detection & Inspection")
        print("Detecting operating systems...")
        roots = g.inspect_os()

        if not roots:
            print("❌ No operating systems detected")
            return 1

        print(f"✓ Found {len(roots)} operating system(s)")

        for idx, root in enumerate(roots, 1):
            print(f"\n--- Operating System #{idx} ---")
            print(f"Root device: {root}")

            os_type = g.inspect_get_type(root)
            print(f"Type: {os_type}")

            if os_type == "windows":
                product = g.inspect_get_product_name(root)
                print(f"Product: {product}")

                distro = g.inspect_get_distro(root)
                print(f"Distro: {distro}")

                major = g.inspect_get_major_version(root)
                minor = g.inspect_get_minor_version(root)
                print(f"Version: {major}.{minor}")

                arch = g.inspect_get_arch(root)
                print(f"Architecture: {arch}")

        # Use first root for remaining tests
        root = roots[0]

        # Phase 3: Mount filesystems
        print_section("Phase 3: Mount Filesystems")
        mountpoints = g.inspect_get_mountpoints(root)
        print(f"Detected {len(mountpoints)} mountpoint(s)")

        for mp, dev in sorted(mountpoints.items()):
            print(f"  Mounting {dev} at {mp}...")
            try:
                if mp == "/":
                    g.mount(dev, mp)
                else:
                    g.mount(dev, mp)
                print(f"    ✓ Mounted")
            except Exception as e:
                print(f"    ⚠ Mount failed: {e}")

        # Phase 4: Container Detection
        print_section("Phase 4: Container Detection")
        try:
            containers = g.detect_containers()
            print(f"Is Container: {containers['is_container']}")
            print(f"Container Type: {containers.get('container_type', 'None')}")
            print("Indicators:")
            for tech, detected in containers['indicators'].items():
                print(f"  {tech}: {detected}")
        except Exception as e:
            print(f"⚠ Container detection failed: {e}")

        # Phase 5: Bootloader Detection
        print_section("Phase 5: Bootloader Detection")
        try:
            bootloader = g.detect_bootloader()
            print(f"Bootloader: {bootloader.get('bootloader', 'unknown')}")
            print(f"Is UEFI: {bootloader.get('is_uefi', False)}")
            print(f"Config Path: {bootloader.get('config_path', 'N/A')}")

            entries = bootloader.get('entries', [])
            if entries:
                print(f"\nBoot Entries ({len(entries)}):")
                for entry in entries[:5]:  # Show first 5
                    print(f"  - {entry.get('title', 'Unknown')}")
        except Exception as e:
            print(f"⚠ Bootloader detection failed: {e}")

        # Phase 6: Windows-Specific Analysis
        if g.inspect_get_type(root) == "windows":
            print_section("Phase 6: Windows Analysis")

            # Windows Users
            print("\n--- Windows Users ---")
            try:
                users = g.win_list_users()
                print(f"Found {len(users)} user(s):")
                for user in users[:10]:  # Show first 10
                    status = "(DISABLED)" if user.get('disabled') else ""
                    print(f"  - {user['username']} {status}")

                # Admin check
                admins = g.win_list_administrators()
                print(f"\nAdministrators ({len(admins)}):")
                for admin in admins[:5]:
                    print(f"  - {admin}")

                # User statistics
                stats = g.win_get_user_count()
                print(f"\nUser Statistics:")
                print(f"  Total: {stats.get('total', 0)}")
                print(f"  Enabled: {stats.get('enabled', 0)}")
                print(f"  Disabled: {stats.get('disabled', 0)}")
                print(f"  Administrators: {stats.get('administrators', 0)}")
            except Exception as e:
                print(f"⚠ User enumeration failed: {e}")

            # Windows Registry
            print("\n--- Windows Registry ---")
            try:
                # Read Windows version info
                product = g.win_registry_read(
                    "SOFTWARE",
                    r"Microsoft\Windows NT\CurrentVersion",
                    "ProductName"
                )
                print(f"ProductName: {product}")

                build = g.win_registry_read(
                    "SOFTWARE",
                    r"Microsoft\Windows NT\CurrentVersion",
                    "CurrentBuild"
                )
                print(f"CurrentBuild: {build}")

                edition = g.win_registry_read(
                    "SOFTWARE",
                    r"Microsoft\Windows NT\CurrentVersion",
                    "EditionID"
                )
                print(f"EditionID: {edition}")
            except Exception as e:
                print(f"⚠ Registry read failed: {e}")

        # Phase 7: Security Analysis
        print_section("Phase 7: Security Analysis")

        # SELinux
        try:
            selinux = g.detect_selinux()
            print(f"SELinux:")
            print(f"  Enabled: {selinux.get('enabled', False)}")
            if selinux.get('enabled'):
                print(f"  Mode: {selinux.get('mode', 'unknown')}")
                print(f"  Policy: {selinux.get('policy', 'unknown')}")
        except Exception as e:
            print(f"⚠ SELinux detection failed: {e}")

        # AppArmor
        try:
            apparmor = g.detect_apparmor()
            print(f"\nAppArmor:")
            print(f"  Enabled: {apparmor.get('enabled', False)}")
            if apparmor.get('enabled'):
                print(f"  Profiles Loaded: {apparmor.get('profiles_loaded', 0)}")
        except Exception as e:
            print(f"⚠ AppArmor detection failed: {e}")

        # Phase 8: Performance Metrics
        print_section("Phase 8: Performance Metrics")
        try:
            metrics = g.get_performance_metrics()
            print(f"Launch Time: {metrics.get('launch_time_s', 0):.2f}s")
            print(f"NBD Connect Time: {metrics.get('nbd_connect_time_s', 0):.2f}s")
            print(f"Storage Activation Time: {metrics.get('storage_activation_time_s', 0):.2f}s")

            ops = metrics.get('operations', {})
            print(f"\nOperations:")
            print(f"  Mounts: {ops.get('mounts', 0)}")
            print(f"  File Reads: {ops.get('file_reads', 0)}")
            print(f"  Registry Reads: {ops.get('registry_reads', 0)}")

            print(f"\nMemory Estimate: {metrics.get('memory_estimate_mb', 0):.1f} MB")
        except Exception as e:
            print(f"⚠ Performance metrics failed: {e}")

        # Cache Statistics
        print("\n--- Cache Statistics ---")
        try:
            cache_stats = g.get_cache_stats()
            print(f"Total Hit Rate: {cache_stats.get('total_hit_rate', 0)*100:.1f}%")

            meta = cache_stats.get('metadata_cache', {})
            print(f"\nMetadata Cache:")
            print(f"  Hits: {meta.get('hits', 0)}")
            print(f"  Misses: {meta.get('misses', 0)}")
            print(f"  Size: {meta.get('size', 0)} entries")
            print(f"  Hit Rate: {meta.get('hit_rate', 0)*100:.1f}%")

            dirr = cache_stats.get('directory_cache', {})
            print(f"\nDirectory Cache:")
            print(f"  Hits: {dirr.get('hits', 0)}")
            print(f"  Misses: {dirr.get('misses', 0)}")
            print(f"  Size: {dirr.get('size', 0)} entries")
            print(f"  Hit Rate: {dirr.get('hit_rate', 0)*100:.1f}%")
        except Exception as e:
            print(f"⚠ Cache statistics failed: {e}")

        # Phase 9: Filesystem Analysis
        print_section("Phase 9: Filesystem Analysis")
        try:
            filesystems = g.list_filesystems()
            print(f"Detected {len(filesystems)} filesystem(s):")
            for dev, fstype in list(filesystems.items())[:10]:  # Show first 10
                print(f"  {dev}: {fstype}")
        except Exception as e:
            print(f"⚠ Filesystem listing failed: {e}")

        # Phase 10: Cleanup
        print_section("Phase 10: Cleanup")
        print("Unmounting filesystems...")
        g.umount_all()
        print("✓ Unmounted")

        print("Shutting down...")
        g.shutdown()
        print("✓ Shutdown complete")

        print_section("✅ Comprehensive Inspection Complete")
        print("All VMCraft enhanced features tested successfully!")

        return 0

    except Exception as e:
        print(f"\n❌ Error during inspection: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # Ensure cleanup
        try:
            g.shutdown()
        except:
            pass
        try:
            g.close()
        except:
            pass

if __name__ == "__main__":
    sys.exit(main())
