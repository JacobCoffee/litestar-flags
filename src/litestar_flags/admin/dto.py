"""Data Transfer Objects for the Admin API.

This module provides msgspec Struct DTOs for request/response schemas
used by the Admin API endpoints. These DTOs ensure type-safe serialization
and validation of data flowing through the API.

Example:
    Creating a new flag::

        from litestar_flags.admin.dto import CreateFlagRequest, FlagResponse
        from litestar_flags.types import FlagType

        request = CreateFlagRequest(
            key="new_feature",
            name="New Feature",
            description="A new feature flag",
            flag_type=FlagType.BOOLEAN,
            default_enabled=False,
        )

"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from msgspec import Struct, field

from litestar_flags.types import EvaluationReason, FlagStatus, FlagType, RuleOperator

__all__ = [
    "ConditionDTO",
    "CreateEnvironmentRequest",
    "CreateFlagRequest",
    "CreateOverrideRequest",
    "CreateRuleRequest",
    "CreateSegmentRequest",
    "CreateVariantRequest",
    "EnvironmentResponse",
    "ErrorDetail",
    "ErrorResponse",
    "EventResponse",
    "EventsQueryParams",
    "EventsResponse",
    "FlagResponse",
    "FlagSummaryResponse",
    "MetricsQueryParams",
    "MetricsResponse",
    "OverrideResponse",
    "PaginatedResponse",
    "PaginationParams",
    "RuleResponse",
    "SegmentResponse",
    "SortOrder",
    "UpdateEnvironmentRequest",
    "UpdateFlagRequest",
    "UpdateOverrideRequest",
    "UpdateRuleRequest",
    "UpdateSegmentRequest",
    "UpdateVariantRequest",
    "VariantResponse",
]


T = TypeVar("T")


# =============================================================================
# Common DTOs
# =============================================================================


class SortOrder(Struct, frozen=True):
    """Sort order enumeration for pagination.

    Attributes:
        value: The sort direction ('asc' or 'desc').

    """

    ASC: str = "asc"
    DESC: str = "desc"


class PaginationParams(Struct, frozen=True):
    """Pagination parameters for list endpoints.

    Attributes:
        page: Page number (1-indexed).
        page_size: Number of items per page.
        sort_by: Field to sort by.
        sort_order: Sort direction ('asc' or 'desc').

    Example:
        >>> params = PaginationParams(page=1, page_size=20, sort_by="created_at")

    """

    page: int = 1
    page_size: int = 20
    sort_by: str | None = None
    sort_order: str = "desc"


class PaginatedResponse(Struct, Generic[T]):
    """Paginated response wrapper for list endpoints.

    Attributes:
        items: List of items for the current page.
        total: Total number of items across all pages.
        page: Current page number.
        page_size: Number of items per page.
        total_pages: Total number of pages.

    Example:
        >>> response = PaginatedResponse(
        ...     items=[flag1, flag2],
        ...     total=50,
        ...     page=1,
        ...     page_size=20,
        ...     total_pages=3,
        ... )

    """

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class ErrorDetail(Struct, frozen=True):
    """Detailed error information.

    Attributes:
        field_name: The field that caused the error (if applicable).
        message: Detailed error message.
        code: Error code for programmatic handling.

    """

    field_name: str | None = None
    message: str = ""
    code: str | None = None


class ErrorResponse(Struct, frozen=True):
    """Standardized error response.

    Attributes:
        code: Machine-readable error code.
        message: Human-readable error message.
        details: Additional error details.
        request_id: Request ID for tracking.

    Example:
        >>> error = ErrorResponse(
        ...     code="FLAG_NOT_FOUND",
        ...     message="Flag 'my_flag' not found",
        ...     details=[ErrorDetail(field_name="key", message="Invalid flag key")],
        ... )

    """

    code: str
    message: str
    details: list[ErrorDetail] = field(default_factory=list)
    request_id: str | None = None


# =============================================================================
# Flag DTOs
# =============================================================================


class CreateFlagRequest(Struct, frozen=True):
    """Request DTO for creating a new feature flag.

    Attributes:
        key: Unique identifier for the flag (used in code).
        name: Human-readable name for the flag.
        description: Optional description of the flag's purpose.
        flag_type: The type of value the flag returns.
        default_enabled: Default boolean value for boolean flags.
        default_value: Default value for non-boolean flags (stored as JSON).
        tags: List of tags for organizing flags.
        metadata: Additional metadata stored as JSON.

    Example:
        >>> request = CreateFlagRequest(
        ...     key="new_checkout",
        ...     name="New Checkout Flow",
        ...     description="Enable the redesigned checkout experience",
        ...     flag_type=FlagType.BOOLEAN,
        ...     default_enabled=False,
        ...     tags=["checkout", "frontend"],
        ... )

    """

    key: str
    name: str
    description: str | None = None
    flag_type: FlagType = FlagType.BOOLEAN
    default_enabled: bool = False
    default_value: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class UpdateFlagRequest(Struct, frozen=True):
    """Request DTO for updating an existing feature flag.

    All fields are optional for partial updates.

    Attributes:
        name: Human-readable name for the flag.
        description: Optional description of the flag's purpose.
        flag_type: The type of value the flag returns.
        status: Current lifecycle status of the flag.
        default_enabled: Default boolean value for boolean flags.
        default_value: Default value for non-boolean flags.
        tags: List of tags for organizing flags.
        metadata: Additional metadata stored as JSON.

    Example:
        >>> request = UpdateFlagRequest(
        ...     name="Updated Checkout Flow",
        ...     default_enabled=True,
        ... )

    """

    name: str | None = None
    description: str | None = None
    flag_type: FlagType | None = None
    status: FlagStatus | None = None
    default_enabled: bool | None = None
    default_value: dict[str, Any] | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class FlagResponse(Struct, frozen=True):
    """Response DTO for a feature flag with full details.

    Attributes:
        id: Unique identifier (UUID) for the flag.
        key: Unique string identifier for the flag (used in code).
        name: Human-readable name for the flag.
        description: Optional description of the flag's purpose.
        flag_type: The type of value the flag returns.
        status: Current lifecycle status of the flag.
        default_enabled: Default boolean value for boolean flags.
        default_value: Default value for non-boolean flags.
        tags: List of tags for organizing flags.
        metadata: Additional metadata stored as JSON.
        rules_count: Number of targeting rules attached to this flag.
        overrides_count: Number of overrides attached to this flag.
        variants_count: Number of variants for A/B testing.
        created_at: Timestamp when the flag was created.
        updated_at: Timestamp when the flag was last updated.

    """

    id: UUID
    key: str
    name: str
    description: str | None
    flag_type: FlagType
    status: FlagStatus
    default_enabled: bool
    default_value: dict[str, Any] | None
    tags: list[str]
    metadata: dict[str, Any]
    rules_count: int = 0
    overrides_count: int = 0
    variants_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FlagSummaryResponse(Struct, frozen=True):
    """Lightweight response DTO for flag listing.

    Attributes:
        id: Unique identifier (UUID) for the flag.
        key: Unique string identifier for the flag.
        name: Human-readable name for the flag.
        flag_type: The type of value the flag returns.
        status: Current lifecycle status of the flag.
        default_enabled: Default boolean value for boolean flags.
        tags: List of tags for organizing flags.
        created_at: Timestamp when the flag was created.

    """

    id: UUID
    key: str
    name: str
    flag_type: FlagType
    status: FlagStatus
    default_enabled: bool
    tags: list[str]
    created_at: datetime | None = None


# =============================================================================
# Rule DTOs
# =============================================================================


class ConditionDTO(Struct, frozen=True):
    """DTO for a single rule condition.

    Attributes:
        attribute: The context attribute to evaluate.
        operator: The comparison operator.
        value: The value to compare against.

    Example:
        >>> condition = ConditionDTO(
        ...     attribute="country",
        ...     operator=RuleOperator.IN,
        ...     value=["US", "CA"],
        ... )

    """

    attribute: str
    operator: RuleOperator
    value: Any


class CreateRuleRequest(Struct, frozen=True):
    """Request DTO for creating a targeting rule.

    Attributes:
        name: Name of the rule for identification.
        description: Optional description of what this rule targets.
        priority: Evaluation order (lower = evaluated first).
        enabled: Whether this rule is active.
        conditions: List of condition objects defining the rule.
        serve_enabled: Boolean value to serve when rule matches.
        serve_value: Value to serve when rule matches (for non-boolean flags).
        rollout_percentage: Optional percentage rollout (0-100).

    Example:
        >>> request = CreateRuleRequest(
        ...     name="Premium Users",
        ...     description="Enable for premium plan subscribers",
        ...     priority=10,
        ...     conditions=[
        ...         {"attribute": "plan", "operator": "eq", "value": "premium"},
        ...     ],
        ...     serve_enabled=True,
        ... )

    """

    name: str
    description: str | None = None
    priority: int = 0
    enabled: bool = True
    conditions: list[dict[str, Any]] = field(default_factory=list)
    serve_enabled: bool = True
    serve_value: dict[str, Any] | None = None
    rollout_percentage: int | None = None


class UpdateRuleRequest(Struct, frozen=True):
    """Request DTO for updating a targeting rule.

    All fields are optional for partial updates.

    Attributes:
        name: Name of the rule for identification.
        description: Optional description of what this rule targets.
        priority: Evaluation order (lower = evaluated first).
        enabled: Whether this rule is active.
        conditions: List of condition objects defining the rule.
        serve_enabled: Boolean value to serve when rule matches.
        serve_value: Value to serve when rule matches.
        rollout_percentage: Optional percentage rollout (0-100).

    """

    name: str | None = None
    description: str | None = None
    priority: int | None = None
    enabled: bool | None = None
    conditions: list[dict[str, Any]] | None = None
    serve_enabled: bool | None = None
    serve_value: dict[str, Any] | None = None
    rollout_percentage: int | None = None


class RuleResponse(Struct, frozen=True):
    """Response DTO for a targeting rule.

    Attributes:
        id: Unique identifier (UUID) for the rule.
        flag_id: Reference to the parent flag.
        name: Name of the rule for identification.
        description: Optional description of what this rule targets.
        priority: Evaluation order (lower = evaluated first).
        enabled: Whether this rule is active.
        conditions: List of condition objects defining the rule.
        serve_enabled: Boolean value to serve when rule matches.
        serve_value: Value to serve when rule matches.
        rollout_percentage: Optional percentage rollout (0-100).
        created_at: Timestamp when the rule was created.
        updated_at: Timestamp when the rule was last updated.

    """

    id: UUID
    flag_id: UUID
    name: str
    description: str | None
    priority: int
    enabled: bool
    conditions: list[dict[str, Any]]
    serve_enabled: bool
    serve_value: dict[str, Any] | None
    rollout_percentage: int | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# =============================================================================
# Override DTOs
# =============================================================================


class CreateOverrideRequest(Struct, frozen=True):
    """Request DTO for creating an entity-specific override.

    Attributes:
        entity_type: Type of entity (e.g., "user", "organization", "tenant").
        entity_id: Identifier of the specific entity.
        enabled: Whether the flag is enabled for this entity.
        value: Optional value override for non-boolean flags.
        expires_at: Optional expiration time for the override.

    Example:
        >>> request = CreateOverrideRequest(
        ...     entity_type="user",
        ...     entity_id="user-123",
        ...     enabled=True,
        ...     expires_at=datetime(2024, 12, 31),
        ... )

    """

    entity_type: str
    entity_id: str
    enabled: bool
    value: dict[str, Any] | None = None
    expires_at: datetime | None = None


class UpdateOverrideRequest(Struct, frozen=True):
    """Request DTO for updating an override.

    All fields are optional for partial updates.

    Attributes:
        enabled: Whether the flag is enabled for this entity.
        value: Optional value override for non-boolean flags.
        expires_at: Optional expiration time for the override.

    """

    enabled: bool | None = None
    value: dict[str, Any] | None = None
    expires_at: datetime | None = None


class OverrideResponse(Struct, frozen=True):
    """Response DTO for an entity-specific override.

    Attributes:
        id: Unique identifier (UUID) for the override.
        flag_id: Reference to the parent flag.
        entity_type: Type of entity (e.g., "user", "organization").
        entity_id: Identifier of the specific entity.
        enabled: Whether the flag is enabled for this entity.
        value: Optional value override for non-boolean flags.
        expires_at: Optional expiration time for the override.
        is_expired: Whether the override has expired.
        created_at: Timestamp when the override was created.
        updated_at: Timestamp when the override was last updated.

    """

    id: UUID
    flag_id: UUID
    entity_type: str
    entity_id: str
    enabled: bool
    value: dict[str, Any] | None
    expires_at: datetime | None
    is_expired: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


# =============================================================================
# Variant DTOs
# =============================================================================


class CreateVariantRequest(Struct, frozen=True):
    """Request DTO for creating a flag variant.

    Attributes:
        key: Unique key for this variant within the flag.
        name: Human-readable name for the variant.
        description: Optional description of the variant.
        value: The value to return when this variant is selected.
        weight: Distribution weight (0-100) for this variant.

    Example:
        >>> request = CreateVariantRequest(
        ...     key="treatment_a",
        ...     name="Treatment A",
        ...     description="New UI with blue button",
        ...     value={"button_color": "blue"},
        ...     weight=50,
        ... )

    """

    key: str
    name: str
    description: str | None = None
    value: dict[str, Any] = field(default_factory=dict)
    weight: int = 0


class UpdateVariantRequest(Struct, frozen=True):
    """Request DTO for updating a flag variant.

    All fields are optional for partial updates.

    Attributes:
        key: Unique key for this variant within the flag.
        name: Human-readable name for the variant.
        description: Optional description of the variant.
        value: The value to return when this variant is selected.
        weight: Distribution weight (0-100) for this variant.

    """

    key: str | None = None
    name: str | None = None
    description: str | None = None
    value: dict[str, Any] | None = None
    weight: int | None = None


class VariantResponse(Struct, frozen=True):
    """Response DTO for a flag variant.

    Attributes:
        id: Unique identifier (UUID) for the variant.
        flag_id: Reference to the parent flag.
        key: Unique key for this variant within the flag.
        name: Human-readable name for the variant.
        description: Optional description of the variant.
        value: The value to return when this variant is selected.
        weight: Distribution weight (0-100) for this variant.
        created_at: Timestamp when the variant was created.
        updated_at: Timestamp when the variant was last updated.

    """

    id: UUID
    flag_id: UUID
    key: str
    name: str
    description: str | None
    value: dict[str, Any]
    weight: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


# =============================================================================
# Segment DTOs
# =============================================================================


class CreateSegmentRequest(Struct, frozen=True):
    """Request DTO for creating a user segment.

    Attributes:
        name: Unique identifier for the segment.
        description: Optional description of what users this segment targets.
        conditions: List of condition objects defining segment membership.
        parent_segment_id: Optional reference to parent segment for nesting.
        enabled: Whether this segment is active for evaluation.

    Example:
        >>> request = CreateSegmentRequest(
        ...     name="premium_us_users",
        ...     description="Premium users located in the US",
        ...     conditions=[
        ...         {"attribute": "plan", "operator": "eq", "value": "premium"},
        ...         {"attribute": "country", "operator": "eq", "value": "US"},
        ...     ],
        ... )

    """

    name: str
    description: str | None = None
    conditions: list[dict[str, Any]] = field(default_factory=list)
    parent_segment_id: UUID | None = None
    enabled: bool = True


class UpdateSegmentRequest(Struct, frozen=True):
    """Request DTO for updating a user segment.

    All fields are optional for partial updates.

    Attributes:
        name: Unique identifier for the segment.
        description: Optional description of what users this segment targets.
        conditions: List of condition objects defining segment membership.
        parent_segment_id: Optional reference to parent segment for nesting.
        enabled: Whether this segment is active for evaluation.

    """

    name: str | None = None
    description: str | None = None
    conditions: list[dict[str, Any]] | None = None
    parent_segment_id: UUID | None = None
    enabled: bool | None = None


class SegmentResponse(Struct, frozen=True):
    """Response DTO for a user segment.

    Attributes:
        id: Unique identifier (UUID) for the segment.
        name: Unique identifier for the segment.
        description: Optional description of what users this segment targets.
        conditions: List of condition objects defining segment membership.
        parent_segment_id: Optional reference to parent segment for nesting.
        enabled: Whether this segment is active for evaluation.
        children_count: Number of child segments.
        created_at: Timestamp when the segment was created.
        updated_at: Timestamp when the segment was last updated.

    """

    id: UUID
    name: str
    description: str | None
    conditions: list[dict[str, Any]]
    parent_segment_id: UUID | None
    enabled: bool
    children_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


# =============================================================================
# Environment DTOs
# =============================================================================


class CreateEnvironmentRequest(Struct, frozen=True):
    """Request DTO for creating an environment.

    Attributes:
        name: Human-readable display name (e.g., "Production").
        slug: URL-safe unique identifier (e.g., "production").
        description: Optional description of the environment's purpose.
        parent_id: Optional reference to parent environment for inheritance.
        is_production: Whether this is a production environment.
        color: Optional color for UI display (e.g., "#FF5733").
        settings: Environment-specific settings stored as JSON.

    Example:
        >>> request = CreateEnvironmentRequest(
        ...     name="Staging",
        ...     slug="staging",
        ...     description="Pre-production testing environment",
        ...     parent_id=production_env_id,
        ...     is_production=False,
        ...     color="#FFA500",
        ...     settings={"require_approval": False},
        ... )

    """

    name: str
    slug: str
    description: str | None = None
    parent_id: UUID | None = None
    is_production: bool = False
    color: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)


class UpdateEnvironmentRequest(Struct, frozen=True):
    """Request DTO for updating an environment.

    All fields are optional for partial updates.

    Attributes:
        name: Human-readable display name.
        slug: URL-safe unique identifier.
        description: Optional description of the environment's purpose.
        parent_id: Optional reference to parent environment for inheritance.
        is_production: Whether this is a production environment.
        is_active: Whether this environment is active.
        color: Optional color for UI display.
        settings: Environment-specific settings stored as JSON.

    """

    name: str | None = None
    slug: str | None = None
    description: str | None = None
    parent_id: UUID | None = None
    is_production: bool | None = None
    is_active: bool | None = None
    color: str | None = None
    settings: dict[str, Any] | None = None


class EnvironmentResponse(Struct, frozen=True):
    """Response DTO for an environment.

    Attributes:
        id: Unique identifier (UUID) for the environment.
        name: Human-readable display name.
        slug: URL-safe unique identifier.
        description: Optional description of the environment's purpose.
        parent_id: Optional reference to parent environment for inheritance.
        is_active: Whether this environment is active.
        is_production: Whether this is a production environment.
        color: Optional color for UI display.
        settings: Environment-specific settings stored as JSON.
        children_count: Number of child environments.
        created_at: Timestamp when the environment was created.
        updated_at: Timestamp when the environment was last updated.

    """

    id: UUID
    name: str
    slug: str
    description: str | None
    parent_id: UUID | None
    is_active: bool
    is_production: bool = False
    color: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)
    children_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


# =============================================================================
# Analytics DTOs
# =============================================================================


class MetricsQueryParams(Struct, frozen=True):
    """Query parameters for metrics endpoints.

    Attributes:
        flag_key: The flag key to get metrics for (optional for aggregated metrics).
        window_seconds: Time window in seconds for aggregation.
        environment: Environment slug to filter metrics by.
        group_by: Field to group metrics by (e.g., "variant", "reason").

    Example:
        >>> params = MetricsQueryParams(
        ...     flag_key="new_checkout",
        ...     window_seconds=3600,
        ...     environment="production",
        ... )

    """

    flag_key: str | None = None
    window_seconds: int = 3600
    environment: str | None = None
    group_by: str | None = None


class MetricsResponse(Struct, frozen=True):
    """Response DTO for flag metrics.

    Attributes:
        flag_key: The flag key these metrics are for.
        evaluation_rate: Evaluations per second in the measurement window.
        unique_users: Count of unique targeting keys in the window.
        total_evaluations: Total number of evaluations in the window.
        variant_distribution: Count of evaluations per variant.
        reason_distribution: Count of evaluations per reason.
        error_rate: Percentage of evaluations that resulted in errors (0-100).
        latency_p50: 50th percentile latency in milliseconds.
        latency_p90: 90th percentile latency in milliseconds.
        latency_p99: 99th percentile latency in milliseconds.
        window_start: Start of the measurement window.
        window_end: End of the measurement window.

    """

    flag_key: str
    evaluation_rate: float
    unique_users: int
    total_evaluations: int
    variant_distribution: dict[str, int]
    reason_distribution: dict[str, int]
    error_rate: float
    latency_p50: float
    latency_p90: float
    latency_p99: float
    window_start: datetime | None = None
    window_end: datetime | None = None


class EventsQueryParams(Struct, frozen=True):
    """Query parameters for events list endpoints.

    Attributes:
        flag_key: Filter by flag key.
        targeting_key: Filter by targeting key (e.g., user ID).
        reason: Filter by evaluation reason.
        variant: Filter by variant.
        since: Only include events after this timestamp.
        until: Only include events before this timestamp.
        page: Page number (1-indexed).
        page_size: Number of items per page.

    Example:
        >>> params = EventsQueryParams(
        ...     flag_key="new_checkout",
        ...     targeting_key="user-123",
        ...     page=1,
        ...     page_size=50,
        ... )

    """

    flag_key: str | None = None
    targeting_key: str | None = None
    reason: EvaluationReason | None = None
    variant: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    page: int = 1
    page_size: int = 50


class EventResponse(Struct, frozen=True):
    """Response DTO for a single evaluation event.

    Attributes:
        id: Unique identifier for the event.
        timestamp: When the evaluation occurred.
        flag_key: The key of the evaluated flag.
        value: The evaluated flag value.
        reason: The reason for the evaluation result.
        variant: The variant key if a variant was selected.
        targeting_key: The targeting key used for evaluation.
        context_attributes: Additional context attributes used in evaluation.
        evaluation_duration_ms: Time taken to evaluate in milliseconds.

    """

    id: UUID
    timestamp: datetime
    flag_key: str
    value: Any
    reason: EvaluationReason
    variant: str | None
    targeting_key: str | None
    context_attributes: dict[str, Any]
    evaluation_duration_ms: float


class EventsResponse(Struct, frozen=True):
    """Response DTO for paginated evaluation events.

    Attributes:
        events: List of evaluation events.
        total: Total number of events matching the query.
        page: Current page number.
        page_size: Number of items per page.
        total_pages: Total number of pages.
        has_next: Whether there are more pages.
        has_previous: Whether there are previous pages.

    """

    events: list[EventResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool = False
    has_previous: bool = False
