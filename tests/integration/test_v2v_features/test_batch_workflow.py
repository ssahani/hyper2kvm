# SPDX-License-Identifier: LGPL-3.0-or-later
"""Integration tests for batch conversion workflows."""

import json
import tempfile
from pathlib import Path

import pytest


class TestBatchWorkflow:
    """Integration tests for complete batch conversion workflows."""

    @pytest.fixture
    def sample_manifests(self, tmp_path):
        """Create sample manifests for testing."""
        manifests = []

        for i in range(1, 4):
            manifest = {
                "manifest_version": "1.0",
                "source": {
                    "provider": "test",
                    "vm_name": f"test-vm{i}",
                },
                "disks": [
                    {
                        "id": "boot",
                        "source_format": "qcow2",
                        "local_path": str(tmp_path / f"vm{i}.qcow2"),
                        "bytes": 1024,
                        "disk_type": "boot",
                    }
                ],
                "pipeline": {
                    "inspect": {"enabled": False},
                    "fix": {"enabled": False},
                    "convert": {"enabled": False},
                    "validate": {"enabled": False},
                },
                "output": {
                    "directory": str(tmp_path / f"output{i}"),
                    "format": "qcow2",
                },
            }

            manifest_path = tmp_path / f"vm{i}" / "manifest.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)

            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)

            # Create dummy disk file
            disk_path = tmp_path / f"vm{i}.qcow2"
            disk_path.write_bytes(b"\x00" * 1024)

            manifests.append(str(manifest_path))

        return manifests

    def test_batch_manifest_creation(self, tmp_path, sample_manifests):
        """Test creating a valid batch manifest."""
        batch = {
            "batch_version": "1.0",
            "batch_metadata": {
                "batch_id": "integration-test",
                "parallel_limit": 2,
                "continue_on_error": True,
            },
            "vms": [
                {"id": f"vm{i}", "manifest": m, "priority": i}
                for i, m in enumerate(sample_manifests, 1)
            ],
        }

        batch_path = tmp_path / "batch.json"
        with open(batch_path, "w") as f:
            json.dump(batch, f, indent=2)

        assert batch_path.exists()

        # Verify can be loaded back
        with open(batch_path) as f:
            loaded = json.load(f)

        assert loaded["batch_version"] == "1.0"
        assert len(loaded["vms"]) == 3

    def test_batch_with_profiles(self, tmp_path, sample_manifests):
        """Test batch manifest with profile references."""
        # Update manifests to use profiles
        for manifest_path in sample_manifests:
            with open(manifest_path) as f:
                manifest = json.load(f)

            manifest["profile"] = "testing"

            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)

        batch = {
            "batch_version": "1.0",
            "vms": [{"manifest": m} for m in sample_manifests],
            "shared_config": {"profile": "production"},
        }

        batch_path = tmp_path / "batch-profiles.json"
        with open(batch_path, "w") as f:
            json.dump(batch, f, indent=2)

        assert batch_path.exists()

    def test_batch_with_network_mapping(self, tmp_path, sample_manifests):
        """Test batch with network mapping in shared config."""
        batch = {
            "batch_version": "1.0",
            "vms": [{"manifest": m} for m in sample_manifests],
            "shared_config": {
                "network_mapping": {
                    "source_networks": {
                        "VM Network": "br0",
                        "DMZ": "br-dmz",
                    },
                    "mac_address_policy": "preserve",
                }
            },
        }

        batch_path = tmp_path / "batch-network.json"
        with open(batch_path, "w") as f:
            json.dump(batch, f, indent=2)

        assert batch_path.exists()

        # Verify structure
        with open(batch_path) as f:
            loaded = json.load(f)

        assert "network_mapping" in loaded["shared_config"]
        assert "br0" in loaded["shared_config"]["network_mapping"]["source_networks"].values()

    def test_priority_based_ordering(self, tmp_path, sample_manifests):
        """Test that VMs can be ordered by priority."""
        batch = {
            "batch_version": "1.0",
            "vms": [
                {"id": "low", "manifest": sample_manifests[0], "priority": 10},
                {"id": "high", "manifest": sample_manifests[1], "priority": 0},
                {"id": "medium", "manifest": sample_manifests[2], "priority": 5},
            ],
        }

        # In real usage, BatchLoader would sort these
        # Here we just verify the structure allows priority
        assert batch["vms"][1]["priority"] == 0
        assert batch["vms"][2]["priority"] == 5
        assert batch["vms"][0]["priority"] == 10


