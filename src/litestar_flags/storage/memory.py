"""In-memory storage backend for feature flags."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from litestar_flags.types import FlagStatus

if TYPE_CHECKING:
    from litestar_flags.models.environment import Environment
    from litestar_flags.models.environment_flag import EnvironmentFlag
    from litestar_flags.models.flag import FeatureFlag
    from litestar_flags.models.override import FlagOverride
    from litestar_flags.models.schedule import RolloutPhase, ScheduledFlagChange, TimeSchedule
    from litestar_flags.models.segment import Segment

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
        self._segments: dict[UUID, Segment] = {}
        self._segments_by_name: dict[str, Segment] = {}
        self._environments: dict[str, Environment] = {}  # keyed by slug
        self._environments_by_id: dict[UUID, Environment] = {}  # keyed by id
        self._environment_flags: dict[str, EnvironmentFlag] = {}  # keyed by "{env_id}:{flag_id}"

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
        self._segments.clear()
        self._segments_by_name.clear()
        self._environments.clear()
        self._environments_by_id.clear()
        self._environment_flags.clear()

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

        return [schedule for schedule in self._time_schedules.values() if schedule.flag_id == flag_id]

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
        phases = [phase for phase in self._rollout_phases.values() if phase.flag_id == flag_id]
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

    # Segment methods

    async def get_segment(self, segment_id: UUID) -> Segment | None:
        """Retrieve a segment by ID.

        Args:
            segment_id: The UUID of the segment.

        Returns:
            The Segment if found, None otherwise.

        """
        return self._segments.get(segment_id)

    async def get_segment_by_name(self, name: str) -> Segment | None:
        """Retrieve a segment by name.

        Args:
            name: The unique segment name.

        Returns:
            The Segment if found, None otherwise.

        """
        return self._segments_by_name.get(name)

    async def get_all_segments(self) -> list[Segment]:
        """Retrieve all segments.

        Returns:
            List of all Segment objects.

        """
        return list(self._segments.values())

    async def get_child_segments(self, parent_id: UUID) -> list[Segment]:
        """Retrieve all child segments of a parent segment.

        Args:
            parent_id: The UUID of the parent segment.

        Returns:
            List of child Segment objects.

        """
        return [segment for segment in self._segments.values() if segment.parent_segment_id == parent_id]

    async def create_segment(self, segment: Segment) -> Segment:
        """Create a new segment.

        Args:
            segment: The segment to create.

        Returns:
            The created segment.

        Raises:
            ValueError: If a segment with the same name already exists.

        """
        if segment.name in self._segments_by_name:
            raise ValueError(f"Segment with name '{segment.name}' already exists")

        now = datetime.now(UTC)
        if segment.created_at is None:
            segment.created_at = now  # type: ignore[misc]
        if segment.updated_at is None:
            segment.updated_at = now  # type: ignore[misc]

        self._segments[segment.id] = segment
        self._segments_by_name[segment.name] = segment
        return segment

    async def update_segment(self, segment: Segment) -> Segment:
        """Update an existing segment.

        Args:
            segment: The segment with updated values.

        Returns:
            The updated segment.

        Raises:
            ValueError: If the segment does not exist or name conflict occurs.

        """
        if segment.id not in self._segments:
            raise ValueError(f"Segment with id '{segment.id}' not found")

        old_segment = self._segments[segment.id]

        # Handle name change
        if old_segment.name != segment.name:
            if segment.name in self._segments_by_name:
                raise ValueError(f"Segment with name '{segment.name}' already exists")
            del self._segments_by_name[old_segment.name]
            self._segments_by_name[segment.name] = segment

        segment.updated_at = datetime.now(UTC)  # type: ignore[misc]
        self._segments[segment.id] = segment
        return segment

    async def delete_segment(self, segment_id: UUID) -> bool:
        """Delete a segment by ID.

        Args:
            segment_id: The UUID of the segment to delete.

        Returns:
            True if the segment was deleted, False if not found.

        """
        segment = self._segments.pop(segment_id, None)
        if segment is not None:
            self._segments_by_name.pop(segment.name, None)
            return True
        return False

    # Environment methods

    def _environment_flag_key(self, env_id: UUID, flag_id: UUID) -> str:
        """Generate a unique key for an environment flag.

        Args:
            env_id: The environment's UUID.
            flag_id: The flag's UUID.

        Returns:
            A unique string key for the environment flag combination.

        """
        return f"{env_id}:{flag_id}"

    async def get_environment(self, slug: str) -> Environment | None:
        """Retrieve an environment by slug.

        Args:
            slug: The unique environment slug.

        Returns:
            The Environment if found, None otherwise.

        """
        return self._environments.get(slug)

    async def get_environment_by_id(self, env_id: UUID) -> Environment | None:
        """Retrieve an environment by ID.

        Args:
            env_id: The UUID of the environment.

        Returns:
            The Environment if found, None otherwise.

        """
        return self._environments_by_id.get(env_id)

    async def get_all_environments(self) -> list[Environment]:
        """Retrieve all environments.

        Returns:
            List of all Environment objects.

        """
        return list(self._environments.values())

    async def get_child_environments(self, parent_id: UUID) -> list[Environment]:
        """Retrieve all child environments of a parent environment.

        Args:
            parent_id: The UUID of the parent environment.

        Returns:
            List of child Environment objects.

        """
        return [env for env in self._environments.values() if env.parent_id == parent_id]

    async def create_environment(self, env: Environment) -> Environment:
        """Create a new environment.

        Args:
            env: The environment to create.

        Returns:
            The created environment.

        Raises:
            ValueError: If an environment with the same slug already exists.

        """
        if env.slug in self._environments:
            raise ValueError(f"Environment with slug '{env.slug}' already exists")

        now = datetime.now(UTC)
        if env.created_at is None:
            env.created_at = now  # type: ignore[misc]
        if env.updated_at is None:
            env.updated_at = now  # type: ignore[misc]

        self._environments[env.slug] = env
        self._environments_by_id[env.id] = env
        return env

    async def update_environment(self, env: Environment) -> Environment:
        """Update an existing environment.

        Args:
            env: The environment with updated values.

        Returns:
            The updated environment.

        Raises:
            ValueError: If the environment does not exist or slug conflict occurs.

        """
        if env.id not in self._environments_by_id:
            raise ValueError(f"Environment with id '{env.id}' not found")

        old_env = self._environments_by_id[env.id]

        # Handle slug change
        if old_env.slug != env.slug:
            if env.slug in self._environments:
                raise ValueError(f"Environment with slug '{env.slug}' already exists")
            del self._environments[old_env.slug]
            self._environments[env.slug] = env

        env.updated_at = datetime.now(UTC)  # type: ignore[misc]
        self._environments[env.slug] = env
        self._environments_by_id[env.id] = env
        return env

    async def delete_environment(self, slug: str) -> bool:
        """Delete an environment by slug.

        Also deletes all related environment flags.

        Args:
            slug: The unique environment slug.

        Returns:
            True if the environment was deleted, False if not found.

        """
        env = self._environments.pop(slug, None)
        if env is not None:
            self._environments_by_id.pop(env.id, None)
            # Remove associated environment flags
            keys_to_remove = [k for k in self._environment_flags if k.startswith(f"{env.id}:")]
            for k in keys_to_remove:
                del self._environment_flags[k]
            return True
        return False

    # Environment flag methods

    async def get_environment_flag(
        self,
        env_id: UUID,
        flag_id: UUID,
    ) -> EnvironmentFlag | None:
        """Retrieve an environment-specific flag configuration.

        Args:
            env_id: The environment's UUID.
            flag_id: The flag's UUID.

        Returns:
            The EnvironmentFlag if found, None otherwise.

        """
        key = self._environment_flag_key(env_id, flag_id)
        return self._environment_flags.get(key)

    async def get_environment_flags(self, env_id: UUID) -> list[EnvironmentFlag]:
        """Retrieve all flag configurations for an environment.

        Args:
            env_id: The environment's UUID.

        Returns:
            List of EnvironmentFlag objects for the environment.

        """
        return [ef for ef in self._environment_flags.values() if ef.environment_id == env_id]

    async def get_flag_environments(self, flag_id: UUID) -> list[EnvironmentFlag]:
        """Retrieve all environment configurations for a flag.

        Args:
            flag_id: The flag's UUID.

        Returns:
            List of EnvironmentFlag objects for the flag.

        """
        return [ef for ef in self._environment_flags.values() if ef.flag_id == flag_id]

    async def create_environment_flag(self, env_flag: EnvironmentFlag) -> EnvironmentFlag:
        """Create a new environment flag configuration.

        Args:
            env_flag: The environment flag configuration to create.

        Returns:
            The created environment flag.

        Raises:
            ValueError: If the environment flag already exists.

        """
        key = self._environment_flag_key(env_flag.environment_id, env_flag.flag_id)
        if key in self._environment_flags:
            raise ValueError(
                f"EnvironmentFlag for environment '{env_flag.environment_id}' "
                f"and flag '{env_flag.flag_id}' already exists"
            )

        now = datetime.now(UTC)
        if env_flag.created_at is None:
            env_flag.created_at = now  # type: ignore[misc]
        if env_flag.updated_at is None:
            env_flag.updated_at = now  # type: ignore[misc]

        self._environment_flags[key] = env_flag
        return env_flag

    async def update_environment_flag(self, env_flag: EnvironmentFlag) -> EnvironmentFlag:
        """Update an existing environment flag configuration.

        Args:
            env_flag: The environment flag with updated values.

        Returns:
            The updated environment flag.

        Raises:
            ValueError: If the environment flag does not exist.

        """
        key = self._environment_flag_key(env_flag.environment_id, env_flag.flag_id)
        if key not in self._environment_flags:
            raise ValueError(
                f"EnvironmentFlag for environment '{env_flag.environment_id}' "
                f"and flag '{env_flag.flag_id}' not found"
            )

        env_flag.updated_at = datetime.now(UTC)  # type: ignore[misc]
        self._environment_flags[key] = env_flag
        return env_flag

    async def delete_environment_flag(self, env_id: UUID, flag_id: UUID) -> bool:
        """Delete an environment flag configuration.

        Args:
            env_id: The environment's UUID.
            flag_id: The flag's UUID.

        Returns:
            True if the environment flag was deleted, False if not found.

        """
        key = self._environment_flag_key(env_id, flag_id)
        if key in self._environment_flags:
            del self._environment_flags[key]
            return True
        return False
