# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# vmdk2kvm/vsphere/http_download_client.py
"""
HTTP/HTTPS datastore file download client for vSphere.
Handles downloading files from vSphere datastores via /folder HTTP interface.

"""

from __future__ import annotations

import logging
import os
import socket
import ssl
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

# Optional: silence urllib3 TLS warnings when verify=False
try:
    import urllib3
except Exception:  # pragma: no cover
    urllib3 = None  # type: ignore

# Optional: HTTP download (requests)
try:
    import requests  # type: ignore

    REQUESTS_AVAILABLE = True
except Exception:  # pragma: no cover
    requests = None  # type: ignore
    REQUESTS_AVAILABLE = False

# Your repo says: from ..core.exceptions import VMwareError
try:
    from ..core.exceptions import VMwareError  # type: ignore
except Exception:  # pragma: no cover
    class VMwareError(RuntimeError):
        pass


try:  # pragma: no cover
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
        DownloadColumn,
    )

    RICH_AVAILABLE = True
except Exception:  # pragma: no cover
    Console = None  # type: ignore
    Panel = None  # type: ignore
    Progress = None  # type: ignore
    SpinnerColumn = None  # type: ignore
    BarColumn = None  # type: ignore
    TextColumn = None  # type: ignore
    TimeElapsedColumn = None  # type: ignore
    TimeRemainingColumn = None  # type: ignore
    TransferSpeedColumn = None  # type: ignore
    DownloadColumn = None  # type: ignore
    RICH_AVAILABLE = False


# --------------------------------------------------------------------------------------
# UI helpers (Rich Panel when possible, otherwise plain box-drawing)
# --------------------------------------------------------------------------------------
def _is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _console() -> Optional[Any]:
    if not (RICH_AVAILABLE and Console and _is_tty()):
        return None
    try:
        return Console(stderr=False)
    except Exception:
        return None


def _print_panel(title: str, body: str = "") -> None:
    """
    Render a panel like:

    ╭─────────────────────────────────────────────────────────╮
    │                  Exporting VM: ...                      │
    ╰─────────────────────────────────────────────────────────╯
    """
    con = _console()
    if con and Panel:
        con.print(Panel(body or "", title=title, expand=True))
        return

    inner_w = max(57, len(title) + 6, *(len(x) + 4 for x in body.splitlines() if x.strip()))  # type: ignore[arg-type]
    line = "─" * inner_w
    print(f"╭{line}╮")

    t = title
    if len(t) > inner_w - 2:
        t = t[: inner_w - 3] + "…"
    print(f"│ {t:<{inner_w-2}} │")

    if body.strip():
        for bl in body.splitlines():
            s = bl.rstrip("\n")
            if len(s) > inner_w - 2:
                s = s[: inner_w - 3] + "…"
            print(f"│ {s:<{inner_w-2}} │")

    print(f"╰{line}╯")


def _ok_line(msg: str) -> None:
    print(f"  ✓ {msg}")


def _warn_line(msg: str) -> None:
    print(f"WARNING: {msg}")


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n/1024:.1f} KiB"
    if n < 1024**3:
        return f"{n/(1024**2):.1f} MiB"
    return f"{n/(1024**3):.2f} GiB"


def _fmt_elapsed(start_time: float) -> Tuple[int, int]:
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    return minutes, seconds


# --------------------------------------------------------------------------------------
# Small options struct (keeps signature sane + easy future expansion)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class HTTPDownloadOptions:
    show_panels: bool = True
    show_progress: bool = True
    progress_refresh_hz: float = 10.0  # Rich refresh; lower -> less CPU
    log_every_bytes: int = 128 * 1024 * 1024  # plain-log progress interval when not using Rich
    retries: int = 0
    retry_backoff_s: float = 2.0


ProgressCallback = Callable[[int, int], None]  # (bytes_delta, total_bytes)


