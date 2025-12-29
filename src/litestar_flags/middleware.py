"""Middleware for automatic context extraction."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from litestar.middleware.base import AbstractMiddleware, DefineMiddleware

from litestar_flags.context import EvaluationContext

if TYPE_CHECKING:
    from litestar import Request
    from litestar.types import ASGIApp, Receive, Scope, Send

__all__ = [
    "EnvironmentMiddleware",
    "FeatureFlagsMiddleware",
    "create_context_middleware",
    "create_environment_middleware",
    "get_request_context",
    "get_request_environment",
]

logger = logging.getLogger(__name__)


class FeatureFlagsMiddleware(AbstractMiddleware):
    """Middleware for extracting evaluation context from requests.

    This middleware automatically extracts context information from
    incoming requests and makes it available for feature flag evaluation.
    """

    def __init__(
        self,
        app: ASGIApp,
        context_extractor: Callable[[Request[Any, Any, Any]], EvaluationContext] | None = None,
    ) -> None:
        """Initialize the middleware.

        Args:
            app: The ASGI application.
            context_extractor: Custom function to extract context from requests.

        """
        super().__init__(app)
        self._context_extractor = context_extractor or self._default_extractor

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process the request and extract context.

        Args:
            scope: The ASGI scope.
            receive: The ASGI receive callable.
            send: The ASGI send callable.

        """
        if scope["type"] == "http":  # type: ignore[comparison-overlap]
            from litestar import Request

            request = Request(scope)
            context = self._context_extractor(request)
            scope["feature_flags_context"] = context  # type: ignore[typeddict-unknown-key]

        await self.app(scope, receive, send)

    def _default_extractor(self, request: Request[Any, Any, Any]) -> EvaluationContext:
        """Extract evaluation context from the request.

        Extracts common attributes from the request:
        - IP address
        - User agent
        - Country (from headers if available)

        Args:
            request: The incoming request.

        Returns:
            Extracted evaluation context.

        """
        # Get IP address (check forwarded headers first)
        ip_address = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or request.headers.get("x-real-ip")
            or (request.client.host if request.client else None)
        )

        # Get user agent
        user_agent = request.headers.get("user-agent")

        # Get country from common headers (set by CDNs/proxies)
        country = (
            request.headers.get("cf-ipcountry")  # Cloudflare
            or request.headers.get("x-country-code")
            or request.headers.get("x-vercel-ip-country")  # Vercel
        )

        # Try to get user ID from auth state if available
        user_id = None
        try:
            if request.scope.get("user") is not None:
                user = request.scope["user"]
                user_id = getattr(user, "id", None) or getattr(user, "user_id", None)
                if user_id is not None:
                    user_id = str(user_id)
        except (KeyError, AttributeError):
            pass  # No auth middleware installed or user not available

        return EvaluationContext(
            targeting_key=user_id,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            country=country,
        )


def create_context_middleware(
    context_extractor: Callable[[Request[Any, Any, Any]], EvaluationContext] | None = None,
) -> DefineMiddleware:
    """Create a context extraction middleware.

    Args:
        context_extractor: Custom function to extract context from requests.

    Returns:
        Middleware definition for use with Litestar.

    """
    return DefineMiddleware(FeatureFlagsMiddleware, context_extractor=context_extractor)


def get_request_context(request: Request[Any, Any, Any]) -> EvaluationContext | None:
    """Get the evaluation context from a request.

    This retrieves the context that was extracted by the middleware.

    Args:
        request: The current request.

    Returns:
        The evaluation context if available, None otherwise.

    """
    return request.scope.get("feature_flags_context")  # type: ignore[return-value]


