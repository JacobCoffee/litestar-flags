Time-based Rules
================

Time-based feature flag rules enable you to control feature availability based
on temporal conditions. Whether you need to launch a feature at a specific
moment, create maintenance windows, or set up recurring schedules, time-based
rules provide the flexibility to automate flag state changes.


What are Time-based Feature Flags?
----------------------------------

Time-based feature flags extend traditional boolean flags with temporal
awareness. Instead of manually toggling features on and off, you can:

- **Schedule launches**: Enable a feature at a precise future date and time
- **Create maintenance windows**: Temporarily disable features during planned downtime
- **Implement time-limited features**: Features that automatically expire
- **Set up recurring availability**: Features enabled only during specific hours or days

Use Cases
~~~~~~~~~

**Scheduled Product Launches**
    Launch a new feature at midnight on a specific date across all time zones
    without requiring manual intervention.

**Maintenance Windows**
    Automatically disable non-critical features during scheduled database
    migrations or infrastructure updates.

**Time-limited Promotions**
    Enable promotional features only during Black Friday weekend or other
    specific time periods.

**Business Hours Features**
    Features available only during customer support hours (e.g., live chat
    widget visible only 9 AM - 5 PM).

**Gradual Time-based Rollouts**
    Combine time-based rules with percentage rollouts to increase feature
    availability over time automatically.


Date-based Conditions
---------------------

Date-based conditions allow you to enable or disable flags based on specific
points in time. The two primary operators are ``DATE_AFTER`` and ``DATE_BEFORE``.


DATE_AFTER Operator
~~~~~~~~~~~~~~~~~~~

The ``DATE_AFTER`` operator enables a flag only after a specified datetime
has passed.

.. code-block:: python

   from litestar_flags.models.flag import FeatureFlag
   from litestar_flags.models.rule import FlagRule
   from litestar_flags.types import FlagType, FlagStatus, RuleOperator

   # Create a flag for a future product launch
   launch_flag = FeatureFlag(
       key="new_checkout_v2",
       name="New Checkout Experience V2",
       description="Redesigned checkout flow launching January 15, 2025",
       flag_type=FlagType.BOOLEAN,
       status=FlagStatus.ACTIVE,
       default_enabled=False,  # Disabled by default until launch date
   )

   # Create a rule that enables the flag after the launch date
   launch_rule = FlagRule(
       name="launch_date_rule",
       description="Enable after January 15, 2025 at 9:00 AM UTC",
       priority=0,
       enabled=True,
       conditions=[
           {
               "attribute": "current_time",
               "operator": RuleOperator.DATE_AFTER.value,
               "value": "2025-01-15T09:00:00Z",
           }
       ],
       serve_enabled=True,
   )


DATE_BEFORE Operator
~~~~~~~~~~~~~~~~~~~~

The ``DATE_BEFORE`` operator enables a flag only before a specified datetime.

.. code-block:: python

   from litestar_flags.models.rule import FlagRule
   from litestar_flags.types import RuleOperator

   # Create a rule for a time-limited beta feature
   beta_expiry_rule = FlagRule(
       name="beta_expiry_rule",
       description="Beta access expires March 1, 2025",
       priority=0,
       enabled=True,
       conditions=[
           {
               "attribute": "current_time",
               "operator": RuleOperator.DATE_BEFORE.value,
               "value": "2025-03-01T00:00:00Z",
           }
       ],
       serve_enabled=True,
   )

**Combining DATE_AFTER and DATE_BEFORE**

For a feature that should only be active during a specific window:

.. code-block:: python

   # Feature active only during conference week
   conference_feature_rule = FlagRule(
       name="conference_week",
       description="Special features during PyCon 2025",
       priority=0,
       enabled=True,
       conditions=[
           {
               "attribute": "current_time",
               "operator": RuleOperator.DATE_AFTER.value,
               "value": "2025-05-14T00:00:00Z",  # Start of conference
           },
           {
               "attribute": "current_time",
               "operator": RuleOperator.DATE_BEFORE.value,
               "value": "2025-05-18T23:59:59Z",  # End of conference
           },
       ],
       serve_enabled=True,
   )


ISO 8601 Datetime Format
~~~~~~~~~~~~~~~~~~~~~~~~

All datetime values in time-based rules **must** use the ISO 8601 format.
The format follows this pattern:

.. code-block:: text

   YYYY-MM-DDTHH:MM:SSZ        # UTC timezone
   YYYY-MM-DDTHH:MM:SS+HH:MM   # Positive offset from UTC
   YYYY-MM-DDTHH:MM:SS-HH:MM   # Negative offset from UTC

Examples:

+--------------------------------+----------------------------------------+
| Format                         | Description                            |
+================================+========================================+
| ``2025-01-15T09:00:00Z``       | January 15, 2025 at 9:00 AM UTC        |
+--------------------------------+----------------------------------------+
| ``2025-01-15T09:00:00+05:30``  | January 15, 2025 at 9:00 AM IST        |
+--------------------------------+----------------------------------------+
| ``2025-01-15T09:00:00-08:00``  | January 15, 2025 at 9:00 AM PST        |
+--------------------------------+----------------------------------------+


Timezone Considerations
~~~~~~~~~~~~~~~~~~~~~~~

.. warning::

   Always use timezone-aware datetimes. Naive datetimes (without timezone info)
   can lead to unpredictable behavior depending on server configuration.

Best practices for handling timezones:

1. **Store all times in UTC**: Use the ``Z`` suffix or ``+00:00`` offset
2. **Convert on display**: Transform to user's local timezone only for display
3. **Be explicit**: When communicating with stakeholders, always specify the timezone

