# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# tests/test_h2kvmctl_common.py
"""Unit tests for h2kvmctl integration."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import subprocess
import os
from pathlib import Path

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from hyper2kvm.vmware.transports.h2kvmctl_common import (
    H2KVMCtlRunner,
    create_h2kvmctl_runner,
    export_vm_h2kvmctl,
    H2KVMCtlConfig,
)
from hyper2kvm.core.exceptions import VMwareError


class TestH2KVMCtlConfig(unittest.TestCase):
    """Test H2KVMCtlConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = H2KVMCtlConfig()

        self.assertEqual(config.daemon_url, "http://localhost:8080")
        self.assertEqual(config.h2kvmctl_path, "h2kvmctl")
        self.assertEqual(config.timeout, 3600)


class TestH2KVMCtlRunner(unittest.TestCase):
    """Test H2KVMCtlRunner class."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = H2KVMCtlRunner(
            daemon_url="http://test:9999",
            h2kvmctl_path="/usr/bin/h2kvmctl",
            timeout=300,
        )

    def test_init(self):
        """Test runner initialization."""
        self.assertEqual(self.runner.daemon_url, "http://test:9999")
        self.assertEqual(self.runner.h2kvmctl_path, "/usr/bin/h2kvmctl")
        self.assertEqual(self.runner.timeout, 300)

    @patch('subprocess.run')
    def test_check_daemon_status_success(self, mock_run):
        """Test successful daemon status check."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Daemon running",
            stderr=""
        )

        result = self.runner.check_daemon_status()

        self.assertEqual(result["status"], "running")
        self.assertIn("Daemon running", result["output"])
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_check_daemon_status_failure(self, mock_run):
        """Test daemon status check failure."""
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Connection refused"
        )

        with self.assertRaises(VMwareError):
            self.runner.check_daemon_status()

    @patch('subprocess.run')
    def test_submit_export_job_success(self, mock_run):
        """Test successful job submission."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Job submitted: abc123-def456",
            stderr=""
        )

        job_id = self.runner.submit_export_job(
            vm_path="/dc/vm/test",
            output_path="/tmp/export",
            parallel_downloads=4,
            remove_cdrom=True,
        )

        self.assertEqual(job_id, "abc123-def456")

        # Verify command was called with correct args
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[0], "/usr/bin/h2kvmctl")
        self.assertIn("--daemon", call_args)
        self.assertIn("http://test:9999", call_args)
        self.assertIn("submit", call_args)
        self.assertIn("/dc/vm/test", call_args)

    @patch('subprocess.run')
    def test_submit_export_job_parse_error(self, mock_run):
        """Test job submission with parse error."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Unknown output format",
            stderr=""
        )

        with self.assertRaises(VMwareError) as ctx:
            self.runner.submit_export_job(
                vm_path="/dc/vm/test",
                output_path="/tmp/export",
            )

        self.assertIn("parse job id", str(ctx.exception).lower())

    @patch('subprocess.run')
    def test_query_job(self, mock_run):
        """Test job query."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Job: abc123 | Status: running",
            stderr=""
        )

        result = self.runner.query_job("abc123")

        self.assertEqual(result["job_id"], "abc123")
        self.assertIn("running", result["output"])

    @patch('subprocess.run')
    def test_command_timeout(self, mock_run):
        """Test command timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["h2kvmctl"], timeout=300
        )

        with self.assertRaises(VMwareError) as ctx:
            self.runner.check_daemon_status()

        self.assertIn("timed out", str(ctx.exception).lower())

    @patch('subprocess.run')
    def test_command_not_found(self, mock_run):
        """Test h2kvmctl not found."""
        mock_run.side_effect = FileNotFoundError()

        with self.assertRaises(VMwareError) as ctx:
            self.runner.check_daemon_status()

        self.assertIn("not found", str(ctx.exception).lower())

    @patch('subprocess.run')
    def test_command_failed(self, mock_run):
        """Test command execution failure."""
        exc = subprocess.CalledProcessError(
            returncode=1,
            cmd=["h2kvmctl"]
        )
        exc.stderr = "Connection refused"
        mock_run.side_effect = exc

        with self.assertRaises(VMwareError) as ctx:
            self.runner.check_daemon_status()

        self.assertIn("failed", str(ctx.exception).lower())

    @patch('subprocess.run')
    @patch('time.sleep', return_value=None)  # Speed up tests
    def test_wait_for_job_completion_success(self, mock_sleep, mock_run):
        """Test waiting for job completion (success)."""
        # First call: running, second call: completed
        mock_run.side_effect = [
            Mock(returncode=0, stdout="Job: abc123 | Status: running", stderr=""),
            Mock(returncode=0, stdout="Job: abc123 | Status: completed", stderr=""),
        ]

        result = self.runner.wait_for_job_completion(
            job_id="abc123",
            poll_interval=1,
        )

        self.assertIn("completed", result["output"])
        self.assertEqual(mock_run.call_count, 2)

    @patch('subprocess.run')
    @patch('time.sleep', return_value=None)
    def test_wait_for_job_completion_failed(self, mock_sleep, mock_run):
        """Test waiting for job completion (failed)."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Job: abc123 | Status: failed | Error: VM not found",
            stderr=""
        )

        with self.assertRaises(VMwareError) as ctx:
            self.runner.wait_for_job_completion(
                job_id="abc123",
                poll_interval=1,
            )

        self.assertIn("failed", str(ctx.exception).lower())

    @patch('subprocess.run')
    @patch('time.sleep', return_value=None)
    @patch('time.time')
    def test_wait_for_job_timeout(self, mock_time, mock_sleep, mock_run):
        """Test job wait timeout."""
        # Simulate time passing
        mock_time.side_effect = [0, 100, 200, 301]  # Exceeds 300s timeout

        mock_run.return_value = Mock(
            returncode=0,
            stdout="Job: abc123 | Status: running",
            stderr=""
        )

        with self.assertRaises(VMwareError) as ctx:
            self.runner.wait_for_job_completion(
                job_id="abc123",
                poll_interval=1,
                timeout=300,
            )

        self.assertIn("timed out", str(ctx.exception).lower())

    @patch('subprocess.run')
    @patch('time.sleep', return_value=None)
    def test_wait_with_progress_callback(self, mock_sleep, mock_run):
        """Test progress callback during wait."""
        mock_run.side_effect = [
            Mock(returncode=0, stdout="Job: abc123 | Status: running", stderr=""),
            Mock(returncode=0, stdout="Job: abc123 | Status: completed", stderr=""),
        ]

        progress_calls = []

        def progress_callback(status):
            progress_calls.append(status)

        result = self.runner.wait_for_job_completion(
            job_id="abc123",
            poll_interval=1,
            progress_callback=progress_callback,
        )

        # Should have called progress callback at least once (for running state)
        # The completed state is returned before callback is called
        self.assertGreaterEqual(len(progress_calls), 1)
        self.assertIn("running", progress_calls[0]["output"].lower())

    @patch.object(H2KVMCtlRunner, 'submit_export_job')
    @patch.object(H2KVMCtlRunner, 'wait_for_job_completion')
    @patch('pathlib.Path.mkdir')
    def test_export_vm_wait(self, mock_mkdir, mock_wait, mock_submit):
        """Test full export with wait."""
        mock_submit.return_value = "job123"
        mock_wait.return_value = {"job_id": "job123", "status": "completed"}

        result = self.runner.export_vm(
            vm_path="/dc/vm/test",
            output_path="/tmp/export",
            wait=True,
        )

        mock_mkdir.assert_called_once()
        mock_submit.assert_called_once()
        mock_wait.assert_called_once()
        self.assertEqual(result["job_id"], "job123")

    @patch.object(H2KVMCtlRunner, 'submit_export_job')
    @patch('pathlib.Path.mkdir')
    def test_export_vm_no_wait(self, mock_mkdir, mock_submit):
        """Test export without waiting."""
        mock_submit.return_value = "job123"

        result = self.runner.export_vm(
            vm_path="/dc/vm/test",
            output_path="/tmp/export",
            wait=False,
        )

        mock_mkdir.assert_called_once()
        mock_submit.assert_called_once()
        self.assertEqual(result["job_id"], "job123")
        self.assertEqual(result["status"], "submitted")


class TestFactoryFunctions(unittest.TestCase):
    """Test factory functions."""

    @patch.dict(os.environ, {
        "H2KVMD_URL": "http://custom:7777",
        "H2KVMCTL_PATH": "/custom/h2kvmctl",
    })
    def test_create_runner_from_env(self):
        """Test creating runner from environment variables."""
        runner = create_h2kvmctl_runner()

        self.assertEqual(runner.daemon_url, "http://custom:7777")
        self.assertEqual(runner.h2kvmctl_path, "/custom/h2kvmctl")

    def test_create_runner_with_args(self):
        """Test creating runner with explicit args."""
        runner = create_h2kvmctl_runner(
            daemon_url="http://explicit:8888",
            h2kvmctl_path="/explicit/bin",
        )

        self.assertEqual(runner.daemon_url, "http://explicit:8888")
        self.assertEqual(runner.h2kvmctl_path, "/explicit/bin")

    @patch.object(H2KVMCtlRunner, 'export_vm')
    def test_export_vm_convenience_function(self, mock_export):
        """Test convenience export function."""
        mock_export.return_value = {"job_id": "test123"}

        result = export_vm_h2kvmctl(
            vm_path="/dc/vm/test",
            output_path="/tmp/test",
            parallel_downloads=8,
            remove_cdrom=True,
        )

        mock_export.assert_called_once()
        call_kwargs = mock_export.call_args[1]
        self.assertEqual(call_kwargs["vm_path"], "/dc/vm/test")
        self.assertEqual(call_kwargs["parallel_downloads"], 8)
        self.assertTrue(call_kwargs["remove_cdrom"])


class TestIntegrationScenarios(unittest.TestCase):
    """Test realistic integration scenarios."""

    @patch('subprocess.run')
    def test_full_export_workflow(self, mock_run):
        """Test complete export workflow."""
        # Simulate complete workflow: submit -> poll -> complete
        mock_run.side_effect = [
            # submit_export_job
            Mock(returncode=0, stdout="Job submitted: workflow123", stderr=""),
            # wait: first poll (running)
            Mock(returncode=0, stdout="Status: running | Progress: 50%", stderr=""),
            # wait: second poll (completed)
            Mock(returncode=0, stdout="Status: completed | Files: 4", stderr=""),
        ]

        runner = H2KVMCtlRunner()

        # Submit job
        job_id = runner.submit_export_job("/dc/vm/test", "/tmp/out")
        self.assertEqual(job_id, "workflow123")

        # Wait for completion
        with patch('time.sleep'):
            result = runner.wait_for_job_completion(job_id, poll_interval=1)

        self.assertIn("completed", result["output"])

    @patch('subprocess.run')
    def test_batch_export_scenario(self, mock_run):
        """Test batch export scenario."""
        # Simulate submitting multiple jobs
        mock_run.side_effect = [
            Mock(returncode=0, stdout="Job submitted: batch1", stderr=""),
            Mock(returncode=0, stdout="Job submitted: batch2", stderr=""),
            Mock(returncode=0, stdout="Job submitted: batch3", stderr=""),
        ]

        runner = H2KVMCtlRunner()

        vms = ["/dc/vm/vm1", "/dc/vm/vm2", "/dc/vm/vm3"]
        job_ids = []

        for vm in vms:
            job_id = runner.submit_export_job(vm, f"/tmp/{vm.split('/')[-1]}")
            job_ids.append(job_id)

        self.assertEqual(len(job_ids), 3)
        self.assertEqual(job_ids, ["batch1", "batch2", "batch3"])


if __name__ == "__main__":
    unittest.main()
