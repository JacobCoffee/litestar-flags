"""OpenTelemetry integration for feature flag tracing and metrics.

This module provides OpenTelemetry instrumentation for feature flag evaluations,
enabling distributed tracing and metrics collection.

Example:
    Basic usage with OpenTelemetry::

        from litestar_flags.contrib.otel import OTelHook

        # Create the hook
        hook = OTelHook()

        # Use with flag evaluation (integration with client TBD)
        await hook.before_evaluation("my-feature", context)
        result = await client.get_boolean_value("my-feature")
        await hook.after_evaluation("my-feature", result, context)

    Custom tracer and meter::

        from opentelemetry import trace, metrics

        tracer = trace.get_tracer("my-app")
        meter = metrics.get_meter("my-app")

        hook = OTelHook(tracer=tracer, meter=meter)

Requires:
    opentelemetry-api>=1.20.0

"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

# Handle optional opentelemetry import
try:
    from opentelemetry import metrics, trace
    from opentelemetry.metrics import Counter, Histogram, Meter
    from opentelemetry.trace import Span, SpanKind, StatusCode, Tracer

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    # Define stub types for type checking when otel is not installed
    Tracer = Any  # type: ignore[misc, assignment]
    Meter = Any  # type: ignore[misc, assignment]
    Span = Any  # type: ignore[misc, assignment]
    Counter = Any  # type: ignore[misc, assignment]
    Histogram = Any  # type: ignore[misc, assignment]
    SpanKind = Any  # type: ignore[misc, assignment]
    StatusCode = Any  # type: ignore[misc, assignment]

if TYPE_CHECKING:
    from litestar_flags.context import EvaluationContext
    from litestar_flags.results import EvaluationDetails

__all__ = ["OTEL_AVAILABLE", "OTelHook"]

# Semantic conventions for feature flag spans
SPAN_NAME = "feature_flag.evaluation"
ATTR_FLAG_KEY = "feature_flag.key"
ATTR_FLAG_TYPE = "feature_flag.type"
ATTR_FLAG_VARIANT = "feature_flag.variant"
ATTR_FLAG_REASON = "feature_flag.reason"
ATTR_FLAG_VALUE = "feature_flag.value"
ATTR_ERROR_CODE = "feature_flag.error_code"
ATTR_ERROR_MESSAGE = "feature_flag.error_message"
ATTR_TARGETING_KEY = "feature_flag.targeting_key"

# Metric names
METRIC_EVALUATION_COUNT = "feature_flag.evaluation.count"
METRIC_EVALUATION_LATENCY = "feature_flag.evaluation.latency"


class OTelHook:
    """OpenTelemetry hook for feature flag evaluation instrumentation.

    Provides tracing spans and metrics for flag evaluations. This hook
    follows OpenTelemetry semantic conventions for feature flags.

    Attributes:
        tracer: The OpenTelemetry tracer for creating spans.
        meter: The OpenTelemetry meter for recording metrics.
        evaluation_counter: Counter for tracking evaluation counts.
        latency_histogram: Histogram for tracking evaluation latency.

    Example:
        >>> hook = OTelHook()
        >>> span = hook.start_evaluation_span("my-feature", context)
        >>> # ... perform evaluation ...
        >>> hook.end_evaluation_span(span, result)

    """

    def __init__(
        self,
        tracer: Tracer | None = None,
        meter: Meter | None = None,
        tracer_name: str = "litestar_flags",
        meter_name: str = "litestar_flags",
        record_values: bool = False,
    ) -> None:
        """Initialize the OpenTelemetry hook.

        Args:
            tracer: Custom tracer instance. If not provided, creates one using tracer_name.
            meter: Custom meter instance. If not provided, creates one using meter_name.
            tracer_name: Name for the default tracer.
            meter_name: Name for the default meter.
            record_values: Whether to record flag values in spans. Disabled by default
                for privacy/security reasons.

        Raises:
            ImportError: If opentelemetry-api is not installed.

        """
        if not OTEL_AVAILABLE:
            raise ImportError(
                "opentelemetry-api is required for OTelHook. Install it with: pip install litestar-flags[otel]"
            )

        self._tracer = tracer or trace.get_tracer(tracer_name)
        self._meter = meter or metrics.get_meter(meter_name)
        self._record_values = record_values

        # Create metrics instruments
        self._evaluation_counter: Counter = self._meter.create_counter(
            name=METRIC_EVALUATION_COUNT,
            unit="1",
            description="Number of feature flag evaluations",
        )
        self._latency_histogram: Histogram = self._meter.create_histogram(
            name=METRIC_EVALUATION_LATENCY,
            unit="ms",
            description="Feature flag evaluation latency in milliseconds",
        )

        # Track active spans for timing
        self._span_start_times: dict[int, float] = {}

    @property
    def tracer(self) -> Tracer:
        """Get the tracer instance."""
        return self._tracer

    @property
    def meter(self) -> Meter:
        """Get the meter instance."""
        return self._meter

    @property
    def evaluation_counter(self) -> Counter:
        """Get the evaluation counter metric."""
        return self._evaluation_counter

    @property
    def latency_histogram(self) -> Histogram:
        """Get the latency histogram metric."""
        return self._latency_histogram

    def start_evaluation_span(
        self,
        flag_key: str,
        context: EvaluationContext | None = None,
        flag_type: str | None = None,
    ) -> Span:
        """Start a span for flag evaluation.

        Args:
            flag_key: The flag key being evaluated.
            context: The evaluation context.
            flag_type: The type of flag being evaluated.

        Returns:
            The started span. Must be ended with end_evaluation_span().

        """
        attributes: dict[str, Any] = {
            ATTR_FLAG_KEY: flag_key,
        }

        if flag_type:
            attributes[ATTR_FLAG_TYPE] = flag_type

        if context:
            if context.targeting_key:
                attributes[ATTR_TARGETING_KEY] = context.targeting_key

        span = self._tracer.start_span(
            name=SPAN_NAME,
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        )

        # Track start time for latency measurement
        self._span_start_times[id(span)] = time.perf_counter()

        return span

    def end_evaluation_span(
        self,
        span: Span,
        result: EvaluationDetails[Any],
    ) -> None:
        """End an evaluation span and record metrics.

        Args:
            span: The span to end.
            result: The evaluation result details.

        """
        # Calculate latency
        start_time = self._span_start_times.pop(id(span), None)
        latency_ms = 0.0
        if start_time is not None:
            latency_ms = (time.perf_counter() - start_time) * 1000

        # Add result attributes to span
        span.set_attribute(ATTR_FLAG_REASON, result.reason.value)

        if result.variant:
            span.set_attribute(ATTR_FLAG_VARIANT, result.variant)

        if self._record_values:
            # Convert value to string for span attribute
            value_str = str(result.value)
            if len(value_str) <= 256:  # Limit attribute size
                span.set_attribute(ATTR_FLAG_VALUE, value_str)

        if result.error_code:
            span.set_attribute(ATTR_ERROR_CODE, result.error_code.value)
            span.set_status(StatusCode.ERROR, result.error_message or "Evaluation error")
        else:
            span.set_status(StatusCode.OK)

        if result.error_message:
            span.set_attribute(ATTR_ERROR_MESSAGE, result.error_message)

        # End the span
        span.end()

        # Record metrics
        metric_attributes = {
            ATTR_FLAG_KEY: result.flag_key,
            ATTR_FLAG_REASON: result.reason.value,
        }

        if result.variant:
            metric_attributes[ATTR_FLAG_VARIANT] = result.variant

        if result.error_code:
            metric_attributes[ATTR_ERROR_CODE] = result.error_code.value

        self._evaluation_counter.add(1, metric_attributes)
        self._latency_histogram.record(latency_ms, metric_attributes)

    async def before_evaluation(
        self,
        flag_key: str,
        context: EvaluationContext | None = None,
        flag_type: str | None = None,
    ) -> Span:
        """Start a span before flag evaluation begins.

        This is an async wrapper around start_evaluation_span for use
        in async evaluation pipelines.

        Args:
            flag_key: The flag key being evaluated.
            context: The evaluation context.
            flag_type: The type of flag being evaluated.

        Returns:
            The started span.

        """
        return self.start_evaluation_span(flag_key, context, flag_type)

    async def after_evaluation(
        self,
        span: Span,
        result: EvaluationDetails[Any],
    ) -> None:
        """End a span after flag evaluation completes.

        This is an async wrapper around end_evaluation_span for use
        in async evaluation pipelines.

        Args:
            span: The span from before_evaluation.
            result: The evaluation result.

        """
        self.end_evaluation_span(span, result)

    async def on_error(
        self,
        span: Span,
        error: Exception,
        flag_key: str,
    ) -> None:
        """Record an error in the span and end it.

        Records the error in the span and ends it.

        Args:
            span: The active span.
            error: The exception that occurred.
            flag_key: The flag key that was being evaluated.

        """
        # Calculate latency
        start_time = self._span_start_times.pop(id(span), None)
        latency_ms = 0.0
        if start_time is not None:
            latency_ms = (time.perf_counter() - start_time) * 1000

        # Record error in span
        span.set_status(StatusCode.ERROR, str(error))
        span.record_exception(error)

        # End the span
        span.end()

        # Record metrics
        metric_attributes = {
            ATTR_FLAG_KEY: flag_key,
            ATTR_FLAG_REASON: "ERROR",
            ATTR_ERROR_CODE: "GENERAL_ERROR",
        }

        self._evaluation_counter.add(1, metric_attributes)
        self._latency_histogram.record(latency_ms, metric_attributes)

    def record_evaluation(
        self,
        flag_key: str,
        result: EvaluationDetails[Any],
        context: EvaluationContext | None = None,
        flag_type: str | None = None,
    ) -> None:
        """Record a complete evaluation as a single operation.

        Convenience method that creates a span, records the result,
        and ends the span in a single call. Useful when timing is
        handled externally.

        Args:
            flag_key: The flag key that was evaluated.
            result: The evaluation result.
            context: The evaluation context.
            flag_type: The type of flag.

        """
        span = self.start_evaluation_span(flag_key, context, flag_type)
        self.end_evaluation_span(span, result)
