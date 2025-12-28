"""Tests for workflow integration.

These tests verify the litestar-workflows integration for feature flag governance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from litestar_flags import MemoryStorageBackend
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.types import FlagStatus, FlagType

# Skip all tests if litestar-workflows is not installed
pytest.importorskip("litestar_workflows")

from litestar_workflows import WorkflowContext

from litestar_flags.contrib.workflows import (
    ApplyFlagChangeStep,
    ChangeType,
    FlagApprovalWorkflow,
    FlagChangeRequest,
    ManagerApprovalStep,
    NotifyStakeholdersStep,
    QAValidationStep,
    RolloutStage,
    RolloutStep,
    ScheduledRolloutWorkflow,
    ValidateFlagChangeStep,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def storage() -> MemoryStorageBackend:
    """Create a fresh memory storage backend."""
    return MemoryStorageBackend()


@pytest.fixture
def sample_flag() -> FeatureFlag:
    """Create a sample flag for testing."""
    return FeatureFlag(
        id=uuid4(),
        key="existing-flag",
        name="Existing Flag",
        flag_type=FlagType.BOOLEAN,
        status=FlagStatus.ACTIVE,
        default_enabled=False,
        tags=["test"],
        metadata_={},
        rules=[],
        overrides=[],
        variants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
async def storage_with_flag(storage: MemoryStorageBackend, sample_flag: FeatureFlag) -> MemoryStorageBackend:
    """Create a storage backend with a pre-existing flag."""
    await storage.create_flag(sample_flag)
    return storage


def create_context(
    data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> WorkflowContext:
    """Create a workflow context for testing."""
    return WorkflowContext(
        workflow_id=uuid4(),
        instance_id=uuid4(),
        data=data or {},
        metadata=metadata or {},
        current_step="test",
        step_history=[],
        started_at=datetime.now(UTC),
        user_id=user_id,
    )


# -----------------------------------------------------------------------------
# FlagChangeRequest Tests
# -----------------------------------------------------------------------------
class TestFlagChangeRequest:
    """Tests for FlagChangeRequest dataclass."""

    def test_create_request(self) -> None:
        """Test creating a flag change request."""
        request = FlagChangeRequest(
            flag_key="new-feature",
            change_type=ChangeType.CREATE,
            requested_by="dev@example.com",
            flag_data={"name": "New Feature", "default_enabled": False},
            reason="Launch new feature",
        )

        assert request.flag_key == "new-feature"
        assert request.change_type == ChangeType.CREATE
        assert request.requested_by == "dev@example.com"
        assert request.flag_data == {"name": "New Feature", "default_enabled": False}
        assert request.reason == "Launch new feature"
        assert request.environment == "production"  # default

    def test_to_dict(self) -> None:
        """Test serializing request to dict."""
        request = FlagChangeRequest(
            flag_key="test-flag",
            change_type=ChangeType.UPDATE,
            requested_by="admin@example.com",
            rollout_percentage=50,
        )

        data = request.to_dict()

        assert data["flag_key"] == "test-flag"
        assert data["change_type"] == "update"
        assert data["requested_by"] == "admin@example.com"
        assert data["rollout_percentage"] == 50

    def test_from_dict(self) -> None:
        """Test deserializing request from dict."""
        data = {
            "flag_key": "test-flag",
            "change_type": "delete",
            "requested_by": "admin@example.com",
            "reason": "Feature deprecated",
            "environment": "staging",
        }

        request = FlagChangeRequest.from_dict(data)

        assert request.flag_key == "test-flag"
        assert request.change_type == ChangeType.DELETE
        assert request.requested_by == "admin@example.com"
        assert request.reason == "Feature deprecated"
        assert request.environment == "staging"

    def test_roundtrip(self) -> None:
        """Test serialization roundtrip."""
        original = FlagChangeRequest(
            flag_key="roundtrip-flag",
            change_type=ChangeType.TOGGLE,
            requested_by="test@example.com",
            flag_data={"name": "Test"},
            reason="Testing",
            environment="production",
            rollout_percentage=25,
            metadata={"ticket": "JIRA-123"},
        )

        restored = FlagChangeRequest.from_dict(original.to_dict())

        assert restored.flag_key == original.flag_key
        assert restored.change_type == original.change_type
        assert restored.requested_by == original.requested_by
        assert restored.flag_data == original.flag_data
        assert restored.reason == original.reason
        assert restored.environment == original.environment
        assert restored.rollout_percentage == original.rollout_percentage
        assert restored.metadata == original.metadata


# -----------------------------------------------------------------------------
# RolloutStage Tests
# -----------------------------------------------------------------------------
class TestRolloutStage:
    """Tests for RolloutStage enum."""

    def test_percentages(self) -> None:
        """Test rollout stage percentages."""
        assert RolloutStage.INITIAL.percentage == 5
        assert RolloutStage.EARLY.percentage == 25
        assert RolloutStage.HALF.percentage == 50
        assert RolloutStage.MAJORITY.percentage == 75
        assert RolloutStage.FULL.percentage == 100

    def test_values(self) -> None:
        """Test rollout stage string values."""
        assert RolloutStage.INITIAL.value == "initial"
        assert RolloutStage.FULL.value == "full"


# -----------------------------------------------------------------------------
# ValidateFlagChangeStep Tests
# -----------------------------------------------------------------------------
class TestValidateFlagChangeStep:
    """Tests for ValidateFlagChangeStep."""

    async def test_validate_create_request_valid(self) -> None:
        """Test validating a valid create request."""
        step = ValidateFlagChangeStep()
        request = FlagChangeRequest(
            flag_key="new-feature",
            change_type=ChangeType.CREATE,
            requested_by="dev@example.com",
            flag_data={"name": "New Feature"},
        )
        context = create_context(data={"request": request.to_dict()})

        result = await step.execute(context)

        assert result["valid"] is True
        assert result["flag_key"] == "new-feature"
        assert result["change_type"] == "create"

    async def test_validate_missing_request(self) -> None:
        """Test validation fails when no request provided."""
        step = ValidateFlagChangeStep()
        context = create_context()

        result = await step.execute(context)

        assert result["valid"] is False
        assert "No change request provided" in result["error"]

    async def test_validate_empty_flag_key(self) -> None:
        """Test validation fails for empty flag key."""
        step = ValidateFlagChangeStep()
        request = FlagChangeRequest(
            flag_key="",
            change_type=ChangeType.CREATE,
            requested_by="dev@example.com",
            flag_data={"name": "Test"},
        )
        context = create_context(data={"request": request.to_dict()})

        result = await step.execute(context)

        assert result["valid"] is False
        assert "Flag key is required" in result["errors"]

    async def test_validate_invalid_flag_key_format(self) -> None:
        """Test validation fails for invalid flag key format."""
        step = ValidateFlagChangeStep()
        request = FlagChangeRequest(
            flag_key="invalid@key!",
            change_type=ChangeType.CREATE,
            requested_by="dev@example.com",
            flag_data={"name": "Test"},
        )
        context = create_context(data={"request": request.to_dict()})

        result = await step.execute(context)

        assert result["valid"] is False
        assert any("alphanumeric" in e for e in result["errors"])

    async def test_validate_valid_flag_key_with_underscore_and_hyphen(self) -> None:
        """Test validation passes for flag keys with underscores and hyphens."""
        step = ValidateFlagChangeStep()
        request = FlagChangeRequest(
            flag_key="my-new_feature",
            change_type=ChangeType.CREATE,
            requested_by="dev@example.com",
            flag_data={"name": "Test"},
        )
        context = create_context(data={"request": request.to_dict()})

        result = await step.execute(context)

        assert result["valid"] is True

    async def test_validate_create_missing_flag_data(self) -> None:
        """Test validation fails for create without flag_data."""
        step = ValidateFlagChangeStep()
        request = FlagChangeRequest(
            flag_key="new-feature",
            change_type=ChangeType.CREATE,
            requested_by="dev@example.com",
        )
        context = create_context(data={"request": request.to_dict()})

        result = await step.execute(context)

        assert result["valid"] is False
        assert any("Flag data is required" in e for e in result["errors"])

    async def test_validate_create_missing_name(self) -> None:
        """Test validation fails for create without name in flag_data."""
        step = ValidateFlagChangeStep()
        request = FlagChangeRequest(
            flag_key="new-feature",
            change_type=ChangeType.CREATE,
            requested_by="dev@example.com",
            flag_data={"default_enabled": True},  # missing 'name'
        )
        context = create_context(data={"request": request.to_dict()})

        result = await step.execute(context)

        assert result["valid"] is False
        assert any("Flag name is required" in e for e in result["errors"])

    async def test_validate_invalid_rollout_percentage(self) -> None:
        """Test validation fails for invalid rollout percentage."""
        step = ValidateFlagChangeStep()
        request = FlagChangeRequest(
            flag_key="feature",
            change_type=ChangeType.ROLLOUT,
            requested_by="dev@example.com",
            rollout_percentage=150,  # invalid
        )
        context = create_context(data={"request": request.to_dict()})

        result = await step.execute(context)

        assert result["valid"] is False
        assert any("between 0 and 100" in e for e in result["errors"])

    async def test_validate_update_nonexistent_flag(self, storage: MemoryStorageBackend) -> None:
        """Test validation fails for update of non-existent flag."""
        step = ValidateFlagChangeStep(storage=storage)
        request = FlagChangeRequest(
            flag_key="nonexistent",
            change_type=ChangeType.UPDATE,
            requested_by="dev@example.com",
            flag_data={"name": "Updated"},
        )
        context = create_context(data={"request": request.to_dict()})

        result = await step.execute(context)

        assert result["valid"] is False
        assert any("does not exist" in e for e in result["errors"])

    async def test_validate_update_existing_flag(self, storage_with_flag: MemoryStorageBackend) -> None:
        """Test validation passes for update of existing flag."""
        step = ValidateFlagChangeStep(storage=storage_with_flag)
        request = FlagChangeRequest(
            flag_key="existing-flag",
            change_type=ChangeType.UPDATE,
            requested_by="dev@example.com",
            flag_data={"name": "Updated Name"},
        )
        context = create_context(data={"request": request.to_dict()})

        result = await step.execute(context)

        assert result["valid"] is True


# -----------------------------------------------------------------------------
# ManagerApprovalStep Tests
# -----------------------------------------------------------------------------
class TestManagerApprovalStep:
    """Tests for ManagerApprovalStep."""

    def test_step_initialization(self) -> None:
        """Test step initializes with correct defaults."""
        step = ManagerApprovalStep()

        assert step.name == "manager_approval"
        assert step.title == "Manager Approval Required"
        assert step.approver_roles == ["manager", "tech_lead"]
        assert step.timeout_hours == 72

    def test_step_custom_roles(self) -> None:
        """Test step with custom approver roles."""
        step = ManagerApprovalStep(approver_roles=["director", "vp"])

        assert step.approver_roles == ["director", "vp"]

    def test_form_schema(self) -> None:
        """Test form schema is properly defined."""
        step = ManagerApprovalStep()

        assert step.form_schema is not None
        assert step.form_schema["type"] == "object"
        assert "approved" in step.form_schema["properties"]
        assert "comments" in step.form_schema["properties"]

    async def test_execute_approved(self) -> None:
        """Test executing with approval."""
        step = ManagerApprovalStep()
        context = create_context(
            data={"form_data": {"approved": True, "comments": "LGTM"}},
            user_id="manager@example.com",
        )

        result = await step.execute(context)

        assert result["approved"] is True
        assert result["approver"] == "manager@example.com"
        assert result["comments"] == "LGTM"
        assert context.get("manager_approved") is True

    async def test_execute_rejected(self) -> None:
        """Test executing with rejection."""
        step = ManagerApprovalStep()
        context = create_context(
            data={"form_data": {"approved": False, "comments": "Needs more testing"}},
            user_id="manager@example.com",
        )

        result = await step.execute(context)

        assert result["approved"] is False
        assert context.get("manager_approved") is False
        assert context.get("manager_comments") == "Needs more testing"


# -----------------------------------------------------------------------------
# QAValidationStep Tests
# -----------------------------------------------------------------------------
class TestQAValidationStep:
    """Tests for QAValidationStep."""

    def test_step_initialization(self) -> None:
        """Test step initializes correctly."""
        step = QAValidationStep()

        assert step.name == "qa_validation"
        assert step.title == "QA Validation Required"

    def test_form_schema(self) -> None:
        """Test form schema is properly defined."""
        step = QAValidationStep()

        assert step.form_schema is not None
        assert "validated" in step.form_schema["properties"]
        assert "test_results" in step.form_schema["properties"]
        assert "staging_verified" in step.form_schema["properties"]

    async def test_execute_validated(self) -> None:
        """Test executing with validation passed."""
        step = QAValidationStep()
        context = create_context(
            data={
                "form_data": {
                    "validated": True,
                    "test_results": "All tests pass",
                    "staging_verified": True,
                }
            },
            user_id="qa@example.com",
        )

        result = await step.execute(context)

        assert result["validated"] is True
        assert result["validator"] == "qa@example.com"
        assert result["test_results"] == "All tests pass"
        assert result["staging_verified"] is True
        assert context.get("qa_validated") is True

    async def test_execute_failed(self) -> None:
        """Test executing with validation failed."""
        step = QAValidationStep()
        context = create_context(
            data={
                "form_data": {
                    "validated": False,
                    "test_results": "Integration tests failing",
                }
            },
            user_id="qa@example.com",
        )

        result = await step.execute(context)

        assert result["validated"] is False
        assert context.get("qa_validated") is False


# -----------------------------------------------------------------------------
# ApplyFlagChangeStep Tests
# -----------------------------------------------------------------------------
class TestApplyFlagChangeStep:
    """Tests for ApplyFlagChangeStep."""

    async def test_create_flag(self, storage: MemoryStorageBackend) -> None:
        """Test creating a new flag."""
        step = ApplyFlagChangeStep(storage=storage)
        request = FlagChangeRequest(
            flag_key="new-feature",
            change_type=ChangeType.CREATE,
            requested_by="dev@example.com",
            flag_data={
                "name": "New Feature",
                "description": "A new feature",
                "default_enabled": True,
            },
        )
        context = create_context(data={"request": request.to_dict()})

        result = await step.execute(context)

        assert result["success"] is True
        assert result["operation"] == "create"
        assert result["flag_key"] == "new-feature"

        # Verify flag was created
        flag = await storage.get_flag("new-feature")
        assert flag is not None
        assert flag.name == "New Feature"
        assert flag.default_enabled is True

    async def test_update_flag(self, storage_with_flag: MemoryStorageBackend) -> None:
        """Test updating an existing flag."""
        step = ApplyFlagChangeStep(storage=storage_with_flag)
        request = FlagChangeRequest(
            flag_key="existing-flag",
            change_type=ChangeType.UPDATE,
            requested_by="dev@example.com",
            flag_data={"name": "Updated Name", "default_enabled": True},
        )
        context = create_context(data={"validated_request": request.to_dict()})

        result = await step.execute(context)

        assert result["success"] is True
        assert result["operation"] == "update"

        # Verify flag was updated
        flag = await storage_with_flag.get_flag("existing-flag")
        assert flag is not None
        assert flag.name == "Updated Name"
        assert flag.default_enabled is True

    async def test_delete_flag(self, storage_with_flag: MemoryStorageBackend) -> None:
        """Test deleting a flag."""
        step = ApplyFlagChangeStep(storage=storage_with_flag)
        request = FlagChangeRequest(
            flag_key="existing-flag",
            change_type=ChangeType.DELETE,
            requested_by="admin@example.com",
        )
        context = create_context(data={"request": request.to_dict()})

        result = await step.execute(context)

        assert result["success"] is True
        assert result["operation"] == "delete"

        # Verify flag was deleted
        flag = await storage_with_flag.get_flag("existing-flag")
        assert flag is None

    async def test_toggle_flag(self, storage_with_flag: MemoryStorageBackend) -> None:
        """Test toggling a flag's enabled state."""
        # Verify initial state
        flag = await storage_with_flag.get_flag("existing-flag")
        assert flag is not None
        initial_state = flag.default_enabled

        step = ApplyFlagChangeStep(storage=storage_with_flag)
        request = FlagChangeRequest(
            flag_key="existing-flag",
            change_type=ChangeType.TOGGLE,
            requested_by="dev@example.com",
        )
        context = create_context(data={"request": request.to_dict()})

        result = await step.execute(context)

        assert result["success"] is True
        assert result["operation"] == "toggle"
        assert result["new_state"] == (not initial_state)

    async def test_update_rollout(self, storage_with_flag: MemoryStorageBackend) -> None:
        """Test updating rollout percentage."""
        step = ApplyFlagChangeStep(storage=storage_with_flag)
        request = FlagChangeRequest(
            flag_key="existing-flag",
            change_type=ChangeType.ROLLOUT,
            requested_by="dev@example.com",
            rollout_percentage=50,
        )
        context = create_context(data={"request": request.to_dict()})

        result = await step.execute(context)

        assert result["success"] is True
        assert result["operation"] == "rollout"
        assert result["rollout_percentage"] == 50

        # Verify metadata was updated
        flag = await storage_with_flag.get_flag("existing-flag")
        assert flag is not None
        assert flag.metadata_["rollout_percentage"] == 50

    async def test_no_storage_available(self) -> None:
        """Test error when no storage is available."""
        step = ApplyFlagChangeStep()  # No storage provided
        request = FlagChangeRequest(
            flag_key="test",
            change_type=ChangeType.CREATE,
            requested_by="dev@example.com",
            flag_data={"name": "Test"},
        )
        context = create_context(data={"request": request.to_dict()})

        result = await step.execute(context)

        assert result["success"] is False
        assert "No storage backend available" in result["error"]


