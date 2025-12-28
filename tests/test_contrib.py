"""Comprehensive tests for litestar-flags contrib modules.

This module tests:
- OTelHook: OpenTelemetry tracing and metrics integration
- LoggingHook: Structured logging integration
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from litestar_flags.context import EvaluationContext
from litestar_flags.results import EvaluationDetails
from litestar_flags.types import ErrorCode, EvaluationReason

if TYPE_CHECKING:
    pass


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def successful_result() -> EvaluationDetails[bool]:
    """Create a successful evaluation result."""
    return EvaluationDetails(
        value=True,
        flag_key="test-flag",
        reason=EvaluationReason.TARGETING_MATCH,
        variant="enabled",
        flag_metadata={"version": "1.0"},
    )


@pytest.fixture
def error_result() -> EvaluationDetails[bool]:
    """Create an error evaluation result."""
    return EvaluationDetails(
        value=False,
        flag_key="test-flag",
        reason=EvaluationReason.ERROR,
        error_code=ErrorCode.FLAG_NOT_FOUND,
        error_message="Flag 'test-flag' not found",
    )


@pytest.fixture
def default_result() -> EvaluationDetails[bool]:
    """Create a default value result."""
    return EvaluationDetails(
        value=False,
        flag_key="test-flag",
        reason=EvaluationReason.DEFAULT,
    )


@pytest.fixture
def full_context() -> EvaluationContext:
    """Create a fully populated evaluation context."""
    return EvaluationContext(
        targeting_key="user-123",
        user_id="user-123",
        organization_id="org-456",
        tenant_id="tenant-789",
        environment="production",
        app_version="2.0.0",
        attributes={"plan": "premium", "beta": True},
        ip_address="192.168.1.1",
        user_agent="TestAgent/1.0",
        country="US",
    )


@pytest.fixture
def minimal_context() -> EvaluationContext:
    """Create a minimal evaluation context."""
    return EvaluationContext(targeting_key="user-abc")


# =============================================================================
# OTelHook Tests
# =============================================================================


class TestOTelHookImport:
    """Test OTelHook import behavior."""

    def test_otel_available_constant_exported(self):
        """Test that OTEL_AVAILABLE is exported."""
        from litestar_flags.contrib.otel import OTEL_AVAILABLE

        # OTEL_AVAILABLE should be a boolean
        assert isinstance(OTEL_AVAILABLE, bool)

    def test_otel_hook_import(self):
        """Test that OTelHook can be imported."""
        from litestar_flags.contrib.otel import OTelHook

        assert OTelHook is not None


class TestOTelHookWithMocks:
    """Test OTelHook with mocked OpenTelemetry."""

    @pytest.fixture
    def mock_tracer(self):
        """Create a mock tracer."""
        tracer = MagicMock()
        mock_span = MagicMock()
        tracer.start_span.return_value = mock_span
        return tracer

    @pytest.fixture
    def mock_meter(self):
        """Create a mock meter."""
        meter = MagicMock()
        meter.create_counter.return_value = MagicMock()
        meter.create_histogram.return_value = MagicMock()
        return meter

    @pytest.fixture
    def otel_hook(self, mock_tracer, mock_meter):
        """Create OTelHook with mocked dependencies."""
        # Patch OTEL_AVAILABLE to True
        with patch("litestar_flags.contrib.otel.OTEL_AVAILABLE", True):
            with patch("litestar_flags.contrib.otel.trace") as mock_trace:
                with patch("litestar_flags.contrib.otel.metrics") as mock_metrics:
                    with patch("litestar_flags.contrib.otel.SpanKind"):
                        with patch("litestar_flags.contrib.otel.StatusCode"):
                            mock_trace.get_tracer.return_value = mock_tracer
                            mock_metrics.get_meter.return_value = mock_meter

                            from litestar_flags.contrib.otel import OTelHook

                            hook = OTelHook(
                                tracer=mock_tracer,
                                meter=mock_meter,
                            )
                            return hook

    def test_init_with_custom_tracer_and_meter(self, mock_tracer, mock_meter):
        """Test initialization with custom tracer and meter."""
        with patch("litestar_flags.contrib.otel.OTEL_AVAILABLE", True):
            from litestar_flags.contrib.otel import OTelHook

            hook = OTelHook(tracer=mock_tracer, meter=mock_meter)

            assert hook.tracer == mock_tracer
            assert hook.meter == mock_meter

    def test_init_creates_counter_and_histogram(self, mock_tracer, mock_meter):
        """Test that init creates metrics instruments."""
        with patch("litestar_flags.contrib.otel.OTEL_AVAILABLE", True):
            from litestar_flags.contrib.otel import (
                METRIC_EVALUATION_COUNT,
                METRIC_EVALUATION_LATENCY,
                OTelHook,
            )

            OTelHook(tracer=mock_tracer, meter=mock_meter)

            mock_meter.create_counter.assert_called_once()
            counter_call = mock_meter.create_counter.call_args
            assert counter_call.kwargs["name"] == METRIC_EVALUATION_COUNT

            mock_meter.create_histogram.assert_called_once()
            histogram_call = mock_meter.create_histogram.call_args
            assert histogram_call.kwargs["name"] == METRIC_EVALUATION_LATENCY

    def test_tracer_property(self, otel_hook, mock_tracer):
        """Test tracer property returns correct tracer."""
        assert otel_hook.tracer == mock_tracer

    def test_meter_property(self, otel_hook, mock_meter):
        """Test meter property returns correct meter."""
        assert otel_hook.meter == mock_meter

    def test_evaluation_counter_property(self, otel_hook):
        """Test evaluation_counter property."""
        counter = otel_hook.evaluation_counter
        assert counter is not None

    def test_latency_histogram_property(self, otel_hook):
        """Test latency_histogram property."""
        histogram = otel_hook.latency_histogram
        assert histogram is not None

    def test_start_evaluation_span_basic(self, otel_hook, mock_tracer):
        """Test starting a basic evaluation span."""
        _span = otel_hook.start_evaluation_span("my-flag")

        mock_tracer.start_span.assert_called_once()
        call_kwargs = mock_tracer.start_span.call_args.kwargs
        assert call_kwargs["name"] == "feature_flag.evaluation"
        assert "feature_flag.key" in call_kwargs["attributes"]
        assert call_kwargs["attributes"]["feature_flag.key"] == "my-flag"

    def test_start_evaluation_span_with_context(self, otel_hook, mock_tracer, full_context):
        """Test starting span with evaluation context."""
        _span = otel_hook.start_evaluation_span("my-flag", context=full_context, flag_type="boolean")

        call_kwargs = mock_tracer.start_span.call_args.kwargs
        assert call_kwargs["attributes"]["feature_flag.key"] == "my-flag"
        assert call_kwargs["attributes"]["feature_flag.type"] == "boolean"
        assert call_kwargs["attributes"]["feature_flag.targeting_key"] == "user-123"

    def test_start_evaluation_span_without_targeting_key(self, otel_hook, mock_tracer):
        """Test starting span with context without targeting key."""
        context = EvaluationContext(user_id="user-123")
        _span = otel_hook.start_evaluation_span("my-flag", context=context)

        call_kwargs = mock_tracer.start_span.call_args.kwargs
        # targeting_key should not be in attributes if not set
        assert "feature_flag.targeting_key" not in call_kwargs["attributes"]

    def test_end_evaluation_span_success(self, otel_hook, successful_result):
        """Test ending a span with successful result."""
        mock_span = MagicMock()
        otel_hook._span_start_times[id(mock_span)] = 0.0  # Mock start time

        with patch("litestar_flags.contrib.otel.StatusCode") as mock_status:
            mock_status.OK = "OK"
            otel_hook.end_evaluation_span(mock_span, successful_result)

        mock_span.set_attribute.assert_any_call("feature_flag.reason", "TARGETING_MATCH")
        mock_span.set_attribute.assert_any_call("feature_flag.variant", "enabled")
        mock_span.set_status.assert_called_once()
        mock_span.end.assert_called_once()

    def test_end_evaluation_span_error(self, otel_hook, error_result):
        """Test ending a span with error result."""
        mock_span = MagicMock()
        otel_hook._span_start_times[id(mock_span)] = 0.0

        with patch("litestar_flags.contrib.otel.StatusCode") as mock_status:
            mock_status.ERROR = "ERROR"
            otel_hook.end_evaluation_span(mock_span, error_result)

        mock_span.set_attribute.assert_any_call("feature_flag.error_code", "FLAG_NOT_FOUND")
        mock_span.set_status.assert_called_once()
        mock_span.end.assert_called_once()

    def test_end_evaluation_span_records_metrics(self, otel_hook, successful_result):
        """Test that ending span records metrics."""
        mock_span = MagicMock()
        otel_hook._span_start_times[id(mock_span)] = 0.0

        with patch("litestar_flags.contrib.otel.StatusCode"):
            otel_hook.end_evaluation_span(mock_span, successful_result)

        otel_hook._evaluation_counter.add.assert_called_once()
        otel_hook._latency_histogram.record.assert_called_once()

    def test_end_evaluation_span_with_record_values(self, mock_tracer, mock_meter, successful_result):
        """Test ending span with record_values enabled."""
        with patch("litestar_flags.contrib.otel.OTEL_AVAILABLE", True):
            from litestar_flags.contrib.otel import OTelHook

            hook = OTelHook(
                tracer=mock_tracer,
                meter=mock_meter,
                record_values=True,
            )

            mock_span = MagicMock()
            hook._span_start_times[id(mock_span)] = 0.0

            with patch("litestar_flags.contrib.otel.StatusCode"):
                hook.end_evaluation_span(mock_span, successful_result)

            # Should have set the value attribute
            set_attr_calls = [c for c in mock_span.set_attribute.call_args_list if c[0][0] == "feature_flag.value"]
            assert len(set_attr_calls) == 1

    @pytest.mark.asyncio
    async def test_before_evaluation(self, otel_hook, full_context):
        """Test async before_evaluation method."""
        span = await otel_hook.before_evaluation("my-flag", context=full_context, flag_type="boolean")

        assert span is not None
        otel_hook._tracer.start_span.assert_called()

    @pytest.mark.asyncio
    async def test_after_evaluation(self, otel_hook, successful_result):
        """Test async after_evaluation method."""
        mock_span = MagicMock()
        otel_hook._span_start_times[id(mock_span)] = 0.0

        with patch("litestar_flags.contrib.otel.StatusCode"):
            await otel_hook.after_evaluation(mock_span, successful_result)

        mock_span.end.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_error(self, otel_hook):
        """Test async on_error method."""
        mock_span = MagicMock()
        otel_hook._span_start_times[id(mock_span)] = 0.0
        error = ValueError("Test error")

        with patch("litestar_flags.contrib.otel.StatusCode") as mock_status:
            mock_status.ERROR = "ERROR"
            await otel_hook.on_error(mock_span, error, "my-flag")

        mock_span.set_status.assert_called_once()
        mock_span.record_exception.assert_called_once_with(error)
        mock_span.end.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_error_records_metrics(self, otel_hook):
        """Test that on_error records error metrics."""
        mock_span = MagicMock()
        otel_hook._span_start_times[id(mock_span)] = 0.0
        error = RuntimeError("Test error")

        with patch("litestar_flags.contrib.otel.StatusCode"):
            await otel_hook.on_error(mock_span, error, "my-flag")

        # Verify metrics were recorded
        counter_call = otel_hook._evaluation_counter.add.call_args
        assert counter_call[0][0] == 1  # count
        assert counter_call[0][1]["feature_flag.key"] == "my-flag"
        assert counter_call[0][1]["feature_flag.reason"] == "ERROR"

    def test_record_evaluation_convenience_method(self, otel_hook, successful_result, full_context):
        """Test record_evaluation convenience method."""
        with patch("litestar_flags.contrib.otel.StatusCode"):
            otel_hook.record_evaluation(
                "my-flag",
                successful_result,
                context=full_context,
                flag_type="boolean",
            )

        # Should have started and ended a span
        otel_hook._tracer.start_span.assert_called_once()

    def test_latency_calculation(self, otel_hook, successful_result):
        """Test that latency is correctly calculated."""
        mock_span = MagicMock()

        # Simulate 100ms delay
        import time

        start_time = time.perf_counter()
        otel_hook._span_start_times[id(mock_span)] = start_time - 0.1  # 100ms ago

        with patch("litestar_flags.contrib.otel.StatusCode"):
            otel_hook.end_evaluation_span(mock_span, successful_result)

        # Check latency was recorded (should be ~100ms or more)
        histogram_call = otel_hook._latency_histogram.record.call_args
        latency_ms = histogram_call[0][0]
        assert latency_ms >= 100.0  # At least 100ms

    def test_span_without_start_time(self, otel_hook, successful_result):
        """Test ending span when start time wasn't recorded."""
        mock_span = MagicMock()
        # Don't add to _span_start_times

        with patch("litestar_flags.contrib.otel.StatusCode"):
            otel_hook.end_evaluation_span(mock_span, successful_result)

        # Should still work, latency will be 0
        histogram_call = otel_hook._latency_histogram.record.call_args
        latency_ms = histogram_call[0][0]
        assert latency_ms == 0.0


