Percentage Rollouts
===================

Percentage rollouts allow you to gradually release features to a subset of
users, reducing risk and enabling data-driven decisions.


Basic Usage
-----------

Create a flag with a rollout percentage:

.. code-block:: python

   from litestar_flags import FeatureFlag

   new_feature = FeatureFlag(
       name="new_checkout_flow",
       enabled=True,
       rollout_percentage=10,  # Enable for 10% of users
       description="New streamlined checkout experience",
   )

When evaluating the flag, pass a user identifier:

.. code-block:: python

   @get("/checkout")
   async def checkout(
       feature_flags: FeatureFlagsClient,
       user_id: str,
   ) -> dict:
       if await feature_flags.is_enabled("new_checkout_flow", user_id=user_id):
           return {"flow": "new"}
       return {"flow": "classic"}


How It Works
------------

The percentage rollout uses a consistent hashing algorithm:

1. A hash is computed from the flag name and user ID
2. The hash is mapped to a value between 0 and 100
3. If the value is less than the rollout percentage, the flag is enabled

This ensures:

- **Consistency**: The same user always gets the same result
- **Even distribution**: Users are evenly distributed across the rollout
- **Stability**: Adding new users doesn't change existing assignments


Gradual Rollout Strategy
------------------------

A common pattern for gradual releases:

.. code-block:: python

   # Week 1: 5% of users
   flag.rollout_percentage = 5
   await feature_flags.update_flag(flag)

   # Week 2: 25% of users
   flag.rollout_percentage = 25
   await feature_flags.update_flag(flag)

   # Week 3: 50% of users
   flag.rollout_percentage = 50
   await feature_flags.update_flag(flag)

   # Week 4: 100% of users
   flag.rollout_percentage = 100
   await feature_flags.update_flag(flag)


Rollback
--------

If issues are detected, you can quickly disable the feature:

.. code-block:: python

   # Immediate rollback
   flag.enabled = False
   await feature_flags.update_flag(flag)

   # Or reduce to 0%
   flag.rollout_percentage = 0
   await feature_flags.update_flag(flag)


Combining with User Targeting
-----------------------------

You can combine percentage rollouts with user targeting to:

- Always enable for beta testers
- Always disable for specific users
- Use percentage rollout for everyone else

See :doc:`user-targeting` for more details.
