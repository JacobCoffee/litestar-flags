"""Prometheus metrics exporter for feature flag analytics.

This module provides Prometheus metrics integration for feature flag evaluations,
enabling monitoring and alerting through Prometheus-compatible systems.

Example:
    Basic usage with Prometheus::

        from litestar_flags.analytics.exporters.prometheus import PrometheusExporter

        # Create the exporter
        exporter = PrometheusExporter()

        # Record evaluation events directly
        await exporter.record(event)

        # Or update from an aggregator
        await exporter.update_from_aggregator(aggregator, ["flag_1", "flag_2"])

    Custom registry::

        from prometheus_client import CollectorRegistry

        registry = CollectorRegistry()
        exporter = PrometheusExporter(registry=registry, prefix="myapp")

Requires:
    prometheus_client>=0.17.0

"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

    from litestar_flags.analytics.models import FlagEvaluationEvent

# Handle optional prometheus_client import
try:
    from prometheus_client import REGISTRY as PROM_REGISTRY
    from prometheus_client import CollectorRegistry as PromCollectorRegistry
    from prometheus_client import Counter as PromCounter
    from prometheus_client import Gauge as PromGauge
    from prometheus_client import Histogram as PromHistogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    PROM_REGISTRY = None  # type: ignore[assignment]
    PromCollectorRegistry = None  # type: ignore[assignment]
    PromCounter = None  # type: ignore[assignment]
    PromGauge = None  # type: ignore[assignment]
    PromHistogram = None  # type: ignore[assignment]


__all__ = ["PROMETHEUS_AVAILABLE", "PrometheusExporter"]

# Default histogram buckets for evaluation duration (in seconds)
# Ranges from 100 microseconds to 1 second
DEFAULT_DURATION_BUCKETS = (
    0.0001,  # 100us
    0.0005,  # 500us
    0.001,  # 1ms
    0.005,  # 5ms
    0.01,  # 10ms
    0.025,  # 25ms
    0.05,  # 50ms
    0.1,  # 100ms
    0.25,  # 250ms
    0.5,  # 500ms
    1.0,  # 1s
)


@runtime_checkable
class MetricsProvider(Protocol):
    """Protocol for objects that provide flag metrics.

    This protocol is compatible with the FlagMetrics dataclass and any
    object that has the required attributes.

    """

    @property
    def unique_users(self) -> int:
        """Number of unique users who evaluated the flag."""
        ...

    @property
    def error_rate(self) -> float:
        """Error rate as a percentage (0-100)."""
        ...

    @property
    def total_evaluations(self) -> int:
        """Total number of evaluations."""
        ...


class PrometheusExporter:
    """Prometheus metrics exporter for feature flag evaluations.

    Exposes feature flag metrics in Prometheus format for monitoring
    and alerting. This exporter implements the AnalyticsCollector protocol,
    allowing it to receive evaluation events directly.

    Metrics exported:
        - feature_flag_evaluations_total: Counter of flag evaluations
            Labels: flag_key, reason, variant
        - feature_flag_evaluation_duration_seconds: Histogram of evaluation times
            Labels: flag_key
        - feature_flag_unique_users: Gauge of unique users per flag
            Labels: flag_key
        - feature_flag_error_rate: Gauge of error rate per flag
            Labels: flag_key

    Attributes:
        registry: The Prometheus registry to use for metrics.
        prefix: Optional prefix for metric names.

    Example:
        >>> exporter = PrometheusExporter()
        >>> await exporter.record(evaluation_event)
        >>> # Metrics are automatically updated

    """

    def __init__(
        self,
        registry: CollectorRegistry | None = None,
        prefix: str = "",
        duration_buckets: tuple[float, ...] = DEFAULT_DURATION_BUCKETS,
    ) -> None:
        """Initialize the Prometheus exporter.

        Args:
            registry: Custom Prometheus registry. If not provided, uses the default
                global registry.
            prefix: Optional prefix for metric names (e.g., "myapp" -> "myapp_feature_flag_*").
            duration_buckets: Custom histogram buckets for duration measurements in seconds.

        Raises:
            ImportError: If prometheus_client is not installed.

        """
        if not PROMETHEUS_AVAILABLE or PromCounter is None:
            raise ImportError(
                "prometheus_client is required for PrometheusExporter. "
                "Install it with: pip install litestar-flags[prometheus]"
            )

        self._registry: CollectorRegistry = registry or PROM_REGISTRY  # type: ignore[assignment]
        self._prefix = f"{prefix}_" if prefix else ""
        self._lock = asyncio.Lock()

        # Track unique users per flag (using sets)
        self._unique_users: dict[str, set[str]] = defaultdict(set)

        # Track error counts and total counts for error rate calculation
        self._error_counts: dict[str, int] = defaultdict(int)
        self._total_counts: dict[str, int] = defaultdict(int)

        # Create metrics
        self._evaluations_counter: Counter = PromCounter(  # type: ignore[assignment]
            f"{self._prefix}feature_flag_evaluations_total",
            "Total number of feature flag evaluations",
            labelnames=["flag_key", "reason", "variant"],
            registry=self._registry,
        )

        self._duration_histogram: Histogram = PromHistogram(  # type: ignore[assignment]
            f"{self._prefix}feature_flag_evaluation_duration_seconds",
            "Duration of feature flag evaluations in seconds",
            labelnames=["flag_key"],
            buckets=duration_buckets,
            registry=self._registry,
        )

        self._unique_users_gauge: Gauge = PromGauge(  # type: ignore[assignment]
            f"{self._prefix}feature_flag_unique_users",
            "Number of unique users who evaluated each flag",
            labelnames=["flag_key"],
            registry=self._registry,
        )

        self._error_rate_gauge: Gauge = PromGauge(  # type: ignore[assignment]
            f"{self._prefix}feature_flag_error_rate",
            "Error rate for feature flag evaluations (0.0 to 1.0)",
            labelnames=["flag_key"],
            registry=self._registry,
        )

    @property
    def registry(self) -> CollectorRegistry:
        """Get the Prometheus registry.

        Returns:
            The Prometheus registry used by this exporter.

        """
        return self._registry

    @property
    def evaluations_counter(self) -> Counter:
        """Get the evaluations counter metric.

        Returns:
            The Counter metric for flag evaluations.

        """
        return self._evaluations_counter

    @property
    def duration_histogram(self) -> Histogram:
        """Get the duration histogram metric.

        Returns:
            The Histogram metric for evaluation durations.

        """
        return self._duration_histogram

    @property
    def unique_users_gauge(self) -> Gauge:
        """Get the unique users gauge metric.

        Returns:
            The Gauge metric for unique users.

        """
        return self._unique_users_gauge

    @property
    def error_rate_gauge(self) -> Gauge:
        """Get the error rate gauge metric.

        Returns:
            The Gauge metric for error rates.

        """
        return self._error_rate_gauge

    async def record(self, event: FlagEvaluationEvent) -> None:
        """Record a single analytics event.

        Updates all Prometheus metrics based on the evaluation event.
        This method implements the AnalyticsCollector protocol.

        Args:
            event: The analytics event to record.

        """
        flag_key = event.flag_key
        reason = event.reason if isinstance(event.reason, str) else event.reason.value
        variant = event.variant or ""

        # Update evaluations counter
        self._evaluations_counter.labels(
            flag_key=flag_key,
            reason=reason,
            variant=variant,
        ).inc()

        # Update duration histogram (convert from ms to seconds)
        latency_ms = getattr(event, "latency_ms", None) or getattr(event, "evaluation_duration_ms", None) or 0.0
        if latency_ms > 0:
            self._duration_histogram.labels(flag_key=flag_key).observe(latency_ms / 1000.0)

        async with self._lock:
            # Track unique users
            targeting_key = event.targeting_key
            if targeting_key:
                self._unique_users[flag_key].add(targeting_key)
                self._unique_users_gauge.labels(flag_key=flag_key).set(len(self._unique_users[flag_key]))

            # Track errors for error rate calculation
            self._total_counts[flag_key] += 1

            # Check if this is an error event
            is_error = reason == "ERROR"

            if is_error:
                self._error_counts[flag_key] += 1

            # Update error rate gauge
            total = self._total_counts[flag_key]
            if total > 0:
                error_rate = self._error_counts[flag_key] / total
                self._error_rate_gauge.labels(flag_key=flag_key).set(error_rate)

    async def record_batch(self, events: list[FlagEvaluationEvent]) -> None:
        """Record multiple analytics events in a batch.

        Args:
            events: List of analytics events to record.

        """
        for event in events:
            await self.record(event)

    async def flush(self) -> None:
        """Flush any buffered data.

        For Prometheus, metrics are updated immediately, so this is a no-op.
        Provided for AnalyticsCollector protocol compliance.

        """
        # Prometheus metrics are updated immediately, nothing to flush

    async def close(self) -> None:
        """Close the exporter and clean up resources.

        Clears internal tracking state but does not unregister metrics
        from the Prometheus registry.

        """
        async with self._lock:
            self._unique_users.clear()
            self._error_counts.clear()
            self._total_counts.clear()

    def update_from_metrics(
        self,
        flag_key: str,
        metrics: MetricsProvider | dict[str, Any],
    ) -> None:
        """Update gauge metrics from a metrics object or dictionary.

        This method syncs Prometheus gauges with pre-aggregated statistics
        from a FlagMetrics object or a compatible dictionary.

        Args:
            flag_key: The flag key to update metrics for.
            metrics: A MetricsProvider (like FlagMetrics) or a dictionary with
                keys: unique_users, error_rate (0-100), total_evaluations.

        Example:
            >>> from litestar_flags.analytics.aggregator import AnalyticsAggregator
            >>> aggregator = AnalyticsAggregator(collector)
            >>> metrics = aggregator.get_flag_metrics("feature_a")
            >>> exporter.update_from_metrics("feature_a", metrics)

        """
        unique_users: int
        error_rate: float

        if isinstance(metrics, dict):
            metrics_dict = cast(dict[str, Any], metrics)
            unique_users = int(metrics_dict.get("unique_users") or 0)
            error_rate = float(metrics_dict.get("error_rate") or 0.0)
        else:
            unique_users = metrics.unique_users
            error_rate = metrics.error_rate

        # Update unique users gauge
        self._unique_users_gauge.labels(flag_key=flag_key).set(unique_users)

        # Update error rate gauge (convert from percentage to 0-1 ratio)
        self._error_rate_gauge.labels(flag_key=flag_key).set(error_rate / 100.0)

    async def update_from_aggregator(
        self,
        aggregator: Any,
        flag_keys: Sequence[str],
        window_seconds: int = 3600,
    ) -> None:
        """Update gauge metrics from an analytics aggregator.

        This method is useful for syncing Prometheus gauges with
        pre-aggregated statistics from an AnalyticsAggregator.

        Args:
            aggregator: An AnalyticsAggregator instance with get_flag_metrics
                or get_flag_metrics_async method.
            flag_keys: List of flag keys to update metrics for.
            window_seconds: Time window for metric aggregation (default: 3600).

        Example:
            >>> from litestar_flags.analytics.aggregator import AnalyticsAggregator
            >>> aggregator = AnalyticsAggregator(collector)
            >>> await exporter.update_from_aggregator(
            ...     aggregator=aggregator,
            ...     flag_keys=["feature_a", "feature_b"],
            ... )

        """
        for flag_key in flag_keys:
            try:
                # Try async method first, then fall back to sync
                if hasattr(aggregator, "get_flag_metrics_async"):
                    metrics = await aggregator.get_flag_metrics_async(flag_key, window_seconds)
                elif hasattr(aggregator, "get_flag_metrics"):
                    metrics = aggregator.get_flag_metrics(flag_key, window_seconds)
                else:
                    continue

                self.update_from_metrics(flag_key, metrics)

            except Exception:  # noqa: S112
                # Silently ignore errors from individual flag stats retrieval
                # to avoid disrupting the update of other flags
                continue

    def get_tracked_flag_keys(self) -> list[str]:
        """Get list of flag keys that have been tracked.

        Returns:
            List of flag keys that have recorded evaluations.

        """
        return list(self._unique_users.keys() | self._total_counts.keys())

    async def reset_flag_stats(self, flag_key: str) -> None:
        """Reset internal tracking stats for a specific flag.

        This clears the unique users set and error tracking for the flag.
        Note: This does not reset Prometheus metrics themselves.

        Args:
            flag_key: The flag key to reset stats for.

        """
        async with self._lock:
            if flag_key in self._unique_users:
                del self._unique_users[flag_key]
            if flag_key in self._error_counts:
                del self._error_counts[flag_key]
            if flag_key in self._total_counts:
                del self._total_counts[flag_key]

    async def reset_all_stats(self) -> None:
        """Reset all internal tracking stats.

        Clears all unique user sets and error tracking.
        Note: This does not reset Prometheus metrics themselves.

        """
        async with self._lock:
            self._unique_users.clear()
            self._error_counts.clear()
            self._total_counts.clear()
