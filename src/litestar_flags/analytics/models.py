"""Analytics models for feature flag evaluation tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from litestar_flags.models.base import HAS_ADVANCED_ALCHEMY
from litestar_flags.types import EvaluationReason

if TYPE_CHECKING:
    pass

__all__ = ["AnalyticsEventModel", "FlagEvaluationEvent"]


if HAS_ADVANCED_ALCHEMY:
    from advanced_alchemy.base import UUIDv7AuditBase
    from sqlalchemy import JSON, Float, Index, String
    from sqlalchemy.orm import Mapped, mapped_column

    class AnalyticsEventModel(UUIDv7AuditBase):
        """SQLAlchemy model for analytics events.

        Stores feature flag evaluation events for analysis and reporting.
        Designed for high-volume writes with appropriate indexes for common queries.

        Attributes:
            timestamp: When the evaluation occurred.
            flag_key: The key of the evaluated flag.
            value: The evaluated value stored as JSON.
            reason: Why this value was returned.
            variant: The variant key if applicable.
            targeting_key: The key used for targeting (e.g., user ID).
            context_attributes: Additional context attributes as JSON.
            evaluation_duration_ms: Evaluation time in milliseconds.

        """

        __tablename__ = "analytics_events"

        timestamp: Mapped[datetime] = mapped_column(index=True)
        flag_key: Mapped[str] = mapped_column(String(255), index=True)
        value: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
        reason: Mapped[str] = mapped_column(String(100))
        variant: Mapped[str | None] = mapped_column(String(255), default=None)
        targeting_key: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
        context_attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
        evaluation_duration_ms: Mapped[float | None] = mapped_column(Float, default=None)

        __table_args__ = (
            Index("ix_analytics_events_flag_timestamp", "flag_key", "timestamp"),
            Index("ix_analytics_events_targeting_timestamp", "targeting_key", "timestamp"),
        )

        def __repr__(self) -> str:
            return f"<AnalyticsEventModel(flag_key={self.flag_key!r}, timestamp={self.timestamp!r})>"

else:
    # Fallback for when advanced-alchemy is not installed
    from uuid import uuid4

    @dataclass(slots=True)
    class AnalyticsEventModel:  # type: ignore[no-redef]
        """Analytics event model (dataclass fallback when advanced-alchemy not installed)."""

        timestamp: datetime
        flag_key: str
        reason: str
        id: UUID = field(default_factory=uuid4)
        value: dict[str, Any] | None = None
        variant: str | None = None
        targeting_key: str | None = None
        context_attributes: dict[str, Any] = field(default_factory=dict)
        evaluation_duration_ms: float | None = None
        created_at: datetime | None = None
        updated_at: datetime | None = None

        def __repr__(self) -> str:
            return f"<AnalyticsEventModel(flag_key={self.flag_key!r}, timestamp={self.timestamp!r})>"


@dataclass(slots=True)
class FlagEvaluationEvent:
    """Event capturing a single feature flag evaluation.

    Records detailed information about each flag evaluation for analytics,
    debugging, and monitoring purposes. This model follows the OpenFeature
    specification patterns for evaluation telemetry.

    Attributes:
        timestamp: When the evaluation occurred (UTC).
        flag_key: The key of the evaluated flag.
        value: The evaluated flag value (any type).
        reason: The reason for the evaluation result.
        variant: The variant key if a variant was selected.
        targeting_key: The targeting key used for evaluation (e.g., user ID).
        context_attributes: Additional context attributes used in evaluation.
        evaluation_duration_ms: Time taken to evaluate the flag in milliseconds.

    Example:
        >>> from datetime import datetime, UTC
        >>> event = FlagEvaluationEvent(
        ...     timestamp=datetime.now(UTC),
        ...     flag_key="new_checkout",
        ...     value=True,
        ...     reason=EvaluationReason.TARGETING_MATCH,
        ...     variant="beta_users",
        ...     targeting_key="user-123",
        ...     context_attributes={"plan": "premium"},
        ...     evaluation_duration_ms=1.5,
        ... )
        >>> event.flag_key
        'new_checkout'

    """

    timestamp: datetime
    flag_key: str
    value: Any
    reason: EvaluationReason
    variant: str | None = None
    targeting_key: str | None = None
    context_attributes: dict[str, Any] = field(default_factory=dict)
    evaluation_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary representation of the evaluation event.

        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "flag_key": self.flag_key,
            "value": self.value,
            "reason": self.reason.value,
            "variant": self.variant,
            "targeting_key": self.targeting_key,
            "context_attributes": self.context_attributes,
            "evaluation_duration_ms": self.evaluation_duration_ms,
        }
