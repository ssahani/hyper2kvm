# How to Run the TUI Dashboard

## Quick Start

### Option 1: Run the Demo (Recommended)

```bash
# From the project root
python examples/tui_demo.py
```

This will automatically:
1. Detect the best available TUI (Textual → Curses → CLI)
2. Show simulated VM migrations with progress
3. Demonstrate the orange theme

### Option 2: Run from Python Code

```python
from hyper2kvm.tui import run_dashboard, get_dashboard_type

# Check which dashboard type will be used
print(f"Dashboard type: {get_dashboard_type()}")

# Run the dashboard (auto-detects best available)
run_dashboard(refresh_interval=1.0)
```

### Option 3: Use Specific Dashboard Type

```python
# 1. Textual Dashboard (Best - requires installation)
from hyper2kvm.tui.dashboard import MigrationDashboard

dashboard = MigrationDashboard(refresh_interval=1.0)
dashboard.run()

# 2. Curses Dashboard (Good - built-in on Unix/Linux)
from hyper2kvm.tui.fallback_dashboard import CursesDashboard

dashboard = CursesDashboard(refresh_interval=1.0)
dashboard.run()

# 3. CLI Dashboard (Basic - works everywhere)
from hyper2kvm.tui.cli_dashboard import CLIDashboard

dashboard = CLIDashboard(refresh_interval=2.0)
dashboard.run()
```

---

## Installation Options

### Minimal (CLI only)
```bash
pip install hyper2kvm
```
This gives you the basic CLI dashboard that works on all platforms.

### Recommended (Textual TUI)
```bash
pip install 'hyper2kvm[tui]'
```
This installs Textual for the best TUI experience with:
- Interactive widgets
- Keyboard shortcuts
- Beautiful orange theme
- Smooth animations

### Full Features
```bash
pip install 'hyper2kvm[full]'
```
Includes TUI + all optional features.

---

## Using the Dashboard in Your Code

### Basic Usage

```python
from hyper2kvm.tui import run_dashboard
from hyper2kvm.tui.types import MigrationStatus

# Create a dashboard instance
if get_dashboard_type() == 'textual':
    from hyper2kvm.tui.dashboard import MigrationDashboard
    dashboard = MigrationDashboard()
elif get_dashboard_type() == 'curses':
    from hyper2kvm.tui.fallback_dashboard import CursesDashboard
    dashboard = CursesDashboard()
else:
    from hyper2kvm.tui.cli_dashboard import CLIDashboard
    dashboard = CLIDashboard()

# Add a migration
migration = MigrationStatus(
    vm_name="web-server-01",
    hypervisor="vmware",
    status="in_progress",
    progress=0.5,
    current_stage="export",
    throughput_mbps=100.0,
    elapsed_seconds=30.0,
)

dashboard.add_migration(migration)

# Update progress
dashboard.update_migration_progress(
    vm_name="web-server-01",
    progress=0.75,
    stage="transfer",
    throughput_mbps=150.0
)

# Log messages
dashboard.log_message("Migration started", "INFO")
dashboard.log_message("Export completed", "SUCCESS")
dashboard.log_message("Network slow", "WARNING")
dashboard.log_message("Connection failed", "ERROR")

# Remove migration when done
dashboard.remove_migration("web-server-01")

# Run the dashboard (blocking)
dashboard.run()
```

### With Background Worker (Textual)

```python
from hyper2kvm.tui.dashboard import MigrationDashboard
from hyper2kvm.tui.types import MigrationStatus
import asyncio

class MyMigrationApp(MigrationDashboard):
    async def on_mount(self):
        """Called when app starts."""
        await super().on_mount()

        # Start your migration worker
        self.migrate_vms()

    @work(exclusive=False)
    async def migrate_vms(self):
        """Background worker for migrations."""
        for i in range(5):
            migration = MigrationStatus(
                vm_name=f"vm-{i}",
                hypervisor="vmware",
                status="in_progress",
                progress=0.0,
                current_stage="export",
            )
            self.add_migration(migration)

            # Simulate progress
            for progress in range(0, 101, 10):
                await asyncio.sleep(0.5)
                self.update_migration_progress(
                    vm_name=f"vm-{i}",
                    progress=progress / 100.0,
                    throughput_mbps=100.0 + (i * 10)
                )

# Run it
app = MyMigrationApp()
app.run()
```

---

## Keyboard Shortcuts

