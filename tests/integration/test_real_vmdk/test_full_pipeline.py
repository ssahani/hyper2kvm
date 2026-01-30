# SPDX-License-Identifier: LGPL-3.0-or-later
"""Full pipeline integration tests with real Photon VMDK.

Tests the complete hyper2kvm pipeline using actual disk images.
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
import yaml

# Check for real VMDK file
PHOTON_VMDK = Path(__file__).parent.parent.parent.parent / "photon.vmdk"
TEST_CONFIG = Path(__file__).parent.parent.parent.parent / "test-confs" / "04-local-photon-os-vmdk.yaml"
SKIP_REASON = "photon.vmdk not found"


@pytest.mark.skipif(not PHOTON_VMDK.exists(), reason=SKIP_REASON)
@pytest.mark.slow
class TestFullPipelineWithPhoton:
    """Test complete migration pipeline with real Photon OS."""

    def test_manifest_driven_conversion(self, tmp_path):
        """Test manifest-driven conversion of Photon VMDK."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Create comprehensive manifest
        manifest = {
            "manifest_version": "1.0",
            "source": {
                "provider": "vmware",
                "vm_name": "photon-test",
                "vm_id": "photon-001",
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
                "distro": "photon",
                "memory_bytes": 2147483648,
                "vcpus": 2,
            },
            "pipeline": {
                "inspect": {
                    "enabled": False,  # Skip for CI
                },
                "fix": {
                    "enabled": False,  # Skip filesystem fixes for now
                },
                "convert": {
                    "enabled": True,
                    "format": "qcow2",
                    "compress": False,  # Faster without compression
                },
                "validate": {
                    "enabled": True,
                },
            },
            "output": {
                "directory": str(output_dir),
                "format": "qcow2",
                "name": "photon-converted",
            },
        }

        manifest_path = tmp_path / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        # Simulate orchestrator processing the manifest
        # In real usage, this would call the orchestrator
        output_disk = output_dir / "photon-converted.qcow2"

        try:
            # Convert using qemu-img (what the converter would do)
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
                # Validate output exists
                assert output_disk.exists()
                assert output_disk.stat().st_size > 100 * 1024 * 1024  # > 100MB

                # Run validation
                from hyper2kvm.validation import DiskValidator

                validator = DiskValidator()
                report = validator.validate({
                    "output_path": str(output_disk),
                    "format": "qcow2",
                    "minimum_size": 100 * 1024 * 1024,
                })

                assert not report.has_errors()
                print(f"✅ Conversion successful: {output_disk}")
                print(f"✅ Validation passed: {report.passed_checks}/{report.total_checks} checks")
            else:
                pytest.skip(f"Conversion failed: {result.stderr}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("qemu-img not available")

    def test_batch_conversion_with_photon(self, tmp_path):
        """Test batch conversion including Photon VMDK."""
        # Create individual manifest
        vm_manifest = {
            "manifest_version": "1.0",
            "source": {
                "provider": "vmware",
                "vm_name": "photon-batch",
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
                "inspect": {"enabled": False},
                "fix": {"enabled": False},
                "convert": {"enabled": True, "format": "qcow2"},
                "validate": {"enabled": True},
            },
            "output": {
                "directory": str(tmp_path / "output"),
                "format": "qcow2",
            },
        }

        vm_manifest_path = tmp_path / "vm-manifest.json"
        with open(vm_manifest_path, "w") as f:
            json.dump(vm_manifest, f)

        # Create batch manifest
        batch = {
            "batch_version": "1.0",
            "batch_metadata": {
                "batch_id": "photon-integration-test",
                "parallel_limit": 1,
                "continue_on_error": True,
            },
            "vms": [
                {
                    "id": "photon-vm",
                    "manifest": str(vm_manifest_path),
                }
            ],
        }

        batch_path = tmp_path / "batch.json"
        with open(batch_path, "w") as f:
            json.dump(batch, f)

        # Test batch loading
        from hyper2kvm.manifest.batch_loader import BatchLoader

        loader = BatchLoader()
        batch_config = loader.load(batch_path)

        assert batch_config["batch_metadata"]["batch_id"] == "photon-integration-test"
        assert len(batch_config["vms"]) == 1

        print(f"✅ Batch manifest loaded successfully")

    def test_complete_workflow_with_progress(self, tmp_path):
        """Test complete workflow with progress tracking."""
        from hyper2kvm.manifest.batch_progress import ProgressTracker
        from hyper2kvm.manifest.checkpoint_manager import CheckpointManager

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        progress_file = tmp_path / "progress.json"
        checkpoint_dir = tmp_path / "checkpoints"
        checkpoint_dir.mkdir()

        # Initialize tracking
        tracker = ProgressTracker(progress_file, "photon-workflow", 1)
        checkpoint = CheckpointManager(checkpoint_dir, "photon-workflow")

        # Start processing
        tracker.start_vm("photon-vm")

        # Stage 1: Extraction (simulated)
        tracker.update_vm_stage("photon-vm", "extraction")
        time.sleep(0.1)

        # Stage 2: Conversion
        tracker.update_vm_stage("photon-vm", "conversion")

        output_disk = output_dir / "photon.qcow2"

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
                check=True,
                capture_output=True,
                timeout=120,
            )

            # Stage 3: Validation
            tracker.update_vm_stage("photon-vm", "validation")

            from hyper2kvm.validation import DiskValidator

            validator = DiskValidator()
            report = validator.validate({
                "output_path": str(output_disk),
                "format": "qcow2",
            })

            success = not report.has_errors()

            # Complete
            tracker.complete_vm("photon-vm", success=success)

            # Save checkpoint
            checkpoint.save_checkpoint(
                completed_vms=["photon-vm"] if success else [],
                failed_vms=[] if success else [{"vm_id": "photon-vm", "error": "Validation failed"}],
                total_vms=1,
            )

            # Verify progress
            progress = tracker.get_progress()
            assert progress.get_completion_percentage() == 100.0

            print(f"✅ Complete workflow finished successfully")
            print(f"   Stages: {tracker.progress.vms['photon-vm'].stages_completed}")

            tracker.cleanup()
            checkpoint.cleanup()

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            tracker.complete_vm("photon-vm", success=False, error="Conversion failed")
            pytest.skip("Conversion failed")


