# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/cli/config.py
"""
Configuration management for CLI.

Handles loading and saving migration configurations.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class MigrationConfig:
    """
    Migration configuration.

    Attributes:
        source_path: Source VM disk image path
        target_path: Target VM path (optional)
        source_format: Source disk format
        target_format: Target disk format
        readonly: Mount source read-only
        create_snapshot: Create pre-migration snapshot
        fix_bootloader: Fix bootloader configuration
        fix_network: Fix network configuration
        stabilize_fstab: Stabilize fstab entries
        run_validation: Run post-migration validation
        validate_services: Validate services
        validate_network: Validate network
        validate_databases: Validate databases
        output_dir: Output directory for reports
        metadata: Additional metadata
    """
    source_path: str
    target_path: str | None = None
    source_format: str = "qcow2"
    target_format: str = "qcow2"
    readonly: bool = True
    create_snapshot: bool = True
    fix_bootloader: bool = True
    fix_network: bool = True
    stabilize_fstab: bool = True
    run_validation: bool = True
    validate_services: bool = True
    validate_network: bool = True
    validate_databases: bool = True
    output_dir: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MigrationConfig:
        """Create from dictionary."""
        # Filter out unknown fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)


class ConfigManager:
    """
    Configuration manager.

    Loads and saves migration configurations from/to files.
    """

    def __init__(self, logger: logging.Logger | None = None):
        """
        Initialize configuration manager.

        Args:
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

    def load_config(self, config_file: str | Path) -> MigrationConfig:
        """
        Load configuration from file.

        Args:
            config_file: Path to configuration file (JSON or YAML)

        Returns:
            Migration configuration

        Raises:
            FileNotFoundError: If config file not found
            ValueError: If config file is invalid
        """
        config_path = Path(config_file)

        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        self.logger.info(f"Loading configuration from {config_path}")

        try:
            # Determine format from extension
            if config_path.suffix.lower() in [".yaml", ".yml"]:
                data = self._load_yaml(config_path)
            elif config_path.suffix.lower() == ".json":
                data = self._load_json(config_path)
            else:
                # Try JSON first, then YAML
                try:
                    data = self._load_json(config_path)
                except Exception:
                    data = self._load_yaml(config_path)

            return MigrationConfig.from_dict(data)

        except Exception as e:
            raise ValueError(f"Failed to load configuration: {e}") from e

    def save_config(
        self,
        config: MigrationConfig,
        config_file: str | Path,
        *,
        format: str = "json",
    ) -> None:
        """
        Save configuration to file.

        Args:
            config: Migration configuration
            config_file: Path to configuration file
            format: Output format ("json" or "yaml")

        Raises:
            ValueError: If format is invalid
        """
        config_path = Path(config_file)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Saving configuration to {config_path}")

        data = config.to_dict()

        if format == "json":
            self._save_json(config_path, data)
        elif format == "yaml":
            self._save_yaml(config_path, data)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _load_json(self, path: Path) -> dict[str, Any]:
        """Load JSON file."""
        with open(path, "r") as f:
            return json.load(f)

    def _save_json(self, path: Path, data: dict[str, Any]) -> None:
        """Save JSON file."""
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """Load YAML file."""
        try:
            import yaml
            with open(path, "r") as f:
                return yaml.safe_load(f)
        except ImportError:
            raise ValueError("PyYAML not installed. Install with: pip install pyyaml")

    def _save_yaml(self, path: Path, data: dict[str, Any]) -> None:
        """Save YAML file."""
        try:
            import yaml
            with open(path, "w") as f:
                yaml.safe_dump(data, f, default_flow_style=False)
        except ImportError:
            raise ValueError("PyYAML not installed. Install with: pip install pyyaml")

    def create_default_config(self, source_path: str) -> MigrationConfig:
        """
        Create default configuration.

        Args:
            source_path: Source VM disk image path

        Returns:
            Default migration configuration
        """
        return MigrationConfig(source_path=source_path)

    def validate_config(self, config: MigrationConfig) -> list[str]:
        """
        Validate configuration.

        Args:
            config: Migration configuration

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Validate source path
        if not config.source_path:
            errors.append("Source path is required")
        elif not Path(config.source_path).exists():
            errors.append(f"Source path does not exist: {config.source_path}")

        # Validate formats
        valid_formats = ["qcow2", "raw", "vmdk", "vdi", "vhd", "vhdx"]
        if config.source_format not in valid_formats:
            errors.append(f"Invalid source format: {config.source_format}")
        if config.target_format not in valid_formats:
            errors.append(f"Invalid target format: {config.target_format}")

        return errors
