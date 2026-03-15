Context
=======

The ``EvaluationContext`` provides attributes for targeting rules and percentage
rollouts during flag evaluation. It follows the OpenFeature specification patterns.

Overview
--------

The context is an immutable dataclass that carries information about the current
evaluation request. This includes:

- **Targeting key**: Primary identifier for consistent hashing in percentage rollouts
- **User attributes**: User ID, organization, tenant for user-level targeting
- **Environment info**: Environment name, app version for deployment-based rules
- **Custom attributes**: Flexible key-value pairs for any targeting logic
- **Request metadata**: IP address, user agent, country for request-level targeting

Key Features:

- Immutable by design (frozen dataclass)
- Flexible attribute access via ``get()`` method
- Merge support for combining contexts
- Builder-style methods for creating variations

Quick Example
-------------

.. code-block:: python

   from litestar_flags import EvaluationContext

   # Create a context for a specific user
   context = EvaluationContext(
       targeting_key="user-123",
       user_id="user-123",
       organization_id="org-456",
       environment="production",
       attributes={
           "plan": "premium",
           "beta_tester": True,
           "signup_date": "2024-01-15",
       },
   )

   # Access attributes
   plan = context.get("plan")  # "premium"
   beta = context.get("beta_tester")  # True


API Reference
-------------

.. automodule:: litestar_flags.context
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource


Creating Contexts
-----------------

Basic Context
~~~~~~~~~~~~~

.. code-block:: python

   # Minimal context with just a targeting key
   context = EvaluationContext(targeting_key="user-123")

   # User context with common attributes
   context = EvaluationContext(
       targeting_key="user-123",
       user_id="user-123",
       organization_id="org-456",
       environment="production",
   )


With Custom Attributes
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   context = EvaluationContext(
       targeting_key="user-123",
       attributes={
           "plan": "enterprise",
           "feature_tier": 3,
           "enabled_addons": ["analytics", "export"],
           "created_at": "2024-01-01",
       },
   )


Request Context
~~~~~~~~~~~~~~~

For request-level targeting (often populated by middleware):

.. code-block:: python

   context = EvaluationContext(
       targeting_key="user-123",
       ip_address="192.168.1.1",
       user_agent="Mozilla/5.0...",
       country="US",
   )


Accessing Attributes
--------------------

The ``get()`` method provides unified access to both standard and custom attributes:

.. code-block:: python

   context = EvaluationContext(
       user_id="user-123",
       attributes={"plan": "premium"},
   )

   # Access standard attributes
   user_id = context.get("user_id")  # "user-123"

   # Access custom attributes
   plan = context.get("plan")  # "premium"

   # Default values for missing attributes
   tier = context.get("tier", default="free")  # "free"


Modifying Contexts
------------------

Since contexts are immutable, modification methods return new instances:

With New Targeting Key
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   base_context = EvaluationContext(
       user_id="user-123",
       environment="production",
   )

   # Create a new context with different targeting key
   session_context = base_context.with_targeting_key("session-abc")


With Additional Attributes
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   base_context = EvaluationContext(
       targeting_key="user-123",
       attributes={"plan": "free"},
   )

   # Add new attributes (original attributes are preserved)
   upgraded_context = base_context.with_attributes(
       plan="premium",
       upgraded_at="2024-06-01",
   )


Merging Contexts
~~~~~~~~~~~~~~~~

Merge two contexts, with the second context taking precedence:

.. code-block:: python

   default_context = EvaluationContext(
       environment="production",
       attributes={"version": "1.0"},
   )

   request_context = EvaluationContext(
       targeting_key="user-123",
       user_id="user-123",
       attributes={"source": "api"},
   )

   # Merge: request_context values override default_context
   merged = default_context.merge(request_context)
   # Result has: environment="production", targeting_key="user-123",
   #             user_id="user-123", attributes={"version": "1.0", "source": "api"}


Integration with Middleware
---------------------------

When using the ``FeatureFlagsMiddleware``, context can be automatically extracted
from requests:

.. code-block:: python

   from litestar_flags import (
       FeatureFlagsConfig,
       FeatureFlagsPlugin,
       EvaluationContext,
   )

   def extract_context(request) -> EvaluationContext:
       """Custom context extractor."""
       return EvaluationContext(
           targeting_key=str(request.user.id) if request.user else None,
           user_id=str(request.user.id) if request.user else None,
           ip_address=request.client.host if request.client else None,
           user_agent=request.headers.get("user-agent"),
       )

   config = FeatureFlagsConfig(
       backend="memory",
       enable_middleware=True,
       context_extractor=extract_context,
   )
