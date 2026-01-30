# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test VMCraft blkid() implementation.

Tests the blkid() method added to VMCraft backend for device metadata retrieval.
This was a critical missing feature that prevented fstab UUID conversion.
"""
import unittest
from unittest.mock import Mock, MagicMock, patch
import subprocess

from hyper2kvm.core.vmcraft.main import VMCraft


class TestVMCraftBlkid(unittest.TestCase):
    """Test VMCraft's blkid implementation."""

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_blkid_parses_export_format(self, mock_run_sudo):
        """Test that blkid correctly parses `blkid -p -o export` output."""
        # Mock blkid output in export format (KEY=VALUE)
        mock_result = Mock()
        mock_result.stdout = """DEVNAME=/dev/nbd0p2
UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85
UUID_SUB=63f75341-021a-40cf-b9d7-23b16af7318b
TYPE=btrfs
USAGE=filesystem
PART_ENTRY_SCHEME=gpt
PART_ENTRY_UUID=0d86db64-f8ad-441f-ada9-3d50632d608d
PART_ENTRY_TYPE=0fc63daf-8483-4772-8e79-3d69d8477de4
PART_ENTRY_NUMBER=2
PART_ENTRY_OFFSET=4096
PART_ENTRY_SIZE=16773120
PART_ENTRY_DISK=259:0"""
        mock_run_sudo.return_value = mock_result

        vmcraft = VMCraft()

        # Call blkid
        metadata = vmcraft.blkid("/dev/nbd0p2")

        # Verify the command was called correctly
        mock_run_sudo.assert_called_once()
        call_args = mock_run_sudo.call_args
        self.assertEqual(call_args[0][1], ["blkid", "-p", "-o", "export", "/dev/nbd0p2"])

        # Verify parsed metadata
        self.assertEqual(metadata["UUID"], "f293ef3c-255a-4582-8016-f72fb8dd3f85")
        self.assertEqual(metadata["UUID_SUB"], "63f75341-021a-40cf-b9d7-23b16af7318b")
        self.assertEqual(metadata["TYPE"], "btrfs")
        self.assertEqual(metadata["PART_ENTRY_UUID"], "0d86db64-f8ad-441f-ada9-3d50632d608d")

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_blkid_handles_swap_partition(self, mock_run_sudo):
        """Test blkid with swap partition."""
        mock_result = Mock()
        mock_result.stdout = """DEVNAME=/dev/nbd0p3
UUID=03c038b5-fb29-470c-9f81-7100da936770
TYPE=swap
USAGE=other
PART_ENTRY_SCHEME=gpt
PART_ENTRY_UUID=f6d3a58b-76f1-4a62-8e04-75b044944370
PART_ENTRY_TYPE=0657fd6d-a4ab-43c4-84e5-0933c84b4f4f
PART_ENTRY_NUMBER=3"""
        mock_run_sudo.return_value = mock_result

        vmcraft = VMCraft()

        metadata = vmcraft.blkid("/dev/nbd0p3")

        self.assertEqual(metadata["UUID"], "03c038b5-fb29-470c-9f81-7100da936770")
        self.assertEqual(metadata["TYPE"], "swap")
        self.assertEqual(metadata["USAGE"], "other")

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_blkid_handles_ext4_partition(self, mock_run_sudo):
        """Test blkid with ext4 partition."""
        mock_result = Mock()
        mock_result.stdout = """DEVNAME=/dev/sda1
UUID=aaaa-bbbb-cccc-dddd-eeee
TYPE=ext4
USAGE=filesystem
LABEL=my-root"""
        mock_run_sudo.return_value = mock_result

        vmcraft = VMCraft()

        metadata = vmcraft.blkid("/dev/sda1")

        self.assertEqual(metadata["UUID"], "aaaa-bbbb-cccc-dddd-eeee")
        self.assertEqual(metadata["TYPE"], "ext4")
        self.assertEqual(metadata["LABEL"], "my-root")

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_blkid_returns_empty_dict_on_error(self, mock_run_sudo):
        """Test that blkid returns empty dict when command fails."""
        # Simulate blkid failure (device not found)
        mock_run_sudo.side_effect = subprocess.CalledProcessError(
            2, "blkid", stderr="blkid: /dev/nonexistent: No such file or directory"
        )

        vmcraft = VMCraft()

        metadata = vmcraft.blkid("/dev/nonexistent")

        # Should return empty dict on failure
        self.assertEqual(metadata, {})

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_blkid_preserves_uppercase_keys(self, mock_run_sudo):
        """Test that blkid preserves uppercase keys from blkid output."""
        mock_result = Mock()
        mock_result.stdout = """UUID=test-uuid
PARTUUID=test-partuuid
LABEL=TEST_LABEL
TYPE=ext4"""
        mock_run_sudo.return_value = mock_result

        vmcraft = VMCraft()

        metadata = vmcraft.blkid("/dev/sda1")

        # Keys should be uppercase as returned by blkid
        self.assertIn("UUID", metadata)
        self.assertIn("PARTUUID", metadata)
        self.assertIn("LABEL", metadata)
        self.assertIn("TYPE", metadata)
        # Not lowercase
        self.assertNotIn("uuid", metadata)

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_blkid_handles_empty_output(self, mock_run_sudo):
        """Test blkid with empty output."""
        mock_result = Mock()
        mock_result.stdout = ""
        mock_run_sudo.return_value = mock_result

        vmcraft = VMCraft()

        metadata = vmcraft.blkid("/dev/sda1")

        # Should return empty dict
        self.assertEqual(metadata, {})

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_blkid_ignores_lines_without_equals(self, mock_run_sudo):
        """Test that blkid ignores malformed lines without '=' separator."""
        mock_result = Mock()
        mock_result.stdout = """UUID=test-uuid
INVALID_LINE_NO_EQUALS
TYPE=ext4
ANOTHER_INVALID
LABEL=test"""
        mock_run_sudo.return_value = mock_result

        vmcraft = VMCraft()

        metadata = vmcraft.blkid("/dev/sda1")

        # Should only parse valid KEY=VALUE lines
        self.assertEqual(metadata["UUID"], "test-uuid")
        self.assertEqual(metadata["TYPE"], "ext4")
        self.assertEqual(metadata["LABEL"], "test")
        self.assertEqual(len(metadata), 3)


