"""Tests for feature flag models.

This module tests the model implementations for:
- FeatureFlag
- FlagRule
- FlagVariant
- FlagOverride

Tests cover both SQLAlchemy models (when advanced-alchemy is installed)
and dataclass fallback versions.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from litestar_flags.models.base import HAS_ADVANCED_ALCHEMY
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.models.override import FlagOverride
from litestar_flags.models.rule import FlagRule
from litestar_flags.models.variant import FlagVariant
from litestar_flags.types import FlagStatus, FlagType


class TestFeatureFlagCreation:
    """Tests for FeatureFlag model creation with all field types."""

    def test_create_minimal_feature_flag(self) -> None:
        """Test creating a feature flag with minimal required fields."""
        # Note: SQLAlchemy models don't apply defaults in constructor,
        # they apply them on INSERT. So we test explicit values here.
        flag = FeatureFlag(
            key="minimal-flag",
            name="Minimal Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
        )

        assert flag.key == "minimal-flag"
        assert flag.name == "Minimal Flag"
        assert flag.flag_type == FlagType.BOOLEAN
        assert flag.status == FlagStatus.ACTIVE
        assert flag.default_enabled is False

    def test_create_feature_flag_with_all_fields(self) -> None:
        """Test creating a feature flag with all fields populated."""
        flag_id = uuid4()
        now = datetime.now(UTC)

        flag = FeatureFlag(
            id=flag_id,
            key="full-flag",
            name="Full Feature Flag",
            description="A complete feature flag with all fields",
            flag_type=FlagType.JSON,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            default_value={"setting": "value", "nested": {"key": 123}},
            tags=["test", "feature", "experiment"],
            metadata_={"owner": "team-a", "jira": "FEAT-123"},
            rules=[],
            overrides=[],
            variants=[],
            created_at=now,
            updated_at=now,
        )

        assert flag.id == flag_id
        assert flag.key == "full-flag"
        assert flag.name == "Full Feature Flag"
        assert flag.description == "A complete feature flag with all fields"
        assert flag.flag_type == FlagType.JSON
        assert flag.status == FlagStatus.ACTIVE
        assert flag.default_enabled is True
        assert flag.default_value == {"setting": "value", "nested": {"key": 123}}
        assert flag.tags == ["test", "feature", "experiment"]
        assert flag.metadata_ == {"owner": "team-a", "jira": "FEAT-123"}
        assert flag.rules == []
        assert flag.overrides == []
        assert flag.variants == []

    @pytest.mark.parametrize(
        "flag_type",
        [FlagType.BOOLEAN, FlagType.STRING, FlagType.NUMBER, FlagType.JSON],
    )
    def test_create_flag_with_different_types(self, flag_type: FlagType) -> None:
        """Test creating flags with each flag type."""
        flag = FeatureFlag(
            key=f"{flag_type.value}-flag",
            name=f"{flag_type.value.title()} Flag",
            flag_type=flag_type,
        )

        assert flag.flag_type == flag_type

    @pytest.mark.parametrize(
        "status",
        [FlagStatus.ACTIVE, FlagStatus.INACTIVE, FlagStatus.ARCHIVED],
    )
    def test_create_flag_with_different_statuses(self, status: FlagStatus) -> None:
        """Test creating flags with each status."""
        flag = FeatureFlag(
            key=f"{status.value}-flag",
            name=f"{status.value.title()} Flag",
            status=status,
        )

        assert flag.status == status

    def test_create_boolean_flag_with_default_enabled(self) -> None:
        """Test creating a boolean flag with default_enabled=True."""
        flag = FeatureFlag(
            key="enabled-flag",
            name="Enabled Flag",
            flag_type=FlagType.BOOLEAN,
            default_enabled=True,
        )

        assert flag.default_enabled is True
        assert flag.flag_type == FlagType.BOOLEAN

    def test_create_string_flag_with_default_value(self) -> None:
        """Test creating a string flag with a default value."""
        flag = FeatureFlag(
            key="string-flag",
            name="String Flag",
            flag_type=FlagType.STRING,
            default_value={"value": "default-string"},
        )

        assert flag.flag_type == FlagType.STRING
        assert flag.default_value == {"value": "default-string"}

    def test_create_number_flag_with_default_value(self) -> None:
        """Test creating a number flag with a default value."""
        flag = FeatureFlag(
            key="number-flag",
            name="Number Flag",
            flag_type=FlagType.NUMBER,
            default_value={"value": 42.5},
        )

        assert flag.flag_type == FlagType.NUMBER
        assert flag.default_value == {"value": 42.5}

    def test_create_json_flag_with_complex_default_value(self) -> None:
        """Test creating a JSON flag with complex nested default value."""
        complex_value: dict[str, Any] = {
            "theme": "dark",
            "features": ["a", "b", "c"],
            "limits": {"max_users": 100, "max_requests": 1000},
            "nested": {"level1": {"level2": {"level3": True}}},
        }

        flag = FeatureFlag(
            key="json-flag",
            name="JSON Flag",
            flag_type=FlagType.JSON,
            default_value=complex_value,
        )

        assert flag.flag_type == FlagType.JSON
        assert flag.default_value == complex_value

    def test_feature_flag_with_empty_tags(self) -> None:
        """Test creating a flag with empty tags list."""
        flag = FeatureFlag(
            key="no-tags",
            name="No Tags Flag",
            tags=[],
        )

        assert flag.tags == []

    def test_feature_flag_with_multiple_tags(self) -> None:
        """Test creating a flag with multiple tags."""
        tags = ["production", "experiment", "team-alpha", "critical"]

        flag = FeatureFlag(
            key="tagged-flag",
            name="Tagged Flag",
            tags=tags,
        )

        assert flag.tags == tags
        assert len(flag.tags) == 4

    def test_feature_flag_with_rich_metadata(self) -> None:
        """Test creating a flag with rich metadata."""
        metadata: dict[str, Any] = {
            "owner": "platform-team",
            "created_by": "user@company.com",
            "jira_ticket": "PLAT-456",
            "rollout_plan": {
                "phase1": "internal",
                "phase2": "beta",
                "phase3": "ga",
            },
            "dependencies": ["auth-service", "user-service"],
        }

        flag = FeatureFlag(
            key="rich-metadata",
            name="Rich Metadata Flag",
            metadata_=metadata,
        )

        assert flag.metadata_ == metadata


class TestFlagRuleConditions:
    """Tests for FlagRule conditions JSON validation and structure."""

    def test_create_rule_with_single_condition(self) -> None:
        """Test creating a rule with a single condition."""
        rule = FlagRule(
            name="Single Condition Rule",
            conditions=[{"attribute": "plan", "operator": "eq", "value": "premium"}],
        )

        assert rule.name == "Single Condition Rule"
        assert len(rule.conditions) == 1
        assert rule.conditions[0]["attribute"] == "plan"
        assert rule.conditions[0]["operator"] == "eq"
        assert rule.conditions[0]["value"] == "premium"

    def test_create_rule_with_multiple_conditions(self) -> None:
        """Test creating a rule with multiple conditions (AND logic)."""
        conditions = [
            {"attribute": "plan", "operator": "eq", "value": "premium"},
            {"attribute": "country", "operator": "in", "value": ["US", "CA", "UK"]},
            {"attribute": "age", "operator": "gte", "value": 18},
        ]

        rule = FlagRule(
            name="Multi Condition Rule",
            conditions=conditions,
        )

        assert len(rule.conditions) == 3

    def test_create_rule_with_empty_conditions(self) -> None:
        """Test creating a rule with empty conditions (matches all)."""
        rule = FlagRule(
            name="Match All Rule",
            conditions=[],
        )

        assert rule.conditions == []

    @pytest.mark.parametrize(
        "operator",
        ["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "contains", "starts_with", "ends_with", "matches"],
    )
    def test_create_rule_with_each_operator(self, operator: str) -> None:
        """Test creating rules with each supported operator."""
        value: Any
        if operator in ["in", "not_in"]:
            value = ["a", "b", "c"]
        elif operator in ["gt", "gte", "lt", "lte"]:
            value = 100
        else:
            value = "test-value"

        rule = FlagRule(
            name=f"{operator} Rule",
            conditions=[{"attribute": "test_attr", "operator": operator, "value": value}],
        )

        assert rule.conditions[0]["operator"] == operator

    def test_create_rule_with_complex_in_condition(self) -> None:
        """Test creating a rule with IN operator and list value."""
        countries = ["US", "CA", "UK", "DE", "FR"]
        rule = FlagRule(
            name="Country Rule",
            conditions=[{"attribute": "country", "operator": "in", "value": countries}],
        )

        assert rule.conditions[0]["value"] == countries

    def test_create_rule_with_regex_condition(self) -> None:
        """Test creating a rule with regex matches operator."""
        rule = FlagRule(
            name="Email Domain Rule",
            conditions=[{"attribute": "email", "operator": "matches", "value": r".*@company\.com$"}],
        )

        assert rule.conditions[0]["operator"] == "matches"
        assert r".*@company\.com$" in rule.conditions[0]["value"]

    def test_rule_with_priority(self) -> None:
        """Test rule priority assignment."""
        rule = FlagRule(
            name="High Priority Rule",
            priority=0,
            conditions=[],
        )

        assert rule.priority == 0

        rule_low = FlagRule(
            name="Low Priority Rule",
            priority=100,
            conditions=[],
        )

        assert rule_low.priority == 100

    def test_rule_with_serve_enabled(self) -> None:
        """Test rule with serve_enabled for boolean outcomes."""
        rule_true = FlagRule(
            name="Enable Rule",
            conditions=[],
            serve_enabled=True,
        )

        assert rule_true.serve_enabled is True

        rule_false = FlagRule(
            name="Disable Rule",
            conditions=[],
            serve_enabled=False,
        )

        assert rule_false.serve_enabled is False

    def test_rule_with_serve_value(self) -> None:
        """Test rule with serve_value for non-boolean outcomes."""
        rule = FlagRule(
            name="Value Rule",
            conditions=[],
            serve_value={"theme": "dark", "limit": 500},
        )

        assert rule.serve_value == {"theme": "dark", "limit": 500}

    def test_rule_with_rollout_percentage(self) -> None:
        """Test rule with percentage rollout."""
        rule = FlagRule(
            name="50% Rollout",
            conditions=[],
            rollout_percentage=50,
        )

        assert rule.rollout_percentage == 50

    def test_rule_enabled_disabled_states(self) -> None:
        """Test rule enabled/disabled states."""
        enabled_rule = FlagRule(name="Enabled", enabled=True, conditions=[])
        disabled_rule = FlagRule(name="Disabled", enabled=False, conditions=[])

        assert enabled_rule.enabled is True
        assert disabled_rule.enabled is False


class TestFlagVariantWeights:
    """Tests for FlagVariant weight constraints and distribution."""

    def test_create_variant_with_weight(self) -> None:
        """Test creating a variant with a weight."""
        variant = FlagVariant(
            key="control",
            name="Control",
            weight=50,
            value={"group": "control"},
        )

        assert variant.key == "control"
        assert variant.name == "Control"
        assert variant.weight == 50
        assert variant.value == {"group": "control"}

    def test_create_variants_summing_to_100(self) -> None:
        """Test creating variants that sum to 100%."""
        variant_a = FlagVariant(key="a", name="Variant A", weight=30, value={})
        variant_b = FlagVariant(key="b", name="Variant B", weight=45, value={})
        variant_c = FlagVariant(key="c", name="Variant C", weight=25, value={})

        total_weight = variant_a.weight + variant_b.weight + variant_c.weight
        assert total_weight == 100

    def test_create_variant_with_zero_weight(self) -> None:
        """Test creating a variant with zero weight (disabled)."""
        variant = FlagVariant(
            key="disabled",
            name="Disabled Variant",
            weight=0,
            value={"disabled": True},
        )

        assert variant.weight == 0

    def test_create_variant_with_full_weight(self) -> None:
        """Test creating a single variant with 100% weight."""
        variant = FlagVariant(
            key="only",
            name="Only Variant",
            weight=100,
            value={"only": True},
        )

        assert variant.weight == 100

    def test_create_ab_test_variants(self) -> None:
        """Test creating standard A/B test variants (50/50 split)."""
        control = FlagVariant(
            key="control",
            name="Control",
            weight=50,
            value={"experiment": False},
        )
        treatment = FlagVariant(
            key="treatment",
            name="Treatment",
            weight=50,
            value={"experiment": True},
        )

        assert control.weight + treatment.weight == 100
        assert control.value != treatment.value

    def test_create_multivariate_test_variants(self) -> None:
        """Test creating multivariate test with multiple variants."""
        variants = [
            FlagVariant(key="v1", name="Variant 1", weight=25, value={"v": 1}),
            FlagVariant(key="v2", name="Variant 2", weight=25, value={"v": 2}),
            FlagVariant(key="v3", name="Variant 3", weight=25, value={"v": 3}),
            FlagVariant(key="v4", name="Variant 4", weight=25, value={"v": 4}),
        ]

        total = sum(v.weight for v in variants)
        assert total == 100
        assert len(variants) == 4

    def test_variant_with_complex_value(self) -> None:
        """Test variant with complex nested value."""
        complex_value: dict[str, Any] = {
            "ui": {
                "theme": "modern",
                "layout": "grid",
                "animations": True,
            },
            "features": ["feature_a", "feature_b"],
            "limits": {"max_items": 100},
        }

        variant = FlagVariant(
            key="new-ui",
            name="New UI",
            weight=50,
            value=complex_value,
        )

        assert variant.value == complex_value

    def test_variant_with_description(self) -> None:
        """Test variant with description field."""
        variant = FlagVariant(
            key="test",
            name="Test Variant",
            description="This variant is used for testing purposes",
            weight=100,
            value={},
        )

        assert variant.description == "This variant is used for testing purposes"


class TestFlagOverrideExpiration:
    """Tests for FlagOverride expiration handling."""

    def test_override_without_expiration_is_not_expired(self) -> None:
        """Test that override without expires_at is never expired."""
        override = FlagOverride(
            entity_type="user",
            entity_id="user-123",
            enabled=True,
            expires_at=None,
        )

        assert override.is_expired() is False

    def test_override_with_future_expiration_is_not_expired(self) -> None:
        """Test that override with future expires_at is not expired."""
        future_time = datetime.now(UTC) + timedelta(hours=24)
        override = FlagOverride(
            entity_type="user",
            entity_id="user-123",
            enabled=True,
            expires_at=future_time,
        )

        assert override.is_expired() is False

    def test_override_with_past_expiration_is_expired(self) -> None:
        """Test that override with past expires_at is expired."""
        past_time = datetime.now(UTC) - timedelta(hours=1)
        override = FlagOverride(
            entity_type="user",
            entity_id="user-123",
            enabled=True,
            expires_at=past_time,
        )

        assert override.is_expired() is True

    def test_override_is_expired_with_custom_now(self) -> None:
        """Test is_expired with custom 'now' parameter."""
        expires_at = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        override = FlagOverride(
            entity_type="user",
            entity_id="user-123",
            enabled=True,
            expires_at=expires_at,
        )

        # Before expiration
        before = datetime(2024, 6, 15, 11, 0, 0, tzinfo=UTC)
        assert override.is_expired(now=before) is False

        # After expiration
        after = datetime(2024, 6, 15, 13, 0, 0, tzinfo=UTC)
        assert override.is_expired(now=after) is True

    def test_override_expiration_boundary(self) -> None:
        """Test expiration at exact boundary."""
        boundary_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        override = FlagOverride(
            entity_type="user",
            entity_id="user-123",
            enabled=True,
            expires_at=boundary_time,
        )

        # Exactly at boundary - should NOT be expired (not > expires_at)
        at_boundary = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        assert override.is_expired(now=at_boundary) is False

        # One microsecond after - should be expired
        just_after = datetime(2024, 6, 15, 12, 0, 0, 1, tzinfo=UTC)
        assert override.is_expired(now=just_after) is True

    def test_create_override_for_user(self) -> None:
        """Test creating a user-specific override."""
        override = FlagOverride(
            entity_type="user",
            entity_id="user-abc-123",
            enabled=True,
            value={"custom": "value"},
        )

        assert override.entity_type == "user"
        assert override.entity_id == "user-abc-123"
        assert override.enabled is True
        assert override.value == {"custom": "value"}

    def test_create_override_for_organization(self) -> None:
        """Test creating an organization-specific override."""
        override = FlagOverride(
            entity_type="organization",
            entity_id="org-456",
            enabled=False,
        )

        assert override.entity_type == "organization"
        assert override.entity_id == "org-456"
        assert override.enabled is False

    def test_create_override_for_tenant(self) -> None:
        """Test creating a tenant-specific override."""
        override = FlagOverride(
            entity_type="tenant",
            entity_id="tenant-xyz",
            enabled=True,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )

        assert override.entity_type == "tenant"
        assert override.entity_id == "tenant-xyz"
        assert override.expires_at is not None


class TestModelSerialization:
    """Tests for model serialization/deserialization."""

    def test_feature_flag_to_dict_dataclass(self) -> None:
        """Test FeatureFlag serialization (dataclass version)."""
        if HAS_ADVANCED_ALCHEMY:
            pytest.skip("Dataclass serialization only applicable without advanced-alchemy")

        flag = FeatureFlag(
            key="serialize-test",
            name="Serialize Test",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=["test"],
            metadata_={"key": "value"},
            rules=[],
            overrides=[],
            variants=[],
        )

        if is_dataclass(flag) and not isinstance(flag, type):
            flag_dict = asdict(flag)
            assert flag_dict["key"] == "serialize-test"
            assert flag_dict["name"] == "Serialize Test"
            assert flag_dict["default_enabled"] is True

    def test_flag_rule_to_dict_dataclass(self) -> None:
        """Test FlagRule serialization (dataclass version)."""
        if HAS_ADVANCED_ALCHEMY:
            pytest.skip("Dataclass serialization only applicable without advanced-alchemy")

        rule = FlagRule(
            name="Rule Test",
            conditions=[{"attribute": "test", "operator": "eq", "value": "value"}],
            serve_enabled=True,
        )

        if is_dataclass(rule) and not isinstance(rule, type):
            rule_dict = asdict(rule)
            assert rule_dict["name"] == "Rule Test"
            assert len(rule_dict["conditions"]) == 1

    def test_flag_variant_to_dict_dataclass(self) -> None:
        """Test FlagVariant serialization (dataclass version)."""
        if HAS_ADVANCED_ALCHEMY:
            pytest.skip("Dataclass serialization only applicable without advanced-alchemy")

        variant = FlagVariant(
            key="test-variant",
            name="Test Variant",
            weight=50,
            value={"test": True},
        )

        if is_dataclass(variant) and not isinstance(variant, type):
            variant_dict = asdict(variant)
            assert variant_dict["key"] == "test-variant"
            assert variant_dict["weight"] == 50

    def test_flag_override_to_dict_dataclass(self) -> None:
        """Test FlagOverride serialization (dataclass version)."""
        if HAS_ADVANCED_ALCHEMY:
            pytest.skip("Dataclass serialization only applicable without advanced-alchemy")

        override = FlagOverride(
            entity_type="user",
            entity_id="user-123",
            enabled=True,
        )

        if is_dataclass(override) and not isinstance(override, type):
            override_dict = asdict(override)
            assert override_dict["entity_type"] == "user"
            assert override_dict["entity_id"] == "user-123"


class TestModelRelationships:
    """Tests for model relationships (flag -> rules, variants, overrides)."""

    def test_flag_with_rules_relationship(self) -> None:
        """Test flag with associated rules."""
        flag_id = uuid4()
        rules = [
            FlagRule(
                id=uuid4(),
                flag_id=flag_id,
                name="Rule 1",
                priority=0,
                conditions=[{"attribute": "plan", "operator": "eq", "value": "premium"}],
            ),
            FlagRule(
                id=uuid4(),
                flag_id=flag_id,
                name="Rule 2",
                priority=1,
                conditions=[{"attribute": "country", "operator": "in", "value": ["US"]}],
            ),
        ]

        flag = FeatureFlag(
            id=flag_id,
            key="rules-flag",
            name="Flag with Rules",
            rules=rules,
            overrides=[],
            variants=[],
        )

        assert len(flag.rules) == 2
        assert flag.rules[0].name == "Rule 1"
        assert flag.rules[1].name == "Rule 2"
        assert all(r.flag_id == flag_id for r in flag.rules)

    def test_flag_with_variants_relationship(self) -> None:
        """Test flag with associated variants."""
        flag_id = uuid4()
        variants = [
            FlagVariant(
                id=uuid4(),
                flag_id=flag_id,
                key="control",
                name="Control",
                weight=50,
                value={"group": "control"},
            ),
            FlagVariant(
                id=uuid4(),
                flag_id=flag_id,
                key="treatment",
                name="Treatment",
                weight=50,
                value={"group": "treatment"},
            ),
        ]

        flag = FeatureFlag(
            id=flag_id,
            key="variants-flag",
            name="Flag with Variants",
            flag_type=FlagType.JSON,
            rules=[],
            overrides=[],
            variants=variants,
        )

        assert len(flag.variants) == 2
        assert flag.variants[0].key == "control"
        assert flag.variants[1].key == "treatment"
        assert all(v.flag_id == flag_id for v in flag.variants)

    def test_flag_with_overrides_relationship(self) -> None:
        """Test flag with associated overrides."""
        flag_id = uuid4()
        overrides = [
            FlagOverride(
                id=uuid4(),
                flag_id=flag_id,
                entity_type="user",
                entity_id="user-123",
                enabled=True,
            ),
            FlagOverride(
                id=uuid4(),
                flag_id=flag_id,
                entity_type="organization",
                entity_id="org-456",
                enabled=False,
            ),
        ]

        flag = FeatureFlag(
            id=flag_id,
            key="overrides-flag",
            name="Flag with Overrides",
            rules=[],
            overrides=overrides,
            variants=[],
        )

        assert len(flag.overrides) == 2
        assert flag.overrides[0].entity_type == "user"
        assert flag.overrides[1].entity_type == "organization"
        assert all(o.flag_id == flag_id for o in flag.overrides)

    def test_flag_with_all_relationships(self) -> None:
        """Test flag with all relationship types populated."""
        flag_id = uuid4()

        rules = [
            FlagRule(
                id=uuid4(),
                flag_id=flag_id,
                name="Premium Rule",
                priority=0,
                conditions=[{"attribute": "plan", "operator": "eq", "value": "premium"}],
            ),
        ]

        variants = [
            FlagVariant(
                id=uuid4(),
                flag_id=flag_id,
                key="control",
                name="Control",
                weight=50,
                value={},
            ),
            FlagVariant(
                id=uuid4(),
                flag_id=flag_id,
                key="treatment",
                name="Treatment",
                weight=50,
                value={"new_feature": True},
            ),
        ]

        overrides = [
            FlagOverride(
                id=uuid4(),
                flag_id=flag_id,
                entity_type="user",
                entity_id="beta-user",
                enabled=True,
            ),
        ]

        flag = FeatureFlag(
            id=flag_id,
            key="full-flag",
            name="Full Flag",
            flag_type=FlagType.JSON,
            rules=rules,
            variants=variants,
            overrides=overrides,
        )

        assert len(flag.rules) == 1
        assert len(flag.variants) == 2
        assert len(flag.overrides) == 1

    def test_rule_flag_reference(self) -> None:
        """Test that rule can reference its parent flag."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="parent-flag",
            name="Parent Flag",
            rules=[],
            overrides=[],
            variants=[],
        )

        rule = FlagRule(
            id=uuid4(),
            flag_id=flag_id,
            name="Child Rule",
            conditions=[],
            flag=flag,
        )

        assert rule.flag_id == flag_id
        assert rule.flag == flag
        assert rule.flag.key == "parent-flag"

    def test_variant_flag_reference(self) -> None:
        """Test that variant can reference its parent flag."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="parent-flag",
            name="Parent Flag",
            rules=[],
            overrides=[],
            variants=[],
        )

        variant = FlagVariant(
            id=uuid4(),
            flag_id=flag_id,
            key="child-variant",
            name="Child Variant",
            weight=100,
            value={},
            flag=flag,
        )

        assert variant.flag_id == flag_id
        assert variant.flag == flag

    def test_override_flag_reference(self) -> None:
        """Test that override can reference its parent flag."""
        flag_id = uuid4()
        flag = FeatureFlag(
            id=flag_id,
            key="parent-flag",
            name="Parent Flag",
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
            flag=flag,
        )

        assert override.flag_id == flag_id
        assert override.flag == flag


class TestModelRepr:
    """Tests for model __repr__ methods."""

    def test_feature_flag_repr(self) -> None:
        """Test FeatureFlag string representation."""
        flag = FeatureFlag(
            key="repr-test",
            name="Repr Test",
            status=FlagStatus.ACTIVE,
        )

        repr_str = repr(flag)
        assert "FeatureFlag" in repr_str
        assert "repr-test" in repr_str
        assert "active" in repr_str

    def test_feature_flag_repr_inactive(self) -> None:
        """Test FeatureFlag repr with inactive status."""
        flag = FeatureFlag(
            key="inactive-flag",
            name="Inactive Flag",
            status=FlagStatus.INACTIVE,
        )

        repr_str = repr(flag)
        assert "inactive" in repr_str

    def test_feature_flag_repr_archived(self) -> None:
        """Test FeatureFlag repr with archived status."""
        flag = FeatureFlag(
            key="archived-flag",
            name="Archived Flag",
            status=FlagStatus.ARCHIVED,
        )

        repr_str = repr(flag)
        assert "archived" in repr_str

    def test_flag_rule_repr(self) -> None:
        """Test FlagRule string representation."""
        rule = FlagRule(
            name="Test Rule",
            priority=5,
            conditions=[],
        )

        repr_str = repr(rule)
        assert "FlagRule" in repr_str
        assert "Test Rule" in repr_str
        assert "5" in repr_str

    def test_flag_rule_repr_high_priority(self) -> None:
        """Test FlagRule repr with priority=0 (highest)."""
        rule = FlagRule(
            name="High Priority",
            priority=0,
            conditions=[],
        )

        repr_str = repr(rule)
        assert "priority=0" in repr_str

    def test_flag_variant_repr(self) -> None:
        """Test FlagVariant string representation."""
        variant = FlagVariant(
            key="variant-a",
            name="Variant A",
            weight=75,
            value={},
        )

        repr_str = repr(variant)
        assert "FlagVariant" in repr_str
        assert "variant-a" in repr_str
        assert "75" in repr_str

    def test_flag_variant_repr_zero_weight(self) -> None:
        """Test FlagVariant repr with zero weight."""
        variant = FlagVariant(
            key="disabled",
            name="Disabled",
            weight=0,
            value={},
        )

        repr_str = repr(variant)
        assert "weight=0" in repr_str

    def test_flag_override_repr(self) -> None:
        """Test FlagOverride string representation."""
        override = FlagOverride(
            entity_type="user",
            entity_id="user-789",
            enabled=True,
        )

        repr_str = repr(override)
        assert "FlagOverride" in repr_str
        assert "user" in repr_str
        assert "user-789" in repr_str

    def test_flag_override_repr_organization(self) -> None:
        """Test FlagOverride repr for organization entity."""
        override = FlagOverride(
            entity_type="organization",
            entity_id="org-acme",
            enabled=False,
        )

        repr_str = repr(override)
        assert "organization" in repr_str
        assert "org-acme" in repr_str


class TestDataclassFallback:
    """Tests for dataclass fallback versions (when advanced-alchemy not installed)."""

    def test_feature_flag_has_id_field(self) -> None:
        """Test that FeatureFlag has id field."""
        flag = FeatureFlag(
            key="id-test",
            name="ID Test",
        )

        # Both SQLAlchemy and dataclass versions should have id
        assert hasattr(flag, "id")
        if not HAS_ADVANCED_ALCHEMY:
            # Dataclass version generates UUID by default
            assert isinstance(flag.id, UUID)

    def test_feature_flag_has_timestamp_fields(self) -> None:
        """Test that FeatureFlag has timestamp fields."""
        now = datetime.now(UTC)
        flag = FeatureFlag(
            key="timestamp-test",
            name="Timestamp Test",
            created_at=now,
            updated_at=now,
        )

        assert hasattr(flag, "created_at")
        assert hasattr(flag, "updated_at")

    def test_flag_rule_has_id_field(self) -> None:
        """Test that FlagRule has id field."""
        rule = FlagRule(
            name="ID Test Rule",
            conditions=[],
        )

        assert hasattr(rule, "id")

    def test_flag_variant_has_id_field(self) -> None:
        """Test that FlagVariant has id field."""
        variant = FlagVariant(
            key="id-test",
            name="ID Test Variant",
            value={},
        )

        assert hasattr(variant, "id")

    def test_flag_override_has_id_field(self) -> None:
        """Test that FlagOverride has id field."""
        override = FlagOverride(
            entity_type="user",
            entity_id="test-user",
            enabled=True,
        )

        assert hasattr(override, "id")

    def test_models_are_dataclasses_when_no_alchemy(self) -> None:
        """Test that models are dataclasses when advanced-alchemy not installed."""
        if HAS_ADVANCED_ALCHEMY:
            pytest.skip("This test is for dataclass fallback only")

        flag = FeatureFlag(key="test", name="Test")
        rule = FlagRule(name="Test", conditions=[])
        variant = FlagVariant(key="test", name="Test", value={})
        override = FlagOverride(entity_type="user", entity_id="123", enabled=True)

        assert is_dataclass(flag)
        assert is_dataclass(rule)
        assert is_dataclass(variant)
        assert is_dataclass(override)

    def test_dataclass_default_values(self) -> None:
        """Test that dataclass versions have correct default values."""
        if HAS_ADVANCED_ALCHEMY:
            pytest.skip("This test is for dataclass fallback only")

        flag = FeatureFlag(key="defaults", name="Defaults Test")

        assert flag.flag_type == FlagType.BOOLEAN
        assert flag.status == FlagStatus.ACTIVE
        assert flag.default_enabled is False
        assert flag.default_value is None
        assert flag.tags == [] or isinstance(flag.tags, list)
        assert flag.metadata_ == {} or isinstance(flag.metadata_, dict)


class TestAdvancedAlchemyModels:
    """Tests specific to SQLAlchemy/advanced-alchemy model features."""

    @pytest.mark.skipif(not HAS_ADVANCED_ALCHEMY, reason="Requires advanced-alchemy")
    def test_feature_flag_tablename(self) -> None:
        """Test FeatureFlag has correct table name."""
        assert FeatureFlag.__tablename__ == "feature_flags"

    @pytest.mark.skipif(not HAS_ADVANCED_ALCHEMY, reason="Requires advanced-alchemy")
    def test_flag_rule_tablename(self) -> None:
        """Test FlagRule has correct table name."""
        assert FlagRule.__tablename__ == "flag_rules"

    @pytest.mark.skipif(not HAS_ADVANCED_ALCHEMY, reason="Requires advanced-alchemy")
    def test_flag_variant_tablename(self) -> None:
        """Test FlagVariant has correct table name."""
        assert FlagVariant.__tablename__ == "flag_variants"

    @pytest.mark.skipif(not HAS_ADVANCED_ALCHEMY, reason="Requires advanced-alchemy")
    def test_flag_override_tablename(self) -> None:
        """Test FlagOverride has correct table name."""
        assert FlagOverride.__tablename__ == "flag_overrides"

    @pytest.mark.skipif(not HAS_ADVANCED_ALCHEMY, reason="Requires advanced-alchemy")
    def test_feature_flag_has_table_args(self) -> None:
        """Test FeatureFlag has table args for indexes."""
        assert hasattr(FeatureFlag, "__table_args__")

    @pytest.mark.skipif(not HAS_ADVANCED_ALCHEMY, reason="Requires advanced-alchemy")
    def test_flag_rule_has_table_args(self) -> None:
        """Test FlagRule has table args for indexes."""
        assert hasattr(FlagRule, "__table_args__")

    @pytest.mark.skipif(not HAS_ADVANCED_ALCHEMY, reason="Requires advanced-alchemy")
    def test_flag_variant_has_table_args(self) -> None:
        """Test FlagVariant has table args for indexes."""
        assert hasattr(FlagVariant, "__table_args__")

    @pytest.mark.skipif(not HAS_ADVANCED_ALCHEMY, reason="Requires advanced-alchemy")
    def test_flag_override_has_table_args(self) -> None:
        """Test FlagOverride has table args for indexes."""
        assert hasattr(FlagOverride, "__table_args__")


class TestModelEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_flag_with_empty_key(self) -> None:
        """Test flag creation with empty key."""
        flag = FeatureFlag(
            key="",
            name="Empty Key Flag",
        )
        assert flag.key == ""

    def test_flag_with_special_characters_in_key(self) -> None:
        """Test flag with special characters in key."""
        flag = FeatureFlag(
            key="my-flag_v2.0:beta",
            name="Special Key Flag",
        )
        assert flag.key == "my-flag_v2.0:beta"

    def test_flag_with_unicode_characters(self) -> None:
        """Test flag with unicode characters in name/description."""
        flag = FeatureFlag(
            key="unicode-flag",
            name="Unicode Flag",
            description="Multi-language support: Hola, Bonjour, Hallo",
            tags=["i18n", "l10n"],
        )
        assert "Hola" in flag.description
        assert "Bonjour" in flag.description

    def test_rule_with_none_rollout_percentage(self) -> None:
        """Test rule with None rollout percentage (100% by default)."""
        rule = FlagRule(
            name="No Rollout",
            conditions=[],
            rollout_percentage=None,
        )
        assert rule.rollout_percentage is None

    def test_variant_with_empty_value(self) -> None:
        """Test variant with empty value dict."""
        variant = FlagVariant(
            key="empty-value",
            name="Empty Value",
            value={},
            weight=100,
        )
        assert variant.value == {}

    def test_override_with_none_value(self) -> None:
        """Test override with None value."""
        override = FlagOverride(
            entity_type="user",
            entity_id="user-123",
            enabled=True,
            value=None,
        )
        assert override.value is None

    def test_large_conditions_list(self) -> None:
        """Test rule with many conditions."""
        conditions = [{"attribute": f"attr_{i}", "operator": "eq", "value": f"val_{i}"} for i in range(50)]

        rule = FlagRule(
            name="Many Conditions",
            conditions=conditions,
        )

        assert len(rule.conditions) == 50

    def test_deeply_nested_default_value(self) -> None:
        """Test flag with deeply nested default value."""
        nested_value: dict[str, Any] = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "level5": {"deep_value": True},
                        },
                    },
                },
            },
        }

        flag = FeatureFlag(
            key="nested-flag",
            name="Nested Flag",
            flag_type=FlagType.JSON,
            default_value=nested_value,
        )

        assert flag.default_value["level1"]["level2"]["level3"]["level4"]["level5"]["deep_value"] is True
