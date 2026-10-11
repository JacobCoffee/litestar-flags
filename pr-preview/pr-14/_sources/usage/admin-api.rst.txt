Admin API
=========

The Admin API provides a complete RESTful interface for managing feature flags,
targeting rules, user segments, environments, and analytics. It includes
role-based access control, audit logging, and OpenAPI documentation.


Overview
--------

The Admin API enables programmatic management of your feature flag configuration:

- **Flags**: Create, read, update, delete, and archive feature flags
- **Rules**: Manage targeting rules with conditions and rollout percentages
- **Overrides**: Set entity-specific flag values for users, organizations, or devices
- **Segments**: Define reusable user segments for targeting
- **Environments**: Configure deployment environments with inheritance
- **Analytics**: Query evaluation metrics, events, and trends

All endpoints are protected by role-based access control (RBAC) and optionally
logged for audit purposes.


Prerequisites
~~~~~~~~~~~~~

The Admin API requires the ``FeatureFlagsPlugin`` to be registered with your
Litestar application:

.. code-block:: python

   from litestar import Litestar
   from litestar_flags import FeatureFlagsPlugin, FeatureFlagsConfig

   config = FeatureFlagsConfig()
   plugin = FeatureFlagsPlugin(config=config)

   app = Litestar(plugins=[plugin])


Installation & Setup
--------------------

Basic Setup
~~~~~~~~~~~

Register the ``FeatureFlagsAdminPlugin`` alongside the ``FeatureFlagsPlugin``:

.. code-block:: python

   from litestar import Litestar
   from litestar_flags import FeatureFlagsPlugin, FeatureFlagsConfig
   from litestar_flags.admin import FeatureFlagsAdminPlugin, FeatureFlagsAdminConfig

   # Feature flags configuration
   flags_config = FeatureFlagsConfig()
   flags_plugin = FeatureFlagsPlugin(config=flags_config)

   # Admin API configuration
   admin_plugin = FeatureFlagsAdminPlugin()

   app = Litestar(
       plugins=[flags_plugin, admin_plugin],
   )

This registers all Admin API controllers at their default paths under ``/admin``.


Custom Path Prefix
~~~~~~~~~~~~~~~~~~

Use a custom path prefix for API versioning or organizational needs:

.. code-block:: python

   admin_config = FeatureFlagsAdminConfig(
       path_prefix="/api/v1",  # Results in /api/v1/admin/flags, etc.
   )
   admin_plugin = FeatureFlagsAdminPlugin(config=admin_config)

   app = Litestar(
       plugins=[flags_plugin, admin_plugin],
   )


Selective Controller Registration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Enable only the controllers you need:

.. code-block:: python

   admin_config = FeatureFlagsAdminConfig(
       enable_flags=True,           # /admin/flags
       enable_rules=True,           # /admin/flags/{flag_id}/rules
       enable_overrides=True,       # /admin/flags/{flag_id}/overrides
       enable_segments=False,       # Disabled
       enable_environments=False,   # Disabled
       enable_analytics=True,       # /admin/analytics
   )

   admin_plugin = FeatureFlagsAdminPlugin(config=admin_config)


Configuration Options
---------------------

The ``FeatureFlagsAdminConfig`` dataclass provides comprehensive configuration:

.. code-block:: python

   from litestar_flags.admin import FeatureFlagsAdminConfig

   config = FeatureFlagsAdminConfig(
       # Core settings
       enabled=True,                    # Enable/disable the entire Admin API
       path_prefix="/api/v1",           # URL prefix for all endpoints
       require_auth=True,               # Require authentication

       # Controller toggles
       enable_flags=True,               # Flag CRUD controller
       enable_rules=True,               # Rule management controller
       enable_overrides=True,           # Override management controller
       enable_segments=True,            # Segment management controller
       enable_environments=True,        # Environment management controller
       enable_analytics=True,           # Analytics query controller

       # Entity overrides controller (entity-centric view)
       include_entity_overrides=True,   # /admin/overrides/entity endpoints

       # OpenAPI configuration
       openapi_tag_group="Admin",       # Tag group in OpenAPI docs
   )

**Configuration Reference:**

