# SPDX-License-Identifier: LGPL-3.0-or-later
# vmdk2kvm/fixers/windows_registry.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import guestfs  # type: ignore
import hivex  # type: ignore

from ..core.utils import U

# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------


def _safe_logger(self) -> logging.Logger:
    lg = getattr(self, "logger", None)
    if isinstance(lg, logging.Logger):
        return lg
    return logging.getLogger("vmdk2kvm.windows_registry")


# ---------------------------------------------------------------------------
# Robust hive download helpers
# ---------------------------------------------------------------------------


def _is_probably_regf(path: Path) -> bool:
    """
    Windows registry hives start with ASCII 'regf' signature.
    Cheap corruption/truncation guardrail.
    """
    try:
        b = path.read_bytes()
        return len(b) >= 4 and b[:4] == b"regf"
    except Exception:
        return False


def _download_hive_local(logger: logging.Logger, g: guestfs.GuestFS, remote: str, local: Path) -> None:
    """
    Robustly download a hive from the guest to a local path.

    We've seen cases where g.download() does not materialize the local file
    (or produces an empty/truncated file) without raising. This helper:
      1) tries g.download()
      2) verifies local exists + size >= 4KiB + 'regf' signature
      3) falls back to g.read_file()/g.cat() and writes bytes locally
    """
    local.parent.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("Downloading hive: %r -> %r", remote, str(local))
        g.download(remote, str(local))
    except Exception as e:
        logger.warning("g.download(%r, %r) failed: %s", remote, str(local), e)

    try:
        if local.exists() and local.stat().st_size >= 4096 and _is_probably_regf(local):
            return
    except Exception:
        pass

    logger.warning("Hive not materialized after download; falling back to guestfs read: %r", remote)
    data: Optional[bytes] = None

    for fn_name in ("read_file", "cat"):
        fn = getattr(g, fn_name, None)
        if not callable(fn):
            continue
        try:
            out = fn(remote)
            if isinstance(out, (bytes, bytearray)):
                data = bytes(out)
            else:
                # guestfs bindings sometimes return str-ish
                data = str(out).encode("latin-1", errors="ignore")
            break
        except Exception as e:
            logger.warning("%s(%r) failed: %s", fn_name, remote, e)

    if not data or len(data) < 4096:
        raise RuntimeError(
            f"Failed to download hive locally: remote={remote} local={local} (len={len(data) if data else 0})"
        )

    local.write_bytes(data)

    if not local.exists() or local.stat().st_size < 4096:
        raise RuntimeError(f"Local hive still missing after fallback: {local}")

    if not _is_probably_regf(local):
        raise RuntimeError(f"Local hive downloaded but missing regf signature: {local}")


def _log_mountpoints_best_effort(logger: logging.Logger, g: guestfs.GuestFS) -> None:
    try:
        mps = g.mountpoints()
        logger.debug("guestfs mountpoints=%r", mps)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Windows mount + path resolution (CRITICAL for "ensure it's C:")
# ---------------------------------------------------------------------------


def _win_expected_paths() -> List[str]:
    return [
        "/Windows/System32/config/SYSTEM",
        "/Windows/System32/config/SOFTWARE",
        "/Windows/System32/cmd.exe",
    ]


def _guest_path_join(*parts: str) -> str:
    out = ""
    for p in parts:
        if not p:
            continue
        if not out:
            out = p
            continue
        out = out.rstrip("/") + "/" + p.lstrip("/")
    return out or "/"


def _looks_like_windows_root(g: guestfs.GuestFS) -> bool:
    for p in _win_expected_paths():
        try:
            if not g.is_file(p):
                return False
        except Exception:
            return False
    return True


def _mount_inspected_os_best_effort(logger: logging.Logger, g: guestfs.GuestFS) -> bool:
    """
    Canonical libguestfs mount recipe:
      roots = inspect_os()
      mps = inspect_get_mountpoints(root)
      mount in descending mountpoint-length order
    """
    try:
        roots = g.inspect_os()
    except Exception as e:
        logger.warning("inspect_os failed: %s", e)
        return False

    if not roots:
        logger.warning("inspect_os returned no roots")
        return False

    root = roots[0]
    try:
        mps = g.inspect_get_mountpoints(root)
    except Exception as e:
        logger.warning("inspect_get_mountpoints failed: %s", e)
        return False

    mps_sorted = sorted(mps, key=lambda x: len(x[0] or ""), reverse=True)

    try:
        g.umount_all()
    except Exception:
        pass

    for mp, dev in mps_sorted:
        try:
            g.mount(dev, mp)
            logger.debug("Mounted %s at %s", dev, mp)
        except Exception as e:
            logger.debug("Mount failed dev=%s mp=%s: %s", dev, mp, e)

    ok = False
    try:
        ok = _looks_like_windows_root(g)
    except Exception:
        ok = False

    if ok:
        logger.info("Windows root mounted correctly at / (contains /Windows/System32/config/*)")
    else:
        logger.warning("Mounted OS does not look like Windows at / (missing expected paths)")
    return ok


def _ensure_windows_root(logger: logging.Logger, g: guestfs.GuestFS, *, hint_hive_path: Optional[str] = None) -> None:
    """
    Ensure / is the Windows system volume (C: at runtime).

    Strategy:
      1) If / already looks like Windows and (optional) hint exists, accept.
      2) Otherwise, remount using inspect_os and require expected paths.
    """
    _log_mountpoints_best_effort(logger, g)

    looks = False
    try:
        looks = _looks_like_windows_root(g)
    except Exception:
        looks = False

    if looks:
        if hint_hive_path:
            try:
                if g.is_file(hint_hive_path):
                    return
            except Exception:
                pass
        else:
            return

    if _mount_inspected_os_best_effort(logger, g):
        if hint_hive_path:
            try:
                if g.is_file(hint_hive_path):
                    return
            except Exception:
                pass
        else:
            return

    try:
        fs = g.list_filesystems()
        logger.debug("list_filesystems=%r", fs)
    except Exception:
        pass
    raise RuntimeError("Unable to ensure Windows system volume is mounted at / (C: mapping uncertain)")


# ---------------------------------------------------------------------------
# Guest file helpers
# ---------------------------------------------------------------------------


def _mkdir_p_guest(logger: logging.Logger, g: guestfs.GuestFS, path: str) -> None:
    try:
        if g.is_dir(path):
            return
    except Exception:
        pass

    try:
        g.mkdir_p(path)
        logger.debug("Created guest dir: %s", path)
        return
    except Exception:
        pass

    cur = ""
    for comp in path.strip("/").split("/"):
        cur = "/" + comp if not cur else cur.rstrip("/") + "/" + comp
        try:
            if not g.is_dir(cur):
                g.mkdir(cur)
        except Exception:
            pass


