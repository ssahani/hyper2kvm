# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/orchestrator/disk_processor.py
"""
Disk processing pipeline.
Handles single and parallel disk processing operations.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from ..converters.flatten import Flatten
from ..converters.qemu.converter import Convert
from ..core.logger import Log
from ..core.recovery_manager import RecoveryManager
from ..core.utils import U
from ..fixers.offline_fixer import OfflineFSFix
from ..vmware.utils.vmdk_parser import VMDK


class DiskProcessor:
    """
    Processes disks through the conversion pipeline.

    Responsibilities:
    - Single disk processing (flatten + fix + convert)
    - Parallel multi-disk processing
    - Progress reporting
    - Output path resolution
    """

    def __init__(
        self,
        logger: logging.Logger,
        args: argparse.Namespace,
        recovery_manager: RecoveryManager | None = None,
    ):
        self.logger = logger
        self.args = args
        self.recovery_manager = recovery_manager

    @staticmethod
    def _choose_workdir(args: argparse.Namespace, out_root: Path) -> Path:
        """Choose working directory for intermediate files."""
        if getattr(args, "workdir", None):
            return Path(args.workdir).expanduser().resolve()
        return out_root / "work"

    @staticmethod
    def _resolve_output_path(to_output: str, out_root: Path, disk_index: int, multi: bool) -> Path:
        """Resolve final output path for a disk."""
        base_output = Path(to_output)
        if multi:
            base_output = base_output.parent / f"{base_output.stem}_disk{disk_index}{base_output.suffix}"
        if not base_output.is_absolute():
            base_output = out_root / base_output
        return base_output.expanduser().resolve()

    @staticmethod
    def _throttled_progress_logger(logger: logging.Logger, step_pct: int = 5) -> Callable[[float], None]:
        """Create a throttled progress callback that logs at intervals."""
        if step_pct <= 0:
            step_pct = 5
        last_bucket = {"b": -1}

        def cb(progress: float) -> None:
            b = int((progress * 100.0) // step_pct)
            if b != last_bucket["b"]:
                last_bucket["b"] = b
                if progress < 1.0:
                    logger.info(f"⏳ Conversion progress: {progress:.1%}")
                else:
                    logger.info("✅ Conversion complete")

        return cb

    def log_input_layout(self, vmdk: Path) -> None:
        """Log VMDK layout information."""
        try:
            st = vmdk.stat()
            self.logger.info(f"📥 Input VMDK: {vmdk} ({U.human_bytes(st.st_size)})")
        except Exception:
            self.logger.info(f"📥 Input VMDK: {vmdk}")

        layout, extent = VMDK.guess_layout(self.logger, vmdk)
        Log.trace(self.logger, "🧩 VMDK.guess_layout: layout=%r extent=%r", layout, str(extent) if extent else None)
        if layout == "monolithic":
            self.logger.info("VMDK layout: monolithic/binary (no separate extent) ✅")
        else:
            if extent and extent.exists():
                self.logger.info(f"VMDK layout: descriptor + extent ✅ ({extent})")
            else:
                self.logger.warning(f"VMDK layout: descriptor (extent missing?) ⚠️ ({extent})")

    def _load_cloud_init_config(self) -> dict[str, Any] | None:
        """Load cloud-init configuration if specified."""
        import json

        from ..config.config_loader import YAML_AVAILABLE, yaml

        p = getattr(self.args, "cloud_init_config", None)
        if not p:
            Log.trace(self.logger, "☁️ cloud-init: no config provided")
            return None
        try:
            config_path = Path(p).expanduser().resolve()
            if not config_path.exists():
                self.logger.warning(f"Cloud-init config not found: {config_path}")
                return None
            Log.trace(self.logger, "☁️ cloud-init: loading %s", config_path)
            if config_path.suffix.lower() == ".json":
                return json.loads(config_path.read_text(encoding="utf-8"))
            if YAML_AVAILABLE:
                return yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.logger.warning("YAML not available, cannot load cloud-init config")
            return None
        except Exception as e:
            self.logger.warning(f"Failed to load cloud-init config: {e}")
            Log.trace(self.logger, "💥 cloud-init load exception", exc_info=True)
            return None

    def _load_firstboot_config(self) -> dict[str, Any] | None:
        """Load firstboot scripts configuration if specified."""
        import json

        from ..config.config_loader import YAML_AVAILABLE, yaml

        p = getattr(self.args, "firstboot_scripts", None)
        if not p:
            Log.trace(self.logger, "🚀 firstboot: no config provided")
            return None
        try:
            config_path = Path(p).expanduser().resolve()
            if not config_path.exists():
                self.logger.warning(f"Firstboot config not found: {config_path}")
                return None
            Log.trace(self.logger, "🚀 firstboot: loading %s", config_path)
            if config_path.suffix.lower() == ".json":
                return json.loads(config_path.read_text(encoding="utf-8"))
            if YAML_AVAILABLE:
                return yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.logger.warning("YAML not available, cannot load firstboot config")
            return None
        except Exception as e:
            self.logger.warning(f"Failed to load firstboot config: {e}")
            Log.trace(self.logger, "💥 firstboot load exception", exc_info=True)
            return None

    def _load_network_config_inject(self) -> dict[str, Any] | None:
        """Load network configuration injection if specified."""
        import json

        from ..config.config_loader import YAML_AVAILABLE, yaml

        p = getattr(self.args, "network_config_inject", None)
        if not p:
            Log.trace(self.logger, "🌐 network-config-inject: no config provided")
            return None
        try:
            config_path = Path(p).expanduser().resolve()
            if not config_path.exists():
                self.logger.warning(f"Network config inject file not found: {config_path}")
                return None
            Log.trace(self.logger, "🌐 network-config-inject: loading %s", config_path)
            if config_path.suffix.lower() == ".json":
                return json.loads(config_path.read_text(encoding="utf-8"))
            if YAML_AVAILABLE:
                return yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.logger.warning("YAML not available, cannot load network config inject")
            return None
        except Exception as e:
            self.logger.warning(f"Failed to load network config inject: {e}")
            Log.trace(self.logger, "💥 network-config-inject load exception", exc_info=True)
            return None

    def _load_user_config_inject(self) -> dict[str, Any] | None:
        """Load user configuration injection if specified."""
        import json

        from ..config.config_loader import YAML_AVAILABLE, yaml

        p = getattr(self.args, "user_config_inject", None)
        if not p:
            Log.trace(self.logger, "👤 user-config-inject: no config provided")
            return None
        try:
            config_path = Path(p).expanduser().resolve()
            if not config_path.exists():
                self.logger.warning(f"User config inject file not found: {config_path}")
                return None
            Log.trace(self.logger, "👤 user-config-inject: loading %s", config_path)
            if config_path.suffix.lower() == ".json":
                return json.loads(config_path.read_text(encoding="utf-8"))
            if YAML_AVAILABLE:
                return yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.logger.warning("YAML not available, cannot load user config inject")
            return None
        except Exception as e:
            self.logger.warning(f"Failed to load user config inject: {e}")
            Log.trace(self.logger, "💥 user-config-inject load exception", exc_info=True)
            return None

    def _load_service_config_inject(self) -> dict[str, Any] | None:
        """Load systemd service configuration injection if specified."""
        import json

        from ..config.config_loader import YAML_AVAILABLE, yaml

        p = getattr(self.args, "service_config_inject", None)
        if not p:
            Log.trace(self.logger, "⚙️ service-config-inject: no config provided")
            return None
        try:
            config_path = Path(p).expanduser().resolve()
            if not config_path.exists():
                self.logger.warning(f"Service config inject file not found: {config_path}")
                return None
            Log.trace(self.logger, "⚙️ service-config-inject: loading %s", config_path)
            if config_path.suffix.lower() == ".json":
                return json.loads(config_path.read_text(encoding="utf-8"))
            if YAML_AVAILABLE:
                return yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.logger.warning("YAML not available, cannot load service config inject")
            return None
        except Exception as e:
            self.logger.warning(f"Failed to load service config inject: {e}")
            Log.trace(self.logger, "💥 service-config-inject load exception", exc_info=True)
            return None

    def _load_hostname_config_inject(self) -> dict[str, Any] | None:
        """Load hostname configuration injection if specified."""
        import json

        from ..config.config_loader import YAML_AVAILABLE, yaml

        p = getattr(self.args, "hostname_config_inject", None)
        if not p:
            Log.trace(self.logger, "🏷️ hostname-config-inject: no config provided")
            return None
        try:
            config_path = Path(p).expanduser().resolve()
            if not config_path.exists():
                self.logger.warning(f"Hostname config inject file not found: {config_path}")
                return None
            Log.trace(self.logger, "🏷️ hostname-config-inject: loading %s", config_path)
            if config_path.suffix.lower() == ".json":
                return json.loads(config_path.read_text(encoding="utf-8"))
            if YAML_AVAILABLE:
                return yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.logger.warning("YAML not available, cannot load hostname config inject")
            return None
        except Exception as e:
            self.logger.warning(f"Failed to load hostname config inject: {e}")
            Log.trace(self.logger, "💥 hostname-config-inject load exception", exc_info=True)
            return None

    def _is_luks_enabled(self) -> bool:
        """Check if LUKS unlocking is enabled."""
        if hasattr(self.args, "luks_enable"):
            enabled = bool(self.args.luks_enable)
            Log.trace(self.logger, "🔐 luks_enable flag: %s", enabled)
            return enabled
        enabled = bool(
            getattr(self.args, "luks_passphrase", None)
            or getattr(self.args, "luks_passphrase_env", None)
            or getattr(self.args, "luks_keyfile", None)
        )
        Log.trace(self.logger, "🔐 luks implicit enabled: %s", enabled)
        return enabled

    def process_single_disk(self, disk: Path, out_root: Path, disk_index: int, total_disks: int) -> Path:
        """
        Process a single disk through the pipeline.

        Args:
            disk: Input disk path
            out_root: Output directory root
            disk_index: Index of this disk (for naming)
            total_disks: Total number of disks being processed

        Returns:
            Path to final output image
        """
        Log.step(self.logger, f"Processing disk {disk_index + 1}/{total_disks}: {disk.name}")
        Log.trace(self.logger, "🧱 process_single_disk: disk=%s out_root=%s", disk, out_root)

        self.log_input_layout(disk)
        working = disk

        # Flatten if requested
        if getattr(self.args, "flatten", False):
            workdir = self._choose_workdir(self.args, out_root)
            U.ensure_dir(workdir)
            Log.step(self.logger, f"Flatten snapshots → {workdir}")
            working = Flatten.to_working(
                self.logger,
                disk,
                workdir,
                fmt=getattr(self.args, "flatten_format", "qcow2"),
            )
            Log.ok(self.logger, f"Flattened: {working.name}")

        # Report path
        report_path = None
        if getattr(self.args, "report", None):
            rp = Path(self.args.report)
            if total_disks > 1:
                report_path = (out_root / f"{rp.stem}_disk{disk_index}{rp.suffix}") if not rp.is_absolute() else rp
            else:
                report_path = rp if rp.is_absolute() else (out_root / rp)
            Log.trace(self.logger, "🧾 report_path=%s", report_path)

        # Load cloud-init config
        cloud_init_data = self._load_cloud_init_config()
        if cloud_init_data is not None:
            Log.trace(
                self.logger,
                "☁️ cloud-init loaded: keys=%s",
                sorted(cloud_init_data.keys()) if isinstance(cloud_init_data, dict) else type(cloud_init_data).__name__,
            )

        # Load firstboot scripts config
        firstboot_data = self._load_firstboot_config()
        if firstboot_data is not None:
            Log.trace(
                self.logger,
                "🚀 firstboot loaded: keys=%s",
                sorted(firstboot_data.keys()) if isinstance(firstboot_data, dict) else type(firstboot_data).__name__,
            )

        # Load network config inject
        network_config_data = self._load_network_config_inject()
        if network_config_data is not None:
            Log.trace(
                self.logger,
                "🌐 network-config-inject loaded: keys=%s",
                sorted(network_config_data.keys()) if isinstance(network_config_data, dict) else type(network_config_data).__name__,
            )

        # Load user config inject
        user_config_data = self._load_user_config_inject()
        if user_config_data is not None:
            Log.trace(
                self.logger,
                "👤 user-config-inject loaded: keys=%s",
                sorted(user_config_data.keys()) if isinstance(user_config_data, dict) else type(user_config_data).__name__,
            )

        # Load service config inject
        service_config_data = self._load_service_config_inject()
        if service_config_data is not None:
            Log.trace(
                self.logger,
                "⚙️ service-config-inject loaded: keys=%s",
                sorted(service_config_data.keys()) if isinstance(service_config_data, dict) else type(service_config_data).__name__,
            )

        # Load hostname config inject
        hostname_config_data = self._load_hostname_config_inject()
        if hostname_config_data is not None:
            Log.trace(
                self.logger,
                "🏷️ hostname-config-inject loaded: keys=%s",
                sorted(hostname_config_data.keys()) if isinstance(hostname_config_data, dict) else type(hostname_config_data).__name__,
            )

        # Offline fixes
        Log.step(self.logger, "Offline filesystem fixes")
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
            firstboot_scripts=firstboot_data,
            network_config_inject=network_config_data,
            user_config_inject=user_config_data,
            service_config_inject=service_config_data,
            hostname_config_inject=hostname_config_data,
            recovery_manager=self.recovery_manager,
            resize=getattr(self.args, "resize", None),
            virtio_drivers_dir=getattr(self.args, "virtio_drivers_dir", None),
            luks_enable=self._is_luks_enabled(),
            luks_passphrase=getattr(self.args, "luks_passphrase", None),
            luks_passphrase_env=getattr(self.args, "luks_passphrase_env", None),
            luks_keyfile=getattr(self.args, "luks_keyfile", None),
            luks_mapper_prefix=getattr(self.args, "luks_mapper_prefix", "hyper2kvm-crypt"),
        )

        # Pass initramfs_add_drivers to fixer if specified
        if hasattr(self.args, "initramfs_add_drivers") and self.args.initramfs_add_drivers:
            fixer.initramfs_add_drivers = self.args.initramfs_add_drivers
        fixer.run()
        Log.ok(self.logger, "Offline fixes complete")

        # Convert to output format if requested
        out_image: Path | None = None
        if getattr(self.args, "to_output", None) and not getattr(self.args, "dry_run", False):
            out_image = self._resolve_output_path(
                str(self.args.to_output),
                out_root,
                disk_index=disk_index,
                multi=(total_disks > 1),
            )
            U.ensure_dir(out_image.parent)

            Log.step(self.logger, f"Convert image → {out_image.name}")
            Log.trace(
                self.logger,
                "🧪 convert: in=%s out=%s fmt=%s compress=%s level=%r",
                working,
                out_image,
                getattr(self.args, "out_format", "qcow2"),
                getattr(self.args, "compress", False),
                getattr(self.args, "compress_level", None),
            )

            progress_callback = self._throttled_progress_logger(self.logger, step_pct=5)

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
            Log.ok(self.logger, f"Validated: {out_image.name}")

            if getattr(self.args, "checksum", False):
                cs = U.checksum(out_image)
                self.logger.info(f"🧾 SHA256 checksum: {cs}")

        return out_image if out_image else working

    def process_disks_parallel(self, disks: list[Path], out_root: Path) -> list[Path]:
        """
        Process multiple disks in parallel.

        Args:
            disks: List of disk paths to process
            out_root: Output directory root

        Returns:
            List of output image paths
        """
        self.logger.info(f"🧵 Processing {len(disks)} disks in parallel")
        Log.trace(self.logger, "🧵 process_disks_parallel: out_root=%s", out_root)

        results: list[Path | None] = [None] * len(disks)

        env_workers = os.environ.get("VMDK2KVM_WORKERS")
        if env_workers:
            try:
                max_workers = max(1, int(env_workers))
            except Exception:
                max_workers = min(4, len(disks), (os.cpu_count() or 1))
        else:
            max_workers = min(4, len(disks), (os.cpu_count() or 1))

        Log.trace(
            self.logger,
            "👷 parallel workers: max_workers=%d (env=%r cpu=%r)",
            max_workers,
            env_workers,
            os.cpu_count(),
        )

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
                    executor.submit(self.process_single_disk, disk, out_root, idx, len(disks)): idx
                    for idx, disk in enumerate(disks)
                }
                for future in concurrent.futures.as_completed(futures):
                    idx = futures[future]
                    disk = disks[idx]
                    try:
                        result = future.result()
                        results[idx] = result
                        self.logger.info(f"✅ Completed processing disk {idx + 1}/{len(disks)}: {disk.name}")
                    except Exception as e:
                        self.logger.error(f"💥 Failed processing disk {idx + 1}/{len(disks)} ({disk.name}): {e}")
                        Log.trace(
                            self.logger,
                            "💥 process_disks_parallel exception: idx=%d disk=%s",
                            idx,
                            disk,
                            exc_info=True,
                        )
                    progress.update(task, advance=1)

        out = [r for r in results if r is not None]
        Log.trace(self.logger, "📦 process_disks_parallel: outputs=%d", len(out))
        return out
