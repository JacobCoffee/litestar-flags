Getting Started
===============

Welcome to litestar-flags! This section will guide you through installing and
setting up your first feature flag.


Installation
------------

Install litestar-flags using your preferred package manager:

.. tab-set::
   :sync-group: package-manager

   .. tab-item:: uv (Recommended)
      :sync: uv

      .. code-block:: bash

         uv add litestar-flags

   .. tab-item:: pip
      :sync: pip

      .. code-block:: bash

         pip install litestar-flags

Or with optional dependencies for different storage backends:

**Redis support:**

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

**Database support (SQLAlchemy):**

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

**All optional dependencies:**

.. tab-set::
   :sync-group: package-manager

   .. tab-item:: uv (Recommended)
      :sync: uv

      .. code-block:: bash

         uv add litestar-flags[all]

   .. tab-item:: pip
      :sync: pip

      .. code-block:: bash

         pip install litestar-flags[all]


Basic Setup
-----------

Here's a minimal example to get you started:

.. code-block:: python

   from litestar import Litestar, get
   from litestar_flags import FeatureFlagsPlugin, FeatureFlagsConfig, FeatureFlagsClient

   # Create the plugin with default configuration (in-memory storage)
   config = FeatureFlagsConfig()
   plugin = FeatureFlagsPlugin(config=config)

   @get("/")
   async def index(feature_flags: FeatureFlagsClient) -> dict:
       # Check if a feature is enabled
       if await feature_flags.is_enabled("dark_mode"):
           return {"theme": "dark"}
       return {"theme": "light"}

   app = Litestar(
       route_handlers=[index],
       plugins=[plugin],
   )


Creating Feature Flags
----------------------

You can create feature flags programmatically:

.. code-block:: python

   from litestar_flags import FeatureFlag

   # Simple boolean flag
   dark_mode = FeatureFlag(
       name="dark_mode",
       enabled=True,
       description="Enable dark mode theme",
   )

   # Percentage rollout flag
   new_checkout = FeatureFlag(
       name="new_checkout",
       enabled=True,
       rollout_percentage=25,  # Enable for 25% of users
       description="New checkout flow",
   )


Next Steps
----------

- Learn about :doc:`/guides/storage-backends` for production deployments
- Explore :doc:`/guides/percentage-rollouts` for gradual feature releases
- Check the :doc:`/api/index` for complete API documentation


.. toctree::
   :maxdepth: 2
   :hidden:

   installation
   quickstart
   configuration