def _upload_bytes(
    logger: logging.Logger,
    g: guestfs.GuestFS,
    guest_path: str,
    data: bytes,
    *,
    results: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Write bytes to a guest file using a local temp file + upload.
    Adds sha256 + size into results["uploaded_files"] if provided.
    """
    parent = str(Path(guest_path).parent).replace("\\", "/")
    _mkdir_p_guest(logger, g, parent)

    sha = hashlib.sha256(data).hexdigest()
    with tempfile.TemporaryDirectory() as td:
        lp = Path(td) / Path(guest_path).name
        lp.write_bytes(data)
        g.upload(str(lp), guest_path)

    try:
        st = g.statns(guest_path)
        sz = int(getattr(st, "st_size", 0) or 0)
    except Exception:
        sz = len(data)

    if results is not None:
        results.setdefault("uploaded_files", []).append({"guest_path": guest_path, "sha256": sha, "bytes": sz})
    logger.info("Uploaded guest file: %s (sha256=%s, bytes=%s)", guest_path, sha, sz)


def _encode_windows_cmd_script(text: str) -> bytes:
    """
    Encode .cmd in a Windows-friendly way (UTF-16LE + BOM).
    Also normalizes to CRLF.
    """
    t = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    return b"\xff\xfe" + t.encode("utf-16le", errors="replace")


# ---------------------------------------------------------------------------
# Hivex node normalization (IMPORTANT)
# ---------------------------------------------------------------------------

NodeLike = Union[int, None]


def _node_id(n: NodeLike) -> int:
    if n is None:
        return 0
    try:
        return int(n)
    except Exception:
        return 0


def _node_ok(n: NodeLike) -> bool:
    return _node_id(n) != 0


# ---------------------------------------------------------------------------
# Registry encoding helpers (CRITICAL)
# ---------------------------------------------------------------------------


def _reg_sz(s: str) -> bytes:
    return (s + "\0").encode("utf-16le", errors="ignore")


def _decode_reg_sz(raw: bytes) -> str:
    try:
        return raw.decode("utf-16le", errors="ignore").rstrip("\x00")
    except Exception:
        try:
            return raw.decode("utf-8", errors="ignore").rstrip("\x00")
        except Exception:
            return ""


def _mk_reg_value(name: str, t: int, value: bytes) -> Dict[str, Any]:
    return {"key": name, "t": int(t), "value": value}


def _set_sz(h: hivex.Hivex, node: NodeLike, key: str, s: str) -> None:
    nid = _node_id(node)
    if nid == 0:
        raise RuntimeError(f"invalid registry node for setting {key}=REG_SZ")
    h.node_set_value(nid, _mk_reg_value(key, 1, _reg_sz(s)))


def _set_expand_sz(h: hivex.Hivex, node: NodeLike, key: str, s: str) -> None:
    nid = _node_id(node)
    if nid == 0:
        raise RuntimeError(f"invalid registry node for setting {key}=REG_EXPAND_SZ")
    h.node_set_value(nid, _mk_reg_value(key, 2, _reg_sz(s)))


def _set_dword(h: hivex.Hivex, node: NodeLike, key: str, v: int) -> None:
    nid = _node_id(node)
    if nid == 0:
        raise RuntimeError(f"invalid registry node for setting {key}=REG_DWORD")
    h.node_set_value(nid, _mk_reg_value(key, 4, int(v).to_bytes(4, "little", signed=False)))


def _ensure_child(h: hivex.Hivex, parent: NodeLike, name: str) -> int:
    pid = _node_id(parent)
    if pid == 0:
        raise RuntimeError(f"invalid parent node while ensuring child {name}")

    ch = _node_id(h.node_get_child(pid, name))
    if ch == 0:
        ch = _node_id(h.node_add_child(pid, name))
    if ch == 0:
        raise RuntimeError(f"failed to create child key {name}")
    return ch


def _delete_child_if_exists(
    h: hivex.Hivex, parent: NodeLike, name: str, *, logger: Optional[logging.Logger] = None
) -> bool:
    pid = _node_id(parent)
    if pid == 0:
        return False

    child = _node_id(h.node_get_child(pid, name))
    if child == 0:
        return False

    tried: List[str] = []
    for args in ((pid, child), (pid, name), (child,)):
        tried.append(repr(args))
        try:
            h.node_delete_child(*args)  # type: ignore[misc]
            if logger:
                logger.debug("Deleted child key %r using node_delete_child%s", name, args)
            return True
        except Exception as e:
            if logger:
                logger.debug("node_delete_child%s failed for %r: %s", args, name, e)
            continue

    if logger:
        logger.warning("All node_delete_child signatures failed for %r (tried: %s)", name, ", ".join(tried))
    return False


def _hivex_read_value_dict(h: hivex.Hivex, node: NodeLike, key: str) -> Optional[Dict[str, Any]]:
    nid = _node_id(node)
    if nid == 0:
        return None
    try:
        v = h.node_get_value(nid, key)
        if not v or "value" not in v:
            return None
        return v
    except Exception:
        return None


def _hivex_read_sz(h: hivex.Hivex, node: NodeLike, key: str) -> Optional[str]:
    v = _hivex_read_value_dict(h, node, key)
    if not v:
        return None
    raw = v.get("value")
    if isinstance(raw, (bytes, bytearray)):
        s = _decode_reg_sz(bytes(raw)).strip()
        return s or None
    if raw is None:
        return None
    s2 = str(raw).strip()
    return s2 or None


def _hivex_read_dword(h: hivex.Hivex, node: NodeLike, key: str) -> Optional[int]:
    v = _hivex_read_value_dict(h, node, key)
    if not v:
        return None
    raw = v.get("value")
    if isinstance(raw, (bytes, bytearray)) and len(raw) >= 4:
        return int.from_bytes(bytes(raw)[:4], "little", signed=False)
    if isinstance(raw, int):
        return raw
    return None


def _detect_current_controlset(h: hivex.Hivex, root: NodeLike) -> str:
    r = _node_id(root)
    if r == 0:
        return "ControlSet001"

    select = _node_id(h.node_get_child(r, "Select"))
    if select == 0:
        return "ControlSet001"

    v = _hivex_read_value_dict(h, select, "Current")
    if not v:
        return "ControlSet001"

    cur_raw = v.get("value")
    if isinstance(cur_raw, (bytes, bytearray)) and len(cur_raw) >= 4:
        current_set = int.from_bytes(bytes(cur_raw)[:4], "little", signed=False)
    elif isinstance(cur_raw, int):
        current_set = int(cur_raw)
    else:
        current_set = 1

    return f"ControlSet{current_set:03d}"


# ---------------------------------------------------------------------------
# Hivex open helpers (LOCAL FILES ONLY)
# ---------------------------------------------------------------------------


def _open_hive_local(path: Path, *, write: bool) -> hivex.Hivex:
    if not path.exists():
        raise FileNotFoundError(f"hive local file missing: {path}")
    st = path.stat()
    if st.st_size < 4096:
        raise RuntimeError(f"hive local file too small ({st.st_size} bytes): {path}")
    if not _is_probably_regf(path):
        raise RuntimeError(f"hive local file does not look like regf hive: {path}")
    return hivex.Hivex(str(path), write=(1 if write else 0))


def _close_best_effort(h: Optional[hivex.Hivex]) -> None:
    if h is None:
        return
    try:
        if hasattr(h, "close") and callable(getattr(h, "close")):
            h.close()
            return
    except Exception:
        pass
    try:
        if hasattr(h, "hivex_close") and callable(getattr(h, "hivex_close")):
            h.hivex_close()
            return
    except Exception:
        pass


def _commit_best_effort(h: hivex.Hivex) -> None:
    if hasattr(h, "commit") and callable(getattr(h, "commit")):
        try:
            h.commit(None)  # type: ignore[arg-type]
            return
        except TypeError:
            h.commit()  # type: ignore[call-arg]
            return
        except Exception:
            pass

    if hasattr(h, "hivex_commit") and callable(getattr(h, "hivex_commit")):
        try:
            h.hivex_commit(None)  # type: ignore[arg-type]
            return
        except TypeError:
            h.hivex_commit()  # type: ignore[call-arg]
            return

    raise RuntimeError("python-hivex: no commit method found")


# ---------------------------------------------------------------------------
# Internal: normalize Driver values (fixes NoneType -> int errors)
# ---------------------------------------------------------------------------


def _driver_start_default(drv: Any, *, fallback: int = 3) -> int:
    st = getattr(drv, "start_type", None)

    if st is not None and hasattr(st, "value"):
        v = getattr(st, "value", None)
        if v is None:
            return int(fallback)
        try:
            return int(v)
        except Exception:
            return int(fallback)

    if st is None:
        return int(fallback)

    try:
        return int(st)
    except Exception:
        return int(fallback)


def _driver_type_norm(drv: Any) -> str:
    t = getattr(drv, "type", None)
    if t is None:
        return ""
    if hasattr(t, "value"):
        v = getattr(t, "value", None)
        if v is not None:
            return str(v)
    return str(t)


def _pci_id_normalize(pci_id: str) -> str:
    return str(pci_id).strip()


# ---------------------------------------------------------------------------
# First-boot mechanism: create a one-shot SERVICE (more reliable than RunOnce)
# ---------------------------------------------------------------------------

_DEFAULT_GUEST_DIR = "/vmdk2kvm"
_DEFAULT_DRIVER_STAGE_DIR = "/vmdk2kvm/drivers"
_DEFAULT_LOG_PATH = "/Windows/Temp/vmdk2kvm-firstboot.log"
_DEFAULT_MARKER_PATH = "/vmdk2kvm/firstboot.done"


def _service_imagepath_cmd(cmdline: str) -> str:
    return r"%SystemRoot%\System32\cmd.exe /c " + cmdline


def _add_firstboot_service_system_hive(
    self,
    g: guestfs.GuestFS,
    system_hive_path: str,
    *,
    service_name: str,
    display_name: str,
    cmdline: str,
    start: int = 2,  # AUTO_START
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create/update a Win32 service entry that executes once at boot.

    NOTE: This is a "command service" (ImagePath uses cmd.exe /c ...).
    Script must self-delete the service.
    """
    logger = _safe_logger(self)
    dry_run = bool(getattr(self, "dry_run", False))

    results: Dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "hive_path": system_hive_path,
        "service_name": service_name,
        "cmdline": cmdline,
        "errors": [],
        "notes": [],
        "verification": {},
    }

    _ensure_windows_root(logger, g, hint_hive_path=system_hive_path)

    try:
        if not g.is_file(system_hive_path):
            results["errors"].append(f"SYSTEM hive not found: {system_hive_path}")
            return results
    except Exception as e:
        results["errors"].append(f"Failed to stat hive {system_hive_path}: {e}")
        return results

    with tempfile.TemporaryDirectory() as td:
        local_hive = Path(td) / "SYSTEM"
        h: Optional[hivex.Hivex] = None
        try:
            _log_mountpoints_best_effort(logger, g)

            if not dry_run:
                ts = U.now_ts()
                backup_path = f"{system_hive_path}.vmdk2kvm.backup.{ts}"
                g.cp(system_hive_path, backup_path)
                results["hive_backup"] = backup_path

            _download_hive_local(logger, g, system_hive_path, local_hive)
            orig_hash = hashlib.sha256(local_hive.read_bytes()).hexdigest()

            h = _open_hive_local(local_hive, write=(not dry_run))
            root = _node_id(h.root())
            if root == 0:
                results["errors"].append("Invalid hivex root()")
                return results

            cs_name = _detect_current_controlset(h, root)
            cs = _node_id(h.node_get_child(root, cs_name))
            if cs == 0:
                cs_name = "ControlSet001"
                cs = _node_id(h.node_get_child(root, cs_name))
            if cs == 0:
                results["errors"].append("No usable ControlSet found (001/current)")
                return results

            services = _ensure_child(h, cs, "Services")
            svc = _node_id(h.node_get_child(services, service_name))
            action = "updated" if svc != 0 else "created"
            if svc == 0:
                svc = _node_id(h.node_add_child(services, service_name))
            if svc == 0:
                results["errors"].append(f"Failed to create Services\\{service_name}")
                return results

            _set_dword(h, svc, "Type", 0x10)  # SERVICE_WIN32_OWN_PROCESS
            _set_dword(h, svc, "Start", int(start))
            _set_dword(h, svc, "ErrorControl", 1)
            _set_expand_sz(h, svc, "ImagePath", _service_imagepath_cmd(cmdline))
            _set_sz(h, svc, "ObjectName", "LocalSystem")
            _set_sz(h, svc, "DisplayName", display_name)
            if description:
                _set_sz(h, svc, "Description", description)

            results["action"] = action
            results["controlset"] = cs_name

            if not dry_run:
                try:
                    _commit_best_effort(h)
                finally:
                    _close_best_effort(h)
                    h = None

                g.upload(str(local_hive), system_hive_path)

                with tempfile.TemporaryDirectory() as vtd:
                    vlocal = Path(vtd) / "SYSTEM_verify"
                    _download_hive_local(logger, g, system_hive_path, vlocal)
                    new_hash = hashlib.sha256(vlocal.read_bytes()).hexdigest()

                results["verification"] = {
                    "sha256_before": orig_hash,
                    "sha256_after": new_hash,
                    "changed": (new_hash != orig_hash),
                }
                results["success"] = True
            else:
                results["success"] = True

            results["notes"] += [
                f"Service created at HKLM\\SYSTEM\\{cs_name}\\Services\\{service_name}",
                "Service runs as LocalSystem at boot; script should self-delete via sc.exe delete (1060 == already removed).",
                "ImagePath written as REG_EXPAND_SZ to expand %SystemRoot% at runtime.",
            ]
            logger.info("Firstboot service %s: %s", action, service_name)
            return results

        except Exception as e:
            results["errors"].append(f"Firstboot service creation failed: {e}")
            return results
        finally:
            _close_best_effort(h)


