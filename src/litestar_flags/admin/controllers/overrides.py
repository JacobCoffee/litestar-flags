"""Override management controller for the Admin API.

This module provides endpoints for managing entity-specific overrides
on feature flags. Overrides allow specific users, organizations, or other
entities to have different flag values than what targeting rules would determine.

Example:
    Registering the controller with a Litestar app::

        from litestar import Litestar
        from litestar_flags.admin.controllers.overrides import OverridesController

        app = Litestar(
            route_handlers=[OverridesController],
        )

"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID

from litestar import Controller, delete, get, post, put
from litestar.exceptions import HTTPException, NotFoundException, ValidationException
from litestar.params import Parameter
from litestar.status_codes import HTTP_201_CREATED, HTTP_204_NO_CONTENT

from litestar_flags.admin.audit import (
    AuditAction,
    AuditLogger,
    ResourceType,
    audit_admin_action,
    diff_changes,
)
from litestar_flags.admin.dto import (
    CreateOverrideRequest,
    OverrideResponse,
    PaginatedResponse,
    UpdateOverrideRequest,
)
from litestar_flags.admin.guards import Permission, require_permission
from litestar_flags.models.override import FlagOverride
from litestar_flags.storage.memory import MemoryStorageBackend

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection

__all__ = ["EntityOverridesController", "OverridesController"]


# Valid entity types for overrides
VALID_ENTITY_TYPES = frozenset({"user", "organization", "team", "device", "custom"})


def _validate_entity_type(entity_type: str) -> None:
    """Validate that entity_type is a supported value.

    Args:
        entity_type: The entity type to validate.

    Raises:
        ValidationException: If the entity type is not valid.

    """
    if entity_type not in VALID_ENTITY_TYPES:
        raise ValidationException(
            detail=f"Invalid entity_type '{entity_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_ENTITY_TYPES))}"
        )


def _validate_expires_at(expires_at: datetime | None) -> None:
    """Validate that expires_at is in the future if provided.

    Args:
        expires_at: The expiration datetime to validate.

    Raises:
        ValidationException: If expires_at is in the past.

    """
    if expires_at is not None:
        now = datetime.now(UTC)
        if expires_at <= now:
            raise ValidationException(
                detail="expires_at must be in the future"
            )


def _override_to_response(override: FlagOverride) -> OverrideResponse:
    """Convert a FlagOverride model to an OverrideResponse DTO.

    Args:
        override: The FlagOverride model instance.

    Returns:
        An OverrideResponse DTO.

    """
    now = datetime.now(UTC)
    return OverrideResponse(
        id=override.id,
        flag_id=override.flag_id,  # type: ignore[arg-type]
        entity_type=override.entity_type,
        entity_id=override.entity_id,
        enabled=override.enabled,
        value=override.value,
        expires_at=override.expires_at,
        is_expired=override.is_expired(now),
        created_at=override.created_at,
        updated_at=override.updated_at,
    )


def _get_actor_info(connection: ASGIConnection[Any, Any, Any, Any]) -> tuple[str | None, str]:
    """Extract actor information from the connection.

    Args:
        connection: The ASGI connection object.

    Returns:
        Tuple of (actor_id, actor_type).

    """
    user = getattr(connection.state, "user", None) or connection.scope.get("user")
    if user is None:
        return None, "system"

    if hasattr(user, "id"):
        return str(user.id), "user"
    if isinstance(user, dict):
        return user.get("id"), user.get("type", "user")

    return None, "system"


class OverridesController(Controller):
    """Controller for managing flag overrides.

    Provides CRUD operations for entity-specific overrides on feature flags.
    All endpoints are nested under a flag's path.

    Attributes:
        path: Base path for override endpoints.
        tags: OpenAPI tags for documentation grouping.

    """

    path = "/admin/flags/{flag_id:uuid}/overrides"
    tags: ClassVar[list[str]] = ["Admin - Overrides"]

    @get(
        "/",
        summary="List overrides for a flag",
        description="Retrieve all overrides for a specific flag with optional filtering.",
        guards=[require_permission(Permission.FLAGS_READ)],
    )
    async def list_overrides(
        self,
        flag_id: UUID,
        storage: MemoryStorageBackend,
        include_expired: bool = Parameter(
            default=False,
            description="Include expired overrides in the response",
        ),
        entity_type: str | None = Parameter(
            default=None,
            description="Filter by entity type",
        ),
        page: int = Parameter(default=1, ge=1, description="Page number"),
        page_size: int = Parameter(default=20, ge=1, le=100, description="Items per page"),
    ) -> PaginatedResponse[OverrideResponse]:
        """List all overrides for a specific flag.

        Args:
            flag_id: The UUID of the flag.
            storage: The storage backend (injected).
            include_expired: Whether to include expired overrides.
            entity_type: Optional entity type filter.
            page: Page number for pagination.
            page_size: Number of items per page.

        Returns:
            Paginated list of override responses.

        Raises:
            NotFoundException: If the flag does not exist.

        """
        # Verify flag exists
        flag = storage._flags_by_id.get(flag_id)
        if flag is None:
            raise NotFoundException(detail=f"Flag with id '{flag_id}' not found")

        # Get all overrides for this flag
        now = datetime.now(UTC)
        overrides: list[FlagOverride] = []

        for key, override in storage._overrides.items():
            if not key.startswith(f"{flag_id}:"):
                continue

            # Apply entity_type filter
            if entity_type is not None and override.entity_type != entity_type:
                continue

            # Apply expired filter
            is_expired = override.is_expired(now)
            if is_expired and not include_expired:
                continue

            overrides.append(override)

        # Sort by created_at descending
        overrides.sort(
            key=lambda o: o.created_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

        # Paginate
        total = len(overrides)
        start = (page - 1) * page_size
        end = start + page_size
        paginated = overrides[start:end]

        return PaginatedResponse(
            items=[_override_to_response(o) for o in paginated],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total > 0 else 1,
        )

    @get(
        "/{entity_type:str}/{entity_id:str}",
        summary="Get a specific override",
        description="Retrieve an override for a specific entity on a flag.",
        guards=[require_permission(Permission.FLAGS_READ)],
    )
    async def get_override(
        self,
        flag_id: UUID,
        entity_type: str,
        entity_id: str,
        storage: MemoryStorageBackend,
    ) -> OverrideResponse:
        """Get a specific override by flag, entity type, and entity ID.

        Args:
            flag_id: The UUID of the flag.
            entity_type: The type of entity.
            entity_id: The entity's identifier.
            storage: The storage backend (injected).

        Returns:
            The override response.

        Raises:
            NotFoundException: If the flag or override does not exist.
            ValidationException: If the entity type is invalid.

        """
        _validate_entity_type(entity_type)

        # Verify flag exists
        flag = storage._flags_by_id.get(flag_id)
        if flag is None:
            raise NotFoundException(detail=f"Flag with id '{flag_id}' not found")

        override = await storage.get_override(flag_id, entity_type, entity_id)
        if override is None:
            raise NotFoundException(
                detail=f"Override for {entity_type}/{entity_id} on flag '{flag_id}' not found"
            )

        return _override_to_response(override)

    @post(
        "/",
        status_code=HTTP_201_CREATED,
        summary="Create an override",
        description="Create a new entity-specific override for a flag.",
        guards=[require_permission(Permission.FLAGS_WRITE)],
    )
    async def create_override(
        self,
        flag_id: UUID,
        data: CreateOverrideRequest,
        storage: MemoryStorageBackend,
        audit_logger: AuditLogger,
        connection: ASGIConnection[Any, Any, Any, Any],
    ) -> OverrideResponse:
        """Create a new override for an entity on a flag.

        Args:
            flag_id: The UUID of the flag.
            data: The override creation request.
            storage: The storage backend (injected).
            audit_logger: The audit logger (injected).
            connection: The ASGI connection for extracting actor info.

        Returns:
            The created override response.

        Raises:
            NotFoundException: If the flag does not exist.
            ValidationException: If validation fails.
            HTTPException: If the override already exists.

        """
        _validate_entity_type(data.entity_type)
        _validate_expires_at(data.expires_at)

        # Verify flag exists
        flag = storage._flags_by_id.get(flag_id)
        if flag is None:
            raise NotFoundException(detail=f"Flag with id '{flag_id}' not found")

        # Check if override already exists
        existing = await storage.get_override(flag_id, data.entity_type, data.entity_id)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Override for {data.entity_type}/{data.entity_id} already exists on this flag",
            )

        # Create the override
        override = FlagOverride(
            flag_id=flag_id,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            enabled=data.enabled,
            value=data.value,
            expires_at=data.expires_at,
        )

        created_override = await storage.create_override(override)

        # Audit log
        actor_id, actor_type = _get_actor_info(connection)
        await audit_admin_action(
            audit_logger,
            action=AuditAction.CREATE,
            resource_type=ResourceType.OVERRIDE,
            resource_id=created_override.id,
            resource_key=f"{data.entity_type}/{data.entity_id}",
            actor_id=actor_id,
            actor_type=actor_type,
            ip_address=connection.client.host if connection.client else None,
            metadata={
                "flag_id": str(flag_id),
                "flag_key": flag.key,
                "entity_type": data.entity_type,
                "entity_id": data.entity_id,
                "enabled": data.enabled,
                "expires_at": data.expires_at.isoformat() if data.expires_at else None,
            },
        )

        return _override_to_response(created_override)

    @put(
        "/{entity_type:str}/{entity_id:str}",
        summary="Update an override",
        description="Update an existing entity-specific override.",
        guards=[require_permission(Permission.FLAGS_WRITE)],
    )
    async def update_override(
        self,
        flag_id: UUID,
        entity_type: str,
        entity_id: str,
        data: UpdateOverrideRequest,
        storage: MemoryStorageBackend,
        audit_logger: AuditLogger,
        connection: ASGIConnection[Any, Any, Any, Any],
    ) -> OverrideResponse:
        """Update an existing override.

        Args:
            flag_id: The UUID of the flag.
            entity_type: The type of entity.
            entity_id: The entity's identifier.
            data: The override update request.
            storage: The storage backend (injected).
            audit_logger: The audit logger (injected).
            connection: The ASGI connection for extracting actor info.

        Returns:
            The updated override response.

        Raises:
            NotFoundException: If the flag or override does not exist.
            ValidationException: If validation fails.

        """
        _validate_entity_type(entity_type)

        if data.expires_at is not None:
            _validate_expires_at(data.expires_at)

        # Verify flag exists
        flag = storage._flags_by_id.get(flag_id)
        if flag is None:
            raise NotFoundException(detail=f"Flag with id '{flag_id}' not found")

        # Get existing override
        override = await storage.get_override(flag_id, entity_type, entity_id)
        if override is None:
            raise NotFoundException(
                detail=f"Override for {entity_type}/{entity_id} on flag '{flag_id}' not found"
            )

        # Capture before state for audit
        before_state = {
            "enabled": override.enabled,
            "value": override.value,
            "expires_at": override.expires_at.isoformat() if override.expires_at else None,
        }

        # Apply updates
        if data.enabled is not None:
            override.enabled = data.enabled
        if data.value is not None:
            override.value = data.value
        if data.expires_at is not None:
            override.expires_at = data.expires_at

        override.updated_at = datetime.now(UTC)

        # Update in storage (re-insert with same key)
        storage_key = storage._override_key(flag_id, entity_type, entity_id)
        storage._overrides[storage_key] = override

        # Capture after state for audit
        after_state = {
            "enabled": override.enabled,
            "value": override.value,
            "expires_at": override.expires_at.isoformat() if override.expires_at else None,
        }

        # Audit log
        actor_id, actor_type = _get_actor_info(connection)
        changes = diff_changes(before_state, after_state)
        await audit_admin_action(
            audit_logger,
            action=AuditAction.UPDATE,
            resource_type=ResourceType.OVERRIDE,
            resource_id=override.id,
            resource_key=f"{entity_type}/{entity_id}",
            actor_id=actor_id,
            actor_type=actor_type,
            ip_address=connection.client.host if connection.client else None,
            changes=changes,
            metadata={
                "flag_id": str(flag_id),
                "flag_key": flag.key,
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
        )

        return _override_to_response(override)

    @delete(
        "/{entity_type:str}/{entity_id:str}",
        status_code=HTTP_204_NO_CONTENT,
        summary="Delete an override",
        description="Delete an entity-specific override from a flag.",
        guards=[require_permission(Permission.FLAGS_WRITE)],
    )
    async def delete_override(
        self,
        flag_id: UUID,
        entity_type: str,
        entity_id: str,
        storage: MemoryStorageBackend,
        audit_logger: AuditLogger,
        connection: ASGIConnection[Any, Any, Any, Any],
    ) -> None:
        """Delete an override.

        Args:
            flag_id: The UUID of the flag.
            entity_type: The type of entity.
            entity_id: The entity's identifier.
            storage: The storage backend (injected).
            audit_logger: The audit logger (injected).
            connection: The ASGI connection for extracting actor info.

        Raises:
            NotFoundException: If the flag or override does not exist.
            ValidationException: If the entity type is invalid.

        """
        _validate_entity_type(entity_type)

        # Verify flag exists
        flag = storage._flags_by_id.get(flag_id)
        if flag is None:
            raise NotFoundException(detail=f"Flag with id '{flag_id}' not found")

        # Get override for audit purposes
        override = await storage.get_override(flag_id, entity_type, entity_id)
        if override is None:
            raise NotFoundException(
                detail=f"Override for {entity_type}/{entity_id} on flag '{flag_id}' not found"
            )

        override_id = override.id

        # Delete the override
        deleted = await storage.delete_override(flag_id, entity_type, entity_id)
        if not deleted:
            raise NotFoundException(
                detail=f"Override for {entity_type}/{entity_id} on flag '{flag_id}' not found"
            )

        # Audit log
        actor_id, actor_type = _get_actor_info(connection)
        await audit_admin_action(
            audit_logger,
            action=AuditAction.DELETE,
            resource_type=ResourceType.OVERRIDE,
            resource_id=override_id,
            resource_key=f"{entity_type}/{entity_id}",
            actor_id=actor_id,
            actor_type=actor_type,
            ip_address=connection.client.host if connection.client else None,
            metadata={
                "flag_id": str(flag_id),
                "flag_key": flag.key,
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
        )


class EntityOverridesController(Controller):
    """Controller for entity-centric override operations.

    Provides endpoints for viewing and managing overrides from an entity's
    perspective, rather than a flag's perspective.

    Attributes:
        path: Base path for entity override endpoints.
        tags: OpenAPI tags for documentation grouping.

    """

    path = "/admin/overrides/entity"
    tags: ClassVar[list[str]] = ["Admin - Overrides"]

    @get(
        "/{entity_type:str}/{entity_id:str}",
        summary="List overrides for an entity",
        description="Retrieve all overrides for a specific entity across all flags.",
        guards=[require_permission(Permission.FLAGS_READ)],
    )
    async def get_entity_overrides(
        self,
        entity_type: str,
        entity_id: str,
        storage: MemoryStorageBackend,
        include_expired: bool = Parameter(
            default=False,
            description="Include expired overrides in the response",
        ),
        page: int = Parameter(default=1, ge=1, description="Page number"),
        page_size: int = Parameter(default=20, ge=1, le=100, description="Items per page"),
    ) -> PaginatedResponse[OverrideResponse]:
        """Get all overrides for a specific entity.

        Args:
            entity_type: The type of entity.
            entity_id: The entity's identifier.
            storage: The storage backend (injected).
            include_expired: Whether to include expired overrides.
            page: Page number for pagination.
            page_size: Number of items per page.

        Returns:
            Paginated list of override responses.

        Raises:
            ValidationException: If the entity type is invalid.

        """
        _validate_entity_type(entity_type)

        # Get all overrides for this entity
        now = datetime.now(UTC)
        overrides: list[FlagOverride] = []

        for override in storage._overrides.values():
            if override.entity_type != entity_type or override.entity_id != entity_id:
                continue

            # Apply expired filter
            is_expired = override.is_expired(now)
            if is_expired and not include_expired:
                continue

            overrides.append(override)

        # Sort by created_at descending
        overrides.sort(
            key=lambda o: o.created_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

        # Paginate
        total = len(overrides)
        start = (page - 1) * page_size
        end = start + page_size
        paginated = overrides[start:end]

        return PaginatedResponse(
            items=[_override_to_response(o) for o in paginated],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total > 0 else 1,
        )

    @delete(
        "/{entity_type:str}/{entity_id:str}",
        status_code=HTTP_204_NO_CONTENT,
        summary="Delete all overrides for an entity",
        description="Delete all overrides for a specific entity across all flags.",
        guards=[require_permission(Permission.FLAGS_WRITE)],
    )
    async def delete_entity_overrides(
        self,
        entity_type: str,
        entity_id: str,
        storage: MemoryStorageBackend,
        audit_logger: AuditLogger,
        connection: ASGIConnection[Any, Any, Any, Any],
    ) -> None:
        """Delete all overrides for an entity.

        This is a bulk operation that removes all overrides for the specified
        entity across all flags.

        Args:
            entity_type: The type of entity.
            entity_id: The entity's identifier.
            storage: The storage backend (injected).
            audit_logger: The audit logger (injected).
            connection: The ASGI connection for extracting actor info.

        Raises:
            ValidationException: If the entity type is invalid.

        """
        _validate_entity_type(entity_type)

        # Find all overrides for this entity
        keys_to_delete: list[str] = []
        override_ids: list[UUID] = []
        flag_keys: list[str] = []

        for key, override in storage._overrides.items():
            if override.entity_type == entity_type and override.entity_id == entity_id:
                keys_to_delete.append(key)
                override_ids.append(override.id)
                # Get flag key for audit
                if override.flag_id:
                    flag = storage._flags_by_id.get(override.flag_id)
                    if flag:
                        flag_keys.append(flag.key)

        # Delete all matching overrides
        for key in keys_to_delete:
            del storage._overrides[key]

        # Audit log (bulk operation)
        if keys_to_delete:
            actor_id, actor_type = _get_actor_info(connection)
            await audit_admin_action(
                audit_logger,
                action=AuditAction.DELETE,
                resource_type=ResourceType.OVERRIDE,
                resource_id=f"bulk:{entity_type}:{entity_id}",
                resource_key=f"{entity_type}/{entity_id}",
                actor_id=actor_id,
                actor_type=actor_type,
                ip_address=connection.client.host if connection.client else None,
                metadata={
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "deleted_count": len(keys_to_delete),
                    "deleted_override_ids": [str(oid) for oid in override_ids],
                    "affected_flag_keys": flag_keys,
                    "bulk_operation": True,
                },
            )
