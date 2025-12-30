"""Analytics controller for the Admin API.

This module provides a Litestar controller for querying analytics data through
the Admin API. It includes endpoints for retrieving metrics, events, trends,
and exporting analytics data with proper permission guards.

Example:
    Registering the controller with a Litestar app::

        from litestar import Litestar
        from litestar_flags.admin.controllers import AnalyticsController

        app = Litestar(
            route_handlers=[AnalyticsController],
        )

"""

from __future__ import annotations

import csv
import io
import math
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import uuid4

from litestar import Controller, get
from litestar.datastructures import State
from litestar.di import Provide
from litestar.exceptions import HTTPException
from litestar.params import Parameter
from litestar.response import Response
from litestar.status_codes import HTTP_200_OK
from msgspec import Struct

from litestar_flags.admin.dto import (
    EventResponse,
    EventsResponse,
    MetricsResponse,
)
from litestar_flags.admin.guards import Permission, require_permission
from litestar_flags.analytics import AnalyticsAggregator, FlagMetrics, InMemoryAnalyticsCollector
from litestar_flags.analytics.models import FlagEvaluationEvent
from litestar_flags.types import EvaluationReason

if TYPE_CHECKING:
    pass

__all__ = ["AnalyticsController"]


# =============================================================================
# Additional DTOs for Analytics
# =============================================================================


class DashboardFlagSummary(Struct, frozen=True):
    """Summary metrics for a single flag in the dashboard.

    Attributes:
        flag_key: The key of the flag.
        total_evaluations: Total number of evaluations in the window.
        evaluation_rate: Evaluations per second.
        unique_users: Count of unique targeting keys.
        error_rate: Percentage of evaluations that resulted in errors.
        top_variant: Most frequently returned variant.

    """

    flag_key: str
    total_evaluations: int
    evaluation_rate: float
    unique_users: int
    error_rate: float
    top_variant: str | None = None


class DashboardResponse(Struct, frozen=True):
    """Response DTO for dashboard endpoint.

    Attributes:
        total_flags_evaluated: Total number of unique flags with evaluations.
        total_evaluations: Total evaluations across all flags.
        overall_error_rate: Average error rate across all flags.
        overall_evaluation_rate: Total evaluations per second.
        flag_summaries: List of per-flag summary metrics.
        window_start: Start of the measurement window.
        window_end: End of the measurement window.

    """

    total_flags_evaluated: int
    total_evaluations: int
    overall_error_rate: float
    overall_evaluation_rate: float
    flag_summaries: list[DashboardFlagSummary]
    window_start: datetime | None = None
    window_end: datetime | None = None


class TrendDataPoint(Struct, frozen=True):
    """A single data point in a trend.

    Attributes:
        timestamp: The start of this time bucket.
        count: Number of evaluations in this bucket.
        unique_users: Unique users in this bucket.
        error_count: Number of errors in this bucket.

    """

    timestamp: datetime
    count: int
    unique_users: int
    error_count: int


class TrendsResponse(Struct, frozen=True):
    """Response DTO for trends endpoint.

    Attributes:
        flag_key: The flag key for these trends.
        granularity: The time granularity (hour, day, week).
        data_points: List of trend data points.
        window_start: Start of the measurement window.
        window_end: End of the measurement window.

    """

    flag_key: str
    granularity: str
    data_points: list[TrendDataPoint]
    window_start: datetime | None = None
    window_end: datetime | None = None


class ExportFormat(Struct, frozen=True):
    """Export format options.

    Attributes:
        CSV: Export as CSV.
        JSON: Export as JSON.

    """

    CSV: str = "csv"
    JSON: str = "json"


# =============================================================================
# Dependency Providers
# =============================================================================


async def provide_analytics_aggregator(state: State) -> AnalyticsAggregator:
    """Provide the analytics aggregator from app state.

    Args:
        state: The application state object.

    Returns:
        The configured AnalyticsAggregator instance.

    Raises:
        HTTPException: If no analytics aggregator is configured.

    """
    aggregator = getattr(state, "feature_flags_analytics_aggregator", None)
    if aggregator is not None:
        return aggregator

    # Try to create one from the collector
    collector = getattr(state, "feature_flags_analytics_collector", None)
    if collector is not None:
        return AnalyticsAggregator(collector)

    raise HTTPException(
        status_code=500,
        detail="Feature flags analytics not configured",
    )


