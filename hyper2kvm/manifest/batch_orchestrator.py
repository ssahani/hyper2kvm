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
from .batch_progress import ProgressTracker
from .batch_reporter import BatchReporter
from .checkpoint_manager import CheckpointManager
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

    def __init__(
        self,
        batch_manifest_path: str | Path,
        logger: logging.Logger | None = None,
        enable_checkpoint: bool = True,
        enable_progress: bool = True,
    ):
        self.logger = logger or logging.getLogger(__name__)
        self.batch_path = Path(batch_manifest_path)
        self.loader = BatchLoader(self.logger)
        self.reporter = BatchReporter(self.logger)
        self.results: list[VMConversionResult] = []
        self.enable_checkpoint = enable_checkpoint
        self.checkpoint_manager: CheckpointManager | None = None
        self.enable_progress = enable_progress
        self.progress_tracker: ProgressTracker | None = None

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

            # Initialize checkpoint manager if enabled
            if self.enable_checkpoint:
                checkpoint_dir = self._get_checkpoint_directory()
                self.checkpoint_manager = CheckpointManager(
                    checkpoint_dir=checkpoint_dir,
                    batch_id=batch_id,
                    logger=self.logger,
                )

                # Check for existing checkpoint
                if self.checkpoint_manager.has_checkpoint():
                    checkpoint_data = self.checkpoint_manager.load_checkpoint()
                    completed_ids = self.checkpoint_manager.get_completed_vm_ids()
                    failed_ids = self.checkpoint_manager.get_failed_vm_ids()

                    self.logger.info(
                        f"📂 Resuming from checkpoint: {len(completed_ids)} completed, "
                        f"{len(failed_ids)} failed"
                    )

                    # Filter out already-processed VMs
                    original_count = len(vms)
                    vms = [vm for vm in vms if vm.id not in completed_ids and vm.id not in failed_ids]

                    if len(vms) < original_count:
                        self.logger.info(
                            f"⏩ Skipping {original_count - len(vms)} already-processed VMs"
                        )

                    # Restore previous results for reporting
                    self._restore_previous_results(checkpoint_data)

            if not vms:
                self.logger.info("✅ All VMs already processed (checkpoint resume)")
                return self._generate_report(batch_start, time.time())

            # Initialize progress tracker if enabled
            if self.enable_progress:
                progress_file = self._get_progress_file()
                self.progress_tracker = ProgressTracker(
                    progress_file=progress_file,
                    batch_id=batch_id,
                    total_vms=len(self.loader.get_vms()),
                    logger=self.logger,
                )
                self.logger.info(f"📊 Progress tracking enabled: {progress_file}")

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

            # Complete progress tracking
            if self.enable_progress and self.progress_tracker:
                self.progress_tracker.complete_batch()

            # Cleanup checkpoint on successful completion
            if self.enable_checkpoint and self.checkpoint_manager and failed_count == 0:
                self.checkpoint_manager.cleanup()

            # Cleanup progress file on successful completion
            if self.enable_progress and self.progress_tracker and failed_count == 0:
                self.progress_tracker.cleanup()

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

            # Save checkpoint after each VM
            if self.enable_checkpoint and self.checkpoint_manager:
                self._save_checkpoint_state()

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

                        # Save checkpoint after each VM completion (in order)
                        if self.enable_checkpoint and self.checkpoint_manager:
                            # Temporarily update results for checkpoint save
                            self.results = [results_dict[i] for i in sorted(results_dict.keys())]
                            self._save_checkpoint_state()

                        # Check if we should stop on error
                        if not result.success and not continue_on_error:
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

                        # Save checkpoint after exception
                        if self.enable_checkpoint and self.checkpoint_manager:
                            self.results = [results_dict[i] for i in sorted(results_dict.keys())]
                            self._save_checkpoint_state()

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

        # Track VM start in progress
        if self.enable_progress and self.progress_tracker:
            self.progress_tracker.start_vm(vm.id)

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

            # Update progress: extraction stage
            if self.enable_progress and self.progress_tracker:
                self.progress_tracker.update_vm_stage(vm.id, "extraction")

            orchestrator = ManifestOrchestrator(effective_manifest, logger=self.logger)
            report = orchestrator.run()

            vm_duration = time.time() - vm_start

            # Track VM completion in progress
            if self.enable_progress and self.progress_tracker:
                self.progress_tracker.complete_vm(vm.id, success=True)

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

            # Track VM failure in progress
            if self.enable_progress and self.progress_tracker:
                self.progress_tracker.complete_vm(vm.id, success=False, error=error_msg)

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

        Merges shared_config and vm_overrides into the manifest and
        writes a temporary manifest file if overrides exist.

        Args:
            manifest_path: Original VM manifest path
            shared_config: Shared batch configuration
            vm_overrides: VM-specific overrides

        Returns:
            Path to effective manifest (temp file if overrides, else original)
        """
        # If no overrides, return original manifest
        if not shared_config and not vm_overrides:
            return manifest_path

        Log.trace(
            self.logger,
            "📝 Config override: shared_keys=%s override_keys=%s",
            list(shared_config.keys()) if shared_config else [],
            list(vm_overrides.keys()) if vm_overrides else [],
        )

        try:
            import json
            import tempfile

            # Load original manifest
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)

            # Deep merge helper function
            def deep_merge(base: dict, overlay: dict) -> dict:
                """Recursively merge overlay into base."""
                result = base.copy()
                for key, value in overlay.items():
                    if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                        result[key] = deep_merge(result[key], value)
                    else:
                        result[key] = value
                return result

            # Apply shared config first, then VM-specific overrides
            if shared_config:
                manifest = deep_merge(manifest, shared_config)
            if vm_overrides:
                manifest = deep_merge(manifest, vm_overrides)

            # Write merged manifest to temporary file
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.json',
                prefix='manifest_override_',
                delete=False,
                dir=manifest_path.parent,
            ) as tmp_file:
                json.dump(manifest, tmp_file, indent=2)
                tmp_path = Path(tmp_file.name)

            Log.trace(self.logger, "📝 Created merged manifest: %s", tmp_path)
            return tmp_path

        except Exception as e:
            Log.warn(
                self.logger,
                "Failed to merge config overrides: %s, using original manifest",
                e,
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

    def _get_checkpoint_directory(self) -> Path:
        """Get checkpoint directory path."""
        # Use output directory if available, otherwise batch manifest directory
        output_dir = self.loader.get_output_directory()
        if output_dir:
            checkpoint_dir = output_dir / ".checkpoints"
        else:
            checkpoint_dir = self.batch_path.parent / ".checkpoints"

        return checkpoint_dir

    def _get_progress_file(self) -> Path:
        """Get progress file path."""
        # Use output directory if available, otherwise batch manifest directory
        output_dir = self.loader.get_output_directory()
        if output_dir:
            progress_file = output_dir / ".progress" / "batch_progress.json"
        else:
            progress_file = self.batch_path.parent / ".progress" / "batch_progress.json"

        return progress_file

    def _restore_previous_results(self, checkpoint_data: dict[str, Any]) -> None:
        """Restore previous VM results from checkpoint."""
        # Create VMConversionResult objects for completed VMs
        for vm_id in checkpoint_data.get("completed_vms", []):
            # Create a placeholder result for completed VMs
            # We don't have the full VMBatchItem, so create a minimal one
            from .batch_loader import VMBatchItem

            vm_item = VMBatchItem(
                id=vm_id,
                manifest_path=Path("unknown"),  # Not critical for reporting
                priority=0,
                enabled=True,
                overrides={},
            )

            result = VMConversionResult(
                vm_item=vm_item,
                success=True,
                duration=0.0,  # Duration not preserved
                report={},
            )
            self.results.append(result)

        # Create VMConversionResult objects for failed VMs
        for failed_vm in checkpoint_data.get("failed_vms", []):
            from .batch_loader import VMBatchItem

            vm_id = failed_vm.get("vm_id", "unknown")
            error = failed_vm.get("error", "Unknown error")

            vm_item = VMBatchItem(
                id=vm_id,
                manifest_path=Path("unknown"),
                priority=0,
                enabled=True,
                overrides={},
            )

            result = VMConversionResult(
                vm_item=vm_item,
                success=False,
                duration=0.0,
                error=error,
            )
            self.results.append(result)

    def _save_checkpoint_state(self) -> None:
        """Save current checkpoint state."""
        if not self.checkpoint_manager:
            return

        # Separate completed and failed VMs
        completed_vms = [r.vm_id for r in self.results if r.success]
        failed_vms = [
            {"vm_id": r.vm_id, "error": r.error} for r in self.results if not r.success
        ]

        # Get total VMs from loader
        total_vms = len(self.loader.get_vms())

        # Save checkpoint
        self.checkpoint_manager.save_checkpoint(
            completed_vms=completed_vms,
            failed_vms=failed_vms,
            total_vms=total_vms,
        )
