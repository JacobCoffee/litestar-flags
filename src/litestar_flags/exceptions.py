"""Custom exceptions for litestar-flags."""

from __future__ import annotations

__all__ = [
    "ConfigurationError",
    "FeatureFlagError",
    "FlagNotFoundError",
    "RateLimitExceededError",
    "StorageError",
]


class FeatureFlagError(Exception):
    """Base exception for feature flag errors."""

    pass


class FlagNotFoundError(FeatureFlagError):
    """Raised when a feature flag is not found."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Feature flag '{key}' not found")


class StorageError(FeatureFlagError):
    """Raised when a storage operation fails."""

    pass


class ConfigurationError(FeatureFlagError):
    """Raised when configuration is invalid."""

    pass


class RateLimitExceededError(FeatureFlagError):
    """Raised when rate limit for flag evaluations is exceeded.

    Attributes:
        message: Description of the rate limit violation.
        wait_time: Suggested time to wait before retrying (in seconds).
        flag_key: The flag key that triggered the limit (if per-flag limit).

    Example:
        >>> try:
        ...     await rate_limiter.acquire("my-flag")
        ... except RateLimitExceededError as e:
        ...     print(f"Rate limited. Retry after {e.wait_time}s")

    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        wait_time: float | None = None,
        flag_key: str | None = None,
    ) -> None:
        """Initialize the rate limit exception.

        Args:
            message: Description of the rate limit violation.
            wait_time: Suggested time to wait before retrying.
            flag_key: The flag key that triggered the limit.

        """
        self.wait_time = wait_time
        self.flag_key = flag_key
        super().__init__(message)
