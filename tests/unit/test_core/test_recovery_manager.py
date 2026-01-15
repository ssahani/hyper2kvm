# SPDX-License-Identifier: LGPL-3.0-or-later
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from hyper2kvm.core.recovery_manager import RecoveryManager


class TestRecoveryManager(unittest.TestCase):
    """Test failure recovery and cleanup manager."""

    def setUp(self):
        self.logger = Mock()

    def test_registers_cleanup_action(self):
        """Test registering cleanup actions."""
        manager = RecoveryManager(self.logger)
        cleanup_fn = Mock()

        manager.register_cleanup(cleanup_fn, "test cleanup")

        self.assertEqual(len(manager.cleanup_actions), 1)

    def test_executes_cleanup_actions(self):
        """Test execution of cleanup actions."""
        manager = RecoveryManager(self.logger)
        cleanup_fn = Mock()

        manager.register_cleanup(cleanup_fn, "test cleanup")
        manager.execute_cleanup()

        self.assertTrue(cleanup_fn.called)

    def test_cleanup_actions_execute_in_reverse_order(self):
        """Test that cleanup actions execute in reverse registration order."""
        manager = RecoveryManager(self.logger)
        order = []

        def cleanup1():
            order.append(1)

        def cleanup2():
            order.append(2)

        def cleanup3():
            order.append(3)

        manager.register_cleanup(cleanup1, "cleanup 1")
        manager.register_cleanup(cleanup2, "cleanup 2")
        manager.register_cleanup(cleanup3, "cleanup 3")

        manager.execute_cleanup()

        # Should execute in reverse order: 3, 2, 1
        self.assertEqual(order, [3, 2, 1])

    def test_continues_cleanup_on_error(self):
        """Test that cleanup continues even if one action fails."""
        manager = RecoveryManager(self.logger)

        def failing_cleanup():
            raise Exception("Cleanup failed")

        successful_cleanup = Mock()

        manager.register_cleanup(successful_cleanup, "success")
        manager.register_cleanup(failing_cleanup, "failure")

        manager.execute_cleanup()

        # Should still execute successful cleanup despite failure
        self.assertTrue(successful_cleanup.called)

    def test_tracks_temporary_files(self):
        """Test tracking of temporary files for cleanup."""
        with tempfile.TemporaryDirectory() as td:
            manager = RecoveryManager(self.logger)
            temp_file = Path(td) / "temp.txt"
            temp_file.write_text("temporary")

            manager.track_temp_file(temp_file)

            self.assertIn(temp_file, manager.temp_files)

    def test_cleans_up_temporary_files(self):
        """Test cleanup of tracked temporary files."""
        with tempfile.TemporaryDirectory() as td:
            manager = RecoveryManager(self.logger)
            temp_file = Path(td) / "temp.txt"
            temp_file.write_text("temporary")

            manager.track_temp_file(temp_file)
            manager.cleanup_temp_files()

            self.assertFalse(temp_file.exists())

    def test_context_manager_executes_cleanup(self):
        """Test that context manager executes cleanup on exit."""
        cleanup_fn = Mock()

        with RecoveryManager(self.logger) as manager:
            manager.register_cleanup(cleanup_fn, "test")

        self.assertTrue(cleanup_fn.called)

    def test_context_manager_cleanup_on_exception(self):
        """Test that cleanup executes even on exception."""
        cleanup_fn = Mock()

        try:
            with RecoveryManager(self.logger) as manager:
                manager.register_cleanup(cleanup_fn, "test")
                raise ValueError("Test exception")
        except ValueError:
            pass

        self.assertTrue(cleanup_fn.called)


class TestRecoveryManagerFileOperations(unittest.TestCase):
    """Test recovery manager file operations."""

    def setUp(self):
        self.logger = Mock()

    def test_tracks_directory_for_removal(self):
        """Test tracking directory for removal."""
        with tempfile.TemporaryDirectory() as parent:
            manager = RecoveryManager(self.logger)
            test_dir = Path(parent) / "test_dir"
            test_dir.mkdir()

            (test_dir / "file.txt").write_text("content")

            manager.track_directory(test_dir)
            manager.cleanup_directories()

            self.assertFalse(test_dir.exists())

    def test_removes_directory_tree(self):
        """Test removal of directory tree."""
        with tempfile.TemporaryDirectory() as parent:
            manager = RecoveryManager(self.logger)
            test_dir = Path(parent) / "test_dir"
            test_dir.mkdir()

            subdir = test_dir / "subdir"
            subdir.mkdir()
            (subdir / "nested.txt").write_text("nested")

            manager.track_directory(test_dir)
            manager.cleanup_directories()

            self.assertFalse(test_dir.exists())


class TestRecoveryManagerErrorHandling(unittest.TestCase):
    """Test recovery manager error handling."""

    def setUp(self):
        self.logger = Mock()

    def test_logs_cleanup_failures(self):
        """Test that cleanup failures are logged."""
        manager = RecoveryManager(self.logger)

        def failing_cleanup():
            raise Exception("Cleanup error")

        manager.register_cleanup(failing_cleanup, "failing")
        manager.execute_cleanup()

        # Should log the error
        self.assertTrue(self.logger.error.called or self.logger.warning.called)

    def test_handles_missing_file_cleanup(self):
        """Test handling of missing files during cleanup."""
        manager = RecoveryManager(self.logger)
        nonexistent = Path("/nonexistent/file.txt")

        manager.track_temp_file(nonexistent)

        # Should not raise
        manager.cleanup_temp_files()


if __name__ == "__main__":
    unittest.main()
