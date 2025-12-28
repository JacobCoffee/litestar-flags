"""Resilient storage backend wrapper with circuit breaker and retry patterns.

This module provides a wrapper that adds resilience patterns to any storage
backend, providing graceful degradation when the underlying storage fails.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any
from uuid import UUID

from litestar_flags.resilience import (
    CircuitBreaker,
    ResilienceConfig,
    RetryPolicy,
    resilient_call,
)

if TYPE_CHECKING:
    from litestar_flags.models.flag import FeatureFlag
    from litestar_flags.models.override import FlagOverride
    from litestar_flags.protocols import StorageBackend

__all__ = ["ResilientStorageBackend"]

logger = logging.getLogger(__name__)


class ResilientStorageBackend:
    """Storage backend wrapper with resilience patterns.

    Wraps any storage backend with circuit breaker and retry logic
    to provide graceful degradation under failure conditions.

    Attributes:
        storage: The underlying storage backend.
        circuit_breaker: Circuit breaker for failure isolation.
        retry_policy: Retry policy for transient failures.

    Example:
        >>> from litestar_flags.storage import MemoryStorageBackend
        >>> storage = MemoryStorageBackend()
        >>> resilient = ResilientStorageBackend(
        ...     storage=storage,
        ...     circuit_breaker=CircuitBreaker(name="storage"),
        ...     retry_policy=RetryPolicy(max_retries=3),
        ... )
        >>> flag = await resilient.get_flag("my-feature")

    """

    def __init__(
        self,
        storage: StorageBackend,
        circuit_breaker: CircuitBreaker | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        """Initialize the resilient storage backend.

        Args:
            storage: The underlying storage backend to wrap.
            circuit_breaker: Optional circuit breaker for failure isolation.
            retry_policy: Optional retry policy for transient failures.

        """
        self._storage = storage
        self._circuit_breaker = circuit_breaker
        self._retry_policy = retry_policy

    @classmethod
    def wrap(
        cls,
        storage: StorageBackend,
        config: ResilienceConfig | None = None,
    ) -> ResilientStorageBackend:
        """Wrap a storage backend with resilience patterns.

        Args:
            storage: The storage backend to wrap.
            config: Optional resilience configuration.

        Returns:
            ResilientStorageBackend wrapping the original.

        """
        if config is None:
            config = ResilienceConfig.default()

        return cls(
            storage=storage,
            circuit_breaker=config.circuit_breaker,
            retry_policy=config.retry_policy,
        )

    @property
    def storage(self) -> StorageBackend:
        """Get the underlying storage backend."""
        return self._storage

    @property
    def circuit_breaker(self) -> CircuitBreaker | None:
        """Get the circuit breaker instance."""
        return self._circuit_breaker

    @property
    def retry_policy(self) -> RetryPolicy | None:
        """Get the retry policy."""
        return self._retry_policy

    async def _resilient_call(
        self,
        func: Any,
        default: Any = None,
    ) -> Any:
        """Execute a storage operation with resilience patterns.

        Args:
            func: Async function to execute.
            default: Value to return on persistent failure.

        Returns:
            The result of the function, or default on failure.

        """
        return await resilient_call(
            func,
            circuit_breaker=self._circuit_breaker,
            retry_policy=self._retry_policy,
            default=default,
        )

    async def get_flag(self, key: str) -> FeatureFlag | None:
        """Retrieve a single flag by key with resilience.

        Args:
            key: The unique flag key.

        Returns:
            The FeatureFlag if found, None otherwise.

        """
        return await self._resilient_call(
            lambda: self._storage.get_flag(key),
            default=None,
        )

    async def get_flags(self, keys: Sequence[str]) -> dict[str, FeatureFlag]:
        """Retrieve multiple flags by keys with resilience.

        Args:
            keys: Sequence of flag keys to retrieve.

        Returns:
            Dictionary mapping flag keys to FeatureFlag objects.

        """
        return await self._resilient_call(
            lambda: self._storage.get_flags(keys),
            default={},
        )

    async def get_all_active_flags(self) -> list[FeatureFlag]:
        """Retrieve all active flags with resilience.

        Returns:
            List of all FeatureFlag objects with ACTIVE status.

        """
        return await self._resilient_call(
            lambda: self._storage.get_all_active_flags(),
            default=[],
        )

    async def get_override(
        self,
        flag_id: UUID,
        entity_type: str,
        entity_id: str,
    ) -> FlagOverride | None:
        """Retrieve entity-specific override with resilience.

        Args:
            flag_id: The flag's UUID.
            entity_type: Type of entity (e.g., "user", "organization").
            entity_id: The entity's identifier.

        Returns:
            The FlagOverride if found, None otherwise.

        """
        return await self._resilient_call(
            lambda: self._storage.get_override(flag_id, entity_type, entity_id),
            default=None,
        )

    async def create_flag(self, flag: FeatureFlag) -> FeatureFlag:
        """Create a new flag with resilience.

        Note: Write operations do not use a default fallback since
        they must succeed or fail explicitly.

        Args:
            flag: The flag to create.

        Returns:
            The created flag.

        Raises:
            Exception: If the operation fails after retries.

        """
        return await self._resilient_call(
            lambda: self._storage.create_flag(flag),
        )

    async def update_flag(self, flag: FeatureFlag) -> FeatureFlag:
        """Update an existing flag with resilience.

        Args:
            flag: The flag with updated values.

        Returns:
            The updated flag.

        Raises:
            Exception: If the operation fails after retries.

        """
        return await self._resilient_call(
            lambda: self._storage.update_flag(flag),
        )

    async def delete_flag(self, key: str) -> bool:
        """Delete a flag by key with resilience.

        Args:
            key: The unique flag key.

        Returns:
            True if deleted, False otherwise.

        """
        return await self._resilient_call(
            lambda: self._storage.delete_flag(key),
            default=False,
        )

    async def health_check(self) -> bool:
        """Check storage backend health.

        This operation bypasses the circuit breaker to allow
        health checks even when the circuit is open.

        Returns:
            True if the backend is healthy, False otherwise.

        """
        try:
            return await self._storage.health_check()
        except Exception:
            return False

    async def close(self) -> None:
        """Close any open connections and clean up resources."""
        await self._storage.close()

    def get_resilience_stats(self) -> dict[str, Any]:
        """Get statistics about resilience patterns.

        Returns:
            Dictionary with circuit breaker and retry statistics.

        """
        stats: dict[str, Any] = {"enabled": True}

        if self._circuit_breaker:
            stats["circuit_breaker"] = self._circuit_breaker.get_stats()

        if self._retry_policy:
            stats["retry_policy"] = {
                "max_retries": self._retry_policy.max_retries,
                "base_delay": self._retry_policy.base_delay,
                "max_delay": self._retry_policy.max_delay,
                "exponential_backoff": self._retry_policy.exponential_backoff,
            }

        return stats


def with_resilience(
    storage: StorageBackend,
    *,
    circuit_breaker: CircuitBreaker | None = None,
    retry_policy: RetryPolicy | None = None,
) -> ResilientStorageBackend:
    """Wrap a storage backend with resilience patterns.

    Convenience function to create a resilient storage backend
    with the specified circuit breaker and retry policy.

    Args:
        storage: The storage backend to wrap.
        circuit_breaker: Optional circuit breaker for failure isolation.
        retry_policy: Optional retry policy for transient failures.

    Returns:
        ResilientStorageBackend wrapping the original.

    Example:
        >>> from litestar_flags.storage import MemoryStorageBackend
        >>> from litestar_flags.resilience import CircuitBreaker, RetryPolicy
        >>> storage = with_resilience(
        ...     MemoryStorageBackend(),
        ...     circuit_breaker=CircuitBreaker(name="storage"),
        ...     retry_policy=RetryPolicy(max_retries=3),
        ... )

    """
    # Use defaults if not provided
    if circuit_breaker is None:
        circuit_breaker = CircuitBreaker(
            name="storage",
            failure_threshold=5,
            recovery_timeout=30.0,
        )

    if retry_policy is None:
        retry_policy = RetryPolicy(
            max_retries=3,
            base_delay=0.1,
            max_delay=2.0,
            exponential_backoff=True,
        )

    return ResilientStorageBackend(
        storage=storage,
        circuit_breaker=circuit_breaker,
        retry_policy=retry_policy,
    )
