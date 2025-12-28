"""Workflow steps for feature flag operations.

This module provides workflow steps that integrate with litestar-workflows
to enable approval-based flag management, scheduled rollouts, and
auditable flag changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from litestar_workflows import BaseHumanStep, BaseMachineStep, WorkflowContext

from litestar_flags.contrib.workflows.types import ChangeType, RolloutStage
from litestar_flags.types import FlagStatus, FlagType

if TYPE_CHECKING:
    from litestar_flags.protocols import StorageBackend

__all__ = [
    "ApplyFlagChangeStep",
    "FlagChangeRequest",
    "ManagerApprovalStep",
    "NotifyStakeholdersStep",
    "QAValidationStep",
    "RolloutStep",
    "ValidateFlagChangeStep",
]

logger = logging.getLogger(__name__)


@dataclass
class FlagChangeRequest:
    """Request for a feature flag change.

    This dataclass encapsulates all information needed to request
    a change to a feature flag through an approval workflow.

    Attributes:
        flag_key: The unique key of the flag to change.
        change_type: The type of change (create, update, delete, toggle, rollout).
        requested_by: Email or ID of the person requesting the change.
        flag_data: Data for the flag (for create/update operations).
        reason: Business justification for the change.
        environment: Target environment (e.g., "production", "staging").
        rollout_percentage: Target percentage for rollout changes.
        metadata: Additional metadata for the request.

    """

    flag_key: str
    change_type: ChangeType
    requested_by: str
    flag_data: dict[str, Any] | None = None
    reason: str = ""
    environment: str = "production"
    rollout_percentage: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for workflow context storage."""
        return {
            "flag_key": self.flag_key,
            "change_type": self.change_type.value,
            "requested_by": self.requested_by,
            "flag_data": self.flag_data,
            "reason": self.reason,
            "environment": self.environment,
            "rollout_percentage": self.rollout_percentage,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlagChangeRequest:
        """Create from dictionary (from workflow context)."""
        return cls(
            flag_key=data["flag_key"],
            change_type=ChangeType(data["change_type"]),
            requested_by=data["requested_by"],
            flag_data=data.get("flag_data"),
            reason=data.get("reason", ""),
            environment=data.get("environment", "production"),
            rollout_percentage=data.get("rollout_percentage"),
            metadata=data.get("metadata", {}),
        )


class ValidateFlagChangeStep(BaseMachineStep):
    """Validate a flag change request.

    This step performs validation on the incoming change request:
    - Verifies required fields are present
    - Checks flag key format
    - Validates rollout percentages
    - For updates/deletes, verifies the flag exists
    """

    def __init__(
        self,
        storage: StorageBackend | None = None,
        name: str = "validate_flag_change",
        description: str = "Validate the flag change request",
    ) -> None:
        """Initialize with optional storage backend.

        Args:
            storage: Storage backend for flag lookups. If None, will be
                    retrieved from workflow context metadata.
            name: Step name.
            description: Step description.

        """
        super().__init__(name=name, description=description)
        self._storage = storage

    async def execute(self, context: WorkflowContext) -> dict[str, Any]:
        """Execute validation.

        Args:
            context: Workflow context containing the change request.

        Returns:
            Validation result with any error messages.

        """
        request_data = context.get("request")
        if not request_data:
            return {"valid": False, "error": "No change request provided"}

        request = FlagChangeRequest.from_dict(request_data)
        errors: list[str] = []

        # Validate flag key
        if not request.flag_key or not request.flag_key.strip():
            errors.append("Flag key is required")
        elif not request.flag_key.replace("_", "").replace("-", "").isalnum():
            errors.append("Flag key must be alphanumeric with underscores or hyphens")

        # Validate rollout percentage
        if request.rollout_percentage is not None:
            if not 0 <= request.rollout_percentage <= 100:
                errors.append("Rollout percentage must be between 0 and 100")

        # For create, validate flag_data
        if request.change_type == ChangeType.CREATE:
            if not request.flag_data:
                errors.append("Flag data is required for create operations")
            elif "name" not in request.flag_data:
                errors.append("Flag name is required in flag_data")

        # For update/delete/toggle, check flag exists
        storage = self._storage if self._storage is not None else context.metadata.get("storage")
        if storage is not None and request.change_type in (
            ChangeType.UPDATE,
            ChangeType.DELETE,
            ChangeType.TOGGLE,
            ChangeType.ROLLOUT,
        ):
            flag = await storage.get_flag(request.flag_key)
            if flag is None:
                errors.append(f"Flag '{request.flag_key}' does not exist")

        if errors:
            context.set("valid", False)
            context.set("errors", errors)
            return {"valid": False, "errors": errors}

        context.set("valid", True)
        context.set("validated_request", request.to_dict())
        return {"valid": True, "flag_key": request.flag_key, "change_type": request.change_type.value}


class ManagerApprovalStep(BaseHumanStep):
    """Human step requiring manager approval.

    This step pauses the workflow until a manager reviews and
    approves or rejects the flag change request.
    """

    def __init__(
        self,
        approver_roles: list[str] | None = None,
        timeout_hours: int = 72,
        name: str = "manager_approval",
        title: str = "Manager Approval Required",
        description: str = "Manager reviews and approves the flag change",
    ) -> None:
        """Initialize manager approval step.

        Args:
            approver_roles: List of roles that can approve (e.g., ["manager", "lead"]).
            timeout_hours: Hours before the approval request times out.
            name: Step name.
            title: Step title for display.
            description: Step description.

        """
        form_schema = {
            "type": "object",
            "required": ["approved", "comments"],
            "properties": {
                "approved": {
                    "type": "boolean",
                    "title": "Approve this change?",
                    "description": "Check to approve the flag change request",
                },
                "comments": {
                    "type": "string",
                    "title": "Comments",
                    "description": "Provide feedback or reason for approval/rejection",
                },
                "conditions": {
                    "type": "string",
                    "title": "Conditions (optional)",
                    "description": "Any conditions for the approval",
                },
            },
        }
        super().__init__(name=name, title=title, description=description, form_schema=form_schema)
        self.approver_roles = approver_roles or ["manager", "tech_lead"]
        self.timeout_hours = timeout_hours

    async def execute(self, context: WorkflowContext) -> dict[str, Any]:
        """Process the manager's decision.

        Args:
            context: Workflow context with form submission data.

        Returns:
            Approval result.

        """
        form_data = context.get("form_data", {})
        approved = form_data.get("approved", False)
        comments = form_data.get("comments", "")
        approver = context.user_id or "unknown"

        context.set("manager_approved", approved)
        context.set("manager_comments", comments)
        context.set("manager_approver", approver)
        context.set("manager_approved_at", datetime.now(UTC).isoformat())

        return {
            "approved": approved,
            "approver": approver,
            "comments": comments,
            "timestamp": datetime.now(UTC).isoformat(),
        }


class QAValidationStep(BaseHumanStep):
    """Human step for QA validation.

    This step allows QA team members to verify the flag change
    is ready for production.
    """

    def __init__(
        self,
        name: str = "qa_validation",
        title: str = "QA Validation Required",
        description: str = "QA validates the flag change in staging",
    ) -> None:
        """Initialize QA validation step.

        Args:
            name: Step name.
            title: Step title for display.
            description: Step description.

        """
        form_schema = {
            "type": "object",
            "required": ["validated", "test_results"],
            "properties": {
                "validated": {
                    "type": "boolean",
                    "title": "QA Validated",
                    "description": "Confirm testing has passed",
                },
                "test_results": {
                    "type": "string",
                    "title": "Test Results",
                    "description": "Summary of testing performed",
                },
                "staging_verified": {
                    "type": "boolean",
                    "title": "Staging Verified",
                    "description": "Confirmed working in staging environment",
                    "default": False,
                },
                "notes": {
                    "type": "string",
                    "title": "Additional Notes",
                },
            },
        }
        super().__init__(name=name, title=title, description=description, form_schema=form_schema)

    async def execute(self, context: WorkflowContext) -> dict[str, Any]:
        """Process QA validation results.

        Args:
            context: Workflow context with form submission data.

        Returns:
            Validation result.

        """
        form_data = context.get("form_data", {})
        validated = form_data.get("validated", False)
        test_results = form_data.get("test_results", "")
        validator = context.user_id or "unknown"

        context.set("qa_validated", validated)
        context.set("qa_test_results", test_results)
        context.set("qa_validator", validator)
        context.set("qa_validated_at", datetime.now(UTC).isoformat())

        return {
            "validated": validated,
            "validator": validator,
            "test_results": test_results,
            "staging_verified": form_data.get("staging_verified", False),
            "timestamp": datetime.now(UTC).isoformat(),
        }


class ApplyFlagChangeStep(BaseMachineStep):
    """Apply the approved flag change.

    This step executes the actual flag modification once all
    approvals have been obtained.
    """

    def __init__(
        self,
        storage: StorageBackend | None = None,
        name: str = "apply_flag_change",
        description: str = "Apply the approved flag change to the storage backend",
    ) -> None:
        """Initialize with optional storage backend.

        Args:
            storage: Storage backend for flag operations. If None, will be
                    retrieved from workflow context metadata.
            name: Step name.
            description: Step description.

        """
        super().__init__(name=name, description=description)
        self._storage = storage

    async def execute(self, context: WorkflowContext) -> dict[str, Any]:
        """Apply the flag change.

        Args:
            context: Workflow context with validated request.

        Returns:
            Result of the flag operation.

        """
        storage = self._storage if self._storage is not None else context.metadata.get("storage")
        if storage is None:
            return {"success": False, "error": "No storage backend available"}

        request_data = context.get("validated_request") or context.get("request")
        if not request_data:
            return {"success": False, "error": "No validated request found"}

        request = FlagChangeRequest.from_dict(request_data)

        try:
            if request.change_type == ChangeType.CREATE:
                result = await self._create_flag(storage, request)
            elif request.change_type == ChangeType.UPDATE:
                result = await self._update_flag(storage, request)
            elif request.change_type == ChangeType.DELETE:
                result = await self._delete_flag(storage, request)
            elif request.change_type == ChangeType.TOGGLE:
                result = await self._toggle_flag(storage, request)
            elif request.change_type == ChangeType.ROLLOUT:
                result = await self._update_rollout(storage, request)
            else:
                return {"success": False, "error": f"Unknown change type: {request.change_type}"}

            context.set("change_applied", True)
            context.set("change_applied_at", datetime.now(UTC).isoformat())
            return result

        except Exception as e:
            logger.exception(f"Failed to apply flag change: {e}")
            return {"success": False, "error": str(e)}

    async def _create_flag(
        self,
        storage: StorageBackend,
        request: FlagChangeRequest,
    ) -> dict[str, Any]:
        """Create a new flag."""
        from litestar_flags.models import FeatureFlag

        flag_data = request.flag_data or {}
        flag = FeatureFlag(
            key=request.flag_key,
            name=flag_data.get("name", request.flag_key),
            description=flag_data.get("description"),
            flag_type=FlagType(flag_data.get("flag_type", "boolean")),
            status=FlagStatus(flag_data.get("status", "active")),
            default_enabled=flag_data.get("default_enabled", False),
            default_value=flag_data.get("default_value"),
            tags=flag_data.get("tags", []),
            metadata_=flag_data.get("metadata", {}),
        )

        created = await storage.create_flag(flag)
        return {
            "success": True,
            "operation": "create",
            "flag_key": created.key,
            "flag_id": str(created.id),
        }

    async def _update_flag(
        self,
        storage: StorageBackend,
        request: FlagChangeRequest,
    ) -> dict[str, Any]:
        """Update an existing flag."""
        flag = await storage.get_flag(request.flag_key)
        if not flag:
            return {"success": False, "error": f"Flag '{request.flag_key}' not found"}

        flag_data = request.flag_data or {}
        if "name" in flag_data:
            flag.name = flag_data["name"]
        if "description" in flag_data:
            flag.description = flag_data["description"]
        if "default_enabled" in flag_data:
            flag.default_enabled = flag_data["default_enabled"]
        if "default_value" in flag_data:
            flag.default_value = flag_data["default_value"]
        if "status" in flag_data:
            flag.status = FlagStatus(flag_data["status"])
        if "tags" in flag_data:
            flag.tags = flag_data["tags"]

        updated = await storage.update_flag(flag)
        return {
            "success": True,
            "operation": "update",
            "flag_key": updated.key,
        }

    async def _delete_flag(
        self,
        storage: StorageBackend,
        request: FlagChangeRequest,
    ) -> dict[str, Any]:
        """Delete a flag."""
        deleted = await storage.delete_flag(request.flag_key)
        return {
            "success": deleted,
            "operation": "delete",
            "flag_key": request.flag_key,
        }

    async def _toggle_flag(
        self,
        storage: StorageBackend,
        request: FlagChangeRequest,
    ) -> dict[str, Any]:
        """Toggle a flag's enabled state."""
        flag = await storage.get_flag(request.flag_key)
        if not flag:
            return {"success": False, "error": f"Flag '{request.flag_key}' not found"}

        flag.default_enabled = not flag.default_enabled
        updated = await storage.update_flag(flag)
        return {
            "success": True,
            "operation": "toggle",
            "flag_key": updated.key,
            "new_state": updated.default_enabled,
        }

    async def _update_rollout(
        self,
        storage: StorageBackend,
        request: FlagChangeRequest,
    ) -> dict[str, Any]:
        """Update rollout percentage via flag rules."""
        flag = await storage.get_flag(request.flag_key)
        if not flag:
            return {"success": False, "error": f"Flag '{request.flag_key}' not found"}

        # Update metadata with rollout info
        flag.metadata_["rollout_percentage"] = request.rollout_percentage
        flag.metadata_["rollout_updated_at"] = datetime.now(UTC).isoformat()

        updated = await storage.update_flag(flag)
        return {
            "success": True,
            "operation": "rollout",
            "flag_key": updated.key,
            "rollout_percentage": request.rollout_percentage,
        }


class RolloutStep(BaseMachineStep):
    """Execute a rollout stage increase.

    This step is used in gradual rollout workflows to increase
    the rollout percentage in stages.
    """

    def __init__(
        self,
        target_stage: RolloutStage,
        storage: StorageBackend | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        """Initialize rollout step.

        Args:
            target_stage: The rollout stage to reach.
            storage: Storage backend for flag operations.
            name: Step name (defaults to rollout_{stage}).
            description: Step description.

        """
        step_name = name or f"rollout_{target_stage.value}"
        step_desc = description or f"Increase rollout to {target_stage.percentage}%"
        super().__init__(name=step_name, description=step_desc)
        self.target_stage = target_stage
        self._storage = storage

    async def execute(self, context: WorkflowContext) -> dict[str, Any]:
        """Execute the rollout stage increase.

        Args:
            context: Workflow context.

        Returns:
            Rollout result.

        """
        storage = self._storage if self._storage is not None else context.metadata.get("storage")
        if storage is None:
            return {"success": False, "error": "No storage backend available"}

        flag_key = context.get("flag_key")
        if not flag_key:
            return {"success": False, "error": "No flag_key in context"}

        flag = await storage.get_flag(flag_key)
        if not flag:
            return {"success": False, "error": f"Flag '{flag_key}' not found"}

        percentage = self.target_stage.percentage
        flag.metadata_["rollout_percentage"] = percentage
        flag.metadata_["rollout_stage"] = self.target_stage.value
        flag.metadata_["rollout_updated_at"] = datetime.now(UTC).isoformat()

        await storage.update_flag(flag)

        context.set("current_rollout_stage", self.target_stage.value)
        context.set("current_rollout_percentage", percentage)

        return {
            "success": True,
            "stage": self.target_stage.value,
            "percentage": percentage,
            "flag_key": flag_key,
        }


class NotifyStakeholdersStep(BaseMachineStep):
    """Send notifications to stakeholders.

    This step notifies relevant parties about flag changes.
    Override the `send_notification` method to integrate with
    your notification system.
    """

    def __init__(
        self,
        notification_channels: list[str] | None = None,
        name: str = "notify_stakeholders",
        description: str = "Notify stakeholders about the flag change",
    ) -> None:
        """Initialize notification step.

        Args:
            notification_channels: Channels to notify (e.g., ["email", "slack"]).
            name: Step name.
            description: Step description.

        """
        super().__init__(name=name, description=description)
        self.channels = notification_channels or ["email"]

    async def execute(self, context: WorkflowContext) -> dict[str, Any]:
        """Send notifications.

        Args:
            context: Workflow context.

        Returns:
            Notification result.

        """
        request_data = context.get("validated_request") or context.get("request")
        if not request_data:
            return {"success": False, "error": "No request data found"}

        request = FlagChangeRequest.from_dict(request_data)

        notification_data = {
            "flag_key": request.flag_key,
            "change_type": request.change_type.value,
            "requested_by": request.requested_by,
            "environment": request.environment,
            "reason": request.reason,
            "manager_approved": context.get("manager_approved", False),
            "manager_approver": context.get("manager_approver"),
            "qa_validated": context.get("qa_validated", False),
            "qa_validator": context.get("qa_validator"),
            "change_applied": context.get("change_applied", False),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Override this method in subclasses to implement actual notifications
        await self.send_notification(notification_data, self.channels)

        return {
            "success": True,
            "channels": self.channels,
            "notification_data": notification_data,
        }

    async def send_notification(
        self,
        data: dict[str, Any],
        channels: list[str],
    ) -> None:
        """Send the notification.

        Override this method to integrate with your notification system.

        Args:
            data: Notification data.
            channels: Channels to send to.

        """
        logger.info(f"Flag change notification: {data} via {channels}")
