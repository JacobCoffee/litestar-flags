"""Tests for Phase 10: Time-based Rules.

This module tests time-based feature flag functionality including:
- DATE_AFTER and DATE_BEFORE operators
- TimeBasedRuleEvaluator for schedule-based flag evaluation
- ScheduleProcessor for processing pending scheduled changes
- RolloutPhase for gradual rollout phases
- Time-based model creation and validation
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from datetime import time as dt_time
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from litestar_flags import EvaluationContext, MemoryStorageBackend
from litestar_flags.engine import EvaluationEngine
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.models.rule import FlagRule
from litestar_flags.types import FlagStatus, FlagType, RuleOperator

if TYPE_CHECKING:
    pass


# =============================================================================
# TIME-BASED MODELS
# =============================================================================


class ScheduleType:
    """Schedule type constants for time-based rules."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ONE_TIME = "one_time"


class ChangeType:
    """Change type constants for scheduled flag changes."""

    ENABLE = "enable"
    DISABLE = "disable"
    UPDATE_ROLLOUT = "update_rollout"
    UPDATE_VALUE = "update_value"


class ScheduledFlagChange:
    """Model for scheduled flag changes.

    Represents a scheduled change to a feature flag that will be
    executed at a specific time.
    """

    def __init__(
        self,
        change_id: str | None = None,
        flag_id: str | None = None,
        change_type: str = ChangeType.ENABLE,
        scheduled_at: datetime | None = None,
        executed_at: datetime | None = None,
        new_value: Any = None,
        new_rollout_percentage: int | None = None,
        description: str | None = None,
        created_by: str | None = None,
    ) -> None:
        self.id = change_id or str(uuid4())
        self.flag_id = flag_id
        self.change_type = change_type
        self.scheduled_at = scheduled_at
        self.executed_at = executed_at
        self.new_value = new_value
        self.new_rollout_percentage = new_rollout_percentage
        self.description = description
        self.created_by = created_by

    def is_due(self, current_time: datetime | None = None) -> bool:
        """Check if this change is due for execution."""
        if self.executed_at is not None:
            return False
        if self.scheduled_at is None:
            return False
        now = current_time or datetime.now(UTC)
        return now >= self.scheduled_at


class TimeSchedule:
    """Model for recurring time schedules.

    Represents a schedule for when a flag should be active,
    such as daily time windows or specific days of the week.
    """

    def __init__(
        self,
        schedule_id: str | None = None,
        flag_id: str | None = None,
        schedule_type: str = ScheduleType.DAILY,
        start_time: dt_time | None = None,
        end_time: dt_time | None = None,
        days_of_week: list[int] | None = None,
        days_of_month: list[int] | None = None,
        timezone: str = "UTC",
        enabled: bool = True,
    ) -> None:
        self.id = schedule_id or str(uuid4())
        self.flag_id = flag_id
        self.schedule_type = schedule_type
        self.start_time = start_time
        self.end_time = end_time
        self.days_of_week = days_of_week  # 0=Monday, 6=Sunday
        self.days_of_month = days_of_month
        self.timezone = timezone
        self.enabled = enabled


class RolloutPhase:
    """Model for gradual rollout phases.

    Represents a phase in a gradual rollout, where the flag
    is progressively enabled for more users over time.
    """

    def __init__(
        self,
        phase_id: str | None = None,
        flag_id: str | None = None,
        phase_number: int = 1,
        percentage: int = 0,
        start_at: datetime | None = None,
        completed_at: datetime | None = None,
        description: str | None = None,
    ) -> None:
        self.id = phase_id or str(uuid4())
        self.flag_id = flag_id
        self.phase_number = phase_number
        self.percentage = percentage
        self.start_at = start_at
        self.completed_at = completed_at
        self.description = description

    def is_active(self, current_time: datetime | None = None) -> bool:
        """Check if this phase is currently active."""
        now = current_time or datetime.now(UTC)
        if self.start_at is None:
            return False
        if now < self.start_at:
            return False
        return self.completed_at is None


# =============================================================================
# TIME-BASED EVALUATOR
# =============================================================================


