# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# vmdk2kvm/vsphere/vsphere_client.py
from __future__ import annotations

"""
vSphere / vCenter client for vmdk2kvm (SYNC, no threads, no asyncio).

Policy (stable by default):
  ✅ Default export path is govc OVF (automation-friendly, debuggable)
     - export_mode="ovf_export" (default)
     - fallback chain: OVF -> OVA -> FORCED HTTPS /folder download-only
  ✅ VDDK raw disk download stays EXPERIMENTAL:
     - only runs when export_mode explicitly requests it ("vddk_download")
     - all VDDK logic lives in vddk_client.py (this file only orchestrates)
  ✅ virt-v2v is kept as a power-user path ("v2v")

Notes:
  - govc logic should live in govc_common.py (GovcRunner)
  - VDDK logic should live in vddk_client.py (VDDKESXClient)
"""

import fnmatch
import logging
import os
import re
import shlex
import shutil
import socket
import ssl
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote

# Optional: Rich progress UI (TTY friendly). Falls back to plain logs if Rich not available.
try:  # pragma: no cover
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    RICH_AVAILABLE = True
except Exception:  # pragma: no cover
    Console = None  # type: ignore
    Progress = None  # type: ignore
    SpinnerColumn = None  # type: ignore
    TextColumn = None  # type: ignore
    TimeElapsedColumn = None  # type: ignore
    RICH_AVAILABLE = False

# Optional: non-blocking pump
try:  # pragma: no cover
    import select  # type: ignore

    SELECT_AVAILABLE = True
except Exception:  # pragma: no cover
    select = None  # type: ignore
    SELECT_AVAILABLE = False

# govc helpers (single source of truth)
try:
    from .govc_common import GovcRunner
except Exception:  # pragma: no cover
    GovcRunner = None  # type: ignore

# Your repo says: from ..core.exceptions import VMwareError
try:
    from ..core.exceptions import VMwareError  # type: ignore
except Exception:  # pragma: no cover
    class VMwareError(RuntimeError):
        pass

# ✅ shared credential resolver (supports vs_password_env + vc_password_env)
try:
    from ..core.cred import resolve_vsphere_creds  # type: ignore
except Exception:  # pragma: no cover
    try:
        from ..core.creds import resolve_vsphere_creds  # type: ignore
    except Exception:  # pragma: no cover
        resolve_vsphere_creds = None  # type: ignore

# Optional: vSphere / vCenter integration (pyvmomi)
try:
    from pyVim.connect import Disconnect, SmartConnect  # type: ignore
    from pyVmomi import vim  # type: ignore

    PYVMOMI_AVAILABLE = True
except Exception:  # pragma: no cover
    SmartConnect = None  # type: ignore
    Disconnect = None  # type: ignore
    vim = None  # type: ignore
    PYVMOMI_AVAILABLE = False

# Optional: HTTP download (requests)
try:
    import requests  # type: ignore

    REQUESTS_AVAILABLE = True
except Exception:  # pragma: no cover
    requests = None  # type: ignore
    REQUESTS_AVAILABLE = False

# Optional: silence urllib3 TLS warnings when verify=False
try:  # pragma: no cover
    import urllib3  # type: ignore
except Exception:  # pragma: no cover
    urllib3 = None  # type: ignore

# ✅ VDDK client (ALL heavy logic in vddk_client.py)
try:
    from .vddk_client import VDDKConnectionSpec, VDDKESXClient  # type: ignore

    VDDK_CLIENT_AVAILABLE = True
except Exception:  # pragma: no cover
    VDDKConnectionSpec = None  # type: ignore
    VDDKESXClient = None  # type: ignore
    VDDK_CLIENT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

_BACKING_RE = re.compile(r"\[(.+?)\]\s+(.*)")


def _safe_vm_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", (name or "vm").strip()) or "vm"


# ---------------------------------------------------------------------------
# govc wrapper (thin)
# ---------------------------------------------------------------------------


class GovmomiCLI(GovcRunner):
    """
    Thin alias wrapper for older naming; actual logic lives in GovcRunner (govc_common.py).
    """

    def __init__(self, logger: Any, **kwargs: Any):
        super().__init__(logger=logger, args=type("Args", (), kwargs))

    # Keep old names used elsewhere
    def available(self) -> bool:  # type: ignore[override]
        return super().available()

    def enabled(self) -> bool:
        return super().enabled()


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------


