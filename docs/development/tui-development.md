# TUI Development Guide

**Developer Guide for hyper2kvm Terminal User Interface**

This guide documents the patterns, practices, and architecture of the hyper2kvm TUI built with Textual v0.87.1.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Code Organization](#code-organization)
3. [Established Patterns](#established-patterns)
4. [Widget Update Pattern](#widget-update-pattern)
5. [Selection Management](#selection-management)
6. [Modal Dialogs](#modal-dialogs)
7. [Background Workers](#background-workers)
8. [Testing Guidelines](#testing-guidelines)
9. [Styling Conventions](#styling-conventions)
10. [Future Enhancements](#future-enhancements)

---

## Architecture Overview

The hyper2kvm TUI follows a **component-based architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────┐
│              Main Application (main_app.py)         │
│  ┌──────────────────────────────────────────────┐  │
│  │         TabbedContent (Tab Container)        │  │
│  │  ┌────────────┬──────────┬──────────────┐   │  │
│  │  │  Welcome   │ Wizard   │   Browser    │   │  │
│  │  │   Panel    │  Panel   │    Panel     │   │  │
│  │  ├────────────┼──────────┼──────────────┤   │  │
│  │  │ Migrations │  Batch   │   Settings   │   │  │
│  │  │   Panel    │ Manager  │    Panel     │   │  │
│  │  └────────────┴──────────┴──────────────┘   │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  Backend Integration:                              │
│  ├── MigrationTracker (persistent history)         │
│  ├── MigrationController (process control)         │
│  ├── TUIConfig (settings persistence)              │
│  └── HelpDialog (context-sensitive help)           │
└─────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **Separation of Concerns**: Each panel handles its own UI logic
2. **Persistent Backend**: MigrationTracker and TUIConfig provide state persistence
3. **Process Control**: MigrationController manages migration lifecycle via Unix signals
4. **Reactive Updates**: Background workers refresh statistics every 5 seconds
5. **Graceful Degradation**: All features work without external dependencies

---

## Code Organization

```
hyper2kvm/tui/
├── main_app.py              # Main application and tab management
├── batch_manager.py          # Batch migration manager panel
├── migrations_panel.py       # Active migrations monitoring panel
├── vm_browser.py             # VM selection and browsing panel
├── wizard.py                 # Migration wizard panel
├── settings_panel.py         # Settings configuration panel
├── help_dialog.py            # Modal help dialog (Screen)
├── migration_tracker.py      # Backend: Migration history tracking
├── migration_controller.py   # Backend: Process control (SIGSTOP/SIGCONT/SIGTERM)
├── tui_config.py             # Backend: Settings persistence
└── README.md                 # TUI feature documentation
```

### File Naming Conventions

- **`*_panel.py`**: UI panels that are tabs in the main TabbedContent
- **`*_manager.py`**: Complex UI components with business logic
- **`*_dialog.py`**: Modal screens that overlay the main UI
- **`*_tracker.py`**: Backend state management (persistent)
- **`*_controller.py`**: Backend process/business logic
- **`*_config.py`**: Configuration and settings management

---

## Established Patterns

### 1. Widget Update Pattern

**Use Case**: Dynamically update Static widgets with new values (e.g., statistics counters)

**Pattern**:
```python
def update_stats_display(self, stats: Dict[str, Any]) -> None:
    """Update statistics widgets with new values."""
    # Define widget ID to display text mapping
    stat_widgets = {
        "stat_active": f"Active: {stats.get('active_migrations', 0)}",
        "stat_completed": f"Completed: {stats.get('total_completed', 0)}",
        "stat_failed": f"Failed: {stats.get('total_failed', 0)}",
    }

    # Update each widget safely
    for widget_id, text in stat_widgets.items():
        try:
            widget = self.query_one(f"#{widget_id}", Static)
            widget.update(text)
        except Exception:
            # Widget might not exist yet during initialization
            pass
```

**Key Points**:
- Always use `try/except` to handle widgets that don't exist during initialization
- Use f-strings for formatted text display
- Query widgets by ID using `#widget_id` selector
- Call `.update(text)` to change widget content
- Group all widget updates in a single method for maintainability

**Example Usage** (from `batch_manager.py:306-327`):
```python
stats = self.migration_tracker.get_statistics()
self.update_stats_display(stats)
```

---

### 2. Selection Management Pattern

**Use Case**: Track selected items in a DataTable with checkboxes

**Pattern**:
```python
def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
    """Handle row selection in table."""
    table = event.data_table
    row_key = event.row_key

    try:
        # Get current row data
        row = table.get_row(row_key)
        checkbox = row[0]  # First column is the checkbox

        # Toggle selection state
        if checkbox == "[ ]":
            # Select: Add to selection list
            item_info = {
                "name": row[1],        # Assuming name is in column 1
                "row_key": row_key,
                "size_gb": 50.0,       # Parse from actual data
            }
            self.selected_items.append(item_info)
            table.update_cell(row_key, "Select", "[X]")
        else:
            # Deselect: Remove from selection list
            self.selected_items = [
                item for item in self.selected_items
                if item.get("row_key") != row_key
            ]
            table.update_cell(row_key, "Select", "[ ]")

    except Exception as e:
        self.notify(f"Selection error: {e}", severity="error")

    # Update selection info display
    self.update_selection_info()

def update_selection_info(self) -> None:
    """Update selection counter and size display."""
    total_size = sum(item.get("size_gb", 0) for item in self.selected_items)

    try:
        count_widget = self.query_one("#selection_count", Static)
        count_widget.update(f"Selected: {len(self.selected_items)} items")
    except Exception:
        pass

    try:
        size_widget = self.query_one("#selection_size", Static)
        size_widget.update(f"Total size: {total_size:.1f} GB")
    except Exception:
        pass
```

**Key Points**:
- Store selection state in an instance variable (`self.selected_items`)
- Use row_key as a unique identifier for deselection
- Update table cells with `table.update_cell(row_key, column_key, new_value)`
- Always call `update_selection_info()` after changing selection
- Handle errors gracefully with try/except

**Example Usage** (from `vm_browser.py:266-300`):
```python
self.selected_vms = []  # Initialize in __init__

def on_data_table_row_selected(self, event):
    # Toggle checkbox and manage self.selected_vms list
    ...
```

---

### 3. Modal Dialog Pattern

**Use Case**: Display help, confirmation dialogs, or detailed information overlays

**Pattern**:
```python
from textual.screen import Screen
from textual.containers import Container
from textual.widgets import Static, Button

class CustomDialog(Screen):
    """Modal dialog for displaying information."""

    DEFAULT_CSS = """
    CustomDialog {
        align: center middle;
    }

    .dialog-container {
        width: 80;
        height: 35;
        border: heavy #DE7356;  /* Coral brand color */
        background: $surface;
    }

    .dialog-header {
        height: 3;
        background: #DE7356;
        color: white;
        padding: 1 2;
        text-style: bold;
    }

    .dialog-body {
        height: 1fr;
        padding: 1 2;
        overflow-y: scroll;
    }

    .dialog-footer {
        height: 3;
        background: $surface-darken-1;
        padding: 1 2;
    }
    """

    def __init__(self, title: str, content: str, **kwargs):
        super().__init__(**kwargs)
        self.title = title
        self.content = content

    def compose(self) -> ComposeResult:
        with Container(classes="dialog-container"):
            # Header
            with Container(classes="dialog-header"):
                yield Static(self.title)

            # Body
            with Container(classes="dialog-body"):
                yield Static(self.content)

            # Footer with close button
            with Container(classes="dialog-footer"):
                yield Button("Close", id="btn_close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn_close":
            self.app.pop_screen()

# Usage in main app:
def action_show_dialog(self) -> None:
    """Show custom dialog."""
    self.push_screen(CustomDialog(
        title="🔔 Information",
        content="This is a modal dialog example."
    ))
```

**Key Points**:
- Extend `Screen` class for modal dialogs
- Use `self.app.push_screen()` to display
- Use `self.app.pop_screen()` to close
- Apply coral brand color (#DE7356) to headers
- Make body scrollable with `overflow-y: scroll`
- Include close button in footer

**Example Usage** (from `help_dialog.py:1-340`):
```python
class HelpDialog(Screen):
    def __init__(self, topic: str = "general", **kwargs):
        ...

# In main_app.py:
def action_help(self) -> None:
    self.push_screen(HelpDialog(topic="general"))
```

---

### 4. Background Worker Pattern

**Use Case**: Periodically refresh data without blocking the UI

**Pattern**:
```python
from textual.worker import work
import asyncio

class MyPanel(Container):
    def on_mount(self) -> None:
        """Called when panel is mounted."""
        # Start background worker
        self.update_worker = self.update_stats()

    @work(exclusive=True)
    async def update_stats(self) -> None:
        """Update statistics in the background."""
        while True:
            await asyncio.sleep(5)  # 5 second interval

            try:
                # Reload data from backend
                self.tracker.load()
                stats = self.tracker.get_statistics()

                # Update UI widgets
                self.update_stats_display(stats)

            except Exception as e:
                self.logger.debug(f"Failed to update stats: {e}")
```

**Key Points**:
- Use `@work(exclusive=True)` decorator for background tasks
- Use `await asyncio.sleep()` for non-blocking delays
- Handle exceptions to prevent worker crashes
- Store worker reference if you need to cancel it later
- Use `exclusive=True` to prevent multiple instances

**Example Usage** (from `main_app.py:354-372`):
```python
@work(exclusive=True)
async def update_stats(self) -> None:
    while True:
        await asyncio.sleep(5)
        self.migration_tracker.load()
        self.stats = self.migration_tracker.get_statistics()
        self.refresh_welcome_stats()
```

---

### 5. Backend Integration Pattern

**Use Case**: Persist data and manage application state

#### MigrationTracker (Persistent History)

```python
from hyper2kvm.tui.migration_tracker import (
    MigrationTracker,
    MigrationRecord,
    MigrationStatus,
    create_migration_id,
)

# Initialize tracker
tracker = MigrationTracker(logger=logger)
tracker.load()  # Load from ~/.config/hyper2kvm/migration_history.json

# Create new migration record
migration_id = create_migration_id("my-vm")
record = MigrationRecord(
    id=migration_id,
    vm_name="my-vm",
    source_type="vsphere",
    status=MigrationStatus.RUNNING,
    start_time=datetime.now().isoformat(),
    progress=0.0,
    size_mb=10240.0,
)
tracker.add_migration(record)

# Update migration
tracker.update_migration(migration_id, progress=50.0)

# Get statistics
stats = tracker.get_statistics()
# Returns: total_migrations, active_migrations, completed_today, success_rate, etc.

# Save to disk
tracker.save()
```

#### MigrationController (Process Control)

```python
from hyper2kvm.tui.migration_controller import MigrationController

# Initialize controller with tracker
controller = MigrationController(tracker, logger=logger)

# Register migration process
controller.register_process(migration_id, pid=12345)

# Control operations
controller.pause_migration(migration_id)   # Sends SIGSTOP
controller.resume_migration(migration_id)  # Sends SIGCONT
controller.cancel_migration(migration_id)  # Sends SIGTERM

# Check status
is_running = controller.is_process_running(migration_id)

# Cleanup finished processes
controller.cleanup_finished_processes()
```

#### TUIConfig (Settings Persistence)

```python
from hyper2kvm.tui.tui_config import (
    TUIConfig,
    load_tui_settings,
    save_tui_settings,
)

# Load settings
settings = load_tui_settings(logger=logger)
# Loads from ~/.config/hyper2kvm/tui.json

# Access nested settings with dot notation
log_level = settings.get("general.log_level", "info")
disk_format = settings.get("migration.default_format", "qcow2")

# Modify settings
settings["general"]["log_level"] = "debug"
settings["migration"]["enable_compression"] = True

# Save settings
save_tui_settings(settings, logger=logger)
```

---

## Styling Conventions

### Color Palette

```python
# Brand Colors
CORAL_BRAND = "#DE7356"      # RGB: 222, 115, 86 (Pantone 7416 C)

# Status Colors (Textual defaults)
$success = "#00A000"         # Green for completed/success
$error = "#FF0000"           # Red for failed/error
$warning = "#FFA500"         # Orange for warnings
$text-muted = "#808080"      # Gray for queued/disabled

# Surface Colors (Textual defaults)
$surface = "#1E1E1E"         # Main background
$surface-darken-1 = "#151515"  # Slightly darker
```

### CSS Structure Pattern

```python
DEFAULT_CSS = """
ComponentName {
    height: 100%;
    border: heavy #DE7356;
    background: $surface;
}

.component-header {
    height: 5;
    background: #DE7356;
    color: white;
    padding: 1 2;
    text-style: bold;
}

.component-toolbar {
    height: 4;
    background: $surface-darken-1;
    padding: 0 2;
}

.component-body {
    height: 1fr;
    padding: 1 2;
}

.component-footer {
    height: 5;
    background: $surface-darken-1;
    padding: 1 2;
}
"""
```

### Keyboard Shortcuts

Standard shortcuts across all panels:

- `Ctrl+Q`: Quit application
- `F1`: Show help dialog
- `F2`: Open migration wizard
- `F3`: Browse VMs
- `F5`: Refresh current view
- `Ctrl+S`: Open settings
- `Esc`: Close modals/dialogs

---

## Testing Guidelines

### Unit Testing Pattern

```python
# File: tests/unit/test_tui/test_component.py

from hyper2kvm.tui.component import MyComponent

class TestMyComponent:
    """Test suite for MyComponent."""

    def test_component_creation(self):
        """Test component can be instantiated."""
        component = MyComponent()
        assert component is not None

    def test_component_with_params(self):
        """Test component with custom parameters."""
        component = MyComponent(custom_param="value")
        assert component.custom_param == "value"

    def test_method_behavior(self):
        """Test specific method behavior."""
        component = MyComponent()
        result = component.some_method()
        assert result == expected_value
```

### Test Organization

```
tests/unit/test_tui/
├── test_dashboard.py           # Dashboard tests (11 tests)
├── test_migration_tracker.py   # Migration tracking tests (28 tests)
├── test_tui_availability.py    # TUI import tests (7 tests)
├── test_tui_config.py          # Configuration tests (35 tests)
├── test_tui_fallback.py        # Fallback mode tests (18 tests)
└── test_widgets.py             # Widget tests (21 tests)
```

### Running Tests

```bash
# Run all TUI tests
python3 -m pytest tests/unit/test_tui/ -v

# Run specific test file
python3 -m pytest tests/unit/test_tui/test_migration_tracker.py -v

# Run with coverage
python3 -m pytest tests/unit/test_tui/ --cov=hyper2kvm.tui --cov-report=html
```

---

## Future Enhancements

### Documented Future Work

The following features have implementation notes in the code but are not yet implemented:

#### High Priority

1. **vSphere Connection** (`vm_browser.py`)
   - Requires: pyVmomi library integration
   - Steps: Get credentials → SSL context → SmartConnect() → Store connection
   - Location: `vm_browser.py:318-332`

2. **Migration Wizard Backend Integration** (`wizard.py`)
   - Build config from wizard_data
   - Start migration process (subprocess/thread)
   - Register PID with migration_controller
   - Location: `wizard.py:468-482`

3. **Migration Details Dialog** (`migrations_panel.py`)
   - Create modal screen like HelpDialog
   - Display full migration metadata
   - Show progress history and metrics
   - Location: `migrations_panel.py:287-298`

#### Medium Priority

4. **Batch Creation** (`batch_manager.py`)
   - Option 1: File dialog for manifest selection
   - Option 2: Multi-step wizard for batch creation
   - Location: `batch_manager.py:250-260`

5. **Report Export** (`batch_manager.py`)
   - Support JSON, CSV, HTML, Markdown formats
   - Gather migration data from tracker
   - Save to user-specified location
   - Location: `batch_manager.py:301-316`

6. **Browser Source Switching** (`vm_browser.py`)
   - Dynamic panel recomposition
   - Switch between vSphere/Local/Hyper-V sources
   - Location: `vm_browser.py:302-307`

#### Low Priority

7. **Tab-Specific Refresh** (`main_app.py`)
   - Check active tab via TabbedContent.active
   - Call appropriate refresh method per tab
   - Location: `main_app.py:339-352`

8. **Wizard Step Navigation** (`wizard.py`)
   - Dynamic step content updates
   - Progress indicator highlighting
   - Button state management
   - Location: `wizard.py:458-466`

9. **Button Selection Styling** (`wizard.py`)
   - CSS class management for selected buttons
   - Visual feedback for user selections
   - Location: `wizard.py:432-439`

### Implementation Resources

All future enhancements include:
- Detailed implementation notes in source code comments
- Required libraries and dependencies documented
- Step-by-step implementation guidance
- Integration points identified

Search for `# Note:` comments in TUI source files for implementation details.

---

## Common Development Tasks

### Adding a New Panel

1. Create new file `hyper2kvm/tui/my_panel.py`
2. Extend `Container` class
3. Define `DEFAULT_CSS` with coral branding
4. Implement `compose()` method
5. Add event handlers (`on_button_pressed`, etc.)
6. Register in `main_app.py` TabbedContent

### Adding Backend Integration

1. Define data model (dataclass or TypedDict)
2. Implement persistence (JSON/YAML)
3. Create manager class with CRUD operations
4. Add to panel `__init__` method
5. Integrate with widget updates

### Adding a New Modal Dialog

1. Create class extending `Screen`
2. Define CSS with centered alignment
3. Implement `compose()` with header/body/footer
4. Add close button handler
5. Use `self.app.push_screen()` to display

---

## Troubleshooting

### Common Issues

**Widgets not updating**:
- Check widget IDs match between CSS and query_one()
- Verify widgets exist (use try/except during initialization)
- Ensure update_stats_display() is called after data changes

**Background worker not running**:
- Verify `@work(exclusive=True)` decorator is present
- Check worker is started in `on_mount()`
- Use `await asyncio.sleep()` not `time.sleep()`

**Selection state out of sync**:
- Always call `update_selection_info()` after changing selected_items
- Use row_key for unique identification
- Handle both select and deselect cases

### Debug Tips

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Use Textual's inspector
# Run with: textual run --dev hyper2kvm-tui

# Add debug notifications
self.notify(f"Debug: {variable_value}", severity="information")

# Log to file
logger.debug(f"Component state: {self.__dict__}")
```

---

## Resources

- **Textual Documentation**: https://textual.textualize.io/
- **TUI Source Code**: `hyper2kvm/tui/`
- **TUI Tests**: `tests/unit/test_tui/`
- **TUI README**: `hyper2kvm/tui/README.md`
- **Examples**: `examples/tui/migration_demo.py`

---

**Last Updated**: January 26, 2026
**Version**: 1.0
**Status**: Production-Ready
