# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# hyper2kvm/orchestrator/orchestrator.py

from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path
from typing import List, Optional

from ..core.logger import Log
from ..core.recovery_manager import RecoveryManager
from ..core.sanity_checker import SanityChecker
from ..core.utils import U
from ..libvirt.domain_emitter import emit_from_args
from ..testers.libvirt_tester import LibvirtTest
from ..testers.qemu_tester import QemuTest
from ..vmware.vsphere.mode import VsphereMode
from .disk_discovery import DiskDiscovery
from .disk_processor import DiskProcessor
from .virt_v2v_converter import VirtV2VConverter
from .vsphere_exporter import VsphereExporter
from .azure_exporter import AzureExporter

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
        self.recovery_manager: Optional[RecoveryManager] = None
        self.disks: List[Path] = []

        # Initialize component handlers
        self.v2v_converter = VirtV2VConverter(logger)
        self.vsphere_exporter = VsphereExporter(logger, args)
        self.azure_exporter = AzureExporter(logger, args)
        self.disk_discovery = DiskDiscovery(logger, args)
        self.disk_processor: Optional[DiskProcessor] = None  # Created after recovery setup

        Log.trace(
            self.logger,
            "🧠 Orchestrator init: cmd=%r output_dir=%r",
            getattr(args, "cmd", None),
            getattr(args, "output_dir", None),
        )

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
            from ..core.exceptions import Fatal

            raise Fatal(2, "pyvmomi not installed. Install: pip install pyvmomi")

        vs_action = getattr(self.args, "vs_action", "")
        if not REQUESTS_AVAILABLE and (vs_action in ("download_datastore_file", "download_vm_disk", "cbt_sync")):
            from ..core.exceptions import Fatal

            raise Fatal(2, "requests not installed. Install: pip install requests")

        # Check if vSphere export (sync) mode enabled
        if self.vsphere_exporter.is_v2v_enabled():
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

    def _discover_disks(self, out_root: Path) -> Optional[Path]:
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

    def _run_pre_v2v(self, out_root: Path) -> List[Path]:
        """Run virt-v2v before internal processing if requested."""
        if not getattr(self.args, "use_v2v", False):
            return []

        use_parallel = bool(getattr(self.args, "v2v_parallel", False))
        Log.step(self.logger, f"virt-v2v pre-step ({'parallel' if use_parallel else 'single'})")

        if use_parallel and len(self.disks) > 1:
            return self.v2v_converter.convert_parallel(
                self.disks,
                out_root,
                getattr(self.args, "out_format", "qcow2"),
                getattr(self.args, "compress", False),
                getattr(self.args, "luks_passphrase", None),
                getattr(self.args, "luks_passphrase_env", None),
                getattr(self.args, "luks_keyfile", None),
                concurrency=int(getattr(self.args, "v2v_concurrency", 2)),
            )
        else:
            return self.v2v_converter.convert(
                self.disks,
                out_root,
                getattr(self.args, "out_format", "qcow2"),
                getattr(self.args, "compress", False),
                getattr(self.args, "luks_passphrase", None),
                getattr(self.args, "luks_passphrase_env", None),
                getattr(self.args, "luks_keyfile", None),
            )

    def _run_post_v2v(self, fixed_images: List[Path], out_root: Path) -> List[Path]:
        """Run virt-v2v after internal processing if requested."""
        if not getattr(self.args, "post_v2v", False) or not fixed_images:
            return fixed_images

        v2v_dir = out_root / "post-v2v"
        U.ensure_dir(v2v_dir)

        use_parallel = bool(getattr(self.args, "v2v_parallel", False))
        Log.step(self.logger, f"virt-v2v post-step ({'parallel' if use_parallel else 'single'})")

        if use_parallel and len(fixed_images) > 1:
            v2v_images = self.v2v_converter.convert_parallel(
                fixed_images,
                v2v_dir,
                getattr(self.args, "out_format", "qcow2"),
                getattr(self.args, "compress", False),
                getattr(self.args, "luks_passphrase", None),
                getattr(self.args, "luks_passphrase_env", None),
                getattr(self.args, "luks_keyfile", None),
                concurrency=int(getattr(self.args, "v2v_concurrency", 2)),
            )
        else:
            v2v_images = self.v2v_converter.convert(
                fixed_images,
                v2v_dir,
                getattr(self.args, "out_format", "qcow2"),
                getattr(self.args, "compress", False),
                getattr(self.args, "luks_passphrase", None),
                getattr(self.args, "luks_passphrase_env", None),
                getattr(self.args, "luks_keyfile", None),
            )

        return v2v_images if v2v_images else fixed_images

    def _process_disks(self, out_root: Path) -> List[Path]:
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
        fixed_images: List[Path] = []
        for idx, disk in enumerate(self.disks):
            if not disk.exists():
                U.die(self.logger, f"🔥 Disk not found: {disk}", 1)
            fixed_images.append(self.disk_processor.process_single_disk(disk, out_root, idx, len(self.disks)))

        Log.trace(self.logger, "📦 _process_disks: produced=%d", len(fixed_images))
        return fixed_images

    def _run_tests(self, out_images: List[Path]) -> None:
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

    def _emit_domain_xml(self, out_root: Path, out_images: List[Path]) -> None:
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

        # virt-v2v pre-step (optional)
        v2v_images = self._run_pre_v2v(out_root)
        if v2v_images:
            fixed_images = v2v_images
        else:
            fixed_images = self._process_disks(out_root)

        # virt-v2v post-step (optional)
        out_images = self._run_post_v2v(fixed_images, out_root)

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
