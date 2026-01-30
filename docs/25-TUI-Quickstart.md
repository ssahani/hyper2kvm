# TUI Quickstart Guide

**Document Version**: 1.0
**Last Updated**: 2026-01-26
**Status**: Production Ready

---

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Interface Overview](#interface-overview)
- [Migration Wizard](#migration-wizard)
- [VM Browser](#vm-browser)
- [Monitoring Migrations](#monitoring-migrations)
- [Batch Operations](#batch-operations)
- [Settings Configuration](#settings-configuration)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)

---

## Overview

The hyper2kvm TUI (Terminal User Interface) provides a comprehensive, interactive interface for managing VM migrations directly from your terminal. Built with [Textual](https://textual.textualize.io/), it offers a professional, keyboard-driven alternative to CLI commands.

### Key Features

- **🧙 Interactive Wizard**: 5-step guided migration setup
- **📁 Multi-Source Browser**: Browse VMs from vSphere, local storage, or Hyper-V
- **📊 Real-Time Monitoring**: Live migration progress with throughput metrics
- **🗂️ Batch Management**: Handle multiple concurrent migrations
- **⚙️ Comprehensive Settings**: Configure all hyper2kvm options in one place
- **⌨️ Keyboard-Driven**: Full support for keyboard shortcuts

---

## Installation

### Standard Installation

```bash
pip install 'hyper2kvm[tui]'
```

### Full Installation (Recommended)

```bash
pip install 'hyper2kvm[full]'
```

This includes all optional dependencies:
- TUI (Textual)
- vSphere support (pyvmomi)
- Azure support
- Advanced validation (pydantic)
- Daemon mode (watchdog)
- Async operations (httpx)

### Verify Installation

```bash
python3 -c "import textual; print(f'Textual {textual.__version__} installed')"
```

Should output: `Textual 0.47.0 (or higher) installed`

---

## Quick Start

### Launch the TUI

```bash
# Method 1: Direct command
hyper2kvm-tui

# Method 2: Python module
python3 -m hyper2kvm.tui.main_app

# Method 3: With configuration
hyper2kvm-tui --config /path/to/config.yaml
```

### First Migration (Quick Wizard)

1. Press **F2** to open Migration Wizard
2. Select source type (e.g., "Local VMDK")
3. Browse and select VM/disk file
4. Configure output settings (format, directory)
5. Enable offline fixes (recommended for Linux VMs)
6. Review and click "Start Migration"

### Monitor Progress

1. Press **F3** to switch to Migrations tab
2. View real-time progress bars
3. Monitor throughput and ETA
4. Pause/Resume/Cancel as needed

---

## Interface Overview

The TUI features 6 main panels accessible via tabs:

### 🏠 Home

Welcome dashboard with:
- Migration statistics (total, active, completed, success rate)
- Quick action buttons
- Recent activity log
- System status

**Quick Actions**:
- Start Migration Wizard
- Browse VMs
- Import Configuration
- Open Settings

### 🧙 Wizard

5-step interactive migration setup:

1. **Source Selection**: vSphere | Local VMDK | Hyper-V | OVA
2. **VM/File Selection**: Browse and select VMs
3. **Output Configuration**: Format, location, compression
4. **Offline Fixes**: fstab, initramfs, GRUB, network
5. **Review & Start**: Confirm and launch

**Navigation**:
- **Next ▶** - Proceed to next step
- **◀ Back** - Return to previous step
- **Cancel** - Abort wizard

### 📁 Browse

Multi-source VM browser:

**Sources**:
- **vSphere**: Connect to vCenter and browse datacenter
  - Supports SSL verification
  - Credential saving (encrypted)
  - VM metadata display (CPUs, memory, disk, OS)
- **Local**: Browse filesystem for VMDK files
  - Directory tree navigation
  - File size and modification date
  - Multi-file selection
- **Hyper-V**: Browse Hyper-V VMs (experimental)
  - Windows Server integration
  - VHD/VHDX support

**Features**:
- DataTable display with sortable columns
- Multi-select with checkboxes
- Size estimation
- Filters (state, OS type)

### 📊 Migrations

Real-time migration monitoring:

**Display Columns**:
- ID
- VM Name
- Status (running, paused, completed, failed)
- Progress (percentage)
- Current Stage (convert, validate, transfer, done)
- Throughput (MB/s)
- ETA
- Started Time

**Controls**:
- ⏸️ Pause - Pause selected migration
- ▶️ Resume - Resume paused migration
- 🗑️ Cancel - Cancel selected migration
- 🔄 Refresh - Update display
- 📊 Details - View detailed logs

**Statistics Footer**:
- Running count
- Paused count
- Completed count
- Failed count
- Average speed

### 🗂️ Batch

Batch migration management:

**Features**:
- Queue visualization
- Parallel execution control
- Aggregate statistics
- Export batch reports
- Retry failed migrations

**Actions**:
- ➕ New Batch - Create new batch job
- ⏸️ Pause - Pause batch
- ▶️ Resume - Resume batch
- 🗑️ Cancel - Cancel entire batch
- 📊 Export Report - Generate report

### ⚙️ Settings

Comprehensive configuration panel with 6 categories:

**General Settings**:
- Default output directory
- Log level (debug, info, warning, error)
- Enable file logging
- Log file path

**Migration Settings**:
- Default output format (QCOW2, RAW, VDI, VMDK)
- Enable compression
- Parallel migrations (1-8)
- Skip existing files

**vSphere Settings**:
- Default vCenter host
- Username
- Save credentials (encrypted)
- Verify SSL certificates

**Offline Fixes Settings**:
- fstab stabilization mode (stabilize-all, boot-only, disabled)
- Regenerate initramfs
- Update GRUB configuration
- Fix network configuration
- Enhanced chroot (recommended)

**Performance Settings**:
- Max concurrent operations (1-16)
- Operation timeout (300-7200 seconds)
- Network timeout (60-600 seconds)

**Advanced Settings**:
- GuestFS backend (VMCraft vs libguestfs)
- Debug mode
- Verbose output

---

## Migration Wizard

### Step-by-Step Walkthrough

#### Step 1: Source Selection

Choose the source of your VMs:

**☁️ VMware vSphere / vCenter**:
- Best for: Production VMware environments
- Requires: Network access to vCenter
- Features: API-based VM browsing and export

**💾 Local VMDK File(s)**:
- Best for: Downloaded VMware disk images
- Requires: Local VMDK files
- Features: Direct file conversion

**🪟 Microsoft Hyper-V**:
- Best for: Hyper-V environments
- Requires: Windows Server with Hyper-V
- Status: Experimental
- Features: VHD/VHDX conversion

**📦 OVA / OVF Package**:
- Best for: Exported VM appliances
- Requires: OVA/OVF files
- Features: Extract and convert from packages

**Selection**:
- Click on desired source card
- Selected source is highlighted
- Click **Next ▶** to proceed

#### Step 2: VM/File Selection

Varies by source type:

**vSphere Source**:
```
┌─ Connect to vSphere ───────────────┐
│ vCenter Server: vcenter.example.com│
│ Username: administrator@vsphere... │
│ Password: ********                 │
│ [Connect & Browse VMs]             │
└────────────────────────────────────┘
```

After connection:
- Browse datacenter hierarchy
- Select VMs from DataTable
- View VM specifications

**Local Source**:
```
┌─ Select VMDK file(s) ──────────────┐
│ VMDK Path: /path/to/vm.vmdk        │
│ [Browse...]                        │
│                                    │
│ 💡 Tip: Multiple files supported  │
└────────────────────────────────────┘
```

**Validation**:
- At least one VM/file must be selected
- Valid paths required
- Click **Next ▶** when ready

#### Step 3: Output Configuration

Configure conversion output:

**Output Format**:
- QCOW2 (Recommended) - KVM/QEMU native format
- RAW - Universal compatibility, larger size
- VDI - VirtualBox format
- VMDK - VMware format (for compatibility)

**Output Directory**:
- Default: `/tmp/hyper2kvm-output`
- Must have sufficient disk space
- Directory created if doesn't exist

**Options**:
- ☑ Enable compression (slower but saves space)

**Advanced**: Click for additional options (quality, cache mode, etc.)

#### Step 4: Offline Fixes

Configure automated fixes for Linux VMs:

**Recommended Fixes**:

1. **☑ Stabilize fstab**
   - Converts device names to UUIDs
   - Prevents boot failures due to device name changes
   - Mode: Stabilize all | Boot only | Disabled

2. **☑ Regenerate initramfs**
   - Injects virtio drivers
   - Ensures kernel can access disk at boot
   - Critical for VMware → KVM migration

3. **☑ Update GRUB configuration**
   - Regenerates bootloader config
   - Uses enhanced chroot for reliability
   - Adapts to new hardware

4. **☑ Fix network configuration**
   - Removes MAC address pinning
   - Allows network to work in new environment
   - Removes VMware-specific settings

5. **☑ Use enhanced chroot** (recommended)
   - Bind-mounts /proc, /dev, /sys
   - Enables proper bootloader regeneration
   - Required for GRUB updates on some distributions

**Info Box**:
```
ℹ️ These fixes ensure VMs boot correctly on KVM
   Recommended for all Linux VMs migrated from VMware/Hyper-V
```

#### Step 5: Review & Confirm

Final review before starting:

```
📋 Review migration configuration

**Source:**
  Type: local
  Path: /home/user/vms/ubuntu.vmdk

**Output:**
  Format: qcow2
  Directory: /tmp/hyper2kvm-output
  Compression: Yes

**Offline Fixes:**
  Stabilize fstab: Yes
  Regenerate initramfs: Yes
  Update GRUB: Yes
  Fix network: Yes

✅ Ready to start migration
   Click 'Start Migration' to begin the conversion process
```

**Actions**:
- **◀ Back** - Return to modify settings
- **🚀 Start Migration** - Begin conversion

---

## VM Browser

### vSphere Browser

#### Connecting to vCenter

1. Click **☁️ vSphere** button
2. Enter connection details:
   - vCenter Server: `vcenter.example.com`
   - Username: `administrator@vsphere.local`
   - Password: (your password)
3. Optional: ☑ Verify SSL certificates
4. Click **Connect & Browse VMs**

#### Browsing VMs

Once connected, you'll see a DataTable:

```
┌─────┬──────────────────┬─────────┬──────┬────────┬─────────┬────────────────┐
│Sel  │ VM Name          │ State   │ CPUs │ Memory │ Disk    │ OS             │
├─────┼──────────────────┼─────────┼──────┼────────┼─────────┼────────────────┤
│[x]  │ web-server-01    │ Running │ 2    │ 4 GB   │ 50 GB   │ Ubuntu 22.04   │
│[ ]  │ database-server  │ Running │ 4    │ 16 GB  │ 500 GB  │ CentOS 8       │
│[x]  │ app-server-03    │ Stopped │ 2    │ 8 GB   │ 100 GB  │ RHEL 9         │
└─────┴──────────────────┴─────────┴──────┴────────┴─────────┴────────────────┘

Selected: 2 VMs    Total size: 150 GB

[Migrate Selected]  [Clear Selection]
```

**Operations**:
- Click row to select/deselect
- Use filters in sidebar (Running, Stopped, Windows, Linux)
- Search box filters by name
- Click **Migrate Selected** when ready

### Local Browser

#### Browsing Files

1. Click **💾 Local** button
2. Enter or browse to base directory
3. Files displayed in table:

```
┌─────┬───────────────────────┬──────────┬─────────────────────┐
│ Sel │ Filename              │ Size     │ Modified            │
├─────┼───────────────────────┼──────────┼─────────────────────┤
│[x]  │ ubuntu-20.04.vmdk     │ 8.5 GB   │ 2026-01-20 14:30    │
│[ ]  │ windows-server.vmdk   │ 40 GB    │ 2026-01-15 09:15    │
│[x]  │ centos-7.vmdk         │ 12 GB    │ 2026-01-18 16:45    │
└─────┴───────────────────────┴──────────┴─────────────────────┘
```

**Features**:
- Automatic size detection
- Modification date sorting
- Multi-file selection
- Batch conversion

---

## Monitoring Migrations

### Real-Time Progress

The Migrations panel shows live updates:

```
┌─ Active Migrations ────────────────────────────────────────────────────┐
│ ID  │ VM Name        │ Status  │Progress│ Stage    │Throughput│ ETA   │
├─────┼────────────────┼─────────┼────────┼──────────┼──────────┼───────┤
│ 001 │ web-server-01  │running  │ 45%    │ convert  │ 120 MB/s │ 5m30s │
│ 002 │ database-srv   │running  │ 78%    │ validate │ 95 MB/s  │ 2m15s │
│ 003 │ app-server-03  │ paused  │ 23%    │ transfer │ 0 MB/s   │ -     │
│ 004 │ backup-server  │complete │ 100%   │ done     │ -        │ 0s    │
│ 005 │ dev-machine    │ failed  │ 23%    │ transfer │ -        │ -     │
└────────────────────────────────────────────────────────────────────────┘

Running: 2  Paused: 1  Completed: 1  Failed: 1  Avg Speed: 107 MB/s
```

### Migration Stages

**Stages in order**:
1. **pending** - Queued, waiting to start
2. **transfer** - Downloading VM (for remote sources)
3. **convert** - Converting disk format
4. **validate** - Verifying conversion integrity
5. **done** - Migration completed successfully
6. **failed** - Migration encountered error

### Controls

**Pause Migration**:
1. Select migration row
2. Click **⏸️ Pause**
3. Transfer pauses at next safe point

**Resume Migration**:
1. Select paused migration
2. Click **▶️ Resume**
3. Migration continues from pause point

**Cancel Migration**:
1. Select migration row
2. Click **🗑️ Cancel**
3. Confirm cancellation
4. Cleanup performed automatically

**View Details**:
1. Select migration row
2. Click **📊 Details**
3. View detailed logs, errors, and metrics

---

## Batch Operations

### Creating Batches

1. Navigate to **🗂️ Batch** tab
2. Click **➕ New Batch**
3. Add VMs to batch (via browser or import)
4. Configure batch settings:
   - Max concurrent migrations (1-8)
   - Retry on failure (yes/no)
   - Email notifications
5. Click **Start Batch**

### Monitoring Batches

```
┌─ Batch Migration Manager ──────────────────────────────────────────────┐
│ ID  │ VM Name        │ Status    │Progress│ Stage   │Throughput│  ETA  │
├─────┼────────────────┼───────────┼────────┼─────────┼──────────┼───────┤
│ 001 │ web-server-01  │ active    │ 45%    │convert  │ 120 MB/s │ 5m30s │
│ 002 │ database-srv   │ active    │ 78%    │validate │ 95 MB/s  │ 2m15s │
│ 003 │ app-server-03  │ queued    │ 0%     │pending  │ -        │ -     │
│ 004 │ backup-server  │ completed │ 100%   │done     │ -        │ 0s    │
│ 005 │ dev-machine    │ failed    │ 23%    │transfer │ -        │ -     │
└────────────────────────────────────────────────────────────────────────┘

Active: 2  Queued: 1  Completed: 1  Failed: 1  Total: 5
```

### Batch Actions

- **Pause Batch**: Pause all active migrations
- **Resume Batch**: Resume all paused migrations
- **Cancel Batch**: Cancel entire batch (with confirmation)
- **Export Report**: Generate CSV/JSON batch report
- **Refresh**: Update display with latest status

---

## Settings Configuration

### Accessing Settings

- Press **Ctrl+S**
- Or click **⚙️ Settings** tab
- Or click **Settings** button from Home

### Configuring Options

Each setting has:
- **Label**: Description of option
- **Input**: Text field, dropdown, or checkbox
- **Help Text**: Explanation below input (gray text)

**Example**:
```
┌─ General Settings ─────────────────────────────────┐
│ Default Output Directory: [/tmp/hyper2kvm-output] │
│ Default directory for converted VM images          │
│                                                     │
│ Log Level: [Info ▼]                                │
│ Verbosity of log messages                          │
│                                                     │
│ ☑ Enable file logging                              │
│ Log File Path: [/tmp/hyper2kvm.log]                │
└─────────────────────────────────────────────────────┘
```

### Saving Settings

1. Modify desired settings
2. Click **Save Settings** (bottom right)
3. Settings persisted to config file
4. Applied to all new operations

**Actions**:
- **Reset to Defaults** - Restore factory settings
- **Cancel** - Discard changes
- **Save Settings** - Persist changes

### Settings Persistence

Settings are saved to:
- `~/.config/hyper2kvm/tui-settings.yaml` (Linux)
- `C:\Users\<user>\AppData\Local\hyper2kvm\tui-settings.yaml` (Windows)

---

## Keyboard Shortcuts

### Global Shortcuts

Available from any panel:

| Shortcut | Action | Description |
|----------|--------|-------------|
| **Ctrl+Q** | Quit | Exit application |
| **F1** | Help | Show help dialog |
| **F2** | Wizard | Open migration wizard |
| **F3** | Browse | Open VM browser |
| **F5** | Refresh | Refresh current view |
| **Ctrl+S** | Settings | Open settings panel |
| **Tab** | Next Tab | Switch to next tab |
| **Shift+Tab** | Prev Tab | Switch to previous tab |

### Panel-Specific Shortcuts

**Wizard**:
- **Enter** - Proceed to next step / Start migration
- **Esc** - Cancel wizard
- **←** / **→** - Navigate steps

**Browser**:
- **Space** - Select/deselect row
- **/** - Focus search box
- **Enter** - Migrate selected

**Migrations**:
- **P** - Pause selected migration
- **R** - Resume selected migration
- **C** - Cancel selected migration
- **D** - View details

**Batch**:
- **N** - New batch
- **E** - Export report

**Settings**:
- **Ctrl+Enter** - Save settings
- **Esc** - Cancel changes

---

## Troubleshooting

### TUI Won't Launch

**Error**: `ModuleNotFoundError: No module named 'textual'`

**Solution**:
```bash
pip install 'hyper2kvm[tui]'
```

### Display Issues

**Problem**: Characters not displaying correctly

**Solutions**:
1. Use modern terminal emulator:
   - iTerm2 (macOS)
   - Windows Terminal
   - GNOME Terminal
   - Alacritty
   - kitty

2. Ensure UTF-8 encoding:
   ```bash
   export LANG=en_US.UTF-8
   export LC_ALL=en_US.UTF-8
   ```

3. Update terminal fonts with Unicode support

### Keyboard Shortcuts Not Working

**Problem**: F-keys or Ctrl+key not responding

**Solutions**:
1. Check terminal emulator settings for key capture
2. Disable conflicting shortcuts in terminal
3. Try alternative terminal emulator
4. Use mouse for navigation as fallback

### vSphere Connection Failed

**Error**: `Connection refused` or `SSL certificate verification failed`

**Solutions**:
1. Verify vCenter hostname/IP is correct
2. Check network connectivity:
   ```bash
   ping vcenter.example.com
   telnet vcenter.example.com 443
   ```
3. Disable SSL verification (in Settings → vSphere)
4. Check credentials are correct
5. Verify vCenter service is running

### Migration Stuck

**Problem**: Progress not advancing

**Solutions**:
1. Check system resources (CPU, memory, disk)
2. View migration details (📊 Details button)
3. Check logs: `/tmp/hyper2kvm.log`
4. Cancel and retry migration
5. Reduce concurrent migrations in Settings

### Performance Issues

**Problem**: TUI slow or laggy

**Solutions**:
1. Reduce refresh rate:
   - Settings → Performance → Refresh interval
2. Limit concurrent operations:
   - Settings → Performance → Max concurrent operations
3. Close other applications
4. Use more powerful terminal emulator
5. Upgrade system resources

---

## Advanced Usage

### Programmatic Control

#### Launch TUI from Python

```python
from hyper2kvm.tui.main_app import run_hyper2kvm_tui

# Launch with default settings
run_hyper2kvm_tui()
```

#### Custom TUI App

```python
from hyper2kvm.core.optional_imports import App, ComposeResult, TabbedContent, TabPane
from hyper2kvm.tui.wizard import MigrationWizard
from hyper2kvm.tui.vm_browser import VMBrowser

class MyCustomApp(App):
    def compose(self) -> ComposeResult:
        with TabbedContent():
            with TabPane("Wizard"):
                yield MigrationWizard()
            with TabPane("Browser"):
                yield VMBrowser()

app = MyCustomApp()
app.run()
```

### Integration with Backend

#### Migration Callbacks

```python
from hyper2kvm.tui.migrations_panel import MigrationsPanel

class IntegratedApp(App):
    def __init__(self, orchestrator):
        super().__init__()
        self.orchestrator = orchestrator
        self.migration_panel = None

    def on_mount(self):
        self.migration_panel = self.query_one(MigrationsPanel)

        # Connect orchestrator callbacks
        self.orchestrator.on_progress(self.on_migration_progress)

    def on_migration_progress(self, migration_id, status, progress):
        # Update TUI display
        self.migration_panel.update_migration(
            migration_id,
            status=status,
            progress=progress
        )
```

### Custom Themes

#### Create Custom Theme

```python
# custom_theme.py
CUSTOM_CSS = """
Screen {
    background: #001122;
}

Header {
    background: #2d5f8d;
    color: white;
}

Tab.-active {
    background: #2d5f8d;
    color: #00ff00;
}

Button {
    background: #2d5f8d;
}

Button:hover {
    background: #3d7fad;
}
"""

# Apply theme
from hyper2kvm.tui.main_app import Hyper2KVMApp

class ThemedApp(Hyper2KVMApp):
    CSS = CUSTOM_CSS

app = ThemedApp()
app.run()
```

### Debugging

#### Enable Debug Mode

```bash
# Environment variable
export HYPER2KVM_DEBUG=1
hyper2kvm-tui

# Command line
hyper2kvm-tui --debug

# In code
from hyper2kvm.tui.main_app import Hyper2KVMApp

app = Hyper2KVMApp()
app.run(debug=True)  # Shows Textual DevTools
```

#### View Textual Inspector

Press **Ctrl+I** (when debug mode enabled) to open Textual DevTools:
- DOM tree viewer
- CSS inspector
- Widget hierarchy
- Event log

---

## Related Documentation

- [TUI Component README](../hyper2kvm/tui/README.md) - Detailed component documentation
- [Migration Workflow](02-Migration-Workflow.md) - Understanding the migration process
- [Offline Fixes](18-Offline-Fixes.md) - Detailed offline fix documentation
- [Enhanced Chroot](24-Enhanced-Chroot.md) - Enhanced chroot bootloader fix
- [Textual Documentation](https://textual.textualize.io/) - Textual framework reference

---

## Feedback and Support

Having issues with the TUI? Want to request features?

- GitHub Issues: https://github.com/ssahani/hyper2kvm/issues
- Documentation: https://github.com/ssahani/hyper2kvm/tree/main/docs
- Examples: https://github.com/ssahani/hyper2kvm/tree/main/examples/tui

---

**Document Info**:
- Version: 1.0
- Last Updated: 2026-01-26
- Status: Production Ready
