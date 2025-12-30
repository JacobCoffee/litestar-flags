"""Admin API controller for flag rule management.

This module provides the RulesController for managing targeting rules
on feature flags. Rules are nested under flags and are evaluated in
priority order to determine flag values for specific contexts.

Example:
    Registering the controller with a Litestar app::

        from litestar import Litestar
        from litestar_flags.admin.controllers import RulesController

        app = Litestar(
            route_handlers=[RulesController],
        )

"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID

from litestar import Controller, delete, get, patch, post, put
from litestar.di import Provide
from litestar.exceptions import NotFoundException, ValidationException
from litestar.params import Parameter
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED, HTTP_204_NO_CONTENT
from msgspec import Struct

from litestar_flags.admin.audit import (
    AuditAction,
    AuditLogger,
    ResourceType,
    audit_admin_action,
    diff_changes,
)
from litestar_flags.admin.dto import (
    CreateRuleRequest,
    PaginatedResponse,
    RuleResponse,
    UpdateRuleRequest,
)
from litestar_flags.admin.guards import Permission, require_permission
from litestar_flags.models.rule import FlagRule
from litestar_flags.storage.memory import MemoryStorageBackend
from litestar_flags.types import RuleOperator

if TYPE_CHECKING:
    from litestar.connection import Request

__all__ = ["RulesController"]


# =============================================================================
# Request/Response DTOs specific to Rules
# =============================================================================


class ReorderRulesRequest(Struct, frozen=True):
    """Request DTO for reordering rules.

    Attributes:
        rule_ids: List of rule UUIDs in the desired priority order.
            Rules will be assigned priorities starting from 0 based
            on their position in this list.

    Example:
        >>> request = ReorderRulesRequest(
        ...     rule_ids=[uuid1, uuid2, uuid3],  # uuid1 gets priority 0
        ... )

    """

    rule_ids: list[UUID]


class BulkDeleteRulesRequest(Struct, frozen=True):
    """Request DTO for bulk deleting rules.

    Attributes:
        rule_ids: List of rule UUIDs to delete.

    """

    rule_ids: list[UUID]


class BulkDeleteRulesResponse(Struct, frozen=True):
    """Response DTO for bulk delete operation.

    Attributes:
        deleted_count: Number of rules successfully deleted.
        failed_ids: List of rule UUIDs that failed to delete.

    """

    deleted_count: int
    failed_ids: list[UUID]


# =============================================================================
# Validation Helpers
# =============================================================================


VALID_OPERATORS: frozenset[str] = frozenset(op.value for op in RuleOperator)


def _validate_conditions(conditions: list[dict[str, Any]]) -> None:
    """Validate rule condition objects.

    Args:
        conditions: List of condition dictionaries to validate.

    Raises:
        ValidationException: If any condition is invalid.

    """
    for i, condition in enumerate(conditions):
        if not isinstance(condition, dict):
            raise ValidationException(
                detail=f"Condition at index {i} must be an object",
            )

        # Required fields
        if "attribute" not in condition:
            raise ValidationException(
                detail=f"Condition at index {i} missing required field 'attribute'",
            )
        if "operator" not in condition:
            raise ValidationException(
                detail=f"Condition at index {i} missing required field 'operator'",
            )
        if "value" not in condition:
            raise ValidationException(
                detail=f"Condition at index {i} missing required field 'value'",
            )

        # Validate attribute is a non-empty string
        attribute = condition["attribute"]
        if not isinstance(attribute, str) or not attribute.strip():
            raise ValidationException(
                detail=f"Condition at index {i} 'attribute' must be a non-empty string",
            )

        # Validate operator
        operator = condition["operator"]
        if operator not in VALID_OPERATORS:
            raise ValidationException(
                detail=f"Condition at index {i} has invalid operator '{operator}'. "
                f"Valid operators: {', '.join(sorted(VALID_OPERATORS))}",
            )


def _validate_rollout_percentage(percentage: int | None) -> None:
    """Validate rollout percentage is within valid range.

    Args:
        percentage: Percentage value to validate (0-100 or None).

    Raises:
        ValidationException: If percentage is out of range.

    """
    if percentage is not None:
        if not isinstance(percentage, int) or percentage < 0 or percentage > 100:
            raise ValidationException(
                detail="rollout_percentage must be an integer between 0 and 100",
            )


# =============================================================================
# Dependency Providers
# =============================================================================


async def provide_storage(request: Request[Any, Any, Any]) -> MemoryStorageBackend:
    """Provide the storage backend from app state.

    Args:
        request: The incoming request.

    Returns:
        The storage backend instance.

    Raises:
        RuntimeError: If storage is not configured.

    """
    storage = getattr(request.app.state, "feature_flags_storage", None)
    if storage is None:
        raise RuntimeError(
            "Storage backend not configured. Ensure FeatureFlagsPlugin is registered with the application."
        )
    return storage


async def provide_audit_logger(request: Request[Any, Any, Any]) -> AuditLogger | None:
    """Provide the optional audit logger from app state.

    Args:
        request: The incoming request.

    Returns:
        The audit logger if configured, None otherwise.

    """
    return getattr(request.app.state, "feature_flags_audit_logger", None)


# =============================================================================
# Helper Functions
# =============================================================================


def _rule_to_response(rule: FlagRule) -> RuleResponse:
    """Convert a FlagRule model to a RuleResponse DTO.

    Args:
        rule: The FlagRule model instance.

    Returns:
        RuleResponse DTO with the rule data.

    """
    return RuleResponse(
        id=rule.id,
        flag_id=rule.flag_id if rule.flag_id else UUID("00000000-0000-0000-0000-000000000000"),
        name=rule.name,
        description=rule.description,
        priority=rule.priority,
        enabled=rule.enabled,
        conditions=rule.conditions,
        serve_enabled=rule.serve_enabled,
        serve_value=rule.serve_value,
        rollout_percentage=rule.rollout_percentage,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _get_actor_info(request: Request[Any, Any, Any]) -> tuple[str | None, str, str | None]:
    """Extract actor information from the request for audit logging.

    Args:
        request: The incoming request.

    Returns:
        Tuple of (actor_id, actor_type, ip_address).

    """
    actor_id: str | None = None
    actor_type = "system"

    user = getattr(request.state, "user", None) or request.scope.get("user")
    if user:
        if hasattr(user, "id"):
            actor_id = str(user.id)
            actor_type = "user"
        elif isinstance(user, dict) and "id" in user:
            actor_id = str(user["id"])
            actor_type = "user"

    ip_address = request.client.host if request.client else None

    return actor_id, actor_type, ip_address


# =============================================================================
# RulesController
# =============================================================================


class RulesController(Controller):
    """Controller for managing targeting rules on feature flags.

    This controller provides CRUD operations for rules, which are nested
    under feature flags. Rules define targeting conditions and are evaluated
    in priority order during flag evaluation.

    Attributes:
        path: URL path prefix for all rule endpoints.
        tags: OpenAPI tags for documentation.
        dependencies: Dependency injection configuration.

    Example:
        Using the controller endpoints::

            # List all rules for a flag
            GET /admin/flags/{flag_id}/rules

            # Create a new rule
            POST /admin/flags/{flag_id}/rules
            {
                "name": "Premium Users",
                "conditions": [
                    {"attribute": "plan", "operator": "eq", "value": "premium"}
                ],
                "serve_enabled": true
            }

    """

    path: ClassVar[str] = "/admin/flags/{flag_id:uuid}/rules"
    tags: ClassVar[list[str]] = ["Admin - Rules"]
    dependencies: ClassVar[dict[str, Provide]] = {
        "storage": Provide(provide_storage),
        "audit_logger": Provide(provide_audit_logger),
    }

    # -------------------------------------------------------------------------
    # List Rules
    # -------------------------------------------------------------------------

    @get(
        path="/",
        summary="List rules for a flag",
        description="Retrieve all targeting rules for a specific feature flag, "
        "ordered by priority (lowest priority number first).",
        guards=[require_permission(Permission.RULES_READ)],
        status_code=HTTP_200_OK,
    )
    async def list_rules(
        self,
        flag_id: UUID,
        storage: MemoryStorageBackend,
        page: int = Parameter(default=1, ge=1, description="Page number (1-indexed)"),
        page_size: int = Parameter(default=20, ge=1, le=100, description="Items per page"),
    ) -> PaginatedResponse[RuleResponse]:
        """List all rules for a feature flag.

        Args:
            flag_id: The UUID of the parent flag.
            storage: The storage backend.
            page: Page number (1-indexed).
            page_size: Number of items per page.

        Returns:
            Paginated list of rules sorted by priority.

        Raises:
            NotFoundException: If the flag does not exist.

        """
        # Verify flag exists (try by id first, then fallback to iteration)
        flag = storage._flags_by_id.get(flag_id)
        if flag is None:
            # Check if flag exists by iterating (fallback for storage without _flags_by_id)
            for f in storage._flags.values():
                if f.id == flag_id:
                    flag = f
                    break

        if flag is None:
            raise NotFoundException(detail=f"Flag with ID '{flag_id}' not found")

        # Get rules from the flag (rules are stored on the flag object)
        all_rules = sorted(flag.rules, key=lambda r: r.priority)
        total = len(all_rules)

        # Apply pagination
        start = (page - 1) * page_size
        end = start + page_size
        paginated_rules = all_rules[start:end]

        # Calculate total pages
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1

        return PaginatedResponse(
            items=[_rule_to_response(rule) for rule in paginated_rules],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    # -------------------------------------------------------------------------
    # Get Single Rule
    # -------------------------------------------------------------------------

    @get(
        path="/{rule_id:uuid}",
        summary="Get a rule",
        description="Retrieve a single targeting rule by ID.",
        guards=[require_permission(Permission.RULES_READ)],
        status_code=HTTP_200_OK,
    )
    async def get_rule(
        self,
        flag_id: UUID,
        rule_id: UUID,
        storage: MemoryStorageBackend,
    ) -> RuleResponse:
        """Get a single rule by ID.

        Args:
            flag_id: The UUID of the parent flag.
            rule_id: The UUID of the rule to retrieve.
            storage: The storage backend.

        Returns:
            The rule details.

        Raises:
            NotFoundException: If the flag or rule does not exist.

        """
        # Verify flag exists
        flag = None
        for f in storage._flags.values():
            if f.id == flag_id:
                flag = f
                break

        if flag is None:
            raise NotFoundException(detail=f"Flag with ID '{flag_id}' not found")

        # Find the rule
        rule = None
        for r in flag.rules:
            if r.id == rule_id:
                rule = r
                break

        if rule is None:
            raise NotFoundException(detail=f"Rule with ID '{rule_id}' not found for flag '{flag_id}'")

        return _rule_to_response(rule)

    # -------------------------------------------------------------------------
    # Create Rule
    # -------------------------------------------------------------------------

    @post(
        path="/",
        summary="Create a rule",
        description="Create a new targeting rule for a feature flag.",
        guards=[require_permission(Permission.RULES_WRITE)],
        status_code=HTTP_201_CREATED,
    )
    async def create_rule(
        self,
        flag_id: UUID,
        data: CreateRuleRequest,
        storage: MemoryStorageBackend,
        request: Request[Any, Any, Any],
        audit_logger: AuditLogger | None,
    ) -> RuleResponse:
        """Create a new targeting rule.

        Args:
            flag_id: The UUID of the parent flag.
            data: The rule creation request.
            storage: The storage backend.
            request: The incoming request.
            audit_logger: Optional audit logger.

        Returns:
            The created rule.

        Raises:
            NotFoundException: If the flag does not exist.
            ValidationException: If the rule data is invalid.

        """
        # Verify flag exists
        flag = None
        for f in storage._flags.values():
            if f.id == flag_id:
                flag = f
                break

        if flag is None:
            raise NotFoundException(detail=f"Flag with ID '{flag_id}' not found")

        # Validate conditions
        _validate_conditions(data.conditions)

        # Validate rollout percentage
        _validate_rollout_percentage(data.rollout_percentage)

        # Check for priority conflicts
        existing_priorities = {r.priority for r in flag.rules}
        priority = data.priority
        if priority in existing_priorities:
            # Auto-adjust to next available priority
            priority = max(existing_priorities) + 1 if existing_priorities else 0

        # Create the rule
        now = datetime.now(UTC)
        rule = FlagRule(
            name=data.name,
            flag_id=flag_id,
            description=data.description,
            priority=priority,
            enabled=data.enabled,
            conditions=data.conditions,
            serve_enabled=data.serve_enabled,
            serve_value=data.serve_value,
            rollout_percentage=data.rollout_percentage,
            created_at=now,
            updated_at=now,
        )

        # Add rule to flag
        flag.rules.append(rule)
        flag.updated_at = now  # type: ignore[misc]

        # Update flag in storage
        await storage.update_flag(flag)

        # Audit log
        if audit_logger:
            actor_id, actor_type, ip_address = _get_actor_info(request)
            await audit_admin_action(
                audit_logger,
                action=AuditAction.CREATE,
                resource_type=ResourceType.RULE,
                resource_id=rule.id,
                resource_key=rule.name,
                actor_id=actor_id,
                actor_type=actor_type,
                ip_address=ip_address,
                metadata={
                    "flag_id": str(flag_id),
                    "flag_key": flag.key,
                    "priority": rule.priority,
                    "conditions_count": len(rule.conditions),
                },
            )

        return _rule_to_response(rule)

    # -------------------------------------------------------------------------
    # Full Update Rule (PUT)
    # -------------------------------------------------------------------------

    @put(
        path="/{rule_id:uuid}",
        summary="Update a rule (full)",
        description="Fully update a targeting rule. All fields will be replaced.",
        guards=[require_permission(Permission.RULES_WRITE)],
        status_code=HTTP_200_OK,
    )
    async def update_rule(
        self,
        flag_id: UUID,
        rule_id: UUID,
        data: CreateRuleRequest,
        storage: MemoryStorageBackend,
        request: Request[Any, Any, Any],
        audit_logger: AuditLogger | None,
    ) -> RuleResponse:
        """Fully update a targeting rule.

        Args:
            flag_id: The UUID of the parent flag.
            rule_id: The UUID of the rule to update.
            data: The rule update request (all fields required).
            storage: The storage backend.
            request: The incoming request.
            audit_logger: Optional audit logger.

        Returns:
            The updated rule.

        Raises:
            NotFoundException: If the flag or rule does not exist.
            ValidationException: If the rule data is invalid.

        """
        # Verify flag exists
        flag = None
        for f in storage._flags.values():
            if f.id == flag_id:
                flag = f
                break

        if flag is None:
            raise NotFoundException(detail=f"Flag with ID '{flag_id}' not found")

        # Find the rule
        rule_index = None
        original_rule = None
        for i, r in enumerate(flag.rules):
            if r.id == rule_id:
                rule_index = i
                original_rule = r
                break

        if rule_index is None or original_rule is None:
            raise NotFoundException(detail=f"Rule with ID '{rule_id}' not found for flag '{flag_id}'")

        # Validate conditions
        _validate_conditions(data.conditions)

        # Validate rollout percentage
        _validate_rollout_percentage(data.rollout_percentage)

        # Check for priority conflicts (excluding current rule)
        existing_priorities = {r.priority for r in flag.rules if r.id != rule_id}
        priority = data.priority
        if priority in existing_priorities:
            raise ValidationException(detail=f"Priority {priority} is already used by another rule")

        # Capture original state for audit
        original_state = {
            "name": original_rule.name,
            "description": original_rule.description,
            "priority": original_rule.priority,
            "enabled": original_rule.enabled,
            "conditions": original_rule.conditions,
            "serve_enabled": original_rule.serve_enabled,
            "serve_value": original_rule.serve_value,
            "rollout_percentage": original_rule.rollout_percentage,
        }

        # Update the rule
        now = datetime.now(UTC)
        updated_rule = FlagRule(
            name=data.name,
            flag_id=flag_id,
            id=original_rule.id,
            description=data.description,
            priority=priority,
            enabled=data.enabled,
            conditions=data.conditions,
            serve_enabled=data.serve_enabled,
            serve_value=data.serve_value,
            rollout_percentage=data.rollout_percentage,
            created_at=original_rule.created_at,
            updated_at=now,
        )

        # Replace rule in flag
        flag.rules[rule_index] = updated_rule
        flag.updated_at = now  # type: ignore[misc]

        # Update flag in storage
        await storage.update_flag(flag)

        # Audit log
        if audit_logger:
            actor_id, actor_type, ip_address = _get_actor_info(request)
            new_state = {
                "name": updated_rule.name,
                "description": updated_rule.description,
                "priority": updated_rule.priority,
                "enabled": updated_rule.enabled,
                "conditions": updated_rule.conditions,
                "serve_enabled": updated_rule.serve_enabled,
                "serve_value": updated_rule.serve_value,
                "rollout_percentage": updated_rule.rollout_percentage,
            }
            await audit_admin_action(
                audit_logger,
                action=AuditAction.UPDATE,
                resource_type=ResourceType.RULE,
                resource_id=rule_id,
                resource_key=updated_rule.name,
                actor_id=actor_id,
                actor_type=actor_type,
                ip_address=ip_address,
                changes=diff_changes(original_state, new_state),
                metadata={
                    "flag_id": str(flag_id),
                    "flag_key": flag.key,
                },
            )

        return _rule_to_response(updated_rule)

    # -------------------------------------------------------------------------
    # Partial Update Rule (PATCH)
    # -------------------------------------------------------------------------

    @patch(
        path="/{rule_id:uuid}",
        summary="Update a rule (partial)",
        description="Partially update a targeting rule. Only provided fields will be updated.",
        guards=[require_permission(Permission.RULES_WRITE)],
        status_code=HTTP_200_OK,
    )
    async def patch_rule(
        self,
        flag_id: UUID,
        rule_id: UUID,
        data: UpdateRuleRequest,
        storage: MemoryStorageBackend,
        request: Request[Any, Any, Any],
        audit_logger: AuditLogger | None,
    ) -> RuleResponse:
        """Apply partial updates to a targeting rule.

        Args:
            flag_id: The UUID of the parent flag.
            rule_id: The UUID of the rule to update.
            data: The partial rule update request.
            storage: The storage backend.
            request: The incoming request.
            audit_logger: Optional audit logger.

        Returns:
            The updated rule.

        Raises:
            NotFoundException: If the flag or rule does not exist.
            ValidationException: If the rule data is invalid.

        """
        # Verify flag exists
        flag = None
        for f in storage._flags.values():
            if f.id == flag_id:
                flag = f
                break

        if flag is None:
            raise NotFoundException(detail=f"Flag with ID '{flag_id}' not found")

        # Find the rule
        rule_index = None
        original_rule = None
        for i, r in enumerate(flag.rules):
            if r.id == rule_id:
                rule_index = i
                original_rule = r
                break

        if rule_index is None or original_rule is None:
            raise NotFoundException(detail=f"Rule with ID '{rule_id}' not found for flag '{flag_id}'")

        # Validate conditions if provided
        if data.conditions is not None:
            _validate_conditions(data.conditions)

        # Validate rollout percentage if provided
        if data.rollout_percentage is not None:
            _validate_rollout_percentage(data.rollout_percentage)

        # Check for priority conflicts if priority is being changed
        new_priority = data.priority if data.priority is not None else original_rule.priority
        if data.priority is not None:
            existing_priorities = {r.priority for r in flag.rules if r.id != rule_id}
            if new_priority in existing_priorities:
                raise ValidationException(detail=f"Priority {new_priority} is already used by another rule")

        # Capture original state for audit
        original_state = {
            "name": original_rule.name,
            "description": original_rule.description,
            "priority": original_rule.priority,
            "enabled": original_rule.enabled,
            "conditions": original_rule.conditions,
            "serve_enabled": original_rule.serve_enabled,
            "serve_value": original_rule.serve_value,
            "rollout_percentage": original_rule.rollout_percentage,
        }

        # Build updated rule with merged values
        now = datetime.now(UTC)
        new_rollout = (
            data.rollout_percentage if data.rollout_percentage is not None else original_rule.rollout_percentage
        )
        updated_rule = FlagRule(
            name=data.name if data.name is not None else original_rule.name,
            flag_id=flag_id,
            id=original_rule.id,
            description=(data.description if data.description is not None else original_rule.description),
            priority=new_priority,
            enabled=data.enabled if data.enabled is not None else original_rule.enabled,
            conditions=(data.conditions if data.conditions is not None else original_rule.conditions),
            serve_enabled=(data.serve_enabled if data.serve_enabled is not None else original_rule.serve_enabled),
            serve_value=(data.serve_value if data.serve_value is not None else original_rule.serve_value),
            rollout_percentage=new_rollout,
            created_at=original_rule.created_at,
            updated_at=now,
        )

        # Replace rule in flag
        flag.rules[rule_index] = updated_rule
        flag.updated_at = now  # type: ignore[misc]

        # Update flag in storage
        await storage.update_flag(flag)

        # Audit log
        if audit_logger:
            actor_id, actor_type, ip_address = _get_actor_info(request)
            new_state = {
                "name": updated_rule.name,
                "description": updated_rule.description,
                "priority": updated_rule.priority,
                "enabled": updated_rule.enabled,
                "conditions": updated_rule.conditions,
                "serve_enabled": updated_rule.serve_enabled,
                "serve_value": updated_rule.serve_value,
                "rollout_percentage": updated_rule.rollout_percentage,
            }
            await audit_admin_action(
                audit_logger,
                action=AuditAction.UPDATE,
                resource_type=ResourceType.RULE,
                resource_id=rule_id,
                resource_key=updated_rule.name,
                actor_id=actor_id,
                actor_type=actor_type,
                ip_address=ip_address,
                changes=diff_changes(original_state, new_state),
                metadata={
                    "flag_id": str(flag_id),
                    "flag_key": flag.key,
                    "partial_update": True,
                },
            )

        return _rule_to_response(updated_rule)

    # -------------------------------------------------------------------------
    # Delete Rule
    # -------------------------------------------------------------------------

    @delete(
        path="/{rule_id:uuid}",
        summary="Delete a rule",
        description="Delete a targeting rule from a feature flag.",
        guards=[require_permission(Permission.RULES_WRITE)],
        status_code=HTTP_204_NO_CONTENT,
    )
    async def delete_rule(
        self,
        flag_id: UUID,
        rule_id: UUID,
        storage: MemoryStorageBackend,
        request: Request[Any, Any, Any],
        audit_logger: AuditLogger | None,
    ) -> None:
        """Delete a targeting rule.

        Args:
            flag_id: The UUID of the parent flag.
            rule_id: The UUID of the rule to delete.
            storage: The storage backend.
            request: The incoming request.
            audit_logger: Optional audit logger.

        Raises:
            NotFoundException: If the flag or rule does not exist.

        """
        # Verify flag exists
        flag = None
        for f in storage._flags.values():
            if f.id == flag_id:
                flag = f
                break

        if flag is None:
            raise NotFoundException(detail=f"Flag with ID '{flag_id}' not found")

        # Find the rule
        rule_index = None
        rule_to_delete = None
        for i, r in enumerate(flag.rules):
            if r.id == rule_id:
                rule_index = i
                rule_to_delete = r
                break

        if rule_index is None or rule_to_delete is None:
            raise NotFoundException(detail=f"Rule with ID '{rule_id}' not found for flag '{flag_id}'")

        # Remove the rule
        now = datetime.now(UTC)
        flag.rules.pop(rule_index)
        flag.updated_at = now  # type: ignore[misc]

        # Update flag in storage
        await storage.update_flag(flag)

        # Audit log
        if audit_logger:
            actor_id, actor_type, ip_address = _get_actor_info(request)
            await audit_admin_action(
                audit_logger,
                action=AuditAction.DELETE,
                resource_type=ResourceType.RULE,
                resource_id=rule_id,
                resource_key=rule_to_delete.name,
                actor_id=actor_id,
                actor_type=actor_type,
                ip_address=ip_address,
                metadata={
                    "flag_id": str(flag_id),
                    "flag_key": flag.key,
                    "deleted_rule": {
                        "name": rule_to_delete.name,
                        "priority": rule_to_delete.priority,
                        "conditions_count": len(rule_to_delete.conditions),
                    },
                },
            )

    # -------------------------------------------------------------------------
    # Reorder Rules
    # -------------------------------------------------------------------------

    @post(
        path="/reorder",
        summary="Reorder rules",
        description="Reorder targeting rules by specifying the desired priority order. "
        "Rules will be assigned priorities starting from 0 based on their "
        "position in the provided list.",
        guards=[require_permission(Permission.RULES_WRITE)],
        status_code=HTTP_200_OK,
    )
    async def reorder_rules(
        self,
        flag_id: UUID,
        data: ReorderRulesRequest,
        storage: MemoryStorageBackend,
        request: Request[Any, Any, Any],
        audit_logger: AuditLogger | None,
    ) -> list[RuleResponse]:
        """Reorder rules by priority.

        Args:
            flag_id: The UUID of the parent flag.
            data: The reorder request with rule IDs in desired order.
            storage: The storage backend.
            request: The incoming request.
            audit_logger: Optional audit logger.

        Returns:
            List of rules in their new order.

        Raises:
            NotFoundException: If the flag does not exist.
            ValidationException: If the rule IDs are invalid.

        """
        # Verify flag exists
        flag = None
        for f in storage._flags.values():
            if f.id == flag_id:
                flag = f
                break

        if flag is None:
            raise NotFoundException(detail=f"Flag with ID '{flag_id}' not found")

        # Validate all rule IDs exist
        existing_rule_ids = {r.id for r in flag.rules}
        provided_rule_ids = set(data.rule_ids)

        missing_ids = provided_rule_ids - existing_rule_ids
        if missing_ids:
            raise ValidationException(detail=f"Rule IDs not found: {', '.join(str(rid) for rid in missing_ids)}")

        extra_ids = existing_rule_ids - provided_rule_ids
        if extra_ids:
            raise ValidationException(
                detail=f"Missing rule IDs in reorder request: {', '.join(str(rid) for rid in extra_ids)}"
            )

        # Check for duplicates
        if len(data.rule_ids) != len(set(data.rule_ids)):
            raise ValidationException(detail="Duplicate rule IDs in reorder request")

        # Capture original order for audit
        original_order = [(r.id, r.priority) for r in sorted(flag.rules, key=lambda r: r.priority)]

        # Create a mapping of rule_id to rule for quick lookup
        rule_map = {r.id: r for r in flag.rules}

        # Update priorities based on position in the list
        now = datetime.now(UTC)
        for priority, rule_id in enumerate(data.rule_ids):
            rule = rule_map[rule_id]
            rule.priority = priority  # type: ignore[misc]
            rule.updated_at = now  # type: ignore[misc]

        # Sort rules by new priority
        flag.rules.sort(key=lambda r: r.priority)
        flag.updated_at = now  # type: ignore[misc]

        # Update flag in storage
        await storage.update_flag(flag)

        # Audit log
        if audit_logger:
            actor_id, actor_type, ip_address = _get_actor_info(request)
            new_order = [(r.id, r.priority) for r in flag.rules]
            await audit_admin_action(
                audit_logger,
                action=AuditAction.UPDATE,
                resource_type=ResourceType.FLAG,
                resource_id=flag_id,
                resource_key=flag.key,
                actor_id=actor_id,
                actor_type=actor_type,
                ip_address=ip_address,
                changes={
                    "before": {"rule_order": [str(rid) for rid, _ in original_order]},
                    "after": {"rule_order": [str(rid) for rid, _ in new_order]},
                    "changed_fields": ["rule_order"],
                },
                metadata={
                    "operation": "reorder_rules",
                    "rules_count": len(flag.rules),
                },
            )

        return [_rule_to_response(rule) for rule in flag.rules]

    # -------------------------------------------------------------------------
    # Toggle Rule Enabled State
    # -------------------------------------------------------------------------

    @post(
        path="/{rule_id:uuid}/toggle",
        summary="Toggle rule enabled state",
        description="Toggle the enabled state of a targeting rule.",
        guards=[require_permission(Permission.RULES_WRITE)],
        status_code=HTTP_200_OK,
    )
    async def toggle_rule(
        self,
        flag_id: UUID,
        rule_id: UUID,
        storage: MemoryStorageBackend,
        request: Request[Any, Any, Any],
        audit_logger: AuditLogger | None,
    ) -> RuleResponse:
        """Toggle the enabled state of a rule.

        Args:
            flag_id: The UUID of the parent flag.
            rule_id: The UUID of the rule to toggle.
            storage: The storage backend.
            request: The incoming request.
            audit_logger: Optional audit logger.

        Returns:
            The updated rule.

        Raises:
            NotFoundException: If the flag or rule does not exist.

        """
        # Verify flag exists
        flag = None
        for f in storage._flags.values():
            if f.id == flag_id:
                flag = f
                break

        if flag is None:
            raise NotFoundException(detail=f"Flag with ID '{flag_id}' not found")

        # Find the rule
        rule_index = None
        rule = None
        for i, r in enumerate(flag.rules):
            if r.id == rule_id:
                rule_index = i
                rule = r
                break

        if rule_index is None or rule is None:
            raise NotFoundException(detail=f"Rule with ID '{rule_id}' not found for flag '{flag_id}'")

        # Toggle enabled state
        now = datetime.now(UTC)
        original_enabled = rule.enabled
        rule.enabled = not rule.enabled  # type: ignore[misc]
        rule.updated_at = now  # type: ignore[misc]
        flag.updated_at = now  # type: ignore[misc]

        # Update flag in storage
        await storage.update_flag(flag)

        # Audit log
        if audit_logger:
            actor_id, actor_type, ip_address = _get_actor_info(request)
            action = AuditAction.ENABLE if rule.enabled else AuditAction.DISABLE
            await audit_admin_action(
                audit_logger,
                action=action,
                resource_type=ResourceType.RULE,
                resource_id=rule_id,
                resource_key=rule.name,
                actor_id=actor_id,
                actor_type=actor_type,
                ip_address=ip_address,
                changes={
                    "before": {"enabled": original_enabled},
                    "after": {"enabled": rule.enabled},
                    "changed_fields": ["enabled"],
                },
                metadata={
                    "flag_id": str(flag_id),
                    "flag_key": flag.key,
                },
            )

        return _rule_to_response(rule)
