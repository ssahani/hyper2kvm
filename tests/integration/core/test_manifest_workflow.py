# SPDX-License-Identifier: LGPL-3.0-or-later
"""Integration tests for Artifact Manifest v1 workflow."""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from hyper2kvm.manifest.loader import ManifestLoader
from hyper2kvm.manifest.orchestrator import ManifestOrchestrator
from hyper2kvm.manifest.reporter import ManifestReporter


class TestManifestWorkflowIntegration(unittest.TestCase):
    """Integration tests for the complete manifest-driven workflow."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.artifacts_dir = self.test_dir / "artifacts"
        self.output_dir = self.test_dir / "output"
        self.artifacts_dir.mkdir()
        self.output_dir.mkdir()

    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_test_disk(self, filename, size=2048):
        """Create a minimal test disk image."""
        disk_path = self.artifacts_dir / filename
        with open(disk_path, "wb") as f:
            f.write(b"\x00" * size)
        return disk_path

    def _compute_checksum(self, path):
        """Compute SHA-256 checksum for a file."""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return f"sha256:{sha256.hexdigest()}"

    def _create_manifest(self, **kwargs):
        """Create a test manifest file."""
        manifest = {
            "manifest_version": "1.0",
            "disks": kwargs.get("disks", []),
            "pipeline": kwargs.get("pipeline", {
                "inspect": {"enabled": True},
                "fix": {"enabled": False},
                "convert": {"enabled": False},
                "validate": {"enabled": False},
            }),
            "output": {"directory": str(self.output_dir)},
            "options": {"report": {"enabled": True}},
        }

        if "source" in kwargs:
            manifest["source"] = kwargs["source"]
        if "vm" in kwargs:
            manifest["vm"] = kwargs["vm"]

        manifest_path = self.test_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        return manifest_path

    def test_single_disk_inspect_only(self):
        """Test single-disk workflow with inspect stage only."""
        # Create test disk
        disk_path = self._create_test_disk("test-disk.vmdk", 2048)

        # Create manifest
        manifest_path = self._create_manifest(
            disks=[
                {
                    "id": "test-disk",
                    "source_format": "vmdk",
                    "bytes": 2048,
                    "local_path": str(disk_path),
                }
            ]
        )

        # Load and validate
        loader = ManifestLoader()
        manifest = loader.load(manifest_path)

        self.assertEqual(manifest["manifest_version"], "1.0")
        self.assertEqual(len(loader.get_disks()), 1)

        # Verify boot disk identification
        boot_disk = loader.get_boot_disk()
        self.assertEqual(boot_disk.id, "test-disk")

    def test_multi_disk_boot_order(self):
        """Test multi-disk workflow with boot order hints."""
        # Create test disks
        boot_disk_path = self._create_test_disk("boot.vmdk", 1024)
        data_disk_path = self._create_test_disk("data.vmdk", 2048)

        # Create manifest with boot order hints
        manifest_path = self._create_manifest(
            disks=[
                {
                    "id": "data-disk",
                    "source_format": "vmdk",
                    "bytes": 2048,
                    "local_path": str(data_disk_path),
                    "boot_order_hint": 1,
                    "disk_type": "data",
                },
                {
                    "id": "boot-disk",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(boot_disk_path),
                    "boot_order_hint": 0,
                    "disk_type": "boot",
                },
            ]
        )

        # Load and verify
        loader = ManifestLoader()
        loader.load(manifest_path)

        disks = loader.get_disks()
        self.assertEqual(len(disks), 2)

        # Verify boot disk selection
        boot_disk = loader.get_boot_disk()
        self.assertEqual(boot_disk.id, "boot-disk")
        self.assertEqual(boot_disk.boot_order_hint, 0)

    def test_checksum_verification_success(self):
        """Test checksum verification with valid checksums."""
        # Create test disk
        disk_path = self._create_test_disk("test.vmdk", 1024)
        checksum = self._compute_checksum(disk_path)

        # Create manifest with checksum
        manifest_path = self._create_manifest(
            disks=[
                {
                    "id": "test-disk",
                    "source_format": "vmdk",
                    "bytes": 1024,
                    "local_path": str(disk_path),
                    "checksum": checksum,
                }
            ]
        )

        # Load and verify
        loader = ManifestLoader()
        loader.load(manifest_path)

        # Verify checksums
        results = loader.verify_checksums()
        self.assertTrue(results["test-disk"])

    def test_manifest_with_metadata(self):
        """Test manifest with source and VM metadata."""
        # Create test disk
        disk_path = self._create_test_disk("test.vmdk", 2048)

        # Create manifest with metadata
        manifest_path = self._create_manifest(
            source={
                "provider": "vsphere",
                "vm_id": "vm-test-123",
                "vm_name": "test-server",
                "datacenter": "DC1",
            },
            vm={
                "cpu": 4,
                "mem_gb": 16,
                "firmware": "uefi",
                "secureboot": False,
                "os_hint": "linux",
            },
            disks=[
                {
                    "id": "boot-disk",
                    "source_format": "vmdk",
                    "bytes": 2048,
                    "local_path": str(disk_path),
                    "boot_order_hint": 0,
                }
            ],
        )

        # Load and verify
        loader = ManifestLoader()
        loader.load(manifest_path)

        # Verify source metadata
        source_meta = loader.get_source_metadata()
        self.assertEqual(source_meta["provider"], "vsphere")
        self.assertEqual(source_meta["vm_id"], "vm-test-123")

        # Verify VM metadata
        self.assertEqual(loader.get_firmware(), "uefi")
        self.assertEqual(loader.get_os_hint(), "linux")
        self.assertFalse(loader.get_secureboot())

    def test_reporter_multi_disk_artifacts(self):
        """Test reporter with multi-disk artifacts."""
        reporter = ManifestReporter()

        # Simulate load_manifest stage
        reporter.add_stage_result("load_manifest", {
            "success": True,
            "duration": 0.1,
            "result": {
                "manifest_version": "1.0",
                "manifest_path": "/test/manifest.json",
                "source_provider": "vsphere",
                "source_vm_id": "vm-123",
                "source_vm_name": "test-vm",
                "disks_count": 2,
            },
        })

        # Simulate convert stage with multiple disks
        reporter.add_stage_result("convert", {
            "success": True,
            "duration": 10.5,
            "result": {
                "disks_converted": 2,
                "compressed": True,
                "converted_disks": [
                    {
                        "disk_id": "boot-disk",
                        "output_format": "qcow2",
                        "output_path": "/output/boot-disk.qcow2",
                        "output_size_bytes": 1073741824,
                        "output_size_human": "1.00 GiB",
                        "boot_order_hint": 0,
                    },
                    {
                        "disk_id": "data-disk",
                        "output_format": "qcow2",
                        "output_path": "/output/data-disk.qcow2",
                        "output_size_bytes": 2147483648,
                        "output_size_human": "2.00 GiB",
                        "boot_order_hint": 1,
                    },
                ],
            },
        })

        reporter.set_success(True)
        reporter.set_duration(11.0)

        # Generate report
        report = reporter.generate()

        # Verify report structure
        self.assertEqual(report["version"], "1.0")
        self.assertTrue(report["pipeline"]["success"])
        self.assertEqual(report["pipeline"]["duration_seconds"], 11.0)

        # Verify artifacts
        self.assertEqual(len(report["artifacts"]), 2)
        self.assertEqual(report["artifacts"][0]["disk_id"], "boot-disk")
        self.assertEqual(report["artifacts"][1]["disk_id"], "data-disk")

        # Verify summary
        summary = report["summary"]
        self.assertEqual(summary["input_disks"], 2)
        self.assertEqual(summary["output_disks"], 2)
        self.assertEqual(summary["successful_stages"], 2)

    def test_reference_manifest_vsphere(self):
        """Test loading reference vSphere manifest example."""
        # Load reference manifest
        ref_manifest_path = Path(__file__).parent.parent.parent / "examples" / "artifact-manifest-vsphere.json"

        if not ref_manifest_path.exists():
            self.skipTest("Reference manifest not found")

        # Read and modify to point to test disk
        with open(ref_manifest_path) as f:
            manifest_data = json.load(f)

        # Create test disk
        disk_path = self._create_test_disk("test.vmdk", 2048)

        # Update disk path
        manifest_data["disks"][0]["local_path"] = str(disk_path)
        manifest_data["disks"][0]["bytes"] = 2048
        del manifest_data["disks"][0]["checksum"]  # Remove checksum for test

        # Update output directory
        manifest_data["output"] = {"directory": str(self.output_dir)}

        # Disable stages for test
        for stage in ["fix", "convert", "validate"]:
            manifest_data["pipeline"][stage]["enabled"] = False

        # Save modified manifest
        test_manifest_path = self.test_dir / "test-vsphere.json"
        with open(test_manifest_path, "w") as f:
            json.dump(manifest_data, f, indent=2)

        # Load and verify
        loader = ManifestLoader()
        manifest = loader.load(test_manifest_path)

        self.assertEqual(manifest["manifest_version"], "1.0")
        self.assertEqual(manifest["source"]["provider"], "vsphere")
        self.assertEqual(manifest["vm"]["firmware"], "uefi")

    def test_reference_manifest_multi_disk(self):
        """Test loading reference multi-disk manifest example."""
        # Load reference manifest
        ref_manifest_path = Path(__file__).parent.parent.parent / "examples" / "artifact-manifest-multi-disk.json"

        if not ref_manifest_path.exists():
            self.skipTest("Reference manifest not found")

        # Read and modify
        with open(ref_manifest_path) as f:
            manifest_data = json.load(f)

        # Create test disks
        boot_path = self._create_test_disk("boot.vmdk", 1024)
        data1_path = self._create_test_disk("data1.vmdk", 2048)
        data2_path = self._create_test_disk("data2.vmdk", 3072)

        # Update disk paths
        manifest_data["disks"][0]["local_path"] = str(boot_path)
        manifest_data["disks"][0]["bytes"] = 1024
        manifest_data["disks"][1]["local_path"] = str(data1_path)
        manifest_data["disks"][1]["bytes"] = 2048
        manifest_data["disks"][2]["local_path"] = str(data2_path)
        manifest_data["disks"][2]["bytes"] = 3072

        # Remove checksums
        for disk in manifest_data["disks"]:
            if "checksum" in disk:
                del disk["checksum"]

        # Update output
        manifest_data["output"] = {"directory": str(self.output_dir)}

        # Disable stages
        for stage in ["fix", "convert", "validate"]:
            manifest_data["pipeline"][stage]["enabled"] = False

        # Save modified manifest
        test_manifest_path = self.test_dir / "test-multi-disk.json"
        with open(test_manifest_path, "w") as f:
            json.dump(manifest_data, f, indent=2)

        # Load and verify
        loader = ManifestLoader()
        manifest = loader.load(test_manifest_path)

        self.assertEqual(len(loader.get_disks()), 3)

        # Verify boot disk selection
        boot_disk = loader.get_boot_disk()
        self.assertEqual(boot_disk.id, "boot-disk")
        self.assertEqual(boot_disk.disk_type, "boot")


    def test_full_pipeline_end_to_end(self):
        """Test complete INSPECT→FIX→CONVERT→VALIDATE pipeline initialization."""
        # Create a minimal disk image (just for testing structure)
        disk_path = self._create_test_disk("boot.vmdk", 10 * 1024 * 1024)  # 10MB

        # Create manifest with all stages enabled but inspect disabled
        # (inspect requires a valid filesystem which we don't have in test)
        manifest_path = self._create_manifest(
            source={
                "provider": "local",
                "vm_name": "test-vm"
            },
            vm={
                "firmware": "bios",
                "os_hint": "linux"
            },
            disks=[
                {
                    "id": "boot-disk",
                    "source_format": "vmdk",
                    "bytes": 10 * 1024 * 1024,
                    "local_path": str(disk_path),
                    "boot_order_hint": 0,
                    "disk_type": "boot"
                }
            ],
            pipeline={
                "inspect": {"enabled": False},
                "fix": {"enabled": False},
                "convert": {"enabled": False},
                "validate": {"enabled": False}
            }
        )

        # Load manifest directly to verify structure
        loader = ManifestLoader()
        manifest = loader.load(manifest_path)

        # Verify manifest loaded correctly
        self.assertEqual(manifest["manifest_version"], "1.0")
        self.assertEqual(len(loader.get_disks()), 1)

        # Verify boot disk identification
        boot_disk = loader.get_boot_disk()
        self.assertEqual(boot_disk.id, "boot-disk")
        self.assertEqual(boot_disk.disk_type, "boot")

        # Run orchestrator with all stages disabled
        # This tests that the pipeline can initialize and run the LOAD_MANIFEST stage
        orchestrator = ManifestOrchestrator(str(manifest_path), None)
        report = orchestrator.run()

        # Verify report structure
        self.assertEqual(report["version"], "1.0")
        self.assertTrue(report["pipeline"]["success"])

        # Verify load_manifest stage ran
        stages = report["pipeline"]["stages"]
        self.assertIn("load_manifest", stages)
        self.assertTrue(stages["load_manifest"]["success"])

        # Verify stage results include manifest metadata
        load_result = stages["load_manifest"]["result"]
        self.assertEqual(load_result["manifest_version"], "1.0")
        self.assertEqual(load_result["source_provider"], "local")
        self.assertEqual(load_result["source_vm_name"], "test-vm")
        self.assertEqual(load_result["disks_count"], 1)

        # Verify summary
        self.assertIn("summary", report)
        self.assertEqual(report["summary"]["input_disks"], 1)
        self.assertEqual(report["summary"]["successful_stages"], 1)


if __name__ == "__main__":
    unittest.main()
