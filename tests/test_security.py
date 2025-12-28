"""Tests for the security module."""

from __future__ import annotations

import pytest

from litestar_flags.security import (
    SENSITIVE_FIELDS,
    create_safe_log_context,
    hash_targeting_key,
    hash_value,
    is_sensitive_field,
    redact_value,
    sanitize_error_message,
    sanitize_log_context,
    validate_flag_key,
)


class TestHashTargetingKey:
    """Tests for hash_targeting_key function."""

    def test_hash_basic_key(self) -> None:
        """Test hashing a basic targeting key."""
        result = hash_targeting_key("user-12345")

        assert result is not None
        assert len(result) == 12  # Truncated SHA-256
        assert result.isalnum()  # Only hex characters

    def test_hash_consistency(self) -> None:
        """Test that hashing is consistent for the same input."""
        key = "user-12345"
        result1 = hash_targeting_key(key)
        result2 = hash_targeting_key(key)

        assert result1 == result2

    def test_hash_different_keys(self) -> None:
        """Test that different keys produce different hashes."""
        hash1 = hash_targeting_key("user-12345")
        hash2 = hash_targeting_key("user-67890")

        assert hash1 != hash2

    def test_hash_with_salt(self) -> None:
        """Test hashing with salt."""
        key = "user-12345"
        hash_no_salt = hash_targeting_key(key)
        hash_with_salt = hash_targeting_key(key, salt="my-app")

        assert hash_no_salt != hash_with_salt

    def test_hash_empty_key(self) -> None:
        """Test hashing an empty key."""
        result = hash_targeting_key("")

        assert result == ""

    def test_hash_unicode_key(self) -> None:
        """Test hashing a Unicode key."""
        result = hash_targeting_key("user-12345-cafe")

        assert result is not None
        assert len(result) == 12


class TestHashValue:
    """Tests for hash_value function."""

    def test_hash_string_value(self) -> None:
        """Test hashing a string value."""
        result = hash_value("secret-value")

        assert result is not None
        assert len(result) == 12

    def test_hash_integer_value(self) -> None:
        """Test hashing an integer value."""
        result = hash_value(12345)

        assert result is not None
        assert len(result) == 12

    def test_hash_none_value(self) -> None:
        """Test hashing None."""
        result = hash_value(None)

        assert result == ""


class TestIsSensitiveField:
    """Tests for is_sensitive_field function."""

    @pytest.mark.parametrize(
        "field_name",
        [
            "email",
            "password",
            "token",
            "api_key",
            "user_id",
            "targeting_key",
            "secret",
            "session_id",
            "credit_card",
        ],
    )
    def test_sensitive_fields(self, field_name: str) -> None:
        """Test known sensitive fields are detected."""
        assert is_sensitive_field(field_name) is True

    @pytest.mark.parametrize(
        "field_name",
        [
            "plan",
            "country",
            "beta_tester",
            "age",
            "language",
            "theme",
        ],
    )
    def test_non_sensitive_fields(self, field_name: str) -> None:
        """Test non-sensitive fields are not flagged."""
        assert is_sensitive_field(field_name) is False

    def test_pattern_matching(self) -> None:
        """Test pattern-based detection."""
        assert is_sensitive_field("api_key") is True
        assert is_sensitive_field("auth_token") is True
        assert is_sensitive_field("client_secret") is True

    def test_case_insensitive(self) -> None:
        """Test case insensitivity."""
        assert is_sensitive_field("EMAIL") is True
        assert is_sensitive_field("Email") is True
        assert is_sensitive_field("email") is True

    def test_empty_field(self) -> None:
        """Test empty field name."""
        assert is_sensitive_field("") is False

    def test_id_suffix_pattern(self) -> None:
        """Test _id suffix pattern matching."""
        assert is_sensitive_field("custom_id") is True
        assert is_sensitive_field("account_id") is True