# -----------------------------------------------------------------------------
# RolloutStep Tests
# -----------------------------------------------------------------------------
class TestRolloutStep:
    """Tests for RolloutStep."""

    async def test_rollout_initial_stage(self, storage_with_flag: MemoryStorageBackend) -> None:
        """Test rolling out to initial stage (5%)."""
        step = RolloutStep(target_stage=RolloutStage.INITIAL, storage=storage_with_flag)
        context = create_context(data={"flag_key": "existing-flag"})

        result = await step.execute(context)

        assert result["success"] is True
        assert result["stage"] == "initial"
        assert result["percentage"] == 5

        # Verify flag metadata
        flag = await storage_with_flag.get_flag("existing-flag")
        assert flag is not None
        assert flag.metadata_["rollout_percentage"] == 5
        assert flag.metadata_["rollout_stage"] == "initial"

    async def test_rollout_full_stage(self, storage_with_flag: MemoryStorageBackend) -> None:
        """Test rolling out to full stage (100%)."""
        step = RolloutStep(target_stage=RolloutStage.FULL, storage=storage_with_flag)
        context = create_context(data={"flag_key": "existing-flag"})

        result = await step.execute(context)

        assert result["success"] is True
        assert result["stage"] == "full"
        assert result["percentage"] == 100

    async def test_rollout_missing_flag_key(self, storage_with_flag: MemoryStorageBackend) -> None:
        """Test error when flag_key not in context."""
        step = RolloutStep(target_stage=RolloutStage.INITIAL, storage=storage_with_flag)
        context = create_context()  # No flag_key

        result = await step.execute(context)

        assert result["success"] is False
        assert "No flag_key in context" in result["error"]

    async def test_rollout_nonexistent_flag(self, storage: MemoryStorageBackend) -> None:
        """Test error when flag doesn't exist."""
        step = RolloutStep(target_stage=RolloutStage.INITIAL, storage=storage)
        context = create_context(data={"flag_key": "nonexistent"})

        result = await step.execute(context)

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_step_name_defaults(self) -> None:
        """Test step name is auto-generated from stage."""
        step = RolloutStep(target_stage=RolloutStage.HALF)

        assert step.name == "rollout_half"
        assert "50%" in step.description


