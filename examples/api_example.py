#!/usr/bin/env python3
"""
Example: Using the hyper2kvm Worker Job Protocol REST API.

This demonstrates:
1. Starting the API server
2. Submitting jobs via HTTP
3. Monitoring progress via SSE
4. Worker registration
5. Job queue management

Requirements:
    pip install -r requirements-api.txt

Usage:
    # Terminal 1: Start API server
    python examples/api_example.py server

    # Terminal 2: Submit a job
    python examples/api_example.py submit

    # Terminal 3: Monitor progress
    python examples/api_example.py monitor <job-id>
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import httpx
from rich.console import Console
from rich.live import Live
from rich.table import Table

console = Console()

API_BASE_URL = "http://localhost:8000"


# ============================================================================
# Server Mode - Start API Server
# ============================================================================

def start_server():
    """Start the FastAPI server."""
    import uvicorn

    console.print("[bold green]Starting hyper2kvm Worker API server...")
    console.print(f"[cyan]API Documentation: {API_BASE_URL}/docs")
    console.print(f"[cyan]ReDoc: {API_BASE_URL}/redoc")
    console.print()

    uvicorn.run(
        "hyper2kvm.worker.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )


# ============================================================================
# Client Mode - Submit Job
# ============================================================================

async def submit_job(job_file: Optional[str] = None):
    """Submit a job to the API."""
    # Create example job spec if no file provided
    if job_file:
        with open(job_file) as f:
            job_spec = json.load(f)
    else:
        job_spec = {
            "job_id": f"demo-job-{asyncio.get_event_loop().time():.0f}",
            "operation": "convert",
            "image": {
                "path": "/tmp/example.vmdk",
                "format": "vmdk",
            },
            "parameters": {
                "output_format": "qcow2",
                "compress": True,
            },
            "execution_policy": {
                "timeout_seconds": 3600,
                "retry_count": 3,
                "priority": 75,
                "idempotent": True,
            },
            "audit_info": {
                "requested_by": "api_example",
                "tags": ["demo", "example"],
            },
        }

    console.print("[bold cyan]Submitting job...")
    console.print(f"Job ID: [yellow]{job_spec['job_id']}")

    async with httpx.AsyncClient() as client:
        try:
            # Submit job
            response = await client.post(
                f"{API_BASE_URL}/jobs",
                json=job_spec,
                params={"queue": True},  # Add to queue
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()

            console.print("\n[bold green]✓ Job submitted successfully!")
            console.print(f"Job ID: [yellow]{result['job_id']}")
            console.print(f"State: [cyan]{result['state']}")
            console.print(f"Queue Position: [magenta]{result.get('queue_position', 'N/A')}")

            return result["job_id"]

        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Error submitting job: {e}")
            return None


# ============================================================================
# Client Mode - Monitor Progress
# ============================================================================

async def monitor_job(job_id: str):
    """Monitor job progress using SSE streaming."""
    console.print(f"[bold cyan]Monitoring job: [yellow]{job_id}")
    console.print("[dim]Press Ctrl+C to stop\n")

    async with httpx.AsyncClient() as client:
        try:
            # Get initial status
            response = await client.get(f"{API_BASE_URL}/jobs/{job_id}")
            if response.status_code == 404:
                console.print(f"[bold red]✗ Job {job_id} not found")
                return

            status = response.json()
            console.print(f"Current State: [cyan]{status['state']}")
            console.print()

            # Stream progress events (using polling for simplicity)
            # In production, use SSE client or WebSocket
            last_timestamp = None

            while True:
                # Poll for new events
                params = {}
                if last_timestamp:
                    params["since"] = last_timestamp

                response = await client.get(
                    f"{API_BASE_URL}/jobs/{job_id}/events",
                    params=params,
                )

                events = response.json()

                if events:
                    # Display new events
                    for event in events:
                        timestamp = event.get("timestamp", "")
                        phase = event.get("phase", "unknown")
                        percentage = event.get("percentage", 0)
                        message = event.get("message", "")

                        console.print(
                            f"[dim]{timestamp[:19]}[/] "
                            f"[cyan]{phase:12}[/] "
                            f"[yellow]{percentage:3d}%[/] "
                            f"{message}"
                        )

                        last_timestamp = timestamp

                # Check if job is complete
                response = await client.get(f"{API_BASE_URL}/jobs/{job_id}")
                status = response.json()
                state = status["state"]

                if state in ["COMPLETED", "FAILED", "CANCELLED"]:
                    console.print(f"\n[bold]Job finished with state: [cyan]{state}")
                    break

                # Wait before next poll
                await asyncio.sleep(2)

        except KeyboardInterrupt:
            console.print("\n[yellow]Monitoring stopped")
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Error monitoring job: {e}")


# ============================================================================
# Client Mode - Register Worker
# ============================================================================

async def register_worker():
    """Register a worker with the API."""
    console.print("[bold cyan]Registering worker...")

    # Detect worker capabilities
    from hyper2kvm.worker.capabilities import CapabilityDetector

    detector = CapabilityDetector()
    capabilities = detector.detect()

    # Convert to dict for HTTP transport
    caps_dict = capabilities.model_dump()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_BASE_URL}/workers/register",
                json=caps_dict,
                timeout=10.0,
            )
            response.raise_for_status()
            result = response.json()

            console.print("\n[bold green]✓ Worker registered successfully!")
            console.print(f"Worker ID: [yellow]{result['worker_id']}")
            console.print(f"Capabilities: [cyan]{', '.join(result['capabilities'])}")

            return result["worker_id"]

        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Error registering worker: {e}")
            return None


# ============================================================================
# Client Mode - List Jobs
# ============================================================================

async def list_jobs():
    """List all jobs."""
    console.print("[bold cyan]Listing jobs...")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_BASE_URL}/jobs")
            response.raise_for_status()
            result = response.json()

            if result["total"] == 0:
                console.print("[yellow]No jobs found")
                return

            # Create table
            table = Table(title=f"Jobs ({result['total']} total)")
            table.add_column("Job ID", style="cyan")
            table.add_column("State", style="yellow")
            table.add_column("Created At", style="dim")

            for job in result["jobs"]:
                table.add_row(
                    job["job_id"],
                    job["state"],
                    job.get("created_at", "N/A")[:19] if job.get("created_at") else "N/A",
                )

            console.print(table)

        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Error listing jobs: {e}")


# ============================================================================
# Client Mode - Health Check
# ============================================================================

async def health_check():
    """Check API health."""
    console.print("[bold cyan]Checking API health...")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_BASE_URL}/health", timeout=5.0)
            response.raise_for_status()
            health = response.json()

            console.print("\n[bold green]✓ API is healthy")
            console.print(f"Version: [cyan]{health['version']}")
            console.print(f"Workers: [yellow]{health['workers']}")
            console.print(f"Active Jobs: [magenta]{health['active_jobs']}")

        except httpx.ConnectError:
            console.print("[bold red]✗ API server is not running")
            console.print(f"[dim]Start the server with: python {__file__} server")
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Error checking health: {e}")


# ============================================================================
# Main CLI
# ============================================================================

async def async_main():
    """Main async entry point."""
    if len(sys.argv) < 2:
        console.print("[bold]Usage:")
        console.print("  python api_example.py server              - Start API server")
        console.print("  python api_example.py health              - Check API health")
        console.print("  python api_example.py submit [job.json]   - Submit a job")
        console.print("  python api_example.py monitor <job-id>    - Monitor job progress")
        console.print("  python api_example.py register            - Register worker")
        console.print("  python api_example.py list                - List all jobs")
        sys.exit(1)

    command = sys.argv[1]

    if command == "server":
        start_server()
    elif command == "health":
        await health_check()
    elif command == "submit":
        job_file = sys.argv[2] if len(sys.argv) > 2 else None
        job_id = await submit_job(job_file)
        if job_id:
            console.print(f"\n[dim]Monitor with: python {__file__} monitor {job_id}")
    elif command == "monitor":
        if len(sys.argv) < 3:
            console.print("[bold red]✗ Please provide job ID")
            sys.exit(1)
        await monitor_job(sys.argv[2])
    elif command == "register":
        worker_id = await register_worker()
        if worker_id:
            console.print(f"\n[dim]Worker registered successfully")
    elif command == "list":
        await list_jobs()
    else:
        console.print(f"[bold red]✗ Unknown command: {command}")
        sys.exit(1)


def main():
    """Main entry point."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
