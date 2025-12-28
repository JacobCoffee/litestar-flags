"""Tests for bootstrap and offline client functionality."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from litestar_flags.bootstrap import (
    BootstrapConfig,
    BootstrapLoader,
    OfflineClient,
    _OfflineStorageAdapter,
)
from litestar_flags.context import EvaluationContext
from litestar_flags.exceptions import ConfigurationError
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.types import ErrorCode, EvaluationReason, FlagStatus, FlagType


# -----------------------------------------------------------------------------
# BootstrapConfig Tests
# -----------------------------------------------------------------------------
class TestBootstrapConfig:
    """Tests for BootstrapConfig dataclass."""

    def test_config_with_path_source(self) -> None:
        """Test config initialization with Path source."""
        path = Path("flags.json")
        config = BootstrapConfig(source=path)

        assert config.source == path
        assert config.fallback_on_error is True
        assert config.refresh_interval is None

    def test_config_with_string_source(self) -> None:
        """Test config initialization with string path source."""
        config = BootstrapConfig(source="flags.json")

        assert config.source == "flags.json"
        assert config.fallback_on_error is True
        assert config.refresh_interval is None

    def test_config_with_dict_source(self) -> None:
        """Test config initialization with dictionary source."""
        data = {"flags": [{"key": "test", "name": "Test"}]}
        config = BootstrapConfig(source=data)

        assert config.source == data
        assert config.fallback_on_error is True
        assert config.refresh_interval is None

    def test_config_with_custom_options(self) -> None:
        """Test config with custom fallback and refresh settings."""
        config = BootstrapConfig(
            source=Path("flags.json"),
            fallback_on_error=False,
            refresh_interval=300.0,
        )

        assert config.fallback_on_error is False
        assert config.refresh_interval == 300.0


# -----------------------------------------------------------------------------
# BootstrapLoader Tests
# -----------------------------------------------------------------------------
class TestBootstrapLoader:
    """Tests for BootstrapLoader class."""

    @pytest.fixture
    def loader(self) -> BootstrapLoader:
        """Create a BootstrapLoader instance."""
        return BootstrapLoader()

    @pytest.fixture
    def valid_flag_data(self) -> dict[str, Any]:
        """Create valid flag data dictionary."""
        return {
            "flags": [
                {
                    "key": "feature-1",
                    "name": "Feature One",
                    "description": "First test feature",
                    "flag_type": "boolean",
                    "status": "active",
                    "default_enabled": True,
                    "tags": ["test", "beta"],
                    "metadata": {"team": "platform"},
                },
                {
                    "key": "feature-2",
                    "name": "Feature Two",
                    "flag_type": "string",
                    "default_enabled": False,
                    "default_value": "default-string",
                },
            ]
        }

    @pytest.fixture
    def temp_json_file(self, valid_flag_data: dict[str, Any]) -> Path:
        """Create a temporary JSON file with flag data."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(valid_flag_data, f)
            return Path(f.name)

    # load_from_dict tests
    def test_load_from_dict_success(self, loader: BootstrapLoader, valid_flag_data: dict[str, Any]) -> None:
        """Test loading flags from dictionary."""
        flags = loader.load_from_dict(valid_flag_data)

        assert len(flags) == 2
        assert flags[0].key == "feature-1"
        assert flags[0].name == "Feature One"
        assert flags[0].description == "First test feature"
        assert flags[0].flag_type == FlagType.BOOLEAN
        assert flags[0].status == FlagStatus.ACTIVE
        assert flags[0].default_enabled is True
        assert flags[0].tags == ["test", "beta"]
        assert flags[0].metadata_ == {"team": "platform"}

        assert flags[1].key == "feature-2"
        assert flags[1].flag_type == FlagType.STRING
        assert flags[1].default_value == "default-string"

    def test_load_from_dict_empty_flags(self, loader: BootstrapLoader) -> None:
        """Test loading empty flags list."""
        flags = loader.load_from_dict({"flags": []})
        assert flags == []

    def test_load_from_dict_no_flags_key(self, loader: BootstrapLoader) -> None:
        """Test loading data without flags key returns empty list."""
        flags = loader.load_from_dict({})
        assert flags == []

    def test_load_from_dict_flags_not_list(self, loader: BootstrapLoader) -> None:
        """Test loading data where flags is not a list raises error."""
        with pytest.raises(ConfigurationError, match="'flags' must be a list"):
            loader.load_from_dict({"flags": "not-a-list"})

    def test_load_from_dict_missing_key_field(self, loader: BootstrapLoader) -> None:
        """Test loading flag without key field raises error."""
        with pytest.raises(ConfigurationError, match="Flag missing required 'key' field"):
            loader.load_from_dict({"flags": [{"name": "No Key Flag"}]})

    def test_load_from_dict_name_defaults_to_key(self, loader: BootstrapLoader) -> None:
        """Test that name defaults to key if not provided."""
        flags = loader.load_from_dict({"flags": [{"key": "my-key"}]})

        assert len(flags) == 1
        assert flags[0].key == "my-key"
        assert flags[0].name == "my-key"

    def test_load_from_dict_invalid_flag_type(self, loader: BootstrapLoader) -> None:
        """Test loading flag with invalid flag_type raises error."""
        with pytest.raises(ConfigurationError, match="Invalid flag_type: invalid"):
            loader.load_from_dict({"flags": [{"key": "test", "flag_type": "invalid"}]})

    def test_load_from_dict_invalid_status(self, loader: BootstrapLoader) -> None:
        """Test loading flag with invalid status raises error."""
        with pytest.raises(ConfigurationError, match="Invalid status: invalid"):
            loader.load_from_dict({"flags": [{"key": "test", "status": "invalid"}]})

    def test_load_from_dict_with_uuid_id(self, loader: BootstrapLoader) -> None:
        """Test loading flag with provided UUID id."""
        flag_id = str(uuid4())
        flags = loader.load_from_dict({"flags": [{"key": "test", "id": flag_id}]})

        assert str(flags[0].id) == flag_id

    def test_load_from_dict_with_invalid_uuid(self, loader: BootstrapLoader) -> None:
        """Test loading flag with invalid UUID raises error."""
        with pytest.raises(ConfigurationError, match="Invalid UUID"):
            loader.load_from_dict({"flags": [{"key": "test", "id": "not-a-uuid"}]})

    def test_load_from_dict_generates_uuid_if_not_provided(self, loader: BootstrapLoader) -> None:
        """Test that UUID is generated if not provided."""
        flags = loader.load_from_dict({"flags": [{"key": "test"}]})

        assert flags[0].id is not None
        assert isinstance(flags[0].id, UUID)

    def test_load_from_dict_with_timestamps(self, loader: BootstrapLoader) -> None:
        """Test loading flag with ISO timestamp strings."""
        created = "2024-01-15T10:30:00+00:00"
        updated = "2024-06-20T14:45:00+00:00"

        flags = loader.load_from_dict(
            {
                "flags": [
                    {
                        "key": "test",
                        "created_at": created,
                        "updated_at": updated,
                    }
                ]
            }
        )

        assert flags[0].created_at.year == 2024
        assert flags[0].created_at.month == 1
        assert flags[0].updated_at.month == 6

    def test_load_from_dict_all_flag_types(self, loader: BootstrapLoader) -> None:
        """Test loading flags with all supported flag types."""
        flags = loader.load_from_dict(
            {
                "flags": [
                    {"key": "bool-flag", "flag_type": "boolean"},
                    {"key": "str-flag", "flag_type": "string"},
                    {"key": "num-flag", "flag_type": "number"},
                    {"key": "json-flag", "flag_type": "json"},
                ]
            }
        )

        assert len(flags) == 4
        assert flags[0].flag_type == FlagType.BOOLEAN
        assert flags[1].flag_type == FlagType.STRING
        assert flags[2].flag_type == FlagType.NUMBER
        assert flags[3].flag_type == FlagType.JSON

    def test_load_from_dict_all_statuses(self, loader: BootstrapLoader) -> None:
        """Test loading flags with all supported statuses."""
        flags = loader.load_from_dict(
            {
                "flags": [
                    {"key": "active-flag", "status": "active"},
                    {"key": "inactive-flag", "status": "inactive"},
                    {"key": "archived-flag", "status": "archived"},
                ]
            }
        )

        assert len(flags) == 3
        assert flags[0].status == FlagStatus.ACTIVE
        assert flags[1].status == FlagStatus.INACTIVE
        assert flags[2].status == FlagStatus.ARCHIVED

    # load_from_file tests
    @pytest.mark.asyncio
    async def test_load_from_file_success(self, loader: BootstrapLoader, temp_json_file: Path) -> None:
        """Test loading flags from JSON file."""
        flags = await loader.load_from_file(temp_json_file)

        assert len(flags) == 2
        assert flags[0].key == "feature-1"
        assert flags[1].key == "feature-2"

        # Cleanup
        temp_json_file.unlink()

    @pytest.mark.asyncio
    async def test_load_from_file_not_found(self, loader: BootstrapLoader) -> None:
        """Test loading from non-existent file raises error."""
        with pytest.raises(ConfigurationError, match="Bootstrap file not found"):
            await loader.load_from_file(Path("/nonexistent/flags.json"))

    @pytest.mark.asyncio
    async def test_load_from_file_invalid_json(self, loader: BootstrapLoader) -> None:
        """Test loading file with invalid JSON raises error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {{{")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ConfigurationError, match="Invalid JSON"):
                await loader.load_from_file(temp_path)
        finally:
            temp_path.unlink()

    # load (with config) tests
    @pytest.mark.asyncio
    async def test_load_with_path_config(self, loader: BootstrapLoader, temp_json_file: Path) -> None:
        """Test load method with Path config source."""
        config = BootstrapConfig(source=temp_json_file)
        flags = await loader.load(config)

        assert len(flags) == 2

        temp_json_file.unlink()

    @pytest.mark.asyncio
    async def test_load_with_string_path_config(self, loader: BootstrapLoader, temp_json_file: Path) -> None:
        """Test load method with string path config source."""
        config = BootstrapConfig(source=str(temp_json_file))
        flags = await loader.load(config)

        assert len(flags) == 2

        temp_json_file.unlink()

    @pytest.mark.asyncio
    async def test_load_with_dict_config(self, loader: BootstrapLoader, valid_flag_data: dict[str, Any]) -> None:
        """Test load method with dict config source."""
        config = BootstrapConfig(source=valid_flag_data)
        flags = await loader.load(config)

        assert len(flags) == 2
        assert flags[0].key == "feature-1"

    @pytest.mark.asyncio
    async def test_load_fallback_on_error_true(self, loader: BootstrapLoader) -> None:
        """Test load returns empty list on error when fallback_on_error is True."""
        config = BootstrapConfig(
            source=Path("/nonexistent/flags.json"),
            fallback_on_error=True,
        )
        flags = await loader.load(config)

        assert flags == []

    @pytest.mark.asyncio
    async def test_load_fallback_on_error_false(self, loader: BootstrapLoader) -> None:
        """Test load raises error when fallback_on_error is False."""
        config = BootstrapConfig(
            source=Path("/nonexistent/flags.json"),
            fallback_on_error=False,
        )

        with pytest.raises(ConfigurationError):
            await loader.load(config)


# -----------------------------------------------------------------------------
# OfflineClient Tests
# -----------------------------------------------------------------------------
class TestOfflineClient:
    """Tests for OfflineClient class."""

    @pytest.fixture
    def sample_flags(self) -> list[FeatureFlag]:
        """Create sample flags for testing."""
        now = datetime.now(UTC)
        return [
            FeatureFlag(
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
                created_at=now,
                updated_at=now,
            ),
            FeatureFlag(
                id=uuid4(),
                key="disabled-bool",
                name="Disabled Boolean",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=False,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
                created_at=now,
                updated_at=now,
            ),
            FeatureFlag(
                id=uuid4(),
                key="string-flag",
                name="String Flag",
                flag_type=FlagType.STRING,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                default_value="hello-world",
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
                created_at=now,
                updated_at=now,
            ),
            FeatureFlag(
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
                created_at=now,
                updated_at=now,
            ),
            FeatureFlag(
                id=uuid4(),
                key="json-flag",
                name="JSON Flag",
                flag_type=FlagType.JSON,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                default_value={"nested": {"value": 123}},
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
                created_at=now,
                updated_at=now,
            ),
            FeatureFlag(
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
                created_at=now,
                updated_at=now,
            ),
        ]

    @pytest.fixture
    def offline_client(self, sample_flags: list[FeatureFlag]) -> OfflineClient:
        """Create an OfflineClient instance with sample flags."""
        return OfflineClient(flags=sample_flags)

    @pytest.fixture
    def context(self) -> EvaluationContext:
        """Create an evaluation context."""
        return EvaluationContext(
            targeting_key="user-123",
            user_id="user-123",
            attributes={"plan": "premium"},
        )

    # Initialization tests
    def test_init_with_flags(self, sample_flags: list[FeatureFlag]) -> None:
        """Test client initialization with flags."""
        client = OfflineClient(flags=sample_flags)

        assert len(client.flags) == 6
        assert "bool-flag" in client.flags
        assert "string-flag" in client.flags

    def test_init_with_empty_flags(self) -> None:
        """Test client initialization with empty flags list."""
        client = OfflineClient(flags=[])
        assert len(client.flags) == 0

    def test_init_with_default_context(self, sample_flags: list[FeatureFlag]) -> None:
        """Test client initialization with default context."""
        default_ctx = EvaluationContext(
            targeting_key="default-user",
            environment="production",
        )
        client = OfflineClient(flags=sample_flags, default_context=default_ctx)

        assert client._default_context == default_ctx

    @pytest.mark.asyncio
    async def test_from_config(self) -> None:
        """Test creating client from BootstrapConfig."""
        config = BootstrapConfig(source={"flags": [{"key": "test-flag", "default_enabled": True}]})

        client = await OfflineClient.from_config(config)

        assert len(client.flags) == 1
        assert "test-flag" in client.flags

    @pytest.mark.asyncio
    async def test_from_config_with_context(self) -> None:
        """Test creating client from config with default context."""
        config = BootstrapConfig(source={"flags": [{"key": "test"}]})
        ctx = EvaluationContext(targeting_key="user-1")

        client = await OfflineClient.from_config(config, default_context=ctx)

        assert client._default_context == ctx

    def test_from_flags(self, sample_flags: list[FeatureFlag]) -> None:
        """Test creating client from flags list."""
        client = OfflineClient.from_flags(sample_flags)

        assert len(client.flags) == 6

    def test_from_flags_with_context(self, sample_flags: list[FeatureFlag]) -> None:
        """Test creating client from flags with context."""
        ctx = EvaluationContext(user_id="user-123")
        client = OfflineClient.from_flags(sample_flags, default_context=ctx)

        assert client._default_context == ctx

    # Boolean evaluation tests
    @pytest.mark.asyncio
    async def test_get_boolean_value_enabled(self, offline_client: OfflineClient) -> None:
        """Test getting enabled boolean flag value."""
        value = await offline_client.get_boolean_value("bool-flag")
        assert value is True

    @pytest.mark.asyncio
    async def test_get_boolean_value_disabled(self, offline_client: OfflineClient) -> None:
        """Test getting disabled boolean flag value."""
        value = await offline_client.get_boolean_value("disabled-bool")
        assert value is False

    @pytest.mark.asyncio
    async def test_get_boolean_value_not_found(self, offline_client: OfflineClient) -> None:
        """Test getting boolean value for non-existent flag returns default."""
        value = await offline_client.get_boolean_value("nonexistent", default=True)
        assert value is True

    @pytest.mark.asyncio
    async def test_get_boolean_details(self, offline_client: OfflineClient) -> None:
        """Test getting boolean flag with details."""
        details = await offline_client.get_boolean_details("bool-flag")

        assert details.value is True
        assert details.flag_key == "bool-flag"
        assert details.error_code is None

    @pytest.mark.asyncio
    async def test_get_boolean_details_not_found(self, offline_client: OfflineClient) -> None:
        """Test boolean details for non-existent flag."""
        details = await offline_client.get_boolean_details("nonexistent")

        assert details.value is False
        assert details.error_code == ErrorCode.FLAG_NOT_FOUND
        assert details.reason == EvaluationReason.DEFAULT

    # String evaluation tests
    @pytest.mark.asyncio
    async def test_get_string_value(self, offline_client: OfflineClient) -> None:
        """Test getting string flag value."""
        value = await offline_client.get_string_value("string-flag")
        assert value == "hello-world"

    @pytest.mark.asyncio
    async def test_get_string_value_not_found(self, offline_client: OfflineClient) -> None:
        """Test getting string value for non-existent flag returns default."""
        value = await offline_client.get_string_value("nonexistent", default="fallback")
        assert value == "fallback"

    @pytest.mark.asyncio
    async def test_get_string_details(self, offline_client: OfflineClient) -> None:
        """Test getting string flag with details."""
        details = await offline_client.get_string_details("string-flag")

        assert details.value == "hello-world"
        assert details.flag_key == "string-flag"
        assert details.error_code is None

    @pytest.mark.asyncio
    async def test_get_string_type_mismatch(self, offline_client: OfflineClient) -> None:
        """Test type mismatch when getting string from boolean flag."""
        details = await offline_client.get_string_details("bool-flag", default="default")

        assert details.value == "default"
        assert details.error_code == ErrorCode.TYPE_MISMATCH
        assert details.reason == EvaluationReason.ERROR

    # Number evaluation tests
    @pytest.mark.asyncio
    async def test_get_number_value(self, offline_client: OfflineClient) -> None:
        """Test getting number flag value."""
        value = await offline_client.get_number_value("number-flag")
        assert value == 42.5

    @pytest.mark.asyncio
    async def test_get_number_value_not_found(self, offline_client: OfflineClient) -> None:
        """Test getting number value for non-existent flag returns default."""
        value = await offline_client.get_number_value("nonexistent", default=99.9)
        assert value == 99.9

    @pytest.mark.asyncio
    async def test_get_number_details(self, offline_client: OfflineClient) -> None:
        """Test getting number flag with details."""
        details = await offline_client.get_number_details("number-flag")

        assert details.value == 42.5
        assert details.flag_key == "number-flag"
        assert details.error_code is None

    @pytest.mark.asyncio
    async def test_get_number_type_mismatch(self, offline_client: OfflineClient) -> None:
        """Test type mismatch when getting number from string flag."""
        details = await offline_client.get_number_details("string-flag", default=0.0)

        assert details.value == 0.0
        assert details.error_code == ErrorCode.TYPE_MISMATCH

    # Object/JSON evaluation tests
    @pytest.mark.asyncio
    async def test_get_object_value(self, offline_client: OfflineClient) -> None:
        """Test getting JSON/object flag value."""
        value = await offline_client.get_object_value("json-flag")
        assert value == {"nested": {"value": 123}}

    @pytest.mark.asyncio
    async def test_get_object_value_not_found(self, offline_client: OfflineClient) -> None:
        """Test getting object value for non-existent flag returns default."""
        default = {"fallback": True}
        value = await offline_client.get_object_value("nonexistent", default=default)
        assert value == default

    @pytest.mark.asyncio
    async def test_get_object_value_none_default(self, offline_client: OfflineClient) -> None:
        """Test getting object value with None default returns empty dict."""
        value = await offline_client.get_object_value("nonexistent")
        assert value == {}

    @pytest.mark.asyncio
    async def test_get_object_details(self, offline_client: OfflineClient) -> None:
        """Test getting object flag with details."""
        details = await offline_client.get_object_details("json-flag", default={})

        assert details.value == {"nested": {"value": 123}}
        assert details.flag_key == "json-flag"
        assert details.error_code is None

    @pytest.mark.asyncio
    async def test_get_object_type_mismatch(self, offline_client: OfflineClient) -> None:
        """Test type mismatch when getting object from boolean flag."""
        details = await offline_client.get_object_details("bool-flag", default={})

        assert details.value == {}
        assert details.error_code == ErrorCode.TYPE_MISMATCH

    # Convenience method tests
    @pytest.mark.asyncio
    async def test_is_enabled_true(self, offline_client: OfflineClient) -> None:
        """Test is_enabled returns True for enabled flag."""
        enabled = await offline_client.is_enabled("bool-flag")
        assert enabled is True

    @pytest.mark.asyncio
    async def test_is_enabled_false(self, offline_client: OfflineClient) -> None:
        """Test is_enabled returns False for disabled flag."""
        enabled = await offline_client.is_enabled("disabled-bool")
        assert enabled is False

    @pytest.mark.asyncio
    async def test_is_enabled_not_found(self, offline_client: OfflineClient) -> None:
        """Test is_enabled returns False for non-existent flag."""
        enabled = await offline_client.is_enabled("nonexistent")
        assert enabled is False

    # Bulk evaluation tests
    @pytest.mark.asyncio
    async def test_get_all_flags(self, offline_client: OfflineClient) -> None:
        """Test getting all active flags."""
        results = await offline_client.get_all_flags()

        # Should only include active flags (5 out of 6)
        assert len(results) == 5
        assert "bool-flag" in results
        assert "string-flag" in results
        assert "inactive-flag" not in results

    @pytest.mark.asyncio
    async def test_get_all_flags_with_context(self, offline_client: OfflineClient, context: EvaluationContext) -> None:
        """Test getting all flags with evaluation context."""
        results = await offline_client.get_all_flags(context=context)

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_get_flags_specific_keys(self, offline_client: OfflineClient) -> None:
        """Test getting specific flags by key."""
        results = await offline_client.get_flags(["bool-flag", "string-flag"])

        assert len(results) == 2
        assert "bool-flag" in results
        assert "string-flag" in results

    @pytest.mark.asyncio
    async def test_get_flags_missing_keys(self, offline_client: OfflineClient) -> None:
        """Test getting flags with some non-existent keys."""
        results = await offline_client.get_flags(["bool-flag", "nonexistent"])

        assert len(results) == 1
        assert "bool-flag" in results
        assert "nonexistent" not in results

    @pytest.mark.asyncio
    async def test_get_flags_empty_keys(self, offline_client: OfflineClient) -> None:
        """Test getting flags with empty keys list."""
        results = await offline_client.get_flags([])
        assert results == {}

    # Context merging tests
    @pytest.mark.asyncio
    async def test_evaluation_with_context(self, sample_flags: list[FeatureFlag], context: EvaluationContext) -> None:
        """Test flag evaluation with provided context."""
        client = OfflineClient(flags=sample_flags)
        value = await client.get_boolean_value("bool-flag", context=context)

        assert value is True

    @pytest.mark.asyncio
    async def test_context_merging_with_default(self, sample_flags: list[FeatureFlag]) -> None:
        """Test context merging with default context."""
        default_ctx = EvaluationContext(
            targeting_key="default-key",
            environment="staging",
        )
        client = OfflineClient(flags=sample_flags, default_context=default_ctx)

        call_ctx = EvaluationContext(targeting_key="call-key")

        # The call context should override default
        merged = client._merge_context(call_ctx)
        assert merged.targeting_key == "call-key"
        assert merged.environment == "staging"

    @pytest.mark.asyncio
    async def test_context_none_uses_default(self, sample_flags: list[FeatureFlag]) -> None:
        """Test that None context uses default context."""
        default_ctx = EvaluationContext(targeting_key="default-key")
        client = OfflineClient(flags=sample_flags, default_context=default_ctx)

        merged = client._merge_context(None)
        assert merged == default_ctx

    # Health check and lifecycle tests
    @pytest.mark.asyncio
    async def test_health_check_healthy(self, offline_client: OfflineClient) -> None:
        """Test health check returns True when not closed."""
        is_healthy = await offline_client.health_check()
        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_after_close(self, offline_client: OfflineClient) -> None:
        """Test health check returns False after close."""
        await offline_client.close()

        is_healthy = await offline_client.health_check()
        assert is_healthy is False

    @pytest.mark.asyncio
    async def test_close_clears_flags(self, offline_client: OfflineClient) -> None:
        """Test close clears the flags dictionary."""
        assert len(offline_client.flags) > 0

        await offline_client.close()

        assert len(offline_client.flags) == 0

    @pytest.mark.asyncio
    async def test_context_manager(self, sample_flags: list[FeatureFlag]) -> None:
        """Test async context manager protocol."""
        async with OfflineClient(flags=sample_flags) as client:
            assert await client.health_check() is True
            value = await client.get_boolean_value("bool-flag")
            assert value is True

        # After exiting context, client should be closed
        assert await client.health_check() is False

    # Edge cases and error handling
    @pytest.mark.asyncio
    async def test_evaluation_after_close(self, offline_client: OfflineClient) -> None:
        """Test evaluating flags after client is closed returns default."""
        await offline_client.close()

        value = await offline_client.get_boolean_value("bool-flag", default=True)
        # Flag was cleared, so should return default
        assert value is True

    @pytest.mark.asyncio
    async def test_flags_property(self, offline_client: OfflineClient) -> None:
        """Test flags property returns the flags dictionary."""
        flags = offline_client.flags

        assert isinstance(flags, dict)
        assert "bool-flag" in flags
        assert flags["bool-flag"].name == "Boolean Flag"


# -----------------------------------------------------------------------------
# _OfflineStorageAdapter Tests
# -----------------------------------------------------------------------------
class TestOfflineStorageAdapter:
    """Tests for _OfflineStorageAdapter internal class."""

    @pytest.fixture
    def sample_flags_dict(self) -> dict[str, FeatureFlag]:
        """Create sample flags dictionary."""
        now = datetime.now(UTC)
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
            created_at=now,
            updated_at=now,
        )
        flag2 = FeatureFlag(
            id=uuid4(),
            key="flag-2",
            name="Flag 2",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.INACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
            created_at=now,
            updated_at=now,
        )
        return {"flag-1": flag1, "flag-2": flag2}

    @pytest.fixture
    def adapter(self, sample_flags_dict: dict[str, FeatureFlag]) -> _OfflineStorageAdapter:
        """Create adapter instance."""
        return _OfflineStorageAdapter(sample_flags_dict)

    @pytest.mark.asyncio
    async def test_get_flag_exists(self, adapter: _OfflineStorageAdapter) -> None:
        """Test getting an existing flag."""
        flag = await adapter.get_flag("flag-1")

        assert flag is not None
        assert flag.key == "flag-1"

    @pytest.mark.asyncio
    async def test_get_flag_not_exists(self, adapter: _OfflineStorageAdapter) -> None:
        """Test getting a non-existent flag returns None."""
        flag = await adapter.get_flag("nonexistent")
        assert flag is None

    @pytest.mark.asyncio
    async def test_get_flags_multiple(self, adapter: _OfflineStorageAdapter) -> None:
        """Test getting multiple flags."""
        flags = await adapter.get_flags(["flag-1", "flag-2"])

        assert len(flags) == 2
        assert "flag-1" in flags
        assert "flag-2" in flags

    @pytest.mark.asyncio
    async def test_get_flags_partial(self, adapter: _OfflineStorageAdapter) -> None:
        """Test getting flags with some non-existent keys."""
        flags = await adapter.get_flags(["flag-1", "nonexistent"])

        assert len(flags) == 1
        assert "flag-1" in flags

    @pytest.mark.asyncio
    async def test_get_all_active_flags(self, adapter: _OfflineStorageAdapter) -> None:
        """Test getting all active flags."""
        flags = await adapter.get_all_active_flags()

        # Only flag-1 is active
        assert len(flags) == 1
        assert flags[0].key == "flag-1"

    @pytest.mark.asyncio
    async def test_get_override_returns_none(self, adapter: _OfflineStorageAdapter) -> None:
        """Test get_override always returns None."""
        override = await adapter.get_override(uuid4(), "user", "user-123")
        assert override is None

    @pytest.mark.asyncio
    async def test_health_check(self, adapter: _OfflineStorageAdapter) -> None:
        """Test health check returns True."""
        is_healthy = await adapter.health_check()
        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_close(self, adapter: _OfflineStorageAdapter) -> None:
        """Test close is a no-op that doesn't raise."""
        await adapter.close()  # Should not raise


