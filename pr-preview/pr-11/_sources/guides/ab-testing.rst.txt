A/B Testing
===========

litestar-flags supports A/B testing through feature flag variants, allowing
you to test multiple versions of a feature simultaneously.


Setting Up Variants
-------------------

Create a flag with multiple variants:

.. code-block:: python

   from litestar_flags import FeatureFlag

   checkout_test = FeatureFlag(
       name="checkout_experiment",
       enabled=True,
       variants={
           "control": 50,    # Original checkout (50%)
           "variant_a": 25,  # Single-page checkout (25%)
           "variant_b": 25,  # Express checkout (25%)
       },
       description="Checkout flow A/B test",
   )


Getting the Assigned Variant
----------------------------

Use ``get_variant`` to determine which variant a user should see:

.. code-block:: python

   @get("/checkout")
   async def checkout(
       feature_flags: FeatureFlagsClient,
       user_id: str,
   ) -> dict:
       variant = await feature_flags.get_variant(
           "checkout_experiment",
           user_id=user_id,
       )

       if variant == "control":
           return {"checkout": "classic"}
       elif variant == "variant_a":
           return {"checkout": "single_page"}
       elif variant == "variant_b":
           return {"checkout": "express"}


Tracking Experiment Results
---------------------------

Track which variant each user sees for analysis:

.. code-block:: python

   @get("/checkout")
   async def checkout(
       feature_flags: FeatureFlagsClient,
       analytics: AnalyticsClient,
       user_id: str,
   ) -> dict:
       variant = await feature_flags.get_variant(
           "checkout_experiment",
           user_id=user_id,
       )

       # Track the experiment exposure
       await analytics.track(
           event="experiment_exposure",
           user_id=user_id,
           properties={
               "experiment": "checkout_experiment",
               "variant": variant,
           },
       )

       # Render the appropriate variant
       return {"checkout": variant}


Variant Consistency
-------------------

Variants use consistent hashing, ensuring:

- The same user always sees the same variant
- Variant assignment is deterministic based on user ID
- Distribution matches the configured percentages over large samples


Analyzing Results
-----------------

To analyze A/B test results:

1. **Collect data**: Track variant assignments and outcomes
2. **Calculate metrics**: Conversion rates, engagement, etc.
3. **Statistical significance**: Use appropriate statistical tests
4. **Make decisions**: Choose the winning variant or iterate


Example Analysis Query
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: sql

   SELECT
       variant,
       COUNT(*) as users,
       SUM(converted) as conversions,
       AVG(converted) * 100 as conversion_rate
   FROM experiment_exposures
   WHERE experiment = 'checkout_experiment'
   GROUP BY variant;


Best Practices
--------------

1. **Test one thing at a time**: Isolate variables for clear results
2. **Sufficient sample size**: Ensure statistical significance
3. **Run long enough**: Account for daily/weekly patterns
4. **Document hypotheses**: Record what you're testing and why
5. **Clean up experiments**: Remove completed experiments
