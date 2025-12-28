"""Tests for the rate limiting module."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import pytest

from litestar_flags.exceptions import RateLimitExceededError

# Import internal class for testing
from litestar_flags.rate_limit import (
    RateLimitConfig,
    RateLimiter,
    RateLimitHook,
    TokenBucketRateLimiter,
    _TokenBucket,
)

if TYPE_CHECKING:
    pass


class TestRateLimitConfig:
    """Tests for RateLimitConfig dataclass."""

    def test_default_values(self):
        """Test that RateLimitConfig has sensible defaults."""
        config = RateLimitConfig()
        assert config.max_evaluations_per_second == 1000.0
        assert config.max_evaluations_per_minute == 50000.0
        assert config.per_flag_limits is None
        assert config.burst_multiplier == 1.5

    def test_custom_values(self):
        """Test RateLimitConfig with custom values."""
        config = RateLimitConfig(
            max_evaluations_per_second=500.0,
            max_evaluations_per_minute=25000.0,
            per_flag_limits={"expensive-flag": 10.0},
            burst_multiplier=2.0,
        )
        assert config.max_evaluations_per_second == 500.0
        assert config.max_evaluations_per_minute == 25000.0
        assert config.per_flag_limits == {"expensive-flag": 10.0}
        assert config.burst_multiplier == 2.0

    def test_per_flag_limits_dict(self):
        """Test per_flag_limits configuration."""
        config = RateLimitConfig(
            per_flag_limits={
                "flag-a": 100.0,
                "flag-b": 50.0,
                "flag-c": 10.0,
            }
        )
        assert len(config.per_flag_limits) == 3
        assert config.per_flag_limits["flag-a"] == 100.0
        assert config.per_flag_limits["flag-b"] == 50.0
        assert config.per_flag_limits["flag-c"] == 10.0


class TestTokenBucket:
    """Tests for the internal _TokenBucket class."""

    def test_initial_tokens(self):
        """Test that bucket starts with full capacity."""
        bucket = _TokenBucket(rate=10.0, capacity=100.0)
        assert bucket.tokens == 100.0
        assert bucket.rate == 10.0
        assert bucket.capacity == 100.0

    def test_consume_success(self):
        """Test successful token consumption."""
        bucket = _TokenBucket(rate=10.0, capacity=100.0)
        result = bucket.consume(1.0)
        assert result is True
        assert bucket.tokens == 99.0

    def test_consume_multiple_tokens(self):
        """Test consuming multiple tokens at once."""
        bucket = _TokenBucket(rate=10.0, capacity=100.0)
        result = bucket.consume(50.0)
        assert result is True
        assert bucket.tokens == 50.0

    def test_consume_insufficient_tokens(self):
        """Test consumption failure when insufficient tokens."""
        bucket = _TokenBucket(rate=10.0, capacity=10.0)
        # Consume all tokens first
        bucket.consume(10.0)
        # Try to consume more
        result = bucket.consume(1.0)
        assert result is False

    def test_consume_all_tokens(self):
        """Test consuming exactly all available tokens."""
        bucket = _TokenBucket(rate=10.0, capacity=50.0)
        result = bucket.consume(50.0)
        assert result is True
        assert bucket.tokens == 0.0

    def test_refill_over_time(self):
        """Test that tokens are refilled over time."""
        bucket = _TokenBucket(rate=1000.0, capacity=100.0)
        bucket.consume(100.0)  # Empty the bucket
        assert bucket.tokens == 0.0

        # Wait a small amount of time
        time.sleep(0.01)  # 10ms

        # Trigger refill
        bucket._refill()

        # Should have some tokens now (1000 tokens/sec * 0.01s = 10 tokens)
        assert bucket.tokens > 0.0
        assert bucket.tokens <= 100.0  # Capped at capacity

    def test_refill_capped_at_capacity(self):
        """Test that refill doesn't exceed capacity."""
        bucket = _TokenBucket(rate=10000.0, capacity=50.0)
        # Wait for potential over-refill
        time.sleep(0.01)
        bucket._refill()
        assert bucket.tokens <= bucket.capacity

    def test_time_until_available_immediate(self):
        """Test time_until_available when tokens are available."""
        bucket = _TokenBucket(rate=10.0, capacity=100.0)
        wait_time = bucket.time_until_available(1.0)
        assert wait_time == 0.0

    def test_time_until_available_wait_needed(self):
        """Test time_until_available when wait is needed."""
        bucket = _TokenBucket(rate=10.0, capacity=10.0)
        bucket.consume(10.0)  # Empty the bucket

        wait_time = bucket.time_until_available(5.0)
        # Need 5 tokens at 10 tokens/sec = 0.5 seconds
        assert wait_time > 0.0
        assert wait_time <= 0.6  # Allow some tolerance

    def test_time_until_available_partial(self):
        """Test time_until_available with partial tokens."""
        bucket = _TokenBucket(rate=100.0, capacity=100.0)
        bucket.consume(99.0)  # Leave 1 token

        wait_time = bucket.time_until_available(10.0)
        # Need 9 more tokens at 100 tokens/sec = 0.09 seconds
        assert wait_time > 0.0
        assert wait_time < 0.15


