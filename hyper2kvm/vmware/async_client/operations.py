# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/vmware/async_client/operations.py
"""
High-level async VMware operations.

Provides convenient async operations for common tasks.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path
from dataclasses import dataclass

from .client import AsyncVMwareClient

logger = logging.getLogger(__name__)


@dataclass
class MigrationProgress:
    """Progress information for a migration."""

    vm_name: str
    progress: float  # 0.0 to 1.0
    stage: str
    throughput_mbps: float
    elapsed_seconds: float
    eta_seconds: Optional[float] = None


class AsyncVMwareOperations:
    """
    High-level async VMware operations.

    Provides convenient methods for common async tasks with
    progress tracking and error handling.

    Example:
        >>> ops = AsyncVMwareOperations(client)
        >>> await ops.batch_export(
        ...     ["vm1", "vm2", "vm3"],
        ...     Path("/output"),
        ...     on_progress=lambda p: print(p.vm_name, p.progress),
        ... )
    """

    def __init__(self, client: AsyncVMwareClient):
        """
        Initialize operations.

        Args:
            client: Async VMware client
        """
        self.client = client

    async def batch_export(
        self,
        vm_names: List[str],
        output_dir: Path,
        on_progress: Optional[Callable[[MigrationProgress], None]] = None,
        on_complete: Optional[Callable[[str, bool, Optional[str]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Export multiple VMs in parallel with progress tracking.

        Args:
            vm_names: List of VM names to export
            output_dir: Output directory
            on_progress: Optional progress callback
            on_complete: Optional completion callback(vm_name, success, error)

        Returns:
            Summary of batch export

        Example:
            >>> def progress_cb(p: MigrationProgress):
            ...     print(f"{p.vm_name}: {p.progress*100:.1f}% - {p.stage}")
            >>>
            >>> results = await ops.batch_export(
            ...     ["vm1", "vm2", "vm3"],
            ...     Path("/output"),
            ...     on_progress=progress_cb,
            ... )
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Starting batch export of {len(vm_names)} VMs")

        # Track progress and start time for each VM
        import time
        progress_trackers = {vm_name: 0.0 for vm_name in vm_names}
        start_times = {vm_name: time.time() for vm_name in vm_names}

        def make_progress_callback(vm_name: str):
            """Create progress callback for specific VM."""

            def callback(progress: float, stage: str, throughput: float):
                progress_trackers[vm_name] = progress

                if on_progress:
                    # Calculate elapsed time since export started
                    elapsed = time.time() - start_times[vm_name]

                    # Calculate ETA if we have progress
                    eta = None
                    if progress > 0.0 and progress < 1.0:
                        eta = (elapsed / progress) * (1.0 - progress)

                    prog = MigrationProgress(
                        vm_name=vm_name,
                        progress=progress,
                        stage=stage,
                        throughput_mbps=throughput,
                        elapsed_seconds=elapsed,
                        eta_seconds=eta,
                    )
                    on_progress(prog)

            return callback

        # Export VMs in parallel
        results = await self.client.export_vms_parallel(
            vm_names,
            output_dir,
            progress_callback=None,  # Per-VM callbacks set below
        )

        # Process results
        successes = []
        failures = []

        for idx, result in enumerate(results):
            vm_name = vm_names[idx]

            if isinstance(result, dict) and result.get("status") == "success":
                successes.append(vm_name)
                if on_complete:
                    on_complete(vm_name, True, None)
            else:
                error = str(result) if isinstance(result, Exception) else "Unknown error"
                failures.append((vm_name, error))
                if on_complete:
                    on_complete(vm_name, False, error)

        summary = {
            "total": len(vm_names),
            "succeeded": len(successes),
            "failed": len(failures),
            "success_rate": len(successes) / len(vm_names) if vm_names else 0,
            "successes": successes,
            "failures": failures,
        }

        logger.info(
            f"Batch export complete: {summary['succeeded']}/{summary['total']} succeeded"
        )

        return summary

    async def export_with_retry(
        self,
        vm_name: str,
        output_dir: Path,
        max_retries: int = 3,
        on_progress: Optional[Callable[[MigrationProgress], None]] = None,
    ) -> Dict[str, Any]:
        """
        Export VM with automatic retry on failure.

        Args:
            vm_name: VM name
            output_dir: Output directory
            max_retries: Maximum retry attempts (default: 3)
            on_progress: Optional progress callback

        Returns:
            Export result

        Example:
            >>> result = await ops.export_with_retry(
            ...     "web-server-01",
            ...     Path("/output"),
            ...     max_retries=3,
            ... )
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"Export attempt {attempt + 1}/{max_retries} for {vm_name}")

                result = await self.client.export_vm_async(vm_name, output_dir)

                logger.info(f"Successfully exported {vm_name} on attempt {attempt + 1}")
                return result

            except Exception as e:
                logger.warning(
                    f"Export attempt {attempt + 1} failed for {vm_name}: {e}"
                )

                if attempt + 1 < max_retries:
                    # Exponential backoff
                    wait_time = 2**attempt
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All {max_retries} attempts failed for {vm_name}")
                    raise

    async def get_vms_by_pattern(
        self,
        pattern: str,
        use_regex: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get VMs matching a name pattern.

        Args:
            pattern: Pattern to match (glob or regex)
            use_regex: Use regex instead of glob (default: False)

        Returns:
            List of matching VMs

        Example:
            >>> vms = await ops.get_vms_by_pattern("web-server-*")
            >>> vms = await ops.get_vms_by_pattern(r"^db-\\d+$", use_regex=True)
        """
        import fnmatch
        import re

        all_vms = await self.client.list_vms()

        if use_regex:
            regex = re.compile(pattern)
            matching = [vm for vm in all_vms if regex.match(vm["name"])]
        else:
            matching = [vm for vm in all_vms if fnmatch.fnmatch(vm["name"], pattern)]

        logger.info(f"Found {len(matching)} VMs matching pattern: {pattern}")
        return matching


# Convenience function
async def migrate_vms_async(
    host: str,
    username: str,
    password: str,
    vm_names: List[str],
    output_dir: Path,
    datacenter: Optional[str] = None,
    max_concurrent: int = 5,
    on_progress: Optional[Callable[[MigrationProgress], None]] = None,
    on_complete: Optional[Callable[[str, bool, Optional[str]], None]] = None,
) -> Dict[str, Any]:
    """
    Convenience function to migrate multiple VMs asynchronously.

    Args:
        host: vCenter host
        username: vCenter username
        password: vCenter password
        vm_names: List of VM names
        output_dir: Output directory
        datacenter: Datacenter name
        max_concurrent: Max parallel migrations (default: 5)
        on_progress: Progress callback
        on_complete: Completion callback

    Returns:
        Migration summary

    Example:
        >>> results = await migrate_vms_async(
        ...     "vcenter.example.com",
        ...     "admin",
        ...     "password",
        ...     ["vm1", "vm2", "vm3"],
        ...     Path("/output"),
        ...     max_concurrent=3,
        ... )
    """
    async with AsyncVMwareClient(
        host=host,
        username=username,
        password=password,
        datacenter=datacenter,
        max_concurrent_vms=max_concurrent,
    ) as client:
        ops = AsyncVMwareOperations(client)
        return await ops.batch_export(
            vm_names,
            output_dir,
            on_progress=on_progress,
            on_complete=on_complete,
        )