+---------------------------+------------+---------------------------------------------+
| Option                    | Default    | Description                                 |
+===========================+============+=============================================+
| ``enabled``               | ``True``   | Enable/disable the entire Admin API         |
+---------------------------+------------+---------------------------------------------+
| ``path_prefix``           | ``""``     | URL prefix prepended to all routes          |
+---------------------------+------------+---------------------------------------------+
| ``require_auth``          | ``True``   | Reject requests without authenticated user  |
+---------------------------+------------+---------------------------------------------+
| ``audit_logger``          | ``None``   | AuditLogger instance for logging actions    |
+---------------------------+------------+---------------------------------------------+
| ``auth_guard``            | ``None``   | Custom guard applied to all routes          |
+---------------------------+------------+---------------------------------------------+
| ``enable_flags``          | ``True``   | Enable flags CRUD controller                |
+---------------------------+------------+---------------------------------------------+
| ``enable_rules``          | ``True``   | Enable rules management controller          |
+---------------------------+------------+---------------------------------------------+
| ``enable_overrides``      | ``True``   | Enable overrides management controller      |
+---------------------------+------------+---------------------------------------------+
| ``enable_segments``       | ``True``   | Enable segments management controller       |
+---------------------------+------------+---------------------------------------------+
| ``enable_environments``   | ``True``   | Enable environments management controller   |
+---------------------------+------------+---------------------------------------------+
| ``enable_analytics``      | ``True``   | Enable analytics query controller           |
+---------------------------+------------+---------------------------------------------+


Authentication & Authorization
------------------------------

The Admin API uses a flexible role-based access control (RBAC) system that
integrates with your existing authentication mechanism.

Permission System
~~~~~~~~~~~~~~~~~

Permissions follow a ``resource:action`` naming convention:

.. code-block:: python

   from litestar_flags.admin import Permission

   # Flag permissions
   Permission.FLAGS_READ      # "flags:read"
   Permission.FLAGS_WRITE     # "flags:write"
   Permission.FLAGS_DELETE    # "flags:delete"

   # Rule permissions
   Permission.RULES_READ      # "rules:read"
   Permission.RULES_WRITE     # "rules:write"

   # Segment permissions
   Permission.SEGMENTS_READ   # "segments:read"
   Permission.SEGMENTS_WRITE  # "segments:write"

   # Environment permissions
   Permission.ENVIRONMENTS_READ   # "environments:read"
   Permission.ENVIRONMENTS_WRITE  # "environments:write"

   # Analytics permissions
   Permission.ANALYTICS_READ  # "analytics:read"

   # Superadmin (grants all permissions)
   Permission.ADMIN_ALL       # "admin:*"


Role System
~~~~~~~~~~~

Predefined roles group common permission sets:

.. code-block:: python

   from litestar_flags.admin import Role, ROLE_PERMISSIONS

   # VIEWER: Read-only access
   Role.VIEWER
   # Permissions: flags:read, rules:read, segments:read,
   #              environments:read, analytics:read

   # EDITOR: Read + Write (no delete)
   Role.EDITOR
   # Permissions: All VIEWER permissions plus
   #              flags:write, rules:write, segments:write, environments:write

   # ADMIN: Full access (except superadmin actions)
   Role.ADMIN
   # Permissions: All EDITOR permissions plus flags:delete

   # SUPERADMIN: Unrestricted access
   Role.SUPERADMIN
   # Permissions: All permissions including admin:*

**Role Permission Mapping:**

+----------------+-------+-------+--------+------------+
| Permission     | VIEWER| EDITOR| ADMIN  | SUPERADMIN |
+================+=======+=======+========+============+
| flags:read     | Yes   | Yes   | Yes    | Yes        |
+----------------+-------+-------+--------+------------+
| flags:write    | No    | Yes   | Yes    | Yes        |
+----------------+-------+-------+--------+------------+
| flags:delete   | No    | No    | Yes    | Yes        |
+----------------+-------+-------+--------+------------+
| rules:read     | Yes   | Yes   | Yes    | Yes        |
+----------------+-------+-------+--------+------------+
| rules:write    | No    | Yes   | Yes    | Yes        |
+----------------+-------+-------+--------+------------+
| segments:read  | Yes   | Yes   | Yes    | Yes        |
+----------------+-------+-------+--------+------------+
| segments:write | No    | Yes   | Yes    | Yes        |
+----------------+-------+-------+--------+------------+
| environments:* | Yes/No| Yes   | Yes    | Yes        |
+----------------+-------+-------+--------+------------+
| analytics:read | Yes   | Yes   | Yes    | Yes        |
+----------------+-------+-------+--------+------------+
| admin:*        | No    | No    | No     | Yes        |
+----------------+-------+-------+--------+------------+


