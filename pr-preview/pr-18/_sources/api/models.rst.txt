Models
======

Data models representing feature flags and their components. These models are
used for creating, storing, and evaluating feature flags.

Overview
--------

The litestar-flags library provides four main models:

- **FeatureFlag**: The core flag entity with configuration and metadata
- **FlagRule**: Targeting rules for conditional evaluation
- **FlagVariant**: Variants for A/B testing and multivariate flags
- **FlagOverride**: Entity-specific overrides for individual users or organizations

.. note::

   When ``advanced-alchemy`` is installed, these models are SQLAlchemy ORM models
   with database persistence. Otherwise, they are simple dataclasses suitable for
   in-memory or Redis storage.


FeatureFlag
-----------

The core feature flag model containing configuration and relationships.

.. automodule:: litestar_flags.models.flag
   :members:
   :undoc-members:
   :show-inheritance:


Creating Flags
~~~~~~~~~~~~~~

.. code-block:: python

   from litestar_flags.models import FeatureFlag
   from litestar_flags.types import FlagType, FlagStatus

   # Boolean flag (most common)
   flag = FeatureFlag(
       key="new-checkout",
       name="New Checkout Flow",
       description="Enable the redesigned checkout experience",
       flag_type=FlagType.BOOLEAN,
       status=FlagStatus.ACTIVE,
       default_enabled=False,
       tags=["checkout", "experiment"],
   )

   # String flag for variants
   flag = FeatureFlag(
       key="button-color",
       name="Button Color Experiment",
       flag_type=FlagType.STRING,
       default_value={"value": "blue"},
   )

   # JSON flag for complex configuration
   flag = FeatureFlag(
       key="feature-limits",
       name="Feature Limits",
       flag_type=FlagType.JSON,
       default_value={
           "max_items": 100,
           "rate_limit": 1000,
           "features": ["basic", "advanced"],
       },
   )


Flag Lifecycle
~~~~~~~~~~~~~~

Flags have three lifecycle statuses:

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Status
     - Description
   * - ``ACTIVE``
     - Flag is live and will be evaluated normally
   * - ``INACTIVE``
     - Flag is paused; evaluations return the default value
   * - ``ARCHIVED``
     - Flag is retired; evaluations return the default value


FlagRule
--------

Targeting rules for conditional flag evaluation based on context attributes.

.. automodule:: litestar_flags.models.rule
   :members:
   :undoc-members:
   :show-inheritance:


Rule Conditions
~~~~~~~~~~~~~~~

Rules use a JSON array of condition objects for targeting:

.. code-block:: python

   from litestar_flags.models import FlagRule

   # Target premium users
   rule = FlagRule(
       name="Premium Users",
       priority=1,  # Lower number = higher priority
       conditions=[
           {"attribute": "plan", "operator": "eq", "value": "premium"},
       ],
       serve_enabled=True,
   )

   # Target users in specific countries
   rule = FlagRule(
       name="US and Canada",
       priority=2,
       conditions=[
           {"attribute": "country", "operator": "in", "value": ["US", "CA"]},
       ],
       serve_enabled=True,
   )

   # Multiple conditions (AND logic)
   rule = FlagRule(
       name="Premium Beta Testers",
       priority=1,
       conditions=[
           {"attribute": "plan", "operator": "eq", "value": "premium"},
           {"attribute": "beta_tester", "operator": "eq", "value": True},
       ],
       serve_enabled=True,
   )


Percentage Rollouts
~~~~~~~~~~~~~~~~~~~

Use ``rollout_percentage`` for gradual rollouts:

.. code-block:: python

   # Enable for 25% of users
   rule = FlagRule(
       name="25% Rollout",
       priority=1,
       conditions=[],  # No conditions = matches all
       serve_enabled=True,
       rollout_percentage=25,  # 0-100
   )


FlagVariant
-----------

Variants for multivariate flags and A/B testing experiments.

.. automodule:: litestar_flags.models.variant
   :members:
   :undoc-members:
   :show-inheritance:


A/B Testing Setup
~~~~~~~~~~~~~~~~~

.. code-block:: python

   from litestar_flags.models import FeatureFlag, FlagVariant
   from litestar_flags.types import FlagType

   flag = FeatureFlag(
       key="checkout-experiment",
       name="Checkout A/B Test",
       flag_type=FlagType.JSON,
   )

   # 50/50 split
   variant_a = FlagVariant(
       key="control",
       name="Control Group",
       weight=50,
       value={"layout": "classic", "button_color": "blue"},
   )

   variant_b = FlagVariant(
       key="treatment",
       name="Treatment Group",
       weight=50,
       value={"layout": "modern", "button_color": "green"},
   )

   flag.variants = [variant_a, variant_b]


Multiple Variants
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Three-way split
   variants = [
       FlagVariant(key="control", name="Control", weight=33, value={"theme": "classic"}),
       FlagVariant(key="modern", name="Modern UI", weight=33, value={"theme": "modern"}),
       FlagVariant(key="minimal", name="Minimal UI", weight=34, value={"theme": "minimal"}),
   ]


FlagOverride
------------

Entity-specific overrides that take precedence over rules and defaults.

.. automodule:: litestar_flags.models.override
   :members:
   :undoc-members:
   :show-inheritance:


User Overrides
~~~~~~~~~~~~~~

.. code-block:: python

   from litestar_flags.models import FlagOverride
   from datetime import datetime, timedelta

   # Enable feature for specific user
   override = FlagOverride(
       flag_id=flag.id,
       entity_type="user",
       entity_id="user-123",
       enabled=True,
   )

   # Temporary override with expiration
   override = FlagOverride(
       flag_id=flag.id,
       entity_type="user",
       entity_id="user-456",
       enabled=True,
       expires_at=datetime.now() + timedelta(days=30),
   )


Organization Overrides
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Enable for entire organization
   override = FlagOverride(
       flag_id=flag.id,
       entity_type="organization",
       entity_id="org-789",
       enabled=True,
   )


Evaluation Priority
-------------------

When evaluating a flag, the system checks in this order:

1. **Overrides**: Entity-specific overrides take highest priority
2. **Rules**: Matching rules are evaluated in priority order (lower number first)
3. **Variants**: If no rules match but variants exist, a variant is selected
4. **Default**: The flag's default value is used as fallback

.. code-block:: text

   Request comes in with context
           |
           v
   Check for entity override -----> Override found? --> Return override value
           |
           | No override
           v
   Evaluate rules in priority order --> Rule matches? --> Return rule value
           |
           | No match
           v
   Select variant (if any) ---------> Variant selected? --> Return variant value
           |
           | No variants
           v
   Return default value
