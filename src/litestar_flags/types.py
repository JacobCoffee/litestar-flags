"""Core types and enums for litestar-flags."""

from __future__ import annotations

from enum import Enum

__all__ = [
    "ChangeType",
    "ErrorCode",
    "EvaluationReason",
    "FlagStatus",
    "FlagType",
    "RecurrenceType",
    "RuleOperator",
]


class FlagType(str, Enum):
    """Types of feature flags."""

    BOOLEAN = "boolean"
    STRING = "string"
    NUMBER = "number"
    JSON = "json"


class FlagStatus(str, Enum):
    """Flag lifecycle status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class RuleOperator(str, Enum):
    """Operators for rule conditions."""

    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    GREATER_THAN_OR_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_THAN_OR_EQUAL = "lte"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES = "matches"
    SEMVER_EQ = "semver_eq"
    SEMVER_GT = "semver_gt"
    SEMVER_LT = "semver_lt"
    # Time-based operators
    DATE_AFTER = "date_after"
    DATE_BEFORE = "date_before"
    TIME_WINDOW = "time_window"


class RecurrenceType(str, Enum):
    """Types of recurrence for time schedules."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CRON = "cron"


class ChangeType(str, Enum):
    """Types of scheduled flag changes."""

    ENABLE = "enable"
    DISABLE = "disable"
    UPDATE_VALUE = "update_value"
    UPDATE_ROLLOUT = "update_rollout"


class EvaluationReason(str, Enum):
    """Reason for evaluation result."""

    DEFAULT = "DEFAULT"
    STATIC = "STATIC"
    TARGETING_MATCH = "TARGETING_MATCH"
    OVERRIDE = "OVERRIDE"
    SPLIT = "SPLIT"
    DISABLED = "DISABLED"
    ERROR = "ERROR"


class ErrorCode(str, Enum):
    """Error codes for failed evaluations."""

    FLAG_NOT_FOUND = "FLAG_NOT_FOUND"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    PARSE_ERROR = "PARSE_ERROR"
    PROVIDER_NOT_READY = "PROVIDER_NOT_READY"
    GENERAL_ERROR = "GENERAL_ERROR"
    TARGETING_KEY_MISSING = "TARGETING_KEY_MISSING"
    INVALID_CONTEXT = "INVALID_CONTEXT"