Using Guards in Route Handlers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Apply guards to your custom endpoints:

.. code-block:: python

   from litestar import get, post
   from litestar_flags.admin import (
       Permission,
       Role,
       require_permission,
       require_role,
       require_superadmin,
   )

   # Require specific permission
   @get(
       "/my-endpoint",
       guards=[require_permission(Permission.FLAGS_READ)],
   )
   async def read_endpoint() -> dict:
       return {"status": "ok"}

   # Require multiple permissions (all required by default)
   @post(
       "/my-endpoint",
       guards=[require_permission(
           Permission.FLAGS_READ,
           Permission.FLAGS_WRITE,
       )],
   )
   async def write_endpoint() -> dict:
       return {"status": "created"}

   # Require any of multiple permissions
   @get(
       "/flexible-endpoint",
       guards=[require_permission(
           Permission.FLAGS_READ,
           Permission.ANALYTICS_READ,
           require_all=False,  # Only one required
       )],
   )
   async def flexible_endpoint() -> dict:
       return {"status": "ok"}

   # Require specific role
   @get(
       "/admin-only",
       guards=[require_role(Role.ADMIN)],
   )
   async def admin_endpoint() -> dict:
       return {"admin": True}

   # Require superadmin
   @get(
       "/superadmin-only",
       guards=[require_superadmin()],
   )
   async def superadmin_endpoint() -> dict:
       return {"superadmin": True}


Implementing a User Provider
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The guard system looks for user information in the connection state. Create a
user object that implements the ``HasPermissions`` protocol:

.. code-block:: python

   from dataclasses import dataclass
   from litestar_flags.admin import Role, Permission, HasPermissions

   @dataclass
   class AdminUser:
       """User class implementing HasPermissions protocol."""

       id: str
       roles: list[Role]
       permissions: list[Permission] | None = None

   # Example: Create an admin user
   user = AdminUser(
       id="user-123",
       roles=[Role.ADMIN],
       permissions=[Permission.ANALYTICS_READ],  # Additional permissions
   )

The user object can also be a dictionary:

.. code-block:: python

   user = {
       "id": "user-123",
       "roles": ["admin"],  # String values are converted to Role enum
       "permissions": ["analytics:read"],
   }


JWT Authentication Example
~~~~~~~~~~~~~~~~~~~~~~~~~~

Integrate with JWT authentication:

.. code-block:: python

   from dataclasses import dataclass
   from litestar import Litestar, Request
   from litestar.middleware import AbstractAuthenticationMiddleware, AuthenticationResult
   from litestar.connection import ASGIConnection
   from litestar_flags.admin import Role, FeatureFlagsAdminPlugin, FeatureFlagsAdminConfig
   import jwt

   @dataclass
   class AdminUser:
       id: str
       roles: list[Role]
       permissions: list | None = None

   class JWTAuthMiddleware(AbstractAuthenticationMiddleware):
       async def authenticate_request(
           self,
           connection: ASGIConnection,
       ) -> AuthenticationResult:
           auth_header = connection.headers.get("Authorization")
           if not auth_header or not auth_header.startswith("Bearer "):
               return AuthenticationResult(user=None, auth=None)

           token = auth_header[7:]
           try:
               payload = jwt.decode(token, "secret", algorithms=["HS256"])
               user = AdminUser(
                   id=payload["sub"],
                   roles=[Role(r) for r in payload.get("roles", [])],
               )
               return AuthenticationResult(user=user, auth=token)
           except jwt.InvalidTokenError:
               return AuthenticationResult(user=None, auth=None)

   # Configure Admin API with auth middleware
   admin_config = FeatureFlagsAdminConfig(require_auth=True)
   admin_plugin = FeatureFlagsAdminPlugin(config=admin_config)

   app = Litestar(
       plugins=[flags_plugin, admin_plugin],
       middleware=[JWTAuthMiddleware],
   )


Custom Auth Guard
~~~~~~~~~~~~~~~~~

Apply a custom authentication guard to all Admin API routes:

.. code-block:: python

   from litestar.connection import ASGIConnection
   from litestar.handlers.base import BaseRouteHandler
   from litestar.exceptions import NotAuthorizedException

   async def my_auth_guard(
       connection: ASGIConnection,
       _: BaseRouteHandler,
   ) -> None:
       """Custom authentication guard."""
       api_key = connection.headers.get("X-API-Key")
       if not api_key or not await validate_api_key(api_key):
           raise NotAuthorizedException(detail="Invalid API key")

   admin_config = FeatureFlagsAdminConfig(
       auth_guard=my_auth_guard,
   )


