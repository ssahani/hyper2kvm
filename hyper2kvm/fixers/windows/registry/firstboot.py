# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/windows/registry/firstboot.py
# -*- coding: utf-8 -*-
"""
First-boot provisioning for Windows VMs.

This module provides functionality to create and manage a one-shot Windows service
that executes on first boot to perform driver installation, VMware Tools removal,
and other post-conversion tasks. The service is more reliable than RunOnce registry
entries as it executes regardless of logon/autologon quirks.

Key features:
- Creates a Windows service that runs firstboot.cmd as LocalSystem
- Installs staged drivers via pnputil
- Optionally removes VMware Tools (registry-based uninstall + service cleanup)
- Writes detailed logs to Windows\\Temp\\hyper2kvm-firstboot.log
- Self-deletes the service after successful execution
- Uses idempotency markers to prevent reruns
"""
from __future__ import annotations

import hashlib
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    import guestfs  # type: ignore
else:
    try:
        import guestfs  # type: ignore
    except ImportError:
        guestfs = None  # type: ignore
import hivex  # type: ignore

from ....core.utils import U
from ....core.logging_utils import safe_logger as _safe_logger_base
from .encoding import (
    _close_best_effort,
    _commit_best_effort,
    _detect_current_controlset,
    _encode_windows_cmd_script,
    _ensure_child,
    _mkdir_p_guest,
    _node_id,
    _open_hive_local,
    _set_dword,
    _set_expand_sz,
    _set_sz,
    _upload_bytes,
)
from .io import _download_hive_local, _log_mountpoints_best_effort
from .mount import _ensure_windows_root, _guest_path_join


# Logging helper


def _safe_logger(self) -> logging.Logger:
    """Get logger from instance or create default for registry modules."""
    return _safe_logger_base(self, "hyper2kvm.windows_registry")


# First-boot mechanism: create a one-shot SERVICE (more reliable than RunOnce)

_DEFAULT_GUEST_DIR = "/hyper2kvm"
_DEFAULT_DRIVER_STAGE_DIR = "/hyper2kvm/drivers/virtio"
_DEFAULT_LOG_PATH = "/Windows/Temp/hyper2kvm-firstboot.log"
_DEFAULT_MARKER_PATH = "/hyper2kvm/firstboot.done"


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
                backup_path = f"{system_hive_path}.hyper2kvm.backup.{ts}"
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


# VMware Tools removal (firstboot script block)


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
    " ('Found: ' + $a.DisplayName + ' [' + $a.Publisher + ']') | Out-File -Append -Encoding ascii $env:LOG;" ^
    " $u=$a.QuietUninstallString; if(-not $u){ $u=$a.UninstallString };" ^
    " if(-not $u){ 'No uninstall string' | Out-File -Append -Encoding ascii $env:LOG; continue }" ^
    " ('UninstallString: ' + $u) | Out-File -Append -Encoding ascii $env:LOG;" ^
    " try {" ^
    " if($u -match 'msiexec'){ if($u -notmatch '/qn'){ $u += ' /qn' }; if($u -notmatch '/norestart'){ $u += ' /norestart' } }" ^
    " $p=Start-Process -FilePath 'cmd.exe' -ArgumentList ('/c ' + $u) -Wait -PassThru;" ^
    " ('rc=' + $p.ExitCode) | Out-File -Append -Encoding ascii $env:LOG;" ^
    " } catch { $_ | Out-File -Append -Encoding ascii $env:LOG }" ^
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

echo --- VMware driver/services DELETE (aggressive cleanup) --- >> "%LOG%"
for %%D in (vm3dmp vmmouse vmusbmouse vmxnet3 vmxnet vmhgfs vmci vmscsi pvscsi vmmemctl vsock vmrawdsk vm3dservice vmvss) do (
  echo Removing driver service: %%D >> "%LOG%"
  sc.exe stop "%%D" >> "%LOG%" 2>&1
  sc.exe delete "%%D" >> "%LOG%" 2>&1
  reg delete "HKLM\SYSTEM\CurrentControlSet\Services\%%D" /f >> "%LOG%" 2>&1
  reg delete "HKLM\SYSTEM\ControlSet001\Services\%%D" /f >> "%LOG%" 2>&1
  reg delete "HKLM\SYSTEM\ControlSet002\Services\%%D" /f >> "%LOG%" 2>&1
)

echo --- VMware driver files DELETE from System32\drivers --- >> "%LOG%"
for %%F in (vm3dmp.sys vmmouse.sys vmusbmouse.sys vmxnet3.sys vmxnet.sys vmhgfs.sys vmci.sys vmscsi.sys pvscsi.sys vmmemctl.sys vsock.sys vmrawdsk.sys) do (
  if exist "%SystemRoot%\System32\drivers\%%F" (
    echo Deleting: %SystemRoot%\System32\drivers\%%F >> "%LOG%"
    del /f /q "%SystemRoot%\System32\drivers\%%F" >> "%LOG%" 2>&1
  )
)

