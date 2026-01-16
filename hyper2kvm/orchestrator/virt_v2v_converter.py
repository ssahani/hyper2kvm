# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# hyper2kvm/orchestrator/virt_v2v_converter.py
"""
virt-v2v conversion wrapper with parallel support.
Handles conversion operations using virt-v2v tool.
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from ..core.exceptions import Fatal
from ..core.logger import Log
from ..core.utils import U


class VirtV2VConverter:
    """
    Handles virt-v2v conversion operations.

    Responsibilities:
    - Single and parallel virt-v2v conversions
    - LUKS key handling via passphrase env or keyfile
    - Robust output discovery across multiple formats
    - Temp keyfile cleanup safety
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def convert(
        self,
        disks: List[Path],
        out_root: Path,
        out_format: str,
        compress: bool,
        passphrase: Optional[str] = None,
        passphrase_env: Optional[str] = None,
        keyfile: Optional[str] = None,
    ) -> List[Path]:
        """
        Single virt-v2v conversion wrapper.

        Args:
            disks: List of disk paths to convert
            out_root: Output directory
            out_format: Output format (qcow2, raw, etc.)
            compress: Enable compression
            passphrase: LUKS passphrase (optional)
            passphrase_env: Environment variable name for passphrase
            keyfile: Path to LUKS keyfile

        Returns:
            List of output image paths
        """
        Log.trace(
            self.logger,
            "🧪 v2v_convert: disks=%d out_root=%s out_format=%s compress=%s",
            len(disks),
            out_root,
            out_format,
            compress,
        )

        if U.which("virt-v2v") is None:
            self.logger.warning("virt-v2v not found; falling back to internal fixer")
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
                    self.logger,
                    "🔐 v2v_convert: passphrase_env=%r present=%s",
                    passphrase_env,
                    bool(effective_passphrase),
                )

            if keyfile:
                keyfile_path_temp = Path(keyfile).expanduser().resolve()
                if not keyfile_path_temp.exists():
                    self.logger.warning(f"LUKS keyfile not found: {keyfile_path_temp}")
                else:
                    keyfile_path = str(keyfile_path_temp)
                    Log.trace(self.logger, "🔑 v2v_convert: using keyfile=%s", keyfile_path)
            elif effective_passphrase:
                # virt-v2v expects a file reference for LUKS keys. Ensure newline.
                with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as keyfile_tmp:
                    keyfile_tmp.write(effective_passphrase + "\n")
                    keyfile_path = keyfile_tmp.name
                    is_temp_keyfile = True
                Log.trace(self.logger, "🧾 v2v_convert: wrote temp keyfile=%s", keyfile_path)

            if keyfile_path:
                cmd += ["--key", f"ALL:file:{keyfile_path}"]

            U.banner(self.logger, "Using virt-v2v for conversion")
            Log.trace(self.logger, "🧷 v2v_convert: cmd=%r", cmd)
            U.run_cmd(self.logger, cmd, check=True, capture=False)

        finally:
            if keyfile_path and is_temp_keyfile:
                try:
                    os.unlink(keyfile_path)
                    Log.trace(self.logger, "🧹 v2v_convert: removed temp keyfile=%s", keyfile_path)
                except Exception:
                    Log.trace(
                        self.logger,
                        "⚠️ v2v_convert: failed to remove temp keyfile=%s",
                        keyfile_path,
                        exc_info=True,
                    )

        # virt-v2v output files can vary; capture common ones robustly.
        patterns = ["*.qcow2", "*.raw", "*.img", "*.vmdk", "*.vdi"]
        out_images: List[Path] = []
        for pat in patterns:
            found = sorted(out_root.glob(pat))
            Log.trace(self.logger, "🔎 v2v_convert: glob=%s -> %d", pat, len(found))
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
            self.logger.warning("virt-v2v completed but produced no recognizable disk outputs in out_root")
        else:
            self.logger.info(f"virt-v2v conversion completed: produced {len(uniq)} image(s).")
            Log.trace(self.logger, "📦 v2v_convert: outputs=%s", [str(x) for x in uniq])
        return uniq

    def convert_parallel(
        self,
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
        Run multiple virt-v2v processes in parallel (bounded).

        Args:
            disks: List of disk paths to convert
            out_root: Output directory
            out_format: Output format
            compress: Enable compression
            passphrase: LUKS passphrase
            passphrase_env: Environment variable for passphrase
            keyfile: LUKS keyfile path
            concurrency: Maximum concurrent jobs

        Returns:
            List of output image paths (flattened from all jobs)
        """
        Log.trace(
            self.logger,
            "🧵 v2v_convert_parallel: disks=%d out_root=%s concurrency=%s",
            len(disks),
            out_root,
            concurrency,
        )

        if not disks:
            return []

        if len(disks) == 1:
            return self.convert(
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
            self.logger.info("➡️ virt-v2v job %d/%d: %s", idx + 1, len(disks), disk.name)
            Log.trace(self.logger, "📁 v2v job_dir=%s", job_dir)
            return self.convert(
                [disk],
                job_dir,
                out_format,
                compress,
                passphrase,
                passphrase_env,
                keyfile,
            )

        self.logger.info(f"virt-v2v parallel: {len(disks)} job(s), concurrency={concurrency}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = {ex.submit(_one, i, d): i for i, d in enumerate(disks)}
            for fut in concurrent.futures.as_completed(futs):
                i = futs[fut]
                try:
                    results[i] = fut.result()
                    Log.trace(self.logger, "✅ v2v job done: idx=%d outputs=%d", i, len(results[i] or []))
                except Exception as e:
                    self.logger.error(f"virt-v2v job failed for disk {i} ({disks[i].name}): {e}")
                    Log.trace(self.logger, "💥 v2v job exception: idx=%d disk=%s", i, disks[i], exc_info=True)
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

        Log.trace(self.logger, "📦 v2v_convert_parallel: uniq_outputs=%d", len(uniq))
        return uniq