class TestBlkidIntegrationWithFstab(unittest.TestCase):
    """Test blkid integration with fstab conversion."""

    @patch('hyper2kvm.core.vmcraft.main.run_sudo')
    def test_blkid_provides_data_for_fstab_conversion(self, mock_run_sudo):
        """Test that blkid provides necessary data for Ident.choose_stable()."""
        # This simulates the flow:
        # 1. spec_converter calls g.blkid(device)
        # 2. Ident.g_blkid_map() normalizes the data
        # 3. Ident.choose_stable() picks UUID/PARTUUID/LABEL

        mock_result = Mock()
        mock_result.stdout = """UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85
PART_ENTRY_UUID=0d86db64-f8ad-441f-ada9-3d50632d608d
TYPE=btrfs"""
        mock_run_sudo.return_value = mock_result

        vmcraft = VMCraft()

        # Get blkid metadata
        metadata = vmcraft.blkid("/dev/nbd0p2")

        # This is what Ident.g_blkid_map() does - it expects uppercase keys
        blkid_map = {str(k).upper(): str(v) for k, v in metadata.items()}

        # Verify the data is suitable for fstab conversion
        self.assertEqual(blkid_map["UUID"], "f293ef3c-255a-4582-8016-f72fb8dd3f85")
        self.assertIn("PART_ENTRY_UUID", blkid_map)

        # Simulate what Ident.choose_stable() does
        if "UUID" in blkid_map:
            stable_id = f"UUID={blkid_map['UUID']}"
            self.assertEqual(stable_id, "UUID=f293ef3c-255a-4582-8016-f72fb8dd3f85")


if __name__ == "__main__":
    unittest.main()
