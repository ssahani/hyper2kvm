# SPDX-License-Identifier: LGPL-3.0-or-later
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from .utils import U


_STAGE_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_stage(stage: str) -> str:
    stage = stage.strip() or "unknown"
    stage = _STAGE_SAFE_RE.sub("-", stage)
    return stage[:120]


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding)
    tmp.replace(path)


@dataclass
class Checkpoint:
    stage: str
    timestamp: str
    data: Dict[str, Any]
    completed: bool = False
    version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Checkpoint":
        return Checkpoint(
            stage=str(d.get("stage", "")),
            timestamp=str(d.get("timestamp", "")),
            data=dict(d.get("data", {}) or {}),
            completed=bool(d.get("completed", False)),
            version=int(d.get("version", 1)),
        )

    @staticmethod
    def from_json(text: str) -> "Checkpoint":
        return Checkpoint.from_dict(json.loads(text))


class RecoveryManager:
    """
    Simple checkpoint manager:
      - write a checkpoint JSON file for each stage/timestamp
      - mark a checkpoint completed (and persist that change)
      - recover the newest completed checkpoint (optionally bounded by stage order)
      - cleanup old checkpoints

    Notes:
      - We keep your per-checkpoint JSON files (nice for debugging).
      - Optionally also append to a JSONL index for faster scans.
    """

    def __init__(self, logger: logging.Logger, workdir: Path, *, enable_index: bool = True):
        self.logger = logger
        self.workdir = workdir
        self.checkpoints: List[Checkpoint] = []
        self.enable_index = enable_index
        U.ensure_dir(workdir)

    def _checkpoint_path(self, cp: Checkpoint) -> Path:
        st = _safe_stage(cp.stage)
        return self.workdir / f"checkpoint_{st}_{cp.timestamp}.json"

    def _index_path(self) -> Path:
        return self.workdir / "checkpoints.jsonl"

    def _append_index(self, cp: Checkpoint) -> None:
        if not self.enable_index:
            return
        # JSONL: one object per line, durable append.
        line = json.dumps(cp.to_dict(), sort_keys=True)
        p = self._index_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def save_checkpoint(self, stage: str, data: Dict[str, Any]) -> Checkpoint:
        cp = Checkpoint(
            stage=stage,
            timestamp=U.now_ts(),
            data=data,
            completed=False,
        )
        self.checkpoints.append(cp)

        cp_file = self._checkpoint_path(cp)
        _atomic_write_text(cp_file, cp.to_json(indent=2))
        self._append_index(cp)

        self.logger.debug("Checkpoint saved: %s -> %s", stage, cp_file)
        return cp

    def mark_checkpoint_complete(self, stage: str) -> Optional[Checkpoint]:
        """
        Marks the newest in-memory checkpoint for `stage` as completed.
        If not found in memory, falls back to newest checkpoint file for the stage.
        """
        # 1) Try in-memory newest first
        for cp in reversed(self.checkpoints):
            if cp.stage == stage and not cp.completed:
                cp.completed = True
                cp_file = self._checkpoint_path(cp)
                if cp_file.exists():
                    # rewrite file atomically
                    _atomic_write_text(cp_file, cp.to_json(indent=2))
                self.logger.debug("Checkpoint completed: %s", stage)
                return cp

        # 2) Fallback: locate newest file matching stage and update it
        st = _safe_stage(stage)
        matches = sorted(self.workdir.glob(f"checkpoint_{st}_*.json"))
        if not matches:
            self.logger.debug("No checkpoint files found to complete for stage=%s", stage)
            return None

        cp_file = matches[-1]
        try:
            cp = Checkpoint.from_json(cp_file.read_text(encoding="utf-8"))
            if not cp.completed:
                cp.completed = True
                _atomic_write_text(cp_file, cp.to_json(indent=2))
            self.logger.debug("Checkpoint completed (file): %s -> %s", stage, cp_file)
            return cp
        except Exception as e:
            self.logger.debug("Failed to mark checkpoint complete for %s (%s): %s", stage, cp_file, e)
            return None

    def _load_all_checkpoint_files(self) -> List[Tuple[Path, Checkpoint]]:
        files = sorted(self.workdir.glob("checkpoint_*.json"))
        out: List[Tuple[Path, Checkpoint]] = []

        if not files:
            return out

        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Scanning checkpoints", total=len(files))
            for p in files:
                try:
                    cp = Checkpoint.from_json(p.read_text(encoding="utf-8"))
                    out.append((p, cp))
                except Exception:
                    # corrupted/partial file -> ignore
                    self.logger.debug("Skipping unreadable checkpoint: %s", p)
                progress.update(task, advance=1)

        return out

    def recover_from_checkpoint(
        self,
        stage: str,
        *,
        allow_future: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Recovery policy:
          - Find newest completed checkpoint.
          - If allow_future=False, prefer checkpoints whose stage != requested stage
            AND (heuristically) are "earlier" than requested by timestamp ordering only.
            (Stage ordering is domain-specific; if you have a stage order list, we can plug it in.)
        """
        stage = stage.strip()
        cps = self._load_all_checkpoint_files()
        if not cps:
            return None

        # Iterate newest -> oldest
        requested_safe = _safe_stage(stage)
        latest: Optional[Tuple[Path, Checkpoint]] = None

        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Selecting recovery point", total=len(cps))
            for p, cp in reversed(cps):
                # Only completed checkpoints can be resumed from
                if not cp.completed:
                    progress.update(task, advance=1)
                    continue

                # If stage is same as requested, we usually want the *previous* completed stage
                # (requested stage may be the one that failed mid-run).
                same_stage = (_safe_stage(cp.stage) == requested_safe)
                if same_stage and not allow_future:
                    progress.update(task, advance=1)
                    continue

                latest = (p, cp)
                progress.update(task, advance=1)
                break

                # (Unreachable) but keep progress logic symmetric
            # Fill progress if we broke early
            if latest is not None:
                progress.update(task, completed=len(cps))

        if latest is None:
            return None

        p, cp = latest
        self.logger.info("Recovering from checkpoint: %s (%s)", cp.stage, p.name)
        return cp.data

    def cleanup_old_checkpoints(self, keep_last: int = 5) -> None:
        cps = self._load_all_checkpoint_files()
        if len(cps) <= keep_last:
            return

        # Sort newest first by filename timestamp (you encoded timestamp in name)
        # and keep newest completed checkpoints preferentially.
        def _sort_key(item: Tuple[Path, Checkpoint]) -> str:
            return item[0].name

        cps_sorted = sorted(cps, key=_sort_key, reverse=True)

        # Prefer to keep completed ones
        keep: List[Tuple[Path, Checkpoint]] = []
        for item in cps_sorted:
            if item[1].completed:
                keep.append(item)
            if len(keep) >= keep_last:
                break

        # If not enough completed, fill with newest remaining
        if len(keep) < keep_last:
            for item in cps_sorted:
                if item in keep:
                    continue
                keep.append(item)
                if len(keep) >= keep_last:
                    break

        keep_paths = {p for p, _ in keep}
        to_delete = [p for p, _ in cps_sorted if p not in keep_paths]

        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Cleaning checkpoints", total=len(to_delete))
            for p in to_delete:
                try:
                    p.unlink(missing_ok=True)
                    self.logger.debug("Cleaned old checkpoint: %s", p.name)
                except Exception:
                    pass
                progress.update(task, advance=1)
