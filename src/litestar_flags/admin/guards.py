"""Role-based access control (RBAC) guards for the Admin API.

This module provides permission and role-based guards for securing
Admin API endpoints. It supports flexible authentication systems
through the HasPermissions protocol.

Example:
    Using guards with route handlers::

        from litestar import get
        from litestar_flags.admin.guards import require_permission, Permission

        @get("/flags", guards=[require_permission(Permission.FLAGS_READ)])
        async def list_flags() -> list[dict]:
            ...

        @get("/admin/settings", guards=[require_role(Role.ADMIN)])
        async def admin_settings() -> dict:
            ...
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from litestar.exceptions import PermissionDeniedException

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection
    from litestar.handlers.base import BaseRouteHandler

__all__ = [
    "HasPermissions",
    "Permission",
    "PermissionGuard",
    "Role",
    "ROLE_PERMISSIONS",
    "get_current_user_permissions",
    "require_permission",
    "require_role",
]


class Permission(StrEnum):
    """Permissions for Admin API access control.

    Permissions follow a resource:action naming convention where:
    - The resource is the type of object (flags, rules, segments, etc.)
    - The action is what can be done (read, write, delete)

    The special `admin:*` permission grants superadmin access to all resources.
    """

    # Flag permissions
    FLAGS_READ = "flags:read"
    FLAGS_WRITE = "flags:write"
    FLAGS_DELETE = "flags:delete"

    # Rule permissions
    RULES_READ = "rules:read"
    RULES_WRITE = "rules:write"

    # Segment permissions
    SEGMENTS_READ = "segments:read"
    SEGMENTS_WRITE = "segments:write"

    # Environment permissions
    ENVIRONMENTS_READ = "environments:read"
    ENVIRONMENTS_WRITE = "environments:write"

    # Analytics permissions
    ANALYTICS_READ = "analytics:read"

    # Superadmin - grants all permissions
    ADMIN_ALL = "admin:*"


class Role(StrEnum):
    """Predefined roles for Admin API access control.

    Roles are a convenient way to group permissions. Each role
    has a predefined set of permissions associated with it.

    Roles:
        VIEWER: Read-only access to flags, rules, segments, and environments.
        EDITOR: Viewer permissions plus write access (no delete).
        ADMIN: Full access to all resources except superadmin actions.
        SUPERADMIN: Unrestricted access to all resources and actions.
    """

    VIEWER = "viewer"
    EDITOR = "editor"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


# Role to permission mappings
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({
        Permission.FLAGS_READ,
        Permission.RULES_READ,
        Permission.SEGMENTS_READ,
        Permission.ENVIRONMENTS_READ,
        Permission.ANALYTICS_READ,
    }),
    Role.EDITOR: frozenset({
        Permission.FLAGS_READ,
        Permission.FLAGS_WRITE,
        Permission.RULES_READ,
        Permission.RULES_WRITE,
        Permission.SEGMENTS_READ,
        Permission.SEGMENTS_WRITE,
        Permission.ENVIRONMENTS_READ,
        Permission.ENVIRONMENTS_WRITE,
        Permission.ANALYTICS_READ,
    }),
    Role.ADMIN: frozenset({
        Permission.FLAGS_READ,
        Permission.FLAGS_WRITE,
        Permission.FLAGS_DELETE,
        Permission.RULES_READ,
        Permission.RULES_WRITE,
        Permission.SEGMENTS_READ,
        Permission.SEGMENTS_WRITE,
        Permission.ENVIRONMENTS_READ,
        Permission.ENVIRONMENTS_WRITE,
        Permission.ANALYTICS_READ,
    }),
    Role.SUPERADMIN: frozenset({
        Permission.FLAGS_READ,
        Permission.FLAGS_WRITE,
        Permission.FLAGS_DELETE,
        Permission.RULES_READ,
        Permission.RULES_WRITE,
        Permission.SEGMENTS_READ,
        Permission.SEGMENTS_WRITE,
        Permission.ENVIRONMENTS_READ,
        Permission.ENVIRONMENTS_WRITE,
        Permission.ANALYTICS_READ,
        Permission.ADMIN_ALL,
    }),
}


@runtime_checkable
class HasPermissions(Protocol):
    """Protocol for user objects that have permissions.

    Any user object used with the permission guards must implement
    this protocol. The object should provide:

    - id: A unique identifier for the user
    - roles: A sequence of Role values assigned to the user
    - permissions: Optional explicit permissions beyond role-based permissions

    Example:
        Implementing a user class::

            @dataclass
            class AdminUser:
                id: str
                roles: list[Role]
                permissions: list[Permission] | None = None

    Note:
        The permissions field is optional and allows for granting
        specific permissions that are not part of a user's roles.
    """

    @property
    def id(self) -> str:
        """The unique identifier for the user."""
        ...

    @property
    def roles(self) -> Sequence[Role]:
        """The roles assigned to the user."""
        ...

    @property
    def permissions(self) -> Sequence[Permission] | None:
        """Explicit permissions granted to the user beyond their roles.

        Returns None if no explicit permissions are set.
        """
        ...


def get_permissions_for_roles(roles: Sequence[Role]) -> set[Permission]:
    """Get all permissions granted by a set of roles.

    Args:
        roles: Sequence of roles to get permissions for.

    Returns:
        Set of all permissions granted by the given roles.

    Example:
        >>> get_permissions_for_roles([Role.VIEWER])
        {Permission.FLAGS_READ, Permission.RULES_READ, ...}
    """
    permissions: set[Permission] = set()
    for role in roles:
        role_perms = ROLE_PERMISSIONS.get(role)
        if role_perms:
            permissions.update(role_perms)
    return permissions


def get_current_user_permissions(
    connection: ASGIConnection[Any, Any, Any, Any],
) -> set[Permission]:
    """Extract current user permissions from the connection state.

    This function looks for user information in the connection state
    and extracts permissions from the user object. It supports:

    1. A user object implementing HasPermissions protocol
    2. A dict with 'roles' and optional 'permissions' keys
    3. Direct permissions list in state.permissions

    Args:
        connection: The ASGI connection object.

    Returns:
        Set of Permission values the current user has.

    Raises:
        PermissionDeniedException: If no user is found in the connection state.

    Example:
        Using in a route handler::

            @get("/current-permissions")
            async def get_my_permissions(
                request: Request,
            ) -> list[str]:
                perms = get_current_user_permissions(request)
                return [p.value for p in perms]
    """
    # Try to get user from state
    user = getattr(connection.state, "user", None)
    if user is None:
        user = connection.scope.get("user")

    if user is None:
        raise PermissionDeniedException(
            detail="Authentication required",
        )

    permissions: set[Permission] = set()

    # Check if user implements HasPermissions protocol
    if isinstance(user, HasPermissions):
        permissions = get_permissions_for_roles(user.roles)
        if user.permissions:
            permissions.update(user.permissions)
        return permissions

    # Handle dict-like user objects
    if isinstance(user, dict):
        roles = user.get("roles", [])
        if roles:
            role_objects = [Role(r) if isinstance(r, str) else r for r in roles]
            permissions = get_permissions_for_roles(role_objects)

        explicit_perms = user.get("permissions", [])
        if explicit_perms:
            for p in explicit_perms:
                permissions.add(Permission(p) if isinstance(p, str) else p)

        return permissions

    # Try accessing as attributes
    if hasattr(user, "roles"):
        roles = getattr(user, "roles", [])
        role_objects = [Role(r) if isinstance(r, str) else r for r in roles]
        permissions = get_permissions_for_roles(role_objects)

    if hasattr(user, "permissions"):
        explicit_perms = getattr(user, "permissions", None)
        if explicit_perms:
            for p in explicit_perms:
                permissions.add(Permission(p) if isinstance(p, str) else p)

    # Check for direct permissions in state
    if not permissions:
        state_perms = getattr(connection.state, "permissions", None)
        if state_perms:
            for p in state_perms:
                permissions.add(Permission(p) if isinstance(p, str) else p)

    return permissions


def has_permission(
    user_permissions: set[Permission],
    required_permissions: Sequence[Permission],
    require_all: bool = True,
) -> bool:
    """Check if user has required permissions.

    Args:
        user_permissions: Set of permissions the user has.
        required_permissions: Sequence of permissions to check for.
        require_all: If True, user must have ALL required permissions.
            If False, user must have AT LEAST ONE required permission.

    Returns:
        True if user has the required permissions, False otherwise.

    Example:
        >>> user_perms = {Permission.FLAGS_READ, Permission.FLAGS_WRITE}
        >>> has_permission(user_perms, [Permission.FLAGS_READ])
        True
        >>> has_permission(user_perms, [Permission.FLAGS_DELETE])
        False
    """
    # Superadmin bypasses all permission checks
    if Permission.ADMIN_ALL in user_permissions:
        return True

    if not required_permissions:
        return True

    required_set = set(required_permissions)

    if require_all:
        return required_set.issubset(user_permissions)
    else:
        return bool(required_set.intersection(user_permissions))


def has_role(
    user_roles: Sequence[Role],
    required_roles: Sequence[Role],
    require_all: bool = False,
) -> bool:
    """Check if user has required roles.

    Args:
        user_roles: Sequence of roles the user has.
        required_roles: Sequence of roles to check for.
        require_all: If True, user must have ALL required roles.
            If False (default), user must have AT LEAST ONE required role.

    Returns:
        True if user has the required roles, False otherwise.

    Example:
        >>> has_role([Role.EDITOR], [Role.VIEWER, Role.EDITOR])
        True
        >>> has_role([Role.VIEWER], [Role.ADMIN])
        False
    """
    if not required_roles:
        return True

    # Superadmin has all roles implicitly
    if Role.SUPERADMIN in user_roles:
        return True

    user_role_set = set(user_roles)
    required_role_set = set(required_roles)

    if require_all:
        return required_role_set.issubset(user_role_set)
    else:
        return bool(required_role_set.intersection(user_role_set))


class PermissionGuard:
    """Guard that checks for required permissions.

    This guard can be used to protect route handlers by requiring
    specific permissions. It checks the connection state for user
    permissions and raises PermissionDeniedException if the user
    lacks the required permissions.

    Args:
        permissions: Permission(s) required to access the route.
        require_all: If True (default), all permissions are required.
            If False, only one of the permissions is required.

    Example:
        Using as a guard::

            from litestar import get
            from litestar_flags.admin.guards import PermissionGuard, Permission

            @get(
                "/flags",
                guards=[PermissionGuard(Permission.FLAGS_READ)],
            )
            async def list_flags() -> list[dict]:
                ...

            # Require multiple permissions
            @post(
                "/flags",
                guards=[PermissionGuard(
                    Permission.FLAGS_READ,
                    Permission.FLAGS_WRITE,
                )],
            )
            async def create_flag(data: FlagCreate) -> dict:
                ...
    """

    __slots__ = ("permissions", "require_all")

    def __init__(
        self,
        *permissions: Permission,
        require_all: bool = True,
    ) -> None:
        """Initialize the permission guard.

        Args:
            *permissions: One or more permissions to require.
            require_all: If True, all permissions are required.
        """
        self.permissions = permissions
        self.require_all = require_all

    async def __call__(
        self,
        connection: ASGIConnection[Any, Any, Any, Any],
        _: BaseRouteHandler,
    ) -> None:
        """Check if the user has required permissions.

        Args:
            connection: The ASGI connection object.
            _: The route handler (unused).

        Raises:
            PermissionDeniedException: If the user lacks required permissions.
        """
        try:
            user_permissions = get_current_user_permissions(connection)
        except PermissionDeniedException:
            raise

        if not has_permission(
            user_permissions,
            self.permissions,
            require_all=self.require_all,
        ):
            missing = set(self.permissions) - user_permissions
            raise PermissionDeniedException(
                detail=f"Missing required permissions: {', '.join(p.value for p in missing)}",
            )


class RoleGuard:
    """Guard that checks for required roles.

    This guard can be used to protect route handlers by requiring
    specific roles. It checks the connection state for user roles
    and raises PermissionDeniedException if the user lacks the
    required roles.

    Args:
        roles: Role(s) required to access the route.
        require_all: If True, all roles are required.
            If False (default), only one of the roles is required.

    Example:
        Using as a guard::

            from litestar import get
            from litestar_flags.admin.guards import RoleGuard, Role

            @get(
                "/admin/settings",
                guards=[RoleGuard(Role.ADMIN)],
            )
            async def admin_settings() -> dict:
                ...

            # Allow multiple roles
            @get(
                "/reports",
                guards=[RoleGuard(Role.EDITOR, Role.ADMIN)],
            )
            async def get_reports() -> list[dict]:
                ...
    """

    __slots__ = ("roles", "require_all")

    def __init__(
        self,
        *roles: Role,
        require_all: bool = False,
    ) -> None:
        """Initialize the role guard.

        Args:
            *roles: One or more roles to require.
            require_all: If True, all roles are required.
        """
        self.roles = roles
        self.require_all = require_all

    async def __call__(
        self,
        connection: ASGIConnection[Any, Any, Any, Any],
        _: BaseRouteHandler,
    ) -> None:
        """Check if the user has required roles.

        Args:
            connection: The ASGI connection object.
            _: The route handler (unused).

        Raises:
            PermissionDeniedException: If the user lacks required roles.
        """
        user = getattr(connection.state, "user", None)
        if user is None:
            user = connection.scope.get("user")

        if user is None:
            raise PermissionDeniedException(
                detail="Authentication required",
            )

        # Get roles from user
        user_roles: list[Role] = []

        if isinstance(user, HasPermissions):
            user_roles = list(user.roles)
        elif isinstance(user, dict):
            roles = user.get("roles", [])
            user_roles = [Role(r) if isinstance(r, str) else r for r in roles]
        elif hasattr(user, "roles"):
            roles = getattr(user, "roles", [])
            user_roles = [Role(r) if isinstance(r, str) else r for r in roles]

        if not has_role(user_roles, self.roles, require_all=self.require_all):
            raise PermissionDeniedException(
                detail=f"Required roles: {', '.join(r.value for r in self.roles)}",
            )


def require_permission(
    *permissions: Permission,
    require_all: bool = True,
) -> PermissionGuard:
    """Factory function to create a PermissionGuard.

    This is a convenience function for creating PermissionGuard instances
    that can be used directly in the guards parameter of route handlers.

    Args:
        *permissions: One or more permissions to require.
        require_all: If True (default), all permissions are required.
            If False, only one of the permissions is required.

    Returns:
        A PermissionGuard instance configured with the specified permissions.

    Example:
        Using as a decorator factory::

            from litestar import get
            from litestar_flags.admin.guards import require_permission, Permission

            @get(
                "/flags",
                guards=[require_permission(Permission.FLAGS_READ)],
            )
            async def list_flags() -> list[dict]:
                ...

            # Require any of multiple permissions
            @get(
                "/data",
                guards=[require_permission(
                    Permission.FLAGS_READ,
                    Permission.ANALYTICS_READ,
                    require_all=False,
                )],
            )
            async def get_data() -> dict:
                ...
    """
    return PermissionGuard(*permissions, require_all=require_all)


def require_role(
    *roles: Role,
    require_all: bool = False,
) -> RoleGuard:
    """Factory function to create a RoleGuard.

    This is a convenience function for creating RoleGuard instances
    that can be used directly in the guards parameter of route handlers.

    Args:
        *roles: One or more roles to require.
        require_all: If True, all roles are required.
            If False (default), only one of the roles is required.

    Returns:
        A RoleGuard instance configured with the specified roles.

    Example:
        Using as a decorator factory::

            from litestar import get
            from litestar_flags.admin.guards import require_role, Role

            @get(
                "/admin",
                guards=[require_role(Role.ADMIN)],
            )
            async def admin_only() -> dict:
                ...

            # Allow editors or admins
            @get(
                "/dashboard",
                guards=[require_role(Role.EDITOR, Role.ADMIN)],
            )
            async def dashboard() -> dict:
                ...
    """
    return RoleGuard(*roles, require_all=require_all)


def require_superadmin() -> RoleGuard:
    """Factory function to create a guard requiring superadmin role.

    This is a convenience function for the common case of requiring
    superadmin access to a route.

    Returns:
        A RoleGuard instance configured to require the SUPERADMIN role.

    Example:
        Using as a guard::

            from litestar import delete
            from litestar_flags.admin.guards import require_superadmin

            @delete(
                "/system/reset",
                guards=[require_superadmin()],
            )
            async def reset_system() -> dict:
                ...
    """
    return RoleGuard(Role.SUPERADMIN)
