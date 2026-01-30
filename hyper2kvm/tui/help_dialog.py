# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/help_dialog.py
"""
Help dialog and documentation viewer for the TUI.
"""

from __future__ import annotations

from typing import Dict, List

from ..core.optional_imports import (
    TEXTUAL_AVAILABLE,
    ComposeResult,
    Static,
    Container,
    Vertical,
    Horizontal,
    Button,
    Screen,
)

if not TEXTUAL_AVAILABLE:
    raise ImportError("Textual required")


class HelpDialog(Screen):
    """
    Modal help dialog displaying keyboard shortcuts and usage information.

    Features:
    - Keyboard shortcuts reference
    - Panel-specific help
    - Feature overview
    - Quick tips
    """

    DEFAULT_CSS = """
    HelpDialog {
        align: center middle;
    }

    .help-container {
        width: 80;
        height: 35;
        border: heavy #DE7356;  /* Coral brand color */
        background: $surface;
    }

    .help-header {
        height: 3;
        background: #DE7356;  /* Coral brand color */
        color: white;
        padding: 1 2;
        text-style: bold;
        content-align: center middle;
    }

    .help-body {
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }

    .help-footer {
        height: 3;
        background: $surface-darken-1;
        padding: 0 2;
        content-align: center middle;
    }

    .section-title {
        text-style: bold;
        color: #DE7356;  /* Coral brand color */
        margin: 1 0 0 0;
    }

    .shortcut-row {
        layout: horizontal;
        height: auto;
        margin: 0 0 0 2;
    }

    .shortcut-key {
        width: 15;
        text-style: bold;
        color: #F5B5A3;  /* Light coral */
    }

    .shortcut-desc {
        width: 1fr;
    }

    .tip-box {
        border: solid #F5B5A3;  /* Light coral */
        background: $surface-darken-2;
        padding: 1 2;
        margin: 1 0;
    }
    """

    def __init__(self, topic: str = "general"):
        """
        Initialize help dialog.

        Args:
            topic: Help topic to display (general, wizard, browser, migrations, etc.)
        """
        super().__init__()
        self.topic = topic

    def compose(self) -> ComposeResult:
        """Compose the help dialog."""
        with Container(classes="help-container"):
            # Header
            with Container(classes="help-header"):
                yield Static("📖 hyper2kvm TUI - Help & Documentation")

            # Body with help content
            with Vertical(classes="help-body"):
                yield from self.compose_help_content()

            # Footer with close button
            with Container(classes="help-footer"):
                yield Button("Close (ESC)", id="btn_close_help", variant="primary")

    def compose_help_content(self) -> ComposeResult:
        """Compose help content based on topic."""
        if self.topic == "general":
            yield from self.compose_general_help()
        elif self.topic == "wizard":
            yield from self.compose_wizard_help()
        elif self.topic == "browser":
            yield from self.compose_browser_help()
        elif self.topic == "migrations":
            yield from self.compose_migrations_help()
        elif self.topic == "batch":
            yield from self.compose_batch_help()
        elif self.topic == "settings":
            yield from self.compose_settings_help()
        else:
            yield from self.compose_general_help()

    def compose_general_help(self) -> ComposeResult:
        """General help content."""
        yield Static("🔑 Keyboard Shortcuts", classes="section-title")

        shortcuts = [
            ("Ctrl+Q", "Quit application"),
            ("F1", "Show this help dialog"),
            ("F2", "Open migration wizard"),
            ("F3", "Browse VMs"),
            ("F5", "Refresh current view"),
            ("Ctrl+S", "Open settings"),
            ("Tab", "Switch between panels"),
            ("ESC", "Close dialogs / Cancel"),
        ]

        for key, desc in shortcuts:
            with Horizontal(classes="shortcut-row"):
                yield Static(key, classes="shortcut-key")
                yield Static(desc, classes="shortcut-desc")

        yield Static("\n🏠 Navigation", classes="section-title")
        yield Static("Use the tabbed interface to switch between panels:")
        yield Static("  • Home - Dashboard with statistics")
        yield Static("  • Wizard - Step-by-step migration setup")
        yield Static("  • Browse - VM discovery and selection")
        yield Static("  • Migrations - Active migration monitoring")
        yield Static("  • Batch - Batch migration management")
        yield Static("  • Settings - Configuration preferences")

        yield Static("\n💡 Quick Tips", classes="section-title")
        with Container(classes="tip-box"):
            yield Static(
                "Start with F2 to launch the migration wizard for guided setup, "
                "or use F3 to browse and select VMs manually."
            )

    def compose_wizard_help(self) -> ComposeResult:
        """Migration wizard help."""
        yield Static("🧙 Migration Wizard", classes="section-title")
        yield Static("\nThe wizard guides you through 5 steps:")

        steps = [
            ("1. Source Selection", "Choose vSphere, local VMDK, Hyper-V, or OVA"),
            ("2. VM/File Selection", "Browse and select VMs or disk images"),
            ("3. Output Configuration", "Set format (QCOW2/RAW/VDI), location, compression"),
            ("4. Offline Fixes", "Configure fstab, initramfs, GRUB, network fixes"),
            ("5. Review & Start", "Confirm settings and launch migration"),
        ]

        for step, desc in steps:
            yield Static(f"  {step}")
            yield Static(f"    {desc}")

        yield Static("\n⌨️ Wizard Controls", classes="section-title")
        with Horizontal(classes="shortcut-row"):
            yield Static("Back", classes="shortcut-key")
            yield Static("Return to previous step", classes="shortcut-desc")

        with Horizontal(classes="shortcut-row"):
            yield Static("Next", classes="shortcut-key")
            yield Static("Advance to next step", classes="shortcut-desc")

        with Horizontal(classes="shortcut-row"):
            yield Static("Start", classes="shortcut-key")
            yield Static("Begin migration (final step)", classes="shortcut-desc")

    def compose_browser_help(self) -> ComposeResult:
        """VM browser help."""
        yield Static("📁 VM Browser", classes="section-title")
        yield Static("\nBrowse and select VMs from various sources:")

        yield Static("\n☁️ vSphere Source", classes="section-title")
        yield Static("  1. Enter vCenter server hostname")
        yield Static("  2. Provide credentials")
        yield Static("  3. Browse datacenter hierarchy")
        yield Static("  4. Select VMs for migration")

        yield Static("\n💾 Local Source", classes="section-title")
        yield Static("  1. Specify base directory")
        yield Static("  2. Browse for VMDK files")
        yield Static("  3. Select disk images")

        yield Static("\n🎯 Selection", classes="section-title")
        yield Static("  • Click rows to toggle selection")
        yield Static("  • Use filters to narrow results")
        yield Static("  • View total size at bottom")
        yield Static("  • Click 'Migrate Selected' to proceed")

    def compose_migrations_help(self) -> ComposeResult:
        """Active migrations panel help."""
        yield Static("📊 Active Migrations", classes="section-title")
        yield Static("\nMonitor ongoing migrations in real-time:")

        yield Static("\n📈 Information Displayed", classes="section-title")
        yield Static("  • VM Name - Source VM being migrated")
        yield Static("  • Status - Current state (running/paused)")
        yield Static("  • Progress - Completion percentage")
        yield Static("  • Stage - Current operation (convert/validate/transfer)")
        yield Static("  • Throughput - Data transfer rate (MB/s)")
        yield Static("  • ETA - Estimated time remaining")
        yield Static("  • Started - Migration start time")

        yield Static("\n🎮 Controls", classes="section-title")
        with Horizontal(classes="shortcut-row"):
            yield Static("Pause", classes="shortcut-key")
            yield Static("Temporarily pause selected migration", classes="shortcut-desc")

        with Horizontal(classes="shortcut-row"):
            yield Static("Resume", classes="shortcut-key")
            yield Static("Resume paused migration", classes="shortcut-desc")

        with Horizontal(classes="shortcut-row"):
            yield Static("Cancel", classes="shortcut-key")
            yield Static("Stop and cancel migration", classes="shortcut-desc")

        with Horizontal(classes="shortcut-row"):
            yield Static("Details", classes="shortcut-key")
            yield Static("View detailed logs and information", classes="shortcut-desc")

    def compose_batch_help(self) -> ComposeResult:
        """Batch manager help."""
        yield Static("🗂️ Batch Migration Manager", classes="section-title")
        yield Static("\nManage multiple migrations as a batch:")

        yield Static("\n📋 Features", classes="section-title")
        yield Static("  • Queue multiple migrations for sequential execution")
        yield Static("  • Parallel migration support (configurable)")
        yield Static("  • Aggregate statistics and reporting")
        yield Static("  • Retry failed migrations")
        yield Static("  • Export batch reports")

        yield Static("\n📊 Statistics", classes="section-title")
        yield Static("  • Active - Currently running migrations")
        yield Static("  • Queued - Waiting to start")
        yield Static("  • Completed - Successfully finished")
        yield Static("  • Failed - Errors encountered")
        yield Static("  • Total - All migrations in batch")

    def compose_settings_help(self) -> ComposeResult:
        """Settings panel help."""
        yield Static("⚙️ Settings", classes="section-title")
        yield Static("\nConfigure hyper2kvm defaults and preferences:")

        categories = [
            ("General", "Output directory, logging level, log file location"),
            ("Migration", "Default format, compression, parallelism, skip existing"),
            ("vSphere", "Default vCenter host, username, SSL verification"),
            ("Offline Fixes", "fstab mode, initramfs, GRUB, network, enhanced chroot"),
            ("Performance", "Max concurrent operations, timeouts"),
            ("Advanced", "GuestFS backend (VMCraft/libguestfs), debug mode"),
        ]

        for category, desc in categories:
            yield Static(f"\n📌 {category}", classes="section-title")
            yield Static(f"  {desc}")

        yield Static("\n💾 Persistence", classes="section-title")
        with Container(classes="tip-box"):
            yield Static(
                "Settings are automatically saved to ~/.config/hyper2kvm/tui.json "
                "and loaded on startup. Click 'Save Settings' to persist changes."
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn_close_help":
            self.app.pop_screen()

    def on_key(self, event) -> None:
        """Handle key presses."""
        if event.key == "escape":
            self.app.pop_screen()