class TestOTelHookWithoutOTel:
    """Test OTelHook behavior when OpenTelemetry is not available."""

    def test_init_raises_import_error_when_otel_not_available(self):
        """Test that OTelHook raises ImportError when otel is not available."""
        with patch("litestar_flags.contrib.otel.OTEL_AVAILABLE", False):
            # Need to reload the module to pick up the patched value

            import litestar_flags.contrib.otel as otel_module

            # Temporarily modify the module's OTEL_AVAILABLE
            original_value = otel_module.OTEL_AVAILABLE
            otel_module.OTEL_AVAILABLE = False

            try:
                with pytest.raises(ImportError, match="opentelemetry-api is required"):
                    otel_module.OTelHook()
            finally:
                otel_module.OTEL_AVAILABLE = original_value


class TestOTelHookSemanticConventions:
    """Test that OTelHook follows semantic conventions."""

    def test_span_name_constant(self):
        """Test span name follows conventions."""
        from litestar_flags.contrib.otel import SPAN_NAME

        assert SPAN_NAME == "feature_flag.evaluation"

    def test_attribute_constants(self):
        """Test attribute name constants."""
        from litestar_flags.contrib.otel import (
            ATTR_ERROR_CODE,
            ATTR_ERROR_MESSAGE,
            ATTR_FLAG_KEY,
            ATTR_FLAG_REASON,
            ATTR_FLAG_TYPE,
            ATTR_FLAG_VALUE,
            ATTR_FLAG_VARIANT,
            ATTR_TARGETING_KEY,
        )

        assert ATTR_FLAG_KEY == "feature_flag.key"
        assert ATTR_FLAG_TYPE == "feature_flag.type"
        assert ATTR_FLAG_VARIANT == "feature_flag.variant"
        assert ATTR_FLAG_REASON == "feature_flag.reason"
        assert ATTR_FLAG_VALUE == "feature_flag.value"
        assert ATTR_ERROR_CODE == "feature_flag.error_code"
        assert ATTR_ERROR_MESSAGE == "feature_flag.error_message"
        assert ATTR_TARGETING_KEY == "feature_flag.targeting_key"

    def test_metric_name_constants(self):
        """Test metric name constants."""
        from litestar_flags.contrib.otel import (
            METRIC_EVALUATION_COUNT,
            METRIC_EVALUATION_LATENCY,
        )

        assert METRIC_EVALUATION_COUNT == "feature_flag.evaluation.count"
        assert METRIC_EVALUATION_LATENCY == "feature_flag.evaluation.latency"


