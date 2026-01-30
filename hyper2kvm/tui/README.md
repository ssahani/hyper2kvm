# hyper2kvm TUI - Terminal User Interface

Comprehensive Terminal User Interface for hyper2kvm VM migration management.

## Features

### 6-Panel Interface

1. **🏠 Home** - Welcome dashboard with migration statistics and quick actions
2. **🧙 Wizard** - Interactive 5-step migration wizard
3. **📁 Browse** - VM browser for vSphere, local, and Hyper-V sources
4. **📊 Migrations** - Real-time monitoring of active migrations
5. **🗂️ Batch** - Batch migration management with statistics
6. **⚙️ Settings** - Configuration panel for all hyper2kvm options

## Installation

Install with TUI support:

```bash
pip install 'hyper2kvm[tui]'
```

Or install with all optional dependencies:

```bash
pip install 'hyper2kvm[full]'
```

## Usage

### Launch the TUI

```bash
hyper2kvm-tui
```

Or run as Python module:

```bash
python -m hyper2kvm.tui.main_app
```

### Keyboard Shortcuts

- **Ctrl+Q**: Quit application
- **F1**: Show help
- **F2**: Open migration wizard
- **F3**: Browse VMs
- **F5**: Refresh current view
- **Ctrl+S**: Open settings
- **Tab**: Switch between panels

## Components

### Migration Wizard (`wizard.py`)

5-step guided migration setup:

1. **Source Selection**: Choose from vSphere, local VMDK, Hyper-V, or OVA
2. **VM/File Selection**: Browse and select VMs or disk images
3. **Output Configuration**: Set format, directory, compression
4. **Offline Fixes**: Configure fstab, initramfs, GRUB, network fixes
5. **Review & Start**: Confirm settings and launch migration

Features:
- Visual progress indicator
- Step validation
- Back/Next navigation
- Context-sensitive help

### VM Browser (`vm_browser.py`)

Multi-source VM browsing:

- **vSphere**: Connect to vCenter and browse datacenter
- **Local**: Browse local filesystem for VMDK files
- **Hyper-V**: Browse Hyper-V VMs (experimental)

Features:
- DataTable display with sortable columns
- Multiple VM selection
- Size estimation
- Filters (running, stopped, OS type)
- Batch selection

### Migrations Panel (`migrations_panel.py`)

Real-time migration monitoring:

- Live status updates
- Progress bars with percentage
- Throughput metrics (MB/s)
- ETA calculations
- Stage tracking (convert, validate, transfer)

Controls:
- Pause/Resume migrations
- Cancel migrations
- View detailed logs
- Export reports

### Batch Manager (`batch_manager.py`)

Manage multiple concurrent migrations:

- Queue management
- Parallel execution control
- Aggregate statistics
- Export batch reports
- Retry failed migrations

Statistics:
- Active migrations
- Queued migrations
- Completed count
- Failed count
- Success rate

### Settings Panel (`settings_panel.py`)

Configure all hyper2kvm options:

**General Settings**:
- Default output directory
- Log level and file logging
- Log file path

**Migration Settings**:
- Default output format (QCOW2, RAW, VDI, VMDK)
- Compression enabled
- Parallel migrations
- Skip existing files

**vSphere Settings**:
- Default vCenter host
- Username
- Save credentials (encrypted)
- Verify SSL certificates

**Offline Fixes Settings**:
- fstab stabilization mode
- Regenerate initramfs
- Update GRUB
- Fix network configuration
- Enhanced chroot

**Performance Settings**:
- Max concurrent operations
- Operation timeout
- Network timeout

**Advanced Settings**:
- GuestFS backend (VMCraft vs libguestfs)
- Debug mode
- Verbose output

## Theme

Professional dark theme with orange accents:
- Primary color: Orange (#ff6600)
- Accent color: Gold-orange (#ffaa44)
- Background: Dark surface
- Success: Green
- Error: Red
- Warning: Yellow

## Architecture

### Main Application (`main_app.py`)

- `Hyper2KVMApp`: Main application class
  - Tabbed interface using `TabbedContent`
  - Welcome screen with statistics
  - Global keyboard shortcuts
  - Background statistics updates

### Component Communication

Components communicate via:
- Event handlers (`on_button_pressed`, `on_data_table_row_selected`)
- Notifications (`self.notify()`)
- Shared state (to be implemented)
- Message passing (to be implemented)

### Backend Integration (TODO)

Currently, components have placeholder TODOs for:
- vSphere connection
- File browsing
- Migration launching
- Progress monitoring
- Statistics collection

These will be integrated with the existing hyper2kvm backend.

## Development

### Adding New Components

1. Create new file in `hyper2kvm/tui/`
2. Subclass `Container` (not `App`)
3. Define `DEFAULT_CSS` for styling
4. Implement `compose()` method
5. Add event handlers
6. Import and use in `main_app.py`

Example:

```python
from ..core.optional_imports import TEXTUAL_AVAILABLE, Container, ComposeResult

class MyPanel(Container):
    DEFAULT_CSS = """
    MyPanel {
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("My Panel Content")
```

### Testing the TUI

```bash
# Run the TUI
hyper2kvm-tui

# Run with verbose logging
HYPER2KVM_LOG_LEVEL=DEBUG hyper2kvm-tui
```

### Styling Guidelines

- Use Textual CSS syntax
- Follow existing color scheme (orange theme)
- Use consistent spacing (padding, margin)
- Make components responsive
- Test in different terminal sizes

## Roadmap

### v0.2 (Current)
- ✅ Main application structure
- ✅ All 6 panels implemented
- ✅ Basic UI and navigation
- ⏳ Backend integration (in progress)

### v0.3 (Next)
- [ ] Live migration progress updates
- [ ] vSphere connection implementation
- [ ] File browser implementation
- [ ] Settings persistence
- [ ] Help dialogs

### v0.4 (Future)
- [ ] Advanced filtering
- [ ] Migration templates
- [ ] Scheduled migrations
- [ ] Email notifications
- [ ] Export to CSV/JSON

## Troubleshooting

### TUI won't start

Check Textual installation:
```bash
python -c "import textual; print(textual.__version__)"
```

Should show version 0.47.0 or higher.

### Display issues

Try different terminal emulators:
- Recommended: iTerm2 (macOS), Windows Terminal, GNOME Terminal
- Works: Most modern terminals with 256-color support
- May have issues: Basic terminals without Unicode support

### Keyboard shortcuts not working

Check terminal emulator settings:
- Ensure F-keys are not captured by the terminal
- Check if Ctrl+Q is captured by terminal
- Try alternative terminals

## References

- [Textual Documentation](https://textual.textualize.io/)
- [hyper2kvm Documentation](../../docs/00-Index.md)
- [Migration Workflow](../../docs/02-Migration-Workflow.md)
- [Offline Fixes](../../docs/18-Offline-Fixes.md)
