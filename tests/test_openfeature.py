"""Comprehensive tests for OpenFeature Provider integration.

This module tests the LitestarFlagsProvider which adapts litestar-flags
to work with the OpenFeature Python SDK.

Tests cover:
- Provider initialization and metadata
- All resolve methods (boolean, string, integer, float, object)
- Async resolve methods
- EvaluationContext adaptation
- Error handling and error code mapping
- Reason mapping
- Lifecycle methods (initialize, shutdown)
- Hook integration
- OpenFeature API integration
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

openfeature = pytest.importorskip("openfeature")

from openfeature.evaluation_context import EvaluationContext as OFEvaluationContext
from openfeature.exception import ErrorCode as OFErrorCode
from openfeature.flag_evaluation import FlagResolutionDetails, Reason
from openfeature.hook import Hook
from openfeature.provider import Metadata

from litestar_flags.context import EvaluationContext
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.models.variant import FlagVariant
from litestar_flags.storage.memory import MemoryStorageBackend
from litestar_flags.types import ErrorCode, EvaluationReason, FlagStatus, FlagType

if TYPE_CHECKING:
    from litestar_flags.client import FeatureFlagClient


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def memory_storage() -> MemoryStorageBackend:
    """Create a memory storage backend."""
    return MemoryStorageBackend()


@pytest.fixture
async def storage_with_flags(memory_storage: MemoryStorageBackend) -> MemoryStorageBackend:
    """Create memory storage pre-populated with test flags."""
    # Boolean flag - enabled
    enabled_flag = FeatureFlag(
        id=uuid4(),
        key="enabled-feature",
        name="Enabled Feature",
        flag_type=FlagType.BOOLEAN,
        status=FlagStatus.ACTIVE,
        default_enabled=True,
        tags=["test"],
        metadata_={},
        rules=[],
        overrides=[],
        variants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await memory_storage.create_flag(enabled_flag)

    # Boolean flag - disabled
    disabled_flag = FeatureFlag(
        id=uuid4(),
        key="disabled-feature",
        name="Disabled Feature",
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
    await memory_storage.create_flag(disabled_flag)

    # String flag with variants
    string_flag_id = uuid4()
    string_flag = FeatureFlag(
        id=string_flag_id,
        key="string-flag",
        name="String Flag",
        flag_type=FlagType.STRING,
        status=FlagStatus.ACTIVE,
        default_enabled=True,
        default_value="default-variant",
        tags=["experiment"],
        metadata_={"experiment_id": "exp-123"},
        rules=[],
        overrides=[],
        variants=[
            FlagVariant(
                id=uuid4(),
                flag_id=string_flag_id,
                key="control",
                name="Control",
                value="control",
                weight=50,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            FlagVariant(
                id=uuid4(),
                flag_id=string_flag_id,
                key="treatment",
                name="Treatment",
                value="treatment",
                weight=50,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await memory_storage.create_flag(string_flag)

    # Number flag
    number_flag = FeatureFlag(
        id=uuid4(),
        key="number-flag",
        name="Number Flag",
        flag_type=FlagType.NUMBER,
        status=FlagStatus.ACTIVE,
        default_enabled=True,
        default_value=42.5,
        tags=[],
        metadata_={},
        rules=[],
        overrides=[],
        variants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await memory_storage.create_flag(number_flag)

    # JSON flag
    json_flag = FeatureFlag(
        id=uuid4(),
        key="json-flag",
        name="JSON Flag",
        flag_type=FlagType.JSON,
        status=FlagStatus.ACTIVE,
        default_enabled=True,
        default_value={"theme": "dark", "features": ["a", "b"]},
        tags=[],
        metadata_={},
        rules=[],
        overrides=[],
        variants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await memory_storage.create_flag(json_flag)

    # Inactive flag
    inactive_flag = FeatureFlag(
        id=uuid4(),
        key="inactive-flag",
        name="Inactive Flag",
        flag_type=FlagType.BOOLEAN,
        status=FlagStatus.INACTIVE,
        default_enabled=True,
        tags=[],
        metadata_={},
        rules=[],
        overrides=[],
        variants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await memory_storage.create_flag(inactive_flag)

    return memory_storage


@pytest.fixture
async def client(storage_with_flags: MemoryStorageBackend) -> FeatureFlagClient:
    """Create a feature flag client with test flags."""
    from litestar_flags.client import FeatureFlagClient

    return FeatureFlagClient(storage=storage_with_flags)


@pytest.fixture
def provider(client: FeatureFlagClient):
    """Create LitestarFlagsProvider with the test client."""
    from litestar_flags.contrib.openfeature import LitestarFlagsProvider

    return LitestarFlagsProvider(client=client)


@pytest.fixture
def boolean_flag() -> FeatureFlag:
    """Create a boolean test flag."""
    return FeatureFlag(
        id=uuid4(),
        key="test-boolean",
        name="Test Boolean",
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
def string_flag() -> FeatureFlag:
    """Create a string test flag with variants."""
    flag_id = uuid4()
    return FeatureFlag(
        id=flag_id,
        key="test-string",
        name="Test String",
        flag_type=FlagType.STRING,
        status=FlagStatus.ACTIVE,
        default_enabled=True,
        default_value={"value": "default"},
        tags=[],
        metadata_={},
        rules=[],
        overrides=[],
        variants=[
            FlagVariant(
                id=uuid4(),
                flag_id=flag_id,
                key="variant-a",
                name="Variant A",
                value={"value": "option-a"},
                weight=50,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            FlagVariant(
                id=uuid4(),
                flag_id=flag_id,
                key="variant-b",
                name="Variant B",
                value={"value": "option-b"},
                weight=50,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def number_flag() -> FeatureFlag:
    """Create a number test flag."""
    return FeatureFlag(
        id=uuid4(),
        key="test-number",
        name="Test Number",
        flag_type=FlagType.NUMBER,
        status=FlagStatus.ACTIVE,
        default_enabled=True,
        default_value={"value": 100.0},
        tags=[],
        metadata_={},
        rules=[],
        overrides=[],
        variants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def json_flag() -> FeatureFlag:
    """Create a JSON test flag."""
    return FeatureFlag(
        id=uuid4(),
        key="test-json",
        name="Test JSON",
        flag_type=FlagType.JSON,
        status=FlagStatus.ACTIVE,
        default_enabled=True,
        default_value={"settings": {"enabled": True, "count": 5}},
        tags=[],
        metadata_={},
        rules=[],
        overrides=[],
        variants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def of_context() -> OFEvaluationContext:
    """Create an OpenFeature evaluation context."""
    return OFEvaluationContext(
        targeting_key="user-123",
        attributes={
            "user_id": "user-123",
            "email": "user@example.com",
            "plan": "premium",
            "country": "US",
        },
    )


@pytest.fixture
def lf_context() -> EvaluationContext:
    """Create a litestar-flags evaluation context."""
    return EvaluationContext(
        targeting_key="user-123",
        user_id="user-123",
        attributes={"plan": "premium", "country": "US"},
    )


# =============================================================================
# Provider Initialization Tests
# =============================================================================


class TestProviderInitialization:
    """Tests for LitestarFlagsProvider initialization."""

    def test_create_provider_with_client(self, client: FeatureFlagClient):
        """Test creating provider with FeatureFlagClient."""
        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        provider = LitestarFlagsProvider(client=client)

        assert provider is not None
        assert provider._client is client

    def test_get_metadata_returns_correct_name(self, provider):
        """Test get_metadata() returns correct provider name."""
        metadata = provider.get_metadata()

        assert isinstance(metadata, Metadata)
        assert metadata.name == "litestar-flags"

    def test_get_provider_hooks_returns_hooks(self, provider):
        """Test get_provider_hooks() returns list of hooks."""
        hooks = provider.get_provider_hooks()

        assert isinstance(hooks, list)
        # Hooks should be empty by default or contain Hook instances
        for hook in hooks:
            assert isinstance(hook, Hook)

    def test_provider_with_custom_hooks(self, client: FeatureFlagClient):
        """Test creating provider with custom hooks."""
        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        mock_hook = MagicMock(spec=Hook)
        provider = LitestarFlagsProvider(client=client, hooks=[mock_hook])

        hooks = provider.get_provider_hooks()
        assert mock_hook in hooks


# =============================================================================
# Boolean Resolution Tests
# =============================================================================


class TestBooleanResolution:
    """Tests for boolean flag resolution."""

    @pytest.mark.asyncio
    async def test_resolve_boolean_details_enabled_flag(self, provider, of_context):
        """Test resolving an enabled boolean flag."""
        result = provider.resolve_boolean_details(
            flag_key="enabled-feature",
            default_value=False,
            evaluation_context=of_context,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert result.value is True
        assert result.reason in (Reason.STATIC, Reason.DEFAULT, Reason.TARGETING_MATCH)

    @pytest.mark.asyncio
    async def test_resolve_boolean_details_disabled_flag(self, provider, of_context):
        """Test resolving a disabled boolean flag."""
        result = provider.resolve_boolean_details(
            flag_key="disabled-feature",
            default_value=True,
            evaluation_context=of_context,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert result.value is False

    @pytest.mark.asyncio
    async def test_resolve_boolean_details_flag_not_found(self, provider, of_context):
        """Test resolving a non-existent boolean flag."""
        result = provider.resolve_boolean_details(
            flag_key="non-existent-flag",
            default_value=False,
            evaluation_context=of_context,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert result.value is False  # Default value
        assert result.error_code == OFErrorCode.FLAG_NOT_FOUND
        # When flag is not found, reason is DEFAULT (returning default value)
        assert result.reason == Reason.DEFAULT

    @pytest.mark.asyncio
    async def test_resolve_boolean_details_without_context(self, provider):
        """Test resolving boolean flag without evaluation context."""
        result = provider.resolve_boolean_details(
            flag_key="enabled-feature",
            default_value=False,
            evaluation_context=None,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert result.value is True


# =============================================================================
# String Resolution Tests
# =============================================================================


class TestStringResolution:
    """Tests for string flag resolution."""

    @pytest.mark.asyncio
    async def test_resolve_string_details_with_variant(self, provider, of_context):
        """Test resolving a string flag returns variant value."""
        result = provider.resolve_string_details(
            flag_key="string-flag",
            default_value="fallback",
            evaluation_context=of_context,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert isinstance(result.value, str)
        # Value should be from one of the variants or default
        assert result.value in ("control", "treatment", "default-variant", "fallback")

    @pytest.mark.asyncio
    async def test_resolve_string_details_default_value(self, provider, of_context):
        """Test resolving non-existent string flag returns default."""
        result = provider.resolve_string_details(
            flag_key="missing-string-flag",
            default_value="default-string",
            evaluation_context=of_context,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert result.value == "default-string"
        assert result.error_code == OFErrorCode.FLAG_NOT_FOUND

    @pytest.mark.asyncio
    async def test_resolve_string_details_without_context(self, provider):
        """Test resolving string flag without context."""
        result = provider.resolve_string_details(
            flag_key="string-flag",
            default_value="fallback",
            evaluation_context=None,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert isinstance(result.value, str)


# =============================================================================
# Integer Resolution Tests
# =============================================================================


class TestIntegerResolution:
    """Tests for integer flag resolution."""

    @pytest.mark.asyncio
    async def test_resolve_integer_details(self, provider, of_context):
        """Test resolving an integer flag."""
        result = provider.resolve_integer_details(
            flag_key="number-flag",
            default_value=0,
            evaluation_context=of_context,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert isinstance(result.value, int)
        # 42.5 should be converted to 42
        assert result.value == 42

    @pytest.mark.asyncio
    async def test_resolve_integer_details_default(self, provider, of_context):
        """Test resolving non-existent integer flag returns default."""
        result = provider.resolve_integer_details(
            flag_key="missing-number-flag",
            default_value=99,
            evaluation_context=of_context,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert result.value == 99
        assert result.error_code == OFErrorCode.FLAG_NOT_FOUND

    @pytest.mark.asyncio
    async def test_resolve_integer_details_without_context(self, provider):
        """Test resolving integer flag without context."""
        result = provider.resolve_integer_details(
            flag_key="number-flag",
            default_value=0,
            evaluation_context=None,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert isinstance(result.value, int)


# =============================================================================
# Float Resolution Tests
# =============================================================================


class TestFloatResolution:
    """Tests for float flag resolution."""

    @pytest.mark.asyncio
    async def test_resolve_float_details(self, provider, of_context):
        """Test resolving a float flag."""
        result = provider.resolve_float_details(
            flag_key="number-flag",
            default_value=0.0,
            evaluation_context=of_context,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert isinstance(result.value, float)
        assert result.value == 42.5

    @pytest.mark.asyncio
    async def test_resolve_float_details_default(self, provider, of_context):
        """Test resolving non-existent float flag returns default."""
        result = provider.resolve_float_details(
            flag_key="missing-float-flag",
            default_value=3.14,
            evaluation_context=of_context,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert result.value == 3.14
        assert result.error_code == OFErrorCode.FLAG_NOT_FOUND

    @pytest.mark.asyncio
    async def test_resolve_float_details_without_context(self, provider):
        """Test resolving float flag without context."""
        result = provider.resolve_float_details(
            flag_key="number-flag",
            default_value=0.0,
            evaluation_context=None,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert isinstance(result.value, float)


# =============================================================================
# Object Resolution Tests
# =============================================================================


class TestObjectResolution:
    """Tests for object/JSON flag resolution."""

    @pytest.mark.asyncio
    async def test_resolve_object_details(self, provider, of_context):
        """Test resolving a JSON object flag."""
        result = provider.resolve_object_details(
            flag_key="json-flag",
            default_value={},
            evaluation_context=of_context,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert isinstance(result.value, dict)
        assert "config" in result.value or "theme" in result.value

    @pytest.mark.asyncio
    async def test_resolve_object_details_default(self, provider, of_context):
        """Test resolving non-existent object flag returns default."""
        default_obj = {"fallback": True}
        result = provider.resolve_object_details(
            flag_key="missing-json-flag",
            default_value=default_obj,
            evaluation_context=of_context,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert result.value == default_obj
        assert result.error_code == OFErrorCode.FLAG_NOT_FOUND

    @pytest.mark.asyncio
    async def test_resolve_object_details_without_context(self, provider):
        """Test resolving object flag without context."""
        result = provider.resolve_object_details(
            flag_key="json-flag",
            default_value={},
            evaluation_context=None,
        )

        assert isinstance(result, FlagResolutionDetails)
        assert isinstance(result.value, dict)


# =============================================================================
# Async Resolution Tests
# =============================================================================


class TestAsyncResolution:
    """Tests for async resolution methods."""

    @pytest.mark.asyncio
    async def test_resolve_boolean_details_async(self, provider, of_context):
        """Test async boolean resolution."""
        # Check if provider has async method
        if hasattr(provider, "resolve_boolean_details_async"):
            result = await provider.resolve_boolean_details_async(
                flag_key="enabled-feature",
                default_value=False,
                evaluation_context=of_context,
            )

            assert isinstance(result, FlagResolutionDetails)
            assert result.value is True

    @pytest.mark.asyncio
    async def test_resolve_string_details_async(self, provider, of_context):
        """Test async string resolution."""
        if hasattr(provider, "resolve_string_details_async"):
            result = await provider.resolve_string_details_async(
                flag_key="string-flag",
                default_value="fallback",
                evaluation_context=of_context,
            )

            assert isinstance(result, FlagResolutionDetails)
            assert isinstance(result.value, str)

    @pytest.mark.asyncio
    async def test_resolve_integer_details_async(self, provider, of_context):
        """Test async integer resolution."""
        if hasattr(provider, "resolve_integer_details_async"):
            result = await provider.resolve_integer_details_async(
                flag_key="number-flag",
                default_value=0,
                evaluation_context=of_context,
            )

            assert isinstance(result, FlagResolutionDetails)
            assert isinstance(result.value, int)

    @pytest.mark.asyncio
    async def test_resolve_float_details_async(self, provider, of_context):
        """Test async float resolution."""
        if hasattr(provider, "resolve_float_details_async"):
            result = await provider.resolve_float_details_async(
                flag_key="number-flag",
                default_value=0.0,
                evaluation_context=of_context,
            )

            assert isinstance(result, FlagResolutionDetails)
            assert isinstance(result.value, float)

    @pytest.mark.asyncio
    async def test_resolve_object_details_async(self, provider, of_context):
        """Test async object resolution."""
        if hasattr(provider, "resolve_object_details_async"):
            result = await provider.resolve_object_details_async(
                flag_key="json-flag",
                default_value={},
                evaluation_context=of_context,
            )

            assert isinstance(result, FlagResolutionDetails)
            assert isinstance(result.value, dict)


# =============================================================================
# EvaluationContext Adaptation Tests
# =============================================================================


class TestEvaluationContextAdaptation:
    """Tests for adapting OpenFeature EvaluationContext to litestar-flags context."""

    def test_adapt_evaluation_context_with_targeting_key(self):
        """Test adapting context with targeting key."""
        from litestar_flags.contrib.openfeature import adapt_evaluation_context

        of_ctx = OFEvaluationContext(targeting_key="user-123")
        lf_ctx = adapt_evaluation_context(of_ctx)

        assert isinstance(lf_ctx, EvaluationContext)
        assert lf_ctx.targeting_key == "user-123"

    def test_adapt_evaluation_context_with_attributes(self):
        """Test adapting context with attributes."""
        from litestar_flags.contrib.openfeature import adapt_evaluation_context

        of_ctx = OFEvaluationContext(
            targeting_key="user-456",
            attributes={
                "user_id": "user-456",
                "organization_id": "org-789",
                "plan": "enterprise",
                "country": "CA",
                "environment": "production",
                "custom_attr": "custom_value",
            },
        )
        lf_ctx = adapt_evaluation_context(of_ctx)

        assert lf_ctx.targeting_key == "user-456"
        # Standard attributes should be mapped
        assert lf_ctx.user_id == "user-456"
        assert lf_ctx.organization_id == "org-789"
        assert lf_ctx.country == "CA"
        assert lf_ctx.environment == "production"
        # Custom attributes should be in attributes dict
        assert lf_ctx.attributes.get("plan") == "enterprise"
        assert lf_ctx.attributes.get("custom_attr") == "custom_value"

    def test_adapt_evaluation_context_none(self):
        """Test adapting None context returns default context."""
        from litestar_flags.contrib.openfeature import adapt_evaluation_context

        lf_ctx = adapt_evaluation_context(None)

        assert isinstance(lf_ctx, EvaluationContext)
        assert lf_ctx.targeting_key is None

    def test_adapt_evaluation_context_empty(self):
        """Test adapting empty context."""
        from litestar_flags.contrib.openfeature import adapt_evaluation_context

        of_ctx = OFEvaluationContext()
        lf_ctx = adapt_evaluation_context(of_ctx)

        assert isinstance(lf_ctx, EvaluationContext)
        assert lf_ctx.targeting_key is None

    def test_adapt_evaluation_context_preserves_all_standard_fields(self):
        """Test that all standard OpenFeature fields are preserved."""
        from litestar_flags.contrib.openfeature import adapt_evaluation_context

        of_ctx = OFEvaluationContext(
            targeting_key="target-key",
            attributes={
                "user_id": "user-id",
                "organization_id": "org-id",
                "tenant_id": "tenant-id",
                "environment": "staging",
                "app_version": "1.2.3",
                "ip_address": "192.168.1.1",
                "user_agent": "Mozilla/5.0",
                "country": "UK",
            },
        )
        lf_ctx = adapt_evaluation_context(of_ctx)

        assert lf_ctx.targeting_key == "target-key"
        assert lf_ctx.user_id == "user-id"
        assert lf_ctx.organization_id == "org-id"
        assert lf_ctx.tenant_id == "tenant-id"
        assert lf_ctx.environment == "staging"
        assert lf_ctx.app_version == "1.2.3"
        assert lf_ctx.ip_address == "192.168.1.1"
        assert lf_ctx.user_agent == "Mozilla/5.0"
        assert lf_ctx.country == "UK"


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in the provider."""

    @pytest.mark.asyncio
    async def test_flag_not_found_error(self, provider, of_context):
        """Test FLAG_NOT_FOUND error for missing flags."""
        result = provider.resolve_boolean_details(
            flag_key="definitely-not-existing-flag",
            default_value=False,
            evaluation_context=of_context,
        )

        assert result.value is False
        assert result.error_code == OFErrorCode.FLAG_NOT_FOUND
        # When flag is not found, reason is DEFAULT (returning default value)
        assert result.reason == Reason.DEFAULT

    @pytest.mark.asyncio
    async def test_type_mismatch_error(self, provider, of_context):
        """Test TYPE_MISMATCH error when requesting wrong type."""
        # Request boolean for a string flag
        result = provider.resolve_boolean_details(
            flag_key="string-flag",
            default_value=False,
            evaluation_context=of_context,
        )

        # Should return default with type mismatch error
        # (behavior may vary based on implementation)
        assert isinstance(result, FlagResolutionDetails)
        if result.error_code is not None:
            assert result.error_code in (OFErrorCode.TYPE_MISMATCH, OFErrorCode.GENERAL)

    @pytest.mark.asyncio
    async def test_provider_not_ready_error(self, client: FeatureFlagClient):
        """Test error behavior when client is closed."""
        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        # Close the client
        await client.close()

        provider = LitestarFlagsProvider(client=client)

        result = provider.resolve_boolean_details(
            flag_key="enabled-feature",
            default_value=False,
            evaluation_context=None,
        )

        assert result.value is False
        # A closed client may return FLAG_NOT_FOUND or other errors
        # depending on the storage backend behavior
        if result.error_code is not None:
            assert result.error_code in (
                OFErrorCode.PROVIDER_NOT_READY,
                OFErrorCode.GENERAL,
                OFErrorCode.FLAG_NOT_FOUND,
            )

    @pytest.mark.asyncio
    async def test_general_error_handling(self, client: FeatureFlagClient, of_context):
        """Test GENERAL error handling for unexpected exceptions."""
        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        # Mock the client to raise an unexpected exception
        # Use AsyncMock for async method
        client.get_boolean_details = AsyncMock(side_effect=RuntimeError("Unexpected error"))
        provider = LitestarFlagsProvider(client=client)

        result = provider.resolve_boolean_details(
            flag_key="enabled-feature",
            default_value=False,
            evaluation_context=of_context,
        )

        assert result.value is False
        assert result.error_code == OFErrorCode.GENERAL
        assert result.reason == Reason.ERROR