class TestRedactValue:
    """Tests for redact_value function."""

    def test_redact_basic(self) -> None:
        """Test basic redaction."""
        result = redact_value("secret")

        assert result == "[REDACTED]"

    def test_redact_none(self) -> None:
        """Test redacting None."""
        result = redact_value(None)

        assert result == "[REDACTED]"

    def test_redact_with_hash(self) -> None:
        """Test redaction with hashing instead."""
        result = redact_value("secret", hash_instead=True)

        assert result != "[REDACTED]"
        assert len(result) == 12


class TestSanitizeLogContext:
    """Tests for sanitize_log_context function."""

    def test_sanitize_basic_context(self) -> None:
        """Test sanitizing a basic context."""
        context = {
            "targeting_key": "user-123",
            "email": "user@example.com",
            "plan": "premium",
        }
        result = sanitize_log_context(context)

        # targeting_key should be hashed
        assert result["targeting_key"] != "user-123"
        assert len(result["targeting_key"]) == 12

        # email should be redacted
        assert result["email"] == "[REDACTED]"

        # plan should be preserved
        assert result["plan"] == "premium"

    def test_sanitize_empty_context(self) -> None:
        """Test sanitizing an empty context."""
        result = sanitize_log_context({})

        assert result == {}

    def test_sanitize_nested_context(self) -> None:
        """Test sanitizing nested dictionaries."""
        context = {
            "user": {
                "email": "user@example.com",
                "plan": "premium",
            },
            "metadata": {
                "version": "1.0",
            },
        }
        result = sanitize_log_context(context)

        assert result["user"]["email"] == "[REDACTED]"
        assert result["user"]["plan"] == "premium"
        assert result["metadata"]["version"] == "1.0"

    def test_sanitize_with_lists(self) -> None:
        """Test sanitizing contexts with lists."""
        context = {
            "items": [
                {"email": "user1@example.com", "name": "User 1"},
                {"email": "user2@example.com", "name": "User 2"},
            ],
        }
        result = sanitize_log_context(context)

        assert result["items"][0]["email"] == "[REDACTED]"
        assert result["items"][0]["name"] == "User 1"
        assert result["items"][1]["email"] == "[REDACTED]"

    def test_sanitize_without_hashing(self) -> None:
        """Test sanitization without hashing identifiers."""
        context = {
            "targeting_key": "user-123",
            "plan": "premium",
        }
        result = sanitize_log_context(context, hash_identifiers=False)

        # targeting_key should be redacted, not hashed
        assert result["targeting_key"] == "[REDACTED]"

    def test_sanitize_without_redaction(self) -> None:
        """Test sanitization without redaction."""
        context = {
            "targeting_key": "user-123",
            "email": "user@example.com",
        }
        result = sanitize_log_context(context, redact_sensitive=False)

        # Only identifiers should be hashed
        assert len(result["targeting_key"]) == 12
        assert result["email"] == "user@example.com"

    def test_sanitize_with_extra_fields(self) -> None:
        """Test sanitization with extra sensitive fields."""
        context = {
            "custom_secret": "my-secret",
            "plan": "premium",
        }
        result = sanitize_log_context(context, extra_sensitive_fields={"custom_secret"})

        assert result["custom_secret"] == "[REDACTED]"
        assert result["plan"] == "premium"

    def test_sanitize_with_salt(self) -> None:
        """Test sanitization with custom salt."""
        context = {
            "targeting_key": "user-123",
        }
        result1 = sanitize_log_context(context)
        result2 = sanitize_log_context(context, salt="custom-salt")

        # Different salts should produce different hashes
        assert result1["targeting_key"] != result2["targeting_key"]


