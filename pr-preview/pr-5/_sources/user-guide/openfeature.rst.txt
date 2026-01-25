OpenFeature Integration
=======================

This guide covers the OpenFeature provider for litestar-flags, enabling
vendor-agnostic feature flag evaluation in your applications.


What is OpenFeature?
--------------------

`OpenFeature <https://openfeature.dev/>`_ is an open specification that provides
a vendor-agnostic, community-driven API for feature flagging. By using OpenFeature,
you gain:

**Portability**
    Switch between feature flag providers without changing application code.
    Start with litestar-flags and migrate to LaunchDarkly, Split, or Flagsmith
    later without refactoring.

**Standardization**
    A consistent API across all languages and providers. Developers familiar
    with OpenFeature can work with any compliant provider immediately.

**Ecosystem**
    Access to a growing ecosystem of hooks, integrations, and tooling that
    works with any OpenFeature-compliant provider.

**Future-Proofing**
    As the feature flagging landscape evolves, OpenFeature ensures your code
    remains compatible with new providers and capabilities.


Installation
------------

Install litestar-flags with the OpenFeature extra:

.. tab-set::
   :sync-group: package-manager

   .. tab-item:: uv (Recommended)
      :sync: uv

      .. code-block:: bash

         uv add litestar-flags[openfeature]

   .. tab-item:: pip
      :sync: pip

      .. code-block:: bash

         pip install litestar-flags[openfeature]

This installs both ``litestar-flags`` and the ``openfeature-sdk`` package.


Quick Start
-----------

Here is a minimal example to get started with the OpenFeature provider:

.. code-block:: python

   from openfeature import api
   from litestar_flags.contrib.openfeature import LitestarFlagsProvider
   from litestar_flags.client import FeatureFlagClient
   from litestar_flags.storage.memory import MemoryStorageBackend

   # Step 1: Create the litestar-flags client
   storage = MemoryStorageBackend()
   client = FeatureFlagClient(storage=storage)

   # Step 2: Create and register the OpenFeature provider
   provider = LitestarFlagsProvider(client)
   api.set_provider(provider)

   # Step 3: Use the OpenFeature API
   of_client = api.get_client()
   enabled = of_client.get_boolean_value("my-feature", False)
   print(f"Feature enabled: {enabled}")

The OpenFeature API mirrors the litestar-flags client methods but uses
the standardized OpenFeature interface.


Provider Configuration
----------------------

The ``LitestarFlagsProvider`` accepts the following configuration options:

Constructor Parameters
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from litestar_flags.contrib.openfeature import LitestarFlagsProvider

   provider = LitestarFlagsProvider(
       client=client,           # Required: FeatureFlagClient instance
       name="litestar-flags",   # Optional: Provider name (default: "litestar-flags")
   )

**client** (required)
    A configured ``FeatureFlagClient`` instance. The provider delegates all
    flag evaluation to this client.

**name** (optional)
    A human-readable name for the provider. Useful when debugging or when
    using multiple providers. Defaults to ``"litestar-flags"``.

Provider Lifecycle
~~~~~~~~~~~~~~~~~~

The provider follows the OpenFeature lifecycle:

.. code-block:: python

   from openfeature import api
   from openfeature.provider import ProviderStatus

   # Register the provider
   api.set_provider(provider)

   # Check provider status
   status = api.get_provider().get_status()
   assert status == ProviderStatus.READY

   # The provider is ready when the underlying client is initialized
   # and the storage backend is connected

   # Shutdown (if needed)
   await api.shutdown()


Using with Litestar
-------------------

The OpenFeature provider integrates seamlessly with Litestar applications.

Basic Integration
~~~~~~~~~~~~~~~~~

You can use both the native litestar-flags client and the OpenFeature API
in the same application:

.. code-block:: python

   from litestar import Litestar, get
   from openfeature import api
   from litestar_flags import FeatureFlagsPlugin, FeatureFlagsConfig
   from litestar_flags.client import FeatureFlagClient
   from litestar_flags.contrib.openfeature import LitestarFlagsProvider


   @get("/native")
   async def native_example(feature_flags: FeatureFlagClient) -> dict:
       """Use the native litestar-flags client."""
       enabled = await feature_flags.is_enabled("new-dashboard")
       return {"dashboard_version": "v2" if enabled else "v1"}


   @get("/openfeature")
   async def openfeature_example() -> dict:
       """Use the OpenFeature API."""
       of_client = api.get_client()
       enabled = of_client.get_boolean_value("new-dashboard", False)
       return {"dashboard_version": "v2" if enabled else "v1"}


   # Configure and create the app
   config = FeatureFlagsConfig()
   plugin = FeatureFlagsPlugin(config=config)

   app = Litestar(
       route_handlers=[native_example, openfeature_example],
       plugins=[plugin],
       on_startup=[setup_openfeature],
   )


   async def setup_openfeature(app: Litestar) -> None:
       """Register the OpenFeature provider on startup."""
       client = app.state.feature_flags
       provider = LitestarFlagsProvider(client)
       api.set_provider(provider)

