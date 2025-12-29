"""Tests for EvaluationEngine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from litestar_flags import EvaluationContext, EvaluationReason, MemoryStorageBackend
from litestar_flags.engine import EvaluationEngine
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.models.override import FlagOverride
from litestar_flags.models.rule import FlagRule
from litestar_flags.models.variant import FlagVariant
from litestar_flags.types import FlagStatus, FlagType


class TestEvaluationEngine:
    """Tests for EvaluationEngine."""

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        """Create an evaluation engine."""
        return EvaluationEngine()

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        """Create a memory storage backend."""
        return MemoryStorageBackend()

    async def test_disabled_flag_returns_default(self, engine: EvaluationEngine, storage: MemoryStorageBackend) -> None:
        """Test that disabled flags return the default value."""
        flag = FeatureFlag(
            id=uuid4(),
            key="disabled",
            name="Disabled Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.INACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        context = EvaluationContext()

        result = await engine.evaluate(flag, context, storage)

        assert result.value is True  # default_enabled
        assert result.reason == EvaluationReason.DISABLED

    async def test_override_takes_precedence(self, engine: EvaluationEngine, storage: MemoryStorageBackend) -> None:
        """Test that overrides take precedence over rules."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="override-test",
            name="Override Test",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="All Users",
                    priority=0,
                    enabled=True,
                    conditions=[],
                    serve_enabled=True,
                )
            ],
            overrides=[],
            variants=[],
        )

        # Create override
        override = FlagOverride(
            id=uuid4(),
            flag_id=flag_id,
            entity_type="user",
            entity_id="user-123",
            enabled=False,
        )
        await storage.create_override(override)

        context = EvaluationContext(targeting_key="user-123", user_id="user-123")

        result = await engine.evaluate(flag, context, storage)

        assert result.value is False
        assert result.reason == EvaluationReason.OVERRIDE

    async def test_expired_override_ignored(self, engine: EvaluationEngine, storage: MemoryStorageBackend) -> None:
        """Test that expired overrides are ignored."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="expired-override",
            name="Expired Override",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        # Create expired override
        override = FlagOverride(
            id=uuid4(),
            flag_id=flag_id,
            entity_type="user",
            entity_id="user-123",
            enabled=True,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        await storage.create_override(override)

        context = EvaluationContext(user_id="user-123")

        result = await engine.evaluate(flag, context, storage)

        assert result.value is False  # Falls to default
        assert result.reason == EvaluationReason.STATIC


class TestConditionEvaluation:
    """Tests for rule condition evaluation."""

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        return EvaluationEngine()

    async def test_equals_operator(self, engine: EvaluationEngine) -> None:
        """Test EQUALS operator."""
        conditions = [{"attribute": "plan", "operator": "eq", "value": "premium"}]
        context = EvaluationContext(attributes={"plan": "premium"})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"plan": "free"})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_not_equals_operator(self, engine: EvaluationEngine) -> None:
        """Test NOT_EQUALS operator."""
        conditions = [{"attribute": "plan", "operator": "ne", "value": "free"}]
        context = EvaluationContext(attributes={"plan": "premium"})
        assert await engine._matches_conditions(conditions, context) is True

    async def test_in_operator(self, engine: EvaluationEngine) -> None:
        """Test IN operator."""
        conditions = [{"attribute": "country", "operator": "in", "value": ["US", "CA", "UK"]}]

        context = EvaluationContext(attributes={"country": "US"})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"country": "DE"})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_not_in_operator(self, engine: EvaluationEngine) -> None:
        """Test NOT_IN operator."""
        conditions = [{"attribute": "country", "operator": "not_in", "value": ["CN", "RU"]}]

        context = EvaluationContext(attributes={"country": "US"})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"country": "CN"})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_greater_than_operator(self, engine: EvaluationEngine) -> None:
        """Test GREATER_THAN operator."""
        conditions = [{"attribute": "age", "operator": "gt", "value": 18}]

        context = EvaluationContext(attributes={"age": 21})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"age": 18})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_contains_operator(self, engine: EvaluationEngine) -> None:
        """Test CONTAINS operator."""
        conditions = [{"attribute": "email", "operator": "contains", "value": "@company.com"}]

        context = EvaluationContext(attributes={"email": "user@company.com"})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"email": "user@other.com"})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_starts_with_operator(self, engine: EvaluationEngine) -> None:
        """Test STARTS_WITH operator."""
        conditions = [{"attribute": "email", "operator": "starts_with", "value": "admin"}]

        context = EvaluationContext(attributes={"email": "admin@company.com"})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"email": "user@company.com"})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_matches_operator(self, engine: EvaluationEngine) -> None:
        """Test MATCHES (regex) operator."""
        conditions = [{"attribute": "email", "operator": "matches", "value": r".*@company\.com$"}]

        context = EvaluationContext(attributes={"email": "user@company.com"})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"email": "user@other.com"})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_multiple_conditions_and_logic(self, engine: EvaluationEngine) -> None:
        """Test that multiple conditions use AND logic."""
        conditions = [
            {"attribute": "plan", "operator": "eq", "value": "premium"},
            {"attribute": "country", "operator": "in", "value": ["US", "CA"]},
        ]

        # Both match
        context = EvaluationContext(attributes={"plan": "premium", "country": "US"})
        assert await engine._matches_conditions(conditions, context) is True

        # Only one matches
        context = EvaluationContext(attributes={"plan": "premium", "country": "DE"})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_empty_conditions_match_all(self, engine: EvaluationEngine) -> None:
        """Test that empty conditions match all contexts."""
        conditions: list[dict] = []
        context = EvaluationContext()
        assert await engine._matches_conditions(conditions, context) is True


class TestPercentageRollout:
    """Tests for percentage rollout using Murmur3 hashing."""

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        return EvaluationEngine()

    def test_zero_percent_never_matches(self, engine: EvaluationEngine) -> None:
        """Test that 0% rollout never includes anyone."""
        for i in range(100):
            result = engine._in_rollout("test-flag", f"user-{i}", 0)
            assert result is False

    def test_hundred_percent_always_matches(self, engine: EvaluationEngine) -> None:
        """Test that 100% rollout includes everyone."""
        for i in range(100):
            result = engine._in_rollout("test-flag", f"user-{i}", 100)
            assert result is True

    def test_consistent_hashing(self, engine: EvaluationEngine) -> None:
        """Test that same user always gets same result."""
        flag_key = "consistency-test"
        user_id = "user-123"

        results = [engine._in_rollout(flag_key, user_id, 50) for _ in range(100)]

        # All results should be the same
        assert len(set(results)) == 1

    def test_different_flags_different_buckets(self, engine: EvaluationEngine) -> None:
        """Test that different flags may give different results for same user."""
        user_id = "user-123"

        # With enough different flags, we should see variation
        results = [engine._in_rollout(f"flag-{i}", user_id, 50) for i in range(100)]

        # Should have both True and False results
        assert True in results
        assert False in results

    def test_rollout_distribution(self, engine: EvaluationEngine) -> None:
        """Test that rollout roughly follows the percentage."""
        flag_key = "distribution-test"
        percentage = 30

        enabled_count = sum(1 for i in range(10000) if engine._in_rollout(flag_key, f"user-{i}", percentage))

        # Should be within 5% of expected (25-35%)
        ratio = enabled_count / 10000
        assert 0.25 <= ratio <= 0.35, f"Expected ~30%, got {ratio * 100}%"

    def test_no_targeting_key_returns_false(self, engine: EvaluationEngine) -> None:
        """Test that missing targeting key always returns False."""
        result = engine._in_rollout("test-flag", None, 50)
        assert result is False


class TestVariantSelection:
    """Tests for A/B test variant selection."""

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        return EvaluationEngine()

    def test_consistent_variant_selection(self, engine: EvaluationEngine) -> None:
        """Test that same user always gets same variant."""
        flag = FeatureFlag(
            id=uuid4(),
            key="ab-test",
            name="A/B Test",
            flag_type=FlagType.STRING,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[
                FlagVariant(
                    id=uuid4(),
                    key="control",
                    name="Control",
                    value={"v": "control"},
                    weight=50,
                ),
                FlagVariant(
                    id=uuid4(),
                    key="treatment",
                    name="Treatment",
                    value={"v": "treatment"},
                    weight=50,
                ),
            ],
        )

        context = EvaluationContext(targeting_key="user-123")

        variants = [engine._select_variant(flag, context) for _ in range(100)]

        # All should be the same
        assert len(set(v.key for v in variants if v)) == 1

    def test_variant_distribution(self, engine: EvaluationEngine) -> None:
        """Test that variants are distributed according to weights."""
        flag = FeatureFlag(
            id=uuid4(),
            key="distribution-test",
            name="Distribution Test",
            flag_type=FlagType.STRING,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[
                FlagVariant(
                    id=uuid4(),
                    key="a",
                    name="A",
                    value={"v": "a"},
                    weight=70,
                ),
                FlagVariant(
                    id=uuid4(),
                    key="b",
                    name="B",
                    value={"v": "b"},
                    weight=30,
                ),
            ],
        )

        counts = {"a": 0, "b": 0}
        for i in range(10000):
            context = EvaluationContext(targeting_key=f"user-{i}")
            variant = engine._select_variant(flag, context)
            if variant:
                counts[variant.key] += 1

        # A should be ~70%, B ~30% (with some tolerance)
        a_ratio = counts["a"] / 10000
        b_ratio = counts["b"] / 10000

        assert 0.65 <= a_ratio <= 0.75, f"Expected A ~70%, got {a_ratio * 100}%"
        assert 0.25 <= b_ratio <= 0.35, f"Expected B ~30%, got {b_ratio * 100}%"

    def test_no_variants_returns_none(self, engine: EvaluationEngine) -> None:
        """Test that flags without variants return None."""
        flag = FeatureFlag(
            id=uuid4(),
            key="no-variants",
            name="No Variants",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        context = EvaluationContext(targeting_key="user-123")
        result = engine._select_variant(flag, context)
        assert result is None

    def test_variant_selection_with_empty_targeting_key(self, engine: EvaluationEngine) -> None:
        """Test variant selection when targeting key is empty or None."""
        flag = FeatureFlag(
            id=uuid4(),
            key="variant-empty-key",
            name="Variant Empty Key",
            flag_type=FlagType.STRING,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[
                FlagVariant(
                    id=uuid4(),
                    key="control",
                    name="Control",
                    value={"v": "control"},
                    weight=50,
                ),
                FlagVariant(
                    id=uuid4(),
                    key="treatment",
                    name="Treatment",
                    value={"v": "treatment"},
                    weight=50,
                ),
            ],
        )

        # Empty targeting key should still work (defaults to empty string)
        context = EvaluationContext(targeting_key=None)
        result = engine._select_variant(flag, context)
        assert result is not None
        assert result.key in ["control", "treatment"]

    def test_variant_weights_not_summing_to_100(self, engine: EvaluationEngine) -> None:
        """Test that variants work when weights don't sum to 100."""
        flag = FeatureFlag(
            id=uuid4(),
            key="weight-test",
            name="Weight Test",
            flag_type=FlagType.STRING,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[
                FlagVariant(id=uuid4(), key="a", name="A", value={"v": "a"}, weight=20),
                FlagVariant(id=uuid4(), key="b", name="B", value={"v": "b"}, weight=30),
                # Total = 50, not 100
            ],
        )

        # Should still work - users with bucket >= 50 should get last variant
        results = set()
        for i in range(1000):
            context = EvaluationContext(targeting_key=f"user-{i}")
            variant = engine._select_variant(flag, context)
            if variant:
                results.add(variant.key)

        # Should see both variants
        assert "a" in results
        assert "b" in results

    def test_single_variant_100_percent(self, engine: EvaluationEngine) -> None:
        """Test single variant with 100% weight."""
        flag = FeatureFlag(
            id=uuid4(),
            key="single-variant",
            name="Single Variant",
            flag_type=FlagType.STRING,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[
                FlagVariant(id=uuid4(), key="only", name="Only", value={"v": "only"}, weight=100),
            ],
        )

        # All users should get the only variant
        for i in range(100):
            context = EvaluationContext(targeting_key=f"user-{i}")
            variant = engine._select_variant(flag, context)
            assert variant is not None
            assert variant.key == "only"


