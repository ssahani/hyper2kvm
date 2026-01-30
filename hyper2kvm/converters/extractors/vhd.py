# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/converters/extractors/vhd.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import os
import tarfile
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

_ALLOWED_MANIFEST_EXTS = {".txt", ".json", ".yaml", ".yml"}


class VHD:
    @staticmethod
    def extract_vhd_or_tar(
        logger: logging.Logger,
        src: Path,
        outdir: Path,
        *,
        # --- Enhancement (non-breaking): optional convert stage right after extract ---
        convert_to_qcow2: bool = False,
        convert_outdir: Path | None = None,
        convert_compress: bool = False,
        convert_compress_level: int | None = None,
        # --- Enhancement: optional host-side debug logging ---
        log_virt_filesystems: bool = False,
        # --- Safety rails (non-breaking) ---
        max_members: int | None = None,
        max_total_bytes: int | None = None,
        skip_special: bool = True,
        preserve_permissions: bool = True,
        # --- Extraction policy ---
        extract_all: bool = False,
        include_manifests: bool = True,
        overwrite: bool = False,
        rename_on_collision: bool = False,
        # --- Optional timestamp preservation (off by default) ---
        preserve_timestamps: bool = False,
    ) -> list[Path]:
        """
        Accepts either:
          - a plain .vhd / .vhdx
          - a tar/tar.gz/tgz/tar.xz containing .vhd/.vhdx file(s)

        Defaults to a "safe" extraction policy:
          - Extract ONLY .vhd/.vhdx (+ optional small manifest-like files)
          - Skip special tar members (symlinks/hardlinks/devices/FIFOs)
          - Block path traversal / absolute paths / NUL bytes
          - Optional max_members / max_total_bytes safety rails

        Returns:
          - extracted VHD/VHDX paths (if no conversion), OR
          - converted .qcow2 paths (if convert_to_qcow2=True)
        """
        src = Path(src)
        outdir = Path(outdir)
        U.ensure_dir(outdir)

        if not src.exists():
            U.die(logger, f"Source not found: {src}", 1)
        if not src.is_file():
            U.die(logger, f"Source is not a file: {src}", 1)

        # Case A: direct VHD/VHDX
        if VHD._looks_like_vhd(src):
            logger.info(f"VHD: {src}")
            vhds = [src.expanduser().resolve()]
            if log_virt_filesystems:
                VHD._log_virt_filesystems(logger, vhds[0])

            if convert_to_qcow2:
                out_conv = Path(convert_outdir) if convert_outdir else (outdir / "qcow2")
                U.ensure_dir(out_conv)
                logger.info(f"QCOW2 outdir: {out_conv}")
                return VHD._convert_disks_to_qcow2(
                    logger,
                    vhds,
                    out_conv,
                    compress=convert_compress,
                    compress_level=convert_compress_level,
                    log_virt_filesystems=log_virt_filesystems,
                )
            return vhds

        # Case B: tarball
        if VHD._looks_like_tar(src):
            return VHD._extract_vhd_tar(
                logger,
                src,
                outdir,
                convert_to_qcow2=convert_to_qcow2,
                convert_outdir=convert_outdir,
                convert_compress=convert_compress,
                convert_compress_level=convert_compress_level,
                log_virt_filesystems=log_virt_filesystems,
                max_members=max_members,
                max_total_bytes=max_total_bytes,
                skip_special=skip_special,
                preserve_permissions=preserve_permissions,
                extract_all=extract_all,
                include_manifests=include_manifests,
                overwrite=overwrite,
                rename_on_collision=rename_on_collision,
                preserve_timestamps=preserve_timestamps,
            )

        # Unknown extension: try tar open anyway; if it fails, error nicely.
        try:
            with tarfile.open(src, mode="r:*"):
                pass
            return VHD._extract_vhd_tar(
                logger,
                src,
                outdir,
                convert_to_qcow2=convert_to_qcow2,
                convert_outdir=convert_outdir,
                convert_compress=convert_compress,
                convert_compress_level=convert_compress_level,
                log_virt_filesystems=log_virt_filesystems,
                max_members=max_members,
                max_total_bytes=max_total_bytes,
                skip_special=skip_special,
                preserve_permissions=preserve_permissions,
                extract_all=extract_all,
                include_manifests=include_manifests,
                overwrite=overwrite,
                rename_on_collision=rename_on_collision,
                preserve_timestamps=preserve_timestamps,
            )
        except Exception:
            U.die(logger, f"Unsupported source type (expected .vhd/.vhdx or tarball): {src}", 1)
            raise  # unreachable

    @staticmethod
    def _extract_vhd_tar(
        logger: logging.Logger,
        vhd_tar: Path,
        outdir: Path,
        *,
        convert_to_qcow2: bool = False,
        convert_outdir: Path | None = None,
        convert_compress: bool = False,
        convert_compress_level: int | None = None,
        log_virt_filesystems: bool = False,
        max_members: int | None = None,
        max_total_bytes: int | None = None,
        skip_special: bool = True,
        preserve_permissions: bool = True,
        extract_all: bool = False,
        include_manifests: bool = True,
        overwrite: bool = False,
        rename_on_collision: bool = False,
        preserve_timestamps: bool = False,
    ) -> list[Path]:
        U.banner(logger, "Extract VHD tarball")
        logger.info(f"VHD tarball: {vhd_tar}")

        outdir = Path(outdir)
        U.ensure_dir(outdir)

        # UX: summarize policy up front
        policy = "all" if extract_all else ("vhd+manifests" if include_manifests else "vhd-only")
        logger.info(
            "Extract policy: "
            f"policy={policy}, skip_special={skip_special}, "
            f"overwrite={overwrite}, rename_on_collision={rename_on_collision}, "
            f"preserve_permissions={preserve_permissions}, preserve_timestamps={preserve_timestamps}, "
            f"max_members={max_members}, max_total_bytes={max_total_bytes}"
        )
        if extract_all and not skip_special:
            logger.warning(
                "Unsafe extraction configuration: extract_all=True and skip_special=False. "
                "This may extract symlinks/hardlinks/devices/FIFOs from the tarball."
            )
        if not extract_all and include_manifests:
            logger.info(f"Manifest extensions: {', '.join(sorted(_ALLOWED_MANIFEST_EXTS))}")

        # Enforced byte limit during copy (if set)
        bytes_budget = max_total_bytes
        written_total = 0

        extracted_vhds: list[Path] = []
        extracted_other: list[Path] = []

        skipped_by_filter = 0
        skipped_special = 0

        def should_extract(member: tarfile.TarInfo) -> bool:
            """
            Default: only extract .vhd/.vhdx (+ optional manifests).
            If extract_all=True: extract everything (still subject to skip_special and safety checks).
            """
            if extract_all:
                return True

            nm = (member.name or "").strip()
            if not nm:
                return False
            # normalize separators for basename decisions
            nm = nm.replace("\\", "/")
            base = PurePosixPath(nm).name.strip().lower()

            if base.endswith(".vhd") or base.endswith(".vhdx"):
                return True
            if include_manifests:
                ext = Path(base).suffix.lower()
                if ext in _ALLOWED_MANIFEST_EXTS:
                    return True
            return False

        with tarfile.open(vhd_tar, mode="r:*") as tar:
            members = tar.getmembers()

            if max_members is not None and len(members) > max_members:
                U.die(logger, f"Tarball has too many members ({len(members)} > max_members={max_members})", 1)

            # Progress total: regular-file bytes for members we intend to extract
            total_bytes = 0
            planned_files = 0
            planned_dirs = 0
            for m in members:
                if not should_extract(m):
                    continue
                if m.isdir():
                    planned_dirs += 1
                    continue
                planned_files += 1
                if m.isreg():
                    try:
                        total_bytes += int(getattr(m, "size", 0) or 0)
                    except Exception:
                        pass

            if planned_files == 0 and planned_dirs == 0:
                U.die(
                    logger,
                    "Tarball contains no extractable members under current policy "
                    "(expected .vhd/.vhdx, optionally manifests).",
                    1,
                )

            # Metadata-based check is still useful, but not sufficient; we enforce at write-time too.
            if bytes_budget is not None and total_bytes > bytes_budget:
                U.die(
                    logger,
                    f"Tarball planned payload too large ({total_bytes} bytes > max_total_bytes={bytes_budget})",
                    1,
                )

            logger.info(
                f"Planned extraction: files={planned_files}, dirs={planned_dirs}, "
                f"planned_regular_bytes={total_bytes}"
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
                # If we have file bytes, use byte-progress. Otherwise fall back to count.
                task_total = total_bytes if total_bytes > 0 else (planned_files + planned_dirs)
                task = progress.add_task("Extracting VHD tarball", total=task_total)

                for member in members:
                    if not should_extract(member):
                        skipped_by_filter += 1
                        continue

                    extracted_bytes, extracted_path = VHD._safe_extract_one(
                        logger,
                        tar,
                        member,
                        outdir,
                        skip_special=skip_special,
                        preserve_permissions=preserve_permissions,
                        preserve_timestamps=preserve_timestamps,
                        # byte limit enforcement + overwrite policy:
                        bytes_budget=bytes_budget,
                        written_total=written_total,
                        overwrite=overwrite,
                        rename_on_collision=rename_on_collision,
                    )

                    written_total += extracted_bytes

                    if extracted_path is None and extracted_bytes == 0:
                        # chosen by filter but skipped (usually special member)
                        skipped_special += 1

                    if extracted_path is not None:
                        if VHD._looks_like_vhd(extracted_path):
                            extracted_vhds.append(extracted_path)
                        else:
                            extracted_other.append(extracted_path)

                    if total_bytes > 0:
                        progress.update(task, advance=extracted_bytes)
                    else:
                        progress.update(task, advance=1)

        # De-dup while preserving order
        def _dedup(paths: list[Path]) -> list[Path]:
            seen: set[str] = set()
            out: list[Path] = []
            for p in paths:
                s = str(p)
                if s not in seen:
                    out.append(p)
                    seen.add(s)
            return out

        uniq_vhds = _dedup(extracted_vhds)
        uniq_other = _dedup(extracted_other)

        if not uniq_vhds:
            U.die(logger, "No .vhd/.vhdx found inside tarball after extraction.", 1)

        # UX: summary
        logger.info(
            "Extraction summary: "
            f"extracted_vhds={len(uniq_vhds)}, extracted_other={len(uniq_other)}, "
            f"skipped_by_filter={skipped_by_filter}, skipped_special={skipped_special}, "
            f"written_total_bytes={written_total}"
        )
        logger.info(f"Output directory: {outdir.resolve()}")

        logger.info("VHD(s) extracted:")
        for d in uniq_vhds:
            logger.info(f" - {d}")

        if uniq_other:
            logger.info("Other extracted files:")
            for p in uniq_other[:50]:
                logger.info(f" - {p}")
            if len(uniq_other) > 50:
                logger.info(f" - ... ({len(uniq_other) - 50} more)")

        if log_virt_filesystems:
            for d in uniq_vhds:
                if d.exists():
                    VHD._log_virt_filesystems(logger, d)

        if convert_to_qcow2:
            out_conv = Path(convert_outdir) if convert_outdir else (outdir / "qcow2")
            U.ensure_dir(out_conv)
            logger.info(f"QCOW2 outdir: {out_conv}")
            return VHD._convert_disks_to_qcow2(
                logger,
                uniq_vhds,
                out_conv,
                compress=convert_compress,
                compress_level=convert_compress_level,
                log_virt_filesystems=log_virt_filesystems,
            )

        return uniq_vhds

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
        try:
            from ..qemu.converter import Convert  # type: ignore
        except Exception as e:
            U.die(logger, f"QCOW2 conversion requested but Convert could not be imported: {e}", 1)
            raise

        U.banner(logger, "Convert extracted VHD(s) to QCOW2")
        U.ensure_dir(outdir)

        outputs: list[Path] = []
        for idx, disk in enumerate(disks, 1):
            if not disk.exists():
                logger.warning(f"Skipping missing disk: {disk}")
                continue

            if log_virt_filesystems:
                VHD._log_virt_filesystems(logger, disk)

            out = (outdir / f"{disk.stem}.qcow2").expanduser().resolve()

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

            if log_virt_filesystems:
                VHD._log_virt_filesystems(logger, out)

        # De-dup preserving order
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
        cmd = ["virt-filesystems", "-a", str(image), "--all", "--long", "-h"]
        try:
            cp = U.run_cmd(logger, cmd, capture=True, check=False)
            out = (cp.stdout or "").strip()
            if out:
                logger.info(f"virt-filesystems -a {image} --all --long -h\n{out}")
            else:
                logger.info(f"virt-filesystems -a {image}: (empty)")
            return {"ok": True, "stdout": out, "cmd": cmd, "rc": getattr(cp, "returncode", 0)}
        except Exception as e:
            logger.warning(f"virt-filesystems failed for {image}: {e}")
            return {"ok": False, "error": str(e), "cmd": cmd}

    @staticmethod
    def _looks_like_vhd(p: Path) -> bool:
        s = p.name.lower()
        return s.endswith(".vhd") or s.endswith(".vhdx")

    @staticmethod
    def _looks_like_tar(p: Path) -> bool:
        s = p.name.lower()
        return s.endswith(".tar") or s.endswith(".tar.gz") or s.endswith(".tgz") or s.endswith(".tar.xz") or s.endswith(".txz")

    @staticmethod
    def _normalize_tar_name(name: str) -> str:
        """
        Normalize tar member names to a predictable POSIX-ish form.

        - Reject NUL bytes
        - Convert backslashes to slashes.
        - Strip leading "./"
        - Reject empty names.
        - Reject any path segment that is ".." after normalization.
        - Drop "." segments to make paths/logs cleaner.
        """
        nm = (name or "").strip()
        if "\x00" in nm:
            raise RuntimeError(f"Blocked NUL byte in tar member name: {name!r}")

        nm = nm.replace("\\", "/")
        while nm.startswith("./"):
            nm = nm[2:]
        if not nm:
            raise RuntimeError("Blocked empty tar member name")

        # Block absolute paths (posix + windows-ish)
        if nm.startswith("/") or nm.startswith("\\") or (len(nm) >= 2 and nm[1] == ":" and nm[0].isalpha()):
            raise RuntimeError(f"Blocked unsafe tar absolute path: {name}")

        pp = PurePosixPath(nm)
        clean_parts: list[str] = []
        for part in pp.parts:
            if part in ("", "."):
                continue
            if part == "..":
                raise RuntimeError(f"Blocked unsafe tar path segment '..': {name}")
            clean_parts.append(part)

        if not clean_parts:
            raise RuntimeError("Blocked empty tar member name after normalization")

        return str(PurePosixPath(*clean_parts))

    @staticmethod
    def _unique_path(path: Path) -> Path:
        """
        Create a unique path by appending ' (N)' before suffix.
        Example: disk.vhd -> disk (1).vhd, disk (2).vhd, ...
        """
        if not path.exists():
            return path
        stem = path.stem
        suf = path.suffix
        parent = path.parent
        for i in range(1, 10_000):
            cand = parent / f"{stem} ({i}){suf}"
            if not cand.exists():
                return cand
        raise RuntimeError(f"Could not find unique filename for {path}")

    @staticmethod
    def _safe_extract_one(
        logger: logging.Logger,
        tar: tarfile.TarFile,
        member: tarfile.TarInfo,
        outdir: Path,
        *,
        skip_special: bool = True,
        preserve_permissions: bool = True,
        preserve_timestamps: bool = False,
        bytes_budget: int | None = None,
        written_total: int = 0,
        overwrite: bool = False,
        rename_on_collision: bool = False,
    ) -> tuple[int, Path | None]:
        """
        Safely extract a single tar member into outdir.

        Policy:
          - Normalize path: '\\' -> '/', strip './', reject '..' segments, reject NUL bytes, drop '.' segments.
          - Block absolute paths + traversal.
          - By default, skip symlinks/hardlinks/devices/FIFOs and anything non-file/non-dir.
          - Extract regular files manually via extractfile() (avoid tar.extract() footguns).
          - Create directories explicitly.
          - Enforce byte budget during copy (if set).
          - Handle collisions: default fail; optional overwrite; optional auto-rename.
          - On any error (budget abort, I/O): delete partially written file.
          - Optional timestamp preservation (mtime).

        Returns:
          (extracted_bytes, extracted_path_or_none)
        """
        outdir = Path(outdir).resolve()

        # Normalize and validate member name
        norm = VHD._normalize_tar_name(member.name or "")
        target_path = (outdir / norm).resolve()

        # Block traversal (defense in depth after normalization)
        if outdir != target_path and outdir not in target_path.parents:
            raise RuntimeError(f"Blocked unsafe tar path traversal: {member.name}")

        # Directories
        if member.isdir():
            target_path.mkdir(parents=True, exist_ok=True)
            if preserve_permissions:
                try:
                    mode = int(member.mode or 0o755) & 0o777
                    mode |= 0o200  # ensure user-write
                    os.chmod(target_path, mode)
                except Exception:
                    pass
            if preserve_timestamps:
                try:
                    mt = int(getattr(member, "mtime", 0) or 0)
                    if mt > 0:
                        os.utime(target_path, (mt, mt))
                except Exception:
                    pass
            return 0, target_path

        # Regular files
        if member.isreg():
            target_path.parent.mkdir(parents=True, exist_ok=True)

            final_path = target_path
            if final_path.exists():
                if rename_on_collision and not overwrite:
                    final_path = VHD._unique_path(final_path)
                elif overwrite:
                    pass
                else:
                    raise RuntimeError(f"Refusing to overwrite existing file: {final_path}")

            f = tar.extractfile(member)
            if f is None:
                raise RuntimeError(f"Failed to read tar member payload: {member.name}")

            extracted = 0
            try:
                with f:
                    with open(final_path, "wb") as out_f:
                        while True:
                            chunk = f.read(1024 * 1024)
                            if not chunk:
                                break
                            out_f.write(chunk)
                            extracted += len(chunk)

                            if bytes_budget is not None and (written_total + extracted) > bytes_budget:
                                try:
                                    out_f.flush()
                                    os.fsync(out_f.fileno())
                                except Exception:
                                    pass
                                raise RuntimeError(
                                    f"Extraction exceeded max_total_bytes={bytes_budget} while writing {member.name} "
                                    f"(written_total={written_total}, this_file={extracted})"
                                )
            except Exception:
                # Ensure partial file doesn't survive errors
                try:
                    if final_path.exists():
                        final_path.unlink()
                except Exception:
                    pass
                raise

            if preserve_permissions:
                try:
                    # files: mask to 666, and ensure user-write so cleanup is possible
                    mode = int(member.mode or 0o644) & 0o666
                    mode |= 0o200
                    os.chmod(final_path, mode)
                except Exception:
                    pass

            if preserve_timestamps:
                try:
                    mt = int(getattr(member, "mtime", 0) or 0)
                    if mt > 0:
                        os.utime(final_path, (mt, mt))
                except Exception:
                    pass

            return extracted, final_path

        # Everything else (symlinks, hardlinks, devices, fifos, etc.)
        if skip_special:
            logger.warning(f"Skipping special tar member: {member.name} (type={member.type!r})")
            return 0, None

        raise RuntimeError(f"Refusing to extract unsupported tar member: {member.name} (type={member.type!r})")