.. code-block:: python

   from datetime import datetime, timezone

   # Good: Explicit UTC timezone
   launch_time = datetime(2025, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
   launch_time_str = launch_time.isoformat()  # "2025-01-15T09:00:00+00:00"

   # Good: Convert from local to UTC before storing
   import zoneinfo

   local_tz = zoneinfo.ZoneInfo("America/New_York")
   local_time = datetime(2025, 1, 15, 9, 0, 0, tzinfo=local_tz)
   utc_time = local_time.astimezone(timezone.utc)

   # Bad: Naive datetime (no timezone)
   # launch_time = datetime(2025, 1, 15, 9, 0, 0)  # Avoid this!


Recurring Time Windows
----------------------

Recurring time windows enable features on a repeating schedule rather than
at fixed points in time. This is useful for features that should only be
active during specific hours, days, or periods.


Daily Schedules
~~~~~~~~~~~~~~~

Enable features during specific hours each day:

.. code-block:: python

   from litestar_flags.models.rule import FlagRule
   from litestar_flags.types import RuleOperator

   # Live chat widget available during business hours (9 AM - 6 PM UTC)
   business_hours_rule = FlagRule(
       name="business_hours",
       description="Enable during business hours",
       priority=0,
       enabled=True,
       conditions=[
           {
               "attribute": "current_time",
               "operator": RuleOperator.TIME_WINDOW.value,
               "value": {
                   "type": "daily",
                   "start_time": "09:00:00",
                   "end_time": "18:00:00",
                   "timezone": "UTC",
               },
           }
       ],
       serve_enabled=True,
   )


Weekly Schedules
~~~~~~~~~~~~~~~~

Enable features only on specific days of the week:

.. code-block:: python

   # Flash sale features active only on weekends
   weekend_sale_rule = FlagRule(
       name="weekend_sale",
       description="Weekend flash sales",
       priority=0,
       enabled=True,
       conditions=[
           {
               "attribute": "current_time",
               "operator": RuleOperator.TIME_WINDOW.value,
               "value": {
                   "type": "weekly",
                   "days_of_week": ["saturday", "sunday"],
                   "start_time": "00:00:00",
                   "end_time": "23:59:59",
                   "timezone": "America/New_York",
               },
           }
       ],
       serve_enabled=True,
   )

   # Support chat available Monday through Friday, 9 AM - 5 PM
   weekday_support_rule = FlagRule(
       name="weekday_support",
       description="Weekday support hours",
       priority=0,
       enabled=True,
       conditions=[
           {
               "attribute": "current_time",
               "operator": RuleOperator.TIME_WINDOW.value,
               "value": {
                   "type": "weekly",
                   "days_of_week": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                   "start_time": "09:00:00",
                   "end_time": "17:00:00",
                   "timezone": "America/Chicago",
               },
           }
       ],
       serve_enabled=True,
   )


Monthly Schedules
~~~~~~~~~~~~~~~~~

Enable features on specific days of the month:

.. code-block:: python

   # Payroll features active on the 1st and 15th of each month
   payroll_rule = FlagRule(
       name="payroll_days",
       description="Enhanced payroll features on pay days",
       priority=0,
       enabled=True,
       conditions=[
           {
               "attribute": "current_time",
               "operator": RuleOperator.TIME_WINDOW.value,
               "value": {
                   "type": "monthly",
                   "days_of_month": [1, 15],
                   "start_time": "00:00:00",
                   "end_time": "23:59:59",
                   "timezone": "UTC",
               },
           }
       ],
       serve_enabled=True,
   )

   # End-of-month reporting features (last 3 days)
   eom_reporting_rule = FlagRule(
       name="eom_reporting",
       description="End of month reporting tools",
       priority=0,
       enabled=True,
       conditions=[
           {
               "attribute": "current_time",
               "operator": RuleOperator.TIME_WINDOW.value,
               "value": {
                   "type": "monthly",
                   "days_of_month": [-3, -2, -1],  # Last 3 days (negative indexing)
                   "start_time": "00:00:00",
                   "end_time": "23:59:59",
                   "timezone": "UTC",
               },
           }
       ],
       serve_enabled=True,
   )


CRON Expressions
~~~~~~~~~~~~~~~~

For complex recurring schedules, use CRON expressions:

.. code-block:: python

   from litestar_flags.types import RecurrenceType

   # Complex schedule: Every Tuesday and Thursday, 2-4 PM
   training_mode_rule = FlagRule(
       name="training_mode",
       description="Training mode during scheduled sessions",
       priority=0,
       enabled=True,
       conditions=[
           {
               "attribute": "current_time",
               "operator": RuleOperator.TIME_WINDOW.value,
               "value": {
                   "type": "cron",
                   "cron_expression": "0 14-16 * * 2,4",  # Min Hour Day Month DayOfWeek
                   "timezone": "America/New_York",
               },
           }
       ],
       serve_enabled=True,
   )

**CRON Expression Format**

.. code-block:: text

   * * * * *
   | | | | |
   | | | | +-- Day of week (0-6, Sunday=0)
   | | | +---- Month (1-12)
   | | +------ Day of month (1-31)
   | +-------- Hour (0-23)
   +---------- Minute (0-59)

Common CRON patterns:

+---------------------------+------------------------------------------+
| Expression                | Description                              |
+===========================+==========================================+
| ``0 9 * * 1-5``           | 9 AM, Monday through Friday              |
+---------------------------+------------------------------------------+
| ``0 0 1 * *``             | Midnight on the 1st of each month        |
+---------------------------+------------------------------------------+
| ``0 */2 * * *``           | Every 2 hours                            |
+---------------------------+------------------------------------------+
| ``0 9-17 * * 1-5``        | Every hour from 9 AM to 5 PM, weekdays   |
+---------------------------+------------------------------------------+


Scheduled Flag Changes
----------------------

Scheduled flag changes allow you to queue future modifications to your flags.
This is useful for planned launches, deprecations, and automated rollout
progression.


Creating a Scheduled Enable/Disable
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from datetime import datetime, timezone, timedelta
   from litestar_flags.types import ChangeType

   # Schedule a flag to be enabled in 24 hours
   scheduled_change = {
       "flag_key": "new_feature",
       "change_type": ChangeType.ENABLE.value,
       "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
       "reason": "Scheduled launch after QA approval",
       "created_by": "release-manager@example.com",
   }

   # To create via storage backend (when implemented)
   # await storage.create_scheduled_change(scheduled_change)

   # Schedule a flag to be disabled for maintenance
   maintenance_change = {
       "flag_key": "api_integration",
       "change_type": ChangeType.DISABLE.value,
       "scheduled_at": "2025-02-15T02:00:00Z",  # 2 AM UTC
       "reason": "Scheduled maintenance window",
       "auto_revert_at": "2025-02-15T04:00:00Z",  # Re-enable at 4 AM UTC
       "created_by": "ops-team@example.com",
   }


Scheduling Rollout Percentage Changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Combine scheduled changes with percentage rollouts for gradual, automated
increases:

.. code-block:: python

   from datetime import datetime, timezone, timedelta
   from litestar_flags.types import ChangeType

   # Current time as base
   now = datetime.now(timezone.utc)

   # Schedule a series of rollout increases
   rollout_schedule = [
       {
           "flag_key": "new_checkout_flow",
           "change_type": ChangeType.UPDATE_ROLLOUT.value,
           "scheduled_at": now.isoformat(),
           "rollout_percentage": 5,
           "reason": "Initial rollout to 5%",
       },
       {
           "flag_key": "new_checkout_flow",
           "change_type": ChangeType.UPDATE_ROLLOUT.value,
           "scheduled_at": (now + timedelta(days=7)).isoformat(),
           "rollout_percentage": 25,
           "reason": "Increase to 25% after 1 week monitoring",
       },
       {
           "flag_key": "new_checkout_flow",
           "change_type": ChangeType.UPDATE_ROLLOUT.value,
           "scheduled_at": (now + timedelta(days=14)).isoformat(),
           "rollout_percentage": 50,
           "reason": "Increase to 50% after 2 weeks",
       },
       {
           "flag_key": "new_checkout_flow",
           "change_type": ChangeType.UPDATE_ROLLOUT.value,
           "scheduled_at": (now + timedelta(days=21)).isoformat(),
           "rollout_percentage": 100,
           "reason": "Full rollout after 3 weeks",
       },
   ]

   # Register all scheduled changes
   # for change in rollout_schedule:
   #     await storage.create_scheduled_change(change)


Viewing Pending Schedules
~~~~~~~~~~~~~~~~~~~~~~~~~

Query pending scheduled changes for visibility and auditing:

.. code-block:: python

   # List all pending scheduled changes for a flag
   # pending_changes = await storage.list_scheduled_changes(
   #     flag_key="new_checkout_flow",
   #     status="pending",
   # )

   # List all scheduled changes in a time range
   # upcoming_changes = await storage.list_scheduled_changes(
   #     scheduled_after=datetime.now(timezone.utc),
   #     scheduled_before=datetime.now(timezone.utc) + timedelta(days=7),
   # )


Canceling Scheduled Changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Remove scheduled changes that are no longer needed:

.. code-block:: python

   # Cancel a specific scheduled change by ID
   # await storage.cancel_scheduled_change(
   #     change_id="change-uuid-here",
   #     reason="Feature postponed due to dependency issues",
   #     canceled_by="product-manager@example.com",
   # )

   # Cancel all pending changes for a flag
   # await storage.cancel_all_scheduled_changes(
   #     flag_key="new_checkout_flow",
   #     reason="Feature cancelled",
   #     canceled_by="product-manager@example.com",
   # )


Gradual Rollout Phases
----------------------

For complex rollouts, litestar-flags provides a workflow-based approach with
predefined stages. This builds on the ``ScheduledRolloutWorkflow`` from the
workflows module.


Setting Up Phased Rollouts
~~~~~~~~~~~~~~~~~~~~~~~~~~

Use the ``ScheduledRolloutWorkflow`` for automated, staged rollouts:

.. code-block:: python

   from litestar_flags.contrib.workflows import ScheduledRolloutWorkflow
   from litestar_flags.contrib.workflows.types import RolloutStage

   # Get the workflow definition with custom timing
   workflow_def = ScheduledRolloutWorkflow.get_definition(
       storage=storage,
       stage_delay_minutes=60,  # 1 hour between stages
       stages=[
           RolloutStage.INITIAL,    # 5%
           RolloutStage.EARLY,      # 25%
           RolloutStage.HALF,       # 50%
           RolloutStage.MAJORITY,   # 75%
           RolloutStage.FULL,       # 100%
       ],
   )

The ``RolloutStage`` enum defines standard percentages:

+----------------------+------------+
| Stage                | Percentage |
+======================+============+
| ``INITIAL``          | 5%         |
+----------------------+------------+
| ``EARLY``            | 25%        |
+----------------------+------------+
| ``HALF``             | 50%        |
+----------------------+------------+
| ``MAJORITY``         | 75%        |
+----------------------+------------+
| ``FULL``             | 100%       |
+----------------------+------------+


Monitoring Rollout Progress
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Track the status of ongoing rollouts:

.. code-block:: python

   # Query current rollout status (conceptual example)
   # status = await workflow_engine.get_instance_status(instance_id)
   # print(f"Current stage: {status.current_step}")
   # print(f"Current percentage: {status.context.get('current_percentage')}")
   # print(f"Next stage scheduled: {status.context.get('next_stage_at')}")


Pausing and Resuming Rollouts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If issues are detected, pause the rollout workflow:

.. code-block:: python

   # Pause a rollout (workflow-based approach)
   # await workflow_engine.pause_instance(
   #     instance_id=instance_id,
   #     reason="Performance degradation detected at 25% rollout",
   #     paused_by="sre-team@example.com",
   # )

   # Resume when ready
   # await workflow_engine.resume_instance(
   #     instance_id=instance_id,
   #     reason="Performance issues resolved",
   #     resumed_by="sre-team@example.com",
   # )

For immediate rollback without pausing:

.. code-block:: python

   from litestar_flags.client import FeatureFlagClient

   async def emergency_rollback(client: FeatureFlagClient, flag_key: str) -> None:
       """Immediately disable a flag during an incident."""
       flag = await client.storage.get_flag(flag_key)
       if flag:
           flag.default_enabled = False
           flag.rollout_percentage = 0
           await client.storage.update_flag(flag)


Best Practices
--------------

Always Use Timezone-aware Datetimes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from datetime import datetime, timezone

   # CORRECT: Timezone-aware datetime
   scheduled_at = datetime(2025, 1, 15, 9, 0, 0, tzinfo=timezone.utc)

   # INCORRECT: Naive datetime - avoid this!
   # scheduled_at = datetime(2025, 1, 15, 9, 0, 0)

For consistent behavior across different server configurations and deployments,
always include timezone information. UTC is recommended for storage; convert
to local timezones only for display purposes.


Testing Scheduled Changes
~~~~~~~~~~~~~~~~~~~~~~~~~

Test time-based logic by mocking the current time:

.. code-block:: python

   import pytest
   from datetime import datetime, timezone
   from unittest.mock import patch

   @pytest.fixture
   def mock_current_time():
       """Fixture to mock current time for testing."""
       def _mock_time(year, month, day, hour=0, minute=0, second=0):
           mock_dt = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
           with patch("litestar_flags.engine.datetime") as mock_datetime:
               mock_datetime.now.return_value = mock_dt
               mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
               yield mock_dt
       return _mock_time

   async def test_scheduled_launch(mock_current_time, feature_client):
       """Test that a flag activates after its scheduled launch date."""
       # Before launch date
       with mock_current_time(2025, 1, 14, 23, 59, 59):
           assert not await feature_client.is_enabled("new_feature")

       # After launch date
       with mock_current_time(2025, 1, 15, 9, 0, 1):
           assert await feature_client.is_enabled("new_feature")

   async def test_time_window(mock_current_time, feature_client):
       """Test that a flag respects business hours."""
       # During business hours
       with mock_current_time(2025, 1, 15, 14, 0, 0):  # 2 PM
           assert await feature_client.is_enabled("business_hours_feature")

       # Outside business hours
       with mock_current_time(2025, 1, 15, 22, 0, 0):  # 10 PM
           assert not await feature_client.is_enabled("business_hours_feature")


Monitoring Scheduled Changes in Production
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Set up alerting and monitoring for scheduled changes:

1. **Alert on upcoming changes**: Notify stakeholders before scheduled launches

   .. code-block:: python

      from datetime import datetime, timezone, timedelta

      async def check_upcoming_changes(storage, hours_ahead: int = 24) -> list:
          """Find changes happening in the next N hours."""
          now = datetime.now(timezone.utc)
          upcoming = now + timedelta(hours=hours_ahead)

          # Query for upcoming changes (conceptual)
          # return await storage.list_scheduled_changes(
          #     scheduled_after=now,
          #     scheduled_before=upcoming,
          #     status="pending",
          # )
          return []

2. **Log all scheduled executions**: Track when scheduled changes are applied

3. **Monitor rollout metrics**: Track error rates and performance at each stage

4. **Set up automatic rollback triggers**: Define thresholds that pause or
   revert rollouts automatically

.. code-block:: python

   # Example: Automatic rollback based on error rate
   async def monitor_rollout_health(
       flag_key: str,
       error_threshold: float = 0.05,  # 5% error rate
   ) -> bool:
       """Check if rollout is healthy; return False if rollback needed."""
       # Get current error rate from your monitoring system
       # current_error_rate = await metrics.get_error_rate(flag_key)

       # if current_error_rate > error_threshold:
       #     await pause_rollout(flag_key)
       #     await notify_team(f"Rollout paused: {flag_key} error rate {current_error_rate}")
       #     return False

       return True


See Also
--------

- :doc:`/guides/percentage-rollouts` - Percentage-based rollout fundamentals
- :doc:`/guides/user-targeting` - Targeting specific users with rules
- :doc:`/guides/workflows` - Approval workflows and governance
- :doc:`/api/types` - Reference for ``RuleOperator``, ``ChangeType``, and other enums
