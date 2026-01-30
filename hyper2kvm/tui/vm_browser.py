# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/tui/vm_browser.py
"""
VM browser for selecting VMs from vSphere, local directories, or Hyper-V.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

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
    DataTable,
    DirectoryTree,
    Tabs,
    Tab,
)

if not TEXTUAL_AVAILABLE:
    raise ImportError("Textual required")


class VMBrowser(Container):
    """
    Browse and select VMs from various sources.

    Sources:
    - vSphere: Connect to vCenter and browse datacenter
    - Local: Browse local filesystem for VMDK files
    - Hyper-V: Browse Hyper-V VMs (future)
    """

    DEFAULT_CSS = """
    VMBrowser {
        height: 100%;
        border: heavy #DE7356;  /* Coral brand color */
        background: $surface;
    }

    .browser-header {
        height: 5;
        background: #DE7356;  /* Coral brand color */
        color: white;
        padding: 1 2;
        text-style: bold;
    }

    .browser-toolbar {
        height: 4;
        background: $surface-darken-1;
        padding: 0 2;
    }

    .browser-body {
        height: 1fr;
        layout: horizontal;
    }

    .browser-sidebar {
        width: 30;
        border-right: solid #DE7356;  /* Coral brand color */
        padding: 1;
    }

    .browser-main {
        width: 1fr;
        padding: 1 2;
    }

    .browser-footer {
        height: 5;
        background: $surface-darken-1;
        padding: 1 2;
    }

    .toolbar-row {
        layout: horizontal;
        height: auto;
        align: left middle;
    }

    .toolbar-row Button {
        margin: 0 1;
    }

    .toolbar-row Input {
        width: 40;
        margin: 0 1;
    }

    .vm-table {
        height: 1fr;
    }

    .selection-info {
        layout: horizontal;
        height: auto;
        align: left middle;
    }

    .selection-info Static {
        margin: 0 2;
    }

    .connection-form {
        padding: 1;
    }

    .form-row {
        height: auto;
        margin: 1 0;
    }

    .form-label {
        width: 15;
    }

    .form-input {
        width: 1fr;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_vms: List[Dict[str, Any]] = []
        self.current_source = "local"  # local, vsphere, hyperv
        self.vsphere_connected = False
        self.vm_list: List[Dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        """Compose the browser UI."""
        # Header
        with Container(classes="browser-header"):
            yield Static("📁 VM Browser - Select VMs to migrate")

        # Toolbar
        with Container(classes="browser-toolbar"):
            with Horizontal(classes="toolbar-row"):
                yield Button("🔄 Refresh", id="btn_refresh", variant="default")
                yield Button("☁️ vSphere", id="btn_source_vsphere", variant="default")
                yield Button("💾 Local", id="btn_source_local", variant="primary")
                yield Input(placeholder="Search VMs...", id="input_search")

        # Body with sidebar and main area
        with Container(classes="browser-body"):
            # Sidebar for filters/tree
            with Vertical(classes="browser-sidebar"):
                yield Static("Filters", classes="section-title")
                yield Button("All VMs", id="filter_all", variant="default")
                yield Button("Running", id="filter_running", variant="default")
                yield Button("Stopped", id="filter_stopped", variant="default")
                yield Button("Windows", id="filter_windows", variant="default")
                yield Button("Linux", id="filter_linux", variant="default")

            # Main area for VM table
            with Vertical(classes="browser-main"):
                if self.current_source == "local":
                    yield from self.compose_local_browser()
                elif self.current_source == "vsphere":
                    yield from self.compose_vsphere_browser()

        # Footer with selection info and actions
        with Container(classes="browser-footer"):
            with Horizontal(classes="selection-info"):
                yield Static(f"Selected: {len(self.selected_vms)} VMs", id="selection_count")
                yield Static("Total size: 0 GB", id="selection_size")
                yield Button("Migrate Selected", id="btn_migrate_selected", variant="success")
                yield Button("Clear Selection", id="btn_clear_selection", variant="default")

    def compose_local_browser(self) -> ComposeResult:
        """Compose local filesystem browser."""
        yield Static("📁 Local VMDK Files")

        # Directory tree or file browser
        with Vertical():
            with Horizontal(classes="form-row"):
                yield Label("Base Directory:", classes="form-label")
                yield Input(value=str(Path.home()), classes="form-input", id="input_base_dir")
                yield Button("Browse", id="btn_browse_dir")

            # File table
            table = DataTable(classes="vm-table", id="table_local_files")
            table.add_columns("Select", "Filename", "Size", "Modified")
            table.cursor_type = "row"
            yield table

    def compose_vsphere_browser(self) -> ComposeResult:
        """Compose vSphere VM browser."""
        if not self.vsphere_connected:
            # Connection form
            with Vertical(classes="connection-form"):
                yield Static("☁️ Connect to vSphere")

                with Horizontal(classes="form-row"):
                    yield Label("vCenter Server:", classes="form-label")
                    yield Input(placeholder="vcenter.example.com", classes="form-input", id="input_vcenter_host")

                with Horizontal(classes="form-row"):
                    yield Label("Username:", classes="form-label")
                    yield Input(placeholder="administrator@vsphere.local", classes="form-input", id="input_vcenter_user")

                with Horizontal(classes="form-row"):
                    yield Label("Password:", classes="form-label")
                    yield Input(password=True, classes="form-input", id="input_vcenter_pass")

                yield Button("Connect", id="btn_connect_vsphere", variant="primary")
        else:
            # VM table
            yield Static("☁️ vSphere VMs")

            table = DataTable(classes="vm-table", id="table_vsphere_vms")
            table.add_columns("Select", "VM Name", "State", "CPUs", "Memory", "Disk", "OS")
            table.cursor_type = "row"

            # Populate with sample data for now
            self.populate_sample_vms(table)

            yield table

    def populate_sample_vms(self, table: DataTable) -> None:
        """Populate table with sample VM data."""
        sample_vms = [
            ("web-server-01", "Running", "2", "4 GB", "50 GB", "Ubuntu 22.04"),
            ("database-server", "Running", "4", "16 GB", "500 GB", "CentOS 8"),
            ("app-server-03", "Stopped", "2", "8 GB", "100 GB", "RHEL 9"),
            ("backup-server", "Running", "2", "4 GB", "200 GB", "Windows Server 2022"),
            ("dev-machine", "Stopped", "4", "8 GB", "80 GB", "Fedora 40"),
        ]

        for idx, (name, state, cpus, mem, disk, os) in enumerate(sample_vms):
            table.add_row("[ ]", name, state, cpus, mem, disk, os, key=f"vm_{idx}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn_source_local":
            self.current_source = "local"
            self.refresh_browser()

        elif button_id == "btn_source_vsphere":
            self.current_source = "vsphere"
            self.refresh_browser()

        elif button_id == "btn_refresh":
            self.refresh_vm_list()

        elif button_id == "btn_connect_vsphere":
            self.connect_vsphere()

        elif button_id == "btn_migrate_selected":
            self.migrate_selected()

        elif button_id == "btn_clear_selection":
            self.clear_selection()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in the VM table."""
        table = event.data_table
        row_key = event.row_key

        try:
            # Get current row data
            row = table.get_row(row_key)
            checkbox = row[0]  # First column is the checkbox

            # Toggle selection state
            if checkbox == "[ ]":
                # Select the VM
                new_checkbox = "[X]"
                # Get VM details from the row (name is in column 1)
                vm_name = row[1]
                vm_info = {
                    "name": vm_name,
                    "row_key": row_key,
                    "size_gb": 50.0,  # Placeholder, would be parsed from actual data
                }
                self.selected_vms.append(vm_info)
            else:
                # Deselect the VM
                new_checkbox = "[ ]"
                # Remove from selected_vms
                self.selected_vms = [vm for vm in self.selected_vms if vm.get("row_key") != row_key]

            # Update the checkbox in the table
            table.update_cell(row_key, "Select", new_checkbox)

        except Exception as e:
            self.notify(f"Selection error: {e}", severity="error")

        self.update_selection_info()

    def refresh_browser(self) -> None:
        """Refresh the browser view."""
        self.notify(f"Switched to {self.current_source} browser")
        # Note: Full browser recomposition would require removing and re-adding
        # the main browser container. Current implementation shows notification only.
        # Future enhancement: Dynamically update the browser panel based on source type.

    def refresh_vm_list(self) -> None:
        """Refresh the VM list from the current source."""
        self.notify("Refreshing VM list...")
        # Note: Actual VM reloading requires integration with source APIs:
        # - vSphere: Use pyVmomi to query VMs from vCenter
        # - Local: Scan filesystem for VMDK/VDI/QCOW2 files
        # - Hyper-V: Query Hyper-V WMI/PowerShell interfaces
        # Current implementation shows notification only.

    def connect_vsphere(self) -> None:
        """Connect to vSphere server."""
        # Get connection details from inputs
        self.notify("Connecting to vSphere...", severity="information")

        # Note: Actual vSphere connection requires pyVmomi integration:
        # from pyVim.connect import SmartConnect, Disconnect
        # 1. Get credentials from input widgets (input_vcenter_host, input_vcenter_user, input_vcenter_pass)
        # 2. Create SSL context (disable verification or use custom certs)
        # 3. Call SmartConnect(host=host, user=user, pwd=pwd, sslContext=context)
        # 4. Store connection object for later VM queries
        # 5. Handle authentication errors and show appropriate messages
        # For now, simulate successful connection for UI testing
        self.vsphere_connected = True
        self.refresh_browser()

    def migrate_selected(self) -> None:
        """Start migration for selected VMs."""
        if not self.selected_vms:
            self.notify("No VMs selected", severity="warning")
            return

        self.notify(f"Starting migration for {len(self.selected_vms)} VMs...")
        # Note: Migration launch requires integration with wizard:
        # Option 1: Launch migration wizard with pre-selected VMs
        #   - Get MainApp instance via self.app
        #   - Call wizard.set_selected_vms(self.selected_vms)
        #   - Switch to wizard tab: self.app.query_one(TabbedContent).active = "wizard"
        # Option 2: Start migration directly (bypass wizard)
        #   - Create migration batch from selected_vms
        #   - Call batch orchestrator with VM list
        #   - Show progress in migrations panel
        # Current implementation shows notification only.

    def clear_selection(self) -> None:
        """Clear all VM selections."""
        self.selected_vms.clear()
        self.update_selection_info()
        self.notify("Selection cleared")

    def update_selection_info(self) -> None:
        """Update the selection info in the footer."""
        total_size = sum(vm.get("size_gb", 0) for vm in self.selected_vms)

        # Update selection count widget
        try:
            count_widget = self.query_one("#selection_count", Static)
            count_widget.update(f"Selected: {len(self.selected_vms)} VMs")
        except Exception:
            pass

        # Update selection size widget
        try:
            size_widget = self.query_one("#selection_size", Static)
            size_widget.update(f"Total size: {total_size:.1f} GB")
        except Exception:
            pass
