"""Feature flag client for evaluation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypeVar

from litestar_flags.context import EvaluationContext
from litestar_flags.engine import EvaluationEngine
from litestar_flags.results import EvaluationDetails
from litestar_flags.security import sanitize_error_message
from litestar_flags.types import ErrorCode, EvaluationReason, FlagType

if TYPE_CHECKING:
    from litestar_flags.analytics.protocols import AnalyticsCollector
    from litestar_flags.bootstrap import BootstrapConfig
    from litestar_flags.cache import CacheProtocol, CacheStats
    from litestar_flags.models.flag import FeatureFlag
    from litestar_flags.protocols import StorageBackend
    from litestar_flags.rate_limit import RateLimiter

__all__ = ["FeatureFlagClient"]

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Cache key prefix for flags
_CACHE_KEY_PREFIX = "flag:"


class FeatureFlagClient:
    """Main client for feature flag evaluation.

    Provides type-safe methods for all flag types with automatic caching
    and graceful degradation (never throws exceptions).

    Example:
        >>> client = FeatureFlagClient(storage=MemoryStorageBackend())
        >>> enabled = await client.get_boolean_value("my-feature", default=False)
        >>> variant = await client.get_string_value("ab-test", default="control")

    """

    def __init__(
        self,
        storage: StorageBackend,
        default_context: EvaluationContext | None = None,
        rate_limiter: RateLimiter | None = None,
        cache: CacheProtocol | None = None,
        analytics_collector: AnalyticsCollector | None = None,
    ) -> None:
        """Initialize the feature flag client.

        Args:
            storage: The storage backend for flag data.
            default_context: Default evaluation context to use when none is provided.
            rate_limiter: Optional rate limiter to control evaluation throughput.
            cache: Optional cache for flag data. When provided, flag lookups will
                check the cache before hitting storage, and cache entries will be
                populated after storage reads.
            analytics_collector: Optional analytics collector for evaluation tracking.
                When provided, evaluation events will be recorded for monitoring
                and insights into flag usage.

        """
        self._storage = storage
        self._default_context = default_context or EvaluationContext()
        self._engine = EvaluationEngine(analytics_collector=analytics_collector)
        self._rate_limiter = rate_limiter
        self._cache = cache
        self._analytics_collector = analytics_collector
        self._preloaded_flags: dict[str, FeatureFlag] = {}
        self._closed = False

    @property
    def storage(self) -> StorageBackend:
        """Get the storage backend."""
        return self._storage

    @property
    def rate_limiter(self) -> RateLimiter | None:
        """Get the rate limiter."""
        return self._rate_limiter

    @property
    def cache(self) -> CacheProtocol | None:
        """Get the cache instance."""
        return self._cache

    @property
    def analytics_collector(self) -> AnalyticsCollector | None:
        """Get the analytics collector instance."""
        return self._analytics_collector

    def cache_stats(self) -> CacheStats | None:
        """Get cache statistics.

        Returns:
            CacheStats if a cache is configured, None otherwise.

        """
        if self._cache is not None:
            return self._cache.stats()
        return None

    # Bootstrap and preload methods

    @classmethod
    async def bootstrap(
        cls,
        config: BootstrapConfig,
        storage: StorageBackend,
        default_context: EvaluationContext | None = None,
        rate_limiter: RateLimiter | None = None,
        cache: CacheProtocol | None = None,
        analytics_collector: AnalyticsCollector | None = None,
    ) -> FeatureFlagClient:
        """Create a client with flags bootstrapped from a static source.

        Loads flags from the bootstrap configuration and stores them in the
        provided storage backend, then returns a configured client.

        Args:
            config: Bootstrap configuration specifying flag source.
            storage: Storage backend to populate with bootstrap flags.
            default_context: Default evaluation context.
            rate_limiter: Optional rate limiter.
            cache: Optional cache for flag data.
            analytics_collector: Optional analytics collector for evaluation tracking.

        Returns:
            Configured FeatureFlagClient with bootstrapped flags.

        Example:
            >>> config = BootstrapConfig(source=Path("flags.json"))
            >>> client = await FeatureFlagClient.bootstrap(
            ...     config=config,
            ...     storage=MemoryStorageBackend(),
            ... )

        """
        from litestar_flags.bootstrap import BootstrapLoader

        loader = BootstrapLoader()
        flags = await loader.load(config)

        # Store bootstrap flags in the storage backend
        for flag in flags:
            try:
                await storage.create_flag(flag)
            except ValueError:
                # Flag already exists, update it
                await storage.update_flag(flag)

        return cls(
            storage=storage,
            default_context=default_context,
            rate_limiter=rate_limiter,
            cache=cache,
            analytics_collector=analytics_collector,
        )

    async def preload_flags(
        self,
        flag_keys: list[str] | None = None,
    ) -> dict[str, FeatureFlag]:
        """Preload flags into the client's cache for faster evaluation.

        This method fetches flags from storage and caches them locally.
        Useful for warming up the client at startup to avoid cold-start
        latency on first evaluations.

        Args:
            flag_keys: Optional list of specific flag keys to preload.
                      If None, preloads all active flags.

        Returns:
            Dictionary of preloaded flags keyed by flag key.

        Example:
            >>> await client.preload_flags()  # Preload all flags
            >>> await client.preload_flags(["feature-a", "feature-b"])

        """
        try:
            if flag_keys is None:
                flags = await self._storage.get_all_active_flags()
                self._preloaded_flags = {flag.key: flag for flag in flags}
            else:
                flags_dict = await self._storage.get_flags(flag_keys)
                self._preloaded_flags.update(flags_dict)

            logger.info(f"Preloaded {len(self._preloaded_flags)} flags")
            return self._preloaded_flags.copy()
        except Exception as e:
            logger.error(f"Error preloading flags: {e}")
            return {}

    def clear_preloaded_flags(self) -> None:
        """Clear the preloaded flags cache.

        Call this method when you want to force fresh flag fetches
        from the storage backend.
        """
        self._preloaded_flags.clear()
        logger.debug("Cleared preloaded flags cache")

    async def clear_cache(self) -> None:
        """Clear the external cache.

        This method clears all entries in the external cache if one is configured.
        Use this when you need to invalidate all cached flag data.

        Note:
            This does not clear the preloaded flags. Use clear_preloaded_flags()
            for that, or clear_all_caches() to clear both.

        """
        if self._cache is not None:
            await self._cache.clear()
            logger.debug("Cleared external cache")

    async def clear_all_caches(self) -> None:
        """Clear both preloaded flags and external cache.

        Convenience method to ensure all cached data is cleared.

        """
        self.clear_preloaded_flags()
        await self.clear_cache()

    async def invalidate_flag(self, flag_key: str) -> None:
        """Invalidate a specific flag from all caches.

        Args:
            flag_key: The flag key to invalidate.

        """
        # Remove from preloaded flags
        self._preloaded_flags.pop(flag_key, None)

        # Remove from external cache
        if self._cache is not None:
            cache_key = f"{_CACHE_KEY_PREFIX}{flag_key}"
            await self._cache.delete(cache_key)

        logger.debug(f"Invalidated flag '{flag_key}' from all caches")

    async def _get_flag_with_cache(self, flag_key: str) -> FeatureFlag | None:
        """Get a flag, checking preloaded cache and external cache first.

        The lookup order is:
        1. Preloaded flags (in-memory, set via preload_flags())
        2. External cache (if configured)
        3. Storage backend

        Args:
            flag_key: The flag key to retrieve.

        Returns:
            The flag if found, None otherwise.

        """
        # Check preloaded flags first (fastest)
        if flag_key in self._preloaded_flags:
            return self._preloaded_flags[flag_key]

        cache_key = f"{_CACHE_KEY_PREFIX}{flag_key}"

        # Check external cache if configured
        if self._cache is not None:
            try:
                cached = await self._cache.get(cache_key)
                if cached is not None:
                    # Reconstruct flag from cached data
                    return self._deserialize_cached_flag(cached)
            except Exception as e:
                logger.warning(f"Cache get error for '{flag_key}': {e}")

        # Fall back to storage
        flag = await self._storage.get_flag(flag_key)

        # Populate cache on successful storage read
        if flag is not None and self._cache is not None:
            try:
                serialized = self._serialize_flag_for_cache(flag)
                await self._cache.set(cache_key, serialized)
            except Exception as e:
                logger.warning(f"Cache set error for '{flag_key}': {e}")

        return flag

    def _serialize_flag_for_cache(self, flag: FeatureFlag) -> dict[str, Any]:
        """Serialize a flag for cache storage.

        Args:
            flag: The flag to serialize.

        Returns:
            Dictionary representation of the flag.

        """
        return {
            "id": str(flag.id),
            "key": flag.key,
            "name": flag.name,
            "description": flag.description,
            "flag_type": flag.flag_type.value,
            "status": flag.status.value,
            "default_enabled": flag.default_enabled,
            "default_value": flag.default_value,
            "tags": flag.tags,
            "metadata": flag.metadata_,
            "rules": [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "description": r.description,
                    "priority": r.priority,
                    "enabled": r.enabled,
                    "conditions": r.conditions,
                    "serve_enabled": r.serve_enabled,
                    "serve_value": r.serve_value,
                    "rollout_percentage": r.rollout_percentage,
                }
                for r in (flag.rules or [])
            ],
            "variants": [
                {
                    "id": str(v.id),
                    "key": v.key,
                    "name": v.name,
                    "description": v.description,
                    "value": v.value,
                    "weight": v.weight,
                }
                for v in (flag.variants or [])
            ],
            "created_at": flag.created_at.isoformat() if flag.created_at else None,
            "updated_at": flag.updated_at.isoformat() if flag.updated_at else None,
        }

    def _deserialize_cached_flag(self, data: dict[str, Any]) -> FeatureFlag:
        """Deserialize a flag from cache storage.

        Args:
            data: The cached dictionary representation.

        Returns:
            Reconstructed FeatureFlag object.

        """
        from datetime import datetime
        from uuid import UUID

        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.rule import FlagRule
        from litestar_flags.models.variant import FlagVariant
        from litestar_flags.types import FlagStatus, FlagType

        # Create rule objects
        rules = [
            FlagRule(
                id=UUID(r["id"]),
                name=r["name"],
                description=r.get("description"),
                priority=r["priority"],
                enabled=r["enabled"],
                conditions=r["conditions"],
                serve_enabled=r["serve_enabled"],
                serve_value=r.get("serve_value"),
                rollout_percentage=r.get("rollout_percentage"),
            )
            for r in data.get("rules", [])
        ]

        # Create variant objects
        variants = [
            FlagVariant(
                id=UUID(v["id"]),
                key=v["key"],
                name=v["name"],
                description=v.get("description"),
                value=v["value"],
                weight=v["weight"],
            )
            for v in data.get("variants", [])
        ]

        return FeatureFlag(
            id=UUID(data["id"]),
            key=data["key"],
            name=data["name"],
            description=data.get("description"),
            flag_type=FlagType(data["flag_type"]),
            status=FlagStatus(data["status"]),
            default_enabled=data["default_enabled"],
            default_value=data.get("default_value"),
            tags=data.get("tags", []),
            metadata_=data.get("metadata", {}),
            rules=rules,
            variants=variants,
            created_at=(datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None),
            updated_at=(datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None),
        )

    # Boolean evaluation

    async def get_boolean_value(
        self,
        flag_key: str,
        default: bool = False,
        context: EvaluationContext | None = None,
    ) -> bool:
        """Evaluate a boolean flag.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            The evaluated boolean value.

        """
        details = await self.get_boolean_details(flag_key, default, context)
        return details.value

    async def get_boolean_details(
        self,
        flag_key: str,
        default: bool = False,
        context: EvaluationContext | None = None,
    ) -> EvaluationDetails[bool]:
        """Evaluate a boolean flag with details.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            EvaluationDetails containing the value and metadata.

        """
        return await self._evaluate(flag_key, default, FlagType.BOOLEAN, context)

    # String evaluation

    async def get_string_value(
        self,
        flag_key: str,
        default: str = "",
        context: EvaluationContext | None = None,
    ) -> str:
        """Evaluate a string flag.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            The evaluated string value.

        """
        details = await self.get_string_details(flag_key, default, context)
        return details.value

    async def get_string_details(
        self,
        flag_key: str,
        default: str = "",
        context: EvaluationContext | None = None,
    ) -> EvaluationDetails[str]:
        """Evaluate a string flag with details.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            EvaluationDetails containing the value and metadata.

        """
        return await self._evaluate(flag_key, default, FlagType.STRING, context)

    # Number evaluation

    async def get_number_value(
        self,
        flag_key: str,
        default: float = 0.0,
        context: EvaluationContext | None = None,
    ) -> float:
        """Evaluate a number flag.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            The evaluated number value.

        """
        details = await self.get_number_details(flag_key, default, context)
        return details.value

    async def get_number_details(
        self,
        flag_key: str,
        default: float = 0.0,
        context: EvaluationContext | None = None,
    ) -> EvaluationDetails[float]:
        """Evaluate a number flag with details.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            EvaluationDetails containing the value and metadata.

        """
        return await self._evaluate(flag_key, default, FlagType.NUMBER, context)

    # Object/JSON evaluation

    async def get_object_value(
        self,
        flag_key: str,
        default: dict[str, Any] | None = None,
        context: EvaluationContext | None = None,
    ) -> dict[str, Any]:
        """Evaluate an object/JSON flag.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            The evaluated object value.

        """
        details = await self.get_object_details(flag_key, default or {}, context)
        return details.value

    async def get_object_details(
        self,
        flag_key: str,
        default: dict[str, Any],
        context: EvaluationContext | None = None,
    ) -> EvaluationDetails[dict[str, Any]]:
        """Evaluate an object/JSON flag with details.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            EvaluationDetails containing the value and metadata.

        """
        return await self._evaluate(flag_key, default, FlagType.JSON, context)

    # Convenience methods

    async def is_enabled(
        self,
        flag_key: str,
        context: EvaluationContext | None = None,
    ) -> bool:
        """Check if a boolean flag is enabled.

        Shorthand for `get_boolean_value(flag_key, default=False, context)`.

        Args:
            flag_key: The unique flag key.
            context: Optional evaluation context.

        Returns:
            True if the flag is enabled, False otherwise.

        """
        return await self.get_boolean_value(flag_key, default=False, context=context)

    # Bulk evaluation

    async def get_all_flags(
        self,
        context: EvaluationContext | None = None,
    ) -> dict[str, EvaluationDetails[Any]]:
        """Evaluate all active flags.

        Args:
            context: Optional evaluation context.

        Returns:
            Dictionary mapping flag keys to their evaluation details.

        """
        ctx = self._merge_context(context)
        results: dict[str, EvaluationDetails[Any]] = {}

        try:
            flags = await self._storage.get_all_active_flags()
            for flag in flags:
                try:
                    results[flag.key] = await self._evaluate_flag(flag, ctx)
                except Exception as e:
                    logger.warning(f"Error evaluating flag '{flag.key}': {e}")
                    # Skip failed evaluations in bulk mode
                    continue
        except Exception as e:
            logger.error(f"Error fetching flags: {e}")

        return results

    async def get_flags(
        self,
        flag_keys: list[str],
        context: EvaluationContext | None = None,
    ) -> dict[str, EvaluationDetails[Any]]:
        """Evaluate specific flags by key.

        Args:
            flag_keys: List of flag keys to evaluate.
            context: Optional evaluation context.

        Returns:
            Dictionary mapping flag keys to their evaluation details.

        """
        ctx = self._merge_context(context)
        results: dict[str, EvaluationDetails[Any]] = {}

        try:
            flags = await self._storage.get_flags(flag_keys)
            for key, flag in flags.items():
                try:
                    results[key] = await self._evaluate_flag(flag, ctx)
                except Exception as e:
                    logger.warning(f"Error evaluating flag '{key}': {e}")
                    continue
        except Exception as e:
            logger.error(f"Error fetching flags: {e}")

        return results

    # Internal methods

    async def _evaluate(
        self,
        flag_key: str,
        default: T,
        expected_type: FlagType,
        context: EvaluationContext | None,
    ) -> EvaluationDetails[T]:
        """Core evaluation logic with error handling.

        This method NEVER throws exceptions - it always returns a result
        with the default value on error.

        Args:
            flag_key: The flag key to evaluate.
            default: Default value on error or not found.
            expected_type: Expected flag type for validation.
            context: Optional evaluation context.

        Returns:
            EvaluationDetails with the evaluated or default value.

        """
        ctx = self._merge_context(context)

        try:
            # Check rate limits if rate limiter is configured
            if self._rate_limiter is not None:
                await self._rate_limiter.acquire(flag_key)

            # Use preload cache, external cache, then fall back to storage
            flag = await self._get_flag_with_cache(flag_key)

            if flag is None:
                return EvaluationDetails(
                    value=default,
                    flag_key=flag_key,
                    reason=EvaluationReason.DEFAULT,
                    error_code=ErrorCode.FLAG_NOT_FOUND,
                    error_message=f"Flag '{flag_key}' not found",
                )

            # Type validation (skip for boolean as it's always compatible)
            if expected_type != FlagType.BOOLEAN and flag.flag_type != expected_type:
                return EvaluationDetails(
                    value=default,
                    flag_key=flag_key,
                    reason=EvaluationReason.ERROR,
                    error_code=ErrorCode.TYPE_MISMATCH,
                    error_message=f"Expected type '{expected_type.value}', got '{flag.flag_type.value}'",
                )

            result = await self._evaluate_flag(flag, ctx)

            # Cast to expected type
            return EvaluationDetails(
                value=result.value,  # type: ignore[arg-type]
                flag_key=result.flag_key,
                reason=result.reason,
                variant=result.variant,
                error_code=result.error_code,
                error_message=result.error_message,
                flag_metadata=result.flag_metadata,
            )

        except Exception as e:
            # Import here to avoid circular imports
            from litestar_flags.exceptions import RateLimitExceededError

            # Sanitize error message to prevent information disclosure
            safe_error = sanitize_error_message(e)

            # Handle rate limit exceptions specially
            if isinstance(e, RateLimitExceededError):
                logger.warning(f"Rate limit exceeded for flag '{flag_key}': {safe_error}")
                return EvaluationDetails(
                    value=default,
                    flag_key=flag_key,
                    reason=EvaluationReason.ERROR,
                    error_code=ErrorCode.GENERAL_ERROR,
                    error_message=f"Rate limit exceeded: {safe_error}",
                )

            logger.error(f"Error evaluating flag '{flag_key}': {safe_error}")
            return EvaluationDetails(
                value=default,
                flag_key=flag_key,
                reason=EvaluationReason.ERROR,
                error_code=ErrorCode.GENERAL_ERROR,
                error_message=safe_error,
            )

    async def _evaluate_flag(
        self,
        flag: FeatureFlag,
        context: EvaluationContext,
    ) -> EvaluationDetails[Any]:
        """Evaluate a single flag using the engine.

        Args:
            flag: The flag to evaluate.
            context: The evaluation context.

        Returns:
            EvaluationDetails from the engine.

        """
        return await self._engine.evaluate(flag, context, self._storage)

    def _merge_context(self, context: EvaluationContext | None) -> EvaluationContext:
        """Merge provided context with default context.

        Args:
            context: The provided context (may be None).

        Returns:
            Merged context with defaults.

        """
        if context is None:
            return self._default_context
        return self._default_context.merge(context)

    async def health_check(self) -> bool:
        """Check if the client and storage are healthy.

        Returns:
            True if healthy, False otherwise.

        """
        if self._closed:
            return False
        try:
            return await self._storage.health_check()
        except Exception:
            return False

    async def close(self) -> None:
        """Close the client and release resources."""
        if not self._closed:
            self._closed = True
            await self._storage.close()

    async def __aenter__(self) -> FeatureFlagClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()
