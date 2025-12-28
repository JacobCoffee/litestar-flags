"""Tests for the caching layer."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from litestar_flags.cache import CacheProtocol, CacheStats, LRUCache
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.types import FlagStatus, FlagType


class TestCacheStats:
    """Tests for CacheStats dataclass."""

    def test_hit_rate_no_requests(self):
        """Hit rate should be 0.0 when no requests have been made."""
        stats = CacheStats(hits=0, misses=0, size=0)
        assert stats.hit_rate == 0.0

    def test_hit_rate_all_hits(self):
        """Hit rate should be 1.0 when all requests are hits."""
        stats = CacheStats(hits=100, misses=0, size=50)
        assert stats.hit_rate == 1.0

    def test_hit_rate_all_misses(self):
        """Hit rate should be 0.0 when all requests are misses."""
        stats = CacheStats(hits=0, misses=100, size=0)
        assert stats.hit_rate == 0.0

    def test_hit_rate_mixed(self):
        """Hit rate should be correctly calculated for mixed hits/misses."""
        stats = CacheStats(hits=75, misses=25, size=50)
        assert stats.hit_rate == 0.75


class TestLRUCache:
    """Tests for LRUCache implementation."""

    @pytest.fixture
    def cache(self) -> LRUCache:
        """Create a test cache."""
        return LRUCache(max_size=5, default_ttl=60)

    async def test_set_and_get(self, cache: LRUCache):
        """Test basic set and get operations."""
        await cache.set("key1", {"value": "test"})
        result = await cache.get("key1")
        assert result == {"value": "test"}

    async def test_get_nonexistent(self, cache: LRUCache):
        """Test getting a nonexistent key returns None."""
        result = await cache.get("nonexistent")
        assert result is None

    async def test_delete(self, cache: LRUCache):
        """Test deleting a key."""
        await cache.set("key1", "value1")
        await cache.delete("key1")
        result = await cache.get("key1")
        assert result is None

    async def test_clear(self, cache: LRUCache):
        """Test clearing all entries."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.clear()
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    async def test_lru_eviction(self, cache: LRUCache):
        """Test that least recently used entries are evicted."""
        # Fill cache to capacity
        for i in range(5):
            await cache.set(f"key{i}", f"value{i}")

        # Access key0 to make it recently used
        await cache.get("key0")

        # Add a new entry, should evict key1 (oldest unused)
        await cache.set("key5", "value5")

        # key1 should be evicted
        assert await cache.get("key1") is None
        # key0 should still exist (was recently accessed)
        assert await cache.get("key0") == "value0"
        # key5 should exist
        assert await cache.get("key5") == "value5"

    async def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        cache = LRUCache(max_size=10, default_ttl=0)  # 0 second TTL
        await cache.set("key1", "value1")

        # Small delay to ensure expiration
        await asyncio.sleep(0.01)

        result = await cache.get("key1")
        assert result is None

    async def test_per_entry_ttl(self, cache: LRUCache):
        """Test that per-entry TTL overrides default."""
        await cache.set("key1", "value1", ttl=0)  # Immediate expiration

        await asyncio.sleep(0.01)

        result = await cache.get("key1")
        assert result is None

    async def test_no_ttl(self):
        """Test entries without TTL don't expire."""
        cache = LRUCache(max_size=10, default_ttl=None)
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    async def test_stats_tracking(self, cache: LRUCache):
        """Test that statistics are tracked correctly."""
        await cache.set("key1", "value1")

        # Generate hits
        await cache.get("key1")
        await cache.get("key1")

        # Generate misses
        await cache.get("nonexistent")

        stats = cache.stats()
        assert stats.hits == 2
        assert stats.misses == 1
        assert stats.size == 1

    async def test_update_existing_key(self, cache: LRUCache):
        """Test updating an existing key."""
        await cache.set("key1", "value1")
        await cache.set("key1", "value2")
        result = await cache.get("key1")
        assert result == "value2"

    async def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        cache = LRUCache(max_size=10, default_ttl=0)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        await asyncio.sleep(0.01)

        removed = await cache.cleanup_expired()
        assert removed == 2
        assert cache.stats().size == 0

    async def test_concurrent_access(self, cache: LRUCache):
        """Test thread safety with concurrent access."""

        async def writer(key: str, value: str):
            for _ in range(10):
                await cache.set(key, value)
                await asyncio.sleep(0.001)

        async def reader(key: str):
            for _ in range(10):
                await cache.get(key)
                await asyncio.sleep(0.001)

        await asyncio.gather(
            writer("key1", "value1"),
            writer("key2", "value2"),
            reader("key1"),
            reader("key2"),
        )

        # Should complete without errors
        stats = cache.stats()
        assert stats.size <= 5  # Within max_size


