# TUI Implementation Guide

## Overview

The hyper2kvm TUI (Terminal User Interface) provides real-time monitoring of VM migrations with a beautiful **orange theme**. The implementation includes an intelligent 3-tier fallback system that works on any platform.

## Orange Theme

The TUI features a vibrant orange color scheme:
- **Bright Orange (#ff6600)**: Headers and key highlights
- **Gold-Orange (#ffaa44)**: Borders and accents
- **Light Orange (#ffbb66)**: Primary text
- **Dark Orange-Brown (#261500)**: Backgrounds
- **Success Green**: Completed migrations
- **Error Red**: Failed migrations

## Fallback System

### Tier 1: Textual (Best Experience)

When `textual>=0.47.0` is installed, you get the full-featured TUI:

**Features:**
- Modern, reactive UI with CSS-like styling
- Async/await support for smooth updates
- Interactive widgets (progress bars, data tables, logs)
- Keyboard shortcuts (q, r, l, m, d)
- Scrollable containers
- Real-time metrics dashboard

**Installation:**
```bash
pip install 'hyper2kvm[tui]'
```

**Keyboard Shortcuts:**
- `q` - Quit application
- `r` - Refresh display
- `l` - Focus log viewer
- `m` - Focus migrations panel
- `d` - Toggle dark mode

### Tier 2: Curses (Good Experience)

When Textual is not installed but curses is available (most Unix/Linux/Mac systems):

**Features:**
- Basic TUI using Python's built-in curses library
- No external dependencies needed
- Live updates with color support
- Keyboard navigation
- Lightweight and fast

**Keyboard Shortcuts:**
- `q` - Quit application
- `r` - Refresh display
- `UP/DOWN` - Scroll logs

**Platform Support:**
- ✅ Linux
- ✅ macOS
- ✅ Unix
- ❌ Windows (curses not available by default)

### Tier 3: CLI (Universal Fallback)

When neither Textual nor curses is available (e.g., Windows without curses):

**Features:**
- Simple terminal output that works everywhere
- Periodic screen refresh
- Progress bars using ASCII characters
- Color output where supported
- Works on all platforms including Windows

**Platform Support:**
- ✅ All platforms (Windows, Linux, macOS, etc.)

## Usage

### Basic Usage

The TUI automatically selects the best available implementation:

```python
from hyper2kvm.tui import run_dashboard

# Run with default settings (1 second refresh)
run_dashboard()

# Or customize refresh interval
run_dashboard(refresh_interval=2.0)
```

### Check Dashboard Type

```python
from hyper2kvm.tui import get_dashboard_type

dashboard_type = get_dashboard_type()
print(f"Using: {dashboard_type}")  # 'textual', 'curses', or 'cli'
```

### Using Specific Implementation

#### Textual Dashboard

```python
from hyper2kvm.tui import TEXTUAL_AVAILABLE

if TEXTUAL_AVAILABLE:
    from hyper2kvm.tui.dashboard import MigrationDashboard

    app = MigrationDashboard(refresh_interval=1.0)
    app.run()
else:
    print("Textual not installed. Install with: pip install 'hyper2kvm[tui]'")
```

#### Curses Dashboard

```python
from hyper2kvm.tui.fallback_dashboard import CursesDashboard

dashboard = CursesDashboard(refresh_interval=1.0)
dashboard.run()
```

#### CLI Dashboard

```python
from hyper2kvm.tui.cli_dashboard import CLIDashboard

dashboard = CLIDashboard(refresh_interval=2.0)
dashboard.run()
```

## Programmatic Control

All dashboard implementations support the same interface:

```python
from hyper2kvm.tui.widgets import MigrationStatus

# Create a migration status
migration = MigrationStatus(
    vm_name="web-server-01",
    hypervisor="vmware",
    status="in_progress",
    progress=0.45,
    current_stage="export",
    throughput_mbps=150.5,
    elapsed_seconds=120.0,
)

# Add to dashboard
dashboard.add_migration(migration)

# Update progress
dashboard.update_migration_progress(
    vm_name="web-server-01",
    progress=0.75,
    stage="convert",
    throughput_mbps=180.2,
)

# Log messages
dashboard.log_message("Export completed", "INFO")
dashboard.log_message("Validation failed", "ERROR")
dashboard.log_message("Migration successful", "SUCCESS")

# Remove migration
dashboard.remove_migration("web-server-01")
```

## Migration Status Fields

```python
@dataclass
class MigrationStatus:
    vm_name: str              # Name of the VM
    hypervisor: str           # Source hypervisor (vmware, azure, hyperv)
    status: str               # pending, in_progress, completed, failed
    progress: float           # 0.0 to 1.0
    current_stage: str        # export, transfer, convert, validate, etc.
    throughput_mbps: float    # Current throughput in MB/s
    elapsed_seconds: float    # Time elapsed
    eta_seconds: float        # Estimated time remaining (optional)
    error: str                # Error message if failed (optional)
```

## Metrics Tracked

The dashboard automatically calculates and displays:

- **Active Migrations**: Currently running migrations
- **Total Migrations**: All migrations (active + completed + failed)
- **Success Rate**: Percentage of successful migrations
- **Average Throughput**: Mean throughput across all migrations (MB/s)
- **Data Processed**: Total data transferred (GB)
- **Average Duration**: Mean time to complete migrations
- **Error Rate**: Errors per minute (if applicable)

## Performance Notes

### Textual Dashboard
- Refresh interval: 1 second (default)
- Async updates for smooth performance
- Handles 100+ concurrent migrations efficiently
- Memory efficient with reactive updates

### Curses Dashboard
- Refresh interval: 1 second (default)
- Synchronous updates
- Lightweight, minimal CPU usage
- Best for systems without Textual

### CLI Dashboard
- Refresh interval: 2 seconds (default, to reduce flicker)
- Full screen refresh each update
- Very lightweight
- Works on any system

## Troubleshooting

### "Textual library is required" Error

Install Textual:
```bash
pip install 'hyper2kvm[tui]'
# or
pip install textual>=0.47.0
```

### Curses Not Available on Windows

Windows doesn't include curses by default. Options:

1. Install `windows-curses`:
   ```bash
   pip install windows-curses
   ```

2. Use the CLI fallback (automatic)

3. Install Textual for best experience:
   ```bash
   pip install 'hyper2kvm[tui]'
   ```

### Display Issues

If you see rendering issues:

1. Ensure your terminal supports ANSI colors
2. Try a different terminal emulator
3. Check terminal size (minimum 80x24 recommended)
4. For Textual, ensure terminal supports Unicode

### Performance Issues

If the dashboard feels slow:

1. Increase refresh interval:
   ```python
   run_dashboard(refresh_interval=2.0)  # Update every 2 seconds
   ```

2. Limit number of displayed migrations
3. Use curses or CLI fallback for lower resource usage

## Examples

See the `examples/` directory:

- `tui_demo.py` - Interactive demo with simulated migrations
- `tui_dashboard_example.py` - Integration example
- `tui_integration_example.py` - Full integration with migration pipeline

## Architecture

```
hyper2kvm/tui/
├── __init__.py              # Auto-detection and fallback logic
├── dashboard.py             # Textual implementation (Tier 1)
├── fallback_dashboard.py    # Curses implementation (Tier 2)
├── cli_dashboard.py         # CLI implementation (Tier 3)
└── widgets.py               # Textual widgets and MigrationStatus
```

## Design Philosophy

1. **Zero Configuration**: Works out of the box on any platform
2. **Graceful Degradation**: Best experience when possible, always functional
3. **Consistent API**: Same interface across all implementations
4. **Orange Theme**: Vibrant, energetic color scheme for better UX
5. **Real-time**: Live updates for migration monitoring
6. **Lightweight**: Minimal dependencies, optional enhancements

## Future Enhancements

Potential future additions:
- [ ] WebSocket support for remote monitoring
- [ ] Export metrics to Prometheus
- [ ] Multi-dashboard support (multiple migration sources)
- [ ] Custom themes (blue, green, etc.)
- [ ] Historical data visualization
- [ ] Alert/notification system

## Contributing

To add new features or improve the TUI:

1. Maintain compatibility with all three tiers
2. Update the `MigrationStatus` dataclass if needed
3. Keep the orange theme consistent
4. Add tests for new functionality
5. Update this documentation

## License

LGPL-3.0-or-later