class TestSemverOperators:
    """Tests for semantic version comparison operators."""

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        return EvaluationEngine()

    async def test_semver_eq_exact_match(self, engine: EvaluationEngine) -> None:
        """Test SEMVER_EQ with exact version match."""
        conditions = [{"attribute": "app_version", "operator": "semver_eq", "value": "1.2.3"}]

        context = EvaluationContext(app_version="1.2.3")
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(app_version="1.2.4")
        assert await engine._matches_conditions(conditions, context) is False

    async def test_semver_eq_with_different_lengths(self, engine: EvaluationEngine) -> None:
        """Test SEMVER_EQ when versions have different segment counts."""
        conditions = [{"attribute": "version", "operator": "semver_eq", "value": "1.0"}]

        # 1.0 should equal 1.0.0 (padded with zeros)
        context = EvaluationContext(attributes={"version": "1.0.0"})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"version": "1.0.1"})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_semver_gt_basic(self, engine: EvaluationEngine) -> None:
        """Test SEMVER_GT basic comparisons."""
        conditions = [{"attribute": "version", "operator": "semver_gt", "value": "2.0.0"}]

        # Greater versions
        context = EvaluationContext(attributes={"version": "2.0.1"})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"version": "2.1.0"})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"version": "3.0.0"})
        assert await engine._matches_conditions(conditions, context) is True

        # Equal version (not greater)
        context = EvaluationContext(attributes={"version": "2.0.0"})
        assert await engine._matches_conditions(conditions, context) is False

        # Lesser versions
        context = EvaluationContext(attributes={"version": "1.9.9"})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_semver_lt_basic(self, engine: EvaluationEngine) -> None:
        """Test SEMVER_LT basic comparisons."""
        conditions = [{"attribute": "version", "operator": "semver_lt", "value": "2.0.0"}]

        # Lesser versions
        context = EvaluationContext(attributes={"version": "1.9.9"})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"version": "1.0.0"})
        assert await engine._matches_conditions(conditions, context) is True

        # Equal version (not less)
        context = EvaluationContext(attributes={"version": "2.0.0"})
        assert await engine._matches_conditions(conditions, context) is False

        # Greater versions
        context = EvaluationContext(attributes={"version": "2.0.1"})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_semver_with_none_value(self, engine: EvaluationEngine) -> None:
        """Test semver comparison when actual value is None."""
        conditions = [{"attribute": "version", "operator": "semver_eq", "value": "1.0.0"}]

        context = EvaluationContext(attributes={"version": None})
        assert await engine._matches_conditions(conditions, context) is False

        context = EvaluationContext(attributes={})  # Missing attribute
        assert await engine._matches_conditions(conditions, context) is False

    async def test_semver_with_none_expected(self, engine: EvaluationEngine) -> None:
        """Test semver comparison when expected value is None."""
        conditions = [{"attribute": "version", "operator": "semver_eq", "value": None}]

        context = EvaluationContext(attributes={"version": "1.0.0"})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_semver_with_invalid_format(self, engine: EvaluationEngine) -> None:
        """Test semver comparison with invalid version format."""
        conditions = [{"attribute": "version", "operator": "semver_eq", "value": "1.0.0"}]

        # Non-numeric version parts
        context = EvaluationContext(attributes={"version": "1.x.0"})
        assert await engine._matches_conditions(conditions, context) is False

        # Empty string
        context = EvaluationContext(attributes={"version": ""})
        assert await engine._matches_conditions(conditions, context) is False

        # Non-string value
        context = EvaluationContext(attributes={"version": 100})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_semver_multi_segment(self, engine: EvaluationEngine) -> None:
        """Test semver with 4+ segments."""
        conditions = [{"attribute": "version", "operator": "semver_gt", "value": "1.2.3.4"}]

        context = EvaluationContext(attributes={"version": "1.2.3.5"})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"version": "1.2.3.4"})
        assert await engine._matches_conditions(conditions, context) is False

        context = EvaluationContext(attributes={"version": "1.2.3.3"})
        assert await engine._matches_conditions(conditions, context) is False


