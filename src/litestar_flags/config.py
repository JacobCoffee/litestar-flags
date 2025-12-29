"""Configuration for the feature flags plugin."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from litestar import Request

    from litestar_flags.context import EvaluationContext
    from litestar_flags.resilience import CircuitBreaker, RetryPolicy

__all__ = ["FeatureFlagsConfig"]


@dataclass(slots=True)
class FeatureFlagsConfig:
    """Configuration for the feature flags plugin.

    Attributes:
        backend: Storage backend type ("memory", "database", "redis").
        connection_string: Database connection string (when backend="database").
        table_prefix: Prefix for database tables (when backend="database").
        redis_url: Redis connection URL (when backend="redis").
        redis_prefix: Prefix for Redis keys (when backend="redis").
        default_context: Default evaluation context.
        enable_middleware: Whether to enable the context extraction middleware.
        context_extractor: Custom function to extract context from requests.
        client_dependency_key: Key for dependency injection of the client.
        enable_health_endpoint: Whether to register a health check endpoint.
        health_endpoint_path: Path for the health check endpoint.
        enable_resilience: Whether to enable circuit breaker and retry patterns.
        circuit_breaker: Optional circuit breaker configuration.
        retry_policy: Optional retry policy configuration.

    Example:
        >>> config = FeatureFlagsConfig(
        ...     backend="database",
        ...     connection_string="postgresql+asyncpg://user:pass@localhost/db",
        ...     enable_health_endpoint=True,
        ... )

    """

    # Storage backend
    backend: Literal["memory", "database", "redis"] = "memory"

    # Database settings (when backend="database")
    connection_string: str | None = None
    table_prefix: str = "ff_"

    # Redis settings (when backend="redis")
    redis_url: str | None = None
    redis_prefix: str = "feature_flags:"

    # Default context
    default_context: EvaluationContext | None = None

    # Middleware
    enable_middleware: bool = False
    context_extractor: Callable[[Request], EvaluationContext] | None = None

    # Dependency key
    client_dependency_key: str = "feature_flags"

    # Health endpoint settings
    enable_health_endpoint: bool = False
    health_endpoint_path: str = "/flags/health"

    # Resilience settings
    enable_resilience: bool = False
    circuit_breaker: CircuitBreaker | None = None
    retry_policy: RetryPolicy | None = None

    # Extra options for custom backends
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.backend == "database" and self.connection_string is None:
            raise ValueError("connection_string is required when backend='database'")
        if self.backend == "redis" and self.redis_url is None:
            raise ValueError("redis_url is required when backend='redis'")
