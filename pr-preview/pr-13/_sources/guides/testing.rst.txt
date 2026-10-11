Testing with Feature Flags
==========================

Testing code that uses feature flags requires special consideration to ensure
all code paths are covered.


Mocking Feature Flags
---------------------

Use a mock client in your tests:

.. code-block:: python

   import pytest
   from unittest.mock import AsyncMock
   from litestar_flags import FeatureFlagsClient

   @pytest.fixture
   def mock_feature_flags():
       client = AsyncMock(spec=FeatureFlagsClient)
       client.is_enabled.return_value = True
       return client

   async def test_feature_enabled(mock_feature_flags):
       mock_feature_flags.is_enabled.return_value = True

       result = await my_function(mock_feature_flags)

       assert result == "new_behavior"

   async def test_feature_disabled(mock_feature_flags):
       mock_feature_flags.is_enabled.return_value = False

       result = await my_function(mock_feature_flags)

       assert result == "old_behavior"


Using In-Memory Backend for Tests
---------------------------------

For integration tests, use the ``MemoryStorageBackend``:

.. code-block:: python

   import pytest
   from litestar.testing import TestClient
   from litestar_flags import FeatureFlagsPlugin, FeatureFlagsConfig
   from litestar_flags.storage import MemoryStorageBackend

   @pytest.fixture
   def test_app():
       backend = MemoryStorageBackend()
       config = FeatureFlagsConfig(storage_backend=backend)
       plugin = FeatureFlagsPlugin(config=config)

       app = Litestar(
           route_handlers=[...],
           plugins=[plugin],
       )

       return app

   def test_with_feature_flag(test_app):
       with TestClient(app=test_app) as client:
           response = client.get("/")
           assert response.status_code == 200


Testing All Variants
--------------------

Ensure you test all feature flag states:

.. code-block:: python

   @pytest.mark.parametrize("flag_enabled,expected", [
       (True, "new_feature_response"),
       (False, "old_feature_response"),
   ])
   async def test_feature_variants(mock_feature_flags, flag_enabled, expected):
       mock_feature_flags.is_enabled.return_value = flag_enabled

       result = await my_function(mock_feature_flags)

       assert result == expected


Testing Percentage Rollouts
---------------------------

For percentage rollouts, test both outcomes:

.. code-block:: python

   async def test_rollout_enabled_user(mock_feature_flags):
       # Simulate a user who falls within the rollout percentage
       mock_feature_flags.is_enabled.return_value = True

       result = await checkout_flow(mock_feature_flags, user_id="user_in_rollout")

       assert result["flow"] == "new"

   async def test_rollout_excluded_user(mock_feature_flags):
       # Simulate a user outside the rollout percentage
       mock_feature_flags.is_enabled.return_value = False

       result = await checkout_flow(mock_feature_flags, user_id="user_out_of_rollout")

       assert result["flow"] == "classic"


Fixture for Controlled Testing
------------------------------

Create a fixture that gives you full control:

.. code-block:: python

   @pytest.fixture
   def feature_flags_fixture():
       """Fixture with pre-configured flags for testing."""
       backend = MemoryStorageBackend()

       # Pre-populate with test flags
       flags = {
           "feature_a": FeatureFlag(name="feature_a", enabled=True),
           "feature_b": FeatureFlag(name="feature_b", enabled=False),
           "rollout_feature": FeatureFlag(
               name="rollout_feature",
               enabled=True,
               rollout_percentage=50,
           ),
       }

       for flag in flags.values():
           backend._flags[flag.name] = flag

       return backend


Best Practices
--------------

1. **Test both states**: Always test enabled and disabled paths
2. **Use parameterized tests**: Reduce code duplication
3. **Isolate flag state**: Each test should set its own flag state
4. **Test edge cases**: Empty user IDs, missing flags, etc.
5. **Clean up**: Reset flag state between tests
