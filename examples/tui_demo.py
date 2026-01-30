#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Demo script for hyper2kvm TUI dashboard with orange theme.

This demonstrates the automatic fallback system:
1. Textual (if installed) - Full-featured modern TUI
2. Curses (if available) - Basic TUI using stdlib
3. CLI (always works) - Simple terminal output

Usage:
    python examples/tui_demo.py
"""

import time
import random
import threading
from pathlib import Path
import sys

# Add hyper2kvm to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hyper2kvm.tui import run_dashboard, get_dashboard_type
from hyper2kvm.tui.widgets import MigrationStatus


def simulate_migrations(dashboard):
    """
    Simulate some VM migrations for demo purposes.

    Args:
        dashboard: Dashboard instance to update
    """
    vms = [
        ("web-server-01", "vmware"),
        ("database-server", "vmware"),
        ("app-server-03", "azure"),
        ("backup-server", "hyperv"),
    ]

    migrations = {}

    # Create initial migrations
    for vm_name, hypervisor in vms:
        migration = MigrationStatus(
            vm_name=vm_name,
            hypervisor=hypervisor,
            status="pending",
            progress=0.0,
            current_stage="initializing",
        )
        migrations[vm_name] = migration
        dashboard.add_migration(migration)
        time.sleep(0.5)

    # Simulate progress
    stages = ["export", "transfer", "convert", "validate", "complete"]

    for stage_idx, stage in enumerate(stages):
        for vm_name in list(migrations.keys()):
            migration = migrations[vm_name]

            if migration.status == "failed":
                continue

            # Randomly fail some migrations
            if random.random() < 0.05:  # 5% chance of failure
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
                dashboard.log_message(f"{vm_name} completed successfully!", "SUCCESS")
            else:
                migration.status = "in_progress"

            dashboard.add_migration(migration)
            time.sleep(0.3)

    dashboard.log_message("All migrations finished!", "SUCCESS")


def main():
    """Run the TUI demo."""
    print("=" * 80)
    print("hyper2kvm TUI Dashboard Demo (Orange Theme)".center(80))
    print("=" * 80)
    print()

    dashboard_type = get_dashboard_type()
    print(f"Dashboard type: {dashboard_type}")

    if dashboard_type == "textual":
        print("Using Textual dashboard - Full featured TUI with orange theme")
        print("\nKeyboard shortcuts:")
        print("  q - Quit")
        print("  r - Refresh")
        print("  l - Focus logs")
        print("  m - Focus migrations")
        print("  d - Toggle dark mode")
    elif dashboard_type == "curses":
        print("Using curses dashboard - Basic TUI (Textual not installed)")
        print("\nKeyboard shortcuts:")
        print("  q - Quit")
        print("  r - Refresh")
        print("  UP/DOWN - Scroll logs")
    else:
        print("Using CLI dashboard - Simple output (curses not available)")
        print("\nPress Ctrl+C to quit")

    print()
    print("Starting demo in 3 seconds...")
    print("This will simulate several VM migrations with progress updates.")
    print()
    time.sleep(3)

    # Note: For demo purposes, we can't easily run the simulation with Textual
    # because Textual's run() is blocking. In a real application, you'd use
    # Textual's @work decorator or background workers.

    if dashboard_type == "textual":
        print("\nNote: This demo works best with curses or CLI dashboard.")
        print("For Textual demo, check examples/tui_dashboard_example.py")
        print("\nFor now, showing a basic Textual dashboard...")
        from hyper2kvm.tui.dashboard import run_dashboard as run_textual
        run_textual()
    else:
        # For curses and CLI, we can run in a thread
        if dashboard_type == "curses":
            from hyper2kvm.tui.fallback_dashboard import CursesDashboard
            dashboard = CursesDashboard(refresh_interval=1.0)

            # Start simulation thread
            sim_thread = threading.Thread(
                target=simulate_migrations,
                args=(dashboard,),
                daemon=True
            )
            sim_thread.start()

            # Run dashboard (blocking)
            dashboard.run()
        else:
            from hyper2kvm.tui.cli_dashboard import CLIDashboard
            dashboard = CLIDashboard(refresh_interval=2.0)

            # Start simulation thread
            sim_thread = threading.Thread(
                target=simulate_migrations,
                args=(dashboard,),
                daemon=True
            )
            sim_thread.start()

            # Run dashboard (blocking)
            dashboard.run()


if __name__ == "__main__":
    main()
