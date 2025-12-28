"""Tests for storage backends."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from litestar_flags import MemoryStorageBackend
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.models.override import FlagOverride
from litestar_flags.types import FlagStatus, FlagType


class TestMemoryStorageBackend:
    """Tests for MemoryStorageBackend."""

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        """Create a fresh storage instance."""
        return MemoryStorageBackend()

    @pytest.fixture
    def sample_flag(self) -> FeatureFlag:
        """Create a sample flag."""
        return FeatureFlag(
            id=uuid4(),
            key="test-flag",
            name="Test Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

    async def test_create_and_get_flag(self, storage: MemoryStorageBackend, sample_flag: FeatureFlag) -> None:
        """Test creating and retrieving a flag."""
        created = await storage.create_flag(sample_flag)
        assert created.key == "test-flag"
        assert created.created_at is not None

        retrieved = await storage.get_flag("test-flag")
        assert retrieved is not None
        assert retrieved.key == "test-flag"
        assert retrieved.default_enabled is True

    async def test_get_nonexistent_flag(self, storage: MemoryStorageBackend) -> None:
        """Test getting a flag that doesn't exist."""
        result = await storage.get_flag("nonexistent")
        assert result is None

    async def test_get_multiple_flags(self, storage: MemoryStorageBackend) -> None:
        """Test getting multiple flags at once."""
        flag1 = FeatureFlag(
            id=uuid4(),
            key="flag-1",
            name="Flag 1",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
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
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        await storage.create_flag(flag1)
        await storage.create_flag(flag2)

        flags = await storage.get_flags(["flag-1", "flag-2", "flag-3"])
        assert len(flags) == 2
        assert "flag-1" in flags
        assert "flag-2" in flags
        assert "flag-3" not in flags

    async def test_get_all_active_flags(self, storage: MemoryStorageBackend) -> None:
        """Test getting all active flags."""
        active_flag = FeatureFlag(
            id=uuid4(),
            key="active",
            name="Active",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        inactive_flag = FeatureFlag(
            id=uuid4(),
            key="inactive",
            name="Inactive",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.INACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        await storage.create_flag(active_flag)
        await storage.create_flag(inactive_flag)

        active_flags = await storage.get_all_active_flags()
        assert len(active_flags) == 1
        assert active_flags[0].key == "active"

    async def test_update_flag(self, storage: MemoryStorageBackend, sample_flag: FeatureFlag) -> None:
        """Test updating a flag."""
        await storage.create_flag(sample_flag)

        sample_flag.default_enabled = False
        updated = await storage.update_flag(sample_flag)

        assert updated.default_enabled is False

        retrieved = await storage.get_flag("test-flag")
        assert retrieved is not None
        assert retrieved.default_enabled is False

    async def test_delete_flag(self, storage: MemoryStorageBackend, sample_flag: FeatureFlag) -> None:
        """Test deleting a flag."""
        await storage.create_flag(sample_flag)

        result = await storage.delete_flag("test-flag")
        assert result is True

        retrieved = await storage.get_flag("test-flag")
        assert retrieved is None

        # Deleting again returns False
        result = await storage.delete_flag("test-flag")
        assert result is False

    async def test_create_duplicate_flag_fails(self, storage: MemoryStorageBackend, sample_flag: FeatureFlag) -> None:
        """Test that creating a duplicate flag raises an error."""
        await storage.create_flag(sample_flag)

        with pytest.raises(ValueError, match="already exists"):
            await storage.create_flag(sample_flag)

    async def test_override_creation_and_retrieval(
        self, storage: MemoryStorageBackend, sample_flag: FeatureFlag
    ) -> None:
        """Test creating and retrieving overrides."""
        await storage.create_flag(sample_flag)

        override = FlagOverride(
            id=uuid4(),
            flag_id=sample_flag.id,
            entity_type="user",
            entity_id="user-123",
            enabled=False,
        )
        await storage.create_override(override)

        retrieved = await storage.get_override(sample_flag.id, "user", "user-123")
        assert retrieved is not None
        assert retrieved.enabled is False

    async def test_expired_override_not_returned(self, storage: MemoryStorageBackend, sample_flag: FeatureFlag) -> None:
        """Test that expired overrides are not returned."""
        await storage.create_flag(sample_flag)

        override = FlagOverride(
            id=uuid4(),
            flag_id=sample_flag.id,
            entity_type="user",
            entity_id="user-123",
            enabled=True,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        await storage.create_override(override)

        retrieved = await storage.get_override(sample_flag.id, "user", "user-123")
        assert retrieved is None

    async def test_health_check(self, storage: MemoryStorageBackend) -> None:
        """Test health check."""
        result = await storage.health_check()
        assert result is True

    async def test_close(self, storage: MemoryStorageBackend) -> None:
        """Test closing the storage."""
        flag = FeatureFlag(
            id=uuid4(),
            key="test",
            name="Test",
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
        assert len(storage) == 1

        await storage.close()
        assert len(storage) == 0
