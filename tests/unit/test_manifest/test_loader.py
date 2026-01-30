# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for Artifact Manifest v1 loader."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from hyper2kvm.manifest.loader import DiskArtifact, ManifestLoader, ManifestValidationError


class TestDiskArtifact(unittest.TestCase):
    """Test suite for DiskArtifact class."""

    def test_disk_artifact_basic(self):
        """Test basic DiskArtifact creation."""
        data = {
            "id": "test-disk",
            "source_format": "vmdk",
            "bytes": 10737418240,
            "local_path": "/path/to/disk.vmdk",
        }
        disk = DiskArtifact(data)

        self.assertEqual(disk.id, "test-disk")
        self.assertEqual(disk.source_format, "vmdk")
        self.assertEqual(disk.bytes, 10737418240)
        self.assertEqual(disk.local_path, Path("/path/to/disk.vmdk"))
        self.assertIsNone(disk.checksum)
        self.assertEqual(disk.boot_order_hint, 999)  # Default
        self.assertEqual(disk.label, "test-disk")  # Defaults to id
        self.assertEqual(disk.disk_type, "unknown")  # Default

    def test_disk_artifact_with_optionals(self):
        """Test DiskArtifact with all optional fields."""
        data = {
            "id": "boot-disk",
            "source_format": "qcow2",
            "bytes": 107374182400,
            "local_path": "/path/to/boot.qcow2",
            "checksum": "sha256:abc123",
            "boot_order_hint": 0,
            "label": "Boot Disk",
            "disk_type": "boot",
        }
        disk = DiskArtifact(data)

        self.assertEqual(disk.id, "boot-disk")
        self.assertEqual(disk.checksum, "sha256:abc123")
        self.assertEqual(disk.boot_order_hint, 0)
        self.assertEqual(disk.label, "Boot Disk")
        self.assertEqual(disk.disk_type, "boot")

    def test_disk_artifact_repr(self):
        """Test DiskArtifact __repr__."""
        data = {
            "id": "test-disk",
            "source_format": "vmdk",
            "bytes": 100,
            "local_path": "/test",
            "disk_type": "boot",
        }
        disk = DiskArtifact(data)

        repr_str = repr(disk)
        self.assertIn("test-disk", repr_str)
        self.assertIn("boot", repr_str)


