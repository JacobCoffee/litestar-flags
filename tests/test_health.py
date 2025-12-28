"""Tests for health check functionality."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from litestar_flags import MemoryStorageBackend
from litestar_flags.health import (
    CacheStats,
    HealthCheckResult,
    HealthStatus,
    health_check,
)
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.types import FlagStatus, FlagType


# -----------------------------------------------------------------------------
# HealthStatus Enum Tests
# -----------------------------------------------------------------------------
class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_health_status_values(self) -> None:
        """Test HealthStatus enum values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"

    def test_health_status_is_string_enum(self) -> None:
        """Test that HealthStatus inherits from str."""
        assert isinstance(HealthStatus.HEALTHY, str)
        assert isinstance(HealthStatus.DEGRADED, str)
        assert isinstance(HealthStatus.UNHEALTHY, str)

    def test_health_status_string_comparison(self) -> None:
        """Test HealthStatus can be compared to strings."""
        assert HealthStatus.HEALTHY == "healthy"
        assert HealthStatus.DEGRADED == "degraded"
        assert HealthStatus.UNHEALTHY == "unhealthy"

    def test_health_status_membership(self) -> None:
        """Test all expected statuses are present."""
        statuses = list(HealthStatus)
        assert len(statuses) == 3
        assert HealthStatus.HEALTHY in statuses
        assert HealthStatus.DEGRADED in statuses
        assert HealthStatus.UNHEALTHY in statuses


# -----------------------------------------------------------------------------
# CacheStats Tests
# -----------------------------------------------------------------------------
class TestCacheStats:
    """Tests for CacheStats dataclass."""

    def test_cache_stats_defaults(self) -> None:
        """Test CacheStats default values."""
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.hit_rate == 0.0
        assert stats.size == 0
        assert stats.max_size is None

    def test_cache_stats_custom_values(self) -> None:
        """Test CacheStats with custom values."""
        stats = CacheStats(
            hits=100,
            misses=20,
            hit_rate=83.33,
            size=50,
            max_size=100,
        )
        assert stats.hits == 100
        assert stats.misses == 20
        assert stats.hit_rate == 83.33
        assert stats.size == 50
        assert stats.max_size == 100

    def test_cache_stats_without_max_size(self) -> None:
        """Test CacheStats without max_size specified."""
        stats = CacheStats(hits=10, misses=5, hit_rate=66.67, size=15)
        assert stats.max_size is None


# -----------------------------------------------------------------------------
# HealthCheckResult Tests
# -----------------------------------------------------------------------------
class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""

    def test_health_check_result_minimal(self) -> None:
        """Test HealthCheckResult with minimal required fields."""
        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            storage_connected=True,
        )
        assert result.status == HealthStatus.HEALTHY
        assert result.storage_connected is True
        assert result.cache_connected is None
        assert result.flag_count == 0
        assert result.cache_stats is None
        assert result.latency_ms == 0.0
        assert result.details == {}

    def test_health_check_result_full(self) -> None:
        """Test HealthCheckResult with all fields populated."""
        cache_stats = CacheStats(hits=100, misses=10, hit_rate=90.9, size=50)
        timestamp = datetime.now(UTC)
        result = HealthCheckResult(
            status=HealthStatus.DEGRADED,
            storage_connected=True,
            cache_connected=True,
            flag_count=25,
            cache_stats=cache_stats,
            latency_ms=15.5,
            timestamp=timestamp,
            details={"warning": "High latency detected"},
        )
        assert result.status == HealthStatus.DEGRADED
        assert result.storage_connected is True
        assert result.cache_connected is True
        assert result.flag_count == 25
        assert result.cache_stats == cache_stats
        assert result.latency_ms == 15.5
        assert result.timestamp == timestamp
        assert result.details == {"warning": "High latency detected"}

    def test_health_check_result_timestamp_default(self) -> None:
        """Test that timestamp defaults to current UTC time."""
        before = datetime.now(UTC)
        result = HealthCheckResult(status=HealthStatus.HEALTHY, storage_connected=True)
        after = datetime.now(UTC)
        assert before <= result.timestamp <= after


