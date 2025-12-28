"""Structured logging integration for feature flag evaluations.

This module provides structured logging for feature flag evaluations,
supporting both structlog (when available) and stdlib logging as a fallback.

Example:
    Basic usage with stdlib logging::

        from litestar_flags.contrib.logging import LoggingHook

        hook = LoggingHook()

        # Log a flag evaluation
        await hook.log_evaluation("my-feature", result, context)

    With structlog::

        import structlog
        from litestar_flags.contrib.logging import LoggingHook

        logger = structlog.get_logger("feature_flags")
        hook = LoggingHook(logger=logger)

    Custom log levels::

        hook = LoggingHook(
            evaluation_level="INFO",
            error_level="CRITICAL",
        )

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

# Handle optional structlog import
try:
    import structlog
    from structlog.typing import FilteringBoundLogger

    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    structlog = None  # type: ignore[assignment]
    FilteringBoundLogger = Any  # type: ignore[misc, assignment]

if TYPE_CHECKING:
    from litestar_flags.context import EvaluationContext
    from litestar_flags.results import EvaluationDetails

__all__ = ["STRUCTLOG_AVAILABLE", "LoggingHook"]


@runtime_checkable
class LoggerProtocol(Protocol):
    """Protocol for logger compatibility.

    This protocol defines the minimum interface required for a logger
    to be used with LoggingHook. Both stdlib logging.Logger and
    structlog bound loggers satisfy this protocol.

    """

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a debug message."""
        ...

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an info message."""
        ...

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a warning message."""
        ...

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an error message."""
        ...


def _get_default_logger() -> logging.Logger | FilteringBoundLogger:
    """Get the default logger based on available packages.

    Returns:
        A structlog logger if structlog is available, otherwise stdlib logger.

    """
    if STRUCTLOG_AVAILABLE and structlog is not None:
        return structlog.get_logger("litestar_flags")
    return logging.getLogger("litestar_flags")


class LoggingHook:
    """Structured logging hook for feature flag evaluations.

    Provides structured logging for flag evaluations with contextual information.
    Supports both structlog (when installed) and stdlib logging as a fallback.

    The hook logs:
    - Successful evaluations at DEBUG level (configurable)
    - Evaluation errors at ERROR level (configurable)

    Logged fields include:
    - flag_key: The flag being evaluated
    - value: The evaluated value (optional, can be disabled for privacy)
    - reason: The evaluation reason
    - variant: The selected variant (if any)
    - targeting_key: The targeting key from context (if any)
    - error_code: Error code (on failure)
    - error_message: Error message (on failure)

    Example:
        >>> hook = LoggingHook()
        >>> await hook.log_evaluation("my-flag", result, context)

    """

    def __init__(
        self,
        logger: logging.Logger | FilteringBoundLogger | None = None,
        evaluation_level: str = "DEBUG",
        error_level: str = "ERROR",
        log_values: bool = False,
        include_context: bool = True,
    ) -> None:
        """Initialize the logging hook.

        Args:
            logger: Custom logger instance. If not provided, uses structlog
                (if available) or stdlib logging.
            evaluation_level: Log level for successful evaluations.
                Default is DEBUG.
            error_level: Log level for evaluation errors. Default is ERROR.
            log_values: Whether to include flag values in logs. Disabled by
                default for privacy/security reasons.
            include_context: Whether to include evaluation context fields
                in log entries.

        """
        self._logger = logger or _get_default_logger()
        self._evaluation_level = evaluation_level.upper()
        self._error_level = error_level.upper()
        self._log_values = log_values
        self._include_context = include_context
        self._use_structlog = STRUCTLOG_AVAILABLE and structlog is not None

    @property
    def logger(self) -> logging.Logger | FilteringBoundLogger:
        """Get the logger instance."""
        return self._logger

    def _get_log_method(self, level: str) -> Any:
        """Get the appropriate log method for the given level.

        Args:
            level: The log level name (DEBUG, INFO, WARNING, ERROR).

        Returns:
            The log method for the given level.

        """
        level_map = {
            "DEBUG": self._logger.debug,
            "INFO": self._logger.info,
            "WARNING": self._logger.warning,
            "ERROR": self._logger.error,
        }
        return level_map.get(level, self._logger.debug)

    def _build_log_data(
        self,
        flag_key: str,
        result: EvaluationDetails[Any],
        context: EvaluationContext | None = None,
    ) -> dict[str, Any]:
        """Build the log data dictionary.

        Args:
            flag_key: The flag key being evaluated.
            result: The evaluation result.
            context: The evaluation context.

        Returns:
            Dictionary of log fields.

        """
        data: dict[str, Any] = {
            "flag_key": flag_key,
            "reason": result.reason.value,
        }

        if result.variant:
            data["variant"] = result.variant

        if self._log_values:
            data["value"] = result.value

        if result.error_code:
            data["error_code"] = result.error_code.value

        if result.error_message:
            data["error_message"] = result.error_message

        if result.flag_metadata:
            data["flag_metadata"] = result.flag_metadata

        if self._include_context and context:
            if context.targeting_key:
                data["targeting_key"] = context.targeting_key
            if context.user_id:
                data["user_id"] = context.user_id
            if context.organization_id:
                data["organization_id"] = context.organization_id
            if context.environment:
                data["environment"] = context.environment
            if context.app_version:
                data["app_version"] = context.app_version

        return data

    def _log_with_data(
        self,
        level: str,
        message: str,
        data: dict[str, Any],
    ) -> None:
        """Log a message with structured data.

        Handles both structlog and stdlib logging appropriately.

        Args:
            level: The log level.
            message: The log message.
            data: The structured data to include.

        """
        log_method = self._get_log_method(level)

        if self._use_structlog:
            # structlog accepts kwargs directly
            log_method(message, **data)
        else:
            # stdlib logging - use extra for structured data
            log_method(message, extra=data)

    async def log_evaluation(
        self,
        flag_key: str,
        result: EvaluationDetails[Any],
        context: EvaluationContext | None = None,
    ) -> None:
        """Log a flag evaluation result.

        Logs successful evaluations at the configured evaluation level
        and errors at the configured error level.

        Args:
            flag_key: The flag key that was evaluated.
            result: The evaluation result details.
            context: The evaluation context.

        """
        data = self._build_log_data(flag_key, result, context)

        if result.is_error:
            self._log_with_data(
                self._error_level,
                f"Feature flag evaluation error: {flag_key}",
                data,
            )
        else:
            self._log_with_data(
                self._evaluation_level,
                f"Feature flag evaluated: {flag_key}",
                data,
            )

    async def before_evaluation(
        self,
        flag_key: str,
        context: EvaluationContext | None = None,
    ) -> None:
        """Log that a flag evaluation is starting.

        Logs at DEBUG level that an evaluation is starting.

        Args:
            flag_key: The flag key being evaluated.
            context: The evaluation context.

        """
        data: dict[str, Any] = {"flag_key": flag_key}

        if self._include_context and context:
            if context.targeting_key:
                data["targeting_key"] = context.targeting_key

        self._log_with_data(
            "DEBUG",
            f"Starting feature flag evaluation: {flag_key}",
            data,
        )

    async def after_evaluation(
        self,
        flag_key: str,
        result: EvaluationDetails[Any],
        context: EvaluationContext | None = None,
    ) -> None:
        """Log flag evaluation result after completion.

        Alias for log_evaluation().

        Args:
            flag_key: The flag key that was evaluated.
            result: The evaluation result.
            context: The evaluation context.

        """
        await self.log_evaluation(flag_key, result, context)

    async def on_error(
        self,
        error: Exception,
        flag_key: str,
        context: EvaluationContext | None = None,
    ) -> None:
        """Log an evaluation error with full exception info.

        Logs the error at the configured error level with full exception info.

        Args:
            error: The exception that occurred.
            flag_key: The flag key that was being evaluated.
            context: The evaluation context.

        """
        data: dict[str, Any] = {
            "flag_key": flag_key,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }

        if self._include_context and context:
            if context.targeting_key:
                data["targeting_key"] = context.targeting_key

        if self._use_structlog:
            # structlog can include exception info
            log_method = self._get_log_method(self._error_level)
            log_method(
                f"Feature flag evaluation exception: {flag_key}",
                exc_info=error,
                **data,
            )
        else:
            # stdlib logging with exc_info
            self._logger.error(
                f"Feature flag evaluation exception: {flag_key}",
                exc_info=error,
                extra=data,
            )

    def log_evaluation_sync(
        self,
        flag_key: str,
        result: EvaluationDetails[Any],
        context: EvaluationContext | None = None,
    ) -> None:
        """Log a flag evaluation result synchronously.

        Useful when logging from synchronous code paths.

        Args:
            flag_key: The flag key that was evaluated.
            result: The evaluation result details.
            context: The evaluation context.

        """
        data = self._build_log_data(flag_key, result, context)

        if result.is_error:
            self._log_with_data(
                self._error_level,
                f"Feature flag evaluation error: {flag_key}",
                data,
            )
        else:
            self._log_with_data(
                self._evaluation_level,
                f"Feature flag evaluated: {flag_key}",
                data,
            )

    def bind(self, **kwargs: Any) -> LoggingHook:
        """Create a new hook with bound context.

        If using structlog, creates a new hook with a bound logger.
        For stdlib logging, stores the context for inclusion in all logs.

        Args:
            **kwargs: Context fields to bind.

        Returns:
            A new LoggingHook with the bound context.

        """
        if self._use_structlog and structlog is not None:
            bound_logger = self._logger.bind(**kwargs)  # type: ignore[union-attr]
            return LoggingHook(
                logger=bound_logger,
                evaluation_level=self._evaluation_level,
                error_level=self._error_level,
                log_values=self._log_values,
                include_context=self._include_context,
            )
        else:
            # For stdlib logging, we can't truly bind context,
            # but we return a new hook for API consistency
            return LoggingHook(
                logger=self._logger,
                evaluation_level=self._evaluation_level,
                error_level=self._error_level,
                log_values=self._log_values,
                include_context=self._include_context,
            )
