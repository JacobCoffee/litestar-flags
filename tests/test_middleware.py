"""Tests for FeatureFlagsMiddleware."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from litestar import Litestar, Request, get
from litestar.testing import TestClient

from litestar_flags.context import EvaluationContext
from litestar_flags.middleware import (
    EnvironmentMiddleware,
    FeatureFlagsMiddleware,
    create_context_middleware,
    create_environment_middleware,
    get_request_context,
    get_request_environment,
)


class TestContextExtractionFromHeaders:
    """Tests for context extraction from request headers."""

    def test_extract_ip_from_x_forwarded_for(self) -> None:
        """Test extracting IP address from X-Forwarded-For header."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            return {"ip": context.ip_address if context else None}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware()],
        )

        with TestClient(app) as client:
            response = client.get(
                "/test",
                headers={"X-Forwarded-For": "203.0.113.195, 70.41.3.18, 150.172.238.178"},
            )
            assert response.status_code == 200
            assert response.json()["ip"] == "203.0.113.195"

    def test_extract_ip_from_x_real_ip(self) -> None:
        """Test extracting IP address from X-Real-IP header."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            return {"ip": context.ip_address if context else None}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware()],
        )

        with TestClient(app) as client:
            response = client.get("/test", headers={"X-Real-IP": "192.168.1.1"})
            assert response.status_code == 200
            assert response.json()["ip"] == "192.168.1.1"

    def test_extract_user_agent(self) -> None:
        """Test extracting user agent from headers."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            return {"user_agent": context.user_agent if context else None}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware()],
        )

        with TestClient(app) as client:
            response = client.get(
                "/test",
                headers={"User-Agent": "Mozilla/5.0 (Test Browser)"},
            )
            assert response.status_code == 200
            assert response.json()["user_agent"] == "Mozilla/5.0 (Test Browser)"

    def test_extract_country_from_cloudflare(self) -> None:
        """Test extracting country from Cloudflare CF-IPCountry header."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            return {"country": context.country if context else None}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware()],
        )

        with TestClient(app) as client:
            response = client.get("/test", headers={"CF-IPCountry": "US"})
            assert response.status_code == 200
            assert response.json()["country"] == "US"

    def test_extract_country_from_x_country_code(self) -> None:
        """Test extracting country from X-Country-Code header."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            return {"country": context.country if context else None}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware()],
        )

        with TestClient(app) as client:
            response = client.get("/test", headers={"X-Country-Code": "GB"})
            assert response.status_code == 200
            assert response.json()["country"] == "GB"

    def test_extract_country_from_vercel(self) -> None:
        """Test extracting country from Vercel X-Vercel-IP-Country header."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            return {"country": context.country if context else None}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware()],
        )

        with TestClient(app) as client:
            response = client.get("/test", headers={"X-Vercel-IP-Country": "CA"})
            assert response.status_code == 200
            assert response.json()["country"] == "CA"

    def test_country_header_priority(self) -> None:
        """Test that Cloudflare header takes priority over others."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            return {"country": context.country if context else None}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware()],
        )

        with TestClient(app) as client:
            response = client.get(
                "/test",
                headers={
                    "CF-IPCountry": "US",
                    "X-Country-Code": "GB",
                    "X-Vercel-IP-Country": "CA",
                },
            )
            assert response.status_code == 200
            assert response.json()["country"] == "US"


