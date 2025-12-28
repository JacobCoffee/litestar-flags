Exceptions
==========

Custom exceptions for the litestar-flags library. These exceptions provide
structured error handling for common failure scenarios.

Overview
--------

The library uses a hierarchy of exceptions:

.. code-block:: text

   Exception
   └── FeatureFlagError (base exception)
       ├── FlagNotFoundError
       ├── StorageError
       └── ConfigurationError


.. note::

   The ``FeatureFlagClient`` is designed to **never throw exceptions** during
   normal flag evaluation. Instead, it returns default values and includes
   error information in the ``EvaluationDetails``. These exceptions are
   primarily raised during configuration, storage operations, or direct
   storage backend usage.


API Reference
-------------

.. automodule:: litestar_flags.exceptions
   :members:
   :undoc-members:
   :show-inheritance:


FeatureFlagError
----------------

Base exception for all feature flag errors.

.. code-block:: python

   from litestar_flags.exceptions import FeatureFlagError

   try:
       # Some operation that might fail
       await storage.create_flag(flag)
   except FeatureFlagError as e:
       # Catch any feature flag related error
       logger.error(f"Feature flag error: {e}")


FlagNotFoundError
-----------------

Raised when attempting to access a flag that does not exist.

.. code-block:: python

   from litestar_flags.exceptions import FlagNotFoundError

   try:
       # Direct storage access (not via client)
       flag = await storage.get_flag("non-existent")
       if flag is None:
           raise FlagNotFoundError("non-existent")
   except FlagNotFoundError as e:
       print(f"Flag key: {e.key}")  # Access the flag key
       print(f"Message: {e}")       # "Feature flag 'non-existent' not found"


Attributes
~~~~~~~~~~

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Attribute
     - Description
   * - ``key``
     - The flag key that was not found


StorageError
------------

Raised when a storage backend operation fails.

.. code-block:: python

   from litestar_flags.exceptions import StorageError

   try:
       await storage.create_flag(flag)
   except StorageError as e:
       logger.error(f"Storage operation failed: {e}")
       # Handle storage failure (retry, fallback, etc.)


Common Causes
~~~~~~~~~~~~~

- Database connection failures
- Redis connection timeouts
- Constraint violations (e.g., duplicate flag key)
- Permission denied errors


ConfigurationError
------------------

Raised when the configuration is invalid.

.. code-block:: python

   from litestar_flags import FeatureFlagsConfig
   from litestar_flags.exceptions import ConfigurationError

   try:
       # This will raise ConfigurationError
       config = FeatureFlagsConfig(
           backend="database",
           # Missing required connection_string
       )
   except ConfigurationError as e:
       print(f"Invalid configuration: {e}")


Common Causes
~~~~~~~~~~~~~

- Missing required configuration (e.g., ``connection_string`` for database backend)
- Invalid backend type
- Incompatible configuration combinations


Error Handling Patterns
-----------------------

Graceful Degradation
~~~~~~~~~~~~~~~~~~~~

The recommended pattern is to use the client's built-in error handling:

.. code-block:: python

   from litestar_flags import FeatureFlagClient

   # Client never throws during evaluation
   enabled = await client.get_boolean_value("my-feature", default=False)

   # Check for errors in details
   details = await client.get_boolean_details("my-feature", default=False)
   if details.is_error:
       logger.warning(f"Flag evaluation error: {details.error_message}")
       # Value will be the default


Storage Operations
~~~~~~~~~~~~~~~~~~

For direct storage operations, catch specific exceptions:

.. code-block:: python

   from litestar_flags.exceptions import (
       FeatureFlagError,
       FlagNotFoundError,
       StorageError,
   )

   async def safe_create_flag(storage, flag):
       try:
           return await storage.create_flag(flag)
       except StorageError as e:
           logger.error(f"Failed to create flag: {e}")
           raise
       except FeatureFlagError as e:
           logger.error(f"Unexpected error: {e}")
           raise


Configuration Validation
~~~~~~~~~~~~~~~~~~~~~~~~

Validate configuration early in application startup:

.. code-block:: python

   from litestar_flags import FeatureFlagsConfig
   from litestar_flags.exceptions import ConfigurationError

   def get_config():
       try:
           return FeatureFlagsConfig(
               backend=os.environ.get("FF_BACKEND", "memory"),
               connection_string=os.environ.get("FF_DATABASE_URL"),
               redis_url=os.environ.get("FF_REDIS_URL"),
           )
       except ConfigurationError as e:
           logger.critical(f"Invalid feature flag configuration: {e}")
           raise SystemExit(1)


Integration with Litestar
-------------------------

Custom Exception Handlers
~~~~~~~~~~~~~~~~~~~~~~~~~

You can register custom exception handlers for feature flag errors:

.. code-block:: python

   from litestar import Litestar, Response
   from litestar.exceptions import HTTPException
   from litestar_flags.exceptions import FeatureFlagError

   def feature_flag_exception_handler(
       request,
       exc: FeatureFlagError,
   ) -> Response:
       return Response(
           content={"error": "Feature flag system error"},
           status_code=500,
       )

   app = Litestar(
       exception_handlers={
           FeatureFlagError: feature_flag_exception_handler,
       },
   )


Health Check Endpoints
~~~~~~~~~~~~~~~~~~~~~~

Use health checks to detect storage issues:

.. code-block:: python

   from litestar import get
   from litestar_flags import FeatureFlagClient

   @get("/health/flags")
   async def feature_flags_health(feature_flags: FeatureFlagClient) -> dict:
       healthy = await feature_flags.health_check()
       return {
           "status": "healthy" if healthy else "unhealthy",
           "service": "feature_flags",
       }
