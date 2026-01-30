# SPDX-License-Identifier: LGPL-3.0-or-later
# vmdk2kvm/vsphere/nfc_lease_client.py
# -*- coding: utf-8 -*-
"""
NFC (HttpNfcLease) data-plane client for vCenter exports.
Design goals (mirrors vddk_client.py philosophy):
  - data-plane only: this module does NOT create the lease (control-plane does that)
  - self-contained: depends only on stdlib + requests
  - robust streaming: resume (.part), retry/backoff, progress, atomic rename
  - lease keepalive: caller provides a heartbeat callback (pyVmomi/govmomi side)
"""
from __future__ import annotations
import contextlib
import hashlib
import logging
import os
import random
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit
import requests
# -----------------------------------------------------------------------------
# Errors
# -----------------------------------------------------------------------------
class NFCLeaseError(RuntimeError):
    """Generic NFC lease download error."""
class NFCLeaseCancelled(NFCLeaseError):
    """Raised when a caller cancels an in-progress download."""
# -----------------------------------------------------------------------------
# Types
# -----------------------------------------------------------------------------
ProgressFn = Callable[[int, int, float], None]
CancelFn = Callable[[], bool]
# Heartbeat is called periodically to keep lease alive.
# It receives (done_bytes, total_bytes) and may raise on fatal lease issues.
LeaseHeartbeatFn = Callable[[int, int], None]
# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _fmt_eta(seconds: float) -> str:
    try:
        s = int(max(0.0, seconds))
    except Exception:
        return "?"
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s"
def _atomic_write_replace(tmp_path: Path, final_path: Path) -> None:
    os.replace(str(tmp_path), str(final_path))
def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except Exception:
        pass
def _is_probably_transient_http(status: int) -> bool:
    # Retry on server errors + common "try later" signals
    return status in (408, 429, 500, 502, 503, 504)
def _is_probably_transient_exc(e: Exception) -> bool:
    m = str(e).lower()
    transient = (
        "timeout",
        "timed out",
        "tempor",
        "reset",
        "broken pipe",
        "connection aborted",
        "connection error",
        "remote end closed",
        "chunked encoding error",
    )
    return any(x in m for x in transient)
def _response_body_hint(r: requests.Response, *, limit: int = 400) -> str:
    """
    Best-effort small hint from response body for debugging HTTP failures.
    Never raises.
    """
    try:
        # Try text first (works for SOAP-ish errors too)
        t = (r.text or "").strip()
        if t:
            return t.replace("\n", " ")[:limit]
    except Exception:
        pass
    try:
        b = r.content or b""
        if b:
            return b[:limit].decode("utf-8", errors="replace").replace("\n", " ")
    except Exception:
        pass
    return ""
def _url_hint(url: str) -> str:
    """
    Safe-ish URL hint for logs: scheme://host/path (no query).
    """
    try:
        u = urlsplit(url)
        host = u.netloc or "?"
        path = u.path or "/"
        return f"{u.scheme}://{host}{path}"
    except Exception:
        return url
def _cookie_hint(cookies: Optional[Dict[str, str]]) -> str:
    """
    Do NOT log cookie values. Only indicate presence and lengths.
    """
    if not cookies:
        return "none"
    parts: List[str] = []
    for k, v in cookies.items():
        if v is None:
            parts.append(f"{k}=<none>")
        else:
            parts.append(f"{k}=<{len(str(v))} chars>")
    return ", ".join(parts)
def _hdr_hint(headers: Optional[Dict[str, str]]) -> str:
    """
    Redact obviously sensitive headers.
    """
    if not headers:
        return "none"
    redacted = {"authorization", "cookie", "x-vmware-api-session-id"}
    out: List[str] = []
    for k, v in headers.items():
        if k.lower() in redacted:
            out.append(f"{k}=<redacted>")
        else:
            out.append(f"{k}={v!r}")
    return ", ".join(out)
# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class NFCDeviceUrl:
    """
    A single NFC export target.
    url: the HTTP(S) URL from HttpNfcLeaseInfo.deviceUrl[i].url
    target_name: local filename stem (e.g. "disk0.vmdk" or "vmname-disk0.vmdk")
    size_bytes: if known; if 0/None, we will attempt HEAD/GET to discover length
    """
    url: str
    target_name: str
    size_bytes: Optional[int] = None