class TestContextInjection:
    """Tests for context injection into request scope."""

    def test_context_available_in_scope(self) -> None:
        """Test that context is injected into request scope."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            return {
                "has_context": context is not None,
                "context_type": type(context).__name__ if context else None,
            }

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware()],
        )

        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            data = response.json()
            assert data["has_context"] is True
            assert data["context_type"] == "EvaluationContext"

    def test_context_available_in_route_handler(self) -> None:
        """Test that context data is accessible in route handlers."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            if context:
                return {
                    "ip": context.ip_address,
                    "user_agent": context.user_agent,
                    "country": context.country,
                }
            return {}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware()],
        )

        with TestClient(app) as client:
            response = client.get(
                "/test",
                headers={
                    "X-Forwarded-For": "10.0.0.1",
                    "User-Agent": "TestClient",
                    "CF-IPCountry": "DE",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["ip"] == "10.0.0.1"
            assert data["user_agent"] == "TestClient"
            assert data["country"] == "DE"

    def test_no_context_without_middleware(self) -> None:
        """Test that no context is available without middleware."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            return {"has_context": context is not None}

        app = Litestar(route_handlers=[handler])

        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            assert response.json()["has_context"] is False


class TestCustomContextExtractor:
    """Tests for custom context extractor functionality."""

    def test_custom_extractor_is_used(self) -> None:
        """Test that custom context extractor is called."""

        def custom_extractor(request: Request[Any, Any, Any]) -> EvaluationContext:
            return EvaluationContext(
                targeting_key="custom-key-123",
                user_id="custom-user",
                attributes={"source": "custom"},
            )

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            if context:
                return {
                    "targeting_key": context.targeting_key,
                    "user_id": context.user_id,
                    "source": context.get("source"),
                }
            return {}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware(context_extractor=custom_extractor)],
        )

        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            data = response.json()
            assert data["targeting_key"] == "custom-key-123"
            assert data["user_id"] == "custom-user"
            assert data["source"] == "custom"

    def test_custom_extractor_with_headers(self) -> None:
        """Test custom extractor can read custom headers."""

        def custom_extractor(request: Request[Any, Any, Any]) -> EvaluationContext:
            user_id = request.headers.get("X-User-ID")
            org_id = request.headers.get("X-Org-ID")
            return EvaluationContext(
                targeting_key=user_id,
                user_id=user_id,
                organization_id=org_id,
            )

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            if context:
                return {
                    "user_id": context.user_id,
                    "org_id": context.organization_id,
                }
            return {}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware(context_extractor=custom_extractor)],
        )

        with TestClient(app) as client:
            response = client.get(
                "/test",
                headers={"X-User-ID": "user-abc", "X-Org-ID": "org-xyz"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == "user-abc"
            assert data["org_id"] == "org-xyz"

    def test_custom_extractor_with_query_params(self) -> None:
        """Test custom extractor can read query parameters."""

        def custom_extractor(request: Request[Any, Any, Any]) -> EvaluationContext:
            tenant = request.query_params.get("tenant")
            env = request.query_params.get("env", "production")
            return EvaluationContext(
                tenant_id=tenant,
                environment=env,
            )

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            if context:
                return {
                    "tenant_id": context.tenant_id,
                    "environment": context.environment,
                }
            return {}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware(context_extractor=custom_extractor)],
        )

        with TestClient(app) as client:
            response = client.get("/test?tenant=acme&env=staging")
            assert response.status_code == 200
            data = response.json()
            assert data["tenant_id"] == "acme"
            assert data["environment"] == "staging"

    def test_custom_extractor_with_attributes(self) -> None:
        """Test custom extractor can set custom attributes."""

        def custom_extractor(request: Request[Any, Any, Any]) -> EvaluationContext:
            plan = request.headers.get("X-Plan", "free")
            beta = request.headers.get("X-Beta", "false").lower() == "true"
            return EvaluationContext(
                attributes={
                    "plan": plan,
                    "beta_tester": beta,
                    "request_path": str(request.url.path),
                },
            )

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            if context:
                return {
                    "plan": context.get("plan"),
                    "beta_tester": context.get("beta_tester"),
                    "request_path": context.get("request_path"),
                }
            return {}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware(context_extractor=custom_extractor)],
        )

        with TestClient(app) as client:
            response = client.get(
                "/test",
                headers={"X-Plan": "premium", "X-Beta": "true"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["plan"] == "premium"
            assert data["beta_tester"] is True
            assert data["request_path"] == "/test"


class TestMiddlewareClass:
    """Tests for FeatureFlagsMiddleware class directly."""

    def test_middleware_initialization_default_extractor(self) -> None:
        """Test middleware initializes with default extractor."""
        mock_app = MagicMock()
        middleware = FeatureFlagsMiddleware(app=mock_app)

        assert middleware.app is mock_app
        assert middleware._context_extractor is not None

    def test_middleware_initialization_custom_extractor(self) -> None:
        """Test middleware initializes with custom extractor."""

        def custom_extractor(request: Request[Any, Any, Any]) -> EvaluationContext:
            return EvaluationContext()

        mock_app = MagicMock()
        middleware = FeatureFlagsMiddleware(app=mock_app, context_extractor=custom_extractor)

        assert middleware._context_extractor is custom_extractor

    def test_middleware_only_processes_http_requests(self) -> None:
        """Test middleware only processes HTTP scope types."""
        captured_context = []

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            captured_context.append(context)
            return {"has_context": context is not None}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware()],
        )

        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            assert response.json()["has_context"] is True
            assert len(captured_context) == 1
            assert isinstance(captured_context[0], EvaluationContext)


class TestCreateContextMiddleware:
    """Tests for create_context_middleware factory function."""

    def test_create_middleware_without_extractor(self) -> None:
        """Test creating middleware without custom extractor."""
        middleware_def = create_context_middleware()

        assert middleware_def is not None
        assert middleware_def.middleware is FeatureFlagsMiddleware

    def test_create_middleware_with_extractor(self) -> None:
        """Test creating middleware with custom extractor."""

        def custom_extractor(request: Request[Any, Any, Any]) -> EvaluationContext:
            return EvaluationContext()

        middleware_def = create_context_middleware(context_extractor=custom_extractor)

        assert middleware_def is not None
        assert middleware_def.middleware is FeatureFlagsMiddleware
        assert middleware_def.kwargs.get("context_extractor") is custom_extractor


class TestGetRequestContext:
    """Tests for get_request_context helper function."""

    def test_get_context_returns_context(self) -> None:
        """Test getting context from request with middleware."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            return {"context_exists": context is not None}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware()],
        )

        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            assert response.json()["context_exists"] is True

    def test_get_context_returns_none_without_middleware(self) -> None:
        """Test getting context from request without middleware."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            return {"context_exists": context is not None}

        app = Litestar(route_handlers=[handler])

        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            assert response.json()["context_exists"] is False


class TestDefaultExtractor:
    """Tests for the default context extraction behavior."""

    def test_default_extractor_empty_headers(self) -> None:
        """Test default extractor with minimal headers."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            if context:
                return {
                    "ip": context.ip_address,
                    "user_agent": context.user_agent,
                    "country": context.country,
                    "user_id": context.user_id,
                }
            return {}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware()],
        )

        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            data = response.json()
            # Should have some values (client IP, user agent from test client)
            assert data["country"] is None
            assert data["user_id"] is None

    def test_default_extractor_x_forwarded_for_priority(self) -> None:
        """Test X-Forwarded-For takes priority over X-Real-IP."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            return {"ip": context.ip_address if context else None}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware()],
        )

        with TestClient(app) as client:
            response = client.get(
                "/test",
                headers={
                    "X-Forwarded-For": "1.1.1.1",
                    "X-Real-IP": "2.2.2.2",
                },
            )
            assert response.status_code == 200
            assert response.json()["ip"] == "1.1.1.1"

    def test_default_extractor_strips_x_forwarded_for(self) -> None:
        """Test X-Forwarded-For values are properly stripped of whitespace."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            return {"ip": context.ip_address if context else None}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_context_middleware()],
        )

        with TestClient(app) as client:
            response = client.get(
                "/test",
                headers={"X-Forwarded-For": "  1.1.1.1  , 2.2.2.2"},
            )
            assert response.status_code == 200
            assert response.json()["ip"] == "1.1.1.1"


