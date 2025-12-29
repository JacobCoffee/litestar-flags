"""In-memory analytics collector for feature flag evaluation events."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from litestar_flags.analytics.models import FlagEvaluationEvent

__all__ = ["InMemoryAnalyticsCollector"]


class InMemoryAnalyticsCollector:
    """In-memory analytics collector for development and testing.

    This collector stores evaluation events in memory with a configurable
    maximum size. When the maximum size is reached, oldest events are
    discarded to make room for new ones.

    Thread-safe implementation using asyncio.Lock for concurrent access.

    Attributes:
        max_size: Maximum number of events to store.

    Example:
        >>> from datetime import datetime, UTC
        >>> from litestar_flags.analytics import FlagEvaluationEvent, InMemoryAnalyticsCollector
        >>> from litestar_flags.types import EvaluationReason
        >>> collector = InMemoryAnalyticsCollector(max_size=1000)
        >>> event = FlagEvaluationEvent(
        ...     timestamp=datetime.now(UTC),
        ...     flag_key="my_flag",
        ...     value=True,
        ...     reason=EvaluationReason.STATIC,
        ... )
        >>> await collector.record(event)
        >>> events = await collector.get_events()
        >>> len(events)
        1

    """

    def __init__(self, max_size: int = 10000) -> None:
        """Initialize the in-memory analytics collector.

        Args:
            max_size: Maximum number of events to store. Defaults to 10000.
                When exceeded, oldest events are discarded.

        """
        self._max_size = max_size
        self._events: list[FlagEvaluationEvent] = []
        self._lock = asyncio.Lock()

    @property
    def max_size(self) -> int:
        """Return the maximum number of events to store.

        Returns:
            The configured maximum size.

        """
        return self._max_size

    async def record(self, event: FlagEvaluationEvent) -> None:
        """Record a flag evaluation event.

        Thread-safe method that stores the event in memory. If the
        maximum size is exceeded, the oldest event is removed.

        Args:
            event: The evaluation event to record.

        """
        async with self._lock:
            self._events.append(event)
            # Remove oldest events if we exceed max size
            if len(self._events) > self._max_size:
                self._events = self._events[-self._max_size :]

    async def flush(self) -> None:
        """Flush buffered events.

        For the in-memory collector, this is a no-op since events
        are stored immediately. Provided for protocol compliance.

        """
        # No-op for in-memory collector

    async def close(self) -> None:
        """Close the collector and clear all stored events.

        Releases the stored events from memory.

        """
        async with self._lock:
            self._events.clear()

    async def get_events(
        self,
        flag_key: str | None = None,
        limit: int | None = None,
    ) -> list[FlagEvaluationEvent]:
        """Retrieve stored evaluation events.

        This method is primarily intended for testing and debugging.
        It allows filtering and limiting the returned events.

        Args:
            flag_key: If provided, only return events for this flag key.
            limit: If provided, return at most this many events (most recent first).

        Returns:
            List of stored evaluation events matching the criteria.

        """
        async with self._lock:
            events = self._events.copy()

        # Filter by flag_key if provided
        if flag_key is not None:
            events = [e for e in events if e.flag_key == flag_key]

        # Apply limit (return most recent)
        if limit is not None and limit > 0:
            events = events[-limit:]

        return events

    async def get_event_count(self, flag_key: str | None = None) -> int:
        """Get the count of stored events.

        Args:
            flag_key: If provided, only count events for this flag key.

        Returns:
            The number of stored events matching the criteria.

        """
        async with self._lock:
            if flag_key is None:
                return len(self._events)
            return sum(1 for e in self._events if e.flag_key == flag_key)

    async def clear(self) -> None:
        """Clear all stored events.

        Removes all events from memory without closing the collector.

        """
        async with self._lock:
            self._events.clear()

    def __len__(self) -> int:
        """Return the number of stored events.

        Note: This is not thread-safe. Use get_event_count() for
        thread-safe counting.

        Returns:
            The current number of stored events.

        """
        return len(self._events)
