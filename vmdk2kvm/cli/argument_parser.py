from __future__ import annotations

import argparse
from typing import Any, Dict, Optional, Tuple

from ..core.logger import c
from ..config.config_loader import Config
from .. import __version__
from ..config.systemd_template import SYSTEMD_UNIT_TEMPLATE
from ..fixers.fstab_rewriter import FstabMode

YAML_EXAMPLE = r"""# vmdk2kvm config (offline/local mode)
# Run:
# sudo ./vmdk2kvm.py --config config.yaml local
# or merge configs:
# sudo ./vmdk2kvm.py --config base.yaml --config overrides.yaml local
#
# For multiple VMs:
# vms:
# - vmdk: vm1.vmdk
#   to_output: vm1.qcow2
# - vmdk: vm2.vmdk
#   to_output: vm2.qcow2
#
# What it will do:
# - Open the VMDK offline with libguestfs
# - Mount root safely (never using /dev/disk/by-path for mounting)
# - Rewrite /etc/fstab to stable identifiers (UUID preferred; fallback PARTUUID then LABEL/PARTLABEL)
# - Canonicalize btrfs subvolume entries (removes btrfsvol: pseudo-specs)
# - Ensure /tmp exists (fixes virt-v2v random seed stage)
# - Optionally flatten snapshot chain first (recommended if snapshots exist)
# - Optionally convert to qcow2/raw/vdi output
command: local
vmdk: /home/ssahani/by-path/openSUSE_Leap_15.4_VM_LinuxVMImages.COM.vmdk
output_dir: /home/ssahani/by-path/out
dry_run: false
print_fstab: true
flatten: true
flatten_format: qcow2
workdir: /home/ssahani/by-path/out/work # Optional work directory
to_output: opensuse-leap-15.4-fixed.qcow2
out_format: qcow2
compress: true
compress_level: 6 # Optional: 1-9 compression level
checksum: true
fstab_mode: stabilize-all # stabilize-all | bypath-only | noop
no_backup: false
grub: true
regen_initramfs: true
remove_vmware_tools: true
enable_recovery: true
parallel_processing: true
resize: +10G
post_v2v: true
cloud_init_config: /path/to/cloud-init.yaml
verbose: 2
# Optional tests:
# libvirt_test: true
# vm_name: vmdk2kvm-opensuse154
# memory: 2048
# vcpus: 2
# uefi: true
# timeout: 60
# keep_domain: false
# headless: true
"""