# ---------------------------------------------------------------------------
# VMware Tools removal (firstboot script block)
# ---------------------------------------------------------------------------


def _vmware_tools_removal_cmd_block() -> str:
    return r"""
echo --- VMware Tools removal (best-effort) --- >> "%LOG%"

where powershell >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Continue';" ^
    "$keys=@(" ^
    "'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'," ^
    "'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'" ^
    ");" ^
    "$apps=Get-ItemProperty $keys -ErrorAction SilentlyContinue | Where-Object { ($_.DisplayName -match 'VMware Tools') -or ($_.Publisher -match 'VMware') };" ^
    "if(-not $apps){ 'No VMware Tools uninstall entry found (DisplayName/Publisher)' | Out-File -Append -Encoding ascii $env:LOG; exit 0 }" ^
    "foreach($a in $apps){" ^
    "  ('Found: ' + $a.DisplayName + ' [' + $a.Publisher + ']') | Out-File -Append -Encoding ascii $env:LOG;" ^
    "  $u=$a.QuietUninstallString; if(-not $u){ $u=$a.UninstallString };" ^
    "  if(-not $u){ 'No uninstall string' | Out-File -Append -Encoding ascii $env:LOG; continue }" ^
    "  ('UninstallString: ' + $u) | Out-File -Append -Encoding ascii $env:LOG;" ^
    "  try {" ^
    "    if($u -match 'msiexec'){ if($u -notmatch '/qn'){ $u += ' /qn' }; if($u -notmatch '/norestart'){ $u += ' /norestart' } }" ^
    "    $p=Start-Process -FilePath 'cmd.exe' -ArgumentList ('/c ' + $u) -Wait -PassThru;" ^
    "    ('rc=' + $p.ExitCode) | Out-File -Append -Encoding ascii $env:LOG;" ^
    "  } catch { $_ | Out-File -Append -Encoding ascii $env:LOG }" ^
    "}" ^
    >> "%LOG%" 2>&1
) else (
  echo powershell not available; skipping VMware Tools uninstall via registry >> "%LOG%"
)

echo --- VMware services stop/delete (best-effort) --- >> "%LOG%"
for %%S in (VMTools VGAuthService vmvss vmware-aliases vmtoolsd) do (
  sc.exe query "%%S" >> "%LOG%" 2>&1
  if %ERRORLEVEL%==0 (
    sc.exe stop "%%S" >> "%LOG%" 2>&1
    sc.exe delete "%%S" >> "%LOG%" 2>&1
  )
)

echo --- VMware driver/services disable (best-effort) --- >> "%LOG%"
for %%D in (vm3dmp vmmouse vmusbmouse vmxnet3 vmhgfs vmci vmscsi pvscsi) do (
  reg query "HKLM\SYSTEM\CurrentControlSet\Services\%%D" >> "%LOG%" 2>&1
  if %ERRORLEVEL%==0 (
    reg add "HKLM\SYSTEM\CurrentControlSet\Services\%%D" /v Start /t REG_DWORD /d 4 /f >> "%LOG%" 2>&1
  )
)

echo --- VMware Tools directory cleanup (best-effort but deterministic) --- >> "%LOG%"
for %%D in (
  "%ProgramFiles%\VMware\VMware Tools"
  "%ProgramFiles(x86)%\VMware\VMware Tools"
) do (
  if exist "%%~D" (
    echo Removing %%~D >> "%LOG%"
    dir /s /b "%%~D" >> "%LOG%" 2>&1
    takeown /f "%%~D" /r /d y >> "%LOG%" 2>&1
    icacls "%%~D" /grant Administrators:F /t >> "%LOG%" 2>&1
    rmdir /s /q "%%~D" >> "%LOG%" 2>&1
    if exist "%%~D" (
      echo WARN: directory still exists after rmdir: %%~D >> "%LOG%"
    ) else (
      echo OK: removed %%~D >> "%LOG%"
    )
  )
)
"""


