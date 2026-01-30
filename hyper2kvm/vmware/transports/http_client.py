# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/vmware/transports/http_client.py
"""
HTTP/HTTPS datastore file download client for vSphere.
Handles downloading files from vSphere datastores via /folder HTTP interface.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

# Optional: silence urllib3 TLS warnings when verify=False
try:
    import urllib3
except Exception:  # pragma: no cover
    urllib3 = None  # type: ignore

# Optional: HTTP download (requests)
try:
    import requests  # type: ignore
    import requests.adapters  # type: ignore

    REQUESTS_AVAILABLE = True
except Exception:  # pragma: no cover
    requests = None  # type: ignore
    REQUESTS_AVAILABLE = False

# Exception Hierarchy
class HTTPDownloadError(Exception):
    """Base exception for HTTP download errors."""


class VMwareError(HTTPDownloadError):
    """Fallback VMwareError when real one not available."""


# Try to import the real VMwareError
try:
    from ...core.exceptions import VMwareError as CoreVMwareError  # type: ignore

    VMwareError = CoreVMwareError  # type: ignore[misc, assignment]
except Exception:
    pass  # Keep our fallback

# Import utility functions
from ...core.utils import U

# Import progress reporters
from .http_progress import (
    ProgressReporter,
    create_progress_reporter,
)

# Optional: Rich UI (for panels only, progress reporters handle their own Rich imports)
try:  # pragma: no cover
    from rich.console import Console
    from rich.panel import Panel

    RICH_AVAILABLE = True
except Exception:  # pragma: no cover
    Console = None  # type: ignore
    Panel = None  # type: ignore
    RICH_AVAILABLE = False


# UI helpers
def _print_panel(
    title: str,
    body: str = "",
    title_style: str = "bold blue",
    panel_style: str = "cyan",
) -> None:
    con = Console() if Console is not None else None
    if con and Panel:
        con.print(Panel(body or "", title=title, title_align="left", expand=True, style=panel_style))
        return

    inner_w = max(57, len(title) + 6, *(len(x) + 4 for x in body.splitlines() if x.strip()))
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
    print(f" ✓ {msg}")


def _warn_line(msg: str) -> None:
    print(f"WARNING: {msg}")


def _fmt_elapsed(start_time: float) -> tuple[int, int]:
    elapsed = max(0.0, time.time() - start_time)
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    return minutes, seconds


# HTTP Download Options
@dataclass(frozen=True)
class HTTPDownloadOptions:
    show_panels: bool = True
    show_progress: bool = True
    progress_refresh_hz: float = 10.0
    log_every_bytes: int = 10 * 1024 * 1024  # FIXED: 10MB instead of 128MB for better progress visibility
    retries: int = 0
    retry_backoff_s: float = 2.0
    simple_progress: bool = True
    resume_download: bool = True
    max_workers: int = 1  # For parallel downloads, 1 = sequential
    chunk_size: int = 1024 * 1024  # 1MB chunks
    atomic: bool = True  # write to temp + replace; resume uses temp pre-copy


ProgressCallback = Callable[[int, int], None]  # (bytes_delta, total_bytes)


# HTTP Download Client
class HTTPDownloadClient:
    """
    HTTP/HTTPS client for downloading files from vSphere datastores.

    Notes:
      - Correct resume support (Range + 206 enforcement).
      - Optional atomic writes via temp file + os.replace.
      - Uses requests Session for pooling; avoid mutating shared session state concurrently.
    """

    def __init__(
        self,
        logger: logging.Logger,
        host: str,
        port: int = 443,
        insecure: bool = False,
        timeout: float | None = None,
        http_client: Any | None = None,  # For testing/mocking
    ) -> None:
        if not host:
            raise ValueError("Host cannot be empty")
        if not 1 <= port <= 65535:
            raise ValueError(f"Invalid port: {port}")
        if timeout is not None and timeout <= 0:
            raise ValueError(f"Invalid timeout: {timeout}")

        if not REQUESTS_AVAILABLE:
            raise VMwareError("requests not installed. Install: pip install requests")

        self.logger = logger
        self.host = host.strip()
        self.port = port
        self.insecure = insecure
        self.timeout = timeout

        self._session_cookie_raw: str | None = None
        self._cookie_header_value: str | None = None

        self._session_pool: Any | None = None
        self._http_client = http_client or requests

        self._disable_tls_warnings()

    def _disable_tls_warnings(self) -> None:
        if not self.insecure or urllib3 is None:
            return
        try:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _validate_connection_params(self) -> None:
        if not self.host:
            raise ValueError("Host not set")
        if not self._cookie_header_value:
            raise VMwareError("Session cookie not set. Call set_session_cookie() first.")

    def set_session_cookie(self, cookie: str) -> None:
        """
        Set the session cookie from pyvmomi connection.

        We normalize to a safe Cookie header value:
          - Accepts raw "name=value; Path=/; HttpOnly" formats
          - Accepts just "name=value"
          - Keeps only the first cookie-pair for the Cookie header
        """
        if not cookie or not cookie.strip():
            raise ValueError("Cookie cannot be empty")
        raw = cookie.strip()
        self._session_cookie_raw = raw

        # Keep only the first "name=value" pair before any ';'
        first = raw.split(";", 1)[0].strip()
        if "=" not in first:
            raise ValueError(f"Cookie does not look like name=value: {cookie!r}")
        self._cookie_header_value = first

    def get_session_cookie(self) -> str:
        if not self._cookie_header_value:
            raise VMwareError("Session cookie not set. Call set_session_cookie() first.")
        return self._cookie_header_value

    @property
    def session(self) -> Any:
        if self._session_pool is None:
            self._session_pool = self._create_session()
        return self._session_pool

    def _create_session(self) -> Any:
        """
        Create HTTP session for datastore downloads.

        SECURITY WARNING: When insecure=True, TLS certificate verification is disabled.
        """
        session = self._http_client.Session()
        session.verify = not self.insecure  # SECURITY: Controlled by insecure flag

        if self.insecure:
            self.logger.warning(
                "HTTP client TLS verification is DISABLED (insecure=True). "
                "Downloads are vulnerable to Man-in-the-Middle attacks. "
                "Only use this in trusted environments with self-signed certificates."
            )

        adapter = self._http_client.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=100,
            max_retries=3,
            pool_block=False,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _build_download_url(self, datastore: str, ds_path: str, dc_name: str) -> str:
        ds_path_encoded = quote(ds_path, safe="")
        dc_name_encoded = quote(dc_name, safe="")
        datastore_encoded = quote(datastore, safe="")
        return (
            f"https://{self.host}:{self.port}/folder/{ds_path_encoded}"
            f"?dcPath={dc_name_encoded}&dsName={datastore_encoded}"
        )

    def get_file_size(self, datastore: str, ds_path: str, dc_name: str) -> int | None:
        """
        Get the size of a datastore file using HEAD.
        Returns None if unknown / cannot retrieve.
        """
        self._validate_connection_params()
        url = self._build_download_url(datastore, ds_path, dc_name)
        headers = {"Cookie": self.get_session_cookie()}

        try:
            response = self.session.head(url, headers=headers, timeout=self.timeout or 30.0)
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length is None:
                return None
            return int(content_length)
        except Exception as e:
            self.logger.debug("Failed to get size for %s: %s", ds_path, e)
            return None

    def _download_to_path(
        self,
        *,
        url: str,
        out_path: Path,
        headers: dict[str, str],
        chunk_size: int,
        reporter: ProgressReporter,
        expect_partial: bool,
    ) -> tuple[int, int]:
        """
        Stream response body into out_path (already opened/created).
        Returns: (downloaded_bytes, http_status)
        """
        downloaded = 0
        with self.session.get(
            url,
            headers=headers,
            stream=True,
            timeout=self.timeout,
        ) as response:
            response.raise_for_status()
            status = int(getattr(response, "status_code", 0) or 0)

            if expect_partial and status != 206:
                # Range was sent but server didn't honor it.
                # We'll signal this to caller so it can restart safely.
                return 0, status

            # write stream
            with open(out_path, "ab") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    reporter.update(len(chunk))

                # durability
                try:
                    f.flush()
                    os.fsync(f.fileno())
                except Exception:
                    pass

        return downloaded, status

    def download_file(
        self,
        *,
        datastore: str,
        ds_path: str,
        local_path: Path,
        dc_name: str,
        on_bytes: ProgressCallback | None = None,
        options: HTTPDownloadOptions | None = None,
    ) -> None:
        """
        Download a single datastore file via HTTP/HTTPS with correct resume capability.
        """
        self._validate_connection_params()
        opt = options or HTTPDownloadOptions()

        url = self._build_download_url(datastore, ds_path, dc_name)
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        start_time = time.time()

        # Decide resume
        headers: dict[str, str] = {"Cookie": self.get_session_cookie()}
        start_byte = 0
        remote_size = self.get_file_size(datastore, ds_path, dc_name)

        if opt.resume_download and local_path.exists():
            existing_size = local_path.stat().st_size
            if remote_size is not None and existing_size == remote_size:
                self.logger.info("File already exists and is complete: %s", local_path)
                return
            if remote_size is not None and 0 < existing_size < remote_size:
                start_byte = existing_size
                headers["Range"] = f"bytes={existing_size}-"
                self.logger.info("Resuming download from byte %d", existing_size)

        # For progress totals, show "remaining" if resuming, else full size.
        total_remaining: int | None = None
        if remote_size is not None:
            total_remaining = max(0, remote_size - start_byte)

        title = f"Downloading file: {Path(ds_path).name or ds_path}"
        body = (
            f"Datastore: [{datastore}]\n"
            f"Path: {ds_path}\n"
            f"DC: {dc_name}\n"
            f"Output: {local_path}\n"
            f"Mode: {'HTTPS (insecure)' if self.insecure else 'HTTPS'}"
            f"{' [RESUME]' if start_byte > 0 else ''}"
        )
        if opt.show_panels:
            _print_panel(title, body, title_style="bold magenta", panel_style="cyan")

        self.logger.info(
            "Downloading via HTTPS: [%s] %s (dc=%s) -> %s%s",
            datastore,
            ds_path,
            dc_name,
            local_path,
            " [resuming]" if start_byte > 0 else "",
        )

        file_name = Path(ds_path).name or "download"
        reporter = create_progress_reporter(opt, file_name, self.logger)
        reporter.start(f"Downloading {file_name}", total_remaining)

        max_attempts = opt.retries + 1
        last_exception: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            temp_path: Path | None = None
            try:
                # Choose output target for this attempt
                # - atomic=False: write directly to local (with correct resume append)
                # - atomic=True: write to temp; for resume, pre-copy existing local into temp first
                if opt.atomic:
                    with tempfile.NamedTemporaryFile(
                        delete=False,
                        dir=local_path.parent,
                        suffix=".part",
                    ) as tf:
                        temp_path = Path(tf.name)
                    # if resuming, pre-seed temp with existing bytes
                    if start_byte > 0 and local_path.exists():
                        # copy only start_byte bytes (file size should match start_byte)
                        with open(local_path, "rb") as src, open(temp_path, "wb") as dst:
                            # stream copy
                            remaining = start_byte
                            buf = 1024 * 1024
                            while remaining > 0:
                                chunk = src.read(min(buf, remaining))
                                if not chunk:
                                    break
                                dst.write(chunk)
                                remaining -= len(chunk)
                            try:
                                dst.flush()
                                os.fsync(dst.fileno())
                            except Exception:
                                pass
                    else:
                        # ensure empty
                        open(temp_path, "wb").close()
                    out_target = temp_path
                else:
                    out_target = local_path

                # If not atomic and not resuming, ensure fresh file
                if not opt.atomic and start_byte == 0:
                    try:
                        if local_path.exists():
                            local_path.unlink()
                    except Exception:
                        pass

                downloaded_this_attempt, status = self._download_to_path(
                    url=url,
                    out_path=out_target,
                    headers=headers,
                    chunk_size=opt.chunk_size,
                    reporter=reporter,
                    expect_partial=("Range" in headers),
                )

                # If Range was requested but server returned 200, restart safely from scratch
                if "Range" in headers and status != 206:
                    self.logger.warning(
                        "Server did not honor Range request (status=%s). Restarting full download.",
                        status,
                    )
                    # cleanup temp if used
                    if opt.atomic and temp_path and temp_path.exists():
                        try:
                            temp_path.unlink()
                        except Exception:
                            pass
                    # reset resume state and retry immediately (counts as this attempt failure)
                    headers.pop("Range", None)
                    start_byte = 0
                    total_remaining = remote_size  # full size again
                    reporter.finish()
                    reporter = create_progress_reporter(opt, file_name, self.logger)
                    reporter.start(f"Downloading {file_name}", total_remaining)
                    raise VMwareError("Range not honored; restarted download")

                # Success: if atomic, replace
                if opt.atomic and temp_path is not None:
                    os.replace(temp_path, local_path)

                # Final size reporting
                final_size = start_byte + downloaded_this_attempt if start_byte > 0 else downloaded_this_attempt
                if remote_size is not None:
                    # If we know remote_size, trust it for "final"
                    final_size = max(final_size, remote_size)

                if on_bytes and remote_size is not None:
                    try:
                        on_bytes(downloaded_this_attempt, total_remaining or remote_size)
                    except Exception:
                        pass

                reporter.finish()

                m, s = _fmt_elapsed(start_time)
                if opt.show_panels:
                    extra = (
                        f"Output: {local_path}\n"
                        f"Size: {U.human_bytes(final_size)}\n"
                        f"Time: {m}m {s}s"
                    )
                    _print_panel(
                        "✓ Download completed successfully!",
                        extra,
                        title_style="bold green",
                        panel_style="green",
                    )
                else:
                    _ok_line(f"Downloaded {local_path} in {m}m {s}s")

                return

            except Exception as e:
                last_exception = e
                # cleanup temp on failure
                if opt.atomic and temp_path and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass

                if attempt < max_attempts:
                    sleep_time = opt.retry_backoff_s * (2 ** (attempt - 1))
                    self.logger.warning(
                        "Download failed (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt,
                        max_attempts,
                        e,
                        sleep_time,
                    )
                    _warn_line(f"Download attempt {attempt} failed: {e}")
                    time.sleep(sleep_time)
                    continue

                reporter.finish()
                raise VMwareError(f"Download failed after {max_attempts} attempts: {last_exception}") from last_exception

    def test_connection(self) -> bool:
        """
        Test if we can connect to the vSphere host via HTTPS.
        """
        if not REQUESTS_AVAILABLE:
            return False
        try:
            test_url = f"https://{self.host}:{self.port}/folder"
            response = self.session.head(test_url, timeout=5.0)
            return int(getattr(response, "status_code", 0) or 0) in (200, 401, 403)
        except Exception:
            return False


# HTTP Download Manager
class HTTPDownloadManager:
    """
    Manager for batch HTTP downloads with parallel download support.
    """

    def __init__(self, download_client: HTTPDownloadClient, logger: logging.Logger) -> None:
        self.download_client = download_client
        self.logger = logger

    def download_files(
        self,
        *,
        datastore: str,
        dc_name: str,
        files: list[tuple[str, Path]],
        fail_on_error: bool = False,
        max_retries: int = 1,
        retry_delay: float = 2.0,
        options: HTTPDownloadOptions | None = None,
    ) -> list[tuple[bool, str, str]]:
        opt = options or HTTPDownloadOptions()

        if opt.max_workers > 1:
            return self._download_files_parallel(
                datastore=datastore,
                dc_name=dc_name,
                files=files,
                fail_on_error=fail_on_error,
                max_retries=max_retries,
                retry_delay=retry_delay,
                options=opt,
            )
        return self._download_files_sequential(
            datastore=datastore,
            dc_name=dc_name,
            files=files,
            fail_on_error=fail_on_error,
            max_retries=max_retries,
            retry_delay=retry_delay,
            options=opt,
        )

    def _download_files_sequential(
        self,
        *,
        datastore: str,
        dc_name: str,
        files: list[tuple[str, Path]],
        fail_on_error: bool,
        max_retries: int,
        retry_delay: float,
        options: HTTPDownloadOptions,
    ) -> list[tuple[bool, str, str]]:
        start = time.time()
        is_batch = len(files) > 1

        if options.show_panels and is_batch:
            _print_panel(
                "Starting HTTPS batch download",
                f"Datastore: [{datastore}]\nDC: {dc_name}\nFiles: {len(files)}\nMode: Sequential",
                title_style="bold magenta",
                panel_style="cyan",
            )

        # For batch, disable per-file panels (keeps output sane)
        single_opt = options
        if is_batch:
            single_opt = HTTPDownloadOptions(
                show_panels=False,
                show_progress=options.show_progress,
                progress_refresh_hz=options.progress_refresh_hz,
                log_every_bytes=options.log_every_bytes,
                retries=options.retries,
                retry_backoff_s=options.retry_backoff_s,
                simple_progress=options.simple_progress,
                resume_download=options.resume_download,
                max_workers=1,
                chunk_size=options.chunk_size,
                atomic=options.atomic,
            )

        results: list[tuple[bool, str, str]] = []
        ok = 0
        fail = 0

        for i, (ds_path, local_path) in enumerate(files):
            if is_batch and not options.show_progress and options.show_panels:
                _print_panel(
                    f"Downloading file {i+1}/{len(files)}: {Path(ds_path).name}",
                    title_style="bold magenta",
                    panel_style="cyan",
                )

            success = False
            msg = ""

            for attempt in range(max_retries + 1):
                try:
                    self.download_client.download_file(
                        datastore=datastore,
                        ds_path=ds_path,
                        local_path=local_path,
                        dc_name=dc_name,
                        on_bytes=None,
                        options=single_opt,
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
                        time.sleep(retry_delay)
                    else:
                        self.logger.error(
                            "Download failed permanently: %s -> %s: %s",
                            ds_path,
                            local_path,
                            msg,
                        )
                        fail += 1

            results.append((success, ds_path, msg))

            if not success and fail_on_error:
                raise VMwareError(f"Download failed: {ds_path}: {msg}")

        self._show_batch_summary(start, ok, fail, datastore, results, options)
        return results

    def _download_files_parallel(
        self,
        *,
        datastore: str,
        dc_name: str,
        files: list[tuple[str, Path]],
        fail_on_error: bool,
        max_retries: int,
        retry_delay: float,
        options: HTTPDownloadOptions,
    ) -> list[tuple[bool, str, str]]:
        start = time.time()

        if options.show_panels:
            _print_panel(
                "Starting parallel HTTPS batch download",
                f"Datastore: [{datastore}]\nDC: {dc_name}\nFiles: {len(files)}\nWorkers: {options.max_workers}",
                title_style="bold magenta",
                panel_style="cyan",
            )

        # Disable per-file UI in parallel mode to avoid interleaved garbage
        single_opt = HTTPDownloadOptions(
            show_panels=False,
            show_progress=False,
            progress_refresh_hz=options.progress_refresh_hz,
            log_every_bytes=options.log_every_bytes,
            retries=options.retries,
            retry_backoff_s=options.retry_backoff_s,
            simple_progress=options.simple_progress,
            resume_download=options.resume_download,
            max_workers=1,
            chunk_size=options.chunk_size,
            atomic=options.atomic,
        )

        results: list[tuple[bool, str, str]] = []
        ok = 0
        fail = 0

        with ThreadPoolExecutor(max_workers=options.max_workers) as executor:
            future_to_file: dict[Any, tuple[str, Path]] = {}
            for ds_path, local_path in files:
                future = executor.submit(
                    self._download_file_with_retry,
                    datastore=datastore,
                    ds_path=ds_path,
                    local_path=local_path,
                    dc_name=dc_name,
                    options=single_opt,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                )
                future_to_file[future] = (ds_path, local_path)

            for future in as_completed(future_to_file):
                ds_path, _local_path = future_to_file[future]
                try:
                    future.result()
                    results.append((True, ds_path, "Success"))
                    ok += 1
                except Exception as e:
                    results.append((False, ds_path, str(e)))
                    fail += 1
                    if fail_on_error:
                        for f in future_to_file:
                            f.cancel()
                        raise VMwareError(f"Download failed: {ds_path}: {e}") from e

        self._show_batch_summary(start, ok, fail, datastore, results, options)
        return results

    def _download_file_with_retry(
        self,
        datastore: str,
        ds_path: str,
        local_path: Path,
        dc_name: str,
        options: HTTPDownloadOptions,
        max_retries: int,
        retry_delay: float,
    ) -> None:
        last_exception: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                self.download_client.download_file(
                    datastore=datastore,
                    ds_path=ds_path,
                    local_path=local_path,
                    dc_name=dc_name,
                    on_bytes=None,
                    options=options,
                )
                return
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    self.logger.debug(
                        "Download failed (attempt %d/%d): %s -> %s: %s. Retrying...",
                        attempt + 1,
                        max_retries + 1,
                        ds_path,
                        local_path,
                        str(e),
                    )
                    time.sleep(retry_delay)
                else:
                    raise VMwareError(f"Download failed after {max_retries + 1} attempts: {last_exception}") from last_exception

    def _show_batch_summary(
        self,
        start_time: float,
        ok: int,
        fail: int,
        datastore: str,
        results: list[tuple[bool, str, str]],
        options: HTTPDownloadOptions,
    ) -> None:
        m, s = _fmt_elapsed(start_time)
        summary_body = f"Success: {ok}\nFailed: {fail}\nDatastore: [{datastore}]\nTime: {m}m {s}s"

        if fail > 0:
            summary_body += "\nFailed files:"
            for succ, ds_p, msg in results:
                if not succ:
                    summary_body += f"\n- {ds_p}: {msg}"

        summary_title_style = "bold green" if fail == 0 else "bold red"
        summary_panel_style = "green" if fail == 0 else "red"

        if options.show_panels:
            _print_panel(
                "Batch download summary",
                summary_body,
                title_style=summary_title_style,
                panel_style=summary_panel_style,
            )
        else:
            print("Batch download summary:")
            print(summary_body)
