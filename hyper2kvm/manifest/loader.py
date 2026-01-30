# SPDX-License-Identifier: LGPL-3.0-or-later
"""Manifest loader and validator for manifest-driven workflows."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any


class ManifestValidationError(Exception):
    """Raised when manifest validation fails."""
    pass


class ManifestLoader:
    """Loads and validates manifest files for the convert workflow."""

    REQUIRED_FIELDS = ["version", "source", "output", "pipeline"]
    SUPPORTED_VERSIONS = ["1.0"]
    SUPPORTED_SOURCE_TYPES = ["vmdk", "ova", "ovf", "vhd", "qcow2", "raw"]
    SUPPORTED_OUTPUT_FORMATS = ["qcow2", "raw", "vdi"]
    PIPELINE_STAGES = ["inspect", "fix", "convert", "validate"]

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self.manifest: dict[str, Any] = {}
        self.path: Path | None = None

    def load(self, manifest_path: str | Path) -> dict[str, Any]:
        """
        Load and validate manifest from file.

        Args:
            manifest_path: Path to manifest JSON file

        Returns:
            Validated manifest dictionary

        Raises:
            ManifestValidationError: If manifest is invalid
            FileNotFoundError: If manifest file doesn't exist
            json.JSONDecodeError: If manifest is not valid JSON
        """
        self.path = Path(manifest_path).expanduser().resolve()

        if not self.path.exists():
            raise FileNotFoundError(f"Manifest not found: {self.path}")

        self.logger.info(f"Loading manifest: {self.path}")

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.manifest = json.load(f)
        except json.JSONDecodeError as e:
            raise ManifestValidationError(f"Invalid JSON in manifest: {e}") from e

        self._validate()
        self.logger.info(f"✅ Manifest loaded and validated: {self.get_name()}")

        return self.manifest

    def _validate(self) -> None:
        """Validate manifest structure and required fields."""
        if not isinstance(self.manifest, dict):
            raise ManifestValidationError("Manifest must be a JSON object")

        # Check required top-level fields
        missing = [f for f in self.REQUIRED_FIELDS if f not in self.manifest]
        if missing:
            raise ManifestValidationError(f"Missing required fields: {missing}")

        # Validate version
        version = self.manifest.get("version")
        if version not in self.SUPPORTED_VERSIONS:
            raise ManifestValidationError(
                f"Unsupported version: {version}. Supported: {self.SUPPORTED_VERSIONS}"
            )

        # Validate source
        self._validate_source()

        # Validate output
        self._validate_output()

        # Validate pipeline
        self._validate_pipeline()

    def _validate_source(self) -> None:
        """Validate source section."""
        source = self.manifest.get("source", {})

        if not isinstance(source, dict):
            raise ManifestValidationError("source must be an object")

        if "type" not in source:
            raise ManifestValidationError("source.type is required")

        if source["type"] not in self.SUPPORTED_SOURCE_TYPES:
            raise ManifestValidationError(
                f"Unsupported source type: {source['type']}. "
                f"Supported: {self.SUPPORTED_SOURCE_TYPES}"
            )

        if "path" not in source:
            raise ManifestValidationError("source.path is required")

        # Validate path exists
        source_path = Path(source["path"]).expanduser().resolve()
        if not source_path.exists():
            raise ManifestValidationError(f"Source path not found: {source_path}")

    def _validate_output(self) -> None:
        """Validate output section."""
        output = self.manifest.get("output", {})

        if not isinstance(output, dict):
            raise ManifestValidationError("output must be an object")

        if "directory" not in output:
            raise ManifestValidationError("output.directory is required")

        if "format" in output and output["format"] not in self.SUPPORTED_OUTPUT_FORMATS:
            raise ManifestValidationError(
                f"Unsupported output format: {output['format']}. "
                f"Supported: {self.SUPPORTED_OUTPUT_FORMATS}"
            )

    def _validate_pipeline(self) -> None:
        """Validate pipeline section."""
        pipeline = self.manifest.get("pipeline", {})

        if not isinstance(pipeline, dict):
            raise ManifestValidationError("pipeline must be an object")

        # Check that at least one stage is defined
        defined_stages = [s for s in self.PIPELINE_STAGES if s in pipeline]
        if not defined_stages:
            raise ManifestValidationError(
                f"pipeline must define at least one stage from: {self.PIPELINE_STAGES}"
            )

        # Validate each stage
        for stage in defined_stages:
            stage_config = pipeline[stage]
            if not isinstance(stage_config, dict):
                raise ManifestValidationError(f"pipeline.{stage} must be an object")

            if "enabled" not in stage_config:
                raise ManifestValidationError(f"pipeline.{stage}.enabled is required")

    # Convenience getters

    def get_name(self) -> str:
        """Get manifest name from metadata."""
        metadata = self.manifest.get("metadata", {})
        return metadata.get("name", "unnamed-manifest")

    def get_description(self) -> str:
        """Get manifest description from metadata."""
        metadata = self.manifest.get("metadata", {})
        return metadata.get("description", "")

    def get_source_path(self) -> Path:
        """Get resolved source path."""
        source = self.manifest["source"]
        return Path(source["path"]).expanduser().resolve()

    def get_source_type(self) -> str:
        """Get source type."""
        return self.manifest["source"]["type"]

    def get_output_directory(self) -> Path:
        """Get resolved output directory."""
        output = self.manifest["output"]
        return Path(output["directory"]).expanduser().resolve()

    def get_output_format(self) -> str:
        """Get output format (default: qcow2)."""
        output = self.manifest["output"]
        return output.get("format", "qcow2")

    def get_output_filename(self) -> str | None:
        """Get output filename if specified."""
        output = self.manifest["output"]
        return output.get("filename")

    def is_stage_enabled(self, stage: str) -> bool:
        """Check if a pipeline stage is enabled."""
        pipeline = self.manifest.get("pipeline", {})
        stage_config = pipeline.get(stage, {})
        return stage_config.get("enabled", False)

    def get_stage_config(self, stage: str) -> dict[str, Any]:
        """Get configuration for a pipeline stage."""
        pipeline = self.manifest.get("pipeline", {})
        return pipeline.get(stage, {})

    def get_configuration(self) -> dict[str, Any]:
        """Get the configuration section (users, services, hostname, etc.)."""
        return self.manifest.get("configuration", {})

    def get_options(self) -> dict[str, Any]:
        """Get the options section (dry_run, verbose, etc.)."""
        return self.manifest.get("options", {})

    def is_dry_run(self) -> bool:
        """Check if dry-run mode is enabled."""
        options = self.get_options()
        return options.get("dry_run", False)

    def get_verbosity(self) -> int:
        """Get verbosity level (default: 1)."""
        options = self.get_options()
        return options.get("verbose", 1)

    def to_dict(self) -> dict[str, Any]:
        """Return the loaded manifest as a dictionary."""
        return self.manifest.copy()