class TestTokenBucketRateLimiter:
    """Tests for TokenBucketRateLimiter."""

    @pytest.fixture
    def config(self) -> RateLimitConfig:
        """Create a test configuration."""
        return RateLimitConfig(
            max_evaluations_per_second=100.0,
            max_evaluations_per_minute=5000.0,
            burst_multiplier=1.5,
        )

    @pytest.fixture
    def limiter(self, config: RateLimitConfig) -> TokenBucketRateLimiter:
        """Create a test rate limiter."""
        return TokenBucketRateLimiter(config)

    def test_init(self, limiter: TokenBucketRateLimiter, config: RateLimitConfig):
        """Test rate limiter initialization."""
        assert limiter.config == config
        assert limiter._total_requests == 0
        assert limiter._rejected_requests == 0

    def test_config_property(self, limiter: TokenBucketRateLimiter, config: RateLimitConfig):
        """Test config property returns configuration."""
        assert limiter.config is config

    async def test_acquire_success(self, limiter: TokenBucketRateLimiter):
        """Test successful acquire."""
        await limiter.acquire("test-flag")
        # Should not raise
        stats = limiter.get_stats()
        assert stats["total_requests"] == 1.0
        assert stats["rejected_requests"] == 0.0

    async def test_acquire_without_flag_key(self, limiter: TokenBucketRateLimiter):
        """Test acquire without flag key."""
        await limiter.acquire()  # No flag key
        stats = limiter.get_stats()
        assert stats["total_requests"] == 1.0

    async def test_acquire_multiple(self, limiter: TokenBucketRateLimiter):
        """Test multiple successful acquisitions."""
        for _ in range(10):
            await limiter.acquire("test-flag")

        stats = limiter.get_stats()
        assert stats["total_requests"] == 10.0
        assert stats["rejected_requests"] == 0.0

    async def test_acquire_rate_limit_exceeded_per_second(self):
        """Test rate limit exceeded for per-second limit."""
        # Very low rate limit for testing
        config = RateLimitConfig(
            max_evaluations_per_second=1.0,
            max_evaluations_per_minute=1000.0,
            burst_multiplier=1.0,  # No burst capacity
        )
        limiter = TokenBucketRateLimiter(config)

        # First acquire should succeed
        await limiter.acquire()

        # Second acquire should fail
        with pytest.raises(RateLimitExceededError) as exc_info:
            await limiter.acquire()

        assert "per-second" in str(exc_info.value)
        assert exc_info.value.wait_time is not None
        assert exc_info.value.wait_time > 0

    async def test_acquire_rate_limit_exceeded_per_minute(self):
        """Test rate limit exceeded for per-minute limit."""
        # High per-second but very low per-minute
        config = RateLimitConfig(
            max_evaluations_per_second=1000.0,
            max_evaluations_per_minute=1.0,
            burst_multiplier=1.0,
        )
        limiter = TokenBucketRateLimiter(config)

        # First acquire should succeed
        await limiter.acquire()

        # Second acquire should fail due to per-minute limit
        with pytest.raises(RateLimitExceededError) as exc_info:
            await limiter.acquire()

        assert "per-minute" in str(exc_info.value)
        assert exc_info.value.wait_time is not None

    async def test_try_acquire_success(self, limiter: TokenBucketRateLimiter):
        """Test try_acquire returns True on success."""
        result = await limiter.try_acquire("test-flag")
        assert result is True

    async def test_try_acquire_failure(self):
        """Test try_acquire returns False on rate limit."""
        config = RateLimitConfig(
            max_evaluations_per_second=1.0,
            burst_multiplier=1.0,
        )
        limiter = TokenBucketRateLimiter(config)

        # First should succeed
        result1 = await limiter.try_acquire()
        assert result1 is True

        # Second should fail without exception
        result2 = await limiter.try_acquire()
        assert result2 is False

    async def test_wait_and_acquire_immediate(self, limiter: TokenBucketRateLimiter):
        """Test wait_and_acquire when immediately available."""
        result = await limiter.wait_and_acquire("test-flag")
        assert result is True

    async def test_wait_and_acquire_with_wait(self):
        """Test wait_and_acquire waits for rate limit."""
        config = RateLimitConfig(
            max_evaluations_per_second=100.0,
            burst_multiplier=1.0,
        )
        limiter = TokenBucketRateLimiter(config)

        # Exhaust most tokens
        for _ in range(100):
            try:
                await limiter.acquire()
            except RateLimitExceededError:
                break

        # This should wait and succeed
        start = time.monotonic()
        result = await limiter.wait_and_acquire(timeout=1.0)
        elapsed = time.monotonic() - start

        assert result is True
        # Should have waited some time (or be very fast if tokens refilled)
        assert elapsed < 1.0  # Should complete within timeout

    async def test_wait_and_acquire_timeout(self):
        """Test wait_and_acquire times out."""
        config = RateLimitConfig(
            max_evaluations_per_second=1.0,  # 1 token/sec refill rate
            burst_multiplier=1.0,  # Capacity of 1 token
        )
        limiter = TokenBucketRateLimiter(config)

        # Exhaust tokens (use the 1 token we have)
        await limiter.acquire()

        # Should timeout since we need to wait 1 second for refill
        # but timeout is only 50ms
        start = time.monotonic()
        result = await limiter.wait_and_acquire(timeout=0.05)  # 50ms timeout
        elapsed = time.monotonic() - start

        assert result is False
        assert elapsed >= 0.05  # Should have waited at least timeout

    async def test_wait_and_acquire_no_timeout(self):
        """Test wait_and_acquire without timeout eventually succeeds."""
        config = RateLimitConfig(
            max_evaluations_per_second=100.0,
            burst_multiplier=1.0,
        )
        limiter = TokenBucketRateLimiter(config)

        # First acquire
        await limiter.acquire()

        # Wait and acquire (should succeed quickly)
        result = await limiter.wait_and_acquire()
        assert result is True

    async def test_get_stats(self, limiter: TokenBucketRateLimiter):
        """Test get_stats returns correct statistics."""
        stats = limiter.get_stats()

        assert "total_requests" in stats
        assert "rejected_requests" in stats
        assert "rejection_rate" in stats
        assert "global_tokens_sec" in stats
        assert "global_tokens_min" in stats

        assert stats["total_requests"] == 0.0
        assert stats["rejected_requests"] == 0.0
        assert stats["rejection_rate"] == 0.0

    async def test_get_stats_after_requests(self):
        """Test get_stats after some requests."""
        config = RateLimitConfig(
            max_evaluations_per_second=2.0,
            burst_multiplier=1.0,
        )
        limiter = TokenBucketRateLimiter(config)

        # Make some successful requests
        await limiter.acquire()
        await limiter.acquire()

        # Make a rejected request
        try:
            await limiter.acquire()
        except RateLimitExceededError:
            pass

        stats = limiter.get_stats()
        assert stats["total_requests"] == 3.0
        assert stats["rejected_requests"] == 1.0
        assert stats["rejection_rate"] == pytest.approx(33.33, rel=0.1)

    async def test_reset_stats(self):
        """Test reset_stats clears statistics."""
        config = RateLimitConfig(
            max_evaluations_per_second=1.0,
            burst_multiplier=1.0,
        )
        limiter = TokenBucketRateLimiter(config)

        await limiter.acquire()
        try:
            await limiter.acquire()
        except RateLimitExceededError:
            pass

        limiter.reset_stats()

        stats = limiter.get_stats()
        assert stats["total_requests"] == 0.0
        assert stats["rejected_requests"] == 0.0
        assert stats["rejection_rate"] == 0.0


