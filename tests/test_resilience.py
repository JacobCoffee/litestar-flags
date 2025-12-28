"""Tests for resilience patterns (circuit breaker, retry, etc.)."""

from __future__ import annotations

import asyncio

import pytest

from litestar_flags.resilience import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
    ResilienceConfig,
    RetryPolicy,
    resilient_call,
)


class TestCircuitState:
    """Tests for CircuitState enum."""

    def test_circuit_state_values(self) -> None:
        """Test that circuit states have correct string values."""
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"

    def test_circuit_state_is_string_enum(self) -> None:
        """Test that CircuitState inherits from str."""
        assert isinstance(CircuitState.CLOSED, str)
        assert CircuitState.CLOSED == "closed"


class TestCircuitBreakerError:
    """Tests for CircuitBreakerError exception."""

    def test_error_with_recovery_time(self) -> None:
        """Test error message includes recovery time when provided."""
        error = CircuitBreakerError("test-circuit", CircuitState.OPEN, recovery_time=10.5)
        assert error.circuit_name == "test-circuit"
        assert error.state == CircuitState.OPEN
        assert error.recovery_time == 10.5
        assert "test-circuit" in str(error)
        assert "open" in str(error)
        assert "10.5s" in str(error)

    def test_error_without_recovery_time(self) -> None:
        """Test error message when recovery time is None."""
        error = CircuitBreakerError("test-circuit", CircuitState.OPEN, recovery_time=None)
        assert error.recovery_time is None
        assert "recovery" not in str(error)

    def test_error_with_zero_recovery_time(self) -> None:
        """Test error message when recovery time is zero."""
        error = CircuitBreakerError("test-circuit", CircuitState.OPEN, recovery_time=0.0)
        # Zero recovery time should not show "recovery in" message
        assert "recovery" not in str(error)

    def test_error_inheritance(self) -> None:
        """Test that CircuitBreakerError is an Exception."""
        error = CircuitBreakerError("test", CircuitState.OPEN)
        assert isinstance(error, Exception)


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    @pytest.fixture
    def breaker(self) -> CircuitBreaker:
        """Create a circuit breaker with test-friendly settings."""
        return CircuitBreaker(
            name="test-breaker",
            failure_threshold=3,
            recovery_timeout=0.1,  # Short timeout for testing
            success_threshold=2,
        )

    async def test_initial_state_is_closed(self, breaker: CircuitBreaker) -> None:
        """Test that circuit breaker starts in closed state."""
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_closed is True
        assert breaker.is_open is False
        assert breaker.failure_count == 0

    async def test_successful_call_in_closed_state(self, breaker: CircuitBreaker) -> None:
        """Test successful call passes through in closed state."""

        async def success_func() -> str:
            return "success"

        result = await breaker.call(success_func)
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    async def test_failure_increments_count(self, breaker: CircuitBreaker) -> None:
        """Test that failures increment the failure count."""

        async def failing_func() -> None:
            raise RuntimeError("test error")

        with pytest.raises(RuntimeError):
            await breaker.call(failing_func)

        assert breaker.failure_count == 1
        assert breaker.state == CircuitState.CLOSED  # Not yet at threshold

    async def test_circuit_opens_at_threshold(self, breaker: CircuitBreaker) -> None:
        """Test that circuit opens when failure threshold is reached."""

        async def failing_func() -> None:
            raise RuntimeError("test error")

        # Trigger failures up to threshold
        for _ in range(breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN
        assert breaker.is_open is True
        assert breaker.failure_count == breaker.failure_threshold

    async def test_open_circuit_raises_error(self, breaker: CircuitBreaker) -> None:
        """Test that open circuit raises CircuitBreakerError."""

        async def failing_func() -> None:
            raise RuntimeError("test error")

        # Open the circuit
        for _ in range(breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                await breaker.call(failing_func)

        async def success_func() -> str:
            return "success"

        # Now circuit is open, should raise CircuitBreakerError
        with pytest.raises(CircuitBreakerError) as exc_info:
            await breaker.call(success_func)

        assert exc_info.value.circuit_name == "test-breaker"
        assert exc_info.value.state == CircuitState.OPEN

    async def test_open_circuit_returns_fallback(self, breaker: CircuitBreaker) -> None:
        """Test that open circuit returns fallback value when provided."""

        async def failing_func() -> None:
            raise RuntimeError("test error")

        # Open the circuit
        for _ in range(breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                await breaker.call(failing_func)

        # Should return fallback instead of raising
        result = await breaker.call(failing_func, fallback="fallback_value")
        assert result == "fallback_value"

    async def test_circuit_transitions_to_half_open(self, breaker: CircuitBreaker) -> None:
        """Test that circuit transitions to half-open after recovery timeout."""

        async def failing_func() -> None:
            raise RuntimeError("test error")

        # Open the circuit
        for _ in range(breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(breaker.recovery_timeout + 0.05)

        async def success_func() -> str:
            return "success"

        # Next call should transition to half-open and succeed
        result = await breaker.call(success_func)
        assert result == "success"
        # After success, still in half-open (need success_threshold successes to close)
        assert breaker.state == CircuitState.HALF_OPEN

    async def test_half_open_closes_after_success_threshold(self, breaker: CircuitBreaker) -> None:
        """Test circuit closes after enough successes in half-open state."""

        async def failing_func() -> None:
            raise RuntimeError("test error")

        # Open the circuit
        for _ in range(breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                await breaker.call(failing_func)

        # Wait for recovery timeout
        await asyncio.sleep(breaker.recovery_timeout + 0.05)

        async def success_func() -> str:
            return "success"

        # Need success_threshold successes to close
        for _ in range(breaker.success_threshold):
            await breaker.call(success_func)

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    async def test_half_open_reopens_on_failure(self, breaker: CircuitBreaker) -> None:
        """Test circuit reopens from half-open state on failure."""

        async def failing_func() -> None:
            raise RuntimeError("test error")

        # Open the circuit
        for _ in range(breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                await breaker.call(failing_func)

        # Wait for recovery timeout
        await asyncio.sleep(breaker.recovery_timeout + 0.05)

        # First call in half-open fails - should reopen
        with pytest.raises(RuntimeError):
            await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

    async def test_success_resets_failure_count_in_closed(self, breaker: CircuitBreaker) -> None:
        """Test that success in closed state resets failure count."""

        async def failing_func() -> None:
            raise RuntimeError("test error")

        async def success_func() -> str:
            return "success"

        # Accumulate some failures (below threshold)
        for _ in range(breaker.failure_threshold - 1):
            with pytest.raises(RuntimeError):
                await breaker.call(failing_func)

        assert breaker.failure_count == breaker.failure_threshold - 1

        # Success should reset failure count
        await breaker.call(success_func)
        assert breaker.failure_count == 0

    async def test_time_until_recovery(self, breaker: CircuitBreaker) -> None:
        """Test time_until_recovery property."""
        # In closed state, should be None
        assert breaker.time_until_recovery is None

        async def failing_func() -> None:
            raise RuntimeError("test error")

        # Open the circuit
        for _ in range(breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                await breaker.call(failing_func)

        # In open state, should have a recovery time
        recovery_time = breaker.time_until_recovery
        assert recovery_time is not None
        assert 0 <= recovery_time <= breaker.recovery_timeout

    async def test_manual_reset(self, breaker: CircuitBreaker) -> None:
        """Test manual reset of circuit breaker."""

        async def failing_func() -> None:
            raise RuntimeError("test error")

        # Open the circuit
        for _ in range(breaker.failure_threshold):
            with pytest.raises(RuntimeError):
                await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

        # Manual reset
        await breaker.reset()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    async def test_get_stats(self, breaker: CircuitBreaker) -> None:
        """Test get_stats returns correct information."""
        stats = breaker.get_stats()

        assert stats["name"] == "test-breaker"
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 0
        assert stats["success_count"] == 0
        assert stats["failure_threshold"] == 3
        assert stats["recovery_timeout"] == 0.1
        assert stats["time_until_recovery"] is None

    async def test_default_parameters(self) -> None:
        """Test circuit breaker with default parameters."""
        breaker = CircuitBreaker()

        assert breaker.name == "default"
        assert breaker.failure_threshold == 5
        assert breaker.recovery_timeout == 30.0
        assert breaker.success_threshold == 2

    async def test_concurrent_calls(self, breaker: CircuitBreaker) -> None:
        """Test circuit breaker handles concurrent calls correctly."""
        call_count = 0

        async def counting_func() -> int:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return call_count

        # Run concurrent calls
        results = await asyncio.gather(*[breaker.call(counting_func) for _ in range(5)])

        assert len(results) == 5
        assert call_count == 5


class TestRetryPolicy:
    """Tests for RetryPolicy."""

    def test_default_values(self) -> None:
        """Test default retry policy values."""
        policy = RetryPolicy()

        assert policy.max_retries == 3
        assert policy.base_delay == 0.1
        assert policy.max_delay == 2.0
        assert policy.exponential_backoff is True
        assert policy.jitter is True
        assert ConnectionError in policy.retryable_exceptions
        assert TimeoutError in policy.retryable_exceptions
        assert OSError in policy.retryable_exceptions

    def test_get_delay_linear(self) -> None:
        """Test delay calculation without exponential backoff."""
        policy = RetryPolicy(
            base_delay=0.5,
            exponential_backoff=False,
            jitter=False,
        )

        # All attempts should have the same delay
        assert policy.get_delay(0) == 0.5
        assert policy.get_delay(1) == 0.5
        assert policy.get_delay(2) == 0.5

    def test_get_delay_exponential(self) -> None:
        """Test delay calculation with exponential backoff."""
        policy = RetryPolicy(
            base_delay=0.1,
            max_delay=10.0,
            exponential_backoff=True,
            jitter=False,
        )

        # Exponential: base_delay * 2^attempt
        assert policy.get_delay(0) == 0.1  # 0.1 * 2^0 = 0.1
        assert policy.get_delay(1) == 0.2  # 0.1 * 2^1 = 0.2
        assert policy.get_delay(2) == 0.4  # 0.1 * 2^2 = 0.4
        assert policy.get_delay(3) == 0.8  # 0.1 * 2^3 = 0.8

    def test_get_delay_respects_max(self) -> None:
        """Test that delay is capped at max_delay."""
        policy = RetryPolicy(
            base_delay=1.0,
            max_delay=2.0,
            exponential_backoff=True,
            jitter=False,
        )

        # High attempt number should be capped at max_delay
        assert policy.get_delay(10) == 2.0

    def test_get_delay_with_jitter(self) -> None:
        """Test that jitter adds randomness to delay."""
        policy = RetryPolicy(
            base_delay=1.0,
            max_delay=10.0,
            exponential_backoff=False,
            jitter=True,
        )

        delays = [policy.get_delay(0) for _ in range(10)]

        # All delays should be >= base_delay (jitter only adds, doesn't subtract)
        for delay in delays:
            assert delay >= 1.0
            assert delay <= 1.25  # Max 25% jitter

        # With jitter, delays should vary (statistically almost certain)
        # But we check that they're not all exactly equal
        unique_delays = set(delays)
        assert len(unique_delays) > 1  # Should have some variation

    def test_should_retry_retryable_exception(self) -> None:
        """Test that retryable exceptions return True."""
        policy = RetryPolicy()

        assert policy.should_retry(ConnectionError("connection failed")) is True
        assert policy.should_retry(TimeoutError("timeout")) is True
        assert policy.should_retry(OSError("os error")) is True

    def test_should_retry_non_retryable_exception(self) -> None:
        """Test that non-retryable exceptions return False."""
        policy = RetryPolicy()

        assert policy.should_retry(ValueError("value error")) is False
        assert policy.should_retry(RuntimeError("runtime error")) is False
        assert policy.should_retry(KeyError("key error")) is False

    def test_custom_retryable_exceptions(self) -> None:
        """Test custom retryable exceptions."""

        class CustomError(Exception):
            pass

        policy = RetryPolicy(retryable_exceptions=(CustomError, ValueError))

        assert policy.should_retry(CustomError("custom")) is True
        assert policy.should_retry(ValueError("value")) is True
        assert policy.should_retry(ConnectionError("connection")) is False


class TestResilientCall:
    """Tests for resilient_call function."""

    async def test_successful_call_without_resilience(self) -> None:
        """Test successful call without circuit breaker or retry."""

        async def success_func() -> str:
            return "success"

        result = await resilient_call(success_func)
        assert result == "success"

    async def test_failing_call_without_resilience(self) -> None:
        """Test failing call without resilience raises exception."""

        async def failing_func() -> str:
            raise RuntimeError("test error")

        with pytest.raises(RuntimeError):
            await resilient_call(failing_func)

    async def test_failing_call_with_default(self) -> None:
        """Test failing call returns default value."""

        async def failing_func() -> str:
            raise RuntimeError("test error")

        result = await resilient_call(failing_func, default="default_value")
        assert result == "default_value"

    async def test_retry_on_retryable_exception(self) -> None:
        """Test that retryable exceptions trigger retries."""
        call_count = 0

        async def flaky_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("connection failed")
            return "success"

        policy = RetryPolicy(
            max_retries=3,
            base_delay=0.01,  # Short delay for testing
            jitter=False,
        )

        result = await resilient_call(flaky_func, retry_policy=policy)
        assert result == "success"
        assert call_count == 3

    async def test_no_retry_on_non_retryable_exception(self) -> None:
        """Test that non-retryable exceptions do not trigger retries."""
        call_count = 0

        async def failing_func() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        policy = RetryPolicy(max_retries=3)

        with pytest.raises(ValueError):
            await resilient_call(failing_func, retry_policy=policy)

        assert call_count == 1  # No retries

    async def test_max_retries_exhausted(self) -> None:
        """Test that retries are exhausted and default is returned."""
        call_count = 0

        async def always_failing() -> str:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("always fails")

        policy = RetryPolicy(
            max_retries=2,
            base_delay=0.01,
            jitter=False,
        )

        result = await resilient_call(
            always_failing,
            retry_policy=policy,
            default="exhausted",
        )

        assert result == "exhausted"
        assert call_count == 3  # Initial + 2 retries

    async def test_max_retries_raises_without_default(self) -> None:
        """Test that exhausted retries raise exception when no default."""

        async def always_failing() -> str:
            raise ConnectionError("always fails")

        policy = RetryPolicy(
            max_retries=2,
            base_delay=0.01,
            jitter=False,
        )

        with pytest.raises(ConnectionError):
            await resilient_call(always_failing, retry_policy=policy)

    async def test_with_circuit_breaker(self) -> None:
        """Test resilient_call with circuit breaker."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.1,
        )

        async def success_func() -> str:
            return "success"

        result = await resilient_call(success_func, circuit_breaker=breaker)
        assert result == "success"

    async def test_circuit_breaker_open_returns_default(self) -> None:
        """Test that open circuit returns default value."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=1.0,
        )

        async def failing_func() -> str:
            raise RuntimeError("test error")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await resilient_call(failing_func, circuit_breaker=breaker)

        # Now circuit is open
        async def success_func() -> str:
            return "success"

        result = await resilient_call(
            success_func,
            circuit_breaker=breaker,
            default="circuit_open_default",
        )
        assert result == "circuit_open_default"

    async def test_circuit_breaker_open_raises_without_default(self) -> None:
        """Test that open circuit raises when no default provided."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=1.0,
        )

        async def failing_func() -> str:
            raise RuntimeError("test error")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await resilient_call(failing_func, circuit_breaker=breaker)

        async def success_func() -> str:
            return "success"

        with pytest.raises(CircuitBreakerError):
            await resilient_call(success_func, circuit_breaker=breaker)

    async def test_on_failure_callback(self) -> None:
        """Test that on_failure callback is invoked."""
        failures: list[Exception] = []

        def on_failure(exc: Exception) -> None:
            failures.append(exc)

        async def failing_func() -> str:
            raise ConnectionError("test error")

        policy = RetryPolicy(
            max_retries=2,
            base_delay=0.01,
            jitter=False,
        )

        await resilient_call(
            failing_func,
            retry_policy=policy,
            default="default",
            on_failure=on_failure,
        )

        assert len(failures) == 3  # Initial + 2 retries
        assert all(isinstance(f, ConnectionError) for f in failures)

    async def test_combined_circuit_breaker_and_retry(self) -> None:
        """Test resilient_call with both circuit breaker and retry policy."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=5,
            recovery_timeout=0.1,
        )

        policy = RetryPolicy(
            max_retries=2,
            base_delay=0.01,
            jitter=False,
        )

        call_count = 0

        async def flaky_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("temporary failure")
            return "success"

        result = await resilient_call(
            flaky_func,
            circuit_breaker=breaker,
            retry_policy=policy,
        )

        assert result == "success"
        assert call_count == 2

    async def test_circuit_breaker_fallback_used(self) -> None:
        """Test that circuit breaker fallback is used when circuit is open."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=1,
            recovery_timeout=1.0,
        )

        async def failing_func() -> str:
            raise RuntimeError("error")

        # Trip the circuit
        with pytest.raises(RuntimeError):
            await resilient_call(failing_func, circuit_breaker=breaker)

        # Circuit is open, should use default
        result = await resilient_call(
            failing_func,
            circuit_breaker=breaker,
            default="fallback",
        )
        assert result == "fallback"

    async def test_circuit_breaker_error_with_default_in_resilient_call(self) -> None:
        """Test that CircuitBreakerError returns default when provided."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=1,
            recovery_timeout=10.0,  # Long timeout so circuit stays open
        )

        async def failing_func() -> str:
            raise RuntimeError("error")

        # Trip the circuit
        with pytest.raises(RuntimeError):
            await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

        # When resilient_call catches CircuitBreakerError with default, it returns default
        async def another_func() -> str:
            return "should not be called"

        result = await resilient_call(
            another_func,
            circuit_breaker=breaker,
            default="cb_default",
        )
        assert result == "cb_default"


class TestResilienceConfig:
    """Tests for ResilienceConfig."""

    def test_default_values(self) -> None:
        """Test default ResilienceConfig values."""
        config = ResilienceConfig()

        assert config.circuit_breaker is None
        assert config.retry_policy is None
        assert config.default_on_failure is True

    def test_default_factory(self) -> None:
        """Test ResilienceConfig.default() factory method."""
        config = ResilienceConfig.default()

        assert config.circuit_breaker is not None
        assert config.circuit_breaker.name == "storage"
        assert config.circuit_breaker.failure_threshold == 5
        assert config.circuit_breaker.recovery_timeout == 30.0

        assert config.retry_policy is not None
        assert config.retry_policy.max_retries == 3
        assert config.retry_policy.base_delay == 0.1
        assert config.retry_policy.max_delay == 2.0
        assert config.retry_policy.exponential_backoff is True

        assert config.default_on_failure is True

    def test_default_factory_with_custom_name(self) -> None:
        """Test ResilienceConfig.default() with custom name."""
        config = ResilienceConfig.default(name="custom-storage")

        assert config.circuit_breaker is not None
        assert config.circuit_breaker.name == "custom-storage"

    def test_custom_config(self) -> None:
        """Test custom ResilienceConfig values."""
        breaker = CircuitBreaker(name="custom", failure_threshold=10)
        policy = RetryPolicy(max_retries=5)

        config = ResilienceConfig(
            circuit_breaker=breaker,
            retry_policy=policy,
            default_on_failure=False,
        )

        assert config.circuit_breaker is breaker
        assert config.retry_policy is policy
        assert config.default_on_failure is False


class TestCircuitBreakerEdgeCases:
    """Edge case tests for CircuitBreaker."""

    async def test_should_attempt_recovery_when_no_failure_time(self) -> None:
        """Test _should_attempt_recovery when _last_failure_time is None."""
        breaker = CircuitBreaker(name="test", failure_threshold=1)

        # Initially, _last_failure_time is None
        assert breaker._last_failure_time is None

        # Manually set state to OPEN to test recovery logic
        breaker._state = CircuitState.OPEN

        # _should_attempt_recovery should return True when _last_failure_time is None
        assert breaker._should_attempt_recovery() is True

    async def test_very_short_recovery_timeout(self) -> None:
        """Test circuit breaker with very short recovery timeout."""
        breaker = CircuitBreaker(
            name="short-timeout",
            failure_threshold=1,
            recovery_timeout=0.01,  # Increased for Windows clock resolution
        )

        async def failing_func() -> None:
            raise RuntimeError("error")

        # Open the circuit
        with pytest.raises(RuntimeError):
            await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.05)  # Increased for Windows clock resolution

        # Should be able to try again (half-open)
        async def success_func() -> str:
            return "recovered"

        result = await breaker.call(success_func)
        assert result == "recovered"

    async def test_none_fallback_vs_no_fallback(self) -> None:
        """Test that None fallback is different from no fallback."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=1,
            recovery_timeout=1.0,
        )

        async def failing_func() -> str:
            raise RuntimeError("error")

        # Open the circuit
        with pytest.raises(RuntimeError):
            await breaker.call(failing_func)

        # With fallback=None explicitly, should still raise because
        # the implementation checks `if fallback is not None`
        with pytest.raises(CircuitBreakerError):
            await breaker.call(failing_func, fallback=None)

    async def test_exception_propagation(self) -> None:
        """Test that original exception is propagated correctly."""
        breaker = CircuitBreaker(name="test", failure_threshold=5)

        class CustomError(Exception):
            def __init__(self, message: str, code: int) -> None:
                super().__init__(message)
                self.code = code

        async def failing_func() -> None:
            raise CustomError("custom error", 42)

        with pytest.raises(CustomError) as exc_info:
            await breaker.call(failing_func)

        assert exc_info.value.code == 42
        assert "custom error" in str(exc_info.value)


class TestRetryPolicyEdgeCases:
    """Edge case tests for RetryPolicy."""

    def test_zero_max_retries(self) -> None:
        """Test retry policy with zero retries."""
        policy = RetryPolicy(max_retries=0)

        # Even with zero retries, should_retry still works
        assert policy.should_retry(ConnectionError()) is True

    def test_very_large_attempt_number(self) -> None:
        """Test delay calculation with large attempt number."""
        policy = RetryPolicy(
            base_delay=0.1,
            max_delay=5.0,
            exponential_backoff=True,
            jitter=False,
        )

        # Very large attempt should still be capped at max_delay
        delay = policy.get_delay(100)
        assert delay == 5.0

    def test_empty_retryable_exceptions(self) -> None:
        """Test retry policy with no retryable exceptions."""
        policy = RetryPolicy(retryable_exceptions=())

        # Nothing is retryable
        assert policy.should_retry(ConnectionError()) is False
        assert policy.should_retry(TimeoutError()) is False
        assert policy.should_retry(RuntimeError()) is False

    def test_subclass_exception_handling(self) -> None:
        """Test that subclass exceptions are matched."""
        policy = RetryPolicy(retryable_exceptions=(OSError,))

        # ConnectionError is a subclass of OSError
        assert policy.should_retry(ConnectionError("test")) is True
        # FileNotFoundError is also a subclass of OSError
        assert policy.should_retry(FileNotFoundError("test")) is True


class TestResilientCallEdgeCases:
    """Edge case tests for resilient_call."""

    async def test_function_returning_none(self) -> None:
        """Test that function returning None works correctly."""

        async def returns_none() -> None:
            return None

        result = await resilient_call(returns_none)
        assert result is None

    async def test_default_none_with_successful_call(self) -> None:
        """Test that successful call doesn't use default."""

        async def success_func() -> str:
            return "actual_value"

        result = await resilient_call(success_func, default="default")
        assert result == "actual_value"

    async def test_async_generator_exception_handling(self) -> None:
        """Test handling of exceptions in async functions."""

        async def async_failing() -> str:
            await asyncio.sleep(0.001)
            raise TimeoutError("async timeout")

        policy = RetryPolicy(
            max_retries=1,
            base_delay=0.01,
            jitter=False,
        )

        result = await resilient_call(
            async_failing,
            retry_policy=policy,
            default="timeout_default",
        )
        assert result == "timeout_default"


class TestIntegrationScenarios:
    """Integration tests for realistic scenarios."""

    async def test_database_connection_scenario(self) -> None:
        """Simulate database connection with transient failures."""
        connection_attempts = 0

        async def connect_to_database() -> dict:
            nonlocal connection_attempts
            connection_attempts += 1

            # Simulate transient failures then success
            if connection_attempts < 3:
                raise ConnectionError("Database connection failed")

            return {"status": "connected", "host": "localhost"}

        breaker = CircuitBreaker(
            name="database",
            failure_threshold=5,
            recovery_timeout=1.0,
        )

        policy = RetryPolicy(
            max_retries=3,
            base_delay=0.01,
            jitter=False,
        )

        result = await resilient_call(
            connect_to_database,
            circuit_breaker=breaker,
            retry_policy=policy,
        )

        assert result["status"] == "connected"
        assert connection_attempts == 3

    async def test_api_call_with_circuit_breaker(self) -> None:
        """Simulate API calls with circuit breaker protection."""
        api_calls = 0
        breaker = CircuitBreaker(
            name="api",
            failure_threshold=3,
            recovery_timeout=0.1,
            success_threshold=2,
        )

        async def call_api() -> dict:
            nonlocal api_calls
            api_calls += 1
            raise TimeoutError("API timeout")

        # Exhaust the circuit breaker
        for _ in range(3):
            with pytest.raises(TimeoutError):
                await breaker.call(call_api)

        assert breaker.state == CircuitState.OPEN
        assert api_calls == 3

        # Circuit is open, should return default
        result = await resilient_call(
            call_api,
            circuit_breaker=breaker,
            default={"status": "unavailable"},
        )
        assert result["status"] == "unavailable"

        # Wait for recovery
        await asyncio.sleep(0.15)

        # Now let API succeed
        async def successful_api() -> dict:
            return {"status": "ok"}

        # Need success_threshold successes to fully close
        for _ in range(breaker.success_threshold):
            result = await breaker.call(successful_api)
            assert result["status"] == "ok"

        assert breaker.state == CircuitState.CLOSED

    async def test_feature_flag_storage_scenario(self) -> None:
        """Simulate feature flag storage with resilience."""
        storage_available = False
        call_count = 0

        async def get_flag_from_storage() -> bool:
            nonlocal call_count
            call_count += 1

            if not storage_available:
                raise ConnectionError("Storage unavailable")

            return True

        config = ResilienceConfig.default(name="flag-storage")
        # Override with test-friendly settings
        config.circuit_breaker = CircuitBreaker(
            name="flag-storage",
            failure_threshold=2,
            recovery_timeout=0.1,
        )
        config.retry_policy = RetryPolicy(
            max_retries=1,
            base_delay=0.01,
            jitter=False,
        )

        # First call should retry and return default
        result = await resilient_call(
            get_flag_from_storage,
            circuit_breaker=config.circuit_breaker,
            retry_policy=config.retry_policy,
            default=False,
        )
        assert result is False
        assert call_count == 2  # Initial + 1 retry

        # More failures to open circuit
        result = await resilient_call(
            get_flag_from_storage,
            circuit_breaker=config.circuit_breaker,
            retry_policy=config.retry_policy,
            default=False,
        )

        assert config.circuit_breaker.state == CircuitState.OPEN

        # Now storage becomes available
        storage_available = True

        # Wait for recovery
        await asyncio.sleep(0.15)

        # Should now succeed
        result = await resilient_call(
            get_flag_from_storage,
            circuit_breaker=config.circuit_breaker,
            retry_policy=config.retry_policy,
            default=False,
        )
        assert result is True