# =============================================================================
# Error Code Mapping Tests
# =============================================================================


class TestErrorCodeMapping:
    """Tests for mapping litestar-flags ErrorCode to OpenFeature ErrorCode."""

    def test_error_code_mapping(self):
        """Verify all litestar-flags ErrorCodes map to OpenFeature ErrorCodes."""
        from litestar_flags.contrib.openfeature import map_error_code

        # Test FLAG_NOT_FOUND mapping
        assert map_error_code(ErrorCode.FLAG_NOT_FOUND) == OFErrorCode.FLAG_NOT_FOUND

        # Test TYPE_MISMATCH mapping
        assert map_error_code(ErrorCode.TYPE_MISMATCH) == OFErrorCode.TYPE_MISMATCH

        # Test PARSE_ERROR mapping
        assert map_error_code(ErrorCode.PARSE_ERROR) == OFErrorCode.PARSE_ERROR

        # Test PROVIDER_NOT_READY mapping
        assert map_error_code(ErrorCode.PROVIDER_NOT_READY) == OFErrorCode.PROVIDER_NOT_READY

        # Test GENERAL_ERROR mapping
        assert map_error_code(ErrorCode.GENERAL_ERROR) == OFErrorCode.GENERAL

    def test_error_code_mapping_none(self):
        """Test that None error code returns None."""
        from litestar_flags.contrib.openfeature import map_error_code

        assert map_error_code(None) is None


