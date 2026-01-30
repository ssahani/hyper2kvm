#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Quick launcher for hyper2kvm TUI dashboard.

Usage:
    python run_tui.py                 # Auto-detect best TUI
    python run_tui.py --demo          # Run with simulated migrations
    python run_tui.py --type textual  # Force specific dashboard type
    python run_tui.py --help          # Show help
"""

import sys
import argparse
import time
import random
import threading
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from hyper2kvm.tui import run_dashboard, get_dashboard_type
from hyper2kvm.tui.types import MigrationStatus


def simulate_migrations(dashboard, num_vms=4):
    """Simulate VM migrations for demo."""
    hypervisors = ["vmware", "hyperv", "azure", "aws"]
    vms = [f"vm-{i:02d}" for i in range(1, num_vms + 1)]

    migrations = {}

    # Create initial migrations
    for i, vm_name in enumerate(vms):
        migration = MigrationStatus(
            vm_name=vm_name,
            hypervisor=hypervisors[i % len(hypervisors)],
            status="pending",
            progress=0.0,
            current_stage="initializing",
        )
        migrations[vm_name] = migration
        dashboard.add_migration(migration)
        dashboard.log_message(f"Started migration for {vm_name}", "INFO")
        time.sleep(0.5)

    # Simulate progress through stages
    stages = ["export", "transfer", "convert", "validate", "complete"]

    for stage_idx, stage in enumerate(stages):
        for vm_name in list(migrations.keys()):
            migration = migrations[vm_name]

            if migration.status == "failed":
                continue

            # Randomly fail some migrations (5% chance)
            if random.random() < 0.05:
                migration.status = "failed"
                migration.error = f"Error during {stage}"
                dashboard.add_migration(migration)
                dashboard.log_message(f"{vm_name} failed during {stage}", "ERROR")
                continue

            # Update progress
            migration.current_stage = stage
            migration.progress = (stage_idx + 1) / len(stages)
            migration.throughput_mbps = random.uniform(50, 200)
            migration.elapsed_seconds += random.uniform(5, 15)

            if stage == "complete":
                migration.status = "completed"
                migration.progress = 1.0
                migration.eta_seconds = 0
                dashboard.log_message(f"{vm_name} completed successfully!", "SUCCESS")
            else:
                migration.status = "in_progress"
                remaining_stages = len(stages) - stage_idx - 1
                migration.eta_seconds = remaining_stages * 10

            dashboard.add_migration(migration)
            time.sleep(0.3)

    dashboard.log_message("All migrations finished!", "SUCCESS")


def main():
    parser = argparse.ArgumentParser(
        description="Run hyper2kvm TUI dashboard with orange theme",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    Run empty dashboard (auto-detect best TUI)
  %(prog)s --demo             Run with simulated migrations
  %(prog)s --demo --vms 10    Run demo with 10 VMs
  %(prog)s --type textual     Force Textual dashboard
  %(prog)s --type curses      Force curses dashboard
  %(prog)s --type cli         Force CLI dashboard
  %(prog)s --interval 2       Set refresh interval to 2 seconds

Dashboard types (in order of preference):
  textual - Full-featured TUI (requires: pip install 'hyper2kvm[tui]')
  curses  - Built-in TUI (works on Unix/Linux/Mac)
  cli     - Simple output (works everywhere including Windows)
        """
    )

    parser.add_argument(
        '--demo',
        action='store_true',
        help='Run with simulated VM migrations'
    )

    parser.add_argument(
        '--vms',
        type=int,
        default=4,
        help='Number of VMs to simulate (default: 4, only with --demo)'
    )

    parser.add_argument(
        '--type',
        choices=['textual', 'curses', 'cli', 'auto'],
        default='auto',
        help='Dashboard type to use (default: auto-detect)'
    )

    parser.add_argument(
        '--interval',
        type=float,
        default=1.0,
        help='Refresh interval in seconds (default: 1.0)'
    )

    args = parser.parse_args()

    # Print banner
    print("=" * 80)
    print("hyper2kvm TUI Dashboard (Orange Theme)".center(80))
    print("=" * 80)
    print()

    # Detect or use specified dashboard type
    if args.type == 'auto':
        dashboard_type = get_dashboard_type()
        print(f"Auto-detected dashboard: {dashboard_type}")
    else:
        dashboard_type = args.type
        print(f"Using dashboard: {dashboard_type}")

    # Show keyboard shortcuts
    if dashboard_type == 'textual':
        print("\n✨ Textual Dashboard - Full Featured TUI")
        print("Keyboard shortcuts:")
        print("  q - Quit  |  r - Refresh  |  l - Focus logs  |  m - Focus migrations")
    elif dashboard_type == 'curses':
        print("\n🎨 Curses Dashboard - Built-in TUI")
        print("Keyboard shortcuts:")
        print("  q - Quit  |  r - Refresh  |  ↑/↓ - Scroll logs")
    else:
        print("\n📟 CLI Dashboard - Simple Terminal Output")
        print("Press Ctrl+C to quit")

    print()

    if args.demo:
        print(f"Demo mode: Simulating {args.vms} VM migrations...")
        print()
    else:
        print("Interactive mode: Dashboard is empty. Use API to add migrations.")
        print("See RUN_TUI.md for examples.")
        print()

    # Create dashboard instance based on type
    if dashboard_type == 'textual':
        try:
            from hyper2kvm.tui.dashboard import MigrationDashboard

            if args.demo:
                print("Note: Demo mode not fully supported with Textual.")
                print("The dashboard will start empty. Check examples/tui_dashboard_example.py")
                print("for Textual-specific demo with background workers.")
                print()

            time.sleep(2)
            dashboard = MigrationDashboard(refresh_interval=args.interval)
            dashboard.run()

        except ImportError:
            print("\n❌ Error: Textual not installed!")
            print("Install with: pip install 'hyper2kvm[tui]'")
            print("Falling back to curses...")
            dashboard_type = 'curses'

    if dashboard_type == 'curses':
        try:
            from hyper2kvm.tui.fallback_dashboard import CursesDashboard

            dashboard = CursesDashboard(refresh_interval=args.interval)

            if args.demo:
                print("Starting demo in 2 seconds...")
                time.sleep(2)

                # Start simulation thread
                sim_thread = threading.Thread(
                    target=simulate_migrations,
                    args=(dashboard, args.vms),
                    daemon=True
                )
                sim_thread.start()

            # Run dashboard (blocking)
            dashboard.run()

        except ImportError:
            print("\n❌ Error: curses not available!")
            print("On Windows, install: pip install windows-curses")
            print("Falling back to CLI...")
            dashboard_type = 'cli'

    if dashboard_type == 'cli':
        from hyper2kvm.tui.cli_dashboard import CLIDashboard

        dashboard = CLIDashboard(refresh_interval=args.interval)

        if args.demo:
            print("Starting demo in 2 seconds...")
            time.sleep(2)

            # Start simulation thread
            sim_thread = threading.Thread(
                target=simulate_migrations,
                args=(dashboard, args.vms),
                daemon=True
            )
            sim_thread.start()

        # Run dashboard (blocking)
        dashboard.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDashboard stopped.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
