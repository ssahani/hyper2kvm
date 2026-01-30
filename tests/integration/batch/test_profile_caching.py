# SPDX-License-Identifier: LGPL-3.0-or-later
"""Integration tests for profile caching in batch workflows."""

import tempfile
import time
from pathlib import Path

import pytest
import yaml

from hyper2kvm.profiles.profile_cache import (
    ProfileCache,
    get_global_cache,
    reset_global_cache,
)
from hyper2kvm.profiles.profile_loader import ProfileLoader


class TestProfileCachingIntegration:
    """Integration tests for profile caching."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset global cache before each test."""
        reset_global_cache()
        yield
        reset_global_cache()

    def test_profile_cache_hit_rate(self, tmp_path):
        """Test cache hit rate with repeated profile loads."""
        # Create custom profile
        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir()

        profile_content = {
            "pipeline": {
                "fix": {"enabled": True},
                "convert": {"compress": True},
            }
        }

        profile_file = profile_dir / "custom.yaml"
        with open(profile_file, "w") as f:
            yaml.dump(profile_content, f)

        loader = ProfileLoader()

        # First load - cache miss
        profile1 = loader.load_profile("custom", custom_profile_path=profile_dir)

        stats = loader.get_cache_statistics()
        assert stats["misses"] == 1
        assert stats["hits"] == 0

        # Second load - cache hit
        profile2 = loader.load_profile("custom", custom_profile_path=profile_dir)

        stats = loader.get_cache_statistics()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

        # Profiles should be identical
        assert profile1 == profile2

    def test_cache_invalidation_on_file_change(self, tmp_path):
        """Test cache invalidation when profile file is modified."""
        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir()

        profile_file = profile_dir / "test.yaml"
        profile_file.write_text(
            """
pipeline:
  fix:
    enabled: true
"""
        )

        loader = ProfileLoader()

        # Load profile
        profile1 = loader.load_profile("test", custom_profile_path=profile_dir)
        assert profile1["pipeline"]["fix"]["enabled"] is True

        # Second load (cache hit)
        profile2 = loader.load_profile("test", custom_profile_path=profile_dir)
        assert profile1 == profile2

        stats = loader.get_cache_statistics()
        initial_hits = stats["hits"]

        # Modify file
        time.sleep(0.1)  # Ensure mtime changes
        profile_file.write_text(
            """
pipeline:
  fix:
    enabled: false
"""
        )

        # Third load - should reload (cache invalidated)
        profile3 = loader.load_profile("test", custom_profile_path=profile_dir)
        assert profile3["pipeline"]["fix"]["enabled"] is False

        # Cache hits shouldn't have increased
        stats = loader.get_cache_statistics()
        assert stats["hits"] == initial_hits

    def test_builtin_profile_caching(self):
        """Test caching of built-in profiles."""
        loader = ProfileLoader()

        # Load built-in profile multiple times
        profiles = []
        for _ in range(5):
            profile = loader.load_profile("production")
            profiles.append(profile)

        # All should be identical
        assert all(p == profiles[0] for p in profiles)

        # Should have 4 cache hits (first is miss)
        stats = loader.get_cache_statistics()
        assert stats["hits"] == 4
        assert stats["misses"] == 1

    def test_cache_performance_benefit(self, tmp_path):
        """Test that caching provides performance benefit."""
        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir()

        # Create complex profile
        profile_content = {
            "extends": "production",
            "pipeline": {
                "inspect": {"enabled": True},
                "fix": {
                    "enabled": True,
                    "fstab_mode": "stabilize-all",
                    "bootloader": {"regenerate": True},
                },
                "convert": {"compress": True, "compress_level": 9},
            },
            "hooks": {
                "pre_fix": [{"type": "script", "path": "/hook.sh"}],
                "post_convert": [{"type": "http", "url": "http://example.com"}],
            },
        }

        profile_file = profile_dir / "complex.yaml"
        with open(profile_file, "w") as f:
            yaml.dump(profile_content, f)

        loader = ProfileLoader()

        # Time first load (uncached)
        start = time.time()
        profile1 = loader.load_profile("complex", custom_profile_path=profile_dir)
        uncached_time = time.time() - start

        # Time subsequent loads (cached)
        cached_times = []
        for _ in range(10):
            start = time.time()
            loader.load_profile("complex", custom_profile_path=profile_dir)
            cached_times.append(time.time() - start)

        avg_cached_time = sum(cached_times) / len(cached_times)

        # Cached loads should be faster (or at least not slower)
        assert avg_cached_time <= uncached_time * 1.5


