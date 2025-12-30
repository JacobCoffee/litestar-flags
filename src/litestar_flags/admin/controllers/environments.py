"""Environments CRUD controller for the Admin API.

This module provides a Litestar controller for managing deployment environments
through the Admin API. It includes endpoints for listing, creating, updating,
and deleting environments with proper permission guards and audit logging.

Environments support hierarchical inheritance, allowing child environments to
inherit flag configurations from parent environments.

Example:
    Registering the controller with a Litestar app::

        from litestar import Litestar
        from litestar_flags.admin.controllers import EnvironmentsController

        app = Litestar(
            route_handlers=[EnvironmentsController],
        )

"""

from __future__ import annotations

import math
import re
from datetime import datetime
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
from msgspec import Struct, field

from litestar_flags.admin.audit import (
    AuditAction,
    AuditLogger,
    ResourceType,
    audit_admin_action,
    diff_changes,
)
from litestar_flags.admin.dto import (
    CreateEnvironmentRequest,
    EnvironmentResponse,
    PaginatedResponse,
    UpdateEnvironmentRequest,
)
from litestar_flags.admin.guards import Permission, require_permission
from litestar_flags.models.environment import Environment
from litestar_flags.models.environment_flag import EnvironmentFlag
from litestar_flags.protocols import StorageBackend

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection

__all__ = ["EnvironmentFlagResponse", "EnvironmentsController", "SetEnvironmentFlagRequest"]


# Regex pattern for valid slug format (lowercase alphanumeric with hyphens)
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


# =============================================================================
# Environment Flag DTOs
# =============================================================================


class EnvironmentFlagResponse(Struct, frozen=True):
    """Response DTO for an environment-specific flag configuration.

    Attributes:
        id: Unique identifier for the environment flag.
        environment_id: Reference to the environment.
        flag_id: Reference to the base flag.
        enabled: Override enabled state (None = inherit).
        percentage: Override rollout percentage (None = inherit).
        rules: Override targeting rules (None = inherit).
        variants: Override variants (None = inherit).
        inherited_from: If inheriting, the environment slug this inherits from.
        created_at: Timestamp when the config was created.
        updated_at: Timestamp when the config was last updated.

    """

    id: UUID
    environment_id: UUID
    flag_id: UUID
    enabled: bool | None
    percentage: float | None
    rules: list[dict[str, Any]] | None
    variants: list[dict[str, Any]] | None
    inherited_from: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SetEnvironmentFlagRequest(Struct, frozen=True):
    """Request DTO for setting environment-specific flag configuration.

    Attributes:
        enabled: Override enabled state (None = inherit from base flag).
        percentage: Override rollout percentage (None = inherit).
        rules: Override targeting rules as JSON (None = inherit).
        variants: Override variants as JSON (None = inherit).

    Example:
        >>> request = SetEnvironmentFlagRequest(
        ...     enabled=True,
        ...     percentage=50.0,
        ... )

    """

    enabled: bool | None = None
    percentage: float | None = None
    rules: list[dict[str, Any]] | None = None
    variants: list[dict[str, Any]] | None = None


