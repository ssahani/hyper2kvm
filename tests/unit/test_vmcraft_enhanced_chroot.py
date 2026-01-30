# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Unit tests for VMCraft enhanced chroot with bind mounts.

Tests the command_with_mounts() method that provides /proc, /dev, /sys
access for bootloader commands like grub2-mkconfig.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, call
from hyper2kvm.core.vmcraft.main import VMCraft


class TestEnhancedChroot:
    """Test enhanced chroot with bind mounts."""

    def test_command_with_mounts_not_launched(self):
        """Test that command_with_mounts raises error when not launched."""
        g = VMCraft()

        with pytest.raises(RuntimeError, match="Not launched"):
            g.command_with_mounts(["echo", "test"])

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_command_with_mounts_creates_bind_mounts(self, mock_run_sudo):
        """Test that command_with_mounts creates /proc, /dev, /sys bind mounts."""
        g = VMCraft()

        # Create temporary mount root
        with tempfile.TemporaryDirectory() as tmpdir:
            mount_root = Path(tmpdir)
            g._mount_root = str(mount_root)

            # Create mount points
            for mp in ["proc", "dev", "sys"]:
                (mount_root / mp).mkdir(exist_ok=True)

            # Mock successful command execution
            def mock_sudo_side_effect(logger, cmd, **kwargs):
                result = Mock()
                result.returncode = 0
                result.stdout = "test output"
                result.stderr = ""

                # Simulate mountpoint checks returning "not mounted"
                if cmd[0] == "mountpoint":
                    result.returncode = 1  # Not mounted

                return result

            mock_run_sudo.side_effect = mock_sudo_side_effect

            # Execute command with mounts
            output = g.command_with_mounts(["grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"])

            # Verify bind mounts were created
            mount_calls = [c for c in mock_run_sudo.call_args_list if "mount" in c[0][1][0]]

            # Should have 3 bind mount calls (proc, dev, sys)
            bind_mount_calls = [c for c in mount_calls if "--bind" in c[0][1]]
            assert len(bind_mount_calls) == 3

            # Verify each mount target
            mount_targets = [c[0][1][3] for c in bind_mount_calls]
            assert str(mount_root / "proc") in mount_targets
            assert str(mount_root / "dev") in mount_targets
            assert str(mount_root / "sys") in mount_targets

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_command_with_mounts_prevents_double_mount(self, mock_run_sudo):
        """Test that command_with_mounts skips already-mounted filesystems."""
        g = VMCraft()

        with tempfile.TemporaryDirectory() as tmpdir:
            mount_root = Path(tmpdir)
            g._mount_root = str(mount_root)

            for mp in ["proc", "dev", "sys"]:
                (mount_root / mp).mkdir(exist_ok=True)

            # Mock /proc already mounted, but /dev and /sys not
            def mock_sudo_side_effect(logger, cmd, **kwargs):
                result = Mock()
                result.returncode = 0
                result.stdout = "test output"
                result.stderr = ""

                # Simulate mountpoint checks
                if cmd[0] == "mountpoint":
                    # /proc is already mounted (returncode 0)
                    if "proc" in cmd[2]:
                        result.returncode = 0
                    # /dev and /sys not mounted (returncode 1)
                    else:
                        result.returncode = 1

                return result

            mock_run_sudo.side_effect = mock_sudo_side_effect

            # Execute command
            output = g.command_with_mounts(["grub2-mkconfig"])

            # Verify only 2 bind mounts created (dev, sys - not proc)
            bind_mount_calls = [c for c in mock_run_sudo.call_args_list
                              if len(c[0]) > 1 and len(c[0][1]) > 1
                              and "--bind" in c[0][1]]

            # Should only mount /dev and /sys (proc already mounted)
            assert len(bind_mount_calls) == 2

            mount_targets = [c[0][1][3] for c in bind_mount_calls]
            assert str(mount_root / "dev") in mount_targets
            assert str(mount_root / "sys") in mount_targets
            assert str(mount_root / "proc") not in mount_targets

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_command_with_mounts_cleanup_on_success(self, mock_run_sudo):
        """Test that bind mounts are cleaned up after successful command."""
        g = VMCraft()

        with tempfile.TemporaryDirectory() as tmpdir:
            mount_root = Path(tmpdir)
            g._mount_root = str(mount_root)

            for mp in ["proc", "dev", "sys"]:
                (mount_root / mp).mkdir(exist_ok=True)

            def mock_sudo_side_effect(logger, cmd, **kwargs):
                result = Mock()
                result.returncode = 0 if cmd[0] != "mountpoint" else 1
                result.stdout = "success"
                result.stderr = ""
                return result

            mock_run_sudo.side_effect = mock_sudo_side_effect

            # Execute command
            output = g.command_with_mounts(["grub2-mkconfig"])

            # Verify umount was called for each mount
            umount_calls = [c for c in mock_run_sudo.call_args_list
                          if len(c[0]) > 1 and c[0][1][0] == "umount"]

            # Should have 3 umount calls (one for each bind mount)
            assert len(umount_calls) == 3

            # Verify unmount targets
            umount_targets = [c[0][1][1] for c in umount_calls]
            assert str(mount_root / "proc") in umount_targets
            assert str(mount_root / "dev") in umount_targets
            assert str(mount_root / "sys") in umount_targets

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_command_with_mounts_cleanup_on_error(self, mock_run_sudo):
        """Test that bind mounts are cleaned up even when command fails."""
        g = VMCraft()

        with tempfile.TemporaryDirectory() as tmpdir:
            mount_root = Path(tmpdir)
            g._mount_root = str(mount_root)

            for mp in ["proc", "dev", "sys"]:
                (mount_root / mp).mkdir(exist_ok=True)

            def mock_sudo_side_effect(logger, cmd, **kwargs):
                result = Mock()

                # Mountpoint checks: not mounted
                if cmd[0] == "mountpoint":
                    result.returncode = 1
                # Mount commands: succeed
                elif cmd[0] == "mount":
                    result.returncode = 0
                # Chroot command: FAIL
                elif cmd[0] == "chroot":
                    result.returncode = 1
                    result.stdout = ""
                    result.stderr = "command failed"
                    if kwargs.get('check'):
                        from hyper2kvm.core.utils import CommandError
                        raise CommandError("Command failed", 1, "", "command failed")
                # Umount commands: succeed
                elif cmd[0] == "umount":
                    result.returncode = 0
                else:
                    result.returncode = 0

                result.stdout = ""
                result.stderr = ""
                return result

            mock_run_sudo.side_effect = mock_sudo_side_effect

            # Execute command (should fail)
            with pytest.raises(Exception):  # CommandError or similar
                g.command_with_mounts(["grub2-mkconfig"])

            # Verify umount was still called for cleanup
            umount_calls = [c for c in mock_run_sudo.call_args_list
                          if len(c[0]) > 1 and c[0][1][0] == "umount"]

            # Should still have 3 umount calls even though command failed
            assert len(umount_calls) == 3

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_command_with_mounts_reverse_order_unmount(self, mock_run_sudo):
        """Test that mounts are unmounted in reverse order."""
        g = VMCraft()

        with tempfile.TemporaryDirectory() as tmpdir:
            mount_root = Path(tmpdir)
            g._mount_root = str(mount_root)

            for mp in ["proc", "dev", "sys"]:
                (mount_root / mp).mkdir(exist_ok=True)

            mount_order = []
            umount_order = []

            def mock_sudo_side_effect(logger, cmd, **kwargs):
                result = Mock()
                result.returncode = 0 if cmd[0] != "mountpoint" else 1
                result.stdout = "ok"
                result.stderr = ""

                # Track mount order
                if cmd[0] == "mount" and "--bind" in cmd:
                    mount_point = cmd[3].split('/')[-1]  # Extract proc/dev/sys
                    mount_order.append(mount_point)

                # Track umount order
                if cmd[0] == "umount":
                    mount_point = cmd[1].split('/')[-1]
                    umount_order.append(mount_point)

                return result

            mock_run_sudo.side_effect = mock_sudo_side_effect

            # Execute command
            output = g.command_with_mounts(["grub2-mkconfig"])

            # Verify mounts created
            assert len(mount_order) == 3

            # Verify unmounts happened in reverse order
            assert len(umount_order) == 3
            assert umount_order == list(reversed(mount_order))

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_command_with_mounts_quiet_mode(self, mock_run_sudo):
        """Test that quiet mode suppresses command output."""
        g = VMCraft()

        with tempfile.TemporaryDirectory() as tmpdir:
            mount_root = Path(tmpdir)
            g._mount_root = str(mount_root)

            for mp in ["proc", "dev", "sys"]:
                (mount_root / mp).mkdir(exist_ok=True)

            def mock_sudo_side_effect(logger, cmd, **kwargs):
                result = Mock()
                result.returncode = 0 if cmd[0] != "mountpoint" else 1
                result.stdout = "output"
                result.stderr = ""
                return result

            mock_run_sudo.side_effect = mock_sudo_side_effect

            # Execute in quiet mode
            output = g.command_with_mounts(["grub2-mkconfig"], quiet=True)

            # Verify chroot command was called with quiet logging
            chroot_calls = [c for c in mock_run_sudo.call_args_list
                          if len(c[0]) > 1 and c[0][1][0] == "chroot"]

            assert len(chroot_calls) == 1

            # Check that failure_log_level was set (indicates quiet mode)
            assert 'failure_log_level' in chroot_calls[0][1]

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_command_with_mounts_creates_mount_points(self, mock_run_sudo):
        """Test that missing mount points are created."""
        g = VMCraft()

        with tempfile.TemporaryDirectory() as tmpdir:
            mount_root = Path(tmpdir)
            g._mount_root = str(mount_root)

            # Don't create mount points - let command_with_mounts do it

            def mock_sudo_side_effect(logger, cmd, **kwargs):
                result = Mock()
                result.returncode = 0 if cmd[0] != "mountpoint" else 1
                result.stdout = ""
                result.stderr = ""
                return result

            mock_run_sudo.side_effect = mock_sudo_side_effect

            # Execute command
            output = g.command_with_mounts(["grub2-mkconfig"])

            # Verify mount points were created
            assert (mount_root / "proc").exists()
            assert (mount_root / "dev").exists()
            assert (mount_root / "sys").exists()

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_command_with_mounts_returns_stdout(self, mock_run_sudo):
        """Test that command_with_mounts returns command stdout."""
        g = VMCraft()

        with tempfile.TemporaryDirectory() as tmpdir:
            mount_root = Path(tmpdir)
            g._mount_root = str(mount_root)

            for mp in ["proc", "dev", "sys"]:
                (mount_root / mp).mkdir(exist_ok=True)

            expected_output = "Generated grub.cfg"

            def mock_sudo_side_effect(logger, cmd, **kwargs):
                result = Mock()
                result.returncode = 0 if cmd[0] != "mountpoint" else 1

                # Return expected output for chroot command
                if cmd[0] == "chroot":
                    result.stdout = expected_output
                else:
                    result.stdout = ""

                result.stderr = ""
                return result

            mock_run_sudo.side_effect = mock_sudo_side_effect

            # Execute command
            output = g.command_with_mounts(["grub2-mkconfig"])

            # Verify correct output returned
            assert output == expected_output