class HTTPDownloadClient:
    """
    HTTP/HTTPS client for downloading files from vSphere datastores.

    Features:
      - Downloads files via vSphere /folder HTTP interface
      - Uses session cookies from pyvmomi connection
      - Supports progress callbacks
      - Handles TLS verification (with insecure option)
      - Rich UI progress (optional)
      - No threads; single-flow streaming
    """

    def __init__(
        self,
        logger: logging.Logger,
        host: str,
        port: int = 443,
        insecure: bool = False,
        timeout: Optional[float] = None,
    ) -> None:
        self.logger = logger
        self.host = (host or "").strip()
        self.port = int(port)
        self.insecure = bool(insecure)
        self.timeout = timeout

        # Session cache
        self._session_cookie: Optional[str] = None

    def set_session_cookie(self, cookie: str) -> None:
        """Set the session cookie from pyvmomi connection."""
        self._session_cookie = cookie

    def get_session_cookie(self) -> str:
        """Get the session cookie (raises if not set)."""
        if not self._session_cookie:
            raise VMwareError("Session cookie not set. Call set_session_cookie() first.")
        return self._session_cookie

    def _ssl_context(self) -> ssl.SSLContext:
        """Create SSL context based on insecure setting."""
        if self.insecure:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        return ssl.create_default_context()

    def _disable_tls_warnings(self) -> None:
        """Disable urllib3 TLS warnings when verify=False."""
        if not self.insecure or urllib3 is None:
            return
        try:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _build_download_url(
        self,
        datastore: str,
        ds_path: str,
        dc_name: str,
    ) -> str:
        """
        Build the download URL for a datastore file.

        Format: https://{host}/folder/{ds_path}?dcPath={dc_name}&dsName={datastore}
        """
        # URL encode path components
        ds_path_encoded = quote(ds_path, safe="")
        dc_name_encoded = quote(dc_name, safe="")
        datastore_encoded = quote(datastore, safe="")

        return (
            f"https://{self.host}:{self.port}/folder/{ds_path_encoded}"
            f"?dcPath={dc_name_encoded}&dsName={datastore_encoded}"
        )

    def download_file(
        self,
        *,
        datastore: str,
        ds_path: str,
        local_path: Path,
        dc_name: str,
        on_bytes: Optional[ProgressCallback] = None,
        chunk_size: int = 1024 * 1024,
        options: Optional[HTTPDownloadOptions] = None,
    ) -> None:
        """
        Download a single datastore file via HTTP/HTTPS.

        Args:
            datastore: Datastore name
            ds_path: Path within datastore
            local_path: Local file path to save to
            dc_name: Datacenter name
            on_bytes: Optional callback for progress tracking (bytes_delta, total_bytes)
            chunk_size: Chunk size for streaming download
            options: UI/retry behavior

        Raises:
            VMwareError: If download fails
        """
        if not REQUESTS_AVAILABLE:
            raise VMwareError("requests not installed. Install: pip install requests")

        opt = options or HTTPDownloadOptions()

        url = self._build_download_url(datastore, ds_path, dc_name)
        headers = {"Cookie": self.get_session_cookie()}
        verify = not self.insecure

        self._disable_tls_warnings()
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        title = f"Downloading file: {Path(ds_path).name or ds_path}"
        body = (
            f"Datastore: [{datastore}]\n"
            f"Path: {ds_path}\n"
            f"DC: {dc_name}\n"
            f"Output: {local_path}\n"
            f"Mode: {'HTTPS (insecure)' if self.insecure else 'HTTPS'}"
        )
        if opt.show_panels:
            _print_panel(title, body)

        self.logger.info(
            "Downloading via HTTPS: [%s] %s (dc=%s) -> %s",
            datastore,
            ds_path,
            dc_name,
            local_path,
        )

        def _attempt_once() -> None:
            start = time.time()

            # Download to temporary file first (atomic publish)
            temp_path = local_path.with_suffix(local_path.suffix + ".part")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

            downloaded = 0
            last_log_mark = 0
            total = 0

            use_rich = bool(
                opt.show_progress
                and RICH_AVAILABLE
                and Progress
                and _is_tty()
            )
            con = _console()

            progress: Optional[Any] = None
            task_id: Optional[int] = None

            try:
                with requests.get(  # type: ignore[union-attr]
                    url,
                    headers=headers,
                    stream=True,
                    verify=verify,
                    timeout=self.timeout,
                ) as response:
                    response.raise_for_status()
                    total = int(response.headers.get("content-length", "0") or "0")

                    if use_rich and con and DownloadColumn and TransferSpeedColumn and TimeRemainingColumn:
                        progress = Progress(
                            SpinnerColumn(),
                            TextColumn("[progress.description]{task.description}"),
                            BarColumn(),
                            DownloadColumn(),
                            TransferSpeedColumn(),
                            TimeRemainingColumn(),
                            TimeElapsedColumn(),
                            console=con,
                            transient=True,
                            refresh_per_second=max(1, int(opt.progress_refresh_hz)),
                        )
                        progress.start()
                        desc = f"Downloading {Path(ds_path).name}"
                        task_id = progress.add_task(desc, total=total if total > 0 else None)

                    with open(temp_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if not chunk:
                                continue
                            f.write(chunk)
                            downloaded += len(chunk)

                            # callback (bytes_delta, total)
                            if on_bytes is not None:
                                try:
                                    on_bytes(len(chunk), total)
                                except Exception:
                                    pass

                            if progress and task_id is not None:
                                # Rich: increment progress, even if total unknown (indeterminate bar)
                                if total > 0:
                                    progress.update(task_id, advance=len(chunk))
                                else:
                                    progress.update(task_id, completed=downloaded)

                            # Plain logging throttle (no Rich)
                            if not progress and opt.log_every_bytes > 0:
                                if downloaded - last_log_mark >= opt.log_every_bytes:
                                    last_log_mark = downloaded
                                    if total > 0:
                                        pct = (downloaded / total) * 100.0
                                        self.logger.info(
                                            "Download progress: %s / %s (%.1f%%)",
                                            _fmt_bytes(downloaded),
                                            _fmt_bytes(total),
                                            pct,
                                        )
                                    else:
                                        self.logger.info("Download progress: %s", _fmt_bytes(downloaded))

                os.replace(temp_path, local_path)

                m, s = _fmt_elapsed(start)
                if opt.show_panels:
                    extra = f"Output: {local_path}\nSize: {_fmt_bytes(downloaded)}"
                    _print_panel("✓ Download completed successfully!", extra)
                else:
                    _ok_line(f"Downloaded {local_path} in {m}m {s}s")

            finally:
                if progress:
                    try:
                        progress.stop()
                    except Exception:
                        pass
                # Clean temp if still there (failed mid-stream)
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass

        # retry wrapper
        attempts = 0
        while True:
            attempts += 1
            try:
                _attempt_once()
                return
            except Exception as e:
                if attempts > (opt.retries + 1):
                    raise
                sleep_s = opt.retry_backoff_s * (2 ** (attempts - 2)) if attempts >= 2 else opt.retry_backoff_s
                self.logger.warning("Download failed (attempt %d): %s", attempts, e)
                _warn_line(f"download attempt {attempts} failed: {e}")
                _info = f"Retrying in {sleep_s:.1f}s..."
                print(_info)
                time.sleep(sleep_s)

    def test_connection(self) -> bool:
        """
        Test if we can connect to the vSphere host via HTTPS.

        Returns:
            True if connection succeeds, False otherwise
        """
        if not REQUESTS_AVAILABLE:
            return False

        try:
            test_url = f"https://{self.host}:{self.port}/folder"
            verify = not self.insecure

            self._disable_tls_warnings()

            response = requests.head(  # type: ignore[union-attr]
                test_url,
                verify=verify,
                timeout=5.0,
            )
            return response.status_code in (200, 401, 403)  # Various valid responses
        except Exception:
            return False


class HTTPDownloadManager:
    """
    Manager for batch HTTP downloads with filtering and error handling.

    Adds:
      - Rich panels per file (optional)
      - Batch summary panel
      - Per-file retries (still supported)
    """

    def __init__(
        self,
        download_client: HTTPDownloadClient,
        logger: logging.Logger,
    ) -> None:
        self.download_client = download_client
        self.logger = logger

    def download_files(
        self,
        *,
        datastore: str,
        dc_name: str,
        files: List[Tuple[str, Path]],  # (ds_path, local_path)
        fail_on_error: bool = False,
        max_retries: int = 1,
        retry_delay: float = 2.0,
        options: Optional[HTTPDownloadOptions] = None,
    ) -> List[Tuple[bool, str, str]]:
        """
        Download multiple files with error handling.

        Args:
            datastore: Datastore name
            dc_name: Datacenter name
            files: List of (ds_path, local_path) tuples
            fail_on_error: Whether to fail on first error
            max_retries: Maximum number of retries per file (manager-level)
            retry_delay: Delay between retries in seconds
            options: UI/progress options (passed to client)

        Returns:
            List of (success, ds_path, message) tuples
        """
        opt = options or HTTPDownloadOptions()

        if opt.show_panels:
            _print_panel(
                "Starting HTTPS batch download",
                f"Datastore: [{datastore}]\nDC: {dc_name}\nFiles: {len(files)}",
            )

        results: List[Tuple[bool, str, str]] = []
        ok = 0
        fail = 0

        for ds_path, local_path in files:
            success = False
            msg = ""

            for attempt in range(max_retries + 1):
                try:
                    # client has its own retry wrapper too; keep manager retries minimal & explicit
                    self.download_client.download_file(
                        datastore=datastore,
                        ds_path=ds_path,
                        local_path=local_path,
                        dc_name=dc_name,
                        options=opt,
                    )
                    success = True
                    msg = "Success"
                    ok += 1
                    break
                except Exception as e:
                    msg = str(e)
                    if attempt < max_retries:
                        self.logger.warning(
                            "Download failed (attempt %d/%d): %s -> %s: %s. Retrying...",
                            attempt + 1,
                            max_retries + 1,
                            ds_path,
                            local_path,
                            msg,
                        )
                        _warn_line(
                            f"Download failed (attempt {attempt+1}/{max_retries+1}): {ds_path} -> {local_path}: {msg}"
                        )
                        time.sleep(retry_delay)
                    else:
                        self.logger.error("Download failed permanently: %s -> %s: %s", ds_path, local_path, msg)
                        _warn_line(f"Download failed permanently: {ds_path} -> {local_path}: {msg}")
                        fail += 1

            results.append((success, ds_path, msg))

            if not success and fail_on_error:
                raise VMwareError(f"Download failed: {ds_path}: {msg}")

        if opt.show_panels:
            _print_panel(
                "Batch download summary",
                f"Success: {ok}\nFailed: {fail}\nDatastore: [{datastore}]",
            )

        return results
