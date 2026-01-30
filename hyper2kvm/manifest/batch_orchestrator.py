# SPDX-License-Identifier: LGPL-3.0-or-later
"""Batch orchestrator for multi-VM conversions with parallel processing."""

from __future__ import annotations

import concurrent.futures
import logging
import os
import time
from pathlib import Path
from typing import Any

from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from ..config.config_loader import Config
from ..core.logger import Log
from ..core.utils import U
from .batch_loader import BatchLoader, VMBatchItem
from .batch_reporter import BatchReporter
from .orchestrator import ManifestOrchestrator


class VMConversionResult:
    """Result of a single VM conversion in batch mode."""

    def __init__(
        self,
        vm_item: VMBatchItem,
        success: bool,
        duration: float,
        error: str | None = None,
        report: dict[str, Any] | None = None,
    ):
        self.vm_item = vm_item
        self.vm_id = vm_item.id
        self.manifest_path = vm_item.manifest_path
        self.success = success
        self.duration = duration
        self.error = error
        self.report = report or {}

    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        return f"VMConversionResult(id={self.vm_id!r}, status={status}, duration={self.duration:.2f}s)"


class BatchOrchestrator:
    """
    Orchestrates batch conversion of multiple VMs.

    Features:
    - Parallel execution with configurable worker limit
    - Priority-based VM ordering
    - Per-VM error isolation with continue-on-error support
    - Aggregate progress reporting
    - Recovery checkpoint support per VM
    """

    def __init__(self, batch_manifest_path: str | Path, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self.batch_path = Path(batch_manifest_path)
        self.loader = BatchLoader(self.logger)
        self.reporter = BatchReporter(self.logger)
        self.results: list[VMConversionResult] = []

    def run(self) -> dict[str, Any]:
        """
        Execute batch conversion for all VMs.

        Returns:
            Aggregate batch report dictionary
        """
        self.logger.info("=" * 80)
        self.logger.info("🚀 Batch Conversion Pipeline")
        self.logger.info("=" * 80)

        batch_start = time.time()

        try:
            # Load batch manifest
            batch_manifest = self.loader.load(self.batch_path)

            # Get configuration
            vms = self.loader.get_vms()
            parallel_limit = self.loader.get_parallel_limit()
            continue_on_error = self.loader.get_continue_on_error()
            batch_id = self.loader.get_batch_id()
            shared_config = self.loader.get_shared_config()

            self.logger.info(f"📋 Batch ID: {batch_id}")
            self.logger.info(f"📦 VMs to process: {len(vms)}")
            self.logger.info(f"🧵 Parallel limit: {parallel_limit}")
            self.logger.info(f"⚠️  Continue on error: {continue_on_error}")

            if not vms:
                self.logger.warning("No VMs to process in batch")
                return self._generate_report(batch_start, time.time())

            # Process VMs
            if parallel_limit > 1 and len(vms) > 1:
                self._process_vms_parallel(vms, parallel_limit, continue_on_error, shared_config)
            else:
                self._process_vms_sequential(vms, continue_on_error, shared_config)

            batch_duration = time.time() - batch_start

            # Generate and return report
            report = self._generate_report(batch_start, time.time())

            # Write batch report to file
            self._write_batch_report(report)

            # Summary
            success_count = sum(1 for r in self.results if r.success)
            failed_count = len(self.results) - success_count

            self.logger.info("=" * 80)
            self.logger.info(f"✅ Batch conversion completed in {batch_duration:.2f}s")
            self.logger.info(f"   Successful: {success_count}/{len(vms)}")
            if failed_count > 0:
                self.logger.info(f"   Failed: {failed_count}/{len(vms)}")
            self.logger.info("=" * 80)

            return report

        except Exception as e:
            batch_duration = time.time() - batch_start
            self.logger.error(f"💥 Batch conversion failed: {e}")
            self.logger.debug("💥 Batch exception", exc_info=True)
            raise

    def _process_vms_sequential(
        self,
        vms: list[VMBatchItem],
        continue_on_error: bool,
        shared_config: dict[str, Any],
    ) -> None:
        """Process VMs sequentially."""
        self.logger.info("🔄 Processing VMs sequentially")

        for idx, vm in enumerate(vms):
            self.logger.info(f"\n{'─' * 80}")
            self.logger.info(f"➡️  Processing VM {idx + 1}/{len(vms)}: {vm.id}")
            self.logger.info(f"{'─' * 80}")

            result = self._process_single_vm(vm, idx, len(vms), shared_config)
            self.results.append(result)

            if not result.success and not continue_on_error:
                self.logger.error(
                    f"💥 VM {vm.id} failed and continue_on_error=False, stopping batch"
                )
                break

    def _process_vms_parallel(
        self,
        vms: list[VMBatchItem],
        parallel_limit: int,
        continue_on_error: bool,
        shared_config: dict[str, Any],
    ) -> None:
        """Process VMs in parallel."""
        self.logger.info(f"🧵 Processing {len(vms)} VMs in parallel (limit: {parallel_limit})")

        # Determine actual max workers
        max_workers = min(
            parallel_limit,
            len(vms),
            os.cpu_count() or 1,
        )

        Log.trace(
            self.logger,
            "👷 batch parallel: max_workers=%d parallel_limit=%d cpu_count=%r",
            max_workers,
            parallel_limit,
            os.cpu_count(),
        )

        results_dict: dict[int, VMConversionResult] = {}

        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task(f"Converting {len(vms)} VMs", total=len(vms))

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all VM conversion tasks
                futures = {
                    executor.submit(
                        self._process_single_vm, vm, idx, len(vms), shared_config
                    ): idx
                    for idx, vm in enumerate(vms)
                }

                # Process results as they complete
                for future in concurrent.futures.as_completed(futures):
                    idx = futures[future]
                    vm = vms[idx]

                    try:
                        result = future.result()
                        results_dict[idx] = result

                        if result.success:
                            self.logger.info(
                                f"✅ Completed VM {idx + 1}/{len(vms)}: {vm.id} ({result.duration:.2f}s)"
                            )
                        else:
                            self.logger.error(
                                f"💥 Failed VM {idx + 1}/{len(vms)}: {vm.id} - {result.error}"
                            )

                            # Check if we should stop on error
                            if not continue_on_error:
                                self.logger.error(
                                    "💥 Stopping batch due to error (continue_on_error=False)"
                                )
                                # Cancel remaining futures
                                for f in futures:
                                    f.cancel()
                                break

                    except Exception as e:
                        self.logger.error(
                            f"💥 Exception processing VM {idx + 1}/{len(vms)} ({vm.id}): {e}"
                        )
                        Log.trace(self.logger, "💥 VM processing exception", exc_info=True)

                        # Create error result
                        results_dict[idx] = VMConversionResult(
                            vm_item=vm,
                            success=False,
                            duration=0.0,
                            error=str(e),
                        )

                        if not continue_on_error:
                            self.logger.error(
                                "💥 Stopping batch due to exception (continue_on_error=False)"
                            )
                            for f in futures:
                                f.cancel()
                            break

                    progress.update(task, advance=1)

        # Store results in order
        self.results = [results_dict[idx] for idx in sorted(results_dict.keys())]

    def _process_single_vm(
        self,
        vm: VMBatchItem,
        vm_index: int,
        total_vms: int,
        shared_config: dict[str, Any],
    ) -> VMConversionResult:
        """
        Process a single VM conversion.

        Args:
            vm: VM batch item to process
            vm_index: Index of this VM in the batch
            total_vms: Total number of VMs in batch
            shared_config: Shared configuration to apply

        Returns:
            VMConversionResult with success/failure status
        """
        vm_start = time.time()

        try:
            # Validate manifest exists
            if not vm.manifest_path.exists():
                raise FileNotFoundError(f"VM manifest not found: {vm.manifest_path}")

            # Apply shared config and overrides if any
            effective_manifest = self._apply_config_overrides(
                vm.manifest_path, shared_config, vm.overrides
            )

            # Run conversion pipeline for this VM
            Log.trace(
                self.logger,
                "🧠 Starting VM conversion: id=%s manifest=%s",
                vm.id,
                vm.manifest_path,
            )

            orchestrator = ManifestOrchestrator(effective_manifest, logger=self.logger)
            report = orchestrator.run()

            vm_duration = time.time() - vm_start

            return VMConversionResult(
                vm_item=vm,
                success=True,
                duration=vm_duration,
                report=report,
            )

        except Exception as e:
            vm_duration = time.time() - vm_start
            error_msg = f"{type(e).__name__}: {e}"

            Log.trace(
                self.logger,
                "💥 VM conversion failed: id=%s error=%s",
                vm.id,
                error_msg,
                exc_info=True,
            )

            return VMConversionResult(
                vm_item=vm,
                success=False,
                duration=vm_duration,
                error=error_msg,
            )

    def _apply_config_overrides(
        self,
        manifest_path: Path,
        shared_config: dict[str, Any],
        vm_overrides: dict[str, Any],
    ) -> Path:
        """
        Apply shared config and VM-specific overrides to manifest.

        For simplicity, we'll just pass the original manifest path
        and let the orchestrator handle it. In a full implementation,
        you would merge configs and write a temporary manifest.

        Args:
            manifest_path: Original VM manifest path
            shared_config: Shared batch configuration
            vm_overrides: VM-specific overrides

        Returns:
            Path to effective manifest (for now, just the original)
        """
        # TODO: In future, merge shared_config and vm_overrides with manifest
        # For Phase 1, we'll just use the original manifest as-is
        Log.trace(
            self.logger,
            "📝 Config override: shared_keys=%s override_keys=%s",
            list(shared_config.keys()) if shared_config else [],
            list(vm_overrides.keys()) if vm_overrides else [],
        )

        return manifest_path

    def _generate_report(self, start_time: float, end_time: float) -> dict[str, Any]:
        """Generate aggregate batch report using BatchReporter."""
        duration = end_time - start_time
        success_count = sum(1 for r in self.results if r.success)
        failed_count = len(self.results) - success_count

        # Populate reporter
        self.reporter.set_batch_info(
            batch_id=self.loader.get_batch_id(),
            manifest_path=str(self.batch_path),
            total_vms=len(self.loader.get_vms()),
            processed_vms=len(self.results),
            successful_vms=success_count,
            failed_vms=failed_count,
        )
        self.reporter.set_duration(duration)

        # Add VM results
        for result in self.results:
            self.reporter.add_vm_result(
                vm_id=result.vm_id,
                manifest=str(result.manifest_path),
                success=result.success,
                duration=result.duration,
                error=result.error,
                vm_report=result.report if result.success else None,
            )

        # Generate and return final report
        return self.reporter.generate()

    def _write_batch_report(self, report: dict[str, Any]) -> None:
        """Write batch report files."""
        # Determine output directory
        output_dir = self.loader.get_output_directory()
        if not output_dir:
            # Fallback to batch manifest directory
            output_dir = self.batch_path.parent

        # Ensure output directory exists
        U.ensure_dir(output_dir)

        # Write JSON report
        json_report_path = output_dir / "batch_report.json"
        self.reporter.write_json(json_report_path)

        # Write human-readable summary
        summary_path = output_dir / "batch_summary.txt"
        self.reporter.write_summary(summary_path)
