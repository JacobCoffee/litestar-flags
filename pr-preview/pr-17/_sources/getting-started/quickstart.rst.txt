Quickstart
==========

This guide will get you up and running with litestar-flags in under 5 minutes.


Step 1: Install the Package
---------------------------

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


Step 2: Create Your First App
-----------------------------

Create a file called ``app.py``:

.. code-block:: python

   from litestar import Litestar, get
   from litestar_flags import (
       FeatureFlagsPlugin,
       FeatureFlagsConfig,
       FeatureFlagsClient,
       FeatureFlag,
   )

   # Configure the plugin
   config = FeatureFlagsConfig()
   plugin = FeatureFlagsPlugin(config=config)


   @get("/")
   async def index(feature_flags: FeatureFlagsClient) -> dict:
       # Create a feature flag if it doesn't exist
       await feature_flags.create_flag(
           FeatureFlag(
               name="welcome_message",
               enabled=True,
               description="Show welcome message",
           )
       )

       # Check if the flag is enabled
       if await feature_flags.is_enabled("welcome_message"):
           return {"message": "Welcome to litestar-flags!"}
       return {"message": "Hello, World!"}


   app = Litestar(
       route_handlers=[index],
       plugins=[plugin],
   )


Step 3: Run Your App
--------------------

.. code-block:: bash

   litestar run

Visit http://localhost:8000 to see your feature flag in action!


Step 4: Toggle Features
-----------------------

You can toggle features at runtime:

.. code-block:: python

   @get("/toggle")
   async def toggle(feature_flags: FeatureFlagsClient) -> dict:
       # Get current state
       flag = await feature_flags.get_flag("welcome_message")

       # Toggle the flag
       flag.enabled = not flag.enabled
       await feature_flags.update_flag(flag)

       return {"enabled": flag.enabled}


What's Next?
------------

- Learn about :doc:`configuration` options
- Explore different :doc:`/guides/storage-backends`
- Set up :doc:`/guides/percentage-rollouts` for gradual releases
