"""Security utilities for litestar-flags.

This module provides utilities for handling sensitive data securely,
including hashing identifiers for logs, sanitizing log contexts,
and managing sensitive field lists.

Example:
    Hashing a targeting key for logging::

        from litestar_flags.security import hash_targeting_key

        # Instead of logging the raw user ID
        hashed = hash_targeting_key("user-12345")
        logger.info(f"Evaluated flag for user: {hashed}")

    Sanitizing evaluation context for logs::

        from litestar_flags.security import sanitize_log_context

        context_dict = {
            "targeting_key": "user-secret-id",
            "email": "user@example.com",
            "plan": "premium",
        }
        safe_context = sanitize_log_context(context_dict)
        # safe_context = {
        #     "targeting_key": "a1b2c3...",  # hashed
        #     "email": "[REDACTED]",
        #     "plan": "premium",  # preserved
        # }

"""

from __future__ import annotations

import hashlib
import re
from typing import Any

__all__ = [
    "SENSITIVE_FIELDS",
    "SENSITIVE_PATTERNS",
    "hash_targeting_key",
    "is_sensitive_field",
    "redact_value",
    "sanitize_log_context",
    "validate_flag_key",
]

# -----------------------------------------------------------------------------
# Sensitive Field Configuration
# -----------------------------------------------------------------------------

#: Fields that should be redacted or hashed in logs
SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {
        # User identifiers
        "targeting_key",
        "user_id",
        "user",
        "userid",
        "username",
        "email",
        "email_address",
        # Organization identifiers
        "organization_id",
        "org_id",
        "tenant_id",
        "tenant",
        "account_id",
        # Authentication
        "password",
        "token",
        "api_key",
        "apikey",
        "secret",
        "secret_key",
        "access_token",
        "refresh_token",
        "session_id",
        "session",
        "auth",
        "authorization",
        "bearer",
        "jwt",
        "credential",
        "credentials",
        # Personal information
        "phone",
        "phone_number",
        "address",
        "ssn",
        "social_security",
        "ip",
        "ip_address",
        "device_id",
        "fingerprint",
        "location",
        "latitude",
        "longitude",
        "credit_card",
        "card_number",
        # Generic sensitive patterns
        "private",
        "sensitive",
    }
)

#: Regex patterns for detecting sensitive field names
SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r".*_key$", re.IGNORECASE),
    re.compile(r".*_token$", re.IGNORECASE),
    re.compile(r".*_secret$", re.IGNORECASE),
    re.compile(r".*_password$", re.IGNORECASE),
    re.compile(r".*_id$", re.IGNORECASE),  # Entity IDs may be sensitive
    re.compile(r"^x-.*", re.IGNORECASE),  # Custom headers
)

#: Default redaction placeholder
REDACTED_PLACEHOLDER: str = "[REDACTED]"

#: Prefix length for hashed values display
HASH_DISPLAY_LENGTH: int = 12


# -----------------------------------------------------------------------------
# Hashing Functions
# -----------------------------------------------------------------------------


def hash_targeting_key(key: str, salt: str = "") -> str:
    """Hash a targeting key for safe logging.

    Uses SHA-256 truncated to provide a consistent, irreversible
    identifier that can be used in logs without exposing the
    original value.

    Args:
        key: The targeting key or identifier to hash.
        salt: Optional salt to add to the hash. Use a consistent
            salt per application for reproducible hashes.

    Returns:
        A truncated SHA-256 hash of the key (12 hex characters).

    Example:
        >>> hash_targeting_key("user-12345")
        'a1b2c3d4e5f6'
        >>> hash_targeting_key("user-12345", salt="my-app")
        'f6e5d4c3b2a1'

    """
    if not key:
        return ""

    # Combine key with salt
    data = f"{salt}:{key}" if salt else key

    # Hash using SHA-256
    hash_bytes = hashlib.sha256(data.encode("utf-8")).hexdigest()

    # Return truncated hash for readability
    return hash_bytes[:HASH_DISPLAY_LENGTH]


