"""Protocols and interfaces for feature flag storage backends."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from litestar_flags.models.environment import Environment
    from litestar_flags.models.environment_flag import EnvironmentFlag
    from litestar_flags.models.flag import FeatureFlag
    from litestar_flags.models.override import FlagOverride
    from litestar_flags.models.schedule import RolloutPhase, ScheduledFlagChange, TimeSchedule
    from litestar_flags.models.segment import Segment

__all__ = ["StorageBackend"]


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for feature flag storage backends.

    All storage backend implementations must implement this protocol.
    Methods are async to support both sync and async backends.

    Implementations:
        - MemoryStorageBackend: In-memory storage for development/testing
        - DatabaseStorageBackend: SQLAlchemy-based persistent storage
        - RedisStorageBackend: Redis-based distributed storage
    """

    async def get_flag(self, key: str) -> FeatureFlag | None:
        """Retrieve a single flag by key.

        Args:
            key: The unique flag key.

        Returns:
            The FeatureFlag if found, None otherwise.

        """
        ...

    async def get_flags(self, keys: Sequence[str]) -> dict[str, FeatureFlag]:
        """Retrieve multiple flags by keys.

        Args:
            keys: Sequence of flag keys to retrieve.

        Returns:
            Dictionary mapping flag keys to FeatureFlag objects.

        """
        ...

    async def get_all_active_flags(self) -> list[FeatureFlag]:
        """Retrieve all active flags.

        Returns:
            List of all FeatureFlag objects with ACTIVE status.

        """
        ...

    async def get_override(
        self,
        flag_id: UUID,
        entity_type: str,
        entity_id: str,
    ) -> FlagOverride | None:
        """Retrieve entity-specific override.

        Args:
            flag_id: The flag's UUID.
            entity_type: Type of entity (e.g., "user", "organization").
            entity_id: The entity's identifier.

        Returns:
            The FlagOverride if found, None otherwise.

        """
        ...

    async def create_flag(self, flag: FeatureFlag) -> FeatureFlag:
        """Create a new flag.

        Args:
            flag: The flag to create.

        Returns:
            The created flag with any generated fields populated.

        """
        ...

    async def update_flag(self, flag: FeatureFlag) -> FeatureFlag:
        """Update an existing flag.

        Args:
            flag: The flag with updated values.

        Returns:
            The updated flag.

        """
        ...

    async def delete_flag(self, key: str) -> bool:
        """Delete a flag by key.

        Args:
            key: The unique flag key.

        Returns:
            True if the flag was deleted, False if not found.

        """
        ...

    async def health_check(self) -> bool:
        """Check storage backend health.

        Returns:
            True if the backend is healthy, False otherwise.

        """
        ...

    async def close(self) -> None:
        """Close any open connections and clean up resources."""
        ...

    # Scheduled changes methods

    async def get_scheduled_changes(
        self,
        flag_id: UUID | None = None,
        pending_only: bool = True,
    ) -> list[ScheduledFlagChange]:
        """Get scheduled changes, optionally filtered by flag and status.

        Args:
            flag_id: If provided, filter to changes for this flag only.
            pending_only: If True, only return changes not yet executed.

        Returns:
            List of scheduled changes matching the criteria.

        """
        ...

    async def create_scheduled_change(
        self,
        change: ScheduledFlagChange,
    ) -> ScheduledFlagChange:
        """Create a new scheduled change.

        Args:
            change: The scheduled change to create.

        Returns:
            The created scheduled change with any generated fields populated.

        """
        ...

    async def update_scheduled_change(
        self,
        change: ScheduledFlagChange,
    ) -> ScheduledFlagChange:
        """Update a scheduled change (e.g., mark as executed).

        Args:
            change: The scheduled change with updated values.

        Returns:
            The updated scheduled change.

        """
        ...

    # Time schedule methods

    async def get_time_schedules(
        self,
        flag_id: UUID | None = None,
    ) -> list[TimeSchedule]:
        """Get time schedules for a flag or all flags.

        Args:
            flag_id: If provided, filter to schedules for this flag only.

        Returns:
            List of time schedules matching the criteria.

        """
        ...

    async def create_time_schedule(
        self,
        schedule: TimeSchedule,
    ) -> TimeSchedule:
        """Create a new time schedule.

        Args:
            schedule: The time schedule to create.

        Returns:
            The created time schedule with any generated fields populated.

        """
        ...

    async def delete_time_schedule(self, schedule_id: UUID) -> bool:
        """Delete a time schedule.

        Args:
            schedule_id: The UUID of the time schedule to delete.

        Returns:
            True if the schedule was deleted, False if not found.

        """
        ...

    # Rollout phase methods

    async def get_rollout_phases(self, flag_id: UUID) -> list[RolloutPhase]:
        """Get rollout phases for a flag.

        Args:
            flag_id: The UUID of the flag.

        Returns:
            List of rollout phases for the flag, ordered by phase number.

        """
        ...

    async def create_rollout_phase(self, phase: RolloutPhase) -> RolloutPhase:
        """Create a new rollout phase.

        Args:
            phase: The rollout phase to create.

        Returns:
            The created rollout phase with any generated fields populated.

        """
        ...

    # Segment methods

    async def get_segment(self, segment_id: UUID) -> Segment | None:
        """Retrieve a segment by ID.

        Args:
            segment_id: The UUID of the segment.

        Returns:
            The Segment if found, None otherwise.

        """
        ...

    async def get_segment_by_name(self, name: str) -> Segment | None:
        """Retrieve a segment by name.

        Args:
            name: The unique segment name.

        Returns:
            The Segment if found, None otherwise.

        """
        ...

    async def get_all_segments(self) -> list[Segment]:
        """Retrieve all segments.

        Returns:
            List of all Segment objects.

        """
        ...

    async def get_child_segments(self, parent_id: UUID) -> list[Segment]:
        """Retrieve all child segments of a parent segment.

        Args:
            parent_id: The UUID of the parent segment.

        Returns:
            List of child Segment objects.

        """
        ...

    async def create_segment(self, segment: Segment) -> Segment:
        """Create a new segment.

        Args:
            segment: The segment to create.

        Returns:
            The created segment with any generated fields populated.

        """
        ...

    async def update_segment(self, segment: Segment) -> Segment:
        """Update an existing segment.

        Args:
            segment: The segment with updated values.

        Returns:
            The updated segment.

        """
        ...

    async def delete_segment(self, segment_id: UUID) -> bool:
        """Delete a segment by ID.

        Args:
            segment_id: The UUID of the segment to delete.

        Returns:
            True if the segment was deleted, False if not found.

        """
        ...

    # Environment methods

    async def get_environment(self, slug: str) -> Environment | None:
        """Retrieve an environment by slug.

        Args:
            slug: The unique URL-safe identifier for the environment.

        Returns:
            The Environment if found, None otherwise.

        """
        ...

    async def get_environment_by_id(self, env_id: UUID) -> Environment | None:
        """Retrieve an environment by ID.

        Args:
            env_id: The UUID of the environment.

        Returns:
            The Environment if found, None otherwise.

        """
        ...

    async def get_all_environments(self) -> list[Environment]:
        """Retrieve all environments.

        Returns:
            List of all Environment objects.

        """
        ...

    async def get_child_environments(self, parent_id: UUID) -> list[Environment]:
        """Retrieve all child environments of a parent environment.

        Args:
            parent_id: The UUID of the parent environment.

        Returns:
            List of child Environment objects.

        """
        ...

    async def create_environment(self, env: Environment) -> Environment:
        """Create a new environment.

        Args:
            env: The environment to create.

        Returns:
            The created environment with any generated fields populated.

        """
        ...

    async def update_environment(self, env: Environment) -> Environment:
        """Update an existing environment.

        Args:
            env: The environment with updated values.

        Returns:
            The updated environment.

        """
        ...

    async def delete_environment(self, slug: str) -> bool:
        """Delete an environment by slug.

        Args:
            slug: The unique URL-safe identifier of the environment to delete.

        Returns:
            True if the environment was deleted, False if not found.

        """
        ...

    # EnvironmentFlag methods

    async def get_environment_flag(
        self,
        env_id: UUID,
        flag_id: UUID,
    ) -> EnvironmentFlag | None:
        """Retrieve environment-specific flag configuration.

        Args:
            env_id: The UUID of the environment.
            flag_id: The UUID of the feature flag.

        Returns:
            The EnvironmentFlag if found, None otherwise.

        """
        ...

    async def get_environment_flags(self, env_id: UUID) -> list[EnvironmentFlag]:
        """Retrieve all flag configurations for an environment.

        Args:
            env_id: The UUID of the environment.

        Returns:
            List of EnvironmentFlag objects for the specified environment.

        """
        ...

    async def get_flag_environments(self, flag_id: UUID) -> list[EnvironmentFlag]:
        """Retrieve all environment configurations for a flag.

        Args:
            flag_id: The UUID of the feature flag.

        Returns:
            List of EnvironmentFlag objects for the specified flag.

        """
        ...

    async def create_environment_flag(
        self,
        env_flag: EnvironmentFlag,
    ) -> EnvironmentFlag:
        """Create a new environment-specific flag configuration.

        Args:
            env_flag: The environment flag configuration to create.

        Returns:
            The created EnvironmentFlag with any generated fields populated.

        """
        ...

    async def update_environment_flag(
        self,
        env_flag: EnvironmentFlag,
    ) -> EnvironmentFlag:
        """Update an existing environment-specific flag configuration.

        Args:
            env_flag: The environment flag configuration with updated values.

        Returns:
            The updated EnvironmentFlag.

        """
        ...

    async def delete_environment_flag(self, env_id: UUID, flag_id: UUID) -> bool:
        """Delete an environment-specific flag configuration.

        Args:
            env_id: The UUID of the environment.
            flag_id: The UUID of the feature flag.

        Returns:
            True if the configuration was deleted, False if not found.

        """
        ...
