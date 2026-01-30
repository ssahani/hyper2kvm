# SPDX-License-Identifier: LGPL-3.0-or-later
"""Tests for JSON Schema validation of Artifact Manifest v1."""

import json
import unittest
from pathlib import Path

try:
    import jsonschema
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False


@unittest.skipUnless(JSONSCHEMA_AVAILABLE, "jsonschema package not installed")
class TestArtifactManifestSchema(unittest.TestCase):
    """Test JSON Schema validation for Artifact Manifest v1."""

    @classmethod
    def setUpClass(cls):
        """Load JSON schema once for all tests."""
        schema_path = Path(__file__).parent.parent.parent.parent / "docs" / "reference" / "artifact-manifest-v1.0.schema.json"
        with open(schema_path) as f:
            cls.schema = json.load(f)

        cls.examples_dir = Path(__file__).parent.parent.parent.parent / "examples"

    def _validate_manifest(self, manifest_data):
        """Validate manifest against schema."""
        jsonschema.validate(instance=manifest_data, schema=self.schema)

    def test_schema_is_valid(self):
        """Test that the schema itself is valid JSON Schema."""
        # This will raise if schema is invalid
        jsonschema.Draft7Validator.check_schema(self.schema)

    def test_minimal_valid_manifest(self):
        """Test minimal valid manifest."""
        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 100,
                    "local_path": "/path/to/disk.vmdk"
                }
            ]
        }
        self._validate_manifest(manifest)

    def test_missing_version_fails(self):
        """Test that missing manifest_version fails validation."""
        manifest = {
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 100,
                    "local_path": "/path/to/disk.vmdk"
                }
            ]
        }
        with self.assertRaises(jsonschema.ValidationError) as ctx:
            self._validate_manifest(manifest)
        self.assertIn("manifest_version", str(ctx.exception))

    def test_wrong_version_fails(self):
        """Test that unsupported version fails validation."""
        manifest = {
            "manifest_version": "99.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 100,
                    "local_path": "/path/to/disk.vmdk"
                }
            ]
        }
        with self.assertRaises(jsonschema.ValidationError) as ctx:
            self._validate_manifest(manifest)
        self.assertIn("99.0", str(ctx.exception))

    def test_missing_disks_fails(self):
        """Test that missing disks array fails validation."""
        manifest = {
            "manifest_version": "1.0"
        }
        with self.assertRaises(jsonschema.ValidationError) as ctx:
            self._validate_manifest(manifest)
        self.assertIn("disks", str(ctx.exception))

    def test_empty_disks_fails(self):
        """Test that empty disks array fails validation."""
        manifest = {
            "manifest_version": "1.0",
            "disks": []
        }
        with self.assertRaises(jsonschema.ValidationError) as ctx:
            self._validate_manifest(manifest)
        # Should fail minItems validation

    def test_invalid_disk_id_format(self):
        """Test that invalid disk ID format fails validation."""
        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk with spaces!",
                    "source_format": "vmdk",
                    "bytes": 100,
                    "local_path": "/path/to/disk.vmdk"
                }
            ]
        }
        with self.assertRaises(jsonschema.ValidationError):
            self._validate_manifest(manifest)

    def test_invalid_source_format(self):
        """Test that invalid source_format fails validation."""
        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "invalid",
                    "bytes": 100,
                    "local_path": "/path/to/disk.vmdk"
                }
            ]
        }
        with self.assertRaises(jsonschema.ValidationError):
            self._validate_manifest(manifest)

    def test_invalid_checksum_format(self):
        """Test that invalid checksum format fails validation."""
        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 100,
                    "local_path": "/path/to/disk.vmdk",
                    "checksum": "invalid-format"
                }
            ]
        }
        with self.assertRaises(jsonschema.ValidationError):
            self._validate_manifest(manifest)

    def test_valid_checksum_format(self):
        """Test that valid checksum format passes validation."""
        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 100,
                    "local_path": "/path/to/disk.vmdk",
                    "checksum": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
                }
            ]
        }
        self._validate_manifest(manifest)

    def test_invalid_firmware_value(self):
        """Test that invalid firmware value fails validation."""
        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 100,
                    "local_path": "/path/to/disk.vmdk"
                }
            ],
            "vm": {
                "firmware": "invalid"
            }
        }
        with self.assertRaises(jsonschema.ValidationError):
            self._validate_manifest(manifest)

    def test_valid_firmware_values(self):
        """Test that valid firmware values pass validation."""
        for firmware in ["bios", "uefi", "unknown"]:
            manifest = {
                "manifest_version": "1.0",
                "disks": [
                    {
                        "id": "disk-0",
                        "source_format": "vmdk",
                        "bytes": 100,
                        "local_path": "/path/to/disk.vmdk"
                    }
                ],
                "vm": {
                    "firmware": firmware
                }
            }
            self._validate_manifest(manifest)

    def test_reference_manifest_minimal(self):
        """Test that artifact-manifest-minimal.json validates."""
        manifest_path = self.examples_dir / "artifact-manifest-minimal.json"
        if not manifest_path.exists():
            self.skipTest("Reference manifest not found")

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Remove local_path requirement for test (file doesn't exist)
        for disk in manifest["disks"]:
            disk["local_path"] = "/test/path.vmdk"

        self._validate_manifest(manifest)

    def test_reference_manifest_local(self):
        """Test that artifact-manifest-local.json validates."""
        manifest_path = self.examples_dir / "artifact-manifest-local.json"
        if not manifest_path.exists():
            self.skipTest("Reference manifest not found")

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Update paths for test
        for disk in manifest["disks"]:
            disk["local_path"] = "/test/path.vmdk"

        self._validate_manifest(manifest)

    def test_reference_manifest_vsphere(self):
        """Test that artifact-manifest-vsphere.json validates."""
        manifest_path = self.examples_dir / "artifact-manifest-vsphere.json"
        if not manifest_path.exists():
            self.skipTest("Reference manifest not found")

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Update paths for test
        for disk in manifest["disks"]:
            disk["local_path"] = "/test/path.vmdk"

        self._validate_manifest(manifest)

    def test_reference_manifest_multi_disk(self):
        """Test that artifact-manifest-multi-disk.json validates."""
        manifest_path = self.examples_dir / "artifact-manifest-multi-disk.json"
        if not manifest_path.exists():
            self.skipTest("Reference manifest not found")

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Update paths for test
        for disk in manifest["disks"]:
            disk["local_path"] = "/test/path.vmdk"

        self._validate_manifest(manifest)

    def test_invalid_mac_address(self):
        """Test that invalid MAC address format fails validation."""
        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 100,
                    "local_path": "/path/to/disk.vmdk"
                }
            ],
            "nics": [
                {
                    "mac": "invalid-mac"
                }
            ]
        }
        with self.assertRaises(jsonschema.ValidationError):
            self._validate_manifest(manifest)

    def test_valid_mac_address(self):
        """Test that valid MAC address format passes validation."""
        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 100,
                    "local_path": "/path/to/disk.vmdk"
                }
            ],
            "nics": [
                {
                    "mac": "00:50:56:ab:cd:ef"
                }
            ]
        }
        self._validate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
