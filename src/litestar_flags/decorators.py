"""Decorators for feature flag evaluation."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

from litestar.exceptions import NotAuthorizedException

from litestar_flags.context import EvaluationContext
from litestar_flags.middleware import get_request_context

if TYPE_CHECKING:
    from litestar import Request

    from litestar_flags.client import FeatureFlagClient

__all__ = ["feature_flag", "require_flag"]

F = TypeVar("F", bound=Callable[..., Any])


def feature_flag(
    flag_key: str,
    *,
    default: bool = False,
    default_response: Any = None,
    context_key: str | None = None,
) -> Callable[[F], F]:
    """Conditionally execute route handlers based on a feature flag.

    When the flag is disabled, the handler returns `default_response` instead
    of executing the handler function.

    Args:
        flag_key: The feature flag key to evaluate.
        default: Default value if flag is not found.
        default_response: Response to return when flag is disabled.
        context_key: Optional request attribute to use as targeting key.

    Returns:
        Decorated function.

    Example:
        >>> @get("/new-feature")
        >>> @feature_flag("new_feature", default_response={"error": "Not available"})
        >>> async def new_feature_endpoint() -> dict:
        ...     return {"message": "New feature!"}

    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Find the request and client from kwargs
            request: Request[Any, Any, Any] | None = kwargs.get("request")
            client: FeatureFlagClient | None = kwargs.get("feature_flags")

            if client is None:
                # Try to get from request state
                if request is not None:
                    client = request.app.state.feature_flags

            if client is None:
                # No client available, use default
                if default:
                    return await func(*args, **kwargs)
                return default_response

            # Build context
            context = _build_context(request, context_key)

            # Evaluate flag
            enabled = await client.get_boolean_value(flag_key, default=default, context=context)

            if enabled:
                return await func(*args, **kwargs)
            return default_response

        return wrapper  # type: ignore[return-value]

    return decorator


def require_flag(
    flag_key: str,
    *,
    default: bool = False,
    context_key: str | None = None,
    error_message: str | None = None,
) -> Callable[[F], F]:
    """Require a feature flag to be enabled for the decorated handler.

    When the flag is disabled, raises NotAuthorizedException.
    This is useful for protecting beta or premium features.

    Args:
        flag_key: The feature flag key to evaluate.
        default: Default value if flag is not found.
        context_key: Optional request attribute to use as targeting key.
        error_message: Custom error message for the exception.

    Returns:
        Decorated function.

    Raises:
        NotAuthorizedException: When the flag is disabled.

    Example:
        >>> @get("/beta")
        >>> @require_flag("beta_access", error_message="Beta access required")
        >>> async def beta_endpoint() -> dict:
        ...     return {"message": "Welcome to beta!"}

    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Find the request and client from kwargs
            request: Request[Any, Any, Any] | None = kwargs.get("request")
            client: FeatureFlagClient | None = kwargs.get("feature_flags")

            if client is None:
                # Try to get from request state
                if request is not None:
                    client = request.app.state.feature_flags

            if client is None:
                # No client available, use default
                if not default:
                    raise NotAuthorizedException(detail=error_message or f"Feature '{flag_key}' is not available")
                return await func(*args, **kwargs)

            # Build context
            context = _build_context(request, context_key)

            # Evaluate flag
            enabled = await client.get_boolean_value(flag_key, default=default, context=context)

            if not enabled:
                raise NotAuthorizedException(detail=error_message or f"Feature '{flag_key}' is not available")

            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def _build_context(
    request: Request[Any, Any, Any] | None,
    context_key: str | None,
) -> EvaluationContext | None:
    """Build evaluation context from request.

    Args:
        request: The current request.
        context_key: Optional attribute to use as targeting key.

    Returns:
        Evaluation context or None.

    """
    if request is None:
        return None

    # Try to get middleware-extracted context first
    context = get_request_context(request)
    if context is not None:
        if context_key is not None:
            # Override targeting key
            targeting_value = _get_context_value(request, context_key)
            if targeting_value is not None:
                context = context.with_targeting_key(str(targeting_value))
        return context

    # Build basic context from request
    targeting_key = None
    user_id = None

    if context_key is not None:
        targeting_value = _get_context_value(request, context_key)
        if targeting_value is not None:
            targeting_key = str(targeting_value)

    # Try to get user ID from auth
    if hasattr(request, "user") and request.user is not None:
        user_id = getattr(request.user, "id", None) or getattr(request.user, "user_id", None)
        if user_id is not None:
            user_id = str(user_id)
            if targeting_key is None:
                targeting_key = user_id

    return EvaluationContext(
        targeting_key=targeting_key,
        user_id=user_id,
    )


def _get_context_value(request: Request[Any, Any, Any], key: str) -> Any:
    """Get a value from request for use as context.

    Args:
        request: The current request.
        key: The key to look up.

    Returns:
        The value or None.

    """
    # Check path params
    if key in request.path_params:
        return request.path_params[key]

    # Check query params
    if key in request.query_params:
        return request.query_params[key]

    # Check headers
    header_value = request.headers.get(key) or request.headers.get(key.replace("_", "-"))
    if header_value is not None:
        return header_value

    # Check user attributes
    if hasattr(request, "user") and request.user is not None:
        if hasattr(request.user, key):
            return getattr(request.user, key)

    return None
