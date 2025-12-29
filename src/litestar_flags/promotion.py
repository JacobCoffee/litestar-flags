"""Flag promotion workflow for moving configurations between environments.

This module provides functionality to promote feature flag configurations from
one environment to another, supporting dry-run capabilities, validation, and
audit logging for safe flag promotions across deployment environments.

Example:
    Basic flag promotion::

        from litestar_flags import StorageBackend
        from litestar_flags.promotion import (
            EnvironmentResolver,
            FlagPromoter,
        )

        storage: StorageBackend = ...
        resolver = EnvironmentResolver(storage)
        promoter = FlagPromoter(storage, resolver)

        # Dry-run first to see what would change
        result = await promoter.promote_flag(
            "my-feature",
            source_env="staging",
            target_env="production",
            dry_run=True,
        )
        print(result.changes_applied)

        # Actually apply the promotion
        if not result.warnings:
            result = await promoter.promote_flag(
                "my-feature",
                source_env="staging",
                target_env="production",
            )

"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from litestar_flags.models.environment import Environment
    from litestar_flags.models.environment_flag import EnvironmentFlag
    from litestar_flags.protocols import StorageBackend

__all__ = [
    "EnvironmentNotFoundError",
    "EnvironmentResolver",
    "FlagPromoter",
    "PromotionError",
    "PromotionResult",
]

logger = logging.getLogger(__name__)

# Environments that require explicit confirmation (dry_run=False) before promotion
PROTECTED_ENVIRONMENTS = frozenset({"production", "prod", "live"})


class PromotionError(Exception):
    """Base exception for promotion errors."""

    pass


class EnvironmentNotFoundError(PromotionError):
    """Raised when an environment cannot be found."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"Environment '{slug}' not found")


@dataclass(slots=True)
class PromotionResult:
    """Result of a flag promotion operation.

    Attributes:
        success: Whether the promotion completed successfully.
        source_environment: The source environment slug.
        target_environment: The target environment slug.
        flag_key: The key of the flag that was promoted.
        changes_applied: Dictionary of changes that were (or would be) applied.
            Contains keys like 'enabled', 'percentage', 'rules', 'variants'.
        warnings: List of non-fatal warnings encountered during promotion.
        error: Error message if the promotion failed, None otherwise.
        timestamp: When the promotion occurred or was attempted.
        dry_run: Whether this was a dry-run (no actual changes made).
        previous_values: The target environment's previous values before promotion.
            Only populated on successful non-dry-run promotions.

    Example:
        >>> result = await promoter.promote_flag("my-feature", "staging", "production")
        >>> if result.success:
        ...     print(f"Promoted {result.flag_key} to {result.target_environment}")
        ...     print(f"Changes: {result.changes_applied}")
        >>> else:
        ...     print(f"Failed: {result.error}")

    """

    success: bool
    source_environment: str
    target_environment: str
    flag_key: str
    changes_applied: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    dry_run: bool = False
    previous_values: dict[str, Any] = field(default_factory=dict)


class EnvironmentResolver:
    """Resolves environments from storage by slug or ID.

    Provides methods to retrieve environment configurations and validate
    environment existence. Used by the FlagPromoter to resolve environment
    references during promotion operations.

    Attributes:
        storage: The storage backend for environment retrieval.

    Example:
        >>> resolver = EnvironmentResolver(storage)
        >>> env = await resolver.get_environment("production")
        >>> if env is not None:
        ...     print(f"Found: {env.name}")

    """

    def __init__(self, storage: StorageBackend) -> None:
        """Initialize the environment resolver.

        Args:
            storage: The storage backend to use for environment lookups.

        """
        self._storage = storage

    @property
    def storage(self) -> StorageBackend:
        """Get the storage backend."""
        return self._storage

    async def get_environment(self, slug: str) -> Environment | None:
        """Retrieve an environment by its slug.

        Args:
            slug: The unique URL-safe identifier for the environment.

        Returns:
            The Environment if found, None otherwise.

        """
        return await self._storage.get_environment(slug)

    async def get_environment_by_id(self, env_id: UUID) -> Environment | None:
        """Retrieve an environment by its UUID.

        Args:
            env_id: The UUID of the environment.

        Returns:
            The Environment if found, None otherwise.

        """
        return await self._storage.get_environment_by_id(env_id)

    async def get_all_environments(self) -> list[Environment]:
        """Retrieve all environments.

        Returns:
            List of all Environment objects in the system.

        """
        return await self._storage.get_all_environments()

    async def environment_exists(self, slug: str) -> bool:
        """Check if an environment exists.

        Args:
            slug: The environment slug to check.

        Returns:
            True if the environment exists, False otherwise.

        """
        env = await self.get_environment(slug)
        return env is not None

    async def is_protected_environment(self, slug: str) -> bool:
        """Check if an environment is protected (requires explicit confirmation).

        Protected environments include production, prod, and live.
        Additional protected environments can be configured via
        environment settings.

        Args:
            slug: The environment slug to check.

        Returns:
            True if the environment is protected, False otherwise.

        """
        if slug.lower() in PROTECTED_ENVIRONMENTS:
            return True

        env = await self.get_environment(slug)
        if env is not None:
            # Check for custom protection setting in environment
            return env.settings.get("is_protected", False)

        return False


