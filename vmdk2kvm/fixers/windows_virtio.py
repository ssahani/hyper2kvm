# SPDX-License-Identifier: LGPL-3.0-or-later
# vmdk2kvm/fixers/windows_virtio.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import guestfs  # type: ignore

from ..config.config_loader import YAML_AVAILABLE, yaml
from ..core.utils import U
from .windows_registry import (
    append_devicepath_software_hive,
    edit_system_hive,
    provision_firstboot_payload_and_service,
    _ensure_windows_root,  # internal helper in same package; ensures correct system volume mounted
)

# Optional ISO extractor
try:
    import pycdlib  # type: ignore
except Exception:  # pragma: no cover
    pycdlib = None


# ---------------------------
# Windows Constants & Enums
# ---------------------------

class DriverType(Enum):
    STORAGE = "storage"
    NETWORK = "network"
    BALLOON = "balloon"
    INPUT = "input"
    GPU = "gpu"
    FILESYSTEM = "filesystem"
    SERIAL = "serial"
    RNG = "rng"


class WindowsRelease(Enum):
    """
    Windows release family (NOT edition like Pro/Home/Enterprise).

    Why: "Edition" is ambiguous terminology in Windows land.
    This enum describes the OS generation / release line.
    """
    SERVER_2022 = "server_2022"
    SERVER_2019 = "server_2019"
    SERVER_2016 = "server_2016"
    SERVER_2012 = "server_2012"
    SERVER_2008 = "server_2008"
    WINDOWS_12 = "windows_12"  # heuristic/future bucket; best-effort only
    WINDOWS_11 = "windows_11"
    WINDOWS_10 = "windows_10"
    WINDOWS_8_1 = "windows_8_1"
    WINDOWS_8 = "windows_8"
    WINDOWS_7 = "windows_7"
    WINDOWS_VISTA = "vista"
    WINDOWS_XP = "xp"
    UNKNOWN = "unknown"


class DriverStartType(Enum):
    BOOT = 0
    SYSTEM = 1
    AUTO = 2
    MANUAL = 3
    DISABLED = 4


# ---------------------------
# Config (drivers + OS->bucket mapping)
# ---------------------------

DEFAULT_VIRTIO_CONFIG: Dict[str, Any] = {
    # Default is Windows 11, not Windows 10.
    "default_release": "windows_11",
    "default_arch_dir": "amd64",

    # Release -> canonical bucket hint
    "release_to_bucket": {
        "windows_12": "w12",
        "windows_11": "w11",
        "windows_10": "w10",
        "windows_8_1": "w8",
        "windows_8": "w8",
        "windows_7": "w7",
        "vista": "vista",
        "xp": "xp",
        "server_2022": "w11",
        "server_2019": "w10",
        "server_2016": "w10",
        "server_2012": "w8",
        "server_2008": "w7",
        "unknown": "w11",
    },

    # Release -> bucket candidates (fallback order)
    "bucket_candidates": {
        "windows_12": ["w12", "w11", "w10", "w8", "w7"],
        "windows_11": ["w11", "w10", "w8", "w7"],
        "windows_10": ["w10", "w11", "w8", "w7"],
        "windows_8_1": ["w8", "w10", "w7"],
        "windows_8": ["w8", "w10", "w7"],
        "windows_7": ["w7", "w8", "w10"],
        "vista": ["vista", "w7", "w8"],
        "xp": ["xp", "w7"],
        "server_2022": ["w11", "w10", "w8", "w7"],
        "server_2019": ["w10", "w11", "w8", "w7"],
        "server_2016": ["w10", "w11", "w8", "w7"],
        "server_2012": ["w8", "w10", "w7"],
        "server_2008": ["w7", "w8", "w10"],
        "unknown": ["w11", "w10", "w8", "w7"],
    },

    # Driver definitions live in config (extensible per vendor / custom PNP IDs).
    "drivers": {
        "storage": [
            {
                "name": "viostor",
                "pattern": "viostor/{bucket}/{arch}/viostor.sys",
                "inf_hint": "viostor.inf",
                "service": "viostor",
                "start": 0,  # BOOT
                "class_guid": "{4D36E967-E325-11CE-BFC1-08002BE10318}",  # SCSIAdapter
                "pci_ids": [
                    "pci#ven_1af4&dev_1001&subsys_00081af4",
                    "pci#ven_1af4&dev_1042&subsys_00081af4",
                ],
            },
            {
                "name": "vioscsi",
                "pattern": "vioscsi/{bucket}/{arch}/vioscsi.sys",
                "inf_hint": "vioscsi.inf",
                "service": "vioscsi",
                "start": 0,  # BOOT
                "class_guid": "{4D36E967-E325-11CE-BFC1-08002BE10318}",  # SCSIAdapter
                "pci_ids": [
                    "pci#ven_1af4&dev_1004&subsys_00081af4",
                    "pci#ven_1af4&dev_1048&subsys_00081af4",
                ],
            },
        ],
        "network": [
            {
                "name": "NetKVM",
                "pattern": "NetKVM/{bucket}/{arch}/netkvm.sys",
                "inf_hint": "netkvm.inf",
                "service": "netkvm",
                "start": 2,  # AUTO
                "class_guid": "{4D36E972-E325-11CE-BFC1-08002BE10318}",  # Net
                "pci_ids": [
                    "pci#ven_1af4&dev_1000&subsys_00081af4",
                    "pci#ven_1af4&dev_1041&subsys_00081af4",
                ],
            },
        ],
        "balloon": [
            {
                "name": "Balloon",
                "pattern": "Balloon/{bucket}/{arch}/balloon.sys",
                "inf_hint": "balloon.inf",
                "service": "balloon",
                "start": 2,  # AUTO
                "class_guid": "{4D36E97D-E325-11CE-BFC1-08002BE10318}",  # System
                "pci_ids": [
                    "pci#ven_1af4&dev_1002&subsys_00051af4",
                    "pci#ven_1af4&dev_1045&subsys_00051af4",
                ],
            },
        ],
        "gpu": [
            {
                "name": "viogpudo",
                "pattern": "viogpudo/{bucket}/{arch}/viogpudo.sys",
                "inf_hint": "viogpudo.inf",
                "service": "viogpudo",
                "start": 3,  # MANUAL
                "class_guid": "{4D36E968-E325-11CE-BFC1-08002BE10318}",  # Display
                "pci_ids": ["pci#ven_1af4&dev_1050&subsys_11001af4"],
            },
        ],
        "input": [
            {
                "name": "vioinput",
                "pattern": "vioinput/{bucket}/{arch}/vioinput.sys",
                "inf_hint": "vioinput.inf",
                "service": "vioinput",
                "start": 3,  # MANUAL
                "class_guid": "{4D36E96F-E325-11CE-BFC1-08002BE10318}",  # Mouse
                "pci_ids": ["pci#ven_1af4&dev_1052&subsys_11001af4"],
            },
        ],
        "filesystem": [
            {
                "name": "virtiofs",
                "pattern": "virtiofs/{bucket}/{arch}/virtiofs.sys",
                "inf_hint": "virtiofs.inf",
                "service": "virtiofs",
                "start": 1,  # SYSTEM
                "class_guid": "{4D36E967-E325-11CE-BFC1-08002BE10318}",  # Storage-ish
                "pci_ids": ["pci#ven_1af4&dev_105a&subsys_11001af4"],
            },
        ],
        "serial": [
            {
                "name": "vioser",
                "pattern": "vioser/{bucket}/{arch}/vioser.sys",
                "inf_hint": "vioser.inf",
                "service": "vioser",
                "start": 3,  # MANUAL
                "class_guid": "{4D36E978-E325-11CE-BFC1-08002BE10318}",  # Ports
                "pci_ids": [
                    "pci#ven_1af4&dev_1003&subsys_00031af4",
                    "pci#ven_1af4&dev_1043&subsys_00031af4",
                ],
            },
        ],
        "rng": [
            {
                "name": "viorng",
                "pattern": "viorng/{bucket}/{arch}/viorng.sys",
                "inf_hint": "viorng.inf",
                "service": "viorng",
                "start": 2,  # AUTO
                "class_guid": "{4D36E97D-E325-11CE-BFC1-08002BE10318}",  # System
                "pci_ids": [
                    "pci#ven_1af4&dev_1005&subsys_00041af4",
                    "pci#ven_1af4&dev_1044&subsys_00041af4",
                ],
            },
        ],
    },
}


