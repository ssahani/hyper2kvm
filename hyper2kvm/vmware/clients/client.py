# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# hyper2kvm/vmware/clients/client.py
from __future__ import annotations

"""
vSphere / vCenter client for hyper2kvm.
"""

import logging
import os
import re
import ssl
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
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
    from ..transports.govc_common import GovcRunner
except Exception:  # pragma: no cover
    GovcRunner = None  # type: ignore

# OVF Tool client
try:
    from ..transports.ovftool_client import (
        find_ovftool,
        ovftool_version,
        export_to_ova,
        deploy_ovf_or_ova,
        OvfExportOptions,
        OvfDeployOptions,
        OvfToolPaths,
        OvfToolError,
        OvfToolNotFound,
    )
except Exception:  # pragma: no cover
    find_ovftool = None  # type: ignore
    ovftool_version = None  # type: ignore
    export_to_ova = None  # type: ignore
    deploy_ovf_or_ova = None  # type: ignore
    OvfExportOptions = None  # type: ignore
    OvfDeployOptions = None  # type: ignore
    OvfToolPaths = None  # type: ignore
    OvfToolError = None  # type: ignore
    OvfToolNotFound = None  # type: ignore

# HTTP/HTTPS download client
try:
    from ..transports.http_client import HTTPDownloadClient, VMwareError
except Exception:  # pragma: no cover
    HTTPDownloadClient = None  # type: ignore
    try:
        from ...core.exceptions import VMwareError  # type: ignore
    except Exception:  # pragma: no cover

        class VMwareError(RuntimeError):
            pass


# ✅ shared credential resolver (supports vs_password_env + vc_password_env)
try:
    from ...core.cred import resolve_vsphere_creds  # type: ignore
except Exception:  # pragma: no cover
    try:
        from ...core.creds import resolve_vsphere_creds  # type: ignore
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

# Optional: requests library for HTTP operations
try:  # pragma: no cover
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
    from ..transports.vddk_client import VDDKConnectionSpec, VDDKESXClient  # type: ignore

    VDDK_CLIENT_AVAILABLE = True
except Exception:  # pragma: no cover
    VDDKConnectionSpec = None  # type: ignore
    VDDKESXClient = None  # type: ignore
    VDDK_CLIENT_AVAILABLE = False


from ..utils.utils import safe_vm_name as _safe_vm_name, quote_inventory_path as _quote_inventory_path

_BACKING_RE = re.compile(r"\[(.+?)\]\s+(.*)")


class GovmomiCLI(GovcRunner):
    """
    Thin alias wrapper for older naming; actual logic lives in GovcRunner (govc_common.py).
    """

    def __init__(self, logger: Any, **kwargs: Any):
        super().__init__(logger=logger, args=type("Args", (), kwargs))

    def available(self) -> bool:  # type: ignore[override]
        return super().available()

    def enabled(self) -> bool:
        return super().enabled()


