"""Analytics aggregator for computing metrics from feature flag evaluation events."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from litestar_flags.analytics.collectors.memory import InMemoryAnalyticsCollector
from litestar_flags.analytics.models import FlagEvaluationEvent
from litestar_flags.types import EvaluationReason

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["AnalyticsAggregator", "FlagMetrics"]


@dataclass(slots=True)
class FlagMetrics:
    """Aggregated metrics for a feature flag.

    Contains computed statistics about flag evaluations including
    evaluation rate, unique users, distributions, and latency percentiles.

    Attributes:
        evaluation_rate: Evaluations per second in the measurement window.
        unique_users: Count of unique targeting keys in the window.
        variant_distribution: Count of evaluations per variant.
        reason_distribution: Count of evaluations per reason.
        error_rate: Percentage of evaluations that resulted in errors (0-100).
        latency_p50: 50th percentile latency in milliseconds.
        latency_p90: 90th percentile latency in milliseconds.
        latency_p99: 99th percentile latency in milliseconds.
        total_evaluations: Total number of evaluations in the window.
        window_start: Start of the measurement window.
        window_end: End of the measurement window.

    Example:
        >>> metrics = FlagMetrics(
        ...     evaluation_rate=10.5,
        ...     unique_users=150,
        ...     variant_distribution={"control": 75, "treatment": 75},
        ...     reason_distribution={"SPLIT": 150},
        ...     error_rate=0.0,
        ...     latency_p50=1.2,
        ...     latency_p90=2.5,
        ...     latency_p99=5.0,
        ... )

    """

    evaluation_rate: float = 0.0
    unique_users: int = 0
    variant_distribution: dict[str, int] = field(default_factory=dict)
    reason_distribution: dict[str, int] = field(default_factory=dict)
    error_rate: float = 0.0
    latency_p50: float = 0.0
    latency_p90: float = 0.0
    latency_p99: float = 0.0
    total_evaluations: int = 0
    window_start: datetime | None = None
    window_end: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary representation.

        Returns:
            Dictionary representation of the metrics.

        """
        return {
            "evaluation_rate": self.evaluation_rate,
            "unique_users": self.unique_users,
            "variant_distribution": self.variant_distribution,
            "reason_distribution": self.reason_distribution,
            "error_rate": self.error_rate,
            "latency_p50": self.latency_p50,
            "latency_p90": self.latency_p90,
            "latency_p99": self.latency_p99,
            "total_evaluations": self.total_evaluations,
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
        }