# ---------------------------
# Logging helpers (emoji + steps)
# ---------------------------

def _safe_logger(self) -> logging.Logger:
    lg = getattr(self, "logger", None)
    if isinstance(lg, logging.Logger):
        return lg
    return logging.getLogger("vmdk2kvm.windows_virtio")


def _emoji(level: int) -> str:
    if level >= logging.ERROR:
        return "❌"
    if level >= logging.WARNING:
        return "⚠️"
    if level >= logging.INFO:
        return "✅"
    return "🔍"


def _log(logger: logging.Logger, level: int, msg: str, *args: Any) -> None:
    logger.log(level, f"{_emoji(level)} {msg}", *args)


@contextmanager
def _step(logger: logging.Logger, title: str):
    t0 = time.time()
    _log(logger, logging.INFO, "%s ...", title)
    try:
        yield
        _log(logger, logging.INFO, "%s done (%.2fs)", title, time.time() - t0)
    except Exception as e:
        _log(logger, logging.ERROR, "%s failed (%.2fs): %s", title, time.time() - t0, e)
        raise


# ---------------------------
# Misc helpers
# ---------------------------

def _to_int(v: Any, default: int = 0) -> int:
    if isinstance(v, int):
        return v
    try:
        return int(float(v)) if isinstance(v, (float, str)) else default
    except Exception:
        return default


def _normalize_product_name(name: str) -> str:
    if not name:
        return ""
    s = name.lower()
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _guest_download_bytes(g: guestfs.GuestFS, guest_path: str, max_bytes: Optional[int] = None) -> bytes:
    with tempfile.TemporaryDirectory() as td:
        lp = Path(td) / "dl"
        g.download(guest_path, str(lp))
        b = lp.read_bytes()
        return b[:max_bytes] if max_bytes is not None else b


def _guest_sha256(g: guestfs.GuestFS, guest_path: str) -> Optional[str]:
    try:
        return hashlib.sha256(_guest_download_bytes(g, guest_path)).hexdigest()
    except Exception:
        return None


def _sha256_path(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _log_mountpoints_best_effort(logger: logging.Logger, g: guestfs.GuestFS) -> None:
    try:
        mps = g.mountpoints()
        _log(logger, logging.DEBUG, "guestfs mountpoints=%r", mps)
    except Exception:
        pass


def _guest_mkdir_p(g: guestfs.GuestFS, path: str, *, dry_run: bool) -> None:
    if dry_run:
        return
    try:
        if not g.is_dir(path):
            g.mkdir_p(path)
    except Exception:
        g.mkdir_p(path)


def _guest_write_text(g: guestfs.GuestFS, path: str, content: str, *, dry_run: bool) -> None:
    if dry_run:
        return
    g.write(path, content.encode("utf-8", errors="ignore"))


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge dicts:
      - dict values merge recursively
      - lists are replaced (override wins)
      - scalars replaced
    """
    out: Dict[str, Any] = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def _parse_start_type(v: Any) -> int:
    if isinstance(v, int):
        return v if 0 <= v <= 4 else DriverStartType.AUTO.value
    if isinstance(v, str):
        s = v.strip()
        if re.fullmatch(r"\d+", s):
            n = int(s)
            return n if 0 <= n <= 4 else DriverStartType.AUTO.value
        s2 = s.upper()
        try:
            return DriverStartType[s2].value
        except Exception:
            return DriverStartType.AUTO.value
    return DriverStartType.AUTO.value


def _validate_virtio_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize + validate config.

    - Ensures drivers are lists of dicts with required keys
    - Normalizes pci_ids to lowercase strings
    - Normalizes start to int (0..4) or enum-name
    - Keeps class_guid/inf_hint as strings (inf_hint may be None)

    Lists are NOT merged; if user overrides drivers.storage, they replace that list.
    """
    d = cfg.get("drivers")
    if isinstance(d, dict):
        for dtype, defs in list(d.items()):
            if not isinstance(defs, list):
                d.pop(dtype, None)
                continue

            cleaned: List[Dict[str, Any]] = []
            for item in defs:
                if not isinstance(item, dict):
                    continue

                name = str(item.get("name") or "").strip()
                pattern = str(item.get("pattern") or "").strip()
                service = str(item.get("service") or "").strip()
                if not (name and pattern and service):
                    continue

                pci_ids = item.get("pci_ids") or []
                if not isinstance(pci_ids, list):
                    pci_ids = []
                pci_ids = [str(x).strip().lower() for x in pci_ids if str(x).strip()]

                start_val = _parse_start_type(item.get("start", DriverStartType.AUTO.value))

                cleaned.append(
                    {
                        **item,
                        "name": name,
                        "pattern": pattern,
                        "service": service,
                        "pci_ids": pci_ids,
                        "start": start_val,
                        "class_guid": str(item.get("class_guid") or "").strip(),
                        "inf_hint": (str(item.get("inf_hint") or "").strip() or None),
                    }
                )

            d[dtype] = cleaned

    return cfg


def _read_structured_file(path: Path) -> Dict[str, Any]:
    """
    Read a JSON/YAML file into a dict.

    Supported:
      - *.json
      - *.yml / *.yaml  (requires YAML_AVAILABLE)
    """
    sfx = path.suffix.lower()
    raw = path.read_text(encoding="utf-8", errors="replace")
    if sfx == ".json":
        parsed = json.loads(raw)
    elif sfx in (".yml", ".yaml"):
        if not YAML_AVAILABLE:
            raise RuntimeError("YAML support not available (PyYAML not installed). Use JSON instead.")
        parsed = yaml.safe_load(raw)  # type: ignore[attr-defined]
    else:
        # Try JSON first, then YAML if available (nice UX for no-suffix files)
        try:
            parsed = json.loads(raw)
        except Exception:
            if not YAML_AVAILABLE:
                raise
            parsed = yaml.safe_load(raw)  # type: ignore[attr-defined]
    if not isinstance(parsed, dict):
        raise ValueError("top-level config must be a mapping/object (dict)")
    return parsed


def _extract_virtio_cfg_from_global_config(global_cfg: Any) -> Optional[Dict[str, Any]]:
    """
    Accept VirtIO config from the *merged app config* if present.

    We support several keys so you can evolve without breaking users:
      - windows_virtio:
      - virtio_windows:
      - virtio:
      - fixers: { windows_virtio: { ... } }
    """
    if not isinstance(global_cfg, dict) or not global_cfg:
        return None

    for k in ("windows_virtio", "virtio_windows", "virtio"):
        v = global_cfg.get(k)
        if isinstance(v, dict) and v:
            return v

    fx = global_cfg.get("fixers")
    if isinstance(fx, dict):
        v = fx.get("windows_virtio")
        if isinstance(v, dict) and v:
            return v

    return None


def _load_virtio_config(self) -> Dict[str, Any]:
    """
    Load VirtIO config (drivers + OS bucket logic) from **any** of:

    1) self.virtio_config (dict)                     [highest priority]
    2) self.virtio_config_inline_json (str JSON)     (or self.virtio_config_json for compat)
    3) self.virtio_config_path (Path|str)            JSON/YAML file
    4) self.config (merged YAML app config dict)     keys: windows_virtio/virtio/fixers.windows_virtio
    5) baked DEFAULT_VIRTIO_CONFIG

    Merge semantics:
      - dicts deep-merge
      - lists replaced (so overriding drivers.storage replaces storage list only)
    """
    logger = _safe_logger(self)

    cfg: Dict[str, Any] = dict(DEFAULT_VIRTIO_CONFIG)

    # 1) explicit dict on object
    cfg_obj = getattr(self, "virtio_config", None)
    if isinstance(cfg_obj, dict) and cfg_obj:
        cfg = _deep_merge_dict(cfg, cfg_obj)
        cfg = _validate_virtio_config(cfg)
        _log(logger, logging.INFO, "Loaded VirtIO config from self.virtio_config (dict)")
        return cfg

    # 2) inline JSON string on object (CLI/YAML can map into this)
    inline = getattr(self, "virtio_config_inline_json", None)
    if not inline:
        inline = getattr(self, "virtio_config_json", None)
    if isinstance(inline, str) and inline.strip():
        try:
            parsed = json.loads(inline)
            if isinstance(parsed, dict):
                cfg = _deep_merge_dict(cfg, parsed)
                cfg = _validate_virtio_config(cfg)
                _log(logger, logging.INFO, "Loaded VirtIO config from inline JSON (self.virtio_config_inline_json)")
                return cfg
        except Exception as e:
            _log(logger, logging.WARNING, "Inline VirtIO config JSON parse failed: %s", e)

    # 3) path to file (JSON/YAML)
    p = getattr(self, "virtio_config_path", None)
    if p:
        try:
            fp = Path(str(p))
            if fp.exists() and fp.is_file():
                parsed = _read_structured_file(fp)
                cfg = _deep_merge_dict(cfg, parsed)
                cfg = _validate_virtio_config(cfg)
                _log(logger, logging.INFO, "Loaded VirtIO config from file: %s", fp)
                return cfg
        except Exception as e:
            _log(logger, logging.WARNING, "VirtIO config load failed (%s): %s", p, e)

    # 4) merged global app config (YAML)
    global_cfg = getattr(self, "config", None)
    vcfg = _extract_virtio_cfg_from_global_config(global_cfg)
    if isinstance(vcfg, dict) and vcfg:
        cfg = _deep_merge_dict(cfg, vcfg)
        cfg = _validate_virtio_config(cfg)
        _log(logger, logging.INFO, "Loaded VirtIO config from self.config (merged YAML)")
        return cfg

    # 5) baked defaults
    cfg = _validate_virtio_config(cfg)
    return cfg


# ---------------------------
# Plan + Driver model
# ---------------------------

@dataclass(frozen=True)
class WindowsVirtioPlan:
    arch_dir: str
    bucket_hint: str
    release: WindowsRelease
    drivers_needed: Set[DriverType]

    @classmethod
    def default_needed(cls) -> Set[DriverType]:
        return {DriverType.STORAGE, DriverType.NETWORK, DriverType.BALLOON}


@dataclass
class DriverFile:
    name: str
    type: DriverType
    src_path: Path
    dest_name: str

    start_type: DriverStartType
    service_name: str

    pci_ids: List[str]
    class_guid: str

    package_dir: Optional[Path] = None
    inf_path: Optional[Path] = None

    bucket_used: Optional[str] = None
    match_pattern: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "src_path": str(self.src_path),
            "dest_name": self.dest_name,
            "start_type": self.start_type.value,
            "service_name": self.service_name,
            "pci_ids": list(self.pci_ids),
            "class_guid": self.class_guid,
            "package_dir": str(self.package_dir) if self.package_dir else None,
            "inf_path": str(self.inf_path) if self.inf_path else None,
            "bucket_used": self.bucket_used,
            "match_pattern": self.match_pattern,
        }


