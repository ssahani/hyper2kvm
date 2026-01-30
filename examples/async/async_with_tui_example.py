#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Example: Async Migrations with TUI Monitoring

Combines async parallel migrations with real-time TUI dashboard.
Shows migrations running in parallel with live progress updates.

Requirements:
    pip install 'hyper2kvm[async,tui]'

Usage:
    python3 examples/async_with_tui_example.py
"""

import asyncio
from pathlib import Path

from hyper2kvm.core.optional_imports import HTTPX_AVAILABLE, TEXTUAL_AVAILABLE, work

if not HTTPX_AVAILABLE:
    print("ERROR: httpx not available! Install with: pip install 'hyper2kvm[async]'")
    exit(1)

if not TEXTUAL_AVAILABLE:
    print("ERROR: textual not available! Install with: pip install 'hyper2kvm[tui]'")
    exit(1)

from hyper2kvm.vmware.async_client import AsyncVMwareClient, AsyncVMwareOperations
from hyper2kvm.vmware.async_client.operations import MigrationProgress
from hyper2kvm.tui.dashboard import MigrationDashboard
from hyper2kvm.tui.widgets import MigrationStatus


class AsyncMigrationDashboard(MigrationDashboard):
    """
    Dashboard that monitors async VM migrations.

    Integrates async VMware operations with real-time TUI display.
    """

    def __init__(self, vcenter_config: dict, vm_names: list, output_dir: Path, **kwargs):
        super().__init__(**kwargs)
        self.vcenter_config = vcenter_config
        self.vm_names = vm_names
        self.output_dir = output_dir

    def on_mount(self):
        """Start async migrations when dashboard mounts."""
        super().on_mount()

        self.log_message("Starting async VM migrations...", "INFO")
        self.log_message(f"vCenter: {self.vcenter_config['host']}", "INFO")
        self.log_message(f"Migrating {len(self.vm_names)} VMs in parallel", "INFO")

        # Start migrations
        self.run_async_migrations()

    @work(exclusive=False)
    async def run_async_migrations(self):
        """Run async migrations with TUI updates."""
        try:
            async with AsyncVMwareClient(**self.vcenter_config) as client:
                self.log_message(
                    f"Connected (max_concurrent={client.concurrency.limits.max_concurrent_vms})",
                    "SUCCESS",
                )

                # Create initial migration statuses
                for vm_name in self.vm_names:
                    migration = MigrationStatus(
                        vm_name=vm_name,
                        hypervisor="vmware",
                        status="pending",
                        progress=0.0,
                        current_stage="Queued",
                    )
                    self.add_migration(migration)

                # Progress callback
                def on_progress(prog: MigrationProgress):
                    if prog.vm_name in self._migrations:
                        migration = self._migrations[prog.vm_name]
                        migration.status = "in_progress"
                        migration.progress = prog.progress
                        migration.current_stage = prog.stage
                        migration.throughput_mbps = prog.throughput_mbps
                        migration.elapsed_seconds = prog.elapsed_seconds
                        self.add_migration(migration)

                # Completion callback
                def on_complete(vm_name: str, success: bool, error: str = None):
                    if vm_name in self._migrations:
                        migration = self._migrations[vm_name]
                        migration.status = "completed" if success else "failed"
                        migration.progress = 1.0 if success else migration.progress
                        if error:
                            migration.error = error
                        self.add_migration(migration)

                        if success:
                            self.log_message(f"Migration completed: {vm_name}", "SUCCESS")
                        else:
                            self.log_message(f"Migration failed: {vm_name} - {error}", "ERROR")

                # Run batch export
                ops = AsyncVMwareOperations(client)
                results = await ops.batch_export(
                    self.vm_names,
                    self.output_dir,
                    on_progress=on_progress,
                    on_complete=on_complete,
                )

                # Final summary
                self.log_message("=" * 60, "INFO")
                self.log_message("Migration Summary:", "INFO")
                self.log_message(f"  Total:     {results['total']}", "INFO")
                self.log_message(f"  Succeeded: {results['succeeded']}", "SUCCESS")
                self.log_message(f"  Failed:    {results['failed']}", "ERROR" if results['failed'] > 0 else "INFO")
                self.log_message(f"  Success:   {results['success_rate']*100:.1f}%", "INFO")
                self.log_message("=" * 60, "INFO")

        except Exception as e:
            self.log_message(f"Error in async migrations: {e}", "ERROR")


def main():
    """Run dashboard with async migrations."""
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║     Async VM Migrations with Real-Time TUI Monitoring         ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    print()
    print("This demo shows:")
    print("  • Multiple VMs migrating in parallel (async)")
    print("  • Real-time progress bars for each VM")
    print("  • Live metrics (throughput, success rate, etc.)")
    print("  • Scrolling event log")
    print()
    print("Keyboard shortcuts:")
    print("  q - Quit")
    print("  r - Refresh")
    print("  l - Focus logs")
    print("  m - Focus migrations")
    print()
    print("Starting in 3 seconds...")

    import time

    time.sleep(3)

    # Configuration
    vcenter_config = {
        "host": "vcenter.example.com",
        "username": "admin",
        "password": "secret",
        "datacenter": "DC1",
        "max_concurrent_vms": 5,
    }

    vm_names = [
        "web-server-01",
        "web-server-02",
        "web-server-03",
        "db-server-01",
        "db-server-02",
        "app-server-01",
        "app-server-02",
        "cache-server-01",
    ]

    output_dir = Path("/var/lib/hyper2kvm/output")

    # Run dashboard
    app = AsyncMigrationDashboard(
        vcenter_config=vcenter_config,
        vm_names=vm_names,
        output_dir=output_dir,
        refresh_interval=0.5,
    )
    app.run()


if __name__ == "__main__":
    main()