# -----------------------------------------------------------------------------
# NotifyStakeholdersStep Tests
# -----------------------------------------------------------------------------
class TestNotifyStakeholdersStep:
    """Tests for NotifyStakeholdersStep."""

    def test_default_channels(self) -> None:
        """Test default notification channels."""
        step = NotifyStakeholdersStep()

        assert step.channels == ["email"]

    def test_custom_channels(self) -> None:
        """Test custom notification channels."""
        step = NotifyStakeholdersStep(notification_channels=["slack", "pagerduty"])

        assert step.channels == ["slack", "pagerduty"]

    async def test_execute_with_request(self) -> None:
        """Test executing notification step."""
        step = NotifyStakeholdersStep(notification_channels=["email", "slack"])
        request = FlagChangeRequest(
            flag_key="test-flag",
            change_type=ChangeType.CREATE,
            requested_by="dev@example.com",
            reason="New feature launch",
        )
        context = create_context(
            data={
                "request": request.to_dict(),
                "manager_approved": True,
                "manager_approver": "manager@example.com",
                "change_applied": True,
            }
        )

        result = await step.execute(context)

        assert result["success"] is True
        assert result["channels"] == ["email", "slack"]
        assert result["notification_data"]["flag_key"] == "test-flag"
        assert result["notification_data"]["manager_approved"] is True

    async def test_execute_missing_request(self) -> None:
        """Test error when no request data found."""
        step = NotifyStakeholdersStep()
        context = create_context()

        result = await step.execute(context)

        assert result["success"] is False
        assert "No request data found" in result["error"]