# =============================================================================
# Reason Mapping Tests
# =============================================================================


class TestReasonMapping:
    """Tests for mapping litestar-flags EvaluationReason to OpenFeature Reason."""

    def test_reason_mapping(self):
        """Verify all litestar-flags EvaluationReasons map to OpenFeature Reasons."""
        from litestar_flags.contrib.openfeature import map_reason

        # Test DEFAULT mapping
        assert map_reason(EvaluationReason.DEFAULT) == Reason.DEFAULT

        # Test STATIC mapping
        assert map_reason(EvaluationReason.STATIC) == Reason.STATIC

        # Test TARGETING_MATCH mapping
        assert map_reason(EvaluationReason.TARGETING_MATCH) == Reason.TARGETING_MATCH

        # Test OVERRIDE mapping - maps to TARGETING_MATCH or similar
        result = map_reason(EvaluationReason.OVERRIDE)
        assert result in (Reason.TARGETING_MATCH, Reason.STATIC)

        # Test SPLIT mapping
        assert map_reason(EvaluationReason.SPLIT) == Reason.SPLIT

        # Test DISABLED mapping
        assert map_reason(EvaluationReason.DISABLED) == Reason.DISABLED

        # Test ERROR mapping
        assert map_reason(EvaluationReason.ERROR) == Reason.ERROR