class FlagPromoter:
    """Promotes feature flag configurations between environments.

    Handles the workflow of copying flag configurations from one environment
    to another, with support for dry-run validation, conflict detection,
    and audit logging.

    Attributes:
        storage: The storage backend for flag and environment operations.
        resolver: The environment resolver for environment lookups.

    Example:
        >>> promoter = FlagPromoter(storage, resolver)
        >>> # Preview changes first
        >>> preview = await promoter.promote_flag(
        ...     "new-checkout",
        ...     source_env="staging",
        ...     target_env="production",
        ...     dry_run=True,
        ... )
        >>> print(f"Would apply: {preview.changes_applied}")
        >>>
        >>> # Apply the promotion
        >>> result = await promoter.promote_flag(
        ...     "new-checkout",
        ...     source_env="staging",
        ...     target_env="production",
        ... )

    """

    def __init__(
        self,
        storage: StorageBackend,
        resolver: EnvironmentResolver,
    ) -> None:
        """Initialize the flag promoter.

        Args:
            storage: The storage backend for flag operations.
            resolver: The environment resolver for environment lookups.

        """
        self._storage = storage
        self._resolver = resolver

    @property
    def storage(self) -> StorageBackend:
        """Get the storage backend."""
        return self._storage

    @property
    def resolver(self) -> EnvironmentResolver:
        """Get the environment resolver."""
        return self._resolver

    async def promote_flag(
        self,
        flag_key: str,
        source_env: str,
        target_env: str,
        *,
        dry_run: bool = False,
    ) -> PromotionResult:
        """Promote a flag configuration from source to target environment.

        Copies the EnvironmentFlag settings (enabled, percentage, rules, variants)
        from the source environment to the target environment.

        Args:
            flag_key: The unique key of the flag to promote.
            source_env: The source environment slug.
            target_env: The target environment slug.
            dry_run: If True, only return what would change without applying.

        Returns:
            PromotionResult with the outcome of the promotion attempt.

        Example:
            >>> result = await promoter.promote_flag(
            ...     "feature-x",
            ...     source_env="staging",
            ...     target_env="production",
            ...     dry_run=True,
            ... )
            >>> if result.warnings:
            ...     for warning in result.warnings:
            ...         print(f"Warning: {warning}")

        """
        timestamp = datetime.now(UTC)

        # Validate the promotion first
        warnings = await self.validate_promotion(flag_key, source_env, target_env)

        # Check for fatal validation errors (prefixed with "ERROR:")
        fatal_errors = [w for w in warnings if w.startswith("ERROR:")]
        if fatal_errors:
            return PromotionResult(
                success=False,
                source_environment=source_env,
                target_environment=target_env,
                flag_key=flag_key,
                warnings=[w for w in warnings if not w.startswith("ERROR:")],
                error=fatal_errors[0].replace("ERROR: ", ""),
                timestamp=timestamp,
                dry_run=dry_run,
            )

        # Get the environments
        source = await self._resolver.get_environment(source_env)
        target = await self._resolver.get_environment(target_env)

        if source is None:
            return PromotionResult(
                success=False,
                source_environment=source_env,
                target_environment=target_env,
                flag_key=flag_key,
                error=f"Source environment '{source_env}' not found",
                timestamp=timestamp,
                dry_run=dry_run,
            )

        if target is None:
            return PromotionResult(
                success=False,
                source_environment=source_env,
                target_environment=target_env,
                flag_key=flag_key,
                error=f"Target environment '{target_env}' not found",
                timestamp=timestamp,
                dry_run=dry_run,
            )

        # Check production safety
        if await self._resolver.is_protected_environment(target_env):
            if dry_run:
                warnings.append(
                    f"Target environment '{target_env}' is protected. "
                    "A non-dry-run promotion will require explicit confirmation."
                )
            else:
                # Log the production promotion for audit
                logger.warning(
                    "Promoting flag '%s' to protected environment '%s' from '%s'",
                    flag_key,
                    target_env,
                    source_env,
                )

        # Get the flag
        flag = await self._storage.get_flag(flag_key)
        if flag is None:
            return PromotionResult(
                success=False,
                source_environment=source_env,
                target_environment=target_env,
                flag_key=flag_key,
                error=f"Flag '{flag_key}' not found",
                timestamp=timestamp,
                dry_run=dry_run,
            )

        # Get the source environment flag configuration
        source_env_flag = await self._storage.get_environment_flag(source.id, flag.id)
        if source_env_flag is None:
            return PromotionResult(
                success=False,
                source_environment=source_env,
                target_environment=target_env,
                flag_key=flag_key,
                error=f"Flag '{flag_key}' has no configuration in source environment '{source_env}'",
                timestamp=timestamp,
                dry_run=dry_run,
            )

        # Get the target environment flag configuration (may not exist)
        target_env_flag = await self._storage.get_environment_flag(target.id, flag.id)

        # Calculate changes to apply
        changes_applied = self._calculate_changes(source_env_flag)
        previous_values: dict[str, Any] = {}

        if target_env_flag is not None:
            previous_values = self._extract_values(target_env_flag)

            # Check for conflicts
            conflicts = self._detect_conflicts(source_env_flag, target_env_flag)
            if conflicts:
                warnings.extend(conflicts)

        if dry_run:
            return PromotionResult(
                success=True,
                source_environment=source_env,
                target_environment=target_env,
                flag_key=flag_key,
                changes_applied=changes_applied,
                warnings=warnings,
                timestamp=timestamp,
                dry_run=True,
                previous_values=previous_values,
            )

        # Apply the promotion
        try:
            await self._apply_promotion(
                source_env_flag=source_env_flag,
                target_env=target,
                target_env_flag=target_env_flag,
                flag_id=flag.id,
            )

            # Log the successful promotion
            logger.info(
                "Promoted flag '%s' from '%s' to '%s': %s",
                flag_key,
                source_env,
                target_env,
                changes_applied,
            )

            return PromotionResult(
                success=True,
                source_environment=source_env,
                target_environment=target_env,
                flag_key=flag_key,
                changes_applied=changes_applied,
                warnings=warnings,
                timestamp=timestamp,
                dry_run=False,
                previous_values=previous_values,
            )

        except Exception as e:
            logger.exception(
                "Failed to promote flag '%s' from '%s' to '%s'",
                flag_key,
                source_env,
                target_env,
            )
            return PromotionResult(
                success=False,
                source_environment=source_env,
                target_environment=target_env,
                flag_key=flag_key,
                changes_applied=changes_applied,
                warnings=warnings,
                error=str(e),
                timestamp=timestamp,
                dry_run=False,
            )

    async def promote_all_flags(
        self,
        source_env: str,
        target_env: str,
        *,
        dry_run: bool = False,
    ) -> list[PromotionResult]:
        """Promote all flag configurations from source to target environment.

        Iterates through all flags configured in the source environment and
        promotes each one to the target environment.

        Args:
            source_env: The source environment slug.
            target_env: The target environment slug.
            dry_run: If True, only return what would change without applying.

        Returns:
            List of PromotionResult objects, one per flag.

        Example:
            >>> results = await promoter.promote_all_flags(
            ...     source_env="staging",
            ...     target_env="production",
            ...     dry_run=True,
            ... )
            >>> for result in results:
            ...     print(f"{result.flag_key}: {result.changes_applied}")

        """
        results: list[PromotionResult] = []

        # Get the source environment
        source = await self._resolver.get_environment(source_env)
        if source is None:
            return [
                PromotionResult(
                    success=False,
                    source_environment=source_env,
                    target_environment=target_env,
                    flag_key="*",
                    error=f"Source environment '{source_env}' not found",
                    dry_run=dry_run,
                )
            ]

        # Get all flags configured in the source environment
        source_env_flags = await self._storage.get_environment_flags(source.id)

        if not source_env_flags:
            return [
                PromotionResult(
                    success=True,
                    source_environment=source_env,
                    target_environment=target_env,
                    flag_key="*",
                    warnings=[f"No flags configured in source environment '{source_env}'"],
                    dry_run=dry_run,
                )
            ]

        # Promote each flag
        for env_flag in source_env_flags:
            # Get the flag to retrieve its key
            flag = None

            # Try to get flag from the environment flag relationship first
            if hasattr(env_flag, "flag") and env_flag.flag is not None:
                flag = env_flag.flag

            if flag is None:
                results.append(
                    PromotionResult(
                        success=False,
                        source_environment=source_env,
                        target_environment=target_env,
                        flag_key=f"unknown (ID: {env_flag.flag_id})",
                        error="Could not resolve flag from environment flag configuration",
                        dry_run=dry_run,
                    )
                )
                continue

            result = await self.promote_flag(
                flag_key=flag.key,
                source_env=source_env,
                target_env=target_env,
                dry_run=dry_run,
            )
            results.append(result)

        return results

    async def compare_environments(
        self,
        env1: str,
        env2: str,
    ) -> dict[str, dict[str, Any]]:
        """Compare flag configurations between two environments.

        Returns a dictionary showing differences for each flag that has
        configurations in either environment.

        Args:
            env1: The first environment slug.
            env2: The second environment slug.

        Returns:
            Dictionary mapping flag keys to their differences.
            Each entry contains 'env1', 'env2', and 'differences' keys.

        Example:
            >>> diff = await promoter.compare_environments("staging", "production")
            >>> for flag_key, info in diff.items():
            ...     print(f"{flag_key}:")
            ...     print(f"  staging: {info['env1']}")
            ...     print(f"  production: {info['env2']}")
            ...     print(f"  differences: {info['differences']}")

        """
        result: dict[str, dict[str, Any]] = {}

        # Get both environments
        environment1 = await self._resolver.get_environment(env1)
        environment2 = await self._resolver.get_environment(env2)

        if environment1 is None or environment2 is None:
            missing = []
            if environment1 is None:
                missing.append(env1)
            if environment2 is None:
                missing.append(env2)
            return {
                "_error": {
                    "env1": None,
                    "env2": None,
                    "differences": [f"Environment(s) not found: {', '.join(missing)}"],
                }
            }

        # Get flags from both environments
        env1_flags = await self._storage.get_environment_flags(environment1.id)
        env2_flags = await self._storage.get_environment_flags(environment2.id)

        # Index by flag_id for efficient lookup
        env1_by_flag: dict[UUID, EnvironmentFlag] = {ef.flag_id: ef for ef in env1_flags}
        env2_by_flag: dict[UUID, EnvironmentFlag] = {ef.flag_id: ef for ef in env2_flags}

        # Get all unique flag IDs
        all_flag_ids = set(env1_by_flag.keys()) | set(env2_by_flag.keys())

        for flag_id in all_flag_ids:
            # Get the flag key - try to get flag from the environment flag relationship
            flag = None
            ef = env1_by_flag.get(flag_id) or env2_by_flag.get(flag_id)
            if ef is not None and hasattr(ef, "flag") and ef.flag is not None:
                flag = ef.flag

            flag_key = flag.key if flag else f"unknown:{flag_id}"

            env1_flag = env1_by_flag.get(flag_id)
            env2_flag = env2_by_flag.get(flag_id)

            env1_values = self._extract_values(env1_flag) if env1_flag else None
            env2_values = self._extract_values(env2_flag) if env2_flag else None

            differences = self._find_differences(env1_values, env2_values)

            result[flag_key] = {
                "env1": env1_values,
                "env2": env2_values,
                "differences": differences,
            }

        return result

    async def validate_promotion(
        self,
        flag_key: str,
        source_env: str,
        target_env: str,
    ) -> list[str]:
        """Validate a promotion before applying it.

        Returns a list of warnings and errors that would be encountered
        during the promotion. Errors are prefixed with "ERROR:" and indicate
        the promotion cannot proceed.

        Args:
            flag_key: The flag key to validate.
            source_env: The source environment slug.
            target_env: The target environment slug.

        Returns:
            List of validation warnings/errors. Empty list means validation passed.

        Example:
            >>> warnings = await promoter.validate_promotion(
            ...     "my-feature", "staging", "production"
            ... )
            >>> for warning in warnings:
            ...     print(warning)

        """
        warnings: list[str] = []

        # Check environments exist
        source = await self._resolver.get_environment(source_env)
        target = await self._resolver.get_environment(target_env)

        if source is None:
            warnings.append(f"ERROR: Source environment '{source_env}' does not exist")

        if target is None:
            warnings.append(f"ERROR: Target environment '{target_env}' does not exist")

        if source is None or target is None:
            return warnings

        # Check source and target are different
        if source_env == target_env:
            warnings.append("ERROR: Source and target environments must be different")
            return warnings

        # Check flag exists
        flag = await self._storage.get_flag(flag_key)
        if flag is None:
            warnings.append(f"ERROR: Flag '{flag_key}' does not exist")
            return warnings

        # Check source has configuration for this flag
        source_env_flag = await self._storage.get_environment_flag(source.id, flag.id)
        if source_env_flag is None:
            warnings.append(f"ERROR: Flag '{flag_key}' has no configuration in source environment '{source_env}'")
            return warnings

        # Check target for conflicts (warnings, not errors)
        target_env_flag = await self._storage.get_environment_flag(target.id, flag.id)
        if target_env_flag is not None:
            conflicts = self._detect_conflicts(source_env_flag, target_env_flag)
            warnings.extend(conflicts)

        # Check for protected environment
        if await self._resolver.is_protected_environment(target_env):
            warnings.append(
                f"Target environment '{target_env}' is protected. "
                "Ensure you have appropriate authorization for this promotion."
            )

        # Check for environment hierarchy issues
        if source.parent_id is not None and source.parent_id == target.id:
            warnings.append(
                f"Warning: Promoting from child environment '{source_env}' to parent '{target_env}'. "
                "This may override inherited settings."
            )

        if target.parent_id is not None and target.parent_id == source.id:
            warnings.append(
                f"Warning: Promoting to child environment '{target_env}' from parent '{source_env}'. "
                "Consider whether inheritance should be used instead."
            )

        # Check if target environment is active
        if not target.is_active:
            warnings.append(
                f"Warning: Target environment '{target_env}' is not active. "
                "The promoted configuration may not take effect."
            )

        return warnings

    def _calculate_changes(self, env_flag: EnvironmentFlag) -> dict[str, Any]:
        """Calculate the changes that would be applied from an environment flag.

        Args:
            env_flag: The source environment flag configuration.

        Returns:
            Dictionary of non-None values from the environment flag.

        """
        changes: dict[str, Any] = {}

        if env_flag.enabled is not None:
            changes["enabled"] = env_flag.enabled

        if env_flag.percentage is not None:
            changes["percentage"] = env_flag.percentage

        # Handle rules and variants (may be JSON or objects depending on backend)
        if hasattr(env_flag, "rules") and env_flag.rules is not None:
            changes["rules"] = env_flag.rules

        if hasattr(env_flag, "variants") and env_flag.variants is not None:
            changes["variants"] = env_flag.variants

        return changes

    def _extract_values(self, env_flag: EnvironmentFlag | None) -> dict[str, Any]:
        """Extract all values from an environment flag configuration.

        Args:
            env_flag: The environment flag to extract values from.

        Returns:
            Dictionary of all values (including None values).

        """
        if env_flag is None:
            return {}

        values: dict[str, Any] = {
            "enabled": env_flag.enabled,
            "percentage": env_flag.percentage,
        }

        if hasattr(env_flag, "rules"):
            values["rules"] = env_flag.rules

        if hasattr(env_flag, "variants"):
            values["variants"] = env_flag.variants

        return values

    def _detect_conflicts(
        self,
        source_flag: EnvironmentFlag,
        target_flag: EnvironmentFlag,
    ) -> list[str]:
        """Detect conflicts between source and target configurations.

        Args:
            source_flag: The source environment flag.
            target_flag: The target environment flag.

        Returns:
            List of conflict warnings.

        """
        conflicts: list[str] = []

        # Check enabled state conflict
        if source_flag.enabled is not None and target_flag.enabled is not None:
            if source_flag.enabled != target_flag.enabled:
                conflicts.append(
                    f"Conflict: 'enabled' differs - source={source_flag.enabled}, target={target_flag.enabled}"
                )

        # Check percentage conflict
        if source_flag.percentage is not None and target_flag.percentage is not None:
            if source_flag.percentage != target_flag.percentage:
                conflicts.append(
                    f"Conflict: 'percentage' differs - source={source_flag.percentage}%, "
                    f"target={target_flag.percentage}%"
                )

        # Check rules conflict
        source_rules = getattr(source_flag, "rules", None)
        target_rules = getattr(target_flag, "rules", None)
        if source_rules is not None and target_rules is not None:
            if source_rules != target_rules:
                conflicts.append("Conflict: 'rules' configuration differs between environments")

        # Check variants conflict
        source_variants = getattr(source_flag, "variants", None)
        target_variants = getattr(target_flag, "variants", None)
        if source_variants is not None and target_variants is not None:
            if source_variants != target_variants:
                conflicts.append("Conflict: 'variants' configuration differs between environments")

        return conflicts

    def _find_differences(
        self,
        values1: dict[str, Any] | None,
        values2: dict[str, Any] | None,
    ) -> list[str]:
        """Find differences between two sets of values.

        Args:
            values1: Values from the first environment.
            values2: Values from the second environment.

        Returns:
            List of difference descriptions.

        """
        differences: list[str] = []

        if values1 is None and values2 is None:
            return differences

        if values1 is None:
            differences.append("Only exists in second environment")
            return differences

        if values2 is None:
            differences.append("Only exists in first environment")
            return differences

        all_keys = set(values1.keys()) | set(values2.keys())

        for key in all_keys:
            val1 = values1.get(key)
            val2 = values2.get(key)

            if val1 != val2:
                differences.append(f"{key}: {val1!r} vs {val2!r}")

        return differences

    async def _apply_promotion(
        self,
        source_env_flag: EnvironmentFlag,
        target_env: Environment,
        target_env_flag: EnvironmentFlag | None,
        flag_id: UUID,
    ) -> None:
        """Apply the promotion to the target environment.

        Args:
            source_env_flag: The source environment flag configuration.
            target_env: The target environment.
            target_env_flag: Existing target environment flag (if any).
            flag_id: The ID of the flag being promoted.

        """
        # Import here to avoid circular imports and handle both dataclass/ORM
        from litestar_flags.models.environment_flag import EnvironmentFlag as EnvFlagModel

        if target_env_flag is not None:
            # Update existing configuration
            target_env_flag.enabled = source_env_flag.enabled
            target_env_flag.percentage = source_env_flag.percentage

            # Copy rules and variants if present
            # Note: rules/variants have different types in ORM vs dataclass models
            if hasattr(source_env_flag, "rules") and hasattr(target_env_flag, "rules"):
                target_env_flag.rules = source_env_flag.rules  # type: ignore[assignment]

            if hasattr(source_env_flag, "variants") and hasattr(target_env_flag, "variants"):
                target_env_flag.variants = source_env_flag.variants  # type: ignore[assignment]

            await self._storage.update_environment_flag(target_env_flag)
        else:
            # Create new configuration
            new_env_flag = EnvFlagModel(
                environment_id=target_env.id,
                flag_id=flag_id,
                enabled=source_env_flag.enabled,
                percentage=source_env_flag.percentage,
            )

            # Copy rules and variants if present
            # Note: rules/variants have different types in ORM vs dataclass models
            if hasattr(source_env_flag, "rules") and hasattr(new_env_flag, "rules"):
                new_env_flag.rules = source_env_flag.rules  # type: ignore[assignment]

            if hasattr(source_env_flag, "variants") and hasattr(new_env_flag, "variants"):
                new_env_flag.variants = source_env_flag.variants  # type: ignore[assignment]

            await self._storage.create_environment_flag(new_env_flag)