class EnvironmentWithHierarchyResponse(Struct, frozen=True):
    """Response DTO for an environment with hierarchy information.

    Attributes:
        id: Unique identifier for the environment.
        name: Human-readable display name.
        slug: URL-safe unique identifier.
        description: Optional description.
        parent_id: Reference to parent environment.
        is_active: Whether this environment is active.
        is_production: Whether this is a production environment.
        color: Optional color for UI display.
        settings: Environment-specific settings.
        children_count: Number of child environments.
        ancestors: List of ancestor environment slugs (from root to parent).
        depth: Depth in the hierarchy (0 = root).
        created_at: Timestamp when created.
        updated_at: Timestamp when last updated.

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
    ancestors: list[str] = field(default_factory=list)
    depth: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


# =============================================================================
# Provider Functions
# =============================================================================


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


# =============================================================================
# Helper Classes and Functions
# =============================================================================


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


def _validate_slug(slug: str) -> None:
    """Validate slug format.

    Args:
        slug: The slug to validate.

    Raises:
        HTTPException: If the slug format is invalid.

    """
    if not SLUG_PATTERN.match(slug):
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid slug format: '{slug}'. "
                "Slug must be lowercase alphanumeric with hyphens only "
                "(e.g., 'production', 'staging-eu', 'dev-1')."
            ),
        )


def _environment_to_response(env: Environment) -> EnvironmentResponse:
    """Convert an Environment model to an EnvironmentResponse DTO.

    Args:
        env: The Environment model instance.

    Returns:
        An EnvironmentResponse DTO with all environment details.

    """
    # Count children
    children_count = len(env.children) if hasattr(env, "children") and env.children else 0

    # Get is_production (may not exist in dataclass version)
    is_production = getattr(env, "is_production", False)

    # Get color (may not exist in dataclass version)
    color = getattr(env, "color", None)

    return EnvironmentResponse(
        id=env.id,
        name=env.name,
        slug=env.slug,
        description=env.description,
        parent_id=env.parent_id,
        is_active=env.is_active,
        is_production=is_production,
        color=color,
        settings=env.settings or {},
        children_count=children_count,
        created_at=env.created_at,
        updated_at=env.updated_at,
    )


def _environment_to_dict(env: Environment) -> dict[str, Any]:
    """Convert an Environment to a dictionary for audit logging.

    Args:
        env: The Environment model instance.

    Returns:
        Dictionary representation of the environment.

    """
    return {
        "id": str(env.id),
        "name": env.name,
        "slug": env.slug,
        "description": env.description,
        "parent_id": str(env.parent_id) if env.parent_id else None,
        "is_active": env.is_active,
        "is_production": getattr(env, "is_production", False),
        "color": getattr(env, "color", None),
        "settings": env.settings,
    }


def _environment_flag_to_response(
    env_flag: EnvironmentFlag,
    inherited_from: str | None = None,
) -> EnvironmentFlagResponse:
    """Convert an EnvironmentFlag model to an EnvironmentFlagResponse DTO.

    Args:
        env_flag: The EnvironmentFlag model instance.
        inherited_from: Slug of environment this config inherits from, if any.

    Returns:
        An EnvironmentFlagResponse DTO.

    """
    # Handle both SQLAlchemy (dict) and dataclass (FlagRule) models
    # The type system sees a union because of conditional model definitions
    rules: list[dict[str, Any]] | None = None
    if env_flag.rules is not None:
        if isinstance(env_flag.rules, list) and len(env_flag.rules) > 0:
            first = env_flag.rules[0]
            if isinstance(first, dict):
                rules = env_flag.rules  # type: ignore[assignment]
            else:
                # Convert FlagRule objects to dicts
                rules = [
                    {
                        "id": str(getattr(r, "id", "")),
                        "attribute": getattr(r, "attribute", ""),
                        "operator": getattr(r, "operator", ""),
                    }
                    for r in env_flag.rules
                ]
        else:
            rules = []

    variants: list[dict[str, Any]] | None = None
    if env_flag.variants is not None:
        if isinstance(env_flag.variants, list) and len(env_flag.variants) > 0:
            first = env_flag.variants[0]
            if isinstance(first, dict):
                variants = env_flag.variants  # type: ignore[assignment]
            else:
                # Convert FlagVariant objects to dicts
                variants = [
                    {
                        "id": str(getattr(v, "id", "")),
                        "key": getattr(v, "key", ""),
                        "name": getattr(v, "name", ""),
                        "weight": getattr(v, "weight", 0),
                    }
                    for v in env_flag.variants
                ]
        else:
            variants = []

    return EnvironmentFlagResponse(
        id=env_flag.id,
        environment_id=env_flag.environment_id,
        flag_id=env_flag.flag_id,
        enabled=env_flag.enabled,
        percentage=env_flag.percentage,
        rules=rules,
        variants=variants,
        inherited_from=inherited_from,
        created_at=env_flag.created_at,
        updated_at=env_flag.updated_at,
    )


def _environment_flag_to_dict(env_flag: EnvironmentFlag) -> dict[str, Any]:
    """Convert an EnvironmentFlag to a dictionary for audit logging.

    Args:
        env_flag: The EnvironmentFlag model instance.

    Returns:
        Dictionary representation of the environment flag.

    """
    return {
        "id": str(env_flag.id),
        "environment_id": str(env_flag.environment_id),
        "flag_id": str(env_flag.flag_id),
        "enabled": env_flag.enabled,
        "percentage": env_flag.percentage,
        "rules": env_flag.rules,
        "variants": env_flag.variants,
    }


async def _get_environment_ancestors(
    storage: StorageBackend,
    env: Environment,
) -> list[str]:
    """Get the ancestor environment slugs from root to parent.

    Args:
        storage: The storage backend.
        env: The environment to get ancestors for.

    Returns:
        List of ancestor slugs from root to immediate parent.

    """
    ancestors: list[str] = []
    current = env

    while current.parent_id is not None:
        parent = await storage.get_environment_by_id(current.parent_id)
        if parent is None:
            break
        ancestors.insert(0, parent.slug)
        current = parent

    return ancestors


async def _check_circular_reference(
    storage: StorageBackend,
    env_id: UUID,
    new_parent_id: UUID,
) -> bool:
    """Check if setting new_parent_id would create a circular reference.

    Args:
        storage: The storage backend.
        env_id: The ID of the environment being updated.
        new_parent_id: The proposed new parent ID.

    Returns:
        True if this would create a circular reference, False otherwise.

    """
    # Walk up the parent chain from new_parent_id
    current_id = new_parent_id

    while current_id is not None:
        if current_id == env_id:
            return True

        parent_env = await storage.get_environment_by_id(current_id)
        if parent_env is None:
            break

        current_id = parent_env.parent_id

    return False


# =============================================================================
# Controller
# =============================================================================


class EnvironmentsController(Controller):
    """Controller for environment management endpoints.

    Provides CRUD operations for deployment environments with:
    - Permission-based access control
    - Audit logging of all changes
    - Hierarchical environment support with inheritance
    - Environment-specific flag configurations
    - Validation of slug format and uniqueness

    Attributes:
        path: The base path for all environment endpoints.
        tags: OpenAPI tags for documentation.
        dependencies: Dependency injection providers.

    Example:
        Using the controller endpoints::

            # List all environments with hierarchy
            GET /admin/environments/

            # Get a specific environment by ID
            GET /admin/environments/{env_id}

            # Get a specific environment by slug
            GET /admin/environments/by-slug/{slug}

            # Create a new environment
            POST /admin/environments/
            {
                "name": "Staging",
                "slug": "staging",
                "parent_id": "..."
            }

            # Update an environment
            PATCH /admin/environments/{env_id}
            {
                "is_production": true
            }

            # Delete an environment
            DELETE /admin/environments/{env_id}?force=true

            # Get child environments
            GET /admin/environments/{env_id}/children

            # Get flag configs for environment
            GET /admin/environments/{env_id}/flags

            # Set flag config for environment
            PUT /admin/environments/{env_id}/flags/{flag_id}

            # Remove flag config from environment
            DELETE /admin/environments/{env_id}/flags/{flag_id}

    """

    path: ClassVar[str] = "/admin/environments"
    tags: ClassVar[list[str]] = ["Admin - Environments"]
    dependencies: ClassVar[dict[str, Provide]] = {
        "storage": Provide(provide_storage),
        "audit_logger": Provide(provide_audit_logger),
    }

    @get(
        "/",
        guards=[require_permission(Permission.ENVIRONMENTS_READ)],
        summary="List environments with hierarchy",
        description="Retrieve a paginated list of environments with hierarchy information.",
        status_code=HTTP_200_OK,
    )
    async def list_environments(
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
        active_only: bool = Parameter(
            default=False,
            description="Filter to only active environments",
        ),
        root_only: bool = Parameter(
            default=False,
            description="Filter to only root environments (no parent)",
        ),
    ) -> PaginatedResponse[EnvironmentWithHierarchyResponse]:
        """List environments with hierarchy information.

        Args:
            storage: The storage backend for environment operations.
            page: Page number (1-indexed).
            page_size: Number of items per page.
            active_only: If True, only return active environments.
            root_only: If True, only return root environments (no parent).

        Returns:
            Paginated list of environments with hierarchy information.

        """
        # Get all environments
        all_envs = await storage.get_all_environments()

        # Apply filters
        if active_only:
            all_envs = [e for e in all_envs if e.is_active]

        if root_only:
            all_envs = [e for e in all_envs if e.parent_id is None]

        # Sort by name
        all_envs.sort(key=lambda e: e.name.lower())

        # Calculate pagination
        total = len(all_envs)
        total_pages = max(1, math.ceil(total / page_size))
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_envs = all_envs[start_idx:end_idx]

        # Build hierarchy responses
        items: list[EnvironmentWithHierarchyResponse] = []
        for env in page_envs:
            ancestors = await _get_environment_ancestors(storage, env)
            children_count = len(env.children) if hasattr(env, "children") and env.children else 0

            items.append(
                EnvironmentWithHierarchyResponse(
                    id=env.id,
                    name=env.name,
                    slug=env.slug,
                    description=env.description,
                    parent_id=env.parent_id,
                    is_active=env.is_active,
                    is_production=getattr(env, "is_production", False),
                    color=getattr(env, "color", None),
                    settings=env.settings or {},
                    children_count=children_count,
                    ancestors=ancestors,
                    depth=len(ancestors),
                    created_at=env.created_at,
                    updated_at=env.updated_at,
                )
            )

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @get(
        "/{env_id:uuid}",
        guards=[require_permission(Permission.ENVIRONMENTS_READ)],
        summary="Get environment by ID",
        description="Retrieve a single environment by its UUID.",
        status_code=HTTP_200_OK,
    )
    async def get_environment_by_id(
        self,
        storage: StorageBackend,
        env_id: UUID = Parameter(description="The environment's UUID"),
    ) -> EnvironmentResponse:
        """Get a single environment by its UUID.

        Args:
            storage: The storage backend for environment operations.
            env_id: The UUID of the environment to retrieve.

        Returns:
            The environment response DTO.

        Raises:
            NotFoundException: If the environment is not found.

        """
        env = await storage.get_environment_by_id(env_id)
        if env is None:
            raise NotFoundException(
                detail=f"Environment with ID '{env_id}' not found",
            )

        return _environment_to_response(env)

    @get(
        "/by-slug/{slug:str}",
        guards=[require_permission(Permission.ENVIRONMENTS_READ)],
        summary="Get environment by slug",
        description="Retrieve a single environment by its unique slug.",
        status_code=HTTP_200_OK,
    )
    async def get_environment_by_slug(
        self,
        storage: StorageBackend,
        slug: str = Parameter(description="The environment's unique slug"),
    ) -> EnvironmentResponse:
        """Get a single environment by its slug.

        Args:
            storage: The storage backend for environment operations.
            slug: The unique slug of the environment to retrieve.

        Returns:
            The environment response DTO.

        Raises:
            NotFoundException: If the environment is not found.

        """
        env = await storage.get_environment(slug)
        if env is None:
            raise NotFoundException(
                detail=f"Environment with slug '{slug}' not found",
            )

        return _environment_to_response(env)

    @post(
        "/",
        guards=[require_permission(Permission.ENVIRONMENTS_WRITE)],
        summary="Create a new environment",
        description="Create a new deployment environment with the specified configuration.",
        status_code=HTTP_201_CREATED,
    )
    async def create_environment(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        data: CreateEnvironmentRequest,
    ) -> EnvironmentResponse:
        """Create a new deployment environment.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for environment operations.
            audit_logger: Optional audit logger for recording the action.
            data: The environment creation request data.

        Returns:
            The created environment response DTO.

        Raises:
            HTTPException: If validation fails or environment already exists.

        """
        # Validate slug format
        _validate_slug(data.slug)

        # Check if environment with this slug already exists
        existing = await storage.get_environment(data.slug)
        if existing is not None:
            raise HTTPException(
                status_code=HTTP_409_CONFLICT,
                detail=f"Environment with slug '{data.slug}' already exists",
            )

        # Validate parent exists if provided
        if data.parent_id is not None:
            parent = await storage.get_environment_by_id(data.parent_id)
            if parent is None:
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail=f"Parent environment with ID '{data.parent_id}' not found",
                )

        # Create the environment model
        env = Environment(
            name=data.name,
            slug=data.slug,
            description=data.description,
            parent_id=data.parent_id,
            settings=dict(data.settings),
            is_active=True,
        )

        # Set optional attributes if they exist
        if hasattr(env, "is_production"):
            env.is_production = data.is_production  # type: ignore[misc]
        if hasattr(env, "color"):
            env.color = data.color  # type: ignore[misc]

        # Persist the environment
        created_env = await storage.create_environment(env)

        # Audit log the creation
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            await audit_admin_action(
                audit_logger,
                action=AuditAction.CREATE,
                resource_type=ResourceType.ENVIRONMENT,
                resource_id=created_env.id,
                resource_key=created_env.slug,
                changes={"after": _environment_to_dict(created_env)},
                actor_id=actor_info.actor_id,
                actor_type=actor_info.actor_type,
                ip_address=actor_info.ip_address,
                user_agent=actor_info.user_agent,
            )

        return _environment_to_response(created_env)

    @put(
        "/{env_id:uuid}",
        guards=[require_permission(Permission.ENVIRONMENTS_WRITE)],
        summary="Full update of an environment",
        description="Replace all environment fields with the provided values.",
        status_code=HTTP_200_OK,
    )
    async def update_environment_full(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        data: UpdateEnvironmentRequest,
        env_id: UUID = Parameter(description="The environment's UUID"),
    ) -> EnvironmentResponse:
        """Perform a full update of an environment.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for environment operations.
            audit_logger: Optional audit logger for recording the action.
            data: The environment update request data.
            env_id: The UUID of the environment to update.

        Returns:
            The updated environment response DTO.

        Raises:
            NotFoundException: If the environment is not found.
            HTTPException: If validation fails.

        """
        # Find the existing environment
        env = await storage.get_environment_by_id(env_id)
        if env is None:
            raise NotFoundException(
                detail=f"Environment with ID '{env_id}' not found",
            )

        # Validate and apply updates
        await self._validate_and_apply_update(storage, env, data, full_update=True)

        # Store before state for audit
        before_state = _environment_to_dict(env)

        # Persist the update
        updated_env = await storage.update_environment(env)

        # Audit log the update
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            changes = diff_changes(
                before_state,
                _environment_to_dict(updated_env),
                excluded_keys=["id"],
            )
            await audit_admin_action(
                audit_logger,
                action=AuditAction.UPDATE,
                resource_type=ResourceType.ENVIRONMENT,
                resource_id=updated_env.id,
                resource_key=updated_env.slug,
                changes=changes,
                actor_id=actor_info.actor_id,
                actor_type=actor_info.actor_type,
                ip_address=actor_info.ip_address,
                user_agent=actor_info.user_agent,
            )

        return _environment_to_response(updated_env)

    @patch(
        "/{env_id:uuid}",
        guards=[require_permission(Permission.ENVIRONMENTS_WRITE)],
        summary="Partial update of an environment",
        description="Update only the specified environment fields.",
        status_code=HTTP_200_OK,
    )
    async def update_environment_partial(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        data: UpdateEnvironmentRequest,
        env_id: UUID = Parameter(description="The environment's UUID"),
    ) -> EnvironmentResponse:
        """Perform a partial update of an environment.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for environment operations.
            audit_logger: Optional audit logger for recording the action.
            data: The environment update request data (only provided fields are updated).
            env_id: The UUID of the environment to update.

        Returns:
            The updated environment response DTO.

        Raises:
            NotFoundException: If the environment is not found.
            HTTPException: If validation fails.

        """
        # Find the existing environment
        env = await storage.get_environment_by_id(env_id)
        if env is None:
            raise NotFoundException(
                detail=f"Environment with ID '{env_id}' not found",
            )

        # Store before state for audit
        before_state = _environment_to_dict(env)

        # Validate and apply updates
        await self._validate_and_apply_update(storage, env, data, full_update=False)

        # Persist the update
        updated_env = await storage.update_environment(env)

        # Audit log the update
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            changes = diff_changes(
                before_state,
                _environment_to_dict(updated_env),
                excluded_keys=["id"],
            )
            await audit_admin_action(
                audit_logger,
                action=AuditAction.UPDATE,
                resource_type=ResourceType.ENVIRONMENT,
                resource_id=updated_env.id,
                resource_key=updated_env.slug,
                changes=changes,
                actor_id=actor_info.actor_id,
                actor_type=actor_info.actor_type,
                ip_address=actor_info.ip_address,
                user_agent=actor_info.user_agent,
            )

        return _environment_to_response(updated_env)

    @delete(
        "/{env_id:uuid}",
        guards=[require_permission(Permission.ENVIRONMENTS_WRITE)],
        summary="Delete an environment",
        description="Delete a deployment environment. Production environments require force flag.",
        status_code=HTTP_204_NO_CONTENT,
    )
    async def delete_environment(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        env_id: UUID = Parameter(description="The environment's UUID"),
        force: bool = Parameter(
            default=False,
            description="Force deletion of production environments",
        ),
    ) -> None:
        """Delete a deployment environment.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for environment operations.
            audit_logger: Optional audit logger for recording the action.
            env_id: The UUID of the environment to delete.
            force: If True, allow deletion of production environments.

        Raises:
            NotFoundException: If the environment is not found.
            HTTPException: If trying to delete production without force.

        """
        # Find the existing environment
        env = await storage.get_environment_by_id(env_id)
        if env is None:
            raise NotFoundException(
                detail=f"Environment with ID '{env_id}' not found",
            )

        # Check if production environment
        is_production = getattr(env, "is_production", False)
        if is_production and not force:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot delete production environment '{env.slug}' without force flag. "
                    "Set force=true to confirm deletion."
                ),
            )

        # Check for child environments
        children = await storage.get_child_environments(env_id)
        if children:
            child_slugs = [c.slug for c in children]
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot delete environment '{env.slug}' with child environments. "
                    f"Delete children first: {', '.join(child_slugs)}"
                ),
            )

        # Store before state for audit
        before_state = _environment_to_dict(env)

        # Delete the environment
        deleted = await storage.delete_environment(env.slug)
        if not deleted:
            raise NotFoundException(
                detail=f"Environment with ID '{env_id}' not found",
            )

        # Audit log the deletion
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            await audit_admin_action(
                audit_logger,
                action=AuditAction.DELETE,
                resource_type=ResourceType.ENVIRONMENT,
                resource_id=env_id,
                resource_key=env.slug,
                changes={"before": before_state},
                metadata={"force": force, "was_production": is_production},
                actor_id=actor_info.actor_id,
                actor_type=actor_info.actor_type,
                ip_address=actor_info.ip_address,
                user_agent=actor_info.user_agent,
            )

    @get(
        "/{env_id:uuid}/children",
        guards=[require_permission(Permission.ENVIRONMENTS_READ)],
        summary="Get child environments",
        description="Retrieve all direct child environments of the specified environment.",
        status_code=HTTP_200_OK,
    )
    async def get_child_environments(
        self,
        storage: StorageBackend,
        env_id: UUID = Parameter(description="The parent environment's UUID"),
    ) -> list[EnvironmentResponse]:
        """Get all direct child environments.

        Args:
            storage: The storage backend for environment operations.
            env_id: The UUID of the parent environment.

        Returns:
            List of child environment response DTOs.

        Raises:
            NotFoundException: If the parent environment is not found.

        """
        # Verify parent exists
        parent = await storage.get_environment_by_id(env_id)
        if parent is None:
            raise NotFoundException(
                detail=f"Environment with ID '{env_id}' not found",
            )

        # Get children
        children = await storage.get_child_environments(env_id)

        # Sort by name and convert to responses
        children.sort(key=lambda e: e.name.lower())
        return [_environment_to_response(c) for c in children]

    @get(
        "/{env_id:uuid}/flags",
        guards=[require_permission(Permission.ENVIRONMENTS_READ)],
        summary="Get flag configs for environment",
        description="Retrieve all flag configurations for an environment, including inherited settings.",
        status_code=HTTP_200_OK,
    )
    async def get_environment_flags(
        self,
        storage: StorageBackend,
        env_id: UUID = Parameter(description="The environment's UUID"),
        include_inherited: bool = Parameter(
            default=True,
            description="Include inherited flag configurations from parent environments",
        ),
    ) -> list[EnvironmentFlagResponse]:
        """Get all flag configurations for an environment.

        Args:
            storage: The storage backend for environment operations.
            env_id: The UUID of the environment.
            include_inherited: If True, include inherited configs from parent environments.

        Returns:
            List of environment flag response DTOs.

        Raises:
            NotFoundException: If the environment is not found.

        """
        # Verify environment exists
        env = await storage.get_environment_by_id(env_id)
        if env is None:
            raise NotFoundException(
                detail=f"Environment with ID '{env_id}' not found",
            )

        # Get direct flag configs
        direct_flags = await storage.get_environment_flags(env_id)
        direct_flag_ids = {f.flag_id for f in direct_flags}

        # Build response
        responses: list[EnvironmentFlagResponse] = []

        # Add direct configs
        for ef in direct_flags:
            responses.append(_environment_flag_to_response(ef))

        # Add inherited configs if requested
        if include_inherited:
            current = env
            while current.parent_id is not None:
                parent = await storage.get_environment_by_id(current.parent_id)
                if parent is None:
                    break

                parent_flags = await storage.get_environment_flags(parent.id)
                for pf in parent_flags:
                    if pf.flag_id not in direct_flag_ids:
                        responses.append(_environment_flag_to_response(pf, inherited_from=parent.slug))
                        direct_flag_ids.add(pf.flag_id)

                current = parent

        return responses

    @put(
        "/{env_id:uuid}/flags/{flag_id:uuid}",
        guards=[require_permission(Permission.ENVIRONMENTS_WRITE)],
        summary="Set flag config for environment",
        description="Set or update environment-specific flag configuration.",
        status_code=HTTP_200_OK,
    )
    async def set_environment_flag(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        data: SetEnvironmentFlagRequest,
        env_id: UUID = Parameter(description="The environment's UUID"),
        flag_id: UUID = Parameter(description="The flag's UUID"),
    ) -> EnvironmentFlagResponse:
        """Set or update environment-specific flag configuration.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for operations.
            audit_logger: Optional audit logger for recording the action.
            data: The flag configuration data.
            env_id: The UUID of the environment.
            flag_id: The UUID of the flag.

        Returns:
            The environment flag response DTO.

        Raises:
            NotFoundException: If the environment or flag is not found.

        """
        # Verify environment exists
        env = await storage.get_environment_by_id(env_id)
        if env is None:
            raise NotFoundException(
                detail=f"Environment with ID '{env_id}' not found",
            )

        # Verify flag exists
        if hasattr(storage, "get_flag_by_id"):
            flag = await storage.get_flag_by_id(flag_id)  # type: ignore[attr-defined]
        elif hasattr(storage, "_flags_by_id"):
            flag = storage._flags_by_id.get(flag_id)  # type: ignore[attr-defined]
        else:
            # Fall back to searching
            flag = None
            all_flags = await storage.get_all_active_flags()
            for f in all_flags:
                if f.id == flag_id:
                    flag = f
                    break

        if flag is None:
            raise NotFoundException(
                detail=f"Flag with ID '{flag_id}' not found",
            )

        # Check if environment flag already exists
        existing = await storage.get_environment_flag(env_id, flag_id)
        is_update = existing is not None

        # Store before state for audit
        before_state = _environment_flag_to_dict(existing) if existing else None

        if existing is not None:
            # Update existing
            existing.enabled = data.enabled  # type: ignore[misc]
            existing.percentage = data.percentage  # type: ignore[misc]
            existing.rules = data.rules  # type: ignore[misc]
            existing.variants = data.variants  # type: ignore[misc]
            env_flag = await storage.update_environment_flag(existing)
        else:
            # Create new
            env_flag = EnvironmentFlag(
                environment_id=env_id,
                flag_id=flag_id,
                enabled=data.enabled,
                percentage=data.percentage,
                rules=data.rules,
                variants=data.variants,
            )
            env_flag = await storage.create_environment_flag(env_flag)

        # Audit log
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            if is_update:
                changes = diff_changes(
                    before_state,
                    _environment_flag_to_dict(env_flag),
                    excluded_keys=["id", "environment_id", "flag_id"],
                )
                await audit_admin_action(
                    audit_logger,
                    action=AuditAction.UPDATE,
                    resource_type=ResourceType.ENVIRONMENT_FLAG,
                    resource_id=env_flag.id,
                    resource_key=f"{env.slug}:{flag.key}",
                    changes=changes,
                    actor_id=actor_info.actor_id,
                    actor_type=actor_info.actor_type,
                    ip_address=actor_info.ip_address,
                    user_agent=actor_info.user_agent,
                )
            else:
                await audit_admin_action(
                    audit_logger,
                    action=AuditAction.CREATE,
                    resource_type=ResourceType.ENVIRONMENT_FLAG,
                    resource_id=env_flag.id,
                    resource_key=f"{env.slug}:{flag.key}",
                    changes={"after": _environment_flag_to_dict(env_flag)},
                    actor_id=actor_info.actor_id,
                    actor_type=actor_info.actor_type,
                    ip_address=actor_info.ip_address,
                    user_agent=actor_info.user_agent,
                )

        return _environment_flag_to_response(env_flag)

    @delete(
        "/{env_id:uuid}/flags/{flag_id:uuid}",
        guards=[require_permission(Permission.ENVIRONMENTS_WRITE)],
        summary="Remove flag config from environment",
        description="Remove environment-specific flag configuration (reverts to inherited or base).",
        status_code=HTTP_204_NO_CONTENT,
    )
    async def remove_environment_flag(
        self,
        request: ASGIConnection[Any, Any, Any, Any],
        storage: StorageBackend,
        audit_logger: AuditLogger | None,
        env_id: UUID = Parameter(description="The environment's UUID"),
        flag_id: UUID = Parameter(description="The flag's UUID"),
    ) -> None:
        """Remove environment-specific flag configuration.

        Args:
            request: The ASGI connection for actor information.
            storage: The storage backend for operations.
            audit_logger: Optional audit logger for recording the action.
            env_id: The UUID of the environment.
            flag_id: The UUID of the flag.

        Raises:
            NotFoundException: If the environment flag config is not found.

        """
        # Verify environment exists
        env = await storage.get_environment_by_id(env_id)
        if env is None:
            raise NotFoundException(
                detail=f"Environment with ID '{env_id}' not found",
            )

        # Get existing config
        existing = await storage.get_environment_flag(env_id, flag_id)
        if existing is None:
            raise NotFoundException(
                detail=f"Flag config for flag '{flag_id}' in environment '{env_id}' not found",
            )

        # Store before state for audit
        before_state = _environment_flag_to_dict(existing)

        # Delete the config
        deleted = await storage.delete_environment_flag(env_id, flag_id)
        if not deleted:
            raise NotFoundException(
                detail=f"Flag config for flag '{flag_id}' in environment '{env_id}' not found",
            )

        # Audit log
        if audit_logger is not None:
            actor_info = _get_actor_info(request)
            await audit_admin_action(
                audit_logger,
                action=AuditAction.DELETE,
                resource_type=ResourceType.ENVIRONMENT_FLAG,
                resource_id=existing.id,
                resource_key=f"{env.slug}:{flag_id}",
                changes={"before": before_state},
                actor_id=actor_info.actor_id,
                actor_type=actor_info.actor_type,
                ip_address=actor_info.ip_address,
                user_agent=actor_info.user_agent,
            )

    async def _validate_and_apply_update(
        self,
        storage: StorageBackend,
        env: Environment,
        data: UpdateEnvironmentRequest,
        *,
        full_update: bool,
    ) -> None:
        """Validate and apply update data to an environment.

        Args:
            storage: The storage backend for validation queries.
            env: The environment to update.
            data: The update request data.
            full_update: If True, set None values; if False, skip None values.

        Raises:
            HTTPException: If validation fails.

        """
        # Validate slug if changing
        if data.slug is not None and data.slug != env.slug:
            _validate_slug(data.slug)

            # Check uniqueness
            existing = await storage.get_environment(data.slug)
            if existing is not None:
                raise HTTPException(
                    status_code=HTTP_409_CONFLICT,
                    detail=f"Environment with slug '{data.slug}' already exists",
                )

            env.slug = data.slug  # type: ignore[misc]

        # Validate parent if changing
        if data.parent_id is not None and data.parent_id != env.parent_id:
            # Validate parent exists
            parent = await storage.get_environment_by_id(data.parent_id)
            if parent is None:
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail=f"Parent environment with ID '{data.parent_id}' not found",
                )

            # Check for circular reference
            if await _check_circular_reference(storage, env.id, data.parent_id):
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail=(f"Setting parent to '{parent.slug}' would create a circular reference"),
                )

            env.parent_id = data.parent_id  # type: ignore[misc]
        elif full_update and data.parent_id is None:
            env.parent_id = None  # type: ignore[misc]

        # Apply other updates
        if data.name is not None:
            env.name = data.name  # type: ignore[misc]

        if data.description is not None:
            env.description = data.description  # type: ignore[misc]
        elif full_update:
            env.description = None  # type: ignore[misc]

        if data.is_active is not None:
            env.is_active = data.is_active  # type: ignore[misc]

        if data.is_production is not None and hasattr(env, "is_production"):
            env.is_production = data.is_production  # type: ignore[misc]

        if data.color is not None and hasattr(env, "color"):
            env.color = data.color  # type: ignore[misc]
        elif full_update and hasattr(env, "color"):
            env.color = None  # type: ignore[misc]

        if data.settings is not None:
            env.settings = dict(data.settings)  # type: ignore[misc]
