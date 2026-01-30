#!/usr/bin/env python3
"""
Show a preview of the TUI components and orange theme.
"""

from hyper2kvm.tui.widgets import MigrationStatus, MigrationStatusWidget, MetricsWidget
from hyper2kvm.tui import get_dashboard_type

print("=" * 80)
print("hyper2kvm TUI Preview - Orange Theme".center(80))
print("=" * 80)
print()

# Show dashboard type
dashboard_type = get_dashboard_type()
print(f"🎯 Dashboard Type: {dashboard_type.upper()}")
print()

# Show orange theme color palette
print("🎨 Orange Theme Color Palette:")
print("-" * 80)
colors = [
    ("Bright Orange", "#ff6600", "Headers and key highlights"),
    ("Gold-Orange", "#ffaa44", "Border titles and accents"),
    ("Light Orange", "#ffbb66", "Primary text content"),
    ("Medium Orange", "#ff7722", "Borders and separators"),
    ("Light Orange-Yellow", "#ffcc66", "Status bar text"),
    ("Deep Dark Brown", "#1a0f00", "Screen background"),
    ("Dark Orange-Brown", "#261500", "Container backgrounds"),
    ("Medium Dark Brown", "#331a00", "Widget backgrounds"),
]

for name, hex_code, usage in colors:
    print(f"  {name:20} {hex_code:10} - {usage}")
print()

# Show migration status examples
print("📦 Migration Status Examples:")
print("-" * 80)

migrations = [
    MigrationStatus(
        vm_name="web-server-01",
        hypervisor="vmware",
        status="in_progress",
        progress=0.45,
        current_stage="export",
        throughput_mbps=150.5,
        elapsed_seconds=120.0,
    ),
    MigrationStatus(
        vm_name="database-server",
        hypervisor="vmware",
        status="completed",
        progress=1.0,
        current_stage="complete",
        throughput_mbps=180.2,
        elapsed_seconds=300.0,
    ),
    MigrationStatus(
        vm_name="app-server-03",
        hypervisor="azure",
        status="failed",
        progress=0.3,
        current_stage="convert",
        throughput_mbps=0.0,
        elapsed_seconds=45.0,
        error="Disk conversion failed: Invalid format",
    ),
    MigrationStatus(
        vm_name="backup-server",
        hypervisor="hyperv",
        status="pending",
        progress=0.0,
        current_stage="initializing",
        throughput_mbps=0.0,
        elapsed_seconds=0.0,
    ),
]

for migration in migrations:
    # Status symbol
    status_symbol = {
        "pending": "⏳",
        "in_progress": "🔄",
        "completed": "✅",
        "failed": "❌",
    }.get(migration.status, "❓")

    # Progress bar
    progress_pct = int(migration.progress * 100)
    filled = int(migration.progress * 30)
    empty = 30 - filled
    progress_bar = f"[{'█' * filled}{'░' * empty}]"

    print(f"\n  {status_symbol} {migration.vm_name} ({migration.hypervisor}) - {migration.status.upper()}")
    print(f"     Stage: {migration.current_stage} | {progress_pct:3}% {progress_bar}")

    if migration.throughput_mbps > 0:
        print(f"     Throughput: {migration.throughput_mbps:.1f} MB/s | Elapsed: {migration.elapsed_seconds:.0f}s")

    if migration.error:
        print(f"     ❌ Error: {migration.error}")

print()
print()

# Show metrics example
print("📊 Metrics Dashboard Preview:")
print("-" * 80)

metrics = {
    "active_migrations": 1,
    "total_migrations": 4,
    "successful_migrations": 1,
    "failed_migrations": 1,
    "avg_throughput_mbps": 165.35,
    "avg_duration_seconds": 172.5,
    "total_bytes_processed": 5368709120,  # 5 GB
}

print(f"""
  Active Migrations:     {metrics['active_migrations']}
  Total Migrations:      {metrics['total_migrations']} (✅ {metrics['successful_migrations']} | ❌ {metrics['failed_migrations']})
  Success Rate:          {(metrics['successful_migrations'] / metrics['total_migrations']) * 100:.1f}%
  Avg Throughput:        {metrics['avg_throughput_mbps']:.1f} MB/s
  Data Processed:        {metrics['total_bytes_processed'] / (1024**3):.2f} GB
  Avg Duration:          {int(metrics['avg_duration_seconds'] / 60)}m {int(metrics['avg_duration_seconds'] % 60)}s
""")

print()
print("🎮 Keyboard Shortcuts:")
print("-" * 80)

if dashboard_type == "textual":
    shortcuts = [
        ("q", "Quit application"),
        ("r", "Refresh display"),
        ("l", "Focus log viewer"),
        ("m", "Focus migrations panel"),
        ("d", "Toggle dark mode"),
    ]
elif dashboard_type == "curses":
    shortcuts = [
        ("q", "Quit application"),
        ("r", "Refresh display"),
        ("UP/DOWN", "Scroll logs"),
    ]
else:
    shortcuts = [
        ("Ctrl+C", "Quit application"),
    ]

for key, description in shortcuts:
    print(f"  {key:10} - {description}")

print()
print()

# Show ASCII mockup of the TUI
print("🖼️  TUI Layout Preview:")
print("=" * 80)

layout = """
╔══════════════════════════════════════════════════════════════════════════════╗
║             hyper2kvm Migration Dashboard | 14:23:45                         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  📦 Active Migrations                                                        ║
║  ┌────────────────────────────────────────────────────────────────────────┐ ║
║  │ 🔄 web-server-01 (vmware) - IN_PROGRESS                                │ ║
║  │ Stage: export | 45% [█████████████░░░░░░░░░░░░░░░░░]                  │ ║
║  │ Throughput: 150.5 MB/s | Elapsed: 2m 0s                                │ ║
║  └────────────────────────────────────────────────────────────────────────┘ ║
║                                                                              ║
║  ┌─────────────────────────────┐ ┌──────────────────────────────────────┐  ║
║  │ 📊 Migration Metrics        │ │ 📝 Migration Logs                    │  ║
║  │ ─────────────────────────── │ │ ──────────────────────────────────── │  ║
║  │ Active Migrations:     1    │ │ [14:23:30] ✅ Dashboard initialized  │  ║
║  │ Total Migrations:      4    │ │ [14:23:35] ⏳ Waiting for migrations │  ║
║  │ Success Rate:       25.0%   │ │ [14:23:40] 🔄 web-server-01: export │  ║
║  │ Avg Throughput:  165.4 MB/s │ │ [14:23:42] 📊 Metrics updated        │  ║
║  │ Data Processed:     5.00 GB │ │ [14:23:45] 🔄 Progress: 45%          │  ║
║  └─────────────────────────────┘ └──────────────────────────────────────┘  ║
║                                                                              ║
║  Last update: 14:23:45 | Active migrations: 1 | Press 'q' to quit           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  q Quit │ r Refresh │ l Logs │ m Migrations │ d Dark Mode                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

print(layout)

print()
print("💡 To run the interactive TUI:")
print("-" * 80)
print("  python examples/tui_demo.py")
print()
print("  Or in your code:")
print("  >>> from hyper2kvm.tui import run_dashboard")
print("  >>> run_dashboard()")
print()
print("=" * 80)