async def provide_analytics_collector(state: State) -> InMemoryAnalyticsCollector:
    """Provide the analytics collector from app state.

    Args:
        state: The application state object.

    Returns:
        The configured InMemoryAnalyticsCollector instance.

    Raises:
        HTTPException: If no analytics collector is configured.

    """
    collector = getattr(state, "feature_flags_analytics_collector", None)
    if collector is None:
        raise HTTPException(
            status_code=500,
            detail="Feature flags analytics collector not configured",
        )
    return collector


# =============================================================================
# Helper Functions
# =============================================================================


def _event_to_response(event: FlagEvaluationEvent) -> EventResponse:
    """Convert a FlagEvaluationEvent to an EventResponse DTO.

    Args:
        event: The evaluation event to convert.

    Returns:
        An EventResponse DTO.

    """
    return EventResponse(
        id=uuid4(),  # Events don't have IDs in memory, generate one
        timestamp=event.timestamp,
        flag_key=event.flag_key,
        value=event.value,
        reason=event.reason,
        variant=event.variant,
        targeting_key=event.targeting_key,
        context_attributes=event.context_attributes,
        evaluation_duration_ms=event.evaluation_duration_ms,
    )


def _metrics_to_response(flag_key: str, metrics: FlagMetrics) -> MetricsResponse:
    """Convert a FlagMetrics to a MetricsResponse DTO.

    Args:
        flag_key: The flag key for these metrics.
        metrics: The metrics to convert.

    Returns:
        A MetricsResponse DTO.

    """
    return MetricsResponse(
        flag_key=flag_key,
        evaluation_rate=metrics.evaluation_rate,
        unique_users=metrics.unique_users,
        total_evaluations=metrics.total_evaluations,
        variant_distribution=metrics.variant_distribution,
        reason_distribution=metrics.reason_distribution,
        error_rate=metrics.error_rate,
        latency_p50=metrics.latency_p50,
        latency_p90=metrics.latency_p90,
        latency_p99=metrics.latency_p99,
        window_start=metrics.window_start,
        window_end=metrics.window_end,
    )


