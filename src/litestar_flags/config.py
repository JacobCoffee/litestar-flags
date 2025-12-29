"""Configuration for the feature flags plugin."""

from __future__ import annotations

import re
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
        default_environment: Default environment slug for flag evaluation (e.g., "production").
            Must be alphanumeric with hyphens or underscores if set.
        enable_environment_inheritance: Whether child environments inherit flag values
            from parent environments. Defaults to True.
        enable_environment_middleware: Whether to enable the environment extraction middleware.
            When enabled, environment is extracted from requests and stored in scope state.
        environment_header: HTTP header name used to detect the current environment.
            Defaults to "X-Environment".
        environment_query_param: Query parameter name used to detect the current environment.
            Defaults to "env". Set to None to disable query parameter detection.
        allowed_environments: Optional list of allowed environment slugs. When set, requests
            with environments not in this list will fall back to default_environment.
            Defaults to None (all environments allowed).

    Example:
        >>> config = FeatureFlagsConfig(
        ...     backend="database",
        ...     connection_string="postgresql+asyncpg://user:pass@localhost/db",
        ...     enable_health_endpoint=True,
        ...     default_environment="production",
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

    # Environment settings
    default_environment: str | None = None
    enable_environment_inheritance: bool = True
    enable_environment_middleware: bool = False
    environment_header: str = "X-Environment"
    environment_query_param: str | None = "env"
    allowed_environments: list[str] | None = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.backend == "database" and self.connection_string is None:
            raise ValueError("connection_string is required when backend='database'")
        if self.backend == "redis" and self.redis_url is None:
            raise ValueError("redis_url is required when backend='redis'")
        slug_pattern = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
        if self.default_environment is not None:
            if not slug_pattern.match(self.default_environment):
                raise ValueError(
                    f"default_environment must be a valid slug (alphanumeric, hyphens, underscores, "
                    f"starting with alphanumeric): got {self.default_environment!r}"
                )
        if self.allowed_environments is not None:
            for env in self.allowed_environments:
                if not slug_pattern.match(env):
                    raise ValueError(
                        f"allowed_environments must contain valid slugs (alphanumeric, hyphens, "
                        f"underscores, starting with alphanumeric): got {env!r}"
                    )
            if self.default_environment is not None and self.default_environment not in self.allowed_environments:
                raise ValueError(f"default_environment {self.default_environment!r} must be in allowed_environments")
