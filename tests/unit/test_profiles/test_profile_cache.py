# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for ProfileCache."""

import tempfile
import time
from pathlib import Path

import pytest

from hyper2kvm.profiles.profile_cache import (
    ProfileCache,
    ProfileCacheEntry,
    get_global_cache,
    reset_global_cache,
)


class TestProfileCacheEntry:
    """Test ProfileCacheEntry functionality."""

    def test_entry_creation(self):
        """Test cache entry creation."""
        profile_data = {"pipeline": {"fix": {"enabled": True}}}
        entry = ProfileCacheEntry(profile_data)

        assert entry.profile_data == profile_data
        assert entry.mtime is None
        assert entry.source_path is None
        assert entry.access_count == 0

    def test_entry_with_file_metadata(self, tmp_path):
        """Test cache entry with file metadata."""
        # Create test file
        test_file = tmp_path / "test.yaml"
        test_file.write_text("test: true")
        mtime = test_file.stat().st_mtime

        profile_data = {"test": True}
        entry = ProfileCacheEntry(profile_data, mtime=mtime, source_path=test_file)

        assert entry.mtime == mtime
        assert entry.source_path == test_file

    def test_builtin_entry_always_valid(self):
        """Test that built-in entries (no source path) are always valid."""
        entry = ProfileCacheEntry({"test": True})
        assert entry.is_valid()

    def test_custom_entry_valid_when_file_unchanged(self, tmp_path):
        """Test custom entry is valid when file unchanged."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("test: true")
        mtime = test_file.stat().st_mtime

        entry = ProfileCacheEntry({"test": True}, mtime=mtime, source_path=test_file)
        assert entry.is_valid()

    def test_custom_entry_invalid_when_file_modified(self, tmp_path):
        """Test custom entry is invalid when file modified."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("test: true")
        mtime = test_file.stat().st_mtime

        entry = ProfileCacheEntry({"test": True}, mtime=mtime, source_path=test_file)

        # Modify file
        time.sleep(0.1)  # Ensure mtime changes
        test_file.write_text("test: false")

        assert not entry.is_valid()

    def test_custom_entry_invalid_when_file_deleted(self, tmp_path):
        """Test custom entry is invalid when file deleted."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("test: true")
        mtime = test_file.stat().st_mtime

        entry = ProfileCacheEntry({"test": True}, mtime=mtime, source_path=test_file)

        # Delete file
        test_file.unlink()

        assert not entry.is_valid()

    def test_entry_access_tracking(self):
        """Test that accesses are tracked."""
        entry = ProfileCacheEntry({"test": True})

        assert entry.access_count == 0

        data1 = entry.access()
        assert entry.access_count == 1
        assert data1 == {"test": True}

        data2 = entry.access()
        assert entry.access_count == 2

    def test_entry_repr(self):
        """Test entry string representation."""
        entry = ProfileCacheEntry({"test": True})
        repr_str = repr(entry)

        assert "ProfileCacheEntry" in repr_str
        assert "builtin" in repr_str
        assert "accesses=0" in repr_str


class TestProfileCache:
    """Test ProfileCache functionality."""

    def test_cache_creation(self):
        """Test cache creation."""
        cache = ProfileCache()
        assert cache.enabled is True

        stats = cache.get_statistics()
        assert stats["enabled"] is True
        assert stats["size"] == 0

    def test_cache_disabled(self):
        """Test cache with caching disabled."""
        cache = ProfileCache(enabled=False)
        assert cache.enabled is False

        # Put and get should not work when disabled
        cache.put("test", {"data": True})
        assert cache.get("test") is None

        stats = cache.get_statistics()
        assert stats["enabled"] is False

    def test_cache_put_and_get(self):
        """Test basic put and get operations."""
        cache = ProfileCache()

        profile_data = {"pipeline": {"fix": {"enabled": True}}}
        cache.put("production", profile_data)

        retrieved = cache.get("production")
        assert retrieved == profile_data

    def test_cache_get_miss(self):
        """Test cache miss."""
        cache = ProfileCache()

        result = cache.get("nonexistent")
        assert result is None

        stats = cache.get_statistics()
        assert stats["misses"] == 1
        assert stats["hits"] == 0

    def test_cache_get_hit(self):
        """Test cache hit."""
        cache = ProfileCache()

        cache.put("test", {"data": True})

        # First get
        result1 = cache.get("test")
        assert result1 == {"data": True}

        # Second get (cache hit)
        result2 = cache.get("test")
        assert result2 == {"data": True}

        stats = cache.get_statistics()
        assert stats["hits"] == 2
        assert stats["misses"] == 0

    def test_cache_invalidation_on_file_change(self, tmp_path):
        """Test that cache invalidates when file changes."""
        cache = ProfileCache()

        # Create test file
        test_file = tmp_path / "test.yaml"
        test_file.write_text("test: true")

        # Cache profile with file metadata
        cache.put("test", {"test": True}, source_path=test_file)

        # Get should work
        assert cache.get("test") == {"test": True}

        # Modify file
        time.sleep(0.1)  # Ensure mtime changes
        test_file.write_text("test: false")

        # Get should return None (invalidated)
        assert cache.get("test") is None

        stats = cache.get_statistics()
        assert stats["invalidations"] == 1

    def test_cache_invalidate_method(self):
        """Test manual invalidation."""
        cache = ProfileCache()

        cache.put("test", {"data": True})
        assert cache.get("test") == {"data": True}

        # Invalidate
        result = cache.invalidate("test")
        assert result is True

        # Should be gone
        assert cache.get("test") is None

        # Invalidating again should return False
        result = cache.invalidate("test")
        assert result is False

    def test_cache_clear(self):
        """Test cache clearing."""
        cache = ProfileCache()

        cache.put("profile1", {"data": 1})
        cache.put("profile2", {"data": 2})
        cache.put("profile3", {"data": 3})

        assert cache.get_statistics()["size"] == 3

        cache.clear()

        assert cache.get_statistics()["size"] == 0
        assert cache.get("profile1") is None

    def test_cache_statistics(self):
        """Test cache statistics tracking."""
        cache = ProfileCache()

        # Initial stats
        stats = cache.get_statistics()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0

        # Add profiles
        cache.put("profile1", {"data": 1})
        cache.put("profile2", {"data": 2})

        # Generate hits and misses
        cache.get("profile1")  # hit
        cache.get("profile1")  # hit
        cache.get("profile2")  # hit
        cache.get("nonexistent")  # miss

        stats = cache.get_statistics()
        assert stats["hits"] == 3
        assert stats["misses"] == 1
        assert stats["size"] == 2
        assert stats["total_requests"] == 4
        assert stats["hit_rate_percent"] == 75.0

    def test_cache_entry_details_in_statistics(self):
        """Test that statistics include entry details."""
        cache = ProfileCache()

        cache.put("test", {"data": True})
        cache.get("test")  # Access once

        stats = cache.get_statistics()
        assert "entries" in stats
        assert "test" in stats["entries"]

        entry_stats = stats["entries"]["test"]
        assert entry_stats["accesses"] == 1
        assert entry_stats["source"] == "builtin"
        assert "age_seconds" in entry_stats

    def test_cache_thread_safety(self):
        """Test basic thread safety (no crashes)."""
        import threading

        cache = ProfileCache()

        def worker():
            for i in range(100):
                cache.put(f"profile{i % 10}", {"data": i})
                cache.get(f"profile{i % 10}")

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should complete without errors
        stats = cache.get_statistics()
        assert stats["size"] <= 10  # Only 10 unique profiles

    def test_cache_repr(self):
        """Test cache string representation."""
        cache = ProfileCache()
        cache.put("test", {"data": True})
        cache.get("test")

        repr_str = repr(cache)
        assert "ProfileCache" in repr_str
        assert "enabled=True" in repr_str


class TestGlobalCache:
    """Test global cache functionality."""

    def test_get_global_cache(self):
        """Test getting global cache instance."""
        # Reset first
        reset_global_cache()

        cache1 = get_global_cache()
        cache2 = get_global_cache()

        # Should be the same instance
        assert cache1 is cache2

    def test_reset_global_cache(self):
        """Test resetting global cache."""
        reset_global_cache()

        cache1 = get_global_cache()
        cache1.put("test", {"data": True})

        reset_global_cache()

        cache2 = get_global_cache()
        # Should be a new instance
        assert cache2 is not cache1
        # Should not have the previous data
        assert cache2.get("test") is None

    def test_global_cache_shared_across_loaders(self):
        """Test that global cache is shared across multiple loaders."""
        from hyper2kvm.profiles import ProfileLoader

        reset_global_cache()

        # Two loaders using global cache
        loader1 = ProfileLoader()
        loader2 = ProfileLoader()

        # They should share the same cache
        assert loader1.cache is loader2.cache

    def test_global_cache_disabled(self):
        """Test creating global cache with caching disabled."""
        reset_global_cache()

        cache = get_global_cache(enabled=False)
        assert cache.enabled is False


class TestProfileCacheIntegration:
    """Test ProfileCache integration with ProfileLoader."""

    def test_profile_loader_uses_cache(self):
        """Test that ProfileLoader uses cache."""
        from hyper2kvm.profiles import ProfileLoader

        reset_global_cache()

        loader = ProfileLoader()

        # Load profile twice
        profile1 = loader.load_profile("production")
        profile2 = loader.load_profile("production")

        # Should be identical
        assert profile1 == profile2

        # Check cache statistics
        stats = loader.get_cache_statistics()
        assert stats["hits"] == 1  # Second load was cache hit
        assert stats["misses"] == 1  # First load was cache miss

    def test_profile_loader_cache_disabled(self):
        """Test ProfileLoader with cache disabled."""
        from hyper2kvm.profiles import ProfileLoader

        loader = ProfileLoader(enable_cache=False)

        # Load profile twice
        loader.load_profile("production")
        loader.load_profile("production")

        # No cache hits since caching disabled
        stats = loader.get_cache_statistics()
        assert stats["hits"] == 0
        assert stats["enabled"] is False

    def test_custom_cache_instance(self):
        """Test ProfileLoader with custom cache instance."""
        from hyper2kvm.profiles import ProfileLoader

        custom_cache = ProfileCache()
        loader = ProfileLoader(cache=custom_cache)

        # Should use the custom cache
        assert loader.cache is custom_cache

    def test_cache_invalidation_on_custom_profile_change(self, tmp_path):
        """Test cache invalidation when custom profile file changes."""
        from hyper2kvm.profiles import ProfileLoader

        # Create custom profile
        custom_dir = tmp_path / "profiles"
        custom_dir.mkdir()
        profile_file = custom_dir / "custom.yaml"
        profile_file.write_text("""
pipeline:
  fix:
    enabled: true
""")

        loader = ProfileLoader()

        # Load profile
        profile1 = loader.load_profile("custom", custom_profile_path=custom_dir)
        assert profile1["pipeline"]["fix"]["enabled"] is True

        # Second load should use cache
        profile2 = loader.load_profile("custom", custom_profile_path=custom_dir)
        assert profile1 == profile2

        stats = loader.get_cache_statistics()
        initial_hits = stats["hits"]

        # Modify file
        time.sleep(0.1)  # Ensure mtime changes
        profile_file.write_text("""
pipeline:
  fix:
    enabled: false
""")

        # Load again - should reload from disk (cache invalidated)
        profile3 = loader.load_profile("custom", custom_profile_path=custom_dir)
        assert profile3["pipeline"]["fix"]["enabled"] is False

        # Hits shouldn't have increased (cache was invalidated)
        stats = loader.get_cache_statistics()
        assert stats["hits"] == initial_hits  # No new hit
