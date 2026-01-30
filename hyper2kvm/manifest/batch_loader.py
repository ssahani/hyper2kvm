# SPDX-License-Identifier: LGPL-3.0-or-later
"""Batch Manifest loader and validator for multi-VM conversions."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore

    YAML_AVAILABLE = True
except Exception:
    YAML_AVAILABLE = False


class BatchValidationError(Exception):
    """Raised when batch manifest validation fails."""

    pass


class VMBatchItem:
    """Represents a single VM in a batch manifest."""

    def __init__(self, data: dict[str, Any], index: int):
        self.index = index
        self.manifest_path = Path(data["manifest"]).expanduser().resolve()
        self.priority = data.get("priority", 0)
        self.overrides = data.get("overrides", {})
        self.id = data.get("id", f"vm_{index}")
        self.enabled = data.get("enabled", True)

    def __repr__(self) -> str:
        return f"VMBatchItem(id={self.id!r}, manifest={self.manifest_path}, priority={self.priority})"


class BatchLoader:
    """Loads and validates Batch Manifest v1 for multi-VM conversions."""

    SUPPORTED_VERSIONS = ["1.0"]

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self.manifest: dict[str, Any] = {}
        self.path: Path | None = None
        self.vms: list[VMBatchItem] = []

    def load(self, manifest_path: str | Path) -> dict[str, Any]:
        """
        Load and validate Batch Manifest v1.

        Args:
            manifest_path: Path to batch manifest JSON/YAML file

        Returns:
            Validated batch manifest dictionary

        Raises:
            BatchValidationError: If manifest is invalid
            FileNotFoundError: If manifest file doesn't exist
        """
        self.path = Path(manifest_path).expanduser().resolve()

        if not self.path.exists():
            raise FileNotFoundError(f"Batch manifest not found: {self.path}")

        self.logger.info(f"Loading Batch Manifest: {self.path}")

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                content = f.read()

            # Try JSON first, then YAML
            if self.path.suffix.lower() == ".json":
                self.manifest = json.loads(content)
            elif self.path.suffix.lower() in (".yaml", ".yml"):
                if not YAML_AVAILABLE:
                    raise BatchValidationError(
                        "PyYAML not installed. Install with: pip install PyYAML"
                    )
                self.manifest = yaml.safe_load(content) or {}
            else:
                # Auto-detect: try JSON first
                try:
                    self.manifest = json.loads(content)
                except json.JSONDecodeError:
                    if YAML_AVAILABLE:
                        self.manifest = yaml.safe_load(content) or {}
                    else:
                        raise BatchValidationError(
                            "Could not parse manifest as JSON and PyYAML not available"
                        )

        except (json.JSONDecodeError, yaml.YAMLError if YAML_AVAILABLE else Exception) as e:
            raise BatchValidationError(f"Invalid manifest format: {e}") from e

        self._validate()
        self.logger.info(
            f"✅ Batch Manifest v{self.get_version()} loaded successfully with {len(self.vms)} VM(s)"
        )

        return self.manifest

    def load_batch(self, manifest_path: str | Path) -> dict[str, Any]:
        """
        Alias for load() - more explicit method name for loading batch manifests.

        Args:
            manifest_path: Path to batch manifest JSON/YAML file

        Returns:
            Validated batch manifest dictionary

        Raises:
            BatchValidationError: If manifest is invalid
            FileNotFoundError: If manifest file doesn't exist
        """
        return self.load(manifest_path)

    def _validate(self) -> None:
        """Validate batch manifest structure and required fields."""
        if not isinstance(self.manifest, dict):
            raise BatchValidationError("Batch manifest must be a JSON/YAML object")

        # Validate version
        version = self.manifest.get("batch_version")
        if not version:
            raise BatchValidationError(
                "Missing required field: batch_version. "
                f"Expected versions: {self.SUPPORTED_VERSIONS}"
            )

        if version not in self.SUPPORTED_VERSIONS:
            raise BatchValidationError(
                f"Unsupported batch version: {version}. "
                f"Supported versions: {self.SUPPORTED_VERSIONS}"
            )

        # Validate VMs array (REQUIRED)
        if "vms" not in self.manifest:
            raise BatchValidationError(
                "Missing required field: vms[]. "
                "Batch Manifest requires at least one VM."
            )

        if not isinstance(self.manifest["vms"], list):
            raise BatchValidationError("Field 'vms' must be an array")

        # Empty batches are allowed (useful for templates and testing)
        # if len(self.manifest["vms"]) == 0:
        #     self.logger.warning("Batch contains no VMs")

        # Validate batch_metadata (optional but recommended)
        if "batch_metadata" in self.manifest:
            self._validate_batch_metadata()

        # Validate each VM
        self._validate_vms()

    def _validate_batch_metadata(self) -> None:
        """Validate batch_metadata section."""
        metadata = self.manifest["batch_metadata"]
        if not isinstance(metadata, dict):
            raise BatchValidationError("batch_metadata must be an object")

        # Validate parallel_limit if present
        if "parallel_limit" in metadata:
            parallel_limit = metadata["parallel_limit"]
            if not isinstance(parallel_limit, int) or parallel_limit < 1:
                raise BatchValidationError(
                    f"batch_metadata.parallel_limit must be a positive integer (got: {parallel_limit})"
                )

        # Validate continue_on_error if present
        if "continue_on_error" in metadata:
            if not isinstance(metadata["continue_on_error"], bool):
                raise BatchValidationError(
                    "batch_metadata.continue_on_error must be a boolean"
                )

    def _validate_vms(self) -> None:
        """Validate vms array."""
        vm_ids = set()

        for idx, vm_data in enumerate(self.manifest["vms"]):
            if not isinstance(vm_data, dict):
                raise BatchValidationError(f"vms[{idx}] must be an object")

            # Required field: manifest
            if "manifest" not in vm_data:
                raise BatchValidationError(
                    f"vms[{idx}].manifest is required (path to VM manifest file)"
                )

            # Validate manifest path format
            manifest_path = vm_data["manifest"]
            if not isinstance(manifest_path, str):
                raise BatchValidationError(
                    f"vms[{idx}].manifest must be a string path"
                )

            # Validate priority if present
            if "priority" in vm_data:
                priority = vm_data["priority"]
                if not isinstance(priority, int):
                    raise BatchValidationError(
                        f"vms[{idx}].priority must be an integer (got: {priority})"
                    )

            # Validate id if present
            vm_id = vm_data.get("id", f"vm_{idx}")
            if not re.match(r"^[a-zA-Z0-9_-]+$", vm_id):
                raise BatchValidationError(
                    f"vms[{idx}].id must match pattern: ^[a-zA-Z0-9_-]+$ (got: {vm_id!r})"
                )

            if vm_id in vm_ids:
                raise BatchValidationError(f"Duplicate VM ID: {vm_id}")
            vm_ids.add(vm_id)

            # Validate overrides if present
            if "overrides" in vm_data:
                if not isinstance(vm_data["overrides"], dict):
                    raise BatchValidationError(
                        f"vms[{idx}].overrides must be an object"
                    )

            # Validate enabled if present
            if "enabled" in vm_data:
                if not isinstance(vm_data["enabled"], bool):
                    raise BatchValidationError(
                        f"vms[{idx}].enabled must be a boolean"
                    )

            # Create VMBatchItem
            try:
                vm_item = VMBatchItem(vm_data, idx)
                self.vms.append(vm_item)
            except Exception as e:
                raise BatchValidationError(f"vms[{idx}]: {e}") from e

        # Sort VMs in manifest by priority (lower values = higher priority)
        self.manifest["vms"] = sorted(
            self.manifest["vms"],
            key=lambda vm: (vm.get("priority", 0), self.manifest["vms"].index(vm))
        )

    # Getters

    def get_version(self) -> str:
        """Get batch manifest version."""
        return self.manifest.get("batch_version", "unknown")

    def get_batch_id(self) -> str:
        """Get batch ID."""
        return self.manifest.get("batch_metadata", {}).get("batch_id", "unnamed_batch")

    def get_parallel_limit(self) -> int:
        """Get parallel execution limit (default: 4)."""
        return self.manifest.get("batch_metadata", {}).get("parallel_limit", 4)

    def get_continue_on_error(self) -> bool:
        """Get continue-on-error flag (default: True)."""
        return self.manifest.get("batch_metadata", {}).get("continue_on_error", True)

    def get_metadata(self) -> dict[str, Any]:
        """Get complete batch metadata dictionary."""
        return self.manifest.get("batch_metadata", {})

    def get_shared_config(self) -> dict[str, Any]:
        """Get shared configuration applied to all VMs."""
        return self.manifest.get("shared_config", {})

    def get_vms(self) -> list[VMBatchItem]:
        """Get list of VM batch items (sorted by priority)."""
        # Sort by priority (lower values = higher priority)
        return sorted(
            [vm for vm in self.vms if vm.enabled], key=lambda x: (x.priority, x.index)
        )

    def get_output_directory(self) -> Path | None:
        """Get shared output directory if specified."""
        shared_config = self.get_shared_config()
        output_dir = shared_config.get("output_directory")
        if output_dir:
            return Path(output_dir).expanduser().resolve()
        return None