# ---------------------------------------------------------------------------
# Firstboot provisioning: refactored into small helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FirstbootPolicyPaths:
    guest_dir: str = _DEFAULT_GUEST_DIR
    driver_stage_dir: str = _DEFAULT_DRIVER_STAGE_DIR
    log_path: str = _DEFAULT_LOG_PATH
    marker_path: str = _DEFAULT_MARKER_PATH

    def as_dict(self) -> Dict[str, str]:
        return {
            "guest_dir": self.guest_dir,
            "driver_stage_dir": self.driver_stage_dir,
            "log_path": self.log_path,
            "marker_path": self.marker_path,
        }


@dataclass(frozen=True)
class _FirstbootWinPaths:
    win_guest_dir: str
    win_stage_dir: str
    win_log: str
    win_marker: str


def _enforce_firstboot_policy_paths(
    guest_dir: str,
    driver_stage_dir: str,
    log_path: str,
    marker_path: str,
    *,
    notes: List[str],
) -> _FirstbootPolicyPaths:
    gd = guest_dir
    sd = driver_stage_dir
    lp = log_path
    mp = marker_path

    if gd.rstrip("/") != _DEFAULT_GUEST_DIR:
        notes.append(f"guest_dir overridden to {_DEFAULT_GUEST_DIR} for stability (was {gd})")
        gd = _DEFAULT_GUEST_DIR
    if sd.rstrip("/") != _DEFAULT_DRIVER_STAGE_DIR:
        notes.append(f"driver_stage_dir overridden to {_DEFAULT_DRIVER_STAGE_DIR} for stability (was {sd})")
        sd = _DEFAULT_DRIVER_STAGE_DIR
    if lp.rstrip("/") != _DEFAULT_LOG_PATH:
        notes.append(f"log_path overridden to {_DEFAULT_LOG_PATH} for stability (was {lp})")
        lp = _DEFAULT_LOG_PATH
    if mp.rstrip("/") != _DEFAULT_MARKER_PATH:
        notes.append(f"marker_path overridden to {_DEFAULT_MARKER_PATH} for stability (was {mp})")
        mp = _DEFAULT_MARKER_PATH

    return _FirstbootPolicyPaths(guest_dir=gd, driver_stage_dir=sd, log_path=lp, marker_path=mp)


def _firstboot_windows_paths(service_name: str) -> _FirstbootWinPaths:
    # Windows runtime paths aligned with policy guestfs paths:
    #   guestfs /vmdk2kvm        -> Windows C:\vmdk2kvm
    #   guestfs /vmdk2kvm/drivers-> Windows C:\vmdk2kvm\drivers
    #   guestfs /Windows/Temp/...-> Windows C:\Windows\Temp\...
    win_guest_dir = r"%SystemDrive%\vmdk2kvm"
    win_stage_dir = fr"{win_guest_dir}\drivers"
    win_log = r"%SystemRoot%\Temp\vmdk2kvm-firstboot.log"
    win_marker = fr"{win_guest_dir}\firstboot.done"
    _ = service_name  # kept for future shaping (service name is in script variables)
    return _FirstbootWinPaths(
        win_guest_dir=win_guest_dir,
        win_stage_dir=win_stage_dir,
        win_log=win_log,
        win_marker=win_marker,
    )


def _firstboot_extra_cmd_block(extra_cmd: Optional[str]) -> str:
    if not extra_cmd:
        return ""
    # Keep this as "call ..." because user might pass a .cmd/.bat path.
    return (
        "\r\n"
        "echo ==== EXTRA CMD BEGIN ====>> \"%LOG%\"\r\n"
        f"call {extra_cmd} >> \"%LOG%\" 2>&1\r\n"
        "echo ==== EXTRA CMD END ====>> \"%LOG%\"\r\n"
    )


def _firstboot_build_cmd_script(
    *,
    service_name: str,
    win: _FirstbootWinPaths,
    include_vmware_removal: bool,
    extra_cmd: Optional[str],
) -> str:
    extra = _firstboot_extra_cmd_block(extra_cmd)

    vmware_block = ""
    if include_vmware_removal:
        vmware_block = _vmware_tools_removal_cmd_block().strip() + "\r\n"

    # NOTE: This is a “pure string builder”; no guestfs/hivex side effects.
    return rf"""@echo off
setlocal EnableExtensions EnableDelayedExpansion

set LOG={win.win_log}
set SVC={service_name}
set STAGE={win.win_stage_dir}
set MARKER={win.win_marker}

rem ---- idempotency guard ----
if exist "%MARKER%" (
  echo vmdk2kvm firstboot marker exists: %MARKER%>> "%LOG%"
  echo Exiting without doing work.>> "%LOG%"
  exit /b 0
)

echo ==================================================>> "%LOG%"
echo vmdk2kvm firstboot starting at %DATE% %TIME%>> "%LOG%"
echo ComputerName=%COMPUTERNAME%>> "%LOG%"
echo SystemDrive=%SystemDrive%>> "%LOG%"
echo SystemRoot=%SystemRoot%>> "%LOG%"
echo StageDir=%STAGE%>> "%LOG%"

echo --- Disk / Volume sanity --- >> "%LOG%"
where wmic >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  wmic logicaldisk get deviceid,volumename,filesystem,freespace,size >> "%LOG%" 2>&1
) else (
  echo wmic not available >> "%LOG%"
)

echo --- Ensure stage exists --- >> "%LOG%"
if not exist "%STAGE%" (
  echo Stage dir missing: %STAGE%>> "%LOG%"
) else (
  dir /s /b "%STAGE%" >> "%LOG%" 2>&1
)

echo --- Install staged drivers (INF) --- >> "%LOG%"
where pnputil >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  for /f "delims=" %%I in ('dir /b /s "%STAGE%\*.inf" 2^>nul') do (
    echo Installing %%I >> "%LOG%"
    pnputil /add-driver "%%I" /install >> "%LOG%" 2>&1
    echo pnputil rc=!ERRORLEVEL!>> "%LOG%"
  )
) else (
  echo pnputil not found; cannot install INF drivers >> "%LOG%"
)

{vmware_block}
{extra}

echo --- Write marker (done) --- >> "%LOG%"
echo done at %DATE% %TIME%> "%MARKER%" 2>> "%LOG%"
if exist "%MARKER%" (
  echo Marker written: %MARKER%>> "%LOG%"
) else (
  echo WARN: failed to write marker: %MARKER%>> "%LOG%"
)

echo --- Cleanup / self-delete service --- >> "%LOG%"
where sc.exe >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  echo Deleting service %SVC% (1060 == already removed) >> "%LOG%"
  sc.exe stop "%SVC%" >> "%LOG%" 2>&1
  sc.exe delete "%SVC%" >> "%LOG%" 2>&1
  echo Service delete attempted (1060 == OK) >> "%LOG%"
) else (
  echo sc.exe not found; cannot delete service >> "%LOG%"
)

echo vmdk2kvm firstboot completed at %DATE% %TIME%>> "%LOG%"
echo ==================================================>> "%LOG%"

endlocal
exit /b 0
"""


