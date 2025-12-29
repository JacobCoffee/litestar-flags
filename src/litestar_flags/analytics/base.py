"""Base protocol and data classes for analytics collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    pass

__all__ = ["AnalyticsCollector", "AnalyticsEvent"]


@dataclass(slots=True)
class AnalyticsEvent:
    """Represents a single feature flag evaluation event.

    Attributes:
        timestamp: When the evaluation occurred.
        flag_key: The key of the evaluated flag.
        value: The evaluated value (can be bool, str, int, float, or dict).
        reason: Why this value was returned (e.g., "default", "rule_match", "override").
        variant: The variant key if a variant was selected, None otherwise.
        targeting_key: The key used for targeting (e.g., user ID), None if anonymous.
        context_attributes: Additional context attributes used in evaluation.
        evaluation_duration_ms: Time taken to evaluate the flag in milliseconds.

    """

    timestamp: datetime
    flag_key: str
    value: bool | str | int | float | dict[str, Any]
    reason: str
    variant: str | None = None
    targeting_key: str | None = None
    context_attributes: dict[str, Any] = field(default_factory=dict)
    evaluation_duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the event to a dictionary.

        Returns:
            Dictionary representation of the event.

        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "flag_key": self.flag_key,
            "value": self.value,
            "reason": self.reason,
            "variant": self.variant,
            "targeting_key": self.targeting_key,
            "context_attributes": self.context_attributes,
            "evaluation_duration_ms": self.evaluation_duration_ms,
        }


@runtime_checkable
class AnalyticsCollector(Protocol):
    """Protocol for analytics collectors.

    Analytics collectors receive evaluation events and store them for later
    analysis. Implementations may write to databases, send to external services,
    or aggregate metrics.

    Implementations:
        - InMemoryAnalyticsCollector: In-memory storage for testing
        - DatabaseAnalyticsCollector: SQLAlchemy-based persistent storage
        - RedisAnalyticsCollector: Redis-based distributed storage

    """

    async def record(self, event: AnalyticsEvent) -> None:
        """Record a single analytics event.

        Args:
            event: The analytics event to record.

        """
        ...

    async def record_batch(self, events: list[AnalyticsEvent]) -> None:
        """Record multiple analytics events in a batch.

        Args:
            events: List of analytics events to record.

        """
        ...

    async def flush(self) -> None:
        """Flush any buffered events to persistent storage.

        This should be called periodically and before shutdown to ensure
        all events are persisted.

        """
        ...

    async def close(self) -> None:
        """Close the collector and release any resources.

        This should flush any pending events and clean up resources.

        """
        ...
