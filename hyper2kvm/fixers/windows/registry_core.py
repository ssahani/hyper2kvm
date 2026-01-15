# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/windows/registry_core.py
# -*- coding: utf-8 -*-
"""
Windows registry editing for virtualization fixes.

This module provides high-level APIs for editing Windows registry hives
to install drivers, configure services, and set up first-boot scripts.

The implementation is split across multiple modules:
- registry_io: Hive download and validation
- registry_mount: Windows filesystem mounting
- registry_encoding: Low-level hivex operations
- registry_firstboot: First-boot service provisioning
- registry_system: SYSTEM hive driver/control editing
- registry_software: SOFTWARE hive DevicePath/RunOnce editing

This file re-exports the public APIs for backward compatibility.
"""
from __future__ import annotations

# Re-export public APIs from sub-modules
from .registry.firstboot import provision_firstboot_payload_and_service
from .registry.software import add_software_runonce, append_devicepath_software_hive
from .registry.system import edit_system_hive, set_system_dword

# Re-export commonly used internal functions for compatibility
# (These are used by other fixers in the codebase)
from .registry.encoding import (
    _close_best_effort,
    _commit_best_effort,
    _decode_reg_sz,
    _delete_child_if_exists,
    _detect_current_controlset,
    _driver_start_default,
    _driver_type_norm,
    _encode_windows_cmd_script,
    _ensure_child,
    _hivex_read_dword,
    _hivex_read_sz,
    _hivex_read_value_dict,
    _mkdir_p_guest,
    _mk_reg_value,
    _node_id,
    _node_ok,
    _open_hive_local,
    _pci_id_normalize,
    _reg_sz,
    _set_dword,
    _set_expand_sz,
    _set_sz,
    _upload_bytes,
    NodeLike,
)
from .registry.io import _download_hive_local, _is_probably_regf, _log_mountpoints_best_effort
from .registry.mount import _ensure_windows_root, _guest_path_join, _looks_like_windows_root

# Re-export for compatibility with existing code that imports these
__all__ = [
    # Public APIs
    "provision_firstboot_payload_and_service",
    "edit_system_hive",
    "set_system_dword",
    "append_devicepath_software_hive",
    "add_software_runonce",
    # Internal functions (for other fixers)
    "_safe_logger",
    "_is_probably_regf",
    "_download_hive_local",
    "_log_mountpoints_best_effort",
    "_guest_path_join",
    "_looks_like_windows_root",
    "_ensure_windows_root",
    "_mkdir_p_guest",
    "_upload_bytes",
    "_encode_windows_cmd_script",
    "_node_id",
    "_node_ok",
    "_reg_sz",
    "_decode_reg_sz",
    "_mk_reg_value",
    "_set_sz",
    "_set_expand_sz",
    "_set_dword",
    "_ensure_child",
    "_delete_child_if_exists",
    "_hivex_read_value_dict",
    "_hivex_read_sz",
    "_hivex_read_dword",
    "_detect_current_controlset",
    "_open_hive_local",
    "_close_best_effort",
    "_commit_best_effort",
    "_driver_start_default",
    "_driver_type_norm",
    "_pci_id_normalize",
    "NodeLike",
]


# Import shared logging utilities
import logging
from ...core.logging_utils import safe_logger as _safe_logger_base


def _safe_logger(self) -> logging.Logger:
    """Get logger from self or create default logger."""
    return _safe_logger_base(self, "hyper2kvm.windows_registry")