def _firstboot_create_guest_dirs(logger: logging.Logger, g: guestfs.GuestFS, policy: _FirstbootPolicyPaths) -> None:
    _mkdir_p_guest(logger, g, policy.guest_dir)
    _mkdir_p_guest(logger, g, str(Path(policy.log_path).parent).replace("\\", "/"))
    _mkdir_p_guest(logger, g, policy.driver_stage_dir)


def _firstboot_upload_payload(
    logger: logging.Logger,
    g: guestfs.GuestFS,
    *,
    policy: _FirstbootPolicyPaths,
    script_text: str,
    results: Dict[str, Any],
    dry_run: bool,
) -> str:
    guest_firstboot = _guest_path_join(policy.guest_dir, "firstboot.cmd")
    if not dry_run:
        _upload_bytes(logger, g, guest_firstboot, _encode_windows_cmd_script(script_text), results=results)
    return guest_firstboot


def _firstboot_service_cmdline(win_guest_dir: str) -> str:
    # Run from C:\vmdk2kvm\firstboot.cmd (quoted)
    return fr'"{win_guest_dir}\firstboot.cmd"'


def provision_firstboot_payload_and_service(
    self,
    g: guestfs.GuestFS,
    *,
    system_hive_path: str = "/Windows/System32/config/SYSTEM",
    service_name: str = "vmdk2kvm-firstboot",
    guest_dir: str = _DEFAULT_GUEST_DIR,
    log_path: str = _DEFAULT_LOG_PATH,
    driver_stage_dir: str = _DEFAULT_DRIVER_STAGE_DIR,
    extra_cmd: Optional[str] = None,
    remove_vmware_tools: bool = False,
    marker_path: str = _DEFAULT_MARKER_PATH,
) -> Dict[str, Any]:
    """
    End-to-end firstboot provisioning (policy-driven paths for stability):
      1) Ensure Windows system volume is mounted as / (C: mapping)
      2) Upload firstboot.cmd to /vmdk2kvm/firstboot.cmd
      3) Create a service that runs it at boot (LocalSystem)
      4) Record uploads (sha256 + bytes)

    NOTE: guest_dir/log_path/driver_stage_dir/marker_path are policy paths.
    If callers pass different values, we override them (and record a note) to
    prevent Windows runtime paths from diverging from guestfs paths.
    """
    logger = _safe_logger(self)
    dry_run = bool(getattr(self, "dry_run", False))

    results: Dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "errors": [],
        "notes": [],
        "uploaded_files": [],
        "service": None,
        "payload": None,
        "paths": {},
        "remove_vmware_tools": bool(remove_vmware_tools),
    }

    # 1) Enforce stable guest paths (policy)
    policy = _enforce_firstboot_policy_paths(
        guest_dir=guest_dir,
        driver_stage_dir=driver_stage_dir,
        log_path=log_path,
        marker_path=marker_path,
        notes=results["notes"],
    )
    results["paths"] = policy.as_dict()

    # 2) Ensure correct Windows root mount (C: mapping)
    try:
        _ensure_windows_root(logger, g, hint_hive_path=system_hive_path)
    except Exception as e:
        results["errors"].append(str(e))
        return results

    # 3) Create guest directories
    try:
        _firstboot_create_guest_dirs(logger, g, policy)
    except Exception as e:
        results["errors"].append(f"Failed to create guest dirs: {e}")
        return results

    # 4) Build script + upload
    win = _firstboot_windows_paths(service_name)
    script = _firstboot_build_cmd_script(
        service_name=service_name,
        win=win,
        include_vmware_removal=bool(remove_vmware_tools),
        extra_cmd=extra_cmd,
    )
    try:
        guest_script_path = _firstboot_upload_payload(
            logger,
            g,
            policy=policy,
            script_text=script,
            results=results,
            dry_run=dry_run,
        )
        results["payload"] = {
            "guest_path": guest_script_path,
            "log_path": policy.log_path,
            "marker_path": policy.marker_path,
        }
    except Exception as e:
        results["errors"].append(f"Failed to upload firstboot.cmd: {e}")
        return results

    # 5) Add service in SYSTEM hive
    cmdline = _firstboot_service_cmdline(win.win_guest_dir)
    svc_res = _add_firstboot_service_system_hive(
        self,
        g,
        system_hive_path,
        service_name=service_name,
        display_name="vmdk2kvm First Boot Driver Installer",
        cmdline=cmdline,
        start=2,
        description="One-shot first boot installer for vmdk2kvm staged drivers; writes log to Windows\\Temp.",
    )
    results["service"] = svc_res
    if not svc_res.get("success"):
        results["errors"].extend(svc_res.get("errors", []))
        return results

    # 6) Notes + success
    results["notes"] += [
        "Firstboot uses a SERVICE (LocalSystem) instead of RunOnce: less fragile across logon/autologon quirks.",
        "Log file will be at C:\\Windows\\Temp\\vmdk2kvm-firstboot.log (guestfs: /Windows/Temp/vmdk2kvm-firstboot.log).",
        "Drivers must be staged under C:\\vmdk2kvm\\drivers (guestfs: /vmdk2kvm/drivers).",
        "A completion marker is written to C:\\vmdk2kvm\\firstboot.done to avoid reruns if the service delete fails.",
        "uploaded_files includes sha256+size so you can prove what landed on disk.",
    ]
    if remove_vmware_tools:
        results["notes"].append(
            "VMware Tools removal enabled: firstboot will attempt registry-based uninstall + stop/delete services "
            "+ disable drivers + remove Tools dirs (best-effort)."
        )

    results["success"] = True
    return results


# ---------------------------------------------------------------------------
# Public: SYSTEM hive edit (Services + CDD + StartOverride)
# ---------------------------------------------------------------------------


def _hive_backup_best_effort(
    logger: logging.Logger,
    g: guestfs.GuestFS,
    hive_path: str,
    *,
    dry_run: bool,
    results: Dict[str, Any],
) -> None:
    if dry_run:
        return
    ts = U.now_ts()
    backup_path = f"{hive_path}.vmdk2kvm.backup.{ts}"
    g.cp(hive_path, backup_path)
    logger.info("Hive backup created: %s", backup_path)
    results["hive_backup"] = backup_path


def _open_system_hive_local_for_edit(
    logger: logging.Logger,
    g: guestfs.GuestFS,
    hive_path: str,
    *,
    dry_run: bool,
    local_hive: Path,
) -> Dict[str, Any]:
    _download_hive_local(logger, g, hive_path, local_hive)
    return {"sha256_before": hashlib.sha256(local_hive.read_bytes()).hexdigest()}


def _resolve_controlset_node(h: hivex.Hivex, root: int, *, logger: logging.Logger) -> Dict[str, Any]:
    cs_name = _detect_current_controlset(h, root)
    logger.info("Using control set: %s", cs_name)

    cs = _node_id(h.node_get_child(root, cs_name))
    if cs == 0:
        logger.warning("%s missing; falling back to ControlSet001", cs_name)
        cs_name = "ControlSet001"
        cs = _node_id(h.node_get_child(root, cs_name))
        if cs == 0:
            raise RuntimeError("No usable ControlSet found (001/current)")
    return {"controlset_name": cs_name, "controlset_node": cs}


def _service_group_for_driver_type(drv_type_value: str, *, storage_type_norm: str) -> str:
    if str(drv_type_value) == storage_type_norm:
        return "SCSI miniport"
    if str(drv_type_value) == "network":
        return "NDIS"
    return "System Bus Extender"


