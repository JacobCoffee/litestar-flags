Approval Workflows
==================

litestar-flags integrates with `litestar-workflows <https://github.com/JacobCoffee/litestar-workflows>`_
to provide human-in-the-loop approval workflows for feature flag governance.

This is ideal for enterprise environments where feature flag changes require:

- Manager approval before going live
- QA validation in staging
- Audit trails for compliance
- Scheduled rollouts with wait periods


Installation
------------

Install the workflows extra:

.. tab-set::
   :sync-group: package-manager

   .. tab-item:: uv (Recommended)
      :sync: uv

      .. code-block:: bash

         uv add litestar-flags[workflows]

   .. tab-item:: pip
      :sync: pip

      .. code-block:: bash

         pip install litestar-flags[workflows]


Key Concepts
------------

Change Request
~~~~~~~~~~~~~~

A ``FlagChangeRequest`` encapsulates all information needed to request a change:

.. code-block:: python

   from litestar_flags.contrib.workflows import FlagChangeRequest, ChangeType

   request = FlagChangeRequest(
       flag_key="new_checkout_flow",
       change_type=ChangeType.CREATE,
       requested_by="developer@example.com",
       reason="Launch new checkout experience",
       flag_data={
           "name": "New Checkout Flow",
           "description": "Enables the redesigned checkout",
           "default_enabled": False,
       },
   )


Change Types
~~~~~~~~~~~~

The following change types are supported:

- ``ChangeType.CREATE`` - Create a new feature flag
- ``ChangeType.UPDATE`` - Modify an existing flag
- ``ChangeType.DELETE`` - Remove a flag
- ``ChangeType.TOGGLE`` - Toggle a flag's enabled state
- ``ChangeType.ROLLOUT`` - Update rollout percentage


Workflow Steps
~~~~~~~~~~~~~~

The integration provides several pre-built workflow steps:

+--------------------------+--------+------------------------------------------+
| Step                     | Type   | Purpose                                  |
+==========================+========+==========================================+
| ValidateFlagChangeStep   | Machine| Validates the change request             |
+--------------------------+--------+------------------------------------------+
| ManagerApprovalStep      | Human  | Manager reviews and approves             |
+--------------------------+--------+------------------------------------------+
| QAValidationStep         | Human  | QA validates in staging                  |
+--------------------------+--------+------------------------------------------+
| ApplyFlagChangeStep      | Machine| Executes the flag change                 |
+--------------------------+--------+------------------------------------------+
| RolloutStep              | Machine| Increases rollout percentage             |
+--------------------------+--------+------------------------------------------+
| NotifyStakeholdersStep   | Machine| Sends notifications                      |
+--------------------------+--------+------------------------------------------+


Flag Approval Workflow
----------------------

The ``FlagApprovalWorkflow`` implements a standard approval chain:

1. **Validate** - Check the request is valid
2. **Manager Approval** - Wait for manager sign-off
3. **QA Validation** - Wait for QA to verify in staging
4. **Apply Change** - Execute the flag modification
5. **Notify** - Inform stakeholders

Basic Usage
~~~~~~~~~~~

.. code-block:: python

   from litestar import Litestar
   from litestar_flags import FeatureFlagsPlugin, FeatureFlagsConfig
   from litestar_flags.contrib.workflows import FlagApprovalWorkflow
   from litestar_workflows import WorkflowPlugin, WorkflowRegistry, LocalExecutionEngine

   # Set up workflow registry
   registry = WorkflowRegistry()
   registry.register(FlagApprovalWorkflow)

   # Configure plugins
   flags_plugin = FeatureFlagsPlugin(config=FeatureFlagsConfig())
   workflow_plugin = WorkflowPlugin(registry=registry)

   app = Litestar(
       route_handlers=[...],
       plugins=[flags_plugin, workflow_plugin],
   )


Starting an Approval Workflow
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from litestar_flags.contrib.workflows import FlagChangeRequest, ChangeType

   # Create a change request
   request = FlagChangeRequest(
       flag_key="new_feature",
       change_type=ChangeType.CREATE,
       requested_by="developer@example.com",
       reason="New feature for Q1 launch",
       flag_data={
           "name": "New Feature",
           "description": "Enables the new feature",
           "default_enabled": False,
           "tags": ["q1", "frontend"],
       },
   )

   # Start the workflow
   engine = LocalExecutionEngine(registry=registry)
   instance = await engine.start_workflow(
       "flag_approval",
       initial_data={"request": request.to_dict()},
   )

   print(f"Workflow started: {instance.id}")


Customizing the Workflow
~~~~~~~~~~~~~~~~~~~~~~~~

You can customize the workflow when getting the definition:

.. code-block:: python

   # Without QA step (manager approval only)
   definition = FlagApprovalWorkflow.get_definition(
       storage=storage,
       require_qa=False,
   )

   # Without notification
   definition = FlagApprovalWorkflow.get_definition(
       storage=storage,
       notify_on_complete=False,
   )


Scheduled Rollout Workflow
--------------------------

The ``ScheduledRolloutWorkflow`` implements gradual feature rollouts with
configurable wait periods between stages.

Default Stages
~~~~~~~~~~~~~~

- **Initial**: 5% of users
- **Early**: 25% of users
- **Half**: 50% of users
- **Majority**: 75% of users
- **Full**: 100% of users

Between each stage, the workflow waits for a configurable period to allow
monitoring for issues.

Usage
~~~~~

.. code-block:: python

   from litestar_flags.contrib.workflows import ScheduledRolloutWorkflow

   # Register the workflow
   registry.register(ScheduledRolloutWorkflow)

   # Start a rollout
   instance = await engine.start_workflow(
       "scheduled_rollout",
       initial_data={"flag_key": "new_feature"},
   )


