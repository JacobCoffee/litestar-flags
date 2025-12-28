"""OpenFeature provider integration for litestar-flags.

This module provides an OpenFeature-compliant provider that wraps the
litestar-flags FeatureFlagClient, enabling interoperability with the
OpenFeature ecosystem.

Example:
    Basic usage with OpenFeature::

        from openfeature import api
        from litestar_flags.client import FeatureFlagClient
        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        # Create the litestar-flags client
        client = FeatureFlagClient(storage=my_storage)

        # Create and register the OpenFeature provider
        provider = LitestarFlagsProvider(client)
        api.set_provider(provider)

        # Use the OpenFeature API
        of_client = api.get_client()
        enabled = of_client.get_boolean_value("my-feature", False)

    Using async methods::

        enabled = await of_client.get_boolean_value_async("my-feature", False)

Requires:
    openfeature-sdk>=0.8.0

"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, TypeVar

# Handle optional openfeature import
try:
    from openfeature.evaluation_context import EvaluationContext as OFEvaluationContext
    from openfeature.exception import ErrorCode as OFErrorCode
    from openfeature.flag_evaluation import FlagResolutionDetails
    from openfeature.flag_evaluation import Reason as OFReason
    from openfeature.hook import Hook
    from openfeature.provider import AbstractProvider, Metadata, ProviderStatus

    OPENFEATURE_AVAILABLE = True
except ImportError:
    OPENFEATURE_AVAILABLE = False
    # Define stub types for type checking when openfeature is not installed
    OFEvaluationContext = Any  # type: ignore[misc, assignment]
    OFErrorCode = Any  # type: ignore[misc, assignment]
    FlagResolutionDetails = Any  # type: ignore[misc, assignment]
    OFReason = Any  # type: ignore[misc, assignment]
    Hook = Any  # type: ignore[misc, assignment]
    AbstractProvider = object  # type: ignore[misc, assignment]
    Metadata = Any  # type: ignore[misc, assignment]
    ProviderStatus = Any  # type: ignore[misc, assignment]

if TYPE_CHECKING:
    from litestar_flags.client import FeatureFlagClient
    from litestar_flags.context import EvaluationContext
    from litestar_flags.results import EvaluationDetails
    from litestar_flags.types import ErrorCode, EvaluationReason

__all__ = [
    "OPENFEATURE_AVAILABLE",
    "LitestarFlagsHook",
    "LitestarFlagsProvider",
    "adapt_evaluation_context",
    "map_error_code",
    "map_reason",
]

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Mapping from litestar-flags ErrorCode to OpenFeature ErrorCode
_ERROR_CODE_MAP: dict[str, str] = {
    "FLAG_NOT_FOUND": "FLAG_NOT_FOUND",
    "TYPE_MISMATCH": "TYPE_MISMATCH",
    "PARSE_ERROR": "PARSE_ERROR",
    "PROVIDER_NOT_READY": "PROVIDER_NOT_READY",
    "GENERAL_ERROR": "GENERAL",
    "TARGETING_KEY_MISSING": "TARGETING_KEY_MISSING",
    "INVALID_CONTEXT": "INVALID_CONTEXT",
}

# Mapping from litestar-flags EvaluationReason to OpenFeature Reason
_REASON_MAP: dict[str, str] = {
    "DEFAULT": "DEFAULT",
    "STATIC": "STATIC",
    "TARGETING_MATCH": "TARGETING_MATCH",
    "OVERRIDE": "STATIC",  # OpenFeature doesn't have OVERRIDE, map to STATIC
    "SPLIT": "SPLIT",
    "DISABLED": "DISABLED",
    "ERROR": "ERROR",
}


def _get_running_loop_or_none() -> asyncio.AbstractEventLoop | None:
    """Get the running event loop or None if not in async context.

    Returns:
        The running event loop or None.

    """
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _run_sync(coro: Any) -> Any:
    """Run an async coroutine synchronously.

    This handles the case where we may or may not be in an async context.
    If we are in an async context, we create a new thread to run the coroutine.
    Otherwise, we use asyncio.run().

    Args:
        coro: The coroutine to run.

    Returns:
        The result of the coroutine.

    """
    loop = _get_running_loop_or_none()
    if loop is not None:
        # We're in an async context, need to run in a thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        # Not in async context, can use asyncio.run directly
        return asyncio.run(coro)


def adapt_evaluation_context(
    of_context: OFEvaluationContext | None,
) -> EvaluationContext:
    """Convert OpenFeature EvaluationContext to litestar-flags EvaluationContext.

    Maps the OpenFeature context attributes to the corresponding litestar-flags
    context fields. Common attribute names are mapped to their respective fields,
    while additional attributes are placed in the attributes dict.

    Args:
        of_context: The OpenFeature evaluation context, or None.

    Returns:
        A litestar-flags EvaluationContext instance.

    Example:
        >>> from openfeature.evaluation_context import EvaluationContext as OFContext
        >>> of_ctx = OFContext(targeting_key="user-123", attributes={"plan": "premium"})
        >>> ctx = adapt_evaluation_context(of_ctx)
        >>> ctx.targeting_key
        'user-123'
        >>> ctx.get("plan")
        'premium'

    """
    from litestar_flags.context import EvaluationContext

    if of_context is None:
        return EvaluationContext()

    # Extract known attributes
    attrs = dict(of_context.attributes) if of_context.attributes else {}

    # Map common attribute names to litestar-flags fields
    user_id = attrs.pop("user_id", None) or attrs.pop("userId", None)
    organization_id = attrs.pop("organization_id", None) or attrs.pop("organizationId", None)
    tenant_id = attrs.pop("tenant_id", None) or attrs.pop("tenantId", None)
    environment = attrs.pop("environment", None) or attrs.pop("env", None)
    app_version = attrs.pop("app_version", None) or attrs.pop("appVersion", None) or attrs.pop("version", None)
    ip_address = attrs.pop("ip_address", None) or attrs.pop("ipAddress", None) or attrs.pop("ip", None)
    user_agent = attrs.pop("user_agent", None) or attrs.pop("userAgent", None)
    country = attrs.pop("country", None)

    return EvaluationContext(
        targeting_key=of_context.targeting_key,
        user_id=str(user_id) if user_id is not None else None,
        organization_id=str(organization_id) if organization_id is not None else None,
        tenant_id=str(tenant_id) if tenant_id is not None else None,
        environment=str(environment) if environment is not None else None,
        app_version=str(app_version) if app_version is not None else None,
        ip_address=str(ip_address) if ip_address is not None else None,
        user_agent=str(user_agent) if user_agent is not None else None,
        country=str(country) if country is not None else None,
        attributes=attrs,
    )


def map_error_code(error_code: ErrorCode | None) -> OFErrorCode | None:
    """Map litestar-flags ErrorCode to OpenFeature ErrorCode.

    Args:
        error_code: The litestar-flags error code.

    Returns:
        The corresponding OpenFeature error code, or None.

    """
    if error_code is None:
        return None

    if not OPENFEATURE_AVAILABLE:
        return None

    from openfeature.exception import ErrorCode as OFErrorCode

    mapped = _ERROR_CODE_MAP.get(error_code.value, "GENERAL")
    return OFErrorCode(mapped)


def map_reason(reason: EvaluationReason) -> OFReason:
    """Map litestar-flags EvaluationReason to OpenFeature Reason.

    Args:
        reason: The litestar-flags evaluation reason.

    Returns:
        The corresponding OpenFeature Reason enum value.

    """
    if not OPENFEATURE_AVAILABLE:
        return _REASON_MAP.get(reason.value, "UNKNOWN")  # type: ignore[return-value]

    from openfeature.flag_evaluation import Reason

    reason_str = _REASON_MAP.get(reason.value, "UNKNOWN")
    return Reason(reason_str)


# Keep aliases for backward compatibility
_map_error_code = map_error_code
_map_reason = map_reason


def _convert_to_resolution_details(
    details: EvaluationDetails[T],
    default_value: T,
) -> FlagResolutionDetails[T]:
    """Convert litestar-flags EvaluationDetails to OpenFeature FlagResolutionDetails.

    Args:
        details: The litestar-flags evaluation details.
        default_value: The default value that was passed to the evaluation.

    Returns:
        OpenFeature FlagResolutionDetails instance.

    """
    from openfeature.flag_evaluation import FlagResolutionDetails

    return FlagResolutionDetails(
        value=details.value,
        reason=_map_reason(details.reason),
        variant=details.variant,
        error_code=_map_error_code(details.error_code),
        error_message=details.error_message,
        flag_metadata=details.flag_metadata,
    )


class LitestarFlagsProvider(AbstractProvider):  # type: ignore[misc]
    """OpenFeature provider implementation for litestar-flags.

    This provider wraps a litestar-flags FeatureFlagClient and exposes it
    through the OpenFeature API, enabling interoperability with other
    OpenFeature-compatible tools and SDKs.

    The provider implements both synchronous and asynchronous resolution
    methods. The async methods are more efficient as they directly call
    the async client methods without needing to bridge sync/async contexts.

    Attributes:
        client: The underlying litestar-flags FeatureFlagClient.

    Example:
        >>> from litestar_flags.client import FeatureFlagClient
        >>> from litestar_flags.contrib.openfeature import LitestarFlagsProvider
        >>> client = FeatureFlagClient(storage=my_storage)
        >>> provider = LitestarFlagsProvider(client)
        >>> metadata = provider.get_metadata()
        >>> metadata.name
        'litestar-flags'

    """

    def __init__(
        self,
        client: FeatureFlagClient,
        hooks: list[Hook] | None = None,
    ) -> None:
        """Initialize the OpenFeature provider.

        Args:
            client: The litestar-flags FeatureFlagClient to wrap.
            hooks: Optional list of OpenFeature hooks to attach to this provider.

        Raises:
            ImportError: If openfeature-sdk is not installed.

        """
        if not OPENFEATURE_AVAILABLE:
            raise ImportError(
                "openfeature-sdk is required for LitestarFlagsProvider. "
                "Install it with: pip install litestar-flags[openfeature]"
            )

        self._client = client
        self._hooks = hooks or []
        self._status = ProviderStatus.NOT_READY

    @property
    def client(self) -> FeatureFlagClient:
        """Get the underlying litestar-flags client.

        Returns:
            The FeatureFlagClient instance.

        """
        return self._client

    def get_metadata(self) -> Metadata:
        """Get provider metadata.

        Returns:
            Metadata containing the provider name.

        """
        return Metadata(name="litestar-flags")

    def get_provider_hooks(self) -> list[Hook]:
        """Get the provider-level hooks.

        Returns:
            List of Hook instances attached to this provider.

        """
        return self._hooks

    # Lifecycle methods

    def initialize(self, evaluation_context: OFEvaluationContext | None = None) -> None:
        """Initialize the provider.

        This method is called when the provider is registered with the OpenFeature API.
        It preloads flags to warm up the cache for faster initial evaluations.

        Args:
            evaluation_context: Optional global evaluation context.

        """
        try:
            # Preload flags to warm the cache
            _run_sync(self._client.preload_flags())
            self._status = ProviderStatus.READY
            logger.info("LitestarFlagsProvider initialized successfully")
        except Exception as e:
            self._status = ProviderStatus.ERROR
            logger.error(f"Failed to initialize LitestarFlagsProvider: {e}")
            raise

    def shutdown(self) -> None:
        """Shutdown the provider and release resources.

        This method is called when the provider is removed from the OpenFeature API.
        It closes the underlying client and clears caches.

        """
        try:
            _run_sync(self._client.close())
            self._status = ProviderStatus.NOT_READY
            logger.info("LitestarFlagsProvider shutdown successfully")
        except Exception as e:
            logger.error(f"Error during LitestarFlagsProvider shutdown: {e}")

    # Synchronous resolution methods

    def resolve_boolean_details(
        self,
        flag_key: str,
        default_value: bool,
        evaluation_context: OFEvaluationContext | None = None,
    ) -> FlagResolutionDetails[bool]:
        """Resolve a boolean flag value with details.

        Args:
            flag_key: The unique key identifying the flag.
            default_value: The default value to return if resolution fails.
            evaluation_context: Optional context for flag evaluation.

        Returns:
            FlagResolutionDetails containing the resolved value and metadata.

        """
        try:
            context = adapt_evaluation_context(evaluation_context)
            details = _run_sync(self._client.get_boolean_details(flag_key, default_value, context))
            return _convert_to_resolution_details(details, default_value)
        except Exception as e:
            logger.error(f"Error resolving boolean flag '{flag_key}': {e}")
            return FlagResolutionDetails(
                value=default_value,
                reason=OFReason.ERROR,
                error_code=OFErrorCode.GENERAL,
                error_message=str(e),
            )

    def resolve_string_details(
        self,
        flag_key: str,
        default_value: str,
        evaluation_context: OFEvaluationContext | None = None,
    ) -> FlagResolutionDetails[str]:
        """Resolve a string flag value with details.

        Args:
            flag_key: The unique key identifying the flag.
            default_value: The default value to return if resolution fails.
            evaluation_context: Optional context for flag evaluation.

        Returns:
            FlagResolutionDetails containing the resolved value and metadata.

        """
        context = adapt_evaluation_context(evaluation_context)
        details = _run_sync(self._client.get_string_details(flag_key, default_value, context))
        return _convert_to_resolution_details(details, default_value)

    def resolve_integer_details(
        self,
        flag_key: str,
        default_value: int,
        evaluation_context: OFEvaluationContext | None = None,
    ) -> FlagResolutionDetails[int]:
        """Resolve an integer flag value with details.

        Args:
            flag_key: The unique key identifying the flag.
            default_value: The default value to return if resolution fails.
            evaluation_context: Optional context for flag evaluation.

        Returns:
            FlagResolutionDetails containing the resolved value and metadata.

        """
        context = adapt_evaluation_context(evaluation_context)
        # Use number_details since litestar-flags uses NUMBER type for both int and float
        details = _run_sync(self._client.get_number_details(flag_key, float(default_value), context))
        # Convert to int
        int_value = int(details.value)
        from litestar_flags.results import EvaluationDetails

        int_details = EvaluationDetails(
            value=int_value,
            flag_key=details.flag_key,
            reason=details.reason,
            variant=details.variant,
            error_code=details.error_code,
            error_message=details.error_message,
            flag_metadata=details.flag_metadata,
        )
        return _convert_to_resolution_details(int_details, default_value)

    def resolve_float_details(
        self,
        flag_key: str,
        default_value: float,
        evaluation_context: OFEvaluationContext | None = None,
    ) -> FlagResolutionDetails[float]:
        """Resolve a float flag value with details.

        Args:
            flag_key: The unique key identifying the flag.
            default_value: The default value to return if resolution fails.
            evaluation_context: Optional context for flag evaluation.

        Returns:
            FlagResolutionDetails containing the resolved value and metadata.

        """
        context = adapt_evaluation_context(evaluation_context)
        details = _run_sync(self._client.get_number_details(flag_key, default_value, context))
        return _convert_to_resolution_details(details, default_value)

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: dict[str, Any] | list[Any],
        evaluation_context: OFEvaluationContext | None = None,
    ) -> FlagResolutionDetails[dict[str, Any] | list[Any]]:
        """Resolve an object/JSON flag value with details.

        Args:
            flag_key: The unique key identifying the flag.
            default_value: The default value to return if resolution fails.
            evaluation_context: Optional context for flag evaluation.

        Returns:
            FlagResolutionDetails containing the resolved value and metadata.

        """
        context = adapt_evaluation_context(evaluation_context)
        # Convert default_value to dict if it's a list for the client call
        if isinstance(default_value, list):
            # Wrap list in a dict for the client, then extract
            details = _run_sync(self._client.get_object_details(flag_key, {"_list": default_value}, context))
            # If the result is a dict with _list key, extract it
            if isinstance(details.value, dict) and "_list" in details.value:
                from litestar_flags.results import EvaluationDetails

                list_details = EvaluationDetails(
                    value=details.value["_list"],
                    flag_key=details.flag_key,
                    reason=details.reason,
                    variant=details.variant,
                    error_code=details.error_code,
                    error_message=details.error_message,
                    flag_metadata=details.flag_metadata,
                )
                return _convert_to_resolution_details(list_details, default_value)
        else:
            details = _run_sync(self._client.get_object_details(flag_key, default_value, context))
        return _convert_to_resolution_details(details, default_value)

    # Asynchronous resolution methods

    async def resolve_boolean_details_async(
        self,
        flag_key: str,
        default_value: bool,
        evaluation_context: OFEvaluationContext | None = None,
    ) -> FlagResolutionDetails[bool]:
        """Resolve a boolean flag value asynchronously with details.

        This is more efficient than the sync version as it directly calls
        the async client methods without needing to bridge contexts.

        Args:
            flag_key: The unique key identifying the flag.
            default_value: The default value to return if resolution fails.
            evaluation_context: Optional context for flag evaluation.

        Returns:
            FlagResolutionDetails containing the resolved value and metadata.

        """
        context = adapt_evaluation_context(evaluation_context)
        details = await self._client.get_boolean_details(flag_key, default_value, context)
        return _convert_to_resolution_details(details, default_value)

    async def resolve_string_details_async(
        self,
        flag_key: str,
        default_value: str,
        evaluation_context: OFEvaluationContext | None = None,
    ) -> FlagResolutionDetails[str]:
        """Resolve a string flag value asynchronously with details.

        Args:
            flag_key: The unique key identifying the flag.
            default_value: The default value to return if resolution fails.
            evaluation_context: Optional context for flag evaluation.

        Returns:
            FlagResolutionDetails containing the resolved value and metadata.

        """
        context = adapt_evaluation_context(evaluation_context)
        details = await self._client.get_string_details(flag_key, default_value, context)
        return _convert_to_resolution_details(details, default_value)

    async def resolve_integer_details_async(
        self,
        flag_key: str,
        default_value: int,
        evaluation_context: OFEvaluationContext | None = None,
    ) -> FlagResolutionDetails[int]:
        """Resolve an integer flag value asynchronously with details.

        Args:
            flag_key: The unique key identifying the flag.
            default_value: The default value to return if resolution fails.
            evaluation_context: Optional context for flag evaluation.

        Returns:
            FlagResolutionDetails containing the resolved value and metadata.

        """
        context = adapt_evaluation_context(evaluation_context)
        details = await self._client.get_number_details(flag_key, float(default_value), context)
        int_value = int(details.value)
        from litestar_flags.results import EvaluationDetails

        int_details = EvaluationDetails(
            value=int_value,
            flag_key=details.flag_key,
            reason=details.reason,
            variant=details.variant,
            error_code=details.error_code,
            error_message=details.error_message,
            flag_metadata=details.flag_metadata,
        )
        return _convert_to_resolution_details(int_details, default_value)

    async def resolve_float_details_async(
        self,
        flag_key: str,
        default_value: float,
        evaluation_context: OFEvaluationContext | None = None,
    ) -> FlagResolutionDetails[float]:
        """Resolve a float flag value asynchronously with details.

        Args:
            flag_key: The unique key identifying the flag.
            default_value: The default value to return if resolution fails.
            evaluation_context: Optional context for flag evaluation.

        Returns:
            FlagResolutionDetails containing the resolved value and metadata.

        """
        context = adapt_evaluation_context(evaluation_context)
        details = await self._client.get_number_details(flag_key, default_value, context)
        return _convert_to_resolution_details(details, default_value)

    async def resolve_object_details_async(
        self,
        flag_key: str,
        default_value: dict[str, Any] | list[Any],
        evaluation_context: OFEvaluationContext | None = None,
    ) -> FlagResolutionDetails[dict[str, Any] | list[Any]]:
        """Resolve an object/JSON flag value asynchronously with details.

        Args:
            flag_key: The unique key identifying the flag.
            default_value: The default value to return if resolution fails.
            evaluation_context: Optional context for flag evaluation.

        Returns:
            FlagResolutionDetails containing the resolved value and metadata.

        """
        context = adapt_evaluation_context(evaluation_context)
        if isinstance(default_value, list):
            details = await self._client.get_object_details(flag_key, {"_list": default_value}, context)
            if isinstance(details.value, dict) and "_list" in details.value:
                from litestar_flags.results import EvaluationDetails

                list_details = EvaluationDetails(
                    value=details.value["_list"],
                    flag_key=details.flag_key,
                    reason=details.reason,
                    variant=details.variant,
                    error_code=details.error_code,
                    error_message=details.error_message,
                    flag_metadata=details.flag_metadata,
                )
                return _convert_to_resolution_details(list_details, default_value)
        else:
            details = await self._client.get_object_details(flag_key, default_value, context)
        return _convert_to_resolution_details(details, default_value)


class LitestarFlagsHook:
    """OpenFeature hook implementation for litestar-flags.

    This hook can be used to add custom logic at various stages of the
    flag evaluation lifecycle. It wraps user-provided callback functions
    and invokes them at the appropriate times.

    The hook supports all four lifecycle stages:
    - before: Called before flag resolution begins
    - after: Called after successful flag resolution
    - error: Called when an error occurs during resolution
    - finally_after: Called after resolution completes (regardless of success/failure)

    Example:
        >>> def log_before(context, hints):
        ...     print(f"Evaluating flag with context: {context}")
        ...
        >>> def log_after(context, details, hints):
        ...     print(f"Flag resolved to: {details.value}")
        ...
        >>> hook = LitestarFlagsHook(before=log_before, after=log_after)
        >>> provider = LitestarFlagsProvider(client, hooks=[hook])

    """

    def __init__(
        self,
        before: Any | None = None,
        after: Any | None = None,
        error: Any | None = None,
        finally_after: Any | None = None,
    ) -> None:
        """Initialize the hook with callback functions.

        Args:
            before: Callback invoked before flag resolution.
                Signature: (context: HookContext, hints: dict) -> Optional[EvaluationContext]
            after: Callback invoked after successful flag resolution.
                Signature: (context: HookContext, details: FlagEvaluationDetails, hints: dict) -> None
            error: Callback invoked when an error occurs.
                Signature: (context: HookContext, exception: Exception, hints: dict) -> None
            finally_after: Callback invoked after resolution completes.
                Signature: (context: HookContext, hints: dict) -> None

        """
        if not OPENFEATURE_AVAILABLE:
            raise ImportError(
                "openfeature-sdk is required for LitestarFlagsHook. "
                "Install it with: pip install litestar-flags[openfeature]"
            )

        self._before = before
        self._after = after
        self._error = error
        self._finally_after = finally_after

    def before(self, hook_context: Any, hints: dict[str, Any]) -> OFEvaluationContext | None:
        """Execute the before hook callback.

        Args:
            hook_context: The hook context containing flag key and other metadata.
            hints: Additional hints passed to the hook.

        Returns:
            Optional modified evaluation context.

        """
        if self._before is not None:
            return self._before(hook_context, hints)
        return None

    def after(
        self,
        hook_context: Any,
        details: Any,
        hints: dict[str, Any],
    ) -> None:
        """Execute the after hook callback.

        Args:
            hook_context: The hook context containing flag key and other metadata.
            details: The flag evaluation details.
            hints: Additional hints passed to the hook.

        """
        if self._after is not None:
            self._after(hook_context, details, hints)

    def error(
        self,
        hook_context: Any,
        exception: Exception,
        hints: dict[str, Any],
    ) -> None:
        """Execute the error hook callback.

        Args:
            hook_context: The hook context containing flag key and other metadata.
            exception: The exception that occurred during evaluation.
            hints: Additional hints passed to the hook.

        """
        if self._error is not None:
            self._error(hook_context, exception, hints)

    def finally_after(
        self,
        hook_context: Any,
        hints: dict[str, Any],
    ) -> None:
        """Execute the finally_after hook callback.

        Args:
            hook_context: The hook context containing flag key and other metadata.
            hints: Additional hints passed to the hook.

        """
        if self._finally_after is not None:
            self._finally_after(hook_context, hints)

    @property
    def supports_flag_value_type(self) -> bool:
        """Check if the hook supports all flag value types.

        Returns:
            True, as this hook supports all flag types.

        """
        return True
