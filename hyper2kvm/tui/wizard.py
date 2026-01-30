# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/wizard.py
"""
Interactive migration wizard for step-by-step VM migration setup.
"""

from __future__ import annotations

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
    DirectoryTree,
)

if not TEXTUAL_AVAILABLE:
    raise ImportError("Textual required")


class MigrationWizard(Container):
    """
    Step-by-step migration wizard.

    Steps:
    1. Select Source (vSphere, local VMDK, Hyper-V, OVA)
    2. Select VMs / Files
    3. Configure Output (format, location, compression)
    4. Offline Fixes (fstab, initramfs, GRUB, network)
    5. Review & Start
    """

    DEFAULT_CSS = """
    MigrationWizard {
        height: 100%;
        border: heavy #DE7356;  /* Coral brand color */
        background: $surface;
    }

    .wizard-header {
        height: 5;
        background: #DE7356;  /* Coral brand color */
        color: white;
        padding: 1 2;
        text-style: bold;
    }

    .wizard-progress {
        height: 3;
        background: $surface-darken-1;
        padding: 0 2;
    }

    .wizard-body {
        height: 1fr;
        padding: 2;
    }

    .wizard-footer {
        height: 5;
        background: $surface-darken-1;
        padding: 1 2;
    }

    .step-indicator {
        layout: horizontal;
        height: auto;
    }

    .step-item {
        width: 1fr;
        height: auto;
        padding: 0 1;
        text-align: center;
    }

    .step-active {
        color: #DE7356;  /* Coral brand color */
        text-style: bold;
    }

    .step-complete {
        color: $success;
    }

    .step-pending {
        color: $text-muted;
    }

    .form-row {
        height: auto;
        margin: 1 0;
    }

    .form-label {
        width: 20;
        content-align: left middle;
    }

    .form-input {
        width: 1fr;
    }

    .wizard-buttons {
        layout: horizontal;
        height: auto;
        align: right middle;
    }

    .wizard-buttons Button {
        margin: 0 1;
    }

    .source-option {
        height: auto;
        border: round #F5B5A3;  /* Lighter coral */
        background: $surface-darken-1;
        padding: 1 2;
        margin: 1 0;
    }

    .source-option:hover {
        background: $surface;
        border: round #DE7356;  /* Coral brand color */
    }

    .source-selected {
        border: heavy #DE7356;  /* Coral brand color */
        background: #3D2620;  /* Dark coral-tinted background */
    }

    .info-box {
        border: solid #F5B5A3;  /* Lighter coral */
        background: $surface-darken-1;
        padding: 1 2;
        margin: 1 0;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_step = 0
        self.steps = [
            "Source",
            "VMs/Files",
            "Output",
            "Fixes",
            "Review"
        ]
        self.wizard_data = {
            "source_type": None,  # vsphere, local, hyperv, ova
            "source_details": {},
            "selected_vms": [],
            "output_format": "qcow2",
            "output_dir": "/tmp/hyper2kvm-output",
            "compress": True,
            "fstab_mode": "stabilize-all",
            "regen_initramfs": True,
            "update_grub": True,
            "fix_network": True,
        }

    def compose(self) -> ComposeResult:
        """Compose the wizard UI."""
        # Header
        with Container(classes="wizard-header"):
            yield Static(f"🧙 Migration Wizard - Step {self.current_step + 1}/5: {self.steps[self.current_step]}")

        # Progress indicator
        with Container(classes="wizard-progress"):
            with Horizontal(classes="step-indicator"):
                for idx, step in enumerate(self.steps):
                    if idx < self.current_step:
                        style = "step-complete"
                        symbol = "✓"
                    elif idx == self.current_step:
                        style = "step-active"
                        symbol = "▶"
                    else:
                        style = "step-pending"
                        symbol = "○"

                    yield Static(f"{symbol} {step}", classes=f"step-item {style}")

        # Body (dynamic based on current step)
        with Container(classes="wizard-body", id="wizard-body"):
            yield from self.compose_step()

        # Footer with navigation buttons
        with Container(classes="wizard-footer"):
            with Horizontal(classes="wizard-buttons"):
                yield Button("Cancel", id="btn_cancel", variant="default")
                if self.current_step > 0:
                    yield Button("◀ Back", id="btn_back", variant="default")
                if self.current_step < len(self.steps) - 1:
                    yield Button("Next ▶", id="btn_next", variant="primary")
                else:
                    yield Button("🚀 Start Migration", id="btn_start", variant="success")

    def compose_step(self) -> ComposeResult:
        """Compose the current step's content."""
        if self.current_step == 0:
            yield from self.compose_step_source()
        elif self.current_step == 1:
            yield from self.compose_step_vms()
        elif self.current_step == 2:
            yield from self.compose_step_output()
        elif self.current_step == 3:
            yield from self.compose_step_fixes()
        elif self.current_step == 4:
            yield from self.compose_step_review()

    def compose_step_source(self) -> ComposeResult:
        """Step 1: Select source type."""
        yield Static("Select the source of your VM(s):", classes="form-label")

        with Vertical():
            # vSphere option
            with Container(classes="source-option", id="source_vsphere"):
                yield Static("☁️ **VMware vSphere / vCenter**")
                yield Static("   Migrate VMs directly from vSphere using API", classes="stat-label")
                yield Static("   Best for: Production VMware environments", classes="stat-label")

            # Local VMDK option
            with Container(classes="source-option", id="source_local"):
                yield Static("💾 **Local VMDK File(s)**")
                yield Static("   Convert local VMDK files to KVM format", classes="stat-label")
                yield Static("   Best for: Downloaded VMware disk images", classes="stat-label")

            # Hyper-V option
            with Container(classes="source-option", id="source_hyperv"):
                yield Static("🪟 **Microsoft Hyper-V**")
                yield Static("   Convert Hyper-V VHD/VHDX to KVM format", classes="stat-label")
                yield Static("   Best for: Hyper-V environments (experimental)", classes="stat-label")

            # OVA/OVF option
            with Container(classes="source-option", id="source_ova"):
                yield Static("📦 **OVA / OVF Package**")
                yield Static("   Extract and convert from OVA/OVF packages", classes="stat-label")
                yield Static("   Best for: Exported VM appliances", classes="stat-label")

    def compose_step_vms(self) -> ComposeResult:
        """Step 2: Select VMs or files."""
        source_type = self.wizard_data.get("source_type")

        if source_type == "vsphere":
            yield Static("🔍 Connect to vSphere and browse VMs", classes="form-label")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("vCenter Server:", classes="form-label")
                    yield Input(placeholder="vcenter.example.com", classes="form-input", id="input_vcenter")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("Username:", classes="form-label")
                    yield Input(placeholder="administrator@vsphere.local", classes="form-input", id="input_username")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("Password:", classes="form-label")
                    yield Input(placeholder="", password=True, classes="form-input", id="input_password")

            yield Button("Connect & Browse VMs", id="btn_connect_vsphere", variant="primary")

        elif source_type == "local":
            yield Static("📁 Select VMDK file(s) to convert", classes="form-label")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("VMDK Path:", classes="form-label")
                    yield Input(placeholder="/path/to/vm.vmdk", classes="form-input", id="input_vmdk_path")
                    yield Button("Browse...", id="btn_browse_vmdk")

            with Container(classes="info-box"):
                yield Static("💡 Tip: You can select multiple VMDK files for batch conversion")

        elif source_type == "ova":
            yield Static("📦 Select OVA/OVF package", classes="form-label")

            with Vertical(classes="form-row"):
                with Horizontal():
                    yield Label("OVA/OVF Path:", classes="form-label")
                    yield Input(placeholder="/path/to/vm.ova", classes="form-input", id="input_ova_path")
                    yield Button("Browse...", id="btn_browse_ova")

    def compose_step_output(self) -> ComposeResult:
        """Step 3: Configure output settings."""
        yield Static("⚙️ Configure output settings", classes="form-label")

        # Output format
        with Vertical(classes="form-row"):
            with Horizontal():
                yield Label("Output Format:", classes="form-label")
                yield Select(
                    [
                        ("QCOW2 (Recommended)", "qcow2"),
                        ("RAW", "raw"),
                        ("VDI (VirtualBox)", "vdi"),
                    ],
                    value="qcow2",
                    id="select_format",
                    classes="form-input"
                )

        # Output directory
        with Vertical(classes="form-row"):
            with Horizontal():
                yield Label("Output Directory:", classes="form-label")
                yield Input(
                    value="/tmp/hyper2kvm-output",
                    classes="form-input",
                    id="input_output_dir"
                )
                yield Button("Browse...", id="btn_browse_output")

        # Compression
        with Vertical(classes="form-row"):
            with Horizontal():
                yield Checkbox("Enable compression (slower but saves space)", value=True, id="check_compress")

        # Advanced options
        with Container(classes="info-box"):
            yield Static("💡 Advanced options available in Settings")

    def compose_step_fixes(self) -> ComposeResult:
        """Step 4: Configure offline fixes."""
        yield Static("🔧 Configure offline fixes (Linux VMs)", classes="form-label")

        with Vertical():
            with Vertical(classes="form-row"):
                yield Checkbox(
                    "Stabilize fstab (convert device names to UUIDs)",
                    value=True,
                    id="check_fstab"
                )

            with Vertical(classes="form-row"):
                yield Checkbox(
                    "Regenerate initramfs (inject virtio drivers)",
                    value=True,
                    id="check_initramfs"
                )

            with Vertical(classes="form-row"):
                yield Checkbox(
                    "Update GRUB configuration",
                    value=True,
                    id="check_grub"
                )

            with Vertical(classes="form-row"):
                yield Checkbox(
                    "Fix network configuration (remove MAC pinning)",
                    value=True,
                    id="check_network"
                )

        with Container(classes="info-box"):
            yield Static("ℹ️ These fixes ensure VMs boot correctly on KVM")
            yield Static("   Recommended for all Linux VMs migrated from VMware/Hyper-V")

    def compose_step_review(self) -> ComposeResult:
        """Step 5: Review and confirm."""
        yield Static("📋 Review migration configuration", classes="form-label")

        with Container(classes="info-box"):
            yield Static("**Source:**")
            source_type = self.wizard_data.get("source_type", "Not selected")
            yield Static(f"  Type: {source_type}")

            yield Static("\n**Output:**")
            yield Static(f"  Format: {self.wizard_data.get('output_format', 'qcow2')}")
            yield Static(f"  Directory: {self.wizard_data.get('output_dir', 'Not set')}")
            yield Static(f"  Compression: {'Yes' if self.wizard_data.get('compress') else 'No'}")

            yield Static("\n**Offline Fixes:**")
            yield Static(f"  Stabilize fstab: {'Yes' if self.wizard_data.get('fstab_mode') else 'No'}")
            yield Static(f"  Regenerate initramfs: {'Yes' if self.wizard_data.get('regen_initramfs') else 'No'}")
            yield Static(f"  Update GRUB: {'Yes' if self.wizard_data.get('update_grub') else 'No'}")
            yield Static(f"  Fix network: {'Yes' if self.wizard_data.get('fix_network') else 'No'}")

        with Container(classes="info-box"):
            yield Static("✅ Ready to start migration")
            yield Static("   Click 'Start Migration' to begin the conversion process")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses in the wizard."""
        button_id = event.button.id

        if button_id == "btn_cancel":
            self.notify("Migration wizard cancelled")
            # Note: Wizard cancellation requires tab switching:
            # - Get MainApp instance: app = self.app
            # - Switch to home tab: app.query_one(TabbedContent).active = "welcome"
            # - Reset wizard state: self.reset_wizard()
            # Current implementation shows notification only.

        elif button_id == "btn_back":
            if self.current_step > 0:
                self.current_step -= 1
                self.refresh_wizard()

        elif button_id == "btn_next":
            if self.validate_current_step():
                self.current_step += 1
                self.refresh_wizard()

        elif button_id == "btn_start":
            self.start_migration()

    def on_container_clicked(self, event) -> None:
        """Handle clicks on source option containers."""
        target_id = event.container.id

        if target_id and target_id.startswith("source_"):
            source_type = target_id.replace("source_", "")
            self.wizard_data["source_type"] = source_type

            # Visual feedback - mark as selected
            # Note: Button selection styling requires:
            # - Add CSS class "selected" to clicked button: button.add_class("selected")
            # - Remove "selected" class from other source buttons
            # - Define .selected style in DEFAULT_CSS with highlighted background
            # Current implementation shows notification only.

            self.notify(f"Selected: {source_type}")

    def validate_current_step(self) -> bool:
        """Validate the current step before proceeding."""
        if self.current_step == 0:
            # Validate source selection
            if not self.wizard_data.get("source_type"):
                self.notify("Please select a source type", severity="warning")
                return False

        elif self.current_step == 1:
            # Validate VM/file selection
            source_type = self.wizard_data.get("source_type")
            if source_type == "local":
                # Check if VMDK path is provided
                pass

        return True

    def refresh_wizard(self) -> None:
        """Refresh the wizard UI for the current step."""
        # Note: Full wizard refresh requires dynamic UI updates:
        # - Remove current step container
        # - Compose new step content based on self.current_step
        # - Update progress indicator to highlight current step
        # - Enable/disable navigation buttons based on step position
        # Current implementation shows notification only.
        self.notify(f"Now on step {self.current_step + 1}: {self.steps[self.current_step]}")

    def start_migration(self) -> None:
        """Start the migration with collected settings."""
        self.notify("Starting migration...", severity="information")
        # Note: Migration launch requires backend integration:
        # 1. Build migration configuration from self.wizard_data:
        #    - source_path, output_path, disk_format, vm_name, etc.
        # 2. Create MigrationRecord via migration_tracker
        # 3. Start migration process (subprocess or thread):
        #    - Import VMCraft or migration engine
        #    - Call conversion methods with wizard_data settings
        #    - Register PID with migration_controller
        # 4. Switch to migrations tab to show progress:
        #    - self.app.query_one(TabbedContent).active = "migrations"
        # 5. Optionally reset wizard for next migration
        # Current implementation shows notification only.
