# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import argparse
import logging
import os
import shutil
import socket
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from .utils import U


@dataclass
class SanityReport:
    missing_required: List[str] = field(default_factory=list)
    missing_optional: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: Dict[str, str] = field(default_factory=dict)

    def ok(self) -> bool:
        return not self.missing_required


class SanityChecker:
    """
    Sanity checks for vmdk2kvm:
      - tool availability (required vs optional, conditional)
      - libguestfs import + minimal init
      - disk space estimate
      - permissions on output dir
      - optional network connectivity (for download/fetch workflows)
    """

    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        self.logger = logger
        self.args = args
        self.out_root = Path(getattr(args, "output_dir", ".")).expanduser().resolve()
        self.report = SanityReport()

    # -------- helpers --------

    def _need(self, flag: str) -> bool:
        """Return True if args has flag and it evaluates truthy."""
        return bool(getattr(self.args, flag, False))

    def _add_warn(self, msg: str) -> None:
        self.report.warnings.append(msg)
        self.logger.warning(msg)

    def _tool_missing(self, tool: str) -> bool:
        return U.which(tool) is None

    def _bytes(self, n: int) -> str:
        # tiny humanizer without extra deps
        units = ["B", "KiB", "MiB", "GiB", "TiB"]
        x = float(n)
        for u in units:
            if x < 1024 or u == units[-1]:
                return f"{x:.2f} {u}" if u != "B" else f"{int(x)} {u}"
            x /= 1024
        return f"{x:.2f} B"

    # -------- checks --------

    def check_tools(self) -> None:
        # Always required
        required_tools = ["qemu-img"]

        # Optional baseline
        optional_tools = ["rsync", "sgdisk"]

        # Conditional optional/required depending on features
        # (Change these flags to match your CLI)
        if self._need("libvirt_test") or self._need("keep_domain"):
            optional_tools.append("virsh")

        if self._need("qemu_test") or self._need("uefi"):
            optional_tools.append("qemu-system-x86_64")

        # If you have a mode like fetch-from-esxi: rsync/scp might be needed
        # Keep optional, but we can warn more loudly
        if getattr(self.args, "mode", "") in ("fetch", "fetch-and-fix", "remote"):
            optional_tools.extend(["ssh", "scp"])

        missing_required = [t for t in required_tools if self._tool_missing(t)]
        missing_optional = sorted({t for t in optional_tools if self._tool_missing(t)})

        self.report.missing_required.extend(missing_required)
        self.report.missing_optional.extend(missing_optional)

        if missing_required:
            U.die(self.logger, f"Missing required tools: {', '.join(missing_required)}", 1)

        if missing_optional:
            self._add_warn(f"Missing optional tools: {', '.join(missing_optional)}")

        # libguestfs check (you rely on it for offline edits)
        try:
            import guestfs  # type: ignore

            g = guestfs.GuestFS(python_return_dict=True)
            # minimal handshake; doesn't require attaching disks
            g.set_trace(0)
            g.set_verbose(0)
            g.close()
            self.report.notes["libguestfs"] = "OK"
        except Exception as e:
            # If you have modes that do not need guestfs, you can relax this.
            U.die(self.logger, f"libguestfs test failed: {e}", 1)

        self.logger.info("Tools sanity check passed.")

    def check_disk_space(self) -> None:
        if getattr(self.args, "dry_run", False):
            self.logger.info("DRY-RUN: skipping disk space check")
            return

        try:
            usage = shutil.disk_usage(self.out_root)
            free_bytes = usage.free

            input_bytes = 0
            disks = getattr(self.args, "disks", None)

            # Some modes pass --vmdk instead of --disks; cover both.
            if disks:
                input_bytes = sum(Path(d).stat().st_size for d in disks)
            else:
                vmdk = getattr(self.args, "vmdk", None)
                if vmdk:
                    input_bytes = Path(vmdk).stat().st_size

            # Estimate:
            # - output image ~= input size (raw) or somewhat less/more depending on format
            # - temp working copy + scratch (snapshot flattening / conversion) can add overhead
            # - compression: may reduce final size but temp space still needed
            factor_out = 1.0
            factor_tmp = 1.0

            # If converting to qcow2, temp + output can be > input
            to_qcow2 = bool(getattr(self.args, "to_qcow2", None))
            if to_qcow2:
                factor_out = 1.1
                factor_tmp = 1.2

            # If flattening snapshot chains or doing heavy fixups, bump temp need
            if self._need("flatten") or self._need("workdir"):
                factor_tmp += 0.5

            # If you keep original + create backups, add overhead
            if self._need("backup") or self._need("keep_work"):
                factor_tmp += 0.3

            # Baseline: output + temp + some slack
            estimated_needed = int(input_bytes * (factor_out + factor_tmp) + (1 * 1024**3))  # +1GiB slack

            self.report.notes["disk_free"] = self._bytes(free_bytes)
            self.report.notes["disk_input"] = self._bytes(input_bytes)
            self.report.notes["disk_need_est"] = self._bytes(estimated_needed)

            if free_bytes < estimated_needed:
                U.die(
                    self.logger,
                    f"Insufficient disk space: {self._bytes(free_bytes)} free, "
                    f"estimated needed {self._bytes(estimated_needed)} "
                    f"(input={self._bytes(input_bytes)})",
                    1,
                )

            self.logger.info(
                "Disk space OK: %s free (estimated needed %s, input %s)",
                self._bytes(free_bytes),
                self._bytes(estimated_needed),
                self._bytes(input_bytes),
            )
        except Exception as e:
            self._add_warn(f"Disk space check failed (non-fatal): {e}")

    def check_permissions(self) -> None:
        try:
            self.out_root.mkdir(parents=True, exist_ok=True)
            # atomic create + write + fsync to catch weird perms / RO mounts
            fd, tmp = tempfile.mkstemp(prefix=".permtest_", dir=str(self.out_root))
            try:
                os.write(fd, b"ok\n")
                os.fsync(fd)
            finally:
                os.close(fd)
            Path(tmp).unlink(missing_ok=True)
            self.logger.debug("Permissions OK (%s)", self.out_root)
        except Exception as e:
            U.die(self.logger, f"Permission check failed for {self.out_root}: {e}", 1)

    def check_network(self) -> None:
        # Only meaningful for modes that fetch/download.
        needs_net = getattr(self.args, "mode", "") in ("fetch", "fetch-and-fix", "remote") or self._need("download")
        if not needs_net:
            self.logger.debug("Network check skipped (not needed for this mode)")
            return

        host = getattr(self.args, "net_check_host", None) or "1.1.1.1"
        port = int(getattr(self.args, "net_check_port", None) or 53)
        timeout = float(getattr(self.args, "net_check_timeout", None) or 2.0)

        try:
            with socket.create_connection((host, port), timeout=timeout):
                pass
            self.logger.debug("Network OK (tcp connect to %s:%s)", host, port)
            self.report.notes["network"] = f"OK ({host}:{port})"
        except Exception as e:
            self._add_warn(f"Network check failed (tcp {host}:{port}): {e}")

    def check_all(self) -> SanityReport:
        checks = [
            ("tools", self.check_tools),
            ("disk space", self.check_disk_space),
            ("permissions", self.check_permissions),
            ("network", self.check_network),
        ]

        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Running sanity checks", total=len(checks))
            for name, fn in checks:
                progress.update(task, description=f"Running sanity checks: {name}")
                fn()
                progress.update(task, advance=1)

        if self.report.missing_optional:
            self.logger.warning("Sanity checks passed with optional missing tools.")
        self.logger.info("All sanity checks passed.")
        return self.report
