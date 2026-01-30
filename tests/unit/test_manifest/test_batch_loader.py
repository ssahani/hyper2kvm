# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for batch manifest loader."""

import json
import tempfile
from pathlib import Path

import pytest

from hyper2kvm.manifest.batch_loader import BatchLoader


class TestBatchLoader:
    """Test BatchLoader functionality."""

    def test_load_valid_json_batch(self):
        """Test loading a valid JSON batch manifest."""
        batch_data = {
            "batch_version": "1.0",
            "batch_metadata": {
                "batch_id": "test-batch",
                "parallel_limit": 4,
                "continue_on_error": True,
            },
            "vms": [
                {"id": "vm1", "manifest": "/path/to/vm1.json", "priority": 0},
                {"id": "vm2", "manifest": "/path/to/vm2.json", "priority": 1},
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(batch_data, f)
            batch_path = Path(f.name)

        try:
            loader = BatchLoader()
            manifest = loader.load(batch_path)

            assert manifest["batch_version"] == "1.0"
            assert manifest["batch_metadata"]["batch_id"] == "test-batch"
            assert len(manifest["vms"]) == 2

            # Test get_vms with sorting
            vms = loader.get_vms()
            assert len(vms) == 2
            assert vms[0].id == "vm1"  # priority 0 comes first
            assert vms[1].id == "vm2"

        finally:
            batch_path.unlink()

    def test_load_yaml_batch(self):
        """Test loading a YAML batch manifest."""
        yaml_content = """
batch_version: "1.0"
batch_metadata:
  batch_id: yaml-test
  parallel_limit: 2
vms:
  - id: vm1
    manifest: /work/vm1.json
  - id: vm2
    manifest: /work/vm2.json
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            batch_path = Path(f.name)

        try:
            loader = BatchLoader()
            manifest = loader.load(batch_path)

            assert manifest["batch_version"] == "1.0"
            assert manifest["batch_metadata"]["batch_id"] == "yaml-test"
            assert len(manifest["vms"]) == 2

        finally:
            batch_path.unlink()

    def test_invalid_version(self):
        """Test that invalid version raises error."""
        from hyper2kvm.manifest.batch_loader import BatchValidationError

        batch_data = {"batch_version": "2.0", "vms": []}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(batch_data, f)
            batch_path = Path(f.name)

        try:
            loader = BatchLoader()
            with pytest.raises(BatchValidationError, match="Unsupported batch version"):
                loader.load(batch_path)
        finally:
            batch_path.unlink()

    def test_missing_required_fields(self):
        """Test that missing required fields raise error."""
        from hyper2kvm.manifest.batch_loader import BatchValidationError

        batch_data = {"batch_version": "1.0"}  # Missing 'vms'

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(batch_data, f)
            batch_path = Path(f.name)

        try:
            loader = BatchLoader()
            with pytest.raises(BatchValidationError, match="[Mm]issing required field"):
                loader.load(batch_path)
        finally:
            batch_path.unlink()

    def test_vm_priority_sorting(self):
        """Test that VMs are sorted by priority."""
        batch_data = {
            "batch_version": "1.0",
            "vms": [
                {"id": "low", "manifest": "/low.json", "priority": 10},
                {"id": "high", "manifest": "/high.json", "priority": 0},
                {"id": "medium", "manifest": "/med.json", "priority": 5},
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(batch_data, f)
            batch_path = Path(f.name)

        try:
            loader = BatchLoader()
            loader.load(batch_path)
            vms = loader.get_vms()

            assert vms[0].id == "high"  # priority 0
            assert vms[1].id == "medium"  # priority 5
            assert vms[2].id == "low"  # priority 10

        finally:
            batch_path.unlink()

    def test_disabled_vms_filtered(self):
        """Test that disabled VMs are filtered out."""
        batch_data = {
            "batch_version": "1.0",
            "vms": [
                {"id": "enabled", "manifest": "/e.json", "enabled": True},
                {"id": "disabled", "manifest": "/d.json", "enabled": False},
                {"id": "default", "manifest": "/def.json"},  # enabled by default
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(batch_data, f)
            batch_path = Path(f.name)

        try:
            loader = BatchLoader()
            loader.load(batch_path)
            vms = loader.get_vms()

            assert len(vms) == 2
            assert all(vm.id != "disabled" for vm in vms)

        finally:
            batch_path.unlink()

    def test_get_metadata(self):
        """Test getting batch metadata."""
        batch_data = {
            "batch_version": "1.0",
            "batch_metadata": {
                "batch_id": "test-123",
                "parallel_limit": 8,
                "continue_on_error": False,
            },
            "vms": [],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(batch_data, f)
            batch_path = Path(f.name)

        try:
            loader = BatchLoader()
            loader.load(batch_path)
            metadata = loader.get_metadata()

            assert metadata["batch_id"] == "test-123"
            assert metadata["parallel_limit"] == 8
            assert metadata["continue_on_error"] is False

        finally:
            batch_path.unlink()

    def test_get_shared_config(self):
        """Test getting shared configuration."""
        batch_data = {
            "batch_version": "1.0",
            "vms": [],
            "shared_config": {
                "output_directory": "/converted",
                "profile": "production",
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(batch_data, f)
            batch_path = Path(f.name)

        try:
            loader = BatchLoader()
            loader.load(batch_path)
            config = loader.get_shared_config()

            assert config["output_directory"] == "/converted"
            assert config["profile"] == "production"

        finally:
            batch_path.unlink()

    def test_file_not_found(self):
        """Test that missing file raises FileNotFoundError."""
        loader = BatchLoader()
        with pytest.raises(FileNotFoundError):
            loader.load(Path("/nonexistent/batch.json"))

    def test_empty_vms_list(self):
        """Test that empty VMs list is valid but returns no VMs."""
        batch_data = {"batch_version": "1.0", "vms": []}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(batch_data, f)
            batch_path = Path(f.name)

        try:
            loader = BatchLoader()
            loader.load(batch_path)
            vms = loader.get_vms()

            assert len(vms) == 0

        finally:
            batch_path.unlink()