Getting the Provider from App State
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For more complex scenarios, you can store the provider in app state:

.. code-block:: python

   from litestar import Litestar
   from litestar.datastructures import State

   async def setup_openfeature(app: Litestar) -> None:
       """Set up OpenFeature with the litestar-flags client."""
       client = app.state.feature_flags
       provider = LitestarFlagsProvider(client)

       # Register with OpenFeature
       api.set_provider(provider)

       # Store provider in state for direct access if needed
       app.state.openfeature_provider = provider


   @get("/provider-info")
   async def get_provider_info(state: State) -> dict:
       """Access provider information."""
       provider = state.openfeature_provider
       return {
           "provider_name": provider.get_metadata().name,
           "status": provider.get_status().value,
       }


Complete Application Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Here is a complete example demonstrating the integration:

.. code-block:: python

   """Complete Litestar application with OpenFeature integration."""
   from litestar import Litestar, get, post
   from openfeature import api
   from openfeature.evaluation_context import EvaluationContext as OFContext

   from litestar_flags import FeatureFlagsPlugin, FeatureFlagsConfig
   from litestar_flags.client import FeatureFlagClient
   from litestar_flags.context import EvaluationContext
   from litestar_flags.contrib.openfeature import LitestarFlagsProvider
   from litestar_flags.models.flag import FeatureFlag
   from litestar_flags.types import FlagType, FlagStatus


   async def on_startup(app: Litestar) -> None:
       """Initialize OpenFeature provider and seed test flags."""
       # Get the client from app state (set up by FeatureFlagsPlugin)
       client: FeatureFlagClient = app.state.feature_flags

       # Register the OpenFeature provider
       provider = LitestarFlagsProvider(client)
       api.set_provider(provider)

       # Seed some test flags
       storage = client.storage
       await storage.create_flag(
           FeatureFlag(
               key="dark-mode",
               name="Dark Mode",
               description="Enable dark mode UI",
               flag_type=FlagType.BOOLEAN,
               status=FlagStatus.ACTIVE,
               default_enabled=True,
           )
       )
       await storage.create_flag(
           FeatureFlag(
               key="max-items",
               name="Maximum Items",
               description="Maximum items per page",
               flag_type=FlagType.NUMBER,
               status=FlagStatus.ACTIVE,
               default_enabled=True,
               default_value=25,
           )
       )


   @get("/features")
   async def list_features() -> dict:
       """List all feature flag values using OpenFeature."""
       of_client = api.get_client()

       return {
           "dark_mode": of_client.get_boolean_value("dark-mode", False),
           "max_items": of_client.get_number_value("max-items", 10),
       }


   @get("/features/{feature_key:str}")
   async def get_feature(feature_key: str) -> dict:
       """Get a specific feature flag with details."""
       of_client = api.get_client()
       details = of_client.get_boolean_details(feature_key, False)

       return {
           "key": feature_key,
           "value": details.value,
           "reason": details.reason.value if details.reason else None,
           "variant": details.variant,
       }


   # Create the application
   config = FeatureFlagsConfig()
   plugin = FeatureFlagsPlugin(config=config)

   app = Litestar(
       route_handlers=[list_features, get_feature],
       plugins=[plugin],
       on_startup=[on_startup],
   )


Evaluation Context
------------------

OpenFeature uses ``EvaluationContext`` to pass targeting information to
flag evaluations. The litestar-flags provider maps these contexts to its
native ``EvaluationContext``.

Context Mapping
~~~~~~~~~~~~~~~

The OpenFeature context is mapped as follows:

+---------------------------+----------------------------------+
| OpenFeature Field         | litestar-flags Field             |
+===========================+==================================+
| ``targeting_key``         | ``targeting_key``                |
+---------------------------+----------------------------------+
| Custom attributes         | ``attributes`` dictionary        |
+---------------------------+----------------------------------+

