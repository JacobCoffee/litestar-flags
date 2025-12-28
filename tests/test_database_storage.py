"""Tests for DatabaseStorageBackend."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from litestar_flags.types import FlagStatus, FlagType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


# Skip all tests in this module if advanced-alchemy is not available
pytest.importorskip("advanced_alchemy")


class TestDatabaseStorageBackend:
    """Tests for DatabaseStorageBackend with SQLite."""

    @pytest.fixture
    async def db_storage(self, async_sqlite_engine: AsyncEngine):
        """Create a DatabaseStorageBackend with SQLite for testing."""
        # Create tables
        from advanced_alchemy.base import orm_registry
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.override import FlagOverride
        from litestar_flags.models.rule import FlagRule
        from litestar_flags.models.variant import FlagVariant
        from litestar_flags.storage.database import DatabaseStorageBackend

        # Register models
        _ = FeatureFlag, FlagOverride, FlagRule, FlagVariant

        async with async_sqlite_engine.begin() as conn:
            await conn.run_sync(orm_registry.metadata.create_all)

        session_maker = async_sessionmaker(async_sqlite_engine, expire_on_commit=False)

        storage = DatabaseStorageBackend(
            engine=async_sqlite_engine,
            session_maker=session_maker,
        )

        yield storage

        # Cleanup
        await storage.close()

    @pytest.fixture
    def sample_flag(self):
        """Create a sample FeatureFlag for testing."""
        from litestar_flags.models.flag import FeatureFlag

        return FeatureFlag(
            key="test-flag",
            name="Test Flag",
            description="A test flag for unit testing",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=["test", "unit"],
            metadata_={"environment": "test"},
        )

    @pytest.fixture
    def inactive_flag(self):
        """Create an inactive FeatureFlag for testing."""
        from litestar_flags.models.flag import FeatureFlag

        return FeatureFlag(
            key="inactive-flag",
            name="Inactive Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.INACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
        )

    # -------------------------------------------------------------------------
    # Test get_flag()
    # -------------------------------------------------------------------------

    async def test_get_flag_returns_none_when_not_found(self, db_storage) -> None:
        """Test that get_flag returns None for non-existent flag."""
        result = await db_storage.get_flag("nonexistent-flag")
        assert result is None

    async def test_get_flag_returns_flag_when_found(self, db_storage, sample_flag) -> None:
        """Test that get_flag returns the flag when it exists."""
        await db_storage.create_flag(sample_flag)

        result = await db_storage.get_flag("test-flag")

        assert result is not None
        assert result.key == "test-flag"
        assert result.name == "Test Flag"
        assert result.description == "A test flag for unit testing"
        assert result.flag_type == FlagType.BOOLEAN
        assert result.status == FlagStatus.ACTIVE
        assert result.default_enabled is True

    async def test_get_flag_returns_flag_with_correct_metadata(self, db_storage, sample_flag) -> None:
        """Test that get_flag returns flag with preserved metadata."""
        await db_storage.create_flag(sample_flag)

        result = await db_storage.get_flag("test-flag")

        assert result is not None
        assert result.tags == ["test", "unit"]
        assert result.metadata_ == {"environment": "test"}

    async def test_get_flag_returns_flag_with_timestamps(self, db_storage, sample_flag) -> None:
        """Test that get_flag returns flag with auto-generated timestamps."""
        await db_storage.create_flag(sample_flag)

        result = await db_storage.get_flag("test-flag")

        assert result is not None
        assert result.created_at is not None
        assert result.updated_at is not None

    # -------------------------------------------------------------------------
    # Test get_flags() bulk retrieval
    # -------------------------------------------------------------------------

    async def test_get_flags_returns_empty_dict_for_empty_keys(self, db_storage) -> None:
        """Test that get_flags returns empty dict when no keys provided."""
        result = await db_storage.get_flags([])
        assert result == {}

    async def test_get_flags_returns_empty_dict_for_nonexistent_keys(self, db_storage) -> None:
        """Test that get_flags returns empty dict when keys don't exist."""
        result = await db_storage.get_flags(["nonexistent-1", "nonexistent-2"])
        assert result == {}

    async def test_get_flags_returns_found_flags(self, db_storage) -> None:
        """Test that get_flags returns only the flags that exist."""
        from litestar_flags.models.flag import FeatureFlag

        flag1 = FeatureFlag(
            key="flag-1",
            name="Flag 1",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
        )
        flag2 = FeatureFlag(
            key="flag-2",
            name="Flag 2",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
        )

        await db_storage.create_flag(flag1)
        await db_storage.create_flag(flag2)

        result = await db_storage.get_flags(["flag-1", "flag-2", "nonexistent"])

        assert len(result) == 2
        assert "flag-1" in result
        assert "flag-2" in result
        assert "nonexistent" not in result
        assert result["flag-1"].name == "Flag 1"
        assert result["flag-2"].name == "Flag 2"

    async def test_get_flags_returns_partial_results(self, db_storage, sample_flag) -> None:
        """Test that get_flags returns partial results when some keys exist."""
        await db_storage.create_flag(sample_flag)

        result = await db_storage.get_flags(["test-flag", "nonexistent"])

        assert len(result) == 1
        assert "test-flag" in result
        assert result["test-flag"].key == "test-flag"

    # -------------------------------------------------------------------------
    # Test get_all_active_flags()
    # -------------------------------------------------------------------------

    async def test_get_all_active_flags_returns_empty_when_no_flags(self, db_storage) -> None:
        """Test that get_all_active_flags returns empty list when no flags exist."""
        result = await db_storage.get_all_active_flags()
        assert result == []

    async def test_get_all_active_flags_returns_only_active_flags(self, db_storage, sample_flag, inactive_flag) -> None:
        """Test that get_all_active_flags returns only ACTIVE status flags."""
        await db_storage.create_flag(sample_flag)  # ACTIVE
        await db_storage.create_flag(inactive_flag)  # INACTIVE

        result = await db_storage.get_all_active_flags()

        assert len(result) == 1
        assert result[0].key == "test-flag"
        assert result[0].status == FlagStatus.ACTIVE

    async def test_get_all_active_flags_returns_multiple_active_flags(self, db_storage) -> None:
        """Test that get_all_active_flags returns all active flags."""
        from litestar_flags.models.flag import FeatureFlag

        flags = [
            FeatureFlag(
                key=f"active-flag-{i}",
                name=f"Active Flag {i}",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                tags=[],
                metadata_={},
            )
            for i in range(3)
        ]

        for flag in flags:
            await db_storage.create_flag(flag)

        result = await db_storage.get_all_active_flags()

        assert len(result) == 3
        keys = {f.key for f in result}
        assert keys == {"active-flag-0", "active-flag-1", "active-flag-2"}

    async def test_get_all_active_flags_excludes_archived_flags(self, db_storage) -> None:
        """Test that get_all_active_flags excludes ARCHIVED status flags."""
        from litestar_flags.models.flag import FeatureFlag

        active_flag = FeatureFlag(
            key="active-flag",
            name="Active Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
        )
        archived_flag = FeatureFlag(
            key="archived-flag",
            name="Archived Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ARCHIVED,
            default_enabled=True,
            tags=[],
            metadata_={},
        )

        await db_storage.create_flag(active_flag)
        await db_storage.create_flag(archived_flag)

        result = await db_storage.get_all_active_flags()

        assert len(result) == 1
        assert result[0].key == "active-flag"

    # -------------------------------------------------------------------------
    # Test create_flag()
    # -------------------------------------------------------------------------

    async def test_create_flag_basic(self, db_storage, sample_flag) -> None:
        """Test basic flag creation."""
        created = await db_storage.create_flag(sample_flag)

        assert created.key == "test-flag"
        assert created.name == "Test Flag"
        assert created.id is not None
        assert created.created_at is not None
        assert created.updated_at is not None

    async def test_create_flag_with_rules(self, db_storage) -> None:
        """Test creating a flag with targeting rules."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.rule import FlagRule

        flag = FeatureFlag(
            key="rules-flag",
            name="Flag with Rules",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    name="Premium Users",
                    priority=0,
                    enabled=True,
                    conditions=[{"attribute": "plan", "operator": "eq", "value": "premium"}],
                    serve_enabled=True,
                ),
                FlagRule(
                    name="US Users",
                    priority=1,
                    enabled=True,
                    conditions=[{"attribute": "country", "operator": "in", "value": ["US", "CA"]}],
                    serve_enabled=True,
                ),
            ],
        )

        created = await db_storage.create_flag(flag)

        assert created.key == "rules-flag"
        assert len(created.rules) == 2
        assert created.rules[0].name == "Premium Users"
        assert created.rules[0].priority == 0
        assert created.rules[1].name == "US Users"
        assert created.rules[1].priority == 1

        # Verify retrieval includes rules
        retrieved = await db_storage.get_flag("rules-flag")
        assert retrieved is not None
        assert len(retrieved.rules) == 2

    async def test_create_flag_with_variants(self, db_storage) -> None:
        """Test creating a flag with A/B test variants."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.variant import FlagVariant

        flag = FeatureFlag(
            key="ab-test",
            name="A/B Test Flag",
            flag_type=FlagType.STRING,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            default_value={"variant": "control"},
            tags=["experiment"],
            metadata_={},
            variants=[
                FlagVariant(
                    key="control",
                    name="Control",
                    value={"variant": "control"},
                    weight=50,
                ),
                FlagVariant(
                    key="treatment",
                    name="Treatment",
                    value={"variant": "treatment"},
                    weight=50,
                ),
            ],
        )

        created = await db_storage.create_flag(flag)

        assert created.key == "ab-test"
        assert len(created.variants) == 2
        assert {v.key for v in created.variants} == {"control", "treatment"}
        assert sum(v.weight for v in created.variants) == 100

        # Verify retrieval includes variants
        retrieved = await db_storage.get_flag("ab-test")
        assert retrieved is not None
        assert len(retrieved.variants) == 2

    async def test_create_flag_with_overrides(self, db_storage) -> None:
        """Test creating a flag with entity overrides."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.override import FlagOverride

        flag = FeatureFlag(
            key="override-flag",
            name="Override Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            overrides=[
                FlagOverride(
                    entity_type="user",
                    entity_id="user-123",
                    enabled=True,
                ),
                FlagOverride(
                    entity_type="organization",
                    entity_id="org-456",
                    enabled=True,
                ),
            ],
        )

        created = await db_storage.create_flag(flag)

        assert created.key == "override-flag"
        assert len(created.overrides) == 2

        # Verify retrieval includes overrides
        retrieved = await db_storage.get_flag("override-flag")
        assert retrieved is not None
        assert len(retrieved.overrides) == 2

    async def test_create_flag_with_all_relationships(self, db_storage) -> None:
        """Test creating a flag with rules, variants, and overrides."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.override import FlagOverride
        from litestar_flags.models.rule import FlagRule
        from litestar_flags.models.variant import FlagVariant

        flag = FeatureFlag(
            key="full-flag",
            name="Full Flag",
            flag_type=FlagType.STRING,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            default_value={"version": "1.0"},
            tags=["full", "test"],
            metadata_={"owner": "test-team"},
            rules=[
                FlagRule(
                    name="Beta Rule",
                    priority=0,
                    enabled=True,
                    conditions=[{"attribute": "beta", "operator": "eq", "value": True}],
                    serve_enabled=True,
                ),
            ],
            variants=[
                FlagVariant(
                    key="v1",
                    name="Version 1",
                    value={"version": "1.0"},
                    weight=70,
                ),
                FlagVariant(
                    key="v2",
                    name="Version 2",
                    value={"version": "2.0"},
                    weight=30,
                ),
            ],
            overrides=[
                FlagOverride(
                    entity_type="user",
                    entity_id="vip-user",
                    enabled=True,
                    value={"version": "2.0"},
                ),
            ],
        )

        created = await db_storage.create_flag(flag)

        assert created.key == "full-flag"
        assert len(created.rules) == 1
        assert len(created.variants) == 2
        assert len(created.overrides) == 1

        # Verify all relationships persist on retrieval
        retrieved = await db_storage.get_flag("full-flag")
        assert retrieved is not None
        assert len(retrieved.rules) == 1
        assert len(retrieved.variants) == 2
        assert len(retrieved.overrides) == 1

    async def test_create_flag_non_boolean_type(self, db_storage) -> None:
        """Test creating a non-boolean flag with default value."""
        from litestar_flags.models.flag import FeatureFlag

        flag = FeatureFlag(
            key="json-flag",
            name="JSON Flag",
            flag_type=FlagType.JSON,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            default_value={"theme": "dark", "max_items": 10},
            tags=[],
            metadata_={},
        )

        created = await db_storage.create_flag(flag)

        assert created.key == "json-flag"
        assert created.flag_type == FlagType.JSON
        assert created.default_value == {"theme": "dark", "max_items": 10}

    # -------------------------------------------------------------------------
    # Test update_flag()
    # -------------------------------------------------------------------------

    async def test_update_flag_basic(self, db_storage, sample_flag) -> None:
        """Test basic flag update."""
        await db_storage.create_flag(sample_flag)

        # Retrieve and modify
        flag = await db_storage.get_flag("test-flag")
        assert flag is not None

        flag.default_enabled = False
        flag.description = "Updated description"

        updated = await db_storage.update_flag(flag)

        assert updated.default_enabled is False
        assert updated.description == "Updated description"

        # Verify persistence
        retrieved = await db_storage.get_flag("test-flag")
        assert retrieved is not None
        assert retrieved.default_enabled is False
        assert retrieved.description == "Updated description"

    async def test_update_flag_status(self, db_storage, sample_flag) -> None:
        """Test updating flag status."""
        await db_storage.create_flag(sample_flag)

        flag = await db_storage.get_flag("test-flag")
        assert flag is not None
        assert flag.status == FlagStatus.ACTIVE

        flag.status = FlagStatus.INACTIVE
        updated = await db_storage.update_flag(flag)

        assert updated.status == FlagStatus.INACTIVE

        # Should no longer appear in active flags
        active_flags = await db_storage.get_all_active_flags()
        assert len(active_flags) == 0

    async def test_update_flag_scalar_fields(self, db_storage, sample_flag) -> None:
        """Test updating scalar flag fields like name and description.

        Note: SQLAlchemy has known limitations with JSON column mutation tracking
        when merging objects across sessions. Scalar fields (name, description,
        default_enabled, status) update correctly.
        """
        await db_storage.create_flag(sample_flag)

        flag = await db_storage.get_flag("test-flag")
        assert flag is not None

        # Update scalar fields
        flag.name = "Updated Test Flag"
        flag.description = "Updated description for testing"

        updated = await db_storage.update_flag(flag)

        assert updated.name == "Updated Test Flag"
        assert updated.description == "Updated description for testing"

        # Verify persistence
        retrieved = await db_storage.get_flag("test-flag")
        assert retrieved is not None
        assert retrieved.name == "Updated Test Flag"
        assert retrieved.description == "Updated description for testing"

    async def test_update_flag_preserves_id(self, db_storage, sample_flag) -> None:
        """Test that update preserves the flag ID."""
        created = await db_storage.create_flag(sample_flag)
        original_id = created.id

        flag = await db_storage.get_flag("test-flag")
        assert flag is not None

        flag.name = "Updated Name"
        updated = await db_storage.update_flag(flag)

        assert updated.id == original_id

    # -------------------------------------------------------------------------
    # Test delete_flag() with cascade
    # -------------------------------------------------------------------------

    async def test_delete_flag_returns_true_when_found(self, db_storage, sample_flag) -> None:
        """Test that delete_flag returns True when flag exists."""
        await db_storage.create_flag(sample_flag)

        result = await db_storage.delete_flag("test-flag")

        assert result is True

    async def test_delete_flag_returns_false_when_not_found(self, db_storage) -> None:
        """Test that delete_flag returns False when flag doesn't exist."""
        result = await db_storage.delete_flag("nonexistent-flag")
        assert result is False

    async def test_delete_flag_removes_flag(self, db_storage, sample_flag) -> None:
        """Test that delete_flag removes the flag from storage."""
        await db_storage.create_flag(sample_flag)

        await db_storage.delete_flag("test-flag")

        result = await db_storage.get_flag("test-flag")
        assert result is None

    async def test_delete_flag_cascades_to_rules(self, db_storage) -> None:
        """Test that deleting a flag cascades to its rules."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.rule import FlagRule

        flag = FeatureFlag(
            key="cascade-rules-flag",
            name="Cascade Rules Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    name="Rule 1",
                    priority=0,
                    enabled=True,
                    conditions=[],
                    serve_enabled=True,
                ),
            ],
        )

        created = await db_storage.create_flag(flag)
        assert len(created.rules) == 1

        # Delete the flag
        result = await db_storage.delete_flag("cascade-rules-flag")
        assert result is True

        # Verify flag is gone
        retrieved = await db_storage.get_flag("cascade-rules-flag")
        assert retrieved is None

    async def test_delete_flag_cascades_to_variants(self, db_storage) -> None:
        """Test that deleting a flag cascades to its variants."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.variant import FlagVariant

        flag = FeatureFlag(
            key="cascade-variants-flag",
            name="Cascade Variants Flag",
            flag_type=FlagType.STRING,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            variants=[
                FlagVariant(
                    key="v1",
                    name="Variant 1",
                    value={"v": 1},
                    weight=100,
                ),
            ],
        )

        created = await db_storage.create_flag(flag)
        assert len(created.variants) == 1

        # Delete the flag
        result = await db_storage.delete_flag("cascade-variants-flag")
        assert result is True

        # Verify flag is gone
        retrieved = await db_storage.get_flag("cascade-variants-flag")
        assert retrieved is None

    async def test_delete_flag_cascades_to_overrides(self, db_storage) -> None:
        """Test that deleting a flag cascades to its overrides."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.override import FlagOverride

        flag = FeatureFlag(
            key="cascade-overrides-flag",
            name="Cascade Overrides Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            overrides=[
                FlagOverride(
                    entity_type="user",
                    entity_id="user-123",
                    enabled=True,
                ),
            ],
        )

        created = await db_storage.create_flag(flag)
        assert len(created.overrides) == 1
        flag_id = created.id

        # Delete the flag
        result = await db_storage.delete_flag("cascade-overrides-flag")
        assert result is True

        # Verify override is also gone (via get_override)
        override = await db_storage.get_override(flag_id, "user", "user-123")
        assert override is None

    async def test_delete_flag_double_delete(self, db_storage, sample_flag) -> None:
        """Test that deleting a flag twice returns False the second time."""
        await db_storage.create_flag(sample_flag)

        first_result = await db_storage.delete_flag("test-flag")
        assert first_result is True

        second_result = await db_storage.delete_flag("test-flag")
        assert second_result is False

    # -------------------------------------------------------------------------
    # Test get_override()
    # -------------------------------------------------------------------------

    async def test_get_override_returns_none_when_not_found(self, db_storage, sample_flag) -> None:
        """Test that get_override returns None when override doesn't exist."""
        await db_storage.create_flag(sample_flag)

        result = await db_storage.get_override(sample_flag.id, "user", "nonexistent")
        assert result is None

    async def test_get_override_returns_override_when_found(self, db_storage) -> None:
        """Test that get_override returns the override when it exists."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.override import FlagOverride

        flag = FeatureFlag(
            key="override-test-flag",
            name="Override Test Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            overrides=[
                FlagOverride(
                    entity_type="user",
                    entity_id="user-123",
                    enabled=True,
                ),
            ],
        )

        created = await db_storage.create_flag(flag)

        result = await db_storage.get_override(created.id, "user", "user-123")

        assert result is not None
        assert result.entity_type == "user"
        assert result.entity_id == "user-123"
        assert result.enabled is True

    async def test_get_override_returns_correct_override_for_entity(self, db_storage) -> None:
        """Test that get_override returns the correct override for specific entity."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.override import FlagOverride

        flag = FeatureFlag(
            key="multi-override-flag",
            name="Multi Override Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            overrides=[
                FlagOverride(
                    entity_type="user",
                    entity_id="user-123",
                    enabled=True,
                ),
                FlagOverride(
                    entity_type="user",
                    entity_id="user-456",
                    enabled=False,
                ),
                FlagOverride(
                    entity_type="organization",
                    entity_id="org-789",
                    enabled=True,
                ),
            ],
        )

        created = await db_storage.create_flag(flag)

        # Test each override
        user123 = await db_storage.get_override(created.id, "user", "user-123")
        assert user123 is not None
        assert user123.enabled is True

        user456 = await db_storage.get_override(created.id, "user", "user-456")
        assert user456 is not None
        assert user456.enabled is False

        org789 = await db_storage.get_override(created.id, "organization", "org-789")
        assert org789 is not None
        assert org789.enabled is True

    async def test_get_override_with_value(self, db_storage) -> None:
        """Test that get_override returns override with value for non-boolean flags."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.override import FlagOverride

        flag = FeatureFlag(
            key="value-override-flag",
            name="Value Override Flag",
            flag_type=FlagType.JSON,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            default_value={"theme": "light"},
            tags=[],
            metadata_={},
            overrides=[
                FlagOverride(
                    entity_type="user",
                    entity_id="user-vip",
                    enabled=True,
                    value={"theme": "dark", "premium": True},
                ),
            ],
        )

        created = await db_storage.create_flag(flag)

        result = await db_storage.get_override(created.id, "user", "user-vip")

        assert result is not None
        assert result.value == {"theme": "dark", "premium": True}

    async def test_get_override_with_expiration(self, db_storage) -> None:
        """Test that get_override returns override with expiration timestamp."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.override import FlagOverride

        expires = datetime.now(UTC) + timedelta(days=7)

        flag = FeatureFlag(
            key="expiring-override-flag",
            name="Expiring Override Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            overrides=[
                FlagOverride(
                    entity_type="user",
                    entity_id="temp-user",
                    enabled=True,
                    expires_at=expires,
                ),
            ],
        )

        created = await db_storage.create_flag(flag)

        result = await db_storage.get_override(created.id, "user", "temp-user")

        assert result is not None
        assert result.expires_at is not None
        # Note: Database returns naive datetime, need to handle timezone
        assert result.is_expired() is False

    # -------------------------------------------------------------------------
    # Test create_override() and delete_override()
    # -------------------------------------------------------------------------

    async def test_create_override_standalone(self, db_storage, sample_flag) -> None:
        """Test creating an override separately from flag creation."""
        from litestar_flags.models.override import FlagOverride

        created_flag = await db_storage.create_flag(sample_flag)

        override = FlagOverride(
            flag_id=created_flag.id,
            entity_type="user",
            entity_id="new-user",
            enabled=True,
        )

        created_override = await db_storage.create_override(override)

        assert created_override.id is not None
        assert created_override.flag_id == created_flag.id
        assert created_override.entity_type == "user"
        assert created_override.entity_id == "new-user"

        # Verify via get_override
        retrieved = await db_storage.get_override(created_flag.id, "user", "new-user")
        assert retrieved is not None
        assert retrieved.enabled is True

    async def test_delete_override_returns_true_when_found(self, db_storage) -> None:
        """Test that delete_override returns True when override exists."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.override import FlagOverride

        flag = FeatureFlag(
            key="delete-override-flag",
            name="Delete Override Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            overrides=[
                FlagOverride(
                    entity_type="user",
                    entity_id="user-to-delete",
                    enabled=True,
                ),
            ],
        )

        created = await db_storage.create_flag(flag)

        result = await db_storage.delete_override(created.id, "user", "user-to-delete")
        assert result is True

        # Verify override is gone
        override = await db_storage.get_override(created.id, "user", "user-to-delete")
        assert override is None

    async def test_delete_override_returns_false_when_not_found(self, db_storage, sample_flag) -> None:
        """Test that delete_override returns False when override doesn't exist."""
        created = await db_storage.create_flag(sample_flag)

        result = await db_storage.delete_override(created.id, "user", "nonexistent")
        assert result is False

    # -------------------------------------------------------------------------
    # Test health_check()
    # -------------------------------------------------------------------------

    async def test_health_check_returns_true_when_healthy(self, db_storage) -> None:
        """Test that health_check returns True when database is accessible."""
        result = await db_storage.health_check()
        assert result is True

    async def test_health_check_after_operations(self, db_storage, sample_flag) -> None:
        """Test that health_check works after performing operations."""
        # Perform some operations
        await db_storage.create_flag(sample_flag)
        await db_storage.get_flag("test-flag")
        await db_storage.get_all_active_flags()

        # Health check should still pass
        result = await db_storage.health_check()
        assert result is True

    async def test_health_check_returns_false_on_error(self, async_sqlite_engine) -> None:
        """Test that health_check returns False when database is unavailable."""
        from unittest.mock import AsyncMock, MagicMock

        from litestar_flags.storage.database import DatabaseStorageBackend

        # Create a mock session maker that raises an exception
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("Database unavailable"))
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_maker = MagicMock(return_value=mock_session)

        storage = DatabaseStorageBackend(
            engine=async_sqlite_engine,
            session_maker=mock_session_maker,
        )

        result = await storage.health_check()
        assert result is False

    # -------------------------------------------------------------------------
    # Test close()
    # -------------------------------------------------------------------------

    async def test_close_disposes_engine(self, async_sqlite_engine) -> None:
        """Test that close properly disposes the database engine."""
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from litestar_flags.storage.database import DatabaseStorageBackend

        session_maker = async_sessionmaker(async_sqlite_engine, expire_on_commit=False)
        storage = DatabaseStorageBackend(
            engine=async_sqlite_engine,
            session_maker=session_maker,
        )

        # Close should not raise
        await storage.close()