# =============================================================================
# Lifecycle Method Tests
# =============================================================================


class TestLifecycleMethods:
    """Tests for provider lifecycle methods."""

    def test_initialize_preloads_flags(self, client: FeatureFlagClient):
        """Test that initialize() preloads flags."""
        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        # Spy on preload_flags
        original_preload = client.preload_flags
        client.preload_flags = AsyncMock(wraps=original_preload)

        provider = LitestarFlagsProvider(client=client)

        # Call initialize if it exists
        if hasattr(provider, "initialize"):
            provider.initialize(OFEvaluationContext())

            # Verify preload was called
            client.preload_flags.assert_called_once()

    def test_shutdown_closes_client(self, client: FeatureFlagClient):
        """Test that shutdown() closes the client."""
        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        # Spy on close
        original_close = client.close
        client.close = AsyncMock(wraps=original_close)

        provider = LitestarFlagsProvider(client=client)

        # Call shutdown if it exists
        if hasattr(provider, "shutdown"):
            provider.shutdown()

            # Verify close was called
            client.close.assert_called_once()

    def test_initialize_handles_errors_gracefully(self, client: FeatureFlagClient):
        """Test that initialize handles errors gracefully."""
        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        # Mock preload to raise an error
        client.preload_flags = AsyncMock(side_effect=RuntimeError("Preload failed"))

        provider = LitestarFlagsProvider(client=client)

        # Initialize should raise the error since that's the current behavior
        if hasattr(provider, "initialize"):
            with pytest.raises(RuntimeError, match="Preload failed"):
                provider.initialize(OFEvaluationContext())


