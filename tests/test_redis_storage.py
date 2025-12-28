"""Tests for Redis storage backend."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from litestar_flags.models.flag import FeatureFlag
from litestar_flags.models.override import FlagOverride
from litestar_flags.models.rule import FlagRule
from litestar_flags.models.variant import FlagVariant
from litestar_flags.types import FlagStatus, FlagType


class TestRedisStorageBackend:
    """Tests for RedisStorageBackend."""

    @pytest.fixture
    def sample_flag(self) -> FeatureFlag:
        """Create a sample flag."""
        return FeatureFlag(
            id=uuid4(),
            key="test-flag",
            name="Test Flag",
            description="A test flag for Redis storage",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=["test", "redis"],
            metadata_={"env": "test"},
            rules=[],
            overrides=[],
            variants=[],
        )

    @pytest.fixture
    def sample_flag_with_rules(self) -> FeatureFlag:
        """Create a sample flag with targeting rules."""
        flag_id = uuid4()
        return FeatureFlag(
            id=flag_id,
            key="rules-flag",
            name="Flag with Rules",
            description="A flag with targeting rules",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=["rules"],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Premium Users",
                    description="Target premium users",
                    priority=0,
                    enabled=True,
                    conditions=[{"attribute": "plan", "operator": "eq", "value": "premium"}],
                    serve_enabled=True,
                    serve_value=None,
                    rollout_percentage=None,
                ),
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Beta Rollout",
                    description="50% rollout for beta",
                    priority=1,
                    enabled=True,
                    conditions=[],
                    serve_enabled=True,
                    serve_value=None,
                    rollout_percentage=50,
                ),
            ],
            overrides=[],
            variants=[],
        )

    @pytest.fixture
    def sample_flag_with_variants(self) -> FeatureFlag:
        """Create a sample flag with A/B test variants."""
        flag_id = uuid4()
        return FeatureFlag(
            id=flag_id,
            key="ab-test-flag",
            name="A/B Test Flag",
            description="Flag for A/B testing",
            flag_type=FlagType.STRING,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            default_value={"variant": "control"},
            tags=["experiment", "ab-test"],
            metadata_={"experiment_id": "exp-123"},
            rules=[],
            overrides=[],
            variants=[
                FlagVariant(
                    id=uuid4(),
                    flag_id=flag_id,
                    key="control",
                    name="Control Group",
                    description="Original experience",
                    value={"variant": "control", "button_color": "blue"},
                    weight=50,
                ),
                FlagVariant(
                    id=uuid4(),
                    flag_id=flag_id,
                    key="treatment",
                    name="Treatment Group",
                    description="New experience",
                    value={"variant": "treatment", "button_color": "green"},
                    weight=50,
                ),
            ],
        )

    # -------------------------------------------------------------------------
    # Basic CRUD Tests
    # -------------------------------------------------------------------------

    async def test_create_and_get_flag(self, redis_storage, sample_flag: FeatureFlag) -> None:
        """Test creating and retrieving a flag from Redis."""
        created = await redis_storage.create_flag(sample_flag)

        assert created.key == "test-flag"
        assert created.name == "Test Flag"
        assert created.created_at is not None
        assert created.updated_at is not None

        retrieved = await redis_storage.get_flag("test-flag")
        assert retrieved is not None
        assert retrieved.key == "test-flag"
        assert retrieved.name == "Test Flag"
        assert retrieved.description == "A test flag for Redis storage"
        assert retrieved.default_enabled is True
        assert retrieved.flag_type == FlagType.BOOLEAN
        assert retrieved.status == FlagStatus.ACTIVE
        assert retrieved.tags == ["test", "redis"]
        assert retrieved.metadata_ == {"env": "test"}

    async def test_get_nonexistent_flag(self, redis_storage) -> None:
        """Test getting a flag that doesn't exist returns None."""
        result = await redis_storage.get_flag("nonexistent-flag")
        assert result is None

    async def test_create_flag_sets_timestamps(self, redis_storage) -> None:
        """Test that create_flag sets or preserves timestamps."""
        before_create = datetime.now(UTC)
        flag = FeatureFlag(
            id=uuid4(),
            key="timestamp-test",
            name="Timestamp Test",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        created = await redis_storage.create_flag(flag)
        after_create = datetime.now(UTC)

        # With SQLAlchemy/Advanced-Alchemy, timestamps are auto-set on model creation
        assert created.created_at is not None
        assert created.updated_at is not None
        # Timestamps should be within the test execution window
        assert before_create <= created.created_at <= after_create
        assert before_create <= created.updated_at <= after_create

    async def test_create_flag_preserves_existing_timestamps(self, redis_storage) -> None:
        """Test that create_flag preserves existing timestamps."""
        existing_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        flag = FeatureFlag(
            id=uuid4(),
            key="preserve-timestamp",
            name="Preserve Timestamp Test",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
            created_at=existing_time,
            updated_at=existing_time,
        )

        created = await redis_storage.create_flag(flag)
        assert created.created_at == existing_time
        assert created.updated_at == existing_time

    # -------------------------------------------------------------------------
    # Serialization Tests
    # -------------------------------------------------------------------------

    async def test_create_flag_with_rules_serialization(
        self, redis_storage, sample_flag_with_rules: FeatureFlag
    ) -> None:
        """Test that flags with rules are properly serialized and deserialized."""
        await redis_storage.create_flag(sample_flag_with_rules)

        retrieved = await redis_storage.get_flag("rules-flag")
        assert retrieved is not None
        assert len(retrieved.rules) == 2

        # Verify first rule
        rule1 = retrieved.rules[0]
        assert rule1.name == "Premium Users"
        assert rule1.description == "Target premium users"
        assert rule1.priority == 0
        assert rule1.enabled is True
        assert rule1.conditions == [{"attribute": "plan", "operator": "eq", "value": "premium"}]
        assert rule1.serve_enabled is True
        assert rule1.rollout_percentage is None

        # Verify second rule
        rule2 = retrieved.rules[1]
        assert rule2.name == "Beta Rollout"
        assert rule2.priority == 1
        assert rule2.rollout_percentage == 50

    async def test_create_flag_with_variants_serialization(
        self, redis_storage, sample_flag_with_variants: FeatureFlag
    ) -> None:
        """Test that flags with variants are properly serialized and deserialized."""
        await redis_storage.create_flag(sample_flag_with_variants)

        retrieved = await redis_storage.get_flag("ab-test-flag")
        assert retrieved is not None
        assert retrieved.flag_type == FlagType.STRING
        assert retrieved.default_value == {"variant": "control"}
        assert len(retrieved.variants) == 2

        # Verify control variant
        control = next(v for v in retrieved.variants if v.key == "control")
        assert control.name == "Control Group"
        assert control.description == "Original experience"
        assert control.value == {"variant": "control", "button_color": "blue"}
        assert control.weight == 50

        # Verify treatment variant
        treatment = next(v for v in retrieved.variants if v.key == "treatment")
        assert treatment.name == "Treatment Group"
        assert treatment.value == {"variant": "treatment", "button_color": "green"}
        assert treatment.weight == 50

    async def test_serialization_with_all_flag_types(self, redis_storage) -> None:
        """Test serialization works for all flag types."""
        flag_types = [
            (FlagType.BOOLEAN, None),
            (FlagType.STRING, {"text": "hello"}),
            (FlagType.NUMBER, {"num": 42}),
            (FlagType.JSON, {"complex": {"nested": True, "items": [1, 2, 3]}}),
        ]

        for flag_type, default_value in flag_types:
            flag = FeatureFlag(
                id=uuid4(),
                key=f"type-test-{flag_type.value}",
                name=f"Type Test {flag_type.value}",
                flag_type=flag_type,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                default_value=default_value,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
            await redis_storage.create_flag(flag)

            retrieved = await redis_storage.get_flag(f"type-test-{flag_type.value}")
            assert retrieved is not None
            assert retrieved.flag_type == flag_type
            assert retrieved.default_value == default_value

    # -------------------------------------------------------------------------
    # Bulk Retrieval Tests
    # -------------------------------------------------------------------------

    async def test_get_flags_bulk_retrieval(self, redis_storage) -> None:
        """Test retrieving multiple flags at once."""
        flags = [
            FeatureFlag(
                id=uuid4(),
                key=f"bulk-flag-{i}",
                name=f"Bulk Flag {i}",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=i % 2 == 0,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
            for i in range(5)
        ]

        for flag in flags:
            await redis_storage.create_flag(flag)

        # Get all flags
        result = await redis_storage.get_flags(
            ["bulk-flag-0", "bulk-flag-1", "bulk-flag-2", "bulk-flag-3", "bulk-flag-4"]
        )
        assert len(result) == 5
        for i in range(5):
            assert f"bulk-flag-{i}" in result
            assert result[f"bulk-flag-{i}"].default_enabled == (i % 2 == 0)

    async def test_get_flags_with_missing_keys(self, redis_storage) -> None:
        """Test get_flags returns only existing flags when some keys don't exist."""
        flag = FeatureFlag(
            id=uuid4(),
            key="existing-flag",
            name="Existing Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        await redis_storage.create_flag(flag)

        result = await redis_storage.get_flags(["existing-flag", "nonexistent-1", "nonexistent-2"])
        assert len(result) == 1
        assert "existing-flag" in result
        assert "nonexistent-1" not in result
        assert "nonexistent-2" not in result

    async def test_get_flags_empty_keys(self, redis_storage) -> None:
        """Test get_flags with empty key list returns empty dict."""
        result = await redis_storage.get_flags([])
        assert result == {}

    async def test_get_flags_all_nonexistent(self, redis_storage) -> None:
        """Test get_flags with all nonexistent keys returns empty dict."""
        result = await redis_storage.get_flags(["fake-1", "fake-2", "fake-3"])
        assert result == {}

    # -------------------------------------------------------------------------
    # Active Flags Tests
    # -------------------------------------------------------------------------

    async def test_get_all_active_flags(self, redis_storage) -> None:
        """Test retrieving all active flags."""
        active_flags = [
            FeatureFlag(
                id=uuid4(),
                key=f"active-{i}",
                name=f"Active Flag {i}",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
            for i in range(3)
        ]

        inactive_flags = [
            FeatureFlag(
                id=uuid4(),
                key=f"inactive-{i}",
                name=f"Inactive Flag {i}",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.INACTIVE,
                default_enabled=False,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
            for i in range(2)
        ]

        archived_flag = FeatureFlag(
            id=uuid4(),
            key="archived-flag",
            name="Archived Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ARCHIVED,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        for flag in active_flags + inactive_flags + [archived_flag]:
            await redis_storage.create_flag(flag)

        result = await redis_storage.get_all_active_flags()
        assert len(result) == 3

        active_keys = {f.key for f in result}
        assert active_keys == {"active-0", "active-1", "active-2"}

    async def test_get_all_active_flags_empty(self, redis_storage) -> None:
        """Test get_all_active_flags when no flags exist."""
        result = await redis_storage.get_all_active_flags()
        assert result == []

    async def test_get_all_active_flags_none_active(self, redis_storage) -> None:
        """Test get_all_active_flags when all flags are inactive."""
        inactive_flag = FeatureFlag(
            id=uuid4(),
            key="only-inactive",
            name="Only Inactive",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.INACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        await redis_storage.create_flag(inactive_flag)

        result = await redis_storage.get_all_active_flags()
        assert result == []

    # -------------------------------------------------------------------------
    # Update Tests
    # -------------------------------------------------------------------------

    async def test_update_flag(self, redis_storage, sample_flag: FeatureFlag) -> None:
        """Test updating a flag."""
        created = await redis_storage.create_flag(sample_flag)
        original_updated_at = created.updated_at

        # Modify the flag
        created.name = "Updated Test Flag"
        created.description = "Updated description"
        created.default_enabled = False
        created.tags = ["updated", "modified"]

        updated = await redis_storage.update_flag(created)

        assert updated.name == "Updated Test Flag"
        assert updated.description == "Updated description"
        assert updated.default_enabled is False
        assert updated.tags == ["updated", "modified"]
        assert updated.updated_at > original_updated_at

        # Verify persistence
        retrieved = await redis_storage.get_flag("test-flag")
        assert retrieved is not None
        assert retrieved.name == "Updated Test Flag"
        assert retrieved.default_enabled is False

    async def test_update_flag_status(self, redis_storage, sample_flag: FeatureFlag) -> None:
        """Test updating a flag's status."""
        await redis_storage.create_flag(sample_flag)

        sample_flag.status = FlagStatus.INACTIVE
        await redis_storage.update_flag(sample_flag)

        retrieved = await redis_storage.get_flag("test-flag")
        assert retrieved is not None
        assert retrieved.status == FlagStatus.INACTIVE

    async def test_update_flag_rules(self, redis_storage, sample_flag_with_rules: FeatureFlag) -> None:
        """Test updating a flag's rules."""
        await redis_storage.create_flag(sample_flag_with_rules)

        # Add a new rule
        sample_flag_with_rules.rules.append(
            FlagRule(
                id=uuid4(),
                flag_id=sample_flag_with_rules.id,
                name="New Rule",
                priority=2,
                enabled=True,
                conditions=[{"attribute": "region", "operator": "eq", "value": "EU"}],
                serve_enabled=True,
            )
        )

        await redis_storage.update_flag(sample_flag_with_rules)

        retrieved = await redis_storage.get_flag("rules-flag")
        assert retrieved is not None
        assert len(retrieved.rules) == 3
        assert any(r.name == "New Rule" for r in retrieved.rules)

    # -------------------------------------------------------------------------
    # Delete Tests
    # -------------------------------------------------------------------------

    async def test_delete_flag(self, redis_storage, sample_flag: FeatureFlag) -> None:
        """Test deleting a flag."""
        await redis_storage.create_flag(sample_flag)

        # Verify flag exists
        assert await redis_storage.get_flag("test-flag") is not None

        # Delete flag
        result = await redis_storage.delete_flag("test-flag")
        assert result is True

        # Verify flag no longer exists
        assert await redis_storage.get_flag("test-flag") is None

    async def test_delete_nonexistent_flag(self, redis_storage) -> None:
        """Test deleting a flag that doesn't exist returns False."""
        result = await redis_storage.delete_flag("nonexistent-flag")
        assert result is False

    async def test_delete_flag_removes_from_index(self, redis_storage) -> None:
        """Test that deleting a flag removes it from the active flags index."""
        flags = [
            FeatureFlag(
                id=uuid4(),
                key=f"index-test-{i}",
                name=f"Index Test {i}",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
            for i in range(3)
        ]

        for flag in flags:
            await redis_storage.create_flag(flag)

        # Verify all active
        active = await redis_storage.get_all_active_flags()
        assert len(active) == 3

        # Delete one
        await redis_storage.delete_flag("index-test-1")

        # Verify only 2 remain
        active = await redis_storage.get_all_active_flags()
        assert len(active) == 2
        assert not any(f.key == "index-test-1" for f in active)

    # -------------------------------------------------------------------------
    # Override Tests
    # -------------------------------------------------------------------------

    async def test_create_and_get_override(self, redis_storage, sample_flag: FeatureFlag) -> None:
        """Test creating and retrieving an override."""
        await redis_storage.create_flag(sample_flag)

        override = FlagOverride(
            id=uuid4(),
            flag_id=sample_flag.id,
            entity_type="user",
            entity_id="user-123",
            enabled=False,
            value={"reason": "beta tester"},
        )

        created = await redis_storage.create_override(override)
        assert created.created_at is not None
        assert created.updated_at is not None

        retrieved = await redis_storage.get_override(sample_flag.id, "user", "user-123")
        assert retrieved is not None
        assert retrieved.enabled is False
        assert retrieved.value == {"reason": "beta tester"}
        assert retrieved.entity_type == "user"
        assert retrieved.entity_id == "user-123"

    async def test_get_nonexistent_override(self, redis_storage, sample_flag: FeatureFlag) -> None:
        """Test getting an override that doesn't exist returns None."""
        await redis_storage.create_flag(sample_flag)

        result = await redis_storage.get_override(sample_flag.id, "user", "nonexistent")
        assert result is None

    async def test_override_with_expiration(self, redis_storage, sample_flag: FeatureFlag) -> None:
        """Test that expired overrides are not returned."""
        await redis_storage.create_flag(sample_flag)

        # Create an already expired override
        expired_override = FlagOverride(
            id=uuid4(),
            flag_id=sample_flag.id,
            entity_type="user",
            entity_id="expired-user",
            enabled=True,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )

        await redis_storage.create_override(expired_override)

        # Should return None for expired override
        result = await redis_storage.get_override(sample_flag.id, "user", "expired-user")
        assert result is None

    async def test_override_with_future_expiration(self, redis_storage, sample_flag: FeatureFlag) -> None:
        """Test that non-expired overrides are returned."""
        await redis_storage.create_flag(sample_flag)

        future_override = FlagOverride(
            id=uuid4(),
            flag_id=sample_flag.id,
            entity_type="user",
            entity_id="future-user",
            enabled=True,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        await redis_storage.create_override(future_override)

        result = await redis_storage.get_override(sample_flag.id, "user", "future-user")
        assert result is not None
        assert result.enabled is True

    async def test_override_without_flag_id_raises(self, redis_storage) -> None:
        """Test that creating an override without flag_id raises ValueError."""
        override = FlagOverride(
            id=uuid4(),
            flag_id=None,
            entity_type="user",
            entity_id="user-123",
            enabled=True,
        )

        with pytest.raises(ValueError, match="flag_id"):
            await redis_storage.create_override(override)

    async def test_delete_override(self, redis_storage, sample_flag: FeatureFlag) -> None:
        """Test deleting an override."""
        await redis_storage.create_flag(sample_flag)

        override = FlagOverride(
            id=uuid4(),
            flag_id=sample_flag.id,
            entity_type="user",
            entity_id="user-to-delete",
            enabled=True,
        )

        await redis_storage.create_override(override)

        # Verify override exists
        assert await redis_storage.get_override(sample_flag.id, "user", "user-to-delete") is not None

        # Delete override
        result = await redis_storage.delete_override(sample_flag.id, "user", "user-to-delete")
        assert result is True

        # Verify override no longer exists
        assert await redis_storage.get_override(sample_flag.id, "user", "user-to-delete") is None

    async def test_delete_nonexistent_override(self, redis_storage, sample_flag: FeatureFlag) -> None:
        """Test deleting an override that doesn't exist returns False."""
        await redis_storage.create_flag(sample_flag)

        result = await redis_storage.delete_override(sample_flag.id, "user", "nonexistent")
        assert result is False

    async def test_multiple_overrides_different_entities(self, redis_storage, sample_flag: FeatureFlag) -> None:
        """Test multiple overrides for different entity types."""
        await redis_storage.create_flag(sample_flag)

        overrides = [
            FlagOverride(
                id=uuid4(),
                flag_id=sample_flag.id,
                entity_type="user",
                entity_id="user-123",
                enabled=True,
            ),
            FlagOverride(
                id=uuid4(),
                flag_id=sample_flag.id,
                entity_type="organization",
                entity_id="org-456",
                enabled=False,
            ),
            FlagOverride(
                id=uuid4(),
                flag_id=sample_flag.id,
                entity_type="tenant",
                entity_id="tenant-789",
                enabled=True,
                value={"tier": "premium"},
            ),
        ]

        for override in overrides:
            await redis_storage.create_override(override)

        # Verify each override
        user_override = await redis_storage.get_override(sample_flag.id, "user", "user-123")
        assert user_override is not None
        assert user_override.enabled is True

        org_override = await redis_storage.get_override(sample_flag.id, "organization", "org-456")
        assert org_override is not None
        assert org_override.enabled is False

        tenant_override = await redis_storage.get_override(sample_flag.id, "tenant", "tenant-789")
        assert tenant_override is not None
        assert tenant_override.enabled is True
        assert tenant_override.value == {"tier": "premium"}

    # -------------------------------------------------------------------------
    # Health Check Tests
    # -------------------------------------------------------------------------

    async def test_health_check_success(self, redis_storage) -> None:
        """Test health check returns True when Redis is healthy."""
        result = await redis_storage.health_check()
        assert result is True

    async def test_health_check_failure(self, fake_redis) -> None:
        """Test health check returns False when Redis ping fails."""
        from unittest.mock import AsyncMock

        from litestar_flags.storage.redis import RedisStorageBackend

        # Create storage with fake redis
        storage = RedisStorageBackend(redis=fake_redis, prefix="test:")

        # Mock ping to raise an exception
        storage._redis.ping = AsyncMock(side_effect=Exception("Connection refused"))

        result = await storage.health_check()
        assert result is False

    # -------------------------------------------------------------------------
    # Close/Cleanup Tests
    # -------------------------------------------------------------------------

    async def test_close(self, redis_storage) -> None:
        """Test closing the storage backend."""
        # Create a flag first
        flag = FeatureFlag(
            id=uuid4(),
            key="close-test",
            name="Close Test",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        await redis_storage.create_flag(flag)

        # Close should not raise
        await redis_storage.close()

    # -------------------------------------------------------------------------
    # Key Prefix Tests
    # -------------------------------------------------------------------------

    async def test_custom_prefix(self, fake_redis) -> None:
        """Test that custom prefixes are properly applied."""
        from litestar_flags.storage.redis import RedisStorageBackend

        storage = RedisStorageBackend(redis=fake_redis, prefix="custom_prefix:")

        flag = FeatureFlag(
            id=uuid4(),
            key="prefix-test",
            name="Prefix Test",
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

        # Verify the key was stored with the custom prefix
        raw_value = await fake_redis.get("custom_prefix:flag:prefix-test")
        assert raw_value is not None

        # Clean up
        await fake_redis.flushall()

    async def test_flag_index_key(self, fake_redis) -> None:
        """Test that flag keys are added to the index set."""
        from litestar_flags.storage.redis import RedisStorageBackend

        storage = RedisStorageBackend(redis=fake_redis, prefix="index_test:")

        flags = [
            FeatureFlag(
                id=uuid4(),
                key=f"indexed-flag-{i}",
                name=f"Indexed Flag {i}",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
            for i in range(3)
        ]

        for flag in flags:
            await storage.create_flag(flag)

        # Check the index set contains all flag keys
        members = await fake_redis.smembers("index_test:flags")
        assert len(members) == 3
        assert "indexed-flag-0" in members
        assert "indexed-flag-1" in members
        assert "indexed-flag-2" in members

        # Clean up
        await fake_redis.flushall()

    # -------------------------------------------------------------------------
    # Edge Case Tests
    # -------------------------------------------------------------------------

    async def test_flag_with_empty_collections(self, redis_storage) -> None:
        """Test flag with empty rules, variants, and tags."""
        flag = FeatureFlag(
            id=uuid4(),
            key="empty-collections",
            name="Empty Collections Test",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        await redis_storage.create_flag(flag)

        retrieved = await redis_storage.get_flag("empty-collections")
        assert retrieved is not None
        assert retrieved.tags == []
        assert retrieved.rules == []
        assert retrieved.variants == []
        assert retrieved.metadata_ == {}

    async def test_flag_with_special_characters_in_key(self, redis_storage) -> None:
        """Test flag with special characters in key."""
        flag = FeatureFlag(
            id=uuid4(),
            key="feature.my-flag_v2",
            name="Special Key Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        await redis_storage.create_flag(flag)

        retrieved = await redis_storage.get_flag("feature.my-flag_v2")
        assert retrieved is not None
        assert retrieved.key == "feature.my-flag_v2"

    async def test_flag_with_unicode_content(self, redis_storage) -> None:
        """Test flag with unicode content in name and description."""
        flag = FeatureFlag(
            id=uuid4(),
            key="unicode-flag",
            name="Flagge mit Umlauten: aou",
            description="Description with emoji and special chars",
            flag_type=FlagType.STRING,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            default_value={"message": "Hello World"},
            tags=["international", "test"],
            metadata_={"region": "EU", "lang": "de"},
            rules=[],
            overrides=[],
            variants=[],
        )

        await redis_storage.create_flag(flag)

        retrieved = await redis_storage.get_flag("unicode-flag")
        assert retrieved is not None
        assert "Umlauten" in retrieved.name
        assert retrieved.default_value == {"message": "Hello World"}

    async def test_large_metadata(self, redis_storage) -> None:
        """Test flag with large metadata payload."""
        large_metadata = {f"key_{i}": f"value_{i}" * 100 for i in range(100)}

        flag = FeatureFlag(
            id=uuid4(),
            key="large-metadata",
            name="Large Metadata Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_=large_metadata,
            rules=[],
            overrides=[],
            variants=[],
        )

        await redis_storage.create_flag(flag)

        retrieved = await redis_storage.get_flag("large-metadata")
        assert retrieved is not None
        assert retrieved.metadata_ == large_metadata

    async def test_concurrent_flag_operations(self, redis_storage) -> None:
        """Test concurrent flag create and read operations."""
        import asyncio

        flags = [
            FeatureFlag(
                id=uuid4(),
                key=f"concurrent-{i}",
                name=f"Concurrent Flag {i}",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
            for i in range(10)
        ]

        # Create all flags concurrently
        await asyncio.gather(*[redis_storage.create_flag(flag) for flag in flags])

        # Read all flags concurrently
        results = await asyncio.gather(*[redis_storage.get_flag(f"concurrent-{i}") for i in range(10)])

        assert all(r is not None for r in results)
        assert len(results) == 10


class TestRedisStorageBackendFactory:
    """Tests for RedisStorageBackend.create() factory method."""

    async def test_create_method_not_tested_without_real_redis(self) -> None:
        """Note: The create() factory method connects to a real Redis server.

        Testing this requires either:
        1. A real Redis server
        2. Mocking Redis.from_url at the module level

        The existing fixtures in conftest.py bypass create() by directly
        instantiating RedisStorageBackend with a fake_redis client.
        """
        # This test documents that create() is not directly tested with fakeredis
        # because it uses Redis.from_url() which expects a real connection URL.
        pass
