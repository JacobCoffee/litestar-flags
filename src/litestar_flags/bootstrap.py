"""Bootstrap and preload functionality for feature flags.

This module provides utilities for loading feature flags from static sources
(files, dictionaries) and creating offline clients that work without a
storage backend.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID, uuid4

from litestar_flags.context import EvaluationContext
from litestar_flags.engine import EvaluationEngine
from litestar_flags.exceptions import ConfigurationError
from litestar_flags.results import EvaluationDetails
from litestar_flags.types import ErrorCode, EvaluationReason, FlagStatus, FlagType

if TYPE_CHECKING:
    from collections.abc import Sequence

    from litestar_flags.models.flag import FeatureFlag
    from litestar_flags.models.override import FlagOverride

__all__ = [
    "BootstrapConfig",
    "BootstrapLoader",
    "OfflineClient",
]

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class BootstrapConfig:
    """Configuration for flag bootstrap loading.

    Attributes:
        source: Path to JSON file, URL string, or inline dictionary of flags.
        fallback_on_error: If True, continue with empty flags on load error.
        refresh_interval: Interval in seconds to refresh from source. None disables refresh.

    Example:
        >>> config = BootstrapConfig(
        ...     source=Path("flags.json"),
        ...     fallback_on_error=True,
        ...     refresh_interval=300.0,  # Refresh every 5 minutes
        ... )

    """

    source: Path | str | dict[str, Any]
    fallback_on_error: bool = True
    refresh_interval: float | None = None


@dataclass
class BootstrapLoader:
    """Loader for feature flags from static sources.

    Supports loading flags from JSON files and dictionaries. The loader
    converts raw data into FeatureFlag objects that can be used with
    the OfflineClient or preloaded into a storage backend.

    Example:
        >>> loader = BootstrapLoader()
        >>> flags = await loader.load_from_file(Path("flags.json"))
        >>> flags = loader.load_from_dict({"flags": [...]})

    """

    _flag_class: type[FeatureFlag] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize the flag class lazily."""
        if self._flag_class is None:
            # Import here to avoid circular imports
            from litestar_flags.models.flag import FeatureFlag

            self._flag_class = FeatureFlag

    async def load_from_file(self, path: Path) -> list[FeatureFlag]:
        """Load feature flags from a JSON file.

        Args:
            path: Path to the JSON file containing flag definitions.

        Returns:
            List of FeatureFlag objects parsed from the file.

        Raises:
            ConfigurationError: If the file cannot be read or parsed.

        Example:
            >>> loader = BootstrapLoader()
            >>> flags = await loader.load_from_file(Path("config/flags.json"))

        """
        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            return self.load_from_dict(data)
        except FileNotFoundError as e:
            raise ConfigurationError(f"Bootstrap file not found: {path}") from e
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in bootstrap file: {e}") from e
        except Exception as e:
            raise ConfigurationError(f"Error loading bootstrap file: {e}") from e

    def load_from_dict(self, data: dict[str, Any]) -> list[FeatureFlag]:
        """Load feature flags from a dictionary.

        The dictionary should have a "flags" key containing a list of flag
        definitions. Each flag definition should match the FeatureFlag schema.

        Args:
            data: Dictionary containing flag definitions under "flags" key.

        Returns:
            List of FeatureFlag objects.

        Raises:
            ConfigurationError: If the data format is invalid.

        Example:
            >>> loader = BootstrapLoader()
            >>> flags = loader.load_from_dict({
            ...     "flags": [
            ...         {
            ...             "key": "my-feature",
            ...             "name": "My Feature",
            ...             "flag_type": "boolean",
            ...             "default_enabled": True,
            ...         }
            ...     ]
            ... })

        """
        try:
            flags_data = data.get("flags", [])
            if not isinstance(flags_data, list):
                raise ConfigurationError("'flags' must be a list")

            return [self._parse_flag(flag_data) for flag_data in flags_data]
        except ConfigurationError:
            raise
        except Exception as e:
            raise ConfigurationError(f"Error parsing flag data: {e}") from e

    def _parse_flag(self, data: dict[str, Any]) -> FeatureFlag:
        """Parse a single flag from dictionary data.

        Args:
            data: Dictionary containing flag definition.

        Returns:
            FeatureFlag object.

        Raises:
            ConfigurationError: If required fields are missing.

        """
        if "key" not in data:
            raise ConfigurationError("Flag missing required 'key' field")
        if "name" not in data:
            # Default name to key if not provided
            data["name"] = data["key"]

        # Parse enum values
        flag_type_str = data.get("flag_type", "boolean")
        status_str = data.get("status", "active")

        try:
            flag_type = FlagType(flag_type_str)
        except ValueError:
            raise ConfigurationError(f"Invalid flag_type: {flag_type_str}") from None

        try:
            status = FlagStatus(status_str)
        except ValueError:
            raise ConfigurationError(f"Invalid status: {status_str}") from None

        # Parse UUID if provided, otherwise generate
        flag_id = data.get("id")
        if flag_id is not None:
            if isinstance(flag_id, str):
                try:
                    flag_id = UUID(flag_id)
                except ValueError:
                    raise ConfigurationError(f"Invalid UUID: {flag_id}") from None
        else:
            flag_id = uuid4()

        # Parse timestamps if provided, default to now for SQLAlchemy audit models
        from datetime import UTC

        now = datetime.now(UTC)
        created_at = data.get("created_at")
        updated_at = data.get("updated_at")

        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = now

        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = now

        # Build flag arguments
        flag_kwargs: dict[str, Any] = {
            "key": data["key"],
            "name": data["name"],
            "id": flag_id,
            "description": data.get("description"),
            "flag_type": flag_type,
            "status": status,
            "default_enabled": data.get("default_enabled", False),
            "default_value": data.get("default_value"),
            "tags": data.get("tags", []),
            "metadata_": data.get("metadata", {}),
            "rules": [],  # Rules can be extended in the future
            "overrides": [],
            "variants": [],
            "created_at": created_at,
            "updated_at": updated_at,
        }

        if self._flag_class is None:
            raise ConfigurationError("Flag class not initialized")
        return self._flag_class(**flag_kwargs)

    async def load(self, config: BootstrapConfig) -> list[FeatureFlag]:
        """Load flags based on bootstrap configuration.

        Args:
            config: Bootstrap configuration specifying the source.

        Returns:
            List of FeatureFlag objects.

        Raises:
            ConfigurationError: If loading fails and fallback_on_error is False.

        """
        try:
            if isinstance(config.source, Path):
                return await self.load_from_file(config.source)
            elif isinstance(config.source, dict):
                return self.load_from_dict(config.source)
            elif isinstance(config.source, str):
                # Treat as file path string
                return await self.load_from_file(Path(config.source))
            else:
                raise ConfigurationError(f"Invalid source type: {type(config.source).__name__}")
        except ConfigurationError:
            if config.fallback_on_error:
                logger.warning("Bootstrap loading failed, using empty flag set")
                return []
            raise


