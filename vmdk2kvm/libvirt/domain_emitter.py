# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# vmdk2kvm/libvirt/domain_emitter.py
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any

import guestfs  # type: ignore

from ..core.logger import Log
from ..core.utils import U


try:
    from .linux_domain import emit_linux_domain  # type: ignore
    _LINUX_DOMAIN_OK = True
except Exception:  # pragma: no cover
    emit_linux_domain = None  # type: ignore
    _LINUX_DOMAIN_OK = False


try:
    from .windows_domain import WinDomainSpec, render_windows_domain_xml  # type: ignore
    _WIN_DOMAIN_OK = True
except Exception:  # pragma: no cover
    WinDomainSpec = None  # type: ignore
    render_windows_domain_xml = None  # type: ignore
    _WIN_DOMAIN_OK = False


# Canonical Windows detection from your repo
try:
    from ..fixers.windows_virtio import is_windows as _wv_is_windows  # type: ignore
    _WIN_VIRTIO_DETECT_OK = True
except Exception:  # pragma: no cover
    _wv_is_windows = None  # type: ignore
    _WIN_VIRTIO_DETECT_OK = False


# --------------------------------------------------------------------------------------
# Enhanced Guest Detection System
# --------------------------------------------------------------------------------------

class GuestType(Enum):
    """Guest operating system types."""
    LINUX = "linux"
    WINDOWS = "windows"
    BSD = "bsd"
    MACOS = "macos"
    UNKNOWN = "unknown"
    
    @classmethod
    def from_string(cls, value: str) -> GuestType:
        """Convert string to GuestType enum."""
        value = value.lower().strip()
        for member in cls:
            if member.value == value:
                return member
        return cls.UNKNOWN


@dataclass
class GuestIdentity:
    """Container for guest identity information."""
    type: GuestType = GuestType.UNKNOWN
    hostname: Optional[str] = None
    machine_id: Optional[str] = None
    os_name: Optional[str] = None
    os_pretty_name: Optional[str] = None
    os_version: Optional[str] = None
    architecture: Optional[str] = None
    kernel_version: Optional[str] = None
    cpe_name: Optional[str] = None
    support_end: Optional[str] = None
    # Windows-specific
    windows_major: Optional[str] = None
    windows_minor: Optional[str] = None
    windows_distro: Optional[str] = None
    # Detection confidence
    confidence: float = 0.0
    detection_method: str = "unknown"
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