# =============================================================================
# LoggingHook Tests
# =============================================================================


class TestLoggingHookImport:
    """Test LoggingHook import behavior."""

    def test_structlog_available_constant_exported(self):
        """Test that STRUCTLOG_AVAILABLE is exported."""
        from litestar_flags.contrib.logging import STRUCTLOG_AVAILABLE

        assert isinstance(STRUCTLOG_AVAILABLE, bool)

    def test_logging_hook_import(self):
        """Test that LoggingHook can be imported."""
        from litestar_flags.contrib.logging import LoggingHook

        assert LoggingHook is not None


class TestLoggingHookWithStdlib:
    """Test LoggingHook with stdlib logging."""

    @pytest.fixture
    def mock_logger(self):
        """Create a mock stdlib logger."""
        logger = MagicMock(spec=logging.Logger)
        return logger

    @pytest.fixture
    def logging_hook(self, mock_logger):
        """Create LoggingHook with mock logger."""
        from litestar_flags.contrib.logging import LoggingHook

        hook = LoggingHook(logger=mock_logger)
        hook._use_structlog = False  # Force stdlib logging
        return hook

    def test_init_with_custom_logger(self, mock_logger):
        """Test initialization with custom logger."""
        from litestar_flags.contrib.logging import LoggingHook

        hook = LoggingHook(logger=mock_logger)
        assert hook.logger == mock_logger

    def test_init_with_custom_levels(self):
        """Test initialization with custom log levels."""
        from litestar_flags.contrib.logging import LoggingHook

        hook = LoggingHook(
            evaluation_level="INFO",
            error_level="CRITICAL",
        )
        assert hook._evaluation_level == "INFO"
        assert hook._error_level == "CRITICAL"

    def test_init_log_values_default_false(self):
        """Test that log_values defaults to False for privacy."""
        from litestar_flags.contrib.logging import LoggingHook

        hook = LoggingHook()
        assert hook._log_values is False

    def test_init_include_context_default_true(self):
        """Test that include_context defaults to True."""
        from litestar_flags.contrib.logging import LoggingHook

        hook = LoggingHook()
        assert hook._include_context is True

    def test_logger_property(self, logging_hook, mock_logger):
        """Test logger property returns correct logger."""
        assert logging_hook.logger == mock_logger

    def test_get_log_method_debug(self, logging_hook, mock_logger):
        """Test _get_log_method returns debug method."""
        method = logging_hook._get_log_method("DEBUG")
        assert method == mock_logger.debug

    def test_get_log_method_info(self, logging_hook, mock_logger):
        """Test _get_log_method returns info method."""
        method = logging_hook._get_log_method("INFO")
        assert method == mock_logger.info

    def test_get_log_method_warning(self, logging_hook, mock_logger):
        """Test _get_log_method returns warning method."""
        method = logging_hook._get_log_method("WARNING")
        assert method == mock_logger.warning

    def test_get_log_method_error(self, logging_hook, mock_logger):
        """Test _get_log_method returns error method."""
        method = logging_hook._get_log_method("ERROR")
        assert method == mock_logger.error

    def test_get_log_method_unknown_defaults_to_debug(self, logging_hook, mock_logger):
        """Test _get_log_method defaults to debug for unknown levels."""
        method = logging_hook._get_log_method("UNKNOWN")
        assert method == mock_logger.debug

    def test_build_log_data_basic(self, logging_hook, successful_result):
        """Test _build_log_data with basic result."""
        data = logging_hook._build_log_data("test-flag", successful_result)

        assert data["flag_key"] == "test-flag"
        assert data["reason"] == "TARGETING_MATCH"
        assert data["variant"] == "enabled"
        assert "value" not in data  # log_values is False

    def test_build_log_data_with_log_values(self, mock_logger, successful_result):
        """Test _build_log_data with log_values enabled."""
        from litestar_flags.contrib.logging import LoggingHook

        hook = LoggingHook(logger=mock_logger, log_values=True)
        data = hook._build_log_data("test-flag", successful_result)

        assert "value" in data
        assert data["value"] is True

    def test_build_log_data_with_error(self, logging_hook, error_result):
        """Test _build_log_data with error result."""
        data = logging_hook._build_log_data("test-flag", error_result)

        assert data["error_code"] == "FLAG_NOT_FOUND"
        assert data["error_message"] == "Flag 'test-flag' not found"

    def test_build_log_data_with_context(self, logging_hook, successful_result, full_context):
        """Test _build_log_data includes context fields."""
        data = logging_hook._build_log_data("test-flag", successful_result, full_context)

        assert data["targeting_key"] == "user-123"
        assert data["user_id"] == "user-123"
        assert data["organization_id"] == "org-456"
        assert data["environment"] == "production"
        assert data["app_version"] == "2.0.0"

    def test_build_log_data_without_context(self, mock_logger, successful_result):
        """Test _build_log_data with include_context=False."""
        from litestar_flags.contrib.logging import LoggingHook

        hook = LoggingHook(logger=mock_logger, include_context=False)
        data = hook._build_log_data("test-flag", successful_result, EvaluationContext(targeting_key="user-123"))

        assert "targeting_key" not in data
        assert "user_id" not in data

    def test_build_log_data_with_flag_metadata(self, logging_hook, successful_result):
        """Test _build_log_data includes flag_metadata."""
        data = logging_hook._build_log_data("test-flag", successful_result)

        assert data["flag_metadata"] == {"version": "1.0"}

    def test_log_with_data_stdlib(self, logging_hook, mock_logger):
        """Test _log_with_data with stdlib logging."""
        data = {"key": "value"}
        logging_hook._log_with_data("INFO", "Test message", data)

        mock_logger.info.assert_called_once_with("Test message", extra=data)

    @pytest.mark.asyncio
    async def test_log_evaluation_success(self, logging_hook, mock_logger, successful_result):
        """Test log_evaluation with successful result."""
        await logging_hook.log_evaluation("test-flag", successful_result)

        mock_logger.debug.assert_called_once()
        call_args = mock_logger.debug.call_args
        assert "Feature flag evaluated: test-flag" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_log_evaluation_error(self, logging_hook, mock_logger, error_result):
        """Test log_evaluation with error result."""
        await logging_hook.log_evaluation("test-flag", error_result)

        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        assert "Feature flag evaluation error: test-flag" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_log_evaluation_with_context(self, logging_hook, mock_logger, successful_result, full_context):
        """Test log_evaluation includes context in log data."""
        await logging_hook.log_evaluation("test-flag", successful_result, full_context)

        call_args = mock_logger.debug.call_args
        extra = call_args.kwargs["extra"]
        assert extra["targeting_key"] == "user-123"

    @pytest.mark.asyncio
    async def test_before_evaluation(self, logging_hook, mock_logger, full_context):
        """Test before_evaluation logs starting message."""
        await logging_hook.before_evaluation("test-flag", full_context)

        mock_logger.debug.assert_called_once()
        call_args = mock_logger.debug.call_args
        assert "Starting feature flag evaluation: test-flag" in call_args[0][0]
        assert call_args.kwargs["extra"]["targeting_key"] == "user-123"

    @pytest.mark.asyncio
    async def test_before_evaluation_without_context(self, logging_hook, mock_logger):
        """Test before_evaluation without context."""
        await logging_hook.before_evaluation("test-flag")

        mock_logger.debug.assert_called_once()
        call_args = mock_logger.debug.call_args
        assert call_args.kwargs["extra"]["flag_key"] == "test-flag"

    @pytest.mark.asyncio
    async def test_after_evaluation(self, logging_hook, mock_logger, successful_result):
        """Test after_evaluation calls log_evaluation."""
        await logging_hook.after_evaluation("test-flag", successful_result)

        mock_logger.debug.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_error_stdlib(self, logging_hook, mock_logger, full_context):
        """Test on_error with stdlib logging."""
        error = ValueError("Test error")
        await logging_hook.on_error(error, "test-flag", full_context)

        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        assert "Feature flag evaluation exception: test-flag" in call_args[0][0]
        assert call_args.kwargs["exc_info"] == error
        assert call_args.kwargs["extra"]["error_type"] == "ValueError"
        assert call_args.kwargs["extra"]["error_message"] == "Test error"

    @pytest.mark.asyncio
    async def test_on_error_without_context(self, logging_hook, mock_logger):
        """Test on_error without context."""
        error = RuntimeError("Test error")
        await logging_hook.on_error(error, "test-flag")

        call_args = mock_logger.error.call_args
        assert "targeting_key" not in call_args.kwargs["extra"]

    def test_log_evaluation_sync(self, logging_hook, mock_logger, successful_result):
        """Test synchronous log_evaluation_sync method."""
        logging_hook.log_evaluation_sync("test-flag", successful_result)

        mock_logger.debug.assert_called_once()

    def test_log_evaluation_sync_error(self, logging_hook, mock_logger, error_result):
        """Test log_evaluation_sync with error result."""
        logging_hook.log_evaluation_sync("test-flag", error_result)

        mock_logger.error.assert_called_once()

    def test_bind_stdlib_returns_new_hook(self, logging_hook):
        """Test bind returns a new LoggingHook for stdlib."""
        new_hook = logging_hook.bind(request_id="abc-123")

        assert new_hook is not logging_hook
        assert new_hook._evaluation_level == logging_hook._evaluation_level
        assert new_hook._error_level == logging_hook._error_level


