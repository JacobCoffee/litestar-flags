"""Rate limiting for feature flag evaluations.

This module provides rate limiting functionality to control the throughput
of flag evaluations, preventing abuse and ensuring fair resource usage.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from litestar_flags.exceptions import RateLimitExceededError

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "RateLimitConfig",
    "RateLimitHook",
    "RateLimiter",
    "TokenBucketRateLimiter",
]

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RateLimitConfig:
    """Configuration for rate limiting flag evaluations.

    Attributes:
        max_evaluations_per_second: Maximum evaluations per second globally.
        max_evaluations_per_minute: Maximum evaluations per minute globally.
        per_flag_limits: Optional per-flag rate limits (evaluations per second).
        burst_multiplier: Multiplier for burst capacity above the rate limit.

    Example:
        >>> config = RateLimitConfig(
        ...     max_evaluations_per_second=1000,
        ...     max_evaluations_per_minute=50000,
        ...     per_flag_limits={"expensive-flag": 10.0},
        ... )

    """

    max_evaluations_per_second: float = 1000.0
    max_evaluations_per_minute: float = 50000.0
    per_flag_limits: dict[str, float] | None = None
    burst_multiplier: float = 1.5


@runtime_checkable
class RateLimiter(Protocol):
    """Protocol for rate limiter implementations.

    All rate limiter implementations must implement this protocol.
    """

    async def acquire(self, flag_key: str | None = None) -> None:
        """Acquire permission to evaluate a flag.

        Args:
            flag_key: Optional flag key for per-flag rate limiting.

        Raises:
            RateLimitExceededError: If the rate limit has been exceeded.

        """
        ...

    async def try_acquire(self, flag_key: str | None = None) -> bool:
        """Try to acquire permission without blocking.

        Args:
            flag_key: Optional flag key for per-flag rate limiting.

        Returns:
            True if permission was granted, False if rate limit exceeded.

        """
        ...

    def get_stats(self) -> dict[str, float]:
        """Get current rate limiting statistics.

        Returns:
            Dictionary containing rate limit statistics.

        """
        ...


@dataclass(slots=True)
class _TokenBucket:
    """Token bucket for rate limiting.

    Implements the token bucket algorithm for smooth rate limiting
    with support for bursting.
    """

    rate: float  # Tokens per second
    capacity: float  # Maximum tokens
    tokens: float = field(init=False)
    last_update: float = field(init=False, default_factory=time.monotonic)

    def __post_init__(self) -> None:
        """Initialize with full capacity."""
        self.tokens = self.capacity

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume.

        Returns:
            True if tokens were consumed, False if insufficient tokens.

        """
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def time_until_available(self, tokens: float = 1.0) -> float:
        """Calculate time until tokens will be available.

        Args:
            tokens: Number of tokens needed.

        Returns:
            Time in seconds until tokens will be available.

        """
        self._refill()
        if self.tokens >= tokens:
            return 0.0
        needed = tokens - self.tokens
        return needed / self.rate