class TestRedisCacheWithFakeredis:
    """Tests for RedisCache using fakeredis."""

    @pytest.fixture
    def fake_redis(self):
        """Create a fake Redis client."""
        try:
            import fakeredis.aioredis
        except ImportError:
            pytest.skip("fakeredis not installed")
        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.fixture
    def redis_cache(self, fake_redis):
        """Create a RedisCache with fake Redis."""
        from litestar_flags.cache import RedisCache

        return RedisCache(redis=fake_redis, prefix="test:", default_ttl=60)

    async def test_set_and_get(self, redis_cache):
        """Test basic set and get operations."""
        await redis_cache.set("key1", {"value": "test"})
        result = await redis_cache.get("key1")
        assert result == {"value": "test"}

    async def test_get_nonexistent(self, redis_cache):
        """Test getting a nonexistent key returns None."""
        result = await redis_cache.get("nonexistent")
        assert result is None

    async def test_delete(self, redis_cache):
        """Test deleting a key."""
        await redis_cache.set("key1", "value1")
        await redis_cache.delete("key1")
        result = await redis_cache.get("key1")
        assert result is None

    async def test_clear(self, redis_cache, fake_redis):
        """Test clearing all entries with prefix."""
        await redis_cache.set("key1", "value1")
        await redis_cache.set("key2", "value2")

        # Add a key without the cache prefix
        await fake_redis.set("other:key", "other_value")

        await redis_cache.clear()

        assert await redis_cache.get("key1") is None
        assert await redis_cache.get("key2") is None
        # Key without prefix should still exist
        assert await fake_redis.get("other:key") == "other_value"

    async def test_stats_tracking(self, redis_cache):
        """Test that statistics are tracked correctly."""
        await redis_cache.set("key1", "value1")

        # Generate hits
        await redis_cache.get("key1")
        await redis_cache.get("key1")

        # Generate misses
        await redis_cache.get("nonexistent")

        stats = redis_cache.stats()
        assert stats.hits == 2
        assert stats.misses == 1

    async def test_delete_pattern(self, redis_cache):
        """Test pattern-based deletion."""
        await redis_cache.set("flag:test-1", "value1")
        await redis_cache.set("flag:test-2", "value2")
        await redis_cache.set("other:key", "value3")

        deleted = await redis_cache.delete_pattern("flag:*")

        assert deleted == 2
        assert await redis_cache.get("flag:test-1") is None
        assert await redis_cache.get("flag:test-2") is None
        assert await redis_cache.get("other:key") == "value3"

    async def test_json_serialization(self, redis_cache):
        """Test that complex values are serialized correctly."""
        complex_value = {
            "enabled": True,
            "variants": ["a", "b"],
            "metadata": {"nested": {"key": "value"}},
        }
        await redis_cache.set("complex", complex_value)
        result = await redis_cache.get("complex")
        assert result == complex_value


class TestCacheProtocol:
    """Tests for CacheProtocol compliance."""

    def test_lru_cache_implements_protocol(self):
        """Test that LRUCache implements CacheProtocol."""
        cache = LRUCache()
        assert isinstance(cache, CacheProtocol)

    def test_redis_cache_implements_protocol(self):
        """Test that RedisCache implements CacheProtocol."""
        try:
            import fakeredis.aioredis

            from litestar_flags.cache import RedisCache

            redis = fakeredis.aioredis.FakeRedis()
            cache = RedisCache(redis=redis)
            assert isinstance(cache, CacheProtocol)
        except ImportError:
            pytest.skip("fakeredis or redis not installed")


