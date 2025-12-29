"""Environment inheritance resolution for feature flags.

This module provides the InheritanceResolver class for resolving flag values
with environment inheritance. It walks up the inheritance chain from child
environments to parent environments to find the effective configuration.

Example:
    >>> from litestar_flags import StorageBackend
    >>> from litestar_flags.environment_resolver import InheritanceResolver
    >>>
    >>> storage: StorageBackend = ...
    >>> resolver = InheritanceResolver(storage)
    >>>
    >>> # Get the inheritance chain for dev
    >>> chain = await resolver.get_inheritance_chain("dev")
    >>> # chain = [dev, staging, production] if dev -> staging -> production
    >>>
    >>> # Resolve a flag with inheritance
    >>> flag, env_flag = await resolver.resolve_flag(my_flag, "dev")
    >>> # flag has dev-specific overrides applied (or inherited from staging/production)

"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from uuid import UUID

    from litestar_flags.models.environment import Environment
    from litestar_flags.models.environment_flag import EnvironmentFlag
    from litestar_flags.models.flag import FeatureFlag
    from litestar_flags.protocols import StorageBackend

__all__ = ["InheritanceResolver"]


class InheritanceResolver:
    """Resolves flag values with environment inheritance.

    When a flag is evaluated in an environment, this resolver:
    1. Checks for environment-specific overrides
    2. If not found, walks up the inheritance chain to parent environments
    3. Falls back to the base flag configuration if no overrides exist

    Example inheritance chain: dev -> staging -> production
    If evaluating in 'dev' and no dev override exists, check staging, then production.

    Attributes:
        storage: The storage backend for fetching environments and flags.
        max_depth: Maximum inheritance depth to prevent cycles.

    Example:
        >>> resolver = InheritanceResolver(storage, max_depth=10)
        >>> chain = await resolver.get_inheritance_chain("staging")
        >>> # chain might be [staging, production] if staging inherits from production
        >>>
        >>> flag, env_override = await resolver.resolve_flag(my_flag, "staging")
        >>> # flag has staging or production overrides applied

    """

    def __init__(self, storage: StorageBackend, max_depth: int = 10) -> None:
        """Initialize the resolver.

        Args:
            storage: Storage backend for fetching environments and flags.
            max_depth: Maximum inheritance depth to prevent cycles (default 10).
                If the chain exceeds this depth, traversal stops.

        """
        self.storage = storage
        self.max_depth = max_depth

    async def get_inheritance_chain(self, environment_slug: str) -> list[Environment]:
        """Get the full inheritance chain for an environment.

        Walks the parent chain starting from the specified environment up to
        the root (an environment with no parent). Stops if the chain exceeds
        max_depth or if a circular reference is detected.

        Args:
            environment_slug: The environment to start from.

        Returns:
            List of environments from child to root (e.g., [dev, staging, production]).
            Returns an empty list if the environment is not found.

        Example:
            >>> chain = await resolver.get_inheritance_chain("dev")
            >>> # If dev -> staging -> production:
            >>> # chain = [<dev>, <staging>, <production>]
            >>> for env in chain:
            ...     print(f"  {env.slug}")

        """
        chain: list[Environment] = []
        current_slug: str | None = environment_slug
        seen_ids: set[UUID] = set()

        for _ in range(self.max_depth):
            if current_slug is None:
                break

            env = await self.storage.get_environment(current_slug)
            if env is None:
                break

            # Cycle detection - stop if we've seen this environment before
            if env.id in seen_ids:
                break
            seen_ids.add(env.id)
            chain.append(env)

            if env.parent_id is None:
                break

            # Get parent by ID to continue traversal
            parent = await self.storage.get_environment_by_id(env.parent_id)
            if parent is None:
                break
            current_slug = parent.slug

        return chain

    async def resolve_flag(
        self,
        flag: FeatureFlag,
        environment_slug: str | None,
    ) -> tuple[FeatureFlag, EnvironmentFlag | None]:
        """Resolve a flag with environment inheritance.

        Finds the effective environment override for the flag (if any) by
        walking the inheritance chain from child to parent. Returns the first
        override found applied to a copy of the flag, along with the override
        itself for reference.

        Args:
            flag: The base flag to resolve.
            environment_slug: The environment to evaluate in (None = use base flag).

        Returns:
            Tuple of (effective flag config, environment override if applied).
            The original flag is not modified.

        Example:
            >>> resolved_flag, env_override = await resolver.resolve_flag(
            ...     flag=my_flag,
            ...     environment_slug="staging",
            ... )
            >>> if env_override:
            ...     print(f"Override from environment: {env_override.environment_id}")
            >>> print(f"Flag enabled: {resolved_flag.default_enabled}")

        """
        if environment_slug is None:
            return flag, None

        chain = await self.get_inheritance_chain(environment_slug)

        # Walk the chain from child to parent looking for overrides
        for env in chain:
            env_flag = await self.storage.get_environment_flag(env.id, flag.id)
            if env_flag is not None:
                # Apply the override to a copy of the flag
                resolved_flag = self._apply_override(flag, env_flag)
                return resolved_flag, env_flag

        # No overrides found, return a copy of the base flag
        return deepcopy(flag), None

    def _apply_override(self, flag: FeatureFlag, override: EnvironmentFlag) -> FeatureFlag:
        """Apply environment override to a flag.

        Creates a copy of the base flag and applies any non-None values
        from the environment override. Fields set to None in the override
        are inherited from the base flag.

        Args:
            flag: The base flag to apply overrides to.
            override: The environment-specific override with values to apply.

        Returns:
            A new FeatureFlag instance with override values applied.
            The original flag is not modified.

        """
        # Check if this is a dataclass (has __dataclass_fields__) or ORM model
        # For dataclasses, we can use replace() if available
        # For ORM models, we use deepcopy and attribute assignment
        from litestar_flags.models.base import HAS_ADVANCED_ALCHEMY

        if HAS_ADVANCED_ALCHEMY:
            # SQLAlchemy ORM model - use deepcopy and assignment
            return self._apply_override_orm(flag, override)
        else:
            # Dataclass model - use replace
            return self._apply_override_dataclass(flag, override)

    def _apply_override_dataclass(self, flag: FeatureFlag, override: EnvironmentFlag) -> FeatureFlag:
        """Apply override to a dataclass flag model.

        Uses dataclasses.replace() for efficient copy-with-modifications.

        Args:
            flag: The base flag (dataclass instance).
            override: The environment override to apply.

        Returns:
            A new FeatureFlag dataclass with overrides applied.

        """
        from dataclasses import replace

        updates: dict[str, Any] = {}

        if override.enabled is not None:
            updates["default_enabled"] = override.enabled

        if override.rules is not None:
            updates["rules"] = override.rules

        if override.variants is not None:
            updates["variants"] = override.variants

        # Cast to Any to satisfy type checker - at runtime this is always a dataclass
        # when HAS_ADVANCED_ALCHEMY is False
        if updates:
            return cast("FeatureFlag", replace(cast(Any, flag), **updates))
        return cast("FeatureFlag", replace(cast(Any, flag)))  # Return a copy even with no updates

    def _apply_override_orm(self, flag: FeatureFlag, override: EnvironmentFlag) -> FeatureFlag:
        """Apply override to an SQLAlchemy ORM flag model.

        Uses deepcopy for ORM models since replace() is not available.

        Args:
            flag: The base flag (ORM model instance).
            override: The environment override to apply.

        Returns:
            A copy of the FeatureFlag with overrides applied.

        """
        # Create a deep copy to avoid mutating the original
        merged = deepcopy(flag)

        # Apply enabled override
        if override.enabled is not None:
            merged.default_enabled = override.enabled

        # Apply rules override if provided
        if override.rules is not None:
            self._apply_rules_override(merged, override.rules)

        # Apply variants override if provided
        if override.variants is not None:
            self._apply_variants_override(merged, override.variants)

        return merged

    def _apply_rules_override(self, flag: FeatureFlag, rules_data: Any) -> None:
        """Apply rules override to a flag.

        Handles both list[dict] (from JSON storage) and list[FlagRule] formats.

        Args:
            flag: The feature flag to modify.
            rules_data: The rules data from the environment override.

        """
        from litestar_flags.models.rule import FlagRule

        # If rules_data is already a list of FlagRule instances, use directly
        if rules_data and isinstance(rules_data[0], FlagRule):
            flag.rules = rules_data  # type: ignore[misc]
            return

        # Convert dict data to FlagRule instances
        flag.rules = [  # type: ignore[misc]
            FlagRule(
                flag_id=flag.id,
                name=rule.get("name", ""),
                conditions=rule.get("conditions", []),
                priority=rule.get("priority", 0),
                enabled=rule.get("enabled", True),
                rollout_percentage=rule.get("rollout_percentage"),
                serve_enabled=rule.get("serve_enabled", True),
                serve_value=rule.get("serve_value"),
            )
            for rule in rules_data
        ]

    def _apply_variants_override(self, flag: FeatureFlag, variants_data: Any) -> None:
        """Apply variants override to a flag.

        Handles both list[dict] (from JSON storage) and list[FlagVariant] formats.

        Args:
            flag: The feature flag to modify.
            variants_data: The variants data from the environment override.

        """
        from litestar_flags.models.variant import FlagVariant

        # If variants_data is already a list of FlagVariant instances, use directly
        if variants_data and isinstance(variants_data[0], FlagVariant):
            flag.variants = variants_data  # type: ignore[misc]
            return

        # Convert dict data to FlagVariant instances
        flag.variants = [  # type: ignore[misc]
            FlagVariant(
                flag_id=flag.id,
                key=variant.get("key", ""),
                value=variant.get("value", {}),
                weight=variant.get("weight", 0),
                description=variant.get("description"),
            )
            for variant in variants_data
        ]