def hash_value(value: Any, salt: str = "") -> str:
    """Hash any value for safe logging.

    Converts the value to string and hashes it.

    Args:
        value: The value to hash.
        salt: Optional salt for the hash.

    Returns:
        A truncated SHA-256 hash of the value.

    """
    if value is None:
        return ""

    return hash_targeting_key(str(value), salt)


# -----------------------------------------------------------------------------
# Field Detection
# -----------------------------------------------------------------------------


def is_sensitive_field(field_name: str) -> bool:
    """Check if a field name indicates sensitive data.

    Args:
        field_name: The name of the field to check.

    Returns:
        True if the field should be treated as sensitive.

    Example:
        >>> is_sensitive_field("email")
        True
        >>> is_sensitive_field("plan")
        False
        >>> is_sensitive_field("api_key")
        True

    """
    if not field_name:
        return False

    # Normalize field name
    normalized = field_name.lower().strip()

    # Check against known sensitive fields
    if normalized in SENSITIVE_FIELDS:
        return True

    # Check against sensitive patterns
    return any(pattern.match(normalized) for pattern in SENSITIVE_PATTERNS)


# -----------------------------------------------------------------------------
# Redaction Functions
# -----------------------------------------------------------------------------


def redact_value(value: Any, hash_instead: bool = False, salt: str = "") -> str:
    """Redact a sensitive value.

    Args:
        value: The value to redact.
        hash_instead: If True, hash the value instead of replacing
            with placeholder. Useful for correlation in logs.
        salt: Salt for hashing (only used if hash_instead=True).

    Returns:
        Either the redaction placeholder or a hashed version.

    """
    if value is None:
        return REDACTED_PLACEHOLDER

    if hash_instead:
        return hash_value(value, salt)

    return REDACTED_PLACEHOLDER


def sanitize_log_context(
    context: dict[str, Any],
    *,
    hash_identifiers: bool = True,
    redact_sensitive: bool = True,
    extra_sensitive_fields: set[str] | None = None,
    salt: str = "",
) -> dict[str, Any]:
    """Sanitize an evaluation context dictionary for safe logging.

    Processes a context dictionary and either hashes or redacts
    sensitive fields based on configuration.

    Args:
        context: The context dictionary to sanitize.
        hash_identifiers: If True, hash identifier fields (targeting_key,
            user_id, etc.) instead of redacting them.
        redact_sensitive: If True, redact sensitive fields. If False,
            leave sensitive fields unchanged.
        extra_sensitive_fields: Additional field names to treat as sensitive.
        salt: Salt for hashing identifiers.

    Returns:
        A new dictionary with sensitive data handled appropriately.

    Example:
        >>> context = {
        ...     "targeting_key": "user-123",
        ...     "email": "user@example.com",
        ...     "plan": "premium",
        ... }
        >>> sanitize_log_context(context)
        {
            'targeting_key': 'a1b2c3d4e5f6',
            'email': '[REDACTED]',
            'plan': 'premium',
        }

    """
    if not context:
        return {}

    # Identifier fields that should be hashed for correlation
    identifier_fields = {"targeting_key", "user_id", "organization_id", "tenant_id"}

    result: dict[str, Any] = {}

    for key, value in context.items():
        normalized_key = key.lower().strip()

        # Handle nested dictionaries recursively
        if isinstance(value, dict):
            result[key] = sanitize_log_context(
                value,
                hash_identifiers=hash_identifiers,
                redact_sensitive=redact_sensitive,
                extra_sensitive_fields=extra_sensitive_fields,
                salt=salt,
            )
            continue

        # Handle lists
        if isinstance(value, list):
            result[key] = [
                sanitize_log_context(
                    item,
                    hash_identifiers=hash_identifiers,
                    redact_sensitive=redact_sensitive,
                    extra_sensitive_fields=extra_sensitive_fields,
                    salt=salt,
                )
                if isinstance(item, dict)
                else item
                for item in value
            ]
            continue

        # Check if this is an identifier field that should be hashed
        if hash_identifiers and normalized_key in identifier_fields:
            result[key] = hash_value(value, salt) if value else ""
            continue

        # Check if this is a sensitive field
        if redact_sensitive and is_sensitive_field(key):
            result[key] = REDACTED_PLACEHOLDER
            continue

        # Check against extra sensitive fields
        if redact_sensitive and extra_sensitive_fields and normalized_key in extra_sensitive_fields:
            result[key] = REDACTED_PLACEHOLDER
            continue

        # Keep non-sensitive values as-is
        result[key] = value

    return result


