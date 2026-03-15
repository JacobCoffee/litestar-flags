Types and Enums
===============

Core type definitions and enumerations used throughout the litestar-flags library.

Overview
--------

The library defines several enums for type safety and consistency:

- ``FlagType``: Types of values a flag can return
- ``FlagStatus``: Lifecycle status of a flag
- ``RuleOperator``: Operators for targeting rule conditions
- ``EvaluationReason``: Reasons for evaluation results
- ``ErrorCode``: Error codes for failed evaluations


API Reference
-------------

.. automodule:: litestar_flags.types
   :members:
   :undoc-members:
   :show-inheritance:


FlagType
--------

Defines the type of value a feature flag returns.

.. code-block:: python

   from litestar_flags.types import FlagType

   # Available types
   FlagType.BOOLEAN  # True/False flags
   FlagType.STRING   # Text values (variants, config strings)
   FlagType.NUMBER   # Numeric values (limits, percentages)
   FlagType.JSON     # Complex objects (configuration dictionaries)


Usage Examples
~~~~~~~~~~~~~~

.. code-block:: python

   from litestar_flags.models import FeatureFlag
   from litestar_flags.types import FlagType

   # Boolean flag (most common)
   feature_flag = FeatureFlag(
       key="dark-mode",
       name="Dark Mode",
       flag_type=FlagType.BOOLEAN,
       default_enabled=False,
   )

   # String flag for A/B testing
   variant_flag = FeatureFlag(
       key="button-color",
       name="Button Color Test",
       flag_type=FlagType.STRING,
       default_value={"value": "blue"},
   )

   # Number flag for configuration
   limit_flag = FeatureFlag(
       key="rate-limit",
       name="API Rate Limit",
       flag_type=FlagType.NUMBER,
       default_value={"value": 100},
   )

   # JSON flag for complex config
   config_flag = FeatureFlag(
       key="feature-config",
       name="Feature Configuration",
       flag_type=FlagType.JSON,
       default_value={
           "enabled_features": ["basic", "advanced"],
           "max_items": 50,
           "theme": "modern",
       },
   )


FlagStatus
----------

Defines the lifecycle status of a feature flag.

.. code-block:: python

   from litestar_flags.types import FlagStatus

   FlagStatus.ACTIVE    # Flag is live and evaluated normally
   FlagStatus.INACTIVE  # Flag is paused; returns default value
   FlagStatus.ARCHIVED  # Flag is retired; returns default value


Status Transitions
~~~~~~~~~~~~~~~~~~

.. code-block:: text

   ACTIVE <---> INACTIVE ---> ARCHIVED

   - ACTIVE: Normal operation, flag is evaluated
   - INACTIVE: Temporarily disabled, can be reactivated
   - ARCHIVED: Permanently retired, ready for cleanup


Usage Examples
~~~~~~~~~~~~~~

.. code-block:: python

   from litestar_flags.models import FeatureFlag
   from litestar_flags.types import FlagStatus

   # Create an active flag
   flag = FeatureFlag(
       key="new-feature",
       name="New Feature",
       status=FlagStatus.ACTIVE,
   )

   # Deactivate a flag
   flag.status = FlagStatus.INACTIVE

   # Archive when no longer needed
   flag.status = FlagStatus.ARCHIVED


RuleOperator
------------

Operators for targeting rule conditions.

.. code-block:: python

   from litestar_flags.types import RuleOperator

   # Equality operators
   RuleOperator.EQUALS              # "eq" - Exact match
   RuleOperator.NOT_EQUALS          # "ne" - Not equal

   # Comparison operators
   RuleOperator.GREATER_THAN        # "gt"
   RuleOperator.GREATER_THAN_OR_EQUAL  # "gte"
   RuleOperator.LESS_THAN           # "lt"
   RuleOperator.LESS_THAN_OR_EQUAL  # "lte"

   # Collection operators
   RuleOperator.IN                  # "in" - Value in list
   RuleOperator.NOT_IN              # "not_in" - Value not in list

   # String operators
   RuleOperator.CONTAINS            # "contains" - Substring match
   RuleOperator.NOT_CONTAINS        # "not_contains"
   RuleOperator.STARTS_WITH         # "starts_with"
   RuleOperator.ENDS_WITH           # "ends_with"
   RuleOperator.MATCHES             # "matches" - Regex match

   # Semantic versioning operators
   RuleOperator.SEMVER_EQ           # "semver_eq" - Semver equal
   RuleOperator.SEMVER_GT           # "semver_gt" - Semver greater than
   RuleOperator.SEMVER_LT           # "semver_lt" - Semver less than


