Storage Backends
================

litestar-flags supports multiple storage backends for different deployment
scenarios.


Memory Backend
--------------

The ``MemoryStorageBackend`` stores flags in memory. This is the default
backend and is ideal for:

- Development and testing
- Single-instance deployments
- Prototyping

.. warning::

   Flags stored in memory are lost when the application restarts.

.. code-block:: python

   from litestar_flags import FeatureFlagsConfig
   from litestar_flags.storage import MemoryStorageBackend

   config = FeatureFlagsConfig(
       storage_backend=MemoryStorageBackend(),
   )


Redis Backend
-------------

The ``RedisStorageBackend`` stores flags in Redis, enabling:

- Distributed flag storage across multiple instances
- Flag persistence across restarts
- Real-time flag synchronization

Requirements
~~~~~~~~~~~~

Install the Redis extra:

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

Configuration
~~~~~~~~~~~~~

.. code-block:: python

   from litestar_flags import FeatureFlagsConfig
   from litestar_flags.storage import RedisStorageBackend

   backend = RedisStorageBackend(
       url="redis://localhost:6379/0",
       prefix="myapp:flags:",  # Key prefix for namespacing
   )

   config = FeatureFlagsConfig(storage_backend=backend)


Database Backend
----------------

The ``DatabaseStorageBackend`` provides persistent storage using SQLAlchemy,
supporting:

- PostgreSQL, MySQL, SQLite, and other databases
- Full ACID compliance
- Integration with existing database infrastructure

Requirements
~~~~~~~~~~~~

Install the database extra:

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

Configuration
~~~~~~~~~~~~~

.. code-block:: python

   from litestar_flags import FeatureFlagsConfig
   from litestar_flags.storage import DatabaseStorageBackend

   backend = DatabaseStorageBackend(
       connection_string="postgresql+asyncpg://user:pass@localhost/mydb",
   )

   config = FeatureFlagsConfig(storage_backend=backend)


Choosing a Backend
------------------

+------------------+-------------+-------------+---------------+
| Feature          | Memory      | Redis       | Database      |
+==================+=============+=============+===============+
| Persistence      | No          | Yes         | Yes           |
+------------------+-------------+-------------+---------------+
| Multi-instance   | No          | Yes         | Yes           |
+------------------+-------------+-------------+---------------+
| Real-time sync   | N/A         | Yes         | No            |
+------------------+-------------+-------------+---------------+
| Setup complexity | None        | Low         | Medium        |
+------------------+-------------+-------------+---------------+
| Best for         | Development | Production  | Production    |
+------------------+-------------+-------------+---------------+


Custom Backends
---------------

You can create custom storage backends by implementing the ``StorageBackend``
abstract base class:

.. code-block:: python

   from litestar_flags.storage import StorageBackend
   from litestar_flags import FeatureFlag

   class MyCustomBackend(StorageBackend):
       async def get(self, name: str) -> FeatureFlag | None:
           # Implement flag retrieval
           ...

       async def set(self, flag: FeatureFlag) -> None:
           # Implement flag storage
           ...

       async def delete(self, name: str) -> None:
           # Implement flag deletion
           ...

       async def list(self) -> list[FeatureFlag]:
           # Implement listing all flags
           ...
