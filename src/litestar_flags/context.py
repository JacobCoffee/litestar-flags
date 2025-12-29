"""Evaluation context for feature flag evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

__all__ = ["EvaluationContext"]


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    """Immutable context for flag evaluation.

    Follows OpenFeature specification patterns. The context provides
    attributes that can be used for targeting rules and percentage rollouts.

    Attributes:
        targeting_key: Primary identifier for consistent hashing in percentage rollouts.
        user_id: User identifier for user-level targeting.
        organization_id: Organization identifier for org-level targeting.
        tenant_id: Tenant identifier for multi-tenant applications.
        environment: Environment name (e.g., "production", "staging").
        app_version: Application version for version-based rollouts.
        attributes: Custom attributes for flexible targeting rules.
        ip_address: Client IP address (can be auto-populated by middleware).
        user_agent: Client user agent string.
        country: Country code (e.g., "US", "GB").
        timestamp: Evaluation timestamp for time-based rules.

    Example:
        >>> context = EvaluationContext(
        ...     targeting_key="user-123",
        ...     user_id="user-123",
        ...     attributes={"plan": "premium", "beta_tester": True},
        ... )
        >>> context.get("plan")
        'premium'

    """

    targeting_key: str | None = None
    user_id: str | None = None
    organization_id: str | None = None
    tenant_id: str | None = None
    environment: str | None = None
    app_version: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    ip_address: str | None = None
    user_agent: str | None = None
    country: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def get(self, key: str, default: Any = None) -> Any:
        """Get attribute by key, checking standard attributes first.

        Args:
            key: The attribute key to look up.
            default: Default value if attribute is not found.

        Returns:
            The attribute value or the default.

        """
        if hasattr(self, key) and key != "attributes":
            value = getattr(self, key)
            if value is not None:
                return value
        return self.attributes.get(key, default)

    def merge(self, other: EvaluationContext) -> EvaluationContext:
        """Merge with another context (other takes precedence).

        Creates a new context with values from both contexts,
        where the `other` context's values override this context's values.

        Args:
            other: The context to merge with (takes precedence).

        Returns:
            A new merged EvaluationContext.

        """
        merged_attrs = {**self.attributes, **other.attributes}
        return EvaluationContext(
            targeting_key=other.targeting_key or self.targeting_key,
            user_id=other.user_id or self.user_id,
            organization_id=other.organization_id or self.organization_id,
            tenant_id=other.tenant_id or self.tenant_id,
            environment=other.environment or self.environment,
            app_version=other.app_version or self.app_version,
            attributes=merged_attrs,
            ip_address=other.ip_address or self.ip_address,
            user_agent=other.user_agent or self.user_agent,
            country=other.country or self.country,
            timestamp=other.timestamp,
        )

    def with_targeting_key(self, targeting_key: str) -> EvaluationContext:
        """Create a new context with an updated targeting key.

        Args:
            targeting_key: The new targeting key.

        Returns:
            A new EvaluationContext with the updated targeting key.

        """
        return replace(self, targeting_key=targeting_key)

    def with_attributes(self, **kwargs: Any) -> EvaluationContext:
        """Create a new context with additional attributes.

        Args:
            **kwargs: Additional attributes to add.

        Returns:
            A new EvaluationContext with the additional attributes.

        """
        return replace(self, attributes={**self.attributes, **kwargs})

    def with_environment(self, environment: str) -> EvaluationContext:
        """Create a new context with the specified environment.

        This is useful for switching environments during request processing
        or for testing flag behavior in different environments.

        Args:
            environment: The environment name (e.g., "production", "staging").

        Returns:
            A new EvaluationContext with the updated environment.

        Example:
            >>> context = EvaluationContext(user_id="user-123")
            >>> staging_context = context.with_environment("staging")
            >>> staging_context.environment
            'staging'

        """
        return replace(self, environment=environment)
