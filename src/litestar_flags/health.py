"""Health check functionality for the feature flags plugin.

This module provides comprehensive health monitoring for the feature flags
system, including storage backend connectivity, cache status, and overall
system health assessment.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from litestar_flags.protocols import StorageBackend

__all__ = [
    "HealthCheckResult",
    "HealthStatus",
    "health_check",
]


class HealthStatus(str, Enum):
    """Health status levels for the feature flags system.

    Attributes:
        HEALTHY: All components are functioning normally.
        DEGRADED: System is operational but with reduced functionality.
        UNHEALTHY: Critical failures preventing normal operation.

    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class CacheStats:
    """Statistics for cache performance.

    Attributes:
        hits: Number of cache hits.
        misses: Number of cache misses.
        hit_rate: Percentage of requests served from cache.
        size: Current number of items in cache.
        max_size: Maximum cache capacity.

    """

    hits: int = 0
    misses: int = 0
    hit_rate: float = 0.0
    size: int = 0
    max_size: int | None = None


@dataclass
class HealthCheckResult:
    """Comprehensive health check result for the feature flags system.

    Attributes:
        status: Overall health status of the system.
        storage_connected: Whether the storage backend is reachable.
        cache_connected: Whether the cache is reachable (if configured).
        flag_count: Total number of active flags in the system.
        cache_stats: Cache performance statistics (if available).
        latency_ms: Time taken to perform the health check in milliseconds.
        timestamp: When the health check was performed.
        details: Additional component-specific health information.

    Example:
        >>> result = await health_check(storage)
        >>> if result.status == HealthStatus.HEALTHY:
        ...     print("All systems operational")
        >>> else:
        ...     print(f"Issues detected: {result.details}")

    """

    status: HealthStatus
    storage_connected: bool
    cache_connected: bool | None = None
    flag_count: int = 0
    cache_stats: CacheStats | None = None
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert the health check result to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.

        """
        result: dict[str, Any] = {
            "status": self.status.value,
            "storage_connected": self.storage_connected,
            "flag_count": self.flag_count,
            "latency_ms": round(self.latency_ms, 2),
            "timestamp": self.timestamp.isoformat(),
        }

        if self.cache_connected is not None:
            result["cache_connected"] = self.cache_connected

        if self.cache_stats is not None:
            result["cache_stats"] = {
                "hits": self.cache_stats.hits,
                "misses": self.cache_stats.misses,
                "hit_rate": round(self.cache_stats.hit_rate, 2),
                "size": self.cache_stats.size,
            }
            if self.cache_stats.max_size is not None:
                result["cache_stats"]["max_size"] = self.cache_stats.max_size

        if self.details:
            result["details"] = self.details

        return result


async def health_check(
    storage: StorageBackend,
    *,
    include_flag_count: bool = True,
    include_cache_stats: bool = True,
) -> HealthCheckResult:
    """Perform a comprehensive health check of the feature flags system.

    This function checks the connectivity and status of all components
    in the feature flags system, including the storage backend and any
    configured caching layers.

    Args:
        storage: The storage backend to check.
        include_flag_count: Whether to count active flags (may add latency).
        include_cache_stats: Whether to include cache statistics if available.

    Returns:
        HealthCheckResult with comprehensive system status.

    Example:
        >>> from litestar_flags.storage import MemoryStorageBackend
        >>> storage = MemoryStorageBackend()
        >>> result = await health_check(storage)
        >>> print(f"Status: {result.status.value}")
        Status: healthy

    """
    start_time = time.perf_counter()
    details: dict[str, Any] = {}
    issues: list[str] = []

    # Check storage backend connectivity
    storage_connected = False
    try:
        storage_connected = await storage.health_check()
        if not storage_connected:
            issues.append("Storage backend health check returned False")
            details["storage_error"] = "Health check returned False"
    except Exception as e:
        issues.append(f"Storage backend unreachable: {e}")
        details["storage_error"] = str(e)

    # Get flag count if requested and storage is connected
    flag_count = 0
    if include_flag_count and storage_connected:
        try:
            flags = await storage.get_all_active_flags()
            flag_count = len(flags)
            details["active_flags"] = flag_count
        except Exception as e:
            issues.append(f"Failed to count flags: {e}")
            details["flag_count_error"] = str(e)

    # Check for cache stats if the storage backend supports it
    cache_stats: CacheStats | None = None
    cache_connected: bool | None = None

    if include_cache_stats and hasattr(storage, "get_cache_stats"):
        try:
            raw_stats = await storage.get_cache_stats()  # type: ignore[attr-defined]
            if raw_stats:
                cache_stats = CacheStats(
                    hits=raw_stats.get("hits", 0),
                    misses=raw_stats.get("misses", 0),
                    hit_rate=raw_stats.get("hit_rate", 0.0),
                    size=raw_stats.get("size", 0),
                    max_size=raw_stats.get("max_size"),
                )
                cache_connected = True
        except Exception as e:
            cache_connected = False
            issues.append(f"Cache stats unavailable: {e}")
            details["cache_error"] = str(e)

    # Calculate latency
    latency_ms = (time.perf_counter() - start_time) * 1000

    # Determine overall status
    if not storage_connected:
        status = HealthStatus.UNHEALTHY
    elif issues:
        status = HealthStatus.DEGRADED
    else:
        status = HealthStatus.HEALTHY

    # Add issues to details if any
    if issues:
        details["issues"] = issues

    return HealthCheckResult(
        status=status,
        storage_connected=storage_connected,
        cache_connected=cache_connected,
        flag_count=flag_count,
        cache_stats=cache_stats,
        latency_ms=latency_ms,
        timestamp=datetime.now(UTC),
        details=details,
    )
