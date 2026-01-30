# SPDX-License-Identifier: LGPL-3.0-or-later
"""Artifact Manifest v1 pipeline orchestrator for hypersdk integration."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...

from ..core.utils import U
from ..converters.qemu.converter import Convert
from ..fixers.offline_fixer import OfflineFSFix
from ..hooks import HookRunner, create_hook_context
from .loader import DiskArtifact, ManifestLoader
from .reporter import ManifestReporter


class ManifestOrchestrator:
    """
    Orchestrates the Artifact Manifest v1 conversion pipeline.

    Pipeline stages:
    1. LOAD_MANIFEST: Load and validate Artifact Manifest v1
    2. INSPECT: Gather information about disk artifacts
    3. FIX: Apply offline fixes to boot disk filesystem
    4. CONVERT: Convert all disks to target format
    5. VALIDATE: Verify output integrity for all disks
    """

    def __init__(self, manifest_path: str | Path, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self.manifest_path = Path(manifest_path)
        self.loader = ManifestLoader(self.logger)
        self.reporter = ManifestReporter(self.logger)
        self.manifest: dict[str, Any] = {}
        self.hook_runner: HookRunner | None = None

        # Pipeline state
        self.current_stage = "none"
        self.output_dir: Path | None = None
        self.converted_disks: dict[str, Path] = {}  # disk_id -> output_path

    def run(self) -> dict[str, Any]:
        """
        Execute the complete pipeline.

        Returns:
            Final report dictionary
        """
        self.logger.info("=" * 80)
        self.logger.info("🚀 Artifact Manifest v1 Conversion Pipeline")
        self.logger.info("=" * 80)

        pipeline_start = time.time()

        try:
            # Pre-extraction hook (before manifest load)
            self._execute_hook_stage("pre_extraction", {
                "manifest_path": str(self.manifest_path),
            })

            # Stage 1: LOAD_MANIFEST (always runs)
            self._run_stage("load_manifest", self._stage_load_manifest)

            # Initialize hook runner from manifest (if hooks are present)
            self.hook_runner = HookRunner.from_manifest(self.manifest, self.logger)

            # Post-extraction hook (after manifest load)
            self._execute_hook_stage("post_extraction", self._create_hook_context())

            # Stage 2: INSPECT
            if self.loader.is_stage_enabled("inspect"):
                self._run_stage("inspect", self._stage_inspect)
            else:
                self.logger.info("⏭️  INSPECT stage disabled")

            # Stage 3: FIX (boot disk only)
            if self.loader.is_stage_enabled("fix"):
                # Pre-fix hook
                self._execute_hook_stage("pre_fix", self._create_hook_context())

                self._run_stage("fix", self._stage_fix)

                # Post-fix hook
                self._execute_hook_stage("post_fix", self._create_hook_context())
            else:
                self.logger.info("⏭️  FIX stage disabled")

            # Stage 4: CONVERT (all disks)
            if self.loader.is_stage_enabled("convert"):
                # Pre-convert hook
                self._execute_hook_stage("pre_convert", self._create_hook_context())

                self._run_stage("convert", self._stage_convert)

                # Post-convert hook
                self._execute_hook_stage("post_convert", self._create_hook_context())
            else:
                self.logger.info("⏭️  CONVERT stage disabled")

            # Stage 5: VALIDATE (all converted disks)
            if self.loader.is_stage_enabled("validate"):
                self._run_stage("validate", self._stage_validate)

                # Post-validate hook
                self._execute_hook_stage("post_validate", self._create_hook_context())
            else:
                self.logger.info("⏭️  VALIDATE stage disabled")

            # Stage 6: LIBVIRT_INTEGRATION (optional - define domain and import disks)
            if self.loader.is_libvirt_integration_enabled():
                self._run_stage("libvirt_integration", self._stage_libvirt_integration)
            else:
                self.logger.info("⏭️  LIBVIRT_INTEGRATION stage disabled")

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
        """Stage 1: Load and validate Artifact Manifest v1."""
        self.manifest = self.loader.load(self.manifest_path)

        # Verify checksums if present
        if any(disk.checksum for disk in self.loader.get_disks()):
            self.logger.info("🔐 Verifying checksums...")
            checksum_results = self.loader.verify_checksums()
            self.logger.info(f"✅ Verified {len(checksum_results)} checksum(s)")

        # Display summary
        source_meta = self.loader.get_source_metadata()
        disks = self.loader.get_disks()
        firmware = self.loader.get_firmware()
        os_hint = self.loader.get_os_hint()

        self.logger.info(f"📋 Manifest: v{self.loader.get_version()}")
        if source_meta.get("provider"):
            self.logger.info(f"📥 Source: {source_meta.get('provider')} / {source_meta.get('vm_name', 'unknown')}")
        self.logger.info(f"💾 Disks: {len(disks)} artifact(s)")
        for disk in disks:
            size_human = U.human_bytes(disk.bytes)
            self.logger.info(f"   - {disk.id}: {disk.source_format} ({size_human})")
        self.logger.info(f"⚙️  Firmware: {firmware}")
        if os_hint != "unknown":
            self.logger.info(f"🖥️  OS Hint: {os_hint}")

        return {
            "manifest_version": self.loader.get_version(),
            "manifest_path": str(self.manifest_path),
            "source_provider": source_meta.get("provider"),
            "source_vm_id": source_meta.get("vm_id"),
            "source_vm_name": source_meta.get("vm_name"),
            "disks_count": len(disks),
            "firmware": firmware,
            "os_hint": os_hint,
            "checksums_verified": any(disk.checksum for disk in disks),
        }

    def _stage_inspect(self) -> dict[str, Any]:
        """Stage 2: Inspect all disk artifacts."""
        inspect_config = self.loader.get_stage_config("inspect")
        disks = self.loader.get_disks()

        self.logger.info(f"🔍 Inspecting {len(disks)} disk artifact(s)...")

        disk_results = []

        for disk in disks:
            self.logger.info(f"\n📀 Disk: {disk.id}")
            self.logger.info(f"   Path: {disk.local_path}")
            self.logger.info(f"   Format: {disk.source_format}")
            self.logger.info(f"   Expected size: {U.human_bytes(disk.bytes)}")

            # Verify file exists
            if not disk.local_path.exists():
                raise FileNotFoundError(f"Disk artifact not found: {disk.local_path}")

            # Get actual size
            stat = disk.local_path.stat()
            actual_bytes = stat.st_size
            size_match = actual_bytes == disk.bytes

            self.logger.info(f"   Actual size: {U.human_bytes(actual_bytes)}")
            if not size_match:
                self.reporter.add_warning(
                    "inspect",
                    f"Disk {disk.id}: Size mismatch (expected {disk.bytes}, got {actual_bytes})"
                )
                self.logger.warning(f"   ⚠️  Size mismatch!")

            disk_result = {
                "id": disk.id,
                "source_format": disk.source_format,
                "expected_bytes": disk.bytes,
                "actual_bytes": actual_bytes,
                "size_match": size_match,
                "size_human": U.human_bytes(actual_bytes),
                "path": str(disk.local_path),
            }

            # Guest inspection if enabled (boot disk only)
            boot_disk = self.loader.get_boot_disk()
            if inspect_config.get("collect_guest_info", False) and disk.id == boot_disk.id:
                self.logger.info("🔍 Collecting guest information...")
                try:
                    g = guestfs.GuestFS(python_return_dict=True)
                    g.add_drive_opts(str(disk.local_path), readonly=1)
                    g.launch()

                    roots = g.inspect_os()
                    if roots:
                        root = roots[0]
                        disk_result["guest"] = {
                            "type": g.inspect_get_type(root),
                            "distro": g.inspect_get_distro(root),
                            "product_name": g.inspect_get_product_name(root),
                            "major_version": g.inspect_get_major_version(root),
                            "minor_version": g.inspect_get_minor_version(root),
                        }
                        self.logger.info(f"   📦 Guest: {disk_result['guest']['product_name']}")

                    g.close()
                except Exception as e:
                    self.logger.warning(f"Guest inspection failed: {e}")
                    disk_result["guest_inspection_error"] = str(e)

            disk_results.append(disk_result)

        return {"disks": disk_results}

    def _stage_fix(self) -> dict[str, Any]:
        """Stage 3: Apply offline fixes to boot disk only."""
        fix_config = self.loader.get_stage_config("fix")
        configuration = self.loader.get_configuration()
        boot_disk = self.loader.get_boot_disk()

        self.logger.info(f"🔧 Applying offline fixes to boot disk: {boot_disk.id}")
        self.logger.info(f"   (Data disks will be skipped)")

        # Setup fixer for boot disk
        fixer = OfflineFSFix(
            self.logger,
            boot_disk.local_path,
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

        # Note about data disks
        all_disks = self.loader.get_disks()
        data_disks = [d for d in all_disks if d.id != boot_disk.id]
        if data_disks:
            for disk in data_disks:
                self.reporter.add_warning(
                    "fix",
                    f"Data disk {disk.id} skipped (fixes only apply to boot disk)"
                )

        return {
            "boot_disk_id": boot_disk.id,
            "data_disks_skipped": len(data_disks),
            "fstab_mode": fix_config.get("fstab_mode", "stabilize-all"),
            "grub_updated": fix_config.get("update_grub", True),
            "initramfs_regenerated": fix_config.get("regen_initramfs", True),
            "vmware_tools_removed": fix_config.get("remove_vmware_tools", False),
        }

    def _stage_convert(self) -> dict[str, Any]:
        """Stage 4: Convert all disks to target format."""
        convert_config = self.loader.get_stage_config("convert")
        output_format = self.loader.get_output_format()
        self.output_dir = self.loader.get_output_directory()
        disks = self.loader.get_disks()

        # Ensure output directory exists
        U.ensure_dir(self.output_dir)

        self.logger.info(f"🔄 Converting {len(disks)} disk(s) to {output_format}...")
        self.logger.info(f"📤 Output: {self.output_dir}")

        converted = []

        for disk in disks:
            self.logger.info(f"\n💾 Converting disk: {disk.id}")

            # Determine output filename
            output_filename = f"{disk.id}.{output_format}"
            output_path = self.output_dir / output_filename

            self.logger.info(f"   Input: {disk.local_path}")
            self.logger.info(f"   Output: {output_path}")

            # Perform conversion
            Convert.convert_image_with_progress(
                self.logger,
                disk.local_path,
                output_path,
                out_format=output_format,
                compress=convert_config.get("compress", False),
                compress_level=convert_config.get("compress_level"),
                progress_callback=lambda p: self.logger.info(f"⏳ Progress: {p:.1%}") if int(p * 100) % 10 == 0 else None,
            )

            # Get output size
            output_stat = output_path.stat()
            output_size_human = U.human_bytes(output_stat.st_size)

            self.logger.info(f"✅ Converted: {output_size_human}")

            # Store converted path
            self.converted_disks[disk.id] = output_path

            converted.append({
                "disk_id": disk.id,
                "input_format": disk.source_format,
                "output_format": output_format,
                "output_path": str(output_path),
                "output_size_bytes": output_stat.st_size,
                "output_size_human": output_size_human,
                "boot_order_hint": disk.boot_order_hint,
            })

        return {
            "disks_converted": len(converted),
            "output_format": output_format,
            "output_directory": str(self.output_dir),
            "compressed": convert_config.get("compress", False),
            "converted_disks": converted,
        }

    def _stage_validate(self) -> dict[str, Any]:
        """Stage 5: Validate all converted disks."""
        validate_config = self.loader.get_stage_config("validate")

        self.logger.info(f"✅ Validating {len(self.converted_disks)} converted disk(s)...")

        validation_results = []

        for disk_id, output_path in self.converted_disks.items():
            self.logger.info(f"\n🔍 Validating: {disk_id}")

            result = {
                "disk_id": disk_id,
                "output_path": str(output_path),
                "exists": output_path.exists(),
            }

            if not output_path.exists():
                result["integrity_check"] = "failed"
                result["error"] = "Output file does not exist"
                self.reporter.add_error("validate", f"Disk {disk_id}: Output file missing")
                raise FileNotFoundError(f"Output file missing: {output_path}")

            # Check image integrity
            if validate_config.get("check_image_integrity", True):
                try:
                    Convert.validate(self.logger, output_path)
                    result["integrity_check"] = "passed"
                    self.logger.info(f"✅ {disk_id}: Integrity check passed")
                except Exception as e:
                    result["integrity_check"] = "failed"
                    result["integrity_error"] = str(e)
                    self.logger.error(f"❌ {disk_id}: Integrity check failed: {e}")
                    raise

            validation_results.append(result)

        return {
            "disks_validated": len(validation_results),
            "all_passed": all(r.get("integrity_check") == "passed" for r in validation_results),
            "validation_results": validation_results,
        }

    def _stage_libvirt_integration(self) -> dict[str, Any]:
        """Stage 6: Libvirt integration - define domain and import disks to pools."""
        from ..libvirt import (
            LIBVIRT_AVAILABLE,
            LibvirtManager,
            LibvirtManagerError,
            PoolManager,
            PoolManagerError,
        )

        if not LIBVIRT_AVAILABLE:
            self.logger.warning(
                "⚠️  Libvirt Python bindings not available. "
                "Install with: pip install libvirt-python"
            )
            return {"enabled": False, "reason": "libvirt not available"}

        libvirt_config = self.loader.get_libvirt_integration_config()

        domain_xml_path = self.output_dir / "domain.xml"
        if not domain_xml_path.exists():
            self.logger.warning(f"⚠️  Domain XML not found: {domain_xml_path}")
            return {"enabled": False, "reason": "domain XML not found"}

        self.logger.info(f"🔧 Integrating with libvirt...")

        results = {
            "domain_defined": False,
            "disks_imported": 0,
            "snapshot_created": False,
            "domain_started": False,
        }

        try:
            # Define domain
            if libvirt_config.get("define_domain", True):
                with LibvirtManager(self.logger) as manager:
                    domain = manager.define_domain(
                        domain_xml_path,
                        overwrite=libvirt_config.get("overwrite_domain", False),
                    )
                    results["domain_defined"] = True
                    results["domain_name"] = domain.name()

                    # Create snapshot if requested
                    if libvirt_config.get("create_snapshot", False):
                        snapshot_name = libvirt_config.get(
                            "snapshot_name", "pre-first-boot"
                        )
                        manager.create_snapshot(
                            domain,
                            snapshot_name,
                            description="Snapshot created by hyper2kvm before first boot",
                        )
                        results["snapshot_created"] = True
                        results["snapshot_name"] = snapshot_name

                    # Set autostart if requested
                    if libvirt_config.get("autostart", False):
                        manager.set_autostart(domain, True)
                        results["autostart_enabled"] = True

                    # Start domain if requested
                    if libvirt_config.get("auto_start", False):
                        manager.start_domain(domain)
                        results["domain_started"] = True

            # Import disks to pool if requested
            pool_name = libvirt_config.get("import_to_pool")
            if pool_name:
                pool_path = libvirt_config.get(
                    "pool_path", "/var/lib/libvirt/images"
                )

                with PoolManager(self.logger) as pool_mgr:
                    pool = pool_mgr.ensure_pool(pool_name, pool_path)

                    # Import each converted disk
                    for disk_id, output_path in self.converted_disks.items():
                        volume_name = f"{libvirt_config.get('vm_name', 'vm')}-{disk_id}"
                        pool_mgr.import_disk(
                            pool,
                            output_path,
                            volume_name,
                            copy=libvirt_config.get("copy_disks", True),
                            overwrite=libvirt_config.get("overwrite_volumes", False),
                        )
                        results["disks_imported"] += 1

            self.logger.info("✅ Libvirt integration completed successfully")
            return results

        except (LibvirtManagerError, PoolManagerError) as e:
            self.logger.error(f"❌ Libvirt integration failed: {e}")
            self.reporter.add_error("libvirt_integration", str(e))
            raise

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
            if self.output_dir:
                report_path = self.output_dir / "report.json"
            else:
                # Fallback to manifest directory
                report_path = self.manifest_path.parent / "report.json"
        else:
            report_path = Path(report_path)
            if not report_path.is_absolute():
                if self.output_dir:
                    report_path = self.output_dir / report_path
                else:
                    report_path = self.manifest_path.parent / report_path

        # Ensure parent directory exists
        report_path.parent.mkdir(parents=True, exist_ok=True)

        # Write report
        self.reporter.write_json(report_path)
        self.logger.info(f"📊 Report written: {report_path}")

    def _execute_hook_stage(self, stage: str, context: dict[str, Any]) -> None:
        """
        Execute hooks for a given pipeline stage.

        Args:
            stage: Stage name (e.g., "pre_fix", "post_convert")
            context: Context variables for template substitution
        """
        if not self.hook_runner:
            return

        if not self.hook_runner.has_hooks_for_stage(stage):
            return

        try:
            success = self.hook_runner.execute_stage_hooks(stage, context)
            if not success:
                self.reporter.add_warning(
                    self.current_stage,
                    f"One or more {stage} hooks failed (continue_on_error enabled)"
                )
        except Exception as e:
            self.logger.error(f"💥 Hook stage '{stage}' failed: {e}")
            self.reporter.add_error(self.current_stage, f"Hook {stage} failed: {e}")
            raise

    def _create_hook_context(self) -> dict[str, Any]:
        """
        Create context dictionary for hook variable substitution.

        Returns:
            Dictionary of context variables
        """
        source_meta = self.loader.get_source_metadata()
        boot_disk = self.loader.get_boot_disk()

        # Get source and output paths
        source_path = str(boot_disk.local_path) if boot_disk else ""
        output_path = ""
        if self.output_dir and boot_disk:
            output_format = self.loader.get_output_format()
            output_path = str(self.output_dir / f"{boot_disk.id}.{output_format}")

        return create_hook_context(
            stage=self.current_stage,
            vm_name=source_meta.get("vm_name"),
            source_path=source_path,
            output_path=output_path,
        )