def _plan_to_dict(plan: WindowsVirtioPlan) -> Dict[str, Any]:
    return {
        "arch_dir": plan.arch_dir,
        "bucket_hint": plan.bucket_hint,
        "release": plan.release.value,
        "drivers_needed": sorted([d.value for d in plan.drivers_needed]),
    }


# ---------------------------
# Windows path model (WindowsRoot + System32 + drivers + hives)
# ---------------------------

@dataclass(frozen=True)
class WindowsSystemPaths:
    # GuestFS paths (mounted filesystem paths, NOT Windows-style C:\ paths)
    windows_dir: str            # e.g. "/Windows" or "/WINNT"
    system32_dir: str           # e.g. "/Windows/System32"
    drivers_dir: str            # e.g. "/Windows/System32/drivers"
    config_dir: str             # e.g. "/Windows/System32/config"
    temp_dir: str               # e.g. "/Windows/Temp"

    system_hive: str            # e.g. "/Windows/System32/config/SYSTEM"
    software_hive: str          # e.g. "/Windows/System32/config/SOFTWARE"


def _find_windows_root(self, g: guestfs.GuestFS) -> Optional[str]:
    logger = _safe_logger(self)
    for p in ["/Windows", "/WINDOWS", "/winnt", "/WINNT"]:
        try:
            if g.is_dir(p):
                _log(logger, logging.DEBUG, "Windows root: found %s", p)
                return p
        except Exception:
            continue
    _log(logger, logging.DEBUG, "Windows root: no direct hit")
    return None


def _resolve_windows_system_paths(self, g: guestfs.GuestFS) -> WindowsSystemPaths:
    """
    Resolve Windows directory + System32 + drivers/config/temp locations.

    IMPORTANT:
      - Assumes REAL Windows system volume (C:) is mounted at '/' already.
      - Call _ensure_windows_root(...) first to avoid "wrong partition" surprises.
    """
    logger = _safe_logger(self)

    win_dir = _find_windows_root(self, g) or "/Windows"
    if not g.is_dir(win_dir):
        _log(logger, logging.WARNING, "Windows dir not found at %s; defaulting to /Windows", win_dir)
        win_dir = "/Windows"

    system32 = f"{win_dir}/System32"
    try:
        if not g.is_dir(system32):
            alt = f"{win_dir}/system32"
            if g.is_dir(alt):
                system32 = alt
    except Exception:
        pass

    drivers = f"{system32}/drivers"
    config = f"{system32}/config"
    temp = f"{win_dir}/Temp"

    return WindowsSystemPaths(
        windows_dir=win_dir,
        system32_dir=system32,
        drivers_dir=drivers,
        config_dir=config,
        temp_dir=temp,
        system_hive=f"{config}/SYSTEM",
        software_hive=f"{config}/SOFTWARE",
    )


def _guestfs_to_windows_path(p: str) -> str:
    """
    Best-effort conversion for logs/UI: guestfs path under /Windows -> C:\\Windows\\...
    If Windows dir is /WINNT, it still maps to C:\\WINNT\\...
    """
    if not p:
        return p
    s = p.replace("/", "\\")
    if s.startswith("\\"):
        s = s[1:]
    return f"C:\\{s}"


# ---------------------------
# VirtIO source materialization (dir OR ISO)
# ---------------------------

@contextmanager
def _materialize_virtio_source(self, virtio_path: Path):
    logger = _safe_logger(self)

    if virtio_path.is_dir():
        yield virtio_path
        return

    if virtio_path.suffix.lower() != ".iso":
        raise RuntimeError(f"virtio_drivers_dir must be a directory or .iso, got: {virtio_path}")

    if pycdlib is None:
        raise RuntimeError(
            "virtio_drivers_dir is an ISO but pycdlib is not installed. "
            "Install pycdlib or provide an extracted virtio-win directory."
        )

    td = Path(tempfile.mkdtemp(prefix="vmdk2kvm-virtio-iso-"))
    extracted = 0
    tried: List[str] = []
    try:
        _log(logger, logging.INFO, "📀 Extracting VirtIO ISO -> %s", td)
        iso = pycdlib.PyCdlib()
        iso.open(str(virtio_path))

        def _children(iso_dir: str, use_joliet: bool):
            if use_joliet:
                return iso.list_children(joliet_path=iso_dir)
            return iso.list_children(iso_path=iso_dir)

        def _walk(iso_dir: str, use_joliet: bool):
            try:
                kids = _children(iso_dir, use_joliet)
            except Exception:
                return
            for c in kids:
                try:
                    name = c.file_identifier().decode("utf-8", errors="ignore").rstrip(";1")
                except Exception:
                    continue
                if name in (".", "..") or not name:
                    continue
                child = iso_dir.rstrip("/") + "/" + name
                try:
                    if c.is_dir():
                        yield from _walk(child, use_joliet)
                    else:
                        yield child
                except Exception:
                    continue

        for use_joliet in (False, True):
            mode = "joliet" if use_joliet else "iso9660"
            tried.append(mode)
            for iso_file in _walk("/", use_joliet):
                rel = iso_file.lstrip("/").rstrip(";1")
                out = td / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                try:
                    if use_joliet:
                        iso.get_file_from_iso(str(out), joliet_path=iso_file)
                    else:
                        iso.get_file_from_iso(str(out), iso_path=iso_file)
                    extracted += 1
                except Exception as e:
                    _log(logger, logging.DEBUG, "ISO extract failed for %s (%s): %s", iso_file, mode, e)

        try:
            iso.close()
        except Exception:
            pass

        _log(logger, logging.INFO, "📀 ISO extraction complete: %d files (modes tried=%s)", extracted, tried)
        yield td
    finally:
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass


# ---------------------------
# Windows detection + version/build
# ---------------------------

def is_windows(self, g: guestfs.GuestFS) -> bool:
    logger = _safe_logger(self)
    if not getattr(self, "inspect_root", None):
        _log(logger, logging.DEBUG, "Windows detect: inspect_root missing -> not Windows")
        return False

    root = self.inspect_root

    try:
        try:
            os_type = U.to_text(g.inspect_get_type(root))
            if os_type and os_type.lower() == "windows":
                _log(logger, logging.DEBUG, "Windows detect: inspect_get_type says windows")
                return True
        except Exception:
            pass

        for dir_path in ["/Windows", "/WINDOWS", "/winnt", "/WINNT", "/Program Files"]:
            try:
                if g.is_dir(dir_path):
                    _log(logger, logging.DEBUG, "Windows detect: found dir %s", dir_path)
                    return True
            except Exception:
                continue

        for reg_file in [
            "/Windows/System32/config/SOFTWARE",
            "/WINDOWS/System32/config/SOFTWARE",
            "/winnt/system32/config/SOFTWARE",
        ]:
            try:
                if g.is_file(reg_file):
                    _log(logger, logging.DEBUG, "Windows detect: found SOFTWARE hive %s", reg_file)
                    return True
            except Exception:
                continue

        _log(logger, logging.DEBUG, "Windows detect: no signals -> not Windows")
        return False

    except Exception as e:
        _log(logger, logging.DEBUG, "Windows detect: exception -> not Windows: %s", e)
        return False


def _hivex_call_known(g: guestfs.GuestFS, fn_name: str, args: Tuple[Any, ...], *, allow_drop_handle: bool, allow_noargs: bool) -> Any:
    """
    Call guestfs hivex_* function with binding compatibility.

    Rules:
      - Always try the provided args first.
      - If TypeError and allow_drop_handle is True and first arg looks like a handle,
        retry without the first arg.
      - If still TypeError and allow_noargs is True, retry with no args.
      - Otherwise raise the last TypeError without calling again.
    """
    fn = getattr(g, fn_name, None)
    if fn is None:
        raise AttributeError(fn_name)

    last_te: Optional[TypeError] = None

    try:
        return fn(*args)
    except TypeError as te:
        last_te = te

    if allow_drop_handle and args and isinstance(args[0], int):
        try:
            return fn(*args[1:])
        except TypeError as te:
            last_te = te

    if allow_noargs:
        try:
            return fn()
        except TypeError as te:
            last_te = te

    assert last_te is not None
    raise last_te


def _read_windows_build_from_software_hive(self, g: guestfs.GuestFS, software_hive_path: str) -> Optional[int]:
    """
    Read Windows build number from SOFTWARE hive:
      HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\CurrentBuildNumber (or CurrentBuild)

    Uses guestfs hivex API (no extra deps). Handle-vs-global-hive differences are normalized.
    """
    logger = _safe_logger(self)

    try:
        if not g.is_file(software_hive_path):
            return None
    except Exception:
        return None

    h: Optional[int] = None
    try:
        try:
            h = _hivex_call_known(g, "hivex_open", (software_hive_path, 0), allow_drop_handle=False, allow_noargs=False)
        except TypeError:
            h = _hivex_call_known(g, "hivex_open", (software_hive_path,), allow_drop_handle=False, allow_noargs=False)

        root = _hivex_call_known(g, "hivex_root", (h,), allow_drop_handle=True, allow_noargs=True)

        node = _hivex_call_known(g, "hivex_node_get_child", (h, root, "Microsoft"), allow_drop_handle=True, allow_noargs=False)
        if not node:
            return None
        node = _hivex_call_known(g, "hivex_node_get_child", (h, node, "Windows NT"), allow_drop_handle=True, allow_noargs=False)
        if not node:
            return None
        node = _hivex_call_known(g, "hivex_node_get_child", (h, node, "CurrentVersion"), allow_drop_handle=True, allow_noargs=False)
        if not node:
            return None

        def _val(name: str) -> Optional[str]:
            try:
                v = _hivex_call_known(g, "hivex_node_get_value", (h, node, name), allow_drop_handle=True, allow_noargs=False)
                if not v:
                    return None
                raw = _hivex_call_known(g, "hivex_value_string", (h, v), allow_drop_handle=True, allow_noargs=False)
                s = U.to_text(raw)
                return s.strip() if s else None
            except Exception:
                return None

        for key in ("CurrentBuildNumber", "CurrentBuild"):
            s = _val(key)
            if not s:
                continue
            m = re.search(r"(\d{4,6})", s)
            if m:
                return int(m.group(1))
        return None

    except Exception as e:
        _log(logger, logging.DEBUG, "hivex build read failed: %s", e)
        return None
    finally:
        try:
            if h is not None:
                _hivex_call_known(g, "hivex_close", (h,), allow_drop_handle=True, allow_noargs=True)
            else:
                _hivex_call_known(g, "hivex_close", tuple(), allow_drop_handle=False, allow_noargs=True)
        except Exception:
            pass


def _windows_version_info(self, g: guestfs.GuestFS, paths: Optional["WindowsSystemPaths"] = None) -> Dict[str, Any]:
    logger = _safe_logger(self)
    info: Dict[str, Any] = {
        "windows": True,
        "bits": 64,
        "build": None,
        "product_name": None,
        "arch": None,
        "major": None,
        "minor": None,
        "distro": None,
    }

    root = getattr(self, "inspect_root", None)
    if root:
        try:
            info["arch"] = U.to_text(g.inspect_get_arch(root))
            info["major"] = g.inspect_get_major_version(root)
            info["minor"] = g.inspect_get_minor_version(root)
            info["product_name"] = U.to_text(g.inspect_get_product_name(root))
            info["distro"] = U.to_text(g.inspect_get_distro(root))
        except Exception as e:
            _log(logger, logging.DEBUG, "Windows info: inspect getters failed: %s", e)

    arch = (info.get("arch") or "").lower()
    if arch in ("x86_64", "amd64", "arm64", "aarch64"):
        info["bits"] = 64
    elif arch in ("i386", "i686", "x86"):
        info["bits"] = 32
    else:
        info["bits"] = 64

    try:
        if paths is None:
            paths = _resolve_windows_system_paths(self, g)
        build = _read_windows_build_from_software_hive(self, g, paths.software_hive)
        if build:
            info["build"] = build
    except Exception as e:
        _log(logger, logging.DEBUG, "Windows info: build read failed: %s", e)

    return info


def _detect_windows_release(self, win_info: Dict[str, Any], cfg: Dict[str, Any]) -> WindowsRelease:
    """
    Detect Windows release family.

    Priority:
      1) product_name hints (best signal)
      2) build number for Win10/Win11 split (>=22000 => Win11+)
      3) major/minor only for older OSes (<=8.1 era)
      4) config default (Windows 11)

    NOTE: Any "Windows 12" mapping is best-effort heuristic only.
    """
    product = _normalize_product_name(str(win_info.get("product_name", "") or ""))
    build = _to_int(win_info.get("build"), default=0)
    major = _to_int(win_info.get("major"), default=0)
    minor = _to_int(win_info.get("minor"), default=0)

    if "server 2022" in product:
        return WindowsRelease.SERVER_2022
    if "server 2019" in product:
        return WindowsRelease.SERVER_2019
    if "server 2016" in product:
        return WindowsRelease.SERVER_2016
    if "server 2012" in product:
        return WindowsRelease.SERVER_2012
    if "server 2008" in product:
        return WindowsRelease.SERVER_2008

    if "windows 12" in product:
        return WindowsRelease.WINDOWS_12
    if "windows 11" in product:
        return WindowsRelease.WINDOWS_11
    if "windows 10" in product:
        return WindowsRelease.WINDOWS_11 if build >= 22000 else WindowsRelease.WINDOWS_10
    if "windows 8.1" in product:
        return WindowsRelease.WINDOWS_8_1
    if "windows 8" in product:
        return WindowsRelease.WINDOWS_8
    if "windows 7" in product:
        return WindowsRelease.WINDOWS_7
    if "vista" in product:
        return WindowsRelease.WINDOWS_VISTA
    if "xp" in product:
        return WindowsRelease.WINDOWS_XP

    if build:
        if build >= 26000:
            return WindowsRelease.WINDOWS_12
        if build >= 22000:
            return WindowsRelease.WINDOWS_11
        if build >= 10240:
            return WindowsRelease.WINDOWS_10

    if major == 6 and minor == 3:
        return WindowsRelease.WINDOWS_8_1
    if major == 6 and minor == 2:
        return WindowsRelease.WINDOWS_8
    if major == 6 and minor == 1:
        return WindowsRelease.WINDOWS_7
    if major == 6 and minor == 0:
        return WindowsRelease.WINDOWS_VISTA
    if major == 5:
        return WindowsRelease.WINDOWS_XP

    d = str(cfg.get("default_release", "windows_11")).strip().lower()
    try:
        return WindowsRelease(d)
    except Exception:
        return WindowsRelease.WINDOWS_11