class TestHealthCheckResultToDict:
    """Tests for HealthCheckResult.to_dict() method."""

    def test_to_dict_minimal(self) -> None:
        """Test to_dict with minimal fields."""
        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            storage_connected=True,
            latency_ms=5.123,
        )
        result_dict = result.to_dict()

        assert result_dict["status"] == "healthy"
        assert result_dict["storage_connected"] is True
        assert result_dict["flag_count"] == 0
        assert result_dict["latency_ms"] == 5.12  # rounded to 2 decimal places
        assert "timestamp" in result_dict
        assert "cache_connected" not in result_dict  # None values excluded
        assert "cache_stats" not in result_dict
        assert "details" not in result_dict  # Empty dict excluded

    def test_to_dict_with_cache_connected(self) -> None:
        """Test to_dict includes cache_connected when not None."""
        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            storage_connected=True,
            cache_connected=True,
        )
        result_dict = result.to_dict()
        assert result_dict["cache_connected"] is True

        result_false = HealthCheckResult(
            status=HealthStatus.DEGRADED,
            storage_connected=True,
            cache_connected=False,
        )
        result_dict_false = result_false.to_dict()
        assert result_dict_false["cache_connected"] is False

    def test_to_dict_with_cache_stats(self) -> None:
        """Test to_dict includes cache_stats when present."""
        cache_stats = CacheStats(
            hits=150,
            misses=30,
            hit_rate=83.333,
            size=100,
            max_size=500,
        )
        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            storage_connected=True,
            cache_stats=cache_stats,
        )
        result_dict = result.to_dict()

        assert "cache_stats" in result_dict
        assert result_dict["cache_stats"]["hits"] == 150
        assert result_dict["cache_stats"]["misses"] == 30
        assert result_dict["cache_stats"]["hit_rate"] == 83.33  # rounded
        assert result_dict["cache_stats"]["size"] == 100
        assert result_dict["cache_stats"]["max_size"] == 500

    def test_to_dict_cache_stats_without_max_size(self) -> None:
        """Test to_dict excludes max_size when None."""
        cache_stats = CacheStats(hits=10, misses=5, hit_rate=66.67, size=15)
        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            storage_connected=True,
            cache_stats=cache_stats,
        )
        result_dict = result.to_dict()

        assert "cache_stats" in result_dict
        assert "max_size" not in result_dict["cache_stats"]

    def test_to_dict_with_details(self) -> None:
        """Test to_dict includes details when non-empty."""
        result = HealthCheckResult(
            status=HealthStatus.DEGRADED,
            storage_connected=True,
            details={"issues": ["High latency"], "storage_error": "Connection timeout"},
        )
        result_dict = result.to_dict()

        assert "details" in result_dict
        assert result_dict["details"]["issues"] == ["High latency"]
        assert result_dict["details"]["storage_error"] == "Connection timeout"

    def test_to_dict_timestamp_format(self) -> None:
        """Test to_dict formats timestamp as ISO string."""
        timestamp = datetime(2024, 1, 15, 12, 30, 45, tzinfo=UTC)
        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            storage_connected=True,
            timestamp=timestamp,
        )
        result_dict = result.to_dict()

        assert result_dict["timestamp"] == timestamp.isoformat()

    def test_to_dict_latency_rounding(self) -> None:
        """Test to_dict rounds latency to 2 decimal places."""
        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            storage_connected=True,
            latency_ms=12.3456789,
        )
        result_dict = result.to_dict()
        assert result_dict["latency_ms"] == 12.35