class TestLoggingHookWithStructlog:
    """Test LoggingHook with structlog (when available)."""

    @pytest.fixture
    def mock_structlog_logger(self):
        """Create a mock structlog logger."""
        logger = MagicMock()
        logger.bind.return_value = MagicMock()
        return logger

    @pytest.fixture
    def logging_hook_structlog(self, mock_structlog_logger):
        """Create LoggingHook configured for structlog."""
        from litestar_flags.contrib.logging import LoggingHook

        hook = LoggingHook(logger=mock_structlog_logger)
        hook._use_structlog = True  # Force structlog mode
        return hook

    def test_log_with_data_structlog(self, logging_hook_structlog, mock_structlog_logger):
        """Test _log_with_data with structlog uses kwargs."""
        data = {"key": "value", "count": 42}
        logging_hook_structlog._log_with_data("INFO", "Test message", data)

        mock_structlog_logger.info.assert_called_once_with("Test message", key="value", count=42)

    @pytest.mark.asyncio
    async def test_on_error_structlog(self, logging_hook_structlog, mock_structlog_logger):
        """Test on_error with structlog includes exc_info."""
        error = ValueError("Structlog error")
        await logging_hook_structlog.on_error(error, "test-flag")

        mock_structlog_logger.error.assert_called_once()
        call_kwargs = mock_structlog_logger.error.call_args.kwargs
        assert call_kwargs["exc_info"] == error
        assert call_kwargs["error_type"] == "ValueError"

    def test_bind_structlog_returns_bound_hook(self, logging_hook_structlog, mock_structlog_logger):
        """Test bind with structlog returns hook with bound logger."""
        bound_logger = MagicMock()
        mock_structlog_logger.bind.return_value = bound_logger

        # Must patch the structlog module reference to not be None
        with patch("litestar_flags.contrib.logging.structlog", MagicMock()):
            new_hook = logging_hook_structlog.bind(request_id="xyz-789")

        mock_structlog_logger.bind.assert_called_once_with(request_id="xyz-789")
        assert new_hook is not logging_hook_structlog


