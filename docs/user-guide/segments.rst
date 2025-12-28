Segment-based Targeting
=======================

Segment-based targeting enables you to define reusable groups of users based on
shared attributes. Instead of duplicating targeting conditions across multiple
flags, you can create segments once and reference them in flag rules for
consistent, maintainable targeting.


What are Segments?
------------------

Segments are named collections of targeting conditions that define groups of
users. They provide a centralized way to manage user targeting that can be
reused across multiple feature flags.

**Key Benefits:**

- **Centralized Management**: Update targeting criteria in one place and
  all flags using that segment automatically reflect the change.
- **Reusability**: Define a segment once (e.g., "premium_users") and use it
  in any number of feature flags.
- **Consistency**: Ensure the same definition of "premium user" or "beta tester"
  is applied uniformly across your application.
- **Composability**: Nest segments to create hierarchical user groups
  (e.g., "premium_us_users" inherits from "premium_users").


Segments vs. Inline Conditions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You have two options for targeting users in flag rules:

**Inline Conditions** (within the rule):

.. code-block:: python

   rule = FlagRule(
       name="Premium Users",
       conditions=[
           {"attribute": "plan", "operator": "eq", "value": "premium"},
       ],
       serve_enabled=True,
   )

**Segment-based Conditions**:

.. code-block:: python

   rule = FlagRule(
       name="Premium Users",
       conditions=[
           {"attribute": "segment", "operator": "in_segment", "value": "premium_users"},
       ],
       serve_enabled=True,
   )

Use **inline conditions** when:

- The targeting logic is unique to a single flag
- You need quick, one-off targeting rules
- The conditions are simple and unlikely to change

Use **segments** when:

- The same user group is targeted by multiple flags
- You want to centrally manage who qualifies for a group
- You need nested or hierarchical targeting
- The targeting criteria may evolve over time


Creating Segments
-----------------

A segment is defined by a name, optional description, and a list of conditions
that must all be satisfied for a user to be considered a member.


Segment Model Fields
~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Field
     - Type
     - Description
   * - ``name``
     - ``str``
     - Unique identifier for the segment (e.g., "premium_users")
   * - ``description``
     - ``str | None``
     - Human-readable description of the segment's purpose
   * - ``conditions``
     - ``list[dict]``
     - JSON array of condition objects (same format as flag rules)
   * - ``parent_segment_id``
     - ``UUID | None``
     - Optional reference to a parent segment for nesting
   * - ``enabled``
     - ``bool``
     - Whether the segment is active (default: ``True``)


Basic Segment Creation
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from litestar_flags.models.segment import Segment

   # Create a segment for premium users
   premium_segment = Segment(
       name="premium_users",
       description="Users with an active premium subscription",
       conditions=[
           {"attribute": "plan", "operator": "eq", "value": "premium"},
       ],
   )

   # Store the segment
   created_segment = await storage.create_segment(premium_segment)


Condition Format
~~~~~~~~~~~~~~~~

Segment conditions use the same format as flag rule conditions. Each condition
is a dictionary with three keys:

- ``attribute``: The context attribute to check
- ``operator``: The comparison operator (see :ref:`condition-operators`)
- ``value``: The expected value to compare against

.. code-block:: python

   conditions = [
       # Exact match
       {"attribute": "plan", "operator": "eq", "value": "premium"},

       # List membership
       {"attribute": "country", "operator": "in", "value": ["US", "CA", "UK"]},

       # Numeric comparison
       {"attribute": "account_age_days", "operator": "gte", "value": 30},

       # String matching
       {"attribute": "email", "operator": "ends_with", "value": "@company.com"},
   ]

.. note::

   All conditions within a segment use AND logic. A user must match **all**
   conditions to be considered a member of the segment.


.. _condition-operators:

Supported Operators
~~~~~~~~~~~~~~~~~~~

All :class:`~litestar_flags.types.RuleOperator` values are supported in
segment conditions:

