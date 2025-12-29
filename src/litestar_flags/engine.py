"""Evaluation engine for feature flag evaluation."""

from __future__ import annotations

import re
import struct
from datetime import UTC, datetime, time, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

from litestar_flags.results import EvaluationDetails
from litestar_flags.segment_evaluator import CircularSegmentReferenceError, SegmentEvaluator
from litestar_flags.types import ErrorCode, EvaluationReason, FlagStatus, FlagType, RuleOperator

if TYPE_CHECKING:
    from litestar_flags.context import EvaluationContext
    from litestar_flags.models.flag import FeatureFlag
    from litestar_flags.models.override import FlagOverride
    from litestar_flags.models.rule import FlagRule
    from litestar_flags.models.segment import Segment
    from litestar_flags.models.variant import FlagVariant
    from litestar_flags.protocols import StorageBackend
    from litestar_flags.time_rules import TimeBasedRuleEvaluator

__all__ = ["EvaluationEngine"]


class EvaluationEngine:
    """Core flag evaluation logic.

    Implements rule matching, percentage rollouts using Murmur3 hashing,
    and variant selection for A/B testing.

    The evaluation flow is:
        1. Check if flag is disabled/archived
        2. Check for entity-specific override
        3. Check time schedules (if time evaluator provided)
        4. Evaluate targeting rules (in priority order)
        5. Apply percentage rollout if configured
        6. Select variant if multivariate flag
        7. Return default value

    Attributes:
        time_evaluator: Optional time-based rule evaluator for schedule support.
        segment_evaluator: Optional segment evaluator for segment-based targeting.

    """

    def __init__(
        self,
        time_evaluator: TimeBasedRuleEvaluator | None = None,
        segment_evaluator: SegmentEvaluator | None = None,
    ) -> None:
        """Initialize the evaluation engine.

        Args:
            time_evaluator: Optional time-based rule evaluator. If not provided,
                time schedule evaluation will be skipped.
            segment_evaluator: Optional segment evaluator. If not provided,
                a default SegmentEvaluator will be created when needed.

        """
        self._time_evaluator = time_evaluator
        self._segment_evaluator = segment_evaluator

    @property
    def time_evaluator(self) -> TimeBasedRuleEvaluator | None:
        """Get the time-based rule evaluator."""
        return self._time_evaluator

    @time_evaluator.setter
    def time_evaluator(self, evaluator: TimeBasedRuleEvaluator | None) -> None:
        """Set the time-based rule evaluator."""
        self._time_evaluator = evaluator

    @property
    def segment_evaluator(self) -> SegmentEvaluator | None:
        """Get the segment evaluator."""
        return self._segment_evaluator

    @segment_evaluator.setter
    def segment_evaluator(self, evaluator: SegmentEvaluator | None) -> None:
        """Set the segment evaluator."""
        self._segment_evaluator = evaluator

    def _get_segment_evaluator(self) -> SegmentEvaluator:
        """Get or create a segment evaluator.

        Returns:
            The configured segment evaluator or a new default instance.

        """
        if self._segment_evaluator is None:
            self._segment_evaluator = SegmentEvaluator()
        return self._segment_evaluator

    async def evaluate(
        self,
        flag: FeatureFlag,
        context: EvaluationContext,
        storage: StorageBackend,
        time_evaluator: TimeBasedRuleEvaluator | None = None,
        segment_cache: dict[UUID, Segment] | None = None,
    ) -> EvaluationDetails[Any]:
        """Evaluate a flag against the provided context.

        Args:
            flag: The feature flag to evaluate.
            context: The evaluation context with user/entity attributes.
            storage: The storage backend for fetching overrides.
            time_evaluator: Optional time evaluator override. If not provided,
                uses the instance's time_evaluator.
            segment_cache: Optional cache for segment lookups. If provided,
                segments will be cached here for reuse across evaluations.

        Returns:
            EvaluationDetails with the result and metadata.

        """
        # Use provided time_evaluator or fall back to instance's evaluator
        effective_time_evaluator = time_evaluator or self.time_evaluator

        # 1. Check flag status
        if flag.status != FlagStatus.ACTIVE:
            return self._create_result(
                flag=flag,
                value=self._get_default_value(flag),
                reason=EvaluationReason.DISABLED,
            )

        # 2. Check for overrides
        override_result = await self._check_overrides(flag, context, storage)
        if override_result is not None:
            return override_result

        # 3. Check time schedules (if time evaluator and schedules available)
        if effective_time_evaluator is not None:
            time_result = await self._check_time_schedules(
                flag,
                context,
                effective_time_evaluator,
            )
            if time_result is not None:
                return time_result

        # 4. Evaluate rules (now async to support segment evaluation)
        rule_result = await self._evaluate_rules(flag, context, storage, segment_cache)
        if rule_result is not None:
            return rule_result

        # 5. Check variants (for multivariate flags)
        if flag.variants:
            variant = self._select_variant(flag, context)
            if variant is not None:
                return self._create_result(
                    flag=flag,
                    value=variant.value if flag.flag_type != FlagType.BOOLEAN else variant.value.get("enabled", False),
                    reason=EvaluationReason.SPLIT,
                    variant=variant.key,
                )

        # 6. Return default
        return self._create_result(
            flag=flag,
            value=self._get_default_value(flag),
            reason=EvaluationReason.STATIC,
        )

    async def _check_time_schedules(
        self,
        flag: FeatureFlag,
        context: EvaluationContext,
        time_evaluator: TimeBasedRuleEvaluator,
    ) -> EvaluationDetails[Any] | None:
        """Check if any time schedules affect the flag evaluation.

        Time schedules can override the flag's default behavior based on
        the current time.

        Args:
            flag: The feature flag to evaluate.
            context: The evaluation context.
            time_evaluator: The time-based rule evaluator.

        Returns:
            EvaluationDetails if a schedule applies, None otherwise.

        """
        # Check if flag has time_schedules attribute
        if not (schedules := getattr(flag, "time_schedules", None)):
            return None

        # Evaluate each schedule
        for schedule in schedules:
            if time_evaluator.evaluate_schedule(schedule, context):
                # Schedule is active - flag should be enabled
                return self._create_result(
                    flag=flag,
                    value=True if flag.flag_type == FlagType.BOOLEAN else flag.default_value,
                    reason=EvaluationReason.TARGETING_MATCH,
                    variant=f"schedule:{schedule.name}",
                )

        # No active schedule found - flag is disabled by schedule
        return self._create_result(
            flag=flag,
            value=False if flag.flag_type == FlagType.BOOLEAN else None,
            reason=EvaluationReason.DISABLED,
        )

    async def _check_overrides(
        self,
        flag: FeatureFlag,
        context: EvaluationContext,
        storage: StorageBackend,
    ) -> EvaluationDetails[Any] | None:
        """Check for entity-specific overrides.

        Checks overrides in order of specificity:
        1. User-level override
        2. Organization-level override
        3. Tenant-level override
        """
        override_checks = [
            ("user", context.user_id),
            ("organization", context.organization_id),
            ("tenant", context.tenant_id),
        ]

        # Also check targeting_key as a fallback
        if context.targeting_key and context.targeting_key not in [
            context.user_id,
            context.organization_id,
            context.tenant_id,
        ]:
            override_checks.append(("targeting_key", context.targeting_key))

        for entity_type, entity_id in override_checks:
            if entity_id is not None:
                override = await storage.get_override(flag.id, entity_type, entity_id)
                if override is not None and not override.is_expired():
                    return self._create_override_result(flag, override)

        return None

    def _create_override_result(
        self,
        flag: FeatureFlag,
        override: FlagOverride,
    ) -> EvaluationDetails[Any]:
        """Create evaluation result from an override."""
        if flag.flag_type == FlagType.BOOLEAN:
            value = override.enabled
        elif override.value is not None:
            value = override.value
        else:
            value = override.enabled

        return self._create_result(
            flag=flag,
            value=value,
            reason=EvaluationReason.OVERRIDE,
        )

    async def _evaluate_rules(
        self,
        flag: FeatureFlag,
        context: EvaluationContext,
        storage: StorageBackend,
        segment_cache: dict[UUID, Segment] | None = None,
    ) -> EvaluationDetails[Any] | None:
        """Evaluate targeting rules in priority order.

        Args:
            flag: The feature flag to evaluate.
            context: The evaluation context.
            storage: The storage backend for segment lookups.
            segment_cache: Optional cache for segment lookups.

        Returns:
            EvaluationDetails if a rule matches, None otherwise.

        """
        for rule in sorted(flag.rules, key=lambda r: r.priority):
            if not rule.enabled:
                continue

            if await self._matches_conditions(rule.conditions, context, storage, segment_cache):
                # Check percentage rollout
                if rule.rollout_percentage is not None:
                    if not self._in_rollout(
                        flag.key,
                        context.targeting_key,
                        rule.rollout_percentage,
                    ):
                        continue

                return self._create_rule_result(flag, rule)

        return None

    def _create_rule_result(
        self,
        flag: FeatureFlag,
        rule: FlagRule,
    ) -> EvaluationDetails[Any]:
        """Create evaluation result from a matching rule."""
        if flag.flag_type == FlagType.BOOLEAN:
            value = rule.serve_enabled
        elif rule.serve_value is not None:
            value = rule.serve_value
        else:
            value = rule.serve_enabled

        return self._create_result(
            flag=flag,
            value=value,
            reason=EvaluationReason.TARGETING_MATCH,
            variant=rule.name,
        )

    async def _matches_conditions(
        self,
        conditions: list[dict[str, Any]],
        context: EvaluationContext,
        storage: StorageBackend | None = None,
        segment_cache: dict[UUID, Segment] | None = None,
    ) -> bool:
        """Check if all conditions match (AND logic).

        Args:
            conditions: List of condition dictionaries.
            context: The evaluation context.
            storage: Optional storage backend for segment lookups.
            segment_cache: Optional cache for segment lookups.

        Returns:
            True if all conditions match, False otherwise.

        """
        if not conditions:
            return True

        for condition in conditions:
            attribute = condition.get("attribute")
            operator_str = condition.get("operator", "eq")
            expected = condition.get("value")

            if attribute is None:
                # No attribute specified, skip this condition
                continue

            try:
                operator = RuleOperator(operator_str)
            except ValueError:
                # Unknown operator, skip this condition
                continue

            # Handle segment operators separately (they are async)
            if operator in (RuleOperator.IN_SEGMENT, RuleOperator.NOT_IN_SEGMENT):
                if storage is None or expected is None:
                    # Cannot evaluate segment condition without storage or segment ID
                    return False
                try:
                    segment_result = await self._evaluate_segment_condition(
                        operator=operator,
                        segment_id=str(expected),
                        context=context,
                        storage=storage,
                        segment_cache=segment_cache,
                    )
                    if not segment_result:
                        return False
                except CircularSegmentReferenceError:
                    # Circular reference detected, condition fails
                    return False
                continue

            actual = context.get(attribute)

            if not self._evaluate_condition(actual, operator, expected):
                return False

        return True

    async def _evaluate_segment_condition(
        self,
        operator: RuleOperator,
        segment_id: str,
        context: EvaluationContext,
        storage: StorageBackend,
        segment_cache: dict[UUID, Segment] | None = None,
    ) -> bool:
        """Evaluate a segment-based condition.

        The segment_id can be either a segment name or a UUID string.
        This method first tries to parse it as a UUID; if that fails,
        it looks up the segment by name.

        Args:
            operator: The segment operator (IN_SEGMENT or NOT_IN_SEGMENT).
            segment_id: The segment name or UUID string from the condition value.
            context: The evaluation context.
            storage: The storage backend for segment lookups.
            segment_cache: Optional cache for segment lookups.

        Returns:
            True if the segment condition matches, False otherwise.

        Raises:
            CircularSegmentReferenceError: If a circular segment reference is detected.

        """
        evaluator = self._get_segment_evaluator()

        # Try to parse as UUID first
        segment_uuid: UUID | None = None
        try:
            segment_uuid = UUID(segment_id)
        except (ValueError, TypeError):
            # Not a valid UUID, treat as segment name
            pass

        if segment_uuid is None:
            # Look up segment by name
            segment = await storage.get_segment_by_name(segment_id)
            if segment is None:
                # Segment not found by name, condition fails for IN_SEGMENT
                # and succeeds for NOT_IN_SEGMENT
                return operator == RuleOperator.NOT_IN_SEGMENT
            segment_uuid = segment.id
            # Cache the segment if cache is provided
            if segment_cache is not None:
                segment_cache[segment_uuid] = segment

        # Evaluate segment membership
        is_in_segment = await evaluator.is_in_segment(
            segment_id=segment_uuid,
            context=context,
            storage=storage,
            segment_cache=segment_cache,
        )

        if operator == RuleOperator.IN_SEGMENT:
            return is_in_segment
        else:  # NOT_IN_SEGMENT
            return not is_in_segment

    def _evaluate_condition(
        self,
        actual: Any,
        operator: RuleOperator,
        expected: Any,
    ) -> bool:
        """Evaluate a single condition.

        Args:
            actual: The actual value from context.
            operator: The comparison operator.
            expected: The expected value.

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
                # Segment operators are handled in _matches_conditions
                # They should not reach here
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

        Handles datetime objects, ISO 8601 strings, and timestamps.

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
                # Try ISO 8601 format (with or without timezone)
                # Handle common formats
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
                # Try fromisoformat as fallback (handles more variations)
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return None

        if isinstance(value, int | float):
            try:
                # Assume Unix timestamp
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
            # Assume naive datetime is in UTC
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

        # Normalize both to UTC for comparison
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

        # Normalize both to UTC for comparison
        actual_dt = self._normalize_datetime(actual_dt)
        expected_dt = self._normalize_datetime(expected_dt)

        return actual_dt < expected_dt

    def _check_time_window(self, actual: Any, expected: Any) -> bool:
        """Check if actual datetime falls within a time window.

        The expected value should be a dictionary with:
            - start: Start datetime or time string (ISO 8601 or HH:MM)
            - end: End datetime or time string (ISO 8601 or HH:MM)
            - timezone: Optional timezone name (default: UTC)

        For time-only windows (HH:MM format), only the time portion is checked.

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

        # Normalize all to UTC
        actual_dt = self._normalize_datetime(actual_dt)
        start_dt = self._normalize_datetime(start_dt)
        end_dt = self._normalize_datetime(end_dt)

        return start_dt <= actual_dt <= end_dt

    def _check_time_only_window(
        self,
        actual_dt: datetime,
        start_str: str,
        end_str: str,
    ) -> bool:
        """Check if actual time falls within a time-of-day window.

        Handles windows that span midnight (e.g., 22:00 to 06:00).

        Args:
            actual_dt: The actual datetime.
            start_str: Start time as HH:MM or HH:MM:SS string.
            end_str: End time as HH:MM or HH:MM:SS string.

        Returns:
            True if actual time is within the window, False otherwise.

        """
        try:
            start_parts = [int(p) for p in start_str.split(":")]
            end_parts = [int(p) for p in end_str.split(":")]

            # Pad to 3 parts (hour, minute, second)
            start_parts += [0] * (3 - len(start_parts))
            end_parts += [0] * (3 - len(end_parts))

            start_time = time(start_parts[0], start_parts[1], start_parts[2])
            end_time = time(end_parts[0], end_parts[1], end_parts[2])

            actual_time = actual_dt.time()

            # Handle window that spans midnight
            if start_time <= end_time:
                # Normal window (e.g., 09:00 to 17:00)
                return start_time <= actual_time <= end_time
            else:
                # Window spans midnight (e.g., 22:00 to 06:00)
                return actual_time >= start_time or actual_time <= end_time

        except (ValueError, IndexError):
            return False

    def _in_rollout(
        self,
        flag_key: str,
        targeting_key: str | None,
        percentage: int,
    ) -> bool:
        """Determine if a user is in a percentage rollout.

        Uses Murmur3 hashing for consistent, deterministic assignment.
        The same targeting_key will always get the same result for the same flag.

        Args:
            flag_key: The flag key (used as part of hash seed).
            targeting_key: The user's targeting key.
            percentage: Rollout percentage (0-100).

        Returns:
            True if the user is in the rollout, False otherwise.

        """
        if targeting_key is None:
            return False

        if percentage >= 100:
            return True
        if percentage <= 0:
            return False

        # Hash flag_key + targeting_key for consistent assignment
        hash_input = f"{flag_key}:{targeting_key}".encode()
        hash_value = self._murmur3_32(hash_input)

        # Normalize to 0-100 range (using modulo for simplicity)
        bucket = (hash_value % 100) + 1

        return bucket <= percentage

    def _murmur3_32(self, data: bytes, seed: int = 0) -> int:
        """Murmur3 32-bit hash implementation.

        This is a well-known non-cryptographic hash function that provides
        good distribution for bucketing users into percentage rollouts.

        Args:
            data: The data to hash.
            seed: Optional seed value.

        Returns:
            32-bit hash value.

        """
        c1 = 0xCC9E2D51
        c2 = 0x1B873593

        h1 = seed
        length = len(data)

        # Process 4-byte chunks
        for i in range(0, length - 3, 4):
            k1 = struct.unpack("<I", data[i : i + 4])[0]
            k1 = (k1 * c1) & 0xFFFFFFFF
            k1 = ((k1 << 15) | (k1 >> 17)) & 0xFFFFFFFF
            k1 = (k1 * c2) & 0xFFFFFFFF

            h1 ^= k1
            h1 = ((h1 << 13) | (h1 >> 19)) & 0xFFFFFFFF
            h1 = ((h1 * 5) + 0xE6546B64) & 0xFFFFFFFF

        # Process remaining bytes
        remaining = length & 3
        if remaining:
            k1 = 0
            for j in range(remaining):
                k1 |= data[length - remaining + j] << (8 * j)
            k1 = (k1 * c1) & 0xFFFFFFFF
            k1 = ((k1 << 15) | (k1 >> 17)) & 0xFFFFFFFF
            k1 = (k1 * c2) & 0xFFFFFFFF
            h1 ^= k1

        # Finalization
        h1 ^= length
        h1 ^= h1 >> 16
        h1 = (h1 * 0x85EBCA6B) & 0xFFFFFFFF
        h1 ^= h1 >> 13
        h1 = (h1 * 0xC2B2AE35) & 0xFFFFFFFF
        h1 ^= h1 >> 16

        return h1

    def _select_variant(
        self,
        flag: FeatureFlag,
        context: EvaluationContext,
    ) -> FlagVariant | None:
        """Select a variant based on weights and targeting key.

        Uses consistent hashing to ensure the same user always gets
        the same variant for a given flag.

        Args:
            flag: The feature flag with variants.
            context: The evaluation context.

        Returns:
            The selected variant, or None if no variants are defined.

        """
        if not flag.variants:
            return None

        targeting_key = context.targeting_key or ""
        hash_input = f"{flag.key}:variant:{targeting_key}".encode()
        hash_value = self._murmur3_32(hash_input)
        bucket = hash_value % 100

        cumulative = 0
        sorted_variants = sorted(flag.variants, key=lambda v: v.key)

        for variant in sorted_variants:
            cumulative += variant.weight
            if bucket < cumulative:
                return variant

        # Return last variant if weights don't sum to 100
        return sorted_variants[-1] if sorted_variants else None

    def _get_default_value(self, flag: FeatureFlag) -> Any:
        """Get the default value for a flag based on its type."""
        if flag.flag_type == FlagType.BOOLEAN:
            return flag.default_enabled
        return flag.default_value

    def _create_result(
        self,
        flag: FeatureFlag,
        value: Any,
        reason: EvaluationReason,
        variant: str | None = None,
        error_code: ErrorCode | None = None,
        error_message: str | None = None,
    ) -> EvaluationDetails[Any]:
        """Create an evaluation result.

        Args:
            flag: The evaluated flag.
            value: The evaluated value.
            reason: The reason for the result.
            variant: Optional variant key.
            error_code: Optional error code.
            error_message: Optional error message.

        Returns:
            EvaluationDetails object.

        """
        return EvaluationDetails(
            value=value,
            flag_key=flag.key,
            reason=reason,
            variant=variant,
            error_code=error_code,
            error_message=error_message,
            flag_metadata={
                "flag_type": flag.flag_type.value,
                "status": flag.status.value,
                "tags": flag.tags,
            },
        )
