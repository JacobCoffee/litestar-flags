"""End-to-end integration tests for litestar-flags.

These tests validate complete user scenarios from flag creation through
evaluation, ensuring all components work together correctly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from litestar import Litestar, Request, get, post
from litestar.testing import TestClient

from litestar_flags import (
    EvaluationContext,
    FeatureFlagClient,
    FeatureFlagsConfig,
    FeatureFlagsPlugin,
)
from litestar_flags.decorators import feature_flag, require_flag
from litestar_flags.middleware import get_request_context
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.models.override import FlagOverride
from litestar_flags.models.rule import FlagRule
from litestar_flags.models.variant import FlagVariant
from litestar_flags.types import FlagStatus, FlagType


class TestFullRequestLifecycle:
    """Tests for complete request lifecycle with flag evaluation."""

    def test_create_flag_and_evaluate_in_request(self) -> None:
        """Test creating a flag and evaluating it in a subsequent request."""
        plugin = FeatureFlagsPlugin()

        @post("/flags/{flag_key:str}")
        async def create_flag_endpoint(
            feature_flags: FeatureFlagClient,
            flag_key: str,
            data: dict,
        ) -> dict:
            flag = FeatureFlag(
                id=uuid4(),
                key=flag_key,
                name=data.get("name", flag_key),
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=data.get("enabled", True),
                tags=data.get("tags", []),
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await feature_flags.storage.create_flag(flag)
            return {"created": True, "key": flag_key}

        @get("/features/{flag_key:str}")
        async def check_feature(
            feature_flags: FeatureFlagClient,
            flag_key: str,
        ) -> dict:
            enabled = await feature_flags.is_enabled(flag_key)
            details = await feature_flags.get_boolean_details(flag_key)
            return {
                "flag": flag_key,
                "enabled": enabled,
                "reason": details.reason.value,
            }

        app = Litestar(
            route_handlers=[create_flag_endpoint, check_feature],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            # First, verify flag doesn't exist
            response = client.get("/features/new-feature")
            assert response.status_code == 200
            data = response.json()
            assert data["enabled"] is False
            assert data["reason"] == "DEFAULT"

            # Create the flag
            response = client.post(
                "/flags/new-feature",
                json={"name": "New Feature", "enabled": True, "tags": ["beta"]},
            )
            assert response.status_code == 201
            assert response.json()["created"] is True

            # Now verify the flag is enabled
            response = client.get("/features/new-feature")
            assert response.status_code == 200
            data = response.json()
            assert data["enabled"] is True
            assert data["reason"] == "STATIC"

    def test_flag_affects_response_content(self) -> None:
        """Test that flag state affects the actual response content."""
        plugin = FeatureFlagsPlugin()

        @get("/pricing")
        async def pricing_endpoint(feature_flags: FeatureFlagClient) -> dict:
            new_pricing = await feature_flags.is_enabled("new-pricing")
            if new_pricing:
                return {"plan": "premium", "price": 19.99, "features": ["advanced"]}
            return {"plan": "basic", "price": 9.99, "features": ["standard"]}

        @post("/admin/flags")
        async def toggle_flag(
            feature_flags: FeatureFlagClient,
            data: dict,
        ) -> dict:
            flag = FeatureFlag(
                id=uuid4(),
                key=data["key"],
                name=data["key"],
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=data["enabled"],
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await feature_flags.storage.create_flag(flag)
            return {"toggled": True}

        app = Litestar(
            route_handlers=[pricing_endpoint, toggle_flag],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            # Without flag, get basic pricing
            response = client.get("/pricing")
            assert response.status_code == 200
            assert response.json()["plan"] == "basic"
            assert response.json()["price"] == 9.99

            # Enable new pricing flag
            client.post("/admin/flags", json={"key": "new-pricing", "enabled": True})

            # Now get premium pricing
            response = client.get("/pricing")
            assert response.status_code == 200
            assert response.json()["plan"] == "premium"
            assert response.json()["price"] == 19.99


class TestABTestingWithVariants:
    """Tests for A/B testing scenarios with variants."""

    def test_variant_distribution_for_multiple_users(self) -> None:
        """Test that variants are distributed consistently for different users."""
        plugin = FeatureFlagsPlugin()

        @get("/experiment")
        async def experiment_endpoint(
            feature_flags: FeatureFlagClient,
            user_id: str,
        ) -> dict:
            context = EvaluationContext(
                targeting_key=user_id,
                user_id=user_id,
            )
            variant = await feature_flags.get_string_value(
                "button-color-test",
                default="control",
                context=context,
            )
            details = await feature_flags.get_string_details(
                "button-color-test",
                default="control",
                context=context,
            )
            return {
                "user_id": user_id,
                "variant": variant,
                "reason": details.reason.value,
            }

        @post("/setup-experiment")
        async def setup_experiment(feature_flags: FeatureFlagClient) -> dict:
            flag_id = uuid4()
            flag = FeatureFlag(
                id=flag_id,
                key="button-color-test",
                name="Button Color A/B Test",
                flag_type=FlagType.STRING,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                default_value="control",
                tags=["experiment"],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[
                    FlagVariant(
                        id=uuid4(),
                        flag_id=flag_id,
                        key="control",
                        name="Control - Blue",
                        value="blue",
                        weight=50,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    ),
                    FlagVariant(
                        id=uuid4(),
                        flag_id=flag_id,
                        key="treatment",
                        name="Treatment - Green",
                        value="green",
                        weight=50,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    ),
                ],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await feature_flags.storage.create_flag(flag)
            return {"setup": True}

        app = Litestar(
            route_handlers=[experiment_endpoint, setup_experiment],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            # Setup the experiment
            client.post("/setup-experiment")

            # Track distribution across many users
            control_count = 0
            treatment_count = 0

            # Test with 100 different users
            for i in range(100):
                user_id = f"user-{i:04d}"
                response = client.get(f"/experiment?user_id={user_id}")
                assert response.status_code == 200

                data = response.json()
                assert data["reason"] == "SPLIT"
                assert data["variant"] in ["blue", "green"]

                if data["variant"] == "blue":
                    control_count += 1
                else:
                    treatment_count += 1

            # Verify roughly 50/50 distribution (with some tolerance)
            # Allow 20% deviation from expected 50/50 split
            assert 30 <= control_count <= 70, f"Control: {control_count}, Treatment: {treatment_count}"
            assert 30 <= treatment_count <= 70, f"Control: {control_count}, Treatment: {treatment_count}"

    def test_consistent_variant_assignment(self) -> None:
        """Test that the same user always gets the same variant."""
        plugin = FeatureFlagsPlugin()

        @get("/experiment")
        async def experiment_endpoint(
            feature_flags: FeatureFlagClient,
            user_id: str,
        ) -> dict:
            context = EvaluationContext(targeting_key=user_id, user_id=user_id)
            variant = await feature_flags.get_string_value(
                "button-color-test",
                default="control",
                context=context,
            )
            return {"user_id": user_id, "variant": variant}

        @post("/setup-experiment")
        async def setup_experiment(feature_flags: FeatureFlagClient) -> dict:
            flag_id = uuid4()
            flag = FeatureFlag(
                id=flag_id,
                key="button-color-test",
                name="Button Color A/B Test",
                flag_type=FlagType.STRING,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                default_value="control",
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
                        value="blue",
                        weight=50,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    ),
                    FlagVariant(
                        id=uuid4(),
                        flag_id=flag_id,
                        key="treatment",
                        name="Treatment",
                        value="green",
                        weight=50,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    ),
                ],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await feature_flags.storage.create_flag(flag)
            return {"setup": True}

        app = Litestar(
            route_handlers=[experiment_endpoint, setup_experiment],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            client.post("/setup-experiment")

            # Call multiple times for same user
            first_variant = None
            for _ in range(10):
                response = client.get("/experiment?user_id=consistent-user-123")
                assert response.status_code == 200

                variant = response.json()["variant"]
                if first_variant is None:
                    first_variant = variant
                else:
                    # Same user should always get same variant
                    assert variant == first_variant


class TestPercentageRollout:
    """Tests for percentage rollout functionality."""

    def test_fifty_percent_rollout(self) -> None:
        """Test that 50% rollout enables flag for approximately half of users."""
        plugin = FeatureFlagsPlugin()

        @get("/feature")
        async def feature_endpoint(
            feature_flags: FeatureFlagClient,
            user_id: str,
        ) -> dict:
            context = EvaluationContext(targeting_key=user_id, user_id=user_id)
            enabled = await feature_flags.is_enabled("gradual-rollout", context=context)
            return {"user_id": user_id, "enabled": enabled}

        @post("/setup-rollout")
        async def setup_rollout(feature_flags: FeatureFlagClient) -> dict:
            flag_id = uuid4()
            flag = FeatureFlag(
                id=flag_id,
                key="gradual-rollout",
                name="Gradual Feature Rollout",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=False,
                tags=["rollout"],
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
            await feature_flags.storage.create_flag(flag)
            return {"setup": True}

        app = Litestar(
            route_handlers=[feature_endpoint, setup_rollout],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            client.post("/setup-rollout")

            enabled_count = 0
            total_users = 200

            for i in range(total_users):
                user_id = f"rollout-user-{i:04d}"
                response = client.get(f"/feature?user_id={user_id}")
                assert response.status_code == 200

                if response.json()["enabled"]:
                    enabled_count += 1

            # Verify approximately 50% are enabled (40%-60% tolerance)
            percentage = (enabled_count / total_users) * 100
            assert 40 <= percentage <= 60, f"Got {percentage}% enabled, expected ~50%"

    def test_rollout_is_deterministic(self) -> None:
        """Test that rollout is deterministic for the same user."""
        plugin = FeatureFlagsPlugin()

        @get("/feature")
        async def feature_endpoint(
            feature_flags: FeatureFlagClient,
            user_id: str,
        ) -> dict:
            context = EvaluationContext(targeting_key=user_id, user_id=user_id)
            enabled = await feature_flags.is_enabled("deterministic-rollout", context=context)
            return {"enabled": enabled}

        @post("/setup")
        async def setup_rollout(feature_flags: FeatureFlagClient) -> dict:
            flag_id = uuid4()
            flag = FeatureFlag(
                id=flag_id,
                key="deterministic-rollout",
                name="Deterministic Rollout",
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
            await feature_flags.storage.create_flag(flag)
            return {"setup": True}

        app = Litestar(
            route_handlers=[feature_endpoint, setup_rollout],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            client.post("/setup")

            # Test multiple users multiple times
            for user_id in ["user-alpha", "user-beta", "user-gamma"]:
                first_result = None
                for _ in range(5):
                    response = client.get(f"/feature?user_id={user_id}")
                    assert response.status_code == 200

                    enabled = response.json()["enabled"]
                    if first_result is None:
                        first_result = enabled
                    else:
                        assert enabled == first_result, f"Inconsistent result for {user_id}"


class TestEntityOverrides:
    """Tests for entity-specific override functionality."""

    def test_user_override_takes_precedence(self) -> None:
        """Test that user override takes precedence over default."""
        plugin = FeatureFlagsPlugin()

        @get("/feature")
        async def feature_endpoint(
            feature_flags: FeatureFlagClient,
            user_id: str,
        ) -> dict:
            context = EvaluationContext(targeting_key=user_id, user_id=user_id)
            enabled = await feature_flags.is_enabled("override-test", context=context)
            details = await feature_flags.get_boolean_details(
                "override-test",
                context=context,
            )
            return {
                "user_id": user_id,
                "enabled": enabled,
                "reason": details.reason.value,
            }

        @post("/setup")
        async def setup_flag(feature_flags: FeatureFlagClient) -> dict:
            flag_id = uuid4()
            flag = FeatureFlag(
                id=flag_id,
                key="override-test",
                name="Override Test Flag",
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
                        entity_id="vip-user",
                        enabled=True,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    ),
                ],
                variants=[],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await feature_flags.storage.create_flag(flag)

            # Also store the override separately
            await feature_flags.storage.create_override(
                FlagOverride(
                    id=uuid4(),
                    flag_id=flag_id,
                    entity_type="user",
                    entity_id="vip-user",
                    enabled=True,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            return {"setup": True}

        app = Litestar(
            route_handlers=[feature_endpoint, setup_flag],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            client.post("/setup")

            # Regular user should get default (disabled)
            response = client.get("/feature?user_id=regular-user")
            assert response.status_code == 200
            data = response.json()
            assert data["enabled"] is False
            assert data["reason"] == "STATIC"

            # VIP user should get override (enabled)
            response = client.get("/feature?user_id=vip-user")
            assert response.status_code == 200
            data = response.json()
            assert data["enabled"] is True
            assert data["reason"] == "OVERRIDE"

    def test_override_with_rollout_rule(self) -> None:
        """Test that override takes precedence over rollout rules."""
        plugin = FeatureFlagsPlugin()

        @get("/feature")
        async def feature_endpoint(
            feature_flags: FeatureFlagClient,
            user_id: str,
        ) -> dict:
            context = EvaluationContext(targeting_key=user_id, user_id=user_id)
            enabled = await feature_flags.is_enabled("override-rollout-test", context=context)
            details = await feature_flags.get_boolean_details(
                "override-rollout-test",
                context=context,
            )
            return {
                "user_id": user_id,
                "enabled": enabled,
                "reason": details.reason.value,
            }

        @post("/setup")
        async def setup_flag(feature_flags: FeatureFlagClient) -> dict:
            flag_id = uuid4()
            flag = FeatureFlag(
                id=flag_id,
                key="override-rollout-test",
                name="Override with Rollout",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=False,
                tags=[],
                metadata_={},
                rules=[
                    FlagRule(
                        id=uuid4(),
                        flag_id=flag_id,
                        name="10% Rollout",
                        priority=0,
                        enabled=True,
                        conditions=[],
                        serve_enabled=True,
                        rollout_percentage=10,  # Very small rollout
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    ),
                ],
                overrides=[],
                variants=[],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await feature_flags.storage.create_flag(flag)

            # Create override for specific user
            await feature_flags.storage.create_override(
                FlagOverride(
                    id=uuid4(),
                    flag_id=flag_id,
                    entity_type="user",
                    entity_id="always-enabled-user",
                    enabled=True,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            return {"setup": True}

        app = Litestar(
            route_handlers=[feature_endpoint, setup_flag],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            client.post("/setup")

            # The override user should ALWAYS be enabled, regardless of rollout
            for _ in range(10):
                response = client.get("/feature?user_id=always-enabled-user")
                assert response.status_code == 200
                data = response.json()
                assert data["enabled"] is True
                assert data["reason"] == "OVERRIDE"


class TestMiddlewareContextExtraction:
    """Tests for middleware context extraction and decorator evaluation flow."""

    def test_middleware_extracts_context_for_decorator(self) -> None:
        """Test that middleware extracts context used by decorator."""
        config = FeatureFlagsConfig(
            backend="memory",
            enable_middleware=True,
        )
        plugin = FeatureFlagsPlugin(config=config)

        @get("/beta-feature")
        @feature_flag("beta-access", default=False, default_response={"error": "Not available"})
        async def beta_feature(
            request: Request,
            feature_flags: FeatureFlagClient,
        ) -> dict:
            return {"message": "Welcome to beta!", "access": True}

        @post("/setup")
        async def setup_flag(feature_flags: FeatureFlagClient) -> dict:
            flag_id = uuid4()
            flag = FeatureFlag(
                id=flag_id,
                key="beta-access",
                name="Beta Access",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=False,
                tags=["beta"],
                metadata_={},
                rules=[
                    FlagRule(
                        id=uuid4(),
                        flag_id=flag_id,
                        name="Beta Testers",
                        priority=0,
                        enabled=True,
                        conditions=[{"attribute": "beta_tester", "operator": "eq", "value": True}],
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
            await feature_flags.storage.create_flag(flag)
            return {"setup": True}

        app = Litestar(
            route_handlers=[beta_feature, setup_flag],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            client.post("/setup")

            # Without beta access, should get default response
            response = client.get("/beta-feature")
            assert response.status_code == 200
            assert response.json() == {"error": "Not available"}

    def test_context_from_request_headers(self) -> None:
        """Test that context is extracted from request headers."""
        config = FeatureFlagsConfig(
            backend="memory",
            enable_middleware=True,
        )
        plugin = FeatureFlagsPlugin(config=config)

        @get("/geo-feature")
        async def geo_feature(
            request: Request,
            feature_flags: FeatureFlagClient,
        ) -> dict:
            # Get context from middleware
            context = get_request_context(request)
            return {
                "country": context.country if context else None,
                "ip": context.ip_address if context else None,
            }

        app = Litestar(
            route_handlers=[geo_feature],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            # Test with Cloudflare country header
            response = client.get(
                "/geo-feature",
                headers={"cf-ipcountry": "US", "x-forwarded-for": "192.168.1.1"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["country"] == "US"
            assert data["ip"] == "192.168.1.1"

    def test_require_flag_decorator_with_middleware(self) -> None:
        """Test require_flag decorator with middleware context."""
        config = FeatureFlagsConfig(
            backend="memory",
            enable_middleware=True,
        )
        plugin = FeatureFlagsPlugin(config=config)

        @get("/premium-content")
        @require_flag("premium-access", error_message="Premium subscription required")
        async def premium_content(
            request: Request,
            feature_flags: FeatureFlagClient,
        ) -> dict:
            return {"content": "Premium article content", "type": "premium"}

        @post("/setup")
        async def setup_flag(feature_flags: FeatureFlagClient) -> dict:
            flag = FeatureFlag(
                id=uuid4(),
                key="premium-access",
                name="Premium Access",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=False,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await feature_flags.storage.create_flag(flag)
            return {"setup": True}

        app = Litestar(
            route_handlers=[premium_content, setup_flag],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            client.post("/setup")

            # Should be denied - flag is disabled
            response = client.get("/premium-content")
            assert response.status_code == 401


class TestPluginLifecycle:
    """Tests for plugin lifecycle (startup and shutdown)."""

    async def test_plugin_startup_initializes_client(self) -> None:
        """Test that plugin startup properly initializes the client."""
        plugin = FeatureFlagsPlugin()

        @get("/health")
        async def health_check(feature_flags: FeatureFlagClient) -> dict:
            healthy = await feature_flags.health_check()
            return {"healthy": healthy}

        app = Litestar(route_handlers=[health_check], plugins=[plugin])

        # Before lifespan, client should be None
        assert plugin.client is None

        async with app.lifespan():
            # During lifespan, client should be initialized
            assert plugin.client is not None
            assert hasattr(app.state, "feature_flags")
            assert hasattr(app.state, "feature_flags_storage")

            # Health check should work
            health = await plugin.client.health_check()
            assert health is True

        # After lifespan, client should be cleaned up
        assert plugin.client is None

    async def test_plugin_shutdown_closes_client(self) -> None:
        """Test that plugin shutdown properly closes the client."""
        plugin = FeatureFlagsPlugin()

        app = Litestar(route_handlers=[], plugins=[plugin])

        async with app.lifespan():
            client = plugin.client
            assert client is not None

            # Client should be healthy
            health = await client.health_check()
            assert health is True

        # After shutdown, the client should be closed
        health = await client.health_check()
        assert health is False

    def test_full_app_lifecycle_with_flag_operations(self) -> None:
        """Test complete app lifecycle from startup through flag operations to shutdown."""
        plugin = FeatureFlagsPlugin()

        @get("/startup-check")
        async def startup_check(feature_flags: FeatureFlagClient) -> dict:
            healthy = await feature_flags.health_check()
            return {"phase": "running", "healthy": healthy}

        @post("/flags/{key:str}")
        async def create_flag(
            feature_flags: FeatureFlagClient,
            key: str,
        ) -> dict:
            flag = FeatureFlag(
                id=uuid4(),
                key=key,
                name=key,
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
            return {"created": key}

        @get("/flags/{key:str}")
        async def get_flag_status(
            feature_flags: FeatureFlagClient,
            key: str,
        ) -> dict:
            enabled = await feature_flags.is_enabled(key)
            return {"key": key, "enabled": enabled}

        app = Litestar(
            route_handlers=[startup_check, create_flag, get_flag_status],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            # Phase 1: Verify startup
            response = client.get("/startup-check")
            assert response.status_code == 200
            assert response.json()["healthy"] is True

            # Phase 2: Create flags
            for flag_name in ["feature-a", "feature-b", "feature-c"]:
                response = client.post(f"/flags/{flag_name}")
                assert response.status_code == 201
                assert response.json()["created"] == flag_name

            # Phase 3: Verify flags work
            for flag_name in ["feature-a", "feature-b", "feature-c"]:
                response = client.get(f"/flags/{flag_name}")
                assert response.status_code == 200
                assert response.json()["enabled"] is True

        # Phase 4: After context exit, plugin should be cleaned up
        assert plugin.client is None


class TestComplexScenarios:
    """Tests for complex real-world scenarios."""

    def test_targeting_rules_with_multiple_conditions(self) -> None:
        """Test flag evaluation with complex targeting rules."""
        plugin = FeatureFlagsPlugin()

        @get("/feature")
        async def feature_endpoint(
            feature_flags: FeatureFlagClient,
            user_id: str,
            plan: str,
            country: str,
        ) -> dict:
            context = EvaluationContext(
                targeting_key=user_id,
                user_id=user_id,
                attributes={"plan": plan, "country": country},
            )
            enabled = await feature_flags.is_enabled("premium-feature", context=context)
            details = await feature_flags.get_boolean_details(
                "premium-feature",
                context=context,
            )
            return {
                "enabled": enabled,
                "reason": details.reason.value,
            }

        @post("/setup")
        async def setup_flag(feature_flags: FeatureFlagClient) -> dict:
            flag_id = uuid4()
            flag = FeatureFlag(
                id=flag_id,
                key="premium-feature",
                name="Premium Feature",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=False,
                tags=[],
                metadata_={},
                rules=[
                    # Rule: Premium US users
                    FlagRule(
                        id=uuid4(),
                        flag_id=flag_id,
                        name="Premium US Users",
                        priority=0,
                        enabled=True,
                        conditions=[
                            {"attribute": "plan", "operator": "eq", "value": "premium"},
                            {"attribute": "country", "operator": "in", "value": ["US", "CA"]},
                        ],
                        serve_enabled=True,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    ),
                    # Rule: Enterprise users (any country)
                    FlagRule(
                        id=uuid4(),
                        flag_id=flag_id,
                        name="Enterprise Users",
                        priority=1,
                        enabled=True,
                        conditions=[
                            {"attribute": "plan", "operator": "eq", "value": "enterprise"},
                        ],
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
            await feature_flags.storage.create_flag(flag)
            return {"setup": True}

        app = Litestar(
            route_handlers=[feature_endpoint, setup_flag],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            client.post("/setup")

            # Premium US user - should be enabled
            response = client.get("/feature?user_id=user1&plan=premium&country=US")
            assert response.json()["enabled"] is True
            assert response.json()["reason"] == "TARGETING_MATCH"

            # Premium UK user - should be disabled (wrong country)
            response = client.get("/feature?user_id=user2&plan=premium&country=UK")
            assert response.json()["enabled"] is False

            # Enterprise UK user - should be enabled (matches second rule)
            response = client.get("/feature?user_id=user3&plan=enterprise&country=UK")
            assert response.json()["enabled"] is True
            assert response.json()["reason"] == "TARGETING_MATCH"

            # Free US user - should be disabled
            response = client.get("/feature?user_id=user4&plan=free&country=US")
            assert response.json()["enabled"] is False

    def test_inactive_flag_returns_default(self) -> None:
        """Test that inactive flags return default value."""
        plugin = FeatureFlagsPlugin()

        @get("/feature")
        async def feature_endpoint(feature_flags: FeatureFlagClient) -> dict:
            enabled = await feature_flags.is_enabled("inactive-feature")
            details = await feature_flags.get_boolean_details("inactive-feature")
            return {
                "enabled": enabled,
                "reason": details.reason.value,
            }

        @post("/setup")
        async def setup_flag(feature_flags: FeatureFlagClient) -> dict:
            flag = FeatureFlag(
                id=uuid4(),
                key="inactive-feature",
                name="Inactive Feature",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.INACTIVE,
                default_enabled=True,  # Even though default is True
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await feature_flags.storage.create_flag(flag)
            return {"setup": True}

        app = Litestar(
            route_handlers=[feature_endpoint, setup_flag],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            client.post("/setup")

            # Inactive flag should return default value (True) but with DISABLED reason
            response = client.get("/feature")
            assert response.status_code == 200
            data = response.json()
            # When inactive, the flag returns default_enabled but reason is DISABLED
            assert data["reason"] == "DISABLED"

    def test_multiple_flag_types_in_single_request(self) -> None:
        """Test evaluating multiple flag types in a single request."""
        plugin = FeatureFlagsPlugin()

        @get("/config")
        async def config_endpoint(
            feature_flags: FeatureFlagClient,
            user_id: str,
        ) -> dict:
            ctx = EvaluationContext(targeting_key=user_id, user_id=user_id)

            # Evaluate different flag types with context
            show_banner = await feature_flags.get_boolean_value("show-banner", default=False, context=ctx)
            banner_color = await feature_flags.get_string_value("banner-color", default="blue", context=ctx)
            max_items = await feature_flags.get_number_value("max-items", default=10.0, context=ctx)
            feature_config = await feature_flags.get_object_value(
                "feature-config",
                default={"enabled": False},
                context=ctx,
            )

            return {
                "show_banner": show_banner,
                "banner_color": banner_color,
                "max_items": max_items,
                "feature_config": feature_config,
            }

        @post("/setup")
        async def setup_flags(feature_flags: FeatureFlagClient) -> dict:
            # Boolean flag
            bool_flag = FeatureFlag(
                id=uuid4(),
                key="show-banner",
                name="Show Banner",
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
                key="banner-color",
                name="Banner Color",
                flag_type=FlagType.STRING,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                default_value="green",
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            # Number flag
            number_flag = FeatureFlag(
                id=uuid4(),
                key="max-items",
                name="Max Items",
                flag_type=FlagType.NUMBER,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                default_value=25.0,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            # JSON flag
            json_flag = FeatureFlag(
                id=uuid4(),
                key="feature-config",
                name="Feature Config",
                flag_type=FlagType.JSON,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                default_value={"enabled": True, "threshold": 100, "mode": "advanced"},
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
            await feature_flags.storage.create_flag(number_flag)
            await feature_flags.storage.create_flag(json_flag)

            return {"setup": True}

        app = Litestar(
            route_handlers=[config_endpoint, setup_flags],
            plugins=[plugin],
        )

        with TestClient(app) as client:
            client.post("/setup")

            response = client.get("/config?user_id=test-user")
            assert response.status_code == 200
            data = response.json()

            assert data["show_banner"] is True
            assert data["banner_color"] == "green"
            assert data["max_items"] == 25.0
            assert data["feature_config"]["enabled"] is True
            assert data["feature_config"]["threshold"] == 100
            assert data["feature_config"]["mode"] == "advanced"
