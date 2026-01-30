#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Demonstration of TUI integration with migration backend.

This example shows how to:
- Create migration records
- Track migration progress
- Update statistics in real-time
- Persist configuration
"""

from __future__ import annotations

import time
import logging
from datetime import datetime
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def demo_migration_tracking():
    """Demonstrate migration tracking functionality."""
    from hyper2kvm.tui.migration_tracker import (
        MigrationTracker,
        MigrationRecord,
        MigrationStatus,
        create_migration_id,
    )

    print("=" * 70)
    print("Migration Tracking Demo")
    print("=" * 70)

    # Create tracker with temporary path
    temp_path = Path("/tmp/hyper2kvm_demo_history.json")
    tracker = MigrationTracker(history_path=temp_path, logger=logger)
    tracker.load()

    print("\n1. Creating sample migrations...")

    # Create a few sample migrations
    migrations = []
    for i in range(3):
        vm_name = f"demo-vm-{i+1}"
        migration_id = create_migration_id(vm_name)

        record = MigrationRecord(
            id=migration_id,
            vm_name=vm_name,
            source_type="local",
            status=MigrationStatus.RUNNING if i < 2 else MigrationStatus.COMPLETED,
            start_time=datetime.now().isoformat(),
            progress=float(i * 30),
            size_mb=1024.0 * (i + 1),
        )

        if i == 2:  # Last one is completed
            record.end_time = datetime.now().isoformat()
            record.progress = 100.0

        migrations.append(record)
        tracker.add_migration(record)
        print(f"  - Added migration: {vm_name} (ID: {migration_id})")

    print("\n2. Retrieving active migrations...")
    active = tracker.get_active_migrations()
    print(f"  Found {len(active)} active migrations:")
    for mig in active:
        print(f"    • {mig.vm_name}: {mig.progress}% complete")

    print("\n3. Calculating statistics...")
    stats = tracker.get_statistics()
    print(f"  Total migrations: {stats['total_migrations']}")
    print(f"  Active: {stats['active_migrations']}")
    print(f"  Completed: {stats['total_completed']}")
    print(f"  Success rate: {stats['success_rate']:.1f}%")

    print("\n4. Simulating migration progress update...")
    first_mig_id = migrations[0].id
    for progress in [25, 50, 75, 100]:
        tracker.update_migration(
            first_mig_id,
            progress=float(progress)
        )
        print(f"  Progress updated to {progress}%")
        time.sleep(0.2)

    # Mark as completed
    tracker.update_migration(
        first_mig_id,
        status=MigrationStatus.COMPLETED,
        end_time=datetime.now().isoformat()
    )
    print("  Migration completed!")

    print("\n5. Final statistics...")
    final_stats = tracker.get_statistics()
    print(f"  Total migrations: {final_stats['total_migrations']}")
    print(f"  Active: {final_stats['active_migrations']}")
    print(f"  Completed: {final_stats['total_completed']}")
    print(f"  Success rate: {final_stats['success_rate']:.1f}%")

    print(f"\n✅ Migration history saved to: {temp_path}")


def demo_settings_persistence():
    """Demonstrate settings persistence functionality."""
    from hyper2kvm.tui.tui_config import (
        TUIConfig,
        get_default_settings,
        load_tui_settings,
        save_tui_settings,
    )

    print("\n" + "=" * 70)
    print("Settings Persistence Demo")
    print("=" * 70)

    # Create config with temporary path
    temp_path = Path("/tmp/hyper2kvm_demo_config.json")
    config = TUIConfig(config_path=temp_path, logger=logger)

    print("\n1. Loading default settings...")
    defaults = get_default_settings()
    print(f"  Found {len(defaults)} setting categories:")
    for category in defaults.keys():
        print(f"    • {category}")

    print("\n2. Customizing settings...")
    custom_settings = defaults.copy()
    custom_settings["general"]["log_level"] = "debug"
    custom_settings["migration"]["default_format"] = "raw"
    custom_settings["offline_fixes"]["enhanced_chroot"] = True

    print("  Modified settings:")
    print(f"    • Log level: {custom_settings['general']['log_level']}")
    print(f"    • Default format: {custom_settings['migration']['default_format']}")
    print(f"    • Enhanced chroot: {custom_settings['offline_fixes']['enhanced_chroot']}")

    print("\n3. Saving settings to file...")
    save_result = save_tui_settings(custom_settings, config_path=temp_path, logger=logger)
    if save_result:
        print(f"  ✅ Settings saved to: {temp_path}")
    else:
        print("  ❌ Failed to save settings")

    print("\n4. Loading settings from file...")
    loaded_settings = load_tui_settings(config_path=temp_path, logger=logger)

    print("  Loaded settings:")
    print(f"    • Log level: {loaded_settings['general']['log_level']}")
    print(f"    • Default format: {loaded_settings['migration']['default_format']}")
    print(f"    • Enhanced chroot: {loaded_settings['offline_fixes']['enhanced_chroot']}")

    print("\n5. Using dot notation for nested access...")
    config.settings = loaded_settings
    log_level = config.get("general.log_level")
    default_format = config.get("migration.default_format")

    print(f"  config.get('general.log_level'): {log_level}")
    print(f"  config.get('migration.default_format'): {default_format}")

    print(f"\n✅ Configuration saved to: {temp_path}")


def demo_integrated_workflow():
    """Demonstrate integrated workflow with both tracking and settings."""
    print("\n" + "=" * 70)
    print("Integrated Workflow Demo")
    print("=" * 70)

    from hyper2kvm.tui.migration_tracker import (
        MigrationTracker,
        MigrationRecord,
        MigrationStatus,
        create_migration_id,
    )
    from hyper2kvm.tui.tui_config import load_tui_settings

    # Load settings
    print("\n1. Loading TUI settings...")
    settings = load_tui_settings(config_path=Path("/tmp/hyper2kvm_demo_config.json"), logger=logger)
    output_format = settings["migration"]["default_format"]
    print(f"  Using output format: {output_format}")
    print(f"  Enhanced chroot enabled: {settings['offline_fixes']['enhanced_chroot']}")

    # Initialize tracker
    print("\n2. Initializing migration tracker...")
    tracker = MigrationTracker(
        history_path=Path("/tmp/hyper2kvm_demo_history.json"),
        logger=logger
    )
    tracker.load()

    # Simulate new migration
    print("\n3. Starting new migration with loaded settings...")
    vm_name = "production-db-server"
    migration_id = create_migration_id(vm_name)

    record = MigrationRecord(
        id=migration_id,
        vm_name=vm_name,
        source_type="vsphere",
        status=MigrationStatus.RUNNING,
        start_time=datetime.now().isoformat(),
        progress=0.0,
        output_path=f"/tmp/output/{vm_name}.{output_format}",
        size_mb=10240.0,
        metadata={
            "format": output_format,
            "enhanced_chroot": settings["offline_fixes"]["enhanced_chroot"],
            "compression": settings["migration"]["enable_compression"],
        }
    )

    tracker.add_migration(record)
    print(f"  Migration started: {vm_name}")
    print(f"  Output format: {output_format}")
    print(f"  Output path: {record.output_path}")

    # Simulate progress
    print("\n4. Simulating migration progress...")
    stages = [
        ("Converting disk format", 25),
        ("Applying offline fixes", 50),
        ("Regenerating initramfs", 75),
        ("Finalizing", 100),
    ]

    for stage_name, progress in stages:
        print(f"  {stage_name}... {progress}%")
        tracker.update_migration(migration_id, progress=float(progress))
        time.sleep(0.3)

    tracker.update_migration(
        migration_id,
        status=MigrationStatus.COMPLETED,
        end_time=datetime.now().isoformat()
    )
    print("  ✅ Migration completed successfully!")

    # Show final statistics
    print("\n5. Final statistics...")
    stats = tracker.get_statistics()
    print(f"  Total migrations: {stats['total_migrations']}")
    print(f"  Completed today: {stats['completed_today']}")
    print(f"  Success rate: {stats['success_rate']:.1f}%")


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print(" hyper2kvm TUI Backend Integration Demo")
    print("=" * 70)
    print("\nThis demo shows the TUI backend components in action:")
    print("  • Migration tracking and history")
    print("  • Settings persistence and loading")
    print("  • Integrated workflow example")
    print()

    try:
        # Run individual demos
        demo_migration_tracking()
        time.sleep(1)

        demo_settings_persistence()
        time.sleep(1)

        demo_integrated_workflow()

        print("\n" + "=" * 70)
        print("✅ All demos completed successfully!")
        print("=" * 70)
        print("\nGenerated files:")
        print("  • /tmp/hyper2kvm_demo_history.json - Migration tracking data")
        print("  • /tmp/hyper2kvm_demo_config.json - TUI configuration")
        print("\nYou can inspect these files to see the JSON structure.")
        print()

    except Exception as e:
        logger.exception("Demo failed")
        print(f"\n❌ Demo failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