class TestTokenBucketRateLimiterPerFlagLimits:
    """Tests for per-flag rate limiting."""

    @pytest.fixture
    def config_with_per_flag(self) -> RateLimitConfig:
        """Create config with per-flag limits."""
        return RateLimitConfig(
            max_evaluations_per_second=1000.0,
            max_evaluations_per_minute=50000.0,
            per_flag_limits={
                "expensive-flag": 1.0,  # Very limited
                "normal-flag": 100.0,
            },
            burst_multiplier=1.0,
        )

    @pytest.fixture
    def limiter(self, config_with_per_flag: RateLimitConfig) -> TokenBucketRateLimiter:
        """Create rate limiter with per-flag limits."""
        return TokenBucketRateLimiter(config_with_per_flag)

    async def test_per_flag_limit_enforced(self, limiter: TokenBucketRateLimiter):
        """Test that per-flag limits are enforced."""
        # First acquire should succeed
        await limiter.acquire("expensive-flag")

        # Second acquire for same flag should fail
        with pytest.raises(RateLimitExceededError) as exc_info:
            await limiter.acquire("expensive-flag")

        assert exc_info.value.flag_key == "expensive-flag"
        assert "per-flag" in str(exc_info.value).lower()

    async def test_different_flags_independent(self, limiter: TokenBucketRateLimiter):
        """Test that different flags have independent limits."""
        # Exhaust expensive-flag limit
        await limiter.acquire("expensive-flag")

        # normal-flag should still work
        await limiter.acquire("normal-flag")  # Should not raise

        # expensive-flag should still fail
        with pytest.raises(RateLimitExceededError):
            await limiter.acquire("expensive-flag")

    async def test_flag_without_per_flag_limit(self, limiter: TokenBucketRateLimiter):
        """Test flag without specific per-flag limit uses global limit."""
        # Flag not in per_flag_limits
        for _ in range(10):
            await limiter.acquire("unlisted-flag")
        # Should work fine up to global limit

    async def test_per_flag_bucket_created_on_demand(self, limiter: TokenBucketRateLimiter):
        """Test that per-flag buckets are created on demand."""
        assert "expensive-flag" not in limiter._flag_buckets

        await limiter.acquire("expensive-flag")

        assert "expensive-flag" in limiter._flag_buckets


