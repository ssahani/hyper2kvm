# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Unit tests for TUI configuration management.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import pytest

from hyper2kvm.tui.tui_config import (
    TUIConfig,
    get_default_settings,
    load_tui_settings,
    save_tui_settings,
)


class TestTUIConfig:
    """Tests for TUIConfig class."""

    def test_config_creation(self):
        """Test creating a TUIConfig instance."""
        config = TUIConfig()
        assert config.settings == {}
        assert config.config_path is not None

    def test_config_with_custom_path(self, tmp_path):
        """Test creating a TUIConfig with custom path."""
        custom_path = tmp_path / "custom_config.json"
        config = TUIConfig(config_path=custom_path)
        assert config.config_path == custom_path

    def test_config_with_logger(self):
        """Test creating a TUIConfig with custom logger."""
        logger = logging.getLogger("test_logger")
        config = TUIConfig(logger=logger)
        assert config.logger == logger

    def test_load_nonexistent_file(self, tmp_path):
        """Test loading from nonexistent config file returns empty dict."""
        config_path = tmp_path / "nonexistent.json"
        config = TUIConfig(config_path=config_path)
        settings = config.load()
        assert settings == {}

    def test_load_valid_config(self, tmp_path):
        """Test loading valid JSON config file."""
        config_path = tmp_path / "config.json"
        test_settings = {
            "general": {"log_level": "debug"},
            "migration": {"default_format": "raw"}
        }
        config_path.write_text(json.dumps(test_settings))

        config = TUIConfig(config_path=config_path)
        settings = config.load()

        assert settings == test_settings
        assert config.settings == test_settings

    def test_load_invalid_json(self, tmp_path):
        """Test loading invalid JSON returns empty dict."""
        config_path = tmp_path / "invalid.json"
        config_path.write_text("{ invalid json }")

        config = TUIConfig(config_path=config_path)
        settings = config.load()

        assert settings == {}

    def test_save_creates_directory(self, tmp_path):
        """Test save creates parent directory if needed."""
        config_path = tmp_path / "subdir" / "config.json"
        test_settings = {"key": "value"}

        config = TUIConfig(config_path=config_path)
        result = config.save(test_settings)

        assert result is True
        assert config_path.exists()
        assert config_path.parent.exists()

    def test_save_writes_formatted_json(self, tmp_path):
        """Test save writes nicely formatted JSON."""
        config_path = tmp_path / "config.json"
        test_settings = {
            "general": {"log_level": "info"},
            "migration": {"default_format": "qcow2"}
        }

        config = TUIConfig(config_path=config_path)
        config.save(test_settings)

        # Read raw content to check formatting
        content = config_path.read_text()
        assert '"general"' in content
        assert '"log_level"' in content
        # Check for indentation (formatted JSON)
        assert '  "' in content or '\t"' in content

    def test_save_and_load_roundtrip(self, tmp_path):
        """Test saving and loading config preserves data."""
        config_path = tmp_path / "config.json"
        test_settings = {
            "general": {
                "default_output_dir": "/tmp/test",
                "log_level": "debug",
            },
            "migration": {
                "default_format": "vdi",
                "enable_compression": False,
            }
        }

        config = TUIConfig(config_path=config_path)
        config.save(test_settings)

        # Load with new instance
        config2 = TUIConfig(config_path=config_path)
        loaded_settings = config2.load()

        assert loaded_settings == test_settings

    def test_get_simple_key(self):
        """Test getting a simple key."""
        config = TUIConfig()
        config.settings = {"key1": "value1", "key2": "value2"}

        assert config.get("key1") == "value1"
        assert config.get("key2") == "value2"

    def test_get_nested_key_with_dot_notation(self):
        """Test getting nested keys with dot notation."""
        config = TUIConfig()
        config.settings = {
            "general": {
                "log_level": "info",
                "nested": {
                    "deep": "value"
                }
            }
        }

        assert config.get("general.log_level") == "info"
        assert config.get("general.nested.deep") == "value"

    def test_get_nonexistent_key_returns_default(self):
        """Test getting nonexistent key returns default."""
        config = TUIConfig()
        config.settings = {"key1": "value1"}

        assert config.get("nonexistent") is None
        assert config.get("nonexistent", "default") == "default"

    def test_set_simple_key(self):
        """Test setting a simple key."""
        config = TUIConfig()
        config.set("key1", "value1")

        assert config.settings["key1"] == "value1"

    def test_set_nested_key_with_dot_notation(self):
        """Test setting nested keys with dot notation."""
        config = TUIConfig()
        config.set("general.log_level", "debug")

        assert config.settings == {"general": {"log_level": "debug"}}

    def test_set_deeply_nested_key(self):
        """Test setting deeply nested keys."""
        config = TUIConfig()
        config.set("a.b.c.d", "value")

        assert config.settings == {"a": {"b": {"c": {"d": "value"}}}}

    def test_get_all(self):
        """Test getting all settings."""
        config = TUIConfig()
        config.settings = {"key1": "value1", "key2": "value2"}

        all_settings = config.get_all()
        assert all_settings == {"key1": "value1", "key2": "value2"}
        # Should be a copy, not the original
        all_settings["key3"] = "value3"
        assert "key3" not in config.settings

    def test_update_simple(self):
        """Test updating settings with simple dict."""
        config = TUIConfig()
        config.settings = {"key1": "value1"}
        config.update({"key2": "value2"})

        assert config.settings == {"key1": "value1", "key2": "value2"}

    def test_update_nested(self):
        """Test updating with nested dicts merges correctly."""
        config = TUIConfig()
        config.settings = {
            "general": {"log_level": "info", "log_to_file": True},
            "migration": {"default_format": "qcow2"}
        }
        config.update({
            "general": {"log_level": "debug"},  # Should merge, not replace
            "vsphere": {"vcenter_host": "localhost"}  # New category
        })

        assert config.settings == {
            "general": {"log_level": "debug", "log_to_file": True},
            "migration": {"default_format": "qcow2"},
            "vsphere": {"vcenter_host": "localhost"}
        }