class TestLoggingHookDefaultLogger:
    """Test LoggingHook default logger creation."""

    def test_get_default_logger_stdlib(self):
        """Test _get_default_logger returns stdlib logger when structlog unavailable."""
        with patch("litestar_flags.contrib.logging.STRUCTLOG_AVAILABLE", False):
            with patch("litestar_flags.contrib.logging.structlog", None):
                from litestar_flags.contrib.logging import _get_default_logger

                logger = _get_default_logger()
                assert isinstance(logger, logging.Logger)
                assert logger.name == "litestar_flags"

    def test_default_logger_created_on_init(self):
        """Test that default logger is created when none provided."""
        from litestar_flags.contrib.logging import LoggingHook

        hook = LoggingHook()
        assert hook.logger is not None


class TestLoggingHookLogLevels:
    """Test LoggingHook with different log levels."""

    @pytest.fixture
    def mock_logger(self):
        """Create a mock logger."""
        return MagicMock(spec=logging.Logger)

    @pytest.mark.parametrize(
        "level,method_name",
        [
            ("DEBUG", "debug"),
            ("INFO", "info"),
            ("WARNING", "warning"),
            ("ERROR", "error"),
        ],
    )
    def test_evaluation_level_configuration(self, mock_logger, level, method_name, successful_result):
        """Test that evaluation_level correctly routes to the right log method."""
        from litestar_flags.contrib.logging import LoggingHook

        hook = LoggingHook(logger=mock_logger, evaluation_level=level)
        hook._use_structlog = False

        hook.log_evaluation_sync("test-flag", successful_result)

        log_method = getattr(mock_logger, method_name)
        log_method.assert_called_once()

    @pytest.mark.parametrize(
        "level,method_name",
        [
            ("DEBUG", "debug"),
            ("INFO", "info"),
            ("WARNING", "warning"),
            ("ERROR", "error"),
        ],
    )
    def test_error_level_configuration(self, mock_logger, level, method_name, error_result):
        """Test that error_level correctly routes to the right log method."""
        from litestar_flags.contrib.logging import LoggingHook

        hook = LoggingHook(logger=mock_logger, error_level=level)
        hook._use_structlog = False

        hook.log_evaluation_sync("test-flag", error_result)

        log_method = getattr(mock_logger, method_name)
        log_method.assert_called_once()