API Endpoints
-------------

All endpoints return JSON responses and accept JSON request bodies where
applicable. Pagination is supported for list endpoints.

Flags API
~~~~~~~~~

Base path: ``/admin/flags``

**List Flags**

.. code-block:: text

   GET /admin/flags?page=1&page_size=20&status=active&tag=beta&search=checkout

Query parameters:

- ``page``: Page number (1-indexed, default: 1)
- ``page_size``: Items per page (1-100, default: 20)
- ``status``: Filter by status (active, archived)
- ``tag``: Filter by tag
- ``search``: Search in key and name

Response:

.. code-block:: json

   {
     "items": [
       {
         "id": "550e8400-e29b-41d4-a716-446655440000",
         "key": "checkout_redesign",
         "name": "Checkout Redesign",
         "description": "New checkout flow",
         "flag_type": "boolean",
         "status": "active",
         "default_enabled": false,
         "default_value": null,
         "tags": ["beta", "checkout"],
         "metadata": {},
         "rules_count": 2,
         "overrides_count": 5,
         "variants_count": 0,
         "created_at": "2024-01-15T10:30:00Z",
         "updated_at": "2024-01-20T14:45:00Z"
       }
     ],
     "total": 42,
     "page": 1,
     "page_size": 20,
     "total_pages": 3
   }

**Get Flag by ID**

.. code-block:: text

   GET /admin/flags/{flag_id}

**Get Flag by Key**

.. code-block:: text

   GET /admin/flags/by-key/{key}

**Create Flag**

.. code-block:: text

   POST /admin/flags
   Content-Type: application/json

   {
     "key": "new_feature",
     "name": "New Feature",
     "description": "Description of the new feature",
     "flag_type": "boolean",
     "default_enabled": false,
     "default_value": null,
     "tags": ["new", "experiment"],
     "metadata": {"owner": "team-a"}
   }

**Update Flag (Full)**

.. code-block:: text

   PUT /admin/flags/{flag_id}
   Content-Type: application/json

   {
     "name": "Updated Name",
     "description": "Updated description",
     "flag_type": "boolean",
     "status": "active",
     "default_enabled": true,
     "default_value": null,
     "tags": ["updated"],
     "metadata": {}
   }

**Update Flag (Partial)**

.. code-block:: text

   PATCH /admin/flags/{flag_id}
   Content-Type: application/json

   {
     "default_enabled": true
   }

**Delete Flag**

.. code-block:: text

   DELETE /admin/flags/{flag_id}

**Archive Flag**

.. code-block:: text

   POST /admin/flags/{flag_id}/archive

**Restore Archived Flag**

.. code-block:: text

   POST /admin/flags/{flag_id}/restore


Rules API
~~~~~~~~~

Base path: ``/admin/flags/{flag_id}/rules``

Rules define targeting conditions that determine which users receive which
flag values. Rules are evaluated in priority order (lowest number first).

**List Rules**

.. code-block:: text

   GET /admin/flags/{flag_id}/rules?page=1&page_size=20

**Get Rule**

.. code-block:: text

   GET /admin/flags/{flag_id}/rules/{rule_id}

**Create Rule**

.. code-block:: text

   POST /admin/flags/{flag_id}/rules
   Content-Type: application/json

   {
     "name": "Premium Users",
     "description": "Enable for premium plan subscribers",
     "priority": 0,
     "enabled": true,
     "conditions": [
       {
         "attribute": "plan",
         "operator": "eq",
         "value": "premium"
       },
       {
         "attribute": "country",
         "operator": "in",
         "value": ["US", "CA", "UK"]
       }
     ],
     "serve_enabled": true,
     "serve_value": null,
     "rollout_percentage": 100
   }

**Condition Operators:**