class GuestDetector:
    """Enhanced guest detection with multiple fallback strategies."""
    
    # Common OS indicator files and directories
    OS_INDICATORS = {
        GuestType.LINUX: [
            "/etc/os-release",
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
    }
    
    # Windows registry hives for deeper detection
    WINDOWS_REGISTRY_HIVES = [
        "/Windows/System32/config/SOFTWARE",
        "/Windows/System32/config/SYSTEM",
        "/WINDOWS/System32/config/SOFTWARE",
        "/WINDOWS/System32/config/SYSTEM",
        "/winnt/system32/config/SOFTWARE",
        "/winnt/system32/config/SYSTEM",
    ]
    
    @staticmethod
    def _read_first_line(g: guestfs.GuestFS, path: str) -> Optional[str]:
        """Safely read first line from a file."""
        try:
            if not g.is_file(path):
                return None
            content = g.read_file(path)
            if content:
                lines = content.splitlines()
                return lines[0].strip() if lines else None
        except Exception:
            pass
        return None
    
    @staticmethod
    def _parse_os_release(text: str) -> Dict[str, str]:
        """Parse /etc/os-release format."""
        out: Dict[str, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            # Remove quotes
            v = v.strip().strip('"').strip("'")
            out[k.strip()] = v
        return out
    
    @staticmethod
    def _parse_issue_file(content: str) -> Optional[str]:
        """Parse /etc/issue or /etc/issue.net for OS hints."""
        # Remove escape sequences and clean up
        content = re.sub(r'\\[a-zA-Z]', '', content)
        content = content.replace('\\n', ' ').replace('\\r', ' ')
        content = content.strip()
        return content if content else None
    
    @classmethod
    def _detect_by_indicators(cls, g: guestfs.GuestFS) -> Dict[GuestType, float]:
        """Detect OS type by checking for indicator files."""
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
        
        # Special handling for Linux: check /proc or /sys
        try:
            if g.is_dir("/proc") and g.is_dir("/sys"):
                scores[GuestType.LINUX] += 2.0
        except Exception:
            pass
        
        # Special handling for Windows: check registry hives
        for hive in cls.WINDOWS_REGISTRY_HIVES:
            try:
                if g.is_file(hive):
                    scores[GuestType.WINDOWS] += 1.5
                    break
            except Exception:
                continue
        
        return scores
    
    @classmethod
    def _detect_by_inspection(cls, g: guestfs.GuestFS, root: str) -> Optional[GuestType]:
        """Detect OS type using guestfs inspection API."""
        try:
            os_type = g.inspect_get_type(root)
            if os_type:
                os_type_str = U.to_text(os_type).lower().strip()
                if os_type_str == "windows":
                    return GuestType.WINDOWS
                elif os_type_str == "linux":
                    return GuestType.LINUX
                elif "bsd" in os_type_str:
                    return GuestType.BSD
        except Exception:
            pass
        return None
    
    @classmethod
    def _detect_by_canonical(cls, g: guestfs.GuestFS, root: str, logger) -> Optional[GuestType]:
        """Use the canonical windows_virtio detection if available."""
        if not _WIN_VIRTIO_DETECT_OK or _wv_is_windows is None:
            return None
        
        class Shim:
            def __init__(self, root: str, logger):
                self.logger = logger
                self.inspect_root = root
        
        try:
            shim = Shim(root, logger)
            if bool(_wv_is_windows(shim, g)):  # type: ignore[misc]
                return GuestType.WINDOWS
            else:
                return GuestType.LINUX
        except Exception:
            return None
    
    @classmethod
    def _collect_linux_identity(cls, g: guestfs.GuestFS, root: str) -> GuestIdentity:
        """Collect detailed identity information for Linux guests."""
        identity = GuestIdentity(type=GuestType.LINUX)
        
        # Mount for better file access
        try:
            mps = g.inspect_get_mountpoints(root)
            for dev, mp in sorted(mps, key=lambda x: len(x[1])):
                try:
                    g.mount(dev, mp)
                except Exception:
                    continue
        except Exception:
            pass
        
        # Get basic architecture
        try:
            identity.architecture = U.to_text(g.inspect_get_arch(root))
        except Exception:
            pass
        
        # Parse /etc/os-release
        os_release_content = None
        for os_release_path in ["/etc/os-release", "/usr/lib/os-release"]:
            try:
                if g.is_file(os_release_path):
                    os_release_content = g.read_file(os_release_path)
                    break
            except Exception:
                continue
        
        if os_release_content:
            os_release = cls._parse_os_release(os_release_content)
            identity.os_pretty_name = os_release.get("PRETTY_NAME")
            identity.os_name = os_release.get("NAME")
            identity.os_version = os_release.get("VERSION")
            identity.cpe_name = os_release.get("CPE_NAME")
            identity.support_end = os_release.get("SUPPORT_END") or os_release.get("SUPPORT_END_DATE")
        
        # Get hostname
        identity.hostname = cls._read_first_line(g, "/etc/hostname")
        
        # Get machine ID
        for machine_id_path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
            machine_id = cls._read_first_line(g, machine_id_path)
            if machine_id:
                identity.machine_id = machine_id
                break
        
        # Get kernel version
        try:
            if g.is_dir("/lib/modules"):
                versions = sorted(g.ls("/lib/modules"))
                if versions:
                    identity.kernel_version = versions[-1]
        except Exception:
            pass
        
        if not identity.kernel_version:
            try:
                if g.is_dir("/boot"):
                    vmlinuz_files = [x for x in g.ls("/boot") if x.startswith("vmlinuz-")]
                    if vmlinuz_files:
                        latest = sorted(vmlinuz_files)[-1]
                        identity.kernel_version = latest[8:] if latest.startswith("vmlinuz-") else latest
            except Exception:
                pass
        
        # Check /etc/issue for additional info
        try:
            if g.is_file("/etc/issue"):
                issue_content = g.read_file("/etc/issue")
                issue_text = cls._parse_issue_file(issue_content)
                if issue_text and not identity.os_pretty_name:
                    identity.os_pretty_name = issue_text
        except Exception:
            pass
        
        return identity
    
    @classmethod
    def _collect_windows_identity(cls, g: guestfs.GuestFS, root: str) -> GuestIdentity:
        """Collect identity information for Windows guests."""
        identity = GuestIdentity(type=GuestType.WINDOWS)
        
        # Try to mount for file access
        try:
            mps = g.inspect_get_mountpoints(root)
            for dev, mp in sorted(mps, key=lambda x: len(x[1])):
                try:
                    g.mount(dev, mp)
                except Exception:
                    continue
        except Exception:
            pass
        
        # Get basic information from inspection
        try:
            identity.os_name = U.to_text(g.inspect_get_product_name(root))
            identity.architecture = U.to_text(g.inspect_get_arch(root))
            identity.windows_distro = U.to_text(g.inspect_get_distro(root))
        except Exception:
            pass
        
        try:
            identity.windows_major = str(g.inspect_get_major_version(root))
        except Exception:
            pass
        
        try:
            identity.windows_minor = str(g.inspect_get_minor_version(root))
        except Exception:
            pass
        
        # Check for Windows directories
        windows_dirs = []
        for win_dir in ["/Windows", "/WINDOWS", "/winnt"]:
            try:
                if g.is_dir(win_dir):
                    windows_dirs.append(win_dir)
            except Exception:
                continue
        
        if windows_dirs:
            identity.metadata["windows_dirs"] = windows_dirs
        
        # Check for registry hives
        registry_hives = []
        for hive in cls.WINDOWS_REGISTRY_HIVES:
            try:
                if g.is_file(hive):
                    registry_hives.append(hive)
            except Exception:
                continue
        
        if registry_hives:
            identity.metadata["registry_hives"] = registry_hives
        
        # Try to determine edition from common files
        edition_indicators = {
            "Professional": ["/Windows/Professional", "/WINDOWS/Professional"],
            "Enterprise": ["/Windows/Enterprise", "/WINDOWS/Enterprise"],
            "Home": ["/Windows/Home", "/WINDOWS/Home"],
            "Server": ["/Windows/Server", "/WINDOWS/Server"],
        }
        
        for edition, paths in edition_indicators.items():
            for path in paths:
                try:
                    if g.is_dir(path) or g.is_file(path):
                        identity.metadata["edition"] = edition
                        break
                except Exception:
                    continue
        
        return identity
    
    @classmethod
    def detect(cls, img_path: Path, logger, readonly: bool = True) -> Optional[GuestIdentity]:
        """
        Main detection method that uses multiple strategies.
        
        Returns a GuestIdentity object with detailed information.
        """
        g = None
        try:
            g = guestfs.GuestFS(python_return_dict=True)
            g.add_drive_opts(str(img_path), readonly=int(readonly))
            g.launch()
            
            # Get inspectable roots
            roots = g.inspect_os()
            if not roots:
                logger.debug("No inspectable OS roots found in image")
                return None
            
            # Try to find the best root (prefer Windows if present)
            root = None
            for r in roots:
                try:
                    os_type = cls._detect_by_inspection(g, r)
                    if os_type == GuestType.WINDOWS:
                        root = r
                        break
                except Exception:
                    continue
            
            if root is None:
                root = roots[0]
            
            # Detection strategy 1: Canonical detection (highest priority)
            identity = None
            detected_type = cls._detect_by_canonical(g, root, logger)
            if detected_type:
                identity = GuestIdentity(
                    type=detected_type,
                    confidence=0.9,
                    detection_method="canonical_windows_virtio"
                )
            
            # Detection strategy 2: GuestFS inspection
            if not identity or identity.confidence < 0.8:
                inspected_type = cls._detect_by_inspection(g, root)
                if inspected_type:
                    confidence = 0.8 if identity and identity.type == inspected_type else 0.7
                    if not identity or confidence > identity.confidence:
                        identity = GuestIdentity(
                            type=inspected_type,
                            confidence=confidence,
                            detection_method="guestfs_inspection"
                        )
            
            # Detection strategy 3: Indicator files
            indicator_scores = cls._detect_by_indicators(g)
            best_type = max(indicator_scores.items(), key=lambda x: x[1])[0]
            indicator_confidence = min(indicator_scores[best_type] / 5.0, 0.6)
            
            if not identity or indicator_confidence > identity.confidence:
                identity = GuestIdentity(
                    type=best_type,
                    confidence=indicator_confidence,
                    detection_method="indicator_files"
                )
            
            # Collect detailed identity based on detected type
            if identity.type == GuestType.LINUX:
                detailed_identity = cls._collect_linux_identity(g, root)
                # Merge detailed info
                for field in detailed_identity.__dataclass_fields__:
                    if field != "type":
                        value = getattr(detailed_identity, field)
                        if value:
                            setattr(identity, field, value)
            
            elif identity.type == GuestType.WINDOWS:
                detailed_identity = cls._collect_windows_identity(g, root)
                # Merge detailed info
                for field in detailed_identity.__dataclass_fields__:
                    if field != "type":
                        value = getattr(detailed_identity, field)
                        if value:
                            setattr(identity, field, value)
            
            # Final confidence adjustment based on collected information
            if identity.hostname or identity.os_name:
                identity.confidence = min(identity.confidence + 0.1, 1.0)
            
            return identity
            
        except Exception as e:
            logger.error(f"Guest detection failed: {e}")
            return None
        
        finally:
            if g:
                try:
                    g.shutdown()
                except Exception:
                    pass
                try:
                    g.close()
                except Exception:
                    pass


def _emit_guest_identity_log(logger, identity: GuestIdentity) -> None:
    """
    Emit a formatted identity summary to logs.
    """
    if identity.type == GuestType.LINUX:
        logger.info(
            "🖥️  Guest Identity (Linux)\n"
            "     Detection Method: %s\n"
            "       Detection Confidence: %.1f%%\n"
            "     Static Hostname: %s\n"
            "          Machine ID: %s\n"
            "    Operating System: %s\n"
            "      OS Pretty Name: %s\n"
            "        OS Version: %s\n"
            "         CPE OS Name: %s\n"
            "      OS Support End: %s\n"
            "        Architecture: %s\n"
            "  Kernel Version: %s",
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
    elif identity.type == GuestType.WINDOWS:
        logger.info(
            "🪟 Guest Identity (Windows)\n"
            "     Detection Method: %s\n"
            "       Detection Confidence: %.1f%%\n"
            "    Operating System: %s\n"
            "        Architecture: %s\n"
            "      Windows Distro: %s\n"
            "      Version (Major): %s\n"
            "      Version (Minor): %s\n"
            "   Registry Hives Found: %s\n"
            "   Windows Dirs Found: %s",
            identity.detection_method,
            identity.confidence * 100,
            identity.os_name or "Windows",
            identity.architecture or "?",
            identity.windows_distro or "?",
            identity.windows_major or "?",
            identity.windows_minor or "?",
            str(len(identity.metadata.get("registry_hives", []))) if identity.metadata.get("registry_hives") else "0",
            str(len(identity.metadata.get("windows_dirs", []))) if identity.metadata.get("windows_dirs") else "0",
        )
    else:
        logger.info(
            "❓ Guest Identity (Unknown)\n"
            "     Detection Method: %s\n"
            "       Detection Confidence: %.1f%%\n"
            "     Detected Type: %s",
            identity.detection_method,
            identity.confidence * 100,
            identity.type.value,
        )


# --------------------------------------------------------------------------------------
# Original functions with improved detection integrated
# --------------------------------------------------------------------------------------

def _read_first_line(g: guestfs.GuestFS, path: str) -> Optional[str]:
    """Legacy function kept for compatibility."""
    try:
        if not g.is_file(path):
            return None
        return g.read_file(path).splitlines()[0].strip()
    except Exception:
        return None


def _parse_os_release(text: str) -> Dict[str, str]:
    """Legacy function kept for compatibility."""
    out: Dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        out[k.strip()] = v
    return out


def _best_effort_kernel(g: guestfs.GuestFS) -> Optional[str]:
    """Legacy function kept for compatibility."""
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


def _best_root(g: guestfs.GuestFS) -> Optional[str]:
    """
    Prefer a Windows root if present, else first root.
    """
    try:
        roots = g.inspect_os()
    except Exception:
        return None
    if not roots:
        return None
    for r in roots:
        try:
            t = (U.to_text(g.inspect_get_type(r)) or "").strip().lower()
            if t == "windows":
                return r
        except Exception:
            continue
    return roots[0]


def _mount_inspected_root(g: guestfs.GuestFS, root: str) -> None:
    """
    Mount all mountpoints for an inspected root, in increasing mountpoint length.
    """
    mps = g.inspect_get_mountpoints(root)
    for dev, mp in sorted(mps, key=lambda x: len(x[1])):
        g.mount(dev, mp)


def _collect_identity_linux(g: guestfs.GuestFS, root: str) -> Dict[str, Optional[str]]:
    """
    Linux-like identity summary that resembles `hostnamectl`, but derived purely offline.
    """
    _mount_inspected_root(g, root)

    osr_raw = g.read_file("/etc/os-release") if g.is_file("/etc/os-release") else ""
    osr = _parse_os_release(osr_raw)

    return {
        "static_hostname": _read_first_line(g, "/etc/hostname"),
        "machine_id": (_read_first_line(g, "/etc/machine-id") or _read_first_line(g, "/var/lib/dbus/machine-id")),
        "operating_system": osr.get("PRETTY_NAME") or osr.get("NAME"),
        "cpe_os_name": osr.get("CPE_NAME"),
        # Some distros carry these; often absent -> None.
        "os_support_end": osr.get("SUPPORT_END") or osr.get("SUPPORT_END_DATE"),
        "architecture": U.to_text(g.inspect_get_arch(root)),
        "kernel_installed": _best_effort_kernel(g),
    }


def _windows_info_best_effort(g: guestfs.GuestFS, root: str) -> Dict[str, Optional[str]]:
    """
    Windows-ish identity summary from guestfs inspection fields.
    (We intentionally do NOT parse registries here; keep emitter light.)
    """
    # Try to mount so the presence checks work consistently (optional).
    try:
        _mount_inspected_root(g, root)
    except Exception:
        pass

    prod = None
    arch = None
    major = None
    minor = None
    distro = None
    try:
        prod = U.to_text(g.inspect_get_product_name(root))
    except Exception:
        pass
    try:
        arch = U.to_text(g.inspect_get_arch(root))
    except Exception:
        pass
    try:
        major = str(g.inspect_get_major_version(root))
    except Exception:
        major = None
    try:
        minor = str(g.inspect_get_minor_version(root))
    except Exception:
        minor = None
    try:
        distro = U.to_text(g.inspect_get_distro(root))
    except Exception:
        pass

    # Machine ID does not exist in Windows like Linux; we can at least hint SYSTEM hive presence.
    system_hive = None
    for p in (
        "/Windows/System32/config/SYSTEM",
        "/WINDOWS/System32/config/SYSTEM",
        "/winnt/system32/config/SYSTEM",
    ):
        try:
            if g.is_file(p):
                system_hive = p
                break
        except Exception:
            continue

    return {
        "operating_system": prod or "Windows",
        "distro": distro,
        "architecture": arch,
        "major": major,
        "minor": minor,
        "system_hive": system_hive,
        "windows_dir_present": "true" if (g.is_dir("/Windows") or g.is_dir("/WINDOWS") or g.is_dir("/winnt")) else "false",
    }


def _emit_guest_identity_log_legacy(logger, kind: str, info: Dict[str, Optional[str]]) -> None:
    """
    Emit a nice "hostnamectl-like" block in logs, sourced from offline guest inspection.
    """
    # Keep this stable and readable; don't over-format with JSON unless asked.
    if kind == "linux":
        logger.info(
            " guest identity (linux)\n"
            "     Static hostname: %s\n"
            "          Machine ID: %s\n"
            "    Operating System: %s\n"
            "         CPE OS Name: %s\n"
            "      OS Support End: %s\n"
            "        Architecture: %s\n"
            "  Kernel (installed): %s",
            info.get("static_hostname") or "?",
            info.get("machine_id") or "?",
            info.get("operating_system") or "?",
            info.get("cpe_os_name") or "?",
            info.get("os_support_end") or "?",
            info.get("architecture") or "?",
            info.get("kernel_installed") or "?",
        )
    else:
        logger.info(
            " guest identity (windows)\n"
            "    Operating System: %s\n"
            "              Distro: %s\n"
            "        Architecture: %s\n"
            "      Version (maj): %s\n"
            "      Version (min): %s\n"
            "         SYSTEM hive: %s\n"
            "   Windows dir found: %s",
            info.get("operating_system") or "Windows",
            info.get("distro") or "?",
            info.get("architecture") or "?",
            info.get("major") or "?",
            info.get("minor") or "?",
            info.get("system_hive") or "?",
            info.get("windows_dir_present") or "?",
        )


@dataclass
class _WvShim:
    """
    windows_virtio.is_windows expects:
      - self.logger (optional)
      - self.inspect_root (required for strongest detection path)
    """
    logger: object
    inspect_root: Optional[str] = None


def _detect_guest_kind_with_guestfs(args: argparse.Namespace, img: Path, logger) -> Optional[str]:
    """
    Open guestfs read-only and detect guest kind.
    Also logs a hostnamectl-like identity summary from inside the guest.

    Returns "windows" / "linux" / None (if no roots).
    """
    g = guestfs.GuestFS(python_return_dict=True)
    try:
        g.add_drive_opts(str(img), readonly=1)
        g.launch()

        roots = g.inspect_os()
        if not roots:
            return None

        root = _best_root(g) or roots[0]

        # Canonical detection (your repo) when available
        kind: Optional[str] = None
        if _WIN_VIRTIO_DETECT_OK and _wv_is_windows is not None:
            shim = _WvShim(logger=logger, inspect_root=root)
            try:
                if bool(_wv_is_windows(shim, g)):  # type: ignore[misc]
                    kind = "windows"
                else:
                    kind = "linux"
            except Exception:
                kind = None

        # Fallback to inspect_get_type
        if kind is None:
            try:
                t = (U.to_text(g.inspect_get_type(root)) or "").strip().lower()
                if t in ("windows", "linux"):
                    kind = t
            except Exception:
                kind = None

        # Identity log (best-effort, depends on mounts)
        try:
            if kind == "windows":
                info = _windows_info_best_effort(g, root)
                _emit_guest_identity_log_legacy(logger, "windows", info)
            else:
                info = _collect_identity_linux(g, root)
                _emit_guest_identity_log_legacy(logger, "linux", info)
        except Exception:
            # never fail emission because identity couldn't be collected
            pass

        return kind
    finally:
        try:
            g.shutdown()
        except Exception:
            pass
        try:
            g.close()
        except Exception:
            pass


def _guess_guest_kind(args: argparse.Namespace, img: Path, logger) -> str:
    """
    Priority:
      1) explicit args.guest_os (linux/windows)
      2) explicit args.windows / args.win / args.is_windows booleans
      3) enhanced guestfs-based detection (uses windows_virtio.is_windows when available)
      4) heuristic fallback with improved pattern matching
      5) default: linux
    """
    # 1) Explicit command line arguments
    v = str(getattr(args, "guest_os", "") or "").strip().lower()
    if v in ("windows", "win"):
        logger.debug("Using explicit guest_os=windows from args")
        return "windows"
    if v in ("linux", "lin"):
        logger.debug("Using explicit guest_os=linux from args")
        return "linux"

    # 2) Boolean flags
    for b in ("windows", "win", "is_windows"):
        if bool(getattr(args, b, False)):
            logger.debug(f"Using {b}=True from args")
            return "windows"

    # 3) Enhanced guestfs-based detection
    identity = GuestDetector.detect(img, logger)
    if identity:
        _emit_guest_identity_log(logger, identity)
        if identity.type in (GuestType.WINDOWS, GuestType.LINUX):
            logger.debug(f"GuestFS detection: {identity.type.value} (confidence: {identity.confidence:.1%})")
            return identity.type.value
    
    # Fallback to legacy detection for compatibility
    k = _detect_guest_kind_with_guestfs(args, img, logger)
    if k in ("windows", "linux"):
        Log.trace(logger, "🧠 guest_kind (guestfs) -> %s", k)
        return k

    # 4) Improved heuristic fallback
    name = str(getattr(args, "vm_name", None) or getattr(args, "name", None) or img.stem).lower()
    stem = img.stem.lower()
    
    # More comprehensive filename pattern matching
    windows_patterns = [
        r'windows', r'win\d+', r'win-\d+', r'win_\d+', r'win\.',
        r'w2k', r'winxp', r'win7', r'win8', r'win10', r'win11',
        r'ws\d+', r'winserver', r'win-server'
    ]
    
    linux_patterns = [
        r'linux', r'ubuntu', r'debian', r'centos', r'redhat', r'fedora',
        r'arch', r'suse', r'sles', r'alpine', r'mint', r'gentoo'
    ]
    
    for pattern in windows_patterns:
        if re.search(pattern, name) or re.search(pattern, stem):
            logger.debug(f"Filename pattern match for Windows: {pattern}")
            return "windows"
    
    for pattern in linux_patterns:
        if re.search(pattern, name) or re.search(pattern, stem):
            logger.debug(f"Filename pattern match for Linux: {pattern}")
            return "linux"
    
    # 5) Default to Linux (safer assumption for KVM)
    logger.debug("No detection succeeded, defaulting to Linux")
    return "linux"


def _write_text(path: Path, s: str) -> None:
    """Safely write text to file with improved error handling."""
    try:
        U.ensure_dir(path.parent)
        path.write_text(s, encoding="utf-8")
        Log.trace(f"Written {len(s)} bytes to {path}")
    except Exception as e:
        Log.error(f"Failed to write to {path}: {e}")
        raise


def emit_from_args(
    logger,
    args: argparse.Namespace,
    *,
    out_root: Path,
    out_images: List[Path],
) -> Optional[Path]:
    """
    Policy: emit ONE domain (first image) unless you later add multi-domain support.

    Controlled by args (common):
      - emit_domain_xml: bool
      - virsh_define: bool (Linux emitter supports define; Windows emitter here writes XML only)
      - vm_name, memory, vcpus, uefi, headless, libvirt_network, graphics*, ovmf*
      - machine, disk_cache, out_format, net_model, video
      - cloudinit_iso/cloudinit_seed_iso (Linux only)

    Windows-specific knobs (optional):
      - win_stage: bootstrap|final (default bootstrap)
      - win_driver_iso / virtio_win_iso / driver_iso
      - win_localtime_clock: bool (default True)
      - win_hyperv: bool (default True)

    Returns the XML path if written, else None.
    """
    if not getattr(args, "emit_domain_xml", False):
        Log.trace(logger, "🧾 emit_domain_xml disabled")
        return None
    if not out_images:
        Log.trace(logger, "🧾 emit_domain_xml: no outputs")
        return None

    img = Path(out_images[0]).expanduser().resolve()
    name = str(getattr(args, "vm_name", None) or getattr(args, "name", None) or img.stem)

    domain_dir = out_root / "libvirt"
    U.ensure_dir(domain_dir)

    # Use enhanced guest detection
    guest_kind = _guess_guest_kind(args, img, logger)
    uefi = bool(getattr(args, "uefi", False))
    headless = bool(getattr(args, "headless", False))

    logger.info(" emit_domain_xml: guest=%s uefi=%s headless=%s name=%s image=%s", 
                guest_kind, uefi, headless, name, img)

    # default graphics policy:
    # - headless => none
    # - otherwise => spice unless user overrides
    graphics = "none"
    if not headless:
        graphics = str(getattr(args, "graphics", None) or "spice")

    # ---------------------------
    # WINDOWS
    # ---------------------------
    if guest_kind == "windows":
        if not _WIN_DOMAIN_OK or WinDomainSpec is None or render_windows_domain_xml is None:
            logger.warning("emit_domain_xml requested for Windows but windows_domain not available")
            return None

        Log.step(logger, "Emit libvirt domain XML (Windows)")

        stage = str(getattr(args, "win_stage", None) or getattr(args, "stage", None) or "bootstrap").strip().lower()
        if stage not in ("bootstrap", "final"):
            raise ValueError(f"invalid win_stage: {stage!r} (expected bootstrap|final)")

        driver_iso = (
            getattr(args, "win_driver_iso", None)
            or getattr(args, "virtio_win_iso", None)
            or getattr(args, "driver_iso", None)
        )

        win_graphics = "none" if headless else str(getattr(args, "graphics", None) or "spice")

        if stage == "bootstrap":
            logger.info("🪟 Windows stage=bootstrap: disk on SATA (first boot safety mode)")
            if driver_iso:
                logger.info("💿 VirtIO ISO provided; keep it attached while installing drivers in Windows.")
        else:
            logger.info("🪟 Windows stage=final: disk on VirtIO (requires VirtIO storage driver installed)")

        if driver_iso:
            logger.info("💿 VirtIO driver ISO: %s", driver_iso)
        else:
            logger.info("💿 VirtIO driver ISO: (not set)")

        spec = WinDomainSpec(  # type: ignore[misc]
            name=name,
            img_path=str(img),

            ovmf_code=str(getattr(args, "ovmf_code", "/usr/share/edk2/ovmf/OVMF_CODE.fd")),
            nvram_vars=str(getattr(args, "nvram_vars", "/var/tmp/VM_VARS.fd")),
            memory_mib=int(getattr(args, "memory", 8192)),
            vcpus=int(getattr(args, "vcpus", 4)),
            machine=str(getattr(args, "machine", "q35")),

            net_model=str(getattr(args, "net_model", "virtio")),

            video=str(getattr(args, "video", "qxl")),
            graphics=win_graphics,
            graphics_listen=str(getattr(args, "graphics_listen", "127.0.0.1")),

            disk_cache=str(getattr(args, "disk_cache", "none")),
            disk_type=str(getattr(args, "out_format", "qcow2")),

            driver_iso=str(driver_iso) if driver_iso else None,

            localtime_clock=bool(getattr(args, "win_localtime_clock", True)),
            hyperv=bool(getattr(args, "win_hyperv", True)),
        )

        xml = render_windows_domain_xml(spec, stage=stage)  # type: ignore[misc]
        xml_path = domain_dir / f"{name}.xml"
        _write_text(xml_path, xml)

        logger.info("🧩 Domain XML: %s", xml_path)
        return xml_path

    # ---------------------------
    # LINUX
    # ---------------------------
    if not _LINUX_DOMAIN_OK or emit_linux_domain is None:
        logger.warning("emit_domain_xml requested but libvirt linux_domain not available")
        return None

    cloudinit_iso = getattr(args, "cloudinit_iso", None) or getattr(args, "cloudinit_seed_iso", None)

    Log.step(logger, "Emit libvirt domain XML (Linux)")
    paths = emit_linux_domain(  # type: ignore[misc]
        name=name,
        image_path=img,
        out_dir=domain_dir,

        firmware=("uefi" if uefi else "bios"),
        memory_mib=int(getattr(args, "memory", 2048)),
        vcpus=int(getattr(args, "vcpus", 2)),
        machine=str(getattr(args, "machine", "q35")),

        disk_bus=str(getattr(args, "disk_bus", "virtio")),
        disk_dev=str(getattr(args, "disk_dev", "vda")),
        disk_type=str(getattr(args, "out_format", "qcow2")),
        disk_cache=str(getattr(args, "disk_cache", "none")),

        network=str(getattr(args, "libvirt_network", "default")),
        net_model=str(getattr(args, "net_model", "virtio")),

        graphics=graphics,
        graphics_listen=str(getattr(args, "graphics_listen", "127.0.0.1")),
        video=str(getattr(args, "video", "virtio")),
        usb_tablet=bool(getattr(args, "usb_tablet", True)),

        serial_pty=True,
        console_pty=True,

        cloudinit_iso=str(cloudinit_iso) if cloudinit_iso else None,
        clock=str(getattr(args, "clock", "utc")),

        ovmf_code=str(getattr(args, "ovmf_code", "/usr/share/edk2/ovmf/OVMF_CODE.fd")),
        nvram_vars=getattr(args, "nvram_vars", None),
        ovmf_vars_template=getattr(args, "ovmf_vars_template", None),

        write_xml=True,
        virsh_define=bool(getattr(args, "virsh_define", False)),
    )

    logger.info("🧩 Domain XML: %s", paths.xml_path)
    if paths.nvram_path:
        logger.info("🧬 NVRAM: %s", paths.nvram_path)
    return paths.xml_path