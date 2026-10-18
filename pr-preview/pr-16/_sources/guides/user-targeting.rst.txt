User Targeting
==============

User targeting allows you to enable or disable features for specific users
or groups of users.


Basic User Targeting
--------------------

Enable a feature for specific users:

.. code-block:: python

   from litestar_flags import FeatureFlag

   beta_feature = FeatureFlag(
       name="beta_dashboard",
       enabled=True,
       allowed_users=["user_123", "user_456", "user_789"],
       description="New beta dashboard for selected users",
   )


Checking Flags with User Context
--------------------------------

Pass the user ID when checking flags:

.. code-block:: python

   @get("/dashboard")
   async def dashboard(
       feature_flags: FeatureFlagsClient,
       current_user: User,
   ) -> dict:
       if await feature_flags.is_enabled("beta_dashboard", user_id=current_user.id):
           return {"dashboard": "beta"}
       return {"dashboard": "stable"}


Group-Based Targeting
---------------------

Target users by group membership:

.. code-block:: python

   internal_feature = FeatureFlag(
       name="admin_tools",
       enabled=True,
       allowed_groups=["admins", "support_staff"],
       description="Administrative tools for internal users",
   )


Evaluation Context
------------------

Provide rich context for flag evaluation:

.. code-block:: python

   @get("/feature")
   async def feature(
       feature_flags: FeatureFlagsClient,
       current_user: User,
   ) -> dict:
       context = {
           "user_id": current_user.id,
           "groups": current_user.groups,
           "plan": current_user.subscription_plan,
           "country": current_user.country,
       }

       if await feature_flags.is_enabled("premium_feature", context=context):
           return {"access": "granted"}
       return {"access": "denied"}


Priority Order
--------------

When multiple targeting rules apply, they are evaluated in this order:

1. **Blocked users**: Always disabled
2. **Allowed users**: Always enabled
3. **Allowed groups**: Enabled if user is in any allowed group
4. **Percentage rollout**: Evaluated if no user/group rules match
5. **Default**: The flag's ``enabled`` value


Best Practices
--------------

1. **Use meaningful identifiers**: Use stable user IDs, not email addresses
2. **Document targeting rules**: Keep track of why certain users are targeted
3. **Clean up old rules**: Remove targeting rules when features are fully released
4. **Test with targeting**: Verify targeting works as expected before rollout
