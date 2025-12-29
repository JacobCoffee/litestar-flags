"""Tests for EvaluationContext."""

from __future__ import annotations

import pytest

from litestar_flags import EvaluationContext


class TestEvaluationContext:
    """Tests for EvaluationContext."""

    def test_create_empty_context(self) -> None:
        """Test creating an empty context."""
        context = EvaluationContext()
        assert context.targeting_key is None
        assert context.user_id is None
        assert context.attributes == {}

    def test_create_context_with_attributes(self) -> None:
        """Test creating a context with attributes."""
        context = EvaluationContext(
            targeting_key="user-123",
            user_id="user-123",
            attributes={"plan": "premium"},
        )
        assert context.targeting_key == "user-123"
        assert context.user_id == "user-123"
        assert context.attributes == {"plan": "premium"}

    def test_get_standard_attribute(self) -> None:
        """Test getting a standard attribute."""
        context = EvaluationContext(user_id="user-123")
        assert context.get("user_id") == "user-123"

    def test_get_custom_attribute(self) -> None:
        """Test getting a custom attribute."""
        context = EvaluationContext(attributes={"plan": "premium"})
        assert context.get("plan") == "premium"

    def test_get_missing_attribute(self) -> None:
        """Test getting a missing attribute with default."""
        context = EvaluationContext()
        assert context.get("missing") is None
        assert context.get("missing", "default") == "default"

    def test_merge_contexts(self) -> None:
        """Test merging two contexts."""
        ctx1 = EvaluationContext(
            targeting_key="user-123",
            attributes={"a": 1, "b": 2},
        )
        ctx2 = EvaluationContext(
            user_id="user-456",
            attributes={"b": 3, "c": 4},
        )
        merged = ctx1.merge(ctx2)

        # Other takes precedence for standard attrs
        assert merged.user_id == "user-456"
        # First's targeting_key is preserved if other is None
        assert merged.targeting_key == "user-123"
        # Attributes are merged with other taking precedence
        assert merged.attributes == {"a": 1, "b": 3, "c": 4}

    def test_with_targeting_key(self) -> None:
        """Test creating context with new targeting key."""
        ctx = EvaluationContext(
            targeting_key="old-key",
            user_id="user-123",
        )
        new_ctx = ctx.with_targeting_key("new-key")

        assert new_ctx.targeting_key == "new-key"
        assert new_ctx.user_id == "user-123"
        # Original unchanged
        assert ctx.targeting_key == "old-key"

    def test_with_attributes(self) -> None:
        """Test creating context with additional attributes."""
        ctx = EvaluationContext(attributes={"a": 1})
        new_ctx = ctx.with_attributes(b=2, c=3)

        assert new_ctx.attributes == {"a": 1, "b": 2, "c": 3}
        # Original unchanged
        assert ctx.attributes == {"a": 1}

    def test_context_is_frozen(self) -> None:
        """Test that context is immutable."""
        ctx = EvaluationContext(targeting_key="user-123")
        with pytest.raises(Exception):  # FrozenInstanceError
            ctx.targeting_key = "user-456"  # type: ignore[misc]

    def test_with_environment(self) -> None:
        """Test creating context with new environment."""
        ctx = EvaluationContext(
            targeting_key="user-123",
            user_id="user-123",
            environment="development",
        )
        new_ctx = ctx.with_environment("production")

        assert new_ctx.environment == "production"
        assert new_ctx.targeting_key == "user-123"
        assert new_ctx.user_id == "user-123"
        # Original unchanged
        assert ctx.environment == "development"

    def test_with_environment_preserves_attributes(self) -> None:
        """Test that with_environment preserves custom attributes."""
        ctx = EvaluationContext(
            targeting_key="user-123",
            attributes={"plan": "premium", "beta_tester": True},
        )
        new_ctx = ctx.with_environment("staging")

        assert new_ctx.environment == "staging"
        assert new_ctx.attributes == {"plan": "premium", "beta_tester": True}

    def test_with_environment_on_empty_context(self) -> None:
        """Test with_environment on an empty context."""
        ctx = EvaluationContext()
        new_ctx = ctx.with_environment("production")

        assert new_ctx.environment == "production"
        assert new_ctx.targeting_key is None
        assert new_ctx.user_id is None