Using the Targeting Key
~~~~~~~~~~~~~~~~~~~~~~~

The ``targeting_key`` is essential for percentage rollouts and consistent
bucketing:

.. code-block:: python

   from openfeature import api
   from openfeature.evaluation_context import EvaluationContext

   of_client = api.get_client()

   # Create context with targeting key
   context = EvaluationContext(
       targeting_key="user-12345",
   )

   # Evaluate with context - user gets consistent results
   enabled = of_client.get_boolean_value("gradual-rollout", False, context)

Custom Attributes
~~~~~~~~~~~~~~~~~

Pass custom attributes for targeting rules:

.. code-block:: python

   from openfeature.evaluation_context import EvaluationContext

   context = EvaluationContext(
       targeting_key="user-12345",
       attributes={
           "plan": "premium",
           "country": "US",
           "beta_tester": True,
           "signup_date": "2024-01-15",
       },
   )

   # These attributes are used in rule evaluation
   of_client = api.get_client()
   enabled = of_client.get_boolean_value(
       "premium-feature",
       default_value=False,
       evaluation_context=context,
   )

Named Attribute Helpers
~~~~~~~~~~~~~~~~~~~~~~~

OpenFeature contexts also support common named attributes:

.. code-block:: python

   from openfeature.evaluation_context import EvaluationContext

   # Using a dictionary for the constructor
   context = EvaluationContext(
       targeting_key="user-12345",
       attributes={
           "user_id": "user-12345",
           "organization_id": "org-789",
           "environment": "production",
           "app_version": "2.1.0",
       }
   )


Error Handling
--------------

The OpenFeature SDK handles errors gracefully, returning default values
when evaluation fails.

Error Codes
~~~~~~~~~~~

The provider maps litestar-flags error codes to OpenFeature error codes:

+----------------------------+--------------------------------+
| Scenario                   | OpenFeature Error Code         |
+============================+================================+
| Flag not found             | ``FLAG_NOT_FOUND``             |
+----------------------------+--------------------------------+
| Type mismatch              | ``TYPE_MISMATCH``              |
+----------------------------+--------------------------------+
| Provider not ready         | ``PROVIDER_NOT_READY``         |
+----------------------------+--------------------------------+
| General error              | ``GENERAL``                    |
+----------------------------+--------------------------------+
| Parse error                | ``PARSE_ERROR``                |
+----------------------------+--------------------------------+

Getting Error Details
~~~~~~~~~~~~~~~~~~~~~

Use the ``*_details`` methods to inspect errors:

.. code-block:: python

   from openfeature import api
   from openfeature.flag_evaluation import Reason

   of_client = api.get_client()

   # Get evaluation details including error information
   details = of_client.get_boolean_details("nonexistent-flag", False)

   if details.reason == Reason.ERROR:
       print(f"Error code: {details.error_code}")
       print(f"Error message: {details.error_message}")
   else:
       print(f"Flag value: {details.value}")
       print(f"Reason: {details.reason}")

Default Values on Error
~~~~~~~~~~~~~~~~~~~~~~~

When evaluation fails, the default value is returned:

.. code-block:: python

   # These return defaults when flags don't exist or evaluation fails
   of_client.get_boolean_value("missing", default_value=True)   # Returns True
   of_client.get_string_value("missing", default_value="fallback")  # Returns "fallback"
   of_client.get_number_value("missing", default_value=42)      # Returns 42
   of_client.get_object_value("missing", default_value={"a": 1})  # Returns {"a": 1}


Hooks
-----

OpenFeature hooks allow you to add custom logic at various points in the
flag evaluation lifecycle.

Hook Lifecycle
~~~~~~~~~~~~~~

Hooks can intercept evaluation at four stages:

1. **before**: Before flag evaluation begins
2. **after**: After successful evaluation
3. **error**: When an error occurs
4. **finally_after**: Always called, regardless of success or failure

Creating Custom Hooks
~~~~~~~~~~~~~~~~~~~~~

Implement the ``Hook`` interface to create custom hooks:

