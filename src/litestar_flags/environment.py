"""Environment resolver for multi-environment flag management.

This module provides the EnvironmentResolver class for resolving feature flags
with environment-specific overrides applied. It supports hierarchical environment
inheritance where child environments can override parent settings.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from litestar_flags.models.environment import Environment
    from litestar_flags.models.environment_flag import EnvironmentFlag
    from litestar_flags.models.flag import FeatureFlag
    from litestar_flags.protocols import StorageBackend

__all__ = [
    "CircularEnvironmentInheritanceError",
    "EnvironmentResolver",
    "merge_environment_flag",
]


class CircularEnvironmentInheritanceError(ValueError):
    """Raised when circular environment inheritance is detected.

    This error occurs when traversing the environment inheritance chain
    and an environment references itself either directly or through a
    chain of parent environments.

    Attributes:
        environment_slug: The slug of the environment where the cycle was detected.
        visited_chain: The list of environment slugs in the order they were visited.

    Example:
        If environment A has parent B, and B has parent A, traversing
        either will raise this error with the circular chain in visited_chain.

    """

    def __init__(self, environment_slug: str, visited_chain: list[str]) -> None:
        """Initialize the circular inheritance error.

        Args:
            environment_slug: The environment slug that caused the circular reference.
            visited_chain: The chain of environment slugs visited before detection.

        """
        self.environment_slug = environment_slug
        self.visited_chain = visited_chain
        chain_str = " -> ".join(visited_chain)
        super().__init__(f"Circular environment inheritance detected: {chain_str} -> {environment_slug}")


class EnvironmentResolver:
    """Resolves feature flags with environment-specific overrides.

    The EnvironmentResolver handles the hierarchical resolution of feature
    flags across environments. It walks the inheritance chain from the most
    specific environment (child) to the least specific (root parent) and
    applies the first found override.

    Features:
        - Hierarchical environment inheritance
        - First-match override resolution (most specific wins)
        - Circular inheritance detection
        - Optional environment caching for performance

    Example:
        >>> resolver = EnvironmentResolver(storage)
        >>> # Get the inheritance chain for staging
        >>> chain = await resolver.get_environment_chain("staging")
        >>> # chain might be [staging, dev, production] if staging -> dev -> production
        >>>
        >>> # Resolve a flag for staging environment
        >>> resolved_flag = await resolver.resolve_flag_for_environment(
        ...     flag=my_flag,
        ...     environment_slug="staging",
        ... )

    """

    def __init__(self, storage: StorageBackend) -> None:
        """Initialize the environment resolver.

        Args:
            storage: The storage backend for fetching environments and flags.

        """
        self._storage = storage

    async def get_environment(self, slug: str) -> Environment | None:
        """Get an environment by slug.

        Args:
            slug: The unique URL-safe identifier for the environment.

        Returns:
            The Environment if found, None otherwise.

        Example:
            >>> env = await resolver.get_environment("production")
            >>> if env:
            ...     print(f"Found environment: {env.name}")

        """
        return await self._storage.get_environment(slug)

    async def get_environment_chain(
        self,
        slug: str,
        _visited: set[str] | None = None,
    ) -> list[Environment]:
        """Get the inheritance chain for an environment from child to root.

        Walks the parent chain starting from the specified environment up to
        the root (an environment with no parent). Detects and raises an error
        if circular inheritance is detected.

        Args:
            slug: The slug of the environment to start from.
            _visited: Internal parameter for circular reference detection.
                Should not be provided by external callers.

        Returns:
            List of environments ordered from child (most specific) to root
            (least specific). Returns an empty list if the environment is
            not found.

        Raises:
            CircularEnvironmentInheritanceError: If a circular reference is
                detected in the inheritance chain.

        Example:
            >>> chain = await resolver.get_environment_chain("staging")
            >>> # If staging -> dev -> production:
            >>> # chain = [<staging>, <dev>, <production>]
            >>> for env in chain:
            ...     print(f"  {env.slug}")

        """
        if _visited is None:
            _visited = set()

        # Check for circular reference
        if slug in _visited:
            raise CircularEnvironmentInheritanceError(
                environment_slug=slug,
                visited_chain=list(_visited),
            )

        # Mark this environment as visited
        _visited.add(slug)

        # Get the environment
        environment = await self._storage.get_environment(slug)
        if environment is None:
            return []

        # Build the chain starting with this environment
        chain: list[Environment] = [environment]

        # If this environment has a parent, recursively get the parent chain
        if environment.parent_id is not None:
            # Need to get parent by ID to find its slug
            parent = await self._storage.get_environment_by_id(environment.parent_id)
            if parent is not None:
                parent_chain = await self.get_environment_chain(
                    slug=parent.slug,
                    _visited=_visited,
                )
                chain.extend(parent_chain)

        return chain

    async def get_effective_environment_flag(
        self,
        flag_id: UUID,
        environment_slug: str,
    ) -> EnvironmentFlag | None:
        """Get the effective environment flag by walking the inheritance chain.

        Walks the inheritance chain from the specified environment up to the
        root, returning the first EnvironmentFlag override found. If no
        override exists anywhere in the chain, returns None.

        Args:
            flag_id: The UUID of the feature flag.
            environment_slug: The slug of the environment to start from.

        Returns:
            The first EnvironmentFlag found in the inheritance chain,
            or None if no override exists for this flag in any ancestor.

        Raises:
            CircularEnvironmentInheritanceError: If a circular reference is
                detected in the inheritance chain.

        Example:
            >>> env_flag = await resolver.get_effective_environment_flag(
            ...     flag_id=my_flag.id,
            ...     environment_slug="staging",
            ... )
            >>> if env_flag and env_flag.enabled is not None:
            ...     print(f"Flag is {'enabled' if env_flag.enabled else 'disabled'}")

        """
        # Get the inheritance chain
        chain = await self.get_environment_chain(environment_slug)

        if not chain:
            return None

        # Walk the chain from child to root, return first override found
        for environment in chain:
            env_flag = await self._storage.get_environment_flag(
                env_id=environment.id,
                flag_id=flag_id,
            )
            if env_flag is not None:
                return env_flag

        return None

    async def resolve_flag_for_environment(
        self,
        flag: FeatureFlag,
        environment_slug: str,
    ) -> FeatureFlag:
        """Resolve a flag with environment overrides applied.

        Finds the effective environment override for the flag (if any) by
        walking the inheritance chain, then merges the override onto a copy
        of the base flag. If no override exists, returns a copy of the
        original flag unchanged.

        Args:
            flag: The base feature flag to resolve.
            environment_slug: The slug of the environment to resolve for.

        Returns:
            A new FeatureFlag instance with environment overrides applied.
            The original flag is not modified.

        Raises:
            CircularEnvironmentInheritanceError: If a circular reference is
                detected in the inheritance chain.

        Example:
            >>> base_flag = await storage.get_flag("new-feature")
            >>> resolved = await resolver.resolve_flag_for_environment(
            ...     flag=base_flag,
            ...     environment_slug="staging",
            ... )
            >>> # resolved has staging-specific overrides applied
            >>> print(f"Enabled in staging: {resolved.default_enabled}")

        """
        # Get the effective override for this flag in this environment chain
        env_flag = await self.get_effective_environment_flag(
            flag_id=flag.id,
            environment_slug=environment_slug,
        )

        if env_flag is None:
            # No override found, return a copy of the original flag
            return deepcopy(flag)

        # Merge the override onto the base flag
        return merge_environment_flag(flag, env_flag)


def merge_environment_flag(base: FeatureFlag, override: EnvironmentFlag) -> FeatureFlag:
    """Merge environment override settings onto a base flag.

    Creates a deep copy of the base flag and applies any non-None values
    from the environment override. Fields set to None in the override
    are inherited from the base flag.

    Args:
        base: The base feature flag to merge onto.
        override: The environment-specific override with values to apply.

    Returns:
        A new FeatureFlag instance with override values merged in.
        The original base flag is not modified.

    Example:
        >>> base = FeatureFlag(key="my-flag", default_enabled=True)
        >>> override = EnvironmentFlag(
        ...     flag_id=base.id,
        ...     environment_id=staging_env.id,
        ...     enabled=False,  # Override to disabled
        ...     percentage=None,  # Inherit from base
        ... )
        >>> merged = merge_environment_flag(base, override)
        >>> print(merged.default_enabled)  # False (overridden)

    """
    # Create a deep copy of the base flag to avoid mutating the original
    merged = deepcopy(base)

    # Apply enabled override
    if override.enabled is not None:
        merged.default_enabled = override.enabled  # type: ignore[misc]

    # Apply rules override if provided
    if override.rules is not None:
        # The override.rules is stored as list[dict[str, Any]] in JSON
        # We need to set it appropriately based on whether we have SQLAlchemy or dataclass
        _apply_rules_override(merged, override.rules)

    # Apply variants override if provided
    if override.variants is not None:
        _apply_variants_override(merged, override.variants)

    return merged


def _apply_rules_override(flag: FeatureFlag, rules_data: Any) -> None:
    """Apply rules override to a flag.

    Args:
        flag: The feature flag to modify.
        rules_data: The rules data from the environment override.
            This could be list[dict[str, Any]] (SQLAlchemy) or list[FlagRule] (dataclass).

    """
    # Import here to avoid circular imports and check model availability
    from litestar_flags.models.base import HAS_ADVANCED_ALCHEMY
    from litestar_flags.models.rule import FlagRule

    # If rules_data is already a list of FlagRule instances, use directly
    if rules_data and isinstance(rules_data[0], FlagRule):
        flag.rules = rules_data  # type: ignore[misc]
        return

    # Otherwise, convert dict data to FlagRule instances
    if HAS_ADVANCED_ALCHEMY:
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
    else:
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


def _apply_variants_override(flag: FeatureFlag, variants_data: Any) -> None:
    """Apply variants override to a flag.

    Args:
        flag: The feature flag to modify.
        variants_data: The variants data from the environment override.
            This could be list[dict[str, Any]] (SQLAlchemy) or list[FlagVariant] (dataclass).

    """
    # Import here to avoid circular imports and check model availability
    from litestar_flags.models.base import HAS_ADVANCED_ALCHEMY
    from litestar_flags.models.variant import FlagVariant

    # If variants_data is already a list of FlagVariant instances, use directly
    if variants_data and isinstance(variants_data[0], FlagVariant):
        flag.variants = variants_data  # type: ignore[misc]
        return

    # Otherwise, convert dict data to FlagVariant instances
    if HAS_ADVANCED_ALCHEMY:
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
    else:
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
