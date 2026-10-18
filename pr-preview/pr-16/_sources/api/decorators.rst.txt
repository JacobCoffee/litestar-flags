Decorators
==========

Convenient decorators for protecting route handlers with feature flags.
These decorators provide a declarative way to control access to endpoints
based on flag evaluation.

Overview
--------

Two decorators are provided:

- ``@feature_flag``: Conditionally execute handlers; returns alternative response when disabled
- ``@require_flag``: Require flag to be enabled; raises exception when disabled

Both decorators integrate seamlessly with Litestar's dependency injection and
automatically extract evaluation context from requests when middleware is enabled.


API Reference
-------------

.. automodule:: litestar_flags.decorators
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource


feature_flag Decorator
----------------------

Use ``@feature_flag`` when you want to return an alternative response instead
of raising an exception.

Basic Usage
~~~~~~~~~~~

.. code-block:: python

   from litestar import get
   from litestar_flags import feature_flag

   @get("/new-feature")
   @feature_flag("new_feature", default_response={"error": "Feature not available"})
   async def new_feature_endpoint() -> dict:
       return {"message": "Welcome to the new feature!"}


With Default Value
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   @get("/beta-feature")
   @feature_flag(
       "beta_access",
       default=False,  # Default if flag not found
       default_response={"status": "coming_soon"},
   )
   async def beta_endpoint() -> dict:
       return {"status": "active", "features": ["beta_1", "beta_2"]}


With Context Key
~~~~~~~~~~~~~~~~

Specify which request attribute to use as the targeting key:

.. code-block:: python

   @get("/user/{user_id:str}/premium")
   @feature_flag(
       "premium_features",
       context_key="user_id",  # Use path param as targeting key
       default_response={"error": "Premium access required"},
   )
   async def premium_endpoint(user_id: str) -> dict:
       return {"premium": True, "user_id": user_id}


Parameters
~~~~~~~~~~

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``flag_key``
     - ``str``
     - The feature flag key to evaluate
   * - ``default``
     - ``bool``
     - Default value if flag is not found (default: ``False``)
   * - ``default_response``
     - ``Any``
     - Response to return when flag is disabled (default: ``None``)
   * - ``context_key``
     - ``str | None``
     - Request attribute to use as targeting key (optional)


require_flag Decorator
----------------------

Use ``@require_flag`` when you want to raise an exception for unauthorized access.
This is useful for protecting premium or beta features.

Basic Usage
~~~~~~~~~~~

.. code-block:: python

   from litestar import get
   from litestar_flags import require_flag

   @get("/admin/dashboard")
   @require_flag("admin_access")
   async def admin_dashboard() -> dict:
       return {"admin": True, "stats": {...}}


With Custom Error Message
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   @get("/beta")
   @require_flag(
       "beta_access",
       error_message="This feature is only available to beta testers",
   )
   async def beta_endpoint() -> dict:
       return {"beta": True}


With Context Key
~~~~~~~~~~~~~~~~

.. code-block:: python

   @get("/org/{org_id:str}/billing")
   @require_flag(
       "billing_v2",
       context_key="org_id",
       error_message="New billing is not enabled for your organization",
   )
   async def billing_endpoint(org_id: str) -> dict:
       return {"billing_version": 2}


Parameters
~~~~~~~~~~

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``flag_key``
     - ``str``
     - The feature flag key to evaluate
   * - ``default``
     - ``bool``
     - Default value if flag is not found (default: ``False``)
   * - ``context_key``
     - ``str | None``
     - Request attribute to use as targeting key (optional)
   * - ``error_message``
     - ``str | None``
     - Custom error message for the exception (optional)


Exception Behavior
~~~~~~~~~~~~~~~~~~

When the flag is disabled, ``@require_flag`` raises ``NotAuthorizedException``
(HTTP 403):

.. code-block:: python

   # Client receives:
   {
       "status_code": 403,
       "detail": "Feature 'beta_access' is not available"
   }


Decorator Order
---------------

When combining with other decorators, place feature flag decorators after the
route decorator:

.. code-block:: python

   from litestar import get
   from litestar_flags import feature_flag, require_flag

   # Correct order
   @get("/feature")
   @feature_flag("my_feature")
   async def handler() -> dict:
       ...

   # Also correct - multiple flags
   @get("/premium-beta")
   @require_flag("premium_access")
   @require_flag("beta_access")
   async def premium_beta_handler() -> dict:
       ...


Context Resolution
------------------

The decorators resolve evaluation context in this order:

1. **Middleware context**: If ``FeatureFlagsMiddleware`` is enabled, use extracted context
2. **Context key**: If ``context_key`` is specified, look up from request:
   - Path parameters (e.g., ``/users/{user_id}``)
   - Query parameters (e.g., ``?user_id=123``)
   - Headers (e.g., ``X-User-ID``)
   - User attributes (e.g., ``request.user.id``)
3. **User auth**: If authenticated, use ``request.user.id`` or ``request.user.user_id``
4. **Default**: Use default context if nothing else is available


Integration Examples
--------------------

With Authentication
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from litestar import get, Request
   from litestar.connection import ASGIConnection
   from litestar_flags import require_flag

   @get("/settings")
   @require_flag("settings_v2")
   async def settings_endpoint(request: Request) -> dict:
       # The decorator automatically uses request.user.id as targeting key
       return {"user": str(request.user.id), "settings_version": 2}


With Guards
~~~~~~~~~~~

.. code-block:: python

   from litestar import get
   from litestar.guards import Guard
   from litestar_flags import require_flag

   async def auth_guard(connection: ASGIConnection, _) -> None:
       if not connection.user:
           raise NotAuthorizedException()

   @get("/protected", guards=[auth_guard])
   @require_flag("protected_feature")
   async def protected_endpoint() -> dict:
       return {"protected": True}


With Rate Limiting
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from litestar import get
   from litestar_flags import feature_flag

   @get("/api/v2/data")
   @feature_flag(
       "api_v2",
       default_response={"error": "API v2 not available", "use": "/api/v1/data"},
   )
   async def api_v2_endpoint() -> dict:
       return {"version": 2, "data": [...]}


A/B Testing Response
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from litestar import get
   from litestar_flags import FeatureFlagClient, EvaluationContext

   @get("/checkout")
   async def checkout_endpoint(
       feature_flags: FeatureFlagClient,
       user_id: str,
   ) -> dict:
       context = EvaluationContext(targeting_key=user_id)
       variant = await feature_flags.get_string_value(
           "checkout_experiment",
           default="control",
           context=context,
       )

       if variant == "treatment":
           return {"checkout_version": "new", "layout": "streamlined"}
       else:
           return {"checkout_version": "classic", "layout": "standard"}