# -----------------------------------------------------------------------------
# FlagApprovalWorkflow Tests
# -----------------------------------------------------------------------------
class TestFlagApprovalWorkflow:
    """Tests for FlagApprovalWorkflow."""

    def test_workflow_name(self) -> None:
        """Test workflow has correct name."""
        assert FlagApprovalWorkflow.__workflow_name__ == "flag_approval"
        assert FlagApprovalWorkflow.__workflow_version__ == "1.0.0"

    def test_get_definition_default(self) -> None:
        """Test getting default workflow definition."""
        definition = FlagApprovalWorkflow.get_definition()

        assert definition.name == "flag_approval"
        assert definition.version == "1.0.0"
        assert definition.initial_step == "validate"
        assert "rejected" in definition.terminal_steps
        assert "notify" in definition.terminal_steps

        # Check all steps are present
        assert "validate" in definition.steps
        assert "manager_approval" in definition.steps
        assert "qa_validation" in definition.steps
        assert "apply_change" in definition.steps
        assert "notify" in definition.steps
        assert "rejected" in definition.steps

    def test_get_definition_without_qa(self) -> None:
        """Test workflow without QA step."""
        definition = FlagApprovalWorkflow.get_definition(require_qa=False)

        assert "qa_validation" not in definition.steps

    def test_get_definition_without_notify(self) -> None:
        """Test workflow without notification step."""
        definition = FlagApprovalWorkflow.get_definition(notify_on_complete=False)

        assert "notify" not in definition.steps
        assert "apply_change" in definition.terminal_steps

    def test_get_definition_with_storage(self, storage: MemoryStorageBackend) -> None:
        """Test workflow passes storage to steps."""
        definition = FlagApprovalWorkflow.get_definition(storage=storage)

        # Storage should be passed to validation and apply steps
        validate_step = definition.steps["validate"]
        apply_step = definition.steps["apply_change"]

        assert validate_step._storage is storage
        assert apply_step._storage is storage