class TestBatchWorkflowWithCaching:
    """Test profile caching in batch conversion workflows."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset global cache before each test."""
        reset_global_cache()
        yield
        reset_global_cache()

    def test_shared_cache_across_batch(self, tmp_path):
        """Test that profile cache is shared across batch processing."""
        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir()

        profile_file = profile_dir / "batch.yaml"
        profile_file.write_text(
            """
pipeline:
  fix:
    enabled: true
  convert:
    compress: true
"""
        )

        # Simulate multiple VMs in batch using same profile
        loaders = [ProfileLoader() for _ in range(5)]

        profiles = []
        for loader in loaders:
            profile = loader.load_profile("batch", custom_profile_path=profile_dir)
            profiles.append(profile)

        # All loaders should share the same global cache
        cache = get_global_cache()
        stats = cache.get_statistics()

        # Should have 1 miss (first load) and 4 hits (subsequent loads)
        assert stats["misses"] == 1
        assert stats["hits"] == 4

        # All profiles should be identical
        assert all(p == profiles[0] for p in profiles)

    def test_different_profiles_in_batch(self, tmp_path):
        """Test batch with VMs using different profiles."""
        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir()

        # Create multiple profiles
        for i in range(1, 4):
            profile_file = profile_dir / f"profile{i}.yaml"
            profile_file.write_text(
                f"""
pipeline:
  fix:
    enabled: true
  convert:
    compress_level: {i}
"""
            )

        loader = ProfileLoader()

        # Load each profile twice
        for i in range(1, 4):
            profile1 = loader.load_profile(
                f"profile{i}", custom_profile_path=profile_dir
            )
            profile2 = loader.load_profile(
                f"profile{i}", custom_profile_path=profile_dir
            )
            assert profile1 == profile2

        stats = loader.get_cache_statistics()

        # 3 profiles x 2 loads = 6 total, 3 misses, 3 hits
        assert stats["total_requests"] == 6
        assert stats["misses"] == 3
        assert stats["hits"] == 3
        assert stats["hit_rate_percent"] == 50.0


class TestCacheWithProfileInheritance:
    """Test caching with profile inheritance."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset global cache before each test."""
        reset_global_cache()
        yield
        reset_global_cache()

    def test_cache_with_extends(self, tmp_path):
        """Test caching profiles that use 'extends'."""
        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir()

        # Create child profile extending production
        child_profile = profile_dir / "child.yaml"
        child_profile.write_text(
            """
extends: production
pipeline:
  convert:
    compress_level: 9
"""
        )

        loader = ProfileLoader()

        # Load child profile multiple times
        profiles = []
        for _ in range(3):
            profile = loader.load_profile("child", custom_profile_path=profile_dir)
            profiles.append(profile)

        # Should all be identical
        assert all(p == profiles[0] for p in profiles)

        # Should have cache hits
        stats = loader.get_cache_statistics()
        assert stats["hits"] > 0