class TestEnvironmentMiddlewareFromHeader:
    """Tests for environment extraction from request headers."""

    def test_extract_environment_from_header(self) -> None:
        """Test extracting environment from X-Environment header."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            env = get_request_environment(request)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_environment_middleware()],
        )

        with TestClient(app) as client:
            response = client.get("/test", headers={"X-Environment": "staging"})
            assert response.status_code == 200
            assert response.json()["environment"] == "staging"

    def test_extract_environment_from_custom_header(self) -> None:
        """Test extracting environment from custom header."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            env = get_request_environment(request)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_environment_middleware(environment_header="X-App-Environment")],
        )

        with TestClient(app) as client:
            response = client.get("/test", headers={"X-App-Environment": "production"})
            assert response.status_code == 200
            assert response.json()["environment"] == "production"


class TestEnvironmentMiddlewareFromQueryParam:
    """Tests for environment extraction from query parameters."""

    def test_extract_environment_from_query_param(self) -> None:
        """Test extracting environment from query parameter."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            env = get_request_environment(request)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_environment_middleware()],
        )

        with TestClient(app) as client:
            response = client.get("/test?env=development")
            assert response.status_code == 200
            assert response.json()["environment"] == "development"

    def test_extract_environment_from_custom_query_param(self) -> None:
        """Test extracting environment from custom query parameter."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            env = get_request_environment(request)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_environment_middleware(environment_query_param="environment")],
        )

        with TestClient(app) as client:
            response = client.get("/test?environment=staging")
            assert response.status_code == 200
            assert response.json()["environment"] == "staging"

    def test_query_param_disabled(self) -> None:
        """Test that query param extraction can be disabled."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            env = get_request_environment(request)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_environment_middleware(environment_query_param=None)],
        )

        with TestClient(app) as client:
            response = client.get("/test?env=staging")
            assert response.status_code == 200
            assert response.json()["environment"] is None


class TestEnvironmentMiddlewarePriority:
    """Tests for environment source priority."""

    def test_header_takes_priority_over_query_param(self) -> None:
        """Test that header takes priority over query parameter."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            env = get_request_environment(request)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_environment_middleware()],
        )

        with TestClient(app) as client:
            response = client.get(
                "/test?env=development",
                headers={"X-Environment": "production"},
            )
            assert response.status_code == 200
            assert response.json()["environment"] == "production"