.. code-block:: python

   from openfeature.hook import Hook
   from openfeature.flag_evaluation import FlagEvaluationDetails
   from openfeature.evaluation_context import EvaluationContext
   from openfeature.hook import HookContext, HookHints
   from typing import Optional
   import logging

   logger = logging.getLogger(__name__)


   class LoggingHook(Hook):
       """Hook that logs all flag evaluations."""

       def before(
           self,
           hook_context: HookContext,
           hints: HookHints,
       ) -> Optional[EvaluationContext]:
           """Called before evaluation."""
           logger.info(
               f"Evaluating flag: {hook_context.flag_key}"
           )
           return None  # Return context to modify, or None

       def after(
           self,
           hook_context: HookContext,
           details: FlagEvaluationDetails,
           hints: HookHints,
       ) -> None:
           """Called after successful evaluation."""
           logger.info(
               f"Flag {hook_context.flag_key} = {details.value} "
               f"(reason: {details.reason})"
           )

       def error(
           self,
           hook_context: HookContext,
           exception: Exception,
           hints: HookHints,
       ) -> None:
           """Called when evaluation fails."""
           logger.error(
               f"Error evaluating {hook_context.flag_key}: {exception}"
           )

       def finally_after(
           self,
           hook_context: HookContext,
           hints: HookHints,
       ) -> None:
           """Always called after evaluation."""
           pass  # Cleanup logic here

Registering Hooks
~~~~~~~~~~~~~~~~~

Hooks can be registered at different levels:

.. code-block:: python

   from openfeature import api

   # Global hooks (apply to all evaluations)
   api.add_hooks([LoggingHook()])

   # Client-level hooks
   of_client = api.get_client()
   of_client.add_hooks([LoggingHook()])

   # Per-evaluation hooks
   of_client.get_boolean_value(
       "my-flag",
       default_value=False,
       hooks=[LoggingHook()],
   )

Example: Metrics Hook
~~~~~~~~~~~~~~~~~~~~~

Here is an example hook that tracks evaluation metrics:

.. code-block:: python

   from openfeature.hook import Hook, HookContext, HookHints
   from openfeature.flag_evaluation import FlagEvaluationDetails
   import time
   from dataclasses import dataclass, field
   from typing import Optional


   @dataclass
   class EvaluationMetrics:
       """Simple metrics collector."""

       evaluations: int = 0
       errors: int = 0
       total_duration_ms: float = 0.0
       flag_counts: dict = field(default_factory=dict)


   class MetricsHook(Hook):
       """Hook that collects evaluation metrics."""

       def __init__(self, metrics: EvaluationMetrics):
           self.metrics = metrics
           self._start_times: dict = {}

       def before(
           self,
           hook_context: HookContext,
           hints: HookHints,
       ) -> Optional[EvaluationContext]:
           self._start_times[hook_context.flag_key] = time.perf_counter()
           return None

       def after(
           self,
           hook_context: HookContext,
           details: FlagEvaluationDetails,
           hints: HookHints,
       ) -> None:
           self.metrics.evaluations += 1
           flag_key = hook_context.flag_key
           self.metrics.flag_counts[flag_key] = (
               self.metrics.flag_counts.get(flag_key, 0) + 1
           )

       def error(
           self,
           hook_context: HookContext,
           exception: Exception,
           hints: HookHints,
       ) -> None:
           self.metrics.errors += 1

       def finally_after(
           self,
           hook_context: HookContext,
           hints: HookHints,
       ) -> None:
           start = self._start_times.pop(hook_context.flag_key, None)
           if start:
               duration = (time.perf_counter() - start) * 1000
               self.metrics.total_duration_ms += duration


   # Usage
   metrics = EvaluationMetrics()
   api.add_hooks([MetricsHook(metrics)])

   # After some evaluations...
   print(f"Total evaluations: {metrics.evaluations}")
   print(f"Errors: {metrics.errors}")
   print(f"Avg duration: {metrics.total_duration_ms / max(metrics.evaluations, 1):.2f}ms")


Async Support
-------------

The litestar-flags client is async-native, but OpenFeature SDK currently
provides synchronous methods. The provider handles this by running async
evaluations in an event loop.

Synchronous Usage
~~~~~~~~~~~~~~~~~

The standard OpenFeature methods are synchronous:

.. code-block:: python

   from openfeature import api

   of_client = api.get_client()

   # These are synchronous calls
   enabled = of_client.get_boolean_value("my-flag", False)
   variant = of_client.get_string_value("ab-test", "control")

Using in Async Context
~~~~~~~~~~~~~~~~~~~~~~

When called from an async context (like a Litestar route handler),
the provider manages the async/sync bridge:

