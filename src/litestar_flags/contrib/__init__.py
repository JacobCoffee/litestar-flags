"""Contrib modules for litestar-flags.

This package contains optional integrations for observability, monitoring,
caching, and third-party feature flag systems:

- ``otel``: OpenTelemetry integration for tracing and metrics
- ``logging``: Structured logging integration with structlog support
- ``cache_invalidation``: Automatic cache invalidation on flag updates
- ``openfeature``: OpenFeature provider for interoperability with the OpenFeature ecosystem

These modules require additional optional dependencies to be installed.

Example:
    Installing with OpenTelemetry support::

        pip install litestar-flags[otel]

    Installing with structured logging support::

        pip install litestar-flags[logging]

    Installing all observability features::

        pip install litestar-flags[observability]

    Installing with OpenFeature support::

        pip install litestar-flags[openfeature]

    Using cache invalidation::

        from litestar_flags.contrib import CacheInvalidationHook
        from litestar_flags.cache import LRUCache

        cache = LRUCache(max_size=1000)
        hook = CacheInvalidationHook(cache=cache)

    Using OpenFeature provider::

        from openfeature import api
        from litestar_flags.client import FeatureFlagClient
        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        client = FeatureFlagClient(storage=my_storage)
        provider = LitestarFlagsProvider(client)
        api.set_provider(provider)

"""

from __future__ import annotations

__all__: list[str] = []

# Export cache invalidation hook
from litestar_flags.contrib.cache_invalidation import CacheInvalidationHook as CacheInvalidationHook
from litestar_flags.contrib.cache_invalidation import CacheInvalidationMiddleware as CacheInvalidationMiddleware

__all__.extend(["CacheInvalidationHook", "CacheInvalidationMiddleware"])

# Conditionally export OTelHook if opentelemetry is available
try:
    from litestar_flags.contrib.otel import OTelHook as OTelHook

    __all__.append("OTelHook")
except ImportError:
    pass

# Conditionally export LoggingHook
# LoggingHook works with stdlib logging by default, structlog is optional
try:
    from litestar_flags.contrib.logging import LoggingHook as LoggingHook

    __all__.append("LoggingHook")
except ImportError:
    pass

# Conditionally export OpenFeature provider if openfeature-sdk is available
try:
    from litestar_flags.contrib.openfeature import LitestarFlagsHook as LitestarFlagsHook
    from litestar_flags.contrib.openfeature import LitestarFlagsProvider as LitestarFlagsProvider
    from litestar_flags.contrib.openfeature import adapt_evaluation_context as adapt_evaluation_context

    __all__.extend(["LitestarFlagsHook", "LitestarFlagsProvider", "adapt_evaluation_context"])
except ImportError:
    pass