class TestEnvironmentMiddlewareDefault:
    """Tests for default environment fallback."""

    def test_fallback_to_default_environment(self) -> None:
        """Test fallback to default environment when none specified."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            env = get_request_environment(request)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_environment_middleware(default_environment="production")],
        )

        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            assert response.json()["environment"] == "production"

    def test_no_default_returns_none(self) -> None:
        """Test that no default environment returns None."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            env = get_request_environment(request)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_environment_middleware()],
        )

        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            assert response.json()["environment"] is None


class TestEnvironmentMiddlewareAllowedEnvironments:
    """Tests for allowed environments validation."""

    def test_allowed_environment_passes(self) -> None:
        """Test that allowed environment passes validation."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            env = get_request_environment(request)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[
                create_environment_middleware(
                    allowed_environments=["production", "staging", "development"],
                )
            ],
        )

        with TestClient(app) as client:
            response = client.get("/test", headers={"X-Environment": "staging"})
            assert response.status_code == 200
            assert response.json()["environment"] == "staging"

    def test_disallowed_environment_falls_back_to_default(self) -> None:
        """Test that disallowed environment falls back to default."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            env = get_request_environment(request)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[
                create_environment_middleware(
                    default_environment="production",
                    allowed_environments=["production", "staging"],
                )
            ],
        )

        with TestClient(app) as client:
            response = client.get("/test", headers={"X-Environment": "invalid"})
            assert response.status_code == 200
            assert response.json()["environment"] == "production"

    def test_disallowed_environment_without_default(self) -> None:
        """Test disallowed environment without default returns None."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            env = get_request_environment(request)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[
                create_environment_middleware(
                    allowed_environments=["production", "staging"],
                )
            ],
        )

        with TestClient(app) as client:
            response = client.get("/test", headers={"X-Environment": "development"})
            assert response.status_code == 200
            assert response.json()["environment"] is None


class TestEnvironmentMiddlewareContextInjection:
    """Tests for environment injection into EvaluationContext."""

    def test_environment_injected_into_context(self) -> None:
        """Test that environment is injected into existing context."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            env = get_request_environment(request)
            return {
                "context_environment": context.environment if context else None,
                "resolved_environment": env,
            }

        app = Litestar(
            route_handlers=[handler],
            middleware=[
                create_context_middleware(),
                create_environment_middleware(),
            ],
        )

        with TestClient(app) as client:
            response = client.get("/test", headers={"X-Environment": "staging"})
            assert response.status_code == 200
            data = response.json()
            assert data["context_environment"] == "staging"
            assert data["resolved_environment"] == "staging"

    def test_context_preserves_other_fields(self) -> None:
        """Test that context preserves other fields when environment is injected."""

        def custom_extractor(request: Request[Any, Any, Any]) -> EvaluationContext:
            return EvaluationContext(
                targeting_key="user-123",
                user_id="user-123",
                attributes={"plan": "premium"},
            )

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            context = get_request_context(request)
            if context:
                return {
                    "targeting_key": context.targeting_key,
                    "user_id": context.user_id,
                    "environment": context.environment,
                    "plan": context.get("plan"),
                }
            return {}

        app = Litestar(
            route_handlers=[handler],
            middleware=[
                create_context_middleware(context_extractor=custom_extractor),
                create_environment_middleware(),
            ],
        )

        with TestClient(app) as client:
            response = client.get("/test", headers={"X-Environment": "production"})
            assert response.status_code == 200
            data = response.json()
            assert data["targeting_key"] == "user-123"
            assert data["user_id"] == "user-123"
            assert data["environment"] == "production"
            assert data["plan"] == "premium"


