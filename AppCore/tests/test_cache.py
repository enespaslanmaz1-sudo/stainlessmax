"""
Tests for Cache Manager Module
"""
import time


class TestMemoryCache:
    """Tests for MemoryCache class"""

    def test_set_and_get(self):
        """Test basic set and get operations"""
        from lib.cache_manager import MemoryCache

        cache = MemoryCache(max_size=10)

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent_key(self):
        """Test getting a key that doesn't exist"""
        from lib.cache_manager import MemoryCache

        cache = MemoryCache()
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        """Test that entries expire after TTL"""
        from lib.cache_manager import MemoryCache

        cache = MemoryCache()

        # Set with very short TTL
        cache.set("expiring_key", "value", ttl=0.1)

        # Should exist immediately
        assert cache.get("expiring_key") == "value"

        # Wait for expiration
        time.sleep(0.15)

        # Should be gone
        assert cache.get("expiring_key") is None

    def test_lru_eviction(self):
        """Test LRU eviction when at capacity"""
        from lib.cache_manager import MemoryCache

        cache = MemoryCache(max_size=3)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Access key1 to make it recently used
        cache.get("key1")

        # Add new key, should evict key2 (least recently used)
        cache.set("key4", "value4")

        assert cache.get("key1") == "value1"  # Still exists
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_delete(self):
        """Test deleting entries"""
        from lib.cache_manager import MemoryCache

        cache = MemoryCache()

        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None
        assert cache.delete("key1") is False  # Already deleted

    def test_clear(self):
        """Test clearing all entries"""
        from lib.cache_manager import MemoryCache

        cache = MemoryCache()

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_stats(self):
        """Test statistics tracking"""
        from lib.cache_manager import MemoryCache

        cache = MemoryCache(max_size=10)

        cache.set("key1", "value1")

        # Hit
        cache.get("key1")
        # Miss
        cache.get("nonexistent")

        stats = cache.get_stats()

        assert stats["hits"] >= 1
        assert stats["misses"] >= 1
        assert stats["size"] == 1

    def test_cleanup_expired(self):
        """Test cleanup of expired entries"""
        from lib.cache_manager import MemoryCache

        cache = MemoryCache()

        cache.set("expiring1", "value1", ttl=0.1)
        cache.set("expiring2", "value2", ttl=0.1)
        cache.set("long_lived", "value3", ttl=3600)

        time.sleep(0.15)

        removed = cache.cleanup_expired()

        assert removed == 2
        assert cache.get("long_lived") == "value3"


class TestDiskCache:
    """Tests for DiskCache class"""

    def test_set_and_get(self, temp_cache_dir):
        """Test basic set and get operations"""
        from lib.cache_manager import DiskCache

        cache = DiskCache(temp_cache_dir)

        cache.set("disk_key", {"data": "test"})
        result = cache.get("disk_key")

        assert result == {"data": "test"}

    def test_ttl_expiration(self, temp_cache_dir):
        """Test that entries expire after TTL"""
        from lib.cache_manager import DiskCache

        cache = DiskCache(temp_cache_dir)

        cache.set("expiring", "value", ttl=0.1)

        time.sleep(0.15)

        assert cache.get("expiring") is None

    def test_delete(self, temp_cache_dir):
        """Test deleting entries"""
        from lib.cache_manager import DiskCache

        cache = DiskCache(temp_cache_dir)

        cache.set("to_delete", "value")
        assert cache.delete("to_delete") is True
        assert cache.get("to_delete") is None

    def test_persistence(self, temp_cache_dir):
        """Test that cache persists across instances"""
        from lib.cache_manager import DiskCache

        # First instance
        cache1 = DiskCache(temp_cache_dir)
        cache1.set("persistent", "value", ttl=3600)

        # Second instance (simulating restart)
        cache2 = DiskCache(temp_cache_dir)

        assert cache2.get("persistent") == "value"


class TestCacheManager:
    """Tests for CacheManager class"""

    def test_initialization(self, temp_cache_dir):
        """Test cache manager initialization"""
        from lib.cache_manager import CacheManager

        manager = CacheManager(temp_cache_dir)

        assert manager._memory is not None
        assert manager._disk is not None

    def test_memory_only_get_set(self):
        """Test memory-only operations"""
        from lib.cache_manager import CacheManager

        manager = CacheManager()

        manager.set("mem_key", "mem_value")
        assert manager.get("mem_key") == "mem_value"

    def test_persist_to_disk(self, temp_cache_dir):
        """Test persisting to disk"""
        from lib.cache_manager import CacheManager

        manager = CacheManager(temp_cache_dir)

        manager.set("persist_key", "persist_value", persist=True)

        # Clear memory
        manager._memory.clear()

        # Should still get from disk
        assert manager.get("persist_key", use_disk=True) == "persist_value"

    def test_viral_trends_caching(self):
        """Test viral trends convenience methods"""
        from lib.cache_manager import CacheManager

        manager = CacheManager()

        trends = [{"title": "Trend 1"}, {"title": "Trend 2"}]

        manager.cache_viral_trends("youtube", trends)
        cached = manager.get_viral_trends("youtube")

        assert cached == trends

    def test_api_response_caching(self):
        """Test API response convenience methods"""
        from lib.cache_manager import CacheManager

        manager = CacheManager()

        response_data = {"results": [1, 2, 3]}

        manager.cache_api_response("pexels", "videos/search", response_data)
        cached = manager.get_api_response("pexels", "videos/search")

        assert cached == response_data


class TestCacheDecorator:
    """Tests for cached decorator"""

    def test_decorator_caches_result(self):
        """Test that decorator caches function results"""
        from lib.cache_manager import cached

        call_count = 0

        @cached("test_func", ttl=60)
        def expensive_function(arg):
            nonlocal call_count
            call_count += 1
            return f"result_{arg}"

        # First call
        result1 = expensive_function("a")
        assert result1 == "result_a"
        assert call_count == 1

        # Second call - should use cache
        result2 = expensive_function("a")
        assert result2 == "result_a"
        assert call_count == 1  # Not incremented

        # Different arg - should call function
        result3 = expensive_function("b")
        assert result3 == "result_b"
        assert call_count == 2