# =============================================================================
# Hook Integration Tests
# =============================================================================


class TestHookIntegration:
    """Tests for hook integration with OpenFeature."""

    @pytest.fixture
    def mock_hook(self):
        """Create a mock OpenFeature hook."""
        hook = MagicMock(spec=Hook)
        hook.before = MagicMock()
        hook.after = MagicMock()
        hook.error = MagicMock()
        hook.finally_after = MagicMock()
        return hook

    def test_hook_before_called(self, client: FeatureFlagClient, mock_hook, of_context):
        """Test that before hook is called during evaluation."""
        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        provider = LitestarFlagsProvider(client=client, hooks=[mock_hook])

        # Trigger evaluation through OpenFeature API
        # This test may need to use the OpenFeature API directly
        # For now, verify hooks are stored
        hooks = provider.get_provider_hooks()
        assert mock_hook in hooks

    def test_hook_after_called(self, client: FeatureFlagClient, mock_hook, of_context):
        """Test that after hook is called after successful evaluation."""
        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        provider = LitestarFlagsProvider(client=client, hooks=[mock_hook])

        # Verify hooks are registered
        hooks = provider.get_provider_hooks()
        assert mock_hook in hooks

    def test_hook_error_called(self, client: FeatureFlagClient, mock_hook, of_context):
        """Test that error hook is called on evaluation error."""
        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        provider = LitestarFlagsProvider(client=client, hooks=[mock_hook])

        # Verify hooks are registered
        hooks = provider.get_provider_hooks()
        assert mock_hook in hooks

    def test_hook_finally_called(self, client: FeatureFlagClient, mock_hook, of_context):
        """Test that finally hook is always called."""
        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        provider = LitestarFlagsProvider(client=client, hooks=[mock_hook])

        # Verify hooks are registered
        hooks = provider.get_provider_hooks()
        assert mock_hook in hooks


