"""Cache invalidation hook for feature flags.

This module provides automatic cache invalidation when feature flags
are updated, ensuring cache consistency across deployments.

Example:
    Using the cache invalidation hook with the plugin::

        from litestar_flags import FeatureFlagClient, FeatureFlagsPlugin
        from litestar_flags.cache import LRUCache
        from litestar_flags.contrib.cache_invalidation import CacheInvalidationHook

        cache = LRUCache(max_size=1000, default_ttl=300)
        invalidation_hook = CacheInvalidationHook(cache=cache)

        # Register the hook with your storage backend
        storage.register_hook(invalidation_hook)

        client = FeatureFlagClient(storage=storage, cache=cache)

"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from litestar_flags.cache import CacheProtocol
    from litestar_flags.models.flag import FeatureFlag

__all__ = ["CacheInvalidationHook", "CacheInvalidationMiddleware", "StorageHookProtocol"]

logger = logging.getLogger(__name__)


@runtime_checkable
class StorageHookProtocol(Protocol):
    """Protocol for storage update hooks.

    Implementations of this protocol can be registered with storage
    backends to receive notifications when flags are modified.

    """

    async def on_flag_created(self, flag: FeatureFlag) -> None:
        """Handle a new flag being created.

        Args:
            flag: The newly created flag.

        """
        ...

    async def on_flag_updated(self, flag: FeatureFlag) -> None:
        """Handle a flag being updated.

        Args:
            flag: The updated flag.

        """
        ...

    async def on_flag_deleted(self, flag_key: str) -> None:
        """Handle a flag being deleted.

        Args:
            flag_key: The key of the deleted flag.

        """
        ...


@dataclass
class CacheInvalidationHook:
    """Hook that invalidates cache entries when flags are modified.

    This hook implements the StorageHookProtocol and can be registered
    with storage backends to automatically invalidate cached flag data
    when flags are created, updated, or deleted.

    Attributes:
        cache: The cache instance to invalidate.
        key_prefix: Prefix used for cache keys (default: "flag:").
        invalidate_on_create: Whether to invalidate on flag creation.
        invalidate_on_update: Whether to invalidate on flag update.
        invalidate_on_delete: Whether to invalidate on flag deletion.

    Example:
        >>> cache = LRUCache(max_size=1000)
        >>> hook = CacheInvalidationHook(cache=cache)
        >>> await hook.on_flag_updated(flag)  # Invalidates cache for this flag
        >>> await hook.invalidate_all()  # Clears entire cache

    """

    cache: CacheProtocol
    key_prefix: str = "flag:"
    invalidate_on_create: bool = True
    invalidate_on_update: bool = True
    invalidate_on_delete: bool = True
    _invalidation_count: int = field(default=0, init=False, repr=False)

    def _cache_key(self, flag_key: str) -> str:
        """Generate the cache key for a flag.

        Args:
            flag_key: The flag key.

        Returns:
            The full cache key.

        """
        return f"{self.key_prefix}{flag_key}"

    async def on_flag_created(self, flag: FeatureFlag) -> None:
        """Invalidate cache when a new flag is created.

        Note:
            While newly created flags won't be in cache, invalidating
            ensures any negative cache entries are cleared.

        Args:
            flag: The newly created flag.

        """
        if not self.invalidate_on_create:
            return

        logger.debug(f"Cache invalidation: flag created '{flag.key}'")
        await self._invalidate_flag(flag.key)

    async def on_flag_updated(self, flag: FeatureFlag) -> None:
        """Invalidate cache when a flag is updated.

        Args:
            flag: The updated flag.

        """
        if not self.invalidate_on_update:
            return

        logger.debug(f"Cache invalidation: flag updated '{flag.key}'")
        await self._invalidate_flag(flag.key)

    async def on_flag_deleted(self, flag_key: str) -> None:
        """Invalidate cache when a flag is deleted.

        Args:
            flag_key: The key of the deleted flag.

        """
        if not self.invalidate_on_delete:
            return

        logger.debug(f"Cache invalidation: flag deleted '{flag_key}'")
        await self._invalidate_flag(flag_key)

    async def _invalidate_flag(self, flag_key: str) -> None:
        """Invalidate the cache entry for a specific flag.

        Args:
            flag_key: The flag key to invalidate.

        """
        try:
            cache_key = self._cache_key(flag_key)
            await self.cache.delete(cache_key)
            self._invalidation_count += 1
        except Exception as e:
            logger.warning(f"Cache invalidation failed for '{flag_key}': {e}")

    async def invalidate_flags(self, flag_keys: list[str]) -> int:
        """Invalidate multiple flag entries from the cache.

        Args:
            flag_keys: List of flag keys to invalidate.

        Returns:
            The number of keys that were invalidated.

        """
        invalidated = 0
        for flag_key in flag_keys:
            try:
                await self._invalidate_flag(flag_key)
                invalidated += 1
            except Exception as e:
                logger.warning(f"Failed to invalidate flag '{flag_key}': {e}")
        return invalidated

    async def invalidate_all(self) -> None:
        """Clear the entire cache.

        This method clears all cached entries, not just flag entries.
        Use with caution in shared cache environments.

        """
        logger.info("Cache invalidation: clearing all entries")
        try:
            await self.cache.clear()
            self._invalidation_count += 1
        except Exception as e:
            logger.warning(f"Full cache invalidation failed: {e}")

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate cache entries matching a pattern.

        This method is only available for cache implementations that
        support pattern-based deletion (e.g., RedisCache).

        Args:
            pattern: The pattern to match (e.g., "flag:feature-*").

        Returns:
            The number of entries invalidated.

        Raises:
            NotImplementedError: If the cache doesn't support pattern deletion.

        """
        # Check if cache supports pattern deletion
        if hasattr(self.cache, "delete_pattern"):
            try:
                deleted = await self.cache.delete_pattern(pattern)  # type: ignore[attr-defined]
                self._invalidation_count += deleted
                return deleted
            except Exception as e:
                logger.warning(f"Pattern invalidation failed for '{pattern}': {e}")
                return 0
        else:
            raise NotImplementedError(f"{type(self.cache).__name__} does not support pattern-based deletion")

    @property
    def invalidation_count(self) -> int:
        """Get the total number of invalidations performed.

        Returns:
            The count of invalidation operations.

        """
        return self._invalidation_count

    def reset_stats(self) -> None:
        """Reset the invalidation count to zero."""
        self._invalidation_count = 0