class TestDefaultSettings:
    """Tests for get_default_settings function."""

    def test_get_default_settings_structure(self):
        """Test default settings has expected structure."""
        defaults = get_default_settings()

        assert isinstance(defaults, dict)
        assert "general" in defaults
        assert "migration" in defaults
        assert "vsphere" in defaults
        assert "offline_fixes" in defaults
        assert "performance" in defaults
        assert "advanced" in defaults

    def test_general_settings_keys(self):
        """Test general settings has expected keys."""
        defaults = get_default_settings()
        general = defaults["general"]

        assert "default_output_dir" in general
        assert "log_level" in general
        assert "log_to_file" in general
        assert "log_file_path" in general

    def test_migration_settings_keys(self):
        """Test migration settings has expected keys."""
        defaults = get_default_settings()
        migration = defaults["migration"]

        assert "default_format" in migration
        assert "enable_compression" in migration
        assert "parallel_migrations" in migration
        assert "skip_existing" in migration

    def test_vsphere_settings_keys(self):
        """Test vSphere settings has expected keys."""
        defaults = get_default_settings()
        vsphere = defaults["vsphere"]

        assert "vcenter_host" in vsphere
        assert "vcenter_username" in vsphere
        assert "vcenter_save_credentials" in vsphere
        assert "vcenter_verify_ssl" in vsphere

    def test_offline_fixes_settings_keys(self):
        """Test offline fixes settings has expected keys."""
        defaults = get_default_settings()
        offline_fixes = defaults["offline_fixes"]

        assert "fstab_mode" in offline_fixes
        assert "regen_initramfs" in offline_fixes
        assert "update_grub" in offline_fixes
        assert "fix_network" in offline_fixes
        assert "enhanced_chroot" in offline_fixes

    def test_performance_settings_keys(self):
        """Test performance settings has expected keys."""
        defaults = get_default_settings()
        performance = defaults["performance"]

        assert "max_concurrent_operations" in performance
        assert "operation_timeout" in performance
        assert "network_timeout" in performance

    def test_advanced_settings_keys(self):
        """Test advanced settings has expected keys."""
        defaults = get_default_settings()
        advanced = defaults["advanced"]

        assert "guestfs_backend" in advanced
        assert "debug_mode" in advanced
        assert "verbose_output" in advanced

    def test_default_values_are_sensible(self):
        """Test default values are sensible."""
        defaults = get_default_settings()

        # General
        assert defaults["general"]["log_level"] in ["debug", "info", "warning", "error"]
        assert isinstance(defaults["general"]["log_to_file"], bool)

        # Migration
        assert defaults["migration"]["default_format"] in ["qcow2", "raw", "vdi", "vmdk"]
        assert isinstance(defaults["migration"]["enable_compression"], bool)
        assert defaults["migration"]["parallel_migrations"] > 0

        # Offline fixes
        assert defaults["offline_fixes"]["fstab_mode"] in ["stabilize-all", "stabilize-boot", "none"]
        assert isinstance(defaults["offline_fixes"]["regen_initramfs"], bool)

        # Performance
        assert defaults["performance"]["max_concurrent_operations"] > 0
        assert defaults["performance"]["operation_timeout"] > 0

        # Advanced
        assert defaults["advanced"]["guestfs_backend"] in ["vmcraft", "libguestfs"]


