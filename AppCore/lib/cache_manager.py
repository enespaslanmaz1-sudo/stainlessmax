"""
Cache Manager Module
Memory and disk-based caching with TTL support
"""
import time
import json
import hashlib
import threading
from pathlib import Path
from typing import Any, Optional, Dict
from dataclasses import dataclass, field
from collections import OrderedDict
from .logger import logger


@dataclass
class CacheEntry:
    """Single cache entry with TTL"""
    value: Any
    created_at: float = field(default_factory=time.time)
    ttl: float = 3600  # Default 1 hour
    hits: int = 0

    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl


class MemoryCache:
    """
    LRU Memory Cache with TTL support.
    Thread-safe implementation.
    """

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
        }

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats["misses"] += 1
                return None

            if entry.is_expired():
                del self._cache[key]
                self._stats["misses"] += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.hits += 1
            self._stats["hits"] += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: float = 3600):
        """Set value in cache"""
        with self._lock:
            # Remove oldest if at capacity
            while len(self._cache) >= self.max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                self._stats["evictions"] += 1

            self._cache[key] = CacheEntry(value=value, ttl=ttl)

    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self):
        """Clear all entries"""
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of removed entries."""
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)

    def get_stats(self) -> Dict:
        """Get cache statistics"""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0
            return {
                **self._stats,
                "size": len(self._cache),
                "max_size": self.max_size,
                "hit_rate": f"{hit_rate:.1f}%",
            }


class DiskCache:
    """
    Disk-based cache for persistence.
    Uses JSON serialization.
    """

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True)
        self._index_file = cache_dir / "_index.json"
        self._index: Dict[str, float] = {}  # key -> expiry_timestamp
        self._lock = threading.Lock()
        self._load_index()

    def _load_index(self):
        """Load cache index from disk"""
        if self._index_file.exists():
            try:
                with open(self._index_file, "r", encoding="utf-8") as f:
                    self._index = json.load(f)
            except Exception as e:
                logger.warning(f"[CACHE] Failed to load index: {e}")
                self._index = {}

    def _save_index(self):
        """Save cache index to disk"""
        try:
            with open(self._index_file, "w", encoding="utf-8") as f:
                json.dump(self._index, f)
        except Exception as e:
            logger.error(f"[CACHE] Failed to save index: {e}")

    def _key_to_filename(self, key: str) -> Path:
        """Convert key to safe filename"""
        hash_key = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{hash_key}.json"

    def get(self, key: str) -> Optional[Any]:
        """Get value from disk cache"""
        with self._lock:
            if key not in self._index:
                return None

            # Check expiry
            if time.time() > self._index[key]:
                filepath = self._key_to_filename(key)
                del self._index[key]
                filepath.unlink(missing_ok=True)
                self._save_index()
                return None

            filepath = self._key_to_filename(key)
            if not filepath.exists():
                del self._index[key]
                return None

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[CACHE] Failed to read {key}: {e}")
                return None

    def set(self, key: str, value: Any, ttl: float = 3600):
        """Set value in disk cache"""
        with self._lock:
            filepath = self._key_to_filename(key)
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(value, f, ensure_ascii=False)
                self._index[key] = time.time() + ttl
                self._save_index()
            except Exception as e:
                logger.error(f"[CACHE] Failed to write {key}: {e}")

    def delete(self, key: str) -> bool:
        """Delete key from disk cache"""
        with self._lock:
            if key in self._index:
                del self._index[key]
                filepath = self._key_to_filename(key)
                filepath.unlink(missing_ok=True)
                self._save_index()
                return True
            return False

    def clear(self):
        """Clear all disk cache"""
        with self._lock:
            for filepath in self.cache_dir.glob("*.json"):
                filepath.unlink(missing_ok=True)
            self._index = {}
            self._save_index()

    def cleanup_expired(self) -> int:
        """Remove all expired entries"""
        with self._lock:
            now = time.time()
            expired_keys = [k for k, exp in self._index.items() if now > exp]
            for key in expired_keys:
                filepath = self._key_to_filename(key)
                filepath.unlink(missing_ok=True)
                del self._index[key]
            if expired_keys:
                self._save_index()
            return len(expired_keys)


class CacheManager:
    """
    Combined cache manager with memory and optional disk caching.
    """

    # Default TTLs for different cache types
    TTL_VIRAL_TRENDS = 3600      # 1 hour
    TTL_API_RESPONSE = 900       # 15 minutes
    TTL_SCENARIO = 1800          # 30 minutes
    TTL_VIDEO_SEARCH = 600       # 10 minutes

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, cache_dir: Path = None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, cache_dir: Path = None):
        if self._initialized:
            return

        self._memory = MemoryCache(max_size=200)
        self._disk = None

        if cache_dir:
            self._disk = DiskCache(cache_dir)

        self._initialized = True
        logger.info("[CACHE] Cache manager initialized")

    def get(self, key: str, use_disk: bool = False) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key
            use_disk: Also check disk cache if memory miss
        """
        # Try memory first
        value = self._memory.get(key)
        if value is not None:
            return value

        # Try disk if enabled
        if use_disk and self._disk:
            value = self._disk.get(key)
            if value is not None:
                # Repopulate memory cache
                self._memory.set(key, value)
                return value

        return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: float = 3600,
        persist: bool = False,
    ):
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds
            persist: Also save to disk cache
        """
        self._memory.set(key, value, ttl)

        if persist and self._disk:
            self._disk.set(key, value, ttl)

    def delete(self, key: str):
        """Delete from both caches"""
        self._memory.delete(key)
        if self._disk:
            self._disk.delete(key)

    def clear(self):
        """Clear all caches"""
        self._memory.clear()
        if self._disk:
            self._disk.clear()

    def cleanup(self) -> Dict[str, int]:
        """Cleanup expired entries from all caches"""
        result = {"memory": self._memory.cleanup_expired()}
        if self._disk:
            result["disk"] = self._disk.cleanup_expired()
        return result

    def get_stats(self) -> Dict:
        """Get cache statistics"""
        return {
            "memory": self._memory.get_stats(),
        }

    # Convenience methods for specific cache types
    def cache_viral_trends(self, platform: str, data: Any):
        """Cache viral trends with appropriate TTL"""
        key = f"viral_trends:{platform}"
        self.set(key, data, ttl=self.TTL_VIRAL_TRENDS)

    def get_viral_trends(self, platform: str) -> Optional[Any]:
        """Get cached viral trends"""
        key = f"viral_trends:{platform}"
        return self.get(key)

    def cache_api_response(self, service: str, endpoint: str, data: Any):
        """Cache API response with appropriate TTL"""
        key = f"api:{service}:{endpoint}"
        self.set(
            key,
            data,
            ttl=self.TTL_API_RESPONSE,
        )

    def get_api_response(self, service: str, endpoint: str) -> Optional[Any]:
        """Get cached API response"""
        key = f"api:{service}:{endpoint}"
        return self.get(key)


# Global instance (initialized lazily)
_cache_instance: Optional[CacheManager] = None


def get_cache(cache_dir: Path = None) -> CacheManager:
    """Get or create global cache manager"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CacheManager(cache_dir)
    return _cache_instance


# Decorator for caching function results
def cached(key_prefix: str, ttl: float = 3600):
    """
    Decorator to cache function results.

    Usage:
        @cached("viral_trends", ttl=3600)
        def fetch_viral_content(platform):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Build cache key from function args
            cache_key = f"{key_prefix}:{':'.join(str(a) for a in args)}"

            cache = get_cache()
            result = cache.get(cache_key)

            if result is not None:
                logger.debug(f"[CACHE] Hit: {cache_key}")
                return result

            logger.debug(f"[CACHE] Miss: {cache_key}")
            result = func(*args, **kwargs)

            if result is not None:
                cache.set(cache_key, result, ttl)

            return result
        return wrapper

    return decorator
