#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Example: Real-Time TUI Dashboard for VM Migrations

This example demonstrates the interactive Terminal User Interface (TUI)
for monitoring VM migrations in real-time.

Features:
- Live migration status with progress bars
- Real-time metrics display (throughput, success rate, etc.)
- Scrolling log viewer
- Keyboard shortcuts for navigation

Requirements:
    pip install 'hyper2kvm[tui]'

Usage:
    python3 examples/tui_dashboard_example.py

Keyboard Shortcuts:
    q - Quit application
    r - Refresh display
    l - Focus log viewer
    m - Focus migrations panel
    d - Toggle dark mode
"""

import asyncio
import random
import time
from pathlib import Path

from hyper2kvm.core.optional_imports import TEXTUAL_AVAILABLE, work

if not TEXTUAL_AVAILABLE:
    print("ERROR: Textual library not available!")
    print("Install with: pip install 'hyper2kvm[tui]'")
    exit(1)

from hyper2kvm.tui.dashboard import MigrationDashboard
from hyper2kvm.tui.widgets import MigrationStatus


class DemoMigrationDashboard(MigrationDashboard):
    """Demo dashboard with simulated migrations."""

    def on_mount(self) -> None:
        """Start demo when mounted."""
        super().on_mount()

        # Start simulating migrations
        self.log_message("Starting demo migrations...", "INFO")
        self.simulate_migrations()

    @work(exclusive=False)
    async def simulate_migrations(self) -> None:
        """Simulate several VM migrations running in parallel."""

        # Define VMs to migrate
        vms = [
            ("web-server-01", "vmware"),
            ("web-server-02", "vmware"),
            ("db-server-01", "vmware"),
            ("app-server-01", "vmware"),
            ("cache-server-01", "vmware"),
        ]

        # Start all migrations
        tasks = []
        for vm_name, hypervisor in vms:
            task = asyncio.create_task(self._simulate_single_migration(vm_name, hypervisor))
            tasks.append(task)

        # Wait for all to complete
        await asyncio.gather(*tasks)

        self.log_message("All demo migrations completed!", "SUCCESS")

    async def _simulate_single_migration(self, vm_name: str, hypervisor: str) -> None:
        """
        Simulate a single VM migration with realistic progress.

        Args:
            vm_name: Name of VM
            hypervisor: Source hypervisor type
        """
        # Random initial delay
        await asyncio.sleep(random.uniform(0, 2))

        # Create migration status
        migration = MigrationStatus(
            vm_name=vm_name,
            hypervisor=hypervisor,
            status="in_progress",
            progress=0.0,
            current_stage="Initializing",
        )

        self.add_migration(migration)
        self.log_message(f"Started migration: {vm_name}", "INFO")

        # Stages of migration
        stages = [
            ("Connecting to hypervisor", 0.05, 2.0),
            ("Exporting VM metadata", 0.10, 3.0),
            ("Exporting disk 1/2", 0.40, 15.0),
            ("Exporting disk 2/2", 0.70, 12.0),
            ("Converting disk format", 0.85, 8.0),
            ("Validating conversion", 0.95, 5.0),
            ("Finalizing", 1.0, 2.0),
        ]

        try:
            for stage_name, target_progress, duration in stages:
                migration.current_stage = stage_name

                # Simulate progress through this stage
                start_progress = migration.progress
                steps = 20
                for i in range(steps):
                    await asyncio.sleep(duration / steps)

                    # Calculate progress
                    step_progress = (target_progress - start_progress) * (i + 1) / steps
                    migration.progress = start_progress + step_progress

                    # Simulate throughput (varies during migration)
                    if "disk" in stage_name.lower():
                        migration.throughput_mbps = random.uniform(80, 150)
                    else:
                        migration.throughput_mbps = random.uniform(10, 30)

                    # Update elapsed time
                    migration.elapsed_seconds += duration / steps

                    # Calculate ETA
                    if migration.progress > 0.1:
                        remaining_progress = 1.0 - migration.progress
                        rate = migration.progress / migration.elapsed_seconds
                        migration.eta_seconds = remaining_progress / rate if rate > 0 else None

                    # Update widget
                    self.add_migration(migration)

            # Occasionally fail a migration (20% chance)
            if random.random() < 0.2:
                migration.status = "failed"
                migration.error = "Network connection lost during export"
                self.log_message(f"Migration failed: {vm_name} - {migration.error}", "ERROR")
            else:
                migration.status = "completed"
                migration.progress = 1.0
                self.log_message(f"Migration completed: {vm_name}", "SUCCESS")

            self.add_migration(migration)

        except Exception as e:
            migration.status = "failed"
            migration.error = str(e)
            self.add_migration(migration)
            self.log_message(f"Migration error: {vm_name} - {e}", "ERROR")


def main():
    """Run demo dashboard."""
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║        hyper2kvm Real-Time Migration Dashboard (Demo)         ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    print()
    print("This demo simulates 5 VM migrations running in parallel.")
    print("Watch the progress bars, metrics, and logs update in real-time!")
    print()
    print("Keyboard shortcuts:")
    print("  q - Quit")
    print("  r - Refresh")
    print("  l - Focus logs")
    print("  m - Focus migrations")
    print("  d - Toggle dark mode")
    print()
    print("Starting in 3 seconds...")
    time.sleep(3)

    # Run dashboard with dark mode enabled
    app = DemoMigrationDashboard(refresh_interval=0.5)
    app.dark = True  # Enable dark mode for cool orange/dark theme
    app.run()


if __name__ == "__main__":
    main()
