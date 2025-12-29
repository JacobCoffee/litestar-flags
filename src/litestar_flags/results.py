"""Evaluation results and details for feature flag evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from litestar_flags.types import ErrorCode, EvaluationReason

__all__ = ["EvaluationDetails"]

T = TypeVar("T")


@dataclass(slots=True)
class EvaluationDetails(Generic[T]):
    """Detailed result of flag evaluation.

    Follows OpenFeature FlagEvaluationDetails pattern. Provides the evaluated
    value along with metadata about how the evaluation was performed.

    Attributes:
        value: The evaluated flag value.
        flag_key: The key of the evaluated flag.
        reason: The reason for the evaluation result.
        variant: The variant key if a variant was selected.
        error_code: Error code if evaluation failed.
        error_message: Human-readable error message if evaluation failed.
        flag_metadata: Additional metadata about the flag.

    Example:
        >>> details = EvaluationDetails(
        ...     value=True,
        ...     flag_key="new_feature",
        ...     reason=EvaluationReason.TARGETING_MATCH,
        ...     variant="beta_users",
        ... )
        >>> details.is_error
        False

    """

    value: T
    flag_key: str
    reason: EvaluationReason
    variant: str | None = None
    error_code: ErrorCode | None = None
    error_message: str | None = None
    flag_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        """Check if the evaluation resulted in an error.

        Returns:
            True if an error occurred during evaluation.

        """
        return self.error_code is not None

    @property
    def is_default(self) -> bool:
        """Check if the default value was returned.

        Returns:
            True if the default value was returned due to flag not found or error.

        """
        return self.reason in (EvaluationReason.DEFAULT, EvaluationReason.ERROR)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary representation of the evaluation details.

        """
        return {
            "value": self.value,
            "flag_key": self.flag_key,
            "reason": self.reason.value,
            "variant": self.variant,
            "error_code": self.error_code.value if self.error_code else None,
            "error_message": self.error_message,
            "flag_metadata": self.flag_metadata,
        }