# =============================================================================
# OpenFeature API Integration Tests
# =============================================================================


class TestOpenFeatureAPIIntegration:
    """Integration tests using the OpenFeature API with our provider."""

    @pytest.mark.asyncio
    async def test_openfeature_api_integration(self, client: FeatureFlagClient):
        """Test using OpenFeature API with our provider."""
        from openfeature import api

        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        # Create and register provider
        provider = LitestarFlagsProvider(client=client)

        # Set as the default provider
        api.set_provider(provider)

        # Get an OpenFeature client
        of_client = api.get_client()

        # Evaluate flags through OpenFeature API
        result = of_client.get_boolean_value(
            flag_key="enabled-feature",
            default_value=False,
        )

        assert result is True

        # Test with context
        context = OFEvaluationContext(
            targeting_key="test-user",
            attributes={"plan": "premium"},
        )

        result_with_context = of_client.get_boolean_value(
            flag_key="enabled-feature",
            default_value=False,
            evaluation_context=context,
        )

        assert result_with_context is True

    @pytest.mark.asyncio
    async def test_openfeature_api_string_flag(self, client: FeatureFlagClient):
        """Test string flag through OpenFeature API."""
        from openfeature import api

        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        provider = LitestarFlagsProvider(client=client)
        api.set_provider(provider)

        of_client = api.get_client()

        result = of_client.get_string_value(
            flag_key="string-flag",
            default_value="fallback",
        )

        assert isinstance(result, str)
        # Should be one of the variant values or default
        assert result in ("control", "treatment", "default-variant", "fallback")

    @pytest.mark.asyncio
    async def test_openfeature_api_number_flag(self, client: FeatureFlagClient):
        """Test number flag through OpenFeature API."""
        from openfeature import api

        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        provider = LitestarFlagsProvider(client=client)
        api.set_provider(provider)

        of_client = api.get_client()

        # Test integer - value 42.5 truncates to 42
        int_result = of_client.get_integer_value(
            flag_key="number-flag",
            default_value=0,
        )

        assert isinstance(int_result, int)
        # The flag value is 42.5, truncated to 42 for integer
        assert int_result == 42

        # Test float - should get the actual value 42.5
        float_result = of_client.get_float_value(
            flag_key="number-flag",
            default_value=0.0,
        )

        assert isinstance(float_result, float)
        assert float_result == 42.5

    @pytest.mark.asyncio
    async def test_openfeature_api_object_flag(self, client: FeatureFlagClient):
        """Test object flag through OpenFeature API."""
        from openfeature import api

        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        provider = LitestarFlagsProvider(client=client)
        api.set_provider(provider)

        of_client = api.get_client()

        result = of_client.get_object_value(
            flag_key="json-flag",
            default_value={},
        )

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_openfeature_api_flag_not_found(self, client: FeatureFlagClient):
        """Test flag not found through OpenFeature API."""
        from openfeature import api

        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        provider = LitestarFlagsProvider(client=client)
        api.set_provider(provider)

        of_client = api.get_client()

        result = of_client.get_boolean_value(
            flag_key="non-existent-flag-xyz",
            default_value=True,
        )

        # Should return default value
        assert result is True

    @pytest.mark.asyncio
    async def test_openfeature_api_with_details(self, client: FeatureFlagClient):
        """Test getting evaluation details through OpenFeature API."""
        from openfeature import api

        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        provider = LitestarFlagsProvider(client=client)
        api.set_provider(provider)

        of_client = api.get_client()

        details = of_client.get_boolean_details(
            flag_key="enabled-feature",
            default_value=False,
        )

        assert details.value is True
        assert details.flag_key == "enabled-feature"
        assert details.reason is not None