class TestConvenienceFunctions:
    """Tests for load_tui_settings and save_tui_settings convenience functions."""

    def test_load_tui_settings_with_defaults(self, tmp_path):
        """Test load_tui_settings merges with defaults."""
        config_path = tmp_path / "config.json"
        # Save minimal config
        config_path.write_text(json.dumps({"general": {"log_level": "debug"}}))

        settings = load_tui_settings(config_path=config_path)

        # Should have merged with defaults
        assert settings["general"]["log_level"] == "debug"  # From file
        assert "migration" in settings  # From defaults
        assert "vsphere" in settings  # From defaults

    def test_load_tui_settings_nonexistent_file_returns_defaults(self, tmp_path):
        """Test load_tui_settings returns defaults for nonexistent file."""
        config_path = tmp_path / "nonexistent.json"

        settings = load_tui_settings(config_path=config_path)

        # Should return defaults
        defaults = get_default_settings()
        assert settings == defaults

    def test_save_tui_settings(self, tmp_path):
        """Test save_tui_settings writes file."""
        config_path = tmp_path / "config.json"
        test_settings = {
            "general": {"log_level": "debug"},
            "migration": {"default_format": "raw"}
        }

        result = save_tui_settings(test_settings, config_path=config_path)

        assert result is True
        assert config_path.exists()

        # Verify content
        loaded = json.loads(config_path.read_text())
        assert loaded == test_settings

    def test_save_load_roundtrip_with_convenience_functions(self, tmp_path):
        """Test save and load roundtrip with convenience functions."""
        config_path = tmp_path / "config.json"
        test_settings = get_default_settings()
        test_settings["general"]["log_level"] = "debug"
        test_settings["migration"]["default_format"] = "vdi"

        # Save
        save_result = save_tui_settings(test_settings, config_path=config_path)
        assert save_result is True

        # Load
        loaded_settings = load_tui_settings(config_path=config_path)

        assert loaded_settings == test_settings


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_settings(self, tmp_path):
        """Test handling empty settings."""
        config_path = tmp_path / "empty.json"
        config = TUIConfig(config_path=config_path)

        result = config.save({})
        assert result is True

        loaded = config.load()
        assert loaded == {}

    def test_unicode_in_settings(self, tmp_path):
        """Test handling Unicode characters in settings."""
        config_path = tmp_path / "unicode.json"
        test_settings = {
            "general": {"default_output_dir": "/tmp/テスト"}
        }

        config = TUIConfig(config_path=config_path)
        config.save(test_settings)

        loaded_config = TUIConfig(config_path=config_path)
        loaded = loaded_config.load()

        assert loaded == test_settings

    def test_special_characters_in_paths(self, tmp_path):
        """Test handling special characters in file paths."""
        config_path = tmp_path / "config with spaces.json"
        test_settings = {"key": "value"}

        config = TUIConfig(config_path=config_path)
        result = config.save(test_settings)

        assert result is True
        assert config_path.exists()

    def test_deep_nesting(self):
        """Test handling deeply nested structures."""
        config = TUIConfig()
        config.set("a.b.c.d.e.f.g", "deep_value")

        assert config.get("a.b.c.d.e.f.g") == "deep_value"

    def test_update_with_none_values(self):
        """Test update doesn't break with None values."""
        config = TUIConfig()
        config.settings = {"key1": "value1"}
        config.update({"key1": None, "key2": "value2"})

        assert config.settings["key1"] is None
        assert config.settings["key2"] == "value2"