# -----------------------------------------------------------------------------
# Input Validation
# -----------------------------------------------------------------------------


#: Valid flag key pattern (alphanumeric, hyphens, underscores)
FLAG_KEY_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,254}$")


def validate_flag_key(key: str) -> bool:
    """Validate a flag key for safe use.

    Flag keys must:
    - Start with a letter
    - Contain only alphanumeric characters, hyphens, and underscores
    - Be between 1 and 255 characters

    Args:
        key: The flag key to validate.

    Returns:
        True if the key is valid, False otherwise.

    Example:
        >>> validate_flag_key("my-feature-flag")
        True
        >>> validate_flag_key("123-invalid")
        False
        >>> validate_flag_key("")
        False

    """
    if not key:
        return False

    return bool(FLAG_KEY_PATTERN.match(key))


def sanitize_error_message(error: str | Exception) -> str:
    """Sanitize an error message to remove sensitive information.

    Removes potential file paths, stack traces, and other
    internal details from error messages.

    Args:
        error: The error message or exception to sanitize.

    Returns:
        A sanitized error message safe for logging/display.

    """
    message = str(error)

    # Remove potential connection strings (must be before paths to avoid partial matches)
    message = re.sub(r"(redis|postgresql|mysql|mongodb)://[^\s]+", "[connection-string]", message)

    # Remove potential email addresses (must be before paths to avoid partial matches)
    message = re.sub(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[email]", message)

    # Remove file paths (Unix and Windows)
    message = re.sub(r"(/[a-zA-Z0-9_./\-]+)+", "[path]", message)
    message = re.sub(r"([A-Za-z]:\\[a-zA-Z0-9_.\\\-]+)+", "[path]", message)

    # Remove potential IP addresses
    message = re.sub(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "[ip]", message)

    # Truncate very long messages
    max_length = 500
    if len(message) > max_length:
        message = message[:max_length] + "..."

    return message


# -----------------------------------------------------------------------------
# Context Helpers
# -----------------------------------------------------------------------------


def create_safe_log_context(
    flag_key: str,
    targeting_key: str | None = None,
    result: Any = None,
    reason: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Create a safe log context for flag evaluation logging.

    Convenience function for creating standardized log entries
    that automatically handle sensitive data.

    Args:
        flag_key: The evaluated flag key.
        targeting_key: The targeting key (will be hashed).
        result: The evaluation result.
        reason: The evaluation reason.
        **extra: Additional context to include (will be sanitized).

    Returns:
        A dictionary safe for logging.

    Example:
        >>> context = create_safe_log_context(
        ...     flag_key="new-feature",
        ...     targeting_key="user-123",
        ...     result=True,
        ...     reason="TARGETING_MATCH",
        ... )
        >>> logger.info("Flag evaluated", extra=context)

    """
    log_context: dict[str, Any] = {
        "flag_key": flag_key,
        "result": result,
    }

    if targeting_key:
        log_context["targeting_key_hash"] = hash_targeting_key(targeting_key)

    if reason:
        log_context["reason"] = reason

    # Sanitize and merge extra context
    if extra:
        sanitized_extra = sanitize_log_context(extra)
        log_context.update(sanitized_extra)

    return log_context