@dataclass
class V2VExportOptions:
    """
    Export and download options for vSphere VMs.
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

    # OVF Tool options
    ovftool_path: Optional[str] = None
    ovftool_no_ssl_verify: bool = True
    ovftool_thumbprint: Optional[str] = None
    ovftool_accept_all_eulas: bool = True
    ovftool_quiet: bool = False
    ovftool_verbose: bool = False
    ovftool_overwrite: bool = False
    ovftool_disk_mode: Optional[str] = None
    ovftool_retries: int = 0
    ovftool_retry_backoff_s: float = 2.0
    ovftool_extra_args: Tuple[str, ...] = ()

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


# Import all functions from split modules

# Import datastore operations
from ..utils.datastore import (
    list_datacenters as _datastore_list_datacenters,
    get_datacenter_by_name as _datastore_get_datacenter_by_name,
    datacenter_exists as _datastore_datacenter_exists,
    list_host_names as _datastore_list_host_names,
    get_vm_by_name as _datastore_get_vm_by_name,
    vm_to_datacenter as _datastore_vm_to_datacenter,
    vm_datacenter_name as _datastore_vm_datacenter_name,
    resolve_datacenter_for_vm as _datastore_resolve_datacenter_for_vm,
    resolve_compute_for_vm as _datastore_resolve_compute_for_vm,
    parse_backing_filename as _datastore_parse_backing_filename,
    download_datastore_file as _datastore_download_datastore_file,
    download_only_vm as _datastore_download_only_vm,
    _download_only_vm_force_https as _datastore_download_only_vm_force_https,
    _refresh_datacenter_cache as _datastore_refresh_datacenter_cache,
    _refresh_host_cache as _datastore_refresh_host_cache,
    resolve_host_system_for_vm as _datastore_resolve_host_system_for_vm,
    wait_for_task as _datastore_wait_for_task,
    _vm_runtime_host as _datastore_vm_runtime_host,
)

# Import v2v operations
from ..utils.v2v import (
    v2v_export_vm as _v2v_export_vm,
)

# Import ovftool operations
from ..transports.ovftool_loader import (
    govc_export_ovf as _ovftool_govc_export_ovf,
    govc_export_ova as _ovftool_govc_export_ova,
    ovftool_export_vm as _ovftool_ovftool_export_vm,
    ovftool_deploy_ova as _ovftool_ovftool_deploy_ova,
)

# Import vddk operations
from ..transports.vddk_loader import (
    vddk_download_disk as _vddk_download_disk,
    vm_disks as _vddk_vm_disks,
    select_disk as _vddk_select_disk,
)


# Client


class VMwareClient:
    """
    vSphere/vCenter client for VM operations and export.
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

        # HTTP download client
        self._http_client: Optional[HTTPDownloadClient] = None

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

        # OVF Tool knobs
        self.ovftool_path: Optional[str] = None
        self._ovftool_paths: Optional[OvfToolPaths] = None

        self._rich_console = Console(stderr=True) if (RICH_AVAILABLE and Console is not None) else None

    # build from config using shared resolver (vs_* + vc_* + *_env)

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
        c.ovftool_path = str(cfg.get("ovftool_path", "")) or None
        return c

    def has_creds(self) -> bool:
        return bool(self.host and self.user and self.password)

    # Internal helpers: tool handles

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

    def _http_download_client(self) -> HTTPDownloadClient:
        """
        Return HTTP download client.
        """
        if self._http_client is None:
            if HTTPDownloadClient is None:
                raise VMwareError("HTTP download client not available. Ensure http_download_client.py is importable.")
            self._http_client = HTTPDownloadClient(
                logger=self.logger,
                host=self.host,
                port=self.port,
                insecure=self.insecure,
                timeout=self.timeout,
            )
        return self._http_client

    def _ovftool(self) -> OvfToolPaths:
        """
        Return OVF Tool paths if available.
        """
        if self._ovftool_paths is None:
            if find_ovftool is None:
                raise VMwareError("OVF Tool client not available. Ensure ovftool_client.py is importable.")
            try:
                self._ovftool_paths = find_ovftool(self.ovftool_path)
                version = ovftool_version(self._ovftool_paths) if ovftool_version is not None else None
                self.logger.info(
                    "OVF Tool found: %s (version: %s)",
                    getattr(self._ovftool_paths, "ovftool_bin", "ovftool"),
                    version or "unknown",
                )
            except Exception as e:
                raise VMwareError(f"OVF Tool not found: {e}")
        return self._ovftool_paths

    # Context managers

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

    # Connection

    def _require_pyvmomi(self) -> None:
        if not PYVMOMI_AVAILABLE:
            raise VMwareError("pyvmomi not installed. Install: pip install pyvmomi")

    def _ssl_context(self) -> ssl.SSLContext:
        """
        Create SSL context for vSphere connections.

        SECURITY WARNING: When insecure=True, TLS certificate verification is completely
        disabled, making connections vulnerable to Man-in-the-Middle attacks. Only use
        insecure mode in trusted network environments with self-signed certificates.
        """
        if self.insecure:
            self.logger.warning(
                "TLS certificate verification is DISABLED (insecure=True). "
                "Connections are vulnerable to Man-in-the-Middle attacks. "
                "Only use this in trusted environments with self-signed certificates."
            )
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False  # SECURITY: Disabled for self-signed cert support
            ctx.verify_mode = ssl.CERT_NONE  # SECURITY: Disabled for self-signed cert support
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

            # Set session cookie for HTTP download client
            try:
                stub = getattr(self.si, "_stub", None)
                cookie = getattr(stub, "cookie", None)
                if cookie:
                    self._http_download_client().set_session_cookie(str(cookie))
            except Exception as e:
                self.logger.debug("Failed to set HTTP session cookie: %s", e)

            # warm caches (best-effort)
            try:
                _datastore_refresh_datacenter_cache(self)
            except Exception as e:
                self.logger.debug("Datacenter cache warmup failed (non-fatal): %s", e)
            try:
                _datastore_refresh_host_cache(self)
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

    # Datacenters / Hosts - Delegate to vmware_datastore

    def _refresh_datacenter_cache(self) -> None:
        return _datastore_refresh_datacenter_cache(self)

    def list_datacenters(self, *, refresh: bool = False) -> List[str]:
        return _datastore_list_datacenters(self, refresh=refresh)

    def get_datacenter_by_name(self, name: str, *, refresh: bool = False) -> Any:
        return _datastore_get_datacenter_by_name(self, name, refresh=refresh)

    def datacenter_exists(self, name: str, *, refresh: bool = False) -> bool:
        return _datastore_datacenter_exists(self, name, refresh=refresh)

    def _refresh_host_cache(self) -> None:
        return _datastore_refresh_host_cache(self)

    def list_host_names(self, *, refresh: bool = False) -> List[str]:
        return _datastore_list_host_names(self, refresh=refresh)

    # VM lookup - Delegate to vmware_datastore

    def get_vm_by_name(self, name: str) -> Any:
        return _datastore_get_vm_by_name(self, name)

    def vm_to_datacenter(self, vm_obj: Any) -> Any:
        return _datastore_vm_to_datacenter(self, vm_obj)

    def vm_datacenter_name(self, vm_obj: Any) -> Optional[str]:
        return _datastore_vm_datacenter_name(self, vm_obj)

    def resolve_datacenter_for_vm(self, vm_name: str, preferred: Optional[str]) -> str:
        return _datastore_resolve_datacenter_for_vm(self, vm_name, preferred)

    def _vm_runtime_host(self, vm_obj: Any) -> Any:
        return _datastore_vm_runtime_host(self, vm_obj)

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
        return _datastore_resolve_host_system_for_vm(self, vm_name)

    def resolve_compute_for_vm(self, vm_name: str, preferred: Optional[str]) -> str:
        return _datastore_resolve_compute_for_vm(self, vm_name, preferred)

    # govc export (stable) - Delegate to vmware_ovftool

    def _ensure_output_dir(self, base: Path) -> Path:
        out = Path(base).expanduser().resolve()
        out.mkdir(parents=True, exist_ok=True)
        return out

    def govc_export_ovf(self, opt: V2VExportOptions) -> Path:
        return _ovftool_govc_export_ovf(self, opt)

    def govc_export_ova(self, opt: V2VExportOptions) -> Path:
        return _ovftool_govc_export_ova(self, opt)

    # OVF Tool export/deploy - Delegate to vmware_ovftool

    def _vm_inventory_path_under_vmfolder(self, vm_obj: Any, dc_obj: Any) -> str:
        """
        Compute inventory path relative to Datacenter/vm folder, e.g.
          "<folder1>/<folder2>/<vmname>"

        This is what ovftool expects after ".../<dc_name>/vm/".
        """
        self._require_pyvmomi()

        vm_folder = getattr(dc_obj, "vmFolder", None)
        if vm_folder is None:
            raise VMwareError("Datacenter has no vmFolder (unexpected)")

        parts: List[str] = []
        obj = vm_obj
        for _ in range(0, 96):
            if obj is None:
                break
            name = getattr(obj, "name", None)
            if name:
                parts.append(str(name))
            parent = getattr(obj, "parent", None)
            if parent is None:
                break
            if parent == vm_folder:
                break
            obj = parent

        if not parts:
            # fallback: at least the VM name
            return str(getattr(vm_obj, "name", "") or "").strip() or "vm"

        parts = list(reversed(parts))
        return "/".join([p.strip("/") for p in parts if p.strip("/")])

    def _build_ovftool_source_url(self, vm_name: str) -> str:
        """
        Build a vi:// source URL for OVF Tool from VM object + inventory path.

        Format:
          vi://user:pass@host/<Datacenter>/vm/<folder...>/<vm>
        """
        vm_obj = self.get_vm_by_name(vm_name)
        if not vm_obj:
            raise VMwareError(f"VM not found: {vm_name}")

        dc_name = self.resolve_datacenter_for_vm(vm_name, "auto")
        dc_obj = self.get_datacenter_by_name(dc_name, refresh=False)
        if dc_obj is None:
            dc_obj = self.get_datacenter_by_name(dc_name, refresh=True)
        if dc_obj is None:
            raise VMwareError(f"Could not resolve datacenter object for dc={dc_name!r}")

        inv_rel = self._vm_inventory_path_under_vmfolder(vm_obj, dc_obj)
        inv_rel_q = _quote_inventory_path(inv_rel)

        # NOTE: credential embedding is required by ovftool; do not log this URL verbatim.
        dc_q = _quote_inventory_path(dc_name)
        return f"vi://{self.user}:{self.password}@{self.host}/{dc_q}/vm/{inv_rel_q}"

    def _ovftool_export_options(self, opt: V2VExportOptions) -> Any:
        if OvfExportOptions is None:
            raise VMwareError("OvfExportOptions not available (ovftool_client import failed)")
        return OvfExportOptions(
            no_ssl_verify=opt.ovftool_no_ssl_verify,
            thumbprint=opt.ovftool_thumbprint,
            accept_all_eulas=opt.ovftool_accept_all_eulas,
            quiet=opt.ovftool_quiet,
            verbose=opt.ovftool_verbose,
            overwrite=opt.ovftool_overwrite,
            disk_mode=opt.ovftool_disk_mode,
            retries=opt.ovftool_retries,
            retry_backoff_s=opt.ovftool_retry_backoff_s,
            extra_args=opt.ovftool_extra_args,
        )

    def _ovftool_deploy_options(self, opt: V2VExportOptions, *, name: str) -> Any:
        if OvfDeployOptions is None:
            raise VMwareError("OvfDeployOptions not available (ovftool_client import failed)")
        return OvfDeployOptions(
            no_ssl_verify=opt.ovftool_no_ssl_verify,
            thumbprint=opt.ovftool_thumbprint,
            accept_all_eulas=opt.ovftool_accept_all_eulas,
            overwrite=opt.ovftool_overwrite,
            name=name,
            disk_mode=opt.ovftool_disk_mode,
            quiet=opt.ovftool_quiet,
            verbose=opt.ovftool_verbose,
            retries=opt.ovftool_retries,
            retry_backoff_s=opt.ovftool_retry_backoff_s,
            extra_args=opt.ovftool_extra_args,
        )

    def ovftool_export_vm(self, opt: V2VExportOptions) -> Path:
        return _ovftool_ovftool_export_vm(self, opt)

    def ovftool_deploy_ova(self, source_ova: Path, opt: V2VExportOptions) -> None:
        return _ovftool_ovftool_deploy_ova(self, source_ova, opt)

    # Datastore parsing + HTTPS /folder download - Delegate to vmware_datastore

    @staticmethod
    def parse_backing_filename(file_name: str) -> Tuple[str, str]:
        """
        Parse VMware style backing fileName:
          "[datastore] path/to/file.ext" -> ("datastore", "path/to/file.ext")
        """
        return _datastore_parse_backing_filename(file_name)

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

    def _resolve_datacenter_for_download(self, dc_name: Optional[str]) -> str:
        """
        Resolve a usable datacenter name for /folder URL construction.
        """
        dc_use = (dc_name or "").strip()
        if dc_use and not self.datacenter_exists(dc_use, refresh=False):
            self.logger.warning("Requested dc_name=%r not found; will auto-resolve", dc_use)
            dc_use = ""

        if dc_use:
            return dc_use

        dcs = self.list_datacenters(refresh=False)
        if len(dcs) == 1:
            return dcs[0]
        if dcs:
            return sorted(dcs)[0]
        raise VMwareError("No datacenters found; cannot build /folder URL")

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
        return _datastore_download_datastore_file(
            self,
            datastore=datastore,
            ds_path=ds_path,
            local_path=local_path,
            dc_name=dc_name,
            on_bytes=on_bytes,
            chunk_size=chunk_size,
            force_https=force_https,
        )

    # Download-only (list via DatastoreBrowser, download via govc/https) - Delegate to vmware_datastore

    def wait_for_task(self, task: Any) -> None:
        return _datastore_wait_for_task(self, task)

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
        import fnmatch
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

    def _download_selected_files(
        self,
        *,
        selected: Sequence[str],
        out_dir: Path,
        ds_name: str,
        folder_rel: str,
        dc_name: str,
        force_https: bool,
        fail_on_missing: bool,
        log_prefix: str,
    ) -> None:
        failures: List[str] = []
        for name in selected:
            ds_path = f"{folder_rel}/{name}" if folder_rel else name
            local_path = out_dir / name
            try:
                self.download_datastore_file(
                    datastore=ds_name,
                    ds_path=ds_path,
                    local_path=local_path,
                    dc_name=dc_name,
                    force_https=force_https,
                )
            except Exception as e:
                msg = f"{name}: {e}"
                failures.append(msg)
                if fail_on_missing:
                    raise VMwareError(f"{log_prefix} download failed:\n" + "\n".join(failures))
                self.logger.error("%s download failed (non-fatal): %s", log_prefix, msg)

        if failures and fail_on_missing:
            raise VMwareError(f"{log_prefix}: one or more downloads failed:\n" + "\n".join(failures))

    def download_only_vm(self, opt: V2VExportOptions) -> Path:
        return _datastore_download_only_vm(self, opt)

    def _download_only_vm_force_https(self, opt: V2VExportOptions) -> Path:
        """
        Forced HTTPS /folder fallback. This bypasses govc even if installed.
        """
        return _datastore_download_only_vm_force_https(self, opt)

    # virt-v2v (power user path) - Delegate to vmware_v2v

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
        base_dir = self._ensure_output_dir(base_dir)
        pwfile = base_dir / f".v2v-pass-{os.getpid()}.txt"
        # Create file atomically with secure permissions to avoid race condition (CWE-377)
        try:
            fd = os.open(str(pwfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            # Stale file from crashed run (extremely rare - requires PID reuse after reboot)
            # Remove it and retry once
            pwfile.unlink(missing_ok=True)
            fd = os.open(str(pwfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, (pw + "\n").encode('utf-8'))
        finally:
            os.close(fd)
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
        self._ensure_output_dir(opt.output_dir)
        argv += ["-o", "local", "-os", str(opt.output_dir), "-of", opt.output_format]
        argv += list(opt.extra_args)
        return argv

    def _popen_text(self, argv: Sequence[str], *, env: Optional[Dict[str, str]] = None) -> Any:
        import subprocess
        import shlex

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
        return proc

    def _pump_lines_blocking(self, proc: Any) -> List[str]:
        assert proc.stdout is not None
        assert proc.stderr is not None
        lines: List[str] = []
        out_line = proc.stdout.readline()
        err_line = proc.stderr.readline()
        if out_line:
            lines.append(out_line.rstrip("\n"))
        if err_line:
            lines.append(err_line.rstrip("\n"))
        return lines

    def _pump_lines_select(self, proc: Any, *, timeout_s: float = 0.20) -> List[str]:
        assert proc.stdout is not None
        assert proc.stderr is not None
        rlist = [proc.stdout, proc.stderr]
        try:
            ready, _, _ = select.select(rlist, [], [], timeout_s)  # type: ignore[union-attr]
        except Exception:
            ready = rlist

        lines: List[str] = []
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

    def _use_rich_progress(self) -> bool:
        return bool(
            RICH_AVAILABLE
            and self._rich_console is not None
            and hasattr(self._rich_console, "is_terminal")
            and self._rich_console.is_terminal  # type: ignore[attr-defined]
            and Progress is not None
            and SpinnerColumn is not None
            and TextColumn is not None
            and TimeElapsedColumn is not None
        )

    def _drain_remaining_output(self, proc: Any, *, max_rounds: int = 10) -> None:
        for _ in range(0, max_rounds):
            lines = self._pump_lines_select(proc, timeout_s=0.05) if SELECT_AVAILABLE else self._pump_lines_blocking(proc)
            if not lines:
                break
            for ln in lines:
                s = ln.strip()
                if s:
                    self.logger.info("%s", s)

    def _run_logged_subprocess(self, argv: Sequence[str], *, env: Optional[Dict[str, str]] = None) -> int:
        proc = self._popen_text(argv, env=env)

        def pump() -> List[str]:
            if SELECT_AVAILABLE:
                return self._pump_lines_select(proc)
            return self._pump_lines_blocking(proc)

        if self._use_rich_progress():
            assert self._rich_console is not None
            assert Progress is not None
            assert SpinnerColumn is not None
            assert TextColumn is not None
            assert TimeElapsedColumn is not None

            last_line = ""
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                console=self._rich_console,  # type: ignore[arg-type]
                transient=True,
            ) as progress:
                task_id = progress.add_task("virt-v2v running…", total=None)
                while True:
                    for ln in pump():
                        last_line = ln.strip()
                        if last_line:
                            self.logger.info("%s", last_line)
                            show = last_line[:117] + "..." if len(last_line) > 120 else last_line
                            progress.update(task_id, description=f"virt-v2v running… {show}")

                    if proc.poll() is not None:
                        self._drain_remaining_output(proc, max_rounds=10)
                        break

                rc = int(proc.wait())
                progress.update(task_id, description=f"virt-v2v finished (rc={rc})")
                return rc

        # Plain logger loop
        while True:
            lines = pump()
            for ln in lines:
                s = ln.strip()
                if s:
                    self.logger.info("%s", s)
            if (not lines) and (proc.poll() is not None):
                break

        self._drain_remaining_output(proc, max_rounds=10)
        return int(proc.wait())

    def v2v_export_vm(self, opt: V2VExportOptions) -> Path:
        return _v2v_export_vm(self, opt)

    # VDDK raw disk download (experimental orchestration only) - Delegate to vmware_vddk

    def _require_vddk_client(self) -> None:
        if not VDDK_CLIENT_AVAILABLE:
            raise VMwareError(
                "VDDK raw download requested but vddk_client is not importable. "
                "Ensure hyper2kvm/vsphere/vddk_client.py exists and imports cleanly."
            )

    def vm_disks(self, vm_obj: Any) -> List[Any]:
        return _vddk_vm_disks(self, vm_obj)

    def select_disk(self, vm_obj: Any, label_or_index: Optional[str]) -> Any:
        return _vddk_select_disk(self, vm_obj, label_or_index)

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
        out_dir = self._ensure_output_dir(opt.output_dir)
        return out_dir / f"{_safe_vm_name(opt.vm_name)}-disk{disk_index}.vmdk"

    def vddk_download_disk(self, opt: V2VExportOptions) -> Path:
        return _vddk_download_disk(self, opt)

    # Unified entrypoint (policy) - refactored into smaller handlers

    @staticmethod
    def _normalize_export_mode(mode: Optional[str]) -> str:
        return (mode or "ovf_export").strip().lower()

    def _handle_mode_vddk(self, mode: str, opt: V2VExportOptions) -> Optional[Path]:
        if mode in ("vddk_download", "vddk-download", "vddkdownload"):
            return self.vddk_download_disk(opt)
        return None

    def _handle_mode_v2v(self, mode: str, opt: V2VExportOptions) -> Optional[Path]:
        if mode in ("v2v", "virt-v2v", "virt_v2v"):
            return self.v2v_export_vm(opt)
        return None

    def _handle_mode_ovftool(self, mode: str, opt: V2VExportOptions) -> Optional[Path]:
        if mode in ("ovftool_export", "ovftool", "ovftool-export"):
            self.logger.info("Export mode=OVF Tool: attempting OVF Tool export for VM=%s", opt.vm_name)
            return self.ovftool_export_vm(opt)
        return None

    def _handle_mode_download_only(self, mode: str, opt: V2VExportOptions) -> Optional[Path]:
        if mode in ("download_only", "download-only", "download"):
            return self.download_only_vm(opt)
        return None

    def _stable_chain_ovf_ova_https(self, opt: V2VExportOptions, *, log_context: str) -> Path:
        try:
            self.logger.info("%s: attempting govc export.ovf for VM=%s", log_context, opt.vm_name)
            return self.govc_export_ovf(opt)
        except Exception as e_ovf:
            self.logger.warning("%s: govc export.ovf failed; trying export.ova next: %s", log_context, e_ovf)
            try:
                return self.govc_export_ova(opt)
            except Exception as e_ova:
                self.logger.warning(
                    "%s: govc export.ova also failed; forcing HTTPS /folder fallback: %s", log_context, e_ova
                )
                return self._download_only_vm_force_https(opt)

    def _stable_chain_ova_https(self, opt: V2VExportOptions, *, log_context: str) -> Path:
        try:
            self.logger.info("%s: attempting govc export.ova for VM=%s", log_context, opt.vm_name)
            return self.govc_export_ova(opt)
        except Exception as e_ova:
            self.logger.warning("%s: govc export.ova failed; forcing HTTPS /folder fallback: %s", log_context, e_ova)
            return self._download_only_vm_force_https(opt)

    def export_vm(self, opt: V2VExportOptions) -> Path:
        """
        Export VM using specified export mode.
        """
        mode = self._normalize_export_mode(opt.export_mode)

        # Explicit/special modes first (no fallback unless explicitly coded)
        for handler in (self._handle_mode_vddk, self._handle_mode_v2v):
            out = handler(mode, opt)
            if out is not None:
                return out

        # OVF Tool requested: if it fails, fall through to stable chain
        try:
            out = self._handle_mode_ovftool(mode, opt)
            if out is not None:
                return out
        except Exception as e:
            self.logger.warning("OVF Tool export failed; falling back to stable chain: %s", e)

        out = self._handle_mode_download_only(mode, opt)
        if out is not None:
            return out

        # Stable families
        if mode in ("ovf_export", "ovf", "export_ovf", "govc_ovf", "govc_export"):
            return self._stable_chain_ovf_ova_https(opt, log_context="Export mode=OVF (stable)")

        if mode in ("ova_export", "ova", "export_ova", "govc_ova"):
            return self._stable_chain_ova_https(opt, log_context="Export mode=OVA")

        # Unknown -> stable default chain
        self.logger.warning("Unknown export_mode=%r; using stable OVF->OVA->HTTPS chain", mode)
        return self._stable_chain_ovf_ova_https(opt, log_context="Export mode=UNKNOWN (stable fallback)")
