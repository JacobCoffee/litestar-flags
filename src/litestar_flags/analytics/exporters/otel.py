"""OpenTelemetry analytics exporter for feature flag metrics.

This module provides OpenTelemetry integration for exporting feature flag
analytics as spans and metrics, enabling distributed tracing and observability.

Example:
    Basic usage with OpenTelemetry::

        from litestar_flags.analytics.exporters.otel import OTelAnalyticsExporter

        # Create the exporter
        exporter = OTelAnalyticsExporter()

        # Record evaluation events
        await exporter.record(event)

        # Flush batched events
        await exporter.flush()

    Custom tracer and meter::

        from opentelemetry import trace, metrics

        tracer = trace.get_tracer("my-app")
        meter = metrics.get_meter("my-app")

        exporter = OTelAnalyticsExporter(tracer=tracer, meter=meter)

    Using with the existing OTelHook::

        from litestar_flags.contrib.otel import OTelHook
        from litestar_flags.analytics.exporters.otel import OTelAnalyticsExporter

        hook = OTelHook()
        exporter = OTelAnalyticsExporter(otel_hook=hook)

Requires:
    opentelemetry-api>=1.20.0

"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.metrics import Counter, Histogram, Meter
    from opentelemetry.trace import Tracer

    from litestar_flags.analytics.models import FlagEvaluationEvent
    from litestar_flags.contrib.otel import OTelHook

# Handle optional opentelemetry import
try:
    from opentelemetry import metrics as otel_metrics
    from opentelemetry import trace as otel_trace
    from opentelemetry.trace import SpanKind, StatusCode

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    otel_trace = None  # type: ignore[assignment]
    otel_metrics = None  # type: ignore[assignment]
    SpanKind = None  # type: ignore[assignment]
    StatusCode = None  # type: ignore[assignment]


__all__ = ["OTEL_AVAILABLE", "OTelAnalyticsExporter"]

# Span names for analytics events
SPAN_NAME_ANALYTICS_EVENT = "feature_flag.analytics.event"
SPAN_NAME_ANALYTICS_BATCH = "feature_flag.analytics.batch"

# Semantic conventions for analytics spans
ATTR_FLAG_KEY = "feature_flag.key"
ATTR_FLAG_VALUE = "feature_flag.value"
ATTR_FLAG_VARIANT = "feature_flag.variant"
ATTR_FLAG_REASON = "feature_flag.reason"
ATTR_TARGETING_KEY = "feature_flag.targeting_key"
ATTR_EVALUATION_DURATION_MS = "feature_flag.evaluation_duration_ms"
ATTR_EVENT_TIMESTAMP = "feature_flag.event_timestamp"
ATTR_BATCH_SIZE = "feature_flag.analytics.batch_size"

# Metric names for analytics
METRIC_EVENTS_RECORDED = "feature_flag.analytics.events_recorded"
METRIC_BATCH_SIZE = "feature_flag.analytics.batch_size"

# Default batch configuration
DEFAULT_BATCH_SIZE = 100
DEFAULT_FLUSH_INTERVAL_SECONDS = 30.0


class OTelAnalyticsExporter:
    """OpenTelemetry exporter for feature flag analytics.

    Exports feature flag evaluation events as OpenTelemetry spans and metrics.
    Implements the AnalyticsCollector protocol for seamless integration with
    the analytics pipeline.

    This exporter can optionally wrap an existing OTelHook instance to share
    tracer and meter configurations, or create its own OpenTelemetry instruments.

    Metrics exported:
        - feature_flag.analytics.events_recorded: Counter of recorded analytics events
            Labels: flag_key, reason
        - feature_flag.analytics.batch_size: Histogram of batch sizes when flushing
            Labels: (none)

    Attributes:
        tracer: The OpenTelemetry tracer for creating spans.
        meter: The OpenTelemetry meter for recording metrics.
        batch_size: Maximum number of events to buffer before auto-flush.
        flush_interval: Time in seconds between automatic flushes.

    Example:
        >>> exporter = OTelAnalyticsExporter(batch_size=50)
        >>> await exporter.record(evaluation_event)
        >>> # Events are batched and flushed automatically
        >>> await exporter.close()

    """

    def __init__(
        self,
        tracer: Tracer | None = None,
        meter: Meter | None = None,
        otel_hook: OTelHook | None = None,
        tracer_name: str = "litestar_flags.analytics",
        meter_name: str = "litestar_flags.analytics",
        batch_size: int = DEFAULT_BATCH_SIZE,
        flush_interval: float = DEFAULT_FLUSH_INTERVAL_SECONDS,
        record_values: bool = False,
        create_spans: bool = True,
    ) -> None:
        """Initialize the OpenTelemetry analytics exporter.

        Args:
            tracer: Custom tracer instance. If not provided, uses otel_hook's tracer
                or creates one using tracer_name.
            meter: Custom meter instance. If not provided, uses otel_hook's meter
                or creates one using meter_name.
            otel_hook: Existing OTelHook instance to share tracer/meter from.
                If provided, tracer and meter arguments are ignored.
            tracer_name: Name for the default tracer if none provided.
            meter_name: Name for the default meter if none provided.
            batch_size: Maximum number of events to buffer before auto-flush.
                Set to 0 to disable batching.
            flush_interval: Time in seconds between automatic flushes.
                Set to 0 to disable automatic flushing.
            record_values: Whether to record flag values in spans. Disabled by default
                for privacy/security reasons.
            create_spans: Whether to create spans for each event. Set to False to
                only record metrics without span overhead.

        Raises:
            ImportError: If opentelemetry-api is not installed.

        """
        if not OTEL_AVAILABLE or otel_trace is None or otel_metrics is None:
            raise ImportError(
                "opentelemetry-api is required for OTelAnalyticsExporter. "
                "Install it with: pip install litestar-flags[otel]"
            )

        # Use otel_hook's instruments if provided, otherwise create our own
        if otel_hook is not None:
            self._tracer: Tracer = otel_hook.tracer
            self._meter: Meter = otel_hook.meter
        else:
            self._tracer = tracer or otel_trace.get_tracer(tracer_name)
            self._meter = meter or otel_metrics.get_meter(meter_name)

        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._record_values = record_values
        self._create_spans = create_spans

        # Event buffer for batching
        self._buffer: deque[FlagEvaluationEvent] = deque()
        self._buffer_lock = asyncio.Lock()

        # Background flush task
        self._flush_task: asyncio.Task[None] | None = None
        self._closed = False

        # Create analytics-specific metrics instruments
        self._events_recorded_counter: Counter = self._meter.create_counter(  # type: ignore[assignment]
            name=METRIC_EVENTS_RECORDED,
            unit="1",
            description="Number of feature flag analytics events recorded",
        )
        self._batch_size_histogram: Histogram = self._meter.create_histogram(  # type: ignore[assignment]
            name=METRIC_BATCH_SIZE,
            unit="1",
            description="Size of analytics event batches when flushed",
        )

    @property
    def tracer(self) -> Tracer:
        """Get the tracer instance.

        Returns:
            The OpenTelemetry tracer used by this exporter.

        """
        return self._tracer

    @property
    def meter(self) -> Meter:
        """Get the meter instance.

        Returns:
            The OpenTelemetry meter used by this exporter.

        """
        return self._meter

    @property
    def events_recorded_counter(self) -> Counter:
        """Get the events recorded counter metric.

        Returns:
            The Counter metric for recorded analytics events.

        """
        return self._events_recorded_counter

    @property
    def batch_size_histogram(self) -> Histogram:
        """Get the batch size histogram metric.

        Returns:
            The Histogram metric for batch sizes.

        """
        return self._batch_size_histogram

    @property
    def buffer_size(self) -> int:
        """Get the current number of buffered events.

        Returns:
            Number of events currently in the buffer.

        """
        return len(self._buffer)

    async def record(self, event: FlagEvaluationEvent) -> None:
        """Record a flag evaluation event.

        Buffers the event and flushes when batch_size is reached.
        This method implements the AnalyticsCollector protocol.

        Args:
            event: The evaluation event to record.

        """
        if self._closed:
            return

        async with self._buffer_lock:
            self._buffer.append(event)

            # Start background flush task if not running and interval is set
            if self._flush_task is None and self._flush_interval > 0:
                self._flush_task = asyncio.create_task(self._background_flush())

            # Auto-flush if batch size reached
            if self._batch_size > 0 and len(self._buffer) >= self._batch_size:
                await self._flush_buffer()

    async def flush(self) -> None:
        """Flush any buffered events.

        Forces immediate processing of all buffered events, creating spans
        and recording metrics for each event.

        """
        async with self._buffer_lock:
            await self._flush_buffer()

    async def close(self) -> None:
        """Close the exporter and release resources.

        Flushes remaining events and cancels the background flush task.

        """
        self._closed = True

        # Cancel background flush task
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        # Flush remaining events
        await self.flush()

    async def _background_flush(self) -> None:
        """Background task for periodic flushing."""
        while not self._closed:
            try:
                await asyncio.sleep(self._flush_interval)
                if not self._closed:
                    await self.flush()
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: S110
                # Log error but continue running
                pass

    async def _flush_buffer(self) -> None:
        """Flush the current buffer.

        Must be called with _buffer_lock held.
        """
        if not self._buffer:
            return

        # Get all events from buffer
        events = list(self._buffer)
        self._buffer.clear()

        # Record batch size metric
        batch_size = len(events)
        self._batch_size_histogram.record(batch_size)

        # Create a parent span for the batch if creating spans
        if self._create_spans and batch_size > 1:
            with self._tracer.start_as_current_span(
                name=SPAN_NAME_ANALYTICS_BATCH,
                kind=SpanKind.INTERNAL,
                attributes={ATTR_BATCH_SIZE: batch_size},
            ) as batch_span:
                for event in events:
                    self._process_event(event)
                batch_span.set_status(StatusCode.OK)
        else:
            # Process events without batch span
            for event in events:
                self._process_event(event)

    def _process_event(self, event: FlagEvaluationEvent) -> None:
        """Process a single analytics event.

        Creates a span (if enabled) and records metrics for the event.

        Args:
            event: The evaluation event to process.

        """
        flag_key = event.flag_key
        reason = event.reason.value if hasattr(event.reason, "value") else str(event.reason)

        # Record event counter metric
        metric_attributes = {
            ATTR_FLAG_KEY: flag_key,
            ATTR_FLAG_REASON: reason,
        }
        self._events_recorded_counter.add(1, metric_attributes)

        # Create span if enabled
        if self._create_spans:
            self._create_event_span(event)

    def _create_event_span(self, event: FlagEvaluationEvent) -> None:
        """Create a span for an analytics event.

        Args:
            event: The evaluation event to create a span for.

        """
        flag_key = event.flag_key
        reason = event.reason.value if hasattr(event.reason, "value") else str(event.reason)

        # Build span attributes
        attributes: dict[str, Any] = {
            ATTR_FLAG_KEY: flag_key,
            ATTR_FLAG_REASON: reason,
            ATTR_EVENT_TIMESTAMP: event.timestamp.isoformat(),
        }

        if event.variant:
            attributes[ATTR_FLAG_VARIANT] = event.variant

        if event.targeting_key:
            attributes[ATTR_TARGETING_KEY] = event.targeting_key

        if event.evaluation_duration_ms > 0:
            attributes[ATTR_EVALUATION_DURATION_MS] = event.evaluation_duration_ms

        if self._record_values:
            # Convert value to string for span attribute
            value_str = str(event.value)
            if len(value_str) <= 256:  # Limit attribute size
                attributes[ATTR_FLAG_VALUE] = value_str

        # Create and immediately end the span (event is already complete)
        with self._tracer.start_as_current_span(
            name=SPAN_NAME_ANALYTICS_EVENT,
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        ) as span:
            span.set_status(StatusCode.OK)

    def record_sync(self, event: FlagEvaluationEvent) -> None:
        """Record an event synchronously without batching.

        This method processes the event immediately without buffering.
        Useful for low-volume scenarios or when immediate recording is required.

        Args:
            event: The evaluation event to record.

        """
        if self._closed:
            return
        self._process_event(event)

    async def record_batch(self, events: list[FlagEvaluationEvent]) -> None:
        """Record multiple events in a batch.

        Adds all events to the buffer and triggers a flush.

        Args:
            events: List of evaluation events to record.

        """
        if self._closed or not events:
            return

        async with self._buffer_lock:
            self._buffer.extend(events)
            await self._flush_buffer()


def create_exporter_from_hook(
    otel_hook: OTelHook,
    batch_size: int = DEFAULT_BATCH_SIZE,
    flush_interval: float = DEFAULT_FLUSH_INTERVAL_SECONDS,
    record_values: bool = False,
    create_spans: bool = True,
) -> OTelAnalyticsExporter:
    """Create an OTelAnalyticsExporter from an existing OTelHook.

    This factory function creates an analytics exporter that shares the
    tracer and meter from an existing OTelHook instance, ensuring consistent
    instrumentation across flag evaluation and analytics.

    Args:
        otel_hook: The OTelHook instance to share tracer/meter from.
        batch_size: Maximum number of events to buffer before auto-flush.
        flush_interval: Time in seconds between automatic flushes.
        record_values: Whether to record flag values in spans.
        create_spans: Whether to create spans for each event.

    Returns:
        A configured OTelAnalyticsExporter instance.

    Raises:
        ImportError: If opentelemetry-api is not installed.

    Example:
        >>> from litestar_flags.contrib.otel import OTelHook
        >>> hook = OTelHook()
        >>> exporter = create_exporter_from_hook(hook)
        >>> await exporter.record(event)

    """
    if not OTEL_AVAILABLE:
        raise ImportError(
            "opentelemetry-api is required for create_exporter_from_hook. "
            "Install it with: pip install litestar-flags[otel]"
        )

    return OTelAnalyticsExporter(
        otel_hook=otel_hook,
        batch_size=batch_size,
        flush_interval=flush_interval,
        record_values=record_values,
        create_spans=create_spans,
    )
