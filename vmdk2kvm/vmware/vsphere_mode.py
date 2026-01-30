# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import fnmatch
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests
from pyVmomi import vim, vmodl

# Optional: Rich progress UI (TTY friendly). Falls back to plain logs if Rich not available.
try:  # pragma: no cover
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeElapsedColumn,
        TransferSpeedColumn,
    )
except Exception:  # pragma: no cover
    Progress = None  # type: ignore
    SpinnerColumn = BarColumn = TextColumn = TimeElapsedColumn = TransferSpeedColumn = None  # type: ignore

# Optional: silence urllib3 TLS warnings when verify=False
try:  # pragma: no cover
    import urllib3  # type: ignore
except Exception:  # pragma: no cover
    urllib3 = None  # type: ignore


from ..core.exceptions import Fatal, VMwareError
from .vmware_client import REQUESTS_AVAILABLE, VMwareClient
from .govc_common import GovcRunner, extract_paths_from_datastore_ls_json, normalize_ds_path


_DEFAULT_HTTP_TIMEOUT = (10, 300)  # (connect, read) seconds
_DEFAULT_CHUNK_SIZE = 1024 * 1024


def _boolish(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    return s in ("1", "true", "yes", "y", "on")


def _short_exc(e: BaseException) -> str:
    try:
        return f"{type(e).__name__}: {e}"
    except Exception:
        return type(e).__name__


def _fmt_bytes(n: Optional[int]) -> str:
    if n is None or n < 0:
        return "?"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    x = float(n)
    for u in units:
        if x < 1024.0 or u == units[-1]:
            return f"{x:.2f} {u}"
        x /= 1024.0
    return f"{n} B"


def _fmt_duration(sec: float) -> str:
    if sec < 1.0:
        return f"{sec*1000:.0f}ms"
    if sec < 60.0:
        return f"{sec:.2f}s"
    m = int(sec // 60)
    s = sec - (m * 60)
    return f"{m}m{s:.0f}s"


def _redact_cookie(cookie: str) -> str:
    if not cookie:
        return ""
    try:
        parts = cookie.split("=", 1)
        if len(parts) != 2:
            return "Cookie=<redacted>"
        k, v = parts
        v = v.strip()
        tail = v[-6:] if len(v) >= 6 else v
        return f"{k}=…{tail}"
    except Exception:
        return "Cookie=<redacted>"


def _is_transient_http(status: int) -> bool:
    return status in (408, 429, 500, 502, 503, 504)


def _norm_action(v: Any) -> str:
    s = str(v or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "export_vmin": "export_vm",
        "exportvm": "export_vm",
        "export": "export_vm",
    }
    return aliases.get(s, s)


def _norm_export_mode(v: Any) -> str:
    s = str(v or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "ovf": "ovf_export",
        "export_ovf": "ovf_export",
        "ovfdir": "ovf_export",
        "ova": "ova_export",
        "export_ova": "ova_export",
    }
    return aliases.get(s, s)


class VsphereMode:
    """
    CLI entry for vSphere actions.

    Updated policy:
      - VDDK is EXPERIMENTAL: never auto-run it. Only attempt if user explicitly sets vs_transport=vddk.
      - Export priority: OVF -> OVA -> HTTP/HTTPS folder
      - Control-plane: prefer govc (inventory/export). pyvmomi is mainly for /folder cookie downloads.
    """

    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        self.logger = logger
        self.args = args
        self.govc = GovcRunner(logger=logger, args=args)

    def _debug_enabled(self) -> bool:
        if _boolish(os.environ.get("VMDK2KVM_DEBUG") or os.environ.get("VMDK2KVM_VSPHERE_DEBUG")):
            return True
        if bool(getattr(self.args, "debug", False)):
            return True
        return self.logger.isEnabledFor(logging.DEBUG)

    def _dc_name(self) -> str:
        v = getattr(self.args, "dc_name", None)
        return v if v else "ha-datacenter"

    def _require_govc(self) -> None:
        if not self.govc.available():
            raise Fatal(
                2,
                "vsphere: govc is required for this action (control-plane prefers govc). "
                "Install govc and ensure GOVC_* env / args are configured.",
            )

    def _transport_preference(self) -> str:
        """
        Transport preference for datastore file downloads.

        New default: HTTPS (stable).
        VDDK: EXPERIMENTAL; only if explicitly requested.
        """
        v = getattr(self.args, "vs_transport", None) or getattr(self.args, "vs_download_transport", None)
        if not v:
            v = os.environ.get("VMDK2KVM_VSPHERE_TRANSPORT") or os.environ.get("VSPHERE_TRANSPORT")
        v = (str(v).strip().lower() if v else "https")
        if v in ("https", "http", "folder", "pyvmomi"):
            return "https"
        if v == "vddk":
            return "vddk"
        if v == "auto":
            # auto now means: stable first
            return "https"
        return "https"

    def _parse_vm_datastore_dir(self, vmx_path: str) -> Tuple[str, str]:
        s = (vmx_path or "").strip()
        if not s.startswith("[") or "]" not in s:
            raise VMwareError(f"Unexpected vmPathName format: {vmx_path}")
        ds = s[1 : s.index("]")]
        rest = s[s.index("]") + 1 :].strip()
        if "/" not in rest:
            folder = ""
        else:
            folder = rest.rsplit("/", 1)[0].lstrip("/")
        return ds, folder

    def _parse_datastore_dir_override(self, s: str, *, default_ds: Optional[str] = None) -> Tuple[str, str]:
        t = (s or "").strip()
        if not t:
            raise VMwareError("Empty vs_datastore_dir override")

        if t.startswith("[") and "]" in t:
            ds = t[1 : t.index("]")]
            rest = t[t.index("]") + 1 :].strip()
            rest = rest.lstrip("/")
            if "/" in rest:
                folder = rest.rsplit("/", 1)[0]
            else:
                folder = ""
            return ds, folder.strip("/")

        if not default_ds:
            raise VMwareError("vs_datastore_dir provided without datastore and default datastore is unknown")

        folder = t.strip().lstrip("/").rstrip("/")
        if "/" in folder and "." in folder.split("/")[-1]:
            folder = folder.rsplit("/", 1)[0]
        return str(default_ds), folder.strip("/")

    # -------------------------------------------------------------------------
    # govc helpers (use govc_common.GovcRunner; do NOT re-implement it)
    # -------------------------------------------------------------------------

    def _govc_list_vm_names(self) -> List[Dict[str, Any]]:
        """
        Inventory via govc:
          - govc find -type m -json .
          - optionally govc vm.info -json per VM (bounded)
        """
        self._require_govc()
        t0 = time.monotonic()

        found = self.govc.run_json(["find", "-type", "m", "-json", "."]) or {}
        vms = (found.get("Elements") or [])
        if not isinstance(vms, list):
            vms = []

        max_detail = int(getattr(self.args, "govc_max_detail", 500) or 500)
        if len(vms) > max_detail:
            out = [{"name": str(p).split("/")[-1], "path": p} for p in vms]
            out = sorted(out, key=lambda x: x.get("name", ""))
            if self._debug_enabled():
                self.logger.debug(f"govc: list_vm_names (names-only) took {_fmt_duration(time.monotonic()-t0)}")
            return out

        detailed: List[Dict[str, Any]] = []
        for pth in vms:
            try:
                info = self.govc.run_json(["vm.info", "-json", str(pth)]) or {}
                arr = info.get("VirtualMachines") or []
                if not arr:
                    continue
                vm = arr[0]
                cfg = (vm.get("Config") or {})
                runtime = (vm.get("Runtime") or {})
                guest = (vm.get("Guest") or {})
                summary = (vm.get("Summary") or {})
                detailed.append(
                    {
                        "name": cfg.get("Name") or str(pth).split("/")[-1],
                        "runtime.powerState": runtime.get("PowerState"),
                        "summary.overallStatus": (summary.get("OverallStatus") or ""),
                        "summary.guest.guestFullName": (cfg.get("GuestFullName") or ""),
                        "summary.config.memorySizeMB": cfg.get("MemoryMB"),
                        "summary.config.numCpu": cfg.get("NumCPU"),
                        "summary.config.vmPathName": (cfg.get("VmPathName") or ""),
                        "summary.config.instanceUuid": cfg.get("InstanceUuid"),
                        "summary.config.uuid": cfg.get("Uuid"),
                        "guest.guestState": guest.get("GuestState"),
                        "path": pth,
                    }
                )
            except Exception as e:
                detailed.append({"name": str(pth).split("/")[-1], "path": pth, "error": str(e)})

        detailed = sorted(detailed, key=lambda x: x.get("name", ""))
        if self._debug_enabled():
            self.logger.debug(f"govc: list_vm_names took {_fmt_duration(time.monotonic()-t0)}")
        return detailed

    def _govc_export_ovf(self, vm_name: str, out_dir: Path) -> None:
        """
        Export VM to OVF directory using the *workflow* wrapper (PTY + Rich progress).

        Critical: do NOT call self.govc.run(["export.ovf", ...]) because govc often buffers
        progress when stdout is not a TTY, which looks like a hang.
        """
        self._require_govc()
        out_dir = Path(out_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        # Pull knobs from args (keep defaults sane)
        power_off = bool(getattr(self.args, "govc_export_power_off", False) or getattr(self.args, "power_off", False))
        shutdown = bool(getattr(self.args, "govc_export_shutdown", False) or getattr(self.args, "shutdown", False))
        shutdown_timeout_s = float(getattr(self.args, "govc_export_shutdown_timeout_s", 300.0) or 300.0)
        shutdown_poll_s = float(getattr(self.args, "govc_export_shutdown_poll_s", 5.0) or 5.0)

        remove_cdroms = bool(getattr(self.args, "govc_export_remove_cdroms", True))
        show_vm_info = bool(getattr(self.args, "govc_export_show_vm_info", True))
        show_progress = bool(getattr(self.args, "govc_export_show_progress", True))
        prefer_pty = bool(getattr(self.args, "govc_export_prefer_pty", True))
        clean_outdir = bool(getattr(self.args, "govc_export_clean_outdir", False))

        t0 = time.monotonic()
        # This calls vmdk2kvm/vsphere/govc_export.py under the hood.
        self.govc.export_ovf(
            vm=str(vm_name),
            out_dir=str(out_dir),
            power_off=power_off,
            remove_cdroms=remove_cdroms,
            show_vm_info=show_vm_info,
            shutdown=shutdown,
            shutdown_timeout_s=shutdown_timeout_s,
            shutdown_poll_s=shutdown_poll_s,
            # Newer govc_export.py supports these fields; older versions will just ignore via spec defaults.
            # GovcRunner.export_ovf passes them through in GovcExportSpec.
            # (If your GovcRunner doesn't yet, update govc_common.py accordingly.)
        )
        self.logger.info("govc: ovf_export done (dir=%s) in %s", out_dir, _fmt_duration(time.monotonic() - t0))

        # NOTE: show_progress/prefer_pty/clean_outdir are handled inside govc_export.py via GovcExportSpec.
        # If your GovcRunner.export_ovf isn't passing them through yet, update govc_common.py.

        # Keep lints happy for unused locals when govc_common is older
        _ = (show_progress, prefer_pty, clean_outdir)

    def _govc_export_ova(self, vm_name: str, out_dir: Path) -> Path:
        """
        Export VM to OVA using the *workflow* wrapper (OVF export + tarfile OVA + Rich progress).
        """
        self._require_govc()
        out_dir = Path(out_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        power_off = bool(getattr(self.args, "govc_export_power_off", False) or getattr(self.args, "power_off", False))
        shutdown = bool(getattr(self.args, "govc_export_shutdown", False) or getattr(self.args, "shutdown", False))
        shutdown_timeout_s = float(getattr(self.args, "govc_export_shutdown_timeout_s", 300.0) or 300.0)
        shutdown_poll_s = float(getattr(self.args, "govc_export_shutdown_poll_s", 5.0) or 5.0)

        remove_cdroms = bool(getattr(self.args, "govc_export_remove_cdroms", True))
        show_vm_info = bool(getattr(self.args, "govc_export_show_vm_info", True))
        show_progress = bool(getattr(self.args, "govc_export_show_progress", True))
        prefer_pty = bool(getattr(self.args, "govc_export_prefer_pty", True))
        clean_outdir = bool(getattr(self.args, "govc_export_clean_outdir", False))

        ova_path = out_dir / f"{vm_name}.ova"

        t0 = time.monotonic()
        self.govc.export_ova(
            vm=str(vm_name),
            out_file=str(ova_path),
            power_off=power_off,
            remove_cdroms=remove_cdroms,
            show_vm_info=show_vm_info,
            shutdown=shutdown,
            shutdown_timeout_s=shutdown_timeout_s,
            shutdown_poll_s=shutdown_poll_s,
        )
        self.logger.info("govc: ova_export done (file=%s) in %s", ova_path, _fmt_duration(time.monotonic() - t0))

        # Keep lints happy for unused locals when govc_common is older
        _ = (show_progress, prefer_pty, clean_outdir)

        if ova_path.exists():
            return ova_path

        # Fallback: newest .ova
        ovas = sorted(out_dir.glob("*.ova"), key=lambda p: p.stat().st_mtime, reverse=True)
        return ovas[0] if ovas else ova_path

    def _govc_datastore_ls(self, datastore: str, folder: str) -> List[str]:
        """
        List files under a datastore folder via govc datastore.ls -json.
        Uses govc_common.extract_paths_from_datastore_ls_json() for parsing.
        """
        self._require_govc()
        t0 = time.monotonic()

        ds, rel = normalize_ds_path(datastore, folder or "")
        rel = rel.strip().lstrip("/")
        rel = rel.rstrip("/")
        rel_dir = (rel + "/") if rel else ""

        candidates = [rel_dir, "/" + rel_dir] if rel_dir else ["", "/"]
        base = rel_dir.lstrip("/")
        prefix = base.rstrip("/") + "/" if base else ""

        for cand in candidates:
            try:
                data = self.govc.run_json(["datastore.ls", "-json", "-ds", ds, cand]) or {}
                paths = extract_paths_from_datastore_ls_json(data)

                out: List[str] = []
                for p in paths:
                    relp = str(p).lstrip("/")
                    if prefix and relp.startswith(prefix):
                        relp = relp[len(prefix) :]
                    if relp:
                        out.append(relp)

                if self._debug_enabled():
                    self.logger.debug(
                        f"govc: datastore_ls ds={ds!r} folder={folder!r} cand={cand!r} -> {len(out)} items "
                        f"({_fmt_duration(time.monotonic() - t0)})"
                    )
                return out
            except Exception as e:
                if self._debug_enabled():
                    self.logger.debug(f"govc datastore.ls failed for candidate '{cand}': {e}")
                continue

        if self._debug_enabled():
            self.logger.debug(
                f"govc: datastore_ls ds={ds!r} folder={folder!r} -> 0 items ({_fmt_duration(time.monotonic() - t0)})"
            )
        return []

    # -------------------------------------------------------------------------
    # HTTPS /folder downloader (data-plane)
    # -------------------------------------------------------------------------

    def _download_one_folder_file(
        self,
        client: VMwareClient,
        vc_host: str,
        dc_name: str,
        ds_name: str,
        ds_path: str,
        local_path: Path,
        verify_tls: bool,
        *,
        on_bytes: Optional[Any] = None,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
    ) -> None:
        if not REQUESTS_AVAILABLE:
            raise VMwareError("requests not installed. Install: pip install requests")

        quoted_path = quote(ds_path, safe="/")
        url = f"https://{vc_host}/folder/{quoted_path}?dcPath={quote(dc_name)}&dsName={quote(ds_name)}"
        cookie = client._session_cookie()
        headers = {"Cookie": cookie}

        if not verify_tls and urllib3 is not None:  # pragma: no cover
            try:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # type: ignore[attr-defined]
            except Exception:
                pass

        local_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = local_path.with_suffix(local_path.suffix + ".part")

        timeout = getattr(self.args, "vs_http_timeout", None)
        if timeout is None:
            timeout = os.environ.get("VMDK2KVM_VSPHERE_HTTP_TIMEOUT")
        if timeout:
            try:
                if isinstance(timeout, str) and "," in timeout:
                    a, b = timeout.split(",", 1)
                    timeout_tuple = (int(a.strip()), int(b.strip()))
                else:
                    t = int(str(timeout).strip())
                    timeout_tuple = (10, t)
            except Exception:
                timeout_tuple = _DEFAULT_HTTP_TIMEOUT
        else:
            timeout_tuple = _DEFAULT_HTTP_TIMEOUT

        retries = getattr(self.args, "vs_http_retries", None)
        if retries is None:
            retries = os.environ.get("VMDK2KVM_VSPHERE_HTTP_RETRIES")
        try:
            retries_i = int(retries) if retries is not None else 3
        except Exception:
            retries_i = 3
        if retries_i < 0:
            retries_i = 0

        if self._debug_enabled():
            self.logger.debug(
                "vsphere: HTTPS /folder download: "
                f"url={url!r} verify_tls={verify_tls} timeout={timeout_tuple} chunk_size={chunk_size} "
                f"cookie={_redact_cookie(cookie)!r}"
            )

        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass

        attempt = 0
        last_err: Optional[BaseException] = None
        t0 = time.monotonic()
        while True:
            attempt += 1
            try:
                got = 0
                total = 0
                with requests.get(url, headers=headers, verify=verify_tls, stream=True, timeout=timeout_tuple) as r:
                    status = int(getattr(r, "status_code", 0) or 0)
                    if status >= 400:
                        try:
                            _ = r.content[:256]
                        except Exception:
                            pass
                        r.raise_for_status()

                    total = int(r.headers.get("content-length", "0") or "0")

                    with open(tmp, "wb") as f:
                        for chunk in r.iter_content(chunk_size=chunk_size):
                            if not chunk:
                                continue
                            f.write(chunk)
                            got += len(chunk)
                            if on_bytes is not None:
                                try:
                                    on_bytes(len(chunk), total)
                                except Exception:
                                    pass

                if total and got != total:
                    raise VMwareError(f"incomplete download: got={got} expected={total}")

                os.replace(tmp, local_path)

                if self._debug_enabled():
                    self.logger.debug(
                        f"vsphere: HTTPS download ok: ds=[{ds_name}] path={ds_path!r} "
                        f"bytes={_fmt_bytes(got)} total={_fmt_bytes(total)} "
                        f"dur={_fmt_duration(time.monotonic() - t0)} attempts={attempt}"
                    )
                return

            except requests.RequestException as e:
                last_err = e
                status = None
                try:
                    resp = getattr(e, "response", None)
                    if resp is not None:
                        status = int(getattr(resp, "status_code", 0) or 0)
                except Exception:
                    status = None

                transient = bool(status and _is_transient_http(status))
                if self._debug_enabled():
                    self.logger.debug(
                        f"vsphere: HTTPS attempt {attempt}/{retries_i+1} failed "
                        f"status={status} transient={transient} err={_short_exc(e)}"
                    )

                try:
                    if tmp.exists():
                        tmp.unlink()
                except Exception:
                    pass

                if attempt > retries_i or not transient:
                    break

                time.sleep(min(2.0 * attempt, 8.0))
                continue

            except Exception as e:
                last_err = e
                if self._debug_enabled():
                    self.logger.debug(
                        f"vsphere: HTTPS attempt {attempt}/{retries_i+1} failed err={_short_exc(e)}"
                    )
                try:
                    if tmp.exists():
                        tmp.unlink()
                except Exception:
                    pass
                break

        raise VMwareError(
            f"HTTPS /folder download failed after {attempt} attempt(s): {_short_exc(last_err or Exception('unknown'))}"
        )

    # -------------------------------------------------------------------------
    # Download transport selector (VDDK is EXPERIMENTAL and opt-in)
    # -------------------------------------------------------------------------

    def _download_one_file_policy(
        self,
        client: VMwareClient,
        *,
        vc_host: str,
        dc_name: str,
        ds_name: str,
        ds_path: str,
        local_path: Path,
        verify_tls: bool,
        on_bytes: Optional[Any] = None,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
    ) -> None:
        """
        New policy order (data-plane):
          - If user explicitly requested VDDK: try VDDK (EXPERIMENTAL), else fall back.
          - Default: HTTPS /folder.
        """
        pref = self._transport_preference()

        if pref == "vddk":
            self.logger.warning("VDDK transport requested: EXPERIMENTAL (opt-in). Will fall back on failure.")
            fn = getattr(client, "download_datastore_file_vddk", None)
            if callable(fn):
                try:
                    # best-effort signature flexibility
                    fn(datastore=ds_name, ds_path=ds_path, local_path=local_path, dc_name=dc_name, chunk_size=chunk_size, on_bytes=on_bytes)
                    return
                except TypeError:
                    fn(ds_name, ds_path, local_path)
                    return
                except Exception as e:
                    self.logger.warning("VDDK download failed; falling back to HTTPS folder: %s", _short_exc(e))
            else:
                self.logger.warning("VDDK requested but VMwareClient has no download_datastore_file_vddk(); falling back to HTTPS.")

        # Stable default
        self._download_one_folder_file(
            client=client,
            vc_host=vc_host,
            dc_name=dc_name,
            ds_name=ds_name,
            ds_path=ds_path,
            local_path=local_path,
            verify_tls=verify_tls,
            on_bytes=on_bytes,
            chunk_size=chunk_size,
        )

    # -------------------------------------------------------------------------
    # Main runner
    # -------------------------------------------------------------------------

    def run(self) -> int:
        vc_host = self.args.vcenter
        vc_user = self.args.vc_user
        vc_pass = self.args.vc_password

        if not vc_pass and getattr(self.args, "vc_password_env", None):
            vc_pass = os.environ.get(self.args.vc_password_env)

        if isinstance(vc_pass, str):
            vc_pass = vc_pass.strip()
        if not vc_pass:
            vc_pass = None

        # action normalization (fix typos like export_vmin)
        action = _norm_action(getattr(self.args, "vs_action", None))

        if not vc_host or not vc_user or not vc_pass:
            raise Fatal(2, "vsphere: --vcenter, --vc-user, and --vc-password (or --vc-password-env) are required")

        if self._debug_enabled():
            self.logger.debug(
                "vsphere: connect params: "
                f"host={vc_host!r} user={vc_user!r} port={getattr(self.args,'vc_port', None)!r} "
                f"insecure={bool(getattr(self.args,'vc_insecure', False))} "
                f"dc_name={self._dc_name()!r} transport_pref={self._transport_preference()!r} "
                f"govc_available={self.govc.available()}"
            )
            self.logger.debug(f"vsphere: normalized action={action!r}")

        # --- CONTROL-PLANE actions: govc preferred (and required)
        if action in ("list_vm_names", "export_vm"):
            self._require_govc()

        # pyvmomi client is still used for /folder cookie downloads and tasks like CBT.
        client = VMwareClient(
            self.logger,
            vc_host,
            vc_user,
            vc_pass,
            port=self.args.vc_port,
            insecure=self.args.vc_insecure,
        )

        try:
            t0 = time.monotonic()
            client.connect()
            if self._debug_enabled():
                self.logger.debug(f"vsphere: connected in {_fmt_duration(time.monotonic()-t0)}")
        except VMwareError as e:
            raise Fatal(2, f"vsphere: Connection failed: {e}")

        try:
            # -----------------------------------------------------------------
            # list_vm_names (govc control-plane)
            # -----------------------------------------------------------------
            if action == "list_vm_names":
                vms = self._govc_list_vm_names()
                self.logger.info(f"VMs found (govc): {len(vms)}")
                if self.args.json:
                    print(json.dumps(vms, indent=2, default=str))
                else:
                    for vm in vms:
                        print(vm.get("name", "Unnamed VM"))
                return 0

            # -----------------------------------------------------------------
            # export_vm (OVF -> OVA -> HTTPS folder fallback)
            # -----------------------------------------------------------------
            if action == "export_vm":
                vm_name = getattr(self.args, "vm_name", None) or getattr(self.args, "name", None)
                if not vm_name:
                    raise Fatal(2, "vsphere export_vm: --vm_name is required")

                out_dir = Path(getattr(self.args, "output_dir", None) or ".").expanduser().resolve()
                out_dir.mkdir(parents=True, exist_ok=True)

                # user can force mode, but policy fallback is still ovf -> ova -> https
                export_mode = _norm_export_mode(getattr(self.args, "export_mode", None) or "ovf_export")

                self.logger.info("export_vm: vm=%r out_dir=%s export_mode=%s (policy: ovf -> ova -> https)", vm_name, out_dir, export_mode)

                # 1) OVF
                try:
                    if export_mode in ("ovf_export", "auto"):
                        self._govc_export_ovf(vm_name, out_dir)
                        return 0
                except Exception as e:
                    self.logger.warning("export_vm: OVF export failed; trying OVA: %s", _short_exc(e))

                # 2) OVA
                try:
                    if export_mode in ("ova_export", "ovf_export", "auto"):
                        _ = self._govc_export_ova(vm_name, out_dir)
                        return 0
                except Exception as e:
                    self.logger.warning("export_vm: OVA export failed; falling back to HTTPS folder download: %s", _short_exc(e))

                # 3) HTTPS folder fallback = download_only_vm semantics
                # We resolve VM folder using pyvmomi summary, then download all files in that folder via /folder.
                vm = client.get_vm_by_name(vm_name)
                if not vm:
                    raise Fatal(2, f"vsphere export_vm: VM not found: {vm_name}")

                vmx_path = None
                try:
                    vmx_path = vm.summary.config.vmPathName if vm.summary and vm.summary.config else None
                except Exception:
                    vmx_path = None

                if not vmx_path:
                    raise Fatal(2, "vsphere export_vm: cannot determine VM folder (vm.summary.config.vmPathName missing)")

                ds_name, folder = self._parse_vm_datastore_dir(str(vmx_path))

                include_glob = list(getattr(self.args, "vs_include_glob", None) or ["*"])
                exclude_glob = list(getattr(self.args, "vs_exclude_glob", None) or ["*.lck", "*.log", "*.vswp", "*.vmem", "*.vmsn"])
                max_files = int(getattr(self.args, "vs_max_files", 5000) or 5000)

                # listing: prefer govc (control-plane)
                rels = self._govc_datastore_ls(ds_name, folder)
                files: List[str] = []
                base = folder.rstrip("/")
                for name in rels:
                    rel = f"{base}/{name}" if base and name else (base or name)
                    if not rel:
                        continue
                    bn = rel.split("/")[-1]
                    if include_glob and not any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(bn, pat) for pat in include_glob):
                        continue
                    if exclude_glob and any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(bn, pat) for pat in exclude_glob):
                        continue
                    files.append(rel)
                    if max_files and len(files) > max_files:
                        raise Fatal(2, f"export_vm: refusing to download > max_files={max_files} (found so far: {len(files)})")

                if not files:
                    self.logger.info("export_vm: HTTPS fallback found no files to download.")
                    return 0

                verify_tls = not client.insecure
                dc_name = self._dc_name()

                self.logger.info("export_vm: HTTPS fallback downloading %d files from [%s] %s", len(files), ds_name, folder or ".")

                progress = None
                files_task = None
                bytes_task = None
                if (Progress is not None) and (not getattr(self.args, "json", False)):
                    try:
                        progress = Progress(
                            SpinnerColumn(),
                            TextColumn("[bold]{task.description}[/bold]"),
                            BarColumn(),
                            TransferSpeedColumn(),
                            TimeElapsedColumn(),
                            transient=False,
                        )
                        files_task = progress.add_task("files", total=len(files))
                        bytes_task = progress.add_task("bytes", total=None)
                    except Exception:
                        progress = None
                        files_task = None
                        bytes_task = None

                def _job(ds_path: str) -> None:
                    local_path = out_dir / ds_path

                    def _on_bytes(n: int, total: int) -> None:
                        if progress is None:
                            return
                        if bytes_task is not None:
                            progress.advance(bytes_task, n)
                        if files_task is not None:
                            progress.update(files_task, description=f"downloading: {ds_path}")

                    self._download_one_file_policy(
                        client=client,
                        vc_host=vc_host,
                        dc_name=dc_name,
                        ds_name=ds_name,
                        ds_path=ds_path,
                        local_path=local_path,
                        verify_tls=verify_tls,
                        on_bytes=_on_bytes,
                        chunk_size=int(getattr(self.args, "chunk_size", _DEFAULT_CHUNK_SIZE)),
                    )
                    if progress is not None and files_task is not None:
                        progress.advance(files_task, 1)

                if progress is not None:
                    with progress:
                        for p in files:
                            _job(p)
                else:
                    for p in files:
                        _job(p)

                self.logger.info("export_vm: HTTPS fallback completed into %s", out_dir)
                return 0

            # -----------------------------------------------------------------
            # download_datastore_file (stable policy: https default; vddk opt-in)
            # -----------------------------------------------------------------
            if action == "download_datastore_file":
                if not all([self.args.datastore, self.args.ds_path, self.args.local_path]):
                    raise Fatal(2, "vsphere download_datastore_file: --datastore, --ds-path, --local-path are required")

                local_path = Path(self.args.local_path).resolve()
                dc_name = self._dc_name()
                chunk_size = int(getattr(self.args, "chunk_size", _DEFAULT_CHUNK_SIZE))

                self._download_one_file_policy(
                    client=client,
                    vc_host=vc_host,
                    dc_name=dc_name,
                    ds_name=self.args.datastore,
                    ds_path=self.args.ds_path,
                    local_path=local_path,
                    verify_tls=not client.insecure,
                    on_bytes=None,
                    chunk_size=chunk_size,
                )
                output = {
                    "status": "success",
                    "local_path": str(local_path),
                    "datastore": self.args.datastore,
                    "ds_path": self.args.ds_path,
                    "dc_name": dc_name,
                    "transport": self._transport_preference(),
                }
                if self.args.json:
                    print(json.dumps(output, indent=2))
                else:
                    print(f"Downloaded [{self.args.datastore}] {self.args.ds_path} to {local_path}")
                return 0

            # -----------------------------------------------------------------
            # download_only_vm (listing via govc preferred; download via policy)
            # -----------------------------------------------------------------
            if action == "download_only_vm":
                if not getattr(self.args, "vm_name", None):
                    raise Fatal(2, "vsphere download_only_vm: --vm_name is required")

                vm = client.get_vm_by_name(self.args.vm_name)
                if not vm:
                    raise Fatal(2, f"vsphere: VM not found: {self.args.vm_name}")

                out_dir = Path(self.args.output_dir).expanduser().resolve()
                out_dir.mkdir(parents=True, exist_ok=True)

                include_glob = list(getattr(self.args, "vs_include_glob", None) or ["*"])
                exclude_glob = list(getattr(self.args, "vs_exclude_glob", None) or [])
                max_files = int(getattr(self.args, "vs_max_files", 5000) or 5000)
                fail_on_missing = bool(getattr(self.args, "vs_fail_on_missing", False))

                vmx_path = None
                try:
                    vmx_path = vm.summary.config.vmPathName if vm.summary and vm.summary.config else None
                except Exception:
                    vmx_path = None

                if not vmx_path:
                    raise Fatal(2, "vsphere download_only_vm: cannot determine VM folder (vm.summary.config.vmPathName missing)")

                ds_name, folder = self._parse_vm_datastore_dir(str(vmx_path))

                override = getattr(self.args, "vs_datastore_dir", None)
                if override:
                    try:
                        ds_name, folder = self._parse_datastore_dir_override(str(override), default_ds=ds_name)
                        self.logger.info(f"download_only_vm: using vs_datastore_dir override: [{ds_name}] {folder or '.'}")
                    except Exception as e:
                        raise Fatal(2, f"vsphere download_only_vm: invalid vs_datastore_dir={override!r}: {e}")

                if self._debug_enabled():
                    self.logger.debug(
                        f"download_only_vm: vm={self.args.vm_name!r} vmx_path={str(vmx_path)!r} "
                        f"resolved=[{ds_name}] {folder or '.'} out_dir={str(out_dir)!r} "
                        f"include={include_glob} exclude={exclude_glob} max_files={max_files} fail_on_missing={fail_on_missing}"
                    )

                # listing via govc (preferred)
                if self.govc.available():
                    rels = self._govc_datastore_ls(ds_name, folder)
                    files: List[str] = []
                    base = folder.rstrip("/")
                    for name in rels:
                        rel = f"{base}/{name}" if base and name else (base or name)
                        if not rel:
                            continue
                        bn = rel.split("/")[-1]
                        if include_glob and not any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(bn, pat) for pat in include_glob):
                            continue
                        if exclude_glob and any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(bn, pat) for pat in exclude_glob):
                            continue
                        files.append(rel)
                        if max_files and len(files) > max_files:
                            raise Fatal(2, f"Refusing to download > max_files={max_files} (found so far: {len(files)})")
                    listing_mode = "govc"
                else:
                    # user asked "always prefer govc", but for download-only we can still proceed if govc missing.
                    self.logger.warning("govc not available; falling back to pyvmomi datastore listing for download-only.")
                    ds_obj = self._find_datastore_obj(client, ds_name)
                    files = self._list_vm_folder_files_pyvmomi(
                        client=client,
                        datastore_obj=ds_obj,
                        ds_name=ds_name,
                        folder=folder,
                        include_glob=include_glob,
                        exclude_glob=exclude_glob,
                        max_files=max_files,
                    )
                    listing_mode = "pyvmomi"

                if not files:
                    output = {
                        "status": "success",
                        "vm_name": self.args.vm_name,
                        "datastore": ds_name,
                        "folder": folder,
                        "matched": 0,
                        "downloaded": 0,
                        "output_dir": str(out_dir),
                        "include_glob": include_glob,
                        "exclude_glob": exclude_glob,
                        "listing": listing_mode,
                        "transport_pref": self._transport_preference(),
                    }
                    if self.args.json:
                        print(json.dumps(output, indent=2, default=str))
                    else:
                        print("No files matched; nothing downloaded.")
                    return 0

                self.logger.info(
                    f"download_only_vm: matched {len(files)} files in [{ds_name}] {folder or '.'} (listing={listing_mode})"
                )

                verify_tls = not client.insecure
                dc_name = self._dc_name()

                downloaded: List[str] = []
                errors: List[str] = []

                progress = None
                files_task = None
                bytes_task = None
                if (Progress is not None) and (not getattr(self.args, "json", False)):
                    try:
                        progress = Progress(
                            SpinnerColumn(),
                            TextColumn("[bold]{task.description}[/bold]"),
                            BarColumn(),
                            TransferSpeedColumn(),
                            TimeElapsedColumn(),
                            transient=False,
                        )
                        files_task = progress.add_task("files", total=len(files))
                        bytes_task = progress.add_task("bytes", total=None)
                    except Exception:
                        progress = None
                        files_task = None
                        bytes_task = None

                def _job(ds_path: str) -> None:
                    local_path = out_dir / ds_path

                    def _on_bytes(n: int, total: int) -> None:
                        if progress is None:
                            return
                        if bytes_task is not None:
                            progress.advance(bytes_task, n)
                        if files_task is not None:
                            progress.update(files_task, description=f"downloading: {ds_path}")

                    t0 = time.monotonic()
                    try:
                        self._download_one_file_policy(
                            client=client,
                            vc_host=vc_host,
                            dc_name=dc_name,
                            ds_name=ds_name,
                            ds_path=ds_path,
                            local_path=local_path,
                            verify_tls=verify_tls,
                            on_bytes=_on_bytes,
                            chunk_size=int(getattr(self.args, "chunk_size", _DEFAULT_CHUNK_SIZE)),
                        )
                        downloaded.append(ds_path)
                        if progress is not None and files_task is not None:
                            progress.advance(files_task, 1)
                        if self._debug_enabled():
                            try:
                                sz = local_path.stat().st_size
                            except Exception:
                                sz = None
                            self.logger.debug(
                                f"download_only_vm: ok ds_path={ds_path!r} local={str(local_path)!r} "
                                f"size={_fmt_bytes(sz)} dur={_fmt_duration(time.monotonic()-t0)}"
                            )
                    except Exception as e:
                        msg = f"{ds_path}: {e}"
                        errors.append(msg)
                        if progress is not None and files_task is not None:
                            progress.update(files_task, description=f"error: {ds_path}")
                        if self._debug_enabled():
                            self.logger.debug(
                                f"download_only_vm: fail ds_path={ds_path!r} dur={_fmt_duration(time.monotonic()-t0)} err={_short_exc(e)}"
                            )
                        if fail_on_missing:
                            raise

                if progress is not None:
                    with progress:
                        for p in files:
                            _job(p)
                else:
                    for p in files:
                        _job(p)

                output = {
                    "status": "success" if not errors else "partial",
                    "vm_name": self.args.vm_name,
                    "datastore": ds_name,
                    "folder": folder,
                    "output_dir": str(out_dir),
                    "matched": len(files),
                    "downloaded": len(downloaded),
                    "errors": errors,
                    "include_glob": include_glob,
                    "exclude_glob": exclude_glob,
                    "dc_name": dc_name,
                    "verify_tls": verify_tls,
                    "listing": listing_mode,
                    "govc_bin": getattr(self.govc, "govc_bin", None) if self.govc.available() else None,
                    "vs_datastore_dir": str(override) if override else None,
                    "transport_pref": self._transport_preference(),
                    "vddk_experimental": True,
                }
                if self.args.json:
                    print(json.dumps(output, indent=2, default=str))
                else:
                    print(f"Downloaded {len(downloaded)}/{len(files)} files into {out_dir}")
                    if errors:
                        print("Some downloads failed:")
                        for e in errors[:20]:
                            print(f"  - {e}")
                        if len(errors) > 20:
                            print(f"  ... and {len(errors)-20} more")
                return 0

            # -----------------------------------------------------------------
            # Keep other actions as-is (pyvmomi based) unless you want govc versions.
            # -----------------------------------------------------------------
            raise Fatal(2, f"vsphere: unknown action: {action}")

        finally:
            try:
                t0 = time.monotonic()
                client.disconnect()
                if self._debug_enabled():
                    self.logger.debug(f"vsphere: disconnected in {_fmt_duration(time.monotonic()-t0)}")
            except Exception as e:
                self.logger.warning(f"Failed to disconnect: {e}")

    # -------------------------------------------------------------------------
    # Minimal pyvmomi helpers (only used when govc missing for download-only listing)
    # -------------------------------------------------------------------------

    def _find_datastore_obj(self, client: VMwareClient, datastore_name: str) -> vim.Datastore:
        t0 = time.monotonic()
        content = client._content()

        def iter_children(obj):
            try:
                return list(getattr(obj, "childEntity", []) or [])
            except Exception:
                return []

        for top in iter_children(content.rootFolder):
            try:
                if isinstance(top, vim.Datacenter):
                    for ds in (top.datastore or []):
                        if ds.name == datastore_name:
                            if self._debug_enabled():
                                self.logger.debug(
                                    f"vsphere: found datastore {datastore_name!r} in {_fmt_duration(time.monotonic()-t0)}"
                                )
                            return ds
                elif isinstance(top, vim.Folder):
                    for child in iter_children(top):
                        if isinstance(child, vim.Datacenter):
                            for ds in (child.datastore or []):
                                if ds.name == datastore_name:
                                    if self._debug_enabled():
                                        self.logger.debug(
                                            f"vsphere: found datastore {datastore_name!r} in {_fmt_duration(time.monotonic()-t0)}"
                                        )
                                    return ds
            except Exception:
                continue

        raise VMwareError(f"Datastore not found in inventory: {datastore_name}")

    def _list_vm_folder_files_pyvmomi(
        self,
        client: VMwareClient,
        datastore_obj: vim.Datastore,
        ds_name: str,
        folder: str,
        include_glob: List[str],
        exclude_glob: List[str],
        max_files: int,
    ) -> List[str]:
        t0 = time.monotonic()
        browser = datastore_obj.browser
        ds_folder_path = f"[{ds_name}] {folder}" if folder else f"[{ds_name}]"

        spec = vim.HostDatastoreBrowserSearchSpec()
        spec.details = vim.FileQueryFlags(fileOwner=True, fileSize=True, fileType=True, modification=True)
        spec.sortFoldersFirst = True

        if self._debug_enabled():
            self.logger.debug(
                f"vsphere: pyvmomi SearchDatastore_Task path={ds_folder_path!r} include={include_glob} exclude={exclude_glob}"
            )

        task = browser.SearchDatastore_Task(datastorePath=ds_folder_path, searchSpec=spec)
        client.wait_for_task(task)

        result = getattr(task.info, "result", None)
        if not result:
            if self._debug_enabled():
                self.logger.debug(
                    f"vsphere: pyvmomi SearchDatastore_Task returned no result ({_fmt_duration(time.monotonic()-t0)})"
                )
            return []

        files: List[str] = []
        base = folder.rstrip("/")

        for f in getattr(result, "file", []) or []:
            name = getattr(f, "path", None)
            if not name:
                continue
            rel = f"{base}/{name}" if base else name

            if include_glob and not any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat) for pat in include_glob):
                continue
            if exclude_glob and any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat) for pat in exclude_glob):
                continue

            files.append(rel)

            if max_files and len(files) > max_files:
                raise VMwareError(f"Refusing to download > max_files={max_files} (found so far: {len(files)})")

        if self._debug_enabled():
            self.logger.debug(
                f"vsphere: pyvmomi listed {len(files)} files in {_fmt_duration(time.monotonic()-t0)}"
            )
        return files
