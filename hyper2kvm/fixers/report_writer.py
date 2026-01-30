# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/report_writer.py
"""
hyper2kvm report writer.

"""

from __future__ import annotations

import datetime as _dt
import os
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .. import __version__
from ..core.utils import U


def _json_safe(obj: Any) -> Any:
    """
    Convert common non-JSON-native objects into JSON-safe representations.
    Keeps the report generation resilient even when payloads contain Paths, Enums,
    dataclasses, datetimes, bytes, etc.
    """
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, _dt.datetime):
        return obj.isoformat()
    if isinstance(obj, _dt.date):
        return obj.isoformat()
    if isinstance(obj, (bytes, bytearray)):
        # Avoid huge blobs; represent as length + short prefix.
        b = bytes(obj)
        prefix = b[:32].hex()
        return {"_type": "bytes", "len": len(b), "prefix_hex": prefix}
    if is_dataclass(obj):
        try:
            return _json_safe(asdict(obj))
        except Exception:
            return {"_type": "dataclass", "repr": repr(obj)}
    # Enums often have `.value`
    v = getattr(obj, "value", None)
    if v is not None and not isinstance(obj, (dict, list, tuple, set)):
        try:
            return _json_safe(v)
        except Exception:
            return str(obj)
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v2 in obj.items():
            try:
                ks = str(k)
            except Exception:
                ks = repr(k)
            out[ks] = _json_safe(v2)
        return out
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(x) for x in list(obj)]
    # Fallback: stringy representation
    return str(obj)


def _dump_json_best_effort(x: Any) -> str:
    """
    Prefer project JSON dump (consistent formatting) but never raise.
    """
    try:
        return U.json_dump(_json_safe(x))
    except Exception:
        # Last-ditch fallback (still safe-ish)
        try:
            import json
            return json.dumps(_json_safe(x), indent=2, sort_keys=True)
        except Exception:
            return repr(x)


def _atomic_write_text(path: Path, content: str, suffix: str = ".tmp.hyper2kvm") -> None:
    """
    Best-effort atomic-ish write:
      - write temp file in the same directory
      - flush + fsync temp
      - os.replace to target
      - fsync directory (best-effort)

    Falls back to non-atomic write if something goes wrong.
    """
    tmp = Path(str(path) + suffix)
    try:
        # Ensure parent exists
        U.ensure_dir(path.parent)

        # Write temp
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass

        # Atomic replace
        os.replace(str(tmp), str(path))

        # Best-effort fsync directory to persist rename
        try:
            dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except Exception:
            pass
    except Exception:
        # Fallback: plain write
        try:
            path.write_text(content, encoding="utf-8")
        except Exception:
            # If even this fails, re-raise to caller (caller will swallow/log)
            raise
    finally:
        # Cleanup temp if still present
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def _json_sidecar_path(base: Path) -> Path:
    """
    Decide JSON report path from a base report path.

    Rules:
      - base ends with .md/.txt/... -> replace suffix with .json
      - base has no suffix -> add .json
      - base ends with .json -> same path (JSON-only destination)
    """
    if base.suffix.lower() == ".json":
        return base
    if base.suffix:
        return base.with_suffix(".json")
    return Path(str(base) + ".json")


def _markdown_path_for_base(base: Path) -> Path:
    """
    Decide Markdown report path from a base report path.

    Rules:
      - base ends with .json -> replace with .md (so JSON + MD can coexist)
      - base ends with something else -> keep base as-is
      - base has no suffix -> keep base as-is (user probably passed a filename)
    """
    if base.suffix.lower() == ".json":
        return base.with_suffix(".md")
    return base


# Report content helpers

