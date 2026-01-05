# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Optional, Tuple

from ..core.utils import U
from ..ssh.ssh_client import SSHClient
from ..vmware.vmdk_parser import VMDK


class Fetch:
    @staticmethod
    async def fetch_descriptor_and_extent(
        logger: logging.Logger,
        sshc: SSHClient,
        remote_desc: str,
        outdir: Path,
        fetch_all: bool,
    ) -> Path:
        """
        Fetch a VMDK descriptor and its extent. If fetch_all=True, walk the parent chain
        and fetch each parent descriptor + its extent as well.
        Returns the *local* path to the top-level descriptor.
        """
        U.banner(logger, "Fetch VMDK from remote")
        U.ensure_dir(outdir)
        await asyncio.to_thread(sshc.check)

        # Normalize remote descriptor path as given (do NOT force abspath - SSH server decides)
        if not await asyncio.to_thread(sshc.exists, remote_desc):
            U.die(logger, f"Remote descriptor not found: {remote_desc}", 1)

        remote_base_dir = os.path.dirname(remote_desc)
        local_desc = outdir / os.path.basename(remote_desc)

        logger.info(f"Copying descriptor: {remote_desc} -> {local_desc}")
        await Fetch._scp_from_with_progress(
            sshc=sshc,
            remote=remote_desc,
            local=local_desc,
            logger=logger,
        )

        # Fetch extent for the top descriptor
        await Fetch._fetch_extent_for_descriptor(
            logger=logger,
            sshc=sshc,
            remote_dir=remote_base_dir,
            local_desc=local_desc,
            outdir=outdir,
        )

        if fetch_all:
            cur_local_desc = local_desc
            seen: set[str] = set()

            while True:
                try:
                    parent_rel = VMDK.parse_parent(logger, cur_local_desc)
                except Exception as e:
                    logger.error(f"Failed to parse parent from {cur_local_desc}: {e}")
                    break

                if not parent_rel:
                    break

                # Parent may include relative components; keep as-is for remote join,
                # and also track loops on the raw string.
                if parent_rel in seen:
                    logger.warning(f"Parent loop detected at {parent_rel}, stopping fetch")
                    break
                seen.add(parent_rel)

                remote_parent_desc = os.path.join(remote_base_dir, parent_rel)
                local_parent_desc = outdir / os.path.basename(parent_rel)

                if not await asyncio.to_thread(sshc.exists, remote_parent_desc):
                    logger.warning(f"Parent descriptor missing: {remote_parent_desc}")
                    break

                logger.info(f"Copying parent descriptor: {remote_parent_desc} -> {local_parent_desc}")
                await Fetch._scp_from_with_progress(
                    sshc=sshc,
                    remote=remote_parent_desc,
                    local=local_parent_desc,
                    logger=logger,
                )

                # Fetch each parent's extent too (critical for later flattening)
                await Fetch._fetch_extent_for_descriptor(
                    logger=logger,
                    sshc=sshc,
                    remote_dir=remote_base_dir,
                    local_desc=local_parent_desc,
                    outdir=outdir,
                )

                cur_local_desc = local_parent_desc

        return local_desc

    @staticmethod
    async def _fetch_extent_for_descriptor(
        logger: logging.Logger,
        sshc: SSHClient,
        remote_dir: str,
        local_desc: Path,
        outdir: Path,
    ) -> Optional[Path]:
        """
        Parse extent path from local descriptor and fetch it. Returns local extent path if found.
        """
        try:
            extent_rel = VMDK.parse_extent(logger, local_desc)
        except Exception as e:
            logger.error(f"Failed to parse extent from descriptor {local_desc}: {e}")
            raise RuntimeError(f"Parsing failed for {local_desc}: {e}")

        if extent_rel:
            remote_extent = os.path.join(remote_dir, extent_rel)
        else:
            # Fallback: descriptorname-flat.vmdk
            stem = local_desc.stem
            remote_extent = os.path.join(remote_dir, f"{stem}-flat.vmdk")

        if not await asyncio.to_thread(sshc.exists, remote_extent):
            logger.warning(f"Extent not found remotely: {remote_extent}")
            return None

        local_extent = outdir / os.path.basename(remote_extent)
        logger.info(f"Copying extent: {remote_extent} -> {local_extent}")
        await Fetch._scp_from_with_progress(
            sshc=sshc,
            remote=remote_extent,
            local=local_extent,
            logger=logger,
        )
        return local_extent

    @staticmethod
    async def _scp_from_with_progress(
        sshc: SSHClient,
        remote: str,
        local: Path,
        logger: logging.Logger,
        *,
        progress_interval_s: float = 1.0,
        min_percent_step: float = 1.0,
        use_atomic: bool = True,
    ) -> None:
        """
        SCP remote->local with progress reporting that is:
          - thread-safe (callback runs in worker thread)
          - throttled (avoids log spam)
          - atomic (downloads to *.part then renames)
        """
        loop = asyncio.get_running_loop()
        q: asyncio.Queue[Tuple[str, int, int]] = asyncio.Queue()

        # Atomic download target
        tmp_local = local.with_suffix(local.suffix + ".part") if use_atomic else local
        U.ensure_dir(tmp_local.parent)

        # Clean any stale partial
        if use_atomic and tmp_local.exists():
            try:
                tmp_local.unlink()
            except Exception:
                # If we can't remove, better to fail early than corrupt.
                raise RuntimeError(f"Cannot remove stale partial file: {tmp_local}")

        def progress_callback(filename: str, size: int, sent: int) -> None:
            # Called from the scp thread: MUST hop safely into the event loop thread.
            loop.call_soon_threadsafe(q.put_nowait, (filename, size, sent))

        def threaded_scp() -> None:
            sshc.scp_from(remote, tmp_local, progress=progress_callback)

        # Start SCP in a worker thread
        scp_task = asyncio.create_task(asyncio.to_thread(threaded_scp))

        last_log_t = 0.0
        last_percent = -1.0
        last_sent = -1

        try:
            while True:
                # Drain multiple updates quickly (we only care about the most recent)
                item: Optional[Tuple[str, int, int]] = None
                try:
                    item = await asyncio.wait_for(q.get(), timeout=0.5)
                    while True:
                        try:
                            item = q.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                except asyncio.TimeoutError:
                    item = None

                # If we got progress, maybe log it (throttled)
                if item is not None:
                    filename, size, sent = item
                    now = time.monotonic()
                    percent = (sent / size) * 100.0 if size > 0 else 0.0

                    should_log = False
                    if now - last_log_t >= progress_interval_s:
                        should_log = True
                    if percent - last_percent >= min_percent_step:
                        should_log = True
                    if sent < last_sent:
                        # weird reset - log once
                        should_log = True

                    if should_log:
                        logger.info(
                            f"Progress for {os.path.basename(filename)}: "
                            f"{sent}/{size} ({percent:.1f}%)"
                        )
                        last_log_t = now
                        last_percent = percent
                        last_sent = sent

                # Exit once SCP thread is done and we’ve drained progress
                if scp_task.done():
                    # Ensure any exception is raised here
                    await scp_task
                    break

            # Finalize atomic rename
            if use_atomic:
                tmp_local.replace(local)

        except asyncio.CancelledError:
            # Propagate cancel, but try to stop work + clean temp
            scp_task.cancel()
            try:
                await scp_task
            except Exception:
                pass
            if use_atomic and tmp_local.exists():
                try:
                    tmp_local.unlink()
                except Exception:
                    pass
            raise

        except Exception as e:
            # Ensure SCP task exception is not swallowed
            if not scp_task.done():
                scp_task.cancel()
                try:
                    await scp_task
                except Exception:
                    pass
            if use_atomic and tmp_local.exists():
                try:
                    tmp_local.unlink()
                except Exception:
                    pass
            logger.error(f"SCP failed for {remote} -> {local}: {e}")
            raise
