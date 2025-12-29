"""Protocols and interfaces for analytics collectors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from litestar_flags.analytics.models import FlagEvaluationEvent

__all__ = ["AnalyticsCollector"]


@runtime_checkable
class AnalyticsCollector(Protocol):
    """Protocol for analytics collectors.

    All analytics collector implementations must implement this protocol.
    Methods are async to support both sync and async backends.

    Implementations:
        - InMemoryAnalyticsCollector: In-memory storage for development/testing
        - (Future) DatadogAnalyticsCollector: Datadog integration
        - (Future) PrometheusAnalyticsCollector: Prometheus metrics

    Example:
        >>> class MyCollector:
        ...     async def record(self, event: FlagEvaluationEvent) -> None:
        ...         # Store or process the event
        ...         pass
        ...
        ...     async def flush(self) -> None:
        ...         # Flush any buffered events
        ...         pass
        ...
        ...     async def close(self) -> None:
        ...         # Clean up resources
        ...         pass
        >>> isinstance(MyCollector(), AnalyticsCollector)
        True

    """

    async def record(self, event: FlagEvaluationEvent) -> None:
        """Record a flag evaluation event.

        This method should be fast and non-blocking. Implementations may
        buffer events and flush them asynchronously to avoid impacting
        flag evaluation latency.

        Args:
            event: The evaluation event to record.

        """
        ...

    async def flush(self) -> None:
        """Flush any buffered events.

        Forces immediate processing of any buffered events. This is useful
        for graceful shutdown or when events need to be persisted immediately.

        """
        ...

    async def close(self) -> None:
        """Close the collector and release any resources.

        This method should flush any remaining events and clean up
        resources such as connections or background tasks.

        """
        ...