class TokenBucketRateLimiter:
    """Token bucket rate limiter for flag evaluations.

    Implements the token bucket algorithm for smooth rate limiting with
    support for per-flag limits and bursting. This rate limiter is
    async-safe and can be used concurrently.

    Example:
        >>> config = RateLimitConfig(max_evaluations_per_second=1000)
        >>> limiter = TokenBucketRateLimiter(config)
        >>> await limiter.acquire("my-flag")  # Acquire permission

    """

    def __init__(self, config: RateLimitConfig) -> None:
        """Initialize the rate limiter.

        Args:
            config: Rate limiting configuration.

        """
        self._config = config
        self._lock = asyncio.Lock()

        # Global rate limiters (per-second and per-minute)
        burst_capacity_sec = config.max_evaluations_per_second * config.burst_multiplier
        self._global_bucket_sec = _TokenBucket(
            rate=config.max_evaluations_per_second,
            capacity=burst_capacity_sec,
        )

        burst_capacity_min = config.max_evaluations_per_minute * config.burst_multiplier
        self._global_bucket_min = _TokenBucket(
            rate=config.max_evaluations_per_minute / 60.0,  # Convert to per-second
            capacity=burst_capacity_min,
        )

        # Per-flag rate limiters
        self._flag_buckets: dict[str, _TokenBucket] = {}

        # Statistics
        self._total_requests: int = 0
        self._rejected_requests: int = 0
        self._last_rejection_time: float | None = None

    @property
    def config(self) -> RateLimitConfig:
        """Get the rate limit configuration."""
        return self._config

    def _get_flag_bucket(self, flag_key: str) -> _TokenBucket | None:
        """Get or create a per-flag rate limiter bucket.

        Args:
            flag_key: The flag key.

        Returns:
            Token bucket for the flag, or None if no per-flag limit.

        """
        if self._config.per_flag_limits is None:
            return None

        limit = self._config.per_flag_limits.get(flag_key)
        if limit is None:
            return None

        if flag_key not in self._flag_buckets:
            burst_capacity = limit * self._config.burst_multiplier
            self._flag_buckets[flag_key] = _TokenBucket(
                rate=limit,
                capacity=burst_capacity,
            )

        return self._flag_buckets[flag_key]

    async def acquire(self, flag_key: str | None = None) -> None:
        """Acquire permission to evaluate a flag.

        This method will raise RateLimitExceededError if the rate limit has
        been exceeded. Use try_acquire() if you want to handle rate
        limiting without exceptions.

        Args:
            flag_key: Optional flag key for per-flag rate limiting.

        Raises:
            RateLimitExceededError: If the rate limit has been exceeded.

        """
        async with self._lock:
            self._total_requests += 1

            # Check global per-second limit
            if not self._global_bucket_sec.consume():
                self._rejected_requests += 1
                self._last_rejection_time = time.monotonic()
                wait_time = self._global_bucket_sec.time_until_available()
                raise RateLimitExceededError(
                    f"Global per-second rate limit exceeded. Retry after {wait_time:.2f}s",
                    wait_time=wait_time,
                )

            # Check global per-minute limit
            if not self._global_bucket_min.consume():
                self._rejected_requests += 1
                self._last_rejection_time = time.monotonic()
                wait_time = self._global_bucket_min.time_until_available()
                raise RateLimitExceededError(
                    f"Global per-minute rate limit exceeded. Retry after {wait_time:.2f}s",
                    wait_time=wait_time,
                )

            # Check per-flag limit if applicable
            if flag_key is not None:
                flag_bucket = self._get_flag_bucket(flag_key)
                if flag_bucket is not None and not flag_bucket.consume():
                    self._rejected_requests += 1
                    self._last_rejection_time = time.monotonic()
                    wait_time = flag_bucket.time_until_available()
                    raise RateLimitExceededError(
                        f"Per-flag rate limit exceeded for '{flag_key}'. Retry after {wait_time:.2f}s",
                        wait_time=wait_time,
                        flag_key=flag_key,
                    )

    async def try_acquire(self, flag_key: str | None = None) -> bool:
        """Try to acquire permission without raising exceptions.

        Args:
            flag_key: Optional flag key for per-flag rate limiting.

        Returns:
            True if permission was granted, False if rate limit exceeded.

        """
        try:
            await self.acquire(flag_key)
            return True
        except RateLimitExceededError:
            return False

    async def wait_and_acquire(
        self,
        flag_key: str | None = None,
        timeout: float | None = None,
    ) -> bool:
        """Wait for rate limit to allow acquisition, then acquire.

        Args:
            flag_key: Optional flag key for per-flag rate limiting.
            timeout: Maximum time to wait in seconds. None means wait forever.

        Returns:
            True if acquired successfully, False if timeout exceeded.

        """
        start_time = time.monotonic()

        while True:
            try:
                await self.acquire(flag_key)
                return True
            except RateLimitExceededError as e:
                if timeout is not None:
                    elapsed = time.monotonic() - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        return False
                    wait_time = min(e.wait_time or 0.1, remaining)
                else:
                    wait_time = e.wait_time or 0.1

                await asyncio.sleep(wait_time)

    def get_stats(self) -> dict[str, float]:
        """Get current rate limiting statistics.

        Returns:
            Dictionary containing:
            - total_requests: Total number of acquire requests
            - rejected_requests: Number of requests rejected due to rate limit
            - rejection_rate: Percentage of rejected requests
            - global_tokens_sec: Current tokens in per-second bucket
            - global_tokens_min: Current tokens in per-minute bucket

        """
        rejection_rate = (self._rejected_requests / self._total_requests * 100) if self._total_requests > 0 else 0.0

        return {
            "total_requests": float(self._total_requests),
            "rejected_requests": float(self._rejected_requests),
            "rejection_rate": rejection_rate,
            "global_tokens_sec": self._global_bucket_sec.tokens,
            "global_tokens_min": self._global_bucket_min.tokens,
        }

    def reset_stats(self) -> None:
        """Reset rate limiting statistics."""
        self._total_requests = 0
        self._rejected_requests = 0
        self._last_rejection_time = None


