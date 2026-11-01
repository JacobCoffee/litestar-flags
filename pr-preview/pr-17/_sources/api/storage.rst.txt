Storage Backends
================

Storage backends provide persistence for feature flags. The library includes
three built-in backends with different characteristics and use cases.

Overview
--------

All storage backends implement the ``StorageBackend`` protocol, ensuring a
consistent interface regardless of the underlying storage mechanism.

Available Backends:

.. list-table::
   :widths: 20 30 50
   :header-rows: 1

   * - Backend
     - Use Case
     - Requirements
   * - ``MemoryStorageBackend``
     - Development, testing, single-instance
     - None (built-in)
   * - ``DatabaseStorageBackend``
     - Production with SQL database
     - ``litestar-flags[database]``
   * - ``RedisStorageBackend``
     - Distributed deployments
     - ``litestar-flags[redis]``


StorageBackend Protocol
-----------------------

All backends implement this protocol:

.. automodule:: litestar_flags.protocols
   :members:
   :undoc-members:
   :show-inheritance:


MemoryStorageBackend
--------------------

In-memory storage for development and testing. Data is not persisted between
application restarts.

.. automodule:: litestar_flags.storage.memory
   :members:
   :undoc-members:
   :show-inheritance:


Usage
~~~~~

.. code-block:: python

   from litestar_flags import MemoryStorageBackend, FeatureFlagClient

   # Create storage
   storage = MemoryStorageBackend()

   # Create client
   client = FeatureFlagClient(storage=storage)

   # Or via plugin configuration
   from litestar_flags import FeatureFlagsConfig

   config = FeatureFlagsConfig(backend="memory")


When to Use
~~~~~~~~~~~

- Local development
- Unit and integration testing
- Simple single-instance deployments
- Prototyping and experimentation


DatabaseStorageBackend
----------------------

SQLAlchemy-based persistent storage using Advanced-Alchemy. Supports PostgreSQL,
MySQL, SQLite, and other SQLAlchemy-compatible databases.

.. automodule:: litestar_flags.storage.database
   :members:
   :undoc-members:
   :show-inheritance:


Installation
~~~~~~~~~~~~

.. tab-set::
   :sync-group: package-manager

   .. tab-item:: uv (Recommended)
      :sync: uv

      .. code-block:: bash

         uv add litestar-flags[database]

   .. tab-item:: pip
      :sync: pip

      .. code-block:: bash

         pip install litestar-flags[database]


Usage
~~~~~

.. code-block:: python

   from litestar_flags import FeatureFlagsConfig

   # PostgreSQL
   config = FeatureFlagsConfig(
       backend="database",
       connection_string="postgresql+asyncpg://user:pass@localhost/mydb",
   )

   # MySQL
   config = FeatureFlagsConfig(
       backend="database",
       connection_string="mysql+aiomysql://user:pass@localhost/mydb",
   )

   # SQLite (for development)
   config = FeatureFlagsConfig(
       backend="database",
       connection_string="sqlite+aiosqlite:///flags.db",
   )


Direct Usage
~~~~~~~~~~~~

For advanced use cases, you can create the backend directly:

.. code-block:: python

   from litestar_flags.storage.database import DatabaseStorageBackend

   storage = await DatabaseStorageBackend.create(
       connection_string="postgresql+asyncpg://user:pass@localhost/mydb",
       table_prefix="ff_",
       create_tables=True,  # Auto-create tables on startup
   )

   # Use with client
   client = FeatureFlagClient(storage=storage)

   # Don't forget to close when done
   await storage.close()


When to Use
~~~~~~~~~~~

- Production deployments requiring persistence
- Multi-instance deployments with shared database
- When you need transactional consistency
- Integration with existing database infrastructure


RedisStorageBackend
-------------------

Redis-based distributed storage for high-performance, distributed deployments.

.. automodule:: litestar_flags.storage.redis
   :members:
   :undoc-members:
   :show-inheritance:


Installation
~~~~~~~~~~~~

.. tab-set::
   :sync-group: package-manager

   .. tab-item:: uv (Recommended)
      :sync: uv

      .. code-block:: bash

         uv add litestar-flags[redis]

   .. tab-item:: pip
      :sync: pip

      .. code-block:: bash

         pip install litestar-flags[redis]


Usage
~~~~~

.. code-block:: python

   from litestar_flags import FeatureFlagsConfig

   # Basic Redis
   config = FeatureFlagsConfig(
       backend="redis",
       redis_url="redis://localhost:6379/0",
   )

   # With authentication
   config = FeatureFlagsConfig(
       backend="redis",
       redis_url="redis://:password@localhost:6379/0",
       redis_prefix="myapp:flags:",  # Custom key prefix
   )

   # Redis Sentinel
   config = FeatureFlagsConfig(
       backend="redis",
       redis_url="redis+sentinel://sentinel1:26379,sentinel2:26379/mymaster/0",
   )


Direct Usage
~~~~~~~~~~~~

.. code-block:: python

   from litestar_flags.storage.redis import RedisStorageBackend

   storage = await RedisStorageBackend.create(
       url="redis://localhost:6379/0",
       prefix="feature_flags:",
   )

   client = FeatureFlagClient(storage=storage)

   # Close when done
   await storage.close()


Key Structure
~~~~~~~~~~~~~

Data is stored with the following key patterns:

- Flags: ``{prefix}flag:{key}``
- Overrides: ``{prefix}override:{flag_id}:{entity_type}:{entity_id}``
- Flag index: ``{prefix}flags`` (SET of all flag keys)


When to Use
~~~~~~~~~~~

- High-performance distributed deployments
- When you need fast reads across multiple instances
- Microservices architecture
- When database latency is a concern


Choosing a Backend
------------------

.. list-table::
   :widths: 25 25 25 25
   :header-rows: 1

   * - Criteria
     - Memory
     - Database
     - Redis
   * - Persistence
     - No
     - Yes
     - Yes (configurable)
   * - Multi-instance
     - No
     - Yes
     - Yes
   * - Performance
     - Fastest
     - Good
     - Very Fast
   * - Transactions
     - No
     - Yes
     - No
   * - Setup complexity
     - None
     - Medium
     - Low


Custom Storage Backends
-----------------------

You can implement custom storage backends by implementing the ``StorageBackend``
protocol:

.. code-block:: python

   from litestar_flags.protocols import StorageBackend
   from litestar_flags.models import FeatureFlag, FlagOverride
   from collections.abc import Sequence
   from uuid import UUID

   class MyCustomBackend:
       """Custom storage backend implementation."""

       async def get_flag(self, key: str) -> FeatureFlag | None:
           # Implement flag retrieval
           ...

       async def get_flags(self, keys: Sequence[str]) -> dict[str, FeatureFlag]:
           # Implement bulk retrieval
           ...

       async def get_all_active_flags(self) -> list[FeatureFlag]:
           # Implement active flags retrieval
           ...

       async def get_override(
           self,
           flag_id: UUID,
           entity_type: str,
           entity_id: str,
       ) -> FlagOverride | None:
           # Implement override retrieval
           ...

       async def create_flag(self, flag: FeatureFlag) -> FeatureFlag:
           # Implement flag creation
           ...

       async def update_flag(self, flag: FeatureFlag) -> FeatureFlag:
           # Implement flag update
           ...

       async def delete_flag(self, key: str) -> bool:
           # Implement flag deletion
           ...

       async def health_check(self) -> bool:
           # Implement health check
           return True

       async def close(self) -> None:
           # Clean up resources
           ...

   # Use with client
   storage = MyCustomBackend()
   client = FeatureFlagClient(storage=storage)