class CLI:
    @staticmethod
    def build_parser() -> argparse.ArgumentParser:
        epilog = (
            c("YAML example:\n", "cyan", ["bold"])
            + c(YAML_EXAMPLE, "cyan")
            + "\n"
            + c("Feature summary:\n", "cyan", ["bold"])
            + c(" • Inputs: local VMDK, remote ESXi fetch, OVA/OVF extract, live SSH fix\n", "cyan")
            + c(" • Snapshot: flatten convert, recursive parent descriptor fetch\n", "cyan")
            + c(
                " • Fixes: fstab UUID/PARTUUID/LABEL, btrfs canonicalization, grub root=, crypttab, mdraid checks\n",
                "cyan",
            )
            + c(" • Windows: BCD store fixes\n", "cyan")
            + c(" • Network: Configuration updates for KVM\n", "cyan")
            + c(" • VMware: Tools removal\n", "cyan")
            + c(" • Cloud: Cloud-init integration\n", "cyan")
            + c(" • Outputs: qcow2/raw/vdi, compression with levels, validation, checksum\n", "cyan")
            + c(" • Tests: libvirt and qemu smoke tests, BIOS/UEFI modes\n", "cyan")
            + c(" • Safety: dry-run, backups, report generation, verbose logs, recovery checkpoints\n", "cyan")
            + c(" • Performance: Parallel disk processing\n", "cyan")
            + c("\nSystemd Service Example:\n", "cyan", ["bold"])
            + c(SYSTEMD_UNIT_TEMPLATE, "cyan")
        )

        p = argparse.ArgumentParser(
            description=c("vmdk2kvm: Ultimate VMware → KVM/QEMU Converter + Fixer", "green", ["bold"]),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=epilog,
        )

        # Global config/logging (two-phase parse relies on these)
        p.add_argument(
            "--config",
            action="append",
            default=[],
            help="YAML/JSON config file (repeatable; later overrides earlier).",
        )
        p.add_argument("--dump-config", action="store_true", help="Print merged normalized config and exit.")
        p.add_argument("--dump-args", action="store_true", help="Print final parsed args and exit.")
        p.add_argument("--version", action="version", version=__version__)
        p.add_argument("-v", "--verbose", action="count", default=0, help="Verbosity: -v, -vv")
        p.add_argument("--log-file", dest="log_file", default=None, help="Write logs to file.")

        # Global operation flags
        p.add_argument("--output-dir", dest="output_dir", default="./out", help="Output directory root.")
        p.add_argument("--dry-run", dest="dry_run", action="store_true", help="Do not modify guest/convert output.")
        p.add_argument("--no-backup", dest="no_backup", action="store_true", help="Skip backups inside guest (dangerous).")
        p.add_argument("--print-fstab", dest="print_fstab", action="store_true", help="Print /etc/fstab before+after.")
        p.add_argument("--workdir", default=None, help="Working directory for intermediate files (default: <output-dir>/work).")

        # Flatten/convert
        p.add_argument("--flatten", action="store_true", help="Flatten snapshot chain into a single working image first.")
        p.add_argument("--flatten-format", dest="flatten_format", default="qcow2", choices=["qcow2", "raw"], help="Flatten output format.")
        p.add_argument("--to-output", dest="to_output", default=None, help="Convert final working image to this path (relative to output-dir if not absolute).")
        p.add_argument("--out-format", dest="out_format", default="qcow2", choices=["qcow2", "raw", "vdi"], help="Output format.")
        p.add_argument("--compress", action="store_true", help="Compression (qcow2 only).")
        p.add_argument("--compress-level", dest="compress_level", type=int, choices=range(1, 10), default=None, help="Compression level 1-9.")
        p.add_argument("--checksum", action="store_true", help="Compute SHA256 checksum of output.")

        # Fixing behavior
        p.add_argument(
            "--fstab-mode",
            dest="fstab_mode",
            default=FstabMode.STABILIZE_ALL.value,
            choices=[m.value for m in FstabMode],
            help="fstab rewrite mode: stabilize-all (recommended), bypath-only, noop",
        )
        p.add_argument("--no-grub", dest="no_grub", action="store_true", help="Skip GRUB root= update and device.map cleanup.")
        p.add_argument("--regen-initramfs", dest="regen_initramfs", action="store_true", help="Regenerate initramfs + grub config (best-effort).")
        p.add_argument("--no-regen-initramfs", dest="regen_initramfs", action="store_false", help="Disable initramfs/grub regen.")
        p.set_defaults(regen_initramfs=True)
        p.add_argument("--remove-vmware-tools", dest="remove_vmware_tools", action="store_true", help="Remove VMware tools from guest (Linux only).")
        p.add_argument("--cloud-init-config", dest="cloud_init_config", default=None, help="Cloud-init config (YAML/JSON) to inject.")
        p.add_argument("--enable-recovery", dest="enable_recovery", action="store_true", help="Enable checkpoint recovery for long operations.")
        p.add_argument("--parallel-processing", dest="parallel_processing", action="store_true", help="Process multiple disks in parallel.")
        p.add_argument("--resize", default=None, help="Resize root filesystem (enlarge only, e.g., +10G or 50G)")
        p.add_argument("--report", default=None, help="Write Markdown report (relative to output-dir if not absolute).")
        p.add_argument("--virtio-drivers-dir", dest="virtio_drivers_dir", default=None, help="Path to virtio-win drivers directory for Windows injection.")
        p.add_argument("--post-v2v", dest="post_v2v", action="store_true", help="Run virt-v2v after internal fixes.")
        p.add_argument("--use-v2v", dest="use_v2v", action="store_true", help="Use virt-v2v for conversion if available.")

        # Tests
        p.add_argument("--libvirt-test", dest="libvirt_test", action="store_true", help="Libvirt smoke test after conversion.")
        p.add_argument("--qemu-test", dest="qemu_test", action="store_true", help="QEMU smoke test after conversion.")
        p.add_argument("--vm-name", dest="vm_name", default="converted-vm", help="VM name for libvirt test.")
        p.add_argument("--memory", type=int, default=2048, help="Memory MiB for tests.")
        p.add_argument("--vcpus", type=int, default=2, help="vCPUs for tests.")
        p.add_argument("--uefi", action="store_true", help="Use UEFI for tests (default BIOS if unset).")
        p.add_argument("--timeout", type=int, default=60, help="Timeout seconds for libvirt state check.")
        p.add_argument("--keep-domain", dest="keep_domain", action="store_true", help="Keep libvirt domain after test.")
        p.add_argument("--headless", action="store_true", help="Headless libvirt domain (no graphics).")

        # Daemon flags (global)
        p.add_argument("--daemon", action="store_true", help="Run in daemon mode (for systemd service).")
        p.add_argument("--watch-dir", dest="watch_dir", default=None, help="Directory to watch for new VMDK files in daemon mode.")

        # Subcommands
        sub = p.add_subparsers(dest="cmd", required=True)

        pl = sub.add_parser("local", help="Offline: local VMDK")
        pl.add_argument("--vmdk", required=True, help="Local VMDK path (descriptor OR monolithic/binary VMDK)")

        pf = sub.add_parser("fetch-and-fix", help="Fetch from remote ESXi over SSH/SCP and fix offline")
        pf.add_argument("--host", required=True)
        pf.add_argument("--user", default="root")
        pf.add_argument("--port", type=int, default=22)
        pf.add_argument("--identity", default=None)
        pf.add_argument("--ssh-opt", action="append", default=None, help="Extra ssh/scp options (repeatable).")
        pf.add_argument("--remote", required=True, help="Remote path to VMDK descriptor")
        pf.add_argument("--fetch-dir", dest="fetch_dir", default=None, help="Where to store fetched files (default: <output-dir>/downloaded)")
        pf.add_argument("--fetch-all", dest="fetch_all", action="store_true", help="Fetch full snapshot descriptor chain recursively.")

        po = sub.add_parser("ova", help="Offline: extract from OVA")
        po.add_argument("--ova", required=True)

        povf = sub.add_parser("ovf", help="Offline: parse OVF (disks in same dir)")
        povf.add_argument("--ovf", required=True)

        plive = sub.add_parser("live-fix", help="LIVE: fix running VM over SSH")
        plive.add_argument("--host", required=True)
        plive.add_argument("--user", default="root")
        plive.add_argument("--port", type=int, default=22)
        plive.add_argument("--identity", default=None)
        plive.add_argument("--ssh-opt", action="append", default=None)
        plive.add_argument("--sudo", action="store_true", help="Run remote commands through sudo -n")

        sub.add_parser("daemon", help="Daemon mode to watch directory")

        pgen = sub.add_parser("generate-systemd", help="Generate systemd unit file")
        pgen.add_argument("--output", default=None, help="Write to file instead of stdout")

        # vSphere / vCenter (pyvmomi) mode
        pvs = sub.add_parser("vsphere", help="vSphere/vCenter: scan VMs, download VMDK, CBT delta sync")
        pvs.add_argument("--vcenter", required=True, help="vCenter/ESXi hostname or IP")
        pvs.add_argument("--vc-user", dest="vc_user", required=True, help="vCenter username")
        pvs.add_argument("--vc-password", dest="vc_password", default=None, help="vCenter password (or use --vc-password-env)")
        pvs.add_argument("--vc-password-env", dest="vc_password_env", default=None, help="Env var containing vCenter password")
        pvs.add_argument("--vc-port", dest="vc_port", type=int, default=443, help="vCenter HTTPS port (default: 443)")
        pvs.add_argument("--vc-insecure", dest="vc_insecure", action="store_true", help="Disable TLS verification")
        pvs.add_argument("--dc-name", dest="dc_name", default="ha-datacenter", help="Datacenter name for /folder URL (default: ha-datacenter)")

        vs_sub = pvs.add_subparsers(dest="vs_action", required=True, help="vSphere actions")

        plist = vs_sub.add_parser("list_vm_names", help="List all VM names")
        plist.add_argument("--json", action="store_true", help="Output in JSON format")

        pget = vs_sub.add_parser("get_vm_by_name", help="Get VM by name")
        pget.add_argument("--name", required=True, help="VM name")
        pget.add_argument("--json", action="store_true", help="Output in JSON format")

        pvm_disks = vs_sub.add_parser("vm_disks", help="List disks for VM")
        pvm_disks.add_argument("--vm_name", required=True, help="VM name")
        pvm_disks.add_argument("--json", action="store_true", help="Output in JSON format")

        pselect = vs_sub.add_parser("select_disk", help="Select disk")
        pselect.add_argument("--vm_name", required=True, help="VM name")
        pselect.add_argument("--label_or_index", default=None, help="Disk label or index")
        pselect.add_argument("--json", action="store_true", help="Output in JSON format")

        pdownload = vs_sub.add_parser("download_datastore_file", help="Download datastore file")
        pdownload.add_argument("--datastore", required=True, help="Datastore name")
        pdownload.add_argument("--ds_path", required=True, help="Datastore path")
        pdownload.add_argument("--local_path", required=True, help="Local output path")
        pdownload.add_argument("--chunk_size", type=int, default=1024 * 1024, help="Download chunk size (bytes)")
        pdownload.add_argument("--json", action="store_true", help="Output in JSON format")

        pcreate = vs_sub.add_parser("create_snapshot", help="Create snapshot")
        pcreate.add_argument("--vm_name", required=True, help="VM name")
        pcreate.add_argument("--name", required=True, help="Snapshot name")
        pcreate.add_argument("--quiesce", action="store_true", default=True, help="Quiesce filesystem")
        pcreate.add_argument("--no_quiesce", action="store_false", dest="quiesce", help="Disable quiesce")
        pcreate.add_argument("--memory", action="store_true", default=False, help="Include memory")
        pcreate.add_argument("--description", default="Created by vmdk2kvm", help="Snapshot description")
        pcreate.add_argument("--json", action="store_true", help="Output in JSON format")

        penable = vs_sub.add_parser("enable_cbt", help="Enable CBT")
        penable.add_argument("--vm_name", required=True, help="VM name")
        penable.add_argument("--json", action="store_true", help="Output in JSON format")

        pquery = vs_sub.add_parser("query_changed_disk_areas", help="Query changed disk areas")
        pquery.add_argument("--vm_name", required=True, help="VM name")
        pquery.add_argument("--snapshot_name", required=True, help="Snapshot name")
        pquery.add_argument("--device_key", type=int, required=False, help="Device key")
        pquery.add_argument("--disk", default=None, help="Disk index or label (alternative to device_key)")
        pquery.add_argument("--start_offset", type=int, default=0, help="Start offset")
        pquery.add_argument("--change_id", default="*", help="Change ID")
        pquery.add_argument("--json", action="store_true", help="Output in JSON format")

        pdownload_vm = vs_sub.add_parser("download_vm_disk", help="Download VM disk")
        pdownload_vm.add_argument("--vm_name", required=True, help="VM name")
        pdownload_vm.add_argument("--disk", default=None, help="Disk index or label")
        pdownload_vm.add_argument("--local_path", required=True, help="Local output path")
        pdownload_vm.add_argument("--chunk_size", type=int, default=1024 * 1024, help="Download chunk size (bytes)")
        pdownload_vm.add_argument("--json", action="store_true", help="Output in JSON format")

        pcbt_sync = vs_sub.add_parser("cbt_sync", help="CBT delta sync")
        pcbt_sync.add_argument("--vm_name", required=True, help="VM name")
        pcbt_sync.add_argument("--disk", default=None, help="Disk index or label")
        pcbt_sync.add_argument("--local_path", required=True, help="Local output path")
        pcbt_sync.add_argument("--enable_cbt", action="store_true", help="Enable CBT")
        pcbt_sync.add_argument("--snapshot_name", default="vmdk2kvm-cbt", help="Snapshot name")
        pcbt_sync.add_argument("--json", action="store_true", help="Output in JSON format")

        return p


