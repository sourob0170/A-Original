import sys
import time
from collections import OrderedDict
from typing import Any, ClassVar

from bot import LOGGER
from bot.core.config_manager import Config


class LRUCache:
    """Memory-efficient LRU cache implementation with automatic cleanup"""

    def __init__(self, max_size: int, ttl: int):
        self.max_size = max_size
        self.ttl = ttl
        self._cache = OrderedDict()
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # 5 minutes

    def get(self, key: str) -> Any | None:
        """Get item from cache with LRU update"""
        if key not in self._cache:
            return None

        # Check if expired
        entry = self._cache[key]
        if time.time() - entry["timestamp"] > self.ttl:
            del self._cache[key]
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        entry["access_count"] += 1
        return entry["data"]

    def set(self, key: str, value: Any) -> None:
        """Set item in cache with automatic eviction"""
        current_time = time.time()

        # Remove if exists (to update position)
        if key in self._cache:
            del self._cache[key]

        # Add new entry
        self._cache[key] = {
            "data": value,
            "timestamp": current_time,
            "access_count": 0,
        }

        # Move to end
        self._cache.move_to_end(key)

        # Evict oldest if over limit
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

        # Periodic cleanup
        if current_time - self._last_cleanup > self._cleanup_interval:
            self._cleanup_expired()

    def _cleanup_expired(self) -> None:
        """Remove expired entries"""
        current_time = time.time()
        expired_keys = [
            key
            for key, entry in self._cache.items()
            if current_time - entry["timestamp"] > self.ttl
        ]
        for key in expired_keys:
            del self._cache[key]
        self._last_cleanup = current_time

    def clear(self) -> None:
        """Clear all cache entries"""
        self._cache.clear()

    def size(self) -> int:
        """Get current cache size"""
        return len(self._cache)

    def stats(self) -> dict[str, Any]:
        """Get cache statistics"""
        total_access = sum(entry["access_count"] for entry in self._cache.values())
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "total_access": total_access,
            "hit_ratio": total_access / max(1, len(self._cache)),
        }


class CacheManager:
    """Optimized memory-efficient cache manager for streaming operations"""

    # Optimized cache settings for reduced memory usage
    _file_cache: ClassVar[LRUCache] = None
    _link_cache: ClassVar[LRUCache] = None
    _user_cache: ClassVar[LRUCache] = None
    _session_cache: ClassVar[LRUCache] = None

    # Reduced cache sizes for better memory efficiency
    _max_file_cache_size = 500  # Reduced from 1000
    _max_link_cache_size = 1000  # Reduced from 2000
    _max_user_cache_size = 200  # Reduced from 500
    _max_session_cache_size = 50  # Reduced from 100

    # Optimized TTL settings
    _file_cache_ttl = 1800  # 30 minutes (reduced from 1 hour)
    _link_cache_ttl = 900  # 15 minutes (reduced from 30 minutes)
    _user_cache_ttl = 3600  # 1 hour (reduced from 2 hours)
    _session_cache_ttl = 300  # 5 minutes (reduced from 10 minutes)

    @classmethod
    def _ensure_caches_initialized(cls):
        """Lazy initialization of caches"""
        if cls._file_cache is None:
            cls._file_cache = LRUCache(cls._max_file_cache_size, cls._file_cache_ttl)
        if cls._link_cache is None:
            cls._link_cache = LRUCache(cls._max_link_cache_size, cls._link_cache_ttl)
        if cls._user_cache is None:
            cls._user_cache = LRUCache(cls._max_user_cache_size, cls._user_cache_ttl)
        if cls._session_cache is None:
            cls._session_cache = LRUCache(
                cls._max_session_cache_size, cls._session_cache_ttl
            )

    @staticmethod
    def is_enabled() -> bool:
        """Check if caching is enabled"""
        return getattr(Config, "STREAM_CACHE_ENABLED", True)

    @staticmethod
    def cache_file_info(file_id: str, file_info: dict):
        """Cache file information with optimized storage"""
        try:
            if not CacheManager.is_enabled():
                return

            CacheManager._ensure_caches_initialized()

            # Handle both dict and list inputs
            if isinstance(file_info, list):
                # If it's a list, cache the whole list
                essential_info = file_info
            else:
                # Store only essential file info to reduce memory usage
                essential_info = {
                    "file_name": file_info.get("file_name"),
                    "file_size": file_info.get("file_size"),
                    "mime_type": file_info.get("mime_type"),
                    "file_unique_id": file_info.get("file_unique_id"),
                    "is_streamable": file_info.get("is_streamable", False),
                }

            CacheManager._file_cache.set(file_id, essential_info)

        except Exception as e:
            LOGGER.error(f"Error caching file info: {e}")

    @staticmethod
    def get_cached_file_info(file_id: str) -> dict | None:
        """Get cached file information with LRU optimization"""
        try:
            if not CacheManager.is_enabled():
                return None

            CacheManager._ensure_caches_initialized()
            return CacheManager._file_cache.get(file_id)

        except Exception as e:
            LOGGER.error(f"Error getting cached file info: {e}")
            return None

    @staticmethod
    def cache_generated_links(file_id: str, links: dict):
        """Cache generated links with memory optimization"""
        try:
            if not CacheManager.is_enabled():
                return

            CacheManager._ensure_caches_initialized()

            # Store only essential link data
            essential_links = {
                "download": links.get("download"),
                "stream": links.get("stream"),
            }

            CacheManager._link_cache.set(file_id, essential_links)

        except Exception as e:
            LOGGER.error(f"Error caching links: {e}")

    @staticmethod
    def get_cached_links(file_id: str) -> dict | None:
        """Get cached links with LRU optimization"""
        try:
            if not CacheManager.is_enabled():
                return None

            CacheManager._ensure_caches_initialized()
            return CacheManager._link_cache.get(file_id)

        except Exception as e:
            LOGGER.error(f"Error getting cached links: {e}")
            return None

    @staticmethod
    def cache_user_preferences(user_id: int, preferences: dict):
        """Cache user preferences with minimal memory usage"""
        try:
            if not CacheManager.is_enabled():
                return

            CacheManager._ensure_caches_initialized()

            # Store only essential user preferences
            essential_prefs = {
                "theme": preferences.get("theme", "dark"),
                "quality": preferences.get("quality", "auto"),
            }

            CacheManager._user_cache.set(str(user_id), essential_prefs)

        except Exception as e:
            LOGGER.error(f"Error caching user preferences: {e}")

    @staticmethod
    def get_cached_user_preferences(user_id: int) -> dict | None:
        """Get cached user preferences with LRU optimization"""
        try:
            if not CacheManager.is_enabled():
                return None

            CacheManager._ensure_caches_initialized()
            return CacheManager._user_cache.get(str(user_id))

        except Exception as e:
            LOGGER.error(f"Error getting cached user preferences: {e}")
            return None

    @staticmethod
    def cache_session_data(session_id: str, session_data: dict):
        """Cache session data with minimal memory footprint"""
        try:
            if not CacheManager.is_enabled():
                return

            CacheManager._ensure_caches_initialized()

            # Store only essential session data
            essential_session = {
                "user_id": session_data.get("user_id"),
                "expires_at": session_data.get("expires_at"),
                "permissions": session_data.get("permissions", []),
            }

            CacheManager._session_cache.set(session_id, essential_session)

        except Exception as e:
            LOGGER.error(f"Error caching session data: {e}")

    @staticmethod
    def get_cached_session_data(session_id: str) -> dict | None:
        """Get cached session data with LRU optimization"""
        try:
            if not CacheManager.is_enabled():
                return None

            CacheManager._ensure_caches_initialized()
            return CacheManager._session_cache.get(session_id)

        except Exception as e:
            LOGGER.error(f"Error getting cached session data: {e}")
            return None

    @staticmethod
    async def cleanup_expired():
        """Optimized cleanup of all expired cache entries"""
        try:
            if not CacheManager.is_enabled():
                return

            CacheManager._ensure_caches_initialized()

            # Cleanup is now handled automatically by LRU caches
            # Just trigger cleanup on each cache
            if CacheManager._file_cache:
                CacheManager._file_cache._cleanup_expired()
            if CacheManager._link_cache:
                CacheManager._link_cache._cleanup_expired()
            if CacheManager._user_cache:
                CacheManager._user_cache._cleanup_expired()
            if CacheManager._session_cache:
                CacheManager._session_cache._cleanup_expired()

        except Exception as e:
            LOGGER.error(f"Error cleaning up expired cache: {e}")

    @staticmethod
    def get_cache_stats() -> dict:
        """Get optimized cache statistics"""
        try:
            if not CacheManager.is_enabled():
                return {"cache_enabled": False}

            CacheManager._ensure_caches_initialized()

            file_stats = (
                CacheManager._file_cache.stats() if CacheManager._file_cache else {}
            )
            link_stats = (
                CacheManager._link_cache.stats() if CacheManager._link_cache else {}
            )
            user_stats = (
                CacheManager._user_cache.stats() if CacheManager._user_cache else {}
            )
            session_stats = (
                CacheManager._session_cache.stats()
                if CacheManager._session_cache
                else {}
            )

            return {
                "cache_enabled": True,
                "file_cache": file_stats,
                "link_cache": link_stats,
                "user_cache": user_stats,
                "session_cache": session_stats,
                "total_entries": (
                    file_stats.get("size", 0)
                    + link_stats.get("size", 0)
                    + user_stats.get("size", 0)
                    + session_stats.get("size", 0)
                ),
                "memory_efficiency": "LRU with automatic cleanup",
            }
        except Exception as e:
            LOGGER.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}

    @staticmethod
    def clear_all_cache():
        """Clear all cache data efficiently"""
        try:
            CacheManager._ensure_caches_initialized()

            if CacheManager._file_cache:
                CacheManager._file_cache.clear()
            if CacheManager._link_cache:
                CacheManager._link_cache.clear()
            if CacheManager._user_cache:
                CacheManager._user_cache.clear()
            if CacheManager._session_cache:
                CacheManager._session_cache.clear()

            LOGGER.info("All cache data cleared efficiently")
        except Exception as e:
            LOGGER.error(f"Error clearing cache: {e}")

    @staticmethod
    def invalidate_file_cache(file_id: str):
        """Invalidate specific file cache efficiently"""
        try:
            CacheManager._ensure_caches_initialized()

            # Remove from both file and link caches
            if (
                CacheManager._file_cache
                and file_id in CacheManager._file_cache._cache
            ):
                del CacheManager._file_cache._cache[file_id]
            if (
                CacheManager._link_cache
                and file_id in CacheManager._link_cache._cache
            ):
                del CacheManager._link_cache._cache[file_id]

        except Exception as e:
            LOGGER.error(f"Error invalidating file cache: {e}")

    @staticmethod
    def get_memory_usage() -> dict:
        """Get estimated memory usage of caches"""
        try:
            CacheManager._ensure_caches_initialized()

            file_size = (
                sys.getsizeof(CacheManager._file_cache._cache)
                if CacheManager._file_cache
                else 0
            )
            link_size = (
                sys.getsizeof(CacheManager._link_cache._cache)
                if CacheManager._link_cache
                else 0
            )
            user_size = (
                sys.getsizeof(CacheManager._user_cache._cache)
                if CacheManager._user_cache
                else 0
            )
            session_size = (
                sys.getsizeof(CacheManager._session_cache._cache)
                if CacheManager._session_cache
                else 0
            )

            total_size = file_size + link_size + user_size + session_size

            return {
                "file_cache_bytes": file_size,
                "link_cache_bytes": link_size,
                "user_cache_bytes": user_size,
                "session_cache_bytes": session_size,
                "total_bytes": total_size,
                "total_mb": round(total_size / (1024 * 1024), 2),
            }
        except Exception as e:
            LOGGER.error(f"Error getting memory usage: {e}")
            return {"error": str(e)}
