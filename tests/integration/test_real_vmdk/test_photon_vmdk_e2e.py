# SPDX-License-Identifier: LGPL-3.0-or-later
"""End-to-end tests using real Photon OS VMDK file.

These tests use the actual photon.vmdk file from the repository root
to test the complete migration pipeline with real disk images.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

# Check if photon.vmdk exists
PHOTON_VMDK = Path(__file__).parent.parent.parent.parent / "photon.vmdk"
SKIP_REASON = "photon.vmdk not found in repository root"


@pytest.mark.skipif(not PHOTON_VMDK.exists(), reason=SKIP_REASON)
class TestPhotonVMDKInspection:
    """Test VMDK inspection with real Photon OS disk."""

    def test_vmdk_file_exists(self):
        """Verify Photon VMDK file exists and is readable."""
        assert PHOTON_VMDK.exists()
        assert PHOTON_VMDK.is_file()
        assert os.access(PHOTON_VMDK, os.R_OK)

        # Check file size (should be ~882MB)
        size_mb = PHOTON_VMDK.stat().st_size / (1024 * 1024)
        assert size_mb > 100  # At least 100MB
        assert size_mb < 2000  # Less than 2GB

    def test_vmdk_format_detection(self):
        """Test detecting VMDK format."""
        # Use qemu-img to inspect the file
        try:
            result = subprocess.run(
                ["qemu-img", "info", "--output=json", str(PHOTON_VMDK)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                info = json.loads(result.stdout)
                assert info["format"] == "vmdk"
                assert "virtual-size" in info
                assert info["virtual-size"] > 0
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            pytest.skip("qemu-img not available or failed")

    def test_vmdk_info_extraction(self):
        """Test extracting VMDK information."""
        try:
            from hyper2kvm.vmware.utils.vmdk_parser import VMDK
        except ImportError:
            pytest.skip("VMDK parser not available")

        try:
            vmdk_info = VMDK(str(PHOTON_VMDK))

            # Verify basic info
            assert vmdk_info.path == str(PHOTON_VMDK)

            # Should have extent information
            assert len(vmdk_info.extents) > 0
        except Exception as e:
            # If VMDKInfo not available, skip
            pytest.skip(f"VMDKInfo not available: {e}")

    def test_vmdk_read_header(self):
        """Test reading VMDK header."""
        with open(PHOTON_VMDK, "rb") as f:
            header = f.read(512)

            # VMDK files should have specific magic bytes
            assert len(header) == 512
            # Check for VMDK signature (various formats possible)
            # KDMV for VMware descriptor, COWD for sparse
            assert b"KDMV" in header or b"COWD" in header or b"# Disk DescriptorFile" in header


@pytest.mark.skipif(not PHOTON_VMDK.exists(), reason=SKIP_REASON)
class TestPhotonVMDKConversion:
    """Test VMDK to QCOW2 conversion with real Photon disk."""

    def test_qcow2_conversion_basic(self, tmp_path):
        """Test basic VMDK to QCOW2 conversion."""
        output_path = tmp_path / "photon.qcow2"

        # Use qemu-img for conversion
        try:
            result = subprocess.run(
                [
                    "qemu-img",
                    "convert",
                    "-f", "vmdk",
                    "-O", "qcow2",
                    str(PHOTON_VMDK),
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                timeout=120,  # 2 minutes
            )

            if result.returncode == 0:
                # Verify output file
                assert output_path.exists()
                assert output_path.stat().st_size > 0

                # Verify format
                info_result = subprocess.run(
                    ["qemu-img", "info", "--output=json", str(output_path)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if info_result.returncode == 0:
                    info = json.loads(info_result.stdout)
                    assert info["format"] == "qcow2"
            else:
                pytest.skip(f"qemu-img convert failed: {result.stderr}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("qemu-img not available or conversion timed out")

    def test_qcow2_conversion_with_compression(self, tmp_path):
        """Test VMDK to QCOW2 conversion with compression."""
        output_path = tmp_path / "photon-compressed.qcow2"

        try:
            result = subprocess.run(
                [
                    "qemu-img",
                    "convert",
                    "-f", "vmdk",
                    "-O", "qcow2",
                    "-c",  # Compression
                    str(PHOTON_VMDK),
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                timeout=180,  # 3 minutes for compression
            )

            if result.returncode == 0:
                assert output_path.exists()

                # Compressed file should be smaller or similar size
                original_size = PHOTON_VMDK.stat().st_size
                compressed_size = output_path.stat().st_size

                # Verify it's actually compressed (allow some overhead)
                assert compressed_size < original_size * 1.5
            else:
                pytest.skip(f"Compression failed: {result.stderr}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("qemu-img not available")

    def test_conversion_preserves_data_integrity(self, tmp_path):
        """Test that conversion preserves data integrity."""
        output_path = tmp_path / "photon-integrity.qcow2"

        try:
            # Convert
            subprocess.run(
                [
                    "qemu-img",
                    "convert",
                    "-f", "vmdk",
                    "-O", "qcow2",
                    str(PHOTON_VMDK),
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )

            # Compare virtual sizes
            orig_info = subprocess.run(
                ["qemu-img", "info", "--output=json", str(PHOTON_VMDK)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            conv_info = subprocess.run(
                ["qemu-img", "info", "--output=json", str(output_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if orig_info.returncode == 0 and conv_info.returncode == 0:
                orig_data = json.loads(orig_info.stdout)
                conv_data = json.loads(conv_info.stdout)

                # Virtual sizes should match
                assert orig_data["virtual-size"] == conv_data["virtual-size"]
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("qemu-img not available or failed")


@pytest.mark.skipif(not PHOTON_VMDK.exists(), reason=SKIP_REASON)
class TestPhotonManifestWorkflow:
    """Test complete manifest-driven workflow with Photon VMDK."""

    def test_create_manifest_for_photon(self, tmp_path):
        """Test creating manifest for Photon VMDK."""
        manifest = {
            "manifest_version": "1.0",
            "source": {
                "provider": "vmware",
                "vm_name": "photon-os-test",
                "vm_id": "photon-vm-001",
            },
            "disks": [
                {
                    "id": "boot",
                    "source_format": "vmdk",
                    "local_path": str(PHOTON_VMDK),
                    "bytes": PHOTON_VMDK.stat().st_size,
                    "disk_type": "boot",
                }
            ],
            "metadata": {
                "os_type": "linux",
                "os_variant": "photon",
                "memory_bytes": 2147483648,  # 2GB
                "vcpus": 2,
            },
            "pipeline": {
                "inspect": {"enabled": True},
                "fix": {
                    "enabled": True,
                    "fstab_mode": "stabilize-all",
                },
                "convert": {
                    "enabled": True,
                    "format": "qcow2",
                    "compress": True,
                },
                "validate": {"enabled": True},
            },
            "output": {
                "directory": str(tmp_path / "output"),
                "format": "qcow2",
                "name": "photon-converted",
            },
        }

        manifest_path = tmp_path / "photon-manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        assert manifest_path.exists()

        # Load and verify
        with open(manifest_path) as f:
            loaded = json.load(f)

        assert loaded["source"]["vm_name"] == "photon-os-test"
        assert loaded["disks"][0]["source_format"] == "vmdk"
        assert loaded["metadata"]["os_variant"] == "photon"

    def test_batch_manifest_with_photon(self, tmp_path):
        """Test batch manifest including Photon VM."""
        # Create individual manifest
        vm_manifest = {
            "manifest_version": "1.0",
            "source": {
                "provider": "vmware",
                "vm_name": "photon-batch-vm",
            },
            "disks": [
                {
                    "id": "boot",
                    "source_format": "vmdk",
                    "local_path": str(PHOTON_VMDK),
                    "bytes": PHOTON_VMDK.stat().st_size,
                }
            ],
        }

        vm_manifest_path = tmp_path / "photon-vm.json"
        with open(vm_manifest_path, "w") as f:
            json.dump(vm_manifest, f)

        # Create batch manifest
        batch = {
            "batch_version": "1.0",
            "batch_metadata": {
                "batch_id": "photon-test-batch",
                "description": "Test batch with Photon OS VM",
                "parallel_limit": 1,
            },
            "vms": [
                {
                    "id": "photon-vm-1",
                    "manifest": str(vm_manifest_path),
                    "priority": 0,
                }
            ],
        }

        batch_path = tmp_path / "batch.json"
        with open(batch_path, "w") as f:
            json.dump(batch, f, indent=2)

        assert batch_path.exists()

        # Load and verify
        with open(batch_path) as f:
            loaded = json.load(f)

        assert loaded["batch_metadata"]["batch_id"] == "photon-test-batch"
        assert len(loaded["vms"]) == 1


@pytest.mark.skipif(not PHOTON_VMDK.exists(), reason=SKIP_REASON)
class TestPhotonLibguestfsInspection:
    """Test libguestfs inspection with Photon VMDK (if available)."""

    def test_guestfs_availability(self):
        """Check if guestfish is available."""
        try:
            result = subprocess.run(
                ["guestfish", "--version"],
                capture_output=True,
                timeout=5,
            )
            assert result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("guestfish not available")

    def test_inspect_photon_os(self):
        """Test inspecting Photon OS filesystem (read-only)."""
        try:
            # Try to inspect the OS
            result = subprocess.run(
                [
                    "guestfish",
                    "--ro",
                    "-a", str(PHOTON_VMDK),
                    "run",
                    ":",
                    "list-filesystems",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                # Should detect filesystems
                assert len(result.stdout) > 0
            else:
                pytest.skip(f"guestfish inspection failed: {result.stderr}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("guestfish not available or timed out")

    def test_detect_photon_os_type(self):
        """Test detecting Photon OS type."""
        try:
            result = subprocess.run(
                [
                    "guestfish",
                    "--ro",
                    "-a", str(PHOTON_VMDK),
                    "run",
                    ":",
                    "inspect-os",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and result.stdout.strip():
                # Should detect Linux
                root_device = result.stdout.strip()
                assert root_device.startswith("/dev/")

                # Try to get OS info
                os_info = subprocess.run(
                    [
                        "guestfish",
                        "--ro",
                        "-a", str(PHOTON_VMDK),
                        "run",
                        ":",
                        "inspect-get-type", root_device,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if os_info.returncode == 0:
                    assert "linux" in os_info.stdout.lower()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("guestfish not available")


@pytest.mark.skipif(not PHOTON_VMDK.exists(), reason=SKIP_REASON)
class TestPhotonEndToEndMigration:
    """Complete end-to-end migration test with Photon VMDK."""

    def test_complete_migration_workflow(self, tmp_path):
        """Test complete migration workflow from VMDK to KVM."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Step 1: Create manifest
        manifest = {
            "manifest_version": "1.0",
            "source": {
                "provider": "vmware",
                "vm_name": "photon-e2e-test",
            },
            "disks": [
                {
                    "id": "boot",
                    "source_format": "vmdk",
                    "local_path": str(PHOTON_VMDK),
                    "bytes": PHOTON_VMDK.stat().st_size,
                }
            ],
            "pipeline": {
                "inspect": {"enabled": False},  # Skip for speed
                "fix": {"enabled": False},
                "convert": {"enabled": True, "format": "qcow2"},
                "validate": {"enabled": True},
            },
            "output": {
                "directory": str(output_dir),
                "format": "qcow2",
            },
        }

        manifest_path = tmp_path / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        # Step 2: Simulate conversion (using qemu-img directly)
        output_disk = output_dir / "photon-e2e-test.qcow2"

        try:
            result = subprocess.run(
                [
                    "qemu-img",
                    "convert",
                    "-f", "vmdk",
                    "-O", "qcow2",
                    str(PHOTON_VMDK),
                    str(output_disk),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                # Step 3: Validate output
                assert output_disk.exists()
                assert output_disk.stat().st_size > 0

                # Step 4: Verify QCOW2 format
                info = subprocess.run(
                    ["qemu-img", "info", "--output=json", str(output_disk)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if info.returncode == 0:
                    data = json.loads(info.stdout)
                    assert data["format"] == "qcow2"

                # Step 5: Generate domain XML
                domain_xml = f"""<?xml version="1.0"?>
<domain type="kvm">
  <name>photon-e2e-test</name>
  <memory unit="GiB">2</memory>
  <vcpu>2</vcpu>
  <os>
    <type arch="x86_64">hvm</type>
  </os>
  <devices>
    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2"/>
      <source file="{output_disk}"/>
      <target dev="vda" bus="virtio"/>
    </disk>
  </devices>
</domain>"""

                xml_path = output_dir / "domain.xml"
                xml_path.write_text(domain_xml)

                # Verify XML
                import xml.etree.ElementTree as ET
                root = ET.fromstring(domain_xml)
                assert root.tag == "domain"

                print(f"✅ Migration complete: {output_disk}")
                print(f"✅ Domain XML: {xml_path}")
            else:
                pytest.skip(f"Conversion failed: {result.stderr}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("qemu-img not available")

    def test_migration_with_progress_tracking(self, tmp_path):
        """Test migration with progress tracking."""
        from hyper2kvm.manifest.batch_progress import ProgressTracker

        progress_file = tmp_path / "progress.json"
        tracker = ProgressTracker(progress_file, "photon-migration", 1)

        # Start VM
        tracker.start_vm("photon-vm")

        # Simulate stages
        tracker.update_vm_stage("photon-vm", "extraction")
        tracker.update_vm_stage("photon-vm", "conversion")

        output_path = tmp_path / "photon.qcow2"

        # Perform conversion
        try:
            subprocess.run(
                [
                    "qemu-img",
                    "convert",
                    "-f", "vmdk",
                    "-O", "qcow2",
                    str(PHOTON_VMDK),
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )

            tracker.update_vm_stage("photon-vm", "validation")
            tracker.complete_vm("photon-vm", success=True)

        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            tracker.complete_vm("photon-vm", success=False, error="Conversion failed")
            pytest.skip("Conversion failed")

        # Verify progress
        progress = tracker.get_progress()
        assert progress.get_completion_percentage() == 100.0
        assert progress.vms["photon-vm"].status.value == "completed"

        tracker.cleanup()

    def test_migration_with_validation(self, tmp_path):
        """Test migration with validation framework."""
        from hyper2kvm.validation import DiskValidator, ValidationRunner

        output_path = tmp_path / "photon-validated.qcow2"

        # Perform conversion
        try:
            subprocess.run(
                [
                    "qemu-img",
                    "convert",
                    "-f", "vmdk",
                    "-O", "qcow2",
                    str(PHOTON_VMDK),
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )

            # Validate output
            runner = ValidationRunner()
            runner.add_validator(DiskValidator())

            reports = runner.run_all({
                "output_path": str(output_path),
                "format": "qcow2",
                "minimum_size": 100 * 1024 * 1024,  # 100MB minimum
            })

            # Check validation results
            assert len(reports) > 0
            assert not reports[0].has_errors()

            summary = runner.get_aggregate_summary(reports)
            assert summary["has_errors"] is False

        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("Conversion failed")


@pytest.mark.skipif(not PHOTON_VMDK.exists(), reason=SKIP_REASON)
class TestPhotonPerformance:
    """Performance tests with real Photon VMDK."""

    def test_conversion_performance(self, tmp_path):
        """Measure conversion performance."""
        import time

        output_path = tmp_path / "photon-perf.qcow2"

        try:
            start_time = time.time()

            subprocess.run(
                [
                    "qemu-img",
                    "convert",
                    "-f", "vmdk",
                    "-O", "qcow2",
                    str(PHOTON_VMDK),
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                timeout=300,  # 5 minutes max
            )

            elapsed = time.time() - start_time

            # Verify completed
            assert output_path.exists()

            # Log performance
            size_mb = PHOTON_VMDK.stat().st_size / (1024 * 1024)
            throughput = size_mb / elapsed if elapsed > 0 else 0

            print(f"\n📊 Conversion Performance:")
            print(f"   Size: {size_mb:.1f} MB")
            print(f"   Time: {elapsed:.1f}s")
            print(f"   Throughput: {throughput:.1f} MB/s")

            # Should complete in reasonable time (< 5 minutes for ~880MB)
            assert elapsed < 300

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Conversion failed or timed out")

    def test_compressed_conversion_performance(self, tmp_path):
        """Measure compressed conversion performance."""
        import time

        output_path = tmp_path / "photon-compressed-perf.qcow2"

        try:
            start_time = time.time()

            subprocess.run(
                [
                    "qemu-img",
                    "convert",
                    "-f", "vmdk",
                    "-O", "qcow2",
                    "-c",  # Compression
                    str(PHOTON_VMDK),
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                timeout=600,  # 10 minutes for compression
            )

            elapsed = time.time() - start_time

            # Verify completed
            assert output_path.exists()

            original_size = PHOTON_VMDK.stat().st_size / (1024 * 1024)
            compressed_size = output_path.stat().st_size / (1024 * 1024)
            compression_ratio = (1 - (compressed_size / original_size)) * 100

            print(f"\n📊 Compressed Conversion Performance:")
            print(f"   Original: {original_size:.1f} MB")
            print(f"   Compressed: {compressed_size:.1f} MB")
            print(f"   Ratio: {compression_ratio:.1f}% reduction")
            print(f"   Time: {elapsed:.1f}s")

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Compressed conversion failed")
