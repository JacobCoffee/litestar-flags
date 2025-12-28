"""Time-based rule evaluation for feature flags."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING

from litestar_flags.types import RecurrenceType

if TYPE_CHECKING:
    from litestar_flags.context import EvaluationContext
    from litestar_flags.models.schedule import TimeSchedule

__all__ = ["TimeBasedRuleEvaluator"]


class TimeBasedRuleEvaluator:
    """Evaluator for time-based and scheduled flag rules.

    This class provides methods to evaluate time schedules and determine
    if a flag should be active based on time-based conditions.

    Supports various recurrence patterns:
        - DAILY: Active during specific time windows each day
        - WEEKLY: Active on specific days of the week
        - MONTHLY: Active on specific days of the month
        - CRON: Active based on cron expression patterns

    Example:
        >>> evaluator = TimeBasedRuleEvaluator()
        >>> schedule = TimeSchedule(
        ...     flag_id=flag.id,
        ...     name="Business Hours",
        ...     recurrence_type=RecurrenceType.WEEKLY,
        ...     start_time="09:00",
        ...     end_time="17:00",
        ...     days_of_week=[0, 1, 2, 3, 4],  # Monday-Friday
        ... )
        >>> evaluator.evaluate_schedule(schedule, context)
        True  # if current time is within business hours

    """

    def is_in_time_window(
        self,
        schedule: TimeSchedule,
        now: datetime | None = None,
    ) -> bool:
        """Check if current time falls within a time schedule window.

        Evaluates the schedule based on its recurrence type and time window
        configuration to determine if the flag should be active.

        Args:
            schedule: The time schedule to evaluate.
            now: Optional datetime to check against. Defaults to current UTC time.

        Returns:
            True if the current time falls within the schedule window.

        """
        if not schedule.enabled:
            return False

        if now is None:
            now = datetime.now(UTC)

        # Check validity period
        if hasattr(schedule, "is_valid_at"):
            if not schedule.is_valid_at(now):
                return False
        else:
            # Manual validity check for dataclass fallback
            if schedule.valid_from is not None and now < schedule.valid_from:
                return False
            if schedule.valid_until is not None and now > schedule.valid_until:
                return False

        # Parse start and end times
        start_time = self._parse_time(schedule.start_time)
        end_time = self._parse_time(schedule.end_time)

        if start_time is None or end_time is None:
            return False

        # Get current time (handle timezone if needed)
        current_time = now.time()
        current_weekday = now.weekday()  # 0 = Monday, 6 = Sunday
        current_day_of_month = now.day

        match schedule.recurrence_type:
            case RecurrenceType.DAILY:
                return self._is_in_time_range(current_time, start_time, end_time)

            case RecurrenceType.WEEKLY:
                # Check if current day is in the allowed days
                if schedule.days_of_week is not None:
                    if current_weekday not in schedule.days_of_week:
                        return False
                return self._is_in_time_range(current_time, start_time, end_time)

            case RecurrenceType.MONTHLY:
                # Check if current day of month is in the allowed days
                if schedule.days_of_month is not None:
                    if current_day_of_month not in schedule.days_of_month:
                        return False
                return self._is_in_time_range(current_time, start_time, end_time)

            case RecurrenceType.CRON:
                return self._evaluate_cron(schedule.cron_expression, now)

            case _:
                return False

    def get_next_occurrence(
        self,
        schedule: TimeSchedule,
        after: datetime | None = None,
    ) -> datetime | None:
        """Get the next occurrence of a recurring time window.

        Calculates when the schedule will next be active based on the
        recurrence pattern.

        Args:
            schedule: The time schedule to evaluate.
            after: Starting point for the search. Defaults to current UTC time.

        Returns:
            The next datetime when the schedule will be active, or None
            if the schedule has expired or is invalid.

        """
        if not schedule.enabled:
            return None

        if after is None:
            after = datetime.now(UTC)

        # Check if schedule has expired
        if hasattr(schedule, "is_valid_at"):
            if schedule.valid_until is not None and after > schedule.valid_until:
                return None
        elif schedule.valid_until is not None and after > schedule.valid_until:
            return None

        start_time = self._parse_time(schedule.start_time)
        if start_time is None:
            return None

        # Start checking from the current date
        check_date = after.date()
        max_days_to_check = 366  # Check up to a year ahead

        for day_offset in range(max_days_to_check):
            candidate_date = check_date + timedelta(days=day_offset)
            candidate_dt = datetime.combine(
                candidate_date,
                start_time,
                tzinfo=UTC,
            )

            # Skip if before the 'after' time
            if candidate_dt <= after:
                continue

            # Check validity period
            if schedule.valid_from is not None and candidate_dt < schedule.valid_from:
                continue
            if schedule.valid_until is not None and candidate_dt > schedule.valid_until:
                return None

            # Check recurrence pattern
            match schedule.recurrence_type:
                case RecurrenceType.DAILY:
                    return candidate_dt

                case RecurrenceType.WEEKLY:
                    if schedule.days_of_week is not None:
                        if candidate_date.weekday() in schedule.days_of_week:
                            return candidate_dt
                    else:
                        return candidate_dt

                case RecurrenceType.MONTHLY:
                    if schedule.days_of_month is not None:
                        if candidate_date.day in schedule.days_of_month:
                            return candidate_dt
                    else:
                        return candidate_dt

                case RecurrenceType.CRON:
                    # For cron, we need a more sophisticated approach
                    if self._evaluate_cron(schedule.cron_expression, candidate_dt):
                        return candidate_dt

        return None

    def evaluate_schedule(
        self,
        schedule: TimeSchedule,
        context: EvaluationContext,
    ) -> bool:
        """Evaluate if a time schedule is currently active.

        Uses the timestamp from the evaluation context to determine if
        the schedule is active.

        Args:
            schedule: The time schedule to evaluate.
            context: The evaluation context containing the timestamp.

        Returns:
            True if the schedule is currently active.

        """
        now = context.timestamp if hasattr(context, "timestamp") else datetime.now(UTC)
        return self.is_in_time_window(schedule, now)

    def _parse_time(self, value: str | time | None) -> time | None:
        """Parse a time value from string or time object.

        Args:
            value: Time as string (HH:MM or HH:MM:SS) or time object.

        Returns:
            A time object or None if parsing fails.

        """
        if value is None:
            return None

        if isinstance(value, time):
            return value

        if isinstance(value, str):
            try:
                parts = [int(p) for p in value.split(":")]
                if len(parts) == 2:
                    return time(parts[0], parts[1])
                elif len(parts) == 3:
                    return time(parts[0], parts[1], parts[2])
            except (ValueError, IndexError):
                pass

        return None

    def _is_in_time_range(
        self,
        current: time,
        start: time,
        end: time,
    ) -> bool:
        """Check if a time falls within a range.

        Handles ranges that span midnight (e.g., 22:00 to 06:00).

        Args:
            current: The current time to check.
            start: Start of the time range.
            end: End of the time range.

        Returns:
            True if current is within the range.

        """
        if start <= end:
            # Normal range (e.g., 09:00 to 17:00)
            return start <= current <= end
        else:
            # Range spans midnight (e.g., 22:00 to 06:00)
            return current >= start or current <= end

    def _evaluate_cron(
        self,
        cron_expression: str | None,
        now: datetime,
    ) -> bool:
        """Evaluate a cron expression against a datetime.

        Implements a basic cron parser supporting standard 5-field format:
        minute hour day-of-month month day-of-week

        Supports:
            - * (any value)
            - Specific values (e.g., 5, 10)
            - Ranges (e.g., 1-5)
            - Lists (e.g., 1,3,5)
            - Step values (e.g., */15)

        Args:
            cron_expression: Standard cron expression string.
            now: The datetime to check against.

        Returns:
            True if the cron expression matches the given datetime.

        """
        if cron_expression is None:
            return False

        try:
            parts = cron_expression.strip().split()
            if len(parts) != 5:
                return False

            minute_expr, hour_expr, dom_expr, month_expr, dow_expr = parts

            # Check each field
            if not self._matches_cron_field(minute_expr, now.minute, 0, 59):
                return False
            if not self._matches_cron_field(hour_expr, now.hour, 0, 23):
                return False
            if not self._matches_cron_field(dom_expr, now.day, 1, 31):
                return False
            if not self._matches_cron_field(month_expr, now.month, 1, 12):
                return False
            # Cron uses 0=Sunday, but Python uses 0=Monday
            # Convert Python weekday to cron weekday (0=Sunday, 1=Monday, ...)
            cron_dow = (now.weekday() + 1) % 7
            if not self._matches_cron_field(dow_expr, cron_dow, 0, 6):
                return False

            return True

        except (ValueError, AttributeError):
            return False

    def _matches_cron_field(
        self,
        expr: str,
        value: int,
        min_val: int,
        max_val: int,
    ) -> bool:
        """Check if a value matches a cron field expression.

        Args:
            expr: Cron field expression (e.g., "*", "5", "1-5", "*/15").
            value: The value to check.
            min_val: Minimum valid value for this field.
            max_val: Maximum valid value for this field.

        Returns:
            True if the value matches the expression.

        """
        # Handle wildcard
        if expr == "*":
            return True

        # Handle step values (e.g., */15)
        if "/" in expr:
            base, step = expr.split("/", 1)
            try:
                step_val = int(step)
                if base == "*":
                    return (value - min_val) % step_val == 0
                else:
                    # Handle range with step (e.g., 1-30/5)
                    start, end = self._parse_range(base, min_val, max_val)
                    if start <= value <= end:
                        return (value - start) % step_val == 0
                    return False
            except (ValueError, TypeError):
                return False

        # Handle lists (e.g., 1,3,5)
        if "," in expr:
            values = []
            for part in expr.split(","):
                if "-" in part:
                    start, end = self._parse_range(part, min_val, max_val)
                    values.extend(range(start, end + 1))
                else:
                    values.append(int(part))
            return value in values

        # Handle ranges (e.g., 1-5)
        if "-" in expr:
            start, end = self._parse_range(expr, min_val, max_val)
            return start <= value <= end

        # Handle single value
        try:
            return value == int(expr)
        except ValueError:
            return False

    def _parse_range(
        self,
        expr: str,
        min_val: int,
        max_val: int,
    ) -> tuple[int, int]:
        """Parse a range expression (e.g., "1-5").

        Args:
            expr: Range expression string.
            min_val: Minimum valid value.
            max_val: Maximum valid value.

        Returns:
            Tuple of (start, end) values.

        """
        if "-" in expr:
            parts = expr.split("-", 1)
            start = int(parts[0])
            end = int(parts[1])
            return (max(start, min_val), min(end, max_val))
        else:
            val = int(expr)
            return (val, val)