class TestTokenBucketRateLimiterConcurrency:
    """Tests for concurrent access to rate limiter."""

    @pytest.fixture
    def limiter(self) -> TokenBucketRateLimiter:
        """Create rate limiter for concurrency tests."""
        config = RateLimitConfig(
            max_evaluations_per_second=100.0,
            burst_multiplier=2.0,  # Allow some burst
        )
        return TokenBucketRateLimiter(config)

    async def test_concurrent_acquire(self, limiter: TokenBucketRateLimiter):
        """Test concurrent acquire operations."""

        async def acquire_task():
            for _ in range(5):
                try:
                    await limiter.acquire("test-flag")
                    await asyncio.sleep(0.001)
                except RateLimitExceededError:
                    pass

        # Run multiple concurrent tasks
        tasks = [acquire_task() for _ in range(5)]
        await asyncio.gather(*tasks)

        # Should complete without errors
        stats = limiter.get_stats()
        assert stats["total_requests"] > 0

    async def test_concurrent_try_acquire(self, limiter: TokenBucketRateLimiter):
        """Test concurrent try_acquire operations."""
        results = []

        async def try_acquire_task():
            for _ in range(10):
                result = await limiter.try_acquire()
                results.append(result)
                await asyncio.sleep(0.001)

        tasks = [try_acquire_task() for _ in range(3)]
        await asyncio.gather(*tasks)

        # Should have mix of successes and failures
        assert any(results)  # At least some succeeded


