#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Demo of custom orange-themed progress bars.

Shows both Rich (if available) and fallback implementations.
"""

import time
import sys
from pathlib import Path

# Add hyper2kvm to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hyper2kvm.core.progress import (
    create_progress_bar,
    SimpleProgressBar,
    ProgressBarConfig,
    Colors,
)
from hyper2kvm.core.optional_imports import RICH_AVAILABLE


def demo_simple_progress():
    """Demonstrate simple progress bar (no Rich)."""
    print("\n" + "=" * 80)
    print("Simple Progress Bar Demo (Orange Theme - No Rich Required)".center(80))
    print("=" * 80)
    print()

    # Basic progress bar
    print("1. Basic Progress Bar:")
    config = ProgressBarConfig(width=40, show_percentage=True)
    progress = SimpleProgressBar(
        total=100,
        description=f"Exporting VM",
        config=config,
    )

    for i in range(101):
        progress.update(i)
        time.sleep(0.03)

    progress.finish("Export completed!")
    print()

    # Progress bar with spinner
    print("2. Progress Bar with Spinner:")
    config = ProgressBarConfig(
        width=40,
        show_percentage=True,
        show_spinner=True,
    )
    progress = SimpleProgressBar(
        total=100,
        description="Converting disk",
        config=config,
    )

    for i in range(101):
        progress.update(i)
        time.sleep(0.03)

    progress.finish("Conversion completed!")
    print()

    # Progress bar with ETA
    print("3. Progress Bar with ETA:")
    config = ProgressBarConfig(
        width=40,
        show_percentage=True,
        show_spinner=True,
        show_eta=True,
    )
    progress = SimpleProgressBar(
        total=100,
        description="Transferring data",
        config=config,
    )

    for i in range(101):
        progress.update(i)
        time.sleep(0.05)

    progress.finish("Transfer completed!")
    print()

    # Custom characters
    print("4. Custom Characters:")
    config = ProgressBarConfig(
        width=30,
        filled_char="=",
        empty_char=" ",
        left_bracket="[",
        right_bracket="]",
        show_percentage=True,
    )
    progress = SimpleProgressBar(
        total=100,
        description="Validating VM",
        config=config,
    )

    for i in range(101):
        progress.update(i)
        time.sleep(0.02)

    progress.finish("Validation completed!")
    print()


def demo_progress_manager():
    """Demonstrate progress manager (auto-detects Rich)."""
    print("\n" + "=" * 80)
    if RICH_AVAILABLE:
        print("Progress Manager Demo (Using Rich)".center(80))
    else:
        print("Progress Manager Demo (Using Simple Progress)".center(80))
    print("=" * 80)
    print()

    # Example 1: VM Migration
    print("Simulating VM Migration Pipeline:")
    print()

    stages = [
        ("Exporting VM from source", 25),
        ("Transferring disk image", 50),
        ("Converting to QCOW2", 15),
        ("Validating image", 10),
    ]

    total_steps = sum(steps for _, steps in stages)
    current = 0

    with create_progress_bar("VM Migration", total=total_steps) as progress:
        for stage_name, steps in stages:
            for step in range(steps):
                current += 1
                progress.update(current, description=stage_name)
                time.sleep(0.05)

    print()

    # Example 2: Batch Migration
    print("Simulating Batch Migration:")
    print()

    vms = ["web-server-01", "database-server", "app-server-03"]

    with create_progress_bar("Batch Migration", total=len(vms) * 100) as progress:
        for idx, vm_name in enumerate(vms):
            for i in range(100):
                progress.update(
                    idx * 100 + i + 1,
                    description=f"Migrating {vm_name}",
                )
                time.sleep(0.02)

    print()


def demo_color_palette():
    """Show the orange theme color palette."""
    print("\n" + "=" * 80)
    print("Orange Theme Color Palette".center(80))
    print("=" * 80)
    print()

    if Colors.supports_color():
        colors = [
            ("BRIGHT_ORANGE", Colors.BRIGHT_ORANGE, "Headers and progress bars"),
            ("GOLD_ORANGE", Colors.GOLD_ORANGE, "Brackets and accents"),
            ("LIGHT_ORANGE", Colors.LIGHT_ORANGE, "Descriptions"),
            ("DARK_ORANGE", Colors.DARK_ORANGE, "Secondary elements"),
            ("SUCCESS_GREEN", Colors.SUCCESS_GREEN, "Completion messages"),
            ("ERROR_RED", Colors.ERROR_RED, "Error messages"),
            ("WARNING_YELLOW", Colors.WARNING_YELLOW, "Warnings"),
        ]

        for name, color_code, usage in colors:
            print(f"{color_code}█████{Colors.RESET} {name:20} - {usage}")
    else:
        print("Terminal does not support ANSI colors")

    print()


def demo_multi_stage():
    """Demonstrate multi-stage migration with progress."""
    print("\n" + "=" * 80)
    print("Multi-Stage Migration Demo".center(80))
    print("=" * 80)
    print()

    stages = [
        ("🔍 Validating source VM", 10),
        ("📤 Exporting VM configuration", 5),
        ("💾 Exporting disk images", 40),
        ("🔄 Transferring to destination", 30),
        ("🔧 Converting disk format", 20),
        ("✅ Validating destination VM", 10),
        ("🚀 Starting VM", 5),
    ]

    total = sum(s[1] for s in stages)
    current = 0

    print(f"Migrating VM: web-server-01")
    print()

    for stage_name, steps in stages:
        config = ProgressBarConfig(
            width=50,
            show_percentage=True,
            show_spinner=True,
        )

        progress = SimpleProgressBar(
            total=steps,
            description=stage_name,
            config=config,
        )

        for i in range(steps + 1):
            progress.update(i)
            time.sleep(0.1)

        progress.finish()

    print()
    if Colors.supports_color():
        print(f"{Colors.SUCCESS_GREEN}✓ Migration completed successfully!{Colors.RESET}")
    else:
        print("✓ Migration completed successfully!")
    print()


def main():
    """Run all demos."""
    print("=" * 80)
    print("hyper2kvm Progress Bar Demos - Orange Theme".center(80))
    print("=" * 80)

    # Show which implementation is being used
    if RICH_AVAILABLE:
        print("\n✨ Rich library detected - will show both Rich and Simple demos")
    else:
        print("\n📦 Rich not available - using Simple progress bars")
        print("   Install Rich for enhanced experience: pip install rich")

    try:
        # Demo simple progress bars
        demo_simple_progress()

        # Demo progress manager
        demo_progress_manager()

        # Demo color palette
        demo_color_palette()

        # Demo multi-stage migration
        demo_multi_stage()

        print("=" * 80)
        print("Demo completed!".center(80))
        print("=" * 80)

    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")


if __name__ == "__main__":
    main()