+------------------+--------------------------------------------------+
| Operator         | Description                                      |
+==================+==================================================+
| ``eq``           | Equals                                           |
+------------------+--------------------------------------------------+
| ``ne``           | Not equals                                       |
+------------------+--------------------------------------------------+
| ``in``           | Value is in list                                 |
+------------------+--------------------------------------------------+
| ``not_in``       | Value is not in list                             |
+------------------+--------------------------------------------------+
| ``contains``     | String/list contains value                       |
+------------------+--------------------------------------------------+
| ``not_contains`` | String/list does not contain value               |
+------------------+--------------------------------------------------+
| ``starts_with``  | String starts with value                         |
+------------------+--------------------------------------------------+
| ``ends_with``    | String ends with value                           |
+------------------+--------------------------------------------------+
| ``gt``           | Greater than                                     |
+------------------+--------------------------------------------------+
| ``gte``          | Greater than or equal                            |
+------------------+--------------------------------------------------+
| ``lt``           | Less than                                        |
+------------------+--------------------------------------------------+
| ``lte``          | Less than or equal                               |
+------------------+--------------------------------------------------+
| ``exists``       | Attribute exists                                 |
+------------------+--------------------------------------------------+
| ``not_exists``   | Attribute does not exist                         |
+------------------+--------------------------------------------------+
| ``regex``        | Matches regular expression                       |
+------------------+--------------------------------------------------+

**Update Rule**

.. code-block:: text

   PUT /admin/flags/{flag_id}/rules/{rule_id}
   Content-Type: application/json

   {
     "name": "Premium Users - Updated",
     "priority": 0,
     "enabled": true,
     "conditions": [...],
     "serve_enabled": true,
     "rollout_percentage": 50
   }

**Partial Update Rule**

.. code-block:: text

   PATCH /admin/flags/{flag_id}/rules/{rule_id}
   Content-Type: application/json

   {
     "rollout_percentage": 75
   }

**Delete Rule**

.. code-block:: text

   DELETE /admin/flags/{flag_id}/rules/{rule_id}

**Reorder Rules**

.. code-block:: text

   POST /admin/flags/{flag_id}/rules/reorder
   Content-Type: application/json

   {
     "rule_ids": [
       "uuid-of-new-first-rule",
       "uuid-of-new-second-rule",
       "uuid-of-new-third-rule"
     ]
   }

**Toggle Rule Enabled State**

.. code-block:: text

   POST /admin/flags/{flag_id}/rules/{rule_id}/toggle


Overrides API
~~~~~~~~~~~~~

Base path: ``/admin/flags/{flag_id}/overrides``

Overrides allow specific entities (users, organizations, devices) to have
different flag values than what targeting rules would determine.

**List Overrides for Flag**

.. code-block:: text

   GET /admin/flags/{flag_id}/overrides?include_expired=false&entity_type=user

**Get Override**

.. code-block:: text

   GET /admin/flags/{flag_id}/overrides/{entity_type}/{entity_id}

**Create Override**

.. code-block:: text

   POST /admin/flags/{flag_id}/overrides
   Content-Type: application/json

   {
     "entity_type": "user",
     "entity_id": "user-12345",
     "enabled": true,
     "value": {"variant": "treatment_a"},
     "expires_at": "2024-12-31T23:59:59Z"
   }

Supported entity types: ``user``, ``organization``, ``team``, ``device``, ``custom``

**Update Override**

.. code-block:: text

   PUT /admin/flags/{flag_id}/overrides/{entity_type}/{entity_id}
   Content-Type: application/json

   {
     "enabled": false,
     "value": null,
     "expires_at": null
   }

**Delete Override**

.. code-block:: text

   DELETE /admin/flags/{flag_id}/overrides/{entity_type}/{entity_id}

**Entity-Centric Endpoints**

List all overrides for a specific entity across all flags:

.. code-block:: text

   GET /admin/overrides/entity/{entity_type}/{entity_id}

Delete all overrides for an entity:

.. code-block:: text

   DELETE /admin/overrides/entity/{entity_type}/{entity_id}


Segments API
~~~~~~~~~~~~

Base path: ``/admin/segments``

Segments define reusable groups of users based on shared attributes.
Segments support hierarchical relationships.

**List Segments**

.. code-block:: text

   GET /admin/segments?page=1&page_size=20&enabled=true&search=premium

**Get Segment**

.. code-block:: text

   GET /admin/segments/{segment_id}

**Get Segment by Name**

.. code-block:: text

   GET /admin/segments/by-name/{name}

**Create Segment**

.. code-block:: text

   POST /admin/segments
   Content-Type: application/json

   {
     "name": "premium_users",
     "description": "Users on premium plans",
     "enabled": true,
     "conditions": [
       {
         "attribute": "plan",
         "operator": "in",
         "value": ["premium", "enterprise"]
       }
     ],
     "parent_segment_id": null
   }

**Update Segment**