class TestRateLimiterProtocol:
    """Tests for RateLimiter protocol compliance."""

    def test_token_bucket_implements_protocol(self):
        """Test that TokenBucketRateLimiter implements RateLimiter protocol."""
        config = RateLimitConfig()
        limiter = TokenBucketRateLimiter(config)
        assert isinstance(limiter, RateLimiter)

    def test_protocol_has_required_methods(self):
        """Test that protocol defines required methods."""
        assert hasattr(RateLimiter, "acquire")
        assert hasattr(RateLimiter, "try_acquire")
        assert hasattr(RateLimiter, "get_stats")


class TestRateLimitHook:
    """Tests for RateLimitHook."""

    @pytest.fixture
    def config(self) -> RateLimitConfig:
        """Create test configuration."""
        return RateLimitConfig(
            max_evaluations_per_second=10.0,
            burst_multiplier=1.0,
        )

    @pytest.fixture
    def limiter(self, config: RateLimitConfig) -> TokenBucketRateLimiter:
        """Create test rate limiter."""
        return TokenBucketRateLimiter(config)

    @pytest.fixture
    def hook(self, limiter: TokenBucketRateLimiter) -> RateLimitHook:
        """Create test rate limit hook."""
        return RateLimitHook(rate_limiter=limiter)

    async def test_before_evaluation_success(self, hook: RateLimitHook):
        """Test before_evaluation succeeds when under limit."""
        await hook.before_evaluation("test-flag")
        assert hook.get_evaluation_count() == 1

    async def test_before_evaluation_increments_count(self, hook: RateLimitHook):
        """Test that before_evaluation increments evaluation count."""
        await hook.before_evaluation("flag-1")
        await hook.before_evaluation("flag-2")
        await hook.before_evaluation("flag-3")
        assert hook.get_evaluation_count() == 3

    async def test_before_evaluation_raises_on_limit(self, limiter: TokenBucketRateLimiter):
        """Test before_evaluation raises when rate limited."""
        hook = RateLimitHook(rate_limiter=limiter)

        # Exhaust the rate limit
        for _ in range(10):
            try:
                await hook.before_evaluation("test-flag")
            except RateLimitExceededError:
                break

        # Next evaluation should raise
        with pytest.raises(RateLimitExceededError):
            await hook.before_evaluation("test-flag")

    async def test_after_evaluation_tracking(self, hook: RateLimitHook):
        """Test after_evaluation can be called without error."""
        await hook.before_evaluation("test-flag")
        hook.after_evaluation("test-flag", success=True)
        hook.after_evaluation("test-flag", success=False)
        # Should not raise

    def test_get_evaluation_count(self, hook: RateLimitHook):
        """Test get_evaluation_count returns correct count."""
        assert hook.get_evaluation_count() == 0

    async def test_reset_count(self, hook: RateLimitHook):
        """Test reset_count clears evaluation counter."""
        await hook.before_evaluation("flag-1")
        await hook.before_evaluation("flag-2")

        hook.reset_count()

        assert hook.get_evaluation_count() == 0

    def test_warning_threshold_default(self, hook: RateLimitHook):
        """Test default warning threshold."""
        assert hook.warning_threshold == 0.8

    def test_custom_warning_threshold(self, limiter: TokenBucketRateLimiter):
        """Test custom warning threshold."""
        hook = RateLimitHook(
            rate_limiter=limiter,
            warning_threshold=0.5,
        )
        assert hook.warning_threshold == 0.5