### Textual Dashboard
- `q` - Quit application
- `r` - Refresh display
- `l` - Focus log viewer
- `m` - Focus migrations list
- `d` - Toggle dark mode

### Curses Dashboard
- `q` - Quit application
- `r` - Refresh display
- `↑/↓` - Scroll logs (up/down arrow keys)

### CLI Dashboard
- `Ctrl+C` - Quit application

---

## Testing the TUI

### Run All TUI Tests
```bash
pytest tests/unit/test_tui/ -v
```

### Run Specific Dashboard Tests
```bash
# Test dashboard
pytest tests/unit/test_tui/test_dashboard.py -v

# Test widgets
pytest tests/unit/test_tui/test_widgets.py -v

# Test fallback system
pytest tests/unit/test_tui/test_tui_fallback.py -v
```

---

## Troubleshooting

### Issue: "Textual not found"
**Solution:** Install Textual:
```bash
pip install 'hyper2kvm[tui]'
```

### Issue: Curses crashes on Windows
**Solution:** Install windows-curses:
```bash
pip install windows-curses
```

Or use CLI dashboard which works everywhere.

### Issue: Emoji/Unicode characters show as �
**Solution:** This is expected on old terminals. The TUI automatically falls back to ASCII:
- ⏳ → `[WAIT]`
- 🔄 → `[WORK]`
- ✅ → `[DONE]`
- ❌ → `[FAIL]`

### Issue: Colors not showing
**Solution:** Your terminal may not support ANSI colors. Try:
- Use a modern terminal (Windows Terminal, iTerm2, GNOME Terminal)
- On Windows, use Windows 10+ Terminal
- The TUI automatically detects and disables colors if unsupported

### Issue: Terminal too small
**Solution:** The TUI works best with:
- Minimum: 80 columns × 24 rows
- Recommended: 120 columns × 40 rows

Resize your terminal or use full screen.

---

## Platform Support

| Platform | Textual | Curses | CLI |
|----------|---------|--------|-----|
| Linux | ✅ | ✅ | ✅ |
| macOS | ✅ | ✅ | ✅ |
| Windows 10+ | ✅ | ⚠️* | ✅ |
| Windows <10 | ✅ | ❌ | ✅ |
| SSH | ✅ | ✅ | ✅ |
| CI/CD | ⚠️** | ⚠️** | ✅ |

\* Requires `windows-curses` package
\** Requires TTY, auto-falls back to CLI

---

## Examples

Check the `examples/` directory for more:

1. **tui_demo.py** - Basic demo with simulated migrations
2. **tui_dashboard_example.py** - Textual-specific features
3. **tui_integration_example.py** - Integration with migration code

---

## Orange Theme

All TUI implementations feature a consistent orange theme:

- **Textual**: CSS-based styling with #ff6600 orange
- **Curses**: ANSI color codes (yellow/orange)
- **CLI**: ASCII art with clear structure

The theme provides:
- High contrast for readability
- Consistent visual identity
- Professional appearance
- Accessibility-friendly colors

---

## API Reference

### MigrationStatus

```python
@dataclass
class MigrationStatus:
    vm_name: str              # VM being migrated
    hypervisor: str           # Source hypervisor (vmware, hyperv, etc)
    status: str               # pending, in_progress, completed, failed
    progress: float           # 0.0 to 1.0
    current_stage: str        # export, transfer, convert, validate, etc
    throughput_mbps: float    # Current throughput in MB/s
    elapsed_seconds: float    # Time elapsed since start
    eta_seconds: float        # Estimated time remaining (optional)
    error: str                # Error message if failed (optional)
```

### Dashboard Methods

```python
# Add or update migration
dashboard.add_migration(migration: MigrationStatus) -> None

# Update progress only
dashboard.update_migration_progress(
    vm_name: str,
    progress: float,
    stage: str = "",
    throughput_mbps: float = 0.0
) -> None

# Remove migration
dashboard.remove_migration(vm_name: str) -> None

# Log message
dashboard.log_message(message: str, level: str = "INFO") -> None
# Levels: INFO, WARNING, ERROR, SUCCESS

# Run dashboard (blocking)
dashboard.run() -> None
```

---

For more information, see:
- `docs/TUI_IMPLEMENTATION.md` - Full implementation guide
- `docs/ORANGE_THEME.md` - Theme customization
- `ARCHITECTURE.md` - System architecture
