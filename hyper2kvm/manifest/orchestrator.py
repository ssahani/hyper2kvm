# SPDX-License-Identifier: LGPL-3.0-or-later
"""Manifest-driven pipeline orchestrator."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import guestfs  # type: ignore

from ..core.logger import Log
from ..core.utils import U
from ..converters.qemu.converter import Convert
from ..fixers.offline_fixer import OfflineFSFix
from .loader import ManifestLoader
from .reporter import ManifestReporter


class ManifestOrchestrator:
    """
    Orchestrates the manifest-driven conversion pipeline.

    Pipeline stages:
    1. LOAD_MANIFEST: Load and validate manifest
    2. INSPECT: Gather information about source disk
    3. FIX: Apply offline fixes to guest filesystem
    4. CONVERT: Convert to target format
    5. VALIDATE: Verify output integrity
    """

    def __init__(self, manifest_path: str | Path, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self.manifest_path = Path(manifest_path)
        self.loader = ManifestLoader(self.logger)
        self.reporter = ManifestReporter(self.logger)
        self.manifest: dict[str, Any] = {}

        # Pipeline state
        self.current_stage = "none"
        self.source_path: Path | None = None
        self.output_path: Path | None = None
        self.working_path: Path | None = None

    def run(self) -> dict[str, Any]:
        """
        Execute the complete pipeline.

        Returns:
            Final report dictionary
        """
        self.logger.info("=" * 80)
        self.logger.info("🚀 Manifest-Driven Conversion Pipeline")
        self.logger.info("=" * 80)

        pipeline_start = time.time()

        try:
            # Stage 1: LOAD_MANIFEST
            self._run_stage("load_manifest", self._stage_load_manifest)

            # Stage 2: INSPECT
            if self.loader.is_stage_enabled("inspect"):
                self._run_stage("inspect", self._stage_inspect)
            else:
                self.logger.info("⏭️  INSPECT stage disabled")

            # Stage 3: FIX
            if self.loader.is_stage_enabled("fix"):
                self._run_stage("fix", self._stage_fix)
            else:
                self.logger.info("⏭️  FIX stage disabled")

            # Stage 4: CONVERT
            if self.loader.is_stage_enabled("convert"):
                self._run_stage("convert", self._stage_convert)
            else:
                self.logger.info("⏭️  CONVERT stage disabled")

            # Stage 5: VALIDATE
            if self.loader.is_stage_enabled("validate"):
                self._run_stage("validate", self._stage_validate)
            else:
                self.logger.info("⏭️  VALIDATE stage disabled")

            # Finalize
            pipeline_duration = time.time() - pipeline_start
            self.reporter.set_duration(pipeline_duration)
            self.reporter.set_success(True)

            self.logger.info("=" * 80)
            self.logger.info(f"✅ Pipeline completed successfully in {pipeline_duration:.2f}s")
            self.logger.info("=" * 80)

        except Exception as e:
            pipeline_duration = time.time() - pipeline_start
            self.reporter.set_duration(pipeline_duration)
            self.reporter.set_success(False)
            self.reporter.add_error(self.current_stage, str(e))

            self.logger.error(f"💥 Pipeline failed at stage '{self.current_stage}': {e}")
            raise

        finally:
            # Write report
            report = self.reporter.generate()
            self._write_report(report)

        return report

    def _run_stage(self, stage_name: str, stage_func: callable) -> Any:
        """Execute a pipeline stage with timing and error handling."""
        self.current_stage = stage_name
        self.logger.info(f"\n{'─' * 80}")
        self.logger.info(f"➡️  Stage: {stage_name.upper().replace('_', ' ')}")
        self.logger.info(f"{'─' * 80}")

        stage_start = time.time()
        try:
            result = stage_func()
            duration = time.time() - stage_start

            self.reporter.add_stage_result(stage_name, {
                "success": True,
                "duration": duration,
                "result": result or {},
            })

            self.logger.info(f"✅ {stage_name} completed in {duration:.2f}s")
            return result

        except Exception as e:
            duration = time.time() - stage_start
            self.reporter.add_stage_result(stage_name, {
                "success": False,
                "duration": duration,
                "error": str(e),
            })
            self.logger.error(f"❌ {stage_name} failed: {e}")
            raise

    # Pipeline Stages

    def _stage_load_manifest(self) -> dict[str, Any]:
        """Stage 1: Load and validate manifest."""
        self.manifest = self.loader.load(self.manifest_path)
        self.source_path = self.loader.get_source_path()

        self.logger.info(f"📋 Manifest: {self.loader.get_name()}")
        self.logger.info(f"📥 Source: {self.source_path} ({self.loader.get_source_type()})")
        self.logger.info(f"📤 Output: {self.loader.get_output_directory()}")
        self.logger.info(f"🎯 Format: {self.loader.get_output_format()}")

        return {
            "manifest_path": str(self.manifest_path),
            "manifest_name": self.loader.get_name(),
            "source_path": str(self.source_path),
            "source_type": self.loader.get_source_type(),
            "output_directory": str(self.loader.get_output_directory()),
            "output_format": self.loader.get_output_format(),
        }

    def _stage_inspect(self) -> dict[str, Any]:
        """Stage 2: Inspect source disk."""
        inspect_config = self.loader.get_stage_config("inspect")

        self.logger.info(f"🔍 Inspecting: {self.source_path}")

        # Get file info
        try:
            stat = self.source_path.stat()
            size_bytes = stat.st_size
            size_human = U.human_bytes(size_bytes)
        except Exception as e:
            self.logger.warning(f"Could not stat source: {e}")
            size_bytes = 0
            size_human = "unknown"

        result = {
            "path": str(self.source_path),
            "exists": self.source_path.exists(),
            "size_bytes": size_bytes,
            "size_human": size_human,
        }

        # Guest inspection if enabled
        if inspect_config.get("collect_guest_info", False):
            self.logger.info("🔍 Collecting guest information...")
            try:
                g = guestfs.GuestFS(python_return_dict=True)
                g.add_drive_opts(str(self.source_path), readonly=1)
                g.launch()

                roots = g.inspect_os()
                if roots:
                    root = roots[0]
                    result["guest"] = {
                        "type": g.inspect_get_type(root),
                        "distro": g.inspect_get_distro(root),
                        "product_name": g.inspect_get_product_name(root),
                        "major_version": g.inspect_get_major_version(root),
                        "minor_version": g.inspect_get_minor_version(root),
                    }
                    self.logger.info(f"📦 Guest: {result['guest']['product_name']}")

                g.close()
            except Exception as e:
                self.logger.warning(f"Guest inspection failed: {e}")
                result["guest_inspection_error"] = str(e)

        self.logger.info(f"📏 Size: {size_human}")
        return result

    def _stage_fix(self) -> dict[str, Any]:
        """Stage 3: Apply offline fixes."""
        fix_config = self.loader.get_stage_config("fix")
        configuration = self.loader.get_configuration()

        self.logger.info("🔧 Applying offline fixes...")

        # Prepare working image (use source directly for now)
        working_image = self.source_path

        # Setup fixer
        fixer = OfflineFSFix(
            self.logger,
            working_image,
            dry_run=self.loader.is_dry_run(),
            no_backup=not fix_config.get("backup", True),
            print_fstab=fix_config.get("print_fstab", False),
            update_grub=fix_config.get("update_grub", True),
            regen_initramfs=fix_config.get("regen_initramfs", True),
            fstab_mode=fix_config.get("fstab_mode", "stabilize-all"),
            report_path=None,
            remove_vmware_tools=fix_config.get("remove_vmware_tools", False),
            user_config_inject=configuration.get("users"),
            service_config_inject=configuration.get("services"),
            hostname_config_inject=configuration.get("hostname"),
            network_config_inject=configuration.get("network"),
        )

        # Run fixes
        fixer.run()

        return {
            "fstab_mode": fix_config.get("fstab_mode", "stabilize-all"),
            "grub_updated": fix_config.get("update_grub", True),
            "initramfs_regenerated": fix_config.get("regen_initramfs", True),
            "vmware_tools_removed": fix_config.get("remove_vmware_tools", False),
        }

    def _stage_convert(self) -> dict[str, Any]:
        """Stage 4: Convert to target format."""
        convert_config = self.loader.get_stage_config("convert")
        output_dir = self.loader.get_output_directory()
        output_format = self.loader.get_output_format()

        # Ensure output directory exists
        U.ensure_dir(output_dir)

        # Determine output filename
        output_filename = self.loader.get_output_filename()
        if not output_filename:
            source_stem = self.source_path.stem
            output_filename = f"{source_stem}-converted.{output_format}"

        self.output_path = output_dir / output_filename

        self.logger.info(f"🔄 Converting to {output_format}...")
        self.logger.info(f"📤 Output: {self.output_path}")

        # Perform conversion
        Convert.convert_image_with_progress(
            self.logger,
            self.source_path,
            self.output_path,
            out_format=output_format,
            compress=convert_config.get("compress", False),
            compress_level=convert_config.get("compress_level"),
            progress_callback=lambda p: self.logger.info(f"⏳ Progress: {p:.1%}") if int(p * 100) % 10 == 0 else None,
        )

        # Get output size
        output_stat = self.output_path.stat()
        output_size = U.human_bytes(output_stat.st_size)

        self.logger.info(f"✅ Converted: {output_size}")

        return {
            "output_path": str(self.output_path),
            "output_format": output_format,
            "output_size_bytes": output_stat.st_size,
            "output_size_human": output_size,
            "compressed": convert_config.get("compress", False),
        }

    def _stage_validate(self) -> dict[str, Any]:
        """Stage 5: Validate output."""
        validate_config = self.loader.get_stage_config("validate")

        self.logger.info("✅ Validating output...")

        result = {
            "image_exists": self.output_path.exists() if self.output_path else False,
        }

        # Check image integrity
        if validate_config.get("check_image_integrity", True) and self.output_path:
            try:
                Convert.validate(self.logger, self.output_path)
                result["integrity_check"] = "passed"
                self.logger.info("✅ Image integrity: OK")
            except Exception as e:
                result["integrity_check"] = "failed"
                result["integrity_error"] = str(e)
                self.logger.error(f"❌ Image integrity check failed: {e}")
                raise

        return result

    def _write_report(self, report: dict[str, Any]) -> None:
        """Write report to file."""
        options = self.loader.get_options()
        report_config = options.get("report", {})

        if not report_config.get("enabled", True):
            self.logger.info("📊 Report generation disabled")
            return

        # Determine report path
        report_path = report_config.get("path")
        if not report_path:
            output_dir = self.loader.get_output_directory()
            report_path = output_dir / "report.json"
        else:
            report_path = Path(report_path)
            if not report_path.is_absolute():
                output_dir = self.loader.get_output_directory()
                report_path = output_dir / report_path

        # Ensure parent directory exists
        report_path.parent.mkdir(parents=True, exist_ok=True)

        # Write report
        self.reporter.write_json(report_path)
        self.logger.info(f"📊 Report written: {report_path}")