# -----------------------------------------------------------------------------
# ScheduledRolloutWorkflow Tests
# -----------------------------------------------------------------------------
class TestScheduledRolloutWorkflow:
    """Tests for ScheduledRolloutWorkflow."""

    def test_workflow_name(self) -> None:
        """Test workflow has correct name."""
        assert ScheduledRolloutWorkflow.__workflow_name__ == "scheduled_rollout"
        assert ScheduledRolloutWorkflow.__workflow_version__ == "1.0.0"

    def test_get_definition_default_stages(self) -> None:
        """Test default workflow includes all stages."""
        definition = ScheduledRolloutWorkflow.get_definition()

        assert definition.name == "scheduled_rollout"
        assert definition.initial_step == "rollout_initial"
        assert "notify_complete" in definition.terminal_steps

        # Check all default stages are present
        assert "rollout_initial" in definition.steps
        assert "rollout_early" in definition.steps
        assert "rollout_half" in definition.steps
        assert "rollout_majority" in definition.steps
        assert "rollout_full" in definition.steps

        # Check wait steps between stages
        assert "wait_before_early" in definition.steps
        assert "wait_before_half" in definition.steps
        assert "wait_before_majority" in definition.steps
        assert "wait_before_full" in definition.steps

    def test_get_definition_custom_stages(self) -> None:
        """Test workflow with custom stages."""
        custom_stages = [RolloutStage.INITIAL, RolloutStage.HALF, RolloutStage.FULL]
        definition = ScheduledRolloutWorkflow.get_definition(stages=custom_stages)

        assert "rollout_initial" in definition.steps
        assert "rollout_half" in definition.steps
        assert "rollout_full" in definition.steps
        assert "rollout_early" not in definition.steps
        assert "rollout_majority" not in definition.steps

    def test_get_definition_custom_delay(self) -> None:
        """Test workflow with custom stage delay."""
        definition = ScheduledRolloutWorkflow.get_definition(stage_delay_minutes=120)

        # Check a wait step has correct duration
        wait_step = definition.steps.get("wait_before_early")
        if wait_step:
            duration = wait_step.get_duration(None)
            assert duration.total_seconds() == 120 * 60

    def test_get_definition_with_storage(self, storage: MemoryStorageBackend) -> None:
        """Test workflow passes storage to rollout steps."""
        definition = ScheduledRolloutWorkflow.get_definition(storage=storage)

        rollout_step = definition.steps["rollout_initial"]
        assert rollout_step._storage is storage


