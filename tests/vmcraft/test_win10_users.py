#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test Windows User Enumeration

Focus on testing Windows user account management via SAM registry.
"""

import sys
from pathlib import Path
from hyper2kvm.core.vmcraft import VMCraft

def main():
    vm_disk = Path("./win10/win10.vmdk")

    print("=== Windows 10 User Enumeration Test ===\n")
    print(f"VM Disk: {vm_disk.absolute()}")

    if not vm_disk.exists():
        print(f"❌ VM disk not found")
        return 1

    g = VMCraft(python_return_dict=True)

    try:
        print("\n1. Launching...")
        g.add_drive_opts(str(vm_disk), readonly=True, format="vmdk")
        g.launch()
        print("   ✓ Launched")

        print("\n2. Detecting OS...")
        roots = g.inspect_os()
        if not roots:
            print("   ❌ No OS detected")
            return 1

        root = roots[0]
        os_type = g.inspect_get_type(root)
        product = g.inspect_get_product_name(root)
        print(f"   ✓ Detected: {product} ({os_type})")

        print("\n3. Listing Windows users...")
        try:
            users = g.win_list_users()
            print(f"   Found {len(users)} users:")
            for user in users:
                status = " (DISABLED)" if user.get('disabled') else ""
                print(f"     - {user['username']}{status}")
                print(f"       RID: {user.get('rid', 'N/A')}")
        except Exception as e:
            print(f"   ❌ User listing failed: {e}")
            import traceback
            traceback.print_exc()

        print("\n4. Getting user statistics...")
        try:
            stats = g.win_get_user_count()
            print(f"   Total users: {stats.get('total', 0)}")
            print(f"   Enabled: {stats.get('enabled', 0)}")
            print(f"   Disabled: {stats.get('disabled', 0)}")
            print(f"   Administrators: {stats.get('administrators', 0)}")
        except Exception as e:
            print(f"   ❌ Statistics failed: {e}")

        print("\n5. Listing administrators...")
        try:
            admins = g.win_list_administrators()
            print(f"   Found {len(admins)} administrators:")
            for admin in admins:
                print(f"     - {admin}")
        except Exception as e:
            print(f"   ❌ Admin listing failed: {e}")

        print("\n6. Checking SAM hive directly...")
        # Try to find SAM hive manually
        mountpoints = g.inspect_get_mountpoints(root)
        print(f"   Mountpoints: {mountpoints}")

        if mountpoints:
            # Mount root
            try:
                for mp, dev in mountpoints.items():
                    if mp == "/":
                        print(f"   Mounting {dev} at /...")
                        g.mount_ro(dev, mp)
                        break

                # Check for SAM hive
                sam_paths = [
                    "/Windows/System32/config/SAM",
                    "/Windows/System32/config/sam",
                    "/windows/system32/config/SAM",
                    "/windows/system32/config/sam",
                ]

                for sam_path in sam_paths:
                    if g.exists(sam_path):
                        print(f"   ✓ Found SAM hive at: {sam_path}")
                        break
                else:
                    print(f"   ⚠ SAM hive not found in standard locations")

                    # List config directory
                    config_paths = [
                        "/Windows/System32/config",
                        "/windows/system32/config",
                    ]
                    for config_path in config_paths:
                        if g.is_dir(config_path):
                            print(f"\n   Contents of {config_path}:")
                            try:
                                files = g.ls(config_path)
                                for f in files:
                                    print(f"     - {f}")
                            except Exception as e:
                                print(f"     Error listing: {e}")
                            break

            except Exception as e:
                print(f"   ⚠ Mount/check failed: {e}")

        print("\n✅ Test complete")
        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        try:
            g.shutdown()
        except:
            pass

if __name__ == "__main__":
    sys.exit(main())
