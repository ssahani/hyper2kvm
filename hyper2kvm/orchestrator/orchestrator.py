# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/orchestrator/orchestrator.py

from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path

from ..core.logger import Log
from ..core.recovery_manager import RecoveryManager
from ..core.sanity_checker import SanityChecker
from ..core.utils import U
from ..libvirt.domain_emitter import emit_from_args
from ..testers.libvirt_tester import LibvirtTest
from ..testers.qemu_tester import QemuTest
from ..vmware.vsphere.mode import VsphereMode
from .azure_exporter import AzureExporter
from .disk_discovery import DiskDiscovery
from .disk_processor import DiskProcessor
from .vsphere_exporter import VsphereExporter

# Check availability
try:
    from ..vmware.clients.client import PYVMOMI_AVAILABLE
except ImportError:
    PYVMOMI_AVAILABLE = False

try:
    from ..vmware.transports.http_client import REQUESTS_AVAILABLE
except ImportError:
    REQUESTS_AVAILABLE = False


class Orchestrator:
    """
    Main pipeline orchestrator.
    """

    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        self.logger = logger
        self.args = args
        self.recovery_manager: RecoveryManager | None = None
        self.disks: list[Path] = []

        # Initialize component handlers
        # Note: using only internal converters
        self.vsphere_exporter = VsphereExporter(logger, args)
        self.azure_exporter = AzureExporter(logger, args)
        self.disk_discovery = DiskDiscovery(logger, args)
        self.disk_processor: DiskProcessor | None = None  # Created after recovery setup

        Log.trace(
            self.logger,
            "🧠 Orchestrator init: cmd=%r output_dir=%r batch=%r",
            getattr(args, "cmd", None),
            getattr(args, "output_dir", None),
            getattr(args, "batch_manifest", None),
        )

    def _handle_batch_mode(self) -> None:
        """Handle batch conversion mode."""
        from ..manifest.batch_orchestrator import BatchOrchestrator

        batch_manifest_path = getattr(self.args, "batch_manifest")
        self.logger.info("🔄 Batch mode detected")
        self.logger.info(f"📋 Batch manifest: {batch_manifest_path}")

        try:
            batch_orchestrator = BatchOrchestrator(batch_manifest_path, logger=self.logger)
            report = batch_orchestrator.run()

            # Overall success/failure
            if report["batch"]["success"]:
                self.logger.info("✅ All VMs converted successfully")
            else:
                failed = report["batch"]["failed_vms"]
                total = report["batch"]["total_vms"]
                self.logger.warning(f"⚠️  Batch completed with {failed}/{total} failures")

        except Exception as e:
            self.logger.error(f"💥 Batch mode failed: {e}")
            U.die(self.logger, f"Batch conversion error: {e}", 1)

    def _setup_recovery(self, out_root: Path) -> None:
        """Setup recovery manager if enabled."""
        if getattr(self.args, "enable_recovery", False):
            recovery_dir = out_root / "recovery"
            self.recovery_manager = RecoveryManager(self.logger, recovery_dir)
            self.logger.info(f"🛟 Recovery mode enabled: {recovery_dir}")
            # Now create disk processor with recovery manager
            self.disk_processor = DiskProcessor(self.logger, self.args, self.recovery_manager)
        else:
            Log.trace(self.logger, "🛟 Recovery mode disabled")
            self.disk_processor = DiskProcessor(self.logger, self.args, None)

    def _handle_vsphere_mode(self, out_root: Path) -> bool:
        """
        Handle vSphere mode operations.

        Returns:
            True if handled and should continue pipeline, False if should exit
        """
        if not PYVMOMI_AVAILABLE:
            from ..core.exceptions import Fatal, create_helpful_error

            raise create_helpful_error(
                Fatal,
                "pyvmomi not installed",
                code=2,
                solutions=[
                    "Install pyvmomi: pip install pyvmomi",
                    "Or install with vSphere support: pip install hyper2kvm[vsphere]"
                ],
                causes=[
                    "pyvmomi package not found in Python environment",
                    "Virtual environment not activated"
                ],
                doc_link="02-Installation.md#vsphere-integration"
            )

        vs_action = getattr(self.args, "vs_action", "")
        if not REQUESTS_AVAILABLE and (vs_action in ("download_datastore_file", "download_vm_disk", "cbt_sync")):
            from ..core.exceptions import Fatal, create_helpful_error

            raise create_helpful_error(
                Fatal,
                "requests library not installed",
                code=2,
                solutions=[
                    "Install requests: pip install requests",
                    "Required for HTTP downloads and vCenter API calls"
                ],
                causes=[
                    "requests package not installed",
                    "Missing optional dependencies"
                ],
                doc_link="02-Installation.md#python-dependencies"
            )

        # Check if vSphere export (sync) mode enabled
        if self.vsphere_exporter.is_export_enabled():
            U.banner(self.logger, "vSphere export (sync)")
            exported = self.vsphere_exporter.export_many_sync(out_root)
            if exported:
                self.disks = exported
                self.logger.info("📦 vSphere export produced %d disk(s)", len(self.disks))
                return True  # Continue pipeline
            self.logger.warning("vSphere export produced no disks; falling back to VsphereMode")
            VsphereMode(self.logger, self.args).run()
            return False  # Exit

        # Standard vsphere mode (exits after running)
        VsphereMode(self.logger, self.args).run()
        return False

    def _handle_azure_mode(self, out_root: Path) -> bool:
        """
        Handle Azure mode operations.

        Returns:
            True if handled and should continue pipeline, False if should exit
        """
        if self.azure_exporter.is_enabled():
            U.banner(self.logger, "Azure export")
            exported = self.azure_exporter.export_vms(out_root)
            if exported:
                self.disks = exported
                self.logger.info("📦 Azure export produced %d disk(s)", len(self.disks))
                return True  # Continue pipeline
            self.logger.warning("Azure export produced no disks")
            return False  # Exit
        return True  # Not Azure mode, continue

    def _discover_disks(self, out_root: Path) -> Path | None:
        """
        Discover disks from various sources.

        Returns:
            temp_dir if cleanup needed, None otherwise
        """
        cmd = getattr(self.args, "cmd", None)
        Log.trace(self.logger, "🧭 _discover_disks: cmd=%r", cmd)

        if cmd == "azure":
            should_continue = self._handle_azure_mode(out_root)
            if not should_continue:
                return None  # Azure mode handled everything

        if cmd == "vsphere":
            should_continue = self._handle_vsphere_mode(out_root)
            if not should_continue:
                return None  # VsphereMode handled everything

        # Use DiskDiscovery for all other modes
        if not self.disks:  # Only if vsphere/azure didn't already populate
            self.disks, temp_dir = self.disk_discovery.discover(out_root)
            return temp_dir

        return None


    def _process_disks(self, out_root: Path) -> list[Path]:
        """Process disks through internal pipeline."""
        if not self.disk_processor:
            raise RuntimeError("DiskProcessor not initialized (call _setup_recovery first)")

        Log.trace(
            self.logger,
            "🧠 _process_disks: disks=%d parallel=%s",
            len(self.disks),
            getattr(self.args, "parallel_processing", False),
        )

        if len(self.disks) > 1 and getattr(self.args, "parallel_processing", False):
            return self.disk_processor.process_disks_parallel(self.disks, out_root)

        # Sequential processing
        fixed_images: list[Path] = []
        for idx, disk in enumerate(self.disks):
            if not disk.exists():
                U.die(self.logger, f"🔥 Disk not found: {disk}", 1)
            fixed_images.append(self.disk_processor.process_single_disk(disk, out_root, idx, len(self.disks)))

        Log.trace(self.logger, "📦 _process_disks: produced=%d", len(fixed_images))
        return fixed_images

    def _run_tests(self, out_images: list[Path]) -> None:
        """Run validation tests if requested."""
        if not out_images:
            return

        test_image = out_images[0]

        if getattr(self.args, "libvirt_test", False):
            Log.step(self.logger, "Libvirt smoke test")
            LibvirtTest.run(
                self.logger,
                test_image,
                name=getattr(self.args, "vm_name", "converted-vm"),
                memory_mib=getattr(self.args, "memory", 2048),
                vcpus=getattr(self.args, "vcpus", 2),
                uefi=getattr(self.args, "uefi", False),
                timeout_s=getattr(self.args, "timeout", 60),
                keep=getattr(self.args, "keep_domain", False),
                headless=getattr(self.args, "headless", False),
            )
            Log.ok(self.logger, "Libvirt test complete")

        if getattr(self.args, "qemu_test", False):
            Log.step(self.logger, "QEMU smoke test")
            QemuTest.run(
                self.logger,
                test_image,
                memory_mib=getattr(self.args, "memory", 2048),
                vcpus=getattr(self.args, "vcpus", 2),
                uefi=getattr(self.args, "uefi", False),
            )
            Log.ok(self.logger, "QEMU test complete")

    def _emit_domain_xml(self, out_root: Path, out_images: list[Path]) -> None:
        """Emit libvirt domain XML if requested."""
        if not out_images:
            return

        try:
            emit_from_args(self.logger, self.args, out_root=out_root, out_images=out_images)
        except Exception as e:
            self.logger.warning("Failed to emit libvirt domain XML: %s", e)
            self.logger.debug("💥 emit_from_args exception", exc_info=True)

    def run(self) -> None:
        """Main orchestration pipeline."""

        # Check for batch mode first
        if getattr(self.args, "batch_manifest", None):
            self._handle_batch_mode()
            return

        # Welcome banner
        self.logger.info("━" * 80)
        self.logger.info("🚀 hyper2kvm - Production-Grade Hypervisor to KVM Migration Toolkit")
        self.logger.info("   Built for the Enterprise Linux ecosystem (Fedora/RHEL/CentOS)")
        self.logger.info("")
        self.logger.info("   ✨ Features:")
        self.logger.info("      • VMware vSphere integration powered by hypersdk")
        self.logger.info("      • Offline guest fixes with VMCraft disk manipulation")
        self.logger.info("      • Windows driver injection & registry editing")
        self.logger.info("      • Deterministic fstab/grub repair for first-boot success")
        self.logger.info("━" * 80)

        out_root = Path(self.args.output_dir).expanduser().resolve()
        U.ensure_dir(out_root)

        self._setup_recovery(out_root)

        # Sanity checks
        sanity = SanityChecker(self.logger, self.args)
        Log.step(self.logger, "Sanity checks")
        sanity.check_all()
        Log.ok(self.logger, "Sanity checks passed")

        U.banner(self.logger, f"Mode: {self.args.cmd}")

        # Handle daemon mode
        if self.args.cmd == "daemon":
            # Check for manifest workflow mode
            if getattr(self.args, "manifest_workflow_mode", False):
                # Manifest workflow daemon mode
                if not getattr(self.args, "manifest_workflow_dir", None):
                    from ..core.exceptions import Fatal
                    raise Fatal(2, "Manifest workflow mode requires --manifest-workflow-dir")

                from ..daemon.manifest_workflow_daemon import ManifestWorkflowDaemon
                watcher = ManifestWorkflowDaemon(self.logger, self.args)
                watcher.run()
                return  # Daemon runs until stopped
            # Check for workflow mode (3-directory) vs standard daemon mode
            elif getattr(self.args, "workflow_mode", False):
                # Workflow daemon mode
                if not getattr(self.args, "workflow_dir", None):
                    from ..core.exceptions import Fatal
                    raise Fatal(2, "Workflow mode requires --workflow-dir or config: workflow_dir")

                from ..daemon.workflow_daemon import WorkflowDaemon
                watcher = WorkflowDaemon(self.logger, self.args)
                watcher.run()
                return  # Daemon runs until stopped
            else:
                # Standard daemon mode
                if not getattr(self.args, "watch_dir", None):
                    from ..core.exceptions import Fatal
                    raise Fatal(2, "Daemon mode requires --watch-dir or config: watch_dir")

                from ..daemon.daemon_watcher import DaemonWatcher
                watcher = DaemonWatcher(self.logger, self.args)
                watcher.run()
                return  # Daemon runs until stopped

        # Check if write operations needed
        write_actions = (
            (not getattr(self.args, "dry_run", False))
            or bool(getattr(self.args, "to_output", None))
            or bool(getattr(self.args, "flatten", False))
        )
        Log.trace(
            self.logger,
            "🧾 write_actions=%s (dry_run=%s to_output=%r flatten=%s)",
            write_actions,
            getattr(self.args, "dry_run", False),
            getattr(self.args, "to_output", None),
            getattr(self.args, "flatten", False),
        )
        U.require_root_if_needed(self.logger, write_actions)

        # Discover disks
        temp_dir = self._discover_disks(out_root)
        if temp_dir is None and getattr(self.args, "cmd", None) in ("live-fix", "vsphere", "azure", "daemon"):
            if getattr(self.args, "cmd", None) == "vsphere" and self.disks:
                Log.trace(self.logger, "🌐 vsphere: continuing pipeline with exported disks=%d", len(self.disks))
            elif getattr(self.args, "cmd", None) == "azure" and self.disks:
                Log.trace(self.logger, "☁️ azure: continuing pipeline with exported disks=%d", len(self.disks))
            else:
                return  # Early exit for modes that don't produce disks

        if self.recovery_manager:
            self.recovery_manager.save_checkpoint(
                "disks_discovered",
                {"count": len(self.disks), "disks": [str(d) for d in self.disks]},
            )

        # Process disks through internal pipeline
        # Note: using only internal converters and fixers
        fixed_images = self._process_disks(out_root)
        out_images = fixed_images

        # Tests
        self._run_tests(out_images)

        # Cleanup recovery checkpoints
        if self.recovery_manager:
            self.recovery_manager.cleanup_old_checkpoints()

        # Cleanup temp directory
        if temp_dir and temp_dir.exists():
            Log.trace(self.logger, "🧹 cleaning temp_dir=%s", temp_dir)
            shutil.rmtree(temp_dir, ignore_errors=True)

        # Emit domain XML
        self._emit_domain_xml(out_root, out_images)

        # Final summary
        U.banner(self.logger, "Done")
        self.logger.info(f"📦 Output directory: {out_root}")
        if out_images:
            self.logger.info("🎉 Generated images:")
            for img in out_images:
                self.logger.info(f" - {img}")