def _edit_system_services(
    logger: logging.Logger,
    h: hivex.Hivex,
    services_node: int,
    drivers: List[Any],
    *,
    storage_type_norm: str,
    boot_start_value: int,
    results: Dict[str, Any],
) -> None:
    for drv in drivers:
        try:
            drv_type_value = _driver_type_norm(drv)
            svc_name = str(getattr(drv, "service_name"))
            dest_name = str(getattr(drv, "dest_name"))

            start_default = _driver_start_default(drv, fallback=3)
            svc = _node_id(h.node_get_child(services_node, svc_name))
            action = "updated" if svc != 0 else "created"
            if svc == 0:
                svc = _node_id(h.node_add_child(services_node, svc_name))
            if svc == 0:
                raise RuntimeError(f"failed to open/create service key {svc_name}")

            logger.info("Registry service %s: Services\\%s", action, svc_name)

            _set_dword(h, svc, "Type", 1)  # SERVICE_KERNEL_DRIVER
            _set_dword(h, svc, "ErrorControl", 1)

            start = int(start_default)
            if str(drv_type_value) == storage_type_norm:
                start = int(boot_start_value)
            _set_dword(h, svc, "Start", start)

            group = _service_group_for_driver_type(str(drv_type_value), storage_type_norm=storage_type_norm)
            _set_sz(h, svc, "Group", group)
            _set_sz(h, svc, "ImagePath", fr"\SystemRoot\System32\drivers\{dest_name}")
            _set_sz(h, svc, "DisplayName", svc_name)

            removed = _delete_child_if_exists(h, svc, "StartOverride", logger=logger)
            if removed:
                logger.info("Removed StartOverride: Services\\%s\\StartOverride", svc_name)
                results["startoverride_removed"].append(svc_name)

            results["services"].append(
                {
                    "service": svc_name,
                    "type": drv_type_value,
                    "start": start,
                    "group": group,
                    "image": fr"\SystemRoot\System32\drivers\{dest_name}",
                    "action": action,
                }
            )
        except Exception as e:
            msg = f"Failed to create/update service {getattr(drv, 'service_name', '?')}: {e}"
            logger.error(msg)
            results["errors"].append(msg)


def _edit_system_cdd(
    logger: logging.Logger,
    h: hivex.Hivex,
    controlset_node: int,
    drivers: List[Any],
    *,
    storage_type_norm: str,
    results: Dict[str, Any],
) -> None:
    control = _ensure_child(h, controlset_node, "Control")
    cdd = _ensure_child(h, control, "CriticalDeviceDatabase")

    for drv in drivers:
        drv_type_value = _driver_type_norm(drv)
        if str(drv_type_value) != storage_type_norm:
            continue

        svc_name = str(getattr(drv, "service_name"))
        class_guid = str(getattr(drv, "class_guid"))
        dev_name = str(getattr(drv, "name"))

        pci_ids = list(getattr(drv, "pci_ids", []) or [])
        for pci_id in pci_ids:
            pci_id = _pci_id_normalize(pci_id)
            if not pci_id:
                continue
            try:
                node = _node_id(h.node_get_child(cdd, pci_id))
                action = "updated" if node != 0 else "created"
                if node == 0:
                    node = _node_id(h.node_add_child(cdd, pci_id))
                if node == 0:
                    raise RuntimeError(f"failed to open/create CDD node {pci_id}")

                _set_sz(h, node, "Service", svc_name)
                _set_sz(h, node, "ClassGUID", class_guid)
                _set_sz(h, node, "Class", "SCSIAdapter")
                _set_sz(h, node, "DeviceDesc", dev_name)

                logger.info("CDD %s: %s -> %s", action, pci_id, svc_name)
                results["cdd"].append({"pci_id": pci_id, "service": svc_name, "action": action})
            except Exception as e:
                msg = f"Failed CDD entry {pci_id} -> {svc_name}: {e}"
                logger.error(msg)
                results["errors"].append(msg)


def _upload_hive_and_verify(
    logger: logging.Logger,
    g: guestfs.GuestFS,
    hive_path: str,
    local_hive: Path,
    *,
    results: Dict[str, Any],
    sha_before: str,
) -> None:
    logger.info("Uploading modified hive back to guest: %s", hive_path)
    g.upload(str(local_hive), hive_path)

    try:
        results.setdefault("uploaded_files", []).append(
            {"guest_path": hive_path, "sha256_local": hashlib.sha256(local_hive.read_bytes()).hexdigest()}
        )
    except Exception:
        pass

    with tempfile.TemporaryDirectory() as verify_tmp:
        verify_path = Path(verify_tmp) / "HIVE_verify"
        _download_hive_local(logger, g, hive_path, verify_path)
        sha_after = hashlib.sha256(verify_path.read_bytes()).hexdigest()

    results["verification"] = {
        "sha256_before": sha_before,
        "sha256_after": sha_after,
        "changed": (sha_after != sha_before),
    }


def _verify_services_post_write(
    logger: logging.Logger,
    g: guestfs.GuestFS,
    hive_path: str,
    *,
    cs_name: str,
    drivers: List[Any],
    storage_type_norm: str,
    boot_start_value: int,
    results: Dict[str, Any],
) -> None:
    # Best-effort verification: download the hive again, open read-only, and check Start values exist.
    with tempfile.TemporaryDirectory() as verify_dir:
        verify_hive = Path(verify_dir) / "SYSTEM_verify"
        _download_hive_local(logger, g, hive_path, verify_hive)

        vh: Optional[hivex.Hivex] = None
        try:
            vh = _open_hive_local(verify_hive, write=False)
            vroot = _node_id(vh.root())
            vcs = _node_id(vh.node_get_child(vroot, cs_name))
            if vcs == 0:
                vcs = _node_id(vh.node_get_child(vroot, "ControlSet001"))
            vservices = _node_id(vh.node_get_child(vcs, "Services")) if vcs != 0 else 0

            if vservices == 0:
                results["verification_errors"].append("Verification failed: Services node missing")
                return

            for drv in drivers:
                svc_name = str(getattr(drv, "service_name"))
                drv_type_value = _driver_type_norm(drv)
                start_default = _driver_start_default(drv, fallback=3)

                svc = _node_id(vh.node_get_child(vservices, svc_name))
                if svc == 0:
                    results["verification_errors"].append(f"Missing service after edit: {svc_name}")
                    continue

                got = _hivex_read_dword(vh, svc, "Start")
                expected = int(start_default)
                if str(drv_type_value) == storage_type_norm:
                    expected = int(boot_start_value)

                if got == expected:
                    results["verified_services"].append(svc_name)
                else:
                    results["verification_errors"].append(f"{svc_name} Start mismatch: got={got} expected={expected}")
        finally:
            _close_best_effort(vh)


