#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Example: Integrating TUI Dashboard with Real Migrations

This example shows how to integrate the TUI dashboard with actual
VM migration operations, providing real-time monitoring.

Requirements:
    pip install 'hyper2kvm[tui,vsphere]'

Usage:
    python3 examples/tui_integration_example.py
"""

from pathlib import Path
from typing import Optional
import logging

from hyper2kvm.core.optional_imports import TEXTUAL_AVAILABLE

if not TEXTUAL_AVAILABLE:
    print("ERROR: Textual library not available!")
    print("Install with: pip install 'hyper2kvm[tui]'")
    exit(1)

from hyper2kvm.tui.dashboard import MigrationDashboard
from hyper2kvm.tui.widgets import MigrationStatus


class IntegratedMigrationDashboard(MigrationDashboard):
    """
    Dashboard integrated with actual migration orchestrator.

    This shows the pattern for integrating the TUI with real migrations.
    """

    def __init__(
        self,
        manifest_path: Optional[Path] = None,
        refresh_interval: float = 1.0,
        **kwargs,
    ):
        super().__init__(refresh_interval=refresh_interval, **kwargs)
        self.manifest_path = manifest_path

    def on_mount(self) -> None:
        """Initialize and start migrations."""
        super().on_mount()

        if self.manifest_path:
            self.log_message(f"Loading manifest: {self.manifest_path}", "INFO")
            self.start_migrations_from_manifest()
        else:
            self.log_message("No manifest provided - waiting for manual start", "INFO")

    def start_migrations_from_manifest(self) -> None:
        """
        Start migrations from manifest file.

        In a real implementation, this would:
        1. Load the manifest using ManifestProcessor
        2. Create Orchestrator instances for each VM
        3. Start migrations with progress callbacks
        4. Update the dashboard as migrations progress
        """
        self.log_message("Starting migrations from manifest...", "INFO")

        # Example integration pattern:
        # from hyper2kvm.daemon.manifest_processor import ManifestProcessor
        # from hyper2kvm.orchestrator import Orchestrator
        #
        # processor = ManifestProcessor()
        # manifest = processor._load_manifest(self.manifest_path)
        #
        # for vm_config in manifest.get('vms', [manifest]):
        #     migration = MigrationStatus(
        #         vm_name=vm_config['vm_name'],
        #         hypervisor=vm_config['hypervisor'],
        #         status='in_progress',
        #         progress=0.0,
        #         current_stage='Initializing',
        #     )
        #     self.add_migration(migration)
        #
        #     # Create orchestrator with progress callback
        #     orchestrator = Orchestrator(vm_config)
        #     orchestrator.on_progress = lambda p: self.update_migration_progress(
        #         vm_config['vm_name'], p
        #     )
        #     orchestrator.on_stage_change = lambda s: self.update_migration_stage(
        #         vm_config['vm_name'], s
        #     )
        #
        #     # Start migration (async)
        #     self.run_migration(orchestrator)

        self.log_message("Manifest processing complete", "SUCCESS")

    def on_migration_progress(
        self,
        vm_name: str,
        progress: float,
        stage: str,
        throughput_mbps: float = 0.0,
    ) -> None:
        """
        Callback for migration progress updates.

        This method should be called by the orchestrator during migration.

        Args:
            vm_name: VM being migrated
            progress: Progress (0.0 to 1.0)
            stage: Current stage
            throughput_mbps: Current throughput
        """
        self.update_migration_progress(vm_name, progress, stage, throughput_mbps)

    def on_migration_complete(self, vm_name: str, success: bool, error: Optional[str] = None) -> None:
        """
        Callback for migration completion.

        Args:
            vm_name: VM that completed
            success: Whether migration succeeded
            error: Error message if failed
        """
        if vm_name in self._migrations:
            migration = self._migrations[vm_name]
            migration.status = "completed" if success else "failed"
            migration.progress = 1.0 if success else migration.progress
            if error:
                migration.error = error

            self.add_migration(migration)

            if success:
                self.log_message(f"Migration completed successfully: {vm_name}", "SUCCESS")
            else:
                self.log_message(f"Migration failed: {vm_name} - {error}", "ERROR")


def setup_logging():
    """Setup logging to capture migration logs in TUI."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def main():
    """Run integrated dashboard."""
    setup_logging()

    print("╔════════════════════════════════════════════════════════════════╗")
    print("║     hyper2kvm TUI Dashboard - Integration Example             ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    print()
    print("This example shows how to integrate the TUI with real migrations.")
    print()
    print("Integration Pattern:")
    print("  1. Create MigrationStatus for each VM")
    print("  2. Add to dashboard using add_migration()")
    print("  3. Update progress using update_migration_progress()")
    print("  4. Set final status using on_migration_complete()")
    print()
    print("See the code comments for full integration details.")
    print()

    # Example: Load from manifest file
    manifest_path = Path("examples/manifests/batch-migration-example.yaml")

    if manifest_path.exists():
        print(f"Using manifest: {manifest_path}")
    else:
        print("Manifest not found - running in demo mode")
        manifest_path = None

    # Run dashboard
    app = IntegratedMigrationDashboard(
        manifest_path=manifest_path,
        refresh_interval=1.0,
    )
    app.run()


if __name__ == "__main__":
    main()
