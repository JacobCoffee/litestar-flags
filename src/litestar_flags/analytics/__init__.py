"""Analytics module for feature flag evaluation tracking.

This module provides analytics collection capabilities for tracking
feature flag evaluations, enabling insights into flag usage, performance,
and targeting effectiveness.

Example:
    Basic usage with in-memory collector::

        from datetime import datetime, UTC
        from litestar_flags.analytics import (
            AnalyticsAggregator,
            FlagEvaluationEvent,
            FlagMetrics,
            InMemoryAnalyticsCollector,
        )
        from litestar_flags.types import EvaluationReason

        # Create a collector and aggregator
        collector = InMemoryAnalyticsCollector(max_size=10000)
        aggregator = AnalyticsAggregator(collector)

        # Record an evaluation event
        event = FlagEvaluationEvent(
            timestamp=datetime.now(UTC),
            flag_key="new_feature",
            value=True,
            reason=EvaluationReason.TARGETING_MATCH,
            targeting_key="user-123",
        )
        await collector.record(event)

        # Get metrics for the flag
        metrics = await aggregator.get_flag_metrics("new_feature")
        print(f"Evaluation rate: {metrics.evaluation_rate}/s")
        print(f"Unique users: {metrics.unique_users}")

"""

from __future__ import annotations

from litestar_flags.analytics.aggregator import AnalyticsAggregator, FlagMetrics
from litestar_flags.analytics.collectors import InMemoryAnalyticsCollector
from litestar_flags.analytics.models import FlagEvaluationEvent
from litestar_flags.analytics.protocols import AnalyticsCollector

__all__ = [
    "AnalyticsAggregator",
    "AnalyticsCollector",
    "FlagEvaluationEvent",
    "FlagMetrics",
    "InMemoryAnalyticsCollector",
]

# Conditionally export PrometheusExporter
try:
    from litestar_flags.analytics.exporters.prometheus import (  # noqa: F401
        PROMETHEUS_AVAILABLE,
        PrometheusExporter,
    )

    __all__.extend(["PROMETHEUS_AVAILABLE", "PrometheusExporter"])
except ImportError:
    PROMETHEUS_AVAILABLE = False
    __all__.append("PROMETHEUS_AVAILABLE")