def _filter_events(
    events: list[FlagEvaluationEvent],
    *,
    flag_key: str | None = None,
    targeting_key: str | None = None,
    reason: EvaluationReason | None = None,
    variant: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[FlagEvaluationEvent]:
    """Filter events based on query parameters.

    Args:
        events: The list of events to filter.
        flag_key: Filter by flag key.
        targeting_key: Filter by targeting key.
        reason: Filter by evaluation reason.
        variant: Filter by variant.
        since: Only include events after this timestamp.
        until: Only include events before this timestamp.

    Returns:
        Filtered list of events.

    """
    filtered = events

    if flag_key is not None:
        filtered = [e for e in filtered if e.flag_key == flag_key]

    if targeting_key is not None:
        filtered = [e for e in filtered if e.targeting_key == targeting_key]

    if reason is not None:
        filtered = [e for e in filtered if e.reason == reason]

    if variant is not None:
        filtered = [e for e in filtered if e.variant == variant]

    if since is not None:
        filtered = [e for e in filtered if e.timestamp >= since]

    if until is not None:
        filtered = [e for e in filtered if e.timestamp <= until]

    return filtered


def _get_time_bucket(timestamp: datetime, granularity: str) -> datetime:
    """Get the start of the time bucket for a timestamp.

    Args:
        timestamp: The timestamp to bucket.
        granularity: The granularity (hour, day, week).

    Returns:
        The start of the time bucket.

    """
    if granularity == "hour":
        return timestamp.replace(minute=0, second=0, microsecond=0)
    elif granularity == "day":
        return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
    elif granularity == "week":
        # Start of week (Monday)
        days_since_monday = timestamp.weekday()
        week_start = timestamp - timedelta(days=days_since_monday)
        return week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        return timestamp.replace(minute=0, second=0, microsecond=0)


# =============================================================================
# Controller
# =============================================================================


class AnalyticsController(Controller):
    """Controller for analytics query endpoints.

    Provides read-only access to analytics data with:
    - Permission-based access control (analytics:read)
    - Metrics aggregation for individual flags and across all flags
    - Event querying with filtering and pagination
    - Dashboard summary for overview
    - Trend data over time
    - Data export in CSV and JSON formats

    Attributes:
        path: The base path for all analytics endpoints.
        tags: OpenAPI tags for documentation.
        dependencies: Dependency injection providers.

    Example:
        Using the controller endpoints::

            # Get metrics for a specific flag
            GET /admin/analytics/metrics/new_feature?window_seconds=3600

            # Get summary metrics for all flags
            GET /admin/analytics/metrics?window_seconds=3600

            # Query evaluation events
            GET /admin/analytics/events?flag_key=new_feature&page=1&page_size=50

            # Get dashboard summary
            GET /admin/analytics/dashboard?window_seconds=86400

            # Get trend data
            GET /admin/analytics/trends/new_feature?granularity=hour

            # Export events
            GET /admin/analytics/export?format=csv

    """

    path: ClassVar[str] = "/admin/analytics"
    tags: ClassVar[list[str]] = ["Admin - Analytics"]
    dependencies: ClassVar[dict[str, Provide]] = {
        "aggregator": Provide(provide_analytics_aggregator),
        "collector": Provide(provide_analytics_collector),
    }

    @get(
        "/metrics/{flag_key:str}",
        guards=[require_permission(Permission.ANALYTICS_READ)],
        summary="Get metrics for a flag",
        description="Retrieve aggregated metrics for a specific feature flag.",
        status_code=HTTP_200_OK,
    )
    async def get_flag_metrics(
        self,
        aggregator: AnalyticsAggregator,
        flag_key: str = Parameter(description="The flag key to get metrics for"),
        window_seconds: int = Parameter(
            default=3600,
            ge=60,
            le=604800,  # Max 1 week
            description="Time window in seconds for aggregation",
        ),
    ) -> MetricsResponse:
        """Get aggregated metrics for a specific flag.

        Args:
            aggregator: The analytics aggregator.
            flag_key: The key of the flag to get metrics for.
            window_seconds: The time window in seconds (default: 3600, 1 hour).

        Returns:
            MetricsResponse with aggregated metrics.

        """
        metrics = await aggregator.get_flag_metrics(flag_key, window_seconds=window_seconds)
        return _metrics_to_response(flag_key, metrics)

    @get(
        "/metrics",
        guards=[require_permission(Permission.ANALYTICS_READ)],
        summary="Get metrics summary for all flags",
        description="Retrieve aggregated metrics summary across all evaluated flags.",
        status_code=HTTP_200_OK,
    )
    async def get_all_metrics(
        self,
        collector: InMemoryAnalyticsCollector,
        window_seconds: int = Parameter(
            default=3600,
            ge=60,
            le=604800,
            description="Time window in seconds for aggregation",
        ),
    ) -> list[MetricsResponse]:
        """Get aggregated metrics for all flags with evaluations.

        Args:
            collector: The analytics collector.
            window_seconds: The time window in seconds (default: 3600, 1 hour).

        Returns:
            List of MetricsResponse for each flag with evaluations.

        """
        # Get all events within the window
        since = datetime.now(UTC) - timedelta(seconds=window_seconds)
        all_events = await collector.get_events()
        events_in_window = [e for e in all_events if e.timestamp >= since]

        # Group by flag_key
        flag_events: dict[str, list[FlagEvaluationEvent]] = {}
        for event in events_in_window:
            if event.flag_key not in flag_events:
                flag_events[event.flag_key] = []
            flag_events[event.flag_key].append(event)

        # Calculate metrics for each flag
        aggregator = AnalyticsAggregator(collector)
        results: list[MetricsResponse] = []

        for flag_key in flag_events:
            metrics = await aggregator.get_flag_metrics(flag_key, window_seconds=window_seconds)
            results.append(_metrics_to_response(flag_key, metrics))

        # Sort by total evaluations descending
        results.sort(key=lambda m: m.total_evaluations, reverse=True)

        return results

    @get(
        "/events",
        guards=[require_permission(Permission.ANALYTICS_READ)],
        summary="Query evaluation events",
        description="Query evaluation events with filtering and pagination.",
        status_code=HTTP_200_OK,
    )
    async def query_events(
        self,
        collector: InMemoryAnalyticsCollector,
        flag_key: str | None = Parameter(
            default=None,
            description="Filter by flag key",
        ),
        targeting_key: str | None = Parameter(
            default=None,
            description="Filter by targeting key (e.g., user ID)",
        ),
        reason: EvaluationReason | None = Parameter(
            default=None,
            description="Filter by evaluation reason",
        ),
        variant: str | None = Parameter(
            default=None,
            description="Filter by variant",
        ),
        since: datetime | None = Parameter(
            default=None,
            description="Only include events after this timestamp",
        ),
        until: datetime | None = Parameter(
            default=None,
            description="Only include events before this timestamp",
        ),
        page: int = Parameter(
            default=1,
            ge=1,
            description="Page number (1-indexed)",
        ),
        page_size: int = Parameter(
            default=50,
            ge=1,
            le=1000,
            description="Number of items per page",
        ),
    ) -> EventsResponse:
        """Query evaluation events with filtering and pagination.

        Args:
            collector: The analytics collector.
            flag_key: Optional filter by flag key.
            targeting_key: Optional filter by targeting key.
            reason: Optional filter by evaluation reason.
            variant: Optional filter by variant.
            since: Optional start timestamp filter.
            until: Optional end timestamp filter.
            page: Page number (1-indexed).
            page_size: Number of items per page.

        Returns:
            EventsResponse with paginated events.

        """
        # Get all events
        all_events = await collector.get_events()

        # Apply filters
        filtered_events = _filter_events(
            all_events,
            flag_key=flag_key,
            targeting_key=targeting_key,
            reason=reason,
            variant=variant,
            since=since,
            until=until,
        )

        # Sort by timestamp descending (newest first)
        filtered_events.sort(key=lambda e: e.timestamp, reverse=True)

        # Paginate
        total = len(filtered_events)
        total_pages = max(1, math.ceil(total / page_size))
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_events = filtered_events[start_idx:end_idx]

        # Convert to response DTOs
        event_responses = [_event_to_response(e) for e in page_events]

        return EventsResponse(
            events=event_responses,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )

    @get(
        "/events/{flag_key:str}",
        guards=[require_permission(Permission.ANALYTICS_READ)],
        summary="Get events for a flag",
        description="Get evaluation events for a specific flag with pagination.",
        status_code=HTTP_200_OK,
    )
    async def get_flag_events(
        self,
        collector: InMemoryAnalyticsCollector,
        flag_key: str = Parameter(description="The flag key to get events for"),
        targeting_key: str | None = Parameter(
            default=None,
            description="Filter by targeting key (e.g., user ID)",
        ),
        reason: EvaluationReason | None = Parameter(
            default=None,
            description="Filter by evaluation reason",
        ),
        variant: str | None = Parameter(
            default=None,
            description="Filter by variant",
        ),
        since: datetime | None = Parameter(
            default=None,
            description="Only include events after this timestamp",
        ),
        until: datetime | None = Parameter(
            default=None,
            description="Only include events before this timestamp",
        ),
        page: int = Parameter(
            default=1,
            ge=1,
            description="Page number (1-indexed)",
        ),
        page_size: int = Parameter(
            default=50,
            ge=1,
            le=1000,
            description="Number of items per page",
        ),
    ) -> EventsResponse:
        """Get evaluation events for a specific flag.

        Args:
            collector: The analytics collector.
            flag_key: The key of the flag to get events for.
            targeting_key: Optional filter by targeting key.
            reason: Optional filter by evaluation reason.
            variant: Optional filter by variant.
            since: Optional start timestamp filter.
            until: Optional end timestamp filter.
            page: Page number (1-indexed).
            page_size: Number of items per page.

        Returns:
            EventsResponse with paginated events for the flag.

        """
        # Get events for this flag
        all_events = await collector.get_events(flag_key=flag_key)

        # Apply additional filters
        filtered_events = _filter_events(
            all_events,
            targeting_key=targeting_key,
            reason=reason,
            variant=variant,
            since=since,
            until=until,
        )

        # Sort by timestamp descending (newest first)
        filtered_events.sort(key=lambda e: e.timestamp, reverse=True)

        # Paginate
        total = len(filtered_events)
        total_pages = max(1, math.ceil(total / page_size))
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_events = filtered_events[start_idx:end_idx]

        # Convert to response DTOs
        event_responses = [_event_to_response(e) for e in page_events]

        return EventsResponse(
            events=event_responses,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )

    @get(
        "/dashboard",
        guards=[require_permission(Permission.ANALYTICS_READ)],
        summary="Get dashboard summary",
        description="Get a high-level dashboard summary of all flag analytics.",
        status_code=HTTP_200_OK,
    )
    async def get_dashboard(
        self,
        collector: InMemoryAnalyticsCollector,
        window_seconds: int = Parameter(
            default=86400,  # 24 hours default
            ge=60,
            le=604800,
            description="Time window in seconds for aggregation",
        ),
        limit: int = Parameter(
            default=10,
            ge=1,
            le=100,
            description="Maximum number of flag summaries to return",
        ),
    ) -> DashboardResponse:
        """Get a dashboard summary of all flag analytics.

        Args:
            collector: The analytics collector.
            window_seconds: The time window in seconds (default: 86400, 24 hours).
            limit: Maximum number of flag summaries to return.

        Returns:
            DashboardResponse with overall and per-flag summaries.

        """
        now = datetime.now(UTC)
        since = now - timedelta(seconds=window_seconds)

        # Get all events within the window
        all_events = await collector.get_events()
        events_in_window = [e for e in all_events if e.timestamp >= since]

        # Group by flag_key
        flag_events: dict[str, list[FlagEvaluationEvent]] = {}
        for event in events_in_window:
            if event.flag_key not in flag_events:
                flag_events[event.flag_key] = []
            flag_events[event.flag_key].append(event)

        # Calculate per-flag summaries
        flag_summaries: list[DashboardFlagSummary] = []
        total_evaluations = 0
        total_errors = 0

        for flag_key, events in flag_events.items():
            count = len(events)
            total_evaluations += count

            # Count errors
            error_count = sum(1 for e in events if e.reason == EvaluationReason.ERROR)
            total_errors += error_count
            error_rate = (error_count / count * 100) if count > 0 else 0.0

            # Get unique users
            unique_users = len({e.targeting_key for e in events if e.targeting_key})

            # Get top variant
            variant_counts: dict[str, int] = {}
            for event in events:
                v = event.variant or "default"
                variant_counts[v] = variant_counts.get(v, 0) + 1
            top_variant = max(variant_counts, key=variant_counts.get) if variant_counts else None  # type: ignore[arg-type]

            flag_summaries.append(
                DashboardFlagSummary(
                    flag_key=flag_key,
                    total_evaluations=count,
                    evaluation_rate=count / window_seconds if window_seconds > 0 else 0.0,
                    unique_users=unique_users,
                    error_rate=error_rate,
                    top_variant=top_variant,
                )
            )

        # Sort by total evaluations and limit
        flag_summaries.sort(key=lambda s: s.total_evaluations, reverse=True)
        flag_summaries = flag_summaries[:limit]

        # Calculate overall metrics
        overall_error_rate = (total_errors / total_evaluations * 100) if total_evaluations > 0 else 0.0
        overall_evaluation_rate = total_evaluations / window_seconds if window_seconds > 0 else 0.0

        return DashboardResponse(
            total_flags_evaluated=len(flag_events),
            total_evaluations=total_evaluations,
            overall_error_rate=overall_error_rate,
            overall_evaluation_rate=overall_evaluation_rate,
            flag_summaries=flag_summaries,
            window_start=since,
            window_end=now,
        )

    @get(
        "/trends/{flag_key:str}",
        guards=[require_permission(Permission.ANALYTICS_READ)],
        summary="Get trend data for a flag",
        description="Get time-series trend data for a specific flag.",
        status_code=HTTP_200_OK,
    )
    async def get_flag_trends(
        self,
        collector: InMemoryAnalyticsCollector,
        flag_key: str = Parameter(description="The flag key to get trends for"),
        granularity: str = Parameter(
            default="hour",
            description="Time granularity for grouping (hour, day, week)",
        ),
        window_seconds: int = Parameter(
            default=86400,  # 24 hours default
            ge=60,
            le=2592000,  # Max 30 days
            description="Time window in seconds",
        ),
    ) -> TrendsResponse:
        """Get time-series trend data for a flag.

        Args:
            collector: The analytics collector.
            flag_key: The key of the flag to get trends for.
            granularity: Time granularity (hour, day, week).
            window_seconds: The time window in seconds.

        Returns:
            TrendsResponse with trend data points.

        """
        now = datetime.now(UTC)
        since = now - timedelta(seconds=window_seconds)

        # Validate granularity
        if granularity not in ("hour", "day", "week"):
            granularity = "hour"

        # Get events for this flag
        all_events = await collector.get_events(flag_key=flag_key)
        events_in_window = [e for e in all_events if e.timestamp >= since]

        # Group events into time buckets
        buckets: dict[datetime, list[FlagEvaluationEvent]] = {}
        for event in events_in_window:
            bucket = _get_time_bucket(event.timestamp, granularity)
            if bucket not in buckets:
                buckets[bucket] = []
            buckets[bucket].append(event)

        # Create data points
        data_points: list[TrendDataPoint] = []
        for bucket_time, bucket_events in sorted(buckets.items()):
            unique_users = len({e.targeting_key for e in bucket_events if e.targeting_key})
            error_count = sum(1 for e in bucket_events if e.reason == EvaluationReason.ERROR)

            data_points.append(
                TrendDataPoint(
                    timestamp=bucket_time,
                    count=len(bucket_events),
                    unique_users=unique_users,
                    error_count=error_count,
                )
            )

        return TrendsResponse(
            flag_key=flag_key,
            granularity=granularity,
            data_points=data_points,
            window_start=since,
            window_end=now,
        )

    @get(
        "/export",
        guards=[require_permission(Permission.ANALYTICS_READ)],
        summary="Export evaluation events",
        description="Export evaluation events as CSV or JSON.",
        status_code=HTTP_200_OK,
    )
    async def export_events(
        self,
        collector: InMemoryAnalyticsCollector,
        format: str = Parameter(  # noqa: A002
            default="json",
            description="Export format (csv or json)",
        ),
        flag_key: str | None = Parameter(
            default=None,
            description="Filter by flag key",
        ),
        targeting_key: str | None = Parameter(
            default=None,
            description="Filter by targeting key",
        ),
        since: datetime | None = Parameter(
            default=None,
            description="Only include events after this timestamp",
        ),
        until: datetime | None = Parameter(
            default=None,
            description="Only include events before this timestamp",
        ),
        limit: int = Parameter(
            default=10000,
            ge=1,
            le=100000,
            description="Maximum number of events to export",
        ),
    ) -> Response[Any]:
        """Export evaluation events as CSV or JSON.

        Args:
            collector: The analytics collector.
            format: Export format (csv or json).
            flag_key: Optional filter by flag key.
            targeting_key: Optional filter by targeting key.
            since: Optional start timestamp filter.
            until: Optional end timestamp filter.
            limit: Maximum number of events to export.

        Returns:
            Response with exported data in the requested format.

        """
        # Get events
        if flag_key:
            all_events = await collector.get_events(flag_key=flag_key)
        else:
            all_events = await collector.get_events()

        # Apply filters
        filtered_events = _filter_events(
            all_events,
            targeting_key=targeting_key,
            since=since,
            until=until,
        )

        # Sort by timestamp descending and limit
        filtered_events.sort(key=lambda e: e.timestamp, reverse=True)
        filtered_events = filtered_events[:limit]

        if format.lower() == "csv":
            # Export as CSV
            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow(
                [
                    "timestamp",
                    "flag_key",
                    "value",
                    "reason",
                    "variant",
                    "targeting_key",
                    "evaluation_duration_ms",
                ]
            )

            # Write data rows
            for event in filtered_events:
                writer.writerow(
                    [
                        event.timestamp.isoformat(),
                        event.flag_key,
                        str(event.value),
                        event.reason.value if isinstance(event.reason, EvaluationReason) else str(event.reason),
                        event.variant or "",
                        event.targeting_key or "",
                        f"{event.evaluation_duration_ms:.3f}",
                    ]
                )

            csv_content = output.getvalue()
            return Response(
                content=csv_content,
                media_type="text/csv",
                headers={
                    "Content-Disposition": "attachment; filename=analytics_export.csv",
                },
            )
        else:
            # Export as JSON
            export_data = [event.to_dict() for event in filtered_events]
            return Response(
                content=export_data,
                media_type="application/json",
                headers={
                    "Content-Disposition": "attachment; filename=analytics_export.json",
                },
            )
