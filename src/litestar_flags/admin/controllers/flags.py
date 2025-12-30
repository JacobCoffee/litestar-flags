"""Feature flags CRUD controller for the Admin API.

This module provides a Litestar controller for managing feature flags through
the Admin API. It includes endpoints for listing, creating, updating, and
deleting flags with proper permission guards and audit logging.

Example:
    Registering the controller with a Litestar app::

        from litestar import Litestar
        from litestar_flags.admin.controllers import FlagsController

        app = Litestar(
            route_handlers=[FlagsController],
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
    HTTP_409_CONFLICT,
)

from litestar_flags.admin.audit import (
    AuditAction,
    AuditLogger,
    ResourceType,
    audit_admin_action,
    diff_changes,
)
from litestar_flags.admin.dto import (
    CreateFlagRequest,
    FlagResponse,
    PaginatedResponse,
    UpdateFlagRequest,
)
from litestar_flags.admin.guards import Permission, require_permission
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.types import FlagStatus

from litestar_flags.protocols import StorageBackend

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection

__all__ = ["FlagsController"]


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


def _flag_to_response(flag: FeatureFlag) -> FlagResponse:
    """Convert a FeatureFlag model to a FlagResponse DTO.

    Args:
        flag: The FeatureFlag model instance.

    Returns:
        A FlagResponse DTO with all flag details.

    """
    # Count related objects
    rules_count = len(flag.rules) if hasattr(flag, "rules") and flag.rules else 0
    overrides_count = len(flag.overrides) if hasattr(flag, "overrides") and flag.overrides else 0
    variants_count = len(flag.variants) if hasattr(flag, "variants") and flag.variants else 0

    # Get metadata (use metadata_ attribute to avoid SQLAlchemy MetaData class attribute)
    metadata = getattr(flag, "metadata_", None)
    if metadata is None or not isinstance(metadata, dict):
        metadata = {}

    return FlagResponse(
        id=flag.id,
        key=flag.key,
        name=flag.name,
        description=flag.description,
        flag_type=flag.flag_type,
        status=flag.status,
        default_enabled=flag.default_enabled,
        default_value=flag.default_value,
        tags=flag.tags or [],
        metadata=metadata,
        rules_count=rules_count,
        overrides_count=overrides_count,
        variants_count=variants_count,
        created_at=flag.created_at,
        updated_at=flag.updated_at,
    )


def _flag_to_dict(flag: FeatureFlag) -> dict[str, Any]:
    """Convert a FeatureFlag to a dictionary for audit logging.

    Args:
        flag: The FeatureFlag model instance.

    Returns:
        Dictionary representation of the flag.

    """
    metadata = getattr(flag, "metadata_", None) or getattr(flag, "metadata", {}) or {}
    return {
        "id": str(flag.id),
        "key": flag.key,
        "name": flag.name,
        "description": flag.description,
        "flag_type": flag.flag_type.value if flag.flag_type else None,
        "status": flag.status.value if flag.status else None,
        "default_enabled": flag.default_enabled,
        "default_value": flag.default_value,
        "tags": flag.tags,
        "metadata": metadata,
    }


class FlagsController(Controller):
    """Controller for feature flag management endpoints.

    Provides CRUD operations for feature flags with:
    - Permission-based access control
    - Audit logging of all changes
    - Pagination and filtering for list endpoints
    - Proper error handling and response DTOs

    Attributes:
        path: The base path for all flag endpoints.
        tags: OpenAPI tags for documentation.
        dependencies: Dependency injection providers.

    Example:
        Using the controller endpoints::

            # List all flags
            GET /admin/flags?page=1&page_size=20

            # Get a specific flag
            GET /admin/flags/{flag_id}

            # Create a new flag
            POST /admin/flags
            {
                "key": "new_feature",
                "name": "New Feature",
                "flag_type": "boolean"
            }

            # Update a flag
            PATCH /admin/flags/{flag_id}
            {
                "default_enabled": true
            }

            # Delete a flag
            DELETE /admin/flags/{flag_id}

    """

    path: ClassVar[str] = "/admin/flags"
    tags: ClassVar[list[str]] = ["Admin - Flags"]
    dependencies: ClassVar[dict[str, Provide]] = {
        "storage": Provide(provide_storage),
        "audit_logger": Provide(provide_audit_logger),
    }

    @get(
        "/",
        guards=[require_permission(Permission.FLAGS_READ)],
        summary="List feature flags",
        description="Retrieve a paginated list of feature flags with optional filtering.",
        status_code=HTTP_200_OK,
    )
    async def list_flags(
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
        status: FlagStatus | None = Parameter(
            default=None,
            description="Filter by flag status",
        ),
        tag: str | None = Parameter(
            default=None,
            description="Filter by tag",
        ),
        search: str | None = Parameter(
            default=None,
            description="Search in key and name",
        ),
    ) -> PaginatedResponse[FlagResponse]:
        """List feature flags with pagination and filtering.

        Args:
            storage: The storage backend for flag operations.
            page: Page number (1-indexed).
            page_size: Number of items per page.
            status: Optional status filter.
            tag: Optional tag filter.
            search: Optional search term for key/name.

        Returns:
            Paginated list of flag responses.

        """
        # Get all flags (we'll filter in memory for now)
        # In production, this should use database-level filtering
        all_flags: list[FeatureFlag] = []

        # Get all flags based on status filter
        if status == FlagStatus.ACTIVE:
            all_flags = await storage.get_all_active_flags()
        else:
            # Get all flags by iterating through storage
            # This is a limitation of the current StorageBackend protocol
            active_flags = await storage.get_all_active_flags()
            all_flags = active_flags

            # Try to get archived/inactive flags if storage supports it
            if hasattr(storage, "get_all_flags"):
                all_flags = await storage.get_all_flags()  # type: ignore[attr-defined]

        # Apply status filter
        if status is not None:
            all_flags = [f for f in all_flags if f.status == status]

        # Apply tag filter
        if tag is not None:
            all_flags = [f for f in all_flags if tag in (f.tags or [])]

        # Apply search filter
        if search is not None:
            search_lower = search.lower()
            all_flags = [f for f in all_flags if search_lower in f.key.lower() or search_lower in f.name.lower()]

        # Sort by created_at descending (newest first)
        all_flags.sort(
            key=lambda f: f.created_at if f.created_at else datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

        # Calculate pagination
        total = len(all_flags)
        total_pages = max(1, math.ceil(total / page_size))
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_flags = all_flags[start_idx:end_idx]

        # Convert to response DTOs
        items = [_flag_to_response(f) for f in page_flags]

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @get(
        "/{flag_id:uuid}",
        guards=[require_permission(Permission.FLAGS_READ)],
        summary="Get flag by ID",
        description="Retrieve a single feature flag by its UUID.",
        status_code=HTTP_200_OK,
    )
    async def get_flag_by_id(
        self,
        storage: StorageBackend,
        flag_id: UUID = Parameter(description="The flag's UUID"),
    ) -> FlagResponse:
        """Get a single flag by its UUID.

        Args:
            storage: The storage backend for flag operations.
            flag_id: The UUID of the flag to retrieve.

        Returns:
            The flag response DTO.

        Raises:
            NotFoundException: If the flag is not found.

        """
        # Try to find flag by ID
        flag = await self._get_flag_by_id(storage, flag_id)
        if flag is None:
            raise NotFoundException(
                detail=f"Flag with ID '{flag_id}' not found",
            )

        return _flag_to_response(flag)

    @get(
        "/by-key/{key:str}",
        guards=[require_permission(Permission.FLAGS_READ)],
        summary="Get flag by key",
        description="Retrieve a single feature flag by its unique key.",
        status_code=HTTP_200_OK,
    )
    async def get_flag_by_key(
        self,
        storage: StorageBackend,
        key: str = Parameter(description="The flag's unique key"),
    ) -> FlagResponse:
        """Get a single flag by its key.

        Args:
            storage: The storage backend for flag operations.
            key: The unique key of the flag to retrieve.

        Returns:
            The flag response DTO.

        Raises:
            NotFoundException: If the flag is not found.

        """
        flag = await storage.get_flag(key)
        if flag is None:
            raise NotFoundException(
                detail=f"Flag with key '{key}' not found",
            )

        return _flag_to_response(flag)

    @post(
        "/",
        guards=[require_permission(Permission.FLAGS_WRITE)],
        summary="Create a new flag",
        description="Create a new feature flag with the specified configuration.",
        status_code=HTTP_201_CREATED,
    )
    async def create_flag(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        data: CreateFlagRequest,
    ) -> FlagResponse:
        """Create a new feature flag.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for flag operations.
            audit_logger: Optional audit logger for recording the action.
            data: The flag creation request data.

        Returns:
            The created flag response DTO.

        Raises:
            HTTPException: If a flag with the same key already exists.

        """
        # Check if flag with this key already exists
        existing = await storage.get_flag(data.key)
        if existing is not None:
            raise HTTPException(
                status_code=HTTP_409_CONFLICT,
                detail=f"Flag with key '{data.key}' already exists",
            )

        # Create the flag model
        # Generate ID for memory storage compatibility when using SQLAlchemy models
        from uuid import uuid4

        flag = FeatureFlag(
            id=uuid4(),  # Explicitly set ID for memory storage compatibility
            key=data.key,
            name=data.name,
            description=data.description,
            flag_type=data.flag_type,
            status=FlagStatus.ACTIVE,
            default_enabled=data.default_enabled,
            default_value=data.default_value,
            tags=list(data.tags),
        )

        # Set metadata (handle both attribute names)
        if hasattr(flag, "metadata_"):
            flag.metadata_ = dict(data.metadata)  # type: ignore[misc]
        elif hasattr(flag, "metadata"):
            flag.metadata = dict(data.metadata)  # type: ignore[attr-defined, misc]

        # Persist the flag
        created_flag = await storage.create_flag(flag)

        # Audit log the creation
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            await audit_admin_action(
                audit_logger,
                action=AuditAction.CREATE,
                resource_type=ResourceType.FLAG,
                resource_id=created_flag.id,
                resource_key=created_flag.key,
                changes={"after": _flag_to_dict(created_flag)},
                actor_id=actor_info.actor_id,
                actor_type=actor_info.actor_type,
                ip_address=actor_info.ip_address,
                user_agent=actor_info.user_agent,
            )

        return _flag_to_response(created_flag)

    @put(
        "/{flag_id:uuid}",
        guards=[require_permission(Permission.FLAGS_WRITE)],
        summary="Full update of a flag",
        description="Replace all flag fields with the provided values.",
        status_code=HTTP_200_OK,
    )
    async def update_flag_full(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        data: UpdateFlagRequest,
        flag_id: UUID = Parameter(description="The flag's UUID"),
    ) -> FlagResponse:
        """Perform a full update of a feature flag.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for flag operations.
            audit_logger: Optional audit logger for recording the action.
            data: The flag update request data.
            flag_id: The UUID of the flag to update.

        Returns:
            The updated flag response DTO.

        Raises:
            NotFoundException: If the flag is not found.

        """
        # Find the existing flag
        flag = await self._get_flag_by_id(storage, flag_id)
        if flag is None:
            raise NotFoundException(
                detail=f"Flag with ID '{flag_id}' not found",
            )

        # Store before state for audit
        before_state = _flag_to_dict(flag)

        # Apply all updates
        self._apply_update(flag, data, full_update=True)

        # Persist the update
        updated_flag = await storage.update_flag(flag)

        # Audit log the update
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            changes = diff_changes(
                before_state,
                _flag_to_dict(updated_flag),
                excluded_keys=["id"],
            )
            await audit_admin_action(
                audit_logger,
                action=AuditAction.UPDATE,
                resource_type=ResourceType.FLAG,
                resource_id=updated_flag.id,
                resource_key=updated_flag.key,
                changes=changes,
                actor_id=actor_info.actor_id,
                actor_type=actor_info.actor_type,
                ip_address=actor_info.ip_address,
                user_agent=actor_info.user_agent,
            )

        return _flag_to_response(updated_flag)

    @patch(
        "/{flag_id:uuid}",
        guards=[require_permission(Permission.FLAGS_WRITE)],
        summary="Partial update of a flag",
        description="Update only the specified flag fields.",
        status_code=HTTP_200_OK,
    )
    async def update_flag_partial(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        data: UpdateFlagRequest,
        flag_id: UUID = Parameter(description="The flag's UUID"),
    ) -> FlagResponse:
        """Perform a partial update of a feature flag.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for flag operations.
            audit_logger: Optional audit logger for recording the action.
            data: The flag update request data (only provided fields are updated).
            flag_id: The UUID of the flag to update.

        Returns:
            The updated flag response DTO.

        Raises:
            NotFoundException: If the flag is not found.

        """
        # Find the existing flag
        flag = await self._get_flag_by_id(storage, flag_id)
        if flag is None:
            raise NotFoundException(
                detail=f"Flag with ID '{flag_id}' not found",
            )

        # Store before state for audit
        before_state = _flag_to_dict(flag)

        # Apply partial updates
        self._apply_update(flag, data, full_update=False)

        # Persist the update
        updated_flag = await storage.update_flag(flag)

        # Audit log the update
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            changes = diff_changes(
                before_state,
                _flag_to_dict(updated_flag),
                excluded_keys=["id"],
            )
            await audit_admin_action(
                audit_logger,
                action=AuditAction.UPDATE,
                resource_type=ResourceType.FLAG,
                resource_id=updated_flag.id,
                resource_key=updated_flag.key,
                changes=changes,
                actor_id=actor_info.actor_id,
                actor_type=actor_info.actor_type,
                ip_address=actor_info.ip_address,
                user_agent=actor_info.user_agent,
            )

        return _flag_to_response(updated_flag)

    @delete(
        "/{flag_id:uuid}",
        guards=[require_permission(Permission.FLAGS_DELETE)],
        summary="Delete a flag",
        description="Permanently delete a feature flag.",
        status_code=HTTP_204_NO_CONTENT,
    )
    async def delete_flag(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        flag_id: UUID = Parameter(description="The flag's UUID"),
    ) -> None:
        """Delete a feature flag.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for flag operations.
            audit_logger: Optional audit logger for recording the action.
            flag_id: The UUID of the flag to delete.

        Raises:
            NotFoundException: If the flag is not found.

        """
        # Find the existing flag
        flag = await self._get_flag_by_id(storage, flag_id)
        if flag is None:
            raise NotFoundException(
                detail=f"Flag with ID '{flag_id}' not found",
            )

        # Store before state for audit
        before_state = _flag_to_dict(flag)

        # Delete the flag
        deleted = await storage.delete_flag(flag.key)
        if not deleted:
            raise NotFoundException(
                detail=f"Flag with ID '{flag_id}' not found",
            )

        # Audit log the deletion
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            await audit_admin_action(
                audit_logger,
                action=AuditAction.DELETE,
                resource_type=ResourceType.FLAG,
                resource_id=flag_id,
                resource_key=flag.key,
                changes={"before": before_state},
                actor_id=actor_info.actor_id,
                actor_type=actor_info.actor_type,
                ip_address=actor_info.ip_address,
                user_agent=actor_info.user_agent,
            )

    @post(
        "/{flag_id:uuid}/archive",
        guards=[require_permission(Permission.FLAGS_WRITE)],
        summary="Archive a flag",
        description="Archive a feature flag, making it inactive but preserving its data.",
        status_code=HTTP_200_OK,
    )
    async def archive_flag(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        flag_id: UUID = Parameter(description="The flag's UUID"),
    ) -> FlagResponse:
        """Archive a feature flag.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for flag operations.
            audit_logger: Optional audit logger for recording the action.
            flag_id: The UUID of the flag to archive.

        Returns:
            The archived flag response DTO.

        Raises:
            NotFoundException: If the flag is not found.
            HTTPException: If the flag is already archived.

        """
        # Find the existing flag
        flag = await self._get_flag_by_id(storage, flag_id)
        if flag is None:
            raise NotFoundException(
                detail=f"Flag with ID '{flag_id}' not found",
            )

        # Check if already archived
        if flag.status == FlagStatus.ARCHIVED:
            raise HTTPException(
                status_code=HTTP_409_CONFLICT,
                detail=f"Flag '{flag.key}' is already archived",
            )

        # Store before state for audit
        before_state = _flag_to_dict(flag)

        # Archive the flag
        flag.status = FlagStatus.ARCHIVED  # type: ignore[misc]

        # Persist the update
        updated_flag = await storage.update_flag(flag)

        # Audit log the archive action
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            changes = diff_changes(
                before_state,
                _flag_to_dict(updated_flag),
                excluded_keys=["id"],
            )
            await audit_admin_action(
                audit_logger,
                action=AuditAction.ARCHIVE,
                resource_type=ResourceType.FLAG,
                resource_id=updated_flag.id,
                resource_key=updated_flag.key,
                changes=changes,
                actor_id=actor_info.actor_id,
                actor_type=actor_info.actor_type,
                ip_address=actor_info.ip_address,
                user_agent=actor_info.user_agent,
            )

        return _flag_to_response(updated_flag)

    @post(
        "/{flag_id:uuid}/restore",
        guards=[require_permission(Permission.FLAGS_WRITE)],
        summary="Restore an archived flag",
        description="Restore a previously archived feature flag to active status.",
        status_code=HTTP_200_OK,
    )
    async def restore_flag(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        flag_id: UUID = Parameter(description="The flag's UUID"),
    ) -> FlagResponse:
        """Restore an archived feature flag.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for flag operations.
            audit_logger: Optional audit logger for recording the action.
            flag_id: The UUID of the flag to restore.

        Returns:
            The restored flag response DTO.

        Raises:
            NotFoundException: If the flag is not found.
            HTTPException: If the flag is not archived.

        """
        # Find the existing flag
        flag = await self._get_flag_by_id(storage, flag_id)
        if flag is None:
            raise NotFoundException(
                detail=f"Flag with ID '{flag_id}' not found",
            )

        # Check if not archived
        if flag.status != FlagStatus.ARCHIVED:
            raise HTTPException(
                status_code=HTTP_409_CONFLICT,
                detail=f"Flag '{flag.key}' is not archived (current status: {flag.status.value})",
            )

        # Store before state for audit
        before_state = _flag_to_dict(flag)

        # Restore the flag to active status
        flag.status = FlagStatus.ACTIVE  # type: ignore[misc]

        # Persist the update
        updated_flag = await storage.update_flag(flag)

        # Audit log the restore action (using ENABLE since there's no RESTORE action)
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            changes = diff_changes(
                before_state,
                _flag_to_dict(updated_flag),
                excluded_keys=["id"],
            )
            await audit_admin_action(
                audit_logger,
                action=AuditAction.ENABLE,
                resource_type=ResourceType.FLAG,
                resource_id=updated_flag.id,
                resource_key=updated_flag.key,
                changes=changes,
                metadata={"action": "restore_from_archive"},
                actor_id=actor_info.actor_id,
                actor_type=actor_info.actor_type,
                ip_address=actor_info.ip_address,
                user_agent=actor_info.user_agent,
            )

        return _flag_to_response(updated_flag)

    async def _get_flag_by_id(
        self,
        storage: StorageBackend,
        flag_id: UUID,
    ) -> FeatureFlag | None:
        """Get a flag by its UUID.

        This helper method attempts to find a flag by ID using available
        storage methods.

        Args:
            storage: The storage backend for flag operations.
            flag_id: The UUID of the flag to find.

        Returns:
            The FeatureFlag if found, None otherwise.

        """
        # First, try direct ID lookup if storage supports it
        if hasattr(storage, "get_flag_by_id"):
            return await storage.get_flag_by_id(flag_id)  # type: ignore[attr-defined]

        # Fall back to searching through all flags
        if hasattr(storage, "_flags_by_id"):
            # MemoryStorageBackend has this internal attribute
            return storage._flags_by_id.get(flag_id)  # type: ignore[attr-defined]

        # Last resort: iterate through all active flags
        active_flags = await storage.get_all_active_flags()
        for flag in active_flags:
            if flag.id == flag_id:
                return flag

        # Try to get all flags if storage supports it
        if hasattr(storage, "get_all_flags"):
            all_flags = await storage.get_all_flags()  # type: ignore[attr-defined]
            for flag in all_flags:
                if flag.id == flag_id:
                    return flag

        return None

    def _apply_update(
        self,
        flag: FeatureFlag,
        data: UpdateFlagRequest,
        *,
        full_update: bool,
    ) -> None:
        """Apply update data to a flag.

        Args:
            flag: The flag to update.
            data: The update request data.
            full_update: If True, set None values; if False, skip None values.

        """
        if data.name is not None:
            flag.name = data.name  # type: ignore[misc]
        elif full_update:
            pass  # Name is required, don't clear it

        if data.description is not None:
            flag.description = data.description  # type: ignore[misc]
        elif full_update:
            flag.description = None  # type: ignore[misc]

        if data.flag_type is not None:
            flag.flag_type = data.flag_type  # type: ignore[misc]

        if data.status is not None:
            flag.status = data.status  # type: ignore[misc]

        if data.default_enabled is not None:
            flag.default_enabled = data.default_enabled  # type: ignore[misc]

        if data.default_value is not None:
            flag.default_value = data.default_value  # type: ignore[misc]
        elif full_update:
            flag.default_value = None  # type: ignore[misc]

        if data.tags is not None:
            flag.tags = list(data.tags)  # type: ignore[misc]

        if data.metadata is not None:
            # Handle both metadata_ and metadata attributes
            if hasattr(flag, "metadata_"):
                flag.metadata_ = dict(data.metadata)  # type: ignore[misc]
            elif hasattr(flag, "metadata"):
                flag.metadata = dict(data.metadata)  # type: ignore[attr-defined, misc]