def _norm_arch_to_dir(arch: str, cfg: Dict[str, Any]) -> str:
    a = (arch or "").lower().strip()
    mapping = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "x64": "amd64",
        "i386": "x86",
        "i686": "x86",
        "x86": "x86",
        "ia64": "ia64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    return mapping.get(a, str(cfg.get("default_arch_dir", "amd64")))


def _bucket_candidates(release: WindowsRelease, cfg: Dict[str, Any]) -> List[str]:
    m = cfg.get("bucket_candidates") or {}
    if isinstance(m, dict):
        c = m.get(release.value)
        if isinstance(c, list) and c:
            return [str(x) for x in c]
    return ["w11", "w10", "w8", "w7"]


def _bucket_hint(release: WindowsRelease, cfg: Dict[str, Any]) -> str:
    m = cfg.get("release_to_bucket") or {}
    if isinstance(m, dict):
        v = m.get(release.value)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "w11"


def _choose_driver_plan(self, win_info: Dict[str, Any], cfg: Dict[str, Any]) -> WindowsVirtioPlan:
    logger = _safe_logger(self)

    release = _detect_windows_release(self, win_info, cfg)
    arch_dir = _norm_arch_to_dir(str(win_info.get("arch") or ""), cfg)
    hint = _bucket_hint(release, cfg)
    drivers_needed = WindowsVirtioPlan.default_needed()

    if getattr(self, "enable_virtio_gpu", False):
        drivers_needed.add(DriverType.GPU)
    if getattr(self, "enable_virtio_input", False):
        drivers_needed.add(DriverType.INPUT)
    if getattr(self, "enable_virtio_fs", False):
        drivers_needed.add(DriverType.FILESYSTEM)
    if getattr(self, "enable_virtio_serial", False):
        drivers_needed.add(DriverType.SERIAL)
    if getattr(self, "enable_virtio_rng", False):
        drivers_needed.add(DriverType.RNG)

    plan = WindowsVirtioPlan(
        arch_dir=arch_dir,
        bucket_hint=hint,
        release=release,
        drivers_needed=drivers_needed,
    )

    _log(
        logger,
        logging.INFO,
        "🧩 Windows plan: release=%s arch=%s bucket_hint=%s candidates=%s drivers=%s",
        plan.release.value,
        plan.arch_dir,
        plan.bucket_hint,
        _bucket_candidates(plan.release, cfg),
        sorted([d.value for d in plan.drivers_needed]),
    )
    return plan


# ---------------------------
# Driver discovery + staging (config-driven)
# ---------------------------

def _is_probably_driver_payload(p: Path) -> bool:
    ext = p.suffix.lower()
    return ext in (".inf", ".cat", ".sys", ".dll", ".mui")


