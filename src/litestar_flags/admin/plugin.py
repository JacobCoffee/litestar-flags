"""Admin API plugin for Litestar feature flags.

This module provides the AdminPlugin for easy registration of all admin
controllers with a Litestar application. It supports configurable controller
inclusion, path prefixes, authentication guards, and audit logging.

Example:
    Basic usage with defaults::

        from litestar import Litestar
        from litestar_flags import FeatureFlagsPlugin
        from litestar_flags.admin import AdminPlugin

        app = Litestar(
            plugins=[FeatureFlagsPlugin(), AdminPlugin()],
        )

    Custom configuration::

        from litestar_flags.admin import AdminConfig, AdminPlugin
        from litestar_flags.admin.audit import InMemoryAuditLogger

        config = AdminConfig(
            path_prefix="/api/v1/admin",
            require_auth=True,
            audit_logger=InMemoryAuditLogger(),
            enable_analytics=False,
        )
        app = Litestar(
            plugins=[FeatureFlagsPlugin(), AdminPlugin(config=config)],
        )

"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from litestar.plugins import InitPlugin
from litestar.router import Router

from litestar_flags.admin.controllers.analytics import AnalyticsController
from litestar_flags.admin.controllers.environments import EnvironmentsController
from litestar_flags.admin.controllers.flags import FlagsController
from litestar_flags.admin.controllers.overrides import EntityOverridesController, OverridesController
from litestar_flags.admin.controllers.rules import RulesController
from litestar_flags.admin.controllers.segments import SegmentsController

if TYPE_CHECKING:
    from litestar import Litestar
    from litestar.config.app import AppConfig
    from litestar.connection import ASGIConnection
    from litestar.handlers.base import BaseRouteHandler

    from litestar_flags.admin.audit import AuditLogger

__all__ = ["AdminConfig", "AdminPlugin"]

logger = logging.getLogger(__name__)


# Type alias for guard callables
GuardCallable = Callable[
    ["ASGIConnection[Any, Any, Any, Any]", "BaseRouteHandler"],
    Any,
]


@dataclass
class AdminConfig:
    """Configuration for the Admin API plugin.

    Attributes:
        enabled: Whether the admin API is enabled. Defaults to True.
        path_prefix: Base path prefix for all admin routes. Defaults to "/admin".
            Note: Controllers already have "/admin" in their paths, so this
            will be prepended (e.g., "/api/v1" + "/admin/flags" = "/api/v1/admin/flags").
        require_auth: Whether to require authentication for admin endpoints.
            Defaults to True. When True, requests without a user in the connection
            state will be rejected by the permission guards.
        audit_logger: Optional audit logger for recording admin actions.
            If provided, it will be stored in app.state.feature_flags_audit_logger.
        auth_guard: Optional custom authentication guard to apply to all admin routes.
            This guard runs before the permission guards on each controller.
        enable_flags: Enable the flags CRUD controller. Defaults to True.
        enable_rules: Enable the rules CRUD controller. Defaults to True.
        enable_overrides: Enable the overrides CRUD controller. Defaults to True.
        enable_segments: Enable the segments CRUD controller. Defaults to True.
        enable_environments: Enable the environments CRUD controller. Defaults to True.
        enable_analytics: Enable the analytics query controller. Defaults to True.
        openapi_tag_group: OpenAPI tag group name for admin endpoints.
            Defaults to "Admin".
        include_entity_overrides: Include the entity-centric overrides controller.
            Defaults to True.

    Example:
        >>> config = AdminConfig(
        ...     path_prefix="/api/v1",
        ...     require_auth=True,
        ...     enable_analytics=False,
        ... )

    """

    enabled: bool = True
    path_prefix: str = ""
    require_auth: bool = True
    audit_logger: AuditLogger | None = None
    auth_guard: GuardCallable | None = None
    enable_flags: bool = True
    enable_rules: bool = True
    enable_overrides: bool = True
    enable_segments: bool = True
    enable_environments: bool = True
    enable_analytics: bool = True
    openapi_tag_group: str = "Admin"
    include_entity_overrides: bool = True


class AdminPlugin(InitPlugin):
    """Litestar plugin for the feature flags Admin API.

    Registers admin controllers for managing feature flags, rules, overrides,
    segments, environments, and analytics through a RESTful API.

    The plugin handles:
    - Dynamic controller registration based on configuration
    - Path prefix application for all admin routes
    - Audit logger initialization and storage in app state
    - OpenAPI tag configuration for documentation
    - Lifecycle hooks for startup and shutdown

    Example:
        Basic usage with defaults::

            from litestar import Litestar
            from litestar_flags import FeatureFlagsPlugin
            from litestar_flags.admin import AdminPlugin

            app = Litestar(
                route_handlers=[...],
                plugins=[FeatureFlagsPlugin(), AdminPlugin()],
            )

        With custom configuration::

            from litestar_flags.admin import AdminConfig, AdminPlugin
            from litestar_flags.admin.audit import InMemoryAuditLogger
            from litestar_flags.admin.guards import require_role, Role

            config = AdminConfig(
                path_prefix="/api/v1",
                audit_logger=InMemoryAuditLogger(),
                auth_guard=require_role(Role.ADMIN),
                enable_analytics=False,
            )
            app = Litestar(
                plugins=[FeatureFlagsPlugin(), AdminPlugin(config=config)],
            )

    """

    __slots__ = ("_config",)

    def __init__(self, config: AdminConfig | None = None) -> None:
        """Initialize the Admin API plugin.

        Args:
            config: Plugin configuration. Defaults to AdminConfig with default values.

        """
        self._config = config or AdminConfig()

    @property
    def config(self) -> AdminConfig:
        """Get the plugin configuration."""
        return self._config

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        """Configure the application with Admin API support.

        This method is called during application initialization. It:
        - Registers enabled controllers as route handlers
        - Sets up lifecycle hooks for audit logger initialization
        - Configures OpenAPI tags for documentation

        Args:
            app_config: The application configuration.

        Returns:
            Modified application configuration with admin routes and hooks.

        """
        if not self._config.enabled:
            logger.info("Admin API plugin is disabled")
            return app_config

        # Collect enabled controllers
        controllers: list[type[Any]] = []

        if self._config.enable_flags:
            controllers.append(FlagsController)
            logger.debug("Enabled FlagsController")

        if self._config.enable_rules:
            controllers.append(RulesController)
            logger.debug("Enabled RulesController")

        if self._config.enable_overrides:
            controllers.append(OverridesController)
            if self._config.include_entity_overrides:
                controllers.append(EntityOverridesController)
            logger.debug("Enabled OverridesController")

        if self._config.enable_segments:
            controllers.append(SegmentsController)
            logger.debug("Enabled SegmentsController")

        if self._config.enable_environments:
            controllers.append(EnvironmentsController)
            logger.debug("Enabled EnvironmentsController")

        if self._config.enable_analytics:
            controllers.append(AnalyticsController)
            logger.debug("Enabled AnalyticsController")

        if not controllers:
            logger.warning("Admin API plugin enabled but no controllers are active")
            return app_config

        # Build route handlers with optional path prefix and guards
        if self._config.path_prefix or self._config.auth_guard:
            # Wrap controllers in a router with the path prefix and/or guards
            router_guards: list[GuardCallable] = []
            if self._config.auth_guard:
                router_guards.append(self._config.auth_guard)

            admin_router = Router(
                path=self._config.path_prefix or "/",
                route_handlers=controllers,
                guards=router_guards if router_guards else None,
                tags=[self._config.openapi_tag_group],
            )
            app_config.route_handlers.append(admin_router)
            logger.info(
                f"Registered Admin API router at '{self._config.path_prefix}' "
                f"with {len(controllers)} controller(s)"
            )
        else:
            # Register controllers directly
            app_config.route_handlers.extend(controllers)
            logger.info(f"Registered {len(controllers)} Admin API controller(s)")

        # Add lifecycle hooks
        app_config.on_startup.append(self._startup)
        app_config.on_shutdown.append(self._shutdown)

        # Configure OpenAPI tags
        self._configure_openapi_tags(app_config)

        return app_config

    def _configure_openapi_tags(self, app_config: AppConfig) -> None:
        """Configure OpenAPI tags for admin endpoints.

        Adds tag descriptions for all admin controller groups to improve
        API documentation.

        Args:
            app_config: The application configuration to modify.

        """
        # Define tag metadata for each controller group
        admin_tags: list[dict[str, str]] = [
            {
                "name": "Admin - Flags",
                "description": "Feature flag CRUD operations",
            },
            {
                "name": "Admin - Rules",
                "description": "Targeting rule management for feature flags",
            },
            {
                "name": "Admin - Overrides",
                "description": "Entity-specific override management",
            },
            {
                "name": "Admin - Segments",
                "description": "User segment management for reusable targeting",
            },
            {
                "name": "Admin - Environments",
                "description": "Deployment environment configuration",
            },
            {
                "name": "Admin - Analytics",
                "description": "Flag evaluation analytics and metrics",
            },
        ]

        # OpenAPI config might not be initialized yet
        if app_config.openapi_config is not None:
            # Add tags to existing openapi config
            existing_tags = list(app_config.openapi_config.tags or [])

            for tag_info in admin_tags:
                # Check if tag already exists
                tag_exists = any(
                    (t.name if hasattr(t, "name") else t.get("name")) == tag_info["name"]
                    for t in existing_tags
                )
                if not tag_exists:
                    existing_tags.append(tag_info)  # type: ignore[arg-type]

            app_config.openapi_config.tags = existing_tags  # type: ignore[assignment]

    async def _startup(self, app: Litestar) -> None:
        """Initialize admin components on application startup.

        Stores the audit logger in app state for access by controllers.

        Args:
            app: The Litestar application.

        """
        logger.info("Initializing Admin API...")

        # Store audit logger in app state if configured
        if self._config.audit_logger is not None:
            app.state.feature_flags_audit_logger = self._config.audit_logger
            logger.info("Audit logger registered in app state")
        else:
            # Ensure the attribute exists even if None
            if not hasattr(app.state, "feature_flags_audit_logger"):
                app.state.feature_flags_audit_logger = None
            logger.debug("No audit logger configured")

        logger.info("Admin API initialized successfully")

    async def _shutdown(self, app: Litestar) -> None:
        """Clean up admin components on application shutdown.

        Args:
            app: The Litestar application.

        """
        logger.info("Shutting down Admin API...")

        # Clean up audit logger reference
        if hasattr(app.state, "feature_flags_audit_logger"):
            app.state.feature_flags_audit_logger = None

        logger.info("Admin API shutdown complete")

    def get_enabled_controllers(self) -> list[str]:
        """Get a list of enabled controller names.

        Useful for debugging and introspection.

        Returns:
            List of enabled controller class names.

        """
        controllers: list[str] = []

        if self._config.enable_flags:
            controllers.append("FlagsController")

        if self._config.enable_rules:
            controllers.append("RulesController")

        if self._config.enable_overrides:
            controllers.append("OverridesController")
            if self._config.include_entity_overrides:
                controllers.append("EntityOverridesController")

        if self._config.enable_segments:
            controllers.append("SegmentsController")

        if self._config.enable_environments:
            controllers.append("EnvironmentsController")

        if self._config.enable_analytics:
            controllers.append("AnalyticsController")

        return controllers
