Multi-Environment Support
=========================

Multi-environment support enables you to manage feature flags across different
deployment environments (development, staging, production) with environment-specific
configurations and hierarchical inheritance.


What is Multi-Environment Support?
----------------------------------

Multi-environment support allows you to:

- **Define separate environments** with their own flag configurations
- **Inherit flag values** from parent environments to reduce duplication
- **Override specific flags** per environment without affecting others
- **Automatically detect** the current environment from requests
- **Promote flags** between environments in a controlled workflow

This is essential for teams that need different feature flag behavior across
their deployment pipeline.


Use Cases
---------

**Development/Staging/Production Pipeline**

Enable features in development and staging for testing before production rollout:

.. code-block:: text

   production (base)
       |
       +-- staging (inherits from production, enables beta features)
       |       |
       |       +-- development (inherits from staging, enables experimental features)

**Regional Deployments**

Customize features for different geographic regions:

.. code-block:: text

   global (base)
       |
       +-- us (US-specific features)
       |
       +-- eu (EU-specific features, GDPR compliance)
       |
       +-- asia (Asia-specific features)

**Feature Branch Testing**

Isolate flag configurations for feature branch deployments:

.. code-block:: text

   staging
       |
       +-- feature-xyz (isolated environment for feature testing)


Core Concepts
-------------

Environment Model
~~~~~~~~~~~~~~~~~

The ``Environment`` model represents a deployment environment with optional
inheritance from a parent environment.

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Field
     - Type
     - Description
   * - ``name``
     - ``str``
     - Human-readable display name (e.g., "Production", "Staging")
   * - ``slug``
     - ``str``
     - URL-safe unique identifier (e.g., "production", "staging")
   * - ``description``
     - ``str | None``
     - Optional description of the environment's purpose
   * - ``parent_id``
     - ``UUID | None``
     - Reference to parent environment for inheritance
   * - ``settings``
     - ``dict[str, Any]``
     - Environment-specific settings stored as JSON
   * - ``is_active``
     - ``bool``
     - Whether this environment is active for flag evaluation
   * - ``parent``
     - ``Environment | None``
     - The parent Environment object (populated via relationship)
   * - ``children``
     - ``list[Environment]``
     - Child environments that inherit from this environment


EnvironmentFlag Model
~~~~~~~~~~~~~~~~~~~~~

The ``EnvironmentFlag`` model stores per-environment flag overrides. Values set
to ``None`` indicate that the flag should inherit from the base flag or parent
environment.

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Field
     - Type
     - Description
   * - ``environment_id``
     - ``UUID``
     - Reference to the environment this override applies to
   * - ``flag_id``
     - ``UUID``
     - Reference to the base feature flag being overridden
   * - ``enabled``
     - ``bool | None``
     - Override enabled state (``None`` = inherit from base)
   * - ``percentage``
     - ``float | None``
     - Override rollout percentage (``None`` = inherit)
   * - ``rules``
     - ``list[dict] | None``
     - Override targeting rules as JSON (``None`` = inherit)
   * - ``variants``
     - ``list[dict] | None``
     - Override variants as JSON (``None`` = inherit)


Environment Inheritance Chain
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When evaluating a flag for a specific environment, the resolver walks the
inheritance chain from the most specific environment (child) up to the root
(parent with no parent). The first override found is applied.