.. list-table::
   :widths: 20 20 60
   :header-rows: 1

   * - Operator
     - Value
     - Description
   * - Equals
     - ``eq``
     - Exact match
   * - Not Equals
     - ``ne``
     - Value does not match
   * - Greater Than
     - ``gt``
     - Numeric comparison
   * - Greater Than or Equal
     - ``gte``
     - Numeric comparison
   * - Less Than
     - ``lt``
     - Numeric comparison
   * - Less Than or Equal
     - ``lte``
     - Numeric comparison
   * - In
     - ``in``
     - Value is in the provided list
   * - Not In
     - ``not_in``
     - Value is not in the provided list
   * - Contains
     - ``contains``
     - String contains substring
   * - Not Contains
     - ``not_contains``
     - String does not contain substring
   * - Starts With
     - ``starts_with``
     - String starts with prefix
   * - Ends With
     - ``ends_with``
     - String ends with suffix
   * - Matches
     - ``matches``
     - Regular expression match
   * - Semver Equals
     - ``semver_eq``
     - Semantic version equality
   * - Semver Greater Than
     - ``semver_gt``
     - Semantic version comparison
   * - Semver Less Than
     - ``semver_lt``
     - Semantic version comparison


Common Segment Examples
~~~~~~~~~~~~~~~~~~~~~~~

**Geographic Segments:**

.. code-block:: python

   # Users in North America
   na_users = Segment(
       name="north_america_users",
       description="Users in US, Canada, or Mexico",
       conditions=[
           {"attribute": "country", "operator": "in", "value": ["US", "CA", "MX"]},
       ],
   )

   # Users NOT in restricted regions
   allowed_regions = Segment(
       name="allowed_regions",
       description="Users outside restricted regions",
       conditions=[
           {"attribute": "country", "operator": "not_in", "value": ["CN", "RU", "KP"]},
       ],
   )

**Subscription-based Segments:**

.. code-block:: python

   # Enterprise customers
   enterprise_segment = Segment(
       name="enterprise_users",
       description="Enterprise tier customers",
       conditions=[
           {"attribute": "plan", "operator": "eq", "value": "enterprise"},
       ],
   )

   # Users with active subscriptions
   active_subscribers = Segment(
       name="active_subscribers",
       description="Users with any paid subscription",
       conditions=[
           {"attribute": "plan", "operator": "in", "value": ["basic", "pro", "enterprise"]},
           {"attribute": "subscription_status", "operator": "eq", "value": "active"},
       ],
   )

**Internal User Segments:**

.. code-block:: python

   # Internal employees
   internal_users = Segment(
       name="internal_users",
       description="Company employees for internal testing",
       conditions=[
           {"attribute": "email", "operator": "ends_with", "value": "@company.com"},
       ],
   )

   # Beta testers
   beta_testers = Segment(
       name="beta_testers",
       description="Users who opted into beta program",
       conditions=[
           {"attribute": "beta_tester", "operator": "eq", "value": True},
       ],
   )

**Version-based Segments:**

.. code-block:: python

   # Users on latest app version
   latest_version_users = Segment(
       name="latest_version",
       description="Users on app version 2.0.0 or later",
       conditions=[
           {"attribute": "app_version", "operator": "semver_gte", "value": "2.0.0"},
       ],
   )


Nested Segments
---------------

Segments support parent-child relationships, enabling you to create hierarchical
user groups. A child segment inherits all conditions from its parent, and a user
must satisfy both the parent's and child's conditions to be a member.


Parent-Child Relationships
~~~~~~~~~~~~~~~~~~~~~~~~~~

When you create a nested segment:

1. The child segment specifies a ``parent_segment_id``
2. During evaluation, the system first checks if the user matches the parent
3. If the parent matches, it then checks the child's conditions
4. A user is only a member if **both** parent AND child conditions match

.. code-block:: python

   # Parent segment: All premium users
   premium_users = Segment(
       name="premium_users",
       description="All premium subscribers",
       conditions=[
           {"attribute": "plan", "operator": "eq", "value": "premium"},
       ],
   )
   premium_users = await storage.create_segment(premium_users)

   # Child segment: Premium users in the US
   premium_us_users = Segment(
       name="premium_us_users",
       description="Premium subscribers located in the United States",
       parent_segment_id=premium_users.id,  # Link to parent
       conditions=[
           {"attribute": "country", "operator": "eq", "value": "US"},
       ],
   )
   premium_us_users = await storage.create_segment(premium_us_users)


Use Cases for Nested Segments
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Geographic Refinement:**

.. code-block:: python

   # Level 1: Enterprise customers
   enterprise = Segment(
       name="enterprise",
       conditions=[{"attribute": "plan", "operator": "eq", "value": "enterprise"}],
   )
   enterprise = await storage.create_segment(enterprise)

   # Level 2: Enterprise customers in EMEA
   enterprise_emea = Segment(
       name="enterprise_emea",
       parent_segment_id=enterprise.id,
       conditions=[
           {"attribute": "region", "operator": "in", "value": ["EU", "UK", "ME", "AF"]},
       ],
   )
   enterprise_emea = await storage.create_segment(enterprise_emea)

   # Level 3: Enterprise EMEA customers with SOC2 compliance
   enterprise_emea_soc2 = Segment(
       name="enterprise_emea_soc2",
       parent_segment_id=enterprise_emea.id,
       conditions=[
           {"attribute": "soc2_compliant", "operator": "eq", "value": True},
       ],
   )