def edit_system_hive(
    self,
    g: guestfs.GuestFS,
    hive_path: str,
    drivers: List[Any],
    *,
    driver_type_storage_value: str,
    boot_start_value: int,
) -> Dict[str, Any]:
    """
    Edit SYSTEM hive offline to:
      - Create Services\\<driver> keys with correct Type/Start/ImagePath/Group
      - Add CriticalDeviceDatabase entries for STORAGE drivers
      - Remove StartOverride keys that frequently disable boot drivers
    """
    logger = _safe_logger(self)
    dry_run = bool(getattr(self, "dry_run", False))

    results: Dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "registry_modified": False,
        "hive_path": hive_path,
        "errors": [],
        "services": [],
        "cdd": [],
        "startoverride_removed": [],
        "notes": [],
        "verified_services": [],
        "verification_errors": [],
        "uploaded_files": [],
        "verification": {},
    }

    try:
        _ensure_windows_root(logger, g, hint_hive_path=hive_path)
    except Exception as e:
        results["errors"].append(str(e))
        return results

    try:
        if not g.is_file(hive_path):
            results["errors"].append(f"SYSTEM hive not found: {hive_path}")
            return results
    except Exception as e:
        results["errors"].append(f"Failed to stat hive {hive_path}: {e}")
        return results

    with tempfile.TemporaryDirectory() as tmpdir:
        local_hive = Path(tmpdir) / "SYSTEM"
        h: Optional[hivex.Hivex] = None

        try:
            _log_mountpoints_best_effort(logger, g)
            _hive_backup_best_effort(logger, g, hive_path, dry_run=dry_run, results=results)

            meta = _open_system_hive_local_for_edit(logger, g, hive_path, dry_run=dry_run, local_hive=local_hive)
            sha_before = str(meta.get("sha256_before") or "")

            h = _open_hive_local(local_hive, write=(not dry_run))
            root = _node_id(h.root())
            if root == 0:
                raise RuntimeError("python-hivex root() returned invalid node")

            cs = _resolve_controlset_node(h, root, logger=logger)
            cs_name = str(cs["controlset_name"])
            control_set = int(cs["controlset_node"])

            services = _ensure_child(h, control_set, "Services")
            storage_type_norm = str(driver_type_storage_value)

            _edit_system_services(
                logger,
                h,
                services,
                drivers,
                storage_type_norm=storage_type_norm,
                boot_start_value=int(boot_start_value),
                results=results,
            )
            _edit_system_cdd(
                logger,
                h,
                control_set,
                drivers,
                storage_type_norm=storage_type_norm,
                results=results,
            )

            if not dry_run:
                try:
                    logger.info("Committing SYSTEM hive changes (python-hivex commit)")
                    _commit_best_effort(h)
                finally:
                    _close_best_effort(h)
                    h = None

                _upload_hive_and_verify(logger, g, hive_path, local_hive, results=results, sha_before=sha_before)
                results["registry_modified"] = bool(results.get("verification", {}).get("changed", False))

                _verify_services_post_write(
                    logger,
                    g,
                    hive_path,
                    cs_name=cs_name,
                    drivers=drivers,
                    storage_type_norm=storage_type_norm,
                    boot_start_value=int(boot_start_value),
                    results=results,
                )
            else:
                logger.info("Dry-run: registry edits computed but not committed/uploaded")

            results["success"] = len(results["errors"]) == 0
            results["notes"] += [
                "Windows root is validated/remounted to ensure C: mapping (prevents writing to wrong partition).",
                "Storage services forced to BOOT start to prevent INACCESSIBLE_BOOT_DEVICE.",
                "StartOverride keys removed (if present) because they can silently disable drivers.",
                "Registry strings written as UTF-16LE REG_SZ/REG_EXPAND_SZ (Windows-correct).",
                "CriticalDeviceDatabase populated for storage PCI IDs.",
                "Node ids normalized across python-hivex versions (0 vs None).",
                "Driver start_type None handled with fallback Start=3 (demand).",
                "Driver type comparisons normalized via _driver_type_norm().",
                "Hive integrity checked via size + 'regf' signature during downloads.",
            ]
            return results

        except Exception as e:
            msg = f"Registry editing failed: {e}"
            logger.error(msg)
            results["errors"].append(msg)
            return results
        finally:
            _close_best_effort(h)


# ---------------------------------------------------------------------------
# Public: SYSTEM hive generic DWORD setter (for CrashControl etc.)
# ---------------------------------------------------------------------------


def _resolve_controlset_for_path(h: hivex.Hivex, root: int) -> Dict[str, Any]:
    cs_name = _detect_current_controlset(h, root)
    cs = _node_id(h.node_get_child(root, cs_name))
    if cs == 0:
        cs_name = "ControlSet001"
        cs = _node_id(h.node_get_child(root, cs_name))
    if cs == 0:
        raise RuntimeError("No usable ControlSet found (001/current)")
    return {"controlset_name": cs_name, "controlset_node": cs}


def _ensure_key_path(h: hivex.Hivex, start_node: int, key_path: List[str]) -> int:
    node = int(start_node)
    for comp in key_path:
        node = _ensure_child(h, node, comp)
    return node


def set_system_dword(
    self,
    g: guestfs.GuestFS,
    hive_path: str,
    *,
    key_path: List[str],
    name: str,
    value: int,
) -> Dict[str, Any]:
    logger = _safe_logger(self)
    dry_run = bool(getattr(self, "dry_run", False))

    out: Dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "hive_path": hive_path,
        "key_path": list(key_path),
        "name": name,
        "value": int(value),
        "modified": False,
        "original": None,
        "new": None,
        "errors": [],
        "notes": [],
        "uploaded_files": [],
        "verification": {},
    }

    try:
        _ensure_windows_root(logger, g, hint_hive_path=hive_path)
    except Exception as e:
        out["errors"].append(str(e))
        return out

    try:
        if not g.is_file(hive_path):
            out["errors"].append(f"SYSTEM hive not found: {hive_path}")
            return out
    except Exception as e:
        out["errors"].append(f"Failed to stat hive {hive_path}: {e}")
        return out

    with tempfile.TemporaryDirectory() as td:
        local = Path(td) / "SYSTEM"
        h: Optional[hivex.Hivex] = None
        try:
            _log_mountpoints_best_effort(logger, g)
            _hive_backup_best_effort(logger, g, hive_path, dry_run=dry_run, results=out)

            _download_hive_local(logger, g, hive_path, local)
            orig_hash = hashlib.sha256(local.read_bytes()).hexdigest()

            h = _open_hive_local(local, write=(not dry_run))
            root = _node_id(h.root())
            if root == 0:
                out["errors"].append("Invalid hivex root()")
                return out

            cs = _resolve_controlset_for_path(h, root)
            cs_name = str(cs["controlset_name"])
            cs_node = int(cs["controlset_node"])

            node = _ensure_key_path(h, cs_node, list(key_path))

            old = _hivex_read_dword(h, node, name)
            out["original"] = old

            if old != int(value):
                _set_dword(h, node, name, int(value))
                out["modified"] = True
                out["new"] = int(value)
            else:
                out["new"] = old

            if not dry_run:
                try:
                    _commit_best_effort(h)
                finally:
                    _close_best_effort(h)
                    h = None

                g.upload(str(local), hive_path)
                out["uploaded_files"].append(
                    {"guest_path": hive_path, "sha256_local": hashlib.sha256(local.read_bytes()).hexdigest()}
                )

                with tempfile.TemporaryDirectory() as vtd:
                    vlocal = Path(vtd) / "SYSTEM_verify"
                    _download_hive_local(logger, g, hive_path, vlocal)
                    new_hash = hashlib.sha256(vlocal.read_bytes()).hexdigest()

                out["verification"] = {
                    "sha256_before": orig_hash,
                    "sha256_after": new_hash,
                    "changed": (new_hash != orig_hash),
                }
                out["success"] = True
            else:
                out["success"] = True

            out["notes"] += [
                f"ControlSet resolved and edited at: {cs_name}",
                "DWORD written as REG_DWORD (little-endian).",
                "Node ids normalized across python-hivex versions (0 vs None).",
                "Windows root mount validated to ensure correct C: mapping.",
                "Hive integrity checked via size + 'regf' signature during downloads.",
            ]
            return out

        except Exception as e:
            out["errors"].append(f"SYSTEM dword set failed: {e}")
            return out
        finally:
            _close_best_effort(h)


# ---------------------------------------------------------------------------
# Public: SOFTWARE hive DevicePath append
# ---------------------------------------------------------------------------


def _normalize_devicepath_part(p: str) -> str:
    return p.strip().strip(";").strip().lower()


def _resolve_software_cv_node(h: hivex.Hivex, root: int) -> int:
    microsoft = _node_id(h.node_get_child(root, "Microsoft"))
    if microsoft == 0:
        raise RuntimeError("SOFTWARE hive missing Microsoft key")

    windows = _node_id(h.node_get_child(microsoft, "Windows"))
    if windows == 0:
        raise RuntimeError("SOFTWARE hive missing Microsoft\\Windows key")

    cv = _node_id(h.node_get_child(windows, "CurrentVersion"))
    if cv == 0:
        raise RuntimeError("SOFTWARE hive missing Microsoft\\Windows\\CurrentVersion key")
    return cv


