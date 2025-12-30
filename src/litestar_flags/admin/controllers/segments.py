"""Segments CRUD controller for the Admin API.

This module provides a Litestar controller for managing user segments through
the Admin API. Segments define reusable groups of users based on shared
attributes for consistent targeting across multiple flags.

Example:
    Registering the controller with a Litestar app::

        from litestar import Litestar
        from litestar_flags.admin.controllers import SegmentsController

        app = Litestar(
            route_handlers=[SegmentsController],
        )

"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID

from litestar import Controller, delete, get, patch, post, put
from litestar.datastructures import State
from litestar.di import Provide
from litestar.exceptions import HTTPException, NotFoundException
from litestar.params import Parameter
from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_409_CONFLICT,
)
from msgspec import Struct

from litestar_flags.admin.audit import (
    AuditAction,
    AuditLogger,
    ResourceType,
    audit_admin_action,
    diff_changes,
)
from litestar_flags.admin.dto import (
    CreateSegmentRequest,
    PaginatedResponse,
    SegmentResponse,
    UpdateSegmentRequest,
)
from litestar_flags.admin.guards import Permission, require_permission
from litestar_flags.models.segment import Segment
from litestar_flags.protocols import StorageBackend

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection

__all__ = ["SegmentsController"]


class EvaluateSegmentRequest(Struct, frozen=True):
    """Request DTO for evaluating segment membership.

    Attributes:
        context: The context attributes to test against the segment conditions.

    Example:
        >>> request = EvaluateSegmentRequest(
        ...     context={"plan": "premium", "country": "US"},
        ... )

    """

    context: dict[str, Any]


class EvaluateSegmentResponse(Struct, frozen=True):
    """Response DTO for segment evaluation result.

    Attributes:
        matches: Whether the context matches the segment conditions.
        segment_id: The ID of the evaluated segment.
        segment_name: The name of the evaluated segment.
        matched_conditions: List of conditions that matched (if any).
        failed_conditions: List of conditions that did not match (if any).

    """

    matches: bool
    segment_id: UUID
    segment_name: str
    matched_conditions: list[dict[str, Any]]
    failed_conditions: list[dict[str, Any]]


async def provide_storage(state: State) -> StorageBackend:
    """Provide the storage backend from app state.

    Args:
        state: The application state object.

    Returns:
        The configured StorageBackend instance.

    Raises:
        HTTPException: If no storage backend is configured.

    """
    storage = getattr(state, "feature_flags_storage", None)
    if storage is None:
        raise HTTPException(
            status_code=500,
            detail="Feature flags storage backend not configured",
        )
    return storage


async def provide_audit_logger(state: State) -> AuditLogger | None:
    """Provide the audit logger from app state (optional).

    Args:
        state: The application state object.

    Returns:
        The configured AuditLogger instance, or None if not configured.

    """
    return getattr(state, "feature_flags_audit_logger", None)


class _ActorInfo:
    """Container for actor information extracted from a connection.

    Attributes:
        actor_id: The unique identifier of the actor.
        actor_type: The type of actor (user, system, api_key, etc.).
        ip_address: The IP address of the actor.
        user_agent: The user agent string of the actor.

    """

    __slots__ = ("actor_id", "actor_type", "ip_address", "user_agent")

    def __init__(
        self,
        actor_id: str | None,
        actor_type: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        """Initialize actor info.

        Args:
            actor_id: The unique identifier of the actor.
            actor_type: The type of actor.
            ip_address: The IP address of the actor.
            user_agent: The user agent string of the actor.

        """
        self.actor_id = actor_id
        self.actor_type = actor_type
        self.ip_address = ip_address
        self.user_agent = user_agent


def _get_actor_info(connection: ASGIConnection[Any, Any, Any, Any]) -> _ActorInfo:
    """Extract actor information from the connection.

    Args:
        connection: The ASGI connection object.

    Returns:
        ActorInfo containing actor_id, actor_type, ip_address, and user_agent.

    """
    user = getattr(connection.state, "user", None)
    if user is None:
        user = connection.scope.get("user")

    actor_id: str | None = None
    actor_type: str = "system"

    if user is not None:
        if hasattr(user, "id"):
            actor_id = str(user.id)
        elif isinstance(user, dict):
            actor_id = user.get("id")
        actor_type = "user"

    # Extract IP address from connection
    client = connection.client
    ip_address = client.host if client else None

    # Extract user agent from headers
    user_agent = connection.headers.get("user-agent")

    return _ActorInfo(
        actor_id=actor_id,
        actor_type=actor_type,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def _segment_to_response(segment: Segment, children_count: int = 0) -> SegmentResponse:
    """Convert a Segment model to a SegmentResponse DTO.

    Args:
        segment: The Segment model instance.
        children_count: The number of child segments.

    Returns:
        A SegmentResponse DTO with all segment details.

    """
    return SegmentResponse(
        id=segment.id,
        name=segment.name,
        description=segment.description,
        conditions=segment.conditions or [],
        parent_segment_id=segment.parent_segment_id,
        enabled=segment.enabled,
        children_count=children_count,
        created_at=segment.created_at,
        updated_at=segment.updated_at,
    )


def _segment_to_dict(segment: Segment) -> dict[str, Any]:
    """Convert a Segment to a dictionary for audit logging.

    Args:
        segment: The Segment model instance.

    Returns:
        Dictionary representation of the segment.

    """
    return {
        "id": str(segment.id),
        "name": segment.name,
        "description": segment.description,
        "conditions": segment.conditions,
        "parent_segment_id": str(segment.parent_segment_id) if segment.parent_segment_id else None,
        "enabled": segment.enabled,
    }


def _validate_conditions(conditions: list[dict[str, Any]]) -> list[str]:
    """Validate segment conditions have required fields.

    Args:
        conditions: List of condition dictionaries to validate.

    Returns:
        List of validation error messages (empty if valid).

    """
    errors: list[str] = []
    required_fields = {"attribute", "operator", "value"}

    for idx, condition in enumerate(conditions):
        if not isinstance(condition, dict):
            errors.append(f"Condition at index {idx} must be a dictionary")
            continue

        missing = required_fields - set(condition.keys())
        if missing:
            errors.append(f"Condition at index {idx} missing required fields: {', '.join(missing)}")

        # Validate attribute is a non-empty string
        attribute = condition.get("attribute")
        if attribute is not None and (not isinstance(attribute, str) or not attribute.strip()):
            errors.append(f"Condition at index {idx} has invalid 'attribute': must be a non-empty string")

        # Validate operator is a non-empty string
        operator = condition.get("operator")
        if operator is not None and (not isinstance(operator, str) or not operator.strip()):
            errors.append(f"Condition at index {idx} has invalid 'operator': must be a non-empty string")

    return errors


def _evaluate_condition(condition: dict[str, Any], context: dict[str, Any]) -> bool:
    """Evaluate a single condition against a context.

    Args:
        condition: The condition to evaluate.
        context: The context attributes to test against.

    Returns:
        True if the condition matches, False otherwise.

    """
    attribute = condition.get("attribute", "")
    operator = condition.get("operator", "")
    value = condition.get("value")

    context_value = context.get(attribute)

    # Handle different operators
    if operator == "eq":
        return context_value == value
    elif operator == "ne":
        return context_value != value
    elif operator == "in":
        if isinstance(value, list):
            return context_value in value
        return False
    elif operator == "not_in":
        if isinstance(value, list):
            return context_value not in value
        return True
    elif operator == "contains":
        if isinstance(context_value, str) and isinstance(value, str):
            return value in context_value
        if isinstance(context_value, list):
            return value in context_value
        return False
    elif operator == "not_contains":
        if isinstance(context_value, str) and isinstance(value, str):
            return value not in context_value
        if isinstance(context_value, list):
            return value not in context_value
        return True
    elif operator == "starts_with":
        if isinstance(context_value, str) and isinstance(value, str):
            return context_value.startswith(value)
        return False
    elif operator == "ends_with":
        if isinstance(context_value, str) and isinstance(value, str):
            return context_value.endswith(value)
        return False
    elif operator == "gt":
        try:
            if context_value is None or value is None:
                return False
            return context_value > value  # type: ignore[operator]
        except TypeError:
            return False
    elif operator == "gte":
        try:
            if context_value is None or value is None:
                return False
            return context_value >= value  # type: ignore[operator]
        except TypeError:
            return False
    elif operator == "lt":
        try:
            if context_value is None or value is None:
                return False
            return context_value < value  # type: ignore[operator]
        except TypeError:
            return False
    elif operator == "lte":
        try:
            if context_value is None or value is None:
                return False
            return context_value <= value  # type: ignore[operator]
        except TypeError:
            return False
    elif operator == "exists":
        return attribute in context
    elif operator == "not_exists":
        return attribute not in context
    elif operator == "regex":
        import re

        if isinstance(context_value, str) and isinstance(value, str):
            try:
                return bool(re.search(value, context_value))
            except re.error:
                return False
        return False
    else:
        # Unknown operator, default to not matching
        return False


class SegmentsController(Controller):
    """Controller for user segment management endpoints.

    Provides CRUD operations for user segments with:
    - Permission-based access control
    - Audit logging of all changes
    - Pagination and filtering for list endpoints
    - Hierarchical segment support
    - Segment evaluation testing

    Attributes:
        path: The base path for all segment endpoints.
        tags: OpenAPI tags for documentation.
        dependencies: Dependency injection providers.

    Example:
        Using the controller endpoints::

            # List all segments
            GET /admin/segments?page=1&page_size=20

            # Get a specific segment by ID
            GET /admin/segments/{segment_id}

            # Get a segment by name
            GET /admin/segments/by-name/{name}

            # Create a new segment
            POST /admin/segments
            {
                "name": "premium_users",
                "description": "Premium plan subscribers",
                "conditions": [
                    {"attribute": "plan", "operator": "eq", "value": "premium"}
                ]
            }

            # Update a segment
            PATCH /admin/segments/{segment_id}
            {
                "enabled": false
            }

            # Get child segments
            GET /admin/segments/{segment_id}/children

            # Test segment matching
            POST /admin/segments/{segment_id}/evaluate
            {
                "context": {"plan": "premium", "country": "US"}
            }

            # Delete a segment
            DELETE /admin/segments/{segment_id}

    """

    path: ClassVar[str] = "/admin/segments"
    tags: ClassVar[list[str]] = ["Admin - Segments"]
    dependencies: ClassVar[dict[str, Provide]] = {
        "storage": Provide(provide_storage),
        "audit_logger": Provide(provide_audit_logger),
    }

    @get(
        "/",
        guards=[require_permission(Permission.SEGMENTS_READ)],
        summary="List user segments",
        description="Retrieve a paginated list of user segments with optional filtering.",
        status_code=HTTP_200_OK,
    )
    async def list_segments(
        self,
        storage: StorageBackend,
        page: int = Parameter(
            default=1,
            ge=1,
            description="Page number (1-indexed)",
        ),
        page_size: int = Parameter(
            default=20,
            ge=1,
            le=100,
            description="Number of items per page",
        ),
        enabled: bool | None = Parameter(
            default=None,
            description="Filter by enabled status",
        ),
        search: str | None = Parameter(
            default=None,
            description="Search in name and description",
        ),
        parent_id: UUID | None = Parameter(
            default=None,
            description="Filter by parent segment ID (use with null for root segments)",
        ),
    ) -> PaginatedResponse[SegmentResponse]:
        """List user segments with pagination and filtering.

        Args:
            storage: The storage backend for segment operations.
            page: Page number (1-indexed).
            page_size: Number of items per page.
            enabled: Optional enabled status filter.
            search: Optional search term for name/description.
            parent_id: Optional parent segment ID filter.

        Returns:
            Paginated list of segment responses.

        """
        # Get all segments
        all_segments = await storage.get_all_segments()

        # Apply enabled filter
        if enabled is not None:
            all_segments = [s for s in all_segments if s.enabled == enabled]

        # Apply parent_id filter
        if parent_id is not None:
            all_segments = [s for s in all_segments if s.parent_segment_id == parent_id]

        # Apply search filter
        if search is not None:
            search_lower = search.lower()
            all_segments = [
                s
                for s in all_segments
                if search_lower in s.name.lower() or (s.description and search_lower in s.description.lower())
            ]

        # Sort by created_at descending (newest first)
        all_segments.sort(
            key=lambda s: s.created_at if s.created_at else datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

        # Calculate pagination
        total = len(all_segments)
        total_pages = max(1, math.ceil(total / page_size))
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_segments = all_segments[start_idx:end_idx]

        # Get children counts for each segment
        items: list[SegmentResponse] = []
        for segment in page_segments:
            children = await storage.get_child_segments(segment.id)
            items.append(_segment_to_response(segment, children_count=len(children)))

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @get(
        "/{segment_id:uuid}",
        guards=[require_permission(Permission.SEGMENTS_READ)],
        summary="Get segment by ID",
        description="Retrieve a single user segment by its UUID.",
        status_code=HTTP_200_OK,
    )
    async def get_segment_by_id(
        self,
        storage: StorageBackend,
        segment_id: UUID = Parameter(description="The segment's UUID"),
    ) -> SegmentResponse:
        """Get a single segment by its UUID.

        Args:
            storage: The storage backend for segment operations.
            segment_id: The UUID of the segment to retrieve.

        Returns:
            The segment response DTO.

        Raises:
            NotFoundException: If the segment is not found.

        """
        segment = await storage.get_segment(segment_id)
        if segment is None:
            raise NotFoundException(
                detail=f"Segment with ID '{segment_id}' not found",
            )

        # Get children count
        children = await storage.get_child_segments(segment_id)

        return _segment_to_response(segment, children_count=len(children))

    @get(
        "/by-name/{name:str}",
        guards=[require_permission(Permission.SEGMENTS_READ)],
        summary="Get segment by name",
        description="Retrieve a single user segment by its unique name.",
        status_code=HTTP_200_OK,
    )
    async def get_segment_by_name(
        self,
        storage: StorageBackend,
        name: str = Parameter(description="The segment's unique name"),
    ) -> SegmentResponse:
        """Get a single segment by its name.

        Args:
            storage: The storage backend for segment operations.
            name: The unique name of the segment to retrieve.

        Returns:
            The segment response DTO.

        Raises:
            NotFoundException: If the segment is not found.

        """
        segment = await storage.get_segment_by_name(name)
        if segment is None:
            raise NotFoundException(
                detail=f"Segment with name '{name}' not found",
            )

        # Get children count
        children = await storage.get_child_segments(segment.id)

        return _segment_to_response(segment, children_count=len(children))

    @post(
        "/",
        guards=[require_permission(Permission.SEGMENTS_WRITE)],
        summary="Create a new segment",
        description="Create a new user segment with the specified configuration.",
        status_code=HTTP_201_CREATED,
    )
    async def create_segment(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        data: CreateSegmentRequest,
    ) -> SegmentResponse:
        """Create a new user segment.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for segment operations.
            audit_logger: Optional audit logger for recording the action.
            data: The segment creation request data.

        Returns:
            The created segment response DTO.

        Raises:
            HTTPException: If a segment with the same name already exists,
                if parent segment does not exist, or if conditions are invalid.

        """
        # Check if segment with this name already exists
        existing = await storage.get_segment_by_name(data.name)
        if existing is not None:
            raise HTTPException(
                status_code=HTTP_409_CONFLICT,
                detail=f"Segment with name '{data.name}' already exists",
            )

        # Validate parent segment exists if provided
        if data.parent_segment_id is not None:
            parent = await storage.get_segment(data.parent_segment_id)
            if parent is None:
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail=f"Parent segment with ID '{data.parent_segment_id}' not found",
                )

        # Validate conditions
        if data.conditions:
            validation_errors = _validate_conditions(data.conditions)
            if validation_errors:
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail=f"Invalid conditions: {'; '.join(validation_errors)}",
                )

        # Create the segment model
        segment = Segment(
            name=data.name,
            description=data.description,
            conditions=list(data.conditions),
            parent_segment_id=data.parent_segment_id,
            enabled=data.enabled,
        )

        # Persist the segment
        created_segment = await storage.create_segment(segment)

        # Audit log the creation
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            metadata: dict[str, Any] = {}
            if data.parent_segment_id is not None:
                parent = await storage.get_segment(data.parent_segment_id)
                if parent is not None:
                    metadata["parent_segment_name"] = parent.name
                    metadata["hierarchy_level"] = await self._get_hierarchy_level(storage, data.parent_segment_id) + 1
            else:
                metadata["hierarchy_level"] = 0

            await audit_admin_action(
                audit_logger,
                action=AuditAction.CREATE,
                resource_type=ResourceType.SEGMENT,
                resource_id=created_segment.id,
                resource_key=created_segment.name,
                changes={"after": _segment_to_dict(created_segment)},
                metadata=metadata,
                actor_id=actor_info.actor_id,
                actor_type=actor_info.actor_type,
                ip_address=actor_info.ip_address,
                user_agent=actor_info.user_agent,
            )

        return _segment_to_response(created_segment, children_count=0)

    @put(
        "/{segment_id:uuid}",
        guards=[require_permission(Permission.SEGMENTS_WRITE)],
        summary="Full update of a segment",
        description="Replace all segment fields with the provided values.",
        status_code=HTTP_200_OK,
    )
    async def update_segment_full(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        data: UpdateSegmentRequest,
        segment_id: UUID = Parameter(description="The segment's UUID"),
    ) -> SegmentResponse:
        """Perform a full update of a user segment.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for segment operations.
            audit_logger: Optional audit logger for recording the action.
            data: The segment update request data.
            segment_id: The UUID of the segment to update.

        Returns:
            The updated segment response DTO.

        Raises:
            NotFoundException: If the segment is not found.
            HTTPException: If validation fails.

        """
        # Find the existing segment
        segment = await storage.get_segment(segment_id)
        if segment is None:
            raise NotFoundException(
                detail=f"Segment with ID '{segment_id}' not found",
            )

        # Store before state for audit
        before_state = _segment_to_dict(segment)

        # Apply all updates with validation
        await self._apply_update(storage, segment, data, segment_id, full_update=True)

        # Persist the update
        updated_segment = await storage.update_segment(segment)

        # Get children count
        children = await storage.get_child_segments(segment_id)

        # Audit log the update
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            changes = diff_changes(
                before_state,
                _segment_to_dict(updated_segment),
                excluded_keys=["id"],
            )
            metadata = await self._get_hierarchy_metadata(storage, updated_segment)
            await audit_admin_action(
                audit_logger,
                action=AuditAction.UPDATE,
                resource_type=ResourceType.SEGMENT,
                resource_id=updated_segment.id,
                resource_key=updated_segment.name,
                changes=changes,
                metadata=metadata,
                actor_id=actor_info.actor_id,
                actor_type=actor_info.actor_type,
                ip_address=actor_info.ip_address,
                user_agent=actor_info.user_agent,
            )

        return _segment_to_response(updated_segment, children_count=len(children))

    @patch(
        "/{segment_id:uuid}",
        guards=[require_permission(Permission.SEGMENTS_WRITE)],
        summary="Partial update of a segment",
        description="Update only the specified segment fields.",
        status_code=HTTP_200_OK,
    )
    async def update_segment_partial(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        data: UpdateSegmentRequest,
        segment_id: UUID = Parameter(description="The segment's UUID"),
    ) -> SegmentResponse:
        """Perform a partial update of a user segment.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for segment operations.
            audit_logger: Optional audit logger for recording the action.
            data: The segment update request data (only provided fields are updated).
            segment_id: The UUID of the segment to update.

        Returns:
            The updated segment response DTO.

        Raises:
            NotFoundException: If the segment is not found.
            HTTPException: If validation fails.

        """
        # Find the existing segment
        segment = await storage.get_segment(segment_id)
        if segment is None:
            raise NotFoundException(
                detail=f"Segment with ID '{segment_id}' not found",
            )

        # Store before state for audit
        before_state = _segment_to_dict(segment)

        # Apply partial updates with validation
        await self._apply_update(storage, segment, data, segment_id, full_update=False)

        # Persist the update
        updated_segment = await storage.update_segment(segment)

        # Get children count
        children = await storage.get_child_segments(segment_id)

        # Audit log the update
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            changes = diff_changes(
                before_state,
                _segment_to_dict(updated_segment),
                excluded_keys=["id"],
            )
            metadata = await self._get_hierarchy_metadata(storage, updated_segment)
            await audit_admin_action(
                audit_logger,
                action=AuditAction.UPDATE,
                resource_type=ResourceType.SEGMENT,
                resource_id=updated_segment.id,
                resource_key=updated_segment.name,
                changes=changes,
                metadata=metadata,
                actor_id=actor_info.actor_id,
                actor_type=actor_info.actor_type,
                ip_address=actor_info.ip_address,
                user_agent=actor_info.user_agent,
            )

        return _segment_to_response(updated_segment, children_count=len(children))

    @delete(
        "/{segment_id:uuid}",
        guards=[require_permission(Permission.SEGMENTS_WRITE)],
        summary="Delete a segment",
        description="Permanently delete a user segment.",
        status_code=HTTP_204_NO_CONTENT,
    )
    async def delete_segment(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        segment_id: UUID = Parameter(description="The segment's UUID"),
    ) -> None:
        """Delete a user segment.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for segment operations.
            audit_logger: Optional audit logger for recording the action.
            segment_id: The UUID of the segment to delete.

        Raises:
            NotFoundException: If the segment is not found.
            HTTPException: If the segment has child segments.

        """
        # Find the existing segment
        segment = await storage.get_segment(segment_id)
        if segment is None:
            raise NotFoundException(
                detail=f"Segment with ID '{segment_id}' not found",
            )

        # Check for child segments
        children = await storage.get_child_segments(segment_id)
        if children:
            raise HTTPException(
                status_code=HTTP_409_CONFLICT,
                detail=f"Cannot delete segment '{segment.name}': it has {len(children)} child segment(s). "
                f"Delete or reassign child segments first.",
            )

        # Store before state for audit
        before_state = _segment_to_dict(segment)
        metadata = await self._get_hierarchy_metadata(storage, segment)

        # Delete the segment
        deleted = await storage.delete_segment(segment_id)
        if not deleted:
            raise NotFoundException(
                detail=f"Segment with ID '{segment_id}' not found",
            )

        # Audit log the deletion
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            await audit_admin_action(
                audit_logger,
                action=AuditAction.DELETE,
                resource_type=ResourceType.SEGMENT,
                resource_id=segment_id,
                resource_key=segment.name,
                changes={"before": before_state},
                metadata=metadata,
                actor_id=actor_info.actor_id,
                actor_type=actor_info.actor_type,
                ip_address=actor_info.ip_address,
                user_agent=actor_info.user_agent,
            )

    @get(
        "/{segment_id:uuid}/children",
        guards=[require_permission(Permission.SEGMENTS_READ)],
        summary="Get child segments",
        description="Retrieve all child segments of a parent segment.",
        status_code=HTTP_200_OK,
    )
    async def get_child_segments(
        self,
        storage: StorageBackend,
        segment_id: UUID = Parameter(description="The parent segment's UUID"),
    ) -> list[SegmentResponse]:
        """Get all child segments of a parent segment.

        Args:
            storage: The storage backend for segment operations.
            segment_id: The UUID of the parent segment.

        Returns:
            List of child segment response DTOs.

        Raises:
            NotFoundException: If the parent segment is not found.

        """
        # Verify parent segment exists
        parent = await storage.get_segment(segment_id)
        if parent is None:
            raise NotFoundException(
                detail=f"Segment with ID '{segment_id}' not found",
            )

        # Get child segments
        children = await storage.get_child_segments(segment_id)

        # Convert to response DTOs with their own children counts
        items: list[SegmentResponse] = []
        for child in children:
            grandchildren = await storage.get_child_segments(child.id)
            items.append(_segment_to_response(child, children_count=len(grandchildren)))

        return items

    @post(
        "/{segment_id:uuid}/evaluate",
        guards=[require_permission(Permission.SEGMENTS_READ)],
        summary="Evaluate segment membership",
        description="Test whether a given context matches the segment conditions.",
        status_code=HTTP_200_OK,
    )
    async def evaluate_segment(
        self,
        storage: StorageBackend,
        data: EvaluateSegmentRequest,
        segment_id: UUID = Parameter(description="The segment's UUID"),
    ) -> EvaluateSegmentResponse:
        """Evaluate whether a context matches the segment conditions.

        Args:
            storage: The storage backend for segment operations.
            data: The evaluation request with context attributes.
            segment_id: The UUID of the segment to evaluate.

        Returns:
            The evaluation result including matched and failed conditions.

        Raises:
            NotFoundException: If the segment is not found.
            HTTPException: If the segment is disabled.

        """
        # Find the segment
        segment = await storage.get_segment(segment_id)
        if segment is None:
            raise NotFoundException(
                detail=f"Segment with ID '{segment_id}' not found",
            )

        # Check if segment is enabled
        if not segment.enabled:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Segment '{segment.name}' is disabled and cannot be evaluated",
            )

        # Collect all conditions including from parent segments
        all_conditions = await self._collect_conditions(storage, segment)

        # Evaluate each condition
        matched_conditions: list[dict[str, Any]] = []
        failed_conditions: list[dict[str, Any]] = []

        for condition in all_conditions:
            if _evaluate_condition(condition, data.context):
                matched_conditions.append(condition)
            else:
                failed_conditions.append(condition)

        # All conditions must match for the segment to match
        matches = len(failed_conditions) == 0 and len(all_conditions) > 0

        return EvaluateSegmentResponse(
            matches=matches,
            segment_id=segment_id,
            segment_name=segment.name,
            matched_conditions=matched_conditions,
            failed_conditions=failed_conditions,
        )

    async def _collect_conditions(
        self,
        storage: StorageBackend,
        segment: Segment,
    ) -> list[dict[str, Any]]:
        """Collect all conditions from a segment and its parent hierarchy.

        Args:
            storage: The storage backend for segment operations.
            segment: The segment to collect conditions from.

        Returns:
            List of all conditions from the segment hierarchy.

        """
        conditions: list[dict[str, Any]] = []

        # If there's a parent, collect its conditions first (inheritance)
        if segment.parent_segment_id is not None:
            parent = await storage.get_segment(segment.parent_segment_id)
            if parent is not None and parent.enabled:
                parent_conditions = await self._collect_conditions(storage, parent)
                conditions.extend(parent_conditions)

        # Add this segment's conditions
        if segment.conditions:
            conditions.extend(segment.conditions)

        return conditions

    async def _get_hierarchy_level(
        self,
        storage: StorageBackend,
        segment_id: UUID,
    ) -> int:
        """Get the hierarchy level of a segment (0 = root).

        Args:
            storage: The storage backend for segment operations.
            segment_id: The UUID of the segment.

        Returns:
            The hierarchy level (0 for root segments).

        """
        level = 0
        current_id: UUID | None = segment_id

        while current_id is not None:
            segment = await storage.get_segment(current_id)
            if segment is None:
                break
            current_id = segment.parent_segment_id
            if current_id is not None:
                level += 1

        return level

    async def _get_hierarchy_metadata(
        self,
        storage: StorageBackend,
        segment: Segment,
    ) -> dict[str, Any]:
        """Build hierarchy metadata for audit logging.

        Args:
            storage: The storage backend for segment operations.
            segment: The segment to get metadata for.

        Returns:
            Dictionary with hierarchy information.

        """
        metadata: dict[str, Any] = {}

        if segment.parent_segment_id is not None:
            parent = await storage.get_segment(segment.parent_segment_id)
            if parent is not None:
                metadata["parent_segment_name"] = parent.name

        # Build ancestry path
        ancestry: list[str] = []
        current_id = segment.parent_segment_id
        while current_id is not None:
            parent = await storage.get_segment(current_id)
            if parent is None:
                break
            ancestry.insert(0, parent.name)
            current_id = parent.parent_segment_id

        if ancestry:
            metadata["ancestry"] = ancestry

        metadata["hierarchy_level"] = len(ancestry)

        # Count descendants
        children = await storage.get_child_segments(segment.id)
        metadata["children_count"] = len(children)

        return metadata

    async def _apply_update(
        self,
        storage: StorageBackend,
        segment: Segment,
        data: UpdateSegmentRequest,
        segment_id: UUID,
        *,
        full_update: bool,
    ) -> None:
        """Apply update data to a segment with validation.

        Args:
            storage: The storage backend for segment operations.
            segment: The segment to update.
            data: The update request data.
            segment_id: The UUID of the segment being updated.
            full_update: If True, set None values; if False, skip None values.

        Raises:
            HTTPException: If validation fails.

        """
        # Validate name uniqueness if changing
        if data.name is not None and data.name != segment.name:
            existing = await storage.get_segment_by_name(data.name)
            if existing is not None:
                raise HTTPException(
                    status_code=HTTP_409_CONFLICT,
                    detail=f"Segment with name '{data.name}' already exists",
                )
            segment.name = data.name  # type: ignore[misc]
        elif full_update:
            pass  # Name is required, don't clear it

        if data.description is not None:
            segment.description = data.description  # type: ignore[misc]
        elif full_update:
            segment.description = None  # type: ignore[misc]

        # Validate and apply conditions
        if data.conditions is not None:
            validation_errors = _validate_conditions(data.conditions)
            if validation_errors:
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail=f"Invalid conditions: {'; '.join(validation_errors)}",
                )
            segment.conditions = list(data.conditions)  # type: ignore[misc]

        # Validate parent segment
        if data.parent_segment_id is not None:
            # Check parent exists
            parent = await storage.get_segment(data.parent_segment_id)
            if parent is None:
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail=f"Parent segment with ID '{data.parent_segment_id}' not found",
                )

            # Check for circular reference
            if await self._would_create_cycle(storage, segment_id, data.parent_segment_id):
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail="Cannot set parent: this would create a circular reference",
                )

            segment.parent_segment_id = data.parent_segment_id  # type: ignore[misc]
        elif full_update:
            segment.parent_segment_id = None  # type: ignore[misc]

        if data.enabled is not None:
            segment.enabled = data.enabled  # type: ignore[misc]

    async def _would_create_cycle(
        self,
        storage: StorageBackend,
        segment_id: UUID,
        proposed_parent_id: UUID,
    ) -> bool:
        """Check if setting a parent would create a circular reference.

        Args:
            storage: The storage backend for segment operations.
            segment_id: The ID of the segment being updated.
            proposed_parent_id: The proposed new parent ID.

        Returns:
            True if a cycle would be created, False otherwise.

        """
        # If the proposed parent is the segment itself, it's a cycle
        if segment_id == proposed_parent_id:
            return True

        # Walk up the proposed parent's ancestry to check for cycles
        current_id: UUID | None = proposed_parent_id
        visited: set[UUID] = {segment_id}

        while current_id is not None:
            if current_id in visited:
                return True
            visited.add(current_id)

            parent = await storage.get_segment(current_id)
            if parent is None:
                break
            current_id = parent.parent_segment_id

        return False
