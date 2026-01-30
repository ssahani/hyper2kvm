# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/worker/cli.py
"""
Worker CLI Interface.

Provides command-line interface for worker job management:
- worker run <job.json>      - Execute job immediately
- worker submit <job.json>   - Submit job to queue
- worker status <job-id>     - Check job status
- worker events <job-id>     - Stream job events
- worker capabilities        - Show worker capabilities
- worker list                - List jobs
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.live import Live
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from .capabilities import CapabilityLevel, get_detector
from .engine import WorkerEngine
from .events import EventStream, get_event_store
from .schemas import JobSpec, JobState, OperationType
from .state_machine import JobRegistry

console = Console()
logger = logging.getLogger(__name__)


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def worker_cli(verbose: bool):
    """hyper2kvm Worker Job Protocol CLI."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)


@worker_cli.command('run')
@click.argument('job_file', type=click.Path(exists=True))
@click.option('--worker-id', default='cli-worker', help='Worker identifier')
@click.option('--follow', is_flag=True, help='Follow progress in real-time')
def run_job(job_file: str, worker_id: str, follow: bool):
    """Execute a job immediately from job specification file."""
    console.print(f"[bold blue]Loading job specification from:[/bold blue] {job_file}")

    try:
        # Load job spec
        with open(job_file, 'r') as f:
            job_data = json.load(f)

        job_spec = JobSpec(**job_data)
        console.print(f"[green]✓[/green] Loaded job: {job_spec.job_id}")
        console.print(f"  Operation: {job_spec.operation.value}")
        console.print(f"  Image: {job_spec.image.path}")

    except Exception as e:
        console.print(f"[red]✗ Failed to load job specification:[/red] {e}")
        sys.exit(1)

    # Create worker engine
    if follow:
        # Create progress display
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console
        )

        task_id = None

        def on_progress(event):
            nonlocal task_id
            if task_id is None:
                task_id = progress.add_task(
                    event.phase,
                    total=100
                )
            progress.update(
                task_id,
                description=f"{event.phase}: {event.message}",
                completed=event.progress_percent
            )

        with Live(progress, console=console):
            engine = WorkerEngine(
                worker_id=worker_id,
                event_callback=on_progress
            )

            result = engine.execute_job(job_spec)
    else:
        # Simple callback
        def on_progress(event):
            console.print(
                f"[dim]{event.timestamp.strftime('%H:%M:%S')}[/dim] "
                f"[cyan]{event.phase}[/cyan] "
                f"[yellow]{event.progress_percent}%[/yellow] - {event.message}"
            )

        engine = WorkerEngine(
            worker_id=worker_id,
            event_callback=on_progress
        )

        result = engine.execute_job(job_spec)

    # Display result
    console.print()
    if result.status == JobState.COMPLETED:
        console.print(f"[bold green]✓ Job completed successfully![/bold green]")
        console.print(f"  Execution time: {result.metrics.execution_seconds}s")

        if result.outputs:
            if result.outputs.fixed_image:
                console.print(f"  Output image: {result.outputs.fixed_image}")
            if result.outputs.report:
                console.print(f"  Report: {result.outputs.report}")
            if result.outputs.logs:
                console.print(f"  Logs: {result.outputs.logs}")
    else:
        console.print(f"[bold red]✗ Job failed![/bold red]")
        if result.error:
            console.print(f"  Phase: {result.error.phase}")
            console.print(f"  Error: {result.error.message}")

    # Save result
    result_file = Path(job_file).parent / f"{job_spec.job_id}_result.json"
    with open(result_file, 'w') as f:
        f.write(result.model_dump_json(indent=2))
    console.print(f"\n[dim]Result saved to: {result_file}[/dim]")