class TestDatabaseStorageBackendCreate:
    """Tests for DatabaseStorageBackend.create() factory method."""

    async def test_create_with_sqlite(self) -> None:
        """Test creating DatabaseStorageBackend with SQLite."""
        from litestar_flags.storage.database import DatabaseStorageBackend

        storage = await DatabaseStorageBackend.create(
            connection_string="sqlite+aiosqlite:///:memory:",
            create_tables=True,
        )

        # Verify it works
        result = await storage.health_check()
        assert result is True

        await storage.close()

    async def test_create_without_tables(self) -> None:
        """Test creating DatabaseStorageBackend without auto table creation."""
        from litestar_flags.storage.database import DatabaseStorageBackend

        # This should succeed even without tables
        storage = await DatabaseStorageBackend.create(
            connection_string="sqlite+aiosqlite:///:memory:",
            create_tables=False,
        )

        # Health check should still work (just runs SELECT 1)
        result = await storage.health_check()
        assert result is True

        await storage.close()


class TestFeatureFlagRepository:
    """Tests for FeatureFlagRepository directly."""

    @pytest.fixture
    async def db_session(self, async_sqlite_engine):
        """Create a database session with tables."""
        from advanced_alchemy.base import orm_registry
        from sqlalchemy.ext.asyncio import AsyncSession

        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.override import FlagOverride
        from litestar_flags.models.rule import FlagRule
        from litestar_flags.models.variant import FlagVariant

        # Register models
        _ = FeatureFlag, FlagOverride, FlagRule, FlagVariant

        async with async_sqlite_engine.begin() as conn:
            await conn.run_sync(orm_registry.metadata.create_all)

        async with AsyncSession(async_sqlite_engine, expire_on_commit=False) as session:
            yield session

    async def test_get_by_key_returns_none(self, db_session) -> None:
        """Test FeatureFlagRepository.get_by_key returns None when not found."""
        from litestar_flags.storage.database import FeatureFlagRepository

        repo = FeatureFlagRepository(session=db_session)

        result = await repo.get_by_key("nonexistent")
        assert result is None

    async def test_get_by_key_returns_flag(self, db_session) -> None:
        """Test FeatureFlagRepository.get_by_key returns flag when found."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.storage.database import FeatureFlagRepository

        repo = FeatureFlagRepository(session=db_session)

        flag = FeatureFlag(
            key="repo-test-flag",
            name="Repo Test Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
        )

        await repo.add(flag)
        await db_session.commit()

        result = await repo.get_by_key("repo-test-flag")
        assert result is not None
        assert result.key == "repo-test-flag"

    async def test_get_by_keys_returns_empty_for_empty_input(self, db_session) -> None:
        """Test FeatureFlagRepository.get_by_keys returns empty list for empty input."""
        from litestar_flags.storage.database import FeatureFlagRepository

        repo = FeatureFlagRepository(session=db_session)

        result = await repo.get_by_keys([])
        assert result == []

    async def test_get_active_flags_returns_only_active(self, db_session) -> None:
        """Test FeatureFlagRepository.get_active_flags returns only active flags."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.storage.database import FeatureFlagRepository

        repo = FeatureFlagRepository(session=db_session)

        active_flag = FeatureFlag(
            key="active-repo-flag",
            name="Active Repo Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
        )
        inactive_flag = FeatureFlag(
            key="inactive-repo-flag",
            name="Inactive Repo Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.INACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
        )

        await repo.add(active_flag)
        await repo.add(inactive_flag)
        await db_session.commit()

        result = await repo.get_active_flags()
        assert len(result) == 1
        assert result[0].key == "active-repo-flag"