class EnvironmentMiddleware(AbstractMiddleware):
    """Middleware for extracting environment from requests.

    This middleware automatically extracts the environment from incoming requests
    based on headers or query parameters and injects it into the evaluation context.
    It validates environments against an optional allowed list and falls back to
    a default environment when needed.

    The resolved environment is stored in the request scope for downstream use.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        default_environment: str | None = None,
        environment_header: str = "X-Environment",
        environment_query_param: str | None = "env",
        allowed_environments: list[str] | None = None,
    ) -> None:
        """Initialize the environment middleware.

        Args:
            app: The ASGI application.
            default_environment: Default environment when none is specified.
            environment_header: HTTP header name to read environment from.
            environment_query_param: Query parameter name to read environment from.
                Set to None to disable query parameter detection.
            allowed_environments: Optional list of allowed environment slugs.
                When set, environments not in this list fall back to default.

        """
        super().__init__(app)
        self._default_environment = default_environment
        self._environment_header = environment_header
        self._environment_query_param = environment_query_param
        self._allowed_environments = set(allowed_environments) if allowed_environments else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process the request and extract environment.

        Args:
            scope: The ASGI scope.
            receive: The ASGI receive callable.
            send: The ASGI send callable.

        """
        if scope["type"] == "http":  # type: ignore[comparison-overlap]
            from litestar import Request

            request = Request(scope)
            environment = self._extract_environment(request)

            # Store resolved environment in scope
            scope["feature_flags_environment"] = environment  # type: ignore[typeddict-unknown-key]

            # Update existing context if present
            existing_context: EvaluationContext | None = scope.get("feature_flags_context")  # type: ignore[assignment]
            if existing_context is not None and environment is not None:
                scope["feature_flags_context"] = existing_context.with_environment(environment)  # type: ignore[typeddict-unknown-key]

        await self.app(scope, receive, send)

    def _extract_environment(self, request: Request[Any, Any, Any]) -> str | None:
        """Extract environment from the request.

        Checks header first, then query parameter. Validates against allowed
        environments if configured, falling back to default if invalid.

        Args:
            request: The incoming request.

        Returns:
            The resolved environment or None.

        """
        environment: str | None = None

        # Check header first (takes priority)
        if self._environment_header:
            environment = request.headers.get(self._environment_header.lower())

        # Fall back to query parameter if header not found
        if environment is None and self._environment_query_param:
            environment = request.query_params.get(self._environment_query_param)

        # Validate against allowed environments
        if environment is not None and self._allowed_environments is not None:
            if environment not in self._allowed_environments:
                logger.warning(
                    "Environment %r not in allowed_environments, falling back to default",
                    environment,
                )
                environment = self._default_environment
        elif environment is None:
            environment = self._default_environment

        return environment


def create_environment_middleware(
    *,
    default_environment: str | None = None,
    environment_header: str = "X-Environment",
    environment_query_param: str | None = "env",
    allowed_environments: list[str] | None = None,
) -> DefineMiddleware:
    """Create an environment extraction middleware.

    This factory function creates a middleware definition that can be added
    to a Litestar application for automatic environment detection.

    Args:
        default_environment: Default environment when none is specified.
        environment_header: HTTP header name to read environment from.
        environment_query_param: Query parameter name to read environment from.
            Set to None to disable query parameter detection.
        allowed_environments: Optional list of allowed environment slugs.

    Returns:
        Middleware definition for use with Litestar.

    Example:
        >>> from litestar import Litestar
        >>> from litestar_flags.middleware import create_environment_middleware
        >>>
        >>> app = Litestar(
        ...     route_handlers=[...],
        ...     middleware=[
        ...         create_environment_middleware(
        ...             default_environment="production",
        ...             allowed_environments=["production", "staging", "development"],
        ...         )
        ...     ],
        ... )

    """
    return DefineMiddleware(
        EnvironmentMiddleware,
        default_environment=default_environment,
        environment_header=environment_header,
        environment_query_param=environment_query_param,
        allowed_environments=allowed_environments,
    )


def get_request_environment(request: Request[Any, Any, Any]) -> str | None:
    """Get the resolved environment from a request.

    This retrieves the environment that was extracted by the EnvironmentMiddleware.

    Args:
        request: The current request.

    Returns:
        The resolved environment if available, None otherwise.

    """
    return request.scope.get("feature_flags_environment")  # type: ignore[return-value]
