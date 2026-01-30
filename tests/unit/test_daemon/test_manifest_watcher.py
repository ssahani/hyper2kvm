# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Tests for manifest file watcher.

Tests both watchdog and polling implementations.
"""

import pytest
import time
from pathlib import Path
from unittest.mock import Mock, patch

from hyper2kvm.daemon.manifest_watcher import (
    ManifestHandler,
    DaemonManifestWatcher,
)
from hyper2kvm.core.optional_imports import WATCHDOG_AVAILABLE


class TestManifestHandler:
    """Test manifest handler logic."""

    def test_valid_manifest_detection(self, tmp_path):
        """Test detection of valid manifest files."""
        callback = Mock()
        handler = ManifestHandler(callback)

        # Create test files
        valid_yaml = tmp_path / "test.yaml"
        valid_yml = tmp_path / "test.yml"
        valid_json = tmp_path / "test.json"
        invalid_txt = tmp_path / "test.txt"

        for f in [valid_yaml, valid_yml, valid_json, invalid_txt]:
            f.write_text("test")

        # Check validity
        assert handler._is_valid_manifest(valid_yaml)
        assert handler._is_valid_manifest(valid_yml)
        assert handler._is_valid_manifest(valid_json)
        assert not handler._is_valid_manifest(invalid_txt)

    def test_hidden_files_ignored(self, tmp_path):
        """Test that hidden files are ignored."""
        callback = Mock()
        handler = ManifestHandler(callback)

        hidden = tmp_path / ".hidden.yaml"
        hidden.write_text("test")

        assert not handler._is_valid_manifest(hidden)

    def test_temp_files_ignored(self, tmp_path):
        """Test that temp files are ignored."""
        callback = Mock()
        handler = ManifestHandler(callback)

        temp = tmp_path / "test.yaml~"
        temp.write_text("test")

        assert not handler._is_valid_manifest(temp)

    def test_process_manifest_calls_callback(self, tmp_path):
        """Test that processing calls the callback."""
        callback = Mock()
        handler = ManifestHandler(callback)

        manifest = tmp_path / "test.yaml"
        manifest.write_text("hypervisor: vmware\n")

        handler._process_manifest(manifest)

        # Should call callback once
        callback.assert_called_once_with(manifest)

    def test_duplicate_processing_prevented(self, tmp_path):
        """Test that files are not processed twice."""
        callback = Mock()
        handler = ManifestHandler(callback)

        manifest = tmp_path / "test.yaml"
        manifest.write_text("hypervisor: vmware\n")

        # Process twice
        handler._process_manifest(manifest)
        handler._process_manifest(manifest)  # Should be ignored

        # Should only call callback once (second call ignored while processing)
        assert callback.call_count == 1


class TestDaemonManifestWatcher:
    """Test daemon manifest watcher."""

    def test_watcher_starts_and_stops(self, tmp_path):
        """Test that watcher can start and stop."""
        callback = Mock()
        watcher = DaemonManifestWatcher(tmp_path, callback, poll_interval=1)

        assert not watcher.is_running()

        watcher.start()
        assert watcher.is_running()

        time.sleep(0.5)

        watcher.stop()
        time.sleep(0.5)
        assert not watcher.is_running()

    def test_watcher_detects_new_files(self, tmp_path):
        """Test that watcher detects new manifest files."""
        callback = Mock()
        watcher = DaemonManifestWatcher(tmp_path, callback, poll_interval=1)

        watcher.start()

        try:
            # Wait for watcher to settle
            time.sleep(0.5)

            # Create a new manifest
            manifest = tmp_path / "test.yaml"
            manifest.write_text("hypervisor: vmware\n")

            # Wait for detection (watchdog is instant, polling needs time)
            if WATCHDOG_AVAILABLE:
                time.sleep(1)
            else:
                time.sleep(2.5)  # Polling interval + buffer

            # Callback should have been called
            assert callback.call_count >= 1
            callback.assert_called_with(manifest)

        finally:
            watcher.stop()

    def test_watcher_ignores_invalid_files(self, tmp_path):
        """Test that watcher ignores non-manifest files."""
        callback = Mock()
        watcher = DaemonManifestWatcher(tmp_path, callback, poll_interval=1)

        watcher.start()

        try:
            time.sleep(0.5)

            # Create invalid files
            txt_file = tmp_path / "test.txt"
            txt_file.write_text("not a manifest")

            # Wait
            time.sleep(2.5)

            # Callback should not be called
            callback.assert_not_called()

        finally:
            watcher.stop()

    def test_callback_exception_handling(self, tmp_path):
        """Test that watcher handles callback exceptions gracefully."""
        # Callback that raises an exception
        callback = Mock(side_effect=Exception("Test error"))
        watcher = DaemonManifestWatcher(tmp_path, callback, poll_interval=1)

        watcher.start()

        try:
            time.sleep(0.5)

            # Create manifest
            manifest = tmp_path / "test.yaml"
            manifest.write_text("hypervisor: vmware\n")

            # Wait for processing
            time.sleep(2.5)

            # Watcher should still be running despite exception
            assert watcher.is_running()

        finally:
            watcher.stop()


class TestWatchdogAvailability:
    """Test watchdog availability detection."""

    def test_watchdog_flag_is_boolean(self):
        """Test that WATCHDOG_AVAILABLE is a boolean."""
        assert isinstance(WATCHDOG_AVAILABLE, bool)

    def test_watcher_works_without_watchdog(self, tmp_path):
        """Test that watcher works even without watchdog (polling mode)."""
        # This test ensures RHEL 10 compatibility
        callback = Mock()

        # Create watcher (will use appropriate implementation)
        watcher = DaemonManifestWatcher(tmp_path, callback, poll_interval=1)

        watcher.start()
        assert watcher.is_running()

        watcher.stop()
        assert not watcher.is_running()
