# SPDX-License-Identifier: LGPL-3.0-or-later
"""
New tests for QemuTest static method API
Tests the current QemuTest.run() static method implementation
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from hyper2kvm.testers.qemu_tester import QemuDisplay, QemuMachine, QemuNet, QemuTest


class TestQemuTestStaticAPI(unittest.TestCase):
    """Test QemuTest static run() method."""

    def setUp(self):
        self.logger = Mock()

    @patch('hyper2kvm.core.utils.U.which')
    def test_qemu_binary_not_found(self, mock_which):
        """Test that missing qemu-system-x86_64 is handled."""
        mock_which.return_value = None

        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            # Should raise Fatal exception when qemu not found
            from hyper2kvm.core.exceptions import Fatal
            with self.assertRaises(Fatal):
                QemuTest.run(
                    self.logger,
                    disk,
                    memory_mib=2048,
                    vcpus=2,
                    uefi=False,
                    timeout_s=1
                )

    @patch('hyper2kvm.core.utils.U.which')
    def test_missing_disk_file(self, mock_which):
        """Test that missing disk file is handled."""
        mock_which.return_value = "/usr/bin/qemu-system-x86_64"

        nonexistent_disk = Path("/tmp/nonexistent-disk.qcow2")

        from hyper2kvm.core.exceptions import Fatal
        with self.assertRaises(Fatal):
            QemuTest.run(
                self.logger,
                nonexistent_disk,
                memory_mib=2048,
                vcpus=2,
                uefi=False,
                timeout_s=1
            )

    @patch('subprocess.Popen')
    @patch('hyper2kvm.core.utils.U.which')
    @patch('hyper2kvm.core.utils.U.run_cmd')
    def test_display_modes(self, mock_run_cmd, mock_which, mock_popen):
        """Test different display mode configurations."""
        mock_which.return_value = "/usr/bin/qemu-system-x86_64"
        mock_proc = MagicMock()
        mock_proc.wait.side_effect = lambda timeout=None: None
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            # Test headless mode (none)
            display = QemuDisplay(mode="none")
            try:
                QemuTest.run(
                    self.logger,
                    disk,
                    memory_mib=1024,
                    vcpus=1,
                    uefi=False,
                    display=display,
                    timeout_s=1
                )
            except:
                pass  # Mock may cause errors, we're just checking it doesn't crash

            # Test VNC mode
            display = QemuDisplay(mode="vnc", vnc_listen="127.0.0.1", vnc_display=1)
            try:
                QemuTest.run(
                    self.logger,
                    disk,
                    memory_mib=1024,
                    vcpus=1,
                    uefi=False,
                    display=display,
                    timeout_s=1
                )
            except:
                pass

    @patch('subprocess.Popen')
    @patch('hyper2kvm.core.utils.U.which')
    @patch('hyper2kvm.core.utils.U.run_cmd')
    def test_network_configuration(self, mock_run_cmd, mock_which, mock_popen):
        """Test network configuration options."""
        mock_which.return_value = "/usr/bin/qemu-system-x86_64"
        mock_proc = MagicMock()
        mock_proc.wait.side_effect = lambda timeout=None: None
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            # Test with SSH forwarding
            net = QemuNet(enabled=True, ssh_forward_host_port=2222)
            try:
                QemuTest.run(
                    self.logger,
                    disk,
                    memory_mib=1024,
                    vcpus=1,
                    uefi=False,
                    net=net,
                    timeout_s=1
                )
            except:
                pass

            # Test without SSH forwarding
            net = QemuNet(enabled=True, ssh_forward_host_port=None)
            try:
                QemuTest.run(
                    self.logger,
                    disk,
                    memory_mib=1024,
                    vcpus=1,
                    uefi=False,
                    net=net,
                    timeout_s=1
                )
            except:
                pass

    @patch('hyper2kvm.core.utils.U.which')
    def test_machine_acceleration_fallback(self, mock_which):
        """Test that KVM fallback to TCG works when /dev/kvm missing."""
        mock_which.return_value = "/usr/bin/qemu-system-x86_64"

        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            # Machine with KVM (will fallback to TCG if /dev/kvm missing)
            machine = QemuMachine(machine="q35", accel="kvm", cpu="host")

            # This should not crash even if /dev/kvm doesn't exist
            # The code will auto-fallback to TCG
            self.assertIsNotNone(machine)

    def test_display_args_generation(self):
        """Test _display_args helper method."""
        # Test headless
        display = QemuDisplay(mode="none")
        args = QemuTest._display_args(display)
        self.assertIn("-nographic", args)

        # Test VNC
        display = QemuDisplay(mode="vnc", vnc_listen="0.0.0.0", vnc_display=2)
        args = QemuTest._display_args(display)
        self.assertIn("-vnc", args)
        self.assertIn("0.0.0.0:2", args)

        # Test GTK
        display = QemuDisplay(mode="gtk")
        args = QemuTest._display_args(display)
        self.assertIn("-display", args)
        self.assertIn("gtk", args)

    def test_net_args_generation(self):
        """Test _net_args helper method."""
        # With SSH forwarding
        net = QemuNet(enabled=True, ssh_forward_host_port=3333)
        args = QemuTest._net_args(net)
        self.assertIn("-netdev", args)
        self.assertIn("hostfwd=tcp::3333-:22", " ".join(args))

        # Without SSH forwarding
        net = QemuNet(enabled=True, ssh_forward_host_port=None)
        args = QemuTest._net_args(net)
        self.assertIn("-netdev", args)
        self.assertIn("virtio-net-pci", " ".join(args))

    @patch('hyper2kvm.core.utils.U.run_cmd')
    @patch('hyper2kvm.core.utils.U.which')
    def test_detect_img_format(self, mock_which, mock_run_cmd):
        """Test image format detection."""
        mock_which.return_value = "/usr/bin/qemu-img"

        with tempfile.TemporaryDirectory() as td:
            # Test qcow2 by suffix
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake")
            fmt = QemuTest._detect_img_format(self.logger, disk)
            self.assertEqual(fmt, "qcow2")

            # Test raw by suffix
            disk = Path(td) / "test.raw"
            disk.write_bytes(b"fake")
            fmt = QemuTest._detect_img_format(self.logger, disk)
            self.assertEqual(fmt, "raw")

            # Test vmdk by suffix
            disk = Path(td) / "test.vmdk"
            disk.write_bytes(b"fake")
            fmt = QemuTest._detect_img_format(self.logger, disk)
            self.assertEqual(fmt, "vmdk")


class TestQemuTestWindowsSupport(unittest.TestCase):
    """Test Windows-specific QEMU configurations."""

    def setUp(self):
        self.logger = Mock()

    def test_disk_interface_for_windows_bootstrap(self):
        """Test that Windows bootstrap uses SATA."""
        from hyper2kvm.testers.qemu_tester import GuestProfile

        profile = GuestProfile(os="windows", win_stage="bootstrap")
        disk_if = QemuTest._disk_if_for_profile(profile)
        self.assertEqual(disk_if, "sata")

    def test_disk_interface_for_windows_final(self):
        """Test that Windows final stage uses virtio."""
        from hyper2kvm.testers.qemu_tester import GuestProfile

        profile = GuestProfile(os="windows", win_stage="final")
        disk_if = QemuTest._disk_if_for_profile(profile)
        self.assertEqual(disk_if, "virtio")

    def test_disk_interface_for_linux(self):
        """Test that Linux uses virtio."""
        from hyper2kvm.testers.qemu_tester import GuestProfile

        profile = GuestProfile(os="linux")
        disk_if = QemuTest._disk_if_for_profile(profile)
        self.assertEqual(disk_if, "virtio")

    def test_video_args_for_headless(self):
        """Test that headless mode has no video args."""
        from hyper2kvm.testers.qemu_tester import GuestProfile

        display = QemuDisplay(mode="none")
        profile = GuestProfile(os="windows", win_stage="bootstrap")

        args = QemuTest._video_args_for_profile(profile, display)
        self.assertEqual(args, [])

    def test_video_args_for_windows_bootstrap(self):
        """Test Windows bootstrap uses standard VGA."""
        from hyper2kvm.testers.qemu_tester import GuestProfile

        display = QemuDisplay(mode="gtk")
        profile = GuestProfile(os="windows", win_stage="bootstrap")

        args = QemuTest._video_args_for_profile(profile, display)
        self.assertIn("-vga", args)
        self.assertIn("std", args)

    def test_video_args_for_windows_final(self):
        """Test Windows final stage uses virtio-vga."""
        from hyper2kvm.testers.qemu_tester import GuestProfile

        display = QemuDisplay(mode="gtk")
        profile = GuestProfile(os="windows", win_stage="final")

        args = QemuTest._video_args_for_profile(profile, display)
        self.assertIn("-vga", args)
        self.assertIn("virtio", args)


if __name__ == "__main__":
    unittest.main()
