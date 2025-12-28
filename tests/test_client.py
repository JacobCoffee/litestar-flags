"""Tests for FeatureFlagClient."""

from __future__ import annotations

from litestar_flags import (
    EvaluationContext,
    EvaluationReason,
    FeatureFlagClient,
    MemoryStorageBackend,
)
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.types import ErrorCode


class TestFeatureFlagClient:
    """Tests for FeatureFlagClient."""

    async def test_get_boolean_value_flag_not_found(self, client: FeatureFlagClient) -> None:
        """Test getting a boolean value when flag doesn't exist."""
        result = await client.get_boolean_value("nonexistent", default=False)
        assert result is False

        result = await client.get_boolean_value("nonexistent", default=True)
        assert result is True

    async def test_get_boolean_details_flag_not_found(self, client: FeatureFlagClient) -> None:
        """Test getting boolean details when flag doesn't exist."""
        details = await client.get_boolean_details("nonexistent", default=False)

        assert details.value is False
        assert details.flag_key == "nonexistent"
        assert details.reason == EvaluationReason.DEFAULT
        assert details.error_code == ErrorCode.FLAG_NOT_FOUND

    async def test_get_boolean_value_simple_flag(
        self,
        client: FeatureFlagClient,
        storage: MemoryStorageBackend,
        simple_flag: FeatureFlag,
    ) -> None:
        """Test getting a boolean value from a simple flag."""
        await storage.create_flag(simple_flag)

        result = await client.get_boolean_value("test-flag")
        assert result is False  # default_enabled is False

    async def test_get_boolean_value_enabled_flag(
        self,
        client: FeatureFlagClient,
        storage: MemoryStorageBackend,
        enabled_flag: FeatureFlag,
    ) -> None:
        """Test getting a boolean value from an enabled flag."""
        await storage.create_flag(enabled_flag)

        result = await client.get_boolean_value("enabled-flag")
        assert result is True

    async def test_is_enabled_convenience_method(
        self,
        client: FeatureFlagClient,
        storage: MemoryStorageBackend,
        enabled_flag: FeatureFlag,
    ) -> None:
        """Test the is_enabled convenience method."""
        await storage.create_flag(enabled_flag)

        result = await client.is_enabled("enabled-flag")
        assert result is True

        result = await client.is_enabled("nonexistent")
        assert result is False

    async def test_targeting_rule_match(
        self,
        client: FeatureFlagClient,
        storage: MemoryStorageBackend,
        flag_with_rules: FeatureFlag,
        premium_context: EvaluationContext,
    ) -> None:
        """Test that targeting rules are evaluated."""
        await storage.create_flag(flag_with_rules)

        # Premium user should match first rule
        result = await client.get_boolean_value("rules-flag", context=premium_context)
        assert result is True

    async def test_targeting_rule_no_match(
        self,
        client: FeatureFlagClient,
        storage: MemoryStorageBackend,
        flag_with_rules: FeatureFlag,
        context: EvaluationContext,
    ) -> None:
        """Test that default is returned when no rules match."""
        await storage.create_flag(flag_with_rules)

        # Free UK user doesn't match any rules
        result = await client.get_boolean_value("rules-flag", context=context)
        assert result is False  # Falls through to default

    async def test_targeting_rule_details(
        self,
        client: FeatureFlagClient,
        storage: MemoryStorageBackend,
        flag_with_rules: FeatureFlag,
        premium_context: EvaluationContext,
    ) -> None:
        """Test detailed evaluation with targeting rules."""
        await storage.create_flag(flag_with_rules)

        details = await client.get_boolean_details("rules-flag", context=premium_context)

        assert details.value is True
        assert details.reason == EvaluationReason.TARGETING_MATCH
        assert details.variant == "Premium Users"

    async def test_client_never_throws(self, storage: MemoryStorageBackend) -> None:
        """Test that the client never throws exceptions."""

        # Create a broken storage that always errors
        class BrokenStorage(MemoryStorageBackend):
            async def get_flag(self, key: str) -> None:
                raise RuntimeError("Storage error")

        client = FeatureFlagClient(storage=BrokenStorage())

        # Should not raise, returns default
        result = await client.get_boolean_value("any-flag", default=True)
        assert result is True

        details = await client.get_boolean_details("any-flag", default=False)
        assert details.value is False
        assert details.reason == EvaluationReason.ERROR
        assert details.error_code == ErrorCode.GENERAL_ERROR

    async def test_get_all_flags(
        self,
        client: FeatureFlagClient,
        storage: MemoryStorageBackend,
        simple_flag: FeatureFlag,
        enabled_flag: FeatureFlag,
    ) -> None:
        """Test getting all active flags."""
        await storage.create_flag(simple_flag)
        await storage.create_flag(enabled_flag)

        results = await client.get_all_flags()

        assert len(results) == 2
        assert "test-flag" in results
        assert "enabled-flag" in results

    async def test_get_specific_flags(
        self,
        client: FeatureFlagClient,
        storage: MemoryStorageBackend,
        simple_flag: FeatureFlag,
        enabled_flag: FeatureFlag,
    ) -> None:
        """Test getting specific flags by key."""
        await storage.create_flag(simple_flag)
        await storage.create_flag(enabled_flag)

        results = await client.get_flags(["test-flag", "nonexistent"])

        assert len(results) == 1
        assert "test-flag" in results

    async def test_health_check(self, client: FeatureFlagClient) -> None:
        """Test client health check."""
        result = await client.health_check()
        assert result is True

    async def test_context_manager(self, storage: MemoryStorageBackend) -> None:
        """Test using client as async context manager."""
        async with FeatureFlagClient(storage=storage) as client:
            result = await client.get_boolean_value("test", default=True)
            assert result is True

        # Storage should be closed
        assert len(storage) == 0

    async def test_default_context(self, storage: MemoryStorageBackend, flag_with_rules: FeatureFlag) -> None:
        """Test using default context."""
        await storage.create_flag(flag_with_rules)

        # Client with premium default context
        default_ctx = EvaluationContext(
            targeting_key="default-user",
            attributes={"plan": "premium"},
        )
        client = FeatureFlagClient(storage=storage, default_context=default_ctx)

        # Should use default context
        result = await client.get_boolean_value("rules-flag")
        assert result is True

    async def test_context_merge(self, storage: MemoryStorageBackend, flag_with_rules: FeatureFlag) -> None:
        """Test that provided context merges with default."""
        await storage.create_flag(flag_with_rules)

        default_ctx = EvaluationContext(
            targeting_key="default-user",
            attributes={"plan": "free"},
        )
        client = FeatureFlagClient(storage=storage, default_context=default_ctx)

        # Override plan in call context
        call_ctx = EvaluationContext(attributes={"plan": "premium"})
        result = await client.get_boolean_value("rules-flag", context=call_ctx)
        assert result is True