.. code-block:: python

   from litestar import get
   from openfeature import api

   @get("/async-example")
   async def async_handler() -> dict:
       """The OpenFeature calls work in async handlers."""
       of_client = api.get_client()

       # These calls are handled appropriately
       enabled = of_client.get_boolean_value("feature", False)
       return {"enabled": enabled}

Performance Considerations
~~~~~~~~~~~~~~~~~~~~~~~~~~

For high-performance scenarios, consider:

1. **Preload flags**: Use the client's ``preload_flags()`` method to cache
   flags at startup.

2. **Use caching**: Configure the ``FeatureFlagClient`` with a cache for
   faster lookups.

3. **Batch evaluations**: When possible, evaluate multiple flags together
   to reduce overhead.

.. code-block:: python

   # Preload flags at startup for faster evaluations
   async def on_startup(app: Litestar) -> None:
       client = app.state.feature_flags
       await client.preload_flags()  # Cache all active flags


Migration Guide
---------------

Migrating from Direct litestar-flags Usage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you are currently using litestar-flags directly and want to add
OpenFeature support:

**Before** (native litestar-flags):

.. code-block:: python

   from litestar_flags.client import FeatureFlagClient

   async def check_feature(client: FeatureFlagClient) -> bool:
       return await client.is_enabled("my-feature")

**After** (OpenFeature):

.. code-block:: python

   from openfeature import api

   def check_feature() -> bool:
       of_client = api.get_client()
       return of_client.get_boolean_value("my-feature", False)

**Gradual Migration**:

You can use both APIs during migration:

.. code-block:: python

   from litestar_flags.client import FeatureFlagClient
   from openfeature import api

   async def check_feature(client: FeatureFlagClient) -> bool:
       # Legacy code path
       native_result = await client.is_enabled("my-feature")

       # New code path (for validation)
       of_client = api.get_client()
       of_result = of_client.get_boolean_value("my-feature", False)

       # They should match
       assert native_result == of_result

       return native_result

Migrating from Other OpenFeature Providers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you are using another OpenFeature provider and want to switch to
litestar-flags:

1. **Install litestar-flags**:

   .. code-block:: bash

      pip install litestar-flags[openfeature]

2. **Replace the provider**:

   .. code-block:: python

      from openfeature import api
      from litestar_flags.contrib.openfeature import LitestarFlagsProvider
      from litestar_flags.client import FeatureFlagClient
      from litestar_flags.storage.memory import MemoryStorageBackend

      # Create litestar-flags client
      storage = MemoryStorageBackend()
      client = FeatureFlagClient(storage=storage)

      # Replace your existing provider
      provider = LitestarFlagsProvider(client)
      api.set_provider(provider)

3. **Migrate your flags**: Export flags from your previous provider and
   import them into litestar-flags storage.

4. **Test thoroughly**: Ensure all flag evaluations produce expected results
   before removing the old provider.

Feature Comparison
~~~~~~~~~~~~~~~~~~

When migrating, note these feature differences:

+-------------------------+------------------+----------------------+
| Feature                 | litestar-flags   | Most Cloud Providers |
+=========================+==================+======================+
| Self-hosted             | Yes              | No                   |
+-------------------------+------------------+----------------------+
| No vendor lock-in       | Yes              | Varies               |
+-------------------------+------------------+----------------------+
| Async-native            | Yes              | Varies               |
+-------------------------+------------------+----------------------+
| Litestar integration    | Native           | Via OpenFeature      |
+-------------------------+------------------+----------------------+
| Real-time updates       | With Redis/DB    | Yes                  |
+-------------------------+------------------+----------------------+
| Management UI           | Build your own   | Included             |
+-------------------------+------------------+----------------------+


API Reference
-------------

For complete API documentation, see:

- :doc:`/api/client` - FeatureFlagClient API
- :doc:`/api/context` - EvaluationContext API
- :doc:`/api/types` - Type definitions and enums

For OpenFeature SDK documentation, see the
`OpenFeature Python SDK docs <https://openfeature.dev/docs/reference/technologies/server/python>`_.


See Also
--------

- :doc:`/getting-started/quickstart` - Getting started with litestar-flags
- :doc:`/guides/storage-backends` - Configuring storage backends
- :doc:`/guides/percentage-rollouts` - Setting up percentage rollouts
- :doc:`/guides/user-targeting` - User targeting with rules
- `OpenFeature Specification <https://openfeature.dev/specification/>`_
- `OpenFeature Python SDK <https://github.com/open-feature/python-sdk>`_