@worker_cli.command('status')
@click.argument('job_id')
def job_status(job_id: str):
    """Check status of a job."""
    registry = JobRegistry()
    sm = registry.get(job_id)

    if not sm:
        console.print(f"[red]✗ Job not found:[/red] {job_id}")
        sys.exit(1)

    # Create status table
    table = Table(title=f"Job Status: {job_id}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="yellow")

    table.add_row("Current State", sm.current_state.value)
    table.add_row("Is Terminal", "Yes" if sm.is_terminal() else "No")

    # Get latest event
    event_store = get_event_store()
    latest_event = event_store.get_latest_event(job_id)

    if latest_event:
        table.add_row("Latest Phase", latest_event.phase)
        table.add_row("Progress", f"{latest_event.progress_percent}%")
        table.add_row("Latest Message", latest_event.message)
        table.add_row(
            "Last Update",
            latest_event.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        )

    console.print(table)

    # Show state history
    console.print("\n[bold]State History:[/bold]")
    for entry in sm.state_history:
        timestamp = entry.get("timestamp", "unknown")
        if isinstance(timestamp, str):
            try:
                dt = datetime.fromisoformat(timestamp)
                timestamp = dt.strftime("%H:%M:%S")
            except:
                pass

        from_state = entry.get("from_state", "-")
        to_state = entry.get("to_state", entry.get("state", "-"))
        reason = entry.get("reason", "")

        if from_state != "-":
            console.print(
                f"  [dim]{timestamp}[/dim] {from_state} → {to_state} "
                f"[dim]({reason})[/dim]"
            )
        else:
            console.print(
                f"  [dim]{timestamp}[/dim] {to_state} [dim]({reason})[/dim]"
            )


@worker_cli.command('events')
@click.argument('job_id')
@click.option('--follow', '-f', is_flag=True, help='Follow events in real-time')
@click.option('--phase', help='Filter by phase')
def job_events(job_id: str, follow: bool, phase: Optional[str]):
    """Stream progress events for a job."""
    event_store = get_event_store()

    console.print(f"[bold blue]Events for job:[/bold blue] {job_id}")

    if follow:
        console.print("[dim]Following new events (Ctrl+C to stop)...[/dim]\n")

    stream = EventStream(
        job_id=job_id,
        event_store=event_store,
        follow=follow
    )

    try:
        for event in stream:
            if phase and event.phase != phase:
                continue

            timestamp = event.timestamp.strftime("%H:%M:%S.%f")[:-3]
            console.print(
                f"[dim]{timestamp}[/dim] "
                f"[cyan]{event.phase:20}[/cyan] "
                f"[yellow]{event.progress_percent:3}%[/yellow] - "
                f"{event.message}"
            )

            if event.details:
                for key, value in event.details.items():
                    console.print(f"    [dim]{key}: {value}[/dim]")

    except KeyboardInterrupt:
        console.print("\n[dim]Stopped following events[/dim]")
        stream.stop()


@worker_cli.command('capabilities')
@click.option('--json-output', is_flag=True, help='Output as JSON')
@click.option('--detailed', '-d', is_flag=True, help='Show detailed capability level report')
def show_capabilities(json_output: bool, detailed: bool):
    """Show worker capabilities."""
    detector = get_detector()

    mode = detector.detect_execution_mode()
    capabilities = detector.detect_capabilities()
    sys_info = detector.get_system_info()

    # Detect capability level for migration operations
    capability_level = detector.detect_capability_level()
    capability_report = detector.get_capability_level_report(capability_level)

    if json_output:
        output = {
            "execution_mode": mode,
            "capabilities": capabilities,
            "system_info": sys_info,
            "migration_capability_level": capability_report
        }
        console.print_json(data=output)
    else:
        # Migration capability level table
        level_table = Table(title="Migration Capability Level", show_header=False)
        level_table.add_column("Property", style="cyan", width=25)
        level_table.add_column("Value", style="yellow")

        level_name = capability_report['level_name']
        level_desc = capability_report['level_description']

        # Color based on level
        if capability_level == CapabilityLevel.FULL_OFFLINE_FIXES:
            level_color = "green"
            level_icon = "✅"
        elif capability_level == CapabilityLevel.NBD_INSPECTION:
            level_color = "yellow"
            level_icon = "⚠️ "
        else:
            level_color = "red"
            level_icon = "❌"

        level_table.add_row(
            "Detected Level",
            f"[{level_color}]{level_icon} {level_name}[/{level_color}]"
        )
        level_table.add_row("Description", level_desc)
        level_table.add_row(
            "Available Operations",
            f"{len(capability_report['operations'])} operations"
        )

        console.print(level_table)
        console.print()

        # Show detailed information if requested
        if detailed:
            # Operations table
            ops_table = Table(title="Available Operations")
            ops_table.add_column("Operation", style="cyan")

            for op in capability_report['operations']:
                ops_table.add_row(f"✓ {op}")

            console.print(ops_table)
            console.print()

            # Limitations table
            if capability_report['limitations']:
                limit_table = Table(title="Limitations")
                limit_table.add_column("Limitation", style="yellow")

                for limitation in capability_report['limitations']:
                    limit_table.add_row(f"⚠️  {limitation}")

                console.print(limit_table)
                console.print()

            # Recommendations table
            if capability_report['recommendations']:
                rec_table = Table(title="Recommendations")
                rec_table.add_column("Recommendation", style="blue")

                for rec in capability_report['recommendations']:
                    rec_table.add_row(f"💡 {rec}")

                console.print(rec_table)
                console.print()

        # Create capabilities table
        table = Table(title="Worker Capabilities")
        table.add_column("Capability", style="cyan")
        table.add_column("Available", style="yellow")

        table.add_row("Execution Mode", mode)
        table.add_row("", "")  # Separator

        for cap, available in capabilities.items():
            status = "✓ Yes" if available else "✗ No"
            style = "green" if available else "red"
            table.add_row(cap, f"[{style}]{status}[/{style}]")

        console.print(table)

        # System info table
        sys_table = Table(title="System Information")
        sys_table.add_column("Property", style="cyan")
        sys_table.add_column("Value", style="yellow")

        sys_table.add_row("Hostname", sys_info.get("hostname", "unknown"))
        sys_table.add_row("OS", f"{sys_info.get('os', '')} {sys_info.get('os_release', '')}")
        sys_table.add_row("Kernel", sys_info.get("kernel_version", "unknown"))
        sys_table.add_row("Memory", f"{sys_info.get('memory_gb', 0)} GB")
        sys_table.add_row("Disk Space", f"{sys_info.get('disk_space_gb', 0)} GB")

        console.print()
        console.print(sys_table)


@worker_cli.command('list')
@click.option('--state', type=click.Choice([s.value for s in JobState]), help='Filter by state')
def list_jobs(state: Optional[str]):
    """List jobs."""
    registry = JobRegistry()
    state_filter = JobState(state) if state else None

    job_ids = registry.list_jobs(state_filter=state_filter)

    if not job_ids:
        console.print("[yellow]No jobs found[/yellow]")
        return

    # Create jobs table
    table = Table(title=f"Jobs{' (filtered by state: ' + state + ')' if state else ''}")
    table.add_column("Job ID", style="cyan")
    table.add_column("State", style="yellow")
    table.add_column("Progress", style="green")
    table.add_column("Last Update", style="dim")

    event_store = get_event_store()

    for job_id in sorted(job_ids):
        sm = registry.get(job_id)
        if not sm:
            continue

        latest_event = event_store.get_latest_event(job_id)

        progress = f"{latest_event.progress_percent}%" if latest_event else "-"
        last_update = latest_event.timestamp.strftime("%H:%M:%S") if latest_event else "-"

        table.add_row(
            job_id,
            sm.current_state.value,
            progress,
            last_update
        )

    console.print(table)


@worker_cli.command('submit')
@click.argument('job_file', type=click.Path(exists=True))
def submit_job(job_file: str):
    """Submit a job to the queue (placeholder - requires scheduler)."""
    console.print("[yellow]⚠ Job queue not yet implemented[/yellow]")
    console.print("Use 'worker run' to execute jobs immediately")
    console.print("\nPlanned implementation:")
    console.print("  1. Load job specification")
    console.print("  2. Validate against worker capabilities")
    console.print("  3. Submit to queue (Redis/Kafka)")
    console.print("  4. Return job ID for tracking")


def main():
    """Entry point for worker CLI."""
    worker_cli()


if __name__ == '__main__':
    main()