class TestEnvironmentMiddlewareClass:
    """Tests for EnvironmentMiddleware class directly."""

    def test_middleware_initialization_defaults(self) -> None:
        """Test middleware initializes with default values."""
        mock_app = MagicMock()
        middleware = EnvironmentMiddleware(app=mock_app)

        assert middleware.app is mock_app
        assert middleware._default_environment is None
        assert middleware._environment_header == "X-Environment"
        assert middleware._environment_query_param == "env"
        assert middleware._allowed_environments is None

    def test_middleware_initialization_custom_values(self) -> None:
        """Test middleware initializes with custom values."""
        mock_app = MagicMock()
        middleware = EnvironmentMiddleware(
            app=mock_app,
            default_environment="production",
            environment_header="X-App-Env",
            environment_query_param="environment",
            allowed_environments=["production", "staging"],
        )

        assert middleware._default_environment == "production"
        assert middleware._environment_header == "X-App-Env"
        assert middleware._environment_query_param == "environment"
        assert middleware._allowed_environments == {"production", "staging"}


class TestCreateEnvironmentMiddleware:
    """Tests for create_environment_middleware factory function."""

    def test_create_middleware_without_options(self) -> None:
        """Test creating middleware without options."""
        middleware_def = create_environment_middleware()

        assert middleware_def is not None
        assert middleware_def.middleware is EnvironmentMiddleware

    def test_create_middleware_with_options(self) -> None:
        """Test creating middleware with options."""
        middleware_def = create_environment_middleware(
            default_environment="production",
            environment_header="X-Env",
            environment_query_param="environment",
            allowed_environments=["production", "staging"],
        )

        assert middleware_def is not None
        assert middleware_def.middleware is EnvironmentMiddleware
        assert middleware_def.kwargs.get("default_environment") == "production"
        assert middleware_def.kwargs.get("environment_header") == "X-Env"
        assert middleware_def.kwargs.get("environment_query_param") == "environment"
        assert middleware_def.kwargs.get("allowed_environments") == ["production", "staging"]


class TestGetRequestEnvironment:
    """Tests for get_request_environment helper function."""

    def test_get_environment_returns_value(self) -> None:
        """Test getting environment from request with middleware."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            env = get_request_environment(request)
            return {"environment": env}

        app = Litestar(
            route_handlers=[handler],
            middleware=[create_environment_middleware()],
        )

        with TestClient(app) as client:
            response = client.get("/test", headers={"X-Environment": "staging"})
            assert response.status_code == 200
            assert response.json()["environment"] == "staging"

    def test_get_environment_returns_none_without_middleware(self) -> None:
        """Test getting environment from request without middleware."""

        @get("/test")
        async def handler(request: Request[Any, Any, Any]) -> dict[str, Any]:
            env = get_request_environment(request)
            return {"environment": env}

        app = Litestar(route_handlers=[handler])

        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            assert response.json()["environment"] is None