.. code-block:: text

   Request for "staging" environment:

   1. Check if staging has override for flag -> YES -> use staging's value
   2. Check if dev (staging's parent) has override -> skip (found in step 1)
   3. Check base flag configuration -> skip (found in step 1)

   Request for "feature-branch" environment:

   1. Check if feature-branch has override -> NO
   2. Check if staging (feature-branch's parent) has override -> YES -> use staging's value
   3. Check base flag configuration -> skip (found in step 2)

This allows you to define flag values at the appropriate level and have them
automatically propagate to child environments.


Configuration
-------------

FeatureFlagsConfig Settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Configure multi-environment support in your ``FeatureFlagsConfig``:

.. code-block:: python

   from litestar_flags import FeatureFlagsConfig

   config = FeatureFlagsConfig(
       backend="database",
       connection_string="postgresql+asyncpg://user:pass@localhost/db",

       # Environment settings
       default_environment="production",
       enable_environment_inheritance=True,
       enable_environment_middleware=True,
       environment_header="X-Environment",
       environment_query_param="env",
       allowed_environments=["production", "staging", "development"],
   )

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Setting
     - Description
   * - ``default_environment``
     - Default environment slug when none is detected from request.
       Must be alphanumeric with hyphens or underscores.
   * - ``enable_environment_inheritance``
     - Whether child environments inherit flag values from parents.
       Defaults to ``True``.
   * - ``enable_environment_middleware``
     - Whether to enable automatic environment detection from requests.
   * - ``environment_header``
     - HTTP header name for environment detection (default: ``X-Environment``).
   * - ``environment_query_param``
     - Query parameter name for environment detection (default: ``env``).
       Set to ``None`` to disable query param detection.
   * - ``allowed_environments``
     - Optional list of allowed environment slugs. Requests with environments
       not in this list fall back to ``default_environment``.


Environment Middleware Setup
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``EnvironmentMiddleware`` automatically extracts the environment from
incoming requests and stores it in the request scope for flag evaluation.

**Detection Priority:**

1. HTTP header (configurable via ``environment_header``)
2. Query parameter (configurable via ``environment_query_param``)
3. Default environment from config (``default_environment``)

.. code-block:: python

   from litestar import Litestar
   from litestar_flags import FeatureFlagsConfig, FeatureFlagsPlugin

   config = FeatureFlagsConfig(
       backend="memory",
       enable_environment_middleware=True,
       environment_header="X-Environment",
       environment_query_param="env",
       default_environment="production",
       allowed_environments=["production", "staging", "development"],
   )

   app = Litestar(
       route_handlers=[...],
       plugins=[FeatureFlagsPlugin(config=config)],
   )

Requests are then processed with environment detection:

.. code-block:: text

   # Environment from header
   curl -H "X-Environment: staging" https://api.example.com/feature

   # Environment from query param
   curl "https://api.example.com/feature?env=development"

   # Falls back to default_environment
   curl https://api.example.com/feature


Accessing the Request Environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use ``get_request_environment()`` to retrieve the detected environment:

.. code-block:: python

   from litestar import get
   from litestar.connection import Request
   from litestar_flags import get_request_environment

   @get("/debug")
   async def debug_environment(request: Request) -> dict:
       environment = get_request_environment(request.scope)
       return {"current_environment": environment}


Usage Examples
--------------

Creating Environments with Inheritance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create a hierarchical environment structure where staging inherits from
production, and development inherits from staging:

.. code-block:: python

   from litestar_flags.models.environment import Environment

   # Create the root production environment
   production = Environment(
       name="Production",
       slug="production",
       description="Live production environment",
       settings={"require_approval": True},
   )
   production = await storage.create_environment(production)

   # Create staging that inherits from production
   staging = Environment(
       name="Staging",
       slug="staging",
       description="Pre-production testing environment",
       parent_id=production.id,
       settings={"require_approval": False},
   )
   staging = await storage.create_environment(staging)

   # Create development that inherits from staging
   development = Environment(
       name="Development",
       slug="development",
       description="Local development environment",
       parent_id=staging.id,
       settings={"debug_mode": True},
   )
   development = await storage.create_environment(development)


Setting Per-Environment Flag Values
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Override flag configurations for specific environments:

.. code-block:: python

   from litestar_flags.models.environment_flag import EnvironmentFlag

   # Get the base flag
   flag = await storage.get_flag("new-checkout-flow")

   # Enable with 100% rollout in staging for testing
   staging_override = EnvironmentFlag(
       environment_id=staging.id,
       flag_id=flag.id,
       enabled=True,
       percentage=100.0,
   )
   await storage.create_environment_flag(staging_override)

   # Enable with 10% rollout in production for gradual release
   production_override = EnvironmentFlag(
       environment_id=production.id,
       flag_id=flag.id,
       enabled=True,
       percentage=10.0,
   )
   await storage.create_environment_flag(production_override)

   # Development inherits from staging (no override needed)
   # It will automatically get 100% rollout


Evaluating Flags in Environment Context
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``EnvironmentResolver`` handles flag evaluation with environment overrides:

.. code-block:: python

   from litestar_flags.environment import EnvironmentResolver

   # Create a resolver with your storage backend
   resolver = EnvironmentResolver(storage)

   # Get the base flag
   base_flag = await storage.get_flag("new-checkout-flow")

   # Resolve for staging environment
   staging_flag = await resolver.resolve_flag_for_environment(
       flag=base_flag,
       environment_slug="staging",
   )
   print(f"Staging rollout: {staging_flag.default_enabled}")  # True

   # Resolve for production environment
   production_flag = await resolver.resolve_flag_for_environment(
       flag=base_flag,
       environment_slug="production",
   )
   print(f"Production rollout: {production_flag.default_enabled}")  # True (10%)


Getting the Environment Inheritance Chain
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Inspect the inheritance chain for debugging:

.. code-block:: python

   from litestar_flags.environment import EnvironmentResolver

   resolver = EnvironmentResolver(storage)

   # Get the full inheritance chain for development
   chain = await resolver.get_environment_chain("development")

   for env in chain:
       print(f"  {env.slug}: {env.name}")
   # Output:
   #   development: Development
   #   staging: Staging
   #   production: Production


Promoting Flags Between Environments
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Manually copy flag configuration from one environment to another:

.. code-block:: python

   async def promote_flag(
       storage,
       flag_key: str,
       from_env: str,
       to_env: str,
   ) -> None:
       """Promote a flag configuration from one environment to another."""
       # Get the source and target environments
       source = await storage.get_environment(from_env)
       target = await storage.get_environment(to_env)

       # Get the flag
       flag = await storage.get_flag(flag_key)

       # Get the source environment's override
       source_override = await storage.get_environment_flag(
           env_id=source.id,
           flag_id=flag.id,
       )

       if source_override is None:
           raise ValueError(f"No override for {flag_key} in {from_env}")

       # Check if target already has an override
       existing = await storage.get_environment_flag(
           env_id=target.id,
           flag_id=flag.id,
       )

       if existing:
           # Update existing override
           existing.enabled = source_override.enabled
           existing.percentage = source_override.percentage
           existing.rules = source_override.rules
           existing.variants = source_override.variants
           await storage.update_environment_flag(existing)
       else:
           # Create new override
           new_override = EnvironmentFlag(
               environment_id=target.id,
               flag_id=flag.id,
               enabled=source_override.enabled,
               percentage=source_override.percentage,
               rules=source_override.rules,
               variants=source_override.variants,
           )
           await storage.create_environment_flag(new_override)

   # Example: Promote from staging to production
   await promote_flag(storage, "new-checkout-flow", "staging", "production")


API Reference
-------------

EnvironmentResolver Methods
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. py:class:: EnvironmentResolver(storage)

   Resolves feature flags with environment-specific overrides.

   .. py:method:: get_environment(slug) -> Environment | None
      :async:

      Get an environment by slug.

      :param slug: The unique URL-safe identifier for the environment.
      :returns: The Environment if found, None otherwise.

   .. py:method:: get_environment_chain(slug) -> list[Environment]
      :async:

      Get the inheritance chain for an environment from child to root.

      Walks the parent chain starting from the specified environment up to
      the root (an environment with no parent).

      :param slug: The slug of the environment to start from.
      :returns: List of environments ordered from child (most specific) to
                root (least specific).
      :raises CircularEnvironmentInheritanceError: If a circular reference is
              detected in the inheritance chain.

   .. py:method:: get_effective_environment_flag(flag_id, environment_slug) -> EnvironmentFlag | None
      :async:

      Get the effective environment flag by walking the inheritance chain.

      Returns the first EnvironmentFlag override found in the chain.

      :param flag_id: The UUID of the feature flag.
      :param environment_slug: The slug of the environment to start from.
      :returns: The first EnvironmentFlag found, or None if no override exists.
      :raises CircularEnvironmentInheritanceError: If a circular reference is
              detected.

   .. py:method:: resolve_flag_for_environment(flag, environment_slug) -> FeatureFlag
      :async:

      Resolve a flag with environment overrides applied.

      :param flag: The base feature flag to resolve.
      :param environment_slug: The slug of the environment to resolve for.
      :returns: A new FeatureFlag instance with environment overrides applied.
      :raises CircularEnvironmentInheritanceError: If a circular reference is
              detected.


Storage Backend Environment Methods
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``StorageBackend`` protocol includes the following environment-related methods:

**Environment Management:**

- ``get_environment(slug)`` - Retrieve an environment by slug
- ``get_environment_by_id(env_id)`` - Retrieve an environment by UUID
- ``get_all_environments()`` - Retrieve all environments
- ``get_child_environments(parent_id)`` - Get child environments of a parent
- ``create_environment(env)`` - Create a new environment
- ``update_environment(env)`` - Update an existing environment
- ``delete_environment(slug)`` - Delete an environment by slug

**EnvironmentFlag Management:**

- ``get_environment_flag(env_id, flag_id)`` - Get specific environment-flag config
- ``get_environment_flags(env_id)`` - Get all flag configs for an environment
- ``get_flag_environments(flag_id)`` - Get all environment configs for a flag
- ``create_environment_flag(env_flag)`` - Create environment-specific override
- ``update_environment_flag(env_flag)`` - Update environment-specific override
- ``delete_environment_flag(env_id, flag_id)`` - Delete environment override


Exception Classes
~~~~~~~~~~~~~~~~~

.. py:exception:: CircularEnvironmentInheritanceError

   Raised when circular environment inheritance is detected.

   This error occurs when traversing the environment inheritance chain and
   an environment references itself either directly or through a chain of
   parent environments.

   .. py:attribute:: environment_slug
      :type: str

      The slug of the environment where the cycle was detected.

   .. py:attribute:: visited_chain
      :type: list[str]

      The list of environment slugs in the order they were visited.


Best Practices
--------------

Environment Naming Conventions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use consistent, descriptive slugs for your environments:

- Use lowercase letters, numbers, hyphens, and underscores
- Start with a letter or number
- Keep names short but descriptive
- Use a consistent prefix for related environments

.. code-block:: text

   Good:
   - production, staging, development
   - prod, stage, dev
   - us-east, us-west, eu-central
   - feature-checkout, feature-payment

   Avoid:
   - PRODUCTION (use lowercase)
   - my production env (no spaces)
   - -staging (don't start with hyphen)


Inheritance Patterns
~~~~~~~~~~~~~~~~~~~~

**Linear Pipeline (Recommended for most teams):**

.. code-block:: text

   production
       |
       +-- staging
               |
               +-- development

All changes flow through the pipeline, with each environment inheriting from
its more production-like parent.

**Feature Branch Pattern:**

.. code-block:: text

   staging
       |
       +-- feature-xyz
       |
       +-- feature-abc

Feature branches inherit from staging to get baseline behavior while allowing
isolated testing.

**Regional Pattern:**

.. code-block:: text

   global
       |
       +-- us
       |       +-- us-east
       |       +-- us-west
       |
       +-- eu
               +-- eu-central
               +-- eu-west

Regional environments inherit global defaults while allowing geo-specific
overrides.


Promotion Workflows
~~~~~~~~~~~~~~~~~~~

Follow a consistent process for promoting flag configurations:

1. **Test in development** - Verify flag behavior with development overrides
2. **Validate in staging** - Test with production-like data and load
3. **Gradual production rollout** - Start with low percentage, increase over time
4. **Monitor and iterate** - Watch metrics before increasing rollout

Example promotion flow:

.. code-block:: python

   # 1. Enable 100% in development for testing
   await set_environment_flag("new-feature", "development", enabled=True, percentage=100)

   # 2. After dev testing, enable in staging
   await set_environment_flag("new-feature", "staging", enabled=True, percentage=100)

   # 3. After staging validation, gradual production rollout
   await set_environment_flag("new-feature", "production", enabled=True, percentage=5)
   # ... monitor metrics ...
   await set_environment_flag("new-feature", "production", percentage=25)
   # ... monitor metrics ...
   await set_environment_flag("new-feature", "production", percentage=100)


Security Considerations
~~~~~~~~~~~~~~~~~~~~~~~

- **Restrict environment headers in production** - Use ``allowed_environments``
  to prevent arbitrary environment injection
- **Disable query param detection in production** - Set ``environment_query_param=None``
  to prevent environment override via URL
- **Audit environment changes** - Log all environment and environment flag modifications
- **Use separate credentials** - Different database/Redis credentials per environment

.. code-block:: python

   # Production-safe configuration
   config = FeatureFlagsConfig(
       backend="database",
       connection_string=os.environ["DATABASE_URL"],

       # Lock down environment detection
       default_environment="production",
       enable_environment_middleware=True,
       environment_header="X-Environment",
       environment_query_param=None,  # Disable query param in production
       allowed_environments=["production"],  # Only allow production
   )
