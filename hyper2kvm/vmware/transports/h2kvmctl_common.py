# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# hyper2kvm/vmware/transports/h2kvmctl_common.py
from __future__ import annotations

"""
h2kvmctl / hyper2kvm-providers common helpers for hyper2kvm.

Design goals:
  - Integrate with hyper2kvmd daemon for high-performance VM exports
  - Fallback to pyvmomi if h2kvmctl/daemon not available
  - Provide both CLI (h2kvmctl) and API (direct REST) interfaces
  - Match the govc_common.py pattern for consistency
"""

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.exceptions import VMwareError

logger = logging.getLogger(__name__)


@dataclass
class H2KVMCtlConfig:
    """Configuration for h2kvmctl CLI tool."""
    daemon_url: str = "http://localhost:8080"
    h2kvmctl_path: str = "h2kvmctl"
    timeout: int = 3600


class H2KVMCtlRunner:
    """
    Wrapper for h2kvmctl CLI tool (hyper2kvm-providers).

    Similar to GovcRunner but for the Go-based provider daemon.
    """

    def __init__(
        self,
        daemon_url: str = "http://localhost:8080",
        h2kvmctl_path: str = "h2kvmctl",
        timeout: int = 3600,
    ):
        self.daemon_url = daemon_url
        self.h2kvmctl_path = h2kvmctl_path
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)

    def _run_command(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run h2kvmctl command."""
        cmd = [self.h2kvmctl_path, "--daemon", self.daemon_url] + args

        self.logger.debug(f"Running h2kvmctl: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=check,
            )
            return result
        except subprocess.TimeoutExpired:
            raise VMwareError(msg=f"h2kvmctl command timed out after {self.timeout}s")
        except subprocess.CalledProcessError as e:
            raise VMwareError(msg=f"h2kvmctl failed: {e.stderr}")
        except FileNotFoundError:
            raise VMwareError(
                msg=f"h2kvmctl not found at {self.h2kvmctl_path}. "
                "Install hyper2kvm-providers or set H2KVMCTL_PATH environment variable."
            )

    def check_daemon_status(self) -> Dict[str, Any]:
        """Check if hyper2kvmd daemon is running and get status."""
        result = self._run_command(["status"])

        # h2kvmctl status outputs a table, but we want JSON for parsing
        # For now, just check if it succeeded
        if result.returncode == 0:
            self.logger.info("hyper2kvmd daemon is running")
            return {"status": "running", "output": result.stdout}
        else:
            raise VMwareError(msg="hyper2kvmd daemon not responding")

    def submit_export_job(
        self,
        vm_path: str,
        output_path: str,
        parallel_downloads: int = 4,
        remove_cdrom: bool = True,
    ) -> str:
        """
        Submit VM export job to hyper2kvmd daemon.

        Returns:
            job_id: The job ID for tracking progress
        """
        args = [
            "submit",
            "-vm", vm_path,
            "-output", output_path,
        ]

        if parallel_downloads:
            args.extend(["-parallel", str(parallel_downloads)])

        if remove_cdrom:
            args.append("-remove-cdrom")

        result = self._run_command(args)

        # Parse job ID from output
        # Output format: "Job submitted: <job-id>"
        for line in result.stdout.split('\n'):
            if "submitted:" in line.lower():
                job_id = line.split()[-1].strip()
                self.logger.info(f"Export job submitted: {job_id}")
                return job_id

        raise VMwareError(msg="Failed to parse job ID from h2kvmctl output")

    def query_job(self, job_id: str) -> Dict[str, Any]:
        """Query job status."""
        result = self._run_command(["query", "-id", job_id])

        # TODO: Parse the table output or add -json flag to h2kvmctl
        # For now, return raw output
        return {"job_id": job_id, "output": result.stdout}

    def wait_for_job_completion(
        self,
        job_id: str,
        poll_interval: int = 5,
        timeout: Optional[int] = None,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Wait for export job to complete.

        Args:
            job_id: Job ID to wait for
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait (None = unlimited)
            progress_callback: Optional callback(progress_dict) for progress updates

        Returns:
            Final job status dict
        """
        start_time = time.time()

        while True:
            if timeout and (time.time() - start_time) > timeout:
                raise VMwareError(msg=f"Job {job_id} timed out after {timeout}s")

            status = self.query_job(job_id)

            # Check if completed (parse from output)
            if "completed" in status["output"].lower():
                self.logger.info(f"Job {job_id} completed successfully")
                return status
            elif "failed" in status["output"].lower():
                raise VMwareError(msg=f"Job {job_id} failed")
            elif "cancelled" in status["output"].lower():
                raise VMwareError(msg=f"Job {job_id} was cancelled")

            # Call progress callback if provided
            if progress_callback:
                try:
                    progress_callback(status)
                except Exception as e:
                    self.logger.warning(f"Progress callback error: {e}")

            time.sleep(poll_interval)

    def export_vm(
        self,
        vm_path: str,
        output_path: str,
        parallel_downloads: int = 4,
        remove_cdrom: bool = True,
        wait: bool = True,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Export VM using hyper2kvmd daemon (high-level wrapper).

        Args:
            vm_path: vSphere VM path (e.g., "/datacenter/vm/my-vm")
            output_path: Local output directory
            parallel_downloads: Number of parallel file downloads
            remove_cdrom: Remove CD/DVD devices before export
            wait: Wait for job completion
            progress_callback: Optional progress callback

        Returns:
            Job result dict
        """
        # Ensure output directory exists
        Path(output_path).mkdir(parents=True, exist_ok=True)

        # Submit job
        job_id = self.submit_export_job(
            vm_path=vm_path,
            output_path=output_path,
            parallel_downloads=parallel_downloads,
            remove_cdrom=remove_cdrom,
        )

        if not wait:
            return {"job_id": job_id, "status": "submitted"}

        # Wait for completion
        return self.wait_for_job_completion(
            job_id=job_id,
            progress_callback=progress_callback,
        )


# Factory function for easy instantiation

def create_h2kvmctl_runner(
    daemon_url: Optional[str] = None,
    h2kvmctl_path: Optional[str] = None,
) -> H2KVMCtlRunner:
    """
    Create H2KVMCtlRunner with environment variable defaults.

    Environment variables:
        H2KVMD_URL: Daemon URL (default: http://localhost:8080)
        H2KVMCTL_PATH: Path to h2kvmctl binary (default: h2kvmctl)
    """
    daemon_url = daemon_url or os.getenv("H2KVMD_URL", "http://localhost:8080")
    h2kvmctl_path = h2kvmctl_path or os.getenv("H2KVMCTL_PATH", "h2kvmctl")

    return H2KVMCtlRunner(
        daemon_url=daemon_url,
        h2kvmctl_path=h2kvmctl_path,
    )


# Convenience function for export

def export_vm_h2kvmctl(
    vm_path: str,
    output_path: str,
    parallel_downloads: int = 4,
    remove_cdrom: bool = True,
    daemon_url: Optional[str] = None,
    progress_callback: Optional[callable] = None,
) -> Dict[str, Any]:
    """
    Export VM using h2kvmctl (convenience function).

    This is the equivalent of export_vm_govc() but using hyper2kvm-providers.

    Example:
        >>> from hyper2kvm.vmware.transports.h2kvmctl_common import export_vm_h2kvmctl
        >>> result = export_vm_h2kvmctl(
        ...     vm_path="/datacenter/vm/my-vm",
        ...     output_path="/tmp/export",
        ...     parallel_downloads=4,
        ... )
        >>> print(result["job_id"])
    """
    runner = create_h2kvmctl_runner(daemon_url=daemon_url)

    return runner.export_vm(
        vm_path=vm_path,
        output_path=output_path,
        parallel_downloads=parallel_downloads,
        remove_cdrom=remove_cdrom,
        progress_callback=progress_callback,
    )
