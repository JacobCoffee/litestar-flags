"""Segment evaluator for feature flag targeting.

This module provides the SegmentEvaluator class for evaluating segment membership
based on user context attributes. It supports nested segments and detects circular
references to prevent infinite loops.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, time, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

from litestar_flags.types import RuleOperator

if TYPE_CHECKING:
    from litestar_flags.context import EvaluationContext
    from litestar_flags.models.segment import Segment
    from litestar_flags.protocols import StorageBackend

__all__ = ["CircularSegmentReferenceError", "SegmentEvaluator"]


class CircularSegmentReferenceError(Exception):
    """Raised when circular segment references are detected.

    This error occurs when evaluating nested segments and a segment
    references itself either directly or through a chain of parent segments.

    Attributes:
        segment_id: The UUID of the segment where the circular reference was detected.
        visited_chain: The list of segment IDs in the order they were visited.

    Example:
        If segment A has parent B, and B has parent A, evaluating either
        will raise this error with the circular chain in visited_chain.

    """

    def __init__(self, segment_id: UUID, visited_chain: list[UUID]) -> None:
        """Initialize the circular reference error.

        Args:
            segment_id: The segment ID that caused the circular reference.
            visited_chain: The chain of segment IDs visited before detection.

        """
        self.segment_id = segment_id
        self.visited_chain = visited_chain
        chain_str = " -> ".join(str(sid) for sid in visited_chain)
        super().__init__(
            f"Circular segment reference detected: {chain_str} -> {segment_id}"
        )


class SegmentEvaluator:
    """Evaluates segment membership for feature flag targeting.

    The SegmentEvaluator checks if a given evaluation context matches the
    conditions defined in a segment. It supports nested segments where a
    segment can have a parent, and membership in the child requires
    membership in the parent as well.

    Features:
        - Condition evaluation with all RuleOperator types
        - Nested segment support with parent inheritance
        - Circular reference detection to prevent infinite loops
        - Optional segment caching for performance optimization

    Example:
        >>> evaluator = SegmentEvaluator()
        >>> context = EvaluationContext(
        ...     user_id="user-123",
        ...     attributes={"country": "US", "plan": "premium"}
        ... )
        >>> is_member = await evaluator.is_in_segment(
        ...     segment_id=segment.id,
        ...     context=context,
        ...     storage=storage_backend,
        ... )

    """

    async def is_in_segment(
        self,
        segment_id: UUID,
        context: EvaluationContext,
        storage: StorageBackend,
        segment_cache: dict[UUID, Segment] | None = None,
        _visited: set[UUID] | None = None,
    ) -> bool:
        """Check if the context is a member of the specified segment.

        Evaluates segment membership by checking conditions against the
        context attributes. For nested segments, also verifies membership
        in all parent segments.

        Args:
            segment_id: The UUID of the segment to check membership for.
            context: The evaluation context containing user attributes.
            storage: The storage backend for fetching segment data.
            segment_cache: Optional cache dict to avoid repeated storage lookups.
                If provided, segments will be stored/retrieved from this cache.
            _visited: Internal parameter for circular reference detection.
                Should not be provided by external callers.

        Returns:
            True if the context matches all segment conditions and parent
            segment conditions (if any), False otherwise.

        Raises:
            CircularSegmentReferenceError: If a circular reference is detected
                in the segment parent chain.

        Example:
            >>> # Simple segment check
            >>> is_premium = await evaluator.is_in_segment(
            ...     segment_id=premium_segment.id,
            ...     context=context,
            ...     storage=storage,
            ... )

            >>> # With caching for multiple evaluations
            >>> cache = {}
            >>> for segment_id in segment_ids:
            ...     await evaluator.is_in_segment(
            ...         segment_id=segment_id,
            ...         context=context,
            ...         storage=storage,
            ...         segment_cache=cache,
            ...     )

        """
        # Initialize visited set for circular reference detection
        if _visited is None:
            _visited = set()

        # Check for circular reference
        if segment_id in _visited:
            raise CircularSegmentReferenceError(
                segment_id=segment_id,
                visited_chain=list(_visited),
            )

        # Mark this segment as visited
        _visited.add(segment_id)

        # Try to get segment from cache first
        segment: Segment | None = None
        if segment_cache is not None:
            segment = segment_cache.get(segment_id)

        # Fetch from storage if not cached
        if segment is None:
            segment = await storage.get_segment(segment_id)
            if segment is not None and segment_cache is not None:
                segment_cache[segment_id] = segment

        # Segment not found
        if segment is None:
            return False

        # Disabled segments never match
        if not segment.enabled:
            return False

        # If this segment has a parent, check parent membership first
        if segment.parent_segment_id is not None:
            parent_in_segment = await self.is_in_segment(
                segment_id=segment.parent_segment_id,
                context=context,
                storage=storage,
                segment_cache=segment_cache,
                _visited=_visited,
            )
            if not parent_in_segment:
                return False

        # Check this segment's conditions
        return self._matches_conditions(segment.conditions, context)

    def _matches_conditions(
        self,
        conditions: list[dict[str, Any]],
        context: EvaluationContext,
    ) -> bool:
        """Check if all conditions match the context (AND logic).

        All conditions must match for the overall result to be True.
        Empty conditions list returns True (matches all contexts).

        Args:
            conditions: List of condition dictionaries with keys:
                - attribute: The context attribute to check
                - operator: The comparison operator (RuleOperator value)
                - value: The expected value to compare against
            context: The evaluation context with user attributes.

        Returns:
            True if all conditions match, False otherwise.

        Example:
            >>> conditions = [
            ...     {"attribute": "country", "operator": "in", "value": ["US", "CA"]},
            ...     {"attribute": "plan", "operator": "eq", "value": "premium"}
            ... ]
            >>> # Returns True only if country is US or CA AND plan is premium

        """
        if not conditions:
            return True

        for condition in conditions:
            attribute = condition.get("attribute")
            operator_str = condition.get("operator", "eq")
            expected = condition.get("value")

            if attribute is None:
                continue

            try:
                operator = RuleOperator(operator_str)
            except ValueError:
                continue

            actual = context.get(attribute)

            if not self._evaluate_condition(actual, operator, expected):
                return False

        return True

    def _evaluate_condition(
        self,
        actual: Any,
        operator: RuleOperator,
        expected: Any,
    ) -> bool:
        """Evaluate a single condition.

        Args:
            actual: The actual value from the context.
            operator: The comparison operator to use.
            expected: The expected value to compare against.

        Returns:
            True if the condition matches, False otherwise.

        """
        match operator:
            case RuleOperator.EQUALS:
                return actual == expected
            case RuleOperator.NOT_EQUALS:
                return actual != expected
            case RuleOperator.GREATER_THAN:
                return actual is not None and actual > expected
            case RuleOperator.GREATER_THAN_OR_EQUAL:
                return actual is not None and actual >= expected
            case RuleOperator.LESS_THAN:
                return actual is not None and actual < expected
            case RuleOperator.LESS_THAN_OR_EQUAL:
                return actual is not None and actual <= expected
            case RuleOperator.IN:
                return actual in expected if expected else False
            case RuleOperator.NOT_IN:
                return actual not in expected if expected else True
            case RuleOperator.CONTAINS:
                return expected in actual if actual else False
            case RuleOperator.NOT_CONTAINS:
                return expected not in actual if actual else True
            case RuleOperator.STARTS_WITH:
                return str(actual).startswith(str(expected)) if actual else False
            case RuleOperator.ENDS_WITH:
                return str(actual).endswith(str(expected)) if actual else False
            case RuleOperator.MATCHES:
                try:
                    return bool(re.match(expected, str(actual))) if actual else False
                except re.error:
                    return False
            case RuleOperator.SEMVER_EQ | RuleOperator.SEMVER_GT | RuleOperator.SEMVER_LT:
                return self._compare_semver(actual, operator, expected)
            case RuleOperator.DATE_AFTER:
                return self._compare_date_after(actual, expected)
            case RuleOperator.DATE_BEFORE:
                return self._compare_date_before(actual, expected)
            case RuleOperator.TIME_WINDOW:
                return self._check_time_window(actual, expected)
            case RuleOperator.IN_SEGMENT | RuleOperator.NOT_IN_SEGMENT:
                # Segment operators are handled at a higher level
                # They should not appear in segment conditions themselves
                return False
            case _:
                return False

    def _compare_semver(
        self,
        actual: Any,
        operator: RuleOperator,
        expected: Any,
    ) -> bool:
        """Compare semantic versions.

        Args:
            actual: The actual version string.
            operator: The semver comparison operator.
            expected: The expected version string.

        Returns:
            True if the comparison matches, False otherwise.

        """
        if actual is None or expected is None:
            return False

        try:
            actual_parts = [int(x) for x in str(actual).split(".")]
            expected_parts = [int(x) for x in str(expected).split(".")]

            # Pad to same length
            max_len = max(len(actual_parts), len(expected_parts))
            actual_parts.extend([0] * (max_len - len(actual_parts)))
            expected_parts.extend([0] * (max_len - len(expected_parts)))

            match operator:
                case RuleOperator.SEMVER_EQ:
                    return actual_parts == expected_parts
                case RuleOperator.SEMVER_GT:
                    return actual_parts > expected_parts
                case RuleOperator.SEMVER_LT:
                    return actual_parts < expected_parts
                case _:
                    return False
        except (ValueError, AttributeError):
            return False

    def _parse_datetime(self, value: Any) -> datetime | None:
        """Parse a value into a datetime object.

        Args:
            value: The value to parse (datetime, str, or int/float timestamp).

        Returns:
            A datetime object or None if parsing fails.

        """
        if value is None:
            return None

        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            try:
                for fmt in [
                    "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%S.%f%z",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d",
                ]:
                    try:
                        return datetime.strptime(value, fmt)
                    except ValueError:
                        continue
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return None

        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value, tz=UTC)
            except (ValueError, OSError, OverflowError):
                return None

        return None

    def _normalize_datetime(
        self,
        dt: datetime,
        target_tz: timezone | None = None,
    ) -> datetime:
        """Normalize a datetime to a target timezone.

        Args:
            dt: The datetime to normalize.
            target_tz: Target timezone. If None, uses UTC.

        Returns:
            Timezone-aware datetime in the target timezone.

        """
        target_tz = target_tz or UTC

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        return dt.astimezone(target_tz)

    def _compare_date_after(self, actual: Any, expected: Any) -> bool:
        """Compare if actual datetime is after expected datetime.

        Args:
            actual: The actual datetime from context.
            expected: The expected datetime to compare against.

        Returns:
            True if actual is after expected, False otherwise.

        """
        actual_dt = self._parse_datetime(actual)
        expected_dt = self._parse_datetime(expected)

        if actual_dt is None or expected_dt is None:
            return False

        actual_dt = self._normalize_datetime(actual_dt)
        expected_dt = self._normalize_datetime(expected_dt)

        return actual_dt > expected_dt

    def _compare_date_before(self, actual: Any, expected: Any) -> bool:
        """Compare if actual datetime is before expected datetime.

        Args:
            actual: The actual datetime from context.
            expected: The expected datetime to compare against.

        Returns:
            True if actual is before expected, False otherwise.

        """
        actual_dt = self._parse_datetime(actual)
        expected_dt = self._parse_datetime(expected)

        if actual_dt is None or expected_dt is None:
            return False

        actual_dt = self._normalize_datetime(actual_dt)
        expected_dt = self._normalize_datetime(expected_dt)

        return actual_dt < expected_dt

    def _check_time_window(self, actual: Any, expected: Any) -> bool:
        """Check if actual datetime falls within a time window.

        Args:
            actual: The actual datetime from context.
            expected: Dict with start, end, and optional timezone.

        Returns:
            True if actual falls within the time window, False otherwise.

        """
        if not isinstance(expected, dict):
            return False

        start = expected.get("start")
        end = expected.get("end")

        if start is None or end is None:
            return False

        actual_dt = self._parse_datetime(actual)
        if actual_dt is None:
            return False

        # Check if start/end are time-only (HH:MM or HH:MM:SS format)
        if isinstance(start, str) and len(start) <= 8 and "T" not in start:
            return self._check_time_only_window(actual_dt, start, end)

        # Parse as full datetimes
        start_dt = self._parse_datetime(start)
        end_dt = self._parse_datetime(end)

        if start_dt is None or end_dt is None:
            return False

        actual_dt = self._normalize_datetime(actual_dt)
        start_dt = self._normalize_datetime(start_dt)
        end_dt = self._normalize_datetime(end_dt)

        return start_dt <= actual_dt <= end_dt

    def _check_time_only_window(
        self,
        actual_dt: datetime,
        start_str: str,
        end_str: Any,
    ) -> bool:
        """Check if actual time falls within a time-of-day window.

        Args:
            actual_dt: The actual datetime.
            start_str: Start time as HH:MM or HH:MM:SS string.
            end_str: End time as HH:MM or HH:MM:SS string.

        Returns:
            True if actual time is within the window, False otherwise.

        """
        if not isinstance(end_str, str):
            return False

        try:
            start_parts = [int(p) for p in start_str.split(":")]
            end_parts = [int(p) for p in end_str.split(":")]

            while len(start_parts) < 3:
                start_parts.append(0)
            while len(end_parts) < 3:
                end_parts.append(0)

            start_time = time(start_parts[0], start_parts[1], start_parts[2])
            end_time = time(end_parts[0], end_parts[1], end_parts[2])

            actual_time = actual_dt.time()

            if start_time <= end_time:
                return start_time <= actual_time <= end_time
            else:
                return actual_time >= start_time or actual_time <= end_time

        except (ValueError, IndexError):
            return False
