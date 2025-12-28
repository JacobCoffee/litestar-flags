"""Resilience patterns for graceful degradation.

This module provides circuit breaker and retry patterns for handling
failures in storage backend operations, ensuring the feature flags
system degrades gracefully under adverse conditions.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerError",
    "CircuitState",
    "RetryPolicy",
    "resilient_call",
]

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    """States of the circuit breaker.

    Attributes:
        CLOSED: Normal operation, requests are allowed through.
        OPEN: Circuit is tripped, requests are blocked.
        HALF_OPEN: Testing if the service has recovered.

    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    """Raised when the circuit breaker is open and blocking requests.

    Attributes:
        circuit_name: Name of the circuit breaker.
        state: Current state of the circuit.
        recovery_time: Seconds until recovery attempt.

    """

    def __init__(
        self,
        circuit_name: str,
        state: CircuitState,
        recovery_time: float | None = None,
    ) -> None:
        self.circuit_name = circuit_name
        self.state = state
        self.recovery_time = recovery_time
        message = f"Circuit '{circuit_name}' is {state.value}"
        if recovery_time is not None and recovery_time > 0:
            message += f", recovery in {recovery_time:.1f}s"
        super().__init__(message)


class CircuitBreaker:
    """Circuit breaker pattern implementation for fault tolerance.

    The circuit breaker monitors failures and opens the circuit when
    the failure threshold is exceeded, preventing cascading failures
    and allowing the system to recover.

    States:
        - CLOSED: Normal operation, requests pass through
        - OPEN: Circuit tripped, requests fail immediately
        - HALF_OPEN: Testing recovery, single request allowed

    Attributes:
        name: Identifier for this circuit breaker.
        failure_threshold: Consecutive failures before opening.
        recovery_timeout: Seconds to wait before attempting recovery.
        success_threshold: Successful calls in half-open before closing.

    Example:
        >>> breaker = CircuitBreaker(
        ...     name="storage",
        ...     failure_threshold=5,
        ...     recovery_timeout=30.0,
        ... )
        >>> async def fetch_data():
        ...     return await storage.get_flag("key")
        >>> result = await breaker.call(fetch_data)

    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2,
    ) -> None:
        """Initialize the circuit breaker.

        Args:
            name: Identifier for this circuit breaker.
            failure_threshold: Number of consecutive failures before opening.
            recovery_timeout: Seconds to wait before attempting recovery.
            success_threshold: Successful calls needed to close from half-open.

        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Get the current circuit state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Get the current consecutive failure count."""
        return self._failure_count

    @property
    def is_closed(self) -> bool:
        """Check if the circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if the circuit is open (blocking requests)."""
        return self._state == CircuitState.OPEN

    @property
    def time_until_recovery(self) -> float | None:
        """Get seconds until recovery attempt, or None if not applicable."""
        if self._state != CircuitState.OPEN or self._last_failure_time is None:
            return None
        elapsed = time.monotonic() - self._last_failure_time
        remaining = self.recovery_timeout - elapsed
        return max(0.0, remaining)

    async def call(
        self,
        func: Callable[[], Awaitable[T]],
        fallback: T | None = None,
    ) -> T:
        """Execute a function through the circuit breaker.

        Args:
            func: Async function to execute.
            fallback: Value to return if circuit is open (if None, raises).

        Returns:
            The result of the function call.

        Raises:
            CircuitBreakerError: If circuit is open and no fallback provided.
            Exception: Any exception from the wrapped function.

        """
        async with self._lock:
            # Check if we should attempt recovery
            if self._state == CircuitState.OPEN:
                if self._should_attempt_recovery():
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    logger.info(f"Circuit '{self.name}' entering half-open state")
                else:
                    if fallback is not None:
                        return fallback
                    raise CircuitBreakerError(
                        self.name,
                        self._state,
                        self.time_until_recovery,
                    )

        try:
            result = await func()
            await self._record_success()
            return result
        except Exception as e:
            await self._record_failure()
            raise e

    async def _record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info(f"Circuit '{self.name}' closed after recovery")
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success in closed state
                self._failure_count = 0

    async def _record_failure(self) -> None:
        """Record a failed call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Single failure in half-open reopens the circuit
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit '{self.name}' reopened after failed recovery")
            elif self._state == CircuitState.CLOSED and self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit '{self.name}' opened after {self._failure_count} failures")

    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self._last_failure_time is None:
            return True
        elapsed = time.monotonic() - self._last_failure_time
        return elapsed >= self.recovery_timeout

    async def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            logger.info(f"Circuit '{self.name}' manually reset")

    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics.

        Returns:
            Dictionary with current state and metrics.

        """
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "time_until_recovery": self.time_until_recovery,
        }


@dataclass
class RetryPolicy:
    """Configuration for retry behavior with exponential backoff.

    Attributes:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay between retries in seconds.
        max_delay: Maximum delay between retries in seconds.
        exponential_backoff: Whether to use exponential backoff.
        jitter: Whether to add random jitter to delays.
        retryable_exceptions: Exception types that should trigger retry.

    Example:
        >>> policy = RetryPolicy(
        ...     max_retries=3,
        ...     base_delay=0.1,
        ...     exponential_backoff=True,
        ... )
        >>> # Delays: 0.1s, 0.2s, 0.4s

    """

    max_retries: int = 3
    base_delay: float = 0.1
    max_delay: float = 2.0
    exponential_backoff: bool = True
    jitter: bool = True
    retryable_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: (ConnectionError, TimeoutError, OSError)
    )

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given retry attempt.

        Args:
            attempt: The retry attempt number (0-indexed).

        Returns:
            Delay in seconds before the next retry.

        """
        if self.exponential_backoff:
            delay = self.base_delay * (2**attempt)
        else:
            delay = self.base_delay

        delay = min(delay, self.max_delay)

        if self.jitter:
            import random

            # Add up to 25% jitter
            jitter_amount = delay * 0.25 * random.random()  # noqa: S311
            delay += jitter_amount

        return delay

    def should_retry(self, exception: Exception) -> bool:
        """Check if an exception should trigger a retry.

        Args:
            exception: The exception that occurred.

        Returns:
            True if the exception is retryable.

        """
        return isinstance(exception, self.retryable_exceptions)