class TestValidateFlagKey:
    """Tests for validate_flag_key function."""

    @pytest.mark.parametrize(
        "key",
        [
            "my-feature",
            "myFeature",
            "my_feature",
            "MyFeature123",
            "feature-123-test",
            "a",
        ],
    )
    def test_valid_keys(self, key: str) -> None:
        """Test valid flag keys."""
        assert validate_flag_key(key) is True

    @pytest.mark.parametrize(
        "key",
        [
            "",  # Empty
            "123-feature",  # Starts with number
            "-feature",  # Starts with hyphen
            "_feature",  # Starts with underscore
            "feature.test",  # Contains period
            "feature@test",  # Contains special char
            "feature test",  # Contains space
        ],
    )
    def test_invalid_keys(self, key: str) -> None:
        """Test invalid flag keys."""
        assert validate_flag_key(key) is False

    def test_max_length(self) -> None:
        """Test max length validation."""
        # 255 characters should be valid
        long_key = "a" * 255
        assert validate_flag_key(long_key) is True

        # 256 characters should be invalid
        too_long = "a" * 256
        assert validate_flag_key(too_long) is False


class TestSanitizeErrorMessage:
    """Tests for sanitize_error_message function."""

    def test_sanitize_file_path(self) -> None:
        """Test sanitizing file paths."""
        error = "Error in /home/user/project/file.py"
        result = sanitize_error_message(error)

        assert "/home/user/project/file.py" not in result
        assert "[path]" in result

    def test_sanitize_ip_address(self) -> None:
        """Test sanitizing IP addresses."""
        error = "Connection failed to 192.168.1.100:5432"
        result = sanitize_error_message(error)

        assert "192.168.1.100" not in result
        assert "[ip]" in result

    def test_sanitize_connection_string(self) -> None:
        """Test sanitizing connection strings."""
        error = "Failed to connect: redis://user:pass@host:6379/0"
        result = sanitize_error_message(error)

        assert "redis://user:pass@host:6379/0" not in result
        assert "[connection-string]" in result

    def test_sanitize_email(self) -> None:
        """Test sanitizing email addresses."""
        error = "Invalid email: user@example.com"
        result = sanitize_error_message(error)

        assert "user@example.com" not in result
        assert "[email]" in result

    def test_truncate_long_message(self) -> None:
        """Test truncating long messages."""
        error = "Error: " + "x" * 600
        result = sanitize_error_message(error)

        assert len(result) <= 503  # 500 + "..."


class TestCreateSafeLogContext:
    """Tests for create_safe_log_context function."""

    def test_create_basic_context(self) -> None:
        """Test creating a basic log context."""
        result = create_safe_log_context(
            flag_key="new-feature",
            targeting_key="user-123",
            result=True,
            reason="TARGETING_MATCH",
        )

        assert result["flag_key"] == "new-feature"
        assert result["result"] is True
        assert result["reason"] == "TARGETING_MATCH"
        assert "targeting_key_hash" in result
        assert len(result["targeting_key_hash"]) == 12

    def test_create_context_without_targeting_key(self) -> None:
        """Test creating context without targeting key."""
        result = create_safe_log_context(
            flag_key="new-feature",
            result=False,
        )

        assert result["flag_key"] == "new-feature"
        assert result["result"] is False
        assert "targeting_key_hash" not in result

    def test_create_context_with_extra(self) -> None:
        """Test creating context with extra fields."""
        result = create_safe_log_context(
            flag_key="new-feature",
            targeting_key="user-123",
            result=True,
            email="user@example.com",
            plan="premium",
        )

        assert result["email"] == "[REDACTED]"
        assert result["plan"] == "premium"


class TestSensitiveFieldsConstant:
    """Tests for the SENSITIVE_FIELDS constant."""

    def test_is_frozenset(self) -> None:
        """Test that SENSITIVE_FIELDS is immutable."""
        assert isinstance(SENSITIVE_FIELDS, frozenset)

    def test_contains_common_fields(self) -> None:
        """Test that common sensitive fields are included."""
        assert "email" in SENSITIVE_FIELDS
        assert "password" in SENSITIVE_FIELDS
        assert "token" in SENSITIVE_FIELDS
        assert "targeting_key" in SENSITIVE_FIELDS
        assert "user_id" in SENSITIVE_FIELDS

    def test_lowercase(self) -> None:
        """Test that all fields are lowercase."""
        for field in SENSITIVE_FIELDS:
            assert field == field.lower()