@dataclass
class RateLimitHook:
    """Hook for integrating rate limiting into the evaluation pipeline.

    This hook checks rate limits before evaluation and tracks evaluation
    counts. It can emit metrics when limits are approached.

    Attributes:
        rate_limiter: The rate limiter to use.
        warning_threshold: Percentage of limit at which to emit warnings.
        on_limit_approached: Callback when limit is being approached.
        on_limit_exceeded: Callback when limit is exceeded.

    Example:
        >>> limiter = TokenBucketRateLimiter(config)
        >>> hook = RateLimitHook(
        ...     rate_limiter=limiter,
        ...     warning_threshold=0.8,
        ...     on_limit_approached=lambda stats: print(f"Warning: {stats}"),
        ... )
        >>> await hook.before_evaluation("my-flag")

    """

    rate_limiter: RateLimiter
    warning_threshold: float = 0.8
    on_limit_approached: Callable[[dict[str, float]], None] | None = None
    on_limit_exceeded: Callable[[str, RateLimitExceededError], None] | None = None

    _evaluation_count: int = field(default=0, init=False, repr=False)
    _last_warning_time: float | None = field(default=None, init=False, repr=False)
    _warning_cooldown: float = field(default=60.0, init=False, repr=False)

    async def before_evaluation(self, flag_key: str) -> None:
        """Check rate limits before flag evaluation.

        Args:
            flag_key: The flag key being evaluated.

        Raises:
            RateLimitExceededError: If the rate limit has been exceeded.

        """
        self._evaluation_count += 1

        # Check if we should emit a warning
        self._check_and_emit_warning()

        try:
            await self.rate_limiter.acquire(flag_key)
        except RateLimitExceededError as e:
            if self.on_limit_exceeded is not None:
                self.on_limit_exceeded(flag_key, e)
            raise

    def _check_and_emit_warning(self) -> None:
        """Check rate limit stats and emit warning if threshold exceeded."""
        if self.on_limit_approached is None:
            return

        # Apply cooldown to avoid spamming warnings
        now = time.monotonic()
        if self._last_warning_time is not None and now - self._last_warning_time < self._warning_cooldown:
            return

        stats = self.rate_limiter.get_stats()

        # Check if rejection rate is approaching threshold
        if stats.get("rejection_rate", 0) >= self.warning_threshold * 100:
            self._last_warning_time = now
            self.on_limit_approached(stats)
            logger.warning(f"Rate limit warning: rejection rate at {stats['rejection_rate']:.1f}%")

    def after_evaluation(self, flag_key: str, success: bool) -> None:
        """Handle post-evaluation tracking.

        Args:
            flag_key: The flag key that was evaluated.
            success: Whether the evaluation was successful.

        """
        # This hook can be extended for additional tracking/metrics
        pass

    def get_evaluation_count(self) -> int:
        """Get the total number of evaluations tracked.

        Returns:
            Total evaluation count.

        """
        return self._evaluation_count

    def reset_count(self) -> None:
        """Reset the evaluation counter."""
        self._evaluation_count = 0