class CacheInvalidationMiddleware:
    """Middleware wrapper for automatic cache invalidation.

    This class wraps a storage backend and automatically triggers
    cache invalidation on mutating operations.

    Example:
        >>> storage = MemoryStorageBackend()
        >>> cache = LRUCache()
        >>> wrapped_storage = CacheInvalidationMiddleware(
        ...     storage=storage,
        ...     hook=CacheInvalidationHook(cache=cache),
        ... )
        >>> # All mutations through wrapped_storage will invalidate cache

    """

    def __init__(
        self,
        storage: Any,
        hook: CacheInvalidationHook,
    ) -> None:
        """Initialize the middleware.

        Args:
            storage: The underlying storage backend.
            hook: The cache invalidation hook.

        """
        self._storage = storage
        self._hook = hook

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the underlying storage.

        Args:
            name: The attribute name.

        Returns:
            The attribute from the underlying storage.

        """
        return getattr(self._storage, name)

    async def create_flag(self, flag: FeatureFlag) -> FeatureFlag:
        """Create a flag and invalidate cache.

        Args:
            flag: The flag to create.

        Returns:
            The created flag.

        """
        result = await self._storage.create_flag(flag)
        await self._hook.on_flag_created(result)
        return result

    async def update_flag(self, flag: FeatureFlag) -> FeatureFlag:
        """Update a flag and invalidate cache.

        Args:
            flag: The flag to update.

        Returns:
            The updated flag.

        """
        result = await self._storage.update_flag(flag)
        await self._hook.on_flag_updated(result)
        return result

    async def delete_flag(self, key: str) -> bool:
        """Delete a flag and invalidate cache.

        Args:
            key: The flag key to delete.

        Returns:
            True if the flag was deleted.

        """
        result = await self._storage.delete_flag(key)
        if result:
            await self._hook.on_flag_deleted(key)
        return result
