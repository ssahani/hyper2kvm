# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# hyper2kvm/fixers/windows/registry/encoding.py
"""
Low-level registry encoding and hivex operations.

Provides:
- Guest file I/O helpers
- Hivex node normalization
- Registry value encoding/decoding (REG_SZ, REG_DWORD, etc.)
- Hivex lifecycle management (open/close/commit)
- Driver value normalization
"""
from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    import guestfs  # type: ignore
else:
    try:
        import guestfs  # type: ignore
    except ImportError:
        guestfs = None  # type: ignore
import hivex  # type: ignore

from .io import _is_probably_regf

# Guest file helpers


def _mkdir_p_guest(logger: logging.Logger, g: guestfs.GuestFS, path: str) -> None:
    """Create directory in guest filesystem (mkdir -p)."""
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


# Hivex node normalization (IMPORTANT)

NodeLike = Union[int, None]


def _node_id(n: NodeLike) -> int:
    """Convert node to int, treating None as 0."""
    if n is None:
        return 0
    try:
        return int(n)
    except Exception:
        return 0


def _node_ok(n: NodeLike) -> bool:
    """Check if node is valid (non-zero)."""
    return _node_id(n) != 0


# Registry encoding helpers (CRITICAL)


def _reg_sz(s: str) -> bytes:
    """Encode string as REG_SZ (UTF-16LE with null terminator)."""
    return (s + "\0").encode("utf-16le", errors="ignore")


def _decode_reg_sz(raw: bytes) -> str:
    """Decode REG_SZ with fallback to UTF-8."""
    try:
        return raw.decode("utf-16le", errors="ignore").rstrip("\x00")
    except Exception:
        try:
            return raw.decode("utf-8", errors="ignore").rstrip("\x00")
        except Exception:
            return ""


def _mk_reg_value(name: str, t: int, value: bytes) -> Dict[str, Any]:
    """Create registry value dictionary."""
    return {"key": name, "t": int(t), "value": value}


def _set_sz(h: hivex.Hivex, node: NodeLike, key: str, s: str) -> None:
    """Set REG_SZ value."""
    nid = _node_id(node)
    if nid == 0:
        raise RuntimeError(f"invalid registry node for setting {key}=REG_SZ")
    h.node_set_value(nid, _mk_reg_value(key, 1, _reg_sz(s)))


def _set_expand_sz(h: hivex.Hivex, node: NodeLike, key: str, s: str) -> None:
    """Set REG_EXPAND_SZ value."""
    nid = _node_id(node)
    if nid == 0:
        raise RuntimeError(f"invalid registry node for setting {key}=REG_EXPAND_SZ")
    h.node_set_value(nid, _mk_reg_value(key, 2, _reg_sz(s)))


def _set_dword(h: hivex.Hivex, node: NodeLike, key: str, v: int) -> None:
    """Set REG_DWORD value."""
    nid = _node_id(node)
    if nid == 0:
        raise RuntimeError(f"invalid registry node for setting {key}=REG_DWORD")
    h.node_set_value(nid, _mk_reg_value(key, 4, int(v).to_bytes(4, "little", signed=False)))


def _ensure_child(h: hivex.Hivex, parent: NodeLike, name: str) -> int:
    """Get or create child node."""
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
    """Delete child node if it exists (tries multiple hivex API signatures)."""
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
    """Read raw value dictionary from registry node."""
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
    """Read REG_SZ value."""
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
    """Read REG_DWORD value."""
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
    """Detect active ControlSet (ControlSet001 vs ControlSet002)."""
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


# Hivex open helpers (LOCAL FILES ONLY)


def _open_hive_local(path: Path, *, write: bool) -> hivex.Hivex:
    """Open local hive file with validation."""
    if not path.exists():
        raise FileNotFoundError(f"hive local file missing: {path}")
    st = path.stat()
    if st.st_size < 4096:
        raise RuntimeError(f"hive local file too small ({st.st_size} bytes): {path}")
    if not _is_probably_regf(path):
        raise RuntimeError(f"hive local file does not look like regf hive: {path}")
    return hivex.Hivex(str(path), write=(1 if write else 0))


def _close_best_effort(h: Optional[hivex.Hivex]) -> None:
    """Close hive (handles version differences)."""
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
    """Commit hive changes (handles version differences)."""
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


# Internal: normalize Driver values (fixes NoneType -> int errors)


def _driver_start_default(drv: Any, *, fallback: int = 3) -> int:
    """Extract start_type from driver object with fallback."""
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
    """Normalize driver type string."""
    t = getattr(drv, "type", None)
    if t is None:
        return ""
    if hasattr(t, "value"):
        v = getattr(t, "value", None)
        if v is not None:
            return str(v)
    return str(t)


def _pci_id_normalize(pci_id: str) -> str:
    """Normalize PCI ID string."""
    return str(pci_id).strip()
