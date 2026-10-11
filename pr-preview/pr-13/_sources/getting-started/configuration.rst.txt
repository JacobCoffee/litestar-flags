Configuration
=============

litestar-flags provides flexible configuration options through the
``FeatureFlagsConfig`` class.


Basic Configuration
-------------------

.. code-block:: python

   from litestar_flags import FeatureFlagsConfig, FeatureFlagsPlugin

   config = FeatureFlagsConfig(
       # Default flag values when not found
       default_enabled=False,
       # Enable debug logging
       debug=False,
   )

   plugin = FeatureFlagsPlugin(config=config)


Storage Backend Configuration
-----------------------------

Memory Backend (Default)
~~~~~~~~~~~~~~~~~~~~~~~~

The in-memory backend is the default and requires no additional configuration:

.. code-block:: python

   from litestar_flags import FeatureFlagsConfig
   from litestar_flags.storage import MemoryStorageBackend

   config = FeatureFlagsConfig(
       storage_backend=MemoryStorageBackend(),
   )

Redis Backend
~~~~~~~~~~~~~

For distributed deployments:

.. code-block:: python

   from litestar_flags import FeatureFlagsConfig
   from litestar_flags.storage import RedisStorageBackend

   config = FeatureFlagsConfig(
       storage_backend=RedisStorageBackend(
           url="redis://localhost:6379/0",
           prefix="feature_flags:",
       ),
   )

Database Backend
~~~~~~~~~~~~~~~~

For persistent storage:

.. code-block:: python

   from litestar_flags import FeatureFlagsConfig
   from litestar_flags.storage import DatabaseStorageBackend

   config = FeatureFlagsConfig(
       storage_backend=DatabaseStorageBackend(
           connection_string="postgresql+asyncpg://user:pass@localhost/db",
       ),
   )


Environment Variables
---------------------

You can also configure litestar-flags using environment variables:

.. code-block:: bash

   export FEATURE_FLAGS_DEBUG=true
   export FEATURE_FLAGS_DEFAULT_ENABLED=false
   export FEATURE_FLAGS_REDIS_URL=redis://localhost:6379/0


Configuration Reference
-----------------------

See the :class:`~litestar_flags.FeatureFlagsConfig` API documentation for
a complete list of configuration options.
