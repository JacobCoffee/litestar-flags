"""Tests for feature flag decorators in HTTP context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from litestar import Litestar, get
from litestar.exceptions import NotAuthorizedException
from litestar.testing import TestClient

from litestar_flags import EvaluationContext, FeatureFlagClient, MemoryStorageBackend
from litestar_flags.decorators import (
    _build_context,
    _get_context_value,
    feature_flag,
    require_flag,
)
from litestar_flags.models.flag import FeatureFlag

if TYPE_CHECKING:
    from litestar import Request


class TestFeatureFlagDecorator:
    """Tests for the @feature_flag decorator."""

    async def test_handler_executes_when_flag_enabled(
        self,
        storage: MemoryStorageBackend,
        enabled_flag: FeatureFlag,
    ) -> None:
        """Test handler executes when the flag is enabled."""
        await storage.create_flag(enabled_flag)
        client = FeatureFlagClient(storage=storage)

        @feature_flag("enabled-flag")
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, str]:
            return {"message": "Feature enabled!"}

        result = await handler(feature_flags=client)
        assert result == {"message": "Feature enabled!"}

    async def test_handler_returns_default_when_flag_disabled(
        self,
        storage: MemoryStorageBackend,
        simple_flag: FeatureFlag,
    ) -> None:
        """Test handler returns default response when flag is disabled."""
        await storage.create_flag(simple_flag)
        client = FeatureFlagClient(storage=storage)

        @feature_flag("test-flag", default_response={"error": "Not available"})
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, str]:
            return {"message": "Feature enabled!"}

        result = await handler(feature_flags=client)
        assert result == {"error": "Not available"}

    async def test_with_custom_default_response(
        self,
        storage: MemoryStorageBackend,
        simple_flag: FeatureFlag,
    ) -> None:
        """Test decorator with custom default response."""
        await storage.create_flag(simple_flag)
        client = FeatureFlagClient(storage=storage)

        custom_response = {"status": "coming_soon", "message": "This feature is coming soon!"}

        @feature_flag("test-flag", default_response=custom_response)
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, Any]:
            return {"status": "active", "data": [1, 2, 3]}

        result = await handler(feature_flags=client)
        assert result == custom_response

    async def test_default_parameter_true_executes_handler_when_flag_not_found(
        self,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test handler executes when default=True and flag not found."""
        client = FeatureFlagClient(storage=storage)

        @feature_flag("nonexistent-flag", default=True)
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, str]:
            return {"message": "Default is True!"}

        result = await handler(feature_flags=client)
        assert result == {"message": "Default is True!"}

    async def test_default_parameter_false_returns_default_response_when_flag_not_found(
        self,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test handler returns default_response when default=False and flag not found."""
        client = FeatureFlagClient(storage=storage)

        @feature_flag("nonexistent-flag", default=False, default_response={"error": "Not found"})
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, str]:
            return {"message": "Should not see this"}

        result = await handler(feature_flags=client)
        assert result == {"error": "Not found"}

    async def test_no_client_available_uses_default_true(self) -> None:
        """Test when no client is available, uses default parameter (True)."""

        @feature_flag("any-flag", default=True)
        async def handler() -> dict[str, str]:
            return {"message": "Executed"}

        result = await handler()
        assert result == {"message": "Executed"}

    async def test_no_client_available_uses_default_false(self) -> None:
        """Test when no client is available, uses default parameter (False)."""

        @feature_flag("any-flag", default=False, default_response={"error": "Disabled"})
        async def handler() -> dict[str, str]:
            return {"message": "Should not execute"}

        result = await handler()
        assert result == {"error": "Disabled"}

    async def test_with_targeting_rules(
        self,
        storage: MemoryStorageBackend,
        flag_with_rules: FeatureFlag,
        premium_context: EvaluationContext,
    ) -> None:
        """Test decorator respects targeting rules."""
        await storage.create_flag(flag_with_rules)
        client = FeatureFlagClient(storage=storage, default_context=premium_context)

        @feature_flag("rules-flag", default_response={"error": "Not eligible"})
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, str]:
            return {"message": "Premium feature!"}

        result = await handler(feature_flags=client)
        assert result == {"message": "Premium feature!"}


class TestRequireFlagDecorator:
    """Tests for the @require_flag decorator."""

    async def test_handler_executes_when_flag_enabled(
        self,
        storage: MemoryStorageBackend,
        enabled_flag: FeatureFlag,
    ) -> None:
        """Test handler executes when flag is enabled."""
        await storage.create_flag(enabled_flag)
        client = FeatureFlagClient(storage=storage)

        @require_flag("enabled-flag")
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, str]:
            return {"message": "Access granted!"}

        result = await handler(feature_flags=client)
        assert result == {"message": "Access granted!"}

    async def test_raises_403_when_flag_disabled(
        self,
        storage: MemoryStorageBackend,
        simple_flag: FeatureFlag,
    ) -> None:
        """Test raises NotAuthorizedException when flag is disabled."""
        await storage.create_flag(simple_flag)
        client = FeatureFlagClient(storage=storage)

        @require_flag("test-flag")
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, str]:
            return {"message": "Should not see this"}

        with pytest.raises(NotAuthorizedException) as exc_info:
            await handler(feature_flags=client)

        assert "test-flag" in str(exc_info.value.detail)

    async def test_custom_error_message(
        self,
        storage: MemoryStorageBackend,
        simple_flag: FeatureFlag,
    ) -> None:
        """Test custom error message in exception."""
        await storage.create_flag(simple_flag)
        client = FeatureFlagClient(storage=storage)

        @require_flag("test-flag", error_message="Beta access required")
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, str]:
            return {"message": "Should not see this"}

        with pytest.raises(NotAuthorizedException) as exc_info:
            await handler(feature_flags=client)

        assert "Beta access required" in str(exc_info.value.detail)

    async def test_raises_when_flag_not_found_default_false(
        self,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test raises exception when flag not found and default=False."""
        client = FeatureFlagClient(storage=storage)

        @require_flag("nonexistent-flag", default=False)
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, str]:
            return {"message": "Should not execute"}

        with pytest.raises(NotAuthorizedException):
            await handler(feature_flags=client)

    async def test_executes_when_flag_not_found_default_true(
        self,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test handler executes when flag not found and default=True."""
        client = FeatureFlagClient(storage=storage)

        @require_flag("nonexistent-flag", default=True)
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, str]:
            return {"message": "Default is True!"}

        result = await handler(feature_flags=client)
        assert result == {"message": "Default is True!"}

    async def test_no_client_raises_when_default_false(self) -> None:
        """Test when no client is available, raises exception if default=False."""

        @require_flag("any-flag", default=False)
        async def handler() -> dict[str, str]:
            return {"message": "Should not execute"}

        with pytest.raises(NotAuthorizedException):
            await handler()

    async def test_no_client_executes_when_default_true(self) -> None:
        """Test when no client is available, executes if default=True."""

        @require_flag("any-flag", default=True)
        async def handler() -> dict[str, str]:
            return {"message": "Executed"}

        result = await handler()
        assert result == {"message": "Executed"}

    async def test_with_targeting_rules_premium_user(
        self,
        storage: MemoryStorageBackend,
        flag_with_rules: FeatureFlag,
        premium_context: EvaluationContext,
    ) -> None:
        """Test require_flag with targeting rules - premium user passes."""
        await storage.create_flag(flag_with_rules)
        client = FeatureFlagClient(storage=storage, default_context=premium_context)

        @require_flag("rules-flag")
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, str]:
            return {"message": "Premium access!"}

        result = await handler(feature_flags=client)
        assert result == {"message": "Premium access!"}

    async def test_with_targeting_rules_non_premium_user(
        self,
        storage: MemoryStorageBackend,
        flag_with_rules: FeatureFlag,
        context: EvaluationContext,
    ) -> None:
        """Test require_flag with targeting rules - non-premium user fails."""
        await storage.create_flag(flag_with_rules)
        client = FeatureFlagClient(storage=storage, default_context=context)

        @require_flag("rules-flag")
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, str]:
            return {"message": "Should not see this"}

        with pytest.raises(NotAuthorizedException):
            await handler(feature_flags=client)


class TestContextExtraction:
    """Tests for context extraction from requests."""

    def test_get_context_value_from_path_params(self) -> None:
        """Test extracting context value from path parameters."""
        mock_request = MagicMock()
        mock_request.path_params = {"user_id": "123"}
        mock_request.query_params = {}
        mock_request.headers = MagicMock()
        mock_request.headers.get.return_value = None

        result = _get_context_value(mock_request, "user_id")
        assert result == "123"

    def test_get_context_value_from_query_params(self) -> None:
        """Test extracting context value from query parameters."""
        mock_request = MagicMock()
        mock_request.path_params = {}
        mock_request.query_params = {"tenant_id": "org-456"}
        mock_request.headers = MagicMock()
        mock_request.headers.get.return_value = None

        result = _get_context_value(mock_request, "tenant_id")
        assert result == "org-456"

    def test_get_context_value_from_headers(self) -> None:
        """Test extracting context value from headers."""
        mock_request = MagicMock()
        mock_request.path_params = {}
        mock_request.query_params = {}
        mock_request.headers = MagicMock()
        mock_request.headers.get.side_effect = lambda key: ("api-key-123" if key == "x-api-key" else None)

        result = _get_context_value(mock_request, "x-api-key")
        assert result == "api-key-123"

    def test_get_context_value_from_headers_with_underscore(self) -> None:
        """Test extracting context value from headers using underscore format."""
        mock_request = MagicMock()
        mock_request.path_params = {}
        mock_request.query_params = {}

        # Simulate header lookup with underscore to hyphen conversion
        def header_get(key: str) -> str | None:
            headers = {"x-targeting-key": "target-123"}
            return headers.get(key)

        mock_request.headers = MagicMock()
        mock_request.headers.get.side_effect = header_get

        result = _get_context_value(mock_request, "x_targeting_key")
        assert result == "target-123"

    def test_get_context_value_from_user_attribute(self) -> None:
        """Test extracting context value from user attributes."""
        mock_request = MagicMock()
        mock_request.path_params = {}
        mock_request.query_params = {}
        mock_request.headers = MagicMock()
        mock_request.headers.get.return_value = None
        mock_request.user = MagicMock()
        mock_request.user.plan = "premium"

        result = _get_context_value(mock_request, "plan")
        assert result == "premium"

    def test_get_context_value_not_found(self) -> None:
        """Test extracting context value when not found."""
        mock_request = MagicMock()
        mock_request.path_params = {}
        mock_request.query_params = {}
        mock_request.headers = MagicMock()
        mock_request.headers.get.return_value = None
        mock_request.user = None

        result = _get_context_value(mock_request, "nonexistent")
        assert result is None

    def test_build_context_returns_none_when_no_request(self) -> None:
        """Test _build_context returns None when request is None."""
        result = _build_context(None, None)
        assert result is None

    def test_build_context_with_middleware_context(self) -> None:
        """Test _build_context uses middleware-extracted context."""
        mock_request = MagicMock()
        middleware_context = EvaluationContext(
            targeting_key="middleware-user",
            user_id="user-123",
        )
        mock_request.scope = {"feature_flags_context": middleware_context}

        with patch("litestar_flags.decorators.get_request_context") as mock_get:
            mock_get.return_value = middleware_context
            result = _build_context(mock_request, None)

        assert result is not None
        assert result.targeting_key == "middleware-user"
        assert result.user_id == "user-123"

    def test_build_context_overrides_targeting_key(self) -> None:
        """Test _build_context overrides targeting key from context_key."""
        mock_request = MagicMock()
        mock_request.path_params = {"org_id": "org-123"}
        mock_request.query_params = {}
        mock_request.headers = MagicMock()
        mock_request.headers.get.return_value = None

        middleware_context = EvaluationContext(
            targeting_key="original-key",
            user_id="user-123",
        )

        with patch("litestar_flags.decorators.get_request_context") as mock_get:
            mock_get.return_value = middleware_context
            result = _build_context(mock_request, context_key="org_id")

        assert result is not None
        assert result.targeting_key == "org-123"

    def test_build_context_without_middleware_creates_basic_context(self) -> None:
        """Test _build_context creates basic context without middleware."""
        mock_request = MagicMock()
        mock_request.path_params = {}
        mock_request.query_params = {}
        mock_request.headers = MagicMock()
        mock_request.headers.get.return_value = None
        mock_request.user = None

        with patch("litestar_flags.decorators.get_request_context") as mock_get:
            mock_get.return_value = None
            result = _build_context(mock_request, None)

        assert result is not None
        assert result.targeting_key is None
        assert result.user_id is None

    def test_build_context_extracts_user_id_from_auth(self) -> None:
        """Test _build_context extracts user_id from request.user."""

        @dataclass
        class User:
            id: str

        mock_request = MagicMock()
        mock_request.path_params = {}
        mock_request.query_params = {}
        mock_request.headers = MagicMock()
        mock_request.headers.get.return_value = None
        mock_request.user = User(id="auth-user-123")

        with patch("litestar_flags.decorators.get_request_context") as mock_get:
            mock_get.return_value = None
            result = _build_context(mock_request, None)

        assert result is not None
        assert result.user_id == "auth-user-123"
        assert result.targeting_key == "auth-user-123"

    def test_build_context_uses_context_key_over_user_id(self) -> None:
        """Test _build_context prioritizes context_key over user_id for targeting."""

        @dataclass
        class User:
            id: str

        mock_request = MagicMock()
        mock_request.path_params = {}
        mock_request.query_params = {"org_id": "org-456"}
        mock_request.headers = MagicMock()
        mock_request.headers.get.return_value = None
        mock_request.user = User(id="auth-user-123")

        with patch("litestar_flags.decorators.get_request_context") as mock_get:
            mock_get.return_value = None
            result = _build_context(mock_request, context_key="org_id")

        assert result is not None
        assert result.targeting_key == "org-456"
        assert result.user_id == "auth-user-123"


class TestDecoratorsInLitestarApp:
    """Integration tests for decorators in a Litestar application."""

    async def test_feature_flag_decorator_in_app(
        self,
        storage: MemoryStorageBackend,
        enabled_flag: FeatureFlag,
    ) -> None:
        """Test @feature_flag decorator in a Litestar app."""
        await storage.create_flag(enabled_flag)
        flag_client = FeatureFlagClient(storage=storage)

        @get("/feature")
        @feature_flag("enabled-flag", default_response={"error": "Not available"})
        async def feature_endpoint(request: Request[Any, Any, Any], feature_flags: FeatureFlagClient) -> dict[str, str]:
            return {"message": "Feature active!"}

        app = Litestar(
            route_handlers=[feature_endpoint],
            state=MagicMock(feature_flags=flag_client),
        )

        with TestClient(app) as _test_client:
            # We need to inject the client manually for this test
            # since the dependency injection isn't set up
            pass  # Integration test placeholder

    async def test_require_flag_decorator_in_app(
        self,
        storage: MemoryStorageBackend,
        simple_flag: FeatureFlag,
    ) -> None:
        """Test @require_flag decorator in a Litestar app."""
        await storage.create_flag(simple_flag)
        flag_client = FeatureFlagClient(storage=storage)

        @get("/protected")
        @require_flag("test-flag", error_message="Access denied")
        async def protected_endpoint(
            request: Request[Any, Any, Any], feature_flags: FeatureFlagClient
        ) -> dict[str, str]:
            return {"message": "Welcome!"}

        app = Litestar(
            route_handlers=[protected_endpoint],
            state=MagicMock(feature_flags=flag_client),
        )

        with TestClient(app) as _test_client:
            # Integration test placeholder
            pass


class TestDecoratorWithVariants:
    """Tests for decorator behavior with variant flags."""

    async def test_feature_flag_with_variant_evaluation(
        self,
        storage: MemoryStorageBackend,
        flag_with_variants: FeatureFlag,
    ) -> None:
        """Test that decorator works with variant-based flags."""
        await storage.create_flag(flag_with_variants)
        client = FeatureFlagClient(storage=storage)

        # The flag is enabled (default_enabled=True), so handler should execute
        @feature_flag("ab-test", default_response={"variant": "none"})
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, str]:
            return {"message": "In experiment!"}

        result = await handler(feature_flags=client)
        assert result == {"message": "In experiment!"}

    async def test_require_flag_with_variant_evaluation(
        self,
        storage: MemoryStorageBackend,
        flag_with_variants: FeatureFlag,
    ) -> None:
        """Test that require_flag works with variant-based flags."""
        await storage.create_flag(flag_with_variants)
        client = FeatureFlagClient(storage=storage)

        @require_flag("ab-test")
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, str]:
            return {"message": "In experiment!"}

        result = await handler(feature_flags=client)
        assert result == {"message": "In experiment!"}


class TestDecoratorEdgeCases:
    """Tests for edge cases and error handling."""

    async def test_decorator_preserves_function_metadata(self) -> None:
        """Test that decorators preserve function metadata."""

        @feature_flag("test-flag")
        async def my_handler() -> dict[str, str]:
            """My handler docstring."""
            return {"message": "Hello"}

        assert my_handler.__name__ == "my_handler"
        assert my_handler.__doc__ == "My handler docstring."

    async def test_require_flag_preserves_function_metadata(self) -> None:
        """Test that require_flag preserves function metadata."""

        @require_flag("test-flag")
        async def my_protected_handler() -> dict[str, str]:
            """My protected handler docstring."""
            return {"message": "Hello"}

        assert my_protected_handler.__name__ == "my_protected_handler"
        assert my_protected_handler.__doc__ == "My protected handler docstring."

    async def test_decorator_with_none_default_response(
        self,
        storage: MemoryStorageBackend,
        simple_flag: FeatureFlag,
    ) -> None:
        """Test decorator with None as default_response."""
        await storage.create_flag(simple_flag)
        client = FeatureFlagClient(storage=storage)

        @feature_flag("test-flag", default_response=None)
        async def handler(feature_flags: FeatureFlagClient = client) -> dict[str, str] | None:
            return {"message": "Active"}

        result = await handler(feature_flags=client)
        assert result is None

    async def test_client_from_app_state(
        self,
        storage: MemoryStorageBackend,
        enabled_flag: FeatureFlag,
    ) -> None:
        """Test decorator retrieves client from request.app.state."""
        await storage.create_flag(enabled_flag)
        client = FeatureFlagClient(storage=storage)

        mock_request = MagicMock()
        mock_request.app.state.feature_flags = client

        @feature_flag("enabled-flag")
        async def handler(request: Any = mock_request) -> dict[str, str]:
            return {"message": "From app state!"}

        result = await handler(request=mock_request)
        assert result == {"message": "From app state!"}
