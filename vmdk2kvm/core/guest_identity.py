# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# vmdk2kvm/core/guest_identity.py
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import guestfs  # type: ignore

from .utils import U

# Canonical Windows detection from your repo (fixers/windows_virtio.py)
try:
    from ..fixers.windows_virtio import is_windows as _wv_is_windows  # type: ignore
    _WIN_VIRTIO_DETECT_OK = True
except Exception:  # pragma: no cover
    _wv_is_windows = None  # type: ignore
    _WIN_VIRTIO_DETECT_OK = False


class GuestType(Enum):
    """Guest operating system types."""
    LINUX = "linux"
    WINDOWS = "windows"
    BSD = "bsd"
    MACOS = "macos"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, value: str) -> "GuestType":
        value = (value or "").lower().strip()
        for member in cls:
            if member.value == value:
                return member
        return cls.UNKNOWN


@dataclass
class GuestIdentity:
    """Container for guest identity information."""
    type: GuestType = GuestType.UNKNOWN

    # Linux-ish (also useful for general OS)
    hostname: Optional[str] = None
    machine_id: Optional[str] = None
    os_name: Optional[str] = None
    os_pretty_name: Optional[str] = None
    os_version: Optional[str] = None
    architecture: Optional[str] = None
    kernel_version: Optional[str] = None
    cpe_name: Optional[str] = None
    support_end: Optional[str] = None

    # Windows-ish
    windows_major: Optional[str] = None
    windows_minor: Optional[str] = None
    windows_distro: Optional[str] = None

    # Detection meta
    confidence: float = 0.0
    detection_method: str = "unknown"

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class _WvShim:
    """
    windows_virtio.is_windows expects:
      - self.logger (optional)
      - self.inspect_root (required for strongest detection path)
    """
    logger: object
    inspect_root: Optional[str] = None