class AnalyticsAggregator:
    """Aggregator for computing metrics from feature flag evaluation events.

    Supports multiple event sources including in-memory collectors and
    database sessions. Provides methods for computing various metrics
    including evaluation rates, unique users, distributions, and latencies.

    The aggregator uses window-based aggregation, only considering events
    within the specified time window for each metric calculation.

    Attributes:
        source: The event source (InMemoryAnalyticsCollector or AsyncSession).

    Example:
        >>> from litestar_flags.analytics import InMemoryAnalyticsCollector
        >>> collector = InMemoryAnalyticsCollector()
        >>> aggregator = AnalyticsAggregator(collector)
        >>> rate = await aggregator.get_evaluation_rate("my_flag", window_seconds=60)
        >>> metrics = await aggregator.get_flag_metrics("my_flag")

    """

    def __init__(
        self,
        source: InMemoryAnalyticsCollector | AsyncSession,
    ) -> None:
        """Initialize the analytics aggregator.

        Args:
            source: The event source to aggregate from. Can be an
                InMemoryAnalyticsCollector for in-memory events or an
                AsyncSession for database-backed events.

        """
        self._source = source
        self._is_memory_source = isinstance(source, InMemoryAnalyticsCollector)

    async def _get_events_in_window(
        self,
        flag_key: str,
        window_seconds: int,
    ) -> list[FlagEvaluationEvent]:
        """Get events from the source within a time window.

        Args:
            flag_key: The flag key to filter events.
            window_seconds: Number of seconds to look back.

        Returns:
            List of events within the time window.

        """
        since = datetime.now(UTC) - timedelta(seconds=window_seconds)

        if self._is_memory_source:
            collector = self._source
            if isinstance(collector, InMemoryAnalyticsCollector):
                # Get all events for the flag and filter by timestamp
                all_events = await collector.get_events(flag_key=flag_key)
                return [e for e in all_events if e.timestamp >= since]

        # For AsyncSession, query the database
        return await self._get_events_from_database(flag_key, window_seconds)

    async def _get_events_from_database(
        self,
        flag_key: str,
        window_seconds: int,
    ) -> list[FlagEvaluationEvent]:
        """Get events from database within a time window.

        Args:
            flag_key: The flag key to filter events.
            window_seconds: Number of seconds to look back.

        Returns:
            List of events within the time window.

        Note:
            This requires the analytics_events table to be defined.
            The implementation expects a table with columns matching
            the AnalyticsEventModel fields.

        """
        if self._is_memory_source:
            return await self._get_events_in_window(flag_key, window_seconds)

        # Import here to avoid circular imports and optional dependency
        try:
            from sqlalchemy import select

            from litestar_flags.analytics.models import AnalyticsEventModel
        except ImportError:
            return []

        session = self._source
        since = datetime.now(UTC) - timedelta(seconds=window_seconds)

        stmt = select(AnalyticsEventModel).where(
            AnalyticsEventModel.flag_key == flag_key,  # type: ignore[arg-type]
            AnalyticsEventModel.timestamp >= since,  # type: ignore[arg-type]
        )

        result = await session.execute(stmt)  # type: ignore[union-attr]
        rows = result.scalars().all()

        # Convert database models to FlagEvaluationEvent
        events = []
        for row in rows:
            # Extract value from JSON storage
            value = row.value.get("value") if row.value else None
            events.append(
                FlagEvaluationEvent(
                    timestamp=row.timestamp,
                    flag_key=row.flag_key,
                    value=value,
                    reason=EvaluationReason(row.reason) if row.reason else EvaluationReason.DEFAULT,
                    variant=row.variant,
                    targeting_key=row.targeting_key,
                    context_attributes=row.context_attributes or {},
                    evaluation_duration_ms=row.evaluation_duration_ms or 0.0,
                )
            )
        return events

    def _is_error_event(self, event: FlagEvaluationEvent) -> bool:
        """Check if an event represents an error.

        Args:
            event: The event to check.

        Returns:
            True if the event has ERROR reason.

        """
        return event.reason == EvaluationReason.ERROR

    async def get_evaluation_rate(
        self,
        flag_key: str,
        window_seconds: int = 60,
    ) -> float:
        """Calculate the evaluation rate for a flag.

        Args:
            flag_key: The key of the flag to measure.
            window_seconds: The time window in seconds (default: 60).

        Returns:
            Evaluations per second within the time window.

        """
        events = await self._get_events_in_window(flag_key, window_seconds)
        if not events or window_seconds <= 0:
            return 0.0
        return len(events) / window_seconds

    async def get_unique_users(
        self,
        flag_key: str,
        window_seconds: int = 3600,
    ) -> int:
        """Count unique targeting keys for a flag.

        Args:
            flag_key: The key of the flag to measure.
            window_seconds: The time window in seconds (default: 3600).

        Returns:
            Count of unique targeting keys within the time window.

        """
        events = await self._get_events_in_window(flag_key, window_seconds)
        unique_keys = {event.targeting_key for event in events if event.targeting_key}
        return len(unique_keys)

    async def get_variant_distribution(
        self,
        flag_key: str,
        window_seconds: int = 3600,
    ) -> dict[str, int]:
        """Get the distribution of variants for a flag.

        Args:
            flag_key: The key of the flag to measure.
            window_seconds: The time window in seconds (default: 3600).

        Returns:
            Dictionary mapping variant names to evaluation counts.

        """
        events = await self._get_events_in_window(flag_key, window_seconds)
        counter: Counter[str] = Counter()
        for event in events:
            variant = event.variant or "default"
            counter[variant] += 1
        return dict(counter)

    async def get_reason_distribution(
        self,
        flag_key: str,
        window_seconds: int = 3600,
    ) -> dict[str, int]:
        """Get the distribution of evaluation reasons for a flag.

        Args:
            flag_key: The key of the flag to measure.
            window_seconds: The time window in seconds (default: 3600).

        Returns:
            Dictionary mapping reason strings to evaluation counts.

        """
        events = await self._get_events_in_window(flag_key, window_seconds)
        counter: Counter[str] = Counter()
        for event in events:
            reason_str = event.reason.value if isinstance(event.reason, EvaluationReason) else str(event.reason)
            counter[reason_str] += 1
        return dict(counter)

    async def get_error_rate(
        self,
        flag_key: str,
        window_seconds: int = 3600,
    ) -> float:
        """Calculate the error rate for a flag.

        Args:
            flag_key: The key of the flag to measure.
            window_seconds: The time window in seconds (default: 3600).

        Returns:
            Percentage of evaluations that resulted in errors (0-100).

        """
        events = await self._get_events_in_window(flag_key, window_seconds)
        if not events:
            return 0.0

        error_count = sum(1 for event in events if self._is_error_event(event))
        return (error_count / len(events)) * 100

    async def get_latency_percentiles(
        self,
        flag_key: str,
        percentiles: list[float] | None = None,
    ) -> dict[float, float]:
        """Calculate latency percentiles for a flag.

        Args:
            flag_key: The key of the flag to measure.
            percentiles: List of percentiles to calculate (default: [50, 90, 99]).

        Returns:
            Dictionary mapping percentile values to latencies in milliseconds.

        """
        if percentiles is None:
            percentiles = [50.0, 90.0, 99.0]

        events = await self._get_events_in_window(flag_key, window_seconds=3600)
        latencies = [event.evaluation_duration_ms for event in events if event.evaluation_duration_ms > 0]

        if not latencies:
            return dict.fromkeys(percentiles, 0.0)

        if len(latencies) == 1:
            # With only one data point, all percentiles are the same
            return dict.fromkeys(percentiles, latencies[0])

        # Calculate quantiles using linear interpolation
        result: dict[float, float] = {}
        sorted_latencies = sorted(latencies)

        for p in percentiles:
            if p <= 0 or p >= 100:
                result[p] = 0.0
                continue

            index = (p / 100) * (len(sorted_latencies) - 1)
            lower_idx = int(index)
            upper_idx = min(lower_idx + 1, len(sorted_latencies) - 1)
            fraction = index - lower_idx

            # Linear interpolation
            result[p] = sorted_latencies[lower_idx] + fraction * (
                sorted_latencies[upper_idx] - sorted_latencies[lower_idx]
            )

        return result

    async def get_flag_metrics(
        self,
        flag_key: str,
        window_seconds: int = 3600,
    ) -> FlagMetrics:
        """Get all aggregated metrics for a flag.

        This is a convenience method that computes all available metrics
        in a single call.

        Args:
            flag_key: The key of the flag to measure.
            window_seconds: The time window in seconds (default: 3600).

        Returns:
            FlagMetrics object containing all computed metrics.

        """
        events = await self._get_events_in_window(flag_key, window_seconds)
        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=window_seconds)

        if not events:
            return FlagMetrics(
                window_start=window_start,
                window_end=now,
            )

        # Calculate all metrics from the same event set
        total = len(events)
        unique_keys = {event.targeting_key for event in events if event.targeting_key}

        # Variant distribution
        variant_counter: Counter[str] = Counter()
        for event in events:
            variant = event.variant or "default"
            variant_counter[variant] += 1

        # Reason distribution
        reason_counter: Counter[str] = Counter()
        error_count = 0
        for event in events:
            reason_str = event.reason.value if isinstance(event.reason, EvaluationReason) else str(event.reason)
            reason_counter[reason_str] += 1
            if self._is_error_event(event):
                error_count += 1

        # Latency percentiles
        latencies = [event.evaluation_duration_ms for event in events if event.evaluation_duration_ms > 0]
        p50, p90, p99 = 0.0, 0.0, 0.0

        if latencies:
            sorted_latencies = sorted(latencies)
            n = len(sorted_latencies)
            if n == 1:
                p50 = p90 = p99 = sorted_latencies[0]
            else:
                p50 = self._percentile(sorted_latencies, 50)
                p90 = self._percentile(sorted_latencies, 90)
                p99 = self._percentile(sorted_latencies, 99)

        return FlagMetrics(
            evaluation_rate=total / window_seconds if window_seconds > 0 else 0.0,
            unique_users=len(unique_keys),
            variant_distribution=dict(variant_counter),
            reason_distribution=dict(reason_counter),
            error_rate=(error_count / total) * 100 if total > 0 else 0.0,
            latency_p50=p50,
            latency_p90=p90,
            latency_p99=p99,
            total_evaluations=total,
            window_start=window_start,
            window_end=now,
        )

    def _percentile(self, sorted_data: list[float], p: float) -> float:
        """Calculate a percentile from sorted data.

        Args:
            sorted_data: Pre-sorted list of values.
            p: Percentile to calculate (0-100).

        Returns:
            The percentile value with linear interpolation.

        """
        if not sorted_data:
            return 0.0
        if len(sorted_data) == 1:
            return sorted_data[0]

        index = (p / 100) * (len(sorted_data) - 1)
        lower_idx = int(index)
        upper_idx = min(lower_idx + 1, len(sorted_data) - 1)
        fraction = index - lower_idx

        return sorted_data[lower_idx] + fraction * (sorted_data[upper_idx] - sorted_data[lower_idx])
