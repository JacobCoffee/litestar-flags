"""Middleware for automatic context extraction."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from litestar.middleware.base import AbstractMiddleware, DefineMiddleware

from litestar_flags.context import EvaluationContext

if TYPE_CHECKING:
    from litestar import Request
    from litestar.types import ASGIApp, Receive, Scope, Send

__all__ = ["FeatureFlagsMiddleware", "create_context_middleware"]


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