class TestLoggerProtocol:
    """Test LoggerProtocol type checking."""

    def test_logger_protocol_exists(self):
        """Test that LoggerProtocol is defined."""
        from litestar_flags.contrib.logging import LoggerProtocol

        assert LoggerProtocol is not None

    def test_stdlib_logger_satisfies_protocol(self):
        """Test that stdlib Logger satisfies LoggerProtocol."""
        from litestar_flags.contrib.logging import LoggerProtocol

        logger = logging.getLogger("test")
        assert isinstance(logger, LoggerProtocol)

    def test_mock_logger_satisfies_protocol(self):
        """Test that a properly mocked logger satisfies LoggerProtocol."""
        from litestar_flags.contrib.logging import LoggerProtocol

        mock_logger = MagicMock()
        mock_logger.debug = MagicMock()
        mock_logger.info = MagicMock()
        mock_logger.warning = MagicMock()
        mock_logger.error = MagicMock()

        assert isinstance(mock_logger, LoggerProtocol)


# =============================================================================
# Integration Tests
# =============================================================================


class TestContribIntegration:
    """Integration tests for contrib modules working together."""

    @pytest.fixture
    def mock_tracer(self):
        """Create a mock tracer."""
        tracer = MagicMock()
        mock_span = MagicMock()
        tracer.start_span.return_value = mock_span
        return tracer

    @pytest.fixture
    def mock_meter(self):
        """Create a mock meter."""
        meter = MagicMock()
        meter.create_counter.return_value = MagicMock()
        meter.create_histogram.return_value = MagicMock()
        return meter

    @pytest.mark.asyncio
    async def test_combined_otel_and_logging_hooks(
        self,
        mock_tracer,
        mock_meter,
        successful_result,
        full_context,
    ):
        """Test using both OTelHook and LoggingHook together."""
        from litestar_flags.contrib.logging import LoggingHook

        # Create logging hook
        mock_logger = MagicMock(spec=logging.Logger)
        logging_hook = LoggingHook(logger=mock_logger)
        logging_hook._use_structlog = False

        # Create otel hook
        with patch("litestar_flags.contrib.otel.OTEL_AVAILABLE", True):
            from litestar_flags.contrib.otel import OTelHook

            otel_hook = OTelHook(tracer=mock_tracer, meter=mock_meter)

            # Simulate evaluation flow
            span = await otel_hook.before_evaluation("test-flag", full_context)
            await logging_hook.before_evaluation("test-flag", full_context)

            # ... evaluation happens ...

            with patch("litestar_flags.contrib.otel.StatusCode"):
                await otel_hook.after_evaluation(span, successful_result)
            await logging_hook.after_evaluation("test-flag", successful_result, full_context)

            # Verify both hooks were called
            mock_tracer.start_span.assert_called()
            mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_error_handling_both_hooks(
        self,
        mock_tracer,
        mock_meter,
        full_context,
    ):
        """Test error handling with both hooks."""
        from litestar_flags.contrib.logging import LoggingHook

        mock_logger = MagicMock(spec=logging.Logger)
        logging_hook = LoggingHook(logger=mock_logger)
        logging_hook._use_structlog = False

        with patch("litestar_flags.contrib.otel.OTEL_AVAILABLE", True):
            from litestar_flags.contrib.otel import OTelHook

            otel_hook = OTelHook(tracer=mock_tracer, meter=mock_meter)

            error = RuntimeError("Evaluation failed")
            span = await otel_hook.before_evaluation("test-flag", full_context)

            with patch("litestar_flags.contrib.otel.StatusCode"):
                await otel_hook.on_error(span, error, "test-flag")
            await logging_hook.on_error(error, "test-flag", full_context)

            # Verify error handling in both
            mock_span = mock_tracer.start_span.return_value
            mock_span.record_exception.assert_called_once_with(error)
            mock_logger.error.assert_called()


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_flag_key(self):
        """Test handling of empty flag key."""
        from litestar_flags.contrib.logging import LoggingHook

        mock_logger = MagicMock(spec=logging.Logger)
        hook = LoggingHook(logger=mock_logger)
        hook._use_structlog = False

        result = EvaluationDetails(
            value=True,
            flag_key="",
            reason=EvaluationReason.DEFAULT,
        )

        hook.log_evaluation_sync("", result)
        mock_logger.debug.assert_called_once()

    def test_very_long_flag_value_in_otel(self):
        """Test that very long values are truncated in OTelHook."""
        mock_tracer = MagicMock()
        mock_meter = MagicMock()
        mock_meter.create_counter.return_value = MagicMock()
        mock_meter.create_histogram.return_value = MagicMock()

        with patch("litestar_flags.contrib.otel.OTEL_AVAILABLE", True):
            from litestar_flags.contrib.otel import OTelHook

            hook = OTelHook(
                tracer=mock_tracer,
                meter=mock_meter,
                record_values=True,
            )

            # Create result with very long value
            long_value = "x" * 500
            result = EvaluationDetails(
                value=long_value,
                flag_key="test-flag",
                reason=EvaluationReason.STATIC,
            )

            mock_span = MagicMock()
            hook._span_start_times[id(mock_span)] = 0.0

            with patch("litestar_flags.contrib.otel.StatusCode"):
                hook.end_evaluation_span(mock_span, result)

            # Value should not be set because it exceeds 256 chars
            set_attr_calls = [c for c in mock_span.set_attribute.call_args_list if c[0][0] == "feature_flag.value"]
            assert len(set_attr_calls) == 0

    def test_none_context_values(self):
        """Test handling of None values in context."""
        from litestar_flags.contrib.logging import LoggingHook

        mock_logger = MagicMock(spec=logging.Logger)
        hook = LoggingHook(logger=mock_logger, include_context=True)
        hook._use_structlog = False

        # Context with all None values
        context = EvaluationContext()

        result = EvaluationDetails(
            value=True,
            flag_key="test-flag",
            reason=EvaluationReason.DEFAULT,
        )

        data = hook._build_log_data("test-flag", result, context)

        # None values should not be included
        assert "targeting_key" not in data
        assert "user_id" not in data
        assert "organization_id" not in data

    def test_special_characters_in_flag_key(self):
        """Test handling of special characters in flag key."""
        from litestar_flags.contrib.logging import LoggingHook

        mock_logger = MagicMock(spec=logging.Logger)
        hook = LoggingHook(logger=mock_logger)
        hook._use_structlog = False

        result = EvaluationDetails(
            value=True,
            flag_key="flag/with:special-chars_and.dots",
            reason=EvaluationReason.DEFAULT,
        )

        hook.log_evaluation_sync("flag/with:special-chars_and.dots", result)
        mock_logger.debug.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_evaluations(self):
        """Test handling concurrent evaluations."""
        import asyncio

        from litestar_flags.contrib.logging import LoggingHook

        mock_logger = MagicMock(spec=logging.Logger)
        hook = LoggingHook(logger=mock_logger)
        hook._use_structlog = False

        async def evaluate_flag(flag_num: int):
            result = EvaluationDetails(
                value=True,
                flag_key=f"flag-{flag_num}",
                reason=EvaluationReason.DEFAULT,
            )
            await hook.log_evaluation(f"flag-{flag_num}", result)

        # Run 10 concurrent evaluations
        await asyncio.gather(*[evaluate_flag(i) for i in range(10)])

        # Should have logged 10 times
        assert mock_logger.debug.call_count == 10
