"""Middleware for automatic environment context injection."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import parse_qs

from litestar.middleware.base import AbstractMiddleware

if TYPE_CHECKING:
    from litestar.types import ASGIApp, Receive, Scope, Send

    from litestar_flags.config import FeatureFlagsConfig

__all__ = ["EnvironmentMiddleware", "get_request_environment"]


class EnvironmentMiddleware(AbstractMiddleware):
    """Middleware that extracts environment from request and injects into context.

    This middleware automatically detects the environment from incoming requests
    and stores it in the request scope for use by the feature flags client and
    evaluation engine.

    Environment is detected in this order:
        1. X-Environment header (configurable via ``environment_header``)
        2. 'env' query parameter (configurable via ``environment_query_param``)
        3. Default environment from config (``default_environment``)

    The detected environment is stored in ``scope["state"]["feature_flags_environment"]``
    for use by the client and engine during flag evaluation.

    Example:
        Configure environment detection in your Litestar application::

            from litestar import Litestar
            from litestar_flags import FeatureFlagsConfig, FeatureFlagsPlugin

            config = FeatureFlagsConfig(
                backend="memory",
                enable_environment_middleware=True,
                environment_header="X-Environment",
                environment_query_param="env",
                default_environment="production",
            )

            app = Litestar(
                route_handlers=[...],
                plugins=[FeatureFlagsPlugin(config=config)],
            )

        Then the environment will be extracted from requests::

            # Header: X-Environment: staging
            # Query: ?env=development
            # Default: production

    """

    def __init__(self, app: ASGIApp, config: FeatureFlagsConfig) -> None:
        """Initialize the environment middleware.

        Args:
            app: The ASGI application.
            config: Feature flags configuration containing environment settings.

        """
        super().__init__(app)
        self.config = config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process the request and extract environment.

        Args:
            scope: The ASGI scope.
            receive: The ASGI receive callable.
            send: The ASGI send callable.

        """
        if scope["type"] == "http":  # type: ignore[comparison-overlap]
            environment = self._extract_environment(scope)

            # Ensure state dict exists
            if "state" not in scope:
                scope["state"] = {}  # type: ignore[typeddict-unknown-key]

            scope["state"]["feature_flags_environment"] = environment  # type: ignore[typeddict-item]

        await self.app(scope, receive, send)

    def _extract_environment(self, scope: Scope) -> str | None:
        """Extract environment from request headers or query params.

        The extraction follows a priority order:
            1. HTTP header (configurable, defaults to X-Environment)
            2. Query parameter (configurable, defaults to env)
            3. Default environment from config

        Args:
            scope: The ASGI scope containing request information.

        Returns:
            The detected environment name, or None if not found and no default.

        """
        # Check header first
        headers = dict(scope.get("headers", []))
        header_name = self.config.environment_header.lower().encode()
        if header_name in headers:
            env = headers[header_name].decode()
            return self._validate_environment(env)

        # Check query params (only if query param detection is enabled)
        param_name = self.config.environment_query_param
        if param_name is not None:
            query_string = scope.get("query_string", b"").decode()
            if query_string:
                params = parse_qs(query_string)
                if params.get(param_name):
                    env = params[param_name][0]
                    return self._validate_environment(env)

        # Fall back to default
        return self.config.default_environment

    def _validate_environment(self, environment: str) -> str | None:
        """Validate that the environment is in the allowed list.

        Args:
            environment: The environment name to validate.

        Returns:
            The environment if valid, or the default environment if not allowed.

        """
        allowed = self.config.allowed_environments
        if allowed is not None and environment not in allowed:
            # Environment not in allowed list, fall back to default
            return self.config.default_environment
        return environment


def get_request_environment(scope: Scope) -> str | None:
    """Get the environment from a request scope.

    This retrieves the environment that was extracted by the middleware.

    Args:
        scope: The ASGI scope.

    Returns:
        The environment name if available, None otherwise.

    """
    state = scope.get("state", {})
    return state.get("feature_flags_environment")  # type: ignore[return-value]