.. code-block:: text

   PATCH /admin/segments/{segment_id}
   Content-Type: application/json

   {
     "enabled": false
   }

**Delete Segment**

.. code-block:: text

   DELETE /admin/segments/{segment_id}

Note: Segments with child segments cannot be deleted. Delete or reassign
children first.

**Get Child Segments**

.. code-block:: text

   GET /admin/segments/{segment_id}/children

**Evaluate Segment**

Test whether a context matches segment conditions:

.. code-block:: text

   POST /admin/segments/{segment_id}/evaluate
   Content-Type: application/json

   {
     "context": {
       "plan": "premium",
       "country": "US",
       "signup_date": "2024-01-15"
     }
   }

Response:

.. code-block:: json

   {
     "matches": true,
     "segment_id": "...",
     "segment_name": "premium_users",
     "matched_conditions": [
       {"attribute": "plan", "operator": "in", "value": ["premium", "enterprise"]}
     ],
     "failed_conditions": []
   }


Environments API
~~~~~~~~~~~~~~~~

Base path: ``/admin/environments``

Environments represent deployment targets (e.g., development, staging,
production) with hierarchical inheritance support.

**List Environments**

.. code-block:: text

   GET /admin/environments?active_only=true&root_only=false

**Get Environment**

.. code-block:: text

   GET /admin/environments/{env_id}

**Get Environment by Slug**

.. code-block:: text

   GET /admin/environments/by-slug/{slug}

**Create Environment**

.. code-block:: text

   POST /admin/environments
   Content-Type: application/json

   {
     "name": "Staging EU",
     "slug": "staging-eu",
     "description": "European staging environment",
     "parent_id": "uuid-of-staging",
     "is_production": false,
     "color": "#FFA500",
     "settings": {
       "region": "eu-west-1",
       "debug": true
     }
   }

Slug format: lowercase alphanumeric with hyphens (e.g., ``staging-eu``, ``prod-1``)

**Update Environment**

.. code-block:: text

   PATCH /admin/environments/{env_id}
   Content-Type: application/json

   {
     "is_production": true
   }

**Delete Environment**

.. code-block:: text

   DELETE /admin/environments/{env_id}?force=false

Use ``force=true`` to delete production environments.

**Get Child Environments**

.. code-block:: text

   GET /admin/environments/{env_id}/children

**Environment Flag Configurations**

Get flag configurations for an environment (includes inherited):

.. code-block:: text

   GET /admin/environments/{env_id}/flags?include_inherited=true

Set environment-specific flag configuration:

.. code-block:: text

   PUT /admin/environments/{env_id}/flags/{flag_id}
   Content-Type: application/json

   {
     "enabled": true,
     "percentage": 50.0,
     "rules": null,
     "variants": null
   }

Remove environment-specific configuration (revert to inherited/base):

.. code-block:: text

   DELETE /admin/environments/{env_id}/flags/{flag_id}


Analytics API
~~~~~~~~~~~~~

Base path: ``/admin/analytics``

Query flag evaluation metrics, events, and trends.

**Get Flag Metrics**

.. code-block:: text

   GET /admin/analytics/metrics/{flag_key}?window_seconds=3600

Response:

.. code-block:: json

   {
     "flag_key": "checkout_redesign",
     "evaluation_rate": 12.5,
     "unique_users": 1500,
     "total_evaluations": 45000,
     "variant_distribution": {
       "control": 22500,
       "treatment": 22500
     },
     "reason_distribution": {
       "TARGETING_MATCH": 30000,
       "SPLIT": 15000
     },
     "error_rate": 0.01,
     "latency_p50": 1.2,
     "latency_p90": 2.5,
     "latency_p99": 5.0,
     "window_start": "2024-01-20T13:00:00Z",
     "window_end": "2024-01-20T14:00:00Z"
   }

**Get All Flags Metrics**

.. code-block:: text

   GET /admin/analytics/metrics?window_seconds=3600

**Query Events**

.. code-block:: text

   GET /admin/analytics/events?flag_key=checkout&targeting_key=user-123&page=1&page_size=50

Query parameters:

- ``flag_key``: Filter by flag key
- ``targeting_key``: Filter by user/entity ID
- ``reason``: Filter by evaluation reason
- ``variant``: Filter by variant
- ``since``: Events after this timestamp (ISO 8601)
- ``until``: Events before this timestamp (ISO 8601)
- ``page``: Page number
- ``page_size``: Items per page (1-1000)