def _extract_validation(validation_payload: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Compatibility:
      - New format: {"results": {...}, "stats": {...}}
      - Old format: flat dict of results
    """
    validation_results: dict[str, Any] = {}
    validation_stats: dict[str, Any] = {}
    if isinstance(validation_payload, dict):
        if isinstance(validation_payload.get("results"), dict):
            validation_results = validation_payload["results"]
            validation_stats = validation_payload.get("stats", {}) or {}
        else:
            validation_results = validation_payload
    return validation_results, validation_stats


def _compute_failed_checks(validation_results: dict[str, Any]) -> tuple[list[str], list[str]]:
    failed: list[str] = []
    critical_failed: list[str] = []
    for name, r in (validation_results or {}).items():
        if not isinstance(r, dict):
            continue
        if not r.get("passed", False):
            failed.append(str(name))
            if r.get("critical"):
                critical_failed.append(str(name))
    return failed, critical_failed


def _build_run_meta(self) -> dict[str, Any]:
    return {
        "version": __version__,
        "dry_run": getattr(self, "dry_run", False),
        "no_backup": getattr(self, "no_backup", False),
        "print_fstab": getattr(self, "print_fstab", False),
        "update_grub": getattr(self, "update_grub", False),
        "regen_initramfs": getattr(self, "regen_initramfs", False),
        "fstab_mode": getattr(getattr(self, "fstab_mode", None), "value", str(getattr(self, "fstab_mode", ""))),
        "remove_vmware_tools": bool(getattr(self, "remove_vmware_tools", False)),
        "resize": getattr(self, "resize", None),
        "virtio_drivers_dir": getattr(self, "virtio_drivers_dir", None),
        "image": str(getattr(self, "image", "")),
        "root_dev": getattr(self, "root_dev", None),
        "root_btrfs_subvol": getattr(self, "root_btrfs_subvol", None),
        "inspect_root": getattr(self, "inspect_root", None),
        "timestamps": getattr(self, "report", {}).get("timestamps", {}) if getattr(self, "report", None) else {},
    }


def _build_host_meta() -> dict[str, Any]:
    host_meta: dict[str, Any] = {"uid": None, "user": None, "cwd": None}
    try:
        host_meta["uid"] = os.geteuid()
    except Exception:
        pass
    try:
        host_meta["user"] = os.environ.get("SUDO_USER") or os.environ.get("USER") or None
    except Exception:
        pass
    try:
        host_meta["cwd"] = str(Path.cwd())
    except Exception:
        pass
    return host_meta


def _build_tool_inventory() -> dict[str, Any]:
    tools = ["qemu-img", "virsh", "qemu-system-x86_64", "sgdisk", "rsync"]
    tool_inv: dict[str, Any] = {}
    for t in tools:
        tool_inv[t] = {"path": U.which(t)}
    tool_inv["python"] = {
        "executable": getattr(sys, "executable", None),
        "version": getattr(sys, "version", None),
    }
    return tool_inv


def _extract_changes_analysis(self) -> tuple[dict[str, Any], dict[str, Any], Any, Any]:
    report = getattr(self, "report", {}) or {}
    changes: dict[str, Any] = report.get("changes", {}) or {}
    analysis: dict[str, Any] = report.get("analysis", {}) or {}
    validation_payload: Any = report.get("validation")
    error_payload: Any = report.get("error")
    return changes, analysis, validation_payload, error_payload


def _extract_counts(changes: dict[str, Any]) -> tuple[int, int, dict[str, Any], list[str]]:
    # fstab count
    fstab_count = int(changes.get("fstab", 0) or 0)

    # crypttab can be int or dict in future
    crypt = changes.get("crypttab", 0)
    if isinstance(crypt, dict):
        crypttab_count = int(crypt.get("count", 0) or 0)
    else:
        try:
            crypttab_count = int(crypt or 0)
        except Exception:
            crypttab_count = 0

    net = changes.get("network", {}) or {}
    net_files = (net.get("updated_files", []) or [])
    if not isinstance(net_files, list):
        net_files = []
    return fstab_count, crypttab_count, net, [str(x) for x in net_files]


def _extract_analysis_sections(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "fstab_changes": analysis.get("fstab_changes", []) or [],
        "regen": analysis.get("regen", {}) or {},
        "disk": analysis.get("disk", {}) or {},
        "mdraid": analysis.get("mdraid", {}) or {},
        "windows": analysis.get("windows", {}) or {},
        "virtio": analysis.get("virtio", {}) or {},
    }


def _extract_feature_flags(changes: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    vmware_rm = changes.get("vmware_tools_removed", {}) or {}
    cloud = changes.get("cloud_init_injected", {}) or {}
    return vmware_rm, cloud


def _extract_checkpoints(self) -> list[dict[str, Any]]:
    cps: list[dict[str, Any]] = []
    rm = getattr(self, "recovery_manager", None)
    if rm and getattr(rm, "checkpoints", None):
        try:
            for cp in rm.checkpoints:
                cps.append(
                    {
                        "stage": getattr(cp, "stage", None),
                        "timestamp": getattr(cp, "timestamp", None),
                        "completed": getattr(cp, "completed", None),
                    }
                )
        except Exception:
            return []
    return cps


def _build_json_report(
    self,
    run_meta: dict[str, Any],
    host_meta: dict[str, Any],
    tool_inv: dict[str, Any],
    changes: dict[str, Any],
    analysis: dict[str, Any],
    validation_payload: Any,
    error_payload: Any,
    checkpoints_summary: list[dict[str, Any]] | None,
    fstab_count: int,
    crypttab_count: int,
    net: dict[str, Any],
    failed: list[str],
    critical_failed: list[str],
    vmware_rm: dict[str, Any],
    cloud: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "hyper2kvm.report.v1",
        "run": run_meta,
        "host": host_meta,
        "tools": tool_inv,
        "changes": changes,
        "analysis": analysis,
        "validation": validation_payload,
        "error": error_payload,
        "recovery_checkpoints": checkpoints_summary or None,
        "summary": {
            "image": str(getattr(self, "image", "")),
            "root_dev": getattr(self, "root_dev", None),
            "root_btrfs_subvol": getattr(self, "root_btrfs_subvol", None),
            "dry_run": getattr(self, "dry_run", False),
            "counts": {
                "fstab": fstab_count,
                "crypttab": crypttab_count,
                "network_files": int(net.get("count", 0) or 0) if isinstance(net, dict) else 0,
                "grub_root": int(changes.get("grub_root", 0) or 0),
                "grub_device_map_removed": int(changes.get("grub_device_map_removed", 0) or 0),
            },
            "failed_checks": {"critical": critical_failed, "all": failed},
            "flags": {
                "vmware_tools_removed": bool(vmware_rm.get("removed", False)),
                "cloud_init_injected": bool(cloud.get("injected", False)),
            },
        },
    }


def _md_append_json_block(md: list[str], title: str, payload: Any) -> None:
    md.append(f"## {title}")
    md.append("```json")
    md.append(_dump_json_best_effort(payload))
    md.append("```")
    md.append("")


def _build_markdown(
    self,
    run_meta: dict[str, Any],
    host_meta: dict[str, Any],
    tool_inv: dict[str, Any],
    changes: dict[str, Any],
    analysis: dict[str, Any],
    validation_payload: Any,
    validation_stats: dict[str, Any],
    failed: list[str],
    critical_failed: list[str],
    fstab_count: int,
    crypttab_count: int,
    net: dict[str, Any],
    net_files: list[str],
    sections: dict[str, Any],
    vmware_rm: dict[str, Any],
    cloud: dict[str, Any],
    error_payload: Any,
    checkpoints_summary: list[dict[str, Any]] | None,
) -> str:
    md: list[str] = []
    md.append("# hyper2kvm Report")
    md.append("")

    _md_append_json_block(md, "Run Metadata", run_meta)
    _md_append_json_block(md, "Host Context (best-effort)", host_meta)
    _md_append_json_block(md, "Tool Inventory (host)", tool_inv)

    # Summary
    md.append("## Summary")
    md.append("")
    md.append(f"- Image: `{getattr(self, 'image', '')}`")
    md.append(
        f"- Root: `{getattr(self, 'root_dev', None)}`"
        + (
            f" (btrfs subvol `{getattr(self, 'root_btrfs_subvol', None)}`)"
            if getattr(self, "root_btrfs_subvol", None)
            else ""
        )
    )
    md.append(f"- Dry-run: `{getattr(self, 'dry_run', False)}`")
    md.append(f"- fstab changes: `{fstab_count}`")
    md.append(f"- crypttab changes: `{crypttab_count}`")
    md.append(f"- network files updated: `{int(net.get('count', 0) or 0) if isinstance(net, dict) else 0}`")
    md.append(f"- grub root updated: `{int(changes.get('grub_root', 0) or 0)}`")
    md.append(f"- stale device.map removed: `{int(changes.get('grub_device_map_removed', 0) or 0)}`")
    md.append(f"- vmware tools removed: `{bool(vmware_rm.get('removed', False))}`")
    md.append(f"- cloud-init injected: `{bool(cloud.get('injected', False))}`")
    md.append("")

    # Validation
    if validation_payload is not None:
        md.append("## Validation")
        md.append("")
        if validation_stats:
            md.append("### Validation Stats")
            md.append("```json")
            md.append(_dump_json_best_effort(validation_stats))
            md.append("```")
            md.append("")
        md.append("### Validation Results")
        md.append("```json")
        md.append(_dump_json_best_effort(validation_payload))
        md.append("```")
        md.append("")
        if failed:
            md.append("### Failed Checks")
            md.append("")
            md.append("- Critical failed: " + (", ".join(critical_failed) if critical_failed else "`none`"))
            noncrit = [x for x in failed if x not in critical_failed]
            md.append("- Non-critical failed: " + (", ".join(noncrit) if noncrit else "`none`"))
            md.append("")

    # Changes (raw)
    _md_append_json_block(md, "Changes", changes)

    # fstab table
    fstab_changes = sections.get("fstab_changes", []) or []
    if fstab_changes:
        md.append("### /etc/fstab Rewrites")
        md.append("")
        md.append("| Line | Mount | Old | New | Reason |")
        md.append("|---:|---|---|---|---|")
        for ch in fstab_changes:
            if isinstance(ch, dict):
                line_no = ch.get("line_no") or ch.get("line") or "?"
                mp = ch.get("mountpoint", "") or ""
                old = ch.get("old", "") or ""
                new = ch.get("new", "") or ""
                reason = ch.get("reason", "") or ""
            else:
                line_no = getattr(ch, "line_no", "?")
                mp = getattr(ch, "mountpoint", "") or ""
                old = getattr(ch, "old", "") or ""
                new = getattr(ch, "new", "") or ""
                reason = getattr(ch, "reason", "") or ""
            md.append(f"| {line_no} | `{mp}` | `{old}` | `{new}` | `{reason}` |")
        md.append("")

        audit = (analysis.get("fstab_audit", {}) or {}) if isinstance(analysis, dict) else {}
        if audit:
            md.append("#### fstab Audit")
            md.append("```json")
            md.append(_dump_json_best_effort(audit))
            md.append("```")
            md.append("")

    # crypttab summary
    md.append("### /etc/crypttab")
    md.append(f"- Changes: `{crypttab_count}`")
    md.append("")

    # network summary
    md.append("### Network Config")
    md.append(f"- Updated files: `{len(net_files)}`")
    if net_files:
        md.append("")
        for fp in net_files[:50]:
            md.append(f" - `{fp}`")
        if len(net_files) > 50:
            md.append(f" - … and `{len(net_files) - 50}` more")
        md.append("")

    # Analysis sections (expanded)
    md.append("## Analysis")
    md.append("")
    md.append("### Disk Usage")
    md.append("```json")
    md.append(_dump_json_best_effort(sections.get("disk", {})))
    md.append("```")
    md.append("")
    md.append("### mdraid")
    md.append("```json")
    md.append(_dump_json_best_effort(sections.get("mdraid", {})))
    md.append("```")
    md.append("")
    md.append("### Windows")
    md.append("```json")
    md.append(_dump_json_best_effort(sections.get("windows", {})))
    md.append("```")
    md.append("")
    md.append("### Virtio Injection")
    md.append("```json")
    md.append(_dump_json_best_effort(sections.get("virtio", {})))
    md.append("```")
    md.append("")
    md.append("### Initramfs/GRUB Regeneration")
    md.append("```json")
    md.append(_dump_json_best_effort(sections.get("regen", {})))
    md.append("```")
    md.append("")

    # Cloud-init + VMware tools details
    md.append("### Cloud-init")
    md.append("```json")
    md.append(_dump_json_best_effort(cloud))
    md.append("```")
    md.append("")
    md.append("### VMware Tools Removal")
    md.append("```json")
    md.append(_dump_json_best_effort(vmware_rm))
    md.append("```")
    md.append("")

    # Error
    if error_payload is not None:
        md.append("## Error")
        md.append("```json")
        md.append(_dump_json_best_effort(error_payload))
        md.append("```")
        md.append("")

    # Recovery checkpoints
    if checkpoints_summary:
        md.append("## Recovery Checkpoints")
        md.append("```json")
        md.append(_dump_json_best_effort(checkpoints_summary))
        md.append("```")
        md.append("")

    # Next actions
    md.append("## Next Actions (hints)")
    hints: list[str] = []

    if critical_failed:
        hints.append(f"- Fix CRITICAL validation failures: `{', '.join(critical_failed)}`")

    disk = sections.get("disk", {}) or {}
    if isinstance(disk, dict) and disk.get("analysis") == "success":
        if disk.get("recommend_cleanup"):
            hints.append("- Guest disk is very full; consider cleaning logs/cache or expanding partition+fs.")
        elif disk.get("recommend_resize"):
            hints.append("- Guest disk is getting tight; consider expanding disk or cleaning space.")

    if getattr(self, "update_grub", False) and int(changes.get("grub_root", 0) or 0) == 0 and getattr(self, "root_dev", None):
        hints.append("- GRUB root= may not have been updated (no match found). Verify kernel cmdline in grub.cfg.")

    regen = sections.get("regen", {}) or {}
    if getattr(self, "regen_initramfs", False) and isinstance(regen, dict) and not regen.get("dry_run", False):
        hints.append("- If the guest still fails to boot, run initramfs+grub regen inside the VM once after first boot (or re-run with --regen-initramfs).")

    if vmware_rm.get("removed"):
        hints.append("- If networking is weird after VMware tools removal, verify NIC naming rules (udev/systemd) and regenerate initramfs if needed.")

    if cloud.get("injected"):
        hints.append("- Verify cloud-init datasource + config syntax on first boot (check /var/log/cloud-init*.log).")

    if not hints:
        hints.append("- No obvious follow-ups detected. If it still doesn’t boot, collect console logs + grub.cfg + fstab + initramfs tool output.")

    md.extend(hints)
    md.append("")

    return "\n".join(md) + "\n"


# Public entrypoint

def write_report(self) -> None:
    """
    Entry point method (kept compatible with your current call sites).
    Writes:
      - Markdown report (default) OR .md alongside JSON when report_path endswith .json
      - JSON report (sidecar) always best-effort
    """
    # Ensure report dict exists
    if not getattr(self, "report", None):
        self.report = {"timestamps": {}}

    # End timestamp
    try:
        self.report.setdefault("timestamps", {})
        self.report["timestamps"]["end"] = _dt.datetime.now().isoformat()
    except Exception:
        pass

    base: Path | None = getattr(self, "report_path", None)
    if not base:
        return

    # Resolve paths
    try:
        base_path = Path(base).expanduser().resolve()
    except Exception:
        # If weird path, bail safely
        return

    md_path = _markdown_path_for_base(base_path)
    json_path = _json_sidecar_path(base_path)

    # Extract data
    changes, analysis, validation_payload, error_payload = _extract_changes_analysis(self)
    validation_results, validation_stats = _extract_validation(validation_payload)
    failed, critical_failed = _compute_failed_checks(validation_results)

    run_meta = _build_run_meta(self)
    host_meta = _build_host_meta()
    tool_inv = _build_tool_inventory()

    fstab_count, crypttab_count, net, net_files = _extract_counts(changes)
    sections = _extract_analysis_sections(analysis)
    vmware_rm, cloud = _extract_feature_flags(changes)
    checkpoints_summary = _extract_checkpoints(self)

    # Build JSON payload (superset)
    json_report = _build_json_report(
        self=self,
        run_meta=run_meta,
        host_meta=host_meta,
        tool_inv=tool_inv,
        changes=changes,
        analysis=analysis,
        validation_payload=validation_payload,
        error_payload=error_payload,
        checkpoints_summary=checkpoints_summary or None,
        fstab_count=fstab_count,
        crypttab_count=crypttab_count,
        net=net,
        failed=failed,
        critical_failed=critical_failed,
        vmware_rm=vmware_rm,
        cloud=cloud,
    )

    # Write JSON (best-effort, but try hard)
    try:
        _atomic_write_text(json_path, _dump_json_best_effort(json_report) + "\n")
    except Exception as e:
        try:
            lg = getattr(self, "logger", None)
            if lg:
                lg.debug(f"Report JSON write failed: {json_path}: {e}")
        except Exception:
            pass

    # Write Markdown (skip if user explicitly asked for JSON-only and base is .json? No: we still write .md alongside)
    try:
        md_text = _build_markdown(
            self=self,
            run_meta=run_meta,
            host_meta=host_meta,
            tool_inv=tool_inv,
            changes=changes,
            analysis=analysis,
            validation_payload=validation_payload,
            validation_stats=validation_stats,
            failed=failed,
            critical_failed=critical_failed,
            fstab_count=fstab_count,
            crypttab_count=crypttab_count,
            net=net,
            net_files=net_files,
            sections=sections,
            vmware_rm=vmware_rm,
            cloud=cloud,
            error_payload=error_payload,
            checkpoints_summary=checkpoints_summary or None,
        )
        _atomic_write_text(md_path, md_text)
    except Exception as e:
        try:
            lg = getattr(self, "logger", None)
            if lg:
                lg.debug(f"Report Markdown write failed: {md_path}: {e}")
        except Exception:
            pass

    # Log paths
    try:
        lg = getattr(self, "logger", None)
        if lg:
            lg.info(f"Report written: {md_path}")
            lg.info(f"Report JSON written: {json_path}")
    except Exception:
        pass