class TimeBasedRuleEvaluator:
    """Evaluator for time-based rules.

    Handles evaluation of time-based conditions including:
    - Date comparisons (before/after)
    - Time window checks
    - Schedule-based activation
    """

    def __init__(self, default_timezone: str = "UTC") -> None:
        self.default_timezone = default_timezone

    def is_in_schedule(
        self,
        schedule: TimeSchedule,
        current_time: datetime | None = None,
    ) -> bool:
        """Check if the current time falls within a schedule.

        Args:
            schedule: The time schedule to check.
            current_time: Optional current time (defaults to now).

        Returns:
            True if currently within the schedule window.
        """
        if not schedule.enabled:
            return False

        now = current_time or datetime.now(UTC)

        # Convert to schedule's timezone
        try:
            tz = ZoneInfo(schedule.timezone)
            local_now = now.astimezone(tz)
        except Exception:
            local_now = now

        current_time_only = local_now.time()
        current_day_of_week = local_now.weekday()
        current_day_of_month = local_now.day

        # Check schedule type
        if schedule.schedule_type == ScheduleType.DAILY:
            return self._is_in_time_window(
                current_time_only,
                schedule.start_time,
                schedule.end_time,
            )

        elif schedule.schedule_type == ScheduleType.WEEKLY:
            if schedule.days_of_week is None:
                return False
            if current_day_of_week not in schedule.days_of_week:
                return False
            return self._is_in_time_window(
                current_time_only,
                schedule.start_time,
                schedule.end_time,
            )

        elif schedule.schedule_type == ScheduleType.MONTHLY:
            if schedule.days_of_month is None:
                return False
            if current_day_of_month not in schedule.days_of_month:
                return False
            return self._is_in_time_window(
                current_time_only,
                schedule.start_time,
                schedule.end_time,
            )

        return False

    def _is_in_time_window(
        self,
        current: dt_time,
        start: dt_time | None,
        end: dt_time | None,
    ) -> bool:
        """Check if current time is within a time window."""
        if start is None or end is None:
            return True

        # Handle overnight windows (e.g., 22:00 - 06:00)
        if start <= end:
            return start <= current <= end
        else:
            return current >= start or current <= end

    def evaluate_date_condition(
        self,
        operator: str,
        actual_date: datetime | str | None,
        expected_date: datetime | str | None,
    ) -> bool:
        """Evaluate a date-based condition.

        Args:
            operator: The comparison operator (date_after, date_before).
            actual_date: The actual date value (can be ISO string or datetime).
            expected_date: The expected date to compare against.

        Returns:
            True if the condition is satisfied.
        """
        actual = self._parse_date(actual_date)
        expected = self._parse_date(expected_date)

        if actual is None or expected is None:
            return False

        if operator == "date_after":
            return actual > expected
        elif operator == "date_before":
            return actual < expected

        return False

    def _parse_date(self, value: datetime | str | None) -> datetime | None:
        """Parse a date value from various formats."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                # Try ISO 8601 format
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None


# =============================================================================
# SCHEDULE PROCESSOR
# =============================================================================


class ScheduleProcessor:
    """Processor for scheduled flag changes.

    Handles execution of pending scheduled changes to feature flags.
    """

    def __init__(self, storage: MemoryStorageBackend) -> None:
        self.storage = storage
        self._pending_changes: list[ScheduledFlagChange] = []

    def add_scheduled_change(self, change: ScheduledFlagChange) -> None:
        """Add a scheduled change to be processed."""
        self._pending_changes.append(change)

    async def process_pending_changes(
        self,
        current_time: datetime | None = None,
    ) -> list[ScheduledFlagChange]:
        """Process all pending changes that are due.

        Args:
            current_time: Optional current time for testing.

        Returns:
            List of executed changes.
        """
        now = current_time or datetime.now(UTC)
        executed = []

        for change in self._pending_changes[:]:
            if change.is_due(now):
                await self._execute_change(change, now)
                executed.append(change)
                self._pending_changes.remove(change)

        return executed

    async def _execute_change(
        self,
        change: ScheduledFlagChange,
        execution_time: datetime,
    ) -> None:
        """Execute a scheduled change."""
        if change.flag_id is None:
            return

        # Get the flag by ID from the internal dict
        # Note: MemoryStorageBackend uses _flags_by_id internally
        try:
            flag_uuid = UUID(change.flag_id) if isinstance(change.flag_id, str) else change.flag_id
            flag = self.storage._flags_by_id.get(flag_uuid)
        except (ValueError, TypeError):
            flag = None

        if flag is None:
            return

        # Apply the change based on type
        if change.change_type == ChangeType.ENABLE:
            flag.status = FlagStatus.ACTIVE
            flag.default_enabled = True
        elif change.change_type == ChangeType.DISABLE:
            flag.status = FlagStatus.INACTIVE
            flag.default_enabled = False
        elif change.change_type == ChangeType.UPDATE_ROLLOUT:
            if change.new_rollout_percentage is not None and flag.rules:
                flag.rules[0].rollout_percentage = change.new_rollout_percentage
        elif change.change_type == ChangeType.UPDATE_VALUE:
            if change.new_value is not None:
                flag.default_value = change.new_value

        # Update the flag
        await self.storage.update_flag(flag)

        # Mark as executed
        change.executed_at = execution_time


# =============================================================================
# EXTENDED ENGINE WITH DATE OPERATORS
# =============================================================================


class TimeAwareEvaluationEngine(EvaluationEngine):
    """Extended evaluation engine with time-based operators."""

    def __init__(self) -> None:
        super().__init__()
        self._time_evaluator = TimeBasedRuleEvaluator()

    def _evaluate_condition(
        self,
        actual: Any,
        operator: RuleOperator | str,
        expected: Any,
    ) -> bool:
        """Evaluate a single condition, including time-based operators."""
        # Handle string operators for time-based rules
        op_str = operator.value if isinstance(operator, RuleOperator) else str(operator)

        if op_str in ("date_after", "date_before"):
            return self._time_evaluator.evaluate_date_condition(
                op_str, actual, expected
            )

        # Fall back to parent implementation
        if isinstance(operator, str):
            try:
                operator = RuleOperator(operator)
            except ValueError:
                return False

        return super()._evaluate_condition(actual, operator, expected)


# =============================================================================
# TESTS: DATE OPERATORS
# =============================================================================


class TestDateOperators:
    """Tests for DATE_AFTER and DATE_BEFORE operators."""

    @pytest.fixture
    def time_evaluator(self) -> TimeBasedRuleEvaluator:
        return TimeBasedRuleEvaluator()

    @pytest.fixture
    def engine(self) -> TimeAwareEvaluationEngine:
        return TimeAwareEvaluationEngine()

    @pytest.mark.asyncio
    async def test_date_after_operator(self, time_evaluator: TimeBasedRuleEvaluator) -> None:
        """Test DATE_AFTER operator matches future dates."""
        reference_date = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        # Date after reference should return True
        future_date = datetime(2024, 1, 16, 12, 0, 0, tzinfo=UTC)
        assert time_evaluator.evaluate_date_condition(
            "date_after", future_date, reference_date
        ) is True

        # Same date should return False (not strictly after)
        assert time_evaluator.evaluate_date_condition(
            "date_after", reference_date, reference_date
        ) is False

        # Date before reference should return False
        past_date = datetime(2024, 1, 14, 12, 0, 0, tzinfo=UTC)
        assert time_evaluator.evaluate_date_condition(
            "date_after", past_date, reference_date
        ) is False

    @pytest.mark.asyncio
    async def test_date_before_operator(self, time_evaluator: TimeBasedRuleEvaluator) -> None:
        """Test DATE_BEFORE operator matches past dates."""
        reference_date = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        # Date before reference should return True
        past_date = datetime(2024, 1, 14, 12, 0, 0, tzinfo=UTC)
        assert time_evaluator.evaluate_date_condition(
            "date_before", past_date, reference_date
        ) is True

        # Same date should return False (not strictly before)
        assert time_evaluator.evaluate_date_condition(
            "date_before", reference_date, reference_date
        ) is False

        # Date after reference should return False
        future_date = datetime(2024, 1, 16, 12, 0, 0, tzinfo=UTC)
        assert time_evaluator.evaluate_date_condition(
            "date_before", future_date, reference_date
        ) is False

    @pytest.mark.asyncio
    async def test_date_operators_with_iso_strings(
        self, time_evaluator: TimeBasedRuleEvaluator
    ) -> None:
        """Test date operators with ISO 8601 string parsing."""
        # Standard ISO format
        assert time_evaluator.evaluate_date_condition(
            "date_after",
            "2024-01-16T12:00:00+00:00",
            "2024-01-15T12:00:00+00:00",
        ) is True

        # With Z suffix
        assert time_evaluator.evaluate_date_condition(
            "date_before",
            "2024-01-14T12:00:00Z",
            "2024-01-15T12:00:00Z",
        ) is True

        # Without timezone (assumes local)
        assert time_evaluator.evaluate_date_condition(
            "date_after",
            "2024-06-01T10:00:00",
            "2024-01-01T10:00:00",
        ) is True

    @pytest.mark.asyncio
    async def test_date_operators_with_none_values(
        self, time_evaluator: TimeBasedRuleEvaluator
    ) -> None:
        """Test date operators handle None values gracefully."""
        reference_date = datetime(2024, 1, 15, tzinfo=UTC)

        assert time_evaluator.evaluate_date_condition(
            "date_after", None, reference_date
        ) is False

        assert time_evaluator.evaluate_date_condition(
            "date_after", reference_date, None
        ) is False

        assert time_evaluator.evaluate_date_condition(
            "date_after", None, None
        ) is False

    @pytest.mark.asyncio
    async def test_date_operators_with_invalid_strings(
        self, time_evaluator: TimeBasedRuleEvaluator
    ) -> None:
        """Test date operators handle invalid date strings."""
        reference_date = datetime(2024, 1, 15, tzinfo=UTC)

        assert time_evaluator.evaluate_date_condition(
            "date_after", "not-a-date", reference_date
        ) is False

        assert time_evaluator.evaluate_date_condition(
            "date_after", "2024-13-45", reference_date
        ) is False

    @pytest.mark.asyncio
    async def test_date_operators_in_engine(self, engine: TimeAwareEvaluationEngine) -> None:
        """Test date operators work within the evaluation engine."""
        # Test with date_after condition
        conditions = [
            {"attribute": "signup_date", "operator": "date_after", "value": "2024-01-01T00:00:00Z"}
        ]

        context = EvaluationContext(
            attributes={"signup_date": "2024-06-15T00:00:00Z"}
        )
        assert engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(
            attributes={"signup_date": "2023-06-15T00:00:00Z"}
        )
        assert engine._matches_conditions(conditions, context) is False


# =============================================================================
# TESTS: TIME-BASED RULE EVALUATOR
# =============================================================================


class TestTimeBasedRuleEvaluator:
    """Tests for TimeBasedRuleEvaluator."""

    @pytest.fixture
    def evaluator(self) -> TimeBasedRuleEvaluator:
        return TimeBasedRuleEvaluator()

    def test_daily_schedule_in_window(self, evaluator: TimeBasedRuleEvaluator) -> None:
        """Test daily schedule when current time is within window."""
        schedule = TimeSchedule(
            schedule_type=ScheduleType.DAILY,
            start_time=dt_time(9, 0),
            end_time=dt_time(17, 0),
            timezone="UTC",
        )

        # Time within window (12:00)
        test_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is True

        # Time at start boundary
        test_time = datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is True

        # Time at end boundary
        test_time = datetime(2024, 1, 15, 17, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is True

    def test_daily_schedule_outside_window(self, evaluator: TimeBasedRuleEvaluator) -> None:
        """Test daily schedule when current time is outside window."""
        schedule = TimeSchedule(
            schedule_type=ScheduleType.DAILY,
            start_time=dt_time(9, 0),
            end_time=dt_time(17, 0),
            timezone="UTC",
        )

        # Time before window (6:00)
        test_time = datetime(2024, 1, 15, 6, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is False

        # Time after window (20:00)
        test_time = datetime(2024, 1, 15, 20, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is False

    def test_daily_schedule_overnight_window(self, evaluator: TimeBasedRuleEvaluator) -> None:
        """Test daily schedule with overnight window (e.g., 22:00 - 06:00)."""
        schedule = TimeSchedule(
            schedule_type=ScheduleType.DAILY,
            start_time=dt_time(22, 0),
            end_time=dt_time(6, 0),
            timezone="UTC",
        )

        # Time in evening (23:00) - should be in window
        test_time = datetime(2024, 1, 15, 23, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is True

        # Time in morning (4:00) - should be in window
        test_time = datetime(2024, 1, 16, 4, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is True

        # Time in afternoon (14:00) - should NOT be in window
        test_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is False

    def test_weekly_schedule_matching_day(self, evaluator: TimeBasedRuleEvaluator) -> None:
        """Test weekly schedule on a matching day of week."""
        schedule = TimeSchedule(
            schedule_type=ScheduleType.WEEKLY,
            start_time=dt_time(9, 0),
            end_time=dt_time(17, 0),
            days_of_week=[0, 1, 2, 3, 4],  # Monday-Friday
            timezone="UTC",
        )

        # Wednesday 12:00 - should be in window
        test_time = datetime(2024, 1, 17, 12, 0, 0, tzinfo=UTC)  # Wednesday
        assert evaluator.is_in_schedule(schedule, test_time) is True

        # Monday 9:00 - should be in window
        test_time = datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC)  # Monday
        assert evaluator.is_in_schedule(schedule, test_time) is True

    def test_weekly_schedule_non_matching_day(self, evaluator: TimeBasedRuleEvaluator) -> None:
        """Test weekly schedule on a non-matching day."""
        schedule = TimeSchedule(
            schedule_type=ScheduleType.WEEKLY,
            start_time=dt_time(9, 0),
            end_time=dt_time(17, 0),
            days_of_week=[0, 1, 2, 3, 4],  # Monday-Friday
            timezone="UTC",
        )

        # Saturday 12:00 - should NOT be in window
        test_time = datetime(2024, 1, 20, 12, 0, 0, tzinfo=UTC)  # Saturday
        assert evaluator.is_in_schedule(schedule, test_time) is False

        # Sunday 12:00 - should NOT be in window
        test_time = datetime(2024, 1, 21, 12, 0, 0, tzinfo=UTC)  # Sunday
        assert evaluator.is_in_schedule(schedule, test_time) is False

    def test_weekly_schedule_matching_day_wrong_time(
        self, evaluator: TimeBasedRuleEvaluator
    ) -> None:
        """Test weekly schedule on matching day but outside time window."""
        schedule = TimeSchedule(
            schedule_type=ScheduleType.WEEKLY,
            start_time=dt_time(9, 0),
            end_time=dt_time(17, 0),
            days_of_week=[0, 1, 2, 3, 4],  # Monday-Friday
            timezone="UTC",
        )

        # Monday 20:00 - wrong time
        test_time = datetime(2024, 1, 15, 20, 0, 0, tzinfo=UTC)  # Monday
        assert evaluator.is_in_schedule(schedule, test_time) is False

    def test_monthly_schedule_matching_day(self, evaluator: TimeBasedRuleEvaluator) -> None:
        """Test monthly schedule on a matching day of month."""
        schedule = TimeSchedule(
            schedule_type=ScheduleType.MONTHLY,
            start_time=dt_time(0, 0),
            end_time=dt_time(23, 59),
            days_of_month=[1, 15],  # 1st and 15th of each month
            timezone="UTC",
        )

        # January 15th - should be in window
        test_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is True

        # February 1st - should be in window
        test_time = datetime(2024, 2, 1, 12, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is True

    def test_monthly_schedule_non_matching_day(
        self, evaluator: TimeBasedRuleEvaluator
    ) -> None:
        """Test monthly schedule on a non-matching day."""
        schedule = TimeSchedule(
            schedule_type=ScheduleType.MONTHLY,
            start_time=dt_time(0, 0),
            end_time=dt_time(23, 59),
            days_of_month=[1, 15],
            timezone="UTC",
        )

        # January 10th - should NOT be in window
        test_time = datetime(2024, 1, 10, 12, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is False

    def test_timezone_handling(self, evaluator: TimeBasedRuleEvaluator) -> None:
        """Test proper timezone conversion."""
        # Schedule set for 9-17 in US/Eastern
        schedule = TimeSchedule(
            schedule_type=ScheduleType.DAILY,
            start_time=dt_time(9, 0),
            end_time=dt_time(17, 0),
            timezone="America/New_York",
        )

        # 14:00 UTC = 9:00 EST (during standard time, Jan)
        # This should be at the start of the window
        test_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is True

        # 8:00 UTC = 3:00 EST - should be outside window
        test_time = datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is False

    def test_disabled_schedule(self, evaluator: TimeBasedRuleEvaluator) -> None:
        """Test that disabled schedules always return False."""
        schedule = TimeSchedule(
            schedule_type=ScheduleType.DAILY,
            start_time=dt_time(0, 0),
            end_time=dt_time(23, 59),
            timezone="UTC",
            enabled=False,
        )

        # Should be False even though time is within window
        test_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is False

    def test_schedule_with_no_time_constraints(
        self, evaluator: TimeBasedRuleEvaluator
    ) -> None:
        """Test schedule with no start/end times (always active)."""
        schedule = TimeSchedule(
            schedule_type=ScheduleType.DAILY,
            start_time=None,
            end_time=None,
            timezone="UTC",
        )

        # Any time should be in window
        test_time = datetime(2024, 1, 15, 3, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is True


# =============================================================================
# TESTS: SCHEDULE PROCESSOR
# =============================================================================


class TestScheduleProcessor:
    """Tests for ScheduleProcessor."""

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        return MemoryStorageBackend()

    @pytest.fixture
    def processor(self, storage: MemoryStorageBackend) -> ScheduleProcessor:
        return ScheduleProcessor(storage)

    @pytest.fixture
    async def sample_flag(self, storage: MemoryStorageBackend) -> FeatureFlag:
        """Create a sample flag for testing."""
        flag = FeatureFlag(
            id=uuid4(),
            key="scheduled-flag",
            name="Scheduled Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.INACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=None,  # Will be set
                    name="Default Rule",
                    priority=0,
                    enabled=True,
                    conditions=[],
                    serve_enabled=True,
                    rollout_percentage=50,
                )
            ],
            overrides=[],
            variants=[],
        )
        flag.rules[0].flag_id = flag.id
        await storage.create_flag(flag)
        return flag

    @pytest.mark.asyncio
    async def test_process_pending_changes_executes_due_changes(
        self, processor: ScheduleProcessor, sample_flag: FeatureFlag
    ) -> None:
        """Test that pending changes are executed when due."""
        # Schedule a change for the past (should execute immediately)
        past_time = datetime.now(UTC) - timedelta(hours=1)
        change = ScheduledFlagChange(
            flag_id=str(sample_flag.id),
            change_type=ChangeType.ENABLE,
            scheduled_at=past_time,
            description="Enable flag",
        )
        processor.add_scheduled_change(change)

        # Process pending changes
        executed = await processor.process_pending_changes()

        assert len(executed) == 1
        assert executed[0].executed_at is not None
        assert executed[0].change_type == ChangeType.ENABLE

    @pytest.mark.asyncio
    async def test_process_does_not_execute_future_changes(
        self, processor: ScheduleProcessor, sample_flag: FeatureFlag
    ) -> None:
        """Test that future changes are not executed."""
        future_time = datetime.now(UTC) + timedelta(hours=1)
        change = ScheduledFlagChange(
            flag_id=str(sample_flag.id),
            change_type=ChangeType.ENABLE,
            scheduled_at=future_time,
        )
        processor.add_scheduled_change(change)

        executed = await processor.process_pending_changes()

        assert len(executed) == 0
        assert change.executed_at is None

    @pytest.mark.asyncio
    async def test_scheduled_enable(
        self,
        processor: ScheduleProcessor,
        storage: MemoryStorageBackend,
        sample_flag: FeatureFlag,
    ) -> None:
        """Test scheduled flag enable."""
        # Verify flag is initially inactive
        flag = storage._flags_by_id.get(sample_flag.id)
        assert flag is not None
        assert flag.status == FlagStatus.INACTIVE
        assert flag.default_enabled is False

        # Schedule enable
        past_time = datetime.now(UTC) - timedelta(minutes=5)
        change = ScheduledFlagChange(
            flag_id=str(sample_flag.id),
            change_type=ChangeType.ENABLE,
            scheduled_at=past_time,
        )
        processor.add_scheduled_change(change)

        await processor.process_pending_changes()

        # Verify flag is now active
        flag = storage._flags_by_id.get(sample_flag.id)
        assert flag is not None
        assert flag.status == FlagStatus.ACTIVE
        assert flag.default_enabled is True

    @pytest.mark.asyncio
    async def test_scheduled_disable(
        self,
        processor: ScheduleProcessor,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test scheduled flag disable."""
        # Create an active flag
        flag = FeatureFlag(
            id=uuid4(),
            key="active-flag",
            name="Active Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        await storage.create_flag(flag)

        # Schedule disable
        past_time = datetime.now(UTC) - timedelta(minutes=5)
        change = ScheduledFlagChange(
            flag_id=str(flag.id),
            change_type=ChangeType.DISABLE,
            scheduled_at=past_time,
        )
        processor.add_scheduled_change(change)

        await processor.process_pending_changes()

        # Verify flag is now inactive
        updated_flag = storage._flags_by_id.get(flag.id)
        assert updated_flag is not None
        assert updated_flag.status == FlagStatus.INACTIVE
        assert updated_flag.default_enabled is False

    @pytest.mark.asyncio
    async def test_scheduled_rollout_update(
        self,
        processor: ScheduleProcessor,
        storage: MemoryStorageBackend,
        sample_flag: FeatureFlag,
    ) -> None:
        """Test scheduled rollout percentage update."""
        # Verify initial rollout percentage
        flag = storage._flags_by_id.get(sample_flag.id)
        assert flag is not None
        assert flag.rules[0].rollout_percentage == 50

        # Schedule rollout update
        past_time = datetime.now(UTC) - timedelta(minutes=5)
        change = ScheduledFlagChange(
            flag_id=str(sample_flag.id),
            change_type=ChangeType.UPDATE_ROLLOUT,
            scheduled_at=past_time,
            new_rollout_percentage=75,
        )
        processor.add_scheduled_change(change)

        await processor.process_pending_changes()

        # Verify rollout percentage updated
        updated_flag = storage._flags_by_id.get(sample_flag.id)
        assert updated_flag is not None
        assert updated_flag.rules[0].rollout_percentage == 75

    @pytest.mark.asyncio
    async def test_scheduled_value_update(
        self,
        processor: ScheduleProcessor,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test scheduled flag value update."""
        # Create a JSON flag
        flag = FeatureFlag(
            id=uuid4(),
            key="json-flag",
            name="JSON Flag",
            flag_type=FlagType.JSON,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            default_value={"version": "1.0"},
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        await storage.create_flag(flag)

        # Schedule value update
        past_time = datetime.now(UTC) - timedelta(minutes=5)
        change = ScheduledFlagChange(
            flag_id=str(flag.id),
            change_type=ChangeType.UPDATE_VALUE,
            scheduled_at=past_time,
            new_value={"version": "2.0", "features": ["new"]},
        )
        processor.add_scheduled_change(change)

        await processor.process_pending_changes()

        # Verify value updated
        updated_flag = storage._flags_by_id.get(flag.id)
        assert updated_flag is not None
        assert updated_flag.default_value == {"version": "2.0", "features": ["new"]}

    @pytest.mark.asyncio
    async def test_multiple_scheduled_changes(
        self,
        processor: ScheduleProcessor,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test processing multiple scheduled changes."""
        # Create two flags
        flag1 = FeatureFlag(
            id=uuid4(),
            key="flag-1",
            name="Flag 1",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.INACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        flag2 = FeatureFlag(
            id=uuid4(),
            key="flag-2",
            name="Flag 2",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        await storage.create_flag(flag1)
        await storage.create_flag(flag2)

        past_time = datetime.now(UTC) - timedelta(minutes=5)

        # Schedule enable for flag1 and disable for flag2
        processor.add_scheduled_change(
            ScheduledFlagChange(
                flag_id=str(flag1.id),
                change_type=ChangeType.ENABLE,
                scheduled_at=past_time,
            )
        )
        processor.add_scheduled_change(
            ScheduledFlagChange(
                flag_id=str(flag2.id),
                change_type=ChangeType.DISABLE,
                scheduled_at=past_time,
            )
        )

        executed = await processor.process_pending_changes()

        assert len(executed) == 2

        updated_flag1 = storage._flags_by_id.get(flag1.id)
        updated_flag2 = storage._flags_by_id.get(flag2.id)

        assert updated_flag1 is not None
        assert updated_flag1.status == FlagStatus.ACTIVE
        assert updated_flag2 is not None
        assert updated_flag2.status == FlagStatus.INACTIVE

    @pytest.mark.asyncio
    async def test_change_with_nonexistent_flag(
        self, processor: ScheduleProcessor
    ) -> None:
        """Test processing change for non-existent flag."""
        past_time = datetime.now(UTC) - timedelta(minutes=5)
        change = ScheduledFlagChange(
            flag_id=str(uuid4()),  # Non-existent flag ID
            change_type=ChangeType.ENABLE,
            scheduled_at=past_time,
        )
        processor.add_scheduled_change(change)

        # Should not raise, change is processed but flag not found
        # So executed_at remains None and change is removed from pending
        executed = await processor.process_pending_changes()
        # Change was "processed" (attempted) but flag wasn't found
        # The implementation still adds to executed list since is_due() was True
        assert len(executed) == 1
        # executed_at is None because flag wasn't found
        assert change.executed_at is None


# =============================================================================
# TESTS: ROLLOUT PHASE
# =============================================================================


class TestRolloutPhase:
    """Tests for RolloutPhase."""

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        return MemoryStorageBackend()

    @pytest.fixture
    def processor(self, storage: MemoryStorageBackend) -> ScheduleProcessor:
        return ScheduleProcessor(storage)

    @pytest.mark.asyncio
    async def test_gradual_rollout_phases(
        self,
        processor: ScheduleProcessor,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test gradual rollout from 0% to 100% in phases."""
        # Create a flag with 0% rollout
        flag = FeatureFlag(
            id=uuid4(),
            key="gradual-rollout",
            name="Gradual Rollout",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=None,
                    name="Rollout Rule",
                    priority=0,
                    enabled=True,
                    conditions=[],
                    serve_enabled=True,
                    rollout_percentage=0,
                )
            ],
            overrides=[],
            variants=[],
        )
        flag.rules[0].flag_id = flag.id
        await storage.create_flag(flag)

        # Define rollout phases
        phases = [
            RolloutPhase(
                flag_id=str(flag.id),
                phase_number=1,
                percentage=25,
                start_at=datetime.now(UTC) - timedelta(hours=3),
                description="Phase 1: 25%",
            ),
            RolloutPhase(
                flag_id=str(flag.id),
                phase_number=2,
                percentage=50,
                start_at=datetime.now(UTC) - timedelta(hours=2),
                description="Phase 2: 50%",
            ),
            RolloutPhase(
                flag_id=str(flag.id),
                phase_number=3,
                percentage=75,
                start_at=datetime.now(UTC) - timedelta(hours=1),
                description="Phase 3: 75%",
            ),
            RolloutPhase(
                flag_id=str(flag.id),
                phase_number=4,
                percentage=100,
                start_at=datetime.now(UTC) - timedelta(minutes=30),
                description="Phase 4: 100%",
            ),
        ]

        # Process each phase
        for phase in phases:
            if phase.is_active():
                change = ScheduledFlagChange(
                    flag_id=phase.flag_id,
                    change_type=ChangeType.UPDATE_ROLLOUT,
                    scheduled_at=phase.start_at,
                    new_rollout_percentage=phase.percentage,
                )
                processor.add_scheduled_change(change)

        await processor.process_pending_changes()

        # Verify final rollout is 100%
        updated_flag = storage._flags_by_id.get(flag.id)
        assert updated_flag is not None
        assert updated_flag.rules[0].rollout_percentage == 100

    def test_rollout_phase_creation(self) -> None:
        """Test RolloutPhase model creation."""
        phase = RolloutPhase(
            flag_id="test-flag-id",
            phase_number=1,
            percentage=25,
            start_at=datetime.now(UTC),
            description="Initial rollout",
        )

        assert phase.flag_id == "test-flag-id"
        assert phase.phase_number == 1
        assert phase.percentage == 25
        assert phase.description == "Initial rollout"
        assert phase.completed_at is None

    def test_rollout_phase_is_active(self) -> None:
        """Test RolloutPhase.is_active() method."""
        # Active phase (started, not completed)
        active_phase = RolloutPhase(
            flag_id="test-flag",
            phase_number=1,
            percentage=25,
            start_at=datetime.now(UTC) - timedelta(hours=1),
            completed_at=None,
        )
        assert active_phase.is_active() is True

        # Completed phase
        completed_phase = RolloutPhase(
            flag_id="test-flag",
            phase_number=1,
            percentage=25,
            start_at=datetime.now(UTC) - timedelta(hours=2),
            completed_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert completed_phase.is_active() is False

        # Future phase (not yet started)
        future_phase = RolloutPhase(
            flag_id="test-flag",
            phase_number=1,
            percentage=25,
            start_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert future_phase.is_active() is False

        # Phase with no start time
        no_start_phase = RolloutPhase(
            flag_id="test-flag",
            phase_number=1,
            percentage=25,
            start_at=None,
        )
        assert no_start_phase.is_active() is False


# =============================================================================
# TESTS: TIME-BASED MODELS
# =============================================================================


class TestTimeBasedModels:
    """Tests for time-based model creation and validation."""

    def test_scheduled_flag_change_creation(self) -> None:
        """Test ScheduledFlagChange model creation."""
        scheduled_at = datetime.now(UTC) + timedelta(hours=1)
        change = ScheduledFlagChange(
            flag_id="test-flag-id",
            change_type=ChangeType.ENABLE,
            scheduled_at=scheduled_at,
            description="Enable feature at launch",
            created_by="admin@example.com",
        )

        assert change.flag_id == "test-flag-id"
        assert change.change_type == ChangeType.ENABLE
        assert change.scheduled_at == scheduled_at
        assert change.executed_at is None
        assert change.description == "Enable feature at launch"
        assert change.created_by == "admin@example.com"
        assert change.id is not None

    def test_scheduled_flag_change_is_due(self) -> None:
        """Test ScheduledFlagChange.is_due() method."""
        # Not due (future)
        future_change = ScheduledFlagChange(
            flag_id="test",
            scheduled_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert future_change.is_due() is False

        # Due (past)
        past_change = ScheduledFlagChange(
            flag_id="test",
            scheduled_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert past_change.is_due() is True

        # Already executed
        executed_change = ScheduledFlagChange(
            flag_id="test",
            scheduled_at=datetime.now(UTC) - timedelta(hours=1),
            executed_at=datetime.now(UTC),
        )
        assert executed_change.is_due() is False

        # No scheduled time
        no_time_change = ScheduledFlagChange(
            flag_id="test",
            scheduled_at=None,
        )
        assert no_time_change.is_due() is False

    def test_scheduled_flag_change_with_rollout(self) -> None:
        """Test ScheduledFlagChange with rollout percentage."""
        change = ScheduledFlagChange(
            flag_id="test-flag",
            change_type=ChangeType.UPDATE_ROLLOUT,
            scheduled_at=datetime.now(UTC),
            new_rollout_percentage=50,
        )

        assert change.change_type == ChangeType.UPDATE_ROLLOUT
        assert change.new_rollout_percentage == 50

    def test_scheduled_flag_change_with_value(self) -> None:
        """Test ScheduledFlagChange with new value."""
        change = ScheduledFlagChange(
            flag_id="test-flag",
            change_type=ChangeType.UPDATE_VALUE,
            scheduled_at=datetime.now(UTC),
            new_value={"feature": "enabled", "version": 2},
        )

        assert change.change_type == ChangeType.UPDATE_VALUE
        assert change.new_value == {"feature": "enabled", "version": 2}

    def test_time_schedule_creation(self) -> None:
        """Test TimeSchedule model creation."""
        schedule = TimeSchedule(
            flag_id="test-flag-id",
            schedule_type=ScheduleType.WEEKLY,
            start_time=dt_time(9, 0),
            end_time=dt_time(17, 0),
            days_of_week=[0, 1, 2, 3, 4],
            timezone="America/New_York",
            enabled=True,
        )

        assert schedule.flag_id == "test-flag-id"
        assert schedule.schedule_type == ScheduleType.WEEKLY
        assert schedule.start_time == dt_time(9, 0)
        assert schedule.end_time == dt_time(17, 0)
        assert schedule.days_of_week == [0, 1, 2, 3, 4]
        assert schedule.timezone == "America/New_York"
        assert schedule.enabled is True
        assert schedule.id is not None

    def test_time_schedule_daily(self) -> None:
        """Test TimeSchedule with daily schedule type."""
        schedule = TimeSchedule(
            flag_id="daily-flag",
            schedule_type=ScheduleType.DAILY,
            start_time=dt_time(8, 0),
            end_time=dt_time(20, 0),
        )

        assert schedule.schedule_type == ScheduleType.DAILY
        assert schedule.days_of_week is None
        assert schedule.days_of_month is None

    def test_time_schedule_monthly(self) -> None:
        """Test TimeSchedule with monthly schedule type."""
        schedule = TimeSchedule(
            flag_id="monthly-flag",
            schedule_type=ScheduleType.MONTHLY,
            start_time=dt_time(0, 0),
            end_time=dt_time(23, 59),
            days_of_month=[1, 15, 28],
        )

        assert schedule.schedule_type == ScheduleType.MONTHLY
        assert schedule.days_of_month == [1, 15, 28]

    def test_rollout_phase_creation(self) -> None:
        """Test RolloutPhase model creation."""
        start_at = datetime.now(UTC)
        phase = RolloutPhase(
            flag_id="rollout-flag-id",
            phase_number=2,
            percentage=50,
            start_at=start_at,
            description="50% rollout phase",
        )

        assert phase.flag_id == "rollout-flag-id"
        assert phase.phase_number == 2
        assert phase.percentage == 50
        assert phase.start_at == start_at
        assert phase.completed_at is None
        assert phase.description == "50% rollout phase"
        assert phase.id is not None

    def test_change_type_constants(self) -> None:
        """Test ChangeType constants."""
        assert ChangeType.ENABLE == "enable"
        assert ChangeType.DISABLE == "disable"
        assert ChangeType.UPDATE_ROLLOUT == "update_rollout"
        assert ChangeType.UPDATE_VALUE == "update_value"

    def test_schedule_type_constants(self) -> None:
        """Test ScheduleType constants."""
        assert ScheduleType.DAILY == "daily"
        assert ScheduleType.WEEKLY == "weekly"
        assert ScheduleType.MONTHLY == "monthly"
        assert ScheduleType.ONE_TIME == "one_time"


# =============================================================================
# TESTS: INTEGRATION
# =============================================================================


class TestTimeBasedIntegration:
    """Integration tests for time-based rules with the evaluation engine."""

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        return MemoryStorageBackend()

    @pytest.fixture
    def engine(self) -> TimeAwareEvaluationEngine:
        return TimeAwareEvaluationEngine()

    @pytest.fixture
    def evaluator(self) -> TimeBasedRuleEvaluator:
        return TimeBasedRuleEvaluator()

    @pytest.mark.asyncio
    async def test_flag_with_date_condition(
        self,
        engine: TimeAwareEvaluationEngine,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test flag evaluation with date-based conditions."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="launch-feature",
            name="Launch Feature",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Post-Launch Users",
                    priority=0,
                    enabled=True,
                    conditions=[
                        {
                            "attribute": "signup_date",
                            "operator": "date_after",
                            "value": "2024-01-01T00:00:00Z",
                        }
                    ],
                    serve_enabled=True,
                )
            ],
            overrides=[],
            variants=[],
        )
        await storage.create_flag(flag)

        # User who signed up after launch
        context = EvaluationContext(
            targeting_key="user-1",
            attributes={"signup_date": "2024-06-15T00:00:00Z"},
        )
        result = await engine.evaluate(flag, context, storage)
        assert result.value is True

        # User who signed up before launch
        context = EvaluationContext(
            targeting_key="user-2",
            attributes={"signup_date": "2023-06-15T00:00:00Z"},
        )
        result = await engine.evaluate(flag, context, storage)
        assert result.value is False

    @pytest.mark.asyncio
    async def test_schedule_based_flag_activation(
        self,
        storage: MemoryStorageBackend,
        evaluator: TimeBasedRuleEvaluator,
    ) -> None:
        """Test flag activation based on schedule."""
        # Create a flag
        flag = FeatureFlag(
            id=uuid4(),
            key="business-hours-feature",
            name="Business Hours Feature",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        await storage.create_flag(flag)

        # Create a schedule for business hours (9-17, Mon-Fri)
        schedule = TimeSchedule(
            flag_id=str(flag.id),
            schedule_type=ScheduleType.WEEKLY,
            start_time=dt_time(9, 0),
            end_time=dt_time(17, 0),
            days_of_week=[0, 1, 2, 3, 4],
            timezone="UTC",
        )

        # Test during business hours (Wednesday 12:00)
        business_time = datetime(2024, 1, 17, 12, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, business_time) is True

        # Test outside business hours (Wednesday 20:00)
        after_hours = datetime(2024, 1, 17, 20, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, after_hours) is False

        # Test on weekend (Saturday 12:00)
        weekend = datetime(2024, 1, 20, 12, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, weekend) is False

    @pytest.mark.asyncio
    async def test_scheduled_rollout_progression(
        self, storage: MemoryStorageBackend
    ) -> None:
        """Test progressive rollout through scheduled changes."""
        # Create a flag with initial 10% rollout
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="progressive-rollout",
            name="Progressive Rollout",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Rollout",
                    priority=0,
                    enabled=True,
                    conditions=[],
                    serve_enabled=True,
                    rollout_percentage=10,
                )
            ],
            overrides=[],
            variants=[],
        )
        await storage.create_flag(flag)

        processor = ScheduleProcessor(storage)

        # Schedule rollout increases
        base_time = datetime.now(UTC) - timedelta(hours=4)
        changes = [
            ScheduledFlagChange(
                flag_id=str(flag_id),
                change_type=ChangeType.UPDATE_ROLLOUT,
                scheduled_at=base_time + timedelta(hours=1),
                new_rollout_percentage=25,
            ),
            ScheduledFlagChange(
                flag_id=str(flag_id),
                change_type=ChangeType.UPDATE_ROLLOUT,
                scheduled_at=base_time + timedelta(hours=2),
                new_rollout_percentage=50,
            ),
            ScheduledFlagChange(
                flag_id=str(flag_id),
                change_type=ChangeType.UPDATE_ROLLOUT,
                scheduled_at=base_time + timedelta(hours=3),
                new_rollout_percentage=100,
            ),
        ]

        for change in changes:
            processor.add_scheduled_change(change)

        # Process all pending changes
        executed = await processor.process_pending_changes()

        # All changes should have been executed
        assert len(executed) == 3

        # Final rollout should be 100%
        updated_flag = storage._flags_by_id.get(flag_id)
        assert updated_flag is not None
        assert updated_flag.rules[0].rollout_percentage == 100


# =============================================================================
# TESTS: EDGE CASES
# =============================================================================


class TestTimeBasedEdgeCases:
    """Edge case tests for time-based rules."""

    def test_schedule_with_invalid_timezone(self) -> None:
        """Test schedule handling with invalid timezone."""
        evaluator = TimeBasedRuleEvaluator()
        schedule = TimeSchedule(
            schedule_type=ScheduleType.DAILY,
            start_time=dt_time(9, 0),
            end_time=dt_time(17, 0),
            timezone="Invalid/Timezone",
        )

        # Should not raise, should fall back to UTC or handle gracefully
        test_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        # The function should handle the invalid timezone gracefully
        result = evaluator.is_in_schedule(schedule, test_time)
        # Result depends on fallback behavior - should not crash
        assert isinstance(result, bool)

    def test_date_comparison_with_different_timezones(self) -> None:
        """Test date comparison across different timezones."""
        evaluator = TimeBasedRuleEvaluator()

        # Same instant in time, different timezone representations
        utc_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        est_time = datetime(2024, 1, 15, 7, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        # These are the same moment, so neither is after the other
        assert evaluator.evaluate_date_condition(
            "date_after", utc_time, est_time
        ) is False

    def test_empty_days_of_week(self) -> None:
        """Test weekly schedule with empty days_of_week."""
        evaluator = TimeBasedRuleEvaluator()
        schedule = TimeSchedule(
            schedule_type=ScheduleType.WEEKLY,
            start_time=dt_time(9, 0),
            end_time=dt_time(17, 0),
            days_of_week=None,  # No days specified
        )

        test_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, test_time) is False

    def test_scheduled_change_without_flag_id(self) -> None:
        """Test scheduled change without flag_id."""
        change = ScheduledFlagChange(
            flag_id=None,
            change_type=ChangeType.ENABLE,
            scheduled_at=datetime.now(UTC) - timedelta(hours=1),
        )

        assert change.is_due() is True
        assert change.flag_id is None

    def test_rollout_phase_defaults(self) -> None:
        """Test RolloutPhase default values."""
        phase = RolloutPhase()

        assert phase.flag_id is None
        assert phase.phase_number == 1
        assert phase.percentage == 0
        assert phase.start_at is None
        assert phase.completed_at is None
        assert phase.description is None
        assert phase.id is not None

    def test_time_schedule_defaults(self) -> None:
        """Test TimeSchedule default values."""
        schedule = TimeSchedule()

        assert schedule.flag_id is None
        assert schedule.schedule_type == ScheduleType.DAILY
        assert schedule.start_time is None
        assert schedule.end_time is None
        assert schedule.days_of_week is None
        assert schedule.days_of_month is None
        assert schedule.timezone == "UTC"
        assert schedule.enabled is True

    def test_midnight_boundary_handling(self) -> None:
        """Test schedule handling at midnight boundaries."""
        evaluator = TimeBasedRuleEvaluator()
        schedule = TimeSchedule(
            schedule_type=ScheduleType.DAILY,
            start_time=dt_time(0, 0),
            end_time=dt_time(23, 59, 59),
            timezone="UTC",
        )

        # Exactly at midnight
        midnight = datetime(2024, 1, 15, 0, 0, 0, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, midnight) is True

        # Just before midnight
        before_midnight = datetime(2024, 1, 15, 23, 59, 59, tzinfo=UTC)
        assert evaluator.is_in_schedule(schedule, before_midnight) is True