class TestManifestLoader(unittest.TestCase):
    """Test suite for ManifestLoader."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = MagicMock()
        self.loader = ManifestLoader(self.logger)
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_test_disk(self, filename, size=1024):
        """Create a test disk file."""
        disk_path = Path(self.temp_dir) / filename
        with open(disk_path, "wb") as f:
            f.write(b"\x00" * size)
        return disk_path

    def _create_manifest(self, content):
        """Create a temporary manifest file."""
        manifest_path = Path(self.temp_dir) / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(content, f)
        return manifest_path

    def test_load_minimal_valid_manifest(self):
        """Test loading minimal valid manifest."""
        disk_path = self._create_test_disk("test.vmdk")

        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                }
            ],
        }
        manifest_path = self._create_manifest(manifest)

        result = self.loader.load(manifest_path)

        self.assertEqual(result["manifest_version"], "1.0")
        self.assertEqual(len(self.loader.get_disks()), 1)
        self.assertEqual(self.loader.get_disks()[0].id, "disk-0")

    def test_load_missing_manifest(self):
        """Test loading non-existent manifest."""
        with self.assertRaises(FileNotFoundError):
            self.loader.load("/nonexistent/manifest.json")

    def test_load_invalid_json(self):
        """Test loading invalid JSON."""
        manifest_path = Path(self.temp_dir) / "bad.json"
        with open(manifest_path, "w") as f:
            f.write("{ invalid json }")

        with self.assertRaises(ManifestValidationError) as ctx:
            self.loader.load(manifest_path)
        self.assertIn("Invalid JSON", str(ctx.exception))

    def test_validate_missing_version(self):
        """Test validation fails when version is missing."""
        disk_path = self._create_test_disk("test.vmdk")

        manifest = {
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                }
            ],
        }
        manifest_path = self._create_manifest(manifest)

        with self.assertRaises(ManifestValidationError) as ctx:
            self.loader.load(manifest_path)
        self.assertIn("manifest_version", str(ctx.exception))

    def test_validate_unsupported_version(self):
        """Test validation fails for unsupported version."""
        disk_path = self._create_test_disk("test.vmdk")

        manifest = {
            "manifest_version": "99.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                }
            ],
        }
        manifest_path = self._create_manifest(manifest)

        with self.assertRaises(ManifestValidationError) as ctx:
            self.loader.load(manifest_path)
        self.assertIn("Unsupported manifest version", str(ctx.exception))
        self.assertIn("99.0", str(ctx.exception))

    def test_validate_missing_disks(self):
        """Test validation fails when disks array is missing."""
        manifest = {"manifest_version": "1.0"}
        manifest_path = self._create_manifest(manifest)

        with self.assertRaises(ManifestValidationError) as ctx:
            self.loader.load(manifest_path)
        self.assertIn("disks", str(ctx.exception).lower())

    def test_validate_empty_disks(self):
        """Test validation fails when disks array is empty."""
        manifest = {
            "manifest_version": "1.0",
            "disks": [],
        }
        manifest_path = self._create_manifest(manifest)

        with self.assertRaises(ManifestValidationError) as ctx:
            self.loader.load(manifest_path)
        self.assertIn("at least one disk", str(ctx.exception))

    def test_validate_disk_missing_required_fields(self):
        """Test validation fails when disk is missing required fields."""
        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    # Missing: source_format, bytes, local_path
                }
            ],
        }
        manifest_path = self._create_manifest(manifest)

        with self.assertRaises(ManifestValidationError) as ctx:
            self.loader.load(manifest_path)
        self.assertIn("required", str(ctx.exception).lower())

    def test_validate_duplicate_disk_ids(self):
        """Test validation fails for duplicate disk IDs."""
        disk_path = self._create_test_disk("test.vmdk")

        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                },
                {
                    "id": "disk-0",  # Duplicate
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                },
            ],
        }
        manifest_path = self._create_manifest(manifest)

        with self.assertRaises(ManifestValidationError) as ctx:
            self.loader.load(manifest_path)
        self.assertIn("Duplicate disk ID", str(ctx.exception))

    def test_validate_invalid_disk_id_format(self):
        """Test validation fails for invalid disk ID format."""
        disk_path = self._create_test_disk("test.vmdk")

        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk with spaces!",  # Invalid
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                }
            ],
        }
        manifest_path = self._create_manifest(manifest)

        with self.assertRaises(ManifestValidationError) as ctx:
            self.loader.load(manifest_path)
        self.assertIn("pattern", str(ctx.exception).lower())

    def test_validate_unsupported_source_format(self):
        """Test validation fails for unsupported source format."""
        disk_path = self._create_test_disk("test.vmdk")

        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "unsupported",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                }
            ],
        }
        manifest_path = self._create_manifest(manifest)

        with self.assertRaises(ManifestValidationError) as ctx:
            self.loader.load(manifest_path)
        self.assertIn("unsupported", str(ctx.exception).lower())
        self.assertIn("source_format", str(ctx.exception).lower())

    def test_validate_disk_file_not_found(self):
        """Test validation fails when disk file doesn't exist."""
        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": "/nonexistent/disk.vmdk",
                }
            ],
        }
        manifest_path = self._create_manifest(manifest)

        with self.assertRaises(ManifestValidationError) as ctx:
            self.loader.load(manifest_path)
        self.assertIn("not found", str(ctx.exception).lower())

    def test_validate_invalid_checksum_format(self):
        """Test validation fails for invalid checksum format."""
        disk_path = self._create_test_disk("test.vmdk")

        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                    "checksum": "invalid-format",
                }
            ],
        }
        manifest_path = self._create_manifest(manifest)

        with self.assertRaises(ManifestValidationError) as ctx:
            self.loader.load(manifest_path)
        self.assertIn("checksum", str(ctx.exception).lower())
        self.assertIn("sha256", str(ctx.exception).lower())

    def test_validate_vm_invalid_firmware(self):
        """Test validation fails for invalid firmware value."""
        disk_path = self._create_test_disk("test.vmdk")

        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                }
            ],
            "vm": {
                "firmware": "invalid",
            },
        }
        manifest_path = self._create_manifest(manifest)

        with self.assertRaises(ManifestValidationError) as ctx:
            self.loader.load(manifest_path)
        self.assertIn("firmware", str(ctx.exception).lower())

    def test_load_multi_disk_manifest(self):
        """Test loading manifest with multiple disks."""
        disk1_path = self._create_test_disk("disk1.vmdk", 1024)
        disk2_path = self._create_test_disk("disk2.vmdk", 2048)

        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "boot-disk",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk1_path),
                    "boot_order_hint": 0,
                    "disk_type": "boot",
                },
                {
                    "id": "data-disk",
                    "source_format": "vmdk",
                    "bytes": 2048,
                    "local_path": str(disk2_path),
                    "boot_order_hint": 1,
                    "disk_type": "data",
                },
            ],
        }
        manifest_path = self._create_manifest(manifest)

        self.loader.load(manifest_path)
        disks = self.loader.get_disks()

        self.assertEqual(len(disks), 2)
        self.assertEqual(disks[0].id, "boot-disk")
        self.assertEqual(disks[1].id, "data-disk")

    def test_get_boot_disk_single(self):
        """Test boot disk identification with single disk."""
        disk_path = self._create_test_disk("test.vmdk")

        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                }
            ],
        }
        manifest_path = self._create_manifest(manifest)

        self.loader.load(manifest_path)
        boot_disk = self.loader.get_boot_disk()

        self.assertEqual(boot_disk.id, "disk-0")

    def test_get_boot_disk_multi_with_hints(self):
        """Test boot disk identification with boot_order_hint."""
        disk1_path = self._create_test_disk("disk1.vmdk", 1024)
        disk2_path = self._create_test_disk("disk2.vmdk", 2048)

        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "data-disk",
                    "source_format": "vmdk",
                    "bytes": 2048,
                    "local_path": str(disk2_path),
                    "boot_order_hint": 1,
                },
                {
                    "id": "boot-disk",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk1_path),
                    "boot_order_hint": 0,
                },
            ],
        }
        manifest_path = self._create_manifest(manifest)

        self.loader.load(manifest_path)
        boot_disk = self.loader.get_boot_disk()

        self.assertEqual(boot_disk.id, "boot-disk")
        self.assertEqual(boot_disk.boot_order_hint, 0)

    def test_verify_checksums_valid(self):
        """Test checksum verification with valid checksum."""
        # Create disk with known content
        disk_path = self._create_test_disk("test.vmdk", 100)
        with open(disk_path, "rb") as f:
            content = f.read()
        actual_hash = hashlib.sha256(content).hexdigest()

        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 100,
                    "local_path": str(disk_path),
                    "checksum": f"sha256:{actual_hash}",
                }
            ],
        }
        manifest_path = self._create_manifest(manifest)

        self.loader.load(manifest_path)
        results = self.loader.verify_checksums()

        self.assertTrue(results["disk-0"])

    def test_verify_checksums_mismatch(self):
        """Test checksum verification with mismatched checksum."""
        disk_path = self._create_test_disk("test.vmdk", 100)
        wrong_hash = "a" * 64  # Wrong hash

        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 100,
                    "local_path": str(disk_path),
                    "checksum": f"sha256:{wrong_hash}",
                }
            ],
        }
        manifest_path = self._create_manifest(manifest)

        self.loader.load(manifest_path)

        with self.assertRaises(ManifestValidationError) as ctx:
            self.loader.verify_checksums()
        self.assertIn("Checksum verification failed", str(ctx.exception))

    def test_verify_checksums_no_checksums(self):
        """Test checksum verification when no checksums present."""
        disk_path = self._create_test_disk("test.vmdk")

        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                }
            ],
        }
        manifest_path = self._create_manifest(manifest)

        self.loader.load(manifest_path)
        results = self.loader.verify_checksums()

        self.assertEqual(len(results), 0)

    def test_get_firmware_default(self):
        """Test firmware hint defaults to bios."""
        disk_path = self._create_test_disk("test.vmdk")

        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                }
            ],
        }
        manifest_path = self._create_manifest(manifest)

        self.loader.load(manifest_path)
        firmware = self.loader.get_firmware()

        self.assertEqual(firmware, "bios")

    def test_get_firmware_uefi(self):
        """Test firmware hint from manifest."""
        disk_path = self._create_test_disk("test.vmdk")

        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                }
            ],
            "vm": {
                "firmware": "uefi",
            },
        }
        manifest_path = self._create_manifest(manifest)

        self.loader.load(manifest_path)
        firmware = self.loader.get_firmware()

        self.assertEqual(firmware, "uefi")

    def test_get_os_hint(self):
        """Test OS hint from manifest."""
        disk_path = self._create_test_disk("test.vmdk")

        manifest = {
            "manifest_version": "1.0",
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                }
            ],
            "vm": {
                "os_hint": "linux",
            },
        }
        manifest_path = self._create_manifest(manifest)

        self.loader.load(manifest_path)
        os_hint = self.loader.get_os_hint()

        self.assertEqual(os_hint, "linux")

    def test_get_source_metadata(self):
        """Test retrieving source metadata."""
        disk_path = self._create_test_disk("test.vmdk")

        manifest = {
            "manifest_version": "1.0",
            "source": {
                "provider": "vsphere",
                "vm_id": "vm-1234",
                "vm_name": "test-vm",
            },
            "disks": [
                {
                    "id": "disk-0",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                }
            ],
        }
        manifest_path = self._create_manifest(manifest)

        self.loader.load(manifest_path)
        source_meta = self.loader.get_source_metadata()

        self.assertEqual(source_meta["provider"], "vsphere")
        self.assertEqual(source_meta["vm_id"], "vm-1234")
        self.assertEqual(source_meta["vm_name"], "test-vm")


if __name__ == "__main__":
    unittest.main()
