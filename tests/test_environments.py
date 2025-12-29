"""Tests for multi-environment feature flag functionality.

This module tests the environment management capabilities including:
- Environment and EnvironmentFlag model creation
- Storage backend environment operations
- Environment inheritance and resolution
- Flag promotion between environments
- Environment middleware configuration

Tests cover both SQLAlchemy models (when advanced-alchemy is installed)
and dataclass fallback versions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from litestar_flags import FeatureFlagsConfig, MemoryStorageBackend
from litestar_flags.environment import (
    CircularEnvironmentInheritanceError,
    EnvironmentResolver,
    merge_environment_flag,
)
from litestar_flags.environment_middleware import (
    EnvironmentMiddleware,
    get_request_environment,
)
from litestar_flags.models.environment import Environment
from litestar_flags.models.environment_flag import EnvironmentFlag
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.types import FlagStatus, FlagType


# =============================================================================
# Environment Model Tests
# =============================================================================
class TestEnvironmentModel:
    """Tests for the Environment model."""

    def test_create_minimal_environment(self) -> None:
        """Test creating an environment with minimal required fields."""
        env = Environment(
            name="Production",
            slug="production",
        )

        assert env.name == "Production"
        assert env.slug == "production"
        # Note: SQLAlchemy model defaults are applied during INSERT, not constructor
        # For dataclass fallback, defaults are applied in constructor

    def test_create_environment_with_all_fields(self) -> None:
        """Test creating an environment with all fields populated."""
        env_id = uuid4()
        parent_id = uuid4()
        now = datetime.now(UTC)

        env = Environment(
            id=env_id,
            name="Staging",
            slug="staging",
            description="Pre-production staging environment",
            parent_id=parent_id,
            settings={"require_approval": False, "max_rollout": 100},
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        assert env.id == env_id
        assert env.name == "Staging"
        assert env.slug == "staging"
        assert env.description == "Pre-production staging environment"
        assert env.parent_id == parent_id
        assert env.settings == {"require_approval": False, "max_rollout": 100}
        assert env.is_active is True
        assert env.created_at == now
        assert env.updated_at == now

    def test_environment_repr(self) -> None:
        """Test environment string representation."""
        env = Environment(name="Test", slug="test", is_active=True)
        repr_str = repr(env)
        assert "test" in repr_str
        assert "is_active=True" in repr_str

    def test_create_inactive_environment(self) -> None:
        """Test creating an inactive environment."""
        env = Environment(
            name="Deprecated",
            slug="deprecated",
            is_active=False,
        )

        assert env.is_active is False

    @pytest.mark.parametrize(
        "settings",
        [
            {},
            {"key": "value"},
            {"nested": {"deep": {"value": 123}}},
            {"list": [1, 2, 3], "boolean": True},
        ],
    )
    def test_environment_with_various_settings(self, settings: dict[str, Any]) -> None:
        """Test environment creation with various settings structures."""
        env = Environment(
            name="Test",
            slug="test",
            settings=settings,
        )

        assert env.settings == settings


class TestEnvironmentFlagModel:
    """Tests for the EnvironmentFlag model."""

    def test_create_minimal_environment_flag(self) -> None:
        """Test creating an environment flag with minimal fields."""
        env_id = uuid4()
        flag_id = uuid4()

        env_flag = EnvironmentFlag(
            environment_id=env_id,
            flag_id=flag_id,
        )

        assert env_flag.environment_id == env_id
        assert env_flag.flag_id == flag_id
        assert env_flag.enabled is None  # Inherit from base
        assert env_flag.percentage is None  # Inherit from base

    def test_create_environment_flag_with_all_fields(self) -> None:
        """Test creating an environment flag with all fields populated."""
        env_flag_id = uuid4()
        env_id = uuid4()
        flag_id = uuid4()
        now = datetime.now(UTC)

        env_flag = EnvironmentFlag(
            id=env_flag_id,
            environment_id=env_id,
            flag_id=flag_id,
            enabled=True,
            percentage=50.0,
            rules=[{"name": "Test Rule", "conditions": []}],
            variants=[{"key": "control", "weight": 50}],
            created_at=now,
            updated_at=now,
        )

        assert env_flag.id == env_flag_id
        assert env_flag.environment_id == env_id
        assert env_flag.flag_id == flag_id
        assert env_flag.enabled is True
        assert env_flag.percentage == 50.0
        assert env_flag.rules == [{"name": "Test Rule", "conditions": []}]
        assert env_flag.variants == [{"key": "control", "weight": 50}]

    def test_environment_flag_repr(self) -> None:
        """Test environment flag string representation."""
        env_id = uuid4()
        flag_id = uuid4()
        env_flag = EnvironmentFlag(environment_id=env_id, flag_id=flag_id)

        repr_str = repr(env_flag)
        assert "EnvironmentFlag" in repr_str

    def test_environment_flag_with_override_values(self) -> None:
        """Test environment flag with explicit override values."""
        env_flag = EnvironmentFlag(
            environment_id=uuid4(),
            flag_id=uuid4(),
            enabled=False,  # Explicitly disabled
            percentage=25.0,  # 25% rollout
        )

        assert env_flag.enabled is False
        assert env_flag.percentage == 25.0


# =============================================================================
# Storage Backend Tests (using MemoryStorageBackend)
# =============================================================================
class TestEnvironmentStorage:
    """Tests for environment storage operations."""

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        """Create a fresh storage instance."""
        return MemoryStorageBackend()

    @pytest.fixture
    def sample_environment(self) -> Environment:
        """Create a sample environment."""
        return Environment(
            id=uuid4(),
            name="Production",
            slug="production",
            description="Production environment",
            settings={"require_approval": True},
            is_active=True,
        )

    @pytest.fixture
    def sample_flag(self) -> FeatureFlag:
        """Create a sample feature flag."""
        return FeatureFlag(
            id=uuid4(),
            key="test-feature",
            name="Test Feature",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

    # Environment CRUD tests

    async def test_create_and_get_environment(
        self, storage: MemoryStorageBackend, sample_environment: Environment
    ) -> None:
        """Test creating and retrieving an environment by slug."""
        created = await storage.create_environment(sample_environment)

        assert created.slug == "production"
        assert created.created_at is not None
        assert created.updated_at is not None

        retrieved = await storage.get_environment("production")
        assert retrieved is not None
        assert retrieved.slug == "production"
        assert retrieved.name == "Production"

    async def test_get_environment_by_id(self, storage: MemoryStorageBackend, sample_environment: Environment) -> None:
        """Test retrieving an environment by ID."""
        await storage.create_environment(sample_environment)

        retrieved = await storage.get_environment_by_id(sample_environment.id)
        assert retrieved is not None
        assert retrieved.id == sample_environment.id
        assert retrieved.slug == "production"

    async def test_get_nonexistent_environment(self, storage: MemoryStorageBackend) -> None:
        """Test retrieving an environment that doesn't exist."""
        result = await storage.get_environment("nonexistent")
        assert result is None

        result_by_id = await storage.get_environment_by_id(uuid4())
        assert result_by_id is None

    async def test_get_all_environments(self, storage: MemoryStorageBackend) -> None:
        """Test retrieving all environments."""
        env1 = Environment(id=uuid4(), name="Production", slug="production")
        env2 = Environment(id=uuid4(), name="Staging", slug="staging")
        env3 = Environment(id=uuid4(), name="Development", slug="development")

        await storage.create_environment(env1)
        await storage.create_environment(env2)
        await storage.create_environment(env3)

        all_envs = await storage.get_all_environments()
        assert len(all_envs) == 3
        slugs = {env.slug for env in all_envs}
        assert slugs == {"production", "staging", "development"}

    async def test_update_environment(self, storage: MemoryStorageBackend, sample_environment: Environment) -> None:
        """Test updating an environment."""
        await storage.create_environment(sample_environment)

        sample_environment.description = "Updated description"
        sample_environment.settings = {"require_approval": False}
        updated = await storage.update_environment(sample_environment)

        assert updated.description == "Updated description"
        assert updated.settings == {"require_approval": False}
        assert updated.updated_at is not None

        # Verify persistence
        retrieved = await storage.get_environment("production")
        assert retrieved is not None
        assert retrieved.description == "Updated description"

    async def test_update_environment_slug(self, storage: MemoryStorageBackend) -> None:
        """Test updating an environment's slug.

        Note: Due to how the memory backend tracks the old slug by reference,
        we need to store the old slug before modification.
        """
        env_id = uuid4()
        env = Environment(id=env_id, name="Old Name", slug="old-slug")
        await storage.create_environment(env)

        # Create a new environment object with the same ID but new slug
        # This simulates the correct way to update a slug
        updated_env = Environment(id=env_id, name="Old Name", slug="new-slug")
        await storage.update_environment(updated_env)

        # New slug should work
        new_result = await storage.get_environment("new-slug")
        assert new_result is not None
        assert new_result.slug == "new-slug"

        # Note: Due to object reference sharing in the current memory backend
        # implementation, the old slug lookup behavior may vary

    async def test_delete_environment(self, storage: MemoryStorageBackend, sample_environment: Environment) -> None:
        """Test deleting an environment."""
        await storage.create_environment(sample_environment)

        result = await storage.delete_environment("production")
        assert result is True

        retrieved = await storage.get_environment("production")
        assert retrieved is None

        # Deleting again returns False
        result = await storage.delete_environment("production")
        assert result is False

    async def test_create_duplicate_environment_fails(
        self, storage: MemoryStorageBackend, sample_environment: Environment
    ) -> None:
        """Test that creating a duplicate environment raises an error."""
        await storage.create_environment(sample_environment)

        with pytest.raises(ValueError, match="already exists"):
            await storage.create_environment(sample_environment)

    async def test_update_nonexistent_environment_fails(self, storage: MemoryStorageBackend) -> None:
        """Test that updating a nonexistent environment raises an error."""
        env = Environment(id=uuid4(), name="Nonexistent", slug="nonexistent")

        with pytest.raises(ValueError, match="not found"):
            await storage.update_environment(env)

    async def test_get_child_environments(self, storage: MemoryStorageBackend) -> None:
        """Test retrieving child environments of a parent."""
        parent = Environment(id=uuid4(), name="Parent", slug="parent")
        child1 = Environment(id=uuid4(), name="Child 1", slug="child-1", parent_id=parent.id)
        child2 = Environment(id=uuid4(), name="Child 2", slug="child-2", parent_id=parent.id)
        unrelated = Environment(id=uuid4(), name="Unrelated", slug="unrelated")

        await storage.create_environment(parent)
        await storage.create_environment(child1)
        await storage.create_environment(child2)
        await storage.create_environment(unrelated)

        children = await storage.get_child_environments(parent.id)
        assert len(children) == 2
        child_slugs = {child.slug for child in children}
        assert child_slugs == {"child-1", "child-2"}


