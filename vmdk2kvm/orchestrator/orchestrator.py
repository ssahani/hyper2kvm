from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional

from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from ..config.config_loader import YAML_AVAILABLE, yaml
from ..converters.fetch import Fetch
from ..converters.flatten import Flatten
from ..converters.ovf_extractor import OVF
from ..converters.qemu_converter import Convert
from ..core.exceptions import Fatal
from ..core.recovery_manager import RecoveryManager
from ..core.sanity_checker import SanityChecker
from ..core.utils import U
from ..fixers.live_fixer import LiveFixer
from ..fixers.offline_fixer import OfflineFSFix
from ..ssh.ssh_client import SSHClient
from ..ssh.ssh_config import SSHConfig
from ..testers.libvirt_tester import LibvirtTest
from ..testers.qemu_tester import QemuTest
from ..vmware.vmdk_parser import VMDK
from ..vmware.vmware_client import PYVMOMI_AVAILABLE, REQUESTS_AVAILABLE
from ..vmware.vsphere_mode import VsphereMode


class Orchestrator:
    """
    Top-level pipeline runner.

    Responsibilities:
    - Determine input disks (local/fetch/ova/ovf/vsphere)
    - Optionally flatten snapshots
    - Run offline fixer
    - Optionally convert output format/compress
    - Optional virt-v2v / post-v2v
    - Optional libvirt/qemu smoke tests
    - Optional parallel processing for multi-disk inputs
    """

    @staticmethod
    def v2v_convert(
        logger: logging.Logger,
        disks: List[Path],
        out_root: Path,
        out_format: str,
        compress: bool,
    ) -> List[Path]:
        if U.which("virt-v2v") is None:
            logger.warning("virt-v2v not found; falling back to internal fixer")
            return []

        cmd = ["virt-v2v"]
        for d in disks:
            cmd += ["-i", "disk", str(d)]
        cmd += ["-o", "local", "-os", str(out_root), "-of", out_format]
        if compress:
            cmd += ["--compressed"]

        U.banner(logger, "Using virt-v2v for conversion")
        U.run_cmd(logger, cmd, check=True, capture=False)

        # NOTE: virt-v2v may output other formats; you requested out_format but
        # many flows produce qcow2. Keep behavior same as your current code.
        out_images = list(out_root.glob("*.qcow2"))
        logger.info("virt-v2v conversion completed.")
        return out_images

    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        self.logger = logger
        self.args = args
        self.recovery_manager: Optional[RecoveryManager] = None
        self.disks: List[Path] = []

    def log_input_layout(self, vmdk: Path) -> None:
        try:
            st = vmdk.stat()
            self.logger.info(f"Input VMDK: {vmdk} ({U.human_bytes(st.st_size)})")
        except Exception:
            self.logger.info(f"Input VMDK: {vmdk}")

        layout, extent = VMDK.guess_layout(self.logger, vmdk)
        if layout == "monolithic":
            self.logger.info("VMDK layout: monolithic/binary (no separate extent) ✅")
        else:
            if extent and extent.exists():
                self.logger.info(f"VMDK layout: descriptor + extent ✅ ({extent})")
            else:
                self.logger.warning(f"VMDK layout: descriptor (extent missing?) ⚠️ ({extent})")

    def _load_cloud_init_config(self) -> Optional[dict]:
        p = getattr(self.args, "cloud_init_config", None)
        if not p:
            return None
        try:
            config_path = Path(p).expanduser().resolve()
            if not config_path.exists():
                self.logger.warning(f"Cloud-init config not found: {config_path}")
                return None

            if config_path.suffix.lower() == ".json":
                return json.loads(config_path.read_text(encoding="utf-8"))

            if YAML_AVAILABLE:
                return yaml.safe_load(config_path.read_text(encoding="utf-8"))

            self.logger.warning("YAML not available, cannot load cloud-init config")
            return None
        except Exception as e:
            self.logger.warning(f"Failed to load cloud-init config: {e}")
            return None

    def process_single_disk(self, disk: Path, out_root: Path, disk_index: int = 0) -> Path:
        self.log_input_layout(disk)

        working = disk

        # Flatten first (optional)
        if getattr(self.args, "flatten", False):
            workdir = (
                Path(self.args.workdir).expanduser().resolve()
                if getattr(self.args, "workdir", None)
                else (out_root / "work")
            )
            U.ensure_dir(workdir)
            working = Flatten.to_working(
                self.logger,
                disk,
                workdir,
                fmt=getattr(self.args, "flatten_format", "qcow2"),
            )

        # Per-disk report path (optional)
        report_path = None
        if getattr(self.args, "report", None):
            rp = Path(self.args.report)
            if len(self.disks) > 1:
                report_path = (out_root / f"{rp.stem}_disk{disk_index}{rp.suffix}") if not rp.is_absolute() else rp
            else:
                report_path = rp if rp.is_absolute() else (out_root / rp)

        cloud_init_data = self._load_cloud_init_config()

        fixer = OfflineFSFix(
            self.logger,
            working,
            dry_run=getattr(self.args, "dry_run", False),
            no_backup=getattr(self.args, "no_backup", False),
            print_fstab=getattr(self.args, "print_fstab", False),
            update_grub=not getattr(self.args, "no_grub", False),
            regen_initramfs=getattr(self.args, "regen_initramfs", True),
            fstab_mode=getattr(self.args, "fstab_mode", "stabilize-all"),
            report_path=report_path,
            remove_vmware_tools=getattr(self.args, "remove_vmware_tools", False),
            inject_cloud_init=cloud_init_data,
            recovery_manager=self.recovery_manager,
            resize=getattr(self.args, "resize", None),
            virtio_drivers_dir=getattr(self.args, "virtio_drivers_dir", None),
        )
        fixer.run()

        out_image: Optional[Path] = None

        # Convert final output (optional)
        if getattr(self.args, "to_output", None) and not getattr(self.args, "dry_run", False):
            if len(self.disks) > 1:
                base_output = Path(self.args.to_output)
                out_image = base_output.parent / f"{base_output.stem}_disk{disk_index}{base_output.suffix}"
            else:
                out_image = Path(self.args.to_output)

            if not out_image.is_absolute():
                out_image = out_root / out_image
            out_image = out_image.expanduser().resolve()

            def progress_callback(progress: float) -> None:
                # keep same behavior, but less spammy callers can override upstream
                if progress < 1.0:
                    self.logger.info(f"Conversion progress: {progress:.1%}")
                else:
                    self.logger.info("Conversion complete")

            Convert.convert_image_with_progress(
                self.logger,
                working,
                out_image,
                out_format=getattr(self.args, "out_format", "qcow2"),
                compress=getattr(self.args, "compress", False),
                compress_level=getattr(self.args, "compress_level", None),
                progress_callback=progress_callback,
            )

            Convert.validate(self.logger, out_image)

            if getattr(self.args, "checksum", False):
                cs = U.checksum(out_image)
                self.logger.info(f"SHA256 checksum: {cs}")

        return out_image if out_image else working

    def process_disks_parallel(self, disks: List[Path], out_root: Path) -> List[Path]:
        self.logger.info(f"Processing {len(disks)} disks in parallel")
        results: List[Path] = []

        max_workers = min(4, len(disks), (os.cpu_count() or 1))

        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Processing disks", total=len(disks))

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self.process_single_disk, disk, out_root, idx): (idx, disk)
                    for idx, disk in enumerate(disks)
                }
                for future in concurrent.futures.as_completed(futures):
                    idx, disk = futures[future]
                    try:
                        result = future.result()
                        results.append(result)
                        self.logger.info(f"Completed processing disk {idx}: {disk.name}")
                    except Exception as e:
                        self.logger.error(f"Failed processing disk {idx} ({disk.name}): {e}")
                    progress.update(task, advance=1)

        return results

    def _setup_recovery(self, out_root: Path) -> None:
        if getattr(self.args, "enable_recovery", False):
            recovery_dir = out_root / "recovery"
            self.recovery_manager = RecoveryManager(self.logger, recovery_dir)
            self.logger.info(f"Recovery mode enabled: {recovery_dir}")

    def _discover_disks(self, out_root: Path) -> Optional[Path]:
        """
        Fill self.disks based on args.cmd.
        Returns temp_dir if created (needs cleanup), else None.
        """
        temp_dir: Optional[Path] = None

        cmd = getattr(self.args, "cmd", None)

        if cmd == "vsphere":
            if not PYVMOMI_AVAILABLE:
                raise Fatal(2, "pyvmomi not installed. Install: pip install pyvmomi")

            # Your code used (download,cbt-sync) but your subcommands are snake_case;
            # keep intent: requests needed for download-ish actions.
            vs_action = getattr(self.args, "vs_action", "")
            if not REQUESTS_AVAILABLE and (vs_action in ("download_datastore_file", "download_vm_disk", "cbt_sync")):
                raise Fatal(2, "requests not installed. Install: pip install requests")

            VsphereMode(self.logger, self.args).run()
            return None  # vsphere handles its own output; stop orchestration

        if cmd == "local":
            self.disks = [Path(self.args.vmdk).expanduser().resolve()]

        elif cmd == "fetch-and-fix":
            sshc = SSHClient(
                self.logger,
                SSHConfig(
                    host=self.args.host,
                    user=self.args.user,
                    port=self.args.port,
                    identity=getattr(self.args, "identity", None),
                    ssh_opt=getattr(self.args, "ssh_opt", None),
                    sudo=False,
                ),
            )
            fetch_dir = (
                Path(self.args.fetch_dir).expanduser().resolve()
                if getattr(self.args, "fetch_dir", None)
                else (out_root / "downloaded")
            )
            U.ensure_dir(fetch_dir)
            desc = Fetch.fetch_descriptor_and_extent(
                self.logger,
                sshc,
                self.args.remote,
                fetch_dir,
                getattr(self.args, "fetch_all", False),
            )
            self.disks = [desc]

        elif cmd == "ova":
            temp_dir = out_root / "extracted"
            self.disks = OVF.extract_ova(
                self.logger,
                Path(self.args.ova).expanduser().resolve(),
                temp_dir,
            )

        elif cmd == "ovf":
            temp_dir = out_root / "extracted"
            self.disks = OVF.extract_ovf(
                self.logger,
                Path(self.args.ovf).expanduser().resolve(),
                temp_dir,
            )

        elif cmd == "live-fix":
            sshc = SSHClient(
                self.logger,
                SSHConfig(
                    host=self.args.host,
                    user=self.args.user,
                    port=self.args.port,
                    identity=getattr(self.args, "identity", None),
                    ssh_opt=getattr(self.args, "ssh_opt", None),
                    sudo=getattr(self.args, "sudo", False),
                ),
            )
            LiveFixer(
                self.logger,
                sshc,
                dry_run=getattr(self.args, "dry_run", False),
                no_backup=getattr(self.args, "no_backup", False),
                print_fstab=getattr(self.args, "print_fstab", False),
                update_grub=not getattr(self.args, "no_grub", False),
                regen_initramfs=getattr(self.args, "regen_initramfs", True),
                remove_vmware_tools=getattr(self.args, "remove_vmware_tools", False),
            ).run()
            self.logger.info("Live fix done.")
            return None

        else:
            U.die(self.logger, f"Unknown command: {cmd}", 1)

        return temp_dir

    def run(self) -> None:
        out_root = Path(self.args.output_dir).expanduser().resolve()
        U.ensure_dir(out_root)

        self._setup_recovery(out_root)

        sanity = SanityChecker(self.logger, self.args)
        sanity.check_all()

        U.banner(self.logger, f"Mode: {self.args.cmd}")

        write_actions = (
            (not getattr(self.args, "dry_run", False))
            or bool(getattr(self.args, "to_output", None))
            or bool(getattr(self.args, "flatten", False))
        )
        U.require_root_if_needed(self.logger, write_actions)

        temp_dir = self._discover_disks(out_root)
        if temp_dir is None and getattr(self.args, "cmd", None) in ("live-fix", "vsphere"):
            # those modes already executed
            return

        if self.recovery_manager:
            self.recovery_manager.save_checkpoint(
                "disks_discovered",
                {"count": len(self.disks), "disks": [str(d) for d in self.disks]},
            )

        fixed_images: List[Path] = []

        if getattr(self.args, "use_v2v", False):
            v2v_images = Orchestrator.v2v_convert(
                self.logger,
                self.disks,
                out_root,
                getattr(self.args, "out_format", "qcow2"),
                getattr(self.args, "compress", False),
            )
            if v2v_images:
                fixed_images = v2v_images
            else:
                fixed_images = self._internal_process(out_root)
        else:
            fixed_images = self._internal_process(out_root)

        out_images = fixed_images

        if getattr(self.args, "post_v2v", False) and out_images:
            v2v_dir = out_root / "post-v2v"
            U.ensure_dir(v2v_dir)
            v2v_images = Orchestrator.v2v_convert(
                self.logger,
                fixed_images,
                v2v_dir,
                getattr(self.args, "out_format", "qcow2"),
                getattr(self.args, "compress", False),
            )
            if v2v_images:
                out_images = v2v_images

        # Optional tests
        if out_images:
            test_image = out_images[0]

            if getattr(self.args, "libvirt_test", False):
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

            if getattr(self.args, "qemu_test", False):
                QemuTest.run(
                    self.logger,
                    test_image,
                    memory_mib=getattr(self.args, "memory", 2048),
                    vcpus=getattr(self.args, "vcpus", 2),
                    uefi=getattr(self.args, "uefi", False),
                )

        if self.recovery_manager:
            self.recovery_manager.cleanup_old_checkpoints()

        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

        U.banner(self.logger, "Done")
        self.logger.info(f"Output directory: {out_root} 📦")
        if out_images:
            self.logger.info("Generated images:")
            for img in out_images:
                self.logger.info(f" - {img}")

    def _internal_process(self, out_root: Path) -> List[Path]:
        fixed_images: List[Path] = []
        if len(self.disks) > 1 and getattr(self.args, "parallel_processing", False):
            return self.process_disks_parallel(self.disks, out_root)

        for idx, disk in enumerate(self.disks):
            if not disk.exists():
                U.die(self.logger, f"Disk not found: {disk}", 1)
            fixed_images.append(self.process_single_disk(disk, out_root, idx))

        return fixed_images


# Backward compatibility: keep old name working across the tree.
Magic = Orchestrator