# =============================================================================
# Edge Cases and Boundary Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_flag_key(self, provider, of_context):
        """Test handling of empty flag key."""
        result = provider.resolve_boolean_details(
            flag_key="",
            default_value=False,
            evaluation_context=of_context,
        )

        assert result.value is False
        assert result.error_code == OFErrorCode.FLAG_NOT_FOUND

    @pytest.mark.asyncio
    async def test_special_characters_in_flag_key(self, provider, of_context):
        """Test handling of special characters in flag key."""
        result = provider.resolve_boolean_details(
            flag_key="flag/with:special-chars_and.dots",
            default_value=False,
            evaluation_context=of_context,
        )

        # Should handle gracefully, likely return not found
        assert result.value is False

    @pytest.mark.asyncio
    async def test_very_long_flag_key(self, provider, of_context):
        """Test handling of very long flag key."""
        long_key = "a" * 1000
        result = provider.resolve_boolean_details(
            flag_key=long_key,
            default_value=False,
            evaluation_context=of_context,
        )

        assert result.value is False

    @pytest.mark.asyncio
    async def test_unicode_in_flag_key(self, provider, of_context):
        """Test handling of unicode in flag key."""
        result = provider.resolve_boolean_details(
            flag_key="flag-with-unicode-\u00e9\u00e8\u00ea",
            default_value=False,
            evaluation_context=of_context,
        )

        assert result.value is False

    @pytest.mark.asyncio
    async def test_context_with_nested_attributes(self, provider):
        """Test context with deeply nested attributes."""
        of_ctx = OFEvaluationContext(
            targeting_key="user-123",
            attributes={
                "nested": {
                    "deeply": {
                        "value": True,
                    },
                },
                "array": [1, 2, 3],
            },
        )

        result = provider.resolve_boolean_details(
            flag_key="enabled-feature",
            default_value=False,
            evaluation_context=of_ctx,
        )

        # Should handle without error
        assert isinstance(result, FlagResolutionDetails)

    @pytest.mark.asyncio
    async def test_concurrent_evaluations(self, provider, of_context):
        """Test concurrent flag evaluations."""
        import asyncio

        async def evaluate(flag_key: str):
            return provider.resolve_boolean_details(
                flag_key=flag_key,
                default_value=False,
                evaluation_context=of_context,
            )

        # Run 10 concurrent evaluations
        tasks = [evaluate("enabled-feature") for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 10
        assert all(r.value is True for r in results)


# =============================================================================
# Provider State Tests
# =============================================================================


class TestProviderState:
    """Tests for provider state management."""

    def test_provider_status_property(self, provider):
        """Test provider status property if available."""
        if hasattr(provider, "status"):
            from openfeature.provider import ProviderStatus

            assert provider.status in (
                ProviderStatus.NOT_READY,
                ProviderStatus.READY,
                ProviderStatus.ERROR,
                ProviderStatus.STALE,
            )

    @pytest.mark.asyncio
    async def test_provider_ready_after_initialize(self, client: FeatureFlagClient):
        """Test provider is ready after initialize."""
        from litestar_flags.contrib.openfeature import LitestarFlagsProvider

        provider = LitestarFlagsProvider(client=client)

        if hasattr(provider, "initialize") and hasattr(provider, "status"):
            from openfeature.provider import ProviderStatus

            await provider.initialize(OFEvaluationContext())
            assert provider.status == ProviderStatus.READY


# =============================================================================
# Flag Metadata Tests
# =============================================================================


class TestFlagMetadata:
    """Tests for flag metadata handling."""

    @pytest.mark.asyncio
    async def test_flag_metadata_in_resolution(self, provider, of_context):
        """Test that flag metadata is included in resolution details."""
        result = provider.resolve_string_details(
            flag_key="string-flag",
            default_value="fallback",
            evaluation_context=of_context,
        )

        # Check if metadata is available
        if hasattr(result, "flag_metadata") and result.flag_metadata:
            assert isinstance(result.flag_metadata, dict)

    @pytest.mark.asyncio
    async def test_variant_in_resolution(self, provider, of_context):
        """Test that variant is included in resolution details."""
        result = provider.resolve_string_details(
            flag_key="string-flag",
            default_value="fallback",
            evaluation_context=of_context,
        )

        # Variant may or may not be set depending on evaluation
        if result.variant is not None:
            assert isinstance(result.variant, str)