Custom Stages and Timing
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from litestar_flags.contrib.workflows import RolloutStage

   # Custom stages with 2-hour delay between each
   definition = ScheduledRolloutWorkflow.get_definition(
       storage=storage,
       stage_delay_minutes=120,
       stages=[
           RolloutStage.INITIAL,  # 5%
           RolloutStage.HALF,     # 50%
           RolloutStage.FULL,     # 100%
       ],
   )


Custom Steps
------------

You can create custom steps by extending the base classes:

Custom Machine Step
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from litestar_workflows import BaseMachineStep, WorkflowContext
   from litestar_flags.protocols import StorageBackend

   class CheckMetricsStep(BaseMachineStep):
       """Check metrics before proceeding with rollout."""

       def __init__(self, metrics_client, storage: StorageBackend | None = None):
           super().__init__(
               name="check_metrics",
               description="Verify metrics are healthy before proceeding",
           )
           self.metrics_client = metrics_client
           self._storage = storage

       async def execute(self, context: WorkflowContext) -> dict:
           flag_key = context.get("flag_key")

           # Check error rates, latency, etc.
           metrics = await self.metrics_client.get_metrics(flag_key)

           if metrics.error_rate > 0.01:  # 1% error threshold
               return {
                   "healthy": False,
                   "reason": f"Error rate too high: {metrics.error_rate:.2%}",
               }

           context.set("metrics_healthy", True)
           return {"healthy": True, "metrics": metrics.to_dict()}


Custom Human Step
~~~~~~~~~~~~~~~~~

.. code-block:: python

   from litestar_workflows import BaseHumanStep, WorkflowContext

   class SecurityReviewStep(BaseHumanStep):
       """Security team review for sensitive flags."""

       def __init__(self):
           form_schema = {
               "type": "object",
               "required": ["approved", "security_notes"],
               "properties": {
                   "approved": {
                       "type": "boolean",
                       "title": "Security Approved",
                   },
                   "security_notes": {
                       "type": "string",
                       "title": "Security Notes",
                   },
                   "risk_level": {
                       "type": "string",
                       "enum": ["low", "medium", "high"],
                       "title": "Risk Level",
                   },
               },
           }
           super().__init__(
               name="security_review",
               title="Security Review Required",
               description="Security team reviews the flag change",
               form_schema=form_schema,
           )

       async def execute(self, context: WorkflowContext) -> dict:
           form_data = context.get("form_data", {})
           approved = form_data.get("approved", False)

           context.set("security_approved", approved)
           context.set("security_notes", form_data.get("security_notes", ""))

           return {
               "approved": approved,
               "risk_level": form_data.get("risk_level", "medium"),
           }


Custom Notifications
~~~~~~~~~~~~~~~~~~~~

Override the ``NotifyStakeholdersStep`` to integrate with your notification system:

.. code-block:: python

   from litestar_flags.contrib.workflows import NotifyStakeholdersStep

   class SlackNotifyStep(NotifyStakeholdersStep):
       """Send notifications via Slack."""

       def __init__(self, slack_client):
           super().__init__(notification_channels=["slack"])
           self.slack_client = slack_client

       async def send_notification(self, data: dict, channels: list[str]) -> None:
           message = (
               f":flag-checkered: Flag Change Applied\n"
               f"*Flag:* `{data['flag_key']}`\n"
               f"*Type:* {data['change_type']}\n"
               f"*Requested by:* {data['requested_by']}\n"
               f"*Approved by:* {data.get('manager_approver', 'N/A')}"
           )

           await self.slack_client.post_message(
               channel="#feature-flags",
               text=message,
           )


Building Custom Workflows
-------------------------

You can compose your own workflows using the provided steps:

.. code-block:: python

   from litestar_workflows import WorkflowDefinition, Edge
   from litestar_flags.contrib.workflows import (
       ValidateFlagChangeStep,
       ManagerApprovalStep,
       ApplyFlagChangeStep,
   )

   class CustomFlagWorkflow:
       __workflow_name__ = "custom_flag_approval"
       __workflow_version__ = "1.0.0"

       @classmethod
       def get_definition(cls, storage):
           return WorkflowDefinition(
               name=cls.__workflow_name__,
               version=cls.__workflow_version__,
               description="Custom approval with security review",
               steps={
                   "validate": ValidateFlagChangeStep(storage=storage),
                   "security": SecurityReviewStep(),
                   "manager": ManagerApprovalStep(),
                   "apply": ApplyFlagChangeStep(storage=storage),
                   "notify": SlackNotifyStep(slack_client),
               },
               edges=[
                   Edge("validate", "security",
                        condition=lambda ctx: ctx.get("valid")),
                   Edge("security", "manager",
                        condition=lambda ctx: ctx.get("security_approved")),
                   Edge("manager", "apply",
                        condition=lambda ctx: ctx.get("manager_approved")),
                   Edge("apply", "notify"),
               ],
               initial_step="validate",
               terminal_steps={"notify"},
           )


API Reference
-------------

.. module:: litestar_flags.contrib.workflows

Types
~~~~~

.. autoclass:: ChangeType
   :members:

.. autoclass:: RolloutStage
   :members:

.. autoclass:: FlagChangeRequest
   :members:

Steps
~~~~~

.. autoclass:: ValidateFlagChangeStep
   :members:

.. autoclass:: ManagerApprovalStep
   :members:

.. autoclass:: QAValidationStep
   :members:

.. autoclass:: ApplyFlagChangeStep
   :members:

.. autoclass:: RolloutStep
   :members:

.. autoclass:: NotifyStakeholdersStep
   :members:

Workflows
~~~~~~~~~

.. autoclass:: FlagApprovalWorkflow
   :members:

.. autoclass:: ScheduledRolloutWorkflow
   :members:
