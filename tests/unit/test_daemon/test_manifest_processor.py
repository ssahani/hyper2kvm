# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Tests for manifest processor.
"""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch

from hyper2kvm.daemon.manifest_processor import (
    ManifestProcessor,
    create_manifest_processor_callback,
)


class TestManifestProcessor:
    """Test manifest processor."""

    def test_processor_initialization(self, tmp_path):
        """Test that processor can be initialized."""
        output_dir = tmp_path / "output"
        processor = ManifestProcessor(output_dir)

        assert processor.output_dir == output_dir
        assert output_dir.exists()

    def test_load_yaml_manifest(self, tmp_path):
        """Test loading YAML manifest."""
        processor = ManifestProcessor(tmp_path)

        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text(
            """
hypervisor: vmware
vmware:
  vm_name: test-vm
  host: vcenter.example.com
"""
        )

        manifest = processor._load_manifest(manifest_file)

        assert manifest is not None
        assert manifest["hypervisor"] == "vmware"
        assert manifest["vmware"]["vm_name"] == "test-vm"

    def test_load_json_manifest(self, tmp_path):
        """Test loading JSON manifest."""
        processor = ManifestProcessor(tmp_path)

        manifest_file = tmp_path / "test.json"
        manifest_data = {
            "hypervisor": "vmware",
            "vmware": {"vm_name": "test-vm", "host": "vcenter.example.com"},
        }
        manifest_file.write_text(json.dumps(manifest_data))

        manifest = processor._load_manifest(manifest_file)

        assert manifest is not None
        assert manifest["hypervisor"] == "vmware"
        assert manifest["vmware"]["vm_name"] == "test-vm"

    def test_load_invalid_manifest(self, tmp_path):
        """Test loading invalid YAML."""
        processor = ManifestProcessor(tmp_path)

        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text("invalid: yaml: content: [")

        manifest = processor._load_manifest(manifest_file)

        assert manifest is None

    def test_validate_single_vm_manifest(self, tmp_path):
        """Test validation of single VM manifest."""
        processor = ManifestProcessor(tmp_path)

        valid_manifest = {
            "hypervisor": "vmware",
            "vmware": {"vm_name": "test-vm", "host": "vcenter.example.com"},
        }

        assert processor._validate_manifest(valid_manifest)

    def test_validate_manifest_missing_hypervisor(self, tmp_path):
        """Test validation fails when hypervisor missing."""
        processor = ManifestProcessor(tmp_path)

        invalid_manifest = {"vmware": {"vm_name": "test-vm"}}

        assert not processor._validate_manifest(invalid_manifest)

    def test_validate_vmware_manifest_missing_vm_name(self, tmp_path):
        """Test validation fails when VMware manifest missing vm_name/uuid."""
        processor = ManifestProcessor(tmp_path)

        invalid_manifest = {"hypervisor": "vmware", "vmware": {"host": "vcenter.example.com"}}

        assert not processor._validate_manifest(invalid_manifest)

    def test_validate_batch_manifest(self, tmp_path):
        """Test validation of batch manifest."""
        processor = ManifestProcessor(tmp_path)

        valid_manifest = {"vms": [{"vm_name": "vm1"}, {"vm_name": "vm2"}]}

        assert processor._validate_manifest(valid_manifest)

    def test_validate_batch_manifest_empty_vms(self, tmp_path):
        """Test validation fails for empty batch."""
        processor = ManifestProcessor(tmp_path)

        invalid_manifest = {"vms": []}

        assert not processor._validate_manifest(invalid_manifest)

    def test_validate_batch_manifest_vms_not_list(self, tmp_path):
        """Test validation fails when vms is not a list."""
        processor = ManifestProcessor(tmp_path)

        invalid_manifest = {"vms": "not-a-list"}

        assert not processor._validate_manifest(invalid_manifest)

    def test_is_batch_manifest_detection(self, tmp_path):
        """Test batch manifest detection."""
        processor = ManifestProcessor(tmp_path)

        batch_manifest = {"vms": [{"vm_name": "vm1"}]}
        single_manifest = {"hypervisor": "vmware", "vmware": {"vm_name": "vm1"}}

        assert processor._is_batch_manifest(batch_manifest)
        assert not processor._is_batch_manifest(single_manifest)

    def test_get_vm_name_from_vm_name_field(self, tmp_path):
        """Test extracting VM name from vm_name field."""
        processor = ManifestProcessor(tmp_path)

        config = {"vm_name": "test-vm"}

        assert processor._get_vm_name(config) == "test-vm"

    def test_get_vm_name_from_vmware_config(self, tmp_path):
        """Test extracting VM name from VMware config."""
        processor = ManifestProcessor(tmp_path)

        config = {"vmware": {"vm_name": "test-vm"}}

        assert processor._get_vm_name(config) == "test-vm"

    def test_get_vm_name_from_vmware_uuid(self, tmp_path):
        """Test extracting VM name from VMware UUID."""
        processor = ManifestProcessor(tmp_path)

        config = {"vmware": {"vm_uuid": "12345-abcde"}}

        assert processor._get_vm_name(config) == "12345-abcde"

    def test_get_vm_name_fallback(self, tmp_path):
        """Test VM name fallback when not found."""
        processor = ManifestProcessor(tmp_path)

        config = {"other": "data"}

        assert processor._get_vm_name(config) == "unknown"

    def test_process_single_manifest_success(self, tmp_path):
        """Test processing single VM manifest."""
        processor = ManifestProcessor(tmp_path)

        manifest_file = tmp_path / "single.yaml"
        manifest_file.write_text(
            """
hypervisor: vmware
vmware:
  vm_name: web-server-01
  host: vcenter.example.com
"""
        )

        result = processor.process_manifest(manifest_file)

        assert result is True

    def test_process_batch_manifest_success(self, tmp_path):
        """Test processing batch manifest."""
        processor = ManifestProcessor(tmp_path)

        manifest_file = tmp_path / "batch.yaml"
        manifest_file.write_text(
            """
vms:
  - vm_name: web-server-01
  - vm_name: web-server-02
  - vm_name: db-server-01
"""
        )

        result = processor.process_manifest(manifest_file)

        assert result is True

    def test_process_empty_manifest(self, tmp_path):
        """Test processing empty manifest file."""
        processor = ManifestProcessor(tmp_path)

        manifest_file = tmp_path / "empty.yaml"
        manifest_file.write_text("")

        result = processor.process_manifest(manifest_file)

        assert result is False

    def test_process_invalid_manifest(self, tmp_path):
        """Test processing invalid manifest."""
        processor = ManifestProcessor(tmp_path)

        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text("hypervisor: vmware\n# Missing vm_name")

        result = processor.process_manifest(manifest_file)

        assert result is False

    def test_process_nonexistent_file(self, tmp_path):
        """Test processing non-existent file."""
        processor = ManifestProcessor(tmp_path)

        manifest_file = tmp_path / "nonexistent.yaml"

        result = processor.process_manifest(manifest_file)

        assert result is False


class TestManifestProcessorCallback:
    """Test manifest processor callback creation."""

    def test_create_callback(self, tmp_path):
        """Test creating processor callback."""
        callback = create_manifest_processor_callback(tmp_path)

        assert callable(callback)

    def test_callback_processes_manifest(self, tmp_path):
        """Test that callback processes manifests."""
        callback = create_manifest_processor_callback(tmp_path)

        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text(
            """
hypervisor: vmware
vmware:
  vm_name: test-vm
  host: vcenter.example.com
"""
        )

        result = callback(manifest_file)

        assert result is True
