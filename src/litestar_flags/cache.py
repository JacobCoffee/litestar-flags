"""Caching layer for feature flag evaluations.

This module provides a flexible caching abstraction with multiple backend
implementations for optimizing feature flag lookups.

Example:
    Using LRU cache for single-instance deployments::

        from litestar_flags.cache import LRUCache

        cache = LRUCache(max_size=1000, default_ttl=300)
        client = FeatureFlagClient(storage=storage, cache=cache)

    Using Redis cache for distributed deployments::

        from litestar_flags.cache import RedisCache

        cache = RedisCache(redis=redis_client)
        client = FeatureFlagClient(storage=storage, cache=cache)

"""

from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redis.asyncio import Redis

__all__ = [
    "CacheProtocol",
    "CacheStats",
    "LRUCache",
    "RedisCache",
]


@dataclass(slots=True)
class CacheStats:
    """Statistics for cache performance monitoring.

    Attributes:
        hits: Number of cache hits.
        misses: Number of cache misses.
        size: Current number of entries in the cache.

    Example:
        >>> stats = cache.stats()
        >>> print(f"Hit rate: {stats.hit_rate:.2%}")
        Hit rate: 85.00%

    """

    hits: int = 0
    misses: int = 0
    size: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate the cache hit rate.

        Returns:
            The hit rate as a float between 0.0 and 1.0.
            Returns 0.0 if no requests have been made.

        """
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


@runtime_checkable
class CacheProtocol(Protocol):
    """Protocol defining the interface for cache implementations.

    All cache backends must implement this protocol to be used with
    the FeatureFlagClient.

    Methods:
        get: Retrieve a value from the cache.
        set: Store a value in the cache.
        delete: Remove a value from the cache.
        clear: Remove all values from the cache.
        stats: Get cache statistics.

    """

    async def get(self, key: str) -> Any | None:
        """Retrieve a value from the cache.

        Args:
            key: The cache key.

        Returns:
            The cached value if found and not expired, None otherwise.

        """
        ...

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store a value in the cache.

        Args:
            key: The cache key.
            value: The value to store.
            ttl: Time-to-live in seconds. If None, uses the default TTL.

        """
        ...

    async def delete(self, key: str) -> None:
        """Remove a value from the cache.

        Args:
            key: The cache key to remove.

        """
        ...

    async def clear(self) -> None:
        """Remove all values from the cache."""
        ...

    def stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            CacheStats containing hit/miss counts and current size.

        """
        ...


@dataclass(slots=True)
class _CacheEntry:
    """Internal representation of a cached entry with TTL support."""

    value: Any
    expires_at: float | None = None

    def is_expired(self) -> bool:
        """Check if the entry has expired.

        Returns:
            True if the entry has expired, False otherwise.

        """
        if self.expires_at is None:
            return False
        return time.monotonic() > self.expires_at


class LRUCache:
    """Async-safe in-memory LRU cache with TTL support.

    This cache implementation uses an ordered dictionary to maintain
    LRU ordering and supports per-entry TTL. It is suitable for
    single-instance deployments.

    Attributes:
        max_size: Maximum number of entries in the cache.
        default_ttl: Default time-to-live in seconds for entries.

    Example:
        >>> cache = LRUCache(max_size=1000, default_ttl=300)
        >>> await cache.set("key", {"enabled": True})
        >>> value = await cache.get("key")
        >>> stats = cache.stats()

    Note:
        This implementation uses ``asyncio.Lock`` for coroutine safety,
        protecting against race conditions between concurrent coroutines
        in the same event loop. It is NOT thread-safe for multi-threaded
        access. For thread safety, use external synchronization or a
        thread-safe cache implementation.

    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int | None = None,
    ) -> None:
        """Initialize the LRU cache.

        Args:
            max_size: Maximum number of entries to store. Default is 1000.
            default_ttl: Default TTL in seconds for entries. None means no expiration.

        """
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> Any | None:
        """Retrieve a value from the cache.

        Moves the accessed entry to the end of the LRU order.

        Args:
            key: The cache key.

        Returns:
            The cached value if found and not expired, None otherwise.

        """
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return entry.value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store a value in the cache.

        If the cache is full, removes the least recently used entry.

        Args:
            key: The cache key.
            value: The value to store.
            ttl: Time-to-live in seconds. If None, uses the default TTL.

        """
        async with self._lock:
            effective_ttl = ttl if ttl is not None else self._default_ttl
            expires_at = time.monotonic() + effective_ttl if effective_ttl is not None else None

            # Remove existing entry if present
            if key in self._cache:
                del self._cache[key]

            # Evict oldest entries if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            self._cache[key] = _CacheEntry(value=value, expires_at=expires_at)

    async def delete(self, key: str) -> None:
        """Remove a value from the cache.

        Args:
            key: The cache key to remove.

        """
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        """Remove all values from the cache."""
        async with self._lock:
            self._cache.clear()

    def stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            CacheStats containing hit/miss counts and current size.

        Note:
            This method does not acquire the lock for performance reasons.
            Statistics may be slightly stale in concurrent scenarios.

        """
        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            size=len(self._cache),
        )

    async def cleanup_expired(self) -> int:
        """Remove all expired entries from the cache.

        This method can be called periodically to proactively clean
        up expired entries and free memory.

        Returns:
            The number of entries removed.

        """
        async with self._lock:
            expired_keys = [key for key, entry in self._cache.items() if entry.is_expired()]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)


