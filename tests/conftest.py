"""Test fixtures for litestar-flags."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from litestar_flags import (
    EvaluationContext,
    FeatureFlagClient,
    FeatureFlagsConfig,
    FeatureFlagsPlugin,
    MemoryStorageBackend,
)
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.models.override import FlagOverride
from litestar_flags.models.rule import FlagRule
from litestar_flags.models.variant import FlagVariant
from litestar_flags.types import FlagStatus, FlagType

if TYPE_CHECKING:
    from litestar import Litestar
    from litestar.testing import TestClient


# -----------------------------------------------------------------------------
# pytest-asyncio Configuration
# -----------------------------------------------------------------------------
pytest_plugins = ["pytest_asyncio"]


# -----------------------------------------------------------------------------
# Storage Backend Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def storage() -> MemoryStorageBackend:
    """Create a memory storage backend."""
    return MemoryStorageBackend()


@pytest.fixture
async def client(storage: MemoryStorageBackend) -> FeatureFlagClient:
    """Create a feature flag client."""
    return FeatureFlagClient(storage=storage)


# -----------------------------------------------------------------------------
# Fakeredis Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def fake_redis():
    """Create a fake Redis client for testing.

    Requires fakeredis package.
    """
    try:
        import fakeredis.aioredis
    except ImportError:
        pytest.skip("fakeredis not installed")

    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
async def redis_storage(fake_redis) -> AsyncGenerator:
    """Create a Redis storage backend using fakeredis.

    This fixture provides a RedisStorageBackend with a fake Redis
    client for isolated testing without a real Redis server.
    """
    try:
        from litestar_flags.storage.redis import RedisStorageBackend
    except ImportError:
        pytest.skip("redis extra not installed")

    backend = RedisStorageBackend(redis=fake_redis, prefix="test:")
    yield backend
    await fake_redis.flushall()


# -----------------------------------------------------------------------------
# SQLite/aiosqlite Database Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
async def async_sqlite_engine():
    """Create an async SQLite engine for testing.

    Uses aiosqlite for async SQLite support.
    """
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
    except ImportError:
        pytest.skip("sqlalchemy[asyncio] not installed")

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(async_sqlite_engine):
    """Create a database session for testing.

    Provides an async session with automatic rollback for test isolation.
    """
    try:
        from sqlalchemy.ext.asyncio import AsyncSession
    except ImportError:
        pytest.skip("sqlalchemy[asyncio] not installed")

    async with AsyncSession(async_sqlite_engine, expire_on_commit=False) as session:
        yield session
        await session.rollback()


# -----------------------------------------------------------------------------
# Litestar Application Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def feature_flags_config() -> FeatureFlagsConfig:
    """Create a default feature flags configuration for testing."""
    return FeatureFlagsConfig(
        backend="memory",
        enable_middleware=False,
    )


@pytest.fixture
def feature_flags_plugin(feature_flags_config: FeatureFlagsConfig) -> FeatureFlagsPlugin:
    """Create a feature flags plugin for testing."""
    return FeatureFlagsPlugin(config=feature_flags_config)


@pytest.fixture
def test_app(feature_flags_plugin: FeatureFlagsPlugin) -> Litestar:
    """Create a Litestar test application with feature flags plugin.

    This fixture provides a minimal Litestar application configured
    with the feature flags plugin for integration testing.
    """
    from litestar import Litestar, get

    @get("/health")
    async def health_check() -> dict:
        return {"status": "ok"}

    @get("/flags/{flag_key:str}")
    async def get_flag_status(
        feature_flags: FeatureFlagClient,
        flag_key: str,
    ) -> dict:
        enabled = await feature_flags.is_enabled(flag_key)
        return {"flag": flag_key, "enabled": enabled}

    app = Litestar(
        route_handlers=[health_check, get_flag_status],
        plugins=[feature_flags_plugin],
        debug=True,
    )
    return app


@pytest.fixture
def test_client(test_app: Litestar) -> TestClient:
    """Create a Litestar TestClient for HTTP testing.

    This fixture provides a synchronous test client for making
    HTTP requests to the test application.
    """
    from litestar.testing import TestClient

    return TestClient(app=test_app)


@pytest.fixture
async def async_test_client(test_app: Litestar) -> AsyncGenerator:
    """Create an async HTTP client for testing.

    Uses httpx.AsyncClient for async HTTP testing with the test app.
    """
    try:
        from httpx import ASGITransport, AsyncClient
    except ImportError:
        pytest.skip("httpx not installed")

    transport = ASGITransport(app=test_app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# -----------------------------------------------------------------------------
# Feature Flag Model Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def simple_flag() -> FeatureFlag:
    """Create a simple boolean flag."""
    return FeatureFlag(
        id=uuid4(),
        key="test-flag",
        name="Test Flag",
        description="A test flag",
        flag_type=FlagType.BOOLEAN,
        status=FlagStatus.ACTIVE,
        default_enabled=False,
        tags=["test"],
        metadata_={},
        rules=[],
        overrides=[],
        variants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def enabled_flag() -> FeatureFlag:
    """Create an enabled boolean flag."""
    return FeatureFlag(
        id=uuid4(),
        key="enabled-flag",
        name="Enabled Flag",
        flag_type=FlagType.BOOLEAN,
        status=FlagStatus.ACTIVE,
        default_enabled=True,
        tags=[],
        metadata_={},
        rules=[],
        overrides=[],
        variants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def flag_with_rules() -> FeatureFlag:
    """Create a flag with targeting rules."""
    flag_id = uuid4()
    return FeatureFlag(
        id=flag_id,
        key="rules-flag",
        name="Flag with Rules",
        flag_type=FlagType.BOOLEAN,
        status=FlagStatus.ACTIVE,
        default_enabled=False,
        tags=[],
        metadata_={},
        rules=[
            FlagRule(
                id=uuid4(),
                flag_id=flag_id,
                name="Premium Users",
                priority=0,
                enabled=True,
                conditions=[{"attribute": "plan", "operator": "eq", "value": "premium"}],
                serve_enabled=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            FlagRule(
                id=uuid4(),
                flag_id=flag_id,
                name="US Users",
                priority=1,
                enabled=True,
                conditions=[{"attribute": "country", "operator": "in", "value": ["US", "CA"]}],
                serve_enabled=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ],
        overrides=[],
        variants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def flag_with_rollout() -> FeatureFlag:
    """Create a flag with percentage rollout."""
    flag_id = uuid4()
    return FeatureFlag(
        id=flag_id,
        key="rollout-flag",
        name="Rollout Flag",
        flag_type=FlagType.BOOLEAN,
        status=FlagStatus.ACTIVE,
        default_enabled=False,
        tags=[],
        metadata_={},
        rules=[
            FlagRule(
                id=uuid4(),
                flag_id=flag_id,
                name="50% Rollout",
                priority=0,
                enabled=True,
                conditions=[],
                serve_enabled=True,
                rollout_percentage=50,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ],
        overrides=[],
        variants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def flag_with_variants() -> FeatureFlag:
    """Create a flag with A/B test variants."""
    flag_id = uuid4()
    return FeatureFlag(
        id=flag_id,
        key="ab-test",
        name="A/B Test",
        flag_type=FlagType.STRING,
        status=FlagStatus.ACTIVE,
        default_enabled=True,
        default_value={"variant": "control"},
        tags=["experiment"],
        metadata_={},
        rules=[],
        overrides=[],
        variants=[
            FlagVariant(
                id=uuid4(),
                flag_id=flag_id,
                key="control",
                name="Control",
                value={"variant": "control"},
                weight=50,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            FlagVariant(
                id=uuid4(),
                flag_id=flag_id,
                key="treatment",
                name="Treatment",
                value={"variant": "treatment"},
                weight=50,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def flag_with_override() -> FeatureFlag:
    """Create a flag with a user override."""
    flag_id = uuid4()
    return FeatureFlag(
        id=flag_id,
        key="override-flag",
        name="Override Flag",
        flag_type=FlagType.BOOLEAN,
        status=FlagStatus.ACTIVE,
        default_enabled=False,
        tags=[],
        metadata_={},
        rules=[],
        overrides=[
            FlagOverride(
                id=uuid4(),
                flag_id=flag_id,
                entity_type="user",
                entity_id="user-123",
                enabled=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ],
        variants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# -----------------------------------------------------------------------------
# Evaluation Context Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def context() -> EvaluationContext:
    """Create a basic evaluation context."""
    return EvaluationContext(
        targeting_key="user-123",
        user_id="user-123",
        attributes={"plan": "free", "country": "UK"},
    )


@pytest.fixture
def premium_context() -> EvaluationContext:
    """Create a premium user context."""
    return EvaluationContext(
        targeting_key="user-456",
        user_id="user-456",
        attributes={"plan": "premium", "country": "US"},
    )


@pytest.fixture
def admin_context() -> EvaluationContext:
    """Create an admin user context."""
    return EvaluationContext(
        targeting_key="admin-001",
        user_id="admin-001",
        attributes={"plan": "enterprise", "country": "US", "role": "admin"},
    )
