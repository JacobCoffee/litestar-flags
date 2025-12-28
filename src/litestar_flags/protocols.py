"""Protocols and interfaces for feature flag storage backends."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from litestar_flags.models.flag import FeatureFlag
    from litestar_flags.models.override import FlagOverride
    from litestar_flags.models.schedule import RolloutPhase, ScheduledFlagChange, TimeSchedule

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
