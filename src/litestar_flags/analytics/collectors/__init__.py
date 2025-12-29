"""Analytics collectors for feature flag evaluation events."""

from __future__ import annotations

from litestar_flags.analytics.collectors.memory import InMemoryAnalyticsCollector

__all__ = ["InMemoryAnalyticsCollector"]

# Conditionally export database collector if advanced-alchemy is available
try:
    from litestar_flags.analytics.collectors.database import (  # noqa: F401
        DatabaseAnalyticsCollector,
    )

    __all__.append("DatabaseAnalyticsCollector")
except ImportError:
    pass