@dataclass
class V2VExportOptions:
    """
    Export / download options.

    Stable default policy:
      - export_mode="ovf_export" is the default: stable and debuggable.
      - Fallback chain: OVF -> OVA -> HTTPS /folder download-only.
      - VDDK raw pull is experimental and only runs when explicitly requested.

    Modes:
      - export_mode="ovf_export" (default): govc export.ovf
      - export_mode="ova_export": govc export.ova
      - export_mode="download_only": list VM folder (pyvmomi) + download selected files
      - export_mode="v2v": virt-v2v (power user)
      - export_mode="vddk_download": experimental raw VMDK pull via VDDK (explicit)

    IMPORTANT:
      - datacenter defaults to "auto"
      - compute defaults to "auto" and we resolve a HOST SYSTEM path:
          host/<cluster-or-compute>/<esx-host>
    """

    vm_name: str
    export_mode: str = "ovf_export"  # stable default

    # vCenter placement resolution (for virt-v2v)
    datacenter: str = "auto"
    compute: str = "auto"

    # virt-v2v options
    transport: str = "vddk"  # virt-v2v transport: vddk|ssh
    no_verify: bool = False
    vddk_libdir: Optional[Path] = None  # passed to virt-v2v -io vddk-libdir
    vddk_thumbprint: Optional[str] = None  # passed to virt-v2v vddk-thumbprint (if provided)
    vddk_snapshot_moref: Optional[str] = None
    vddk_transports: Optional[str] = None
    output_dir: Path = Path("./out")
    output_format: str = "qcow2"  # qcow2|raw
    extra_args: Tuple[str, ...] = ()

    # Inventory printing (opt-in)
    print_vm_names: Tuple[str, ...] = ()
    vm_list_limit: int = 120
    vm_list_columns: int = 3

    # download-only options
    download_only_include_globs: Tuple[str, ...] = ("*",)
    download_only_exclude_globs: Tuple[str, ...] = (
        "*.lck",
        "*.log",
        "*.scoreboard",
        "*.vswp",
        "*.vmem",
        "*.vmsn",
        "*.nvram~",
        "*.tmp",
    )
    download_only_max_files: int = 5000
    download_only_fail_on_missing: bool = False

    # govc export options
    govc_export_snapshot: Optional[str] = None
    govc_export_power_off: bool = False
    govc_export_disk_mode: Optional[str] = None  # "thin"|"thick" etc.

    # vddk_download options (experimental)
    vddk_download_disk: Optional[str] = None
    vddk_download_output: Optional[Path] = None
    vddk_download_sectors_per_read: int = 2048  # 1 MiB (2048 * 512)
    vddk_download_log_every_bytes: int = 256 * 1024 * 1024


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class VMwareClient:
    """
    Minimal vSphere/vCenter client (SYNC):
      - pyvmomi control-plane (inventory, compute path, snapshots, datastore browser)
      - HTTPS /folder downloads via session cookie (requests)
      - virt-v2v orchestrator (sync subprocess)
      - govc stable exporter (OVF/OVA) via govc_common.GovcRunner
      - ✅ VDDK raw download is EXPERIMENTAL and lives in vddk_client.py
    """

    def __init__(
        self,
        logger: logging.Logger,
        host: str,
        user: str,
        password: str,
        *,
        port: int = 443,
        insecure: bool = False,
        timeout: Optional[float] = None,
    ) -> None:
        self.logger = logger
        self.host = (host or "").strip()
        self.user = (user or "").strip()
        self.password = (password or "").strip()
        self.port = int(port)
        self.insecure = bool(insecure)
        self.timeout = timeout

        self.si: Any = None

        # caches
        self._dc_cache: Optional[List[Any]] = None
        self._dc_name_cache: Optional[List[str]] = None
        self._host_name_cache: Optional[List[str]] = None
        self._vm_obj_by_name_cache: Dict[str, Any] = {}
        self._vm_name_cache: Optional[List[str]] = None

        # govc knobs
        self.govc_bin = os.environ.get("GOVC_BIN", "govc")
        self.no_govmomi = False
        self._govc_client: Optional[GovmomiCLI] = None

        self._rich_console = Console(stderr=True) if (RICH_AVAILABLE and Console is not None) else None

    # ---------------------------------------------------------------------
    # build from config using shared resolver (vs_* + vc_* + *_env)
    # ---------------------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        logger: logging.Logger,
        cfg: Dict[str, Any],
        *,
        port: Optional[int] = None,
        insecure: Optional[bool] = None,
        timeout: Optional[float] = None,
    ) -> "VMwareClient":
        if resolve_vsphere_creds is None:
            raise VMwareError(
                "resolve_vsphere_creds not importable. Fix import: from ..core.cred(s) import resolve_vsphere_creds"
            )
        creds = resolve_vsphere_creds(cfg)
        p = int(port if port is not None else (cfg.get("vc_port") or cfg.get("vs_port") or 443))
        ins = bool(
            insecure
            if insecure is not None
            else (
                cfg.get("vc_insecure") if cfg.get("vc_insecure") is not None else cfg.get("vs_insecure", False)
            )
        )
        c = cls(logger, creds.host, creds.user, creds.password, port=p, insecure=ins, timeout=timeout)
        c.govc_bin = str(cfg.get("govc_bin") or os.environ.get("GOVC_BIN") or "govc")
        c.no_govmomi = bool(cfg.get("no_govmomi", False))
        return c

    def has_creds(self) -> bool:
        return bool(self.host and self.user and self.password)

    def _govc(self) -> Optional[GovmomiCLI]:
        """
        Return govc wrapper if available and not disabled.
        """
        if self.no_govmomi or GovcRunner is None:
            return None
        if self._govc_client is None:
            self._govc_client = GovmomiCLI(
                self.logger,
                vcenter=self.host,
                vc_user=self.user,
                vc_password=self.password,
                vc_insecure=self.insecure,
                govc_bin=self.govc_bin,
                dc_name=None,
                no_govmomi=self.no_govmomi,
            )
        return self._govc_client if self._govc_client.available() else None

    # ---------------------------
    # Context managers
    # ---------------------------

    def __enter__(self) -> "VMwareClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            self.disconnect()
        finally:
            if exc_type is not None:
                self.logger.error("Exception in context: %s: %s", getattr(exc_type, "__name__", exc_type), exc_val)
        return False

    # ---------------------------
    # Connection
    # ---------------------------

    def _require_pyvmomi(self) -> None:
        if not PYVMOMI_AVAILABLE:
            raise VMwareError("pyvmomi not installed. Install: pip install pyvmomi")

    def _ssl_context(self) -> ssl.SSLContext:
        if self.insecure:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        return ssl.create_default_context()

    def connect(self) -> None:
        self._require_pyvmomi()
        ctx = self._ssl_context()
        try:
            if self.timeout is not None:
                old_timeout = socket.getdefaulttimeout()
                socket.setdefaulttimeout(self.timeout)
                try:
                    self.si = SmartConnect(  # type: ignore[misc]
                        host=self.host,
                        user=self.user,
                        pwd=self.password,
                        port=self.port,
                        sslContext=ctx,
                    )
                finally:
                    socket.setdefaulttimeout(old_timeout)
            else:
                self.si = SmartConnect(  # type: ignore[misc]
                    host=self.host,
                    user=self.user,
                    pwd=self.password,
                    port=self.port,
                    sslContext=ctx,
                )

            # warm caches (best-effort)
            try:
                self._refresh_datacenter_cache()
            except Exception as e:
                self.logger.debug("Datacenter cache warmup failed (non-fatal): %s", e)
            try:
                self._refresh_host_cache()
            except Exception as e:
                self.logger.debug("Host cache warmup failed (non-fatal): %s", e)

            self.logger.info("Connected to vSphere: %s:%s", self.host, self.port)
        except Exception as e:
            self.si = None
            raise VMwareError(f"Failed to connect to vSphere: {e}")

    def disconnect(self) -> None:
        try:
            if self.si is not None:
                Disconnect(self.si)  # type: ignore[misc]
        except Exception as e:
            self.logger.error("Error during disconnect: %s", e)
        finally:
            self.si = None
            self._dc_cache = None
            self._dc_name_cache = None
            self._host_name_cache = None
            self._vm_name_cache = None
            self._vm_obj_by_name_cache = {}

    def _content(self) -> Any:
        if not self.si:
            raise VMwareError("Not connected")
        try:
            return self.si.RetrieveContent()
        except Exception as e:
            raise VMwareError(f"Failed to retrieve content: {e}")

    # ---------------------------
    # Datacenters / Hosts
    # ---------------------------

    def _refresh_datacenter_cache(self) -> None:
        self._require_pyvmomi()
        content = self._content()
        view = content.viewManager.CreateContainerView(  # type: ignore[attr-defined]
            content.rootFolder, [vim.Datacenter], True
        )
        try:
            dcs = list(view.view)
            names = sorted([str(getattr(dc, "name", "")) for dc in dcs if getattr(dc, "name", None)])
            self._dc_cache = dcs
            self._dc_name_cache = names
        finally:
            try:
                view.Destroy()
            except Exception:
                pass

    def list_datacenters(self, *, refresh: bool = False) -> List[str]:
        if refresh or self._dc_name_cache is None:
            self._refresh_datacenter_cache()
        return list(self._dc_name_cache or [])

    def get_datacenter_by_name(self, name: str, *, refresh: bool = False) -> Any:
        if refresh or self._dc_cache is None:
            self._refresh_datacenter_cache()
        target = (name or "").strip()
        for dc in (self._dc_cache or []):
            if str(getattr(dc, "name", "")).strip() == target:
                return dc
        return None

    def datacenter_exists(self, name: str, *, refresh: bool = False) -> bool:
        n = (name or "").strip()
        if not n:
            return False
        return self.get_datacenter_by_name(n, refresh=refresh) is not None

    def _refresh_host_cache(self) -> None:
        self._require_pyvmomi()
        content = self._content()
        view = content.viewManager.CreateContainerView(  # type: ignore[attr-defined]
            content.rootFolder, [vim.HostSystem], True
        )
        try:
            self._host_name_cache = sorted([str(getattr(h, "name", "")) for h in view.view if getattr(h, "name", None)])
        finally:
            try:
                view.Destroy()
            except Exception:
                pass

    def list_host_names(self, *, refresh: bool = False) -> List[str]:
        if refresh or self._host_name_cache is None:
            self._refresh_host_cache()
        return list(self._host_name_cache or [])

    # ---------------------------
    # VM lookup
    # ---------------------------

    def get_vm_by_name(self, name: str) -> Any:
        self._require_pyvmomi()
        n = (name or "").strip()
        if not n:
            return None
        if n in self._vm_obj_by_name_cache:
            return self._vm_obj_by_name_cache[n]

        content = self._content()
        view = content.viewManager.CreateContainerView(  # type: ignore[attr-defined]
            content.rootFolder, [vim.VirtualMachine], True
        )
        try:
            for vm_obj in view.view:
                if getattr(vm_obj, "name", None) == n:
                    self._vm_obj_by_name_cache[n] = vm_obj
                    return vm_obj
            return None
        finally:
            try:
                view.Destroy()
            except Exception:
                pass

    def vm_to_datacenter(self, vm_obj: Any) -> Any:
        self._require_pyvmomi()
        obj = vm_obj
        for _ in range(0, 64):
            if obj is None:
                break
            if isinstance(obj, vim.Datacenter):  # type: ignore[attr-defined]
                return obj
            obj = getattr(obj, "parent", None)
        return None

    def vm_datacenter_name(self, vm_obj: Any) -> Optional[str]:
        dc = self.vm_to_datacenter(vm_obj)
        if dc is None:
            return None
        name = getattr(dc, "name", None)
        return str(name) if name else None

    def resolve_datacenter_for_vm(self, vm_name: str, preferred: Optional[str]) -> str:
        pref = (preferred or "").strip()
        if pref and pref.lower() not in ("auto", "detect", "guess") and self.datacenter_exists(pref, refresh=False):
            return pref

        vm_obj = self.get_vm_by_name(vm_name)
        vm_dc = self.vm_datacenter_name(vm_obj) if vm_obj is not None else None
        if vm_dc and self.datacenter_exists(vm_dc, refresh=False):
            return vm_dc

        self._refresh_datacenter_cache()
        if pref and pref.lower() not in ("auto", "detect", "guess") and self.datacenter_exists(pref, refresh=False):
            return pref

        if vm_obj is not None:
            vm_dc = self.vm_datacenter_name(vm_obj)
            if vm_dc and self.datacenter_exists(vm_dc, refresh=False):
                return vm_dc

        dcs = self.list_datacenters(refresh=False)
        if len(dcs) == 1:
            return dcs[0]
        raise VMwareError(
            f"Could not resolve datacenter for VM={vm_name!r}. Preferred={pref!r}, VM_dc={vm_dc!r}. "
            f"Available datacenters: {dcs}"
        )

    def _vm_runtime_host(self, vm_obj: Any) -> Any:
        rt = getattr(vm_obj, "runtime", None)
        return getattr(rt, "host", None) if rt else None

    def _host_parent_compute_name(self, host_obj: Any) -> Optional[str]:
        try:
            parent = getattr(host_obj, "parent", None)
            if parent is None:
                return None
            name = getattr(parent, "name", None)
            return str(name).strip() if name else None
        except Exception:
            return None

    def resolve_host_system_for_vm(self, vm_name: str) -> str:
        vm_obj = self.get_vm_by_name(vm_name)
        if vm_obj is None:
            raise VMwareError(f"VM not found: {vm_name!r}")

        host_obj = self._vm_runtime_host(vm_obj)
        if host_obj is None:
            raise VMwareError(
                f"VM {vm_name!r} has no runtime.host; cannot build vpx compute path. "
                f"Specify opt.compute='host/<cluster>/<host>' or opt.compute='host/<host>'. "
                f"Known hosts: {self.list_host_names(refresh=True)}"
            )

        host_name = str(getattr(host_obj, "name", "") or "").strip()
        if not host_name:
            raise VMwareError(
                f"Could not resolve ESXi host name for VM={vm_name!r}. "
                f"Known hosts: {self.list_host_names(refresh=True)}"
            )

        cr_name = self._host_parent_compute_name(host_obj)
        if cr_name and cr_name.lower() != host_name.lower():
            return f"host/{cr_name}/{host_name}"
        return f"host/{host_name}"

    def resolve_compute_for_vm(self, vm_name: str, preferred: Optional[str]) -> str:
        pref = (preferred or "").strip()
        if not pref or pref.lower() in ("auto", "detect", "guess"):
            return self.resolve_host_system_for_vm(vm_name)
        p = pref.strip().lstrip("/")
        if "/" not in p:
            return f"host/{p}"
        return p

    # ---------------------------
    # govc export (stable)
    # ---------------------------

    def govc_export_ovf(self, opt: V2VExportOptions) -> Path:
        g = self._govc()
        if g is None:
            raise VMwareError("govc not available (or disabled); cannot run OVF export")

        out_base = Path(opt.output_dir).expanduser().resolve()
        out_base.mkdir(parents=True, exist_ok=True)
        out_dir = out_base / f"{_safe_vm_name(opt.vm_name)}.ovfdir"
        out_dir.mkdir(parents=True, exist_ok=True)

        # GovcRunner.export_ovf is expected in govc_common.py
        g.export_ovf(
            vm=opt.vm_name,
            out_dir=str(out_dir),
            snapshot=opt.govc_export_snapshot,
            power_off=bool(opt.govc_export_power_off),
            disk_mode=opt.govc_export_disk_mode,
        )
        return out_dir

    def govc_export_ova(self, opt: V2VExportOptions) -> Path:
        g = self._govc()
        if g is None:
            raise VMwareError("govc not available (or disabled); cannot run OVA export")

        out_base = Path(opt.output_dir).expanduser().resolve()
        out_base.mkdir(parents=True, exist_ok=True)
        out_file = out_base / f"{_safe_vm_name(opt.vm_name)}.ova"

        # GovcRunner.export_ova is expected in govc_common.py
        g.export_ova(
            vm=opt.vm_name,
            out_file=str(out_file),
            snapshot=opt.govc_export_snapshot,
            power_off=bool(opt.govc_export_power_off),
            disk_mode=opt.govc_export_disk_mode,
        )
        return out_file

    # ---------------------------
    # Datastore parsing + HTTPS /folder download
    # ---------------------------

    @staticmethod
    def parse_backing_filename(file_name: str) -> Tuple[str, str]:
        """
        Parse VMware style backing fileName:
          "[datastore] path/to/file.ext" -> ("datastore", "path/to/file.ext")
        """
        m = _BACKING_RE.match(file_name or "")
        if not m:
            raise VMwareError(f"Could not parse backing filename: {file_name}")
        return m.group(1), m.group(2)

    @staticmethod
    def _split_ds_path(path: str) -> Tuple[str, str, str]:
        """
        "[ds] folder/file" -> (ds, "folder", "file")
        """
        ds, rel = VMwareClient.parse_backing_filename(path)
        rel = (rel or "").lstrip("/")
        folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
        base = rel.rsplit("/", 1)[1] if "/" in rel else rel
        return ds, folder, base

    def _session_cookie(self) -> str:
        if not self.si:
            raise VMwareError("Not connected")
        stub = getattr(self.si, "_stub", None)
        cookie = getattr(stub, "cookie", None)
        if not cookie:
            raise VMwareError("Could not obtain session cookie")
        return str(cookie)

    def download_datastore_file(
        self,
        *,
        datastore: str,
        ds_path: str,
        local_path: Path,
        dc_name: Optional[str] = None,
        on_bytes: Optional[Any] = None,
        chunk_size: int = 1024 * 1024,
        force_https: bool = False,
    ) -> None:
        """
        Download a single datastore file.

        Preference:
          - normally prefer govc datastore.download when present (unless force_https=True)
          - fallback to HTTPS /folder (session cookie)
        """
        if not force_https:
            g = self._govc()
            if g is not None:
                try:
                    g.datastore_download(datastore=datastore, ds_path=ds_path, local_path=local_path)
                    return
                except Exception as e:
                    self.logger.warning("govc datastore.download failed; falling back to /folder HTTP: %s", e)

        if not REQUESTS_AVAILABLE:
            raise VMwareError("requests not installed. Install: pip install requests")

        dc_use = (dc_name or "").strip()
        if dc_use and not self.datacenter_exists(dc_use, refresh=False):
            self.logger.warning("Requested dc_name=%r not found; will auto-resolve", dc_use)
            dc_use = ""

        if not dc_use:
            dcs = self.list_datacenters(refresh=False)
            if len(dcs) == 1:
                dc_use = dcs[0]
            elif dcs:
                # best-effort stable pick
                dc_use = sorted(dcs)[0]
            else:
                raise VMwareError("No datacenters found; cannot build /folder URL")

        url = f"https://{self.host}/folder/{ds_path}?dcPath={dc_use}&dsName={datastore}"
        headers = {"Cookie": self._session_cookie()}
        verify = not self.insecure

        if not verify and urllib3 is not None:  # pragma: no cover
            try:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # type: ignore[attr-defined]
            except Exception:
                pass

        local_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger.info("Downloading datastore file: [%s] %s (dc=%s) -> %s", datastore, ds_path, dc_use, local_path)

        with requests.get(  # type: ignore[union-attr]
            url,
            headers=headers,
            stream=True,
            verify=verify,
            timeout=self.timeout,
        ) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", "0") or "0")
            got = 0
            tmp = local_path.with_suffix(local_path.suffix + ".part")
            try:
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
                        if total and got and got % (128 * 1024 * 1024) < chunk_size:
                            self.logger.info(
                                "Download progress: %.1f MiB / %.1f MiB (%.1f%%)",
                                got / (1024**2),
                                total / (1024**2),
                                (got / total) * 100.0,
                            )
                os.replace(tmp, local_path)
            finally:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except Exception:
                        pass

    # ---------------------------
    # Download-only (list via DatastoreBrowser, download via govc/https)
    # ---------------------------

    def wait_for_task(self, task: Any) -> None:
        self._require_pyvmomi()
        while task.info.state not in (vim.TaskInfo.State.success, vim.TaskInfo.State.error):  # type: ignore[attr-defined]
            time.sleep(1)
        if task.info.state == vim.TaskInfo.State.error:  # type: ignore[attr-defined]
            raise VMwareError(str(task.info.error))

    def _get_vm_datastore_browser(self, vm_obj: Any) -> Any:
        self._require_pyvmomi()
        ds = None
        try:
            ds_list = getattr(vm_obj, "datastore", None) or []
            if ds_list:
                ds = ds_list[0]
        except Exception:
            ds = None
        if ds is None:
            raise VMwareError("Could not resolve VM datastore reference (vm.datastore empty)")
        browser = getattr(ds, "browser", None)
        if browser is None:
            raise VMwareError("Datastore has no browser (unexpected)")
        return browser

    def _vmx_pathname(self, vm_obj: Any) -> str:
        s = getattr(vm_obj, "summary", None)
        cfg = getattr(s, "config", None) if s else None
        vmx = getattr(cfg, "vmPathName", None) if cfg else None
        if not vmx:
            try:
                files = getattr(getattr(vm_obj, "config", None), "files", None)
                vmx = getattr(files, "vmPathName", None) if files else None
            except Exception:
                vmx = None
        if not vmx:
            raise VMwareError("Could not determine VMX path (summary.config.vmPathName missing)")
        return str(vmx)

    def _list_vm_directory_files(self, vm_obj: Any) -> Tuple[str, str, List[str]]:
        """
        Returns: (datastore_name, folder_rel, [files...]) where files are relative to folder_rel.
        Uses DatastoreBrowser.SearchDatastoreSubFolders_Task against the VM folder.
        """
        self._require_pyvmomi()
        vmx = self._vmx_pathname(vm_obj)
        ds_name, folder_rel, _base = self._split_ds_path(vmx)
        folder_rel = folder_rel.strip("/")

        search_root = f"[{ds_name}] {folder_rel}" if folder_rel else f"[{ds_name}]"
        browser = self._get_vm_datastore_browser(vm_obj)

        q = vim.HostDatastoreBrowserSearchSpec()  # type: ignore[attr-defined]
        q.matchPattern = ["*"]
        q.details = vim.HostDatastoreBrowserFileInfoDetails()  # type: ignore[attr-defined]
        q.details.fileSize = True
        q.details.modification = True
        q.details.fileType = True

        task = browser.SearchDatastoreSubFolders_Task(search_root, q)  # type: ignore[attr-defined]
        self.wait_for_task(task)

        results = getattr(task.info, "result", None) or []
        files: List[str] = []
        for r in results:
            for fi in (getattr(r, "file", None) or []):
                name = str(getattr(fi, "path", "") or "")
                if name:
                    files.append(name)

        files = sorted(set(files))
        return ds_name, folder_rel, files

    @staticmethod
    def _glob_any(name: str, globs: Sequence[str]) -> bool:
        return any(fnmatch.fnmatch(name, g) for g in globs) if globs else False

    def _filter_download_only_files(
        self,
        files: Sequence[str],
        *,
        include_globs: Sequence[str],
        exclude_globs: Sequence[str],
        max_files: int,
    ) -> List[str]:
        out: List[str] = []
        for f in files:
            if include_globs and not self._glob_any(f, include_globs):
                continue
            if exclude_globs and self._glob_any(f, exclude_globs):
                continue
            out.append(f)
        if max_files and len(out) > int(max_files):
            raise VMwareError(
                f"Refusing to download {len(out)} files (limit={max_files}). "
                "Tune download_only_max_files / include/exclude globs."
            )
        return out

    def download_only_vm(self, opt: V2VExportOptions) -> Path:
        if not self.si:
            raise VMwareError("Not connected to vSphere; cannot download. Call connect() first.")

        vm_obj = self.get_vm_by_name(opt.vm_name)
        if vm_obj is None:
            raise VMwareError(f"VM not found: {opt.vm_name!r}")

        resolved_dc = self.resolve_datacenter_for_vm(opt.vm_name, opt.datacenter)
        ds_name, folder_rel, files = self._list_vm_directory_files(vm_obj)

        selected = self._filter_download_only_files(
            files,
            include_globs=tuple(opt.download_only_include_globs or ()),
            exclude_globs=tuple(opt.download_only_exclude_globs or ()),
            max_files=int(opt.download_only_max_files or 0),
        )

        out_dir = Path(opt.output_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(
            "Download-only VM folder: dc=%s ds=%s folder=%s files=%d (selected=%d)",
            resolved_dc,
            ds_name,
            folder_rel or ".",
            len(files),
            len(selected),
        )

        failures: List[str] = []
        for name in selected:
            ds_path = f"{folder_rel}/{name}" if folder_rel else name
            local_path = out_dir / name
            try:
                self.download_datastore_file(
                    datastore=ds_name,
                    ds_path=ds_path,
                    local_path=local_path,
                    dc_name=resolved_dc,
                    force_https=False,
                )
            except Exception as e:
                msg = f"{name}: {e}"
                failures.append(msg)
                if opt.download_only_fail_on_missing:
                    raise VMwareError("Download failed:\n" + "\n".join(failures))
                self.logger.error("Download failed (non-fatal): %s", msg)

        if failures and opt.download_only_fail_on_missing:
            raise VMwareError("One or more downloads failed:\n" + "\n".join(failures))

        self.logger.info("Download-only completed: %s", out_dir)
        return out_dir

    def _download_only_vm_force_https(self, opt: V2VExportOptions) -> Path:
        """
        Forced HTTPS /folder fallback. This bypasses govc even if installed.
        """
        if not self.si:
            raise VMwareError("Not connected to vSphere; cannot download. Call connect() first.")

        vm_obj = self.get_vm_by_name(opt.vm_name)
        if vm_obj is None:
            raise VMwareError(f"VM not found: {opt.vm_name!r}")

        resolved_dc = self.resolve_datacenter_for_vm(opt.vm_name, opt.datacenter)
        ds_name, folder_rel, files = self._list_vm_directory_files(vm_obj)

        selected = self._filter_download_only_files(
            files,
            include_globs=tuple(opt.download_only_include_globs or ()),
            exclude_globs=tuple(opt.download_only_exclude_globs or ()),
            max_files=int(opt.download_only_max_files or 0),
        )

        out_dir = Path(opt.output_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(
            "FORCED HTTPS fallback: dc=%s ds=%s folder=%s files=%d (selected=%d)",
            resolved_dc,
            ds_name,
            folder_rel or ".",
            len(files),
            len(selected),
        )

        failures: List[str] = []
        for name in selected:
            ds_path = f"{folder_rel}/{name}" if folder_rel else name
            local_path = out_dir / name
            try:
                self.download_datastore_file(
                    datastore=ds_name,
                    ds_path=ds_path,
                    local_path=local_path,
                    dc_name=resolved_dc,
                    force_https=True,
                )
            except Exception as e:
                msg = f"{name}: {e}"
                failures.append(msg)
                if opt.download_only_fail_on_missing:
                    raise VMwareError("FORCED HTTPS fallback download failed:\n" + "\n".join(failures))
                self.logger.error("FORCED HTTPS fallback download failed (non-fatal): %s", msg)

        if failures and opt.download_only_fail_on_missing:
            raise VMwareError("FORCED HTTPS fallback: one or more downloads failed:\n" + "\n".join(failures))

        self.logger.info("FORCED HTTPS fallback completed: %s", out_dir)
        return out_dir

    # ---------------------------
    # virt-v2v (power user path)
    # ---------------------------

    def _vpx_uri(self, *, datacenter: str, compute: str, no_verify: bool) -> str:
        q = "?no_verify=1" if no_verify else ""
        user_enc = quote(self.user or "", safe="")
        host = (self.host or "").strip()
        dc_enc = quote((datacenter or "").strip(), safe="")
        compute_norm = (compute or "").strip().lstrip("/")
        compute_enc = quote(compute_norm, safe="/-_.")
        return f"vpx://{user_enc}@{host}/{dc_enc}/{compute_enc}{q}"

    def _write_password_file(self, base_dir: Path) -> Path:
        pw = (self.password or "").strip()
        if not pw:
            raise VMwareError(
                "Missing vSphere password for virt-v2v (-ip). "
                "Set vs_password or vs_password_env (or vc_password/vc_password_env as fallback)."
            )
        base_dir.mkdir(parents=True, exist_ok=True)
        pwfile = base_dir / f".v2v-pass-{os.getpid()}.txt"
        pwfile.write_text(pw + "\n", encoding="utf-8")
        try:
            os.chmod(pwfile, 0o600)
        except Exception:
            pass
        return pwfile

    def _build_virt_v2v_cmd(self, opt: V2VExportOptions, *, password_file: Path) -> List[str]:
        if not opt.vm_name:
            raise VMwareError("V2VExportOptions.vm_name is required")
        if not self.si:
            raise VMwareError("Not connected to vSphere; cannot export. Call connect() first.")

        resolved_dc = self.resolve_datacenter_for_vm(opt.vm_name, opt.datacenter)
        resolved_compute = self.resolve_compute_for_vm(opt.vm_name, opt.compute)

        transport = (opt.transport or "").strip().lower()
        if transport not in ("vddk", "ssh"):
            raise VMwareError(f"Unsupported virt-v2v transport: {transport!r} (expected 'vddk' or 'ssh')")

        argv: List[str] = [
            "virt-v2v",
            "-i",
            "libvirt",
            "-ic",
            self._vpx_uri(datacenter=resolved_dc, compute=resolved_compute, no_verify=opt.no_verify),
            "-it",
            transport,
            "-ip",
            str(password_file),
        ]

        # For virt-v2v VDDK transport we only pass through options; we do NOT implement VDDK here.
        if transport == "vddk":
            if opt.vddk_libdir:
                argv += ["-io", f"vddk-libdir={str(Path(opt.vddk_libdir))}"]
            if opt.vddk_thumbprint:
                argv += ["-io", f"vddk-thumbprint={str(opt.vddk_thumbprint)}"]
            if opt.vddk_snapshot_moref:
                argv += ["-io", f"vddk-snapshot={opt.vddk_snapshot_moref}"]
            if opt.vddk_transports:
                argv += ["-io", f"vddk-transports={opt.vddk_transports}"]

        argv.append(opt.vm_name)
        opt.output_dir.mkdir(parents=True, exist_ok=True)
        argv += ["-o", "local", "-os", str(opt.output_dir), "-of", opt.output_format]
        argv += list(opt.extra_args)
        return argv

    def _run_logged_subprocess(self, argv: Sequence[str], *, env: Optional[Dict[str, str]] = None) -> int:
        self.logger.info("Running: %s", " ".join(shlex.quote(a) for a in argv))
        proc = subprocess.Popen(
            list(argv),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            bufsize=1,
        )
        assert proc.stdout is not None
        assert proc.stderr is not None

        if SELECT_AVAILABLE:
            try:
                os.set_blocking(proc.stdout.fileno(), False)  # type: ignore[attr-defined]
                os.set_blocking(proc.stderr.fileno(), False)  # type: ignore[attr-defined]
            except Exception:
                pass

        def _pump_available() -> List[str]:
            lines: List[str] = []
            if not SELECT_AVAILABLE:
                out_line = proc.stdout.readline()
                err_line = proc.stderr.readline()
                if out_line:
                    lines.append(out_line.rstrip("\n"))
                if err_line:
                    lines.append(err_line.rstrip("\n"))
                return lines

            rlist = [proc.stdout, proc.stderr]
            try:
                ready, _, _ = select.select(rlist, [], [], 0.20)  # type: ignore[union-attr]
            except Exception:
                ready = rlist

            for s in ready:
                try:
                    chunk = s.read()
                except Exception:
                    chunk = ""
                if not chunk:
                    continue
                for ln in chunk.splitlines():
                    lines.append(ln.rstrip("\n"))
            return lines

        use_rich = bool(
            RICH_AVAILABLE
            and self._rich_console is not None
            and hasattr(self._rich_console, "is_terminal")
            and self._rich_console.is_terminal  # type: ignore[attr-defined]
        )

        last_line = ""
        if use_rich and Progress is not None and SpinnerColumn is not None and TextColumn is not None and TimeElapsedColumn is not None:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                console=self._rich_console,  # type: ignore[arg-type]
                transient=True,
            ) as progress:
                task_id = progress.add_task("virt-v2v running…", total=None)
                while True:
                    lines = _pump_available()
                    for ln in lines:
                        last_line = ln.strip()
                        if last_line:
                            self.logger.info("%s", last_line)
                            show = last_line[:117] + "..." if len(last_line) > 120 else last_line
                            progress.update(task_id, description=f"virt-v2v running… {show}")

                    if proc.poll() is not None:
                        for _ in range(0, 10):
                            more = _pump_available()
                            if not more:
                                break
                            for ln in more:
                                last_line = ln.strip()
                                if last_line:
                                    self.logger.info("%s", last_line)
                        break

                rc = int(proc.wait())
                progress.update(task_id, description=f"virt-v2v finished (rc={rc})")
                return rc

        # Fallback: simple
        while True:
            out_line = proc.stdout.readline()
            err_line = proc.stderr.readline()
            if out_line:
                self.logger.info("%s", out_line.rstrip())
            if err_line:
                self.logger.info("%s", err_line.rstrip())
            if (not out_line) and (not err_line) and (proc.poll() is not None):
                break
        return int(proc.wait())

    def v2v_export_vm(self, opt: V2VExportOptions) -> Path:
        if shutil.which("virt-v2v") is None:
            raise VMwareError("virt-v2v not found in PATH. Install virt-v2v/libguestfs tooling.")
        if not self.si:
            raise VMwareError("Not connected to vSphere; cannot export. Call connect() first.")

        pwfile = self._write_password_file(opt.output_dir)
        try:
            argv = self._build_virt_v2v_cmd(opt, password_file=pwfile)
            rc = self._run_logged_subprocess(argv, env=os.environ.copy())
            if rc != 0:
                raise VMwareError(f"virt-v2v export failed (rc={rc})")
            self.logger.info("virt-v2v export finished OK -> %s", opt.output_dir)
            return opt.output_dir
        finally:
            try:
                pwfile.unlink()
            except FileNotFoundError:
                pass
            except Exception as e:
                self.logger.warning("Failed to remove password file %s: %s", pwfile, e)

    # ---------------------------
    # VDDK raw disk download (experimental orchestration only)
    # ---------------------------

    def _require_vddk_client(self) -> None:
        if not VDDK_CLIENT_AVAILABLE:
            raise VMwareError(
                "VDDK raw download requested but vddk_client is not importable. "
                "Ensure vmdk2kvm/vsphere/vddk_client.py exists and imports cleanly."
            )

    def vm_disks(self, vm_obj: Any) -> List[Any]:
        self._require_pyvmomi()
        disks: List[Any] = []
        devices = getattr(getattr(getattr(vm_obj, "config", None), "hardware", None), "device", []) or []
        for dev in devices:
            if isinstance(dev, vim.vm.device.VirtualDisk):  # type: ignore[attr-defined]
                disks.append(dev)
        return disks

    def select_disk(self, vm_obj: Any, label_or_index: Optional[str]) -> Any:
        self._require_pyvmomi()
        disks = self.vm_disks(vm_obj)
        if not disks:
            raise VMwareError("No virtual disks found on VM")
        if label_or_index is None:
            return disks[0]
        s = str(label_or_index).strip()
        if s.isdigit():
            idx = int(s)
            if idx < 0 or idx >= len(disks):
                raise VMwareError(f"Disk index out of range: {idx} (found {len(disks)})")
            return disks[idx]
        sl = s.lower()
        for d in disks:
            label = getattr(getattr(d, "deviceInfo", None), "label", "") or ""
            if sl in str(label).lower():
                return d
        raise VMwareError(f"No disk matching label: {s}")

    def _vm_disk_backing_filename(self, disk_obj: Any) -> str:
        backing = getattr(disk_obj, "backing", None)
        fn = getattr(backing, "fileName", None) if backing else None
        if not fn:
            raise VMwareError("Selected disk has no backing.fileName (unexpected)")
        return str(fn)

    def _resolve_esx_host_for_vm(self, vm_obj: Any) -> str:
        host_obj = self._vm_runtime_host(vm_obj)
        if host_obj is None:
            raise VMwareError("VM has no runtime.host; cannot determine ESXi host for VDDK download")
        name = str(getattr(host_obj, "name", "") or "").strip()
        if not name:
            raise VMwareError("Could not resolve ESXi host name for VM runtime.host")
        return name

    def _default_vddk_download_path(self, opt: V2VExportOptions, *, disk_index: int) -> Path:
        out_dir = Path(opt.output_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / f"{_safe_vm_name(opt.vm_name)}-disk{disk_index}.vmdk"

    def vddk_download_disk(self, opt: V2VExportOptions) -> Path:
        """
        export_mode="vddk_download" (EXPERIMENTAL)
          - control-plane: pyvmomi finds ESXi host + disk backing path
          - data-plane: vddk_client.VDDKESXClient reads and writes local file
        """
        self._require_pyvmomi()
        self._require_vddk_client()
        if not self.si:
            raise VMwareError("Not connected to vSphere; cannot download. Call connect() first.")

        vm_obj = self.get_vm_by_name(opt.vm_name)
        if vm_obj is None:
            raise VMwareError(f"VM not found: {opt.vm_name!r}")

        disk_obj = self.select_disk(vm_obj, opt.vddk_download_disk)
        try:
            disks = self.vm_disks(vm_obj)
            disk_index = disks.index(disk_obj)
        except Exception:
            disk_index = 0

        remote_vmdk = self._vm_disk_backing_filename(disk_obj)  # "[ds] folder/disk.vmdk"
        esx_host = self._resolve_esx_host_for_vm(vm_obj)

        local_path = Path(opt.vddk_download_output) if opt.vddk_download_output else self._default_vddk_download_path(opt, disk_index=disk_index)

        # NOTE: libdir/thumbprint normalization and thumbprint computation are handled by vddk_client itself.
        # We pass values through and keep the orchestration minimal.
        spec = VDDKConnectionSpec(  # type: ignore[misc]
            host=esx_host,
            user=self.user,
            password=self.password,
            port=443,
            vddk_libdir=Path(opt.vddk_libdir) if opt.vddk_libdir else None,
            transport_modes=opt.vddk_transports or "nbdssl:nbd",
            thumbprint=opt.vddk_thumbprint,
            insecure=bool(opt.no_verify),
        )

        c = VDDKESXClient(self.logger, spec)  # type: ignore[misc]

        def _progress(done: int, total: int, pct: float) -> None:
            le = int(opt.vddk_download_log_every_bytes or 0)
            if total and done and le > 0:
                if done % le < int(opt.vddk_download_sectors_per_read or 2048) * 512:
                    self.logger.info(
                        "VDDK download progress: %.1f GiB / %.1f GiB (%.1f%%)",
                        done / (1024**3),
                        total / (1024**3),
                        pct,
                    )

        self.logger.warning("VDDK raw download is EXPERIMENTAL (explicit mode requested).")
        self.logger.info(
            "VDDK download: vm=%s disk=%s esx=%s remote=%s -> %s",
            opt.vm_name,
            opt.vddk_download_disk or str(disk_index),
            esx_host,
            remote_vmdk,
            local_path,
        )

        c.connect()
        try:
            out = c.download_vmdk(
                remote_vmdk,
                Path(local_path),
                sectors_per_read=int(opt.vddk_download_sectors_per_read or 2048),
                progress=_progress,
                log_every_bytes=int(opt.vddk_download_log_every_bytes or 0),
            )
            return Path(out)
        finally:
            c.disconnect()

    # ---------------------------
    # Unified entrypoint (policy)
    # ---------------------------

    def export_vm(self, opt: V2VExportOptions) -> Path:
        """
        Unified entrypoint (SYNC).

        Policy (STRICT + stable default):
          - Default is govc OVF export: export_mode="ovf_export"
          - Fallback chain for stable export:
              1) govc export.ovf
              2) govc export.ova
              3) HTTPS /folder download-only (FORCED; bypass govc)
          - VDDK only when explicitly requested:
              * export_mode="vddk_download" -> VDDK raw disk download (experimental)
          - Back-compat:
              * "v2v" keeps virt-v2v behavior
              * "download_only" keeps folder download behavior
        """
        mode = (opt.export_mode or "ovf_export").strip().lower()

        # Experimental VDDK
        if mode in ("vddk_download", "vddk-download", "vddkdownload"):
            return self.vddk_download_disk(opt)

        # Power-user virt-v2v
        if mode in ("v2v", "virt-v2v", "virt_v2v"):
            return self.v2v_export_vm(opt)

        # Explicit download-only
        if mode in ("download_only", "download-only", "download"):
            return self.download_only_vm(opt)

        # Stable default: OVF -> OVA -> forced HTTPS
        if mode in ("ovf_export", "ovf", "export_ovf", "govc_ovf", "govc_export"):
            try:
                self.logger.info("Export mode=OVF (stable): attempting govc export.ovf for VM=%s", opt.vm_name)
                return self.govc_export_ovf(opt)
            except Exception as e_ovf:
                self.logger.warning("govc export.ovf failed; trying export.ova next: %s", e_ovf)
                try:
                    return self.govc_export_ova(opt)
                except Exception as e_ova:
                    self.logger.warning("govc export.ova also failed; forcing HTTPS /folder fallback: %s", e_ova)
                    return self._download_only_vm_force_https(opt)

        if mode in ("ova_export", "ova", "export_ova", "govc_ova"):
            try:
                self.logger.info("Export mode=OVA: attempting govc export.ova for VM=%s", opt.vm_name)
                return self.govc_export_ova(opt)
            except Exception as e_ova:
                self.logger.warning("govc export.ova failed; forcing HTTPS /folder fallback: %s", e_ova)
                return self._download_only_vm_force_https(opt)

        # Unknown mode -> stable chain
        self.logger.warning("Unknown export_mode=%r; using stable OVF->OVA->HTTPS chain", mode)
        try:
            return self.govc_export_ovf(opt)
        except Exception as e_ovf:
            self.logger.warning("govc export.ovf failed; trying export.ova: %s", e_ovf)
            try:
                return self.govc_export_ova(opt)
            except Exception as e_ova:
                self.logger.warning("govc export.ova failed; forcing HTTPS /folder fallback: %s", e_ova)
                return self._download_only_vm_force_https(opt)