**Get Events for Flag**

.. code-block:: text

   GET /admin/analytics/events/{flag_key}?page=1&page_size=50

**Get Dashboard Summary**

.. code-block:: text

   GET /admin/analytics/dashboard?window_seconds=86400&limit=10

Response:

.. code-block:: json

   {
     "total_flags_evaluated": 15,
     "total_evaluations": 250000,
     "overall_error_rate": 0.02,
     "overall_evaluation_rate": 2.89,
     "flag_summaries": [
       {
         "flag_key": "checkout_redesign",
         "total_evaluations": 45000,
         "evaluation_rate": 0.52,
         "unique_users": 1500,
         "error_rate": 0.01,
         "top_variant": "treatment"
       }
     ],
     "window_start": "2024-01-19T14:00:00Z",
     "window_end": "2024-01-20T14:00:00Z"
   }

**Get Trend Data**

.. code-block:: text

   GET /admin/analytics/trends/{flag_key}?granularity=hour&window_seconds=86400

Granularity options: ``hour``, ``day``, ``week``

**Export Events**

.. code-block:: text

   GET /admin/analytics/export?format=csv&flag_key=checkout&limit=10000

Formats: ``csv``, ``json``


Audit Logging
-------------

The Admin API supports comprehensive audit logging of all administrative
actions for compliance and debugging purposes.

Enabling Audit Logging
~~~~~~~~~~~~~~~~~~~~~~

Configure an audit logger when setting up the Admin API:

.. code-block:: python

   from litestar_flags.admin import (
       FeatureFlagsAdminConfig,
       FeatureFlagsAdminPlugin,
       InMemoryAuditLogger,
   )

   # Create audit logger
   audit_logger = InMemoryAuditLogger(max_entries=10000)

   # Configure Admin API with audit logging
   admin_config = FeatureFlagsAdminConfig(
       audit_logger=audit_logger,
   )

   admin_plugin = FeatureFlagsAdminPlugin(config=admin_config)


Audit Entry Structure
~~~~~~~~~~~~~~~~~~~~~

Each audit entry captures:

.. code-block:: python

   from litestar_flags.admin import AuditEntry, AuditAction, ResourceType

   # Example audit entry (created automatically)
   entry = AuditEntry(
       id=uuid4(),
       timestamp=datetime.now(UTC),
       action=AuditAction.UPDATE,
       resource_type=ResourceType.FLAG,
       resource_id=uuid4(),
       resource_key="checkout_redesign",
       actor_id="user-123",
       actor_type="user",
       ip_address="192.168.1.100",
       user_agent="Mozilla/5.0...",
       changes={
           "before": {"default_enabled": False},
           "after": {"default_enabled": True},
           "changed_fields": ["default_enabled"],
       },
       metadata={"reason": "Rolling out to 50%"},
   )

**Audit Actions:**

- ``CREATE``: Resource creation
- ``UPDATE``: Resource modification
- ``DELETE``: Resource deletion
- ``READ``: Sensitive resource access
- ``ENABLE``: Enabling a flag/rule
- ``DISABLE``: Disabling a flag/rule
- ``PROMOTE``: Promoting to new environment
- ``ARCHIVE``: Archiving a resource

**Resource Types:**

- ``FLAG``: Feature flag
- ``RULE``: Targeting rule
- ``OVERRIDE``: Entity override
- ``SEGMENT``: User segment
- ``ENVIRONMENT``: Deployment environment
- ``ENVIRONMENT_FLAG``: Environment-specific flag config


Querying Audit Logs
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from litestar_flags.admin import ResourceType

   # Get recent entries
   entries = await audit_logger.get_entries(limit=100)

   # Filter by resource type
   flag_entries = await audit_logger.get_entries(
       resource_type=ResourceType.FLAG,
       limit=50,
   )

   # Filter by specific resource
   entries = await audit_logger.get_entries(
       resource_type=ResourceType.FLAG,
       resource_id=flag_id,
   )

   # Filter by actor
   user_entries = await audit_logger.get_entries_by_actor(
       actor_id="user-123",
       limit=100,
   )

   # Filter by action
   deletions = await audit_logger.get_entries_by_action(
       action=AuditAction.DELETE,
       limit=50,
   )

   # Filter by time range
   from datetime import datetime, timedelta

   yesterday = datetime.now(UTC) - timedelta(days=1)
   entries = await audit_logger.get_entries_in_timerange(
       start=yesterday,
       end=datetime.now(UTC),
   )