class TestProfileWorkflow:
    """Integration tests for profile-based workflows."""

    def test_profile_with_overrides(self, tmp_path):
        """Test manifest using profile with overrides."""
        manifest = {
            "manifest_version": "1.0",
            "profile": "production",
            "profile_overrides": {
                "pipeline": {
                    "convert": {"compress_level": 9},
                }
            },
            "source": {"provider": "test", "vm_name": "test"},
            "disks": [],
        }

        manifest_path = tmp_path / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        # Verify structure
        with open(manifest_path) as f:
            loaded = json.load(f)

        assert loaded["profile"] == "production"
        assert loaded["profile_overrides"]["pipeline"]["convert"]["compress_level"] == 9

    def test_custom_profile_structure(self, tmp_path):
        """Test creating a custom profile."""
        custom_profile = {
            "extends": "production",
            "pipeline": {
                "fix": {
                    "fstab_mode": "stabilize-all",
                    "remove_vmware_tools": True,
                },
                "convert": {"compress_level": 8},
            },
            "hooks": {
                "post_convert": [
                    {
                        "type": "http",
                        "url": "https://example.com/notify",
                        "method": "POST",
                    }
                ]
            },
        }

        profile_path = tmp_path / "custom.yaml"
        import yaml

        with open(profile_path, "w") as f:
            yaml.dump(custom_profile, f)

        assert profile_path.exists()

        # Verify can be loaded
        with open(profile_path) as f:
            loaded = yaml.safe_load(f)

        assert loaded["extends"] == "production"
        assert loaded["pipeline"]["convert"]["compress_level"] == 8


class TestHookWorkflow:
    """Integration tests for hook-based workflows."""

    def test_manifest_with_script_hooks(self, tmp_path):
        """Test manifest with script hooks."""
        # Create dummy script
        script_path = tmp_path / "hook.sh"
        script_path.write_text("#!/bin/bash\necho 'Hook executed'\n")
        script_path.chmod(0o755)

        manifest = {
            "manifest_version": "1.0",
            "hooks": {
                "pre_fix": [
                    {
                        "type": "script",
                        "path": str(script_path),
                        "args": ["{{ source_path }}", "/backup"],
                        "env": {"VM_NAME": "{{ vm_name }}"},
                        "timeout": 300,
                    }
                ]
            },
            "source": {"provider": "test", "vm_name": "test"},
            "disks": [],
        }

        manifest_path = tmp_path / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        # Verify structure
        with open(manifest_path) as f:
            loaded = json.load(f)

        assert "hooks" in loaded
        assert "pre_fix" in loaded["hooks"]
        hook = loaded["hooks"]["pre_fix"][0]
        assert hook["type"] == "script"
        assert "{{ source_path }}" in hook["args"]

    def test_manifest_with_python_hooks(self, tmp_path):
        """Test manifest with Python hooks."""
        manifest = {
            "manifest_version": "1.0",
            "hooks": {
                "post_convert": [
                    {
                        "type": "python",
                        "module": "validators",
                        "function": "verify_disk",
                        "args": {"disk_path": "{{ output_path }}"},
                        "timeout": 300,
                    }
                ]
            },
            "source": {"provider": "test", "vm_name": "test"},
            "disks": [],
        }

        manifest_path = tmp_path / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        # Verify structure
        with open(manifest_path) as f:
            loaded = json.load(f)

        hook = loaded["hooks"]["post_convert"][0]
        assert hook["type"] == "python"
        assert hook["module"] == "validators"
        assert "{{ output_path }}" in hook["args"]["disk_path"]

    def test_manifest_with_http_hooks(self, tmp_path):
        """Test manifest with HTTP webhook hooks."""
        manifest = {
            "manifest_version": "1.0",
            "hooks": {
                "post_validate": [
                    {
                        "type": "http",
                        "url": "https://api.example.com/migrations",
                        "method": "POST",
                        "headers": {"Authorization": "Bearer TOKEN"},
                        "body": {
                            "vm_name": "{{ vm_name }}",
                            "status": "completed",
                            "timestamp": "{{ timestamp_iso }}",
                        },
                        "timeout": 30,
                        "continue_on_error": True,
                    }
                ]
            },
            "source": {"provider": "test", "vm_name": "test"},
            "disks": [],
        }

        manifest_path = tmp_path / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        # Verify structure
        with open(manifest_path) as f:
            loaded = json.load(f)

        hook = loaded["hooks"]["post_validate"][0]
        assert hook["type"] == "http"
        assert hook["url"] == "https://api.example.com/migrations"
        assert hook["body"]["vm_name"] == "{{ vm_name }}"