Condition Examples
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Exact match
   {"attribute": "plan", "operator": "eq", "value": "premium"}

   # List membership
   {"attribute": "country", "operator": "in", "value": ["US", "CA", "UK"]}

   # Numeric comparison
   {"attribute": "age", "operator": "gte", "value": 18}

   # String matching
   {"attribute": "email", "operator": "ends_with", "value": "@company.com"}

   # Version targeting
   {"attribute": "app_version", "operator": "semver_gte", "value": "2.0.0"}


EvaluationReason
----------------

Indicates why a particular value was returned during evaluation.

.. code-block:: python

   from litestar_flags.types import EvaluationReason

   EvaluationReason.DEFAULT          # Flag not found or evaluation error
   EvaluationReason.STATIC           # Flag has static value (no rules)
   EvaluationReason.TARGETING_MATCH  # A targeting rule matched
   EvaluationReason.OVERRIDE         # Entity-specific override was applied
   EvaluationReason.SPLIT            # Percentage rollout or variant selection
   EvaluationReason.DISABLED         # Flag is inactive or archived
   EvaluationReason.ERROR            # Evaluation encountered an error


Usage in Evaluation Details
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   details = await client.get_boolean_details("my-feature", default=False)

   match details.reason:
       case EvaluationReason.DEFAULT:
           print("Using default value")
       case EvaluationReason.TARGETING_MATCH:
           print(f"Matched targeting rule")
       case EvaluationReason.OVERRIDE:
           print("Using entity override")
       case EvaluationReason.SPLIT:
           print(f"Selected variant: {details.variant}")
       case EvaluationReason.ERROR:
           print(f"Error: {details.error_message}")


ErrorCode
---------

Error codes for failed evaluations.

.. code-block:: python

   from litestar_flags.types import ErrorCode

   ErrorCode.FLAG_NOT_FOUND     # Flag key does not exist
   ErrorCode.TYPE_MISMATCH      # Requested type doesn't match flag type
   ErrorCode.PARSE_ERROR        # Failed to parse flag value
   ErrorCode.PROVIDER_NOT_READY # Storage backend not initialized
   ErrorCode.GENERAL_ERROR      # Unexpected error during evaluation


Handling Errors
~~~~~~~~~~~~~~~

.. code-block:: python

   details = await client.get_boolean_details("my-feature", default=False)

   if details.is_error:
       match details.error_code:
           case ErrorCode.FLAG_NOT_FOUND:
               logger.warning(f"Flag '{details.flag_key}' not found")
           case ErrorCode.TYPE_MISMATCH:
               logger.error(f"Type mismatch for '{details.flag_key}'")
           case _:
               logger.error(f"Evaluation error: {details.error_message}")


EvaluationDetails
-----------------

Detailed result of flag evaluation, combining value with metadata.
See :doc:`client` for the full ``EvaluationDetails`` API reference.


Usage Examples
~~~~~~~~~~~~~~

.. code-block:: python

   from litestar_flags import FeatureFlagClient, EvaluationContext

   client: FeatureFlagClient = ...

   # Get detailed evaluation result
   details = await client.get_boolean_details(
       "premium-feature",
       default=False,
       context=EvaluationContext(targeting_key="user-123"),
   )

   # Access properties
   print(f"Value: {details.value}")
   print(f"Reason: {details.reason}")
   print(f"Variant: {details.variant}")
   print(f"Is Error: {details.is_error}")
   print(f"Is Default: {details.is_default}")

   # Convert to dictionary for logging/debugging
   log_data = details.to_dict()


Type Safety
-----------

All enums inherit from ``str`` and ``Enum``, allowing them to be used directly
in string contexts:

.. code-block:: python

   from litestar_flags.types import FlagType, FlagStatus

   # Works with JSON serialization
   import json
   data = {"type": FlagType.BOOLEAN, "status": FlagStatus.ACTIVE}
   json.dumps(data)  # '{"type": "boolean", "status": "active"}'

   # Works with string comparison
   if flag.flag_type == "boolean":
       ...

   # Works with match statements
   match flag.status:
       case FlagStatus.ACTIVE:
           ...
       case FlagStatus.INACTIVE:
           ...
