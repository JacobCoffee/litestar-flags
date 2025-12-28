"""Tests for FeatureFlagsPlugin integration with Litestar."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from litestar import Litestar, get
from litestar.testing import TestClient

from litestar_flags import (
    EvaluationContext,
    FeatureFlagClient,
    FeatureFlagsConfig,
    FeatureFlagsPlugin,
    MemoryStorageBackend,
)
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.types import FlagStatus, FlagType


class TestPluginLifecycle:
    """Tests for plugin lifecycle (startup/shutdown)."""

    async def test_plugin_initialization_with_default_config(self) -> None:
        """Test plugin initializes with default configuration."""
        plugin = FeatureFlagsPlugin()

        assert plugin.config is not None
        assert plugin.config.backend == "memory"
        assert plugin.client is None  # Not initialized until startup

    async def test_plugin_initialization_with_custom_config(self) -> None:
        """Test plugin initializes with custom configuration."""
        config = FeatureFlagsConfig(
            backend="memory",
            client_dependency_key="custom_flags",
        )
        plugin = FeatureFlagsPlugin(config=config)

        assert plugin.config.client_dependency_key == "custom_flags"
        assert plugin.config.backend == "memory"

    async def test_plugin_startup_creates_client(self) -> None:
        """Test that plugin startup creates and registers the client."""
        plugin = FeatureFlagsPlugin()

        app = Litestar(route_handlers=[], plugins=[plugin])

        async with app.lifespan():
            assert plugin.client is not None
            assert isinstance(plugin.client, FeatureFlagClient)
            assert hasattr(app.state, "feature_flags")
            assert app.state.feature_flags is plugin.client

    async def test_plugin_shutdown_cleans_up_client(self) -> None:
        """Test that plugin shutdown properly cleans up resources."""
        plugin = FeatureFlagsPlugin()

        app = Litestar(route_handlers=[], plugins=[plugin])

        async with app.lifespan():
            assert plugin.client is not None
            client = plugin.client

        # After lifespan exits, client should be cleaned up
        assert plugin.client is None
        # Verify the client was closed (health_check returns False when closed)
        health = await client.health_check()
        assert health is False

    async def test_plugin_registers_storage_in_app_state(self) -> None:
        """Test that plugin registers storage backend in app state."""
        plugin = FeatureFlagsPlugin()

        app = Litestar(route_handlers=[], plugins=[plugin])

        async with app.lifespan():
            assert hasattr(app.state, "feature_flags_storage")
            assert isinstance(app.state.feature_flags_storage, MemoryStorageBackend)


class TestDependencyInjection:
    """Tests for FeatureFlagClient dependency injection."""

    def test_client_injection_into_route_handler(self) -> None:
        """Test that FeatureFlagClient is injected into route handlers."""

        @get("/check")
        async def check_flag(feature_flags: FeatureFlagClient) -> dict:
            enabled = await feature_flags.is_enabled("test-flag")
            return {"enabled": enabled}

        plugin = FeatureFlagsPlugin()
        app = Litestar(route_handlers=[check_flag], plugins=[plugin])

        with TestClient(app) as client:
            response = client.get("/check")
            assert response.status_code == 200
            assert response.json() == {"enabled": False}

    def test_client_injection_with_custom_dependency_key(self) -> None:
        """Test client injection with custom dependency key."""
        config = FeatureFlagsConfig(client_dependency_key="flags")

        @get("/check")
        async def check_flag(flags: FeatureFlagClient) -> dict:
            enabled = await flags.is_enabled("test-flag")
            return {"enabled": enabled}

        plugin = FeatureFlagsPlugin(config=config)
        app = Litestar(route_handlers=[check_flag], plugins=[plugin])

        with TestClient(app) as client:
            response = client.get("/check")
            assert response.status_code == 200

    def test_client_from_app_state(self) -> None:
        """Test getting client directly from app state."""

        @get("/check")
        async def check_flag(feature_flags: FeatureFlagClient) -> dict:
            return {"has_client": feature_flags is not None}

        plugin = FeatureFlagsPlugin()
        app = Litestar(route_handlers=[check_flag], plugins=[plugin])

        with TestClient(app) as client:
            response = client.get("/check")
            assert response.status_code == 200
            assert response.json()["has_client"] is True


class TestPluginConfiguration:
    """Tests for plugin configuration options."""

    def test_plugin_with_memory_backend_default(self) -> None:
        """Test plugin with default memory backend."""
        plugin = FeatureFlagsPlugin()

        assert plugin.config.backend == "memory"

    def test_plugin_with_explicit_memory_backend(self) -> None:
        """Test plugin with explicitly configured memory backend."""
        config = FeatureFlagsConfig(backend="memory")
        plugin = FeatureFlagsPlugin(config=config)

        app = Litestar(route_handlers=[], plugins=[plugin])

        with TestClient(app):
            assert plugin.client is not None
            assert isinstance(plugin.client.storage, MemoryStorageBackend)

    def test_database_backend_requires_connection_string(self) -> None:
        """Test that database backend requires connection_string."""
        with pytest.raises(ValueError, match="connection_string is required"):
            FeatureFlagsConfig(backend="database")

    def test_redis_backend_requires_redis_url(self) -> None:
        """Test that redis backend requires redis_url."""
        with pytest.raises(ValueError, match="redis_url is required"):
            FeatureFlagsConfig(backend="redis")

    def test_custom_table_prefix(self) -> None:
        """Test custom table prefix configuration."""
        config = FeatureFlagsConfig(
            backend="database",
            connection_string="sqlite+aiosqlite:///:memory:",
            table_prefix="custom_",
        )
        assert config.table_prefix == "custom_"

    def test_custom_redis_prefix(self) -> None:
        """Test custom redis prefix configuration."""
        config = FeatureFlagsConfig(
            backend="redis",
            redis_url="redis://localhost:6379",
            redis_prefix="custom:",
        )
        assert config.redis_prefix == "custom:"

    async def test_unknown_backend_raises_error(self) -> None:
        """Test that unknown backend type raises ValueError."""
        config = FeatureFlagsConfig.__new__(FeatureFlagsConfig)
        config.backend = "unknown"  # type: ignore[assignment]
        config.connection_string = None
        config.redis_url = None
        config.table_prefix = "ff_"
        config.redis_prefix = "feature_flags:"
        config.default_context = None
        config.enable_middleware = False
        config.context_extractor = None
        config.client_dependency_key = "feature_flags"
        config.extra = {}

        plugin = FeatureFlagsPlugin(config=config)

        with pytest.raises(ValueError, match="Unknown backend"):
            await plugin._create_storage()


class TestLitestarIntegration:
    """Integration tests with Litestar application."""

    def test_flag_evaluation_in_request_context(self) -> None:
        """Test flag evaluation works in request context."""

        @get("/feature/{flag_key:str}")
        async def check_feature(
            feature_flags: FeatureFlagClient,
            flag_key: str,
        ) -> dict:
            enabled = await feature_flags.is_enabled(flag_key)
            return {"flag": flag_key, "enabled": enabled}

        plugin = FeatureFlagsPlugin()
        app = Litestar(route_handlers=[check_feature], plugins=[plugin])

        with TestClient(app) as client:
            response = client.get("/feature/my-flag")
            assert response.status_code == 200
            data = response.json()
            assert data["flag"] == "my-flag"
            assert data["enabled"] is False  # Default for non-existent flag

    def test_flag_evaluation_with_context(self) -> None:
        """Test flag evaluation with evaluation context."""

        @get("/feature/{flag_key:str}")
        async def check_feature(
            feature_flags: FeatureFlagClient,
            flag_key: str,
            user_id: str,
        ) -> dict:
            context = EvaluationContext(
                targeting_key=user_id,
                user_id=user_id,
            )
            enabled = await feature_flags.is_enabled(flag_key, context=context)
            return {"flag": flag_key, "user": user_id, "enabled": enabled}

        plugin = FeatureFlagsPlugin()
        app = Litestar(route_handlers=[check_feature], plugins=[plugin])

        with TestClient(app) as client:
            response = client.get("/feature/my-flag?user_id=user-123")
            assert response.status_code == 200
            data = response.json()
            assert data["user"] == "user-123"

    def test_flag_creation_and_evaluation(self) -> None:
        """Test creating and evaluating flags through the plugin."""
        plugin = FeatureFlagsPlugin()

        @get("/create-flag")
        async def create_flag(feature_flags: FeatureFlagClient) -> dict:
            flag = FeatureFlag(
                id=uuid4(),
                key="new-feature",
                name="New Feature",
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
            await feature_flags.storage.create_flag(flag)
            return {"created": True}

        @get("/check-flag")
        async def check_flag(feature_flags: FeatureFlagClient) -> dict:
            enabled = await feature_flags.is_enabled("new-feature")
            return {"enabled": enabled}

        app = Litestar(
            route_handlers=[create_flag, check_flag],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            # Create the flag
            response = client.get("/create-flag")
            assert response.status_code == 200
            assert response.json()["created"] is True

            # Check the flag
            response = client.get("/check-flag")
            assert response.status_code == 200
            assert response.json()["enabled"] is True

    def test_multiple_flag_types(self) -> None:
        """Test different flag value types."""
        plugin = FeatureFlagsPlugin()

        @get("/setup")
        async def setup_flags(feature_flags: FeatureFlagClient) -> dict:
            # Boolean flag
            bool_flag = FeatureFlag(
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
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            # String flag
            string_flag = FeatureFlag(
                id=uuid4(),
                key="string-flag",
                name="String Flag",
                flag_type=FlagType.STRING,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                default_value="variant-a",
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            await feature_flags.storage.create_flag(bool_flag)
            await feature_flags.storage.create_flag(string_flag)
            return {"setup": True}

        @get("/evaluate")
        async def evaluate_flags(feature_flags: FeatureFlagClient) -> dict:
            bool_val = await feature_flags.get_boolean_value("bool-flag")
            string_val = await feature_flags.get_string_value("string-flag")
            return {"bool": bool_val, "string": string_val}

        app = Litestar(
            route_handlers=[setup_flags, evaluate_flags],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            client.get("/setup")
            response = client.get("/evaluate")
            assert response.status_code == 200
            data = response.json()
            assert data["bool"] is True
            assert data["string"] == "variant-a"

    def test_get_all_flags_endpoint(self) -> None:
        """Test getting all flags through an endpoint."""
        plugin = FeatureFlagsPlugin()

        @get("/setup")
        async def setup_flags(feature_flags: FeatureFlagClient) -> dict:
            for i in range(3):
                flag = FeatureFlag(
                    id=uuid4(),
                    key=f"flag-{i}",
                    name=f"Flag {i}",
                    flag_type=FlagType.BOOLEAN,
                    status=FlagStatus.ACTIVE,
                    default_enabled=i % 2 == 0,
                    tags=[],
                    metadata_={},
                    rules=[],
                    overrides=[],
                    variants=[],
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                await feature_flags.storage.create_flag(flag)
            return {"count": 3}

        @get("/all-flags")
        async def get_all_flags(feature_flags: FeatureFlagClient) -> dict:
            flags = await feature_flags.get_all_flags()
            return {"flags": {k: v.value for k, v in flags.items()}}

        app = Litestar(
            route_handlers=[setup_flags, get_all_flags],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            client.get("/setup")
            response = client.get("/all-flags")
            assert response.status_code == 200
            data = response.json()
            assert len(data["flags"]) == 3
            assert data["flags"]["flag-0"] is True
            assert data["flags"]["flag-1"] is False
            assert data["flags"]["flag-2"] is True

    def test_health_check_endpoint(self) -> None:
        """Test health check through an endpoint."""
        plugin = FeatureFlagsPlugin()

        @get("/health")
        async def health_check(feature_flags: FeatureFlagClient) -> dict:
            healthy = await feature_flags.health_check()
            return {"healthy": healthy}

        app = Litestar(route_handlers=[health_check], plugins=[plugin])

        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json()["healthy"] is True


class TestDefaultContext:
    """Tests for default evaluation context configuration."""

    def test_plugin_with_default_context(self) -> None:
        """Test plugin with default evaluation context."""
        default_ctx = EvaluationContext(
            targeting_key="default-user",
            attributes={"environment": "test"},
        )
        config = FeatureFlagsConfig(
            backend="memory",
            default_context=default_ctx,
        )
        plugin = FeatureFlagsPlugin(config=config)

        assert plugin.config.default_context is not None
        assert plugin.config.default_context.targeting_key == "default-user"

    def test_default_context_used_in_evaluation(self) -> None:
        """Test that default context is used when no context provided."""
        default_ctx = EvaluationContext(
            targeting_key="default-user",
            attributes={"plan": "premium"},
        )
        config = FeatureFlagsConfig(
            backend="memory",
            default_context=default_ctx,
        )
        plugin = FeatureFlagsPlugin(config=config)

        @get("/check")
        async def check_flag(feature_flags: FeatureFlagClient) -> dict:
            # No context provided - should use default
            enabled = await feature_flags.is_enabled("premium-feature")
            return {"enabled": enabled}

        app = Litestar(route_handlers=[check_flag], plugins=[plugin])

        with TestClient(app) as client:
            response = client.get("/check")
            assert response.status_code == 200


class TestMultiplePluginInstances:
    """Tests for using multiple plugin configurations."""

    async def test_plugin_config_property(self) -> None:
        """Test that plugin config is accessible via property."""
        config = FeatureFlagsConfig(
            backend="memory",
            client_dependency_key="my_flags",
        )
        plugin = FeatureFlagsPlugin(config=config)

        assert plugin.config == config
        assert plugin.config.client_dependency_key == "my_flags"


class TestErrorHandling:
    """Tests for error handling in plugin operations."""

    def test_client_graceful_degradation(self) -> None:
        """Test that client returns defaults on errors."""
        plugin = FeatureFlagsPlugin()

        @get("/check")
        async def check_flag(feature_flags: FeatureFlagClient) -> dict:
            # Non-existent flag returns default
            enabled = await feature_flags.get_boolean_value(
                "nonexistent",
                default=True,
            )
            return {"enabled": enabled}

        app = Litestar(route_handlers=[check_flag], plugins=[plugin])

        with TestClient(app) as client:
            response = client.get("/check")
            assert response.status_code == 200
            assert response.json()["enabled"] is True

    def test_evaluation_details_with_error(self) -> None:
        """Test getting evaluation details when flag not found."""
        plugin = FeatureFlagsPlugin()

        @get("/details")
        async def get_details(feature_flags: FeatureFlagClient) -> dict:
            details = await feature_flags.get_boolean_details(
                "nonexistent",
                default=False,
            )
            return {
                "value": details.value,
                "reason": details.reason.value,
                "error_code": details.error_code.value if details.error_code else None,
            }

        app = Litestar(route_handlers=[get_details], plugins=[plugin])

        with TestClient(app) as client:
            response = client.get("/details")
            assert response.status_code == 200
            data = response.json()
            assert data["value"] is False
            assert data["reason"] == "DEFAULT"
            assert data["error_code"] == "FLAG_NOT_FOUND"
