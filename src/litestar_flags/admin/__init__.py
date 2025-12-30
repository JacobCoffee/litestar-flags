"""Admin API module for litestar-flags.

Provides REST API endpoints for managing feature flags, rules, segments,
environments, and analytics with role-based access control and audit logging.

Example:
    Basic usage with the FeatureFlagsAdminPlugin::

        from litestar import Litestar
        from litestar_flags import FeatureFlagsPlugin
        from litestar_flags.admin import FeatureFlagsAdminPlugin, FeatureFlagsAdminConfig

        config = FeatureFlagsAdminConfig(path_prefix="/api/admin")
        app = Litestar(
            plugins=[
                FeatureFlagsPlugin(),
                FeatureFlagsAdminPlugin(config=config),
            ],
        )

    Using guards directly in route handlers::

        from litestar import get
        from litestar_flags.admin import require_permission, Permission

        @get("/flags", guards=[require_permission(Permission.FLAGS_READ)])
        async def list_flags() -> list[dict]:
            ...

    Setting up audit logging::

        from litestar_flags.admin import (
            InMemoryAuditLogger,
            AuditAction,
            ResourceType,
            create_audit_entry,
        )

        logger = InMemoryAuditLogger()
        entry = create_audit_entry(
            action=AuditAction.CREATE,
            resource_type=ResourceType.FLAG,
            resource_id="550e8400-e29b-41d4-a716-446655440000",
            resource_key="new_feature",
            actor_id="user-123",
        )
        await logger.log(entry)

"""

from __future__ import annotations

from litestar_flags.admin.audit import (
    AuditAction,
    AuditEntry,
    AuditLogger,
    InMemoryAuditLogger,
    ResourceType,
    audit_admin_action,
    create_audit_entry,
    diff_changes,
)
from litestar_flags.admin.controllers import (
    AnalyticsController,
    EntityOverridesController,
    EnvironmentsController,
    FlagsController,
    OverridesController,
    RulesController,
    SegmentsController,
)
from litestar_flags.admin.dto import (
    ConditionDTO,
    CreateEnvironmentRequest,
    CreateFlagRequest,
    CreateOverrideRequest,
    CreateRuleRequest,
    CreateSegmentRequest,
    CreateVariantRequest,
    EnvironmentResponse,
    ErrorDetail,
    ErrorResponse,
    EventResponse,
    EventsQueryParams,
    EventsResponse,
    FlagResponse,
    FlagSummaryResponse,
    MetricsQueryParams,
    MetricsResponse,
    OverrideResponse,
    PaginatedResponse,
    PaginationParams,
    RuleResponse,
    SegmentResponse,
    SortOrder,
    UpdateEnvironmentRequest,
    UpdateFlagRequest,
    UpdateOverrideRequest,
    UpdateRuleRequest,
    UpdateSegmentRequest,
    UpdateVariantRequest,
    VariantResponse,
)
from litestar_flags.admin.guards import (
    ROLE_PERMISSIONS,
    HasPermissions,
    Permission,
    PermissionGuard,
    Role,
    RoleGuard,
    get_current_user_permissions,
    get_permissions_for_roles,
    has_permission,
    has_role,
    require_permission,
    require_role,
    require_superadmin,
)
from litestar_flags.admin.plugin import FeatureFlagsAdminConfig, FeatureFlagsAdminPlugin

__all__ = [
    "ROLE_PERMISSIONS",
    # Controllers
    "AnalyticsController",
    # Audit
    "AuditAction",
    "AuditEntry",
    "AuditLogger",
    # DTOs
    "ConditionDTO",
    "CreateEnvironmentRequest",
    "CreateFlagRequest",
    "CreateOverrideRequest",
    "CreateRuleRequest",
    "CreateSegmentRequest",
    "CreateVariantRequest",
    "EntityOverridesController",
    "EnvironmentResponse",
    "EnvironmentsController",
    "ErrorDetail",
    "ErrorResponse",
    "EventResponse",
    "EventsQueryParams",
    "EventsResponse",
    # Plugin
    "FeatureFlagsAdminConfig",
    "FeatureFlagsAdminPlugin",
    "FlagResponse",
    "FlagSummaryResponse",
    "FlagsController",
    # Guards
    "HasPermissions",
    "InMemoryAuditLogger",
    "MetricsQueryParams",
    "MetricsResponse",
    "OverrideResponse",
    "OverridesController",
    "PaginatedResponse",
    "PaginationParams",
    "Permission",
    "PermissionGuard",
    "ResourceType",
    "Role",
    "RoleGuard",
    "RuleResponse",
    "RulesController",
    "SegmentResponse",
    "SegmentsController",
    "SortOrder",
    "UpdateEnvironmentRequest",
    "UpdateFlagRequest",
    "UpdateOverrideRequest",
    "UpdateRuleRequest",
    "UpdateSegmentRequest",
    "UpdateVariantRequest",
    "VariantResponse",
    "audit_admin_action",
    "create_audit_entry",
    "diff_changes",
    "get_current_user_permissions",
    "get_permissions_for_roles",
    "has_permission",
    "has_role",
    "require_permission",
    "require_role",
    "require_superadmin",
]