# -----------------------------------------------------------------------------
# health_check Function Tests
# -----------------------------------------------------------------------------
class TestHealthCheckFunction:
    """Tests for the health_check function."""

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        """Create a fresh memory storage backend."""
        return MemoryStorageBackend()

    @pytest.fixture
    def sample_flag(self) -> FeatureFlag:
        """Create a sample active flag."""
        return FeatureFlag(
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

    async def test_health_check_healthy_storage(self, storage: MemoryStorageBackend) -> None:
        """Test health check with healthy storage backend."""
        result = await health_check(storage)

        assert result.status == HealthStatus.HEALTHY
        assert result.storage_connected is True
        assert result.flag_count == 0
        assert result.latency_ms > 0
        assert result.details.get("active_flags") == 0

    async def test_health_check_with_flags(self, storage: MemoryStorageBackend, sample_flag: FeatureFlag) -> None:
        """Test health check counts active flags."""
        await storage.create_flag(sample_flag)

        # Create another active flag
        flag2 = FeatureFlag(
            id=uuid4(),
            key="flag-2",
            name="Flag 2",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        await storage.create_flag(flag2)

        # Create an inactive flag (should not be counted)
        inactive_flag = FeatureFlag(
            id=uuid4(),
            key="inactive-flag",
            name="Inactive Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.INACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        await storage.create_flag(inactive_flag)

        result = await health_check(storage)

        assert result.status == HealthStatus.HEALTHY
        assert result.flag_count == 2  # Only active flags
        assert result.details.get("active_flags") == 2

    async def test_health_check_skip_flag_count(self, storage: MemoryStorageBackend, sample_flag: FeatureFlag) -> None:
        """Test health check without flag counting."""
        await storage.create_flag(sample_flag)

        result = await health_check(storage, include_flag_count=False)

        assert result.status == HealthStatus.HEALTHY
        assert result.flag_count == 0
        assert "active_flags" not in result.details

    async def test_health_check_storage_failure(self) -> None:
        """Test health check when storage health_check returns False."""
        mock_storage = AsyncMock()
        mock_storage.health_check.return_value = False

        result = await health_check(mock_storage)

        assert result.status == HealthStatus.UNHEALTHY
        assert result.storage_connected is False
        assert "storage_error" in result.details
        assert "issues" in result.details
        assert any("False" in issue for issue in result.details["issues"])

    async def test_health_check_storage_exception(self) -> None:
        """Test health check when storage raises an exception."""
        mock_storage = AsyncMock()
        mock_storage.health_check.side_effect = ConnectionError("Database connection failed")

        result = await health_check(mock_storage)

        assert result.status == HealthStatus.UNHEALTHY
        assert result.storage_connected is False
        assert "storage_error" in result.details
        assert "Database connection failed" in result.details["storage_error"]
        assert "issues" in result.details

    async def test_health_check_flag_count_exception(self) -> None:
        """Test health check when get_all_active_flags raises an exception."""
        mock_storage = AsyncMock()
        mock_storage.health_check.return_value = True
        mock_storage.get_all_active_flags.side_effect = RuntimeError("Query timeout")

        result = await health_check(mock_storage)

        # Status should be degraded (storage is connected but flag count failed)
        assert result.status == HealthStatus.DEGRADED
        assert result.storage_connected is True
        assert result.flag_count == 0
        assert "flag_count_error" in result.details
        assert "Query timeout" in result.details["flag_count_error"]

    async def test_health_check_with_cache_stats(self) -> None:
        """Test health check with cache statistics available."""
        mock_storage = AsyncMock()
        mock_storage.health_check.return_value = True
        mock_storage.get_all_active_flags.return_value = []
        mock_storage.get_cache_stats = AsyncMock(
            return_value={
                "hits": 500,
                "misses": 100,
                "hit_rate": 83.33,
                "size": 250,
                "max_size": 1000,
            }
        )

        result = await health_check(mock_storage)

        assert result.status == HealthStatus.HEALTHY
        assert result.cache_connected is True
        assert result.cache_stats is not None
        assert result.cache_stats.hits == 500
        assert result.cache_stats.misses == 100
        assert result.cache_stats.hit_rate == 83.33
        assert result.cache_stats.size == 250
        assert result.cache_stats.max_size == 1000

    async def test_health_check_cache_stats_exception(self) -> None:
        """Test health check when get_cache_stats raises an exception."""
        mock_storage = AsyncMock()
        mock_storage.health_check.return_value = True
        mock_storage.get_all_active_flags.return_value = []
        mock_storage.get_cache_stats = AsyncMock(side_effect=RuntimeError("Cache unavailable"))

        result = await health_check(mock_storage)

        # Status should be degraded (cache issue but storage works)
        assert result.status == HealthStatus.DEGRADED
        assert result.storage_connected is True
        assert result.cache_connected is False
        assert result.cache_stats is None
        assert "cache_error" in result.details
        assert "Cache unavailable" in result.details["cache_error"]

    async def test_health_check_skip_cache_stats(self) -> None:
        """Test health check without cache statistics."""
        mock_storage = AsyncMock()
        mock_storage.health_check.return_value = True
        mock_storage.get_all_active_flags.return_value = []
        mock_storage.get_cache_stats = AsyncMock(return_value={"hits": 100, "misses": 10})

        result = await health_check(mock_storage, include_cache_stats=False)

        assert result.status == HealthStatus.HEALTHY
        assert result.cache_connected is None
        assert result.cache_stats is None
        mock_storage.get_cache_stats.assert_not_called()

    async def test_health_check_no_cache_stats_method(self, storage: MemoryStorageBackend) -> None:
        """Test health check when storage doesn't have get_cache_stats method."""
        # MemoryStorageBackend doesn't have get_cache_stats
        result = await health_check(storage)

        assert result.status == HealthStatus.HEALTHY
        assert result.cache_connected is None
        assert result.cache_stats is None

    async def test_health_check_empty_cache_stats(self) -> None:
        """Test health check when get_cache_stats returns empty/None."""
        mock_storage = AsyncMock()
        mock_storage.health_check.return_value = True
        mock_storage.get_all_active_flags.return_value = []
        mock_storage.get_cache_stats = AsyncMock(return_value=None)

        result = await health_check(mock_storage)

        assert result.status == HealthStatus.HEALTHY
        assert result.cache_connected is None  # Not set when stats are None
        assert result.cache_stats is None

    async def test_health_check_cache_stats_partial(self) -> None:
        """Test health check with partial cache statistics."""
        mock_storage = AsyncMock()
        mock_storage.health_check.return_value = True
        mock_storage.get_all_active_flags.return_value = []
        mock_storage.get_cache_stats = AsyncMock(
            return_value={
                "hits": 50,
                # Missing other fields - should use defaults
            }
        )

        result = await health_check(mock_storage)

        assert result.cache_connected is True
        assert result.cache_stats is not None
        assert result.cache_stats.hits == 50
        assert result.cache_stats.misses == 0  # default
        assert result.cache_stats.hit_rate == 0.0  # default
        assert result.cache_stats.size == 0  # default
        assert result.cache_stats.max_size is None  # default

    async def test_health_check_latency_measurement(self, storage: MemoryStorageBackend) -> None:
        """Test that latency is accurately measured."""
        result = await health_check(storage)

        # Latency should be positive and reasonable
        assert result.latency_ms > 0
        assert result.latency_ms < 1000  # Should be well under 1 second

    async def test_health_check_timestamp_set(self, storage: MemoryStorageBackend) -> None:
        """Test that timestamp is set during health check."""
        before = datetime.now(UTC)
        result = await health_check(storage)
        after = datetime.now(UTC)

        assert before <= result.timestamp <= after

    async def test_health_check_multiple_issues(self) -> None:
        """Test health check captures multiple issues."""
        mock_storage = AsyncMock()
        mock_storage.health_check.return_value = True
        mock_storage.get_all_active_flags.side_effect = RuntimeError("Flag query failed")
        mock_storage.get_cache_stats = AsyncMock(side_effect=RuntimeError("Cache query failed"))

        result = await health_check(mock_storage)

        assert result.status == HealthStatus.DEGRADED
        assert "issues" in result.details
        assert len(result.details["issues"]) == 2  # Both flag count and cache errors

    async def test_health_check_storage_disconnected_skips_flag_count(self) -> None:
        """Test that flag counting is skipped when storage is disconnected."""
        mock_storage = AsyncMock()
        mock_storage.health_check.return_value = False

        result = await health_check(mock_storage)

        assert result.status == HealthStatus.UNHEALTHY
        assert result.storage_connected is False
        assert result.flag_count == 0
        # get_all_active_flags should not be called when storage is disconnected
        mock_storage.get_all_active_flags.assert_not_called()


class TestHealthCheckEdgeCases:
    """Edge case tests for health_check function."""

    async def test_health_check_with_many_flags(self) -> None:
        """Test health check performance with many flags."""
        storage = MemoryStorageBackend()

        # Create 100 flags
        for i in range(100):
            flag = FeatureFlag(
                id=uuid4(),
                key=f"flag-{i}",
                name=f"Flag {i}",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=i % 2 == 0,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
            await storage.create_flag(flag)

        result = await health_check(storage)

        assert result.status == HealthStatus.HEALTHY
        assert result.flag_count == 100

    async def test_health_check_concurrent_calls(self) -> None:
        """Test that concurrent health checks work correctly."""
        import asyncio

        storage = MemoryStorageBackend()

        # Run multiple health checks concurrently
        results = await asyncio.gather(
            health_check(storage),
            health_check(storage),
            health_check(storage),
        )

        assert len(results) == 3
        for result in results:
            assert result.status == HealthStatus.HEALTHY
            assert result.storage_connected is True

    async def test_health_check_result_serialization(self) -> None:
        """Test that health check result can be serialized to JSON."""
        import json

        storage = MemoryStorageBackend()
        result = await health_check(storage)

        # to_dict should produce JSON-serializable output
        result_dict = result.to_dict()
        json_str = json.dumps(result_dict)

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["status"] == "healthy"
        assert parsed["storage_connected"] is True

    async def test_health_check_all_options_disabled(self) -> None:
        """Test health check with all optional features disabled."""
        mock_storage = AsyncMock()
        mock_storage.health_check.return_value = True
        mock_storage.get_cache_stats = AsyncMock(return_value={"hits": 100})

        result = await health_check(
            mock_storage,
            include_flag_count=False,
            include_cache_stats=False,
        )

        assert result.status == HealthStatus.HEALTHY
        assert result.flag_count == 0
        assert result.cache_stats is None
        mock_storage.get_all_active_flags.assert_not_called()
        mock_storage.get_cache_stats.assert_not_called()

    async def test_health_check_details_accumulation(self) -> None:
        """Test that details dictionary accumulates information correctly."""
        mock_storage = AsyncMock()
        mock_storage.health_check.return_value = True

        flags = [
            FeatureFlag(
                id=uuid4(),
                key="flag-1",
                name="Flag 1",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
        ]
        mock_storage.get_all_active_flags.return_value = flags
        mock_storage.get_cache_stats = AsyncMock(return_value={"hits": 10, "misses": 5})

        result = await health_check(mock_storage)

        assert "active_flags" in result.details
        assert result.details["active_flags"] == 1
        # No errors, so no issues key
        assert "issues" not in result.details
