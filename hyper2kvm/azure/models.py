# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# hyper2kvm/azure/models.py

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AzureDiskRef:
    id: str
    name: str
    resource_group: str
    location: str
    size_gb: int
    sku: str = ""
    os_type: Optional[str] = None
    is_os_disk: bool = False
    lun: Optional[int] = None


@dataclass(frozen=True)
class AzureVMRef:
    id: str
    name: str
    resource_group: str
    location: str
    power_state: str = "unknown"
    os_type: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    disks: List[AzureDiskRef] = field(default_factory=list)


@dataclass(frozen=True)
class DiskArtifact:
    role: str           # "os"|"data"
    lun: Optional[int]
    src: str            # source disk id
    local_path: Path
    format: str         # "vhd"
    guest_hint: Optional[str] = None


@dataclass
class AzureExportItem:
    vm_name: str
    vm_rg: str
    disk_id: str
    disk_name: str
    is_os: bool
    lun: Optional[int] = None

    snapshot_id: Optional[str] = None
    temp_disk_id: Optional[str] = None

    sas_hash10: Optional[str] = None
    local_path: Optional[str] = None

    expected_bytes: Optional[int] = None
    bytes_downloaded: Optional[int] = None

    ok: bool = False
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class AzureVMReport:
    name: str
    resource_group: str
    location: str
    power_state: str
    os_type: Optional[str]
    tags: Dict[str, str] = field(default_factory=dict)
    disks: List[Dict[str, Any]] = field(default_factory=list)
    exports: List[AzureExportItem] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_jsonable(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AzureFetchReport:
    subscription: Optional[str] = None
    tenant: Optional[str] = None
    run_tag: str = ""
    selection: Dict[str, Any] = field(default_factory=dict)

    vms: List[AzureVMReport] = field(default_factory=list)

    created_resource_ids: List[str] = field(default_factory=list)
    deleted_resource_ids: List[str] = field(default_factory=list)

    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def sas_hash10(self, sas_url: str) -> str:
        """Return first 10 chars of SHA256 hash for audit preview (not cryptographically secure)."""
        return hashlib.sha256(sas_url.encode("utf-8")).hexdigest()[:10]

    def to_jsonable(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AzureSelectConfig:
    resource_group: Optional[str] = None
    vm_names: List[str] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)
    power_state: Optional[str] = None
    list_only: bool = False
    allow_all_rgs: bool = False


@dataclass
class AzureShutdownConfig:
    mode: str = "none"   # none|stop|deallocate
    wait: bool = True
    force: bool = False  # allow shutdown even when using snapshots


@dataclass
class AzureExportConfig:
    use_snapshots: bool = True
    stage_disk_from_snapshot: bool = False
    keep_snapshots: bool = False
    keep_temp_disks: bool = False
    sas_duration_s: int = 3600
    tag_resources: bool = True
    run_tag: Optional[str] = None
    consistency: str = "crash_consistent"  # crash_consistent|best_effort_quiesce
    disks: str = "all"          # os|data|all


@dataclass
class AzureDownloadConfig:
    parallel: int = 2
    resume: bool = True
    chunk_mb: int = 8
    verify_size: bool = True
    strict_verify: bool = False
    temp_suffix: str = ".part"
    connect_timeout_s: int = 15
    read_timeout_s: int = 60 * 5

    # NEW: retries for large downloads (real-world needed)
    retries: int = 5
    backoff_base_s: float = 1.0
    backoff_cap_s: float = 30.0


@dataclass
class AzureConfig:
    subscription: Optional[str] = None
    tenant: Optional[str] = None
    select: AzureSelectConfig = field(default_factory=AzureSelectConfig)
    shutdown: AzureShutdownConfig = field(default_factory=AzureShutdownConfig)
    export: AzureExportConfig = field(default_factory=AzureExportConfig)
    download: AzureDownloadConfig = field(default_factory=AzureDownloadConfig)
    output_dir: Path = Path("./out")
