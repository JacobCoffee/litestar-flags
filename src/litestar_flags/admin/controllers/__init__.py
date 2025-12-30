"""Admin API controllers for litestar-flags.

This module provides Litestar controllers for managing feature flags and related
resources through the Admin API. Each controller handles CRUD operations for a
specific resource type with proper permission guards and audit logging.

Controllers:
    FlagsController: Manage feature flags (create, read, update, delete).
    RulesController: Manage targeting rules for flags.
    OverridesController: Manage entity-specific overrides for flags.
    EntityOverridesController: Manage overrides by entity type and ID.
    SegmentsController: Manage user segments for targeting.
    EnvironmentsController: Manage deployment environments.
    AnalyticsController: Access flag evaluation metrics and events.

Example:
    Registering all controllers with a Litestar app::

        from litestar import Litestar
        from litestar_flags.admin.controllers import (
            AnalyticsController,
            EntityOverridesController,
            EnvironmentsController,
            FlagsController,
            OverridesController,
            RulesController,
            SegmentsController,
        )

        app = Litestar(
            route_handlers=[
                FlagsController,
                RulesController,
                OverridesController,
                EntityOverridesController,
                SegmentsController,
                EnvironmentsController,
                AnalyticsController,
            ],
        )

    Using a single controller::

        from litestar import Litestar
        from litestar_flags.admin.controllers import FlagsController

        app = Litestar(
            route_handlers=[FlagsController],
        )

"""

from __future__ import annotations

from litestar_flags.admin.controllers.analytics import AnalyticsController
from litestar_flags.admin.controllers.environments import EnvironmentsController
from litestar_flags.admin.controllers.flags import FlagsController
from litestar_flags.admin.controllers.overrides import (
    EntityOverridesController,
    OverridesController,
)
from litestar_flags.admin.controllers.rules import RulesController
from litestar_flags.admin.controllers.segments import SegmentsController

__all__ = [
    "AnalyticsController",
    "EntityOverridesController",
    "EnvironmentsController",
    "FlagsController",
    "OverridesController",
    "RulesController",
    "SegmentsController",
]