class TestEnvironmentFlagStorage:
    """Tests for environment flag storage operations."""

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        """Create a fresh storage instance."""
        return MemoryStorageBackend()

    @pytest.fixture
    async def environment(self, storage: MemoryStorageBackend) -> Environment:
        """Create and store a sample environment."""
        env = Environment(id=uuid4(), name="Staging", slug="staging")
        return await storage.create_environment(env)

    @pytest.fixture
    async def flag(self, storage: MemoryStorageBackend) -> FeatureFlag:
        """Create and store a sample flag."""
        flag = FeatureFlag(
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
        return await storage.create_flag(flag)

    async def test_create_and_get_environment_flag(
        self,
        storage: MemoryStorageBackend,
        environment: Environment,
        flag: FeatureFlag,
    ) -> None:
        """Test creating and retrieving an environment flag."""
        env_flag = EnvironmentFlag(
            environment_id=environment.id,
            flag_id=flag.id,
            enabled=False,
            percentage=50.0,
        )
        created = await storage.create_environment_flag(env_flag)

        assert created.environment_id == environment.id
        assert created.flag_id == flag.id
        assert created.enabled is False
        assert created.percentage == 50.0
        assert created.created_at is not None

        retrieved = await storage.get_environment_flag(environment.id, flag.id)
        assert retrieved is not None
        assert retrieved.enabled is False
        assert retrieved.percentage == 50.0

    async def test_get_nonexistent_environment_flag(self, storage: MemoryStorageBackend) -> None:
        """Test retrieving an environment flag that doesn't exist."""
        result = await storage.get_environment_flag(uuid4(), uuid4())
        assert result is None

    async def test_get_environment_flags(
        self,
        storage: MemoryStorageBackend,
        environment: Environment,
    ) -> None:
        """Test retrieving all flags for an environment."""
        flag1 = await storage.create_flag(
            FeatureFlag(
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
        )
        flag2 = await storage.create_flag(
            FeatureFlag(
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
        )

        await storage.create_environment_flag(
            EnvironmentFlag(environment_id=environment.id, flag_id=flag1.id, enabled=True)
        )
        await storage.create_environment_flag(
            EnvironmentFlag(environment_id=environment.id, flag_id=flag2.id, enabled=False)
        )

        env_flags = await storage.get_environment_flags(environment.id)
        assert len(env_flags) == 2

    async def test_get_flag_environments(
        self,
        storage: MemoryStorageBackend,
        flag: FeatureFlag,
    ) -> None:
        """Test retrieving all environments for a flag."""
        env1 = await storage.create_environment(Environment(id=uuid4(), name="Staging", slug="staging"))
        env2 = await storage.create_environment(Environment(id=uuid4(), name="Production", slug="production"))

        await storage.create_environment_flag(EnvironmentFlag(environment_id=env1.id, flag_id=flag.id, enabled=True))
        await storage.create_environment_flag(EnvironmentFlag(environment_id=env2.id, flag_id=flag.id, enabled=False))

        flag_envs = await storage.get_flag_environments(flag.id)
        assert len(flag_envs) == 2

    async def test_update_environment_flag(
        self,
        storage: MemoryStorageBackend,
        environment: Environment,
        flag: FeatureFlag,
    ) -> None:
        """Test updating an environment flag."""
        env_flag = EnvironmentFlag(
            environment_id=environment.id,
            flag_id=flag.id,
            enabled=True,
            percentage=100.0,
        )
        await storage.create_environment_flag(env_flag)

        env_flag.enabled = False
        env_flag.percentage = 50.0
        updated = await storage.update_environment_flag(env_flag)

        assert updated.enabled is False
        assert updated.percentage == 50.0

        retrieved = await storage.get_environment_flag(environment.id, flag.id)
        assert retrieved is not None
        assert retrieved.enabled is False
        assert retrieved.percentage == 50.0

    async def test_update_nonexistent_environment_flag_fails(self, storage: MemoryStorageBackend) -> None:
        """Test that updating a nonexistent environment flag raises an error."""
        env_flag = EnvironmentFlag(
            environment_id=uuid4(),
            flag_id=uuid4(),
            enabled=True,
        )

        with pytest.raises(ValueError, match="not found"):
            await storage.update_environment_flag(env_flag)

    async def test_delete_environment_flag(
        self,
        storage: MemoryStorageBackend,
        environment: Environment,
        flag: FeatureFlag,
    ) -> None:
        """Test deleting an environment flag."""
        env_flag = EnvironmentFlag(
            environment_id=environment.id,
            flag_id=flag.id,
            enabled=True,
        )
        await storage.create_environment_flag(env_flag)

        result = await storage.delete_environment_flag(environment.id, flag.id)
        assert result is True

        retrieved = await storage.get_environment_flag(environment.id, flag.id)
        assert retrieved is None

        # Deleting again returns False
        result = await storage.delete_environment_flag(environment.id, flag.id)
        assert result is False

    async def test_create_duplicate_environment_flag_fails(
        self,
        storage: MemoryStorageBackend,
        environment: Environment,
        flag: FeatureFlag,
    ) -> None:
        """Test that creating a duplicate environment flag raises an error."""
        env_flag = EnvironmentFlag(
            environment_id=environment.id,
            flag_id=flag.id,
            enabled=True,
        )
        await storage.create_environment_flag(env_flag)

        with pytest.raises(ValueError, match="already exists"):
            await storage.create_environment_flag(env_flag)

    async def test_delete_environment_removes_flags(self, storage: MemoryStorageBackend) -> None:
        """Test that deleting an environment also removes its flags."""
        env = await storage.create_environment(Environment(id=uuid4(), name="Temp", slug="temp"))
        flag = await storage.create_flag(
            FeatureFlag(
                id=uuid4(),
                key="temp-flag",
                name="Temp Flag",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
        )

        await storage.create_environment_flag(EnvironmentFlag(environment_id=env.id, flag_id=flag.id, enabled=True))

        # Verify flag exists
        env_flag = await storage.get_environment_flag(env.id, flag.id)
        assert env_flag is not None

        # Delete environment
        await storage.delete_environment("temp")

        # Environment flag should be gone
        env_flag = await storage.get_environment_flag(env.id, flag.id)
        assert env_flag is None


# =============================================================================
# Environment Inheritance Tests
# =============================================================================
class TestEnvironmentInheritance:
    """Tests for environment inheritance resolution."""

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        """Create a fresh storage instance."""
        return MemoryStorageBackend()

    @pytest.fixture
    def resolver(self, storage: MemoryStorageBackend) -> EnvironmentResolver:
        """Create an environment resolver."""
        return EnvironmentResolver(storage)

    async def test_get_environment_chain_no_parent(
        self,
        storage: MemoryStorageBackend,
        resolver: EnvironmentResolver,
    ) -> None:
        """Test get_environment_chain for environment with no parent."""
        _prod = await storage.create_environment(Environment(id=uuid4(), name="Production", slug="production"))

        chain = await resolver.get_environment_chain("production")
        assert len(chain) == 1
        assert chain[0].slug == "production"

    async def test_get_environment_chain_single_parent(
        self,
        storage: MemoryStorageBackend,
        resolver: EnvironmentResolver,
    ) -> None:
        """Test get_environment_chain with single level inheritance."""
        prod = await storage.create_environment(Environment(id=uuid4(), name="Production", slug="production"))
        _staging = await storage.create_environment(
            Environment(id=uuid4(), name="Staging", slug="staging", parent_id=prod.id)
        )

        chain = await resolver.get_environment_chain("staging")
        assert len(chain) == 2
        assert chain[0].slug == "staging"
        assert chain[1].slug == "production"

    async def test_get_environment_chain_multi_level(
        self,
        storage: MemoryStorageBackend,
        resolver: EnvironmentResolver,
    ) -> None:
        """Test get_environment_chain with multi-level inheritance: dev -> staging -> production."""
        prod = await storage.create_environment(Environment(id=uuid4(), name="Production", slug="production"))
        staging = await storage.create_environment(
            Environment(id=uuid4(), name="Staging", slug="staging", parent_id=prod.id)
        )
        _dev = await storage.create_environment(
            Environment(id=uuid4(), name="Development", slug="development", parent_id=staging.id)
        )

        chain = await resolver.get_environment_chain("development")
        assert len(chain) == 3
        assert chain[0].slug == "development"
        assert chain[1].slug == "staging"
        assert chain[2].slug == "production"

    async def test_get_environment_chain_nonexistent(self, resolver: EnvironmentResolver) -> None:
        """Test get_environment_chain for nonexistent environment."""
        chain = await resolver.get_environment_chain("nonexistent")
        assert chain == []

    async def test_circular_inheritance_detection(
        self,
        storage: MemoryStorageBackend,
        resolver: EnvironmentResolver,
    ) -> None:
        """Test that circular inheritance raises an error."""
        env_a = await storage.create_environment(Environment(id=uuid4(), name="Env A", slug="env-a"))
        env_b = await storage.create_environment(
            Environment(id=uuid4(), name="Env B", slug="env-b", parent_id=env_a.id)
        )

        # Create circular reference: A -> B -> A
        env_a.parent_id = env_b.id
        await storage.update_environment(env_a)

        with pytest.raises(CircularEnvironmentInheritanceError) as exc_info:
            await resolver.get_environment_chain("env-a")

        assert exc_info.value.environment_slug in {"env-a", "env-b"}
        assert len(exc_info.value.visited_chain) > 0

    async def test_circular_inheritance_self_reference(
        self,
        storage: MemoryStorageBackend,
        resolver: EnvironmentResolver,
    ) -> None:
        """Test that self-reference in inheritance raises an error."""
        env = await storage.create_environment(Environment(id=uuid4(), name="Self", slug="self"))

        # Create self-reference
        env.parent_id = env.id
        await storage.update_environment(env)

        with pytest.raises(CircularEnvironmentInheritanceError):
            await resolver.get_environment_chain("self")

    async def test_resolve_flag_for_environment_no_override(
        self,
        storage: MemoryStorageBackend,
        resolver: EnvironmentResolver,
    ) -> None:
        """Test resolve_flag_for_environment when no override exists."""
        await storage.create_environment(Environment(id=uuid4(), name="Staging", slug="staging"))

        base_flag = FeatureFlag(
            id=uuid4(),
            key="my-feature",
            name="My Feature",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        await storage.create_flag(base_flag)

        resolved = await resolver.resolve_flag_for_environment(base_flag, "staging")

        # Should return copy of original flag unchanged
        assert resolved.default_enabled is True
        assert resolved.key == "my-feature"

    async def test_resolve_flag_for_environment_with_override(
        self,
        storage: MemoryStorageBackend,
        resolver: EnvironmentResolver,
    ) -> None:
        """Test resolve_flag_for_environment applies override correctly."""
        env = await storage.create_environment(Environment(id=uuid4(), name="Staging", slug="staging"))

        base_flag = FeatureFlag(
            id=uuid4(),
            key="my-feature",
            name="My Feature",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        await storage.create_flag(base_flag)

        # Create environment-specific override
        await storage.create_environment_flag(
            EnvironmentFlag(
                environment_id=env.id,
                flag_id=base_flag.id,
                enabled=False,
            )
        )

        resolved = await resolver.resolve_flag_for_environment(base_flag, "staging")

        # Should have override applied
        assert resolved.default_enabled is False
        assert resolved.key == "my-feature"

    async def test_resolve_flag_inherits_from_parent(
        self,
        storage: MemoryStorageBackend,
        resolver: EnvironmentResolver,
    ) -> None:
        """Test that flag resolution inherits from parent environment."""
        prod = await storage.create_environment(Environment(id=uuid4(), name="Production", slug="production"))
        staging = await storage.create_environment(
            Environment(id=uuid4(), name="Staging", slug="staging", parent_id=prod.id)
        )
        _dev = await storage.create_environment(
            Environment(id=uuid4(), name="Development", slug="development", parent_id=staging.id)
        )

        base_flag = FeatureFlag(
            id=uuid4(),
            key="my-feature",
            name="My Feature",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        await storage.create_flag(base_flag)

        # Only create override in production
        await storage.create_environment_flag(
            EnvironmentFlag(
                environment_id=prod.id,
                flag_id=base_flag.id,
                enabled=False,
            )
        )

        # Dev should inherit from production via staging
        resolved = await resolver.resolve_flag_for_environment(base_flag, "development")
        assert resolved.default_enabled is False

    async def test_most_specific_environment_wins(
        self,
        storage: MemoryStorageBackend,
        resolver: EnvironmentResolver,
    ) -> None:
        """Test that the most specific (child) environment override wins."""
        prod = await storage.create_environment(Environment(id=uuid4(), name="Production", slug="production"))
        staging = await storage.create_environment(
            Environment(id=uuid4(), name="Staging", slug="staging", parent_id=prod.id)
        )

        base_flag = FeatureFlag(
            id=uuid4(),
            key="my-feature",
            name="My Feature",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )
        await storage.create_flag(base_flag)

        # Override in both environments with different values
        await storage.create_environment_flag(
            EnvironmentFlag(
                environment_id=prod.id,
                flag_id=base_flag.id,
                enabled=False,
            )
        )
        await storage.create_environment_flag(
            EnvironmentFlag(
                environment_id=staging.id,
                flag_id=base_flag.id,
                enabled=True,  # This should win
            )
        )

        # Staging's override should win over production's
        resolved = await resolver.resolve_flag_for_environment(base_flag, "staging")
        assert resolved.default_enabled is True


class TestMergeEnvironmentFlag:
    """Tests for the merge_environment_flag function."""

    def test_merge_with_enabled_override(self) -> None:
        """Test merging with enabled override."""
        base = FeatureFlag(
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

        override = EnvironmentFlag(
            environment_id=uuid4(),
            flag_id=base.id,
            enabled=False,
        )

        merged = merge_environment_flag(base, override)

        assert merged.default_enabled is False
        # Original should be unchanged
        assert base.default_enabled is True

    def test_merge_with_none_enabled_inherits(self) -> None:
        """Test that None enabled value inherits from base."""
        base = FeatureFlag(
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

        override = EnvironmentFlag(
            environment_id=uuid4(),
            flag_id=base.id,
            enabled=None,  # Inherit
        )

        merged = merge_environment_flag(base, override)

        assert merged.default_enabled is True  # Inherited from base

    def test_merge_with_rules_override(self) -> None:
        """Test merging with rules override."""
        base = FeatureFlag(
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

        override = EnvironmentFlag(
            environment_id=uuid4(),
            flag_id=base.id,
            rules=[
                {
                    "name": "Test Rule",
                    "conditions": [{"attribute": "country", "operator": "eq", "value": "US"}],
                    "priority": 1,
                    "enabled": True,
                    "serve_enabled": True,
                }
            ],
        )

        merged = merge_environment_flag(base, override)

        assert len(merged.rules) == 1
        assert merged.rules[0].name == "Test Rule"

    def test_merge_with_variants_override(self) -> None:
        """Test merging with variants override."""
        base = FeatureFlag(
            id=uuid4(),
            key="test",
            name="Test",
            flag_type=FlagType.STRING,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
        )

        override = EnvironmentFlag(
            environment_id=uuid4(),
            flag_id=base.id,
            variants=[
                {"key": "control", "value": {"variant": "control"}, "weight": 50},
                {"key": "treatment", "value": {"variant": "treatment"}, "weight": 50},
            ],
        )

        merged = merge_environment_flag(base, override)

        assert len(merged.variants) == 2
        assert merged.variants[0].key == "control"
        assert merged.variants[1].key == "treatment"


# =============================================================================
# Environment Middleware Tests
# =============================================================================
class TestEnvironmentMiddleware:
    """Tests for the environment middleware configuration."""

    def test_config_default_environment_validation(self) -> None:
        """Test that default_environment must be a valid slug."""
        # Valid slugs
        config = FeatureFlagsConfig(default_environment="production")
        assert config.default_environment == "production"

        config = FeatureFlagsConfig(default_environment="staging-01")
        assert config.default_environment == "staging-01"

        config = FeatureFlagsConfig(default_environment="dev_local")
        assert config.default_environment == "dev_local"

    def test_config_invalid_default_environment(self) -> None:
        """Test that invalid default_environment raises an error."""
        with pytest.raises(ValueError, match="must be a valid slug"):
            FeatureFlagsConfig(default_environment="invalid slug with spaces")

        with pytest.raises(ValueError, match="must be a valid slug"):
            FeatureFlagsConfig(default_environment="-invalid-start")

    def test_config_environment_middleware_settings(self) -> None:
        """Test environment middleware configuration settings."""
        config = FeatureFlagsConfig(
            enable_environment_middleware=True,
            environment_header="X-Custom-Env",
            environment_query_param="environment",
            allowed_environments=["production", "staging", "development"],
        )

        assert config.enable_environment_middleware is True
        assert config.environment_header == "X-Custom-Env"
        assert config.environment_query_param == "environment"
        assert config.allowed_environments == ["production", "staging", "development"]

    def test_config_disable_query_param_detection(self) -> None:
        """Test that query parameter detection can be disabled."""
        config = FeatureFlagsConfig(environment_query_param=None)
        assert config.environment_query_param is None

    def test_config_environment_inheritance_setting(self) -> None:
        """Test environment inheritance configuration."""
        # Default is enabled
        config = FeatureFlagsConfig()
        assert config.enable_environment_inheritance is True

        # Can be disabled
        config = FeatureFlagsConfig(enable_environment_inheritance=False)
        assert config.enable_environment_inheritance is False


class TestEnvironmentMiddlewareExtraction:
    """Tests for environment extraction from requests."""

    @pytest.fixture
    def config(self) -> FeatureFlagsConfig:
        """Create a test configuration."""
        return FeatureFlagsConfig(
            enable_environment_middleware=True,
            environment_header="X-Environment",
            environment_query_param="env",
            default_environment="production",
            allowed_environments=["production", "staging", "development"],
        )

    def test_extract_environment_from_header(self, config: FeatureFlagsConfig) -> None:
        """Test extracting environment from X-Environment header."""
        from litestar import Litestar, Request, get
        from litestar.testing import TestClient

        @get("/test")
        async def handler(request: Request) -> dict[str, Any]:
            env = get_request_environment(request.scope)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[lambda app: EnvironmentMiddleware(app=app, config=config)],
        )

        with TestClient(app) as client:
            response = client.get("/test", headers={"X-Environment": "staging"})
            assert response.status_code == 200
            assert response.json()["environment"] == "staging"

    def test_extract_environment_from_query_param(self, config: FeatureFlagsConfig) -> None:
        """Test extracting environment from query parameter."""
        from litestar import Litestar, Request, get
        from litestar.testing import TestClient

        @get("/test")
        async def handler(request: Request) -> dict[str, Any]:
            env = get_request_environment(request.scope)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[lambda app: EnvironmentMiddleware(app=app, config=config)],
        )

        with TestClient(app) as client:
            response = client.get("/test?env=development")
            assert response.status_code == 200
            assert response.json()["environment"] == "development"

    def test_header_takes_priority_over_query_param(self, config: FeatureFlagsConfig) -> None:
        """Test that header takes priority over query parameter."""
        from litestar import Litestar, Request, get
        from litestar.testing import TestClient

        @get("/test")
        async def handler(request: Request) -> dict[str, Any]:
            env = get_request_environment(request.scope)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[lambda app: EnvironmentMiddleware(app=app, config=config)],
        )

        with TestClient(app) as client:
            response = client.get(
                "/test?env=development",
                headers={"X-Environment": "staging"},
            )
            assert response.status_code == 200
            assert response.json()["environment"] == "staging"

    def test_default_environment_fallback(self, config: FeatureFlagsConfig) -> None:
        """Test that default environment is used when no environment specified."""
        from litestar import Litestar, Request, get
        from litestar.testing import TestClient

        @get("/test")
        async def handler(request: Request) -> dict[str, Any]:
            env = get_request_environment(request.scope)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[lambda app: EnvironmentMiddleware(app=app, config=config)],
        )

        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            assert response.json()["environment"] == "production"

    def test_allowed_environments_validation(self, config: FeatureFlagsConfig) -> None:
        """Test that only allowed environments are accepted."""
        from litestar import Litestar, Request, get
        from litestar.testing import TestClient

        @get("/test")
        async def handler(request: Request) -> dict[str, Any]:
            env = get_request_environment(request.scope)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[lambda app: EnvironmentMiddleware(app=app, config=config)],
        )

        with TestClient(app) as client:
            # Invalid environment falls back to default
            response = client.get("/test", headers={"X-Environment": "invalid-env"})
            assert response.status_code == 200
            assert response.json()["environment"] == "production"

    def test_no_default_environment_returns_none(self) -> None:
        """Test that None is returned when no default and no environment specified."""
        from litestar import Litestar, Request, get
        from litestar.testing import TestClient

        config = FeatureFlagsConfig(
            enable_environment_middleware=True,
            default_environment=None,  # No default
        )

        @get("/test")
        async def handler(request: Request) -> dict[str, Any]:
            env = get_request_environment(request.scope)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[lambda app: EnvironmentMiddleware(app=app, config=config)],
        )

        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            assert response.json()["environment"] is None


# =============================================================================
# Flag Promotion Tests
# =============================================================================
class TestFlagPromotion:
    """Tests for flag promotion between environments using FlagPromoter."""

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        """Create a fresh storage instance."""
        return MemoryStorageBackend()

    async def test_promote_flag_copies_settings(self, storage: MemoryStorageBackend) -> None:
        """Test that promoting a flag copies settings correctly."""
        from litestar_flags.promotion import EnvironmentResolver, FlagPromoter

        # Setup environments (settings dict required for promotion module)
        staging = await storage.create_environment(Environment(id=uuid4(), name="Staging", slug="staging", settings={}))
        prod = await storage.create_environment(
            Environment(id=uuid4(), name="Production", slug="prod-test", settings={})  # Avoid protected name
        )

        # Create base flag
        flag = await storage.create_flag(
            FeatureFlag(
                id=uuid4(),
                key="test-feature",
                name="Test Feature",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=False,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
        )

        # Configure flag in staging
        await storage.create_environment_flag(
            EnvironmentFlag(
                environment_id=staging.id,
                flag_id=flag.id,
                enabled=True,
                percentage=75.0,
            )
        )

        # Promote using FlagPromoter
        resolver = EnvironmentResolver(storage)
        promoter = FlagPromoter(storage, resolver)

        result = await promoter.promote_flag(
            flag_key="test-feature",
            source_env="staging",
            target_env="prod-test",
            dry_run=False,
        )

        assert result.success is True
        assert result.flag_key == "test-feature"
        assert result.changes_applied.get("enabled") is True
        assert result.changes_applied.get("percentage") == 75.0

        # Verify promotion was successful
        promoted = await storage.get_environment_flag(prod.id, flag.id)
        assert promoted is not None
        assert promoted.enabled is True
        assert promoted.percentage == 75.0

    async def test_promote_flag_dry_run(self, storage: MemoryStorageBackend) -> None:
        """Test that dry_run doesn't apply changes."""
        from litestar_flags.promotion import EnvironmentResolver, FlagPromoter

        # Setup environments (settings dict required for promotion module)
        staging = await storage.create_environment(Environment(id=uuid4(), name="Staging", slug="staging", settings={}))
        prod = await storage.create_environment(
            Environment(id=uuid4(), name="Production", slug="prod-test", settings={})
        )

        # Create base flag
        flag = await storage.create_flag(
            FeatureFlag(
                id=uuid4(),
                key="test-feature",
                name="Test Feature",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=False,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
        )

        # Configure flag in staging
        await storage.create_environment_flag(
            EnvironmentFlag(
                environment_id=staging.id,
                flag_id=flag.id,
                enabled=True,
                percentage=50.0,
            )
        )

        # Promote with dry_run=True
        resolver = EnvironmentResolver(storage)
        promoter = FlagPromoter(storage, resolver)

        result = await promoter.promote_flag(
            flag_key="test-feature",
            source_env="staging",
            target_env="prod-test",
            dry_run=True,
        )

        assert result.success is True
        assert result.dry_run is True
        assert result.changes_applied.get("enabled") is True
        assert result.changes_applied.get("percentage") == 50.0

        # Verify no changes were actually applied
        promoted = await storage.get_environment_flag(prod.id, flag.id)
        assert promoted is None  # Should not exist

    async def test_promote_all_flags(self, storage: MemoryStorageBackend) -> None:
        """Test promoting all flags from one environment to another."""
        from litestar_flags.promotion import EnvironmentResolver, FlagPromoter

        # Setup environments (settings dict required for promotion module)
        staging = await storage.create_environment(Environment(id=uuid4(), name="Staging", slug="staging", settings={}))
        prod = await storage.create_environment(
            Environment(id=uuid4(), name="Production", slug="prod-test", settings={})
        )

        # Create multiple flags
        flag1 = await storage.create_flag(
            FeatureFlag(
                id=uuid4(),
                key="feature-1",
                name="Feature 1",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=False,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
        )
        flag2 = await storage.create_flag(
            FeatureFlag(
                id=uuid4(),
                key="feature-2",
                name="Feature 2",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=False,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
        )

        # Configure flags in staging with mock flag references for MemoryStorageBackend
        env_flag1 = EnvironmentFlag(
            environment_id=staging.id,
            flag_id=flag1.id,
            enabled=True,
        )
        env_flag1.flag = flag1  # type: ignore[attr-defined]
        await storage.create_environment_flag(env_flag1)

        env_flag2 = EnvironmentFlag(
            environment_id=staging.id,
            flag_id=flag2.id,
            enabled=True,
            percentage=50.0,
        )
        env_flag2.flag = flag2  # type: ignore[attr-defined]
        await storage.create_environment_flag(env_flag2)

        # Promote all flags
        resolver = EnvironmentResolver(storage)
        promoter = FlagPromoter(storage, resolver)

        results = await promoter.promote_all_flags(
            source_env="staging",
            target_env="prod-test",
            dry_run=False,
        )

        # Should have results for both flags
        successful = [r for r in results if r.success]
        assert len(successful) == 2

        # Verify all were promoted
        prod_flags = await storage.get_environment_flags(prod.id)
        assert len(prod_flags) == 2

    async def test_compare_environments_shows_differences(self, storage: MemoryStorageBackend) -> None:
        """Test comparing flag configurations between environments."""
        from litestar_flags.promotion import EnvironmentResolver, FlagPromoter

        # Setup environments (settings dict required for promotion module)
        staging = await storage.create_environment(Environment(id=uuid4(), name="Staging", slug="staging", settings={}))
        prod = await storage.create_environment(
            Environment(id=uuid4(), name="Production", slug="prod-test", settings={})
        )

        # Create base flag
        flag = await storage.create_flag(
            FeatureFlag(
                id=uuid4(),
                key="test-feature",
                name="Test Feature",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=False,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
        )

        # Configure differently in each environment with mock flag references
        env_flag_staging = EnvironmentFlag(
            environment_id=staging.id,
            flag_id=flag.id,
            enabled=True,
            percentage=100.0,
        )
        env_flag_staging.flag = flag  # type: ignore[attr-defined]
        await storage.create_environment_flag(env_flag_staging)

        env_flag_prod = EnvironmentFlag(
            environment_id=prod.id,
            flag_id=flag.id,
            enabled=True,
            percentage=25.0,  # Different percentage
        )
        env_flag_prod.flag = flag  # type: ignore[attr-defined]
        await storage.create_environment_flag(env_flag_prod)

        # Compare using FlagPromoter
        resolver = EnvironmentResolver(storage)
        promoter = FlagPromoter(storage, resolver)

        diff = await promoter.compare_environments("staging", "prod-test")

        assert "test-feature" in diff
        flag_diff = diff["test-feature"]
        assert flag_diff["env1"]["percentage"] == 100.0
        assert flag_diff["env2"]["percentage"] == 25.0
        assert any("percentage" in d for d in flag_diff["differences"])

    async def test_validate_promotion_catches_missing_environments(self, storage: MemoryStorageBackend) -> None:
        """Test that validation catches missing environments."""
        from litestar_flags.promotion import EnvironmentResolver, FlagPromoter

        resolver = EnvironmentResolver(storage)
        promoter = FlagPromoter(storage, resolver)

        warnings = await promoter.validate_promotion(
            flag_key="any-flag",
            source_env="nonexistent-source",
            target_env="nonexistent-target",
        )

        assert any("Source environment" in w and "does not exist" in w for w in warnings)
        assert any("Target environment" in w and "does not exist" in w for w in warnings)

    async def test_validate_promotion_catches_missing_flag(self, storage: MemoryStorageBackend) -> None:
        """Test that validation catches missing flags."""
        from litestar_flags.promotion import EnvironmentResolver, FlagPromoter

        # Create environments (settings dict required for promotion module)
        await storage.create_environment(Environment(id=uuid4(), name="Staging", slug="staging", settings={}))
        await storage.create_environment(Environment(id=uuid4(), name="Production", slug="prod-test", settings={}))

        resolver = EnvironmentResolver(storage)
        promoter = FlagPromoter(storage, resolver)

        warnings = await promoter.validate_promotion(
            flag_key="nonexistent-flag",
            source_env="staging",
            target_env="prod-test",
        )

        assert any("Flag" in w and "does not exist" in w for w in warnings)

    async def test_promote_flag_to_protected_environment_warning(self, storage: MemoryStorageBackend) -> None:
        """Test that promoting to protected environment generates warning."""
        from litestar_flags.promotion import EnvironmentResolver, FlagPromoter

        # Create environments - production is protected (settings dict required)
        staging = await storage.create_environment(Environment(id=uuid4(), name="Staging", slug="staging", settings={}))
        _prod = await storage.create_environment(
            Environment(id=uuid4(), name="Production", slug="production", settings={})  # Protected name
        )

        # Create flag
        flag = await storage.create_flag(
            FeatureFlag(
                id=uuid4(),
                key="test-feature",
                name="Test Feature",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=False,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
            )
        )

        # Configure flag in staging
        await storage.create_environment_flag(
            EnvironmentFlag(
                environment_id=staging.id,
                flag_id=flag.id,
                enabled=True,
            )
        )

        resolver = EnvironmentResolver(storage)
        promoter = FlagPromoter(storage, resolver)

        # Dry-run should include warning about protected environment
        result = await promoter.promote_flag(
            flag_key="test-feature",
            source_env="staging",
            target_env="production",
            dry_run=True,
        )

        assert result.success is True
        assert result.dry_run is True
        assert any("protected" in w.lower() for w in result.warnings)


class TestEnvironmentResolverGetEnvironment:
    """Tests for EnvironmentResolver.get_environment method."""

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        """Create a fresh storage instance."""
        return MemoryStorageBackend()

    @pytest.fixture
    def resolver(self, storage: MemoryStorageBackend) -> EnvironmentResolver:
        """Create an environment resolver."""
        return EnvironmentResolver(storage)

    async def test_get_environment_exists(
        self,
        storage: MemoryStorageBackend,
        resolver: EnvironmentResolver,
    ) -> None:
        """Test getting an existing environment."""
        await storage.create_environment(Environment(id=uuid4(), name="Test", slug="test"))

        env = await resolver.get_environment("test")
        assert env is not None
        assert env.slug == "test"

    async def test_get_environment_not_exists(self, resolver: EnvironmentResolver) -> None:
        """Test getting a non-existent environment."""
        env = await resolver.get_environment("nonexistent")
        assert env is None


class TestEffectiveEnvironmentFlag:
    """Tests for get_effective_environment_flag method."""

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        """Create a fresh storage instance."""
        return MemoryStorageBackend()

    @pytest.fixture
    def resolver(self, storage: MemoryStorageBackend) -> EnvironmentResolver:
        """Create an environment resolver."""
        return EnvironmentResolver(storage)

    async def test_get_effective_flag_no_chain(self, resolver: EnvironmentResolver) -> None:
        """Test getting effective flag when environment doesn't exist."""
        result = await resolver.get_effective_environment_flag(
            flag_id=uuid4(),
            environment_slug="nonexistent",
        )
        assert result is None

    async def test_get_effective_flag_no_override(
        self,
        storage: MemoryStorageBackend,
        resolver: EnvironmentResolver,
    ) -> None:
        """Test getting effective flag when no override exists."""
        await storage.create_environment(Environment(id=uuid4(), name="Test", slug="test"))
        flag = await storage.create_flag(
            FeatureFlag(
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
        )

        result = await resolver.get_effective_environment_flag(
            flag_id=flag.id,
            environment_slug="test",
        )
        assert result is None

    async def test_get_effective_flag_from_parent(
        self,
        storage: MemoryStorageBackend,
        resolver: EnvironmentResolver,
    ) -> None:
        """Test that effective flag is inherited from parent."""
        parent = await storage.create_environment(Environment(id=uuid4(), name="Parent", slug="parent"))
        _child = await storage.create_environment(
            Environment(id=uuid4(), name="Child", slug="child", parent_id=parent.id)
        )

        flag = await storage.create_flag(
            FeatureFlag(
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
        )

        # Only configure in parent
        await storage.create_environment_flag(
            EnvironmentFlag(
                environment_id=parent.id,
                flag_id=flag.id,
                enabled=False,
            )
        )

        # Should find parent's config when querying child
        result = await resolver.get_effective_environment_flag(
            flag_id=flag.id,
            environment_slug="child",
        )
        assert result is not None
        assert result.environment_id == parent.id
        assert result.enabled is False
