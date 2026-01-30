# SPDX-License-Identifier: LGPL-3.0-or-later
"""Migration profile loader with inheritance and merging support."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..config.config_loader import Config

try:
    import yaml  # type: ignore

    YAML_AVAILABLE = True
except Exception:
    YAML_AVAILABLE = False


class ProfileLoadError(Exception):
    """Raised when profile loading fails."""

    pass


class ProfileLoader:
    """
    Loads and merges migration profiles with inheritance support.

    Profiles provide reusable configuration templates for common migration scenarios:
    - production: Full fixes, compression, validation
    - testing: Minimal fixes, fast conversion
    - minimal: Bare minimum processing

    Profiles support inheritance via 'extends' field.
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self._builtin_profiles_cache: dict[str, dict[str, Any]] | None = None

    def load_profile(self, profile_name: str, custom_profile_path: Path | None = None) -> dict[str, Any]:
        """
        Load a profile by name, checking custom path first, then built-ins.

        Args:
            profile_name: Profile name (e.g., "production", "testing")
            custom_profile_path: Optional path to custom profiles directory

        Returns:
            Resolved profile configuration with inheritance applied

        Raises:
            ProfileLoadError: If profile not found or invalid
        """
        self.logger.debug(f"Loading profile: {profile_name}")

        # Try custom profile path first
        if custom_profile_path:
            profile_path = Path(custom_profile_path) / f"{profile_name}.yaml"
            if profile_path.exists():
                self.logger.debug(f"Loading custom profile: {profile_path}")
                return self._load_and_resolve(profile_path)

        # Try built-in profiles
        builtin_profiles = self._load_builtin_profiles()
        if profile_name in builtin_profiles:
            self.logger.debug(f"Loading built-in profile: {profile_name}")
            profile_data = builtin_profiles[profile_name].copy()
            return self._resolve_inheritance(profile_data, builtin_profiles)

        raise ProfileLoadError(
            f"Profile '{profile_name}' not found. "
            f"Available built-in profiles: {list(builtin_profiles.keys())}"
        )

    def _load_builtin_profiles(self) -> dict[str, dict[str, Any]]:
        """Load built-in profiles from YAML file."""
        if self._builtin_profiles_cache is not None:
            return self._builtin_profiles_cache

        # Find builtin_profiles.yaml in the same directory as this module
        builtin_path = Path(__file__).parent / "builtin_profiles.yaml"

        if not builtin_path.exists():
            self.logger.warning(f"Built-in profiles file not found: {builtin_path}")
            self._builtin_profiles_cache = {}
            return self._builtin_profiles_cache

        try:
            if not YAML_AVAILABLE:
                raise ProfileLoadError(
                    "PyYAML not installed. Install with: pip install PyYAML"
                )

            with open(builtin_path, "r", encoding="utf-8") as f:
                profiles_data = yaml.safe_load(f) or {}

            if not isinstance(profiles_data, dict):
                raise ProfileLoadError(
                    f"Built-in profiles file must contain a dictionary: {builtin_path}"
                )

            self._builtin_profiles_cache = profiles_data
            self.logger.debug(
                f"Loaded {len(profiles_data)} built-in profiles: {list(profiles_data.keys())}"
            )

            return self._builtin_profiles_cache

        except Exception as e:
            raise ProfileLoadError(f"Failed to load built-in profiles: {e}") from e

    def _load_and_resolve(self, profile_path: Path) -> dict[str, Any]:
        """Load a profile from file and resolve inheritance."""
        try:
            if not YAML_AVAILABLE:
                raise ProfileLoadError(
                    "PyYAML not installed. Install with: pip install PyYAML"
                )

            with open(profile_path, "r", encoding="utf-8") as f:
                if profile_path.suffix.lower() == ".json":
                    profile_data = json.load(f)
                else:
                    profile_data = yaml.safe_load(f) or {}

            if not isinstance(profile_data, dict):
                raise ProfileLoadError(
                    f"Profile must be a dictionary: {profile_path}"
                )

            # Resolve inheritance
            builtin_profiles = self._load_builtin_profiles()
            return self._resolve_inheritance(profile_data, builtin_profiles)

        except Exception as e:
            raise ProfileLoadError(
                f"Failed to load profile from {profile_path}: {e}"
            ) from e

    def _resolve_inheritance(
        self,
        profile_data: dict[str, Any],
        available_profiles: dict[str, dict[str, Any]],
        _visited: set[str] | None = None,
    ) -> dict[str, Any]:
        """
        Resolve profile inheritance using 'extends' field.

        Args:
            profile_data: Profile configuration
            available_profiles: Dictionary of available profiles
            _visited: Set of visited profile names (for cycle detection)

        Returns:
            Resolved profile with parent configurations merged

        Raises:
            ProfileLoadError: If circular inheritance detected
        """
        if _visited is None:
            _visited = set()

        # Check for 'extends' field
        parent_name = profile_data.get("extends")
        if not parent_name:
            # No inheritance, return as-is
            return profile_data

        # Detect circular inheritance
        if parent_name in _visited:
            raise ProfileLoadError(
                f"Circular inheritance detected: {parent_name} already visited"
            )

        # Load parent profile
        if parent_name not in available_profiles:
            raise ProfileLoadError(
                f"Parent profile '{parent_name}' not found (extended by profile)"
            )

        parent_data = available_profiles[parent_name].copy()

        # Recursively resolve parent's inheritance
        _visited.add(parent_name)
        resolved_parent = self._resolve_inheritance(
            parent_data, available_profiles, _visited
        )
        _visited.remove(parent_name)

        # Merge: child overrides parent
        merged = self._merge_profiles(resolved_parent, profile_data)

        # Remove 'extends' from final result
        merged.pop("extends", None)

        return merged

    def _merge_profiles(
        self, base: dict[str, Any], override: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Deep merge two profile configurations.

        Args:
            base: Base profile configuration
            override: Override profile configuration

        Returns:
            Merged configuration with override taking precedence
        """
        # Use Config.merge_dicts from existing codebase
        return Config.merge_dicts(base, override)

    def apply_overrides(
        self, profile: dict[str, Any], overrides: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Apply user-specified overrides to a profile.

        Args:
            profile: Base profile configuration
            overrides: User override configuration

        Returns:
            Profile with overrides applied
        """
        if not overrides:
            return profile

        self.logger.debug(
            f"Applying overrides: {list(overrides.keys())} keys"
        )

        return self._merge_profiles(profile, overrides)

    def list_builtin_profiles(self) -> list[str]:
        """Get list of available built-in profile names."""
        builtin_profiles = self._load_builtin_profiles()
        return sorted(builtin_profiles.keys())

    def get_profile_info(self, profile_name: str) -> dict[str, Any]:
        """
        Get profile metadata and configuration.

        Args:
            profile_name: Profile name

        Returns:
            Dictionary with profile info (description, configuration)
        """
        profile = self.load_profile(profile_name)

        return {
            "name": profile_name,
            "description": profile.get("description", "No description"),
            "extends": profile.get("extends"),
            "configuration": profile,
        }
