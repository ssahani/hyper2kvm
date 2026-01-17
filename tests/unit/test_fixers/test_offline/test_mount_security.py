# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Security tests for offline mount engine.
Tests path traversal prevention and input validation.
"""

import unittest

from hyper2kvm.fixers.offline.mount import OfflineMountEngine


class TestSubvolPathSanitization(unittest.TestCase):
    """Test BTRFS subvolume path sanitization for security vulnerabilities."""

    def test_valid_subvol_paths(self):
        """Test that valid subvolume paths are accepted."""
        valid_paths = [
            "@",
            "@root",
            "@rootfs",
            "@/",
            "@/.snapshots/1/snapshot",
            "subvol",
            "path/to/subvol",
            "/absolute/path",
        ]

        for path in valid_paths:
            with self.subTest(path=path):
                result = OfflineMountEngine._sanitize_subvol_path(path)
                self.assertIsNotNone(result)
                self.assertIsInstance(result, str)
                # Should not contain dangerous characters after sanitization
                self.assertNotIn("\x00", result)
                self.assertNotIn(",", result)

    def test_path_traversal_rejected(self):
        """Test that path traversal attempts are rejected."""
        dangerous_paths = [
            "../etc/passwd",
            "../../root",
            "@/../etc",
            "subvol/../../../",
            "..\\..\\windows",
        ]

        for path in dangerous_paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError) as ctx:
                    OfflineMountEngine._sanitize_subvol_path(path)
                self.assertIn("..", str(ctx.exception))

    def test_null_byte_injection_rejected(self):
        """Test that null byte injection is rejected."""
        dangerous_paths = [
            "subvol\x00/etc/shadow",
            "@\x00malicious",
            "path\x00to\x00subvol",
        ]

        for path in dangerous_paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError) as ctx:
                    OfflineMountEngine._sanitize_subvol_path(path)
                self.assertIn("null byte", str(ctx.exception))

    def test_mount_option_injection_rejected(self):
        """Test that mount option injection via comma is rejected."""
        dangerous_paths = [
            "@,rw",
            "subvol,exec",
            "path,nosuid,noexec",
            "@/.snapshots/1/snapshot,malicious=yes",
        ]

        for path in dangerous_paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError) as ctx:
                    OfflineMountEngine._sanitize_subvol_path(path)
                self.assertIn("comma", str(ctx.exception))

    def test_shell_metacharacter_injection_rejected(self):
        """Test that shell metacharacters are rejected."""
        dangerous_chars = [";", "&", "|", "`", "$", "(", ")", "<", ">"]

        for char in dangerous_chars:
            path = f"subvol{char}malicious"
            with self.subTest(path=path, char=char):
                with self.assertRaises(ValueError) as ctx:
                    OfflineMountEngine._sanitize_subvol_path(path)
                self.assertIn("dangerous character", str(ctx.exception))

    def test_newline_injection_rejected(self):
        """Test that newline/carriage return injection is rejected."""
        dangerous_paths = [
            "subvol\nmalicious",
            "@\rmalicious",
            "path\n\rinjection",
        ]

        for path in dangerous_paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError) as ctx:
                    OfflineMountEngine._sanitize_subvol_path(path)
                self.assertIn("dangerous character", str(ctx.exception))

    def test_empty_path_rejected(self):
        """Test that empty paths are rejected."""
        with self.assertRaises(ValueError) as ctx:
            OfflineMountEngine._sanitize_subvol_path("")
        self.assertIn("empty", str(ctx.exception))

    def test_path_length_limit(self):
        """Test that excessively long paths are rejected."""
        # Create a path longer than 4096 characters
        long_path = "a" * 4097
        with self.assertRaises(ValueError) as ctx:
            OfflineMountEngine._sanitize_subvol_path(long_path)
        self.assertIn("too long", str(ctx.exception))

    def test_path_normalization(self):
        """Test that paths are normalized correctly."""
        test_cases = [
            ("@///.snapshots//1/snapshot", "@/.snapshots/1/snapshot"),
            ("path/to///subvol", "path/to/subvol"),
            ("@\\rootfs", "@/rootfs"),  # Windows-style separator
        ]

        for input_path, expected in test_cases:
            with self.subTest(input=input_path, expected=expected):
                result = OfflineMountEngine._sanitize_subvol_path(input_path)
                self.assertEqual(result, expected)

    def test_leading_slash_preserved(self):
        """Test that leading slashes are preserved."""
        paths_with_leading_slash = [
            "/absolute/path",
            "/@root",
            "/subvol",
        ]

        for path in paths_with_leading_slash:
            with self.subTest(path=path):
                result = OfflineMountEngine._sanitize_subvol_path(path)
                self.assertTrue(result.startswith("/"))


if __name__ == "__main__":
    unittest.main()
