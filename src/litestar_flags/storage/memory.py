"""In-memory storage backend for feature flags."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from litestar_flags.types import FlagStatus

if TYPE_CHECKING:
    from litestar_flags.models.flag import FeatureFlag
    from litestar_flags.models.override import FlagOverride
    from litestar_flags.models.schedule import RolloutPhase, ScheduledFlagChange, TimeSchedule

__all__ = ["MemoryStorageBackend"]


class MemoryStorageBackend:
    """In-memory storage backend for development and testing.

    This backend stores all data in memory and is not persistent.
    Ideal for development, testing, and simple single-instance deployments.

    Example:
        >>> storage = MemoryStorageBackend()
        >>> await storage.create_flag(flag)
        >>> flag = await storage.get_flag("my-feature")

    """

    def __init__(self) -> None:
        """Initialize the in-memory storage."""
        self._flags: dict[str, FeatureFlag] = {}
        self._flags_by_id: dict[UUID, FeatureFlag] = {}
        self._overrides: dict[str, FlagOverride] = {}
        self._scheduled_changes: dict[UUID, ScheduledFlagChange] = {}
        self._time_schedules: dict[UUID, TimeSchedule] = {}
        self._rollout_phases: dict[UUID, RolloutPhase] = {}

    def _override_key(self, flag_id: UUID, entity_type: str, entity_id: str) -> str:
        """Generate a unique key for an override."""
        return f"{flag_id}:{entity_type}:{entity_id}"

    async def get_flag(self, key: str) -> FeatureFlag | None:
        """Retrieve a single flag by key.

        Args:
            key: The unique flag key.

        Returns:
            The FeatureFlag if found, None otherwise.

        """
        return self._flags.get(key)

    async def get_flags(self, keys: Sequence[str]) -> dict[str, FeatureFlag]:
        """Retrieve multiple flags by keys.

        Args:
            keys: Sequence of flag keys to retrieve.

        Returns:
            Dictionary mapping flag keys to FeatureFlag objects.

        """
        return {key: flag for key in keys if (flag := self._flags.get(key)) is not None}

    async def get_all_active_flags(self) -> list[FeatureFlag]:
        """Retrieve all active flags.

        Returns:
            List of all FeatureFlag objects with ACTIVE status.

        """
        return [flag for flag in self._flags.values() if flag.status == FlagStatus.ACTIVE]

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
            The FlagOverride if found and not expired, None otherwise.

        """
        key = self._override_key(flag_id, entity_type, entity_id)
        override = self._overrides.get(key)

        if override is not None and override.is_expired(datetime.now(UTC)):
            # Remove expired override
            del self._overrides[key]
            return None

        return override

    async def get_overrides_for_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> list[FlagOverride]:
        """Retrieve all overrides for an entity.

        Args:
            entity_type: Type of entity (e.g., "user", "organization").
            entity_id: The entity's identifier.

        Returns:
            List of non-expired overrides for the entity.

        """
        now = datetime.now(UTC)
        result = []
        expired_keys = []

        for key, override in self._overrides.items():
            if override.entity_type == entity_type and override.entity_id == entity_id:
                if override.is_expired(now):
                    expired_keys.append(key)
                else:
                    result.append(override)

        # Clean up expired overrides
        for key in expired_keys:
            del self._overrides[key]

        return result

    async def create_flag(self, flag: FeatureFlag) -> FeatureFlag:
        """Create a new flag.

        Args:
            flag: The flag to create.

        Returns:
            The created flag.

        Raises:
            ValueError: If a flag with the same key already exists.

        """
        if flag.key in self._flags:
            raise ValueError(f"Flag with key '{flag.key}' already exists")

        # Set timestamps if not present
        now = datetime.now(UTC)
        if flag.created_at is None:
            flag.created_at = now  # type: ignore[misc]
        if flag.updated_at is None:
            flag.updated_at = now  # type: ignore[misc]

        self._flags[flag.key] = flag
        self._flags_by_id[flag.id] = flag
        return flag

    async def update_flag(self, flag: FeatureFlag) -> FeatureFlag:
        """Update an existing flag.

        Args:
            flag: The flag with updated values.

        Returns:
            The updated flag.

        Raises:
            ValueError: If the flag does not exist.

        """
        if flag.key not in self._flags:
            raise ValueError(f"Flag with key '{flag.key}' not found")

        flag.updated_at = datetime.now(UTC)  # type: ignore[misc]
        self._flags[flag.key] = flag
        self._flags_by_id[flag.id] = flag
        return flag

    async def delete_flag(self, key: str) -> bool:
        """Delete a flag by key.

        Args:
            key: The unique flag key.

        Returns:
            True if the flag was deleted, False if not found.

        """
        flag = self._flags.pop(key, None)
        if flag is not None:
            self._flags_by_id.pop(flag.id, None)
            # Remove associated overrides
            keys_to_remove = [k for k in self._overrides if k.startswith(f"{flag.id}:")]
            for k in keys_to_remove:
                del self._overrides[k]
            return True
        return False

    async def create_override(self, override: FlagOverride) -> FlagOverride:
        """Create a new override.

        Args:
            override: The override to create.

        Returns:
            The created override.

        """
        if override.flag_id is None:
            raise ValueError("Override must have a flag_id")

        key = self._override_key(override.flag_id, override.entity_type, override.entity_id)

        now = datetime.now(UTC)
        if override.created_at is None:
            override.created_at = now  # type: ignore[misc]
        if override.updated_at is None:
            override.updated_at = now  # type: ignore[misc]

        self._overrides[key] = override
        return override

    async def delete_override(
        self,
        flag_id: UUID,
        entity_type: str,
        entity_id: str,
    ) -> bool:
        """Delete an override.

        Args:
            flag_id: The flag's UUID.
            entity_type: Type of entity.
            entity_id: The entity's identifier.

        Returns:
            True if the override was deleted, False if not found.

        """
        key = self._override_key(flag_id, entity_type, entity_id)
        if key in self._overrides:
            del self._overrides[key]
            return True
        return False

    async def health_check(self) -> bool:
        """Check storage backend health.

        Returns:
            Always True for in-memory storage.

        """
        return True

    async def close(self) -> None:
        """Close the storage backend.

        Clears all data from memory.
        """
        self._flags.clear()
        self._flags_by_id.clear()
        self._overrides.clear()
        self._scheduled_changes.clear()
        self._time_schedules.clear()
        self._rollout_phases.clear()

    def __len__(self) -> int:
        """Return the number of flags stored."""
        return len(self._flags)

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
        result = []
        for change in self._scheduled_changes.values():
            # Filter by flag_id if provided
            if flag_id is not None and change.flag_id != flag_id:
                continue
            # Filter by pending status if requested
            if pending_only and change.executed:
                continue
            result.append(change)

        # Sort by scheduled_at
        result.sort(key=lambda c: c.scheduled_at)
        return result

    async def create_scheduled_change(
        self,
        change: ScheduledFlagChange,
    ) -> ScheduledFlagChange:
        """Create a new scheduled change.

        Args:
            change: The scheduled change to create.

        Returns:
            The created scheduled change.

        """
        now = datetime.now(UTC)
        if change.created_at is None:
            change.created_at = now  # type: ignore[misc]
        if change.updated_at is None:
            change.updated_at = now  # type: ignore[misc]

        self._scheduled_changes[change.id] = change
        return change

    async def update_scheduled_change(
        self,
        change: ScheduledFlagChange,
    ) -> ScheduledFlagChange:
        """Update a scheduled change (e.g., mark as executed).

        Args:
            change: The scheduled change with updated values.

        Returns:
            The updated scheduled change.

        Raises:
            ValueError: If the scheduled change does not exist.

        """
        if change.id not in self._scheduled_changes:
            raise ValueError(f"Scheduled change with id '{change.id}' not found")

        change.updated_at = datetime.now(UTC)  # type: ignore[misc]
        self._scheduled_changes[change.id] = change
        return change

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
        if flag_id is None:
            return list(self._time_schedules.values())

        return [
            schedule
            for schedule in self._time_schedules.values()
            if schedule.flag_id == flag_id
        ]

    async def create_time_schedule(
        self,
        schedule: TimeSchedule,
    ) -> TimeSchedule:
        """Create a new time schedule.

        Args:
            schedule: The time schedule to create.

        Returns:
            The created time schedule.

        """
        now = datetime.now(UTC)
        if schedule.created_at is None:
            schedule.created_at = now  # type: ignore[misc]
        if schedule.updated_at is None:
            schedule.updated_at = now  # type: ignore[misc]

        self._time_schedules[schedule.id] = schedule
        return schedule

    async def delete_time_schedule(self, schedule_id: UUID) -> bool:
        """Delete a time schedule.

        Args:
            schedule_id: The UUID of the time schedule to delete.

        Returns:
            True if the schedule was deleted, False if not found.

        """
        if schedule_id in self._time_schedules:
            del self._time_schedules[schedule_id]
            return True
        return False

    # Rollout phase methods

    async def get_rollout_phases(self, flag_id: UUID) -> list[RolloutPhase]:
        """Get rollout phases for a flag.

        Args:
            flag_id: The UUID of the flag.

        Returns:
            List of rollout phases for the flag, ordered by phase number.

        """
        phases = [
            phase
            for phase in self._rollout_phases.values()
            if phase.flag_id == flag_id
        ]
        # Sort by phase_number
        phases.sort(key=lambda p: p.phase_number)
        return phases

    async def create_rollout_phase(self, phase: RolloutPhase) -> RolloutPhase:
        """Create a new rollout phase.

        Args:
            phase: The rollout phase to create.

        Returns:
            The created rollout phase.

        """
        now = datetime.now(UTC)
        if phase.created_at is None:
            phase.created_at = now  # type: ignore[misc]
        if phase.updated_at is None:
            phase.updated_at = now  # type: ignore[misc]

        self._rollout_phases[phase.id] = phase
        return phase