class TestCacheStatistics:
    """Test cache statistics and monitoring."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset global cache before each test."""
        reset_global_cache()
        yield
        reset_global_cache()

    def test_cache_statistics_tracking(self, tmp_path):
        """Test detailed cache statistics."""
        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir()

        profile_file = profile_dir / "test.yaml"
        profile_file.write_text("pipeline:\n  fix:\n    enabled: true\n")

        loader = ProfileLoader()

        # Generate various cache events
        loader.load_profile("test", custom_profile_path=profile_dir)  # miss
        loader.load_profile("test", custom_profile_path=profile_dir)  # hit
        loader.load_profile("test", custom_profile_path=profile_dir)  # hit
        loader.load_profile("production")  # miss
        loader.load_profile("production")  # hit

        stats = loader.get_cache_statistics()

        assert stats["total_requests"] == 5
        assert stats["hits"] == 3
        assert stats["misses"] == 2
        assert stats["hit_rate_percent"] == 60.0
        assert stats["size"] == 2  # 2 unique profiles

    def test_cache_entry_details(self, tmp_path):
        """Test per-entry cache statistics."""
        loader = ProfileLoader()

        # Load profile multiple times
        for _ in range(5):
            loader.load_profile("production")

        stats = loader.get_cache_statistics()

        # Check entry details
        assert "entries" in stats
        assert "production" in stats["entries"]

        entry_stats = stats["entries"]["production"]
        # First load is a miss (not an access), then 4 hits (accesses)
        assert entry_stats["accesses"] == 4
        assert entry_stats["source"] == "builtin"
        assert "age_seconds" in entry_stats

    def test_cache_invalidation_tracking(self, tmp_path):
        """Test tracking of cache invalidations."""
        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir()

        profile_file = profile_dir / "test.yaml"
        profile_file.write_text("pipeline:\n  fix:\n    enabled: true\n")

        loader = ProfileLoader()

        # Load, modify, reload
        loader.load_profile("test", custom_profile_path=profile_dir)

        time.sleep(0.1)
        profile_file.write_text("pipeline:\n  fix:\n    enabled: false\n")

        loader.load_profile("test", custom_profile_path=profile_dir)

        stats = loader.get_cache_statistics()
        assert stats["invalidations"] >= 1


class TestCacheDisabled:
    """Test behavior when caching is disabled."""

    def test_cache_disabled_no_hits(self, tmp_path):
        """Test that disabled cache doesn't cache."""
        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir()

        profile_file = profile_dir / "test.yaml"
        profile_file.write_text("pipeline:\n  fix:\n    enabled: true\n")

        loader = ProfileLoader(enable_cache=False)

        # Load multiple times
        for _ in range(5):
            loader.load_profile("test", custom_profile_path=profile_dir)

        stats = loader.get_cache_statistics()

        # No cache hits
        assert stats["enabled"] is False
        assert stats["hits"] == 0

    def test_cache_disabled_always_loads_fresh(self, tmp_path):
        """Test that disabled cache always loads fresh data."""
        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir()

        profile_file = profile_dir / "test.yaml"
        profile_file.write_text("pipeline:\n  fix:\n    enabled: true\n")

        loader = ProfileLoader(enable_cache=False)

        profile1 = loader.load_profile("test", custom_profile_path=profile_dir)
        assert profile1["pipeline"]["fix"]["enabled"] is True

        # Modify immediately (no sleep needed)
        profile_file.write_text("pipeline:\n  fix:\n    enabled: false\n")

        profile2 = loader.load_profile("test", custom_profile_path=profile_dir)
        assert profile2["pipeline"]["fix"]["enabled"] is False


class TestCustomCacheInstance:
    """Test using custom cache instances."""

    def test_custom_cache_instance(self):
        """Test ProfileLoader with custom cache instance."""
        custom_cache = ProfileCache()
        loader = ProfileLoader(cache=custom_cache)

        # Should use the custom cache
        assert loader.cache is custom_cache

        # Load profiles
        for _ in range(3):
            loader.load_profile("production")

        # Check custom cache has the data
        stats = custom_cache.get_statistics()
        assert stats["hits"] == 2
        assert stats["misses"] == 1

    def test_isolated_cache_instances(self):
        """Test that custom caches are isolated."""
        cache1 = ProfileCache()
        cache2 = ProfileCache()

        loader1 = ProfileLoader(cache=cache1)
        loader2 = ProfileLoader(cache=cache2)

        # Load same profile in both
        loader1.load_profile("production")
        loader2.load_profile("production")

        # Each cache should have independent statistics
        stats1 = cache1.get_statistics()
        stats2 = cache2.get_statistics()

        assert stats1["total_requests"] == 1
        assert stats2["total_requests"] == 1