**Progressive Feature Access:**

.. code-block:: python

   # Base segment: Beta testers
   beta_testers = Segment(
       name="beta_testers",
       conditions=[{"attribute": "beta_tester", "operator": "eq", "value": True}],
   )
   beta_testers = await storage.create_segment(beta_testers)

   # Advanced beta: Beta testers who have used the feature before
   advanced_beta = Segment(
       name="advanced_beta_testers",
       parent_segment_id=beta_testers.id,
       conditions=[
           {"attribute": "feature_experience_level", "operator": "gte", "value": 3},
       ],
   )


Evaluation with Nested Segments
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The :class:`~litestar_flags.segment_evaluator.SegmentEvaluator` handles nested
segment evaluation automatically:

.. code-block:: python

   from litestar_flags.segment_evaluator import SegmentEvaluator
   from litestar_flags import EvaluationContext

   evaluator = SegmentEvaluator()

   # Check if a user is in the nested segment
   context = EvaluationContext(
       targeting_key="user-123",
       attributes={
           "plan": "premium",
           "country": "US",
       },
   )

   # This checks both parent (premium) and child (US) conditions
   is_member = await evaluator.is_in_segment(
       segment_id=premium_us_users.id,
       context=context,
       storage=storage,
   )
   # Returns True only if plan="premium" AND country="US"


.. warning::

   **Circular Reference Detection**

   The segment evaluator automatically detects and prevents circular references.
   If segment A has segment B as parent, and segment B has segment A as parent,
   a :class:`~litestar_flags.segment_evaluator.CircularSegmentReferenceError`
   will be raised during evaluation.

   .. code-block:: python

      from litestar_flags.segment_evaluator import CircularSegmentReferenceError

      try:
          await evaluator.is_in_segment(segment_id, context, storage)
      except CircularSegmentReferenceError as e:
          print(f"Circular reference detected: {e}")
          print(f"Visited chain: {e.visited_chain}")


Using Segments in Flag Rules
----------------------------

Once you have created segments, you can reference them in flag rules using the
``IN_SEGMENT`` and ``NOT_IN_SEGMENT`` operators.


IN_SEGMENT Operator
~~~~~~~~~~~~~~~~~~~

Enable a feature for users who are members of a segment:

.. code-block:: python

   from litestar_flags.models.flag import FeatureFlag
   from litestar_flags.models.rule import FlagRule
   from litestar_flags.types import FlagType, FlagStatus, RuleOperator

   # Create a flag that targets premium users via segment
   flag = FeatureFlag(
       key="premium-dashboard",
       name="Premium Dashboard",
       description="Enhanced dashboard for premium subscribers",
       flag_type=FlagType.BOOLEAN,
       status=FlagStatus.ACTIVE,
       default_enabled=False,
       rules=[
           FlagRule(
               name="Premium Users Only",
               priority=1,
               enabled=True,
               conditions=[
                   {
                       "attribute": "segment",
                       "operator": RuleOperator.IN_SEGMENT.value,
                       "value": "premium_users",  # Segment name
                   },
               ],
               serve_enabled=True,
           ),
       ],
   )

.. note::

   The ``value`` field can be either the segment **name** (string) or the
   segment **UUID** (string representation). When using names, the system
   looks up the segment by name during evaluation.


NOT_IN_SEGMENT Operator
~~~~~~~~~~~~~~~~~~~~~~~

Exclude users who are members of a segment:

.. code-block:: python

   # Disable experimental features for restricted users
   flag = FeatureFlag(
       key="experimental-api",
       name="Experimental API Access",
       flag_type=FlagType.BOOLEAN,
       status=FlagStatus.ACTIVE,
       default_enabled=True,  # Enabled by default
       rules=[
           FlagRule(
               name="Block Restricted Users",
               priority=1,
               enabled=True,
               conditions=[
                   {
                       "attribute": "segment",
                       "operator": RuleOperator.NOT_IN_SEGMENT.value,
                       "value": "restricted_users",
                   },
               ],
               serve_enabled=False,  # Disable for users in restricted segment
           ),
       ],
   )