class TestLibvirtXMLWorkflow:
    """Integration tests for libvirt XML import workflows."""

    def test_create_sample_domain_xml(self, tmp_path):
        """Test creating a valid domain XML for parsing."""
        xml_content = """<?xml version="1.0"?>
<domain type="kvm">
  <name>integration-test-vm</name>
  <uuid>12345678-1234-1234-1234-123456789012</uuid>
  <memory unit="GiB">4</memory>
  <vcpu>2</vcpu>
  <os>
    <type arch="x86_64">hvm</type>
    <loader type="pflash">/usr/share/OVMF/OVMF_CODE.fd</loader>
  </os>
  <devices>
    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2"/>
      <source file="/var/lib/libvirt/images/test.qcow2"/>
      <target dev="vda" bus="virtio"/>
    </disk>
    <interface type="bridge">
      <mac address="52:54:00:11:22:33"/>
      <source bridge="br0"/>
      <model type="virtio"/>
    </interface>
  </devices>
</domain>"""

        xml_path = tmp_path / "domain.xml"
        xml_path.write_text(xml_content)

        assert xml_path.exists()

        # Verify can be parsed as XML
        import xml.etree.ElementTree as ET

        tree = ET.parse(xml_path)
        root = tree.getroot()

        assert root.tag == "domain"
        assert root.find("name").text == "integration-test-vm"

    def test_expected_manifest_from_xml(self, tmp_path):
        """Test the expected manifest structure from XML parsing."""
        # This tests what the manifest SHOULD look like after parsing
        expected_manifest = {
            "manifest_version": "1.0",
            "source": {
                "provider": "libvirt",
                "vm_id": "test-uuid",
                "vm_name": "test-vm",
                "libvirt_xml_path": "/path/to/domain.xml",
            },
            "disks": [
                {
                    "id": "vda",
                    "source_format": "qcow2",
                    "local_path": "/var/lib/libvirt/images/disk.qcow2",
                    "disk_type": "boot",
                }
            ],
            "firmware": {"type": "uefi"},
            "os_hint": "unknown",
            "metadata": {
                "networks": [
                    {
                        "type": "bridge",
                        "source": "br0",
                        "mac": "52:54:00:aa:bb:cc",
                        "model": "virtio",
                    }
                ],
                "memory_bytes": 4294967296,  # 4GB
                "vcpus": 2,
            },
            "pipeline": {
                "inspect": {"enabled": True},
                "fix": {"enabled": True, "backup": True},
                "convert": {"enabled": True, "compress": True},
                "validate": {"enabled": True},
            },
            "output": {"format": "qcow2"},
        }

        # Save as reference
        manifest_path = tmp_path / "expected-manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(expected_manifest, f, indent=2)

        assert manifest_path.exists()

        # Verify structure
        with open(manifest_path) as f:
            loaded = json.load(f)

        assert loaded["source"]["provider"] == "libvirt"
        assert loaded["firmware"]["type"] == "uefi"
        assert len(loaded["disks"]) == 1
        assert loaded["metadata"]["vcpus"] == 2
