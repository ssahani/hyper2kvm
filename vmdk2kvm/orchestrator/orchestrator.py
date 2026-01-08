# SPDX-License-Identifier: LGPL-3.0-or-later
from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence

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
from ..converters.vhd_extractor import VHD
from ..converters.qemu_converter import Convert
from ..core.cred import resolve_vsphere_creds
from ..core.exceptions import Fatal, VMwareError
from ..core.logger import Log
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

# ✅ Hook: domain emitter
from ..libvirt.domain_emitter import emit_from_args

# ---------------------------
# vSphere virt-v2v export support (SYNC ONLY)
# Keep optional import so existing code works even if module not present yet.
# ---------------------------
try:
    from ..vmware.vmware_client import VMwareClient, V2VExportOptions  # type: ignore

    VSPHERE_V2V_AVAILABLE = True
except Exception:  # pragma: no cover
    VMwareClient = None  # type: ignore
    V2VExportOptions = None  # type: ignore
    VSPHERE_V2V_AVAILABLE = False


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

    # =========================================================================
    # Existing virt-v2v wrapper (disk input)
    # =========================================================================
    @staticmethod
    def v2v_convert(
        logger: logging.Logger,
        disks: List[Path],
        out_root: Path,
        out_format: str,
        compress: bool,
        passphrase: Optional[str] = None,
        passphrase_env: Optional[str] = None,
        keyfile: Optional[str] = None,
    ) -> List[Path]:
        """
        virt-v2v wrapper with:
          - early input validation (friendlier than virt-v2v spew)
          - LUKS key handling via passphrase env or keyfile
          - robust output discovery across multiple formats
          - temp keyfile cleanup safety
        """
        Log.trace(
            logger,
            "🧪 v2v_convert: disks=%d out_root=%s out_format=%s compress=%s",
            len(disks),
            out_root,
            out_format,
            compress,
        )

        if U.which("virt-v2v") is None:
            logger.warning("virt-v2v not found; falling back to internal fixer")
            return []

        # Validate inputs early (virt-v2v errors are noisy)
        missing = [str(d) for d in disks if not Path(d).exists()]
        if missing:
            raise Fatal(2, f"virt-v2v input disk(s) not found: {', '.join(missing)}")

        U.ensure_dir(out_root)

        cmd = ["virt-v2v"]
        for d in disks:
            cmd += ["-i", "disk", str(d)]
        cmd += ["-o", "local", "-os", str(out_root), "-of", out_format]

        if compress:
            cmd += ["--compressed"]

        keyfile_path: Optional[str] = None
        is_temp_keyfile = False

        try:
            effective_passphrase = passphrase
            if passphrase_env:
                effective_passphrase = os.environ.get(passphrase_env)
                Log.trace(
                    logger,
                    "🔐 v2v_convert: passphrase_env=%r present=%s",
                    passphrase_env,
                    bool(effective_passphrase),
                )

            if keyfile:
                keyfile_path_temp = Path(keyfile).expanduser().resolve()
                if not keyfile_path_temp.exists():
                    logger.warning(f"LUKS keyfile not found: {keyfile_path_temp}")
                else:
                    keyfile_path = str(keyfile_path_temp)
                    Log.trace(logger, "🔑 v2v_convert: using keyfile=%s", keyfile_path)
            elif effective_passphrase:
                # virt-v2v expects a file reference for LUKS keys. Ensure newline.
                with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as keyfile_tmp:
                    keyfile_tmp.write(effective_passphrase + "\n")
                    keyfile_path = keyfile_tmp.name
                    is_temp_keyfile = True
                Log.trace(logger, "🧾 v2v_convert: wrote temp keyfile=%s", keyfile_path)

            if keyfile_path:
                cmd += ["--key", f"ALL:file:{keyfile_path}"]

            U.banner(logger, "Using virt-v2v for conversion")
            Log.trace(logger, "🧷 v2v_convert: cmd=%r", cmd)
            U.run_cmd(logger, cmd, check=True, capture=False)

        finally:
            if keyfile_path and is_temp_keyfile:
                try:
                    os.unlink(keyfile_path)
                    Log.trace(logger, "🧹 v2v_convert: removed temp keyfile=%s", keyfile_path)
                except Exception:
                    Log.trace(
                        logger,
                        "⚠️  v2v_convert: failed to remove temp keyfile=%s",
                        keyfile_path,
                        exc_info=True,
                    )

        # virt-v2v output files can vary; capture common ones robustly.
        patterns = ["*.qcow2", "*.raw", "*.img", "*.vmdk", "*.vdi"]
        out_images: List[Path] = []
        for pat in patterns:
            found = sorted(out_root.glob(pat))
            Log.trace(logger, "🔎 v2v_convert: glob=%s -> %d", pat, len(found))
            out_images.extend(found)

        # De-dup while preserving order
        seen: set[str] = set()
        uniq: List[Path] = []
        for p in out_images:
            s = str(p)
            if s not in seen:
                seen.add(s)
                uniq.append(p)

        if not uniq:
            logger.warning("virt-v2v completed but produced no recognizable disk outputs in out_root")
        else:
            logger.info(f"virt-v2v conversion completed: produced {len(uniq)} image(s).")
            Log.trace(logger, "📦 v2v_convert: outputs=%s", [str(x) for x in uniq])
        return uniq

    # =========================================================================
    # ADD: parallel virt-v2v when disks > 1 (multi-process v2v)
    # =========================================================================
    @staticmethod
    def v2v_convert_parallel(
        logger: logging.Logger,
        disks: List[Path],
        out_root: Path,
        out_format: str,
        compress: bool,
        passphrase: Optional[str] = None,
        passphrase_env: Optional[str] = None,
        keyfile: Optional[str] = None,
        *,
        concurrency: int = 2,
    ) -> List[Path]:
        """
        Run multiple virt-v2v processes in parallel (bounded), each fed one disk.
        Keeps stable ordering and returns a flattened list of output images.
        """
        Log.trace(logger, "🧵 v2v_convert_parallel: disks=%d out_root=%s concurrency=%s", len(disks), out_root, concurrency)

        if not disks:
            return []
        if len(disks) == 1:
            return Orchestrator.v2v_convert(
                logger,
                disks,
                out_root,
                out_format,
                compress,
                passphrase,
                passphrase_env,
                keyfile,
            )

        U.ensure_dir(out_root)
        results: List[Optional[List[Path]]] = [None] * len(disks)

        concurrency = max(1, int(concurrency))
        concurrency = min(concurrency, len(disks))

        env_c = os.environ.get("VMDK2KVM_V2V_CONCURRENCY")
        if env_c:
            try:
                concurrency = max(1, min(int(env_c), len(disks)))
            except Exception:
                pass

        def _one(idx: int, disk: Path) -> List[Path]:
            job_dir = out_root / f"v2v-disk{idx}"
            U.ensure_dir(job_dir)
            logger.info("➡️  virt-v2v job %d/%d: %s", idx + 1, len(disks), disk.name)
            Log.trace(logger, "📁 v2v job_dir=%s", job_dir)
            return Orchestrator.v2v_convert(
                logger,
                [disk],
                job_dir,
                out_format,
                compress,
                passphrase,
                passphrase_env,
                keyfile,
            )

        logger.info(f"virt-v2v parallel: {len(disks)} job(s), concurrency={concurrency}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = {ex.submit(_one, i, d): i for i, d in enumerate(disks)}
            for fut in concurrent.futures.as_completed(futs):
                i = futs[fut]
                try:
                    results[i] = fut.result()
                    Log.trace(logger, "✅ v2v job done: idx=%d outputs=%d", i, len(results[i] or []))
                except Exception as e:
                    logger.error(f"virt-v2v job failed for disk {i} ({disks[i].name}): {e}")
                    Log.trace(logger, "💥 v2v job exception: idx=%d disk=%s", i, disks[i], exc_info=True)
                    results[i] = []

        out_images: List[Path] = []
        for lst in results:
            if lst:
                out_images.extend(lst)

        seen: set[str] = set()
        uniq: List[Path] = []
        for p in out_images:
            sp = str(p)
            if sp not in seen:
                seen.add(sp)
                uniq.append(p)

        Log.trace(logger, "📦 v2v_convert_parallel: uniq_outputs=%d", len(uniq))
        return uniq

    # =========================================================================
    # vSphere export (SYNC ONLY): virt-v2v export, download-only, vddk_download
    # =========================================================================
    def _vsphere_v2v_enabled(self) -> bool:
        enabled = bool(getattr(self.args, "vs_v2v", False))
        Log.trace(self.logger, "🌐 _vsphere_v2v_enabled: %s", enabled)
        return enabled

    def _vsphere_vm_names(self) -> List[str]:
        vms: List[str] = []
        if getattr(self.args, "vs_vm", None):
            vms = [str(self.args.vs_vm)]
        elif getattr(self.args, "vs_vms", None):
            v = getattr(self.args, "vs_vms")
            if isinstance(v, (list, tuple)):
                vms = [str(x) for x in v]
            else:
                vms = [s.strip() for s in str(v).split(",") if s.strip()]
        elif getattr(self.args, "vm_name", None):
            vms = [str(self.args.vm_name)]
        out = [x for x in (n.strip() for n in vms) if x]
        Log.trace(self.logger, "🧾 _vsphere_vm_names: %s", out)
        return out

    def _vsphere_export_many_sync(self, out_root: Path) -> List[Path]:
        """
        SYNC vSphere export path.

        Policy (download-first):
          - If vs_download_only:true and vs_transport:vddk => prefer export_mode="vddk_download"
          - Else if vs_download_only:true => export_mode="download_only"
          - Else => export_mode="v2v" (virt-v2v export)
        """
        Log.step(self.logger, "vSphere export (sync) initializing…")
        Log.trace(self.logger, "🌐 vSphere export: out_root=%s VSPHERE_V2V_AVAILABLE=%s", out_root, VSPHERE_V2V_AVAILABLE)

        if not VSPHERE_V2V_AVAILABLE:
            raise Fatal(2, "vSphere export not available (VMwareClient/V2VExportOptions missing)")

        if not PYVMOMI_AVAILABLE:
            raise Fatal(2, "pyvmomi not installed. Install: pip install pyvmomi")

        vms = self._vsphere_vm_names()
        if not vms:
            raise Fatal(2, "No vSphere VM name(s) provided (vs_vm/vs_vms/vm_name)")

        # Resolve creds using shared core/cred.py (supports vs_* aliases + *_password_env)
        try:
            creds = resolve_vsphere_creds(vars(self.args))
        except Exception as e:
            raise Fatal(2, f"Missing vSphere credentials for export: {e}")

        # Accept both vs_* and vc_* knobs (since configs often carry both)
        port = int(getattr(self.args, "vs_port", None) or getattr(self.args, "vc_port", None) or 443)
        vs_insecure = getattr(self.args, "vs_insecure", None)
        insecure = bool(vs_insecure if vs_insecure is not None else getattr(self.args, "vc_insecure", False))

        timeout = getattr(self.args, "vs_timeout", None) or getattr(self.args, "vc_timeout", None)
        timeout_f = float(timeout) if timeout is not None else None

        datacenter = str(getattr(self.args, "vs_datacenter", None) or getattr(self.args, "vc_datacenter", None) or "auto")
        compute = str(getattr(self.args, "vs_compute", None) or "auto")
        transport = str(getattr(self.args, "vs_transport", "vddk")).strip().lower()

        vddk_libdir = getattr(self.args, "vs_vddk_libdir", None)
        vddk_thumbprint = getattr(self.args, "vs_vddk_thumbprint", None)
        vddk_transports = getattr(self.args, "vs_vddk_transports", None)

        snapshot_moref = getattr(self.args, "vs_snapshot_moref", None)
        create_snapshot = bool(getattr(self.args, "vs_create_snapshot", False))

        extra_args = tuple(getattr(self.args, "vs_v2v_extra_args", []) or ())
        out_format = str(getattr(self.args, "out_format", "qcow2"))

        download_only = bool(getattr(self.args, "vs_download_only", False))
        prefer_vddk_download = bool(getattr(self.args, "vs_prefer_vddk_download", True))

        # Optional vddk_download extras (only meaningful if your VMwareClient/exporter uses them)
        vddk_download_disk = getattr(self.args, "vs_vddk_download_disk", None) or getattr(self.args, "vddk_download_disk", None)
        vddk_download_output = getattr(self.args, "vs_vddk_download_output", None) or getattr(self.args, "vddk_download_output", None)

        Log.trace(
            self.logger,
            "🧷 vSphere export knobs: host=%s port=%s insecure=%s timeout=%s dc=%s compute=%s transport=%s download_only=%s prefer_vddk_download=%s",
            getattr(creds, "host", None),
            port,
            insecure,
            timeout_f,
            datacenter,
            compute,
            transport,
            download_only,
            prefer_vddk_download,
        )

        out_images: List[Path] = []
        failures: List[str] = []

        # IMPORTANT: sync context manager (no async-with)
        with VMwareClient(  # type: ignore[misc]
            self.logger,
            host=str(creds.host),
            user=str(creds.user),
            password=str(creds.password),
            port=port,
            insecure=insecure,
            timeout=timeout_f,
        ) as vc:
            Log.ok(self.logger, "vSphere connection established")
            for vm_name in vms:
                try:
                    Log.step(self.logger, f"Exporting VM: {vm_name}")
                    snap_moref = str(snapshot_moref) if snapshot_moref else None
                    if create_snapshot:
                        Log.trace(self.logger, "📸 create_snapshot enabled for %s", vm_name)
                        vm_obj = vc.get_vm_by_name(vm_name)
                        if not vm_obj:
                            raise VMwareError(f"VM not found: {vm_name}")
                        snap_obj = vc.create_snapshot(vm_obj, name=f"vmdk2kvm-{vm_name}", quiesce=True, memory=False)
                        snap_moref = vc.snapshot_moref(snap_obj)
                        self.logger.info("📸 Snapshot created: %s (moref=%s)", vm_name, snap_moref)

                    job_dir = out_root / "vsphere-v2v" / vm_name
                    U.ensure_dir(job_dir)

                    export_mode = "v2v"
                    if download_only:
                        if prefer_vddk_download and transport == "vddk":
                            export_mode = "vddk_download"
                        else:
                            export_mode = "download_only"

                    Log.trace(self.logger, "🧭 export_mode=%s job_dir=%s", export_mode, job_dir)

                    opt = V2VExportOptions(  # type: ignore[misc]
                        vm_name=vm_name,
                        export_mode=export_mode,
                        datacenter=datacenter,
                        compute=compute,
                        transport=transport,
                        no_verify=bool(getattr(self.args, "vs_no_verify", False)),
                        vddk_libdir=Path(vddk_libdir).expanduser().resolve() if vddk_libdir else None,
                        vddk_thumbprint=str(vddk_thumbprint) if vddk_thumbprint else None,
                        vddk_snapshot_moref=snap_moref,
                        vddk_transports=str(vddk_transports) if vddk_transports else None,
                        output_dir=job_dir,
                        output_format=out_format,
                        extra_args=extra_args,
                        vddk_download_disk=str(vddk_download_disk) if vddk_download_disk is not None else None,
                        vddk_download_output=Path(vddk_download_output).expanduser().resolve()
                        if vddk_download_output
                        else None,
                    )

                    # This must be SYNC in your VMwareClient implementation
                    out_path = vc.export_vm(opt)  # type: ignore[attr-defined]
                    Log.trace(self.logger, "📤 export_vm returned: %r", out_path)

                    if export_mode == "download_only":
                        self.logger.info("⬇️  vSphere download-only OK: %s -> %s", vm_name, out_path)
                        continue

                    if export_mode == "vddk_download":
                        out_images.append(Path(out_path))
                        self.logger.info("⬇️  vSphere VDDK download OK: %s -> %s", vm_name, out_path)
                        continue

                    # export_mode == "v2v": discover artifacts
                    pats = ["*.qcow2", "*.raw", "*.img", "*.vmdk", "*.vdi"]
                    imgs: List[Path] = []
                    for pat in pats:
                        found = sorted(job_dir.glob(pat))
                        Log.trace(self.logger, "🔎 vSphere discover: %s/%s -> %d", job_dir, pat, len(found))
                        imgs.extend(found)
                    if not imgs:
                        self.logger.warning("vSphere v2v export produced no outputs for %s in %s", vm_name, job_dir)
                    else:
                        self.logger.info("✅ vSphere v2v export outputs for %s: %d file(s)", vm_name, len(imgs))
                    out_images.extend(imgs)

                except Exception as e:
                    self.logger.error("vSphere export failed for %s: %s", vm_name, e)
                    Log.trace(self.logger, "💥 vSphere export exception for %s", vm_name, exc_info=True)
                    failures.append(f"{vm_name}: {e}")

        # De-dup while preserving order
        seen: set[str] = set()
        uniq: List[Path] = []
        for p in out_images:
            sp = str(p)
            if sp not in seen:
                seen.add(sp)
                uniq.append(p)

        if failures:
            self.logger.warning("Some vSphere export jobs failed:")
            for f in failures:
                self.logger.warning(" - %s", f)

        Log.trace(self.logger, "📦 vSphere export: uniq_out_images=%d", len(uniq))
        return uniq

    # =========================================================================
    # Existing init + helpers
    # =========================================================================
    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        # Keep exact logger passed in; just emit trace breadcrumbs.
        self.logger = logger
        self.args = args
        self.recovery_manager: Optional[RecoveryManager] = None
        self.disks: List[Path] = []
        Log.trace(
            self.logger,
            "🧠 Orchestrator init: cmd=%r output_dir=%r",
            getattr(args, "cmd", None),
            getattr(args, "output_dir", None),
        )

    def log_input_layout(self, vmdk: Path) -> None:
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

    def _load_cloud_init_config(self) -> Optional[dict]:
        p = getattr(self.args, "cloud_init_config", None)
        if not p:
            Log.trace(self.logger, "☁️  cloud-init: no config provided")
            return None
        try:
            config_path = Path(p).expanduser().resolve()
            if not config_path.exists():
                self.logger.warning(f"Cloud-init config not found: {config_path}")
                return None
            Log.trace(self.logger, "☁️  cloud-init: loading %s", config_path)
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

    def _is_luks_enabled(self) -> bool:
        if hasattr(self.args, "luks_enable"):
            enabled = bool(getattr(self.args, "luks_enable"))
            Log.trace(self.logger, "🔐 luks_enable flag: %s", enabled)
            return enabled
        enabled = bool(
            getattr(self.args, "luks_passphrase", None)
            or getattr(self.args, "luks_passphrase_env", None)
            or getattr(self.args, "luks_keyfile", None)
        )
        Log.trace(self.logger, "🔐 luks implicit enabled: %s", enabled)
        return enabled

    @staticmethod
    def _ensure_parent_dir(path: Optional[Path]) -> None:
        if not path:
            return
        try:
            if path.parent:
                U.ensure_dir(path.parent)
        except Exception:
            pass

    @staticmethod
    def _throttled_progress_logger(logger: logging.Logger, step_pct: int = 5):
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

    @staticmethod
    def _normalize_ssh_opts(v) -> Optional[List[str]]:
        if v is None:
            return None
        if isinstance(v, (list, tuple)):
            out = [str(x) for x in v if x is not None]
            return out or None
        return [str(v)]

    @staticmethod
    def _choose_workdir(args: argparse.Namespace, out_root: Path) -> Path:
        if getattr(args, "workdir", None):
            return Path(args.workdir).expanduser().resolve()
        return out_root / "work"

    @staticmethod
    def _resolve_output_path(to_output: str, out_root: Path, disk_index: int, multi: bool) -> Path:
        base_output = Path(to_output)
        if multi:
            base_output = base_output.parent / f"{base_output.stem}_disk{disk_index}{base_output.suffix}"
        if not base_output.is_absolute():
            base_output = out_root / base_output
        return base_output.expanduser().resolve()

    def process_single_disk(self, disk: Path, out_root: Path, disk_index: int = 0) -> Path:
        Log.step(self.logger, f"Processing disk {disk_index}: {disk.name}")
        Log.trace(self.logger, "🧱 process_single_disk: disk=%s out_root=%s", disk, out_root)

        self.log_input_layout(disk)
        working = disk

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

        report_path = None
        if getattr(self.args, "report", None):
            rp = Path(self.args.report)
            if len(self.disks) > 1:
                report_path = (out_root / f"{rp.stem}_disk{disk_index}{rp.suffix}") if not rp.is_absolute() else rp
            else:
                report_path = rp if rp.is_absolute() else (out_root / rp)
            self._ensure_parent_dir(report_path)
            Log.trace(self.logger, "🧾 report_path=%s", report_path)

        cloud_init_data = self._load_cloud_init_config()
        if cloud_init_data is not None:
            Log.trace(
                self.logger,
                "☁️  cloud-init loaded: keys=%s",
                sorted(list(cloud_init_data.keys())) if isinstance(cloud_init_data, dict) else type(cloud_init_data).__name__,
            )

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
            recovery_manager=self.recovery_manager,
            resize=getattr(self.args, "resize", None),
            virtio_drivers_dir=getattr(self.args, "virtio_drivers_dir", None),
            luks_enable=self._is_luks_enabled(),
            luks_passphrase=getattr(self.args, "luks_passphrase", None),
            luks_passphrase_env=getattr(self.args, "luks_passphrase_env", None),
            luks_keyfile=getattr(self.args, "luks_keyfile", None),
            luks_mapper_prefix=getattr(self.args, "luks_mapper_prefix", "vmdk2kvm-crypt"),
        )
        fixer.run()
        Log.ok(self.logger, "Offline fixes complete")

        out_image: Optional[Path] = None

        if getattr(self.args, "to_output", None) and not getattr(self.args, "dry_run", False):
            out_image = self._resolve_output_path(
                str(self.args.to_output),
                out_root,
                disk_index=disk_index,
                multi=(len(self.disks) > 1),
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

    def process_disks_parallel(self, disks: List[Path], out_root: Path) -> List[Path]:
        self.logger.info(f"🧵 Processing {len(disks)} disks in parallel")
        Log.trace(self.logger, "🧵 process_disks_parallel: out_root=%s", out_root)

        results: List[Optional[Path]] = [None] * len(disks)

        env_workers = os.environ.get("VMDK2KVM_WORKERS")
        if env_workers:
            try:
                max_workers = max(1, int(env_workers))
            except Exception:
                max_workers = min(4, len(disks), (os.cpu_count() or 1))
        else:
            max_workers = min(4, len(disks), (os.cpu_count() or 1))

        Log.trace(self.logger, "👷 parallel workers: max_workers=%d (env=%r cpu=%r)", max_workers, env_workers, os.cpu_count())

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
                    executor.submit(self.process_single_disk, disk, out_root, idx): idx
                    for idx, disk in enumerate(disks)
                }
                for future in concurrent.futures.as_completed(futures):
                    idx = futures[future]
                    disk = disks[idx]
                    try:
                        result = future.result()
                        results[idx] = result
                        self.logger.info(f"✅ Completed processing disk {idx}: {disk.name}")
                    except Exception as e:
                        self.logger.error(f"💥 Failed processing disk {idx} ({disk.name}): {e}")
                        Log.trace(self.logger, "💥 process_disks_parallel exception: idx=%d disk=%s", idx, disk, exc_info=True)
                    progress.update(task, advance=1)

        out = [r for r in results if r is not None]
        Log.trace(self.logger, "📦 process_disks_parallel: outputs=%d", len(out))
        return out

    def _setup_recovery(self, out_root: Path) -> None:
        if getattr(self.args, "enable_recovery", False):
            recovery_dir = out_root / "recovery"
            self.recovery_manager = RecoveryManager(self.logger, recovery_dir)
            self.logger.info(f"🛟 Recovery mode enabled: {recovery_dir}")
        else:
            Log.trace(self.logger, "🛟 Recovery mode disabled")

    def _discover_disks(self, out_root: Path) -> Optional[Path]:
        """
        Fill self.disks based on args.cmd.
        Returns temp_dir if created (needs cleanup), else None.
        """
        temp_dir: Optional[Path] = None
        cmd = getattr(self.args, "cmd", None)

        Log.trace(self.logger, "🧭 _discover_disks: cmd=%r out_root=%s", cmd, out_root)

        if cmd == "vsphere":
            if not PYVMOMI_AVAILABLE:
                raise Fatal(2, "pyvmomi not installed. Install: pip install pyvmomi")
            vs_action = getattr(self.args, "vs_action", "")
            if not REQUESTS_AVAILABLE and (vs_action in ("download_datastore_file", "download_vm_disk", "cbt_sync")):
                raise Fatal(2, "requests not installed. Install: pip install requests")

            # Existing behavior: VsphereMode handles its own output and exits orchestration.
            # ADD (non-breaking): if user asked for vSphere export (sync), run it here and continue pipeline.
            if self._vsphere_v2v_enabled():
                U.banner(self.logger, "vSphere export (sync)")
                exported = self._vsphere_export_many_sync(out_root)
                if exported:
                    self.disks = exported
                    self.logger.info("📦 vSphere export produced %d disk(s)", len(self.disks))
                    return None
                self.logger.warning("vSphere export produced no disks; falling back to VsphereMode")
                VsphereMode(self.logger, self.args).run()
                return None

            VsphereMode(self.logger, self.args).run()
            return None

        if cmd == "local":
            self.disks = [Path(self.args.vmdk).expanduser().resolve()]
            Log.trace(self.logger, "📍 local disk: %s", self.disks[0])

        elif cmd == "fetch-and-fix":
            sshc = SSHClient(
                self.logger,
                SSHConfig(
                    host=self.args.host,
                    user=self.args.user,
                    port=self.args.port,
                    identity=getattr(self.args, "identity", None),
                    ssh_opt=self._normalize_ssh_opts(getattr(self.args, "ssh_opt", None)),
                    sudo=False,
                ),
            )
            fetch_dir = (
                Path(self.args.fetch_dir).expanduser().resolve()
                if getattr(self.args, "fetch_dir", None)
                else (out_root / "downloaded")
            )
            U.ensure_dir(fetch_dir)
            Log.step(self.logger, f"Fetching remote VMDK descriptor/extent → {fetch_dir}")
            desc = Fetch.fetch_descriptor_and_extent(
                self.logger,
                sshc,
                self.args.remote,
                fetch_dir,
                getattr(self.args, "fetch_all", False),
            )
            self.disks = [desc]
            Log.ok(self.logger, f"Fetched: {desc.name}")

        elif cmd == "ova":
            temp_dir = out_root / "extracted"
            U.ensure_dir(temp_dir)

            Log.step(self.logger, f"Extract OVA → {temp_dir}")
            self.disks = OVF.extract_ova(
                self.logger,
                Path(self.args.ova).expanduser().resolve(),
                temp_dir,
                convert_to_qcow2=bool(getattr(self.args, "to_qcow2", False)),
                convert_outdir=(
                    Path(self.args.qcow2_dir).expanduser().resolve()
                    if getattr(self.args, "qcow2_dir", None)
                    else (out_root / "qcow2")
                ),
                convert_compress=bool(getattr(self.args, "compress", False)),
                convert_compress_level=getattr(self.args, "compress_level", None),
                log_virt_filesystems=bool(getattr(self.args, "log_virt_filesystems", False)),
            )
            self.logger.info("📦 Extracted %d disk(s) from OVA", len(self.disks))

        elif cmd == "ovf":
            temp_dir = out_root / "extracted"
            Log.step(self.logger, f"Extract OVF → {temp_dir}")
            self.disks = OVF.extract_ovf(
                self.logger,
                Path(self.args.ovf).expanduser().resolve(),
                temp_dir,
            )
            self.logger.info("📦 Extracted %d disk(s) from OVF", len(self.disks))

        elif cmd == "vhd":
            temp_dir = out_root / "extracted"
            Log.step(self.logger, f"Extract VHD/TAR → {temp_dir}")
            self.disks = VHD.extract_vhd_or_tar(
                self.logger,
                Path(self.args.vhd).expanduser().resolve(),
                temp_dir,
                convert_to_qcow2=True,
                convert_outdir=out_root / "qcow2",
                convert_compress=bool(self.args.compress),
                convert_compress_level=self.args.compress_level,
                log_virt_filesystems=True,
            )
            self.logger.info("📦 Extracted %d disk(s) from VHD/TAR", len(self.disks))

        elif cmd == "ami":
            from vmdk2kvm.converters.ami_extractor import AMI  # new extractor

            temp_dir = out_root / "extracted"
            Log.step(self.logger, f"Extract AMI/TAR → {temp_dir}")

            self.disks = AMI.extract_ami_or_tar(
                self.logger,
                Path(self.args.ami).expanduser().resolve(),
                temp_dir,
                extract_nested_tar=bool(getattr(self.args, "extract_nested_tar", True)),
                convert_payload_to_qcow2=bool(getattr(self.args, "convert_payload_to_qcow2", False)),
                payload_qcow2_dir=(
                    Path(self.args.payload_qcow2_dir).expanduser().resolve()
                    if getattr(self.args, "payload_qcow2_dir", None)
                    else (out_root / "qcow2")
                ),
                payload_convert_compress=bool(getattr(self.args, "payload_convert_compress", False)),
                payload_convert_compress_level=getattr(self.args, "payload_convert_compress_level", None),
                log_virt_filesystems=True,
            )
            self.logger.info("📦 Extracted %d disk(s) from AMI/TAR", len(self.disks))

        elif cmd == "live-fix":
            sshc = SSHClient(
                self.logger,
                SSHConfig(
                    host=self.args.host,
                    user=self.args.user,
                    port=self.args.port,
                    identity=getattr(self.args, "identity", None),
                    ssh_opt=self._normalize_ssh_opts(getattr(self.args, "ssh_opt", None)),
                    sudo=getattr(self.args, "sudo", False),
                ),
            )
            Log.step(self.logger, "Live-fix over SSH")
            LiveFixer(
                self.logger,
                sshc,
                dry_run=getattr(self.args, "dry_run", False),
                no_backup=getattr(self.args, "no_backup", False),
                print_fstab=getattr(self.args, "print_fstab", False),
                update_grub=not getattr(self.args, "no_grub", False),
                regen_initramfs=getattr(self.args, "regen_initramfs", True),
                remove_vmware_tools=getattr(self.args, "remove_vmware_tools", False),
                luks_passphrase=getattr(self.args, "luks_passphrase", None),
                luks_passphrase_env=getattr(self.args, "luks_passphrase_env", None),
                luks_keyfile=getattr(self.args, "luks_keyfile", None),
            ).run()
            self.logger.info("✅ Live fix done.")
            return None

        else:
            U.die(self.logger, f"Unknown command: {cmd}", 1)

        Log.trace(self.logger, "📦 discovered disks=%d: %s", len(self.disks), [str(d) for d in self.disks])
        return temp_dir

    def run(self) -> None:
        out_root = Path(self.args.output_dir).expanduser().resolve()
        U.ensure_dir(out_root)

        self._setup_recovery(out_root)

        sanity = SanityChecker(self.logger, self.args)
        Log.step(self.logger, "Sanity checks")
        sanity.check_all()
        Log.ok(self.logger, "Sanity checks passed")

        U.banner(self.logger, f"Mode: {self.args.cmd}")

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

        temp_dir = self._discover_disks(out_root)
        if temp_dir is None and getattr(self.args, "cmd", None) in ("live-fix", "vsphere"):
            if getattr(self.args, "cmd", None) == "vsphere" and self.disks:
                # vSphere export produced disks and we continue pipeline
                Log.trace(self.logger, "🌐 vsphere cmd: continuing pipeline with exported disks=%d", len(self.disks))
            else:
                return

        if self.recovery_manager:
            self.recovery_manager.save_checkpoint(
                "disks_discovered",
                {"count": len(self.disks), "disks": [str(d) for d in self.disks]},
            )

        fixed_images: List[Path] = []

        # ---------------------------
        # virt-v2v PRE step (existing) + ADD: optional v2v parallel
        # ---------------------------
        if getattr(self.args, "use_v2v", False):
            use_parallel_v2v = bool(getattr(self.args, "v2v_parallel", False))
            Log.step(self.logger, f"virt-v2v pre-step ({'parallel' if use_parallel_v2v else 'single'})")
            if use_parallel_v2v and len(self.disks) > 1:
                v2v_images = Orchestrator.v2v_convert_parallel(
                    self.logger,
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
                v2v_images = Orchestrator.v2v_convert(
                    self.logger,
                    self.disks,
                    out_root,
                    getattr(self.args, "out_format", "qcow2"),
                    getattr(self.args, "compress", False),
                    getattr(self.args, "luks_passphrase", None),
                    getattr(self.args, "luks_passphrase_env", None),
                    getattr(self.args, "luks_keyfile", None),
                )

            fixed_images = v2v_images if v2v_images else self._internal_process(out_root)
        else:
            fixed_images = self._internal_process(out_root)

        out_images = fixed_images

        # ---------------------------
        # Post virt-v2v (existing) + ADD: optional post-v2v parallel
        # ---------------------------
        if getattr(self.args, "post_v2v", False) and out_images:
            v2v_dir = out_root / "post-v2v"
            U.ensure_dir(v2v_dir)

            use_parallel_v2v = bool(getattr(self.args, "v2v_parallel", False))
            Log.step(self.logger, f"virt-v2v post-step ({'parallel' if use_parallel_v2v else 'single'})")
            if use_parallel_v2v and len(fixed_images) > 1:
                v2v_images = Orchestrator.v2v_convert_parallel(
                    self.logger,
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
                v2v_images = Orchestrator.v2v_convert(
                    self.logger,
                    fixed_images,
                    v2v_dir,
                    getattr(self.args, "out_format", "qcow2"),
                    getattr(self.args, "compress", False),
                    getattr(self.args, "luks_passphrase", None),
                    getattr(self.args, "luks_passphrase_env", None),
                    getattr(self.args, "luks_keyfile", None),
                )

            if v2v_images:
                out_images = v2v_images

        # Optional tests
        if out_images:
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

        if self.recovery_manager:
            self.recovery_manager.cleanup_old_checkpoints()

        if temp_dir and temp_dir.exists():
            Log.trace(self.logger, "🧹 cleaning temp_dir=%s", temp_dir)
            shutil.rmtree(temp_dir, ignore_errors=True)

        U.banner(self.logger, "Done")
        self.logger.info(f"📦 Output directory: {out_root}")
        if out_images:
            self.logger.info("🎉 Generated images:")
            for img in out_images:
                self.logger.info(f" - {img}")

        # ✅ Hook point: after out_images computed (and after tests)
        if out_images:
            try:
                emit_from_args(self.logger, self.args, out_root=out_root, out_images=out_images)
            except Exception as e:
                self.logger.warning("Failed to emit libvirt domain XML: %s", e)
                self.logger.debug("💥 emit_from_args exception", exc_info=True)


    def _internal_process(self, out_root: Path) -> List[Path]:
        fixed_images: List[Path] = []

        Log.trace(self.logger, "🧠 _internal_process: disks=%d parallel=%s", len(self.disks), getattr(self.args, "parallel_processing", False))

        if len(self.disks) > 1 and getattr(self.args, "parallel_processing", False):
            return self.process_disks_parallel(self.disks, out_root)

        for idx, disk in enumerate(self.disks):
            if not disk.exists():
                U.die(self.logger, f"🔥 Disk not found: {disk}", 1)
            fixed_images.append(self.process_single_disk(disk, out_root, idx))

        Log.trace(self.logger, "📦 _internal_process: produced=%d", len(fixed_images))
        return fixed_images