echo --- VMware PnP drivers removal via pnputil --- >> "%LOG%"
where pnputil >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  for /f "tokens=1" %%I in ('pnputil /enum-drivers ^| findstr /i "vmware"') do (
    echo Removing PnP driver: %%I >> "%LOG%"
    pnputil /delete-driver %%I /uninstall /force >> "%LOG%" 2>&1
  )
) else (
  echo pnputil not available; skipping PnP driver removal >> "%LOG%"
)

echo --- VMware devices removal from Device Manager --- >> "%LOG%"
where powershell >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Continue';" ^
    "try {" ^
    " $devcon = Get-WmiObject Win32_PnPEntity | Where-Object { $_.Name -match 'VMware' -or $_.Manufacturer -match 'VMware' };" ^
    " if($devcon) {" ^
    "  foreach($d in $devcon) {" ^
    "   ('Removing device: ' + $d.Name) | Out-File -Append -Encoding ascii $env:LOG;" ^
    "   try { $d.Delete() } catch { $_ | Out-File -Append -Encoding ascii $env:LOG }" ^
    "  }" ^
    " } else {" ^
    "  'No VMware devices found in Device Manager' | Out-File -Append -Encoding ascii $env:LOG;" ^
    " }" ^
    "} catch { $_ | Out-File -Append -Encoding ascii $env:LOG }" ^
    >> "%LOG%" 2>&1
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


# Firstboot provisioning: refactored into small helpers


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
    #   guestfs /hyper2kvm               -> Windows C:\hyper2kvm
    #   guestfs /hyper2kvm/drivers/virtio-> Windows C:\hyper2kvm\drivers\virtio
    #   guestfs /Windows/Temp/...        -> Windows C:\Windows\Temp\...
    win_guest_dir = r"%SystemDrive%\hyper2kvm"
    win_stage_dir = fr"{win_guest_dir}\drivers\virtio"
    win_log = r"%SystemRoot%\Temp\hyper2kvm-firstboot.log"
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

    # NOTE: This is a "pure string builder"; no guestfs/hivex side effects.
    return rf"""@echo off
setlocal EnableExtensions EnableDelayedExpansion

set LOG={win.win_log}
set SVC={service_name}
set STAGE={win.win_stage_dir}
set MARKER={win.win_marker}

rem ---- idempotency guard ----
if exist "%MARKER%" (
  echo hyper2kvm firstboot marker exists: %MARKER%>> "%LOG%"
  echo Exiting without doing work.>> "%LOG%"
  exit /b 0
)

echo ==================================================>> "%LOG%"
echo hyper2kvm firstboot starting at %DATE% %TIME%>> "%LOG%"
echo ComputerName=%COMPUTERNAME%>> "%LOG%"
echo SystemDrive=%SystemDrive%>> "%LOG%"
echo SystemRoot=%SystemRoot%>> "%LOG%"
echo StageDir=%STAGE%>> "%LOG%"

echo --- Disk / Volume sanity --- >> "%LOG%"
where wmic >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  wmic logicaldisk get deviceid, volumename, filesystem, freespace, size >> "%LOG%" 2>&1
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

echo hyper2kvm firstboot completed at %DATE% %TIME%>> "%LOG%"
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
    # Run from C:\hyper2kvm\firstboot.cmd (quoted)
    return fr'"{win_guest_dir}\firstboot.cmd"'


def provision_firstboot_payload_and_service(
    self,
    g: guestfs.GuestFS,
    *,
    system_hive_path: str = "/Windows/System32/config/SYSTEM",
    service_name: str = "hyper2kvm-firstboot",
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
      2) Upload firstboot.cmd to /hyper2kvm/firstboot.cmd
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
        display_name="hyper2kvm First Boot Driver Installer",
        cmdline=cmdline,
        start=2,
        description="One-shot first boot installer for hyper2kvm staged drivers; writes log to Windows\\Temp.",
    )
    results["service"] = svc_res
    if not svc_res.get("success"):
        results["errors"].extend(svc_res.get("errors", []))
        return results

    # 6) Notes + success
    results["notes"] += [
        "Firstboot uses a SERVICE (LocalSystem) instead of RunOnce: less fragile across logon/autologon quirks.",
        "Log file will be at C:\\Windows\\Temp\\hyper2kvm-firstboot.log (guestfs: /Windows/Temp/hyper2kvm-firstboot.log).",
        "Drivers must be staged under C:\\hyper2kvm\\drivers\\virtio (guestfs: /hyper2kvm/drivers/virtio).",
        "A completion marker is written to C:\\hyper2kvm\\firstboot.done to avoid reruns if the service delete fails.",
        "uploaded_files includes sha256+size so you can prove what landed on disk.",
    ]
    if remove_vmware_tools:
        results["notes"].append(
            "VMware Tools removal enabled: firstboot will attempt registry-based uninstall + stop/delete services "
            "+ disable drivers + remove Tools dirs (best-effort)."
        )

    results["success"] = True
    return results
