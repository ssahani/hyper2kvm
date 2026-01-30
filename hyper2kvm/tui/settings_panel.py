# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/settings_panel.py
"""
Settings panel for configuring hyper2kvm defaults and preferences.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..core.optional_imports import (
    TEXTUAL_AVAILABLE,
    ComposeResult,
    Static,
    Container,
    Vertical,
    Horizontal,
    Button,
    Input,
    Label,
    Select,
    Checkbox,
    RadioButton,
    RadioSet,
)
from .tui_config import load_tui_settings, save_tui_settings, get_default_settings

if not TEXTUAL_AVAILABLE:
    raise ImportError("Textual required")


class SettingsPanel(Container):
    """
    Settings panel for hyper2kvm configuration.

    Categories:
    - General: Default paths, logging level
    - Migration: Default format, compression, parallelism
    - vSphere: Default connection settings
    - Offline Fixes: Default fix preferences
    - Performance: Resource limits, timeouts
    - Advanced: Backend selection, debug options
    """

    DEFAULT_CSS = """
    SettingsPanel {
        height: 100%;
        background: $surface;
    }

    .settings-header {
        height: 5;
        background: #DE7356;  /* Coral brand color */
        color: white;
        padding: 1 2;
        text-style: bold;
    }

    .settings-body {
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }

    .settings-footer {
        height: 5;
        background: $surface-darken-1;
        padding: 1 2;
    }

    .settings-section {
        border: solid #F5B5A3;  /* Lighter coral */
        background: $surface-darken-1;
        padding: 1 2;
        margin: 1 0;
    }

    .section-title {
        text-style: bold;
        color: #DE7356;  /* Coral brand color */
        margin: 0 0 1 0;
    }

    .form-row {
        height: auto;
        margin: 1 0;
    }

    .form-label {
        width: 30;
        content-align: left middle;
    }

    .form-input {
        width: 1fr;
    }

    .form-help {
        color: $text-muted;
        margin: 0 0 0 30;
    }

    .settings-buttons {
        layout: horizontal;
        height: auto;
        align: right middle;
    }

    .settings-buttons Button {
        margin: 0 1;
    }

    .info-box {
        border: solid #F5B5A3;  /* Lighter coral */
        background: $surface-darken-2;
        padding: 1 2;
        margin: 1 0;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logger = logging.getLogger(__name__)
        self.settings = self._flatten_settings(load_tui_settings(logger=self.logger))
        self.modified = False

    def _flatten_settings(self, nested_settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Flatten nested settings dict to flat dict for compatibility.

        Args:
            nested_settings: Nested settings dict from config file

        Returns:
            Flat settings dict
        """
        flat = {}
        for category, values in nested_settings.items():
            if isinstance(values, dict):
                flat.update(values)
            else:
                flat[category] = values
        return flat

    def _unflatten_settings(self, flat_settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert flat settings dict back to nested structure for saving.

        Args:
            flat_settings: Flat settings dict

        Returns:
            Nested settings dict for config file
        """
        defaults = get_default_settings()
        nested = {}

        # Map flat keys back to nested structure
        for category, category_defaults in defaults.items():
            if isinstance(category_defaults, dict):
                nested[category] = {}
                for key in category_defaults.keys():
                    if key in flat_settings:
                        nested[category][key] = flat_settings[key]
                    else:
                        nested[category][key] = category_defaults[key]

        return nested

    def load_default_settings(self) -> Dict[str, Any]:
        """Load default settings."""
        return self._flatten_settings(get_default_settings())

    def compose(self) -> ComposeResult:
        """Compose the settings panel UI."""
        # Header
        with Container(classes="settings-header"):
            yield Static("⚙️ Settings - Configure hyper2kvm defaults")

        # Body with scrollable sections
        with Container(classes="settings-body"):
            yield from self.compose_general_settings()
            yield from self.compose_migration_settings()
            yield from self.compose_vsphere_settings()
            yield from self.compose_offline_fixes_settings()
            yield from self.compose_performance_settings()
            yield from self.compose_advanced_settings()

        # Footer with action buttons
        with Container(classes="settings-footer"):
            with Horizontal(classes="settings-buttons"):
                yield Button("Reset to Defaults", id="btn_reset", variant="default")
                yield Button("Cancel", id="btn_cancel", variant="default")
                yield Button("Save Settings", id="btn_save", variant="success")

    def compose_general_settings(self) -> ComposeResult:
        """General settings section."""
        with Container(classes="settings-section"):
            yield Static("📁 General Settings", classes="section-title")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("Default Output Directory:", classes="form-label")
                    yield Input(
                        value=self.settings["default_output_dir"],
                        classes="form-input",
                        id="input_output_dir"
                    )
                yield Static("Default directory for converted VM images", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("Log Level:", classes="form-label")
                    yield Select(
                        [
                            ("Debug", "debug"),
                            ("Info", "info"),
                            ("Warning", "warning"),
                            ("Error", "error"),
                        ],
                        value=self.settings["log_level"],
                        id="select_log_level",
                        classes="form-input"
                    )
                yield Static("Verbosity of log messages", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Checkbox(
                        "Enable file logging",
                        value=self.settings["log_to_file"],
                        id="check_log_to_file"
                    )

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("Log File Path:", classes="form-label")
                    yield Input(
                        value=self.settings["log_file_path"],
                        classes="form-input",
                        id="input_log_file"
                    )

    def compose_migration_settings(self) -> ComposeResult:
        """Migration settings section."""
        with Container(classes="settings-section"):
            yield Static("🔄 Migration Settings", classes="section-title")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("Default Output Format:", classes="form-label")
                    yield Select(
                        [
                            ("QCOW2 (Recommended)", "qcow2"),
                            ("RAW", "raw"),
                            ("VDI (VirtualBox)", "vdi"),
                            ("VMDK", "vmdk"),
                        ],
                        value=self.settings["default_format"],
                        id="select_output_format",
                        classes="form-input"
                    )
                yield Static("Default format for converted images", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Checkbox(
                        "Enable compression by default",
                        value=self.settings["enable_compression"],
                        id="check_compression"
                    )
                yield Static("Compress output images (slower but saves space)", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("Parallel Migrations:", classes="form-label")
                    yield Input(
                        value=str(self.settings["parallel_migrations"]),
                        classes="form-input",
                        id="input_parallel_migrations"
                    )
                yield Static("Number of concurrent migrations (1-8)", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Checkbox(
                        "Skip existing output files",
                        value=self.settings["skip_existing"],
                        id="check_skip_existing"
                    )
                yield Static("Skip migration if output file already exists", classes="form-help")

    def compose_vsphere_settings(self) -> ComposeResult:
        """vSphere settings section."""
        with Container(classes="settings-section"):
            yield Static("☁️ vSphere Settings", classes="section-title")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("vCenter Host:", classes="form-label")
                    yield Input(
                        placeholder="vcenter.example.com",
                        value=self.settings["vcenter_host"],
                        classes="form-input",
                        id="input_vcenter_host"
                    )
                yield Static("Default vCenter server address", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("Username:", classes="form-label")
                    yield Input(
                        placeholder="administrator@vsphere.local",
                        value=self.settings["vcenter_username"],
                        classes="form-input",
                        id="input_vcenter_username"
                    )
                yield Static("Default vCenter username", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Checkbox(
                        "Save credentials (encrypted)",
                        value=self.settings["vcenter_save_credentials"],
                        id="check_save_credentials"
                    )
                yield Static("Store vCenter credentials securely", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Checkbox(
                        "Verify SSL certificates",
                        value=self.settings["vcenter_verify_ssl"],
                        id="check_verify_ssl"
                    )
                yield Static("Verify vCenter SSL certificates (recommended)", classes="form-help")

    def compose_offline_fixes_settings(self) -> ComposeResult:
        """Offline fixes settings section."""
        with Container(classes="settings-section"):
            yield Static("🔧 Offline Fixes Settings", classes="section-title")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("fstab Stabilization:", classes="form-label")
                    yield Select(
                        [
                            ("Stabilize All", "stabilize-all"),
                            ("Boot Only", "boot-only"),
                            ("Disabled", "disabled"),
                        ],
                        value=self.settings["fstab_mode"],
                        id="select_fstab_mode",
                        classes="form-input"
                    )
                yield Static("Convert device names to UUIDs in /etc/fstab", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Checkbox(
                        "Regenerate initramfs",
                        value=self.settings["regen_initramfs"],
                        id="check_initramfs"
                    )
                yield Static("Inject virtio drivers into initramfs", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Checkbox(
                        "Update GRUB configuration",
                        value=self.settings["update_grub"],
                        id="check_grub"
                    )
                yield Static("Regenerate GRUB bootloader configuration", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Checkbox(
                        "Fix network configuration",
                        value=self.settings["fix_network"],
                        id="check_network"
                    )
                yield Static("Remove MAC address pinning from network configs", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Checkbox(
                        "Use enhanced chroot (recommended)",
                        value=self.settings["enhanced_chroot"],
                        id="check_enhanced_chroot"
                    )
                yield Static("Bind-mount /proc, /dev, /sys for bootloader commands", classes="form-help")

    def compose_performance_settings(self) -> ComposeResult:
        """Performance settings section."""
        with Container(classes="settings-section"):
            yield Static("⚡ Performance Settings", classes="section-title")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("Max Concurrent Operations:", classes="form-label")
                    yield Input(
                        value=str(self.settings["max_concurrent_operations"]),
                        classes="form-input",
                        id="input_max_operations"
                    )
                yield Static("Maximum parallel operations (1-16)", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("Operation Timeout (seconds):", classes="form-label")
                    yield Input(
                        value=str(self.settings["operation_timeout"]),
                        classes="form-input",
                        id="input_operation_timeout"
                    )
                yield Static("Timeout for individual operations (300-7200)", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("Network Timeout (seconds):", classes="form-label")
                    yield Input(
                        value=str(self.settings["network_timeout"]),
                        classes="form-input",
                        id="input_network_timeout"
                    )
                yield Static("Timeout for network operations (60-600)", classes="form-help")

    def compose_advanced_settings(self) -> ComposeResult:
        """Advanced settings section."""
        with Container(classes="settings-section"):
            yield Static("🔬 Advanced Settings", classes="section-title")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("GuestFS Backend:", classes="form-label")
                    yield Select(
                        [
                            ("VMCraft (Recommended)", "vmcraft"),
                            ("libguestfs", "libguestfs"),
                        ],
                        value=self.settings["guestfs_backend"],
                        id="select_backend",
                        classes="form-input"
                    )
                yield Static("Backend for filesystem operations", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Checkbox(
                        "Enable debug mode",
                        value=self.settings["debug_mode"],
                        id="check_debug"
                    )
                yield Static("Enable detailed debugging output", classes="form-help")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Checkbox(
                        "Verbose output",
                        value=self.settings["verbose_output"],
                        id="check_verbose"
                    )
                yield Static("Show detailed progress information", classes="form-help")

            with Container(classes="info-box"):
                yield Static("⚠️ Warning: Debug mode may expose sensitive information in logs")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses in settings panel."""
        button_id = event.button.id

        if button_id == "btn_save":
            self.save_settings()
        elif button_id == "btn_cancel":
            self.cancel_changes()
        elif button_id == "btn_reset":
            self.reset_to_defaults()

    def save_settings(self) -> None:
        """Save current settings."""
        # Collect values from inputs
        try:
            # General
            self.settings["default_output_dir"] = self.query_one("#input_output_dir", Input).value
            self.settings["log_level"] = self.query_one("#select_log_level", Select).value
            self.settings["log_to_file"] = self.query_one("#check_log_to_file", Checkbox).value
            self.settings["log_file_path"] = self.query_one("#input_log_file", Input).value

            # Migration
            self.settings["default_format"] = self.query_one("#select_output_format", Select).value
            self.settings["enable_compression"] = self.query_one("#check_compression", Checkbox).value
            self.settings["parallel_migrations"] = int(self.query_one("#input_parallel_migrations", Input).value)
            self.settings["skip_existing"] = self.query_one("#check_skip_existing", Checkbox).value

            # vSphere
            self.settings["vcenter_host"] = self.query_one("#input_vcenter_host", Input).value
            self.settings["vcenter_username"] = self.query_one("#input_vcenter_username", Input).value
            self.settings["vcenter_save_credentials"] = self.query_one("#check_save_credentials", Checkbox).value
            self.settings["vcenter_verify_ssl"] = self.query_one("#check_verify_ssl", Checkbox).value

            # Offline Fixes
            self.settings["fstab_mode"] = self.query_one("#select_fstab_mode", Select).value
            self.settings["regen_initramfs"] = self.query_one("#check_initramfs", Checkbox).value
            self.settings["update_grub"] = self.query_one("#check_grub", Checkbox).value
            self.settings["fix_network"] = self.query_one("#check_network", Checkbox).value
            self.settings["enhanced_chroot"] = self.query_one("#check_enhanced_chroot", Checkbox).value

            # Performance
            self.settings["max_concurrent_operations"] = int(self.query_one("#input_max_operations", Input).value)
            self.settings["operation_timeout"] = int(self.query_one("#input_operation_timeout", Input).value)
            self.settings["network_timeout"] = int(self.query_one("#input_network_timeout", Input).value)

            # Advanced
            self.settings["guestfs_backend"] = self.query_one("#select_backend", Select).value
            self.settings["debug_mode"] = self.query_one("#check_debug", Checkbox).value
            self.settings["verbose_output"] = self.query_one("#check_verbose", Checkbox).value

            # Convert flat settings to nested structure and persist to config file
            nested_settings = self._unflatten_settings(self.settings)
            if save_tui_settings(nested_settings, logger=self.logger):
                self.notify("Settings saved successfully", severity="information")
                self.modified = False
            else:
                self.notify("Failed to save settings to config file", severity="error")

        except Exception as e:
            self.notify(f"Failed to save settings: {e}", severity="error")
            self.logger.exception("Error saving settings")

    def cancel_changes(self) -> None:
        """Cancel changes and revert to saved settings."""
        if self.modified:
            # Reload from saved config
            self.settings = self._flatten_settings(load_tui_settings(logger=self.logger))
            self.notify("Changes discarded, settings reloaded")
            self.modified = False
        else:
            self.notify("No changes to discard")

    def reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        self.settings = self.load_default_settings()
        self.notify("Settings reset to defaults - click Save to persist", severity="warning")
        self.modified = True