async def resilient_call(
    func: Callable[[], Awaitable[T]],
    *,
    circuit_breaker: CircuitBreaker | None = None,
    retry_policy: RetryPolicy | None = None,
    default: T | None = None,
    on_failure: Callable[[Exception], None] | None = None,
) -> T:
    """Execute an async function with resilience patterns.

    Combines circuit breaker and retry logic to provide fault-tolerant
    execution of storage operations. On persistent failure, returns the
    default value if provided.

    Args:
        func: Async function to execute.
        circuit_breaker: Optional circuit breaker for failure isolation.
        retry_policy: Optional retry policy for transient failures.
        default: Value to return on persistent failure.
        on_failure: Callback invoked on each failure.

    Returns:
        The result of the function, or default on failure.

    Raises:
        Exception: If no default provided and all attempts fail.

    Example:
        >>> breaker = CircuitBreaker(name="storage")
        >>> policy = RetryPolicy(max_retries=3)
        >>> async def get_flag():
        ...     return await storage.get_flag("my-feature")
        >>> result = await resilient_call(
        ...     get_flag,
        ...     circuit_breaker=breaker,
        ...     retry_policy=policy,
        ...     default=None,
        ... )

    """
    last_exception: Exception | None = None
    max_attempts = (retry_policy.max_retries + 1) if retry_policy else 1

    for attempt in range(max_attempts):
        try:
            if circuit_breaker:
                return await circuit_breaker.call(func, fallback=default)
            return await func()

        except CircuitBreakerError:
            # Circuit is open, return default if available
            if default is not None:
                return default
            raise

        except Exception as e:
            last_exception = e

            if on_failure:
                on_failure(e)

            # Check if we should retry
            if retry_policy and attempt < retry_policy.max_retries:
                if retry_policy.should_retry(e):
                    delay = retry_policy.get_delay(attempt)
                    logger.debug(f"Retry {attempt + 1}/{retry_policy.max_retries} after {delay:.2f}s: {e}")
                    await asyncio.sleep(delay)
                    continue

            # No more retries, check for default
            if default is not None:
                logger.warning(f"All retries exhausted, returning default: {e}")
                return default

            raise

    # Should not reach here, but handle edge case
    if last_exception:
        raise last_exception
    if default is not None:
        return default
    raise RuntimeError("Unexpected state in resilient_call")


@dataclass
class ResilienceConfig:
    """Combined configuration for resilience patterns.

    Attributes:
        circuit_breaker: Circuit breaker instance.
        retry_policy: Retry policy configuration.
        default_on_failure: Whether to return defaults on failure.

    """

    circuit_breaker: CircuitBreaker | None = None
    retry_policy: RetryPolicy | None = None
    default_on_failure: bool = True

    @classmethod
    def default(cls, name: str = "storage") -> ResilienceConfig:
        """Create a default resilience configuration.

        Args:
            name: Name for the circuit breaker.

        Returns:
            ResilienceConfig with sensible defaults.

        """
        return cls(
            circuit_breaker=CircuitBreaker(
                name=name,
                failure_threshold=5,
                recovery_timeout=30.0,
            ),
            retry_policy=RetryPolicy(
                max_retries=3,
                base_delay=0.1,
                max_delay=2.0,
                exponential_backoff=True,
            ),
            default_on_failure=True,
        )
