Client
======

The ``FeatureFlagClient`` is the main interface for evaluating feature flags.
It provides type-safe methods for all flag types with automatic caching and
graceful degradation.

Overview
--------

The client is designed to **never throw exceptions** during flag evaluation.
Instead, it returns the default value and includes error information in the
evaluation details. This ensures your application remains stable even when
flag evaluation encounters issues.

Key Features:

- Type-safe evaluation methods for boolean, string, number, and object flags
- Detailed evaluation results with metadata
- Bulk evaluation for multiple flags
- Async context manager support
- Health check functionality

Quick Example
-------------

.. code-block:: python

   from litestar_flags import FeatureFlagClient, MemoryStorageBackend, EvaluationContext

   # Create a client with in-memory storage
   storage = MemoryStorageBackend()
   client = FeatureFlagClient(storage=storage)

   # Evaluate a boolean flag
   enabled = await client.get_boolean_value("my-feature", default=False)

   # Evaluate with context for targeting
   context = EvaluationContext(
       targeting_key="user-123",
       attributes={"plan": "premium"},
   )
   enabled = await client.get_boolean_value("premium-feature", context=context)

   # Get detailed evaluation information
   details = await client.get_boolean_details("my-feature", default=False)
   print(f"Value: {details.value}, Reason: {details.reason}")


API Reference
-------------

.. automodule:: litestar_flags.client
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource


Evaluation Methods
------------------

The client provides pairs of methods for each flag type:

- ``get_<type>_value()``: Returns just the evaluated value
- ``get_<type>_details()``: Returns the value wrapped in :class:`~litestar_flags.EvaluationDetails`

Boolean Flags
~~~~~~~~~~~~~

.. code-block:: python

   # Simple boolean check
   enabled = await client.get_boolean_value("feature-x", default=False)

   # With full details
   details = await client.get_boolean_details("feature-x", default=False)
   if details.is_error:
       logger.warning(f"Flag evaluation error: {details.error_message}")

   # Convenience method
   if await client.is_enabled("feature-x"):
       # Feature is enabled
       pass


String Flags
~~~~~~~~~~~~

.. code-block:: python

   # Get experiment variant
   variant = await client.get_string_value("experiment-color", default="blue")

   # A/B testing with context
   context = EvaluationContext(targeting_key="user-123")
   variant = await client.get_string_value("button-text", default="Click", context=context)


Number Flags
~~~~~~~~~~~~

.. code-block:: python

   # Get configuration value
   max_items = await client.get_number_value("max-items", default=10.0)
   rate_limit = await client.get_number_value("rate-limit-rps", default=100.0)


Object/JSON Flags
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Get complex configuration
   config = await client.get_object_value(
       "feature-config",
       default={"enabled": False, "limit": 10},
   )


Bulk Evaluation
---------------

For evaluating multiple flags at once:

.. code-block:: python

   # Get all active flags
   all_flags = await client.get_all_flags(context=context)

   # Get specific flags
   flags = await client.get_flags(
       ["feature-a", "feature-b", "experiment-1"],
       context=context,
   )

   for key, details in flags.items():
       print(f"{key}: {details.value}")


Lifecycle Management
--------------------

The client supports async context manager protocol for proper resource cleanup:

.. code-block:: python

   async with FeatureFlagClient(storage=storage) as client:
       enabled = await client.get_boolean_value("my-feature")
   # Resources are automatically cleaned up


Health Checks
-------------

Check if the client and storage backend are healthy:

.. code-block:: python

   if await client.health_check():
       print("Feature flag system is healthy")
   else:
       print("Feature flag system is not available")