class GuestDetector:
    """
    Enhanced guest detection with multiple fallback strategies.

    IMPORTANT:
      - We use guestfs.GuestFS(python_return_dict=True) in detect()
      - That means some APIs (notably inspect_get_mountpoints) return dicts.
        We normalize that shape to avoid the dreaded "string index out of range".
    """

    OS_INDICATORS: Dict[GuestType, List[str]] = {
        GuestType.LINUX: [
            "/etc/os-release",
            "/usr/lib/os-release",
            "/etc/lsb-release",
            "/etc/redhat-release",
            "/etc/debian_version",
            "/etc/arch-release",
            "/etc/SuSE-release",
            "/etc/alpine-release",
            "/proc",
            "/sys",
        ],
        GuestType.WINDOWS: [
            "/Windows/System32",
            "/WINDOWS/System32",
            "/winnt/system32",
            "/Windows/explorer.exe",
            "/WINDOWS/explorer.exe",
            "/Program Files",
            "/Program Files (x86)",
        ],
        GuestType.BSD: [
            "/etc/freebsd-update.conf",
            "/etc/openbsd-version",
            "/etc/netbsd-version",
            "/etc/bsd-release",
        ],
        GuestType.MACOS: [
            "/System/Library/CoreServices",
            "/Applications",
            "/Library/Preferences",
            "/usr/bin/sw_vers",
        ],
        GuestType.UNKNOWN: [],
    }

    WINDOWS_REGISTRY_HIVES: List[str] = [
        "/Windows/System32/config/SOFTWARE",
        "/Windows/System32/config/SYSTEM",
        "/WINDOWS/System32/config/SOFTWARE",
        "/WINDOWS/System32/config/SYSTEM",
        "/winnt/system32/config/SOFTWARE",
        "/winnt/system32/config/SYSTEM",
    ]

    # ---------------------------
    # Small parsing helpers
    # ---------------------------

    @staticmethod
    def read_first_line(g: guestfs.GuestFS, path: str) -> Optional[str]:
        try:
            if not g.is_file(path):
                return None
            content = g.read_file(path) or ""
            lines = content.splitlines()
            return lines[0].strip() if lines else None
        except Exception:
            return None

    @staticmethod
    def parse_os_release(text: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for line in (text or "").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            out[k.strip()] = v
        return out

    @staticmethod
    def parse_issue_file(content: str) -> Optional[str]:
        if not content:
            return None
        content = re.sub(r"\\[a-zA-Z]", "", content)
        content = content.replace("\\n", " ").replace("\\r", " ")
        content = content.strip()
        return content or None

    # ---------------------------
    # Mounting (shape-safe)
    # ---------------------------

    @staticmethod
    def _normalize_mountpoints(mps: Any) -> List[Tuple[str, str]]:
        """
        guestfs inspect_get_mountpoints(root) can be:
          - dict when python_return_dict=True: { mountpoint: device }
          - list/tuple when python_return_dict=False: [(device, mountpoint), ...]
        We normalize to: [(device, mountpoint), ...]
        """
        out: List[Tuple[str, str]] = []
        if mps is None:
            return out

        # python_return_dict=True => dict { mp: dev }
        if isinstance(mps, dict):
            for mp, dev in mps.items():
                if isinstance(dev, str) and isinstance(mp, str):
                    out.append((dev, mp))
            return out

        # list/tuple => iterable of 2-tuples
        if isinstance(mps, (list, tuple)):
            for item in mps:
                try:
                    dev, mp = item  # type: ignore[misc]
                    if isinstance(dev, str) and isinstance(mp, str):
                        out.append((dev, mp))
                except Exception:
                    continue
            return out

        return out

    @classmethod
    def mount_inspected_root(cls, g: guestfs.GuestFS, root: str) -> None:
        """
        Mount all mountpoints for an inspected root, in increasing mountpoint length.
        Never throws (best-effort).
        """
        try:
            raw = g.inspect_get_mountpoints(root)
        except Exception:
            return

        mps = cls._normalize_mountpoints(raw)
        for dev, mp in sorted(mps, key=lambda x: len(x[1])):
            try:
                g.mount(dev, mp)
            except Exception:
                continue

    # ---------------------------
    # Detection strategies
    # ---------------------------

    @classmethod
    def detect_by_indicators(cls, g: guestfs.GuestFS) -> Dict[GuestType, float]:
        scores: Dict[GuestType, float] = {gt: 0.0 for gt in GuestType}

        for os_type, indicators in cls.OS_INDICATORS.items():
            for indicator in indicators:
                try:
                    if g.is_dir(indicator):
                        scores[os_type] += 1.0
                    elif g.is_file(indicator):
                        scores[os_type] += 0.8
                except Exception:
                    continue

        # Extra hint for Windows: registry hives
        for hive in cls.WINDOWS_REGISTRY_HIVES:
            try:
                if g.is_file(hive):
                    scores[GuestType.WINDOWS] += 1.5
                    break
            except Exception:
                continue

        return scores

    @classmethod
    def detect_by_inspection(cls, g: guestfs.GuestFS, root: str) -> Optional[GuestType]:
        try:
            os_type = g.inspect_get_type(root)
            if not os_type:
                return None
            os_type_str = (U.to_text(os_type) or "").lower().strip()
            if os_type_str == "windows":
                return GuestType.WINDOWS
            if os_type_str == "linux":
                return GuestType.LINUX
            if "bsd" in os_type_str:
                return GuestType.BSD
        except Exception:
            pass
        return None

    @classmethod
    def detect_by_canonical(cls, g: guestfs.GuestFS, root: str, logger) -> Optional[GuestType]:
        if not _WIN_VIRTIO_DETECT_OK or _wv_is_windows is None:
            return None
        shim = _WvShim(logger=logger, inspect_root=root)
        try:
            return GuestType.WINDOWS if bool(_wv_is_windows(shim, g)) else GuestType.LINUX  # type: ignore[misc]
        except Exception:
            return None

    # ---------------------------
    # Identity collection
    # ---------------------------

    @staticmethod
    def best_effort_kernel(g: guestfs.GuestFS) -> Optional[str]:
        try:
            if g.is_dir("/lib/modules"):
                vers = sorted(g.ls("/lib/modules"))
                return vers[-1] if vers else None
        except Exception:
            pass
        try:
            if g.is_dir("/boot"):
                vml = sorted(x for x in g.ls("/boot") if x.startswith("vmlinuz-"))
                if not vml:
                    return None
                last = vml[-1]
                return last[len("vmlinuz-"):] if last.startswith("vmlinuz-") else last
        except Exception:
            pass
        return None

    @classmethod
    def collect_linux_identity(cls, g: guestfs.GuestFS, root: str) -> GuestIdentity:
        ident = GuestIdentity(type=GuestType.LINUX)

        cls.mount_inspected_root(g, root)

        # arch
        try:
            ident.architecture = U.to_text(g.inspect_get_arch(root))
        except Exception:
            pass

        # os-release
        osr_raw = ""
        for p in ("/etc/os-release", "/usr/lib/os-release"):
            try:
                if g.is_file(p):
                    osr_raw = g.read_file(p) or ""
                    break
            except Exception:
                continue
        osr = cls.parse_os_release(osr_raw)
        ident.os_pretty_name = osr.get("PRETTY_NAME")
        ident.os_name = osr.get("NAME")
        ident.os_version = osr.get("VERSION")
        ident.cpe_name = osr.get("CPE_NAME")
        ident.support_end = osr.get("SUPPORT_END") or osr.get("SUPPORT_END_DATE")

        # hostname
        ident.hostname = cls.read_first_line(g, "/etc/hostname")

        # machine-id
        ident.machine_id = (
            cls.read_first_line(g, "/etc/machine-id")
            or cls.read_first_line(g, "/var/lib/dbus/machine-id")
        )

        # kernel
        ident.kernel_version = cls.best_effort_kernel(g)

        # issue fallback
        try:
            if g.is_file("/etc/issue") and not ident.os_pretty_name:
                issue = g.read_file("/etc/issue") or ""
                txt = cls.parse_issue_file(issue)
                if txt:
                    ident.os_pretty_name = txt
        except Exception:
            pass

        return ident

    @classmethod
    def collect_windows_identity(cls, g: guestfs.GuestFS, root: str) -> GuestIdentity:
        ident = GuestIdentity(type=GuestType.WINDOWS)

        cls.mount_inspected_root(g, root)

        try:
            ident.os_name = U.to_text(g.inspect_get_product_name(root))
        except Exception:
            pass
        try:
            ident.architecture = U.to_text(g.inspect_get_arch(root))
        except Exception:
            pass
        try:
            ident.windows_distro = U.to_text(g.inspect_get_distro(root))
        except Exception:
            pass
        try:
            ident.windows_major = str(g.inspect_get_major_version(root))
        except Exception:
            pass
        try:
            ident.windows_minor = str(g.inspect_get_minor_version(root))
        except Exception:
            pass

        # evidence (dirs/hives)
        windows_dirs: List[str] = []
        for d in ("/Windows", "/WINDOWS", "/winnt"):
            try:
                if g.is_dir(d):
                    windows_dirs.append(d)
            except Exception:
                continue
        if windows_dirs:
            ident.metadata["windows_dirs"] = windows_dirs

        reg_hives: List[str] = []
        for h in cls.WINDOWS_REGISTRY_HIVES:
            try:
                if g.is_file(h):
                    reg_hives.append(h)
            except Exception:
                continue
        if reg_hives:
            ident.metadata["registry_hives"] = reg_hives

        return ident

    # ---------------------------
    # Root selection + main detect()
    # ---------------------------

    @classmethod
    def best_root(cls, g: guestfs.GuestFS) -> Optional[str]:
        try:
            roots = g.inspect_os()
        except Exception:
            return None
        if not roots:
            return None
        # Prefer a Windows root if present
        for r in roots:
            try:
                t = (U.to_text(g.inspect_get_type(r)) or "").strip().lower()
                if t == "windows":
                    return r
            except Exception:
                continue
        return roots[0]

    @classmethod
    def detect(cls, img_path: Path, logger, readonly: bool = True) -> Optional[GuestIdentity]:
        """
        Open guestfs read-only and detect guest OS + identity.

        Returns GuestIdentity or None if no OS roots.
        """
        g: Optional[guestfs.GuestFS] = None
        try:
            g = guestfs.GuestFS(python_return_dict=True)
            g.add_drive_opts(str(img_path), readonly=int(bool(readonly)))
            g.launch()

            roots = g.inspect_os()
            if not roots:
                try:
                    logger.debug("GuestDetector: no inspectable OS roots found in image=%s", img_path)
                except Exception:
                    pass
                return None

            root = cls.best_root(g) or roots[0]

            # Strategy 1: canonical windows_virtio detection
            identity: Optional[GuestIdentity] = None
            t1 = cls.detect_by_canonical(g, root, logger)
            if t1:
                identity = GuestIdentity(type=t1, confidence=0.90, detection_method="canonical_windows_virtio")

            # Strategy 2: guestfs inspection
            if not identity or identity.confidence < 0.80:
                t2 = cls.detect_by_inspection(g, root)
                if t2:
                    conf = 0.80 if (identity and identity.type == t2) else 0.70
                    if (identity is None) or (conf > identity.confidence):
                        identity = GuestIdentity(type=t2, confidence=conf, detection_method="guestfs_inspection")

            # Strategy 3: indicator scoring
            scores = cls.detect_by_indicators(g)
            best_type = max(scores.items(), key=lambda x: x[1])[0]
            indicator_conf = min(scores[best_type] / 5.0, 0.60)

            if (identity is None) or (indicator_conf > identity.confidence):
                identity = GuestIdentity(type=best_type, confidence=indicator_conf, detection_method="indicator_files")

            # Collect detailed identity
            if identity.type == GuestType.LINUX:
                detailed = cls.collect_linux_identity(g, root)
            elif identity.type == GuestType.WINDOWS:
                detailed = cls.collect_windows_identity(g, root)
            else:
                detailed = GuestIdentity(type=identity.type)

            # merge (do not overwrite meta like detection_method/confidence)
            for f in detailed.__dataclass_fields__:
                if f in ("confidence", "detection_method"):
                    continue
                v = getattr(detailed, f)
                if v:
                    setattr(identity, f, v)

            # nudge confidence if we found good identity anchors
            if identity.hostname or identity.os_name or identity.os_pretty_name:
                identity.confidence = min(identity.confidence + 0.10, 1.0)

            return identity

        except Exception as e:
            try:
                logger.error("Guest detection failed: %s", e)
            except Exception:
                pass
            return None
        finally:
            if g is not None:
                try:
                    g.shutdown()
                except Exception:
                    pass
                try:
                    g.close()
                except Exception:
                    pass


def emit_guest_identity_log(logger, identity: GuestIdentity) -> None:
    """
    Emit a hostnamectl-like identity summary.
    Keep it readable; avoid JSON spam unless requested elsewhere.
    """
    if identity.type == GuestType.LINUX:
        logger.info(
            " guest identity (linux)\n"
            "     Detection Method: %s\n"
            "  Detection Confidence: %.1f%%\n"
            "     Static hostname: %s\n"
            "          Machine ID: %s\n"
            "    Operating System: %s\n"
            "      OS Pretty Name: %s\n"
            "          OS Version: %s\n"
            "         CPE OS Name: %s\n"
            "      OS Support End: %s\n"
            "        Architecture: %s\n"
            "  Kernel (installed): %s",
            identity.detection_method,
            identity.confidence * 100,
            identity.hostname or "?",
            identity.machine_id or "?",
            identity.os_name or "?",
            identity.os_pretty_name or "?",
            identity.os_version or "?",
            identity.cpe_name or "?",
            identity.support_end or "?",
            identity.architecture or "?",
            identity.kernel_version or "?",
        )
        return

    if identity.type == GuestType.WINDOWS:
        reg_hives = identity.metadata.get("registry_hives", [])
        win_dirs = identity.metadata.get("windows_dirs", [])
        logger.info(
            " guest identity (windows)\n"
            "     Detection Method: %s\n"
            "  Detection Confidence: %.1f%%\n"
            "    Operating System: %s\n"
            "        Architecture: %s\n"
            "      Windows Distro: %s\n"
            "      Version (maj): %s\n"
            "      Version (min): %s\n"
            "   Registry hives #: %s\n"
            "   Windows dirs   #: %s",
            identity.detection_method,
            identity.confidence * 100,
            identity.os_name or "Windows",
            identity.architecture or "?",
            identity.windows_distro or "?",
            identity.windows_major or "?",
            identity.windows_minor or "?",
            str(len(reg_hives)) if isinstance(reg_hives, list) else "?",
            str(len(win_dirs)) if isinstance(win_dirs, list) else "?",
        )
        return

    logger.info(
        " guest identity (unknown)\n"
        "     Detection Method: %s\n"
        "  Detection Confidence: %.1f%%\n"
        "       Detected Type: %s",
        identity.detection_method,
        identity.confidence * 100,
        identity.type.value,
    )
