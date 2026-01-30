# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/converters/extractors/ovf.py
from __future__ import annotations

import logging
import os
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Any

from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from ...core.utils import U


class OVF:
    @staticmethod
    def extract_ova(
        logger: logging.Logger,
        ova: Path,
        outdir: Path,
        *,
        # --- Enhancement (non-breaking): optional convert stage right after extract ---
        convert_to_qcow2: bool = False,
        convert_outdir: Path | None = None,
        convert_compress: bool = False,
        convert_compress_level: int | None = None,
        # --- Enhancement: optional host-side debug logging ---
        log_virt_filesystems: bool = False,
        # --- Safety rails (optional; defaults keep behavior permissive) ---
        skip_special: bool = True,  # skip symlinks/hardlinks/devices/fifos
        max_members: int | None = None,
        max_total_bytes: int | None = None,
        max_member_bytes: int | None = None,
        max_files: int | None = None,  # regular files only
    ) -> list[Path]:
        """
        Extract an OVA (tar) into outdir, then parse OVF(s) inside and return referenced disk paths.

        Enhancements (non-breaking):
          - Optional conversion to QCOW2 immediately after extraction (convert_to_qcow2=True)
          - Optional "virt-filesystems -a ..." logging for each disk

        Safety improvements:
          - Strong safe extraction (no tar.extract for files; blocks traversal; skips links/devices by default)
          - Optional limits to reduce tar-bomb risk (max_members / max_total_bytes / max_member_bytes / max_files)
          - OVF href safe-join (blocks ../ escapes from OVF metadata)

        Returns:
            List[Path]: Disk file paths (in outdir) referenced by the OVF
                        (or converted qcow2 outputs if enabled).
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

        extracted_files = 0
        skipped_special_count = 0
        skipped_other = 0
        blocked = 0
        regular_file_count = 0

        with tarfile.open(ova, mode="r:*") as tar:
            members = tar.getmembers()

            if max_members is not None and len(members) > max_members:
                U.die(
                    logger,
                    f"OVA contains {len(members)} members which exceeds max_members={max_members}",
                    1,
                )

            # Total bytes for progress (regular files only; directories/specials don't count)
            total_bytes = 0
            for m in members:
                try:
                    if m.isreg():
                        total_bytes += int(getattr(m, "size", 0) or 0)
                except Exception:
                    pass

            if max_total_bytes is not None and total_bytes > max_total_bytes:
                U.die(
                    logger,
                    f"OVA total regular-file size {total_bytes} exceeds max_total_bytes={max_total_bytes}",
                    1,
                )

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
                    wrote = 0  # IMPORTANT: avoid UnboundLocalError when exceptions happen

                    # File-count DoS guard (regular files only)
                    if member.isreg():
                        regular_file_count += 1
                        if max_files is not None and regular_file_count > max_files:
                            U.die(
                                logger,
                                f"OVA exceeds max_files={max_files} (regular files seen: {regular_file_count})",
                                1,
                            )

                    try:
                        wrote, status = OVF._safe_extract_one(
                            tar,
                            member,
                            outdir,
                            skip_special=skip_special,
                            max_member_bytes=max_member_bytes,
                        )
                        if status == "extracted":
                            extracted_files += 1
                        elif status == "skipped_special":
                            skipped_special_count += 1
                        elif status == "skipped_other":
                            skipped_other += 1
                    except Exception as e:
                        blocked += 1
                        logger.error(f"Blocked/failed extracting tar member {member.name!r}: {e}")

                    # Advance by bytes written if we can, otherwise by 1 if total unknown
                    progress.update(task, advance=wrote if total_bytes else 1)

        if skipped_special_count:
            logger.warning(
                f"Security: skipped {skipped_special_count} special tar members (links/devices/fifos)"
            )
        if blocked:
            logger.warning(f"Security: {blocked} tar members failed safety checks or extraction (see errors above)")

        ovfs = sorted(outdir.glob("*.ovf"))
        if not ovfs:
            U.die(logger, "No OVF found inside OVA.", 1)

        # Many OVAs have one OVF; if multiple, parse them all and union disk references.
        disks: list[Path] = []
        for ovf in ovfs:
            disks.extend(
                OVF.extract_ovf(
                    logger,
                    ovf,
                    outdir,
                    log_virt_filesystems=log_virt_filesystems,
                )
            )

        # De-dup while preserving order
        seen: set[Path] = set()
        uniq: list[Path] = []
        for d in disks:
            if d not in seen:
                uniq.append(d)
                seen.add(d)

        # Validate existence and warn (don’t hard-fail; OVFs can reference missing disks in broken exports)
        missing = [d for d in uniq if not d.exists()]
        if missing:
            logger.warning("Some OVF-referenced disks were not found after extraction:")
            for m in missing:
                logger.warning(f" - {m}")
            uniq = [d for d in uniq if d.exists()]
            if not uniq:
                U.die(logger, "OVF referenced disks but none were found on disk after extraction.", 1)

        # Optional conversion
        if convert_to_qcow2:
            out_conv = Path(convert_outdir) if convert_outdir else (outdir / "qcow2")
            U.ensure_dir(out_conv)
            return OVF._convert_disks_to_qcow2(
                logger,
                uniq,
                out_conv,
                compress=convert_compress,
                compress_level=convert_compress_level,
                log_virt_filesystems=log_virt_filesystems,
            )

        return uniq

    @staticmethod
    def extract_ovf(
        logger: logging.Logger,
        ovf: Path,
        outdir: Path,
        *,
        log_virt_filesystems: bool = False,
    ) -> list[Path]:
        """
        Parse an OVF file and return disk paths referenced via <File ... ovf:href="..."> used by <Disk ovf:fileRef="...">.

        Safety improvement:
          - OVF href safe-join (blocks ../ escapes from OVF metadata)
          - Prefer defusedxml if available (mitigates XML entity expansion DoS)
        """
        U.banner(logger, "Parse OVF")
        ovf = Path(ovf)
        outdir = Path(outdir)

        if not ovf.exists():
            U.die(logger, f"OVF not found: {ovf}", 1)

        logger.info(f"OVF: {ovf}")

        # Prefer defusedxml if installed
        try:
            from defusedxml.ElementTree import parse as safe_parse  # type: ignore
        except Exception:
            safe_parse = None

        try:
            tree = safe_parse(ovf) if safe_parse else ET.parse(ovf)
        except ET.ParseError as e:
            U.die(logger, f"Failed to parse OVF XML: {ovf}: {e}", 1)
        except Exception as e:
            U.die(logger, f"Failed to read OVF XML: {ovf}: {e}", 1)

        root = tree.getroot()

        # Try to detect OVF namespace dynamically, fallback to common one.
        ns_uri = None
        if root.tag.startswith("{") and "}" in root.tag:
            ns_uri = root.tag.split("}", 1)[0][1:]
        if not ns_uri:
            ns_uri = "http://schemas.dmtf.org/ovf/envelope/1"

        ns = {"ovf": ns_uri}

        # Build fileRef -> href map from <File ovf:id="..." ovf:href="...">
        file_map: dict[str, str] = {}
        for f in root.findall(".//ovf:File", ns):
            fid = f.get(f"{{{ns_uri}}}id") or f.get("ovf:id") or f.get("id")
            href = f.get(f"{{{ns_uri}}}href") or f.get("ovf:href") or f.get("href")
            if fid and href:
                file_map[fid] = href

        disks: list[Path] = []
        for disk in root.findall(".//ovf:Disk", ns):
            file_id = disk.get(f"{{{ns_uri}}}fileRef") or disk.get("ovf:fileRef") or disk.get("fileRef")
            if not file_id:
                continue

            href = file_map.get(file_id)
            if not href:
                logger.warning(f"OVF disk references fileRef={file_id} but no matching <File> entry was found")
                continue

            try:
                disks.append(OVF._safe_out_path(outdir, href))
            except Exception as e:
                logger.warning(f"Security: skipping unsafe OVF href={href!r} (fileRef={file_id}): {e}")

        if not disks:
            U.die(logger, "No disks found in OVF.", 1)

        logger.info("Disks referenced by OVF:")
        for d in disks:
            logger.info(f" - {d}")

        # Optional: log host-side disk layout for each disk that exists
        if log_virt_filesystems:
            for d in disks:
                if d.exists():
                    OVF._log_virt_filesystems(logger, d)

        return disks

    @staticmethod
    def _convert_disks_to_qcow2(
        logger: logging.Logger,
        disks: list[Path],
        outdir: Path,
        *,
        compress: bool = False,
        compress_level: int | None = None,
        log_virt_filesystems: bool = False,
    ) -> list[Path]:
        """
        Convert extracted disks to qcow2 outputs. Keeps order and de-dups.
        Uses the project Convert wrapper if available.
        """
        try:
            from ..qemu.converter import Convert  # type: ignore
        except Exception as e:
            U.die(logger, f"QCOW2 conversion requested but Convert could not be imported: {e}", 1)
            raise  # unreachable

        U.banner(logger, "Convert extracted disks to QCOW2")
        U.ensure_dir(outdir)

        outputs: list[Path] = []
        for idx, disk in enumerate(disks, 1):
            if not disk.exists():
                logger.warning(f"Skipping missing disk: {disk}")
                continue

            if log_virt_filesystems:
                OVF._log_virt_filesystems(logger, disk)

            # Name outputs deterministically
            stem = disk.name
            if stem.lower().endswith(".vmdk"):
                stem = stem[:-5]
            out = (outdir / f"{stem}.qcow2").expanduser().resolve()

            last_bucket = {"b": -1}

            def progress_callback(progress: float, idx=idx, disk=disk, last_bucket=last_bucket) -> None:
                b = int(progress * 20)  # 0..20
                if b != last_bucket["b"]:
                    last_bucket["b"] = b
                    if progress < 1.0:
                        logger.info(f"QCOW2 convert [{idx}/{len(disks)}] {disk.name}: {progress:.1%}")
                    else:
                        logger.info(f"QCOW2 convert [{idx}/{len(disks)}] {disk.name}: complete")

            logger.info(
                f"Converting [{idx}/{len(disks)}]: {disk} -> {out} "
                f"(compress={compress}, level={compress_level})"
            )

            Convert.convert_image_with_progress(
                logger,
                disk,
                out,
                out_format="qcow2",
                compress=compress,
                compress_level=compress_level,
                progress_callback=progress_callback,
            )
            Convert.validate(logger, out)
            outputs.append(out)

        # De-dup while preserving order
        seen: set[str] = set()
        uniq: list[Path] = []
        for p in outputs:
            s = str(p)
            if s not in seen:
                uniq.append(p)
                seen.add(s)

        if not uniq:
            U.die(logger, "QCOW2 conversion produced no outputs.", 1)

        logger.info("QCOW2 outputs:")
        for p in uniq:
            logger.info(f" - {p}")
        return uniq

    @staticmethod
    def _log_virt_filesystems(logger: logging.Logger, image: Path) -> dict[str, Any]:
        """
        Host-side introspection:
          virt-filesystems -a <image> --all --long -h

        Note: resource limiting/timeouts are best implemented in U.run_cmd globally.
        """
        cmd = ["virt-filesystems", "-a", str(image), "--all", "--long", "-h"]
        try:
            # If your U.run_cmd supports timeout, pass it; otherwise ignore (compat).
            try:
                cp = U.run_cmd(logger, cmd, capture=True, timeout_s=60)  # type: ignore[call-arg]
            except TypeError:
                cp = U.run_cmd(logger, cmd, capture=True)

            out = (cp.stdout or "").strip()
            if out:
                logger.info(f"virt-filesystems -a {image} --all --long -h\n{out}")
            else:
                logger.info(f"virt-filesystems -a {image}: (empty)")
            return {"ok": True, "stdout": out, "cmd": cmd}
        except Exception as e:
            logger.warning(f"virt-filesystems failed for {image}: {e}")
            return {"ok": False, "error": str(e), "cmd": cmd}

    # Safe path helpers

    @staticmethod
    def _clean_posix_relpath(name: str) -> PurePosixPath:
        """
        Normalize a tar/OVF path to a safe relative POSIX path:
          - converts backslashes to slashes
          - strips ALL leading '/' (no absolute paths)
          - drops '.' segments
          - rejects '..' segments
          - rejects empty results
        """
        raw = (name or "").replace("\\", "/")

        # Strip all leading slashes explicitly (clear intent)
        raw = raw.lstrip("/")

        p = PurePosixPath(raw)

        clean_parts: list[str] = []
        for part in p.parts:
            if part in ("", "."):
                continue
            if part == "..":
                raise ValueError(f"Blocked '..' in path: {name!r}")
            clean_parts.append(part)

        if not clean_parts:
            raise ValueError(f"Empty/invalid path: {name!r}")

        return PurePosixPath(*clean_parts)

    @staticmethod
    def _assert_no_symlink_parents(outdir_r: Path, target: Path) -> None:
        """
        Hardening: ensure no path component *within outdir* is a symlink.
        This mitigates attacks where an adversary pre-creates symlinks inside outdir.
        """
        try:
            rel = target.relative_to(outdir_r)
        except Exception:
            raise ValueError(f"Target is not inside outdir: {target}") from None

        cur = outdir_r
        for part in rel.parts[:-1]:  # parent components only
            cur = cur / part
            # If it exists and is a symlink -> reject
            try:
                if cur.exists() and cur.is_symlink():
                    raise ValueError(f"Parent component is a symlink: {cur}")
            except OSError:
                # If we can't stat, treat as suspicious
                raise ValueError(f"Unable to stat parent component safely: {cur}") from None

    @staticmethod
    def _safe_out_path(outdir: Path, rel: str) -> Path:
        """
        Safe-join outdir with a possibly-untrusted relative path (tar member name or OVF href).
        """
        outdir_r = Path(outdir).resolve()
        pp = OVF._clean_posix_relpath(rel)
        target = (outdir_r / Path(*pp.parts)).resolve()

        if target != outdir_r and outdir_r not in target.parents:
            raise ValueError(f"Blocked path traversal: {rel!r}")

        # Additional hardening: prevent symlink parent hops
        OVF._assert_no_symlink_parents(outdir_r, target)

        return target

    # Safe extraction

    @staticmethod
    def _safe_extract_one(
        tar: tarfile.TarFile,
        member: tarfile.TarInfo,
        outdir: Path,
        *,
        skip_special: bool = True,
        max_member_bytes: int | None = None,
    ) -> tuple[int, str]:
        """
        Extract a single tar member safely.

        Returns:
            (bytes_written, status)
            status in: extracted | skipped_special | skipped_other
        """
        # Identify special members
        is_special = (
            member.issym()
            or member.islnk()
            or member.ischr()
            or member.isblk()
            or member.isfifo()
            or getattr(member, "isdev", lambda: False)()
        )
        if is_special and skip_special:
            return (0, "skipped_special")

        # We only support dirs + regular files (everything else skipped)
        if member.isdir():
            target_dir = OVF._safe_out_path(outdir, member.name)
            target_dir.mkdir(parents=True, exist_ok=True)
            return (0, "extracted")

        if not member.isreg():
            return (0, "skipped_other")

        # Size safety rail
        size = int(getattr(member, "size", 0) or 0)
        if max_member_bytes is not None and size > max_member_bytes:
            raise ValueError(
                f"Member {member.name!r} size {size} exceeds max_member_bytes={max_member_bytes}"
            )

        target = OVF._safe_out_path(outdir, member.name)
        target.parent.mkdir(parents=True, exist_ok=True)

        src = tar.extractfile(member)
        if src is None:
            return (0, "skipped_other")

        wrote = 0
        tmp_path: Path | None = None
        try:
            # Use a unique temp file in the same directory (avoids collisions; best-effort atomic replace)
            with tempfile.NamedTemporaryFile(
                dir=str(target.parent),
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as tf:
                tmp_path = Path(tf.name)
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    tf.write(chunk)
                    wrote += len(chunk)

            os.replace(str(tmp_path), str(target))

            # Conservative permissions: we are not honoring tar modes (safer),
            # but ensure it's not accidentally executable/world-writable.
            try:
                if os.name == "posix":
                    os.chmod(target, 0o644)
            except Exception:
                pass

        finally:
            try:
                if tmp_path is not None and tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

        return (wrote, "extracted")
