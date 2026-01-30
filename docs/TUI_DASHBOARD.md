# Interactive TUI Dashboard

Real-time Terminal User Interface for monitoring VM migrations.

## Overview

The hyper2kvm TUI Dashboard provides a beautiful, interactive terminal interface for monitoring VM migrations in real-time. It displays:

- **Live migration status** with progress bars for each VM
- **Real-time metrics** (throughput, success rate, active migrations)
- **Scrolling log viewer** for migration events
- **Keyboard shortcuts** for easy navigation

## Features

### Real-Time Monitoring
- Live progress bars showing migration completion
- Current stage display (Exporting, Converting, Validating, etc.)
- Throughput metrics in MB/s
- Elapsed time and ETA for each migration

### Metrics Dashboard
- Active migrations count
- Total migrations (successful/failed)
- Success rate percentage
- Average throughput
- Total data processed
- Average migration duration
- Error rate

### Interactive Controls
- **q** - Quit application
- **r** - Refresh display
- **l** - Focus log viewer
- **m** - Focus migrations panel
- **d** - Toggle dark mode

## Installation

Install with TUI support:

```bash
pip install 'hyper2kvm[tui]'
```

Or install all enhancements:

```bash
pip install 'hyper2kvm[enhanced]'
```

## Quick Start

### Run Demo Dashboard

See the TUI in action with simulated migrations:

```bash
python3 examples/tui_dashboard_example.py
```

This demo:
- Simulates 5 VM migrations running in parallel
- Shows realistic progress, throughput, and timing
- Demonstrates all dashboard features
- Occasionally simulates failures (20% chance)

### Integrate with Your Migrations

```python
from hyper2kvm.tui.dashboard import MigrationDashboard
from hyper2kvm.tui.widgets import MigrationStatus

# Create dashboard
app = MigrationDashboard(refresh_interval=1.0)

# Add a migration
migration = MigrationStatus(
    vm_name="web-server-01",
    hypervisor="vmware",
    status="in_progress",
    progress=0.0,
    current_stage="Initializing",
)
app.add_migration(migration)

# Update progress (call this from your migration code)
app.update_migration_progress(
    vm_name="web-server-01",
    progress=0.5,
    stage="Exporting disk",
    throughput_mbps=125.5,
)

# Mark complete
migration.status = "completed"
migration.progress = 1.0
app.add_migration(migration)

# Run dashboard
app.run()
```

## Integration Patterns

### Pattern 1: Callback-Based Integration

Integrate with existing orchestrator using callbacks:

```python
from hyper2kvm.tui.dashboard import MigrationDashboard
from hyper2kvm.tui.widgets import MigrationStatus

class IntegratedDashboard(MigrationDashboard):
    def start_migration(self, vm_config):
        # Create status
        migration = MigrationStatus(
            vm_name=vm_config['vm_name'],
            hypervisor=vm_config['hypervisor'],
            status='in_progress',
            progress=0.0,
            current_stage='Initializing',
        )
        self.add_migration(migration)

        # Create orchestrator with callbacks
        orchestrator = Orchestrator(vm_config)

        # Progress callback
        orchestrator.on_progress = lambda p, s, t: (
            self.update_migration_progress(
                vm_config['vm_name'],
                progress=p,
                stage=s,
                throughput_mbps=t,
            )
        )

        # Completion callback
        orchestrator.on_complete = lambda success, error: (
            self.on_migration_complete(
                vm_config['vm_name'],
                success,
                error,
            )
        )

        # Run migration
        orchestrator.run()
```

### Pattern 2: Event-Based Integration

Integrate with event-driven architecture:

```python
from hyper2kvm.tui.dashboard import MigrationDashboard

class EventDrivenDashboard(MigrationDashboard):
    def on_mount(self):
        super().on_mount()

        # Subscribe to migration events
        event_bus.subscribe('migration.started', self.on_migration_started)
        event_bus.subscribe('migration.progress', self.on_migration_progress)
        event_bus.subscribe('migration.completed', self.on_migration_completed)

    def on_migration_started(self, event):
        migration = MigrationStatus(
            vm_name=event.vm_name,
            hypervisor=event.hypervisor,
            status='in_progress',
            progress=0.0,
            current_stage='Initializing',
        )
        self.add_migration(migration)

    def on_migration_progress(self, event):
        self.update_migration_progress(
            event.vm_name,
            event.progress,
            event.stage,
            event.throughput_mbps,
        )

    def on_migration_completed(self, event):
        if event.vm_name in self._migrations:
            migration = self._migrations[event.vm_name]
            migration.status = 'completed' if event.success else 'failed'
            migration.progress = 1.0 if event.success else migration.progress
            if event.error:
                migration.error = event.error
            self.add_migration(migration)
```

### Pattern 3: Async Integration

Integrate with async/await code:

```python
import asyncio
from hyper2kvm.tui.dashboard import MigrationDashboard

class AsyncDashboard(MigrationDashboard):
    @MigrationDashboard.work(exclusive=False)
    async def run_migration_async(self, vm_config):
        # Create migration status
        migration = MigrationStatus(
            vm_name=vm_config['vm_name'],
            hypervisor=vm_config['hypervisor'],
            status='in_progress',
            progress=0.0,
            current_stage='Initializing',
        )
        self.add_migration(migration)

        try:
            # Run async migration
            async for progress in orchestrator.migrate_async(vm_config):
                migration.progress = progress.percent
                migration.current_stage = progress.stage
                migration.throughput_mbps = progress.throughput
                self.add_migration(migration)

            # Success
            migration.status = 'completed'
            migration.progress = 1.0

        except Exception as e:
            migration.status = 'failed'
            migration.error = str(e)

        finally:
            self.add_migration(migration)
```

## Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ hyper2kvm Migration Dashboard                            12:34:56│
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│ 📦 Active Migrations                                             │
│ ┌───────────────────────────────────────────────────────────┐   │
│ │ 🔄 web-server-01 (vmware) - IN_PROGRESS                   │   │
│ │ Stage: Exporting disk | 65% [█████████████░░░░░░░░░░]    │   │
│ │ Throughput: 120.5 MB/s | Elapsed: 3m 15s | ETA: 1m 45s   │   │
│ └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│ ┌───────────────────────────────────────────────────────────┐   │
│ │ ✅ web-server-02 (vmware) - COMPLETED                     │   │
│ │ Stage: Finalized | 100% [████████████████████]           │   │
│ │ Throughput: 105.0 MB/s | Elapsed: 5m 30s                 │   │
│ └───────────────────────────────────────────────────────────┘   │
│                                                                   │
├────────────────────────────────┬────────────────────────────────┤
│                                 │                                 │
│ 📊 Migration Metrics           │ 📝 Migration Logs               │
│ ──────────────────────         │                                 │
│ Active Migrations:     2       │ [12:30:15] ✅ Dashboard init    │
│ Total Migrations:      10      │ [12:30:20] ℹ️ Started: web-01   │
│ Success Rate:          90.0%   │ [12:32:45] ✅ Completed: web-02 │
│ Avg Throughput:        110 MB/s│ [12:33:10] ℹ️ Progress: web-01  │
│ Data Processed:        50.2 GB │                                 │
│ Avg Duration:          5m 45s  │                                 │
│                                 │                                 │
├────────────────────────────────┴────────────────────────────────┤
│ Last update: 12:34:56 | Active: 2 | Press 'q' to quit            │
└─────────────────────────────────────────────────────────────────┘
```

## Advanced Usage

### Custom Styling

Override CSS to customize appearance:

```python
from hyper2kvm.tui.dashboard import MigrationDashboard

class CustomStyledDashboard(MigrationDashboard):
    CSS = """
    MigrationStatusWidget.in_progress {
        border: solid blue;
    }

    MigrationStatusWidget.completed {
        border: solid green;
    }

    #metrics_widget {
        background: $panel;
    }
    """
```

### Custom Refresh Logic

Override refresh behavior:

```python
class CustomRefreshDashboard(MigrationDashboard):
    def refresh_display(self):
        super().refresh_display()

        # Add custom refresh logic
        self.update_custom_widgets()

    def update_custom_widgets(self):
        # Your custom update logic
        pass
```

### Background Workers

Add background workers for data collection:

```python
class WorkerDashboard(MigrationDashboard):
    @MigrationDashboard.work(exclusive=False)
    async def collect_metrics(self):
        while True:
            await asyncio.sleep(5)

            # Collect metrics from Prometheus
            metrics = await self.fetch_prometheus_metrics()
            self._metrics.update(metrics)
            self.refresh_display()
```

## Troubleshooting

### TUI Not Starting

**Problem:** Dashboard doesn't start or shows import errors.

**Solution:** Ensure Textual is installed:
```bash
pip install 'hyper2kvm[tui]'
```

### Display Issues Over SSH

**Problem:** Characters not rendering correctly over SSH.

**Solution:** Ensure your terminal supports Unicode:
```bash
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
```

### Performance Issues

**Problem:** Dashboard updates slowly with many migrations.

**Solution:** Increase refresh interval:
```python
app = MigrationDashboard(refresh_interval=2.0)  # Slower refresh
```

### Dark Mode Not Working

**Problem:** Dark mode toggle doesn't change colors.

**Solution:** Some terminals don't support all color modes. Try:
```python
app.dark = True  # Force dark mode
```

## Best Practices

1. **Set Appropriate Refresh Interval**
   - Fast refresh (0.5s): For demo/testing
   - Normal refresh (1.0s): For interactive monitoring
   - Slow refresh (2-5s): For many migrations or slow terminals

2. **Limit Active Migrations Displayed**
   - Consider removing completed migrations after a delay
   - Archive old migrations to a separate view

3. **Use Async Workers**
   - Keep UI responsive by using async workers
   - Don't block the main thread

4. **Handle Errors Gracefully**
   - Always wrap migration code in try/except
   - Display clear error messages to users

5. **Log Important Events**
   - Use `log_message()` for user-visible events
   - Use standard logging for debug messages

## Examples

See the `examples/` directory for complete examples:

- `tui_dashboard_example.py` - Demo with simulated migrations
- `tui_integration_example.py` - Integration patterns
- `daemon_with_tui_example.py` - Daemon mode + TUI

## API Reference

### MigrationDashboard

Main TUI application class.

**Constructor:**
```python
MigrationDashboard(refresh_interval: float = 1.0)
```

**Methods:**
- `add_migration(migration: MigrationStatus)` - Add/update migration
- `remove_migration(vm_name: str)` - Remove migration
- `update_migration_progress(...)` - Update progress
- `log_message(message: str, level: str)` - Add log entry
- `refresh_display()` - Force refresh

### MigrationStatus

Dataclass representing migration state.

**Fields:**
- `vm_name: str` - VM name
- `hypervisor: str` - Source hypervisor
- `status: str` - Status (pending/in_progress/completed/failed)
- `progress: float` - Progress (0.0 to 1.0)
- `current_stage: str` - Current stage name
- `throughput_mbps: float` - Throughput in MB/s
- `elapsed_seconds: float` - Elapsed time
- `eta_seconds: Optional[float]` - Estimated time remaining
- `error: Optional[str]` - Error message if failed

## See Also

- [Daemon Mode Documentation](DAEMON_MODE.md)
- [Prometheus Metrics](METRICS.md)
- [Integration Guide](INTEGRATION.md)