Custom Audit Logger
~~~~~~~~~~~~~~~~~~~

Implement the ``AuditLogger`` protocol for custom storage:

.. code-block:: python

   from litestar_flags.admin import AuditLogger, AuditEntry, ResourceType

   class DatabaseAuditLogger:
       """Store audit entries in a database."""

       def __init__(self, db_session):
           self.session = db_session

       async def log(self, entry: AuditEntry) -> None:
           """Store an audit entry."""
           await self.session.execute(
               insert(audit_table).values(**entry.to_dict())
           )
           await self.session.commit()

       async def get_entries(
           self,
           resource_type: ResourceType | None = None,
           resource_id: UUID | str | None = None,
           limit: int = 100,
           offset: int = 0,
       ) -> list[AuditEntry]:
           """Query audit entries."""
           query = select(audit_table)
           if resource_type:
               query = query.where(audit_table.c.resource_type == resource_type.value)
           if resource_id:
               query = query.where(audit_table.c.resource_id == str(resource_id))
           query = query.order_by(audit_table.c.timestamp.desc())
           query = query.limit(limit).offset(offset)
           result = await self.session.execute(query)
           return [self._row_to_entry(row) for row in result]


OpenAPI Integration
-------------------

The Admin API automatically generates OpenAPI (Swagger) documentation with
proper schemas, descriptions, and security definitions.

Tags
~~~~

All Admin API endpoints are organized under descriptive tags:

- **Admin - Flags**: Feature flag CRUD operations
- **Admin - Rules**: Targeting rule management
- **Admin - Overrides**: Entity override management
- **Admin - Segments**: User segment management
- **Admin - Environments**: Environment configuration
- **Admin - Analytics**: Flag analytics and metrics

Security Schemes
~~~~~~~~~~~~~~~~

When using authentication guards, document security requirements:

.. code-block:: python

   from litestar import Litestar
   from litestar.openapi import OpenAPIConfig
   from litestar.openapi.spec import SecurityScheme

   openapi_config = OpenAPIConfig(
       title="My API",
       version="1.0.0",
       security=[{"BearerAuth": []}],
       components={
           "securitySchemes": {
               "BearerAuth": SecurityScheme(
                   type="http",
                   scheme="bearer",
                   bearer_format="JWT",
               ),
           },
       },
   )

   app = Litestar(
       plugins=[flags_plugin, admin_plugin],
       openapi_config=openapi_config,
   )


Complete Example
----------------

Full example with all features:

.. code-block:: python

   from dataclasses import dataclass
   from litestar import Litestar
   from litestar.middleware import AbstractAuthenticationMiddleware, AuthenticationResult
   from litestar.connection import ASGIConnection
   from litestar_flags import FeatureFlagsPlugin, FeatureFlagsConfig
   from litestar_flags.storage import MemoryStorageBackend
   from litestar_flags.admin import (
       FeatureFlagsAdminPlugin,
       FeatureFlagsAdminConfig,
       InMemoryAuditLogger,
       Role,
   )

   @dataclass
   class User:
       id: str
       roles: list[Role]
       permissions: list | None = None

   class AuthMiddleware(AbstractAuthenticationMiddleware):
       async def authenticate_request(
           self,
           connection: ASGIConnection,
       ) -> AuthenticationResult:
           # Your authentication logic here
           user = User(id="admin-1", roles=[Role.ADMIN])
           return AuthenticationResult(user=user, auth=None)

   # Feature flags setup
   flags_config = FeatureFlagsConfig(
       storage_backend=MemoryStorageBackend(),
   )
   flags_plugin = FeatureFlagsPlugin(config=flags_config)

   # Admin API setup with audit logging
   audit_logger = InMemoryAuditLogger(max_entries=10000)
   admin_config = FeatureFlagsAdminConfig(
       path_prefix="/api/v1",
       require_auth=True,
       audit_logger=audit_logger,
       enable_analytics=True,
   )
   admin_plugin = FeatureFlagsAdminPlugin(config=admin_config)

   app = Litestar(
       plugins=[flags_plugin, admin_plugin],
       middleware=[AuthMiddleware],
   )


See Also
--------

- :doc:`/getting-started/quickstart` - Getting started with litestar-flags
- :doc:`/user-guide/analytics` - Analytics module documentation
- :doc:`/guides/user-targeting` - User targeting guide
- :doc:`/api/index` - Complete API reference