# -----------------------------------------------------------------------------
# Integration Tests
# -----------------------------------------------------------------------------
class TestBootstrapIntegration:
    """Integration tests for bootstrap workflow."""

    @pytest.mark.asyncio
    async def test_full_bootstrap_workflow_from_dict(self) -> None:
        """Test complete workflow: config -> loader -> client -> evaluation."""
        # Define flags
        flag_data = {
            "flags": [
                {
                    "key": "feature-x",
                    "name": "Feature X",
                    "flag_type": "boolean",
                    "default_enabled": True,
                },
                {
                    "key": "api-limit",
                    "name": "API Limit",
                    "flag_type": "number",
                    "default_enabled": True,
                    "default_value": 100,
                },
            ]
        }

        # Create config
        config = BootstrapConfig(source=flag_data)

        # Load flags via client factory
        client = await OfflineClient.from_config(config)

        # Evaluate flags
        feature_enabled = await client.get_boolean_value("feature-x")
        api_limit = await client.get_number_value("api-limit")

        assert feature_enabled is True
        assert api_limit == 100

        await client.close()

    @pytest.mark.asyncio
    async def test_full_bootstrap_workflow_from_file(self) -> None:
        """Test complete workflow from JSON file."""
        flag_data = {
            "flags": [
                {
                    "key": "file-feature",
                    "name": "File Feature",
                    "flag_type": "string",
                    "default_enabled": True,
                    "default_value": "file-value",
                }
            ]
        }

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(flag_data, f)
            temp_path = Path(f.name)

        try:
            config = BootstrapConfig(source=temp_path)
            client = await OfflineClient.from_config(config)

            value = await client.get_string_value("file-feature")
            assert value == "file-value"

            await client.close()
        finally:
            temp_path.unlink()

    @pytest.mark.asyncio
    async def test_offline_client_with_evaluation_context(self) -> None:
        """Test offline client respects evaluation context."""
        flag_data = {
            "flags": [
                {
                    "key": "context-flag",
                    "name": "Context Flag",
                    "flag_type": "boolean",
                    "default_enabled": True,
                }
            ]
        }

        config = BootstrapConfig(source=flag_data)
        default_ctx = EvaluationContext(
            targeting_key="default-user",
            environment="test",
        )

        client = await OfflineClient.from_config(config, default_context=default_ctx)

        # Should work with default context
        value = await client.get_boolean_value("context-flag")
        assert value is True

        # Should work with explicit context
        custom_ctx = EvaluationContext(
            targeting_key="custom-user",
            attributes={"plan": "premium"},
        )
        value = await client.get_boolean_value("context-flag", context=custom_ctx)
        assert value is True

        await client.close()

    @pytest.mark.asyncio
    async def test_error_recovery_with_fallback(self) -> None:
        """Test error recovery when loading fails with fallback enabled."""
        # Invalid source path with fallback enabled
        config = BootstrapConfig(
            source=Path("/nonexistent/path/flags.json"),
            fallback_on_error=True,
        )

        # Should not raise, creates empty client
        client = await OfflineClient.from_config(config)

        assert len(client.flags) == 0

        # Evaluations should return defaults
        value = await client.get_boolean_value("any-flag", default=True)
        assert value is True

        await client.close()
