from __future__ import annotations

import logging
import os
import tarfile
from pathlib import Path
from typing import List, Optional, Dict
import xml.etree.ElementTree as ET

from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    DownloadColumn,
    TransferSpeedColumn,
)

from ..core.utils import U


class OVF:
    @staticmethod
    def extract_ova(logger: logging.Logger, ova: Path, outdir: Path) -> List[Path]:
        """
        Extract an OVA (tar) into outdir, then parse OVF(s) inside and return referenced disk paths.

        Returns:
            List[Path]: Disk file paths (in outdir) referenced by the OVF.
        """
        U.banner(logger, "Extract OVA")
        ova = Path(ova)
        outdir = Path(outdir)
        U.ensure_dir(outdir)

        if not ova.exists():
            U.die(logger, f"OVA not found: {ova}", 1)
        if not ova.is_file():
            U.die(logger, f"OVA is not a file: {ova}", 1)

        logger.info(f"OVA: {ova}")

        with tarfile.open(ova, mode="r:*") as tar:
            members = tar.getmembers()

            # Total bytes for progress (some tar members may have 0/None size)
            total_bytes = 0
            for m in members:
                try:
                    total_bytes += int(getattr(m, "size", 0) or 0)
                except Exception:
                    pass

            with Progress(
                TextColumn("{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TextColumn("{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
            ) as progress:
                task = progress.add_task("Extracting OVA", total=total_bytes or len(members))

                for member in members:
                    OVF._safe_extract_one(tar, member, outdir)

                    # Advance by bytes if we can, otherwise by 1
                    advance = int(getattr(member, "size", 0) or 0)
                    progress.update(task, advance=advance if total_bytes else 1)

        ovfs = sorted(outdir.glob("*.ovf"))
        if not ovfs:
            U.die(logger, "No OVF found inside OVA.", 1)

        # Many OVAs have one OVF; if multiple, parse them all and union disk references.
        disks: List[Path] = []
        for ovf in ovfs:
            disks.extend(OVF.extract_ovf(logger, ovf, outdir))

        # De-dup while preserving order
        seen = set()
        uniq: List[Path] = []
        for d in disks:
            if d not in seen:
                uniq.append(d)
                seen.add(d)
        return uniq

    @staticmethod
    def extract_ovf(logger: logging.Logger, ovf: Path, outdir: Path) -> List[Path]:
        """
        Parse an OVF file and return disk paths referenced via <File ... ovf:href="..."> used by <Disk ovf:fileRef="...">.
        """
        U.banner(logger, "Parse OVF")
        ovf = Path(ovf)
        outdir = Path(outdir)

        if not ovf.exists():
            U.die(logger, f"OVF not found: {ovf}", 1)

        logger.info(f"OVF: {ovf}")

        try:
            tree = ET.parse(ovf)
        except ET.ParseError as e:
            U.die(logger, f"Failed to parse OVF XML: {ovf}: {e}", 1)

        root = tree.getroot()

        # Try to detect OVF namespace dynamically, fallback to common one.
        ns_uri = None
        if root.tag.startswith("{") and "}" in root.tag:
            ns_uri = root.tag.split("}", 1)[0][1:]
        if not ns_uri:
            ns_uri = "http://schemas.dmtf.org/ovf/envelope/1"

        ns = {"ovf": ns_uri}

        # Build fileRef -> href map from <File ovf:id="..." ovf:href="...">
        file_map: Dict[str, str] = {}
        for f in root.findall(".//ovf:File", ns):
            fid = f.get(f"{{{ns_uri}}}id") or f.get("ovf:id") or f.get("id")
            href = f.get(f"{{{ns_uri}}}href") or f.get("ovf:href") or f.get("href")
            if fid and href:
                file_map[fid] = href

        disks: List[Path] = []
        for disk in root.findall(".//ovf:Disk", ns):
            file_id = disk.get(f"{{{ns_uri}}}fileRef") or disk.get("ovf:fileRef") or disk.get("fileRef")
            if not file_id:
                continue

            href = file_map.get(file_id)
            if not href:
                # Some OVFs are weird; don’t hard-fail, but warn loudly.
                logger.warning(f"OVF disk references fileRef={file_id} but no matching <File> entry was found")
                continue

            # Normalize (OVF hrefs are usually relative, but can include directories)
            href_norm = href.replace("\\", "/").lstrip("/")
            disks.append(outdir / href_norm)

        if not disks:
            U.die(logger, "No disks found in OVF.", 1)

        logger.info("Disks referenced by OVF:")
        for d in disks:
            logger.info(f" - {d}")

        return disks

    @staticmethod
    def _safe_extract_one(tar: tarfile.TarFile, member: tarfile.TarInfo, outdir: Path) -> None:
        """
        Extract a single tar member safely, preventing path traversal.
        """
        outdir = Path(outdir).resolve()

        # member.name can be absolute or contain .. components
        target_path = (outdir / member.name).resolve()

        # Ensure the target is within outdir
        if outdir != target_path and outdir not in target_path.parents:
            raise RuntimeError(f"Blocked unsafe tar path traversal: {member.name}")

        # Extract (tarfile handles dirs/files/links; we rely on path check above)
        tar.extract(member, outdir)