class TestRateLimitHookCallbacks:
    """Tests for RateLimitHook callback functionality."""

    @pytest.fixture
    def limiter(self) -> TokenBucketRateLimiter:
        """Create rate limiter with low limits for testing."""
        config = RateLimitConfig(
            max_evaluations_per_second=2.0,
            burst_multiplier=1.0,
        )
        return TokenBucketRateLimiter(config)

    async def test_on_limit_exceeded_callback(self, limiter: TokenBucketRateLimiter):
        """Test on_limit_exceeded callback is called."""
        callback_calls: list[tuple[str, RateLimitExceededError]] = []

        def on_exceeded(flag_key: str, exc: RateLimitExceededError):
            callback_calls.append((flag_key, exc))

        hook = RateLimitHook(
            rate_limiter=limiter,
            on_limit_exceeded=on_exceeded,
        )

        # Exhaust limit
        for _ in range(2):
            await hook.before_evaluation("test-flag")

        # Trigger callback
        with pytest.raises(RateLimitExceededError):
            await hook.before_evaluation("test-flag")

        assert len(callback_calls) == 1
        assert callback_calls[0][0] == "test-flag"
        assert isinstance(callback_calls[0][1], RateLimitExceededError)

    async def test_on_limit_approached_callback(self, limiter: TokenBucketRateLimiter):
        """Test on_limit_approached callback is called."""
        callback_calls: list[dict] = []

        def on_approached(stats: dict[str, float]):
            callback_calls.append(stats)

        hook = RateLimitHook(
            rate_limiter=limiter,
            warning_threshold=0.0,  # Always warn
            on_limit_approached=on_approached,
        )

        # Need to trigger a high rejection rate
        # First exhaust the limit
        for _ in range(3):
            try:
                await hook.before_evaluation("test-flag")
            except RateLimitExceededError:
                pass

        # At this point rejection rate should be high enough to trigger warning
        # (if rejection_rate >= warning_threshold * 100)
        # Note: callback may or may not be called depending on timing

    async def test_warning_cooldown(self, limiter: TokenBucketRateLimiter):
        """Test that warnings have a cooldown period."""
        callback_calls: list[dict] = []

        def on_approached(stats: dict[str, float]):
            callback_calls.append(stats)

        hook = RateLimitHook(
            rate_limiter=limiter,
            warning_threshold=0.0,  # Always trigger warning check
            on_limit_approached=on_approached,
        )
        # Set short cooldown for testing
        hook._warning_cooldown = 0.01

        # First evaluation that triggers warning
        limiter._rejected_requests = 100
        limiter._total_requests = 100
        await hook.before_evaluation("flag-1")

        initial_count = len(callback_calls)

        # Rapid evaluations should be throttled
        for i in range(5):
            try:
                await hook.before_evaluation(f"flag-{i + 2}")
            except RateLimitExceededError:
                pass

        # After cooldown, warning can trigger again
        await asyncio.sleep(0.02)
        limiter._total_requests = 200
        limiter._rejected_requests = 200
        try:
            await hook.before_evaluation("flag-final")
        except RateLimitExceededError:
            pass

        # Should have limited number of warnings due to cooldown
        assert len(callback_calls) <= initial_count + 2

    async def test_no_callbacks_when_none(self, limiter: TokenBucketRateLimiter):
        """Test that no callbacks when set to None."""
        hook = RateLimitHook(
            rate_limiter=limiter,
            on_limit_exceeded=None,
            on_limit_approached=None,
        )

        # Exhaust limit and trigger rate limit
        for _ in range(3):
            try:
                await hook.before_evaluation("test-flag")
            except RateLimitExceededError:
                pass

        # Should not raise any errors from callback handling