class TestEnhancedChrootIntegration:
    """Integration tests for enhanced chroot in GRUB fixer."""

    def test_run_guestfs_cmd_uses_enhanced_chroot(self):
        """Test that _run_guestfs_cmd detects and uses command_with_mounts for bootloader commands."""
        from hyper2kvm.fixers.bootloader.grub import _run_guestfs_cmd

        # Create mock context (self) with logger
        mock_self = Mock()
        mock_self.logger = Mock()

        # Create mock VMCraft with command_with_mounts
        mock_g = Mock(spec=VMCraft)
        mock_g.command_with_mounts = Mock(return_value="")
        mock_g.command_quiet = Mock(return_value="")

        # Run grub2-mkconfig (should use command_with_mounts)
        success, output = _run_guestfs_cmd(mock_self, mock_g, ["grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"])

        # Verify command_with_mounts was called
        mock_g.command_with_mounts.assert_called_once()

        # Verify it was called with quiet=True
        call_kwargs = mock_g.command_with_mounts.call_args[1]
        assert call_kwargs.get('quiet') == True
        assert success == True

    def test_run_guestfs_cmd_detects_bootloader_commands(self):
        """Test that _run_guestfs_cmd correctly identifies bootloader commands."""
        from hyper2kvm.fixers.bootloader.grub import _run_guestfs_cmd

        mock_self = Mock()
        mock_self.logger = Mock()

        # Test all bootloader commands
        bootloader_commands = [
            "grub2-mkconfig",
            "grub-mkconfig",
            "update-grub",
            "update-grub2",
            "grub2-install",
            "grub-install",
            "grub2-probe",
            "grub-probe"
        ]

        for cmd in bootloader_commands:
            mock_g = Mock(spec=VMCraft)
            mock_g.command_with_mounts = Mock(return_value="")
            mock_g.command_quiet = Mock(return_value="")

            success, output = _run_guestfs_cmd(mock_self, mock_g, [cmd, "--option"])

            # Should use command_with_mounts for bootloader commands
            assert mock_g.command_with_mounts.called, f"{cmd} should use command_with_mounts"
            assert not mock_g.command_quiet.called, f"{cmd} should not use command_quiet"

    def test_run_guestfs_cmd_fallback_for_non_bootloader(self):
        """Test that _run_guestfs_cmd uses standard command for non-bootloader commands."""
        from hyper2kvm.fixers.bootloader.grub import _run_guestfs_cmd

        mock_self = Mock()
        mock_self.logger = Mock()

        mock_g = Mock(spec=VMCraft)
        mock_g.command_with_mounts = Mock(return_value="")
        mock_g.command_quiet = Mock(return_value="")

        # Run non-bootloader command
        success, output = _run_guestfs_cmd(mock_self, mock_g, ["cat", "/etc/fstab"])

        # Should use command_quiet, not command_with_mounts
        assert not mock_g.command_with_mounts.called
        assert mock_g.command_quiet.called

    def test_run_guestfs_cmd_backward_compatibility(self):
        """Test that _run_guestfs_cmd falls back gracefully when command_with_mounts not available."""
        from hyper2kvm.fixers.bootloader.grub import _run_guestfs_cmd

        mock_self = Mock()
        mock_self.logger = Mock()

        # Create mock without command_with_mounts (simulating old VMCraft or libguestfs)
        mock_g = Mock()
        mock_g.command_quiet = Mock(return_value="")

        # Remove command_with_mounts attribute
        if hasattr(mock_g, 'command_with_mounts'):
            delattr(mock_g, 'command_with_mounts')

        # Run bootloader command
        success, output = _run_guestfs_cmd(mock_self, mock_g, ["grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"])

        # Should fall back to command_quiet
        assert mock_g.command_quiet.called
