"""Tests for the analytics module."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from litestar_flags.analytics import (
    AnalyticsAggregator,
    FlagEvaluationEvent,
    FlagMetrics,
    InMemoryAnalyticsCollector,
)
from litestar_flags.types import EvaluationReason

if TYPE_CHECKING:
    pass


# -----------------------------------------------------------------------------
# FlagEvaluationEvent Tests
# -----------------------------------------------------------------------------
class TestFlagEvaluationEvent:
    """Tests for FlagEvaluationEvent dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating an event with all fields populated."""
        timestamp = datetime.now(UTC)
        event = FlagEvaluationEvent(
            timestamp=timestamp,
            flag_key="test-flag",
            value=True,
            reason=EvaluationReason.TARGETING_MATCH,
            variant="beta-users",
            targeting_key="user-123",
            context_attributes={"plan": "premium", "country": "US"},
            evaluation_duration_ms=2.5,
        )

        assert event.timestamp == timestamp
        assert event.flag_key == "test-flag"
        assert event.value is True
        assert event.reason == EvaluationReason.TARGETING_MATCH
        assert event.variant == "beta-users"
        assert event.targeting_key == "user-123"
        assert event.context_attributes == {"plan": "premium", "country": "US"}
        assert event.evaluation_duration_ms == 2.5

    def test_creation_with_required_fields_only(self) -> None:
        """Test creating an event with only required fields."""
        timestamp = datetime.now(UTC)
        event = FlagEvaluationEvent(
            timestamp=timestamp,
            flag_key="minimal-flag",
            value=False,
            reason=EvaluationReason.DEFAULT,
        )

        assert event.timestamp == timestamp
        assert event.flag_key == "minimal-flag"
        assert event.value is False
        assert event.reason == EvaluationReason.DEFAULT
        assert event.variant is None
        assert event.targeting_key is None
        assert event.context_attributes == {}
        assert event.evaluation_duration_ms == 0.0

    def test_default_values(self) -> None:
        """Test that default values are correctly applied."""
        event = FlagEvaluationEvent(
            timestamp=datetime.now(UTC),
            flag_key="defaults",
            value="control",
            reason=EvaluationReason.STATIC,
        )

        assert event.variant is None
        assert event.targeting_key is None
        assert event.context_attributes == {}
        assert event.evaluation_duration_ms == 0.0

    def test_to_dict_serialization(self) -> None:
        """Test that to_dict() correctly serializes the event."""
        timestamp = datetime.now(UTC)
        event = FlagEvaluationEvent(
            timestamp=timestamp,
            flag_key="serialize-test",
            value={"variant": "treatment"},
            reason=EvaluationReason.SPLIT,
            variant="treatment",
            targeting_key="user-456",
            context_attributes={"role": "admin"},
            evaluation_duration_ms=1.5,
        )

        result = event.to_dict()

        assert result["timestamp"] == timestamp.isoformat()
        assert result["flag_key"] == "serialize-test"
        assert result["value"] == {"variant": "treatment"}
        assert result["reason"] == "SPLIT"
        assert result["variant"] == "treatment"
        assert result["targeting_key"] == "user-456"
        assert result["context_attributes"] == {"role": "admin"}
        assert result["evaluation_duration_ms"] == 1.5

    def test_to_dict_with_none_values(self) -> None:
        """Test to_dict() handles None values correctly."""
        event = FlagEvaluationEvent(
            timestamp=datetime.now(UTC),
            flag_key="none-test",
            value=None,
            reason=EvaluationReason.ERROR,
        )

        result = event.to_dict()

        assert result["value"] is None
        assert result["variant"] is None
        assert result["targeting_key"] is None

    def test_different_value_types(self) -> None:
        """Test events with different value types."""
        timestamp = datetime.now(UTC)

        # Boolean value
        bool_event = FlagEvaluationEvent(
            timestamp=timestamp,
            flag_key="bool-flag",
            value=True,
            reason=EvaluationReason.STATIC,
        )
        assert bool_event.value is True

        # String value
        str_event = FlagEvaluationEvent(
            timestamp=timestamp,
            flag_key="str-flag",
            value="variant-a",
            reason=EvaluationReason.SPLIT,
        )
        assert str_event.value == "variant-a"

        # Number value
        num_event = FlagEvaluationEvent(
            timestamp=timestamp,
            flag_key="num-flag",
            value=42,
            reason=EvaluationReason.DEFAULT,
        )
        assert num_event.value == 42

        # Float value
        float_event = FlagEvaluationEvent(
            timestamp=timestamp,
            flag_key="float-flag",
            value=3.14,
            reason=EvaluationReason.DEFAULT,
        )
        assert float_event.value == 3.14

        # Dict value
        dict_event = FlagEvaluationEvent(
            timestamp=timestamp,
            flag_key="json-flag",
            value={"key": "value", "nested": {"data": True}},
            reason=EvaluationReason.TARGETING_MATCH,
        )
        assert dict_event.value == {"key": "value", "nested": {"data": True}}


# -----------------------------------------------------------------------------
# InMemoryAnalyticsCollector Tests
# -----------------------------------------------------------------------------
class TestInMemoryAnalyticsCollector:
    """Tests for InMemoryAnalyticsCollector."""

    @pytest.fixture
    def collector(self) -> InMemoryAnalyticsCollector:
        """Create an in-memory analytics collector."""
        return InMemoryAnalyticsCollector(max_size=100)

    @pytest.fixture
    def sample_event(self) -> FlagEvaluationEvent:
        """Create a sample evaluation event."""
        return FlagEvaluationEvent(
            timestamp=datetime.now(UTC),
            flag_key="test-flag",
            value=True,
            reason=EvaluationReason.STATIC,
            targeting_key="user-123",
        )

    async def test_record_stores_event(
        self, collector: InMemoryAnalyticsCollector, sample_event: FlagEvaluationEvent
    ) -> None:
        """Test that record() stores an event."""
        await collector.record(sample_event)

        events = await collector.get_events()
        assert len(events) == 1
        assert events[0] == sample_event

    async def test_record_multiple_events(self, collector: InMemoryAnalyticsCollector) -> None:
        """Test recording multiple events."""
        events_to_record = [
            FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key=f"flag-{i}",
                value=i % 2 == 0,
                reason=EvaluationReason.STATIC,
            )
            for i in range(10)
        ]

        for event in events_to_record:
            await collector.record(event)

        stored_events = await collector.get_events()
        assert len(stored_events) == 10

    async def test_max_size_eviction(self) -> None:
        """Test that oldest events are evicted when max_size is exceeded."""
        collector = InMemoryAnalyticsCollector(max_size=5)

        # Record 10 events
        for i in range(10):
            event = FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key=f"flag-{i}",
                value=True,
                reason=EvaluationReason.STATIC,
            )
            await collector.record(event)

        # Only the last 5 should remain
        events = await collector.get_events()
        assert len(events) == 5

        # Check that we have the newest events (flags 5-9)
        flag_keys = [e.flag_key for e in events]
        assert flag_keys == ["flag-5", "flag-6", "flag-7", "flag-8", "flag-9"]

    async def test_max_size_property(self) -> None:
        """Test that max_size property returns the configured value."""
        collector = InMemoryAnalyticsCollector(max_size=500)
        assert collector.max_size == 500

    async def test_get_events_without_filter(self, collector: InMemoryAnalyticsCollector) -> None:
        """Test get_events() returns all events when no filter is provided."""
        events = [
            FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key=f"flag-{i % 3}",  # 3 different flags
                value=True,
                reason=EvaluationReason.STATIC,
            )
            for i in range(9)
        ]

        for event in events:
            await collector.record(event)

        result = await collector.get_events()
        assert len(result) == 9

    async def test_get_events_with_flag_key_filter(self, collector: InMemoryAnalyticsCollector) -> None:
        """Test get_events() filters by flag_key when provided."""
        # Record events for different flags
        for i in range(10):
            event = FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key="target-flag" if i % 2 == 0 else "other-flag",
                value=True,
                reason=EvaluationReason.STATIC,
            )
            await collector.record(event)

        # Get only events for target-flag
        result = await collector.get_events(flag_key="target-flag")
        assert len(result) == 5
        assert all(e.flag_key == "target-flag" for e in result)

    async def test_get_events_with_limit(self, collector: InMemoryAnalyticsCollector) -> None:
        """Test get_events() respects the limit parameter."""
        for i in range(20):
            event = FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key=f"flag-{i}",
                value=True,
                reason=EvaluationReason.STATIC,
            )
            await collector.record(event)

        # Get only the last 5 events
        result = await collector.get_events(limit=5)
        assert len(result) == 5

        # Should be the most recent events
        flag_keys = [e.flag_key for e in result]
        assert flag_keys == ["flag-15", "flag-16", "flag-17", "flag-18", "flag-19"]

    async def test_get_events_with_flag_key_and_limit(self, collector: InMemoryAnalyticsCollector) -> None:
        """Test get_events() with both flag_key and limit."""
        for i in range(10):
            event = FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key="target-flag" if i < 6 else "other-flag",
                value=True,
                reason=EvaluationReason.STATIC,
            )
            await collector.record(event)

        result = await collector.get_events(flag_key="target-flag", limit=3)
        assert len(result) == 3
        assert all(e.flag_key == "target-flag" for e in result)

    async def test_clear_removes_all_events(
        self, collector: InMemoryAnalyticsCollector, sample_event: FlagEvaluationEvent
    ) -> None:
        """Test that clear() removes all stored events."""
        # Add some events
        for _ in range(5):
            await collector.record(sample_event)

        # Verify events exist
        events = await collector.get_events()
        assert len(events) == 5

        # Clear and verify
        await collector.clear()
        events = await collector.get_events()
        assert len(events) == 0

    async def test_flush_is_noop(
        self, collector: InMemoryAnalyticsCollector, sample_event: FlagEvaluationEvent
    ) -> None:
        """Test that flush() is a no-op for in-memory collector."""
        await collector.record(sample_event)

        # flush() should not raise and events should still be there
        await collector.flush()

        events = await collector.get_events()
        assert len(events) == 1

    async def test_close_clears_events(
        self, collector: InMemoryAnalyticsCollector, sample_event: FlagEvaluationEvent
    ) -> None:
        """Test that close() clears all stored events."""
        for _ in range(5):
            await collector.record(sample_event)

        await collector.close()

        events = await collector.get_events()
        assert len(events) == 0

    async def test_get_event_count(self, collector: InMemoryAnalyticsCollector) -> None:
        """Test get_event_count() returns correct counts."""
        for i in range(10):
            event = FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key="flag-a" if i < 6 else "flag-b",
                value=True,
                reason=EvaluationReason.STATIC,
            )
            await collector.record(event)

        assert await collector.get_event_count() == 10
        assert await collector.get_event_count(flag_key="flag-a") == 6
        assert await collector.get_event_count(flag_key="flag-b") == 4
        assert await collector.get_event_count(flag_key="flag-c") == 0

    async def test_len_returns_event_count(
        self, collector: InMemoryAnalyticsCollector, sample_event: FlagEvaluationEvent
    ) -> None:
        """Test that __len__ returns the number of stored events."""
        assert len(collector) == 0

        for _ in range(5):
            await collector.record(sample_event)

        assert len(collector) == 5

    async def test_thread_safety_with_concurrent_records(self) -> None:
        """Test thread safety with concurrent record operations."""
        collector = InMemoryAnalyticsCollector(max_size=1000)

        async def record_events(start: int, count: int) -> None:
            for i in range(count):
                event = FlagEvaluationEvent(
                    timestamp=datetime.now(UTC),
                    flag_key=f"flag-{start + i}",
                    value=True,
                    reason=EvaluationReason.STATIC,
                )
                await collector.record(event)

        # Run multiple concurrent record operations
        await asyncio.gather(
            record_events(0, 100),
            record_events(100, 100),
            record_events(200, 100),
            record_events(300, 100),
            record_events(400, 100),
        )

        # All 500 events should be recorded
        count = await collector.get_event_count()
        assert count == 500

    async def test_thread_safety_with_concurrent_reads_and_writes(self) -> None:
        """Test thread safety with concurrent reads and writes."""
        collector = InMemoryAnalyticsCollector(max_size=1000)

        async def write_events() -> None:
            for i in range(100):
                event = FlagEvaluationEvent(
                    timestamp=datetime.now(UTC),
                    flag_key=f"flag-{i}",
                    value=True,
                    reason=EvaluationReason.STATIC,
                )
                await collector.record(event)

        async def read_events() -> list[int]:
            results = []
            for _ in range(50):
                events = await collector.get_events()
                results.append(len(events))
                await asyncio.sleep(0.001)  # Small delay
            return results

        # Run concurrent reads and writes
        write_task = asyncio.create_task(write_events())
        read_results = await read_events()
        await write_task

        # All operations should complete without error
        # Final count should be 100
        assert await collector.get_event_count() == 100

        # Read counts should be non-decreasing (or at least not crash)
        assert len(read_results) == 50


# -----------------------------------------------------------------------------
# AnalyticsAggregator Tests
# -----------------------------------------------------------------------------
class TestAnalyticsAggregator:
    """Tests for AnalyticsAggregator."""

    @pytest.fixture
    def collector(self) -> InMemoryAnalyticsCollector:
        """Create an in-memory analytics collector."""
        return InMemoryAnalyticsCollector(max_size=10000)

    @pytest.fixture
    def aggregator(self, collector: InMemoryAnalyticsCollector) -> AnalyticsAggregator:
        """Create an analytics aggregator."""
        return AnalyticsAggregator(collector)

    async def _create_events(
        self,
        collector: InMemoryAnalyticsCollector,
        flag_key: str,
        count: int,
        *,
        reason: EvaluationReason = EvaluationReason.STATIC,
        variant: str | None = None,
        targeting_key_prefix: str = "user",
        duration_ms: float = 1.0,
        time_offset: timedelta = timedelta(0),
    ) -> None:
        """Helper to create and record test events."""
        for i in range(count):
            event = FlagEvaluationEvent(
                timestamp=datetime.now(UTC) - time_offset,
                flag_key=flag_key,
                value=True,
                reason=reason,
                variant=variant,
                targeting_key=f"{targeting_key_prefix}-{i}",
                evaluation_duration_ms=duration_ms,
            )
            await collector.record(event)

    async def test_get_evaluation_rate_with_known_events(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test get_evaluation_rate() with a known number of events."""
        # Record 60 events in the last 60 seconds
        await self._create_events(collector, "test-flag", 60)

        rate = await aggregator.get_evaluation_rate("test-flag", window_seconds=60)

        # Should be 60 events / 60 seconds = 1.0 events/second
        assert rate == 1.0

    async def test_get_evaluation_rate_empty(self, aggregator: AnalyticsAggregator) -> None:
        """Test get_evaluation_rate() with no events."""
        rate = await aggregator.get_evaluation_rate("nonexistent-flag")

        assert rate == 0.0

    async def test_get_evaluation_rate_with_zero_window(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test get_evaluation_rate() with zero window returns 0."""
        await self._create_events(collector, "test-flag", 10)

        rate = await aggregator.get_evaluation_rate("test-flag", window_seconds=0)

        assert rate == 0.0

    async def test_get_unique_users_counting(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test get_unique_users() counts unique targeting keys."""
        # Create events with unique targeting keys
        await self._create_events(collector, "test-flag", 10, targeting_key_prefix="user")

        count = await aggregator.get_unique_users("test-flag")

        assert count == 10

    async def test_get_unique_users_with_duplicates(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test get_unique_users() handles duplicate targeting keys."""
        # Create events with some duplicate targeting keys
        for i in range(20):
            event = FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key="test-flag",
                value=True,
                reason=EvaluationReason.STATIC,
                targeting_key=f"user-{i % 5}",  # Only 5 unique keys
            )
            await collector.record(event)

        count = await aggregator.get_unique_users("test-flag")

        assert count == 5

    async def test_get_unique_users_ignores_none_keys(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test get_unique_users() ignores events with None targeting_key."""
        # Create some events with targeting_key and some without
        for i in range(10):
            event = FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key="test-flag",
                value=True,
                reason=EvaluationReason.STATIC,
                targeting_key=f"user-{i}" if i < 5 else None,
            )
            await collector.record(event)

        count = await aggregator.get_unique_users("test-flag")

        assert count == 5

    async def test_get_variant_distribution(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test get_variant_distribution() returns correct counts."""
        # Create events with different variants
        for variant, count in [("control", 30), ("treatment", 50), ("variant-c", 20)]:
            for i in range(count):
                event = FlagEvaluationEvent(
                    timestamp=datetime.now(UTC),
                    flag_key="test-flag",
                    value=True,
                    reason=EvaluationReason.SPLIT,
                    variant=variant,
                    targeting_key=f"user-{variant}-{i}",
                )
                await collector.record(event)

        distribution = await aggregator.get_variant_distribution("test-flag")

        assert distribution == {"control": 30, "treatment": 50, "variant-c": 20}

    async def test_get_variant_distribution_with_default(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test get_variant_distribution() counts None variants as 'default'."""
        for i in range(10):
            event = FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key="test-flag",
                value=True,
                reason=EvaluationReason.STATIC,
                variant=None,
                targeting_key=f"user-{i}",
            )
            await collector.record(event)

        distribution = await aggregator.get_variant_distribution("test-flag")

        assert distribution == {"default": 10}

    async def test_get_reason_distribution(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test get_reason_distribution() returns correct counts."""
        reasons = [
            (EvaluationReason.STATIC, 40),
            (EvaluationReason.TARGETING_MATCH, 30),
            (EvaluationReason.SPLIT, 20),
            (EvaluationReason.OVERRIDE, 10),
        ]

        for reason, count in reasons:
            for i in range(count):
                event = FlagEvaluationEvent(
                    timestamp=datetime.now(UTC),
                    flag_key="test-flag",
                    value=True,
                    reason=reason,
                    targeting_key=f"user-{reason.value}-{i}",
                )
                await collector.record(event)

        distribution = await aggregator.get_reason_distribution("test-flag")

        assert distribution == {
            "STATIC": 40,
            "TARGETING_MATCH": 30,
            "SPLIT": 20,
            "OVERRIDE": 10,
        }

    async def test_get_error_rate_calculation(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test get_error_rate() calculates percentage correctly."""
        # Create 80 success events and 20 error events
        for i in range(80):
            event = FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key="test-flag",
                value=True,
                reason=EvaluationReason.STATIC,
                targeting_key=f"user-success-{i}",
            )
            await collector.record(event)

        for i in range(20):
            event = FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key="test-flag",
                value=None,
                reason=EvaluationReason.ERROR,
                targeting_key=f"user-error-{i}",
            )
            await collector.record(event)

        error_rate = await aggregator.get_error_rate("test-flag")

        # 20 errors out of 100 total = 20%
        assert error_rate == 20.0

    async def test_get_error_rate_no_errors(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test get_error_rate() with no errors."""
        await self._create_events(collector, "test-flag", 50)

        error_rate = await aggregator.get_error_rate("test-flag")

        assert error_rate == 0.0

    async def test_get_error_rate_all_errors(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test get_error_rate() when all events are errors."""
        await self._create_events(collector, "test-flag", 10, reason=EvaluationReason.ERROR)

        error_rate = await aggregator.get_error_rate("test-flag")

        assert error_rate == 100.0

    async def test_get_error_rate_empty(self, aggregator: AnalyticsAggregator) -> None:
        """Test get_error_rate() with no events."""
        error_rate = await aggregator.get_error_rate("nonexistent-flag")

        assert error_rate == 0.0

    async def test_get_latency_percentiles(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test get_latency_percentiles() calculates correct percentiles."""
        # Create events with known latencies (1ms to 100ms)
        for i in range(100):
            event = FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key="test-flag",
                value=True,
                reason=EvaluationReason.STATIC,
                targeting_key=f"user-{i}",
                evaluation_duration_ms=float(i + 1),  # 1 to 100
            )
            await collector.record(event)

        percentiles = await aggregator.get_latency_percentiles("test-flag")

        # With 100 evenly distributed values (1-100):
        # p50 should be around 50.5
        # p90 should be around 90.1
        # p99 should be around 99.01
        assert 49.0 <= percentiles[50.0] <= 52.0
        assert 89.0 <= percentiles[90.0] <= 92.0
        assert 98.0 <= percentiles[99.0] <= 100.0

    async def test_get_latency_percentiles_custom_percentiles(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test get_latency_percentiles() with custom percentile values."""
        for i in range(100):
            event = FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key="test-flag",
                value=True,
                reason=EvaluationReason.STATIC,
                targeting_key=f"user-{i}",
                evaluation_duration_ms=float(i + 1),
            )
            await collector.record(event)

        percentiles = await aggregator.get_latency_percentiles(
            "test-flag",
            percentiles=[25.0, 75.0, 95.0],
        )

        assert 25.0 in percentiles
        assert 75.0 in percentiles
        assert 95.0 in percentiles

    async def test_get_latency_percentiles_empty(self, aggregator: AnalyticsAggregator) -> None:
        """Test get_latency_percentiles() with no events."""
        percentiles = await aggregator.get_latency_percentiles("nonexistent-flag")

        assert percentiles == {50.0: 0.0, 90.0: 0.0, 99.0: 0.0}

    async def test_get_latency_percentiles_single_event(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test get_latency_percentiles() with a single event."""
        event = FlagEvaluationEvent(
            timestamp=datetime.now(UTC),
            flag_key="test-flag",
            value=True,
            reason=EvaluationReason.STATIC,
            targeting_key="user-1",
            evaluation_duration_ms=5.0,
        )
        await collector.record(event)

        percentiles = await aggregator.get_latency_percentiles("test-flag")

        # With a single data point, all percentiles should be that value
        assert percentiles[50.0] == 5.0
        assert percentiles[90.0] == 5.0
        assert percentiles[99.0] == 5.0

    async def test_get_flag_metrics_returns_complete_metrics(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test get_flag_metrics() returns all metrics."""
        # Create diverse events
        for i in range(50):
            variant = "control" if i < 25 else "treatment"
            reason = EvaluationReason.SPLIT if i < 45 else EvaluationReason.ERROR
            event = FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key="test-flag",
                value=True,
                reason=reason,
                variant=variant,
                targeting_key=f"user-{i}",
                evaluation_duration_ms=float(i + 1),
            )
            await collector.record(event)

        metrics = await aggregator.get_flag_metrics("test-flag", window_seconds=3600)

        # Verify all metrics are present
        assert isinstance(metrics, FlagMetrics)
        assert metrics.total_evaluations == 50
        assert metrics.unique_users == 50
        assert metrics.evaluation_rate > 0
        assert "control" in metrics.variant_distribution
        assert "treatment" in metrics.variant_distribution
        assert "SPLIT" in metrics.reason_distribution
        assert "ERROR" in metrics.reason_distribution
        assert metrics.error_rate == 10.0  # 5 errors out of 50
        assert metrics.latency_p50 > 0
        assert metrics.latency_p90 > 0
        assert metrics.latency_p99 > 0
        assert metrics.window_start is not None
        assert metrics.window_end is not None

    async def test_get_flag_metrics_empty(self, aggregator: AnalyticsAggregator) -> None:
        """Test get_flag_metrics() with no events."""
        metrics = await aggregator.get_flag_metrics("nonexistent-flag")

        assert metrics.total_evaluations == 0
        assert metrics.unique_users == 0
        assert metrics.evaluation_rate == 0.0
        assert metrics.variant_distribution == {}
        assert metrics.reason_distribution == {}
        assert metrics.error_rate == 0.0
        assert metrics.latency_p50 == 0.0
        assert metrics.latency_p90 == 0.0
        assert metrics.latency_p99 == 0.0
        assert metrics.window_start is not None
        assert metrics.window_end is not None

    async def test_window_filtering_only_recent_events(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test that aggregator only counts events within the window."""
        now = datetime.now(UTC)

        # Create events at different times
        # 5 events from 30 seconds ago (within 60s window)
        for i in range(5):
            event = FlagEvaluationEvent(
                timestamp=now - timedelta(seconds=30),
                flag_key="test-flag",
                value=True,
                reason=EvaluationReason.STATIC,
                targeting_key=f"recent-user-{i}",
            )
            await collector.record(event)

        # 5 events from 2 hours ago (outside 60s window)
        for i in range(5):
            event = FlagEvaluationEvent(
                timestamp=now - timedelta(hours=2),
                flag_key="test-flag",
                value=True,
                reason=EvaluationReason.STATIC,
                targeting_key=f"old-user-{i}",
            )
            await collector.record(event)

        # With 60 second window, only the 5 recent events should be counted
        rate = await aggregator.get_evaluation_rate("test-flag", window_seconds=60)

        # Should only count the 5 recent events
        assert rate == 5 / 60  # 5 events in 60 seconds

    async def test_flag_metrics_to_dict(
        self, collector: InMemoryAnalyticsCollector, aggregator: AnalyticsAggregator
    ) -> None:
        """Test FlagMetrics.to_dict() serialization."""
        await self._create_events(collector, "test-flag", 10)

        metrics = await aggregator.get_flag_metrics("test-flag")
        metrics_dict = metrics.to_dict()

        assert "evaluation_rate" in metrics_dict
        assert "unique_users" in metrics_dict
        assert "variant_distribution" in metrics_dict
        assert "reason_distribution" in metrics_dict
        assert "error_rate" in metrics_dict
        assert "latency_p50" in metrics_dict
        assert "latency_p90" in metrics_dict
        assert "latency_p99" in metrics_dict
        assert "total_evaluations" in metrics_dict
        assert "window_start" in metrics_dict
        assert "window_end" in metrics_dict


# -----------------------------------------------------------------------------
# EvaluationEngine Analytics Integration Tests
# -----------------------------------------------------------------------------
class TestEvaluationEngineAnalytics:
    """Tests for EvaluationEngine analytics integration."""

    @pytest.fixture
    def collector(self) -> InMemoryAnalyticsCollector:
        """Create an in-memory analytics collector."""
        return InMemoryAnalyticsCollector(max_size=1000)

    @pytest.fixture
    def storage(self) -> None:
        """Create a memory storage backend."""
        from litestar_flags import MemoryStorageBackend

        return MemoryStorageBackend()

    def test_engine_accepts_analytics_collector(self, collector: InMemoryAnalyticsCollector) -> None:
        """Test that EvaluationEngine accepts an analytics_collector."""
        from litestar_flags.engine import EvaluationEngine

        engine = EvaluationEngine(analytics_collector=collector)

        assert engine.analytics_collector is collector

    def test_engine_analytics_collector_setter(self, collector: InMemoryAnalyticsCollector) -> None:
        """Test that analytics_collector can be set after construction."""
        from litestar_flags.engine import EvaluationEngine

        engine = EvaluationEngine()
        assert engine.analytics_collector is None

        engine.analytics_collector = collector
        assert engine.analytics_collector is collector

    def test_engine_analytics_collector_can_be_none(self) -> None:
        """Test that analytics_collector can be None."""
        from litestar_flags.engine import EvaluationEngine

        engine = EvaluationEngine(analytics_collector=None)

        assert engine.analytics_collector is None

    async def test_evaluation_does_not_fail_without_collector(self, storage) -> None:
        """Test that evaluation works without an analytics collector."""
        from litestar_flags import EvaluationContext
        from litestar_flags.engine import EvaluationEngine
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.types import FlagStatus, FlagType

        engine = EvaluationEngine(analytics_collector=None)

        flag = FeatureFlag(
            id=uuid4(),
            key="test-flag",
            name="Test Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        context = EvaluationContext()

        # Should not raise
        result = await engine.evaluate(flag, context, storage)

        assert result.value is True

    async def test_evaluation_with_collector_does_not_fail(
        self, collector: InMemoryAnalyticsCollector, storage
    ) -> None:
        """Test that evaluation works with an analytics collector."""
        from litestar_flags import EvaluationContext
        from litestar_flags.engine import EvaluationEngine
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.types import FlagStatus, FlagType

        engine = EvaluationEngine(analytics_collector=collector)

        flag = FeatureFlag(
            id=uuid4(),
            key="test-flag",
            name="Test Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        context = EvaluationContext(targeting_key="user-123")

        # Should not raise
        result = await engine.evaluate(flag, context, storage)

        assert result.value is True

    async def test_collector_can_be_replaced(self, collector: InMemoryAnalyticsCollector) -> None:
        """Test that the collector can be replaced dynamically."""
        from litestar_flags.engine import EvaluationEngine

        engine = EvaluationEngine()

        # Start without collector
        assert engine.analytics_collector is None

        # Add collector
        engine.analytics_collector = collector
        assert engine.analytics_collector is collector

        # Replace with different collector
        new_collector = InMemoryAnalyticsCollector(max_size=500)
        engine.analytics_collector = new_collector
        assert engine.analytics_collector is new_collector

        # Remove collector
        engine.analytics_collector = None
        assert engine.analytics_collector is None


# -----------------------------------------------------------------------------
# AnalyticsCollector Protocol Tests
# -----------------------------------------------------------------------------
class TestAnalyticsCollectorProtocol:
    """Tests for AnalyticsCollector protocol compliance."""

    def test_in_memory_collector_implements_protocol(self) -> None:
        """Test that InMemoryAnalyticsCollector implements the protocol."""
        from litestar_flags.analytics.protocols import AnalyticsCollector

        collector = InMemoryAnalyticsCollector()

        # Should be an instance of the protocol
        assert isinstance(collector, AnalyticsCollector)

    async def test_protocol_method_signatures(self) -> None:
        """Test that protocol methods have correct signatures."""

        collector = InMemoryAnalyticsCollector()

        # Test record method
        event = FlagEvaluationEvent(
            timestamp=datetime.now(UTC),
            flag_key="test",
            value=True,
            reason=EvaluationReason.STATIC,
        )
        result = await collector.record(event)
        assert result is None  # record returns None

        # Test flush method
        result = await collector.flush()
        assert result is None  # flush returns None

        # Test close method
        result = await collector.close()
        assert result is None  # close returns None


# -----------------------------------------------------------------------------
# Edge Cases and Error Handling Tests
# -----------------------------------------------------------------------------
class TestAnalyticsEdgeCases:
    """Tests for edge cases and error handling in analytics."""

    async def test_very_large_latency_values(self) -> None:
        """Test handling of very large latency values."""
        collector = InMemoryAnalyticsCollector()
        aggregator = AnalyticsAggregator(collector)

        event = FlagEvaluationEvent(
            timestamp=datetime.now(UTC),
            flag_key="test-flag",
            value=True,
            reason=EvaluationReason.STATIC,
            evaluation_duration_ms=1000000.0,  # 1000 seconds
        )
        await collector.record(event)

        percentiles = await aggregator.get_latency_percentiles("test-flag")

        assert percentiles[50.0] == 1000000.0

    async def test_zero_latency_values(self) -> None:
        """Test handling of zero latency values."""
        collector = InMemoryAnalyticsCollector()
        aggregator = AnalyticsAggregator(collector)

        # Record events with zero latency (should be filtered out in percentile calc)
        for _ in range(10):
            event = FlagEvaluationEvent(
                timestamp=datetime.now(UTC),
                flag_key="test-flag",
                value=True,
                reason=EvaluationReason.STATIC,
                evaluation_duration_ms=0.0,
            )
            await collector.record(event)

        percentiles = await aggregator.get_latency_percentiles("test-flag")

        # With no positive latencies, should return 0
        assert percentiles[50.0] == 0.0

    async def test_negative_latency_values_ignored(self) -> None:
        """Test that negative latency values are ignored in calculations."""
        collector = InMemoryAnalyticsCollector()
        aggregator = AnalyticsAggregator(collector)

        # Record events with negative latency (should be filtered out)
        event_negative = FlagEvaluationEvent(
            timestamp=datetime.now(UTC),
            flag_key="test-flag",
            value=True,
            reason=EvaluationReason.STATIC,
            evaluation_duration_ms=-1.0,
        )
        await collector.record(event_negative)

        # Record one valid event
        event_positive = FlagEvaluationEvent(
            timestamp=datetime.now(UTC),
            flag_key="test-flag",
            value=True,
            reason=EvaluationReason.STATIC,
            evaluation_duration_ms=5.0,
        )
        await collector.record(event_positive)

        percentiles = await aggregator.get_latency_percentiles("test-flag")

        # Should only consider the positive latency
        assert percentiles[50.0] == 5.0

    async def test_empty_flag_key(self) -> None:
        """Test handling of empty flag key."""
        collector = InMemoryAnalyticsCollector()

        event = FlagEvaluationEvent(
            timestamp=datetime.now(UTC),
            flag_key="",  # Empty key
            value=True,
            reason=EvaluationReason.STATIC,
        )
        await collector.record(event)

        events = await collector.get_events(flag_key="")
        assert len(events) == 1

    async def test_special_characters_in_flag_key(self) -> None:
        """Test handling of special characters in flag key."""
        collector = InMemoryAnalyticsCollector()

        special_key = "flag:with/special$chars!@#"
        event = FlagEvaluationEvent(
            timestamp=datetime.now(UTC),
            flag_key=special_key,
            value=True,
            reason=EvaluationReason.STATIC,
        )
        await collector.record(event)

        events = await collector.get_events(flag_key=special_key)
        assert len(events) == 1
        assert events[0].flag_key == special_key

    async def test_unicode_in_context_attributes(self) -> None:
        """Test handling of unicode in context attributes."""
        collector = InMemoryAnalyticsCollector()

        event = FlagEvaluationEvent(
            timestamp=datetime.now(UTC),
            flag_key="test-flag",
            value=True,
            reason=EvaluationReason.STATIC,
            context_attributes={"name": "Test", "city": "Tokyo"},
        )
        await collector.record(event)

        events = await collector.get_events()
        assert events[0].context_attributes["city"] == "Tokyo"

    async def test_large_context_attributes(self) -> None:
        """Test handling of large context attributes."""
        collector = InMemoryAnalyticsCollector()

        large_attrs = {f"key_{i}": f"value_{i}" * 100 for i in range(100)}
        event = FlagEvaluationEvent(
            timestamp=datetime.now(UTC),
            flag_key="test-flag",
            value=True,
            reason=EvaluationReason.STATIC,
            context_attributes=large_attrs,
        )
        await collector.record(event)

        events = await collector.get_events()
        assert len(events[0].context_attributes) == 100