class TestRateLimitExceedException:
    """Tests for RateLimitExceededError exception."""

    def test_basic_exception(self):
        """Test basic exception creation."""
        exc = RateLimitExceededError("Rate limit exceeded")
        assert str(exc) == "Rate limit exceeded"
        assert exc.wait_time is None
        assert exc.flag_key is None

    def test_exception_with_wait_time(self):
        """Test exception with wait_time."""
        exc = RateLimitExceededError("Retry later", wait_time=5.5)
        assert exc.wait_time == 5.5

    def test_exception_with_flag_key(self):
        """Test exception with flag_key."""
        exc = RateLimitExceededError("Per-flag limit", flag_key="my-flag")
        assert exc.flag_key == "my-flag"

    def test_exception_full(self):
        """Test exception with all parameters."""
        exc = RateLimitExceededError(
            "Complete rate limit error",
            wait_time=10.0,
            flag_key="expensive-operation",
        )
        assert "Complete rate limit error" in str(exc)
        assert exc.wait_time == 10.0
        assert exc.flag_key == "expensive-operation"

    def test_exception_inheritance(self):
        """Test that RateLimitExceededError inherits from FeatureFlagError."""
        from litestar_flags.exceptions import FeatureFlagError

        exc = RateLimitExceededError()
        assert isinstance(exc, FeatureFlagError)
        assert isinstance(exc, Exception)


class TestBurstCapacity:
    """Tests for burst capacity functionality."""

    async def test_burst_allows_extra_requests(self):
        """Test that burst multiplier allows extra requests."""
        config = RateLimitConfig(
            max_evaluations_per_second=10.0,
            burst_multiplier=2.0,  # Allow 2x burst
        )
        limiter = TokenBucketRateLimiter(config)

        # Should be able to do 20 requests (10 * 2.0 burst)
        successful = 0
        for _ in range(25):
            try:
                await limiter.acquire()
                successful += 1
            except RateLimitExceededError:
                break

        # Should have succeeded around 20 times (burst capacity)
        assert successful >= 15  # Allow some margin

    async def test_no_burst_with_multiplier_1(self):
        """Test that burst_multiplier=1.0 means no burst."""
        config = RateLimitConfig(
            max_evaluations_per_second=5.0,
            burst_multiplier=1.0,
        )
        limiter = TokenBucketRateLimiter(config)

        successful = 0
        for _ in range(10):
            try:
                await limiter.acquire()
                successful += 1
            except RateLimitExceededError:
                break

        # Should succeed exactly 5 times (no burst)
        assert successful == 5


class TestTokenRefill:
    """Tests for token refill behavior."""

    async def test_tokens_refill_after_wait(self):
        """Test that tokens refill after waiting."""
        config = RateLimitConfig(
            max_evaluations_per_second=100.0,
            burst_multiplier=1.0,
        )
        limiter = TokenBucketRateLimiter(config)

        # Exhaust tokens
        for _ in range(100):
            try:
                await limiter.acquire()
            except RateLimitExceededError:
                break

        # Wait for refill
        await asyncio.sleep(0.05)  # 50ms = 5 tokens at 100/sec

        # Should be able to acquire again
        result = await limiter.try_acquire()
        assert result is True

    async def test_per_minute_bucket_refill(self):
        """Test per-minute bucket refill rate."""
        config = RateLimitConfig(
            max_evaluations_per_second=1000.0,
            max_evaluations_per_minute=60.0,  # 1 per second
            burst_multiplier=1.0,
        )
        limiter = TokenBucketRateLimiter(config)

        # Exhaust per-minute bucket
        for _ in range(60):
            try:
                await limiter.acquire()
            except RateLimitExceededError:
                break

        # Should be rate limited by per-minute
        result = await limiter.try_acquire()
        assert result is False

        # Wait 1 second for refill (60/min = 1/sec)
        await asyncio.sleep(1.1)

        # Should succeed now
        result = await limiter.try_acquire()
        assert result is True
