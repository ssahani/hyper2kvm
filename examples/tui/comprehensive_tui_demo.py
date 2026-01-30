#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
# examples/tui/comprehensive_tui_demo.py
"""
Comprehensive demo of the hyper2kvm TUI management interface.

This example demonstrates:
1. How to launch the TUI programmatically
2. How to integrate with existing migration backend
3. How to customize the TUI components
4. How to handle TUI events and callbacks

Prerequisites:
    pip install 'hyper2kvm[tui]'

Usage:
    # Launch default TUI
    python comprehensive_tui_demo.py

    # Launch with custom configuration
    python comprehensive_tui_demo.py --config /path/to/config.yaml

Features Demonstrated:
    - Main application with 6 tabbed panels
    - Migration wizard workflow
    - VM browser integration
    - Real-time migration monitoring
    - Batch migration management
    - Settings configuration
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from hyper2kvm.tui.main_app import run_hyper2kvm_tui


def main():
    """
    Launch the comprehensive TUI application.

    This demonstrates the simplest way to use the TUI - just call
    run_hyper2kvm_tui() which handles all initialization.
    """
    print("=" * 80)
    print("hyper2kvm Comprehensive TUI Demo")
    print("=" * 80)
    print()
    print("This demo launches the full hyper2kvm TUI management interface.")
    print()
    print("Features:")
    print("  🏠 Home - Welcome dashboard with migration statistics")
    print("  🧙 Wizard - 5-step interactive migration setup")
    print("  📁 Browse - Multi-source VM browser (vSphere, local, Hyper-V)")
    print("  📊 Migrations - Real-time migration monitoring")
    print("  🗂️ Batch - Batch migration management")
    print("  ⚙️ Settings - Comprehensive configuration panel")
    print()
    print("Keyboard Shortcuts:")
    print("  Ctrl+Q - Quit")
    print("  F1 - Help")
    print("  F2 - Migration Wizard")
    print("  F3 - Browse VMs")
    print("  F5 - Refresh")
    print("  Ctrl+S - Settings")
    print()
    print("=" * 80)
    print()

    # Launch the TUI
    try:
        run_hyper2kvm_tui()
    except KeyboardInterrupt:
        print("\nTUI closed by user")
    except Exception as e:
        print(f"\nError launching TUI: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def example_custom_app():
    """
    Example showing how to create a customized TUI app.

    This demonstrates how to:
    - Import individual TUI components
    - Create a custom application layout
    - Add custom panels and functionality
    """
    from hyper2kvm.core.optional_imports import (
        TEXTUAL_AVAILABLE,
        App,
        ComposeResult,
        Header,
        Footer,
        TabbedContent,
        TabPane,
    )

    if not TEXTUAL_AVAILABLE:
        raise ImportError("Textual library required for TUI")

    from hyper2kvm.tui.wizard import MigrationWizard
    from hyper2kvm.tui.vm_browser import VMBrowser
    from hyper2kvm.tui.migrations_panel import MigrationsPanel

    class CustomMigrationApp(App):
        """Custom TUI with only essential panels."""

        TITLE = "Custom Migration TUI"

        def compose(self) -> ComposeResult:
            yield Header()

            with TabbedContent():
                # Only include wizard and browser tabs
                with TabPane("Wizard", id="wizard"):
                    yield MigrationWizard()

                with TabPane("Browse", id="browser"):
                    yield VMBrowser()

                with TabPane("Monitor", id="monitor"):
                    yield MigrationsPanel()

            yield Footer()

    # Run the custom app
    app = CustomMigrationApp()
    app.run()


def example_tui_integration():
    """
    Example showing how to integrate the TUI with backend services.

    This demonstrates how to:
    - Connect TUI to existing orchestration
    - Update migration status in real-time
    - Handle migration callbacks
    - Integrate with monitoring systems
    """
    print("\nTUI Integration Example")
    print("-" * 80)
    print()
    print("To integrate the TUI with your migration backend:")
    print()
    print("1. Import TUI components:")
    print("   from hyper2kvm.tui.migrations_panel import MigrationsPanel")
    print()
    print("2. Create migration monitoring callback:")
    print("   def on_migration_update(migration_id, status, progress):")
    print("       # Update TUI display")
    print("       panel.update_migration_status(migration_id, status, progress)")
    print()
    print("3. Connect to orchestrator:")
    print("   orchestrator.on_progress(on_migration_update)")
    print()
    print("4. Launch TUI:")
    print("   app = Hyper2KVMApp()")
    print("   app.run()")
    print()
    print("See hyper2kvm/tui/*.py for component implementation details.")
    print()


def example_tui_customization():
    """
    Example showing how to customize TUI appearance and behavior.

    This demonstrates how to:
    - Modify CSS styling
    - Change color schemes
    - Add custom keyboard shortcuts
    - Create custom widgets
    """
    print("\nTUI Customization Example")
    print("-" * 80)
    print()
    print("Customize TUI appearance by modifying DEFAULT_CSS in components:")
    print()
    print("1. Change color scheme:")
    print("   class MyPanel(Container):")
    print("       DEFAULT_CSS = '''")
    print("       MyPanel {")
    print("           background: #1a1a1a;  /* Dark background */")
    print("           color: #00ff00;       /* Green text */")
    print("       }'''")
    print()
    print("2. Add custom keyboard shortcuts:")
    print("   class MyApp(App):")
    print("       BINDINGS = [")
    print("           Binding('f10', 'custom_action', 'My Action'),")
    print("       ]")
    print()
    print("3. Create custom widgets:")
    print("   class StatusWidget(Static):")
    print("       def update_status(self, status: str):")
    print("           self.update(f'Status: {status}')")
    print()
    print("See Textual documentation for more customization options:")
    print("https://textual.textualize.io/")
    print()


def print_usage():
    """Print usage information and examples."""
    print("\n" + "=" * 80)
    print("hyper2kvm TUI Usage Examples")
    print("=" * 80)
    print()
    print("1. Basic Usage:")
    print("   hyper2kvm-tui")
    print()
    print("2. With configuration file:")
    print("   hyper2kvm-tui --config /etc/hyper2kvm/config.yaml")
    print()
    print("3. Programmatic usage:")
    print("   from hyper2kvm.tui.main_app import run_hyper2kvm_tui")
    print("   run_hyper2kvm_tui()")
    print()
    print("4. Custom application:")
    print("   from hyper2kvm.tui.wizard import MigrationWizard")
    print("   # Build custom TUI with selected components")
    print()
    print("=" * 80)
    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Comprehensive demo of hyper2kvm TUI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Launch default TUI
  python comprehensive_tui_demo.py

  # Show custom app example
  python comprehensive_tui_demo.py --custom

  # Show integration examples
  python comprehensive_tui_demo.py --integration

  # Show customization examples
  python comprehensive_tui_demo.py --customization

  # Show usage guide
  python comprehensive_tui_demo.py --usage
        """
    )

    parser.add_argument(
        "--custom",
        action="store_true",
        help="Run custom TUI app example"
    )

    parser.add_argument(
        "--integration",
        action="store_true",
        help="Show TUI integration examples"
    )

    parser.add_argument(
        "--customization",
        action="store_true",
        help="Show TUI customization examples"
    )

    parser.add_argument(
        "--usage",
        action="store_true",
        help="Show usage guide"
    )

    parser.add_argument(
        "--config",
        help="Path to configuration file"
    )

    args = parser.parse_args()

    # Run requested example
    if args.custom:
        example_custom_app()
    elif args.integration:
        example_tui_integration()
    elif args.customization:
        example_tui_customization()
    elif args.usage:
        print_usage()
    else:
        # Launch default TUI
        main()