class OfflineClient:
    """Feature flag client that operates without a storage backend.

    The OfflineClient is initialized with a static set of flags loaded from
    bootstrap data. It provides the same evaluation interface as FeatureFlagClient
    but does not require a storage backend connection.

    This is useful for:
    - Testing and development
    - Offline scenarios
    - Edge deployments with static configuration
    - Fallback when storage is unavailable

    Example:
        >>> config = BootstrapConfig(source=Path("flags.json"))
        >>> client = await OfflineClient.from_config(config)
        >>> enabled = await client.get_boolean_value("my-feature")

    """

    def __init__(
        self,
        flags: list[FeatureFlag],
        default_context: EvaluationContext | None = None,
    ) -> None:
        """Initialize the offline client with bootstrap flags.

        Args:
            flags: List of FeatureFlag objects to use for evaluation.
            default_context: Default evaluation context when none is provided.

        """
        self._flags: dict[str, FeatureFlag] = {flag.key: flag for flag in flags}
        self._default_context = default_context or EvaluationContext()
        self._engine = EvaluationEngine()
        self._closed = False

    @classmethod
    async def from_config(
        cls,
        config: BootstrapConfig,
        default_context: EvaluationContext | None = None,
    ) -> OfflineClient:
        """Create an OfflineClient from bootstrap configuration.

        Args:
            config: Bootstrap configuration specifying flag source.
            default_context: Default evaluation context.

        Returns:
            Configured OfflineClient instance.

        Example:
            >>> config = BootstrapConfig(source={"flags": [...]})
            >>> client = await OfflineClient.from_config(config)

        """
        loader = BootstrapLoader()
        flags = await loader.load(config)
        return cls(flags=flags, default_context=default_context)

    @classmethod
    def from_flags(
        cls,
        flags: list[FeatureFlag],
        default_context: EvaluationContext | None = None,
    ) -> OfflineClient:
        """Create an OfflineClient from a list of flags.

        Args:
            flags: List of FeatureFlag objects.
            default_context: Default evaluation context.

        Returns:
            Configured OfflineClient instance.

        """
        return cls(flags=flags, default_context=default_context)

    @property
    def flags(self) -> dict[str, FeatureFlag]:
        """Get the flags dictionary."""
        return self._flags

    # Boolean evaluation

    async def get_boolean_value(
        self,
        flag_key: str,
        default: bool = False,
        context: EvaluationContext | None = None,
    ) -> bool:
        """Evaluate a boolean flag.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            The evaluated boolean value.

        """
        details = await self.get_boolean_details(flag_key, default, context)
        return details.value

    async def get_boolean_details(
        self,
        flag_key: str,
        default: bool = False,
        context: EvaluationContext | None = None,
    ) -> EvaluationDetails[bool]:
        """Evaluate a boolean flag with details.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            EvaluationDetails containing the value and metadata.

        """
        return await self._evaluate(flag_key, default, FlagType.BOOLEAN, context)

    # String evaluation

    async def get_string_value(
        self,
        flag_key: str,
        default: str = "",
        context: EvaluationContext | None = None,
    ) -> str:
        """Evaluate a string flag.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            The evaluated string value.

        """
        details = await self.get_string_details(flag_key, default, context)
        return details.value

    async def get_string_details(
        self,
        flag_key: str,
        default: str = "",
        context: EvaluationContext | None = None,
    ) -> EvaluationDetails[str]:
        """Evaluate a string flag with details.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            EvaluationDetails containing the value and metadata.

        """
        return await self._evaluate(flag_key, default, FlagType.STRING, context)

    # Number evaluation

    async def get_number_value(
        self,
        flag_key: str,
        default: float = 0.0,
        context: EvaluationContext | None = None,
    ) -> float:
        """Evaluate a number flag.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            The evaluated number value.

        """
        details = await self.get_number_details(flag_key, default, context)
        return details.value

    async def get_number_details(
        self,
        flag_key: str,
        default: float = 0.0,
        context: EvaluationContext | None = None,
    ) -> EvaluationDetails[float]:
        """Evaluate a number flag with details.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            EvaluationDetails containing the value and metadata.

        """
        return await self._evaluate(flag_key, default, FlagType.NUMBER, context)

    # Object/JSON evaluation

    async def get_object_value(
        self,
        flag_key: str,
        default: dict[str, Any] | None = None,
        context: EvaluationContext | None = None,
    ) -> dict[str, Any]:
        """Evaluate an object/JSON flag.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            The evaluated object value.

        """
        details = await self.get_object_details(flag_key, default or {}, context)
        return details.value

    async def get_object_details(
        self,
        flag_key: str,
        default: dict[str, Any],
        context: EvaluationContext | None = None,
    ) -> EvaluationDetails[dict[str, Any]]:
        """Evaluate an object/JSON flag with details.

        Args:
            flag_key: The unique flag key.
            default: Default value if flag is not found or evaluation fails.
            context: Optional evaluation context.

        Returns:
            EvaluationDetails containing the value and metadata.

        """
        return await self._evaluate(flag_key, default, FlagType.JSON, context)

    # Convenience methods

    async def is_enabled(
        self,
        flag_key: str,
        context: EvaluationContext | None = None,
    ) -> bool:
        """Check if a boolean flag is enabled.

        Args:
            flag_key: The unique flag key.
            context: Optional evaluation context.

        Returns:
            True if the flag is enabled, False otherwise.

        """
        return await self.get_boolean_value(flag_key, default=False, context=context)

    # Bulk evaluation

    async def get_all_flags(
        self,
        context: EvaluationContext | None = None,
    ) -> dict[str, EvaluationDetails[Any]]:
        """Evaluate all active flags.

        Args:
            context: Optional evaluation context.

        Returns:
            Dictionary mapping flag keys to their evaluation details.

        """
        ctx = self._merge_context(context)
        results: dict[str, EvaluationDetails[Any]] = {}

        for flag in self._flags.values():
            if flag.status == FlagStatus.ACTIVE:
                try:
                    results[flag.key] = await self._evaluate_flag(flag, ctx)
                except Exception as e:
                    logger.warning(f"Error evaluating flag '{flag.key}': {e}")
                    continue

        return results

    async def get_flags(
        self,
        flag_keys: list[str],
        context: EvaluationContext | None = None,
    ) -> dict[str, EvaluationDetails[Any]]:
        """Evaluate specific flags by key.

        Args:
            flag_keys: List of flag keys to evaluate.
            context: Optional evaluation context.

        Returns:
            Dictionary mapping flag keys to their evaluation details.

        """
        ctx = self._merge_context(context)
        results: dict[str, EvaluationDetails[Any]] = {}

        for key in flag_keys:
            flag = self._flags.get(key)
            if flag is not None:
                try:
                    results[key] = await self._evaluate_flag(flag, ctx)
                except Exception as e:
                    logger.warning(f"Error evaluating flag '{key}': {e}")
                    continue

        return results

    # Internal methods

    async def _evaluate(
        self,
        flag_key: str,
        default: T,
        expected_type: FlagType,
        context: EvaluationContext | None,
    ) -> EvaluationDetails[T]:
        """Core evaluation logic with error handling.

        Args:
            flag_key: The flag key to evaluate.
            default: Default value on error or not found.
            expected_type: Expected flag type for validation.
            context: Optional evaluation context.

        Returns:
            EvaluationDetails with the evaluated or default value.

        """
        ctx = self._merge_context(context)

        try:
            flag = self._flags.get(flag_key)

            if flag is None:
                return EvaluationDetails(
                    value=default,
                    flag_key=flag_key,
                    reason=EvaluationReason.DEFAULT,
                    error_code=ErrorCode.FLAG_NOT_FOUND,
                    error_message=f"Flag '{flag_key}' not found",
                )

            # Type validation
            if expected_type != FlagType.BOOLEAN and flag.flag_type != expected_type:
                return EvaluationDetails(
                    value=default,
                    flag_key=flag_key,
                    reason=EvaluationReason.ERROR,
                    error_code=ErrorCode.TYPE_MISMATCH,
                    error_message=f"Expected type '{expected_type.value}', got '{flag.flag_type.value}'",
                )

            result = await self._evaluate_flag(flag, ctx)

            return EvaluationDetails(
                value=result.value,  # type: ignore[arg-type]
                flag_key=result.flag_key,
                reason=result.reason,
                variant=result.variant,
                error_code=result.error_code,
                error_message=result.error_message,
                flag_metadata=result.flag_metadata,
            )

        except Exception as e:
            logger.error(f"Error evaluating flag '{flag_key}': {e}")
            return EvaluationDetails(
                value=default,
                flag_key=flag_key,
                reason=EvaluationReason.ERROR,
                error_code=ErrorCode.GENERAL_ERROR,
                error_message=str(e),
            )

    async def _evaluate_flag(
        self,
        flag: FeatureFlag,
        context: EvaluationContext,
    ) -> EvaluationDetails[Any]:
        """Evaluate a single flag using the engine.

        Args:
            flag: The flag to evaluate.
            context: The evaluation context.

        Returns:
            EvaluationDetails from the engine.

        """
        # Create a minimal storage adapter for the engine
        storage = _OfflineStorageAdapter(self._flags)
        return await self._engine.evaluate(flag, context, storage)

    def _merge_context(self, context: EvaluationContext | None) -> EvaluationContext:
        """Merge provided context with default context.

        Args:
            context: The provided context (may be None).

        Returns:
            Merged context with defaults.

        """
        if context is None:
            return self._default_context
        return self._default_context.merge(context)

    async def health_check(self) -> bool:
        """Check if the client is healthy.

        Returns:
            True if not closed, False otherwise.

        """
        return not self._closed

    async def close(self) -> None:
        """Close the client and release resources."""
        self._closed = True
        self._flags.clear()

    async def __aenter__(self) -> OfflineClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()


class _OfflineStorageAdapter:
    """Minimal storage adapter for offline evaluation.

    This adapter wraps the in-memory flags dictionary to provide the
    minimal interface required by the EvaluationEngine.
    """

    def __init__(self, flags: dict[str, FeatureFlag]) -> None:
        """Initialize the adapter with flags dictionary.

        Args:
            flags: Dictionary mapping flag keys to FeatureFlag objects.

        """
        self._flags = flags

    async def get_flag(self, key: str) -> FeatureFlag | None:
        """Get a flag by key.

        Args:
            key: The flag key.

        Returns:
            The flag if found, None otherwise.

        """
        return self._flags.get(key)

    async def get_flags(self, keys: Sequence[str]) -> dict[str, FeatureFlag]:
        """Get multiple flags by keys.

        Args:
            keys: Sequence of flag keys.

        Returns:
            Dictionary of found flags.

        """
        return {key: flag for key in keys if (flag := self._flags.get(key)) is not None}

    async def get_all_active_flags(self) -> list[FeatureFlag]:
        """Get all active flags.

        Returns:
            List of active flags.

        """
        return [flag for flag in self._flags.values() if flag.status == FlagStatus.ACTIVE]

    async def get_override(
        self,
        flag_id: UUID,
        entity_type: str,
        entity_id: str,
    ) -> FlagOverride | None:
        """Get override (always None for offline).

        Args:
            flag_id: The flag ID.
            entity_type: Entity type.
            entity_id: Entity ID.

        Returns:
            Always None (overrides not supported in offline mode).

        """
        return None

    async def health_check(self) -> bool:
        """Health check (always True).

        Returns:
            Always True.

        """
        return True

    async def close(self) -> None:
        """Close (no-op)."""
        pass