class TestRulePriority:
    """Tests for rule priority ordering."""

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        return EvaluationEngine()

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        return MemoryStorageBackend()

    async def test_lower_priority_evaluates_first(
        self, engine: EvaluationEngine, storage: MemoryStorageBackend
    ) -> None:
        """Test that lower priority number rules are evaluated first."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="priority-test",
            name="Priority Test",
            flag_type=FlagType.STRING,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            default_value={"result": "default"},
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Low Priority",
                    priority=10,
                    enabled=True,
                    conditions=[{"attribute": "plan", "operator": "eq", "value": "premium"}],
                    serve_enabled=True,
                    serve_value={"result": "low_priority"},
                ),
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="High Priority",
                    priority=1,
                    enabled=True,
                    conditions=[{"attribute": "plan", "operator": "eq", "value": "premium"}],
                    serve_enabled=True,
                    serve_value={"result": "high_priority"},
                ),
            ],
            overrides=[],
            variants=[],
        )

        context = EvaluationContext(attributes={"plan": "premium"})
        result = await engine.evaluate(flag, context, storage)

        # High priority (lower number) should win
        assert result.value == {"result": "high_priority"}
        assert result.reason == EvaluationReason.TARGETING_MATCH

    async def test_first_matching_rule_wins(self, engine: EvaluationEngine, storage: MemoryStorageBackend) -> None:
        """Test that first matching rule stops evaluation."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="first-match-test",
            name="First Match Test",
            flag_type=FlagType.STRING,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            default_value={"result": "default"},
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="First Rule",
                    priority=1,
                    enabled=True,
                    conditions=[{"attribute": "country", "operator": "eq", "value": "US"}],
                    serve_enabled=True,
                    serve_value={"result": "first"},
                ),
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Second Rule",
                    priority=2,
                    enabled=True,
                    conditions=[{"attribute": "plan", "operator": "eq", "value": "premium"}],
                    serve_enabled=True,
                    serve_value={"result": "second"},
                ),
            ],
            overrides=[],
            variants=[],
        )

        # Both conditions match, but first rule should win
        context = EvaluationContext(attributes={"country": "US", "plan": "premium"})
        result = await engine.evaluate(flag, context, storage)

        assert result.value == {"result": "first"}

    async def test_skip_non_matching_rules(self, engine: EvaluationEngine, storage: MemoryStorageBackend) -> None:
        """Test that non-matching rules are skipped."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="skip-test",
            name="Skip Test",
            flag_type=FlagType.STRING,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            default_value={"result": "default"},
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Non-matching",
                    priority=1,
                    enabled=True,
                    conditions=[{"attribute": "country", "operator": "eq", "value": "UK"}],
                    serve_enabled=True,
                    serve_value={"result": "uk"},
                ),
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Matching",
                    priority=2,
                    enabled=True,
                    conditions=[{"attribute": "country", "operator": "eq", "value": "US"}],
                    serve_enabled=True,
                    serve_value={"result": "us"},
                ),
            ],
            overrides=[],
            variants=[],
        )

        context = EvaluationContext(attributes={"country": "US"})
        result = await engine.evaluate(flag, context, storage)

        assert result.value == {"result": "us"}


class TestDisabledRules:
    """Tests for disabled rules handling."""

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        return EvaluationEngine()

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        return MemoryStorageBackend()

    async def test_disabled_rule_skipped(self, engine: EvaluationEngine, storage: MemoryStorageBackend) -> None:
        """Test that disabled rules are skipped during evaluation."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="disabled-rule-test",
            name="Disabled Rule Test",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Disabled Rule",
                    priority=1,
                    enabled=False,  # Disabled
                    conditions=[],  # Would match all
                    serve_enabled=True,
                ),
            ],
            overrides=[],
            variants=[],
        )

        context = EvaluationContext()
        result = await engine.evaluate(flag, context, storage)

        # Should fall to default since rule is disabled
        assert result.value is False
        assert result.reason == EvaluationReason.STATIC

    async def test_enabled_rule_after_disabled(self, engine: EvaluationEngine, storage: MemoryStorageBackend) -> None:
        """Test that enabled rules after disabled ones are evaluated."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="enabled-after-disabled",
            name="Enabled After Disabled",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Disabled Rule",
                    priority=1,
                    enabled=False,
                    conditions=[],
                    serve_enabled=False,
                ),
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Enabled Rule",
                    priority=2,
                    enabled=True,
                    conditions=[],
                    serve_enabled=True,
                ),
            ],
            overrides=[],
            variants=[],
        )

        context = EvaluationContext()
        result = await engine.evaluate(flag, context, storage)

        assert result.value is True
        assert result.reason == EvaluationReason.TARGETING_MATCH


class TestOverrideExpiration:
    """Comprehensive tests for override expiration logic."""

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        return EvaluationEngine()

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        return MemoryStorageBackend()

    async def test_non_expired_override_applied(self, engine: EvaluationEngine, storage: MemoryStorageBackend) -> None:
        """Test that non-expired overrides are applied."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="non-expired-override",
            name="Non-Expired Override",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        # Override expires in 1 hour (still valid)
        override = FlagOverride(
            id=uuid4(),
            flag_id=flag_id,
            entity_type="user",
            entity_id="user-123",
            enabled=True,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        await storage.create_override(override)

        context = EvaluationContext(user_id="user-123")
        result = await engine.evaluate(flag, context, storage)

        assert result.value is True
        assert result.reason == EvaluationReason.OVERRIDE

    async def test_override_without_expiration(self, engine: EvaluationEngine, storage: MemoryStorageBackend) -> None:
        """Test that overrides without expiration are always applied."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="no-expiration",
            name="No Expiration",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        override = FlagOverride(
            id=uuid4(),
            flag_id=flag_id,
            entity_type="user",
            entity_id="user-123",
            enabled=True,
            expires_at=None,  # No expiration
        )
        await storage.create_override(override)

        context = EvaluationContext(user_id="user-123")
        result = await engine.evaluate(flag, context, storage)

        assert result.value is True
        assert result.reason == EvaluationReason.OVERRIDE

    async def test_organization_override(self, engine: EvaluationEngine, storage: MemoryStorageBackend) -> None:
        """Test organization-level override."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="org-override",
            name="Org Override",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        override = FlagOverride(
            id=uuid4(),
            flag_id=flag_id,
            entity_type="organization",
            entity_id="org-456",
            enabled=True,
        )
        await storage.create_override(override)

        context = EvaluationContext(organization_id="org-456")
        result = await engine.evaluate(flag, context, storage)

        assert result.value is True
        assert result.reason == EvaluationReason.OVERRIDE

    async def test_tenant_override(self, engine: EvaluationEngine, storage: MemoryStorageBackend) -> None:
        """Test tenant-level override."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="tenant-override",
            name="Tenant Override",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        override = FlagOverride(
            id=uuid4(),
            flag_id=flag_id,
            entity_type="tenant",
            entity_id="tenant-789",
            enabled=True,
        )
        await storage.create_override(override)

        context = EvaluationContext(tenant_id="tenant-789")
        result = await engine.evaluate(flag, context, storage)

        assert result.value is True
        assert result.reason == EvaluationReason.OVERRIDE

    async def test_override_with_value(self, engine: EvaluationEngine, storage: MemoryStorageBackend) -> None:
        """Test override with custom value for non-boolean flags."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="value-override",
            name="Value Override",
            flag_type=FlagType.JSON,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            default_value={"theme": "light"},
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        override = FlagOverride(
            id=uuid4(),
            flag_id=flag_id,
            entity_type="user",
            entity_id="user-123",
            enabled=True,
            value={"theme": "dark", "beta": True},
        )
        await storage.create_override(override)

        context = EvaluationContext(user_id="user-123")
        result = await engine.evaluate(flag, context, storage)

        assert result.value == {"theme": "dark", "beta": True}
        assert result.reason == EvaluationReason.OVERRIDE


class TestMurmur3Hash:
    """Tests for Murmur3 hash consistency and distribution."""

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        return EvaluationEngine()

    def test_hash_consistency_same_input(self, engine: EvaluationEngine) -> None:
        """Test that same input always produces same hash."""
        test_input = b"test-string-for-hashing"

        hashes = [engine._murmur3_32(test_input) for _ in range(100)]

        # All should be identical
        assert len(set(hashes)) == 1

    def test_hash_different_inputs_different_hashes(self, engine: EvaluationEngine) -> None:
        """Test that different inputs produce different hashes."""
        inputs = [b"input1", b"input2", b"input3", b"input4", b"input5"]
        hashes = [engine._murmur3_32(data) for data in inputs]

        # All should be unique
        assert len(set(hashes)) == len(inputs)

    def test_hash_with_different_seeds(self, engine: EvaluationEngine) -> None:
        """Test that different seeds produce different hashes."""
        test_input = b"test-input"

        hash1 = engine._murmur3_32(test_input, seed=0)
        hash2 = engine._murmur3_32(test_input, seed=42)
        hash3 = engine._murmur3_32(test_input, seed=12345)

        assert hash1 != hash2
        assert hash2 != hash3
        assert hash1 != hash3

    def test_hash_empty_input(self, engine: EvaluationEngine) -> None:
        """Test hash of empty input."""
        result = engine._murmur3_32(b"")
        # Should return a valid 32-bit integer
        assert isinstance(result, int)
        assert 0 <= result < 2**32

    def test_hash_short_input(self, engine: EvaluationEngine) -> None:
        """Test hash of short inputs (less than 4 bytes)."""
        hash1 = engine._murmur3_32(b"a")
        hash2 = engine._murmur3_32(b"ab")
        hash3 = engine._murmur3_32(b"abc")

        # All should be valid and different
        assert all(isinstance(h, int) for h in [hash1, hash2, hash3])
        assert len({hash1, hash2, hash3}) == 3

    def test_hash_long_input(self, engine: EvaluationEngine) -> None:
        """Test hash of long input."""
        long_input = b"x" * 10000
        result = engine._murmur3_32(long_input)

        assert isinstance(result, int)
        assert 0 <= result < 2**32

    def test_hash_distribution(self, engine: EvaluationEngine) -> None:
        """Test that hash values are well-distributed."""
        # Generate many hashes
        hashes = [engine._murmur3_32(f"key-{i}".encode()) for i in range(10000)]

        # Check distribution by dividing into buckets
        num_buckets = 10
        bucket_size = 2**32 // num_buckets
        buckets = [0] * num_buckets

        for h in hashes:
            bucket = min(h // bucket_size, num_buckets - 1)
            buckets[bucket] += 1

        # Each bucket should have roughly 1000 items (10% of 10000)
        # Allow 30% variance
        for count in buckets:
            assert 700 <= count <= 1300, f"Bucket count {count} outside expected range"


class TestAdditionalOperators:
    """Tests for remaining operators not covered in TestConditionEvaluation."""

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        return EvaluationEngine()

    async def test_less_than_operator(self, engine: EvaluationEngine) -> None:
        """Test LESS_THAN operator."""
        conditions = [{"attribute": "age", "operator": "lt", "value": 18}]

        context = EvaluationContext(attributes={"age": 17})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"age": 18})
        assert await engine._matches_conditions(conditions, context) is False

        context = EvaluationContext(attributes={"age": 19})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_greater_than_or_equal_operator(self, engine: EvaluationEngine) -> None:
        """Test GREATER_THAN_OR_EQUAL operator."""
        conditions = [{"attribute": "age", "operator": "gte", "value": 18}]

        context = EvaluationContext(attributes={"age": 18})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"age": 19})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"age": 17})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_less_than_or_equal_operator(self, engine: EvaluationEngine) -> None:
        """Test LESS_THAN_OR_EQUAL operator."""
        conditions = [{"attribute": "age", "operator": "lte", "value": 18}]

        context = EvaluationContext(attributes={"age": 18})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"age": 17})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"age": 19})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_ends_with_operator(self, engine: EvaluationEngine) -> None:
        """Test ENDS_WITH operator."""
        conditions = [{"attribute": "email", "operator": "ends_with", "value": "@company.com"}]

        context = EvaluationContext(attributes={"email": "user@company.com"})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"email": "user@other.com"})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_not_contains_operator(self, engine: EvaluationEngine) -> None:
        """Test NOT_CONTAINS operator."""
        conditions = [{"attribute": "email", "operator": "not_contains", "value": "spam"}]

        context = EvaluationContext(attributes={"email": "user@company.com"})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"email": "spam@company.com"})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_unknown_operator_skipped(self, engine: EvaluationEngine) -> None:
        """Test that unknown operators are skipped (condition continues to next)."""
        conditions = [
            {"attribute": "plan", "operator": "unknown_op", "value": "premium"},
            {"attribute": "country", "operator": "eq", "value": "US"},
        ]

        # Unknown operator is skipped, second condition should still be evaluated
        context = EvaluationContext(attributes={"plan": "premium", "country": "US"})
        assert await engine._matches_conditions(conditions, context) is True

        context = EvaluationContext(attributes={"plan": "premium", "country": "UK"})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_operators_with_none_actual_value(self, engine: EvaluationEngine) -> None:
        """Test operators when actual value is None."""
        # GT with None
        conditions = [{"attribute": "age", "operator": "gt", "value": 18}]
        context = EvaluationContext(attributes={"age": None})
        assert await engine._matches_conditions(conditions, context) is False

        context = EvaluationContext(attributes={})  # Missing attribute
        assert await engine._matches_conditions(conditions, context) is False

        # CONTAINS with None
        conditions = [{"attribute": "name", "operator": "contains", "value": "test"}]
        context = EvaluationContext(attributes={"name": None})
        assert await engine._matches_conditions(conditions, context) is False

        # NOT_CONTAINS with None actual (returns True)
        conditions = [{"attribute": "name", "operator": "not_contains", "value": "test"}]
        context = EvaluationContext(attributes={"name": None})
        assert await engine._matches_conditions(conditions, context) is True

        # STARTS_WITH with None
        conditions = [{"attribute": "name", "operator": "starts_with", "value": "test"}]
        context = EvaluationContext(attributes={"name": None})
        assert await engine._matches_conditions(conditions, context) is False

        # ENDS_WITH with None
        conditions = [{"attribute": "name", "operator": "ends_with", "value": "test"}]
        context = EvaluationContext(attributes={"name": None})
        assert await engine._matches_conditions(conditions, context) is False

        # MATCHES with None
        conditions = [{"attribute": "name", "operator": "matches", "value": ".*"}]
        context = EvaluationContext(attributes={"name": None})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_in_operator_with_empty_list(self, engine: EvaluationEngine) -> None:
        """Test IN operator with empty list."""
        conditions = [{"attribute": "country", "operator": "in", "value": []}]

        context = EvaluationContext(attributes={"country": "US"})
        assert await engine._matches_conditions(conditions, context) is False

    async def test_not_in_operator_with_empty_list(self, engine: EvaluationEngine) -> None:
        """Test NOT_IN operator with empty list."""
        conditions = [{"attribute": "country", "operator": "not_in", "value": []}]

        context = EvaluationContext(attributes={"country": "US"})
        assert await engine._matches_conditions(conditions, context) is True

    async def test_matches_with_invalid_regex(self, engine: EvaluationEngine) -> None:
        """Test MATCHES operator with invalid regex pattern."""
        conditions = [{"attribute": "name", "operator": "matches", "value": "[invalid(regex"}]

        context = EvaluationContext(attributes={"name": "test"})
        assert await engine._matches_conditions(conditions, context) is False