class TestFeatureFlagClientEdgeCases:
    """Edge case tests for FeatureFlagClient."""

    # -------------------------------------------------------------------------
    # Type Mismatch Tests
    # -------------------------------------------------------------------------
    async def test_type_mismatch_string_on_boolean_flag(
        self,
        client: FeatureFlagClient,
        storage: MemoryStorageBackend,
        enabled_flag: FeatureFlag,
    ) -> None:
        """Test type mismatch when calling get_string_value on a boolean flag."""
        await storage.create_flag(enabled_flag)

        details = await client.get_string_details("enabled-flag", default="fallback")
        assert details.value == "fallback"
        assert details.reason == EvaluationReason.ERROR
        assert details.error_code == ErrorCode.TYPE_MISMATCH
        assert "Expected type 'string'" in str(details.error_message)

    async def test_type_mismatch_number_on_boolean_flag(
        self,
        client: FeatureFlagClient,
        storage: MemoryStorageBackend,
        enabled_flag: FeatureFlag,
    ) -> None:
        """Test type mismatch when calling get_number_value on a boolean flag."""
        await storage.create_flag(enabled_flag)

        details = await client.get_number_details("enabled-flag", default=42.0)
        assert details.value == 42.0
        assert details.reason == EvaluationReason.ERROR
        assert details.error_code == ErrorCode.TYPE_MISMATCH

    async def test_type_mismatch_object_on_boolean_flag(
        self,
        client: FeatureFlagClient,
        storage: MemoryStorageBackend,
        enabled_flag: FeatureFlag,
    ) -> None:
        """Test type mismatch when calling get_object_value on a boolean flag."""
        await storage.create_flag(enabled_flag)

        default_obj = {"key": "default"}
        details = await client.get_object_details("enabled-flag", default=default_obj)
        assert details.value == default_obj
        assert details.reason == EvaluationReason.ERROR
        assert details.error_code == ErrorCode.TYPE_MISMATCH

    async def test_boolean_type_skips_validation(
        self,
        client: FeatureFlagClient,
        storage: MemoryStorageBackend,
        flag_with_variants: FeatureFlag,
    ) -> None:
        """Test that boolean type skips type validation (returns variant value)."""
        await storage.create_flag(flag_with_variants)

        # Boolean type skips type validation per client implementation (line 346)
        details = await client.get_boolean_details("ab-test", default=False)

        # Since boolean skips type validation, evaluation proceeds and returns variant
        assert details.error_code != ErrorCode.TYPE_MISMATCH
        assert details.reason == EvaluationReason.SPLIT

    # -------------------------------------------------------------------------
    # String Details Tests
    # -------------------------------------------------------------------------
    async def test_get_string_details_flag_not_found(self, client: FeatureFlagClient) -> None:
        """Test get_string_details when flag doesn't exist."""
        details = await client.get_string_details("nonexistent", default="fallback")

        assert details.value == "fallback"
        assert details.flag_key == "nonexistent"
        assert details.reason == EvaluationReason.DEFAULT
        assert details.error_code == ErrorCode.FLAG_NOT_FOUND
        assert "not found" in str(details.error_message)

    async def test_get_string_value_with_various_defaults(self, client: FeatureFlagClient) -> None:
        """Test get_string_value with various default values."""
        result = await client.get_string_value("nonexistent", default="")
        assert result == ""

        long_string = "a" * 1000
        result = await client.get_string_value("nonexistent", default=long_string)
        assert result == long_string

        unicode_string = "Hello, World!"
        result = await client.get_string_value("nonexistent", default=unicode_string)
        assert result == unicode_string

    # -------------------------------------------------------------------------
    # Number Details Tests
    # -------------------------------------------------------------------------
    async def test_get_number_details_flag_not_found(self, client: FeatureFlagClient) -> None:
        """Test get_number_details when flag doesn't exist."""
        details = await client.get_number_details("nonexistent", default=99.5)

        assert details.value == 99.5
        assert details.flag_key == "nonexistent"
        assert details.reason == EvaluationReason.DEFAULT
        assert details.error_code == ErrorCode.FLAG_NOT_FOUND

    async def test_get_number_value_with_various_defaults(self, client: FeatureFlagClient) -> None:
        """Test get_number_value with various default values."""
        result = await client.get_number_value("nonexistent", default=0.0)
        assert result == 0.0

        result = await client.get_number_value("nonexistent", default=-42.5)
        assert result == -42.5

        result = await client.get_number_value("nonexistent", default=1e10)
        assert result == 1e10

    # -------------------------------------------------------------------------
    # Object Details Tests
    # -------------------------------------------------------------------------
    async def test_get_object_details_flag_not_found(self, client: FeatureFlagClient) -> None:
        """Test get_object_details when flag doesn't exist."""
        default_obj = {"nested": {"key": "value"}, "list": [1, 2, 3]}
        details = await client.get_object_details("nonexistent", default=default_obj)

        assert details.value == default_obj
        assert details.flag_key == "nonexistent"
        assert details.reason == EvaluationReason.DEFAULT
        assert details.error_code == ErrorCode.FLAG_NOT_FOUND

    async def test_get_object_value_with_various_defaults(self, client: FeatureFlagClient) -> None:
        """Test get_object_value with various default values."""
        result = await client.get_object_value("nonexistent", default=None)
        assert result == {}

        complex_obj = {
            "string": "value",
            "number": 42,
            "bool": True,
            "null": None,
            "array": [1, "two", 3.0],
            "nested": {"deep": {"deeper": "value"}},
        }
        result = await client.get_object_value("nonexistent", default=complex_obj)
        assert result == complex_obj

    # -------------------------------------------------------------------------
    # Never-Throw Pattern Tests
    # -------------------------------------------------------------------------
    async def test_never_throws_on_storage_get_flag_error(self, storage: MemoryStorageBackend) -> None:
        """Test that client never throws on storage get_flag errors."""

        class ErrorOnGetStorage(MemoryStorageBackend):
            async def get_flag(self, key: str) -> None:
                raise RuntimeError("Database connection failed")

        client = FeatureFlagClient(storage=ErrorOnGetStorage())

        assert await client.get_boolean_value("any", default=True) is True
        assert await client.get_string_value("any", default="safe") == "safe"
        assert await client.get_number_value("any", default=123.0) == 123.0
        assert await client.get_object_value("any", default={"safe": True}) == {"safe": True}

    async def test_never_throws_on_storage_timeout(self, storage: MemoryStorageBackend) -> None:
        """Test that client never throws on storage timeout errors."""

        class TimeoutStorage(MemoryStorageBackend):
            async def get_flag(self, key: str) -> None:
                raise TimeoutError("Storage timeout")

        client = FeatureFlagClient(storage=TimeoutStorage())

        details = await client.get_boolean_details("any", default=False)
        assert details.value is False
        assert details.reason == EvaluationReason.ERROR
        assert details.error_code == ErrorCode.GENERAL_ERROR

    async def test_never_throws_various_exception_types(self, storage: MemoryStorageBackend) -> None:
        """Test that client handles various exception types gracefully."""
        exception_types = [
            ValueError("Invalid value"),
            KeyError("Missing key"),
            TypeError("Wrong type"),
            AttributeError("Missing attribute"),
            OSError("IO error"),
        ]

        for exc in exception_types:

            class ExceptionStorage(MemoryStorageBackend):
                _exc = exc

                async def get_flag(self, key: str) -> None:
                    raise self._exc

            client = FeatureFlagClient(storage=ExceptionStorage())
            result = await client.get_boolean_value("any", default=True)
            assert result is True, f"Failed for exception type: {type(exc).__name__}"

    # -------------------------------------------------------------------------
    # Bulk Evaluation Tests
    # -------------------------------------------------------------------------
    async def test_get_all_flags_empty_storage(self, client: FeatureFlagClient) -> None:
        """Test get_all_flags with empty storage."""
        results = await client.get_all_flags()
        assert results == {}

    async def test_get_all_flags_with_context(
        self,
        client: FeatureFlagClient,
        storage: MemoryStorageBackend,
        flag_with_rules: FeatureFlag,
        premium_context: EvaluationContext,
    ) -> None:
        """Test get_all_flags with evaluation context."""
        await storage.create_flag(flag_with_rules)

        results = await client.get_all_flags(context=premium_context)

        assert "rules-flag" in results
        assert results["rules-flag"].value is True
        assert results["rules-flag"].reason == EvaluationReason.TARGETING_MATCH

    async def test_get_all_flags_with_evaluation_error(
        self,
        storage: MemoryStorageBackend,
        simple_flag: FeatureFlag,
        enabled_flag: FeatureFlag,
    ) -> None:
        """Test get_all_flags handles individual flag evaluation errors gracefully."""
        await storage.create_flag(simple_flag)
        await storage.create_flag(enabled_flag)

        from unittest.mock import patch

        client = FeatureFlagClient(storage=storage)
        original_evaluate_flag = client._evaluate_flag

        async def mock_evaluate_flag(flag, ctx):
            if flag.key == "test-flag":
                raise RuntimeError("Simulated evaluation error")
            return await original_evaluate_flag(flag, ctx)

        with patch.object(client, "_evaluate_flag", side_effect=mock_evaluate_flag):
            results = await client.get_all_flags()

        assert len(results) == 1
        assert "enabled-flag" in results
        assert "test-flag" not in results

    async def test_get_all_flags_storage_error(self, storage: MemoryStorageBackend) -> None:
        """Test get_all_flags when storage.get_all_active_flags fails."""

        class BrokenAllFlagsStorage(MemoryStorageBackend):
            async def get_all_active_flags(self) -> list:
                raise RuntimeError("Storage failure")

        client = FeatureFlagClient(storage=BrokenAllFlagsStorage())
        results = await client.get_all_flags()
        assert results == {}

    async def test_get_flags_storage_error(self, storage: MemoryStorageBackend) -> None:
        """Test get_flags when storage.get_flags fails."""

        class BrokenGetFlagsStorage(MemoryStorageBackend):
            async def get_flags(self, keys: list) -> dict:
                raise RuntimeError("Storage failure")

        client = FeatureFlagClient(storage=BrokenGetFlagsStorage())
        results = await client.get_flags(["flag1", "flag2"])
        assert results == {}

    async def test_get_flags_partial_results(
        self,
        client: FeatureFlagClient,
        storage: MemoryStorageBackend,
        simple_flag: FeatureFlag,
        enabled_flag: FeatureFlag,
    ) -> None:
        """Test get_flags returns only found flags."""
        await storage.create_flag(simple_flag)
        await storage.create_flag(enabled_flag)

        results = await client.get_flags(["test-flag", "nonexistent", "enabled-flag"])

        assert len(results) == 2
        assert "test-flag" in results
        assert "enabled-flag" in results
        assert "nonexistent" not in results

    async def test_get_flags_with_evaluation_error(
        self,
        storage: MemoryStorageBackend,
        simple_flag: FeatureFlag,
        enabled_flag: FeatureFlag,
    ) -> None:
        """Test get_flags handles individual flag evaluation errors gracefully."""
        await storage.create_flag(simple_flag)
        await storage.create_flag(enabled_flag)

        from unittest.mock import patch

        client = FeatureFlagClient(storage=storage)
        original_evaluate_flag = client._evaluate_flag

        async def mock_evaluate_flag(flag, ctx):
            if flag.key == "test-flag":
                raise RuntimeError("Simulated evaluation error")
            return await original_evaluate_flag(flag, ctx)

        with patch.object(client, "_evaluate_flag", side_effect=mock_evaluate_flag):
            results = await client.get_flags(["test-flag", "enabled-flag"])

        assert len(results) == 1
        assert "enabled-flag" in results
        assert "test-flag" not in results

    # -------------------------------------------------------------------------
    # Context Merging Precedence Tests
    # -------------------------------------------------------------------------
    async def test_context_merge_attributes_override(
        self,
        storage: MemoryStorageBackend,
        flag_with_rules: FeatureFlag,
    ) -> None:
        """Test that call context attributes override default context attributes."""
        await storage.create_flag(flag_with_rules)

        default_ctx = EvaluationContext(
            targeting_key="default-user",
            user_id="default-id",
            attributes={"plan": "free", "region": "us-east"},
        )
        client = FeatureFlagClient(storage=storage, default_context=default_ctx)

        call_ctx = EvaluationContext(attributes={"plan": "premium"})
        merged = client._merge_context(call_ctx)

        assert merged.targeting_key == "default-user"
        assert merged.user_id == "default-id"
        assert merged.attributes["plan"] == "premium"
        assert merged.attributes["region"] == "us-east"

    async def test_context_merge_targeting_key_override(
        self,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test that call context targeting_key overrides default."""
        default_ctx = EvaluationContext(targeting_key="default-key")
        client = FeatureFlagClient(storage=storage, default_context=default_ctx)

        call_ctx = EvaluationContext(targeting_key="call-key")
        merged = client._merge_context(call_ctx)

        assert merged.targeting_key == "call-key"

    async def test_context_merge_none_does_not_override(
        self,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test that None values in call context don't override defaults."""
        default_ctx = EvaluationContext(
            targeting_key="default-key",
            user_id="default-user",
            environment="production",
        )
        client = FeatureFlagClient(storage=storage, default_context=default_ctx)

        call_ctx = EvaluationContext()
        merged = client._merge_context(call_ctx)

        assert merged.targeting_key == "default-key"
        assert merged.user_id == "default-user"
        assert merged.environment == "production"

    async def test_context_merge_returns_default_when_no_context(
        self,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test that _merge_context returns default when context is None."""
        default_ctx = EvaluationContext(targeting_key="default-key")
        client = FeatureFlagClient(storage=storage, default_context=default_ctx)

        merged = client._merge_context(None)

        assert merged is default_ctx

    # -------------------------------------------------------------------------
    # Health Check Edge Cases
    # -------------------------------------------------------------------------
    async def test_health_check_after_close(self, storage: MemoryStorageBackend) -> None:
        """Test health check returns False after client is closed."""
        client = FeatureFlagClient(storage=storage)

        assert await client.health_check() is True

        await client.close()

        assert await client.health_check() is False

    async def test_health_check_storage_error(self, storage: MemoryStorageBackend) -> None:
        """Test health check returns False when storage health check fails."""

        class UnhealthyStorage(MemoryStorageBackend):
            async def health_check(self) -> bool:
                raise RuntimeError("Storage unhealthy")

        client = FeatureFlagClient(storage=UnhealthyStorage())
        assert await client.health_check() is False

    async def test_health_check_storage_returns_false(self, storage: MemoryStorageBackend) -> None:
        """Test health check returns False when storage returns False."""

        class UnhealthyStorage(MemoryStorageBackend):
            async def health_check(self) -> bool:
                return False

        client = FeatureFlagClient(storage=UnhealthyStorage())
        assert await client.health_check() is False

    # -------------------------------------------------------------------------
    # Client Lifecycle Tests
    # -------------------------------------------------------------------------
    async def test_close_idempotent(self, storage: MemoryStorageBackend) -> None:
        """Test that calling close multiple times is safe."""
        client = FeatureFlagClient(storage=storage)

        await client.close()
        await client.close()
        await client.close()

        assert await client.health_check() is False

    async def test_storage_property(self, client: FeatureFlagClient, storage: MemoryStorageBackend) -> None:
        """Test that storage property returns the storage backend."""
        assert client.storage is storage

    # -------------------------------------------------------------------------
    # EvaluationDetails Tests
    # -------------------------------------------------------------------------
    async def test_evaluation_details_is_error_property(self, client: FeatureFlagClient) -> None:
        """Test EvaluationDetails.is_error property."""
        details = await client.get_boolean_details("nonexistent", default=False)

        assert details.is_error is True
        assert details.is_default is True

    async def test_evaluation_details_is_default_property(
        self,
        client: FeatureFlagClient,
        storage: MemoryStorageBackend,
        enabled_flag: FeatureFlag,
    ) -> None:
        """Test EvaluationDetails.is_default property for successful evaluation."""
        await storage.create_flag(enabled_flag)

        details = await client.get_boolean_details("enabled-flag")

        assert details.is_error is False
        assert details.is_default is False

    async def test_evaluation_details_to_dict(self, client: FeatureFlagClient) -> None:
        """Test EvaluationDetails.to_dict method."""
        details = await client.get_boolean_details("nonexistent", default=True)

        result_dict = details.to_dict()

        assert result_dict["value"] is True
        assert result_dict["flag_key"] == "nonexistent"
        assert result_dict["reason"] == "DEFAULT"
        assert result_dict["error_code"] == "FLAG_NOT_FOUND"
        assert result_dict["error_message"] is not None

    # -------------------------------------------------------------------------
    # Flag with Override Tests
    # -------------------------------------------------------------------------
    async def test_override_evaluation(
        self,
        storage: MemoryStorageBackend,
        flag_with_override: FeatureFlag,
    ) -> None:
        """Test that user overrides are evaluated correctly."""
        await storage.create_flag(flag_with_override)

        for override in flag_with_override.overrides:
            await storage.create_override(override)

        client = FeatureFlagClient(storage=storage)

        override_ctx = EvaluationContext(targeting_key="user-123", user_id="user-123")
        details = await client.get_boolean_details("override-flag", context=override_ctx)

        assert details.value is True
        assert details.reason == EvaluationReason.OVERRIDE

    async def test_no_override_for_different_user(
        self,
        storage: MemoryStorageBackend,
        flag_with_override: FeatureFlag,
    ) -> None:
        """Test that users without override get default value."""
        await storage.create_flag(flag_with_override)

        for override in flag_with_override.overrides:
            await storage.create_override(override)

        client = FeatureFlagClient(storage=storage)

        other_ctx = EvaluationContext(targeting_key="user-999", user_id="user-999")
        details = await client.get_boolean_details("override-flag", context=other_ctx)

        assert details.value is False

    # -------------------------------------------------------------------------
    # Default Values Edge Cases
    # -------------------------------------------------------------------------
    async def test_boolean_default_true(self, client: FeatureFlagClient) -> None:
        """Test boolean flag with True as default."""
        result = await client.get_boolean_value("nonexistent", default=True)
        assert result is True

    async def test_boolean_default_false(self, client: FeatureFlagClient) -> None:
        """Test boolean flag with False as default."""
        result = await client.get_boolean_value("nonexistent", default=False)
        assert result is False

    async def test_is_enabled_always_defaults_false(self, client: FeatureFlagClient) -> None:
        """Test is_enabled convenience method always defaults to False."""
        result = await client.is_enabled("nonexistent")
        assert result is False

    async def test_empty_string_default(self, client: FeatureFlagClient) -> None:
        """Test string flag with empty string default."""
        result = await client.get_string_value("nonexistent", default="")
        assert result == ""

    async def test_zero_default(self, client: FeatureFlagClient) -> None:
        """Test number flag with zero default."""
        result = await client.get_number_value("nonexistent", default=0.0)
        assert result == 0.0

    async def test_empty_dict_default(self, client: FeatureFlagClient) -> None:
        """Test object flag with empty dict default."""
        result = await client.get_object_value("nonexistent", default={})
        assert result == {}
