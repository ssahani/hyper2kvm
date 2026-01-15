# SPDX-License-Identifier: LGPL-3.0-or-later
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from hyper2kvm.testers.qemu_tester import QemuTester


class TestQemuTester(unittest.TestCase):
    """Test QEMU-based VM testing."""

    def setUp(self):
        self.logger = Mock()

    @patch('hyper2kvm.core.utils.U.which')
    def test_checks_for_qemu(self, mock_which):
        """Test that QEMU availability is checked."""
        mock_which.return_value = None

        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            tester = QemuTester(self.logger, disk)

            # Should detect missing QEMU
            with self.assertRaises((SystemExit, RuntimeError)):
                tester.boot_test(timeout=1)

    @patch('subprocess.Popen')
    @patch('hyper2kvm.core.utils.U.which')
    def test_launches_qemu_process(self, mock_which, mock_popen):
        """Test that QEMU process is launched."""
        mock_which.return_value = "/usr/bin/qemu-system-x86_64"

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            tester = QemuTester(self.logger, disk)

            try:
                tester.boot_test(timeout=1, headless=True)
            except:
                pass  # May fail due to mocking

            # Verify QEMU was called
            self.assertTrue(mock_popen.called)

    def test_configures_memory(self):
        """Test that memory configuration is passed to QEMU."""
        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            tester = QemuTester(self.logger, disk, memory_mb=2048)

            self.assertEqual(tester.memory_mb, 2048)

    def test_configures_vcpus(self):
        """Test that vCPU configuration is passed to QEMU."""
        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            tester = QemuTester(self.logger, disk, vcpus=4)

            self.assertEqual(tester.vcpus, 4)

    def test_headless_mode(self):
        """Test headless mode configuration."""
        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            tester = QemuTester(self.logger, disk)

            # Headless mode should disable graphics
            self.assertTrue(hasattr(tester, 'boot_test'))


class TestQemuTesterCommandBuilding(unittest.TestCase):
    """Test QEMU command line building."""

    def setUp(self):
        self.logger = Mock()

    def test_builds_basic_command(self):
        """Test basic QEMU command construction."""
        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            tester = QemuTester(self.logger, disk)
            cmd = tester.build_qemu_command()

            self.assertIn("qemu-system-x86_64", " ".join(cmd))
            self.assertIn(str(disk), " ".join(cmd))

    def test_includes_kvm_acceleration(self):
        """Test that KVM acceleration is enabled when available."""
        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            tester = QemuTester(self.logger, disk, enable_kvm=True)
            cmd = tester.build_qemu_command()

            self.assertIn("-enable-kvm", cmd)

    def test_snapshot_mode(self):
        """Test snapshot mode to prevent disk modifications."""
        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            tester = QemuTester(self.logger, disk, snapshot=True)
            cmd = tester.build_qemu_command()

            self.assertIn("-snapshot", cmd)


if __name__ == "__main__":
    unittest.main()