def append_devicepath_software_hive(
    self,
    g: guestfs.GuestFS,
    software_hive_path: str,
    append_path: str,
) -> Dict[str, Any]:
    logger = _safe_logger(self)
    dry_run = bool(getattr(self, "dry_run", False))

    out: Dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "hive_path": software_hive_path,
        "modified": False,
        "original": None,
        "new": None,
        "errors": [],
        "notes": [],
        "uploaded_files": [],
        "verification": {},
    }

    try:
        _ensure_windows_root(logger, g, hint_hive_path=software_hive_path)
    except Exception as e:
        out["errors"].append(str(e))
        return out

    try:
        if not g.is_file(software_hive_path):
            out["errors"].append(f"SOFTWARE hive not found: {software_hive_path}")
            return out
    except Exception as e:
        out["errors"].append(f"Failed to stat hive {software_hive_path}: {e}")
        return out

    with tempfile.TemporaryDirectory() as td:
        local = Path(td) / "SOFTWARE"
        h: Optional[hivex.Hivex] = None
        try:
            _log_mountpoints_best_effort(logger, g)
            _hive_backup_best_effort(logger, g, software_hive_path, dry_run=dry_run, results=out)

            _download_hive_local(logger, g, software_hive_path, local)
            orig_hash = hashlib.sha256(local.read_bytes()).hexdigest()

            h = _open_hive_local(local, write=(not dry_run))
            root = _node_id(h.root())
            if root == 0:
                out["errors"].append("Invalid hivex root()")
                return out

            cv = _resolve_software_cv_node(h, root)

            cur = _hivex_read_sz(h, cv, "DevicePath") or r"%SystemRoot%\inf"
            out["original"] = cur

            parts_raw = [p.strip() for p in cur.split(";") if p.strip()]
            parts_norm = {_normalize_devicepath_part(p) for p in parts_raw}

            ap_norm = _normalize_devicepath_part(append_path)
            if ap_norm and ap_norm not in parts_norm:
                parts_raw.append(append_path.strip())
            new = ";".join(parts_raw)
            out["new"] = new

            if new != cur:
                logger.info("Updating DevicePath: +%s", append_path)
                _set_expand_sz(h, cv, "DevicePath", new)
                out["modified"] = True
            else:
                logger.info("DevicePath already contains staging path (case-insensitive); no change needed")

            if not dry_run:
                try:
                    _commit_best_effort(h)
                finally:
                    _close_best_effort(h)
                    h = None

                g.upload(str(local), software_hive_path)
                out["uploaded_files"].append(
                    {"guest_path": software_hive_path, "sha256_local": hashlib.sha256(local.read_bytes()).hexdigest()}
                )

                with tempfile.TemporaryDirectory() as vtd:
                    vlocal = Path(vtd) / "SOFTWARE_verify"
                    _download_hive_local(logger, g, software_hive_path, vlocal)
                    new_hash = hashlib.sha256(vlocal.read_bytes()).hexdigest()

                out["verification"] = {
                    "sha256_before": orig_hash,
                    "sha256_after": new_hash,
                    "changed": (new_hash != orig_hash),
                }
                out["success"] = True
            else:
                out["success"] = True

            out["notes"] += [
                "DevicePath updated to help Windows PnP discover staged INF packages on first boot.",
                "Comparison is case-insensitive to avoid duplicates differing only by case/whitespace.",
                "Value written as REG_EXPAND_SZ (UTF-16LE).",
                "Node ids normalized across python-hivex versions (0 vs None).",
                "Backup created alongside other SOFTWARE edits.",
                "Windows root mount validated to ensure correct C: mapping.",
                "Hive integrity checked via size + 'regf' signature during downloads.",
            ]
            return out

        except Exception as e:
            out["errors"].append(f"DevicePath update failed: {e}")
            return out
        finally:
            _close_best_effort(h)


# ---------------------------------------------------------------------------
# Public: SOFTWARE hive RunOnce helper (kept, but SERVICE is preferred)
# ---------------------------------------------------------------------------


def _ensure_software_cv_path(h: hivex.Hivex, root: int) -> int:
    microsoft = _node_id(h.node_get_child(root, "Microsoft"))
    if microsoft == 0:
        microsoft = _ensure_child(h, root, "Microsoft")

    windows = _node_id(h.node_get_child(microsoft, "Windows"))
    if windows == 0:
        windows = _ensure_child(h, microsoft, "Windows")

    cv = _node_id(h.node_get_child(windows, "CurrentVersion"))
    if cv == 0:
        cv = _ensure_child(h, windows, "CurrentVersion")
    return cv


def add_software_runonce(
    self,
    g: guestfs.GuestFS,
    software_hive_path: str,
    *,
    name: str,
    command: str,
) -> Dict[str, Any]:
    logger = _safe_logger(self)
    dry_run = bool(getattr(self, "dry_run", False))

    out: Dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "hive_path": software_hive_path,
        "name": name,
        "command": command,
        "modified": False,
        "original": None,
        "new": None,
        "errors": [],
        "notes": [],
        "uploaded_files": [],
        "verification": {},
    }

    try:
        _ensure_windows_root(logger, g, hint_hive_path=software_hive_path)
    except Exception as e:
        out["errors"].append(str(e))
        return out

    try:
        if not g.is_file(software_hive_path):
            out["errors"].append(f"SOFTWARE hive not found: {software_hive_path}")
            return out
    except Exception as e:
        out["errors"].append(f"Failed to stat hive {software_hive_path}: {e}")
        return out

    with tempfile.TemporaryDirectory() as td:
        local = Path(td) / "SOFTWARE"
        h: Optional[hivex.Hivex] = None
        try:
            _log_mountpoints_best_effort(logger, g)
            _hive_backup_best_effort(logger, g, software_hive_path, dry_run=dry_run, results=out)

            _download_hive_local(logger, g, software_hive_path, local)
            orig_hash = hashlib.sha256(local.read_bytes()).hexdigest()

            h = _open_hive_local(local, write=(not dry_run))
            root = _node_id(h.root())
            if root == 0:
                out["errors"].append("Invalid hivex root()")
                return out

            cv = _ensure_software_cv_path(h, root)
            runonce = _node_id(h.node_get_child(cv, "RunOnce"))
            if runonce == 0:
                runonce = _ensure_child(h, cv, "RunOnce")

            old = _hivex_read_sz(h, runonce, name)
            out["original"] = old

            if old != command:
                _set_sz(h, runonce, name, command)
                out["modified"] = True
                out["new"] = command
            else:
                out["new"] = old

            if not dry_run:
                try:
                    _commit_best_effort(h)
                finally:
                    _close_best_effort(h)
                    h = None

                g.upload(str(local), software_hive_path)
                out["uploaded_files"].append(
                    {"guest_path": software_hive_path, "sha256_local": hashlib.sha256(local.read_bytes()).hexdigest()}
                )

                with tempfile.TemporaryDirectory() as vtd:
                    vlocal = Path(vtd) / "SOFTWARE_verify"
                    _download_hive_local(logger, g, software_hive_path, vlocal)
                    new_hash = hashlib.sha256(vlocal.read_bytes()).hexdigest()

                out["verification"] = {
                    "sha256_before": orig_hash,
                    "sha256_after": new_hash,
                    "changed": (new_hash != orig_hash),
                }
                out["success"] = True
            else:
                out["success"] = True

            logger.info("RunOnce set: %s -> %s", name, command)
            out["notes"] += [
                r"RunOnce written at HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
                "Value written as REG_SZ (UTF-16LE).",
                "Node ids normalized across python-hivex versions (0 vs None).",
                "Windows root mount validated to ensure correct C: mapping.",
                "Hive integrity checked via size + 'regf' signature during downloads.",
                "Consider using provision_firstboot_payload_and_service() for higher reliability than RunOnce.",
            ]
            return out

        except Exception as e:
            out["errors"].append(f"RunOnce update failed: {e}")
            return out
        finally:
            _close_best_effort(h)