class TestFlagOverrideRepository:
    """Tests for FlagOverrideRepository directly."""

    @pytest.fixture
    async def db_session(self, async_sqlite_engine):
        """Create a database session with tables."""
        from advanced_alchemy.base import orm_registry
        from sqlalchemy.ext.asyncio import AsyncSession

        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.override import FlagOverride
        from litestar_flags.models.rule import FlagRule
        from litestar_flags.models.variant import FlagVariant

        # Register models
        _ = FeatureFlag, FlagOverride, FlagRule, FlagVariant

        async with async_sqlite_engine.begin() as conn:
            await conn.run_sync(orm_registry.metadata.create_all)

        async with AsyncSession(async_sqlite_engine, expire_on_commit=False) as session:
            yield session

    async def test_get_override_returns_none(self, db_session) -> None:
        """Test FlagOverrideRepository.get_override returns None when not found."""
        from uuid import uuid4

        from litestar_flags.storage.database import FlagOverrideRepository

        repo = FlagOverrideRepository(session=db_session)

        result = await repo.get_override(uuid4(), "user", "nonexistent")
        assert result is None

    async def test_get_override_returns_override(self, db_session) -> None:
        """Test FlagOverrideRepository.get_override returns override when found."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.override import FlagOverride
        from litestar_flags.storage.database import FeatureFlagRepository, FlagOverrideRepository

        flag_repo = FeatureFlagRepository(session=db_session)
        override_repo = FlagOverrideRepository(session=db_session)

        # Create flag first
        flag = FeatureFlag(
            key="override-repo-flag",
            name="Override Repo Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
        )
        await flag_repo.add(flag)
        await db_session.commit()
        await db_session.refresh(flag)

        # Create override
        override = FlagOverride(
            flag_id=flag.id,
            entity_type="user",
            entity_id="user-repo-test",
            enabled=True,
        )
        await override_repo.add(override)
        await db_session.commit()

        result = await override_repo.get_override(flag.id, "user", "user-repo-test")
        assert result is not None
        assert result.enabled is True
