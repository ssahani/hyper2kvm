#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/main_app.py
"""
Main TUI application for hyper2kvm - Comprehensive VM migration management interface.

Features:
- Interactive migration wizard
- VM browser (vSphere, local, Hyper-V)
- Live migration dashboard
- Batch migration management
- Configuration editor
- Settings panel
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from ..core.optional_imports import (
    TEXTUAL_AVAILABLE,
    App,
    ComposeResult,
    Header,
    Footer,
    Static,
    Container,
    Vertical,
    Horizontal,
    TabbedContent,
    TabPane,
    Button,
    Input,
    Label,
    Select,
    Checkbox,
    RadioButton,
    RadioSet,
    DataTable,
    DirectoryTree,
    Binding,
    work,
)

if not TEXTUAL_AVAILABLE:
    raise ImportError(
        "Textual library is required for TUI. "
        "Install with: pip install 'hyper2kvm[tui]'"
    )

from .wizard import MigrationWizard
from .vm_browser import VMBrowser
from .migrations_panel import MigrationsPanel
from .batch_manager import BatchMigrationManager
from .settings_panel import SettingsPanel
from .migration_tracker import MigrationTracker
from .help_dialog import HelpDialog

logger = logging.getLogger(__name__)


class Hyper2KVMApp(App):
    """
    Comprehensive TUI application for hyper2kvm VM migrations.

    Navigation:
    - Tab: Switch between panels
    - F1: Help
    - F2: Quick wizard
    - F3: Browse VMs
    - F5: Refresh
    - Ctrl+Q: Quit
    """

    TITLE = "hyper2kvm - VM Migration Management"
    SUB_TITLE = "Enterprise-grade Hypervisor to KVM/QEMU Migration"

    CSS = """
    /* Professional dark theme with coral accents (RGB: 222, 115, 86 / Pantone 7416 C) */
    Screen {
        background: $surface;
    }

    Header {
        background: #DE7356;  /* Coral brand color */
        color: $text;
        text-style: bold;
    }

    Header .header--title {
        color: white;
    }

    Header .header--subtitle {
        color: #F5B5A3;  /* Lighter coral for subtitle */
    }

    Footer {
        background: #DE7356;  /* Coral brand color */
        color: white;
    }

    TabbedContent {
        height: 1fr;
        border: solid #DE7356;  /* Coral brand color */
    }

    TabPane {
        padding: 1 2;
    }

    Tabs {
        background: $surface-darken-1;
    }

    Tab {
        background: $surface-darken-1;
        color: $text;
        text-style: bold;
    }

    Tab:hover {
        background: $surface;
        color: #F5B5A3;  /* Lighter coral on hover */
    }

    Tab.-active {
        background: #DE7356;  /* Coral brand color for active tab */
        color: white;
    }

    .welcome-panel {
        width: 100%;
        height: 100%;
        content-align: center middle;
    }

    .welcome-box {
        width: 80;
        height: auto;
        border: heavy #DE7356;  /* Coral brand color */
        background: $surface-darken-1;
        padding: 2 4;
    }

    .welcome-title {
        text-align: center;
        text-style: bold;
        color: #DE7356;  /* Coral brand color */
        margin: 0 0 1 0;
    }

    .welcome-subtitle {
        text-align: center;
        color: $text-muted;
        margin: 0 0 2 0;
    }

    .quick-action {
        margin: 1 0;
        width: 100%;
        min-height: 3;
    }

    .quick-action Button {
        width: 1fr;
        margin: 0 1;
    }

    .stats-panel {
        height: auto;
        border: solid #DE7356;  /* Coral brand color */
        background: $surface-darken-1;
        padding: 1 2;
        margin: 1 0;
    }

    .stats-grid {
        layout: grid;
        grid-size: 4;
        grid-gutter: 1;
    }

    .stat-box {
        height: 5;
        border: round #F5B5A3;  /* Lighter coral */
        background: $surface;
        padding: 1;
        content-align: center middle;
    }

    .stat-value {
        text-style: bold;
        color: #DE7356;  /* Coral brand color */
        text-align: center;
    }

    .stat-label {
        color: $text-muted;
        text-align: center;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("f1", "help", "Help"),
        Binding("f2", "quick_wizard", "Quick Wizard"),
        Binding("f3", "browse_vms", "Browse VMs"),
        Binding("f5", "refresh", "Refresh"),
        Binding("ctrl+s", "settings", "Settings"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.theme = "textual-dark"
        self.migration_tracker = MigrationTracker(logger=logger)
        self.migration_tracker.load()
        self.stats = self.migration_tracker.get_statistics()

    def compose(self) -> ComposeResult:
        """Create the application UI."""
        yield Header()

        with TabbedContent(initial="welcome"):
            # Welcome / Dashboard Tab
            with TabPane("🏠 Home", id="welcome"):
                yield from self.compose_welcome()

            # Migration Wizard Tab
            with TabPane("🧙 Wizard", id="wizard"):
                yield MigrationWizard()

            # VM Browser Tab
            with TabPane("📁 Browse", id="browser"):
                yield VMBrowser()

            # Active Migrations Tab
            with TabPane("📊 Migrations", id="migrations"):
                yield MigrationsPanel()

            # Batch Manager Tab
            with TabPane("🗂️ Batch", id="batch"):
                yield BatchMigrationManager()

            # Settings Tab
            with TabPane("⚙️ Settings", id="settings"):
                yield SettingsPanel()

        yield Footer()

    def compose_welcome(self) -> ComposeResult:
        """Compose the welcome screen."""
        with Container(classes="welcome-panel"):
            with Vertical(classes="welcome-box"):
                yield Static("🚀 Welcome to hyper2kvm", classes="welcome-title")
                yield Static("Enterprise-grade VM migration toolkit", classes="welcome-subtitle")

                # Quick actions
                with Horizontal(classes="quick-action"):
                    yield Button("🧙 Start Migration Wizard", id="btn_wizard", variant="primary")
                    yield Button("📁 Browse VMs", id="btn_browse", variant="default")

                with Horizontal(classes="quick-action"):
                    yield Button("📥 Import Configuration", id="btn_import", variant="default")
                    yield Button("⚙️ Settings", id="btn_settings", variant="default")

                # Statistics
                with Container(classes="stats-panel"):
                    yield Static("📈 Migration Statistics", classes="welcome-subtitle")
                    with Container(classes="stats-grid"):
                        # Total migrations
                        with Vertical(classes="stat-box"):
                            yield Static(str(self.stats["total_migrations"]), classes="stat-value")
                            yield Static("Total Migrations", classes="stat-label")

                        # Active migrations
                        with Vertical(classes="stat-box"):
                            yield Static(str(self.stats["active_migrations"]), classes="stat-value")
                            yield Static("Active", classes="stat-label")

                        # Completed today
                        with Vertical(classes="stat-box"):
                            yield Static(str(self.stats["completed_today"]), classes="stat-value")
                            yield Static("Completed Today", classes="stat-label")

                        # Success rate
                        with Vertical(classes="stat-box"):
                            yield Static(f"{self.stats['success_rate']:.1f}%", classes="stat-value")
                            yield Static("Success Rate", classes="stat-label")

                # Recent activity placeholder
                yield Static("\n📋 Recent Activity", classes="welcome-subtitle")
                yield Static("No recent migrations", classes="stat-label")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn_wizard":
            self.action_quick_wizard()
        elif button_id == "btn_browse":
            self.action_browse_vms()
        elif button_id == "btn_import":
            self.action_import_config()
        elif button_id == "btn_settings":
            self.action_settings()

    def action_quick_wizard(self) -> None:
        """Open the migration wizard."""
        # Switch to wizard tab
        tabbed_content = self.query_one(TabbedContent)
        tabbed_content.active = "wizard"
        self.notify("Migration wizard opened")

    def action_browse_vms(self) -> None:
        """Open the VM browser."""
        tabbed_content = self.query_one(TabbedContent)
        tabbed_content.active = "browser"
        self.notify("VM browser opened")

    def action_import_config(self) -> None:
        """Import a configuration file."""
        self.notify("Configuration import - Coming soon!")

    def action_settings(self) -> None:
        """Open settings panel."""
        tabbed_content = self.query_one(TabbedContent)
        tabbed_content.active = "settings"
        self.notify("Settings opened")

    def action_help(self) -> None:
        """Show help dialog."""
        self.push_screen(HelpDialog(topic="general"))

    def action_refresh(self) -> None:
        """Refresh the current view."""
        self.notify("Refreshing...")
        # Note: Tab-specific refresh requires checking active tab:
        # tabbed_content = self.query_one(TabbedContent)
        # if tabbed_content.active == "welcome":
        #     self.refresh_welcome_stats()
        # elif tabbed_content.active == "migrations":
        #     migrations_panel.refresh_migrations()
        # elif tabbed_content.active == "batch":
        #     batch_manager.refresh_migrations()
        # elif tabbed_content.active == "browser":
        #     vm_browser.refresh_vm_list()
        # Current implementation shows notification only.

    @work(exclusive=True)
    async def update_stats(self) -> None:
        """Update statistics in the background."""
        while True:
            await asyncio.sleep(5)

            # Reload migration history and update stats
            try:
                self.migration_tracker.load()
                self.stats = self.migration_tracker.get_statistics()

                # Update stats display if on welcome screen
                tabbed_content = self.query_one(TabbedContent)
                if tabbed_content.active == "welcome":
                    # Refresh welcome screen stats
                    self.refresh_welcome_stats()
            except Exception as e:
                logger.debug(f"Failed to update stats: {e}")

    def refresh_welcome_stats(self) -> None:
        """Refresh statistics display on welcome screen."""
        try:
            # This would ideally update the static widgets with new values
            # For now, just log the update
            logger.debug(f"Stats updated: {self.stats}")
        except Exception as e:
            logger.debug(f"Failed to refresh welcome stats: {e}")


def run_hyper2kvm_tui() -> None:
    """
    Run the comprehensive hyper2kvm TUI application.

    This is the main entry point for the interactive TUI.
    """
    app = Hyper2KVMApp()
    app.run()


if __name__ == "__main__":
    run_hyper2kvm_tui()