# -----------------------------------------------------------------------------
# Integration Tests
# -----------------------------------------------------------------------------
class TestWorkflowIntegration:
    """Integration tests for workflow components."""

    async def test_full_approval_flow_simulation(self, storage: MemoryStorageBackend) -> None:
        """Test simulating a full approval flow."""
        # Step 1: Validate
        validate_step = ValidateFlagChangeStep(storage=storage)
        request = FlagChangeRequest(
            flag_key="new-feature",
            change_type=ChangeType.CREATE,
            requested_by="dev@example.com",
            flag_data={"name": "New Feature"},
        )
        context = create_context(data={"request": request.to_dict()})

        result = await validate_step.execute(context)
        assert result["valid"] is True

        # Step 2: Manager Approval
        manager_step = ManagerApprovalStep()
        context.set("form_data", {"approved": True, "comments": "Approved"})

        result = await manager_step.execute(context)
        assert result["approved"] is True

        # Step 3: QA Validation
        qa_step = QAValidationStep()
        context.set("form_data", {"validated": True, "test_results": "All pass"})

        result = await qa_step.execute(context)
        assert result["validated"] is True

        # Step 4: Apply Change
        apply_step = ApplyFlagChangeStep(storage=storage)

        result = await apply_step.execute(context)
        assert result["success"] is True

        # Step 5: Notify
        notify_step = NotifyStakeholdersStep()

        result = await notify_step.execute(context)
        assert result["success"] is True

        # Verify flag was created
        flag = await storage.get_flag("new-feature")
        assert flag is not None
        assert flag.name == "New Feature"

    async def test_approval_flow_rejected_at_validation(self, storage: MemoryStorageBackend) -> None:
        """Test approval flow rejected at validation stage."""
        validate_step = ValidateFlagChangeStep(storage=storage)
        request = FlagChangeRequest(
            flag_key="",  # Invalid - empty key
            change_type=ChangeType.CREATE,
            requested_by="dev@example.com",
            flag_data={"name": "Test"},
        )
        context = create_context(data={"request": request.to_dict()})

        result = await validate_step.execute(context)

        assert result["valid"] is False
        assert context.get("valid") is False

    async def test_approval_flow_rejected_by_manager(self) -> None:
        """Test approval flow rejected by manager."""
        manager_step = ManagerApprovalStep()
        context = create_context(
            data={"form_data": {"approved": False, "comments": "Not ready"}},
            user_id="manager@example.com",
        )

        result = await manager_step.execute(context)

        assert result["approved"] is False
        assert context.get("manager_approved") is False
