Multi-Environment Configuration
===============================

This guide covers practical steps for setting up and managing feature flags
across multiple deployment environments.

.. seealso::

   For detailed API reference and conceptual overview, see
   :doc:`/user-guide/multi-environment`.


Setting Up Environment Hierarchy
--------------------------------

Create a standard dev/staging/production pipeline:

.. code-block:: python

   from litestar_flags.models.environment import Environment

   async def setup_environments(storage) -> None:
       """Create standard environment hierarchy."""
       # Root: Production (no parent)
       production = await storage.create_environment(
           Environment(
               name="Production",
               slug="production",
               description="Live production environment",
               settings={"require_approval": True},
           )
       )

       # Staging inherits from production
       staging = await storage.create_environment(
           Environment(
               name="Staging",
               slug="staging",
               parent_id=production.id,
               settings={"require_approval": False},
           )
       )

       # Development inherits from staging
       await storage.create_environment(
           Environment(
               name="Development",
               slug="development",
               parent_id=staging.id,
               settings={"debug_mode": True},
           )
       )


Configuring Environment Detection
---------------------------------

Enable automatic environment detection from HTTP requests:

.. code-block:: python

   from litestar import Litestar
   from litestar_flags import FeatureFlagsConfig, FeatureFlagsPlugin

   config = FeatureFlagsConfig(
       backend="database",
       connection_string="postgresql+asyncpg://user:pass@localhost/db",

       # Environment detection
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

**Request examples:**

.. code-block:: bash

   # Via header
   curl -H "X-Environment: staging" https://api.example.com/feature

   # Via query param
   curl "https://api.example.com/feature?env=development"

   # Falls back to default
   curl https://api.example.com/feature


Creating Environment-Specific Overrides
---------------------------------------

Override flag values for specific environments:

.. code-block:: python

   from litestar_flags.models.environment_flag import EnvironmentFlag

   async def configure_flag_per_environment(storage, flag_key: str) -> None:
       """Set different rollout percentages per environment."""
       flag = await storage.get_flag(flag_key)
       staging = await storage.get_environment("staging")
       production = await storage.get_environment("production")

       # 100% in staging for full testing
       await storage.create_environment_flag(
           EnvironmentFlag(
               environment_id=staging.id,
               flag_id=flag.id,
               enabled=True,
               percentage=100.0,
           )
       )

       # 10% gradual rollout in production
       await storage.create_environment_flag(
           EnvironmentFlag(
               environment_id=production.id,
               flag_id=flag.id,
               enabled=True,
               percentage=10.0,
           )
       )

       # Development inherits staging's 100% (no override needed)


Evaluating Flags with Environment Context
-----------------------------------------

Use the resolver to get environment-specific flag values:

.. code-block:: python

   from litestar_flags.environment import EnvironmentResolver

   async def check_flag_per_environment(storage, flag_key: str) -> None:
       """Demonstrate environment-aware flag evaluation."""
       resolver = EnvironmentResolver(storage)
       base_flag = await storage.get_flag(flag_key)

       # Each environment gets its resolved configuration
       for env_slug in ["production", "staging", "development"]:
           resolved = await resolver.resolve_flag_for_environment(
               flag=base_flag,
               environment_slug=env_slug,
           )
           print(f"{env_slug}: enabled={resolved.default_enabled}")


Promoting Flags Between Environments
------------------------------------

Copy flag configuration from one environment to another:

.. code-block:: python

   from litestar_flags.models.environment_flag import EnvironmentFlag

   async def promote_flag(
       storage,
       flag_key: str,
       from_env: str,
       to_env: str,
   ) -> None:
       """Promote flag configuration between environments."""
       source = await storage.get_environment(from_env)
       target = await storage.get_environment(to_env)
       flag = await storage.get_flag(flag_key)

       source_override = await storage.get_environment_flag(
           env_id=source.id,
           flag_id=flag.id,
       )
       if not source_override:
           raise ValueError(f"No override for {flag_key} in {from_env}")

       existing = await storage.get_environment_flag(
           env_id=target.id,
           flag_id=flag.id,
       )

       if existing:
           existing.enabled = source_override.enabled
           existing.percentage = source_override.percentage
           existing.rules = source_override.rules
           await storage.update_environment_flag(existing)
       else:
           await storage.create_environment_flag(
               EnvironmentFlag(
                   environment_id=target.id,
                   flag_id=flag.id,
                   enabled=source_override.enabled,
                   percentage=source_override.percentage,
                   rules=source_override.rules,
               )
           )

   # Usage: promote from staging to production
   await promote_flag(storage, "new-checkout", "staging", "production")


Accessing Environment in Route Handlers
---------------------------------------

Get the detected environment within your handlers:

.. code-block:: python

   from litestar import get
   from litestar.connection import Request
   from litestar_flags import get_request_environment

   @get("/debug/environment")
   async def debug_environment(request: Request) -> dict:
       """Return the current request environment."""
       environment = get_request_environment(request.scope)
       return {"environment": environment}


Inspecting the Inheritance Chain
--------------------------------

Debug which environment provides a flag's value:

.. code-block:: python

   from litestar_flags.environment import EnvironmentResolver

   async def debug_inheritance(storage, env_slug: str) -> None:
       """Print the inheritance chain for an environment."""
       resolver = EnvironmentResolver(storage)
       chain = await resolver.get_environment_chain(env_slug)

       print(f"Inheritance chain for '{env_slug}':")
       for env in chain:
           print(f"  -> {env.slug} ({env.name})")

   # Example output for "development":
   #   -> development (Development)
   #   -> staging (Staging)
   #   -> production (Production)


Production Security Configuration
---------------------------------

Lock down environment detection in production:

.. code-block:: python

   import os
   from litestar_flags import FeatureFlagsConfig

   config = FeatureFlagsConfig(
       backend="database",
       connection_string=os.environ["DATABASE_URL"],

       # Strict production settings
       default_environment="production",
       enable_environment_middleware=True,
       environment_header="X-Environment",
       environment_query_param=None,  # Disable query param
       allowed_environments=["production"],  # Only allow production
   )


Gradual Rollout Workflow
------------------------

Standard pattern for releasing a feature across environments:

.. code-block:: python

   # Step 1: Enable 100% in development
   await storage.create_environment_flag(
       EnvironmentFlag(environment_id=dev.id, flag_id=flag.id, percentage=100)
   )
   # Test thoroughly...

   # Step 2: Enable 100% in staging
   await storage.create_environment_flag(
       EnvironmentFlag(environment_id=staging.id, flag_id=flag.id, percentage=100)
   )
   # Validate with production-like data...

   # Step 3: Gradual production rollout
   prod_flag = EnvironmentFlag(
       environment_id=production.id, flag_id=flag.id, enabled=True, percentage=5
   )
   await storage.create_environment_flag(prod_flag)
   # Monitor metrics, then increase...

   prod_flag.percentage = 25
   await storage.update_environment_flag(prod_flag)
   # Monitor, then continue to 100%...
