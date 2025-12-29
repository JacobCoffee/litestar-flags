"""Litestar plugin for feature flags."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from litestar import get
from litestar.di import Provide
from litestar.plugins import InitPlugin
from litestar.response import Response
from litestar.status_codes import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE

from litestar_flags.client import FeatureFlagClient
from litestar_flags.config import FeatureFlagsConfig
from litestar_flags.health import HealthCheckResult, HealthStatus, health_check
from litestar_flags.security import sanitize_error_message
from litestar_flags.storage.memory import MemoryStorageBackend

if TYPE_CHECKING:
    from litestar import Litestar
    from litestar.config.app import AppConfig
    from litestar.datastructures import State

    from litestar_flags.protocols import StorageBackend

__all__ = ["FeatureFlagsPlugin"]

logger = logging.getLogger(__name__)


class FeatureFlagsPlugin(InitPlugin):
    """Litestar plugin for feature flags.

    Registers the feature flag client as a dependency and sets up
    lifecycle hooks for initialization and cleanup.

    Example:
        >>> from litestar import Litestar
        >>> from litestar_flags import FeatureFlagsPlugin, FeatureFlagsConfig
        >>>
        >>> config = FeatureFlagsConfig(backend="memory")
        >>> app = Litestar(
        ...     route_handlers=[...],
        ...     plugins=[FeatureFlagsPlugin(config=config)],
        ... )

    """

    __slots__ = ("_client", "_config", "_storage")

    def __init__(self, config: FeatureFlagsConfig | None = None) -> None:
        """Initialize the plugin.

        Args:
            config: Plugin configuration. Defaults to memory backend.

        """
        self._config = config or FeatureFlagsConfig()
        self._client: FeatureFlagClient | None = None
        self._storage: StorageBackend | None = None

    @property
    def config(self) -> FeatureFlagsConfig:
        """Get the plugin configuration."""
        return self._config

    @property
    def client(self) -> FeatureFlagClient | None:
        """Get the feature flag client (available after startup)."""
        return self._client

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        """Configure the application with feature flags support.

        Args:
            app_config: The application configuration.

        Returns:
            Modified application configuration.

        """
        # Register dependencies
        app_config.dependencies[self._config.client_dependency_key] = Provide(
            self._provide_client,
        )

        # Add lifecycle hooks
        app_config.on_startup.append(self._startup)
        app_config.on_shutdown.append(self._shutdown)

        # Add middleware if enabled
        if self._config.enable_middleware:
            from litestar_flags.middleware import create_context_middleware

            middleware = create_context_middleware(
                context_extractor=self._config.context_extractor,
            )
            app_config.middleware.append(middleware)

        # Add environment middleware if enabled
        if self._config.enable_environment_middleware:
            from litestar_flags.middleware import create_environment_middleware

            env_middleware = create_environment_middleware(
                default_environment=self._config.default_environment,
                environment_header=self._config.environment_header,
                environment_query_param=self._config.environment_query_param,
                allowed_environments=self._config.allowed_environments,
            )
            app_config.middleware.append(env_middleware)

        # Add health endpoint if enabled
        if self._config.enable_health_endpoint:
            health_handler = self._create_health_handler()
            app_config.route_handlers.append(health_handler)

        return app_config

    def _create_health_handler(self) -> Any:
        """Create the health check route handler.

        Returns:
            A route handler function for the health endpoint.

        """
        plugin = self  # Capture reference for closure

        @get(
            path=self._config.health_endpoint_path,
            tags=["Feature Flags"],
            summary="Feature flags health check",
            description="Check the health status of the feature flags system.",
        )
        async def health_endpoint() -> Response[dict[str, Any]]:
            """Health check endpoint for feature flags.

            Returns:
                JSON response with health status and details.

            """
            if plugin._storage is None:
                result = HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    storage_connected=False,
                    details={"error": "Storage not initialized"},
                )
            else:
                result = await health_check(plugin._storage)

            status_code = (
                HTTP_200_OK
                if result.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)
                else HTTP_503_SERVICE_UNAVAILABLE
            )

            return Response(
                content=result.to_dict(),
                status_code=status_code,
                media_type="application/json",
            )

        return health_endpoint

    async def _startup(self, app: Litestar) -> None:
        """Initialize the feature flag client on startup.

        Args:
            app: The Litestar application.

        """
        logger.info("Initializing feature flags...")

        try:
            self._storage = await self._create_storage()
            self._client = FeatureFlagClient(
                storage=self._storage,
                default_context=self._config.default_context,
            )

            # Store in app state for direct access
            app.state.feature_flags = self._client
            app.state.feature_flags_storage = self._storage

            logger.info(f"Feature flags initialized with {self._config.backend} backend")
        except Exception as e:
            logger.error(f"Failed to initialize feature flags: {sanitize_error_message(e)}")
            raise

    async def _shutdown(self, app: Litestar) -> None:
        """Clean up resources on shutdown.

        Args:
            app: The Litestar application.

        """
        logger.info("Shutting down feature flags...")

        if self._client is not None:
            await self._client.close()
            self._client = None
            self._storage = None

        logger.info("Feature flags shutdown complete")

    async def _provide_client(self, state: State) -> FeatureFlagClient:
        """Provide the feature flag client as a dependency.

        Args:
            state: The application state.

        Returns:
            The feature flag client.

        """
        return state.feature_flags  # type: ignore[return-value]

    async def _create_storage(self) -> StorageBackend:
        """Create the appropriate storage backend.

        Returns:
            The configured storage backend, optionally wrapped with resilience.

        Raises:
            ValueError: If the backend type is unknown.
            ImportError: If required dependencies are not installed.

        """
        storage: StorageBackend

        match self._config.backend:
            case "memory":
                storage = MemoryStorageBackend()

            case "database":
                try:
                    from litestar_flags.storage.database import DatabaseStorageBackend

                    storage = await DatabaseStorageBackend.create(
                        connection_string=self._config.connection_string,  # type: ignore[arg-type]
                        table_prefix=self._config.table_prefix,
                    )
                except ImportError as e:
                    raise ImportError(
                        "Database backend requires 'advanced-alchemy' and 'sqlalchemy'. "
                        "Install with: pip install litestar-flags[database]"
                    ) from e

            case "redis":
                try:
                    from litestar_flags.storage.redis import RedisStorageBackend

                    storage = await RedisStorageBackend.create(
                        url=self._config.redis_url,  # type: ignore[arg-type]
                        prefix=self._config.redis_prefix,
                    )
                except ImportError as e:
                    raise ImportError(
                        "Redis backend requires 'redis'. Install with: pip install litestar-flags[redis]"
                    ) from e

            case _:
                raise ValueError(f"Unknown backend: {self._config.backend}")

        # Wrap with resilience patterns if enabled
        if self._config.enable_resilience:
            from litestar_flags.resilience import CircuitBreaker, RetryPolicy
            from litestar_flags.storage.resilient import ResilientStorageBackend

            circuit_breaker = self._config.circuit_breaker or CircuitBreaker(
                name=f"feature_flags_{self._config.backend}",
                failure_threshold=5,
                recovery_timeout=30.0,
            )
            retry_policy = self._config.retry_policy or RetryPolicy(
                max_retries=3,
                base_delay=0.1,
                max_delay=2.0,
                exponential_backoff=True,
            )

            storage = ResilientStorageBackend(
                storage=storage,
                circuit_breaker=circuit_breaker,
                retry_policy=retry_policy,
            )
            logger.info("Resilience patterns enabled for storage backend")

        return storage


def provide_feature_flags() -> type[FeatureFlagClient]:
    """Provide type hint for dependency injection.

    Use this for type annotations in route handlers:

        @get("/feature")
        async def check_feature(
            feature_flags: FeatureFlagClient,
        ) -> dict:
            ...

    Returns:
        The FeatureFlagClient type for type hinting.

    """
    return FeatureFlagClient