Combining Segment and Standard Conditions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can mix segment conditions with other condition types in the same rule:

.. code-block:: python

   # Enable for premium users who are also on the latest app version
   rule = FlagRule(
       name="Premium Latest Version",
       priority=1,
       enabled=True,
       conditions=[
           {
               "attribute": "segment",
               "operator": RuleOperator.IN_SEGMENT.value,
               "value": "premium_users",
           },
           {
               "attribute": "app_version",
               "operator": RuleOperator.SEMVER_GT.value,
               "value": "2.0.0",
           },
       ],
       serve_enabled=True,
   )


Multiple Segment Conditions
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Target users who are members of multiple segments:

.. code-block:: python

   # Enable for users who are both beta testers AND enterprise customers
   rule = FlagRule(
       name="Enterprise Beta",
       priority=1,
       enabled=True,
       conditions=[
           {
               "attribute": "segment",
               "operator": RuleOperator.IN_SEGMENT.value,
               "value": "beta_testers",
           },
           {
               "attribute": "segment",
               "operator": RuleOperator.IN_SEGMENT.value,
               "value": "enterprise_users",
           },
       ],
       serve_enabled=True,
   )


Storage Backend Integration
---------------------------

All storage backends support full CRUD operations for segments.


Creating and Retrieving Segments
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from litestar_flags import MemoryStorageBackend
   from litestar_flags.models.segment import Segment

   storage = MemoryStorageBackend()

   # Create a segment
   segment = Segment(
       name="early_adopters",
       description="Users who signed up in the first month",
       conditions=[
           {"attribute": "signup_date", "operator": "date_before", "value": "2025-02-01T00:00:00Z"},
       ],
   )
   created = await storage.create_segment(segment)

   # Retrieve by ID
   segment = await storage.get_segment(created.id)

   # Retrieve by name
   segment = await storage.get_segment_by_name("early_adopters")

   # Get all segments
   all_segments = await storage.get_all_segments()


Updating Segments
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Update segment conditions
   segment = await storage.get_segment_by_name("premium_users")
   segment.conditions = [
       {"attribute": "plan", "operator": "in", "value": ["premium", "enterprise"]},
   ]
   segment.description = "Premium and Enterprise subscribers"

   updated = await storage.update_segment(segment)


Deleting Segments
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Delete a segment by ID
   deleted = await storage.delete_segment(segment.id)

   if deleted:
       print("Segment deleted successfully")
   else:
       print("Segment not found")

.. warning::

   Deleting a segment that is referenced by flag rules or as a parent of other
   segments may cause evaluation failures. Consider disabling segments instead
   of deleting them, or update dependent rules first.


Retrieving Child Segments
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Get all child segments of a parent
   children = await storage.get_child_segments(parent_segment.id)

   for child in children:
       print(f"Child segment: {child.name}")


Caching for Performance
~~~~~~~~~~~~~~~~~~~~~~~

The :class:`~litestar_flags.segment_evaluator.SegmentEvaluator` supports an
optional segment cache to avoid repeated storage lookups during evaluation:

.. code-block:: python

   from uuid import UUID
   from litestar_flags.models.segment import Segment

   # Create a cache dict
   segment_cache: dict[UUID, Segment] = {}

   # The cache is populated during evaluation
   await evaluator.is_in_segment(
       segment_id=segment.id,
       context=context,
       storage=storage,
       segment_cache=segment_cache,  # Pass the cache
   )

   # Subsequent evaluations will use cached segments
   await evaluator.is_in_segment(
       segment_id=another_segment.id,
       context=context,
       storage=storage,
       segment_cache=segment_cache,  # Same cache
   )

The cache is particularly useful when:

- Evaluating multiple flags that reference the same segments
- Evaluating nested segments (parent segments are cached)
- Processing batch evaluations for multiple users


API Reference
-------------

For complete API documentation, see:

- :class:`~litestar_flags.models.segment.Segment` - Segment model
- :class:`~litestar_flags.segment_evaluator.SegmentEvaluator` - Segment evaluation engine
- :class:`~litestar_flags.segment_evaluator.CircularSegmentReferenceError` - Error for circular references
- :class:`~litestar_flags.types.RuleOperator` - Includes ``IN_SEGMENT`` and ``NOT_IN_SEGMENT``


See Also
--------

- :doc:`/guides/user-targeting` - User targeting fundamentals
- :doc:`/guides/percentage-rollouts` - Combining segments with percentage rollouts
- :doc:`/api/models` - Complete model reference
- :doc:`/api/storage` - Storage backend operations
