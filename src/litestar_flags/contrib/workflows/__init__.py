"""Workflow integration for feature flag governance.

This module provides workflow steps and pre-built workflows for managing
feature flag changes with approval processes, scheduled rollouts, and
audit trails.

Requires the `workflows` extra: `pip install litestar-flags[workflows]`

Example:
    Using the flag approval workflow::

        from litestar import Litestar
        from litestar_flags import FeatureFlagsPlugin, FeatureFlagsConfig
        from litestar_flags.contrib.workflows import (
            FlagApprovalWorkflow,
            FlagChangeRequest,
        )
        from litestar_workflows import WorkflowPlugin, WorkflowRegistry

        # Register the workflow
        registry = WorkflowRegistry()
        registry.register(FlagApprovalWorkflow)

        app = Litestar(
            plugins=[
                FeatureFlagsPlugin(config=FeatureFlagsConfig()),
                WorkflowPlugin(registry=registry),
            ],
        )

    Creating a flag change request::

        from litestar_flags.contrib.workflows import FlagChangeRequest, ChangeType

        request = FlagChangeRequest(
            flag_key="new_feature",
            change_type=ChangeType.CREATE,
            requested_by="developer@example.com",
            flag_data={
                "name": "New Feature",
                "description": "Enables the new feature",
                "default_enabled": False,
            },
        )

"""

from __future__ import annotations

from litestar_flags.contrib.workflows.steps import (
    ApplyFlagChangeStep,
    FlagChangeRequest,
    ManagerApprovalStep,
    NotifyStakeholdersStep,
    QAValidationStep,
    RolloutStep,
    ValidateFlagChangeStep,
)
from litestar_flags.contrib.workflows.types import ChangeType, RolloutStage
from litestar_flags.contrib.workflows.workflows import (
    FlagApprovalWorkflow,
    ScheduledRolloutWorkflow,
)

__all__ = [
    "ApplyFlagChangeStep",
    "ChangeType",
    "FlagApprovalWorkflow",
    "FlagChangeRequest",
    "ManagerApprovalStep",
    "NotifyStakeholdersStep",
    "QAValidationStep",
    "RolloutStage",
    "RolloutStep",
    "ScheduledRolloutWorkflow",
    "ValidateFlagChangeStep",
]