class RedisCache:
    """Distributed cache implementation using Redis.

    This cache implementation wraps a Redis client to provide distributed
    caching suitable for multi-instance deployments. It uses JSON
    serialization for values.

    Attributes:
        prefix: Key prefix for all cached entries.
        default_ttl: Default time-to-live in seconds for entries.

    Example:
        >>> from redis.asyncio import Redis
        >>> redis = Redis.from_url("redis://localhost:6379")
        >>> cache = RedisCache(redis=redis, prefix="flags:", default_ttl=300)
        >>> await cache.set("key", {"enabled": True})
        >>> value = await cache.get("key")

    Note:
        This implementation requires the `redis` package to be installed.
        Statistics are approximations based on Redis INFO command.

    """

    def __init__(
        self,
        redis: Redis,  # type: ignore[type-arg]
        prefix: str = "litestar_flags:cache:",
        default_ttl: int | None = 300,
    ) -> None:
        """Initialize the Redis cache.

        Args:
            redis: The Redis client instance.
            prefix: Key prefix for all cached entries. Default is "litestar_flags:cache:".
            default_ttl: Default TTL in seconds for entries. Default is 300 (5 minutes).

        """
        self._redis = redis
        self._prefix = prefix
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    @property
    def redis(self) -> Redis:  # type: ignore[type-arg]
        """Get the underlying Redis client.

        Returns:
            The Redis client instance.

        """
        return self._redis

    def _make_key(self, key: str) -> str:
        """Create a prefixed Redis key.

        Args:
            key: The cache key.

        Returns:
            The prefixed key for Redis storage.

        """
        return f"{self._prefix}{key}"

    async def get(self, key: str) -> Any | None:
        """Retrieve a value from the cache.

        Args:
            key: The cache key.

        Returns:
            The cached value if found, None otherwise.

        Raises:
            redis.RedisError: If the Redis operation fails.

        """
        data = await self._redis.get(self._make_key(key))
        if data is None:
            self._misses += 1
            return None

        self._hits += 1
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return json.loads(data)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store a value in the cache.

        Args:
            key: The cache key.
            value: The value to store (must be JSON serializable).
            ttl: Time-to-live in seconds. If None, uses the default TTL.

        Raises:
            redis.RedisError: If the Redis operation fails.

        """
        effective_ttl = ttl if ttl is not None else self._default_ttl
        serialized = json.dumps(value)

        if effective_ttl is not None:
            await self._redis.setex(self._make_key(key), effective_ttl, serialized)
        else:
            await self._redis.set(self._make_key(key), serialized)

    async def delete(self, key: str) -> None:
        """Remove a value from the cache.

        Args:
            key: The cache key to remove.

        Raises:
            redis.RedisError: If the Redis operation fails.

        """
        await self._redis.delete(self._make_key(key))

    async def clear(self) -> None:
        """Remove all values with the cache prefix.

        Warning:
            This method uses SCAN to find and delete keys, which may
            be slow for large datasets. Use with caution in production.

        Raises:
            redis.RedisError: If the Redis operation fails.

        """
        cursor = 0
        pattern = f"{self._prefix}*"
        while True:
            cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                await self._redis.delete(*keys)
            if cursor == 0:
                break

    def stats(self) -> CacheStats:
        """Get cache statistics.

        Note:
            The size field is an approximation based on local hit/miss tracking.
            For accurate Redis key counts, use the Redis INFO command directly.

        Returns:
            CacheStats containing hit/miss counts and estimated size.

        """
        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            size=0,  # Size tracking would require Redis SCAN
        )

    async def get_redis_stats(self) -> dict[str, Any]:
        """Get detailed statistics from Redis INFO command.

        Returns:
            Dictionary containing Redis memory and keyspace statistics.

        Raises:
            redis.RedisError: If the Redis INFO command fails.

        """
        info = await self._redis.info()
        return {
            "used_memory": info.get("used_memory", 0),
            "used_memory_human": info.get("used_memory_human", "0B"),
            "keyspace": {k: v for k, v in info.items() if k.startswith("db")},
        }

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern.

        Args:
            pattern: The pattern to match (without prefix).

        Returns:
            The number of keys deleted.

        Raises:
            redis.RedisError: If the Redis operation fails.

        """
        deleted = 0
        cursor = 0
        full_pattern = f"{self._prefix}{pattern}"
        while True:
            cursor, keys = await self._redis.scan(cursor=cursor, match=full_pattern, count=100)
            if keys:
                deleted += await self._redis.delete(*keys)
            if cursor == 0:
                break
        return deleted
