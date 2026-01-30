# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/orchestrator/disk_discovery.py
"""
Disk discovery from various sources.
Handles input disk detection for different conversion modes.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..converters.extractors.libvirt_xml import LibvirtXML
from ..converters.extractors.ovf import OVF
from ..converters.extractors.raw import RAW
from ..converters.extractors.vhd import VHD
from ..converters.fetch import Fetch
from ..core.exceptions import Fatal
from ..core.logger import Log
from ..core.utils import U
from ..fixers.live.fixer import LiveFixer
from ..ssh.ssh_client import SSHClient
from ..ssh.ssh_config import SSHConfig


class DiskDiscovery:
    """
    Discovers and prepares disks from various input sources.

    Responsibilities:
    - Detect input mode from args
    - Handle local VMDK, OVA, OVF, VHD, AMI, RAW inputs
    - Handle remote fetch-and-fix mode
    - Handle live-fix mode (no disks returned)
    - Manage temporary extraction directories
    """

    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        self.logger = logger
        self.args = args

    @staticmethod
    def _normalize_ssh_opts(v) -> list[str] | None:
        """Normalize SSH options from various input formats."""
        if v is None:
            return None
        if isinstance(v, (list, tuple)):
            out = [str(x) for x in v if x is not None]
            return out or None
        return [str(v)]

    def discover(self, out_root: Path) -> tuple[list[Path], Path | None]:
        """
        Discover disks based on args.cmd.

        Args:
            out_root: Output directory root

        Returns:
            Tuple of (disk_list, temp_dir_to_cleanup)
            temp_dir is None if no cleanup needed or if mode exits early (live-fix, vsphere)
        """
        temp_dir: Path | None = None
        disks: list[Path] = []
        cmd = getattr(self.args, "cmd", None)

        Log.trace(self.logger, "🧭 discover_disks: cmd=%r out_root=%s", cmd, out_root)

        if cmd == "local":
            disks = [Path(self.args.vmdk).expanduser().resolve()]
            Log.trace(self.logger, "📍 local disk: %s", disks[0])

        elif cmd == "fetch-and-fix":
            sshc = SSHClient(
                self.logger,
                SSHConfig(
                    host=self.args.host,
                    user=self.args.user,
                    port=self.args.port,
                    identity=getattr(self.args, "identity", None),
                    ssh_opts=self._normalize_ssh_opts(getattr(self.args, "ssh_opt", None)),
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
            disks = [desc]
            Log.ok(self.logger, f"Fetched: {desc.name}")

        elif cmd == "ova":
            temp_dir = out_root / "extracted"
            U.ensure_dir(temp_dir)

            Log.step(self.logger, f"Extract OVA → {temp_dir}")
            disks = OVF.extract_ova(
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
            self.logger.info("📦 Extracted %d disk(s) from OVA", len(disks))

        elif cmd == "ovf":
            temp_dir = out_root / "extracted"
            Log.step(self.logger, f"Extract OVF → {temp_dir}")
            disks = OVF.extract_ovf(
                self.logger,
                Path(self.args.ovf).expanduser().resolve(),
                temp_dir,
            )
            self.logger.info("📦 Extracted %d disk(s) from OVF", len(disks))

        elif cmd == "vhd":
            temp_dir = out_root / "extracted"
            Log.step(self.logger, f"Extract VHD/TAR → {temp_dir}")
            disks = VHD.extract_vhd_or_tar(
                self.logger,
                Path(self.args.vhd).expanduser().resolve(),
                temp_dir,
                convert_to_qcow2=True,
                convert_outdir=out_root / "qcow2",
                convert_compress=bool(self.args.compress),
                convert_compress_level=self.args.compress_level,
                log_virt_filesystems=True,
            )
            self.logger.info("📦 Extracted %d disk(s) from VHD/TAR", len(disks))

        elif cmd == "raw":
            temp_dir = out_root / "extracted"
            Log.step(self.logger, f"Extract RAW/IMG/TAR → {temp_dir}")

            # accept multiple arg names (configs vary)
            raw_src = (
                getattr(self.args, "raw", None)
                or getattr(self.args, "img", None)
                or getattr(self.args, "raw_src", None)
                or getattr(self.args, "raw_path", None)
            )
            if not raw_src:
                raise Fatal(2, "raw mode requires --raw <path> (or config: raw/img/raw_src/raw_path)")

            disks = RAW.extract_raw_or_tar(
                self.logger,
                Path(raw_src).expanduser().resolve(),
                temp_dir,
                convert_to_qcow2=bool(getattr(self.args, "to_qcow2", False) or getattr(self.args, "convert_to_qcow2", False)),
                convert_outdir=(
                    Path(getattr(self.args, "qcow2_dir", None)).expanduser().resolve()
                    if getattr(self.args, "qcow2_dir", None)
                    else (out_root / "qcow2")
                ),
                convert_compress=bool(getattr(self.args, "compress", False)),
                convert_compress_level=getattr(self.args, "compress_level", None),
                log_virt_filesystems=bool(getattr(self.args, "log_virt_filesystems", False)),
                max_members=getattr(self.args, "max_members", None),
                max_total_bytes=getattr(self.args, "max_total_bytes", None),
                max_manifest_bytes=int(getattr(self.args, "max_manifest_bytes", 5 * 1024 * 1024) or (5 * 1024 * 1024)),
                skip_special=bool(getattr(self.args, "skip_special", True)),
                preserve_permissions=bool(getattr(self.args, "preserve_permissions", True)),
                extract_all=bool(getattr(self.args, "extract_all", False)),
                include_manifests=bool(getattr(self.args, "include_manifests", True)),
                overwrite=bool(getattr(self.args, "overwrite", False)),
                rename_on_collision=bool(getattr(self.args, "rename_on_collision", False)),
                preserve_timestamps=bool(getattr(self.args, "preserve_timestamps", False)),
            )
            self.logger.info("📦 Extracted %d disk(s) from RAW/IMG/TAR", len(disks))

        elif cmd == "ami":
            from ..converters.extractors.ami import AMI

            temp_dir = out_root / "extracted"
            Log.step(self.logger, f"Extract AMI/TAR → {temp_dir}")

            disks = AMI.extract_ami_or_tar(
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
            self.logger.info("📦 Extracted %d disk(s) from AMI/TAR", len(disks))

        elif cmd == "live-fix":
            sshc = SSHClient(
                self.logger,
                SSHConfig(
                    host=self.args.host,
                    user=self.args.user,
                    port=self.args.port,
                    identity=getattr(self.args, "identity", None),
                    ssh_opts=self._normalize_ssh_opts(getattr(self.args, "ssh_opt", None)),
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
            # Return empty - live-fix doesn't produce disks
            return [], None

        elif cmd == "libvirt-xml":
            # Libvirt domain XML parsing - generates Artifact Manifest v1
            Log.step(self.logger, "Parse Libvirt Domain XML → Generate Manifest")

            xml_path = getattr(self.args, "libvirt_xml", None) or getattr(self.args, "xml_path", None)
            if not xml_path:
                raise Fatal(2, "libvirt-xml mode requires --libvirt-xml <path> or --xml-path <path>")

            manifest = LibvirtXML.parse_domain_xml(
                self.logger,
                Path(xml_path).expanduser().resolve(),
                output_dir=out_root,
                compute_checksums=bool(getattr(self.args, "compute_checksums", True)),
                manifest_filename=getattr(self.args, "manifest_filename", "manifest.json"),
            )

            self.logger.info("=" * 80)
            self.logger.info("✅ Artifact Manifest v1 generated successfully")
            self.logger.info("=" * 80)
            self.logger.info(f"📄 Manifest: {out_root / getattr(self.args, 'manifest_filename', 'manifest.json')}")
            self.logger.info("")
            self.logger.info("Next steps:")
            self.logger.info(f"  sudo hyper2kvm --config {out_root / getattr(self.args, 'manifest_filename', 'manifest.json')}")
            self.logger.info("")

            # Return empty - libvirt-xml just generates manifest, doesn't do conversion
            return [], None

        elif cmd == "daemon":
            # Daemon mode is handled by orchestrator, not DiskDiscovery
            # Return empty - daemon mode doesn't use the normal disk discovery flow
            return [], None

        else:
            U.die(self.logger, f"Unknown command: {cmd}", 1)

        Log.trace(self.logger, "📦 discovered disks=%d: %s", len(disks), [str(d) for d in disks])
        return disks, temp_dir
