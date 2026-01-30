# TUI (Terminal User Interface) Guides

Interactive terminal interface documentation for Hyper2KVM TUI.

---

## Quick Links

- **[TUI Quickstart](quickstart.md)** - Get started with TUI in 5 minutes
- **[Running the TUI](run-tui.md)** - Installation and execution guide
- **[Dashboard Guide](dashboard.md)** - Complete dashboard reference

---

## TUI Overview

The hyper2kvm TUI (Terminal User Interface) provides a comprehensive, interactive interface for managing VM migrations directly from your terminal. Built with [Textual](https://textual.textualize.io/), it offers a professional, keyboard-driven alternative to CLI commands.

### Key Features

- **🧙 Interactive Wizard**: 5-step guided migration setup
- **📁 Multi-Source Browser**: Browse VMs from vSphere, local storage, or Hyper-V
- **📊 Real-Time Monitoring**: Live migration progress with throughput metrics
- **🗂️ Batch Management**: Handle multiple concurrent migrations
- **⚙️ Comprehensive Settings**: Configure all hyper2kvm options in one place
- **⌨️ Keyboard-Driven**: Full support for keyboard shortcuts

---

## Guide Descriptions

### TUI Quickstart
**File**: [quickstart.md](quickstart.md)

**5-minute guide to TUI**:
- Installation and setup
- Quick start guide
- Interface overview
- Migration wizard walkthrough
- VM browser usage
- Monitoring migrations
- Batch operations
- Settings configuration
- Keyboard shortcuts
- Troubleshooting

**Use when**: First time using TUI, need quick reference

---

### Running the TUI
**File**: [run-tui.md](run-tui.md)

**Installation and execution**:
- Prerequisites
- Installation steps
- Running the TUI
- Configuration options
- Environment setup
- Troubleshooting startup issues

**Use when**: Installing TUI, troubleshooting startup

---

### Dashboard Guide
**File**: [dashboard.md](dashboard.md)

**Complete dashboard reference**:
- Dashboard layout
- Navigation controls
- Widget descriptions
- Status indicators
- Real-time updates
- Customization options

**Use when**: Learning dashboard features, customizing interface

---

## Quick Start

### Install and Run TUI
```bash
# Install with TUI support
pip install "hyper2kvm[full]"

# Launch TUI
hyper2kvm tui

# Or use h2kvmctl
h2kvmctl tui
```

**Documentation**: [TUI Quickstart](quickstart.md) - Installation

---

### Navigation Basics

**Main Menu**:
- `1` - Migration Wizard
- `2` - VM Browser
- `3` - Monitor Migrations
- `4` - Batch Operations
- `5` - Settings
- `q` - Quit

**Universal Shortcuts**:
- `Tab` - Next widget
- `Shift+Tab` - Previous widget
- `Enter` - Activate/Confirm
- `Esc` - Cancel/Back
- `?` - Help

**Documentation**: [TUI Quickstart](quickstart.md) - Keyboard Shortcuts

---

## TUI Workflows

### Workflow 1: Single VM Migration

**Using Migration Wizard**:
1. Launch TUI: `hyper2kvm tui`
2. Select "1 - Migration Wizard"
3. Choose source type (Local/vSphere/Hyper-V)
4. Select source VM
5. Configure output settings
6. Configure fix options
7. Review and start migration
8. Monitor progress in real-time

**Documentation**: [TUI Quickstart](quickstart.md) - Migration Wizard

---

### Workflow 2: Browse and Select VMs

**Using VM Browser**:
1. Launch TUI
2. Select "2 - VM Browser"
3. Choose source (vSphere/Local/Hyper-V)
4. Browse directory structure
5. Preview VM details
6. Queue for migration
7. Return to main menu

**Documentation**: [TUI Quickstart](quickstart.md) - VM Browser

---

### Workflow 3: Monitor Active Migrations

**Using Monitor Dashboard**:
1. Launch TUI
2. Select "3 - Monitor Migrations"
3. View active migrations
4. See progress bars and throughput
5. Check completed migrations
6. Review errors if any

**Documentation**: [Dashboard Guide](dashboard.md)

---

### Workflow 4: Batch Migration

**Using Batch Operations**:
1. Launch TUI
2. Select "4 - Batch Operations"
3. Import batch manifest or create new
4. Configure parallel execution
5. Review VM list
6. Start batch migration
7. Monitor all migrations

**Documentation**: [TUI Quickstart](quickstart.md) - Batch Operations

---

## TUI vs CLI Comparison

| Feature | TUI | CLI |
|---------|-----|-----|
| **Interactive** | ✅ Yes | ❌ No |
| **Visual Feedback** | ✅ Real-time | ⚠️ Logs only |
| **VM Browsing** | ✅ Built-in | ❌ Manual |
| **Progress Monitor** | ✅ Real-time | ⚠️ Log parsing |
| **Multi-Migration** | ✅ Dashboard view | ⚠️ Separate terminals |
| **Learning Curve** | ✅ Guided | ⚠️ Steeper |
| **Automation** | ❌ No | ✅ Yes |
| **Scripting** | ❌ No | ✅ Yes |
| **Remote Use** | ⚠️ SSH OK | ✅ Perfect |

**Recommendation**: Use TUI for interactive work, CLI for automation

---

## TUI Features

### Interactive Wizard

**5-step migration setup**:
1. **Source Selection** - Choose VM source type
2. **VM Selection** - Browse and select VMs
3. **Output Configuration** - Set output format and location
4. **Fix Options** - Configure automated fixes
5. **Review & Execute** - Confirm and start

**Benefits**:
- No need to remember command syntax
- Validation at each step
- Visual preview of configuration
- Easy error correction

---

### Real-Time Monitoring

**Live migration dashboard**:
- Progress bars for each VM
- Throughput metrics (MB/s)
- Elapsed time tracking
- ETA calculation
- Error alerts
- Success/failure counts

**Benefits**:
- Immediate visibility
- Quick issue detection
- Multi-migration overview
- Historical tracking

---

### VM Browser

**Browse multiple sources**:
- **vSphere**: Connect to vCenter/ESXi, browse datastores
- **Local Storage**: Browse local filesystem
- **Hyper-V**: Connect to Hyper-V host, browse VMs

**Features**:
- Tree view navigation
- VM details preview
- Multi-select support
- Quick search/filter

---

### Batch Management

**Handle multiple migrations**:
- Import existing batch manifest
- Create new batch configuration
- Configure parallelism (1-16 concurrent)
- Error handling (continue vs stop)
- Progress tracking for all VMs

---

## Keyboard Shortcuts

### Global
- `q` - Quit application
- `?` - Show help
- `Ctrl+C` - Cancel operation
- `Tab` - Next field
- `Shift+Tab` - Previous field

### Navigation
- `↑/↓` - Move up/down in lists
- `←/→` - Navigate tabs
- `Enter` - Select/Confirm
- `Esc` - Back/Cancel
- `/` - Search (in VM browser)

### Migration Control
- `s` - Start migration
- `p` - Pause migration
- `r` - Resume migration
- `c` - Cancel migration
- `d` - View details

**Full list**: [TUI Quickstart](quickstart.md) - Keyboard Shortcuts

---

## Installation

### Prerequisites
```bash
# Install Python 3.8+
python3 --version

# Install hyper2kvm with TUI support
pip install "hyper2kvm[full]"
```

### Launch TUI
```bash
# Using hyper2kvm command
hyper2kvm tui

# Using h2kvmctl command
h2kvmctl tui

# With custom config
hyper2kvm tui --config tui-settings.yaml
```

**Documentation**: [Running the TUI](run-tui.md)

---

## Configuration

### TUI Settings File

**Create `~/.hyper2kvm/tui-settings.yaml`**:
```yaml
tui:
  theme: dark  # or light
  refresh_rate: 1  # seconds
  max_concurrent: 4
  default_source: vsphere
  vsphere:
    host: vcenter.example.com
    user: administrator@vsphere.local
  output:
    default_format: qcow2
    default_dir: /vms/migrated
```

**Documentation**: [TUI Quickstart](quickstart.md) - Settings Configuration

---

## Troubleshooting

### TUI Won't Start

**Issue**: Terminal compatibility problems

**Solution**:
```bash
# Check terminal
echo $TERM

# Try with different TERM
TERM=xterm-256color hyper2kvm tui

# Install terminal dependencies
pip install "textual[dev]"
```

---

### Slow Performance

**Issue**: TUI feels sluggish

**Solution**:
- Increase refresh rate in settings
- Reduce concurrent migrations
- Check system resources
- Use SSH compression if remote

---

### Display Issues

**Issue**: Characters not rendering correctly

**Solution**:
```bash
# Use UTF-8 locale
export LC_ALL=en_US.UTF-8

# Update terminal emulator
# Use modern terminal (iTerm2, Windows Terminal, Alacritty)
```

**Full troubleshooting**: [TUI Quickstart](quickstart.md) - Troubleshooting

---

## Integration with Other Tools

### With CLI
```bash
# Start migration with CLI, monitor with TUI
hyper2kvm --config migration.yaml &
hyper2kvm tui  # Opens monitoring view
```

### With Daemon
```bash
# Run daemon, use TUI as control interface
sudo systemctl start hyper2kvm-daemon
h2kvmctl tui  # Connect to daemon
```

### With API
```bash
# TUI can connect to REST API endpoint
hyper2kvm tui --api-url http://localhost:8080
```

---

## Related Documentation

### Getting Started
- **[Installation Guide](../../getting-started/01-Installation.md)** - Install Hyper2KVM
- **[Quick Start](../../getting-started/02-Quick-Start.md)** - First migration
- **[Beginner Tutorial](../../tutorials/01-beginner-migration.md)** - Step-by-step

### CLI Documentation
- **[CLI Reference](../cli/reference.md)** - Command-line interface
- **[h2kvmctl Guide](../cli/h2kvmctl-guide.md)** - kubectl-style CLI

### Guides
- **[Migration Guides](../migration/)** - Migration workflows
- **[Operational Guides](../operations/)** - Production operations

---

## Summary

**3 comprehensive TUI guides** covering:
- ✅ TUI quickstart and keyboard shortcuts
- ✅ Installation and execution guide
- ✅ Complete dashboard reference

**Features**: Interactive wizard, VM browser, real-time monitoring, batch management

---

**Last Updated**: February 2026
**Documentation Version**: 2.1.0
**TUI Status**: Production Ready

**Quick Navigation**: [Guides Hub](../README.md) | [Documentation Hub](../../index.md) | [CLI Guides](../cli/)