@dataclass(frozen=True)
class NFCSessionSpec:
    """
    Session/auth + TLS config for NFC downloads.
    """
    # Provide either cookies or headers (or both).
    cookies: Optional[Dict[str, str]] = None
    headers: Optional[Dict[str, str]] = None
    # TLS verification: False for self-signed lab vCenter (govc -k equivalent)
    verify_tls: bool = True
    # HTTP timeouts: (connect, read)
    timeout_s: Tuple[float, float] = (10.0, 60.0)
    # Optional: requests proxies
    proxies: Optional[Dict[str, str]] = None
class NFCHttpLeaseClient:
    """
    NFC data-plane downloader.
    Key features (aligned with vddk_client.py):
      ✅ resume: <file>.part with Range requests
      ✅ retry/backoff: transient HTTP errors + transient exceptions
      ✅ progress callback + throttled progress logs + ETA
      ✅ lease heartbeat callback (keepalive) called periodically
      ✅ atomic output: .part -> rename (optional fsync)
      ✅ cancellation hook + clean stop preserving .part
      ✅ optional SHA256 checksum
    """
    def __init__(self, logger: logging.Logger, session: NFCSessionSpec):
        self.logger = logger
        self.session_spec = session
        s = requests.Session()
        # Cookies are the most common: {"vmware_soap_session": "..."}
        if session.cookies:
            s.cookies.update(session.cookies)
        if session.headers:
            s.headers.update(session.headers)
        if session.proxies:
            s.proxies.update(session.proxies)
        # Keep-alive helps long pulls
        s.headers.setdefault("Connection", "keep-alive")
        s.headers.setdefault("User-Agent", "vmdk2kvm-nfc-lease/1.0")
        self._s = s
        # 🧠 Useful once-per-client debug breadcrumb (no secrets)
        self.logger.debug(
            "🔌 NFC: session init verify_tls=%s timeout=%s cookies={%s} headers={%s} proxies=%s",
            session.verify_tls,
            session.timeout_s,
            _cookie_hint(session.cookies),
            _hdr_hint(session.headers),
            bool(session.proxies),
        )
    def close(self) -> None:
        try:
            self._s.close()
        except Exception:
            pass
    def __enter__(self) -> "NFCHttpLeaseClient":
        return self
    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
    # ---------------------------
    # Core HTTP primitives
    # ---------------------------
    def _head_length(self, url: str) -> Optional[int]:
        hint_url = _url_hint(url)
        try:
            self.logger.debug("🧪 NFC: HEAD %s", hint_url)
            r = self._s.head(
                url,
                allow_redirects=True,
                verify=self.session_spec.verify_tls,
                timeout=self.session_spec.timeout_s,
            )
            try:
                if r.status_code >= 400:
                    self.logger.debug(
                        "⚠️ NFC: HEAD %s -> %d cl=%r hint=%r",
                        hint_url,
                        r.status_code,
                        r.headers.get("Content-Length"),
                        _response_body_hint(r),
                    )
                    return None
                cl = r.headers.get("Content-Length")
                if cl and cl.isdigit():
                    self.logger.debug("📏 NFC: HEAD %s -> Content-Length=%s", hint_url, cl)
                    return int(cl)
                self.logger.debug("📏 NFC: HEAD %s -> no Content-Length", hint_url)
                return None
            finally:
                try:
                    r.close()
                except Exception:
                    pass
        except Exception as e:
            self.logger.debug("⚠️ NFC: HEAD failed for %s: %s", hint_url, e)
            return None
    def _stream_get(
        self,
        url: str,
        *,
        range_start: Optional[int],
    ) -> requests.Response:
        headers: Dict[str, str] = {}
        if range_start is not None and range_start > 0:
            headers["Range"] = f"bytes={int(range_start)}-"
        return self._s.get(
            url,
            headers=headers,
            stream=True,
            allow_redirects=True,
            verify=self.session_spec.verify_tls,
            timeout=self.session_spec.timeout_s,
        )
    def prefetch_sizes(self, devices: Iterable[NFCDeviceUrl]) -> List[NFCDeviceUrl]:
        """
        Prefetch sizes for devices where size_bytes is None or <=0 using HEAD requests.
        Returns a new list of NFCDeviceUrl with updated sizes where possible.
        """
        out: List[NFCDeviceUrl] = []
        for dev in devices:
            if dev.size_bytes is None or dev.size_bytes <= 0:
                sz = self._head_length(dev.url)
                out.append(NFCDeviceUrl(url=dev.url, target_name=dev.target_name, size_bytes=sz))
            else:
                out.append(dev)
        return out
    # ---------------------------
    # Download logic
    # ---------------------------
    def download(
        self,
        dev: NFCDeviceUrl,
        out_dir: Path,
        *,
        resume: bool = True,
        durable: bool = False,
        chunk_bytes: int = 4 * 1024 * 1024,  # 4 MiB
        progress: Optional[ProgressFn] = None,
        progress_interval_s: float = 0.5,
        log_every_bytes: int = 256 * 1024 * 1024,
        cancel: Optional[CancelFn] = None,
        heartbeat: Optional[LeaseHeartbeatFn] = None,
        heartbeat_interval_s: float = 10.0,
        max_retries: int = 8,
        base_backoff_s: float = 0.5,
        max_backoff_s: float = 15.0,
        jitter_s: float = 0.3,
        verify_size: bool = True,
        compute_sha256: bool = False,
        update_fn: Optional[Callable[[int], None]] = None,
    ) -> Path:
        """
        Download one NFC deviceUrl to out_dir/target_name.
        Returns final path (not .part).
        """
        out_dir = Path(out_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        final_path = out_dir / dev.target_name
        tmp_path = final_path.with_suffix(final_path.suffix + ".part")
        # Determine total size
        total: Optional[int] = dev.size_bytes if (dev.size_bytes and dev.size_bytes > 0) else None
        if total is None:
            total = self._head_length(dev.url)
        if total is None:
            self.logger.warning("🤷 NFC: total size unknown for %s (will infer from stream headers if possible)", dev.target_name)
        # Resume offset
        done = 0
        mode = "wb"
        if resume and tmp_path.exists():
            try:
                st = tmp_path.stat()
                if st.st_size > 0:
                    done = int(st.st_size)
                    mode = "ab"
                self.logger.info("▶️ NFC: resuming %s at %.2f MiB", tmp_path.name, done / (1024**2))
            except Exception:
                pass
        # If we know total and tmp > total, restart
        if total is not None and done > total:
            self.logger.warning("🧨 NFC: .part larger than expected total; restarting: %s", tmp_path)
            try:
                tmp_path.unlink()
            except Exception:
                pass
            done = 0
            mode = "wb"
        self.logger.info(
            "🚚 NFC: download start: %s -> %s%s",
            dev.target_name,
            final_path,
            " [resume]" if done else "",
        )
        self.logger.debug(
            "🔍 NFC: url=%s verify_tls=%s timeout=%s chunk=%.1fMiB durable=%s",
            _url_hint(dev.url),
            self.session_spec.verify_tls,
            self.session_spec.timeout_s,
            chunk_bytes / (1024**2),
            durable,
        )
        sha256 = hashlib.sha256() if compute_sha256 else None
        start_ts = time.time()
        last_progress_ts = 0.0
        last_log_bytes = done
        # "window" for speed calculation
        win_bytes = done
        win_ts = time.time()
        # heartbeat tracking
        last_hb = 0.0
        attempt = 0
        while True:
            if cancel and cancel():
                self.logger.warning("🛑 NFC: cancelled before GET; partial kept at %s", tmp_path)
                raise NFCLeaseCancelled("Download cancelled")
            try:
                # Always re-sync done from filesystem before GET, so resume position matches reality
                if resume and tmp_path.exists():
                    try:
                        done = int(tmp_path.stat().st_size)
                        mode = "ab" if done > 0 else "wb"
                    except Exception:
                        pass
                range_start = done if done > 0 else None
                self.logger.debug(
                    "📡 NFC: GET %s range_start=%s attempt=%d/%d",
                    _url_hint(dev.url),
                    range_start,
                    attempt + 1,
                    int(max_retries),
                )
                r = self._stream_get(dev.url, range_start=range_start)
                try:
                    # Accept:
                    # - 200 OK (full)
                    # - 206 Partial Content (range)
                    if r.status_code not in (200, 206):
                        hint = _response_body_hint(r)
                        self.logger.debug(
                            "❌ NFC: GET %s -> %d cl=%r cr=%r hint=%r",
                            _url_hint(dev.url),
                            r.status_code,
                            r.headers.get("Content-Length"),
                            r.headers.get("Content-Range"),
                            hint,
                        )
                        # 4xx is almost always fatal (auth/perm/bad URL/expired ticket)
                        if 400 <= r.status_code < 500:
                            raise NFCLeaseError(f"HTTP {r.status_code} (fatal) for {dev.target_name}: {hint}")
                        # 5xx-ish: transient
                        if _is_probably_transient_http(r.status_code) and attempt < max_retries:
                            raise NFCLeaseError(f"HTTP {r.status_code} (transient) for {dev.target_name}: {hint}")
                        raise NFCLeaseError(f"HTTP {r.status_code} for {dev.target_name}: {hint}")
                    self.logger.debug(
                        "✅ NFC: GET %s -> %d cl=%r cr=%r",
                        _url_hint(dev.url),
                        r.status_code,
                        r.headers.get("Content-Length"),
                        r.headers.get("Content-Range"),
                    )
                    # Infer total from headers if possible
                    if total is None:
                        # Content-Range: bytes <start>-<end>/<total>
                        cr = (r.headers.get("Content-Range") or "").strip()
                        if cr and "/" in cr:
                            try:
                                total_part = cr.split("/")[-1].strip()
                                if total_part.isdigit():
                                    total = int(total_part)
                                    self.logger.debug("📦 NFC: inferred total from Content-Range: %d", total)
                            except Exception:
                                total = None
                        if total is None:
                            cl = r.headers.get("Content-Length")
                            # If 200, CL is full length; if 206, CL is remaining length
                            if cl and cl.isdigit():
                                if r.status_code == 200:
                                    total = int(cl)
                                    self.logger.debug("📦 NFC: inferred total from Content-Length(200): %d", total)
                                else:
                                    total = done + int(cl)
                                    self.logger.debug("📦 NFC: inferred total from Content-Length(206): %d", total)
                    # If server ignored Range (200) while we have done>0, restart safely
                    if done > 0 and r.status_code == 200:
                        self.logger.warning("🔁 NFC: server ignored Range; restarting %s from 0", dev.target_name)
                        try:
                            tmp_path.unlink()
                        except Exception:
                            pass
                        done = 0
                        mode = "wb"
                        attempt += 1
                        continue
                    # Stream body
                    with open(tmp_path, mode) as f:
                        for chunk in r.iter_content(chunk_size=max(64 * 1024, int(chunk_bytes))):
                            if not chunk:
                                continue
                            if cancel and cancel():
                                self.logger.warning("🛑 NFC: cancelled; partial kept at %s", tmp_path)
                                raise NFCLeaseCancelled("Download cancelled")
                            f.write(chunk)
                            if sha256 is not None:
                                sha256.update(chunk)
                            done += len(chunk)
                            if update_fn is not None:
                                update_fn(len(chunk))
                            now = time.time()
                            # heartbeat (keep lease alive)
                            if heartbeat is not None and (now - last_hb) >= max(1.0, float(heartbeat_interval_s)):
                                last_hb = now
                                try:
                                    heartbeat(done, total or 0)
                                    self.logger.debug("💓 NFC: heartbeat done=%d total=%d", done, int(total or 0))
                                except Exception as e:
                                    raise NFCLeaseError(f"Lease heartbeat failed for {dev.target_name}: {e}") from e
                            # progress callback
                            if progress is not None:
                                if (now - last_progress_ts) >= max(0.05, float(progress_interval_s)):
                                    last_progress_ts = now
                                    pct = (done / total * 100.0) if total else 0.0
                                    progress(done, total or 0, pct)
                            # progress logs
                            if log_every_bytes and (done - last_log_bytes) >= int(log_every_bytes):
                                last_log_bytes = done
                                now2 = time.time()
                                w_elapsed = max(0.001, now2 - win_ts)
                                w_bytes = max(0, done - win_bytes)
                                if w_elapsed >= 1.0:
                                    win_ts = now2
                                    win_bytes = done
                                mib_s = (w_bytes / (1024**2)) / w_elapsed if w_elapsed else 0.0
                                remain = max(0, (total - done)) if total else 0
                                eta_s = (remain / (mib_s * (1024**2))) if (total and mib_s > 0) else 0.0
                                pct = (done / total * 100.0) if total else 0.0
                                if total:
                                    self.logger.info(
                                        "📈 NFC: %.1f%% (%.1f/%.1f MiB) speed=%.1f MiB/s eta=%s",
                                        pct,
                                        done / (1024**2),
                                        total / (1024**2),
                                        mib_s,
                                        _fmt_eta(eta_s),
                                    )
                                else:
                                    self.logger.info(
                                        "📈 NFC: (%.1f MiB) speed=%.1f MiB/s",
                                        done / (1024**2),
                                        mib_s,
                                    )
                            # Durable mode: fsync every chunk (expensive, but requested)
                            if durable:
                                try:
                                    f.flush()
                                    os.fsync(f.fileno())
                                except Exception as e:
                                    self.logger.warning("⚠️ NFC: fsync failed (ignored): %s", e)
                    # Done streaming this response; validate if we know total
                    if total is not None and verify_size and done != total:
                        # Treat as transient: we can retry with Range from current 'done'
                        raise NFCLeaseError(f"Short download for {dev.target_name}: got={done} expected={total}")
                finally:
                    try:
                        r.close()
                    except Exception:
                        pass
                # Finalize
                _atomic_write_replace(tmp_path, final_path)
                if durable:
                    _fsync_dir(final_path.parent)
                elapsed = max(0.001, time.time() - start_ts)
                mib_s_total = (done / (1024**2)) / elapsed
                if sha256 is not None:
                    self.logger.info("🔐 NFC: sha256 %s %s", sha256.hexdigest(), final_path)
                self.logger.info(
                    "✅ NFC: download done: %s (%.2f GiB, %.1f MiB/s)",
                    final_path,
                    done / (1024**3),
                    mib_s_total,
                )
                return final_path
            except NFCLeaseCancelled:
                raise
            except Exception as e:
                attempt += 1
                # Normalize message
                if isinstance(e, NFCLeaseError):
                    msg = str(e)
                else:
                    msg = f"{type(e).__name__}: {e}"
                # Decide transient vs fatal
                transient = False
                if isinstance(e, NFCLeaseError):
                    # Only treat as transient if it looks like transient (we already label 4xx fatal above)
                    transient = True
                    # But still double-check for explicit fatal markers
                    if "fatal" in msg.lower():
                        transient = False
                else:
                    transient = _is_probably_transient_exc(e)
                if (not transient) or attempt > int(max_retries):
                    self.logger.error(
                        "💥 NFC: download FAILED after %d attempts for %s: %s (kept partial=%s)",
                        attempt,
                        dev.target_name,
                        msg,
                        tmp_path,
                    )
                    raise NFCLeaseError(f"Download failed for {dev.target_name}: {msg}") from e
                backoff = min(float(max_backoff_s), float(base_backoff_s) * (2 ** (attempt - 1)))
                backoff = backoff + random.uniform(0.0, max(0.0, float(jitter_s)))
                # Refresh 'done' from disk before sleeping/logging
                try:
                    if tmp_path.exists():
                        done = int(tmp_path.stat().st_size)
                        mode = "ab" if done > 0 else "wb"
                except Exception:
                    pass
                self.logger.warning(
                    "🔁 NFC: transient error for %s: %s (retry %d/%d in %.2fs) resume_at=%.2f MiB",
                    dev.target_name,
                    msg,
                    attempt,
                    int(max_retries),
                    backoff,
                    done / (1024**2),
                )
                time.sleep(backoff)
                # Continue loop: it will GET again with Range from current 'done'
                mode = "ab"
def download_many(
    logger: logging.Logger,
    session: NFCSessionSpec,
    devices: Iterable[NFCDeviceUrl],
    out_dir: Path,
    *,
    resume: bool = True,
    durable: bool = False,
    chunk_bytes: int = 4 * 1024 * 1024,
    progress: Optional[ProgressFn] = None,
    progress_interval_s: float = 0.5,
    log_every_bytes: int = 256 * 1024 * 1024,
    cancel: Optional[CancelFn] = None,
    heartbeat: Optional[LeaseHeartbeatFn] = None,
    heartbeat_interval_s: float = 10.0,
    max_retries: int = 8,
    base_backoff_s: float = 0.5,
    max_backoff_s: float = 15.0,
    jitter_s: float = 0.3,
    verify_size: bool = True,
    compute_sha256: bool = False,
    parallel: int = 0,  # 0: auto (min(len(devices), 4)), 1: sequential
) -> List[Path]:
    """
    Convenience helper to download multiple device URLs, optionally in parallel.
    Enhancements:
    - Prefetches sizes if missing.
    - Uses aggregate progress for heartbeat/progress callbacks if all sizes known.
    - Supports parallel downloads via threading.
    Note: Cancellation in parallel mode may not immediately stop all threads.
    """
    out: List[Path] = []
    with NFCHttpLeaseClient(logger, session) as c:
        devices_list: List[NFCDeviceUrl] = list(devices)
        if not devices_list:
            return []
        logger.info("📦 NFC: preparing %d device(s) for download", len(devices_list))
        # Prefetch sizes if any missing
        has_all_sizes = all(dev.size_bytes is not None and dev.size_bytes > 0 for dev in devices_list)
        if not has_all_sizes:
            logger.info("🔎 NFC: prefetching missing device sizes (HEAD)...")
            devices_list = c.prefetch_sizes(devices_list)
        # Recompute has_all_sizes and grand_total
        grand_total = 0
        has_all_sizes = True
        for dev in devices_list:
            if dev.size_bytes is None or dev.size_bytes <= 0:
                has_all_sizes = False
            else:
                grand_total += dev.size_bytes
        use_aggregate = has_all_sizes and (heartbeat is not None or progress is not None)
        if has_all_sizes:
            logger.info("🧮 NFC: total export size: %.2f GiB", grand_total / (1024**3))
        else:
            logger.warning("⚠️ NFC: some device sizes unknown; progress/heartbeat will be per-device (multi-device totals may be fuzzy)")
        update_fn = None
        if use_aggregate:
            lock = threading.Lock()
            shared_done = 0
            last_hb = time.time()
            last_progress_ts = time.time()
            def update_fn(delta: int) -> None:
                nonlocal shared_done, last_hb, last_progress_ts
                with lock:
                    shared_done += delta
                    now = time.time()
                    if heartbeat is not None and (now - last_hb) >= max(1.0, float(heartbeat_interval_s)):
                        last_hb = now
                        heartbeat(shared_done, grand_total)
                    if progress is not None and (now - last_progress_ts) >= max(0.05, float(progress_interval_s)):
                        last_progress_ts = now
                        pct = (shared_done / grand_total * 100.0) if grand_total > 0 else 0.0
                        progress(shared_done, grand_total, pct)
        # Determine parallel workers
        if parallel == 0:
            parallel = min(len(devices_list), 4)
        if parallel > 1:
            logger.info("🧵 NFC: parallel download enabled (workers=%d)", parallel)
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = [
                    executor.submit(
                        c.download,
                        dev,
                        out_dir,
                        resume=resume,
                        durable=durable,
                        chunk_bytes=chunk_bytes,
                        progress=None if use_aggregate else progress,
                        progress_interval_s=progress_interval_s,
                        log_every_bytes=log_every_bytes,
                        cancel=cancel,
                        heartbeat=None if use_aggregate else heartbeat,
                        heartbeat_interval_s=heartbeat_interval_s,
                        max_retries=max_retries,
                        base_backoff_s=base_backoff_s,
                        max_backoff_s=max_backoff_s,
                        jitter_s=jitter_s,
                        verify_size=verify_size,
                        compute_sha256=compute_sha256,
                        update_fn=update_fn,
                    )
                    for dev in devices_list
                ]
                for future in as_completed(futures):
                    out.append(future.result())
        else:
            logger.info("🐢 NFC: sequential download mode")
            for dev in devices_list:
                out.append(
                    c.download(
                        dev,
                        out_dir,
                        resume=resume,
                        durable=durable,
                        chunk_bytes=chunk_bytes,
                        progress=None if use_aggregate else progress,
                        progress_interval_s=progress_interval_s,
                        log_every_bytes=log_every_bytes,
                        cancel=cancel,
                        heartbeat=None if use_aggregate else heartbeat,
                        heartbeat_interval_s=heartbeat_interval_s,
                        max_retries=max_retries,
                        base_backoff_s=base_backoff_s,
                        max_backoff_s=max_backoff_s,
                        jitter_s=jitter_s,
                        verify_size=verify_size,
                        compute_sha256=compute_sha256,
                        update_fn=update_fn,
                    )
                )
        logger.info("🎉 NFC: all downloads complete (%d file(s))", len(out))
        return out