def _get_driver_definitions(cfg: Dict[str, Any], dt: DriverType) -> List[Dict[str, Any]]:
    d = cfg.get("drivers") or {}
    if not isinstance(d, dict):
        return []
    arr = d.get(dt.value)
    if not isinstance(arr, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in arr:
        if isinstance(item, dict) and item.get("name") and item.get("pattern") and item.get("service"):
            out.append(item)
    return out


def _warn_if_driver_defs_suspicious(self, cfg: Dict[str, Any]) -> None:
    """
    Emit warnings for malformed driver definitions that will likely break registry binding.
    Especially important for storage drivers.
    """
    logger = _safe_logger(self)
    for dt in DriverType:
        defs = _get_driver_definitions(cfg, dt)
        for dfn in defs:
            name = str(dfn.get("name") or "")
            service = str(dfn.get("service") or "")
            class_guid = str(dfn.get("class_guid") or "")
            pci_ids = dfn.get("pci_ids") or []
            if dt == DriverType.STORAGE:
                if not class_guid:
                    _log(logger, logging.WARNING, "Config: storage driver %s/%s missing class_guid (SYSTEM hive edits may be incomplete)", name, service)
                if not pci_ids:
                    _log(logger, logging.WARNING, "Config: storage driver %s/%s missing pci_ids (CDD population will be incomplete)", name, service)
            else:
                if not class_guid:
                    _log(logger, logging.DEBUG, "Config: driver %s/%s missing class_guid", name, service)


def _pick_best_match(paths: List[Path]) -> Path:
    """
    Pick best candidate among multiple matches:
      1) shortest path (usually most specific / canonical)
      2) newest mtime
      3) lexical tie-break
    """
    def _key(p: Path) -> Tuple[int, float, str]:
        try:
            mt = p.stat().st_mtime
        except Exception:
            mt = 0.0
        return (len(str(p)), -mt, str(p))
    return sorted(paths, key=_key)[0]


def _discover_virtio_drivers(self, virtio_src: Path, plan: WindowsVirtioPlan, cfg: Dict[str, Any]) -> List["DriverFile"]:
    logger = _safe_logger(self)
    drivers: List[DriverFile] = []
    buckets = _bucket_candidates(plan.release, cfg)

    search_patterns = [
        "{pattern}",
        "{driver}/{bucket}/{arch}/*.sys",
        "{driver}/{arch}/*.sys",
        "{driver}/*/{arch}/*.sys",
        "{driver}/*/*/{arch}/*.sys",
    ]

    def _glob_all(base: Path, pat: str) -> List[Path]:
        try:
            return sorted([p for p in base.glob(pat) if p.is_file()])
        except Exception:
            return []

    def _find_inf_near_sys(sys_path: Path, inf_hint: Optional[str]) -> Optional[Path]:
        pkg = sys_path.parent
        try:
            if inf_hint:
                cand = pkg / inf_hint
                if cand.exists() and cand.is_file():
                    return cand
            infs = sorted([p for p in pkg.glob("*.inf") if p.is_file()])
            return infs[0] if infs else None
        except Exception:
            return None

    _log(logger, logging.INFO, "🔎 Discovering VirtIO drivers ...")
    _log(logger, logging.INFO, "VirtIO source: %s", virtio_src)
    _log(logger, logging.INFO, "Bucket candidates: %s", buckets)

    with _materialize_virtio_source(self, virtio_src) as base:
        _log(logger, logging.INFO, "VirtIO materialized dir: %s", base)

        for driver_type in sorted(plan.drivers_needed, key=lambda d: d.value):
            defs = _get_driver_definitions(cfg, driver_type)
            if not defs:
                continue

            for dfn in defs:
                driver_name = str(dfn.get("name") or "")
                service = str(dfn.get("service") or "")
                pattern_tmpl = str(dfn.get("pattern") or "")
                inf_hint = dfn.get("inf_hint") or None
                class_guid = str(dfn.get("class_guid") or "")
                pci_ids = [str(x).lower() for x in (dfn.get("pci_ids") or []) if str(x).strip()]

                start_val = _parse_start_type(dfn.get("start", DriverStartType.AUTO.value))
                try:
                    start_enum = DriverStartType(start_val)
                except ValueError:
                    start_enum = DriverStartType.AUTO

                found = False
                for bucket in buckets:
                    if found:
                        break

                    canonical = pattern_tmpl.format(bucket=bucket, arch=plan.arch_dir)

                    for tmpl in search_patterns:
                        pat = tmpl.format(
                            pattern=canonical,
                            driver=driver_name,
                            bucket=bucket,
                            arch=plan.arch_dir,
                        )

                        matches = _glob_all(base, pat)
                        if not matches:
                            continue

                        src = matches[0]
                        if len(matches) > 1:
                            src = _pick_best_match(matches)
                            _log(
                                logger,
                                logging.WARNING,
                                "Multiple matches for %s (picked %s): %s",
                                pat,
                                src,
                                [str(m) for m in matches[:10]],
                            )

                        infp = _find_inf_near_sys(src, str(inf_hint) if inf_hint else None)
                        pkg_dir = src.parent

                        drivers.append(
                            DriverFile(
                                name=driver_name,
                                type=driver_type,
                                src_path=src,
                                dest_name=f"{service}.sys",
                                start_type=start_enum,
                                service_name=service,
                                pci_ids=pci_ids,
                                class_guid=class_guid,
                                package_dir=pkg_dir,
                                inf_path=infp,
                                bucket_used=bucket,
                                match_pattern=pat,
                            )
                        )
                        _log(logger, logging.INFO, "📦 Found driver: type=%s service=%s bucket=%s -> %s", driver_type.value, service, bucket, src)
                        if infp:
                            _log(logger, logging.INFO, "📄 INF: %s", infp)
                        else:
                            _log(logger, logging.WARNING, "📄 INF missing near %s (PnP may still work via SYS only)", src)
                        found = True
                        break

                if not found:
                    lvl = logging.WARNING if driver_type == DriverType.STORAGE else logging.INFO
                    _log(logger, lvl, "Driver not found: type=%s name=%s arch=%s buckets=%s", driver_type.value, driver_name, plan.arch_dir, buckets)

    return drivers


# ---------------------------
# Public: BCD backup + hints (offline-safe)
# ---------------------------

def windows_bcd_actual_fix(self, g: guestfs.GuestFS) -> Dict[str, Any]:
    logger = _safe_logger(self)

    if not is_windows(self, g):
        return {"windows": False, "reason": "not_windows"}

    windows_root = _find_windows_root(self, g)
    if not windows_root:
        return {"windows": True, "bcd": "no_windows_directory"}

    bcd_stores = {
        "bios": f"{windows_root}/Boot/BCD",
        "uefi_standard": "/boot/efi/EFI/Microsoft/Boot/BCD",
        "uefi_alternative": "/boot/EFI/Microsoft/Boot/BCD",
        "uefi_fallback": "/efi/EFI/Microsoft/Boot/BCD",
        "uefi_root": "/EFI/Microsoft/Boot/BCD",
    }

    found: Dict[str, Any] = {}
    backups: Dict[str, Any] = {}
    dry_run = getattr(self, "dry_run", False)

    for store_type, store_path in bcd_stores.items():
        try:
            if g.is_file(store_path):
                size = g.filesize(store_path)
                found[store_type] = {"path": store_path, "size": size, "exists": True}
                if not dry_run:
                    ts = U.now_ts()
                    backup_path = f"{store_path}.backup.vmdk2kvm.{ts}"
                    try:
                        g.cp(store_path, backup_path)
                        backups[store_type] = {"backup_path": backup_path, "timestamp": ts, "size": size}
                    except Exception as be:
                        backups[store_type] = {"error": str(be), "path": store_path}
            else:
                found[store_type] = {"path": store_path, "exists": False}
        except Exception as e:
            found[store_type] = {"path": store_path, "exists": False, "error": str(e)}

    if not any(v.get("exists") for v in found.values()):
        return {"windows": True, "bcd": "no_bcd_store", "stores": found}

    notes: List[str] = [
        "Offline-safe: backups created where possible.",
        "Deep BCD edits need Windows tools (bcdedit/bootrec) inside Windows RE.",
    ]

    has_uefi = any(found.get(k, {}).get("exists") for k in ("uefi_standard", "uefi_alternative", "uefi_fallback", "uefi_root"))
    has_bios = found.get("bios", {}).get("exists")

    if has_uefi and not has_bios:
        notes.append("Hint: UEFI-style BCD present; boot the converted VM in UEFI mode.")
    if has_bios and not has_uefi:
        notes.append("Hint: BIOS-style BCD present; boot the converted VM in legacy BIOS mode.")
    if has_bios and has_uefi:
        notes.append("Hint: Both BIOS+UEFI BCD stores found; boot mode must match installed Windows mode.")

    return {"windows": True, "bcd": "found", "stores": found, "backups": backups, "notes": notes}


# ---------------------------
# Injection pipeline (split into smaller functions)
# ---------------------------

def _virtio_preflight(self, g: guestfs.GuestFS) -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
    logger = _safe_logger(self)
    virtio_dir = getattr(self, "virtio_drivers_dir", None)
    if not virtio_dir:
        _log(logger, logging.INFO, "VirtIO inject: virtio_drivers_dir not set -> skip")
        return None, {"injected": False, "reason": "virtio_drivers_dir_not_set"}

    virtio_src = Path(str(virtio_dir))
    if not virtio_src.exists():
        return None, {"injected": False, "reason": "virtio_drivers_dir_not_found", "path": str(virtio_src)}
    if not (virtio_src.is_dir() or virtio_src.suffix.lower() == ".iso"):
        return None, {"injected": False, "reason": "virtio_drivers_dir_invalid", "path": str(virtio_src)}

    if not is_windows(self, g):
        return None, {"injected": False, "reason": "not_windows"}
    if not getattr(self, "inspect_root", None):
        return None, {"injected": False, "reason": "no_inspect_root"}

    return virtio_src, None


def _virtio_ensure_system_volume(self, g: guestfs.GuestFS) -> WindowsSystemPaths:
    logger = _safe_logger(self)
    with _step(logger, "🧭 Ensure Windows system volume mounted (C: -> /)"):
        _ensure_windows_root(logger, g, hint_hive_path="/Windows/System32/config/SYSTEM")
    return _resolve_windows_system_paths(self, g)


def _virtio_ensure_temp_dir(self, g: guestfs.GuestFS, paths: WindowsSystemPaths, *, dry_run: bool) -> None:
    logger = _safe_logger(self)
    with _step(logger, "📁 Ensure Windows Temp dir exists"):
        try:
            _guest_mkdir_p(g, paths.temp_dir, dry_run=dry_run)
        except Exception as e:
            _log(logger, logging.WARNING, "Temp dir ensure failed (%s): %s", paths.temp_dir, e)


def _virtio_init_result(self, virtio_src: Path, win_info: Dict[str, Any], plan: WindowsVirtioPlan, paths: WindowsSystemPaths) -> Dict[str, Any]:
    dry_run = bool(getattr(self, "dry_run", False))
    force_overwrite = bool(getattr(self, "force_virtio_overwrite", False))
    return {
        "injected": False,
        "success": False,
        "dry_run": bool(dry_run),
        "force_overwrite": bool(force_overwrite),
        "windows": win_info,
        "plan": _plan_to_dict(plan),
        "virtio_dir": str(virtio_src),
        "windows_paths": {
            "windows_dir": paths.windows_dir,
            "system32_dir": paths.system32_dir,
            "drivers_dir": paths.drivers_dir,
            "config_dir": paths.config_dir,
            "temp_dir": paths.temp_dir,
            "system_hive": paths.system_hive,
            "software_hive": paths.software_hive,
        },
        "drivers_found": [],
        "files_copied": [],
        "packages_staged": [],
        "registry_changes": {},
        "devicepath_changes": {},
        "bcd_changes": {},
        "firstboot": {},
        "artifacts": [],
        "warnings": [],
        "notes": [],
    }


def _virtio_copy_sys_binaries(self, g: guestfs.GuestFS, result: Dict[str, Any], paths: WindowsSystemPaths, drivers: List[DriverFile]) -> None:
    logger = _safe_logger(self)
    dry_run = bool(result.get("dry_run"))
    force_overwrite = bool(result.get("force_overwrite"))

    with _step(logger, "🧱 Ensure System32\\drivers exists"):
        if not g.is_dir(paths.drivers_dir) and not dry_run:
            g.mkdir_p(paths.drivers_dir)

    with _step(logger, "📦 Upload .sys driver binaries"):
        for drv in drivers:
            dest_path = f"{paths.drivers_dir}/{drv.dest_name}"
            try:
                src_size = drv.src_path.stat().st_size
                host_hash = _sha256_path(drv.src_path)

                if g.is_file(dest_path) and not force_overwrite:
                    try:
                        guest_hash = _guest_sha256(g, dest_path)
                        if guest_hash and guest_hash == host_hash:
                            result["files_copied"].append(
                                {
                                    "name": drv.dest_name,
                                    "action": "skipped",
                                    "reason": "already_exists_same_hash",
                                    "source": str(drv.src_path),
                                    "destination": dest_path,
                                    "size": src_size,
                                    "sha256": host_hash,
                                    "type": drv.type.value,
                                    "service": drv.service_name,
                                }
                            )
                            result["artifacts"].append(
                                {
                                    "kind": "driver_sys",
                                    "service": drv.service_name,
                                    "type": drv.type.value,
                                    "src": str(drv.src_path),
                                    "dst": dest_path,
                                    "size": src_size,
                                    "sha256": host_hash,
                                    "action": "skipped",
                                }
                            )
                            _log(logger, logging.INFO, "Skip (same hash): %s -> %s", drv.src_path, dest_path)
                            continue
                    except Exception:
                        pass

                if not dry_run:
                    g.upload(str(drv.src_path), dest_path)

                verify = None
                if drv.type == DriverType.STORAGE and not dry_run:
                    try:
                        verify = _guest_sha256(g, dest_path)
                    except Exception:
                        verify = None

                action = "copied" if not dry_run else "dry_run"
                result["files_copied"].append(
                    {
                        "name": drv.dest_name,
                        "action": action,
                        "source": str(drv.src_path),
                        "destination": dest_path,
                        "size": src_size,
                        "sha256": host_hash,
                        "guest_sha256": verify,
                        "type": drv.type.value,
                        "service": drv.service_name,
                        "bucket_used": drv.bucket_used,
                        "match_pattern": drv.match_pattern,
                    }
                )
                result["artifacts"].append(
                    {
                        "kind": "driver_sys",
                        "service": drv.service_name,
                        "type": drv.type.value,
                        "src": str(drv.src_path),
                        "dst": dest_path,
                        "size": src_size,
                        "sha256": host_hash,
                        "guest_sha256": verify,
                        "action": action,
                        "bucket_used": drv.bucket_used,
                        "match_pattern": drv.match_pattern,
                    }
                )
                _log(logger, logging.INFO, "Upload: %s -> %s", drv.src_path, dest_path)
            except Exception as e:
                msg = f"VirtIO inject: copy failed {drv.src_path} -> {dest_path}: {e}"
                result["warnings"].append(msg)
                _log(logger, logging.WARNING, "%s", msg)


def _virtio_stage_packages(self, g: guestfs.GuestFS, result: Dict[str, Any], drivers: List[DriverFile]) -> Tuple[str, str]:
    """
    Stage INF/CAT/DLL payloads so firstboot can pnputil /install them.

    Returns (staging_root_guestfs_path, devicepath_append_string)
    """
    logger = _safe_logger(self)
    dry_run = bool(result.get("dry_run"))

    staging_root = "/vmdk2kvm/drivers/virtio"
    devicepath_append = r"%SystemDrive%\vmdk2kvm\drivers\virtio"

    with _step(logger, "📁 Stage driver packages (INF/CAT/DLL) for PnP"):
        try:
            _guest_mkdir_p(g, staging_root, dry_run=dry_run)
        except Exception as e:
            msg = f"VirtIO stage: failed to create staging root {staging_root}: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)

        for drv in drivers:
            if not drv.package_dir or not drv.package_dir.exists() or not drv.inf_path:
                continue

            guest_pkg_dir = f"{staging_root}/{drv.service_name}"
            try:
                _guest_mkdir_p(g, guest_pkg_dir, dry_run=dry_run)
            except Exception as e:
                msg = f"VirtIO stage: cannot create {guest_pkg_dir}: {e}"
                result["warnings"].append(msg)
                _log(logger, logging.WARNING, "%s", msg)
                continue

            staged_files: List[Dict[str, Any]] = []
            try:
                payload = sorted([p for p in drv.package_dir.iterdir() if p.is_file() and _is_probably_driver_payload(p)])
                for p in payload:
                    gp = f"{guest_pkg_dir}/{p.name}"
                    try:
                        if not dry_run:
                            g.upload(str(p), gp)
                        staged_files.append({"name": p.name, "source": str(p), "dest": gp, "size": p.stat().st_size})
                        result["artifacts"].append(
                            {
                                "kind": "staged_payload",
                                "service": drv.service_name,
                                "type": drv.type.value,
                                "src": str(p),
                                "dst": gp,
                                "size": p.stat().st_size,
                                "action": "copied" if not dry_run else "dry_run",
                            }
                        )
                    except Exception as e:
                        msg = f"VirtIO stage: upload failed {p} -> {gp}: {e}"
                        result["warnings"].append(msg)
                        _log(logger, logging.WARNING, "%s", msg)

                if staged_files:
                    result["packages_staged"].append(
                        {
                            "service": drv.service_name,
                            "type": drv.type.value,
                            "package_dir": str(drv.package_dir),
                            "inf": str(drv.inf_path),
                            "guest_dir": guest_pkg_dir,
                            "files": staged_files,
                        }
                    )
                    _log(logger, logging.INFO, "Staged package: %s -> %s (%d files)", drv.service_name, guest_pkg_dir, len(staged_files))
            except Exception as e:
                msg = f"VirtIO stage: failed staging package for {drv.service_name}: {e}"
                result["warnings"].append(msg)
                _log(logger, logging.WARNING, "%s", msg)

    return staging_root, devicepath_append


def _virtio_stage_manual_setup_cmd(self, g: guestfs.GuestFS, result: Dict[str, Any]) -> None:
    logger = _safe_logger(self)
    dry_run = bool(result.get("dry_run"))

    if not result.get("packages_staged"):
        return

    setup_script = "/vmdk2kvm/setup.cmd"
    script_content = "@echo off\r\n"
    script_content += "echo Installing staged VirtIO drivers...\r\n"
    for staged in result["packages_staged"]:
        inf = staged.get("inf")
        if inf:
            inf_name = Path(str(inf)).name
            script_content += f'pnputil /add-driver "C:\\vmdk2kvm\\drivers\\virtio\\{staged["service"]}\\{inf_name}" /install\r\n'
    script_content += "echo Done.\r\n"

    try:
        with _step(logger, "🧾 Stage manual setup.cmd (optional)"):
            _guest_write_text(g, setup_script, script_content, dry_run=dry_run)
        result["setup_script"] = {"path": setup_script, "content": script_content}
        result["artifacts"].append({"kind": "setup_cmd", "dst": setup_script, "action": "written" if not dry_run else "dry_run"})
    except Exception as e:
        msg = f"Failed to stage setup.cmd: {e}"
        result["warnings"].append(msg)
        _log(logger, logging.WARNING, "%s", msg)


def _virtio_edit_registry_system(self, g: guestfs.GuestFS, result: Dict[str, Any], paths: WindowsSystemPaths, drivers: List[DriverFile]) -> None:
    logger = _safe_logger(self)
    with _step(logger, "🧬 Edit SYSTEM hive (Services + CDD + StartOverride)"):
        try:
            reg_res = edit_system_hive(
                self,
                g,
                paths.system_hive,
                drivers,
                driver_type_storage_value=DriverType.STORAGE.value,
                boot_start_value=DriverStartType.BOOT.value,
            )
            result["registry_changes"] = reg_res
            if not reg_res.get("success"):
                _log(logger, logging.WARNING, "SYSTEM hive edit reported errors: %s", reg_res.get("errors"))
        except Exception as e:
            result["registry_changes"] = {"success": False, "error": str(e)}
            msg = f"Registry edit failed: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)


def _virtio_update_devicepath(self, g: guestfs.GuestFS, result: Dict[str, Any], paths: WindowsSystemPaths, devicepath_append: str) -> None:
    logger = _safe_logger(self)
    with _step(logger, "🧩 Update SOFTWARE DevicePath (PnP discovery)"):
        try:
            if result.get("packages_staged"):
                dp_res = append_devicepath_software_hive(self, g, paths.software_hive, devicepath_append)
                result["devicepath_changes"] = dp_res
                if not dp_res.get("success", True):
                    _log(logger, logging.WARNING, "DevicePath update reported errors: %s", dp_res.get("errors"))
            else:
                result["devicepath_changes"] = {"skipped": True, "reason": "no_packages_staged"}
                _log(logger, logging.INFO, "DevicePath: skipped (no packages staged)")
        except Exception as e:
            result["devicepath_changes"] = {"success": False, "error": str(e)}
            msg = f"DevicePath update failed: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)


def _virtio_provision_firstboot(self, g: guestfs.GuestFS, result: Dict[str, Any], paths: WindowsSystemPaths, staging_root: str) -> None:
    logger = _safe_logger(self)
    if not result.get("packages_staged"):
        result["firstboot"] = {"skipped": True, "reason": "no_packages_staged"}
        return

    log_path_guestfs = f"{paths.temp_dir}/vmdk2kvm-firstboot.log"

    with _step(logger, "🛠️ Provision firstboot service (pnputil /install + logging)"):
        try:
            fb = provision_firstboot_payload_and_service(
                self,
                g,
                system_hive_path=paths.system_hive,
                service_name="vmdk2kvm-firstboot",
                guest_dir="/vmdk2kvm",
                log_path=log_path_guestfs,
                driver_stage_dir=staging_root,
                extra_cmd=None,
                remove_vmware_tools=True,
            )
            result["firstboot"] = fb
            if not fb.get("success", True):
                msg = f"Firstboot provisioning failed: {fb.get('errors')}"
                result["warnings"].append(msg)
                _log(logger, logging.WARNING, "%s", msg)
            else:
                _log(
                    logger,
                    logging.INFO,
                    "Firstboot installed: service=%s log=%s",
                    "vmdk2kvm-firstboot",
                    _guestfs_to_windows_path(log_path_guestfs),
                )
        except Exception as e:
            result["firstboot"] = {"success": False, "error": str(e)}
            msg = f"Firstboot provisioning exception: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)


def _virtio_bcd_backup(self, g: guestfs.GuestFS, result: Dict[str, Any]) -> None:
    logger = _safe_logger(self)
    with _step(logger, "🧷 BCD store discovery + backup"):
        try:
            result["bcd_changes"] = windows_bcd_actual_fix(self, g)
        except Exception as e:
            result["bcd_changes"] = {"windows": True, "bcd": "error", "error": str(e)}
            msg = f"BCD check failed: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)


def _virtio_finalize(self, result: Dict[str, Any], drivers: List[DriverFile], *, plan: WindowsVirtioPlan, cfg: Dict[str, Any]) -> Dict[str, Any]:
    logger = _safe_logger(self)

    result["drivers_found"] = [d.to_dict() for d in drivers]

    sys_ok = any(x.get("action") in ("copied", "dry_run", "skipped") for x in result.get("files_copied", []))
    reg_ok = bool(result.get("registry_changes", {}).get("success"))
    result["injected"] = bool(sys_ok and reg_ok)
    result["success"] = result["injected"]
    if not result["success"]:
        result["reason"] = "registry_update_failed" if not reg_ok else "sys_copy_failed"

    storage_found = sorted({d.service_name for d in drivers if d.type == DriverType.STORAGE})
    storage_missing: List[str] = []
    if "viostor" not in storage_found:
        storage_missing.append("viostor")
    if "vioscsi" not in storage_found:
        storage_missing.append("vioscsi")

    result["notes"] += [
        "Release detection: prefers ProductName + build number (CurrentBuildNumber/CurrentBuild) over major/minor.",
        "Config-driven: driver definitions + OS(bucket) mapping can come from YAML/JSON config (self.config) or an override file.",
        "Config merge: dicts deep-merge; lists are replaced (override wins).",
        "Default release fallback: Windows 11.",
        "Driver discovery: canonical pattern first; fallback globs warn on multiple matches and pick a best candidate.",
        "Storage: injects viostor + vioscsi when present and forces BOOT start in SYSTEM hive.",
        "Registry: StartOverride removed when found (can silently disable boot drivers).",
        "CDD: CriticalDeviceDatabase populated for virtio storage PCI IDs to ensure early binding.",
        f"Driver discovery buckets: {_bucket_candidates(plan.release, cfg)}",
        f"Storage drivers found: {storage_found} missing: {storage_missing}",
        r"Staging: payload staged under C:\vmdk2kvm\drivers\virtio and installed via firstboot service (pnputil).",
        r"Logs: see the 'firstboot' section for the exact log path.",
    ]

    if storage_missing:
        msg = f"Missing critical storage drivers: {storage_missing} (guest may BSOD INACCESSIBLE_BOOT_DEVICE)"
        result["warnings"].append(msg)
        _log(logger, logging.WARNING, "%s", msg)

    export_report = bool(getattr(self, "export_report", False))
    if export_report:
        report_path = "virtio_inject_report.json"
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            result["report_exported"] = report_path
            _log(logger, logging.INFO, "Report exported: %s", report_path)
        except Exception as e:
            msg = f"Failed to export report: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)

    return result


# ---------------------------
# Public: VirtIO injection
# ---------------------------

def inject_virtio_drivers(self, g: guestfs.GuestFS) -> Dict[str, Any]:
    logger = _safe_logger(self)

    virtio_src, early = _virtio_preflight(self, g)
    if early is not None:
        return early
    assert virtio_src is not None

    cfg = _load_virtio_config(self)
    _warn_if_driver_defs_suspicious(self, cfg)

    _log_mountpoints_best_effort(logger, g)

    paths = _virtio_ensure_system_volume(self, g)
    if not paths.windows_dir or not g.is_dir(paths.windows_dir):
        return {"injected": False, "reason": "no_windows_root", "windows_dir": paths.windows_dir}

    dry_run = bool(getattr(self, "dry_run", False))
    _virtio_ensure_temp_dir(self, g, paths, dry_run=dry_run)

    win_info = _windows_version_info(self, g, paths=paths)
    plan = _choose_driver_plan(self, win_info, cfg)

    with _step(logger, "🔎 Discover VirtIO drivers"):
        drivers = _discover_virtio_drivers(self, virtio_src, plan, cfg)

    if not drivers:
        return {
            "injected": False,
            "reason": "no_drivers_found",
            "virtio_dir": str(virtio_src),
            "windows_info": win_info,
            "plan": _plan_to_dict(plan),
            "buckets_tried": _bucket_candidates(plan.release, cfg),
            "windows_paths": {
                "windows_dir": paths.windows_dir,
                "system32_dir": paths.system32_dir,
                "drivers_dir": paths.drivers_dir,
                "config_dir": paths.config_dir,
                "temp_dir": paths.temp_dir,
            },
        }

    result = _virtio_init_result(self, virtio_src, win_info, plan, paths)

    try:
        _virtio_copy_sys_binaries(self, g, result, paths, drivers)
    except Exception as e:
        return {**result, "reason": f"sys_copy_failed: {e}"}

    staging_root, devicepath_append = _virtio_stage_packages(self, g, result, drivers)

    _virtio_stage_manual_setup_cmd(self, g, result)
    _virtio_edit_registry_system(self, g, result, paths, drivers)
    _virtio_update_devicepath(self, g, result, paths, devicepath_append)
    _virtio_provision_firstboot(self, g, result, paths, staging_root)
    _virtio_bcd_backup(self, g, result)

    return _virtio_finalize(self, result, drivers, plan=plan, cfg=cfg)


class WindowsFixer:
    def is_windows(self, g: guestfs.GuestFS) -> bool:
        return is_windows(self, g)

    def windows_bcd_actual_fix(self, g: guestfs.GuestFS) -> Dict[str, Any]:
        return windows_bcd_actual_fix(self, g)

    def inject_virtio_drivers(self, g: guestfs.GuestFS) -> Dict[str, Any]:
        return inject_virtio_drivers(self, g)
