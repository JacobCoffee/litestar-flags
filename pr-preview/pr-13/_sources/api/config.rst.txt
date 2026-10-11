Configuration
=============

The ``FeatureFlagsConfig`` dataclass provides configuration options for the
feature flags plugin, including storage backend selection and middleware settings.

Overview
--------

Configuration is passed to the ``FeatureFlagsPlugin`` on initialization and
controls:

- Which storage backend to use (memory, database, or Redis)
- Connection settings for external backends
- Default evaluation context
- Middleware and context extraction settings
- Dependency injection key for the client

Quick Example
-------------

.. code-block:: python

   from litestar import Litestar
   from litestar_flags import FeatureFlagsPlugin, FeatureFlagsConfig

   # Simple in-memory configuration
   config = FeatureFlagsConfig(backend="memory")

   # Database configuration
   config = FeatureFlagsConfig(
       backend="database",
       connection_string="postgresql+asyncpg://user:pass@localhost/db",
   )

   # Redis configuration
   config = FeatureFlagsConfig(
       backend="redis",
       redis_url="redis://localhost:6379",
   )

   app = Litestar(
       plugins=[FeatureFlagsPlugin(config=config)],
   )


API Reference
-------------

.. automodule:: litestar_flags.config
   :members:
   :undoc-members:
   :show-inheritance:


Configuration Options
---------------------

Backend Selection
~~~~~~~~~~~~~~~~~

The ``backend`` parameter accepts one of three values:

- ``"memory"``: In-memory storage (default). No persistence, ideal for development.
- ``"database"``: SQLAlchemy-based persistent storage. Requires ``connection_string``.
- ``"redis"``: Redis-based distributed storage. Requires ``redis_url``.

.. code-block:: python

   # Memory backend (default)
   config = FeatureFlagsConfig(backend="memory")

   # Database backend
   config = FeatureFlagsConfig(
       backend="database",
       connection_string="postgresql+asyncpg://user:pass@localhost/db",
       table_prefix="ff_",  # Optional table prefix
   )

   # Redis backend
   config = FeatureFlagsConfig(
       backend="redis",
       redis_url="redis://localhost:6379/0",
       redis_prefix="feature_flags:",  # Optional key prefix
   )


Database Settings
~~~~~~~~~~~~~~~~~

When using ``backend="database"``:

.. list-table::
   :widths: 25 15 60
   :header-rows: 1

   * - Parameter
     - Required
     - Description
   * - ``connection_string``
     - Yes
     - SQLAlchemy async connection string
   * - ``table_prefix``
     - No
     - Prefix for database table names (default: ``"ff_"``)


.. code-block:: python

   config = FeatureFlagsConfig(
       backend="database",
       connection_string="postgresql+asyncpg://user:pass@localhost/mydb",
       table_prefix="feature_flags_",
   )


Redis Settings
~~~~~~~~~~~~~~

When using ``backend="redis"``:

.. list-table::
   :widths: 25 15 60
   :header-rows: 1

   * - Parameter
     - Required
     - Description
   * - ``redis_url``
     - Yes
     - Redis connection URL
   * - ``redis_prefix``
     - No
     - Prefix for Redis keys (default: ``"feature_flags:"``)


.. code-block:: python

   config = FeatureFlagsConfig(
       backend="redis",
       redis_url="redis://:password@localhost:6379/0",
       redis_prefix="myapp:flags:",
   )


Middleware Configuration
~~~~~~~~~~~~~~~~~~~~~~~~

Enable automatic context extraction from requests:

.. code-block:: python

   from litestar_flags import FeatureFlagsConfig, EvaluationContext

   def my_context_extractor(request) -> EvaluationContext:
       """Extract evaluation context from the request."""
       user_id = None
       if hasattr(request, "user") and request.user:
           user_id = str(request.user.id)

       return EvaluationContext(
           targeting_key=user_id,
           user_id=user_id,
           ip_address=request.client.host if request.client else None,
       )

   config = FeatureFlagsConfig(
       backend="memory",
       enable_middleware=True,
       context_extractor=my_context_extractor,
   )


Default Context
~~~~~~~~~~~~~~~

Set a default evaluation context that applies to all evaluations:

.. code-block:: python

   from litestar_flags import FeatureFlagsConfig, EvaluationContext

   config = FeatureFlagsConfig(
       backend="memory",
       default_context=EvaluationContext(
           environment="production",
           app_version="2.1.0",
       ),
   )


Dependency Key
~~~~~~~~~~~~~~

Customize the dependency injection key for the client:

.. code-block:: python

   config = FeatureFlagsConfig(
       backend="memory",
       client_dependency_key="flags",  # Default is "feature_flags"
   )

   # In your route handler:
   @get("/")
   async def handler(flags: FeatureFlagClient) -> dict:
       # Use 'flags' instead of 'feature_flags'
       pass


Plugin Reference
----------------

.. automodule:: litestar_flags.plugin
   :members:
   :undoc-members:
   :show-inheritance:


Plugin Usage
------------

Basic Setup
~~~~~~~~~~~

.. code-block:: python

   from litestar import Litestar, get
   from litestar_flags import (
       FeatureFlagsPlugin,
       FeatureFlagsConfig,
       FeatureFlagClient,
   )

   config = FeatureFlagsConfig(backend="memory")
   plugin = FeatureFlagsPlugin(config=config)

   @get("/")
   async def handler(feature_flags: FeatureFlagClient) -> dict:
       enabled = await feature_flags.get_boolean_value("my-feature")
       return {"enabled": enabled}

   app = Litestar(
       route_handlers=[handler],
       plugins=[plugin],
   )


Accessing the Client
~~~~~~~~~~~~~~~~~~~~

The client is available in three ways:

1. **Dependency Injection** (recommended):

   .. code-block:: python

      @get("/")
      async def handler(feature_flags: FeatureFlagClient) -> dict:
          enabled = await feature_flags.is_enabled("my-feature")
          return {"enabled": enabled}

2. **From Application State**:

   .. code-block:: python

      @get("/")
      async def handler(request: Request) -> dict:
          client = request.app.state.feature_flags
          enabled = await client.is_enabled("my-feature")
          return {"enabled": enabled}

3. **From Plugin Instance**:

   .. code-block:: python

      plugin = FeatureFlagsPlugin(config=config)
      # After app startup:
      client = plugin.client
