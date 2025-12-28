"""Pre-built workflows for feature flag governance.

This module provides ready-to-use workflow definitions for common
feature flag management scenarios.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from litestar_workflows import BaseMachineStep, Edge, TimerStep, WorkflowContext, WorkflowDefinition

from litestar_flags.contrib.workflows.steps import (
    ApplyFlagChangeStep,
    ManagerApprovalStep,
    NotifyStakeholdersStep,
    QAValidationStep,
    RolloutStep,
    ValidateFlagChangeStep,
)
from litestar_flags.contrib.workflows.types import RolloutStage

if TYPE_CHECKING:
    from litestar_flags.protocols import StorageBackend

__all__ = [
    "FlagApprovalWorkflow",
    "ScheduledRolloutWorkflow",
]


class _RejectedStep(BaseMachineStep):
    """Internal step for rejected changes.

    This is a terminal step that marks the workflow as rejected
    without performing any actions.
    """

    def __init__(self) -> None:
        """Initialize rejected step."""
        super().__init__(name="rejected", description="Change request was rejected")

    async def execute(self, context: WorkflowContext) -> dict[str, Any]:
        """Mark as rejected."""
        return {
            "rejected": True,
            "reason": context.get("manager_comments") or context.get("errors", ["Unknown reason"]),
        }


class FlagApprovalWorkflow:
    """Workflow for approving feature flag changes.

    This workflow implements a standard approval process:
    1. Validate the change request
    2. Manager approval (human step)
    3. QA validation (human step)
    4. Apply the change
    5. Notify stakeholders

    Example:
        Registering the workflow::

            from litestar_workflows import WorkflowRegistry
            from litestar_flags.contrib.workflows import FlagApprovalWorkflow

            registry = WorkflowRegistry()
            registry.register(FlagApprovalWorkflow)

        Starting an approval workflow::

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

            instance = await engine.start_workflow(
                "flag_approval",
                initial_data={"request": request.to_dict()},
            )

    """

    __workflow_name__ = "flag_approval"
    __workflow_version__ = "1.0.0"
    __workflow_description__ = "Approval workflow for feature flag changes"

    def __init__(self, storage: StorageBackend | None = None) -> None:
        """Initialize the workflow.

        Args:
            storage: Storage backend for flag operations.

        """
        self._storage = storage

    @classmethod
    def get_definition(
        cls,
        storage: StorageBackend | None = None,
        require_qa: bool = True,
        notify_on_complete: bool = True,
    ) -> WorkflowDefinition:
        """Get the workflow definition.

        Args:
            storage: Storage backend for flag operations.
            require_qa: Whether to require QA validation step.
            notify_on_complete: Whether to notify stakeholders on completion.

        Returns:
            The workflow definition.

        """
        steps: dict[str, Any] = {
            "validate": ValidateFlagChangeStep(storage=storage),
            "manager_approval": ManagerApprovalStep(),
            "apply_change": ApplyFlagChangeStep(storage=storage),
            "rejected": _RejectedStep(),
        }

        edges = [
            Edge("validate", "manager_approval", condition=lambda ctx: ctx.get("valid", False)),
            Edge("validate", "rejected", condition=lambda ctx: not ctx.get("valid", False)),
        ]

        terminal_steps = {"rejected"}

        if require_qa:
            steps["qa_validation"] = QAValidationStep()
            edges.extend(
                [
                    Edge("manager_approval", "qa_validation", condition=lambda ctx: ctx.get("manager_approved", False)),
                    Edge("manager_approval", "rejected", condition=lambda ctx: not ctx.get("manager_approved", False)),
                    Edge("qa_validation", "apply_change", condition=lambda ctx: ctx.get("qa_validated", False)),
                    Edge("qa_validation", "rejected", condition=lambda ctx: not ctx.get("qa_validated", False)),
                ]
            )
        else:
            edges.extend(
                [
                    Edge("manager_approval", "apply_change", condition=lambda ctx: ctx.get("manager_approved", False)),
                    Edge("manager_approval", "rejected", condition=lambda ctx: not ctx.get("manager_approved", False)),
                ]
            )

        if notify_on_complete:
            steps["notify"] = NotifyStakeholdersStep()
            edges.append(Edge("apply_change", "notify"))
            terminal_steps.add("notify")
        else:
            terminal_steps.add("apply_change")

        return WorkflowDefinition(
            name=cls.__workflow_name__,
            version=cls.__workflow_version__,
            description=cls.__workflow_description__,
            steps=steps,
            edges=edges,
            initial_step="validate",
            terminal_steps=terminal_steps,
        )


class ScheduledRolloutWorkflow:
    """Workflow for gradual feature flag rollouts.

    This workflow implements a staged rollout process:
    1. Start at 5% (INITIAL stage)
    2. Wait, then increase to 25% (EARLY stage)
    3. Wait, then increase to 50% (HALF stage)
    4. Wait, then increase to 75% (MAJORITY stage)
    5. Wait, then increase to 100% (FULL stage)

    Between each stage, there's a configurable wait period to
    monitor for issues before proceeding.

    Example:
        Starting a rollout workflow::

            instance = await engine.start_workflow(
                "scheduled_rollout",
                initial_data={
                    "flag_key": "new_feature",
                },
            )

    """

    __workflow_name__ = "scheduled_rollout"
    __workflow_version__ = "1.0.0"
    __workflow_description__ = "Gradual rollout workflow with staged percentages"

    @classmethod
    def get_definition(
        cls,
        storage: StorageBackend | None = None,
        stage_delay_minutes: int = 60,
        stages: list[RolloutStage] | None = None,
    ) -> WorkflowDefinition:
        """Get the workflow definition.

        Args:
            storage: Storage backend for flag operations.
            stage_delay_minutes: Minutes to wait between rollout stages.
            stages: List of rollout stages to execute. Defaults to all stages.

        Returns:
            The workflow definition.

        """
        if stages is None:
            stages = [
                RolloutStage.INITIAL,
                RolloutStage.EARLY,
                RolloutStage.HALF,
                RolloutStage.MAJORITY,
                RolloutStage.FULL,
            ]

        steps: dict[str, Any] = {}
        edges: list[Edge] = []

        prev_step = None
        for stage in stages:
            step_name = f"rollout_{stage.value}"
            steps[step_name] = RolloutStep(target_stage=stage, storage=storage)

            if prev_step:
                # Add wait step between stages
                wait_name = f"wait_before_{stage.value}"
                steps[wait_name] = TimerStep(
                    name=wait_name,
                    duration=timedelta(minutes=stage_delay_minutes),
                    description=f"Wait before {stage.value} rollout ({stage.percentage}%)",
                )
                edges.append(Edge(prev_step, wait_name))
                edges.append(Edge(wait_name, step_name))

            prev_step = step_name

        # Add notification at the end
        steps["notify_complete"] = NotifyStakeholdersStep(
            notification_channels=["email", "slack"],
        )
        if prev_step:
            edges.append(Edge(prev_step, "notify_complete"))

        return WorkflowDefinition(
            name=cls.__workflow_name__,
            version=cls.__workflow_version__,
            description=cls.__workflow_description__,
            steps=steps,
            edges=edges,
            initial_step=f"rollout_{stages[0].value}",
            terminal_steps={"notify_complete"},
        )