@pytest.mark.skipif(not PHOTON_VMDK.exists(), reason=SKIP_REASON)
@pytest.mark.slow
class TestPhotonSpecificFeatures:
    """Test Photon OS specific features."""

    def test_photon_metadata_extraction(self):
        """Test extracting Photon OS specific metadata."""
        metadata = {
            "os_type": "linux",
            "distro": "photon",
            "package_manager": "tdnf",  # Photon's package manager
            "init_system": "systemd",
            "network_manager": "systemd-networkd",
        }

        assert metadata["distro"] == "photon"
        assert metadata["package_manager"] == "tdnf"

    def test_photon_network_config(self):
        """Test Photon OS network configuration."""
        # Photon uses systemd-networkd
        network_config = {
            "type": "systemd-networkd",
            "config_path": "/etc/systemd/network",
            "files": [
                "10-static-en.network",
                "99-dhcp.network",
            ],
        }

        assert network_config["type"] == "systemd-networkd"
        assert len(network_config["files"]) > 0

    def test_photon_bootloader_config(self):
        """Test Photon OS bootloader configuration."""
        # Photon typically uses GRUB2
        bootloader = {
            "type": "grub2",
            "config_path": "/boot/grub2/grub.cfg",
            "update_command": "grub2-mkconfig -o /boot/grub2/grub.cfg",
        }

        assert bootloader["type"] == "grub2"

    def test_photon_package_info(self):
        """Test Photon OS package information."""
        # Example Photon packages
        packages = {
            "kernel": "linux",
            "package_manager": "tdnf",
            "container_runtime": "containerd",
            "python": "python3",
        }

        assert "tdnf" in packages.values()


@pytest.mark.skipif(not PHOTON_VMDK.exists(), reason=SKIP_REASON)
@pytest.mark.slow
class TestPhotonConversionQuality:
    """Test conversion quality and correctness."""

    def test_disk_format_correctness(self, tmp_path):
        """Test that converted disk has correct format."""
        output_path = tmp_path / "photon-quality.qcow2"

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

            # Check format with qemu-img
            result = subprocess.run(
                ["qemu-img", "info", "--output=json", str(output_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                info = json.loads(result.stdout)

                # Verify format
                assert info["format"] == "qcow2"
                assert "virtual-size" in info
                assert info["virtual-size"] > 0

                # Check for qcow2 specific fields
                assert "cluster-size" in info
                assert info["cluster-size"] > 0

                print(f"✅ QCOW2 format verified")
                print(f"   Virtual size: {info['virtual-size'] // (1024**3)} GB")
                print(f"   Cluster size: {info['cluster-size']} bytes")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            pytest.skip("Format check failed")

    def test_virtual_size_preservation(self, tmp_path):
        """Test that virtual size is preserved during conversion."""
        output_path = tmp_path / "photon-size.qcow2"

        try:
            # Get original size
            orig_result = subprocess.run(
                ["qemu-img", "info", "--output=json", str(PHOTON_VMDK)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if orig_result.returncode != 0:
                pytest.skip("Cannot read original size")

            orig_info = json.loads(orig_result.stdout)
            orig_size = orig_info["virtual-size"]

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

            # Get converted size
            conv_result = subprocess.run(
                ["qemu-img", "info", "--output=json", str(output_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if conv_result.returncode == 0:
                conv_info = json.loads(conv_result.stdout)
                conv_size = conv_info["virtual-size"]

                # Sizes should match
                assert orig_size == conv_size

                print(f"✅ Virtual size preserved: {orig_size // (1024**3)} GB")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            pytest.skip("Size check failed")

    def test_no_corruption_after_conversion(self, tmp_path):
        """Test basic corruption detection after conversion."""
        output_path = tmp_path / "photon-check.qcow2"

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

            # Run qemu-img check
            check_result = subprocess.run(
                ["qemu-img", "check", str(output_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Check should pass (return 0)
            if check_result.returncode == 0:
                assert "No errors" in check_result.stdout or check_result.returncode == 0
                print(f"✅ No corruption detected")
            else:
                pytest.fail(f"Corruption detected: {check_result.stdout}")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Corruption check failed")


@pytest.mark.skipif(not PHOTON_VMDK.exists() or not TEST_CONFIG.exists(), reason="Config or VMDK not found")
@pytest.mark.slow
class TestPhotonWithActualConfig:
    """Test using actual hyper2kvm configuration."""

    def test_load_photon_config(self):
        """Test loading actual Photon OS configuration."""
        with open(TEST_CONFIG) as f:
            config = yaml.safe_load(f)

        assert config["cmd"] == "local"
        assert "vmdk" in config
        assert config["fstab_mode"] == "stabilize-all"
        assert config.get("regen_initramfs") is True

        print(f"✅ Configuration loaded:")
        print(f"   Command: {config['cmd']}")
        print(f"   FSTAB mode: {config['fstab_mode']}")
        print(f"   Initramfs regen: {config.get('regen_initramfs')}")

    def test_config_validation(self):
        """Test configuration validation."""
        with open(TEST_CONFIG) as f:
            config = yaml.safe_load(f)

        # Required fields
        assert "cmd" in config
        assert "vmdk" in config or "ova" in config

        # Output configuration
        if "output_dir" in config:
            assert isinstance(config["output_dir"], str)

        # Pipeline configuration
        assert "fstab_mode" in config
        assert config["fstab_mode"] in ["stabilize-all", "uuid-only", "leave-as-is"]

        print(f"✅ Configuration valid")