class TestRolloutPercentageWithRules:
    """Tests for percentage rollout combined with rules."""

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        return EvaluationEngine()

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        return MemoryStorageBackend()

    async def test_rule_with_zero_percent_rollout(
        self, engine: EvaluationEngine, storage: MemoryStorageBackend
    ) -> None:
        """Test that 0% rollout rule never matches."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="zero-rollout",
            name="Zero Rollout",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Zero Rollout Rule",
                    priority=1,
                    enabled=True,
                    conditions=[],  # Matches all
                    serve_enabled=True,
                    rollout_percentage=0,
                ),
            ],
            overrides=[],
            variants=[],
        )

        # Should never match even though conditions match
        for i in range(100):
            context = EvaluationContext(targeting_key=f"user-{i}")
            result = await engine.evaluate(flag, context, storage)
            assert result.value is False
            assert result.reason == EvaluationReason.STATIC

    async def test_rule_with_100_percent_rollout(self, engine: EvaluationEngine, storage: MemoryStorageBackend) -> None:
        """Test that 100% rollout rule always matches."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="full-rollout",
            name="Full Rollout",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Full Rollout Rule",
                    priority=1,
                    enabled=True,
                    conditions=[],
                    serve_enabled=True,
                    rollout_percentage=100,
                ),
            ],
            overrides=[],
            variants=[],
        )

        for i in range(100):
            context = EvaluationContext(targeting_key=f"user-{i}")
            result = await engine.evaluate(flag, context, storage)
            assert result.value is True
            assert result.reason == EvaluationReason.TARGETING_MATCH

    async def test_rule_rollout_with_no_targeting_key(
        self, engine: EvaluationEngine, storage: MemoryStorageBackend
    ) -> None:
        """Test that rollout returns False when no targeting key."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="rollout-no-key",
            name="Rollout No Key",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Rollout Rule",
                    priority=1,
                    enabled=True,
                    conditions=[],
                    serve_enabled=True,
                    rollout_percentage=50,
                ),
            ],
            overrides=[],
            variants=[],
        )

        # No targeting key means rollout returns False
        context = EvaluationContext(targeting_key=None)
        result = await engine.evaluate(flag, context, storage)

        assert result.value is False
        assert result.reason == EvaluationReason.STATIC


class TestFlagTypes:
    """Tests for different flag types."""

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        return EvaluationEngine()

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        return MemoryStorageBackend()

    async def test_boolean_flag_returns_default_enabled(
        self, engine: EvaluationEngine, storage: MemoryStorageBackend
    ) -> None:
        """Test that boolean flags return default_enabled."""
        flag = FeatureFlag(
            id=uuid4(),
            key="bool-flag",
            name="Boolean Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        result = await engine.evaluate(flag, EvaluationContext(), storage)

        assert result.value is True

    async def test_string_flag_returns_default_value(
        self, engine: EvaluationEngine, storage: MemoryStorageBackend
    ) -> None:
        """Test that string flags return default_value."""
        flag = FeatureFlag(
            id=uuid4(),
            key="string-flag",
            name="String Flag",
            flag_type=FlagType.STRING,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            default_value="default_string",
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        result = await engine.evaluate(flag, EvaluationContext(), storage)

        assert result.value == "default_string"

    async def test_number_flag_returns_default_value(
        self, engine: EvaluationEngine, storage: MemoryStorageBackend
    ) -> None:
        """Test that number flags return default_value."""
        flag = FeatureFlag(
            id=uuid4(),
            key="number-flag",
            name="Number Flag",
            flag_type=FlagType.NUMBER,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            default_value=42,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        result = await engine.evaluate(flag, EvaluationContext(), storage)

        assert result.value == 42

    async def test_json_flag_returns_default_value(
        self, engine: EvaluationEngine, storage: MemoryStorageBackend
    ) -> None:
        """Test that JSON flags return default_value."""
        flag = FeatureFlag(
            id=uuid4(),
            key="json-flag",
            name="JSON Flag",
            flag_type=FlagType.JSON,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            default_value={"key": "value", "nested": {"data": True}},
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        result = await engine.evaluate(flag, EvaluationContext(), storage)

        assert result.value == {"key": "value", "nested": {"data": True}}

    async def test_archived_flag_returns_default(self, engine: EvaluationEngine, storage: MemoryStorageBackend) -> None:
        """Test that archived flags return default value."""
        flag = FeatureFlag(
            id=uuid4(),
            key="archived-flag",
            name="Archived Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ARCHIVED,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        result = await engine.evaluate(flag, EvaluationContext(), storage)

        assert result.value is True
        assert result.reason == EvaluationReason.DISABLED


class TestVariantWithBooleanFlag:
    """Tests for variant selection with boolean flags."""

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        return EvaluationEngine()

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        return MemoryStorageBackend()

    async def test_boolean_flag_with_variants_uses_enabled_from_value(
        self, engine: EvaluationEngine, storage: MemoryStorageBackend
    ) -> None:
        """Test that boolean flags extract 'enabled' from variant value."""
        flag = FeatureFlag(
            id=uuid4(),
            key="bool-with-variants",
            name="Boolean With Variants",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[
                FlagVariant(
                    id=uuid4(),
                    key="enabled-variant",
                    name="Enabled Variant",
                    value={"enabled": True},
                    weight=100,
                ),
            ],
        )

        context = EvaluationContext(targeting_key="user-123")
        result = await engine.evaluate(flag, context, storage)

        assert result.value is True
        assert result.reason == EvaluationReason.SPLIT

    async def test_boolean_flag_variant_without_enabled_key(
        self, engine: EvaluationEngine, storage: MemoryStorageBackend
    ) -> None:
        """Test boolean flag variant when 'enabled' key is missing."""
        flag = FeatureFlag(
            id=uuid4(),
            key="bool-variant-no-enabled",
            name="Boolean Variant No Enabled",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[
                FlagVariant(
                    id=uuid4(),
                    key="variant-no-enabled",
                    name="Variant No Enabled",
                    value={"other_key": "value"},  # No 'enabled' key
                    weight=100,
                ),
            ],
        )

        context = EvaluationContext(targeting_key="user-123")
        result = await engine.evaluate(flag, context, storage)

        # Should return False (default for missing enabled key)
        assert result.value is False
        assert result.reason == EvaluationReason.SPLIT


class TestTargetingKeyFallback:
    """Tests for targeting_key override fallback."""

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        return EvaluationEngine()

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        return MemoryStorageBackend()

    async def test_targeting_key_override_used_as_fallback(
        self, engine: EvaluationEngine, storage: MemoryStorageBackend
    ) -> None:
        """Test that targeting_key is used for override lookup as fallback."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="targeting-key-fallback",
            name="Targeting Key Fallback",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        # Create override with targeting_key entity type
        override = FlagOverride(
            id=uuid4(),
            flag_id=flag_id,
            entity_type="targeting_key",
            entity_id="custom-key-123",
            enabled=True,
        )
        await storage.create_override(override)

        # Context with targeting_key that differs from user_id, org_id, tenant_id
        context = EvaluationContext(
            targeting_key="custom-key-123",
            user_id="different-user",
            organization_id="different-org",
            tenant_id="different-tenant",
        )
        result = await engine.evaluate(flag, context, storage)

        assert result.value is True
        assert result.reason == EvaluationReason.OVERRIDE

    async def test_targeting_key_not_used_when_matches_other_ids(
        self, engine: EvaluationEngine, storage: MemoryStorageBackend
    ) -> None:
        """Test that targeting_key is not re-checked when it matches user_id."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="targeting-key-duplicate",
            name="Targeting Key Duplicate",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        # Override with user entity type
        override = FlagOverride(
            id=uuid4(),
            flag_id=flag_id,
            entity_type="user",
            entity_id="user-123",
            enabled=True,
        )
        await storage.create_override(override)

        # targeting_key matches user_id - should be found via user lookup
        context = EvaluationContext(
            targeting_key="user-123",
            user_id="user-123",
        )
        result = await engine.evaluate(flag, context, storage)

        assert result.value is True
        assert result.reason == EvaluationReason.OVERRIDE


class TestRuleResult:
    """Tests for rule result creation."""

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        return EvaluationEngine()

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        return MemoryStorageBackend()

    async def test_rule_serve_value_for_non_boolean_flag(
        self, engine: EvaluationEngine, storage: MemoryStorageBackend
    ) -> None:
        """Test that rules can serve custom values for non-boolean flags."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="rule-serve-value",
            name="Rule Serve Value",
            flag_type=FlagType.JSON,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            default_value={"default": True},
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Custom Value Rule",
                    priority=1,
                    enabled=True,
                    conditions=[],
                    serve_enabled=True,
                    serve_value={"custom": "value", "from": "rule"},
                ),
            ],
            overrides=[],
            variants=[],
        )

        result = await engine.evaluate(flag, EvaluationContext(), storage)

        assert result.value == {"custom": "value", "from": "rule"}
        assert result.variant == "Custom Value Rule"

    async def test_rule_serve_enabled_when_no_serve_value(
        self, engine: EvaluationEngine, storage: MemoryStorageBackend
    ) -> None:
        """Test that rules fall back to serve_enabled when serve_value is None."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="rule-no-value",
            name="Rule No Value",
            flag_type=FlagType.STRING,  # Non-boolean flag
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            default_value="default",
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="No Value Rule",
                    priority=1,
                    enabled=True,
                    conditions=[],
                    serve_enabled=True,
                    serve_value=None,  # No serve_value
                ),
            ],
            overrides=[],
            variants=[],
        )

        result = await engine.evaluate(flag, EvaluationContext(), storage)

        # Falls back to serve_enabled
        assert result.value is True
