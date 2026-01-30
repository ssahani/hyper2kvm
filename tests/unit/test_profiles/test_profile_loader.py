# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for profile loader."""

import tempfile
from pathlib import Path

import pytest
import yaml

from hyper2kvm.profiles.profile_loader import ProfileLoader


class TestProfileLoader:
    """Test ProfileLoader functionality."""

    def test_load_builtin_production_profile(self):
        """Test loading built-in production profile."""
        loader = ProfileLoader()
        profile = loader.load_profile("production")

        assert "pipeline" in profile
        assert profile["pipeline"]["fix"]["enabled"] is True
        assert profile["pipeline"]["convert"]["enabled"] is True
        assert profile["pipeline"]["convert"]["compress"] is True
        assert profile["output"]["format"] == "qcow2"

    def test_load_builtin_testing_profile(self):
        """Test loading built-in testing profile with inheritance."""
        loader = ProfileLoader()
        profile = loader.load_profile("testing")

        # Should have base from production
        assert profile["pipeline"]["fix"]["enabled"] is True
        # But overrides some settings
        assert profile["pipeline"]["convert"]["compress"] is False
        assert profile["pipeline"]["validate"]["enabled"] is False
        assert profile["output"]["format"] == "qcow2"  # Testing still uses qcow2

    def test_load_builtin_minimal_profile(self):
        """Test loading built-in minimal profile."""
        loader = ProfileLoader()
        profile = loader.load_profile("minimal")

        assert profile["pipeline"]["fix"]["enabled"] is True
        assert profile["pipeline"]["fix"]["regen_initramfs"] is False
        assert profile["pipeline"]["convert"]["enabled"] is False
        assert profile["pipeline"]["validate"]["enabled"] is False

    def test_load_builtin_fast_profile(self):
        """Test loading built-in fast profile."""
        loader = ProfileLoader()
        profile = loader.load_profile("fast")

        assert profile["pipeline"]["fix"]["backup"] is False
        assert profile["pipeline"]["fix"]["update_grub"] is False
        assert profile["pipeline"]["convert"]["compress"] is False
        assert profile["pipeline"]["validate"]["enabled"] is False

    def test_load_builtin_windows_profile(self):
        """Test loading built-in windows profile."""
        loader = ProfileLoader()
        profile = loader.load_profile("windows")

        assert profile["pipeline"]["fix"]["enabled"] is True  # Windows profile enables fixes
        assert profile["pipeline"]["fix"]["update_grub"] is False  # But skips GRUB
        assert profile["pipeline"]["fix"]["regen_initramfs"] is False  # And initramfs
        assert profile["pipeline"]["convert"]["enabled"] is True
        assert profile["output"]["format"] == "qcow2"

    def test_profile_not_found(self):
        """Test that non-existent profile raises error."""
        from hyper2kvm.profiles.profile_loader import ProfileLoadError

        loader = ProfileLoader()
        with pytest.raises(ProfileLoadError, match="Profile 'nonexistent' not found"):
            loader.load_profile("nonexistent")

    def test_custom_profile_loading(self):
        """Test loading a custom profile from directory."""
        custom_profile = {
            "extends": "production",
            "pipeline": {
                "convert": {"compress_level": 9},
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            custom_path = Path(tmpdir) / "custom.yaml"
            with open(custom_path, "w") as f:
                yaml.dump(custom_profile, f)

            loader = ProfileLoader()
            profile = loader.load_profile("custom", Path(tmpdir))

            # Should inherit from production
            assert profile["pipeline"]["fix"]["enabled"] is True
            # Should have custom override
            assert profile["pipeline"]["convert"]["compress_level"] == 9

    def test_circular_inheritance_detection(self):
        """Test that circular inheritance is detected."""
        from hyper2kvm.profiles.profile_loader import ProfileLoadError

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create profile A that extends B
            profile_a = {"extends": "profile_b"}
            profile_b = {"extends": "profile_a"}

            with open(Path(tmpdir) / "profile_a.yaml", "w") as f:
                yaml.dump(profile_a, f)
            with open(Path(tmpdir) / "profile_b.yaml", "w") as f:
                yaml.dump(profile_b, f)

            loader = ProfileLoader()
            with pytest.raises(ProfileLoadError, match="Circular inheritance detected"):
                loader.load_profile("profile_a", Path(tmpdir))

    def test_deep_inheritance_chain(self):
        """Test multiple levels of inheritance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create chain: custom -> intermediate -> production
            intermediate = {
                "extends": "production",
                "pipeline": {"convert": {"compress_level": 7}},
            }
            custom = {
                "extends": "intermediate",
                "pipeline": {"fix": {"backup": False}},
            }

            with open(Path(tmpdir) / "intermediate.yaml", "w") as f:
                yaml.dump(intermediate, f)
            with open(Path(tmpdir) / "custom.yaml", "w") as f:
                yaml.dump(custom, f)

            loader = ProfileLoader()
            profile = loader.load_profile("custom", Path(tmpdir))

            # Should have base from production
            assert profile["pipeline"]["convert"]["enabled"] is True
            # Should have intermediate override
            assert profile["pipeline"]["convert"]["compress_level"] == 7
            # Should have custom override
            assert profile["pipeline"]["fix"]["backup"] is False

    def test_profile_without_extends(self):
        """Test loading profile without inheritance."""
        standalone = {
            "pipeline": {
                "fix": {"enabled": False},
                "convert": {"enabled": True},
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with open(Path(tmpdir) / "standalone.yaml", "w") as f:
                yaml.dump(standalone, f)

            loader = ProfileLoader()
            profile = loader.load_profile("standalone", Path(tmpdir))

            assert profile == standalone

    def test_list_builtin_profiles(self):
        """Test listing available profiles."""
        loader = ProfileLoader()
        profiles = loader.list_builtin_profiles()

        # Should include all built-in profiles
        assert "production" in profiles
        assert "testing" in profiles
        assert "minimal" in profiles
        assert "fast" in profiles
        assert "windows" in profiles
        assert "archive" in profiles
        assert "debug" in profiles
        assert len(profiles) == 7

    def test_list_available_with_custom(self):
        """Test listing profiles including custom ones."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create custom profiles
            for name in ["custom1", "custom2"]:
                with open(Path(tmpdir) / f"{name}.yaml", "w") as f:
                    yaml.dump({"pipeline": {}}, f)

            loader = ProfileLoader()
            profiles = loader.list_builtin_profiles(Path(tmpdir))

            # Should include built-in + custom
            assert "production" in profiles
            assert "custom1" in profiles
            assert "custom2" in profiles
            assert len(profiles) >= 9  # 7 built-in + 2 custom

    def test_merge_with_none_values(self):
        """Test that None values don't override in merging."""
        base = {"pipeline": {"fix": {"enabled": True, "backup": True}}}
        override = {"pipeline": {"fix": {"backup": False}}}

        with tempfile.TemporaryDirectory() as tmpdir:
            with open(Path(tmpdir) / "base.yaml", "w") as f:
                yaml.dump(base, f)
            with open(Path(tmpdir) / "override.yaml", "w") as f:
                yaml.dump({"extends": "base", **override}, f)

            loader = ProfileLoader()
            profile = loader.load_profile("override", Path(tmpdir))

            assert profile["pipeline"]["fix"]["enabled"] is True  # from base
            assert profile["pipeline"]["fix"]["backup"] is False  # override

    def test_invalid_yaml_syntax(self):
        """Test that invalid YAML syntax is caught."""
        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_path = Path(tmpdir) / "invalid.yaml"
            with open(invalid_path, "w") as f:
                f.write("invalid: yaml: syntax: :")

            loader = ProfileLoader()
            with pytest.raises(Exception):  # YAML parse error
                loader.load_profile("invalid", Path(tmpdir))