def parse_args_with_config(argv=None, logger=None):
    """
    Two-phase parse that preserves the monolith's behavior.

      Phase 0: parse ONLY global flags needed to find config/logging (no subcommand/required args)
      Phase 1: load+merge config files and apply as argparse defaults
      Phase 2: full parse_args with defaults applied (so required args can come from config)

    Returns: (args, merged_config_dict, logger)
    """
    parser = CLI.build_parser()

    # Phase 0: tiny pre-parser that *cannot* trip over subcommand required args.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", action="append", default=[])
    pre.add_argument("-v", "--verbose", action="count", default=0)
    pre.add_argument("--log-file", dest="log_file", default=None)
    pre.add_argument("--dump-config", action="store_true")
    pre.add_argument("--dump-args", action="store_true")
    args0, _rest = pre.parse_known_args(argv)

    # Setup a logger early if caller didn't provide one (used for config merge diagnostics).
    if logger is None:
        from ..core.logger import Log  # local import to avoid cycles
        logger = Log.setup(getattr(args0, "verbose", 0), getattr(args0, "log_file", None))

    conf: Dict[str, Any] = {}
    cfgs = getattr(args0, "config", None) or []
    if cfgs:
        cfgs = Config.expand_configs(logger, list(cfgs))
        conf = Config.load_many(logger, cfgs)

        # Apply config values as argparse defaults (so required args can come from config)
        Config.apply_as_defaults(logger, parser, conf)

    # Phase 2: full parse with defaults applied.
    args = parser.parse_args(argv)

    # Convenience: allow --dump-config / --dump-args to work even if config supplies required args.
    if getattr(args0, "dump_config", False):
        print(U.json_dump(conf))
        raise SystemExit(0)

    if getattr(args0, "dump_args", False):
        print(U.json_dump(vars(args)))
        raise SystemExit(0)

    return args, conf, logger