class TestClientCacheIntegration:
    """Tests for client cache integration."""

    @pytest.fixture
    def storage(self):
        """Create a memory storage backend."""
        from litestar_flags import MemoryStorageBackend

        return MemoryStorageBackend()

    @pytest.fixture
    def cache(self):
        """Create an LRU cache."""
        return LRUCache(max_size=100, default_ttl=300)

    @pytest.fixture
    def sample_flag(self) -> FeatureFlag:
        """Create a sample feature flag."""
        return FeatureFlag(
            id=uuid4(),
            key="test-cached-flag",
            name="Test Cached Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    async def test_client_with_cache(self, storage, cache, sample_flag):
        """Test that client uses cache for flag lookups."""
        from litestar_flags import FeatureFlagClient

        await storage.create_flag(sample_flag)

        client = FeatureFlagClient(storage=storage, cache=cache)

        # First lookup should hit storage and populate cache
        result1 = await client.get_boolean_value("test-cached-flag")
        assert result1 is True

        stats = cache.stats()
        assert stats.misses == 1  # Cache miss on first lookup

        # Second lookup should hit cache
        result2 = await client.get_boolean_value("test-cached-flag")
        assert result2 is True

        stats = cache.stats()
        assert stats.hits == 1  # Cache hit on second lookup

    async def test_client_cache_stats(self, storage, cache, sample_flag):
        """Test that client exposes cache stats."""
        from litestar_flags import FeatureFlagClient

        await storage.create_flag(sample_flag)

        client = FeatureFlagClient(storage=storage, cache=cache)

        await client.get_boolean_value("test-cached-flag")
        await client.get_boolean_value("test-cached-flag")

        stats = client.cache_stats()
        assert stats is not None
        assert stats.hits == 1
        assert stats.misses == 1

    async def test_client_cache_invalidation(self, storage, cache, sample_flag):
        """Test that client can invalidate cached flags."""
        from litestar_flags import FeatureFlagClient

        await storage.create_flag(sample_flag)

        client = FeatureFlagClient(storage=storage, cache=cache)

        # Populate cache
        await client.get_boolean_value("test-cached-flag")

        # Invalidate
        await client.invalidate_flag("test-cached-flag")

        # Next lookup should miss cache
        await client.get_boolean_value("test-cached-flag")

        stats = cache.stats()
        assert stats.misses == 2  # Two cache misses

    async def test_client_clear_cache(self, storage, cache, sample_flag):
        """Test clearing the client cache."""
        from litestar_flags import FeatureFlagClient

        await storage.create_flag(sample_flag)

        client = FeatureFlagClient(storage=storage, cache=cache)

        # Populate cache
        await client.get_boolean_value("test-cached-flag")

        # Clear cache
        await client.clear_cache()

        # Verify cache is empty
        stats = cache.stats()
        assert stats.size == 0

    async def test_client_without_cache(self, storage, sample_flag):
        """Test that client works without cache."""
        from litestar_flags import FeatureFlagClient

        await storage.create_flag(sample_flag)

        client = FeatureFlagClient(storage=storage)

        result = await client.get_boolean_value("test-cached-flag")
        assert result is True

        # cache_stats should return None when no cache configured
        assert client.cache_stats() is None


class TestCacheInvalidationHook:
    """Tests for CacheInvalidationHook."""

    @pytest.fixture
    def cache(self):
        """Create an LRU cache."""
        return LRUCache(max_size=100, default_ttl=300)

    @pytest.fixture
    def hook(self, cache):
        """Create a cache invalidation hook."""
        from litestar_flags.contrib.cache_invalidation import CacheInvalidationHook

        return CacheInvalidationHook(cache=cache)

    @pytest.fixture
    def sample_flag(self) -> FeatureFlag:
        """Create a sample feature flag."""
        return FeatureFlag(
            id=uuid4(),
            key="test-hook-flag",
            name="Test Hook Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    async def test_on_flag_created(self, cache, hook, sample_flag):
        """Test cache invalidation on flag creation."""
        # Pre-populate cache
        await cache.set("flag:test-hook-flag", {"cached": True})

        await hook.on_flag_created(sample_flag)

        # Cache entry should be removed
        result = await cache.get("flag:test-hook-flag")
        assert result is None
        assert hook.invalidation_count == 1

    async def test_on_flag_updated(self, cache, hook, sample_flag):
        """Test cache invalidation on flag update."""
        # Pre-populate cache
        await cache.set("flag:test-hook-flag", {"cached": True})

        await hook.on_flag_updated(sample_flag)

        # Cache entry should be removed
        result = await cache.get("flag:test-hook-flag")
        assert result is None
        assert hook.invalidation_count == 1

    async def test_on_flag_deleted(self, cache, hook):
        """Test cache invalidation on flag deletion."""
        # Pre-populate cache
        await cache.set("flag:test-hook-flag", {"cached": True})

        await hook.on_flag_deleted("test-hook-flag")

        # Cache entry should be removed
        result = await cache.get("flag:test-hook-flag")
        assert result is None
        assert hook.invalidation_count == 1

    async def test_invalidate_all(self, cache, hook):
        """Test full cache invalidation."""
        # Pre-populate cache
        await cache.set("flag:flag1", {"cached": True})
        await cache.set("flag:flag2", {"cached": True})

        await hook.invalidate_all()

        # All entries should be removed
        assert await cache.get("flag:flag1") is None
        assert await cache.get("flag:flag2") is None

    async def test_invalidate_flags(self, cache, hook):
        """Test bulk flag invalidation."""
        # Pre-populate cache
        await cache.set("flag:flag1", {"cached": True})
        await cache.set("flag:flag2", {"cached": True})
        await cache.set("flag:flag3", {"cached": True})

        invalidated = await hook.invalidate_flags(["flag1", "flag2"])

        assert invalidated == 2
        assert await cache.get("flag:flag1") is None
        assert await cache.get("flag:flag2") is None
        assert await cache.get("flag:flag3") == {"cached": True}

    async def test_disabled_invalidation(self, cache, sample_flag):
        """Test that invalidation can be disabled."""
        from litestar_flags.contrib.cache_invalidation import CacheInvalidationHook

        hook = CacheInvalidationHook(
            cache=cache,
            invalidate_on_create=False,
            invalidate_on_update=False,
            invalidate_on_delete=False,
        )

        # Pre-populate cache
        await cache.set("flag:test-hook-flag", {"cached": True})

        await hook.on_flag_created(sample_flag)
        await hook.on_flag_updated(sample_flag)
        await hook.on_flag_deleted("test-hook-flag")

        # Cache entry should still exist
        result = await cache.get("flag:test-hook-flag")
        assert result == {"cached": True}
        assert hook.invalidation_count == 0

    def test_reset_stats(self, hook):
        """Test resetting invalidation stats."""
        hook._invalidation_count = 10
        hook.reset_stats()
        assert hook.invalidation_count == 0


class TestCacheInvalidationMiddleware:
    """Tests for CacheInvalidationMiddleware."""

    @pytest.fixture
    def storage(self):
        """Create a memory storage backend."""
        from litestar_flags import MemoryStorageBackend

        return MemoryStorageBackend()

    @pytest.fixture
    def cache(self):
        """Create an LRU cache."""
        return LRUCache(max_size=100, default_ttl=300)

    @pytest.fixture
    def sample_flag(self) -> FeatureFlag:
        """Create a sample feature flag."""
        return FeatureFlag(
            id=uuid4(),
            key="middleware-flag",
            name="Middleware Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    async def test_create_flag_invalidates_cache(self, storage, cache, sample_flag):
        """Test that creating a flag through middleware invalidates cache."""
        from litestar_flags.contrib.cache_invalidation import (
            CacheInvalidationHook,
            CacheInvalidationMiddleware,
        )

        hook = CacheInvalidationHook(cache=cache)
        wrapped_storage = CacheInvalidationMiddleware(storage=storage, hook=hook)

        await wrapped_storage.create_flag(sample_flag)

        assert hook.invalidation_count == 1

    async def test_update_flag_invalidates_cache(self, storage, cache, sample_flag):
        """Test that updating a flag through middleware invalidates cache."""
        from litestar_flags.contrib.cache_invalidation import (
            CacheInvalidationHook,
            CacheInvalidationMiddleware,
        )

        hook = CacheInvalidationHook(cache=cache)
        wrapped_storage = CacheInvalidationMiddleware(storage=storage, hook=hook)

        await storage.create_flag(sample_flag)
        await cache.set("flag:middleware-flag", {"cached": True})

        sample_flag.default_enabled = False
        await wrapped_storage.update_flag(sample_flag)

        assert hook.invalidation_count == 1
        assert await cache.get("flag:middleware-flag") is None

    async def test_delete_flag_invalidates_cache(self, storage, cache, sample_flag):
        """Test that deleting a flag through middleware invalidates cache."""
        from litestar_flags.contrib.cache_invalidation import (
            CacheInvalidationHook,
            CacheInvalidationMiddleware,
        )

        hook = CacheInvalidationHook(cache=cache)
        wrapped_storage = CacheInvalidationMiddleware(storage=storage, hook=hook)

        await storage.create_flag(sample_flag)
        await cache.set("flag:middleware-flag", {"cached": True})

        await wrapped_storage.delete_flag("middleware-flag")

        assert hook.invalidation_count == 1
        assert await cache.get("flag:middleware-flag") is None

    async def test_middleware_delegates_to_storage(self, storage, cache, sample_flag):
        """Test that middleware delegates non-mutating operations."""
        from litestar_flags.contrib.cache_invalidation import (
            CacheInvalidationHook,
            CacheInvalidationMiddleware,
        )

        hook = CacheInvalidationHook(cache=cache)
        wrapped_storage = CacheInvalidationMiddleware(storage=storage, hook=hook)

        await storage.create_flag(sample_flag)

        # get_flag should delegate to underlying storage
        result = await wrapped_storage.get_flag("middleware-flag")
        assert result is not None
        assert result.key == "middleware-flag"
