"""Redis storage backend for feature flags."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

try:
    from redis.asyncio import Redis
except ImportError as e:
    raise ImportError("Redis backend requires 'redis'. Install with: pip install litestar-flags[redis]") from e

from litestar_flags.types import ChangeType, FlagStatus, FlagType, RecurrenceType

if TYPE_CHECKING:
    from litestar_flags.models.flag import FeatureFlag
    from litestar_flags.models.override import FlagOverride
    from litestar_flags.models.schedule import RolloutPhase, ScheduledFlagChange, TimeSchedule

__all__ = ["RedisStorageBackend"]


class RedisStorageBackend:
    """Redis storage backend for distributed feature flags.

    This backend stores feature flags in Redis, making it suitable for
    distributed deployments where multiple application instances need
    to share flag state.

    Data is stored as JSON strings with the following key patterns:
    - Flags: {prefix}flag:{key}
    - Overrides: {prefix}override:{flag_id}:{entity_type}:{entity_id}
    - Flag index: {prefix}flags (SET of all flag keys)

    Example:
        >>> storage = await RedisStorageBackend.create(
        ...     url="redis://localhost:6379",
        ...     prefix="ff:"
        ... )
        >>> flag = await storage.get_flag("my-feature")

    """

    def __init__(self, redis: Redis, prefix: str = "feature_flags:") -> None:  # type: ignore[type-arg]
        """Initialize the Redis storage backend.

        Args:
            redis: The Redis client instance.
            prefix: Key prefix for all stored data.

        """
        self._redis = redis
        self._prefix = prefix

    @classmethod
    async def create(
        cls,
        url: str,
        prefix: str = "feature_flags:",
        **redis_kwargs: Any,
    ) -> RedisStorageBackend:
        """Create a new Redis storage backend.

        Args:
            url: Redis connection URL.
            prefix: Key prefix for all stored data.
            **redis_kwargs: Additional arguments for Redis.from_url().

        Returns:
            Configured RedisStorageBackend instance.

        """
        redis = Redis.from_url(url, decode_responses=True, **redis_kwargs)
        # Test connection
        await redis.ping()
        return cls(redis=redis, prefix=prefix)

    def _flag_key(self, key: str) -> str:
        """Get the Redis key for a flag."""
        return f"{self._prefix}flag:{key}"

    def _override_key(self, flag_id: UUID, entity_type: str, entity_id: str) -> str:
        """Get the Redis key for an override."""
        return f"{self._prefix}override:{flag_id}:{entity_type}:{entity_id}"

    def _flags_index_key(self) -> str:
        """Get the Redis key for the flags index set."""
        return f"{self._prefix}flags"

    def _scheduled_change_key(self, change_id: UUID) -> str:
        """Get the Redis key for a scheduled change."""
        return f"{self._prefix}schedule:{change_id}"

    def _scheduled_changes_index_key(self, flag_id: UUID | None = None) -> str:
        """Get the Redis key for the scheduled changes index set."""
        if flag_id is not None:
            return f"{self._prefix}schedules:flag:{flag_id}"
        return f"{self._prefix}schedules"

    def _time_schedule_key(self, schedule_id: UUID) -> str:
        """Get the Redis key for a time schedule."""
        return f"{self._prefix}time_schedule:{schedule_id}"

    def _time_schedules_index_key(self, flag_id: UUID | None = None) -> str:
        """Get the Redis key for the time schedules index set."""
        if flag_id is not None:
            return f"{self._prefix}time_schedules:flag:{flag_id}"
        return f"{self._prefix}time_schedules"

    def _rollout_phase_key(self, phase_id: UUID) -> str:
        """Get the Redis key for a rollout phase."""
        return f"{self._prefix}rollout_phase:{phase_id}"

    def _rollout_phases_index_key(self, flag_id: UUID) -> str:
        """Get the Redis key for the rollout phases index set for a flag."""
        return f"{self._prefix}rollout_phases:flag:{flag_id}"

    def _serialize_flag(self, flag: FeatureFlag) -> str:
        """Serialize a flag to JSON."""
        data = {
            "id": str(flag.id),
            "key": flag.key,
            "name": flag.name,
            "description": flag.description,
            "flag_type": flag.flag_type.value,
            "status": flag.status.value,
            "default_enabled": flag.default_enabled,
            "default_value": flag.default_value,
            "tags": flag.tags,
            "metadata": flag.metadata_,
            "rules": [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "description": r.description,
                    "priority": r.priority,
                    "enabled": r.enabled,
                    "conditions": r.conditions,
                    "serve_enabled": r.serve_enabled,
                    "serve_value": r.serve_value,
                    "rollout_percentage": r.rollout_percentage,
                }
                for r in (flag.rules or [])
            ],
            "variants": [
                {
                    "id": str(v.id),
                    "key": v.key,
                    "name": v.name,
                    "description": v.description,
                    "value": v.value,
                    "weight": v.weight,
                }
                for v in (flag.variants or [])
            ],
            "created_at": flag.created_at.isoformat() if flag.created_at else None,
            "updated_at": flag.updated_at.isoformat() if flag.updated_at else None,
        }
        return json.dumps(data)

    def _deserialize_flag(self, data: str) -> FeatureFlag:
        """Deserialize a flag from JSON."""
        from litestar_flags.models.flag import FeatureFlag
        from litestar_flags.models.rule import FlagRule
        from litestar_flags.models.variant import FlagVariant

        obj = json.loads(data)

        # Create rule objects
        rules = [
            FlagRule(
                id=UUID(r["id"]),
                name=r["name"],
                description=r.get("description"),
                priority=r["priority"],
                enabled=r["enabled"],
                conditions=r["conditions"],
                serve_enabled=r["serve_enabled"],
                serve_value=r.get("serve_value"),
                rollout_percentage=r.get("rollout_percentage"),
            )
            for r in obj.get("rules", [])
        ]

        # Create variant objects
        variants = [
            FlagVariant(
                id=UUID(v["id"]),
                key=v["key"],
                name=v["name"],
                description=v.get("description"),
                value=v["value"],
                weight=v["weight"],
            )
            for v in obj.get("variants", [])
        ]

        return FeatureFlag(
            id=UUID(obj["id"]),
            key=obj["key"],
            name=obj["name"],
            description=obj.get("description"),
            flag_type=FlagType(obj["flag_type"]),
            status=FlagStatus(obj["status"]),
            default_enabled=obj["default_enabled"],
            default_value=obj.get("default_value"),
            tags=obj.get("tags", []),
            metadata_=obj.get("metadata", {}),
            rules=rules,
            variants=variants,
            created_at=datetime.fromisoformat(obj["created_at"]) if obj.get("created_at") else None,
            updated_at=datetime.fromisoformat(obj["updated_at"]) if obj.get("updated_at") else None,
        )

    def _serialize_override(self, override: FlagOverride) -> str:
        """Serialize an override to JSON."""
        data = {
            "id": str(override.id),
            "flag_id": str(override.flag_id),
            "entity_type": override.entity_type,
            "entity_id": override.entity_id,
            "enabled": override.enabled,
            "value": override.value,
            "expires_at": override.expires_at.isoformat() if override.expires_at else None,
            "created_at": override.created_at.isoformat() if override.created_at else None,
            "updated_at": override.updated_at.isoformat() if override.updated_at else None,
        }
        return json.dumps(data)

    def _deserialize_override(self, data: str) -> FlagOverride:
        """Deserialize an override from JSON."""
        from litestar_flags.models.override import FlagOverride

        obj = json.loads(data)
        return FlagOverride(
            id=UUID(obj["id"]),
            flag_id=UUID(obj["flag_id"]),
            entity_type=obj["entity_type"],
            entity_id=obj["entity_id"],
            enabled=obj["enabled"],
            value=obj.get("value"),
            expires_at=datetime.fromisoformat(obj["expires_at"]) if obj.get("expires_at") else None,
            created_at=datetime.fromisoformat(obj["created_at"]) if obj.get("created_at") else None,
            updated_at=datetime.fromisoformat(obj["updated_at"]) if obj.get("updated_at") else None,
        )

    def _serialize_scheduled_change(self, change: ScheduledFlagChange) -> str:
        """Serialize a scheduled change to JSON."""
        data = {
            "id": str(change.id),
            "flag_id": str(change.flag_id),
            "change_type": change.change_type.value,
            "scheduled_at": change.scheduled_at.isoformat(),
            "executed": change.executed,
            "executed_at": change.executed_at.isoformat() if change.executed_at else None,
            "new_value": change.new_value,
            "new_rollout_percentage": change.new_rollout_percentage,
            "created_by": change.created_by,
            "created_at": change.created_at.isoformat() if change.created_at else None,
            "updated_at": change.updated_at.isoformat() if change.updated_at else None,
        }
        return json.dumps(data)

    def _deserialize_scheduled_change(self, data: str) -> ScheduledFlagChange:
        """Deserialize a scheduled change from JSON."""
        from litestar_flags.models.schedule import ScheduledFlagChange

        obj = json.loads(data)
        return ScheduledFlagChange(
            id=UUID(obj["id"]),
            flag_id=UUID(obj["flag_id"]),
            change_type=ChangeType(obj["change_type"]),
            scheduled_at=datetime.fromisoformat(obj["scheduled_at"]),
            executed=obj.get("executed", False),
            executed_at=datetime.fromisoformat(obj["executed_at"]) if obj.get("executed_at") else None,
            new_value=obj.get("new_value"),
            new_rollout_percentage=obj.get("new_rollout_percentage"),
            created_by=obj.get("created_by"),
            created_at=datetime.fromisoformat(obj["created_at"]) if obj.get("created_at") else None,
            updated_at=datetime.fromisoformat(obj["updated_at"]) if obj.get("updated_at") else None,
        )

    def _serialize_time_schedule(self, schedule: TimeSchedule) -> str:
        """Serialize a time schedule to JSON."""
        from datetime import time

        data = {
            "id": str(schedule.id),
            "flag_id": str(schedule.flag_id),
            "name": schedule.name,
            "recurrence_type": schedule.recurrence_type.value,
            "start_time": (
                schedule.start_time.isoformat()
                if isinstance(schedule.start_time, time)
                else schedule.start_time
            ),
            "end_time": (
                schedule.end_time.isoformat()
                if isinstance(schedule.end_time, time)
                else schedule.end_time
            ),
            "days_of_week": schedule.days_of_week,
            "days_of_month": schedule.days_of_month,
            "cron_expression": schedule.cron_expression,
            "timezone": schedule.timezone,
            "enabled": schedule.enabled,
            "created_at": schedule.created_at.isoformat() if schedule.created_at else None,
            "updated_at": schedule.updated_at.isoformat() if schedule.updated_at else None,
        }
        return json.dumps(data)

    def _deserialize_time_schedule(self, data: str) -> TimeSchedule:
        """Deserialize a time schedule from JSON."""
        from datetime import time

        from litestar_flags.models.schedule import TimeSchedule

        obj = json.loads(data)

        # Handle time parsing
        start_time_str = obj["start_time"]
        end_time_str = obj["end_time"]
        start_time = time.fromisoformat(start_time_str) if start_time_str else time(0, 0)
        end_time = time.fromisoformat(end_time_str) if end_time_str else time(23, 59)

        return TimeSchedule(
            id=UUID(obj["id"]),
            flag_id=UUID(obj["flag_id"]),
            name=obj["name"],
            recurrence_type=RecurrenceType(obj["recurrence_type"]),
            start_time=start_time,
            end_time=end_time,
            days_of_week=obj.get("days_of_week"),
            days_of_month=obj.get("days_of_month"),
            cron_expression=obj.get("cron_expression"),
            timezone=obj.get("timezone", "UTC"),
            enabled=obj.get("enabled", True),
            created_at=datetime.fromisoformat(obj["created_at"]) if obj.get("created_at") else None,
            updated_at=datetime.fromisoformat(obj["updated_at"]) if obj.get("updated_at") else None,
        )

    def _serialize_rollout_phase(self, phase: RolloutPhase) -> str:
        """Serialize a rollout phase to JSON."""
        data = {
            "id": str(phase.id),
            "flag_id": str(phase.flag_id),
            "phase_number": phase.phase_number,
            "target_percentage": phase.target_percentage,
            "scheduled_at": phase.scheduled_at.isoformat(),
            "executed": phase.executed,
            "executed_at": phase.executed_at.isoformat() if phase.executed_at else None,
            "created_at": phase.created_at.isoformat() if phase.created_at else None,
            "updated_at": phase.updated_at.isoformat() if phase.updated_at else None,
        }
        return json.dumps(data)

    def _deserialize_rollout_phase(self, data: str) -> RolloutPhase:
        """Deserialize a rollout phase from JSON."""
        from litestar_flags.models.schedule import RolloutPhase

        obj = json.loads(data)
        return RolloutPhase(
            id=UUID(obj["id"]),
            flag_id=UUID(obj["flag_id"]),
            phase_number=obj["phase_number"],
            target_percentage=obj["target_percentage"],
            scheduled_at=datetime.fromisoformat(obj["scheduled_at"]),
            executed=obj.get("executed", False),
            executed_at=datetime.fromisoformat(obj["executed_at"]) if obj.get("executed_at") else None,
            created_at=datetime.fromisoformat(obj["created_at"]) if obj.get("created_at") else None,
            updated_at=datetime.fromisoformat(obj["updated_at"]) if obj.get("updated_at") else None,
        )

    async def get_flag(self, key: str) -> FeatureFlag | None:
        """Retrieve a single flag by key.

        Args:
            key: The unique flag key.

        Returns:
            The FeatureFlag if found, None otherwise.

        """
        data = await self._redis.get(self._flag_key(key))
        if data is None:
            return None
        return self._deserialize_flag(data)

    async def get_flags(self, keys: Sequence[str]) -> dict[str, FeatureFlag]:
        """Retrieve multiple flags by keys.

        Args:
            keys: Sequence of flag keys to retrieve.

        Returns:
            Dictionary mapping flag keys to FeatureFlag objects.

        """
        if not keys:
            return {}

        redis_keys = [self._flag_key(k) for k in keys]
        values = await self._redis.mget(redis_keys)

        result = {}
        for key, value in zip(keys, values, strict=False):
            if value is not None:
                result[key] = self._deserialize_flag(value)
        return result

    async def get_all_active_flags(self) -> list[FeatureFlag]:
        """Retrieve all active flags.

        Returns:
            List of all FeatureFlag objects with ACTIVE status.

        """
        # Get all flag keys from the index
        keys = await self._redis.smembers(self._flags_index_key())
        if not keys:
            return []

        # Get all flags
        flags = await self.get_flags(list(keys))

        # Filter to active only
        return [f for f in flags.values() if f.status == FlagStatus.ACTIVE]

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
        data = await self._redis.get(key)
        if data is None:
            return None

        override = self._deserialize_override(data)

        # Check expiration
        if override.is_expired(datetime.now(UTC)):
            await self._redis.delete(key)
            return None

        return override

    async def create_flag(self, flag: FeatureFlag) -> FeatureFlag:
        """Create a new flag.

        Args:
            flag: The flag to create.

        Returns:
            The created flag.

        """
        now = datetime.now(UTC)
        if flag.created_at is None:
            flag.created_at = now  # type: ignore[misc]
        if flag.updated_at is None:
            flag.updated_at = now  # type: ignore[misc]

        # Store flag
        await self._redis.set(self._flag_key(flag.key), self._serialize_flag(flag))

        # Add to index
        await self._redis.sadd(self._flags_index_key(), flag.key)

        return flag

    async def update_flag(self, flag: FeatureFlag) -> FeatureFlag:
        """Update an existing flag.

        Args:
            flag: The flag with updated values.

        Returns:
            The updated flag.

        """
        flag.updated_at = datetime.now(UTC)  # type: ignore[misc]
        await self._redis.set(self._flag_key(flag.key), self._serialize_flag(flag))
        return flag

    async def delete_flag(self, key: str) -> bool:
        """Delete a flag by key.

        Args:
            key: The unique flag key.

        Returns:
            True if the flag was deleted, False if not found.

        """
        # Get flag to find its ID for override cleanup
        flag = await self.get_flag(key)
        if flag is None:
            return False

        # Delete flag
        await self._redis.delete(self._flag_key(key))

        # Remove from index
        await self._redis.srem(self._flags_index_key(), key)

        # Note: Overrides are not automatically cleaned up
        # This could be handled with a pattern scan if needed

        return True

    async def create_override(self, override: FlagOverride) -> FlagOverride:
        """Create a new override.

        Args:
            override: The override to create.

        Returns:
            The created override.

        """
        if override.flag_id is None:
            raise ValueError("Override must have a flag_id")

        now = datetime.now(UTC)
        if override.created_at is None:
            override.created_at = now  # type: ignore[misc]
        if override.updated_at is None:
            override.updated_at = now  # type: ignore[misc]

        key = self._override_key(override.flag_id, override.entity_type, override.entity_id)
        await self._redis.set(key, self._serialize_override(override))

        # Set TTL if expires_at is set
        if override.expires_at:
            ttl = int((override.expires_at - now).total_seconds())
            if ttl > 0:
                await self._redis.expire(key, ttl)

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
        result = await self._redis.delete(key)
        return result > 0

    async def health_check(self) -> bool:
        """Check storage backend health.

        Returns:
            True if the backend is healthy, False otherwise.

        """
        try:
            await self._redis.ping()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close Redis connections."""
        await self._redis.aclose()

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
        # Get all change IDs from the appropriate index
        index_key = self._scheduled_changes_index_key(flag_id)
        change_ids = await self._redis.smembers(index_key)

        if not change_ids:
            # If filtering by flag_id and no index, try the global index
            if flag_id is not None:
                global_ids = await self._redis.smembers(self._scheduled_changes_index_key())
                change_ids = global_ids
            else:
                return []

        # Get all changes
        result = []
        for change_id in change_ids:
            key = self._scheduled_change_key(UUID(change_id))
            data = await self._redis.get(key)
            if data:
                change = self._deserialize_scheduled_change(data)
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

        # Store the change
        key = self._scheduled_change_key(change.id)
        await self._redis.set(key, self._serialize_scheduled_change(change))

        # Add to global index
        await self._redis.sadd(self._scheduled_changes_index_key(), str(change.id))

        # Add to flag-specific index
        await self._redis.sadd(self._scheduled_changes_index_key(change.flag_id), str(change.id))

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

        """
        change.updated_at = datetime.now(UTC)  # type: ignore[misc]

        key = self._scheduled_change_key(change.id)
        await self._redis.set(key, self._serialize_scheduled_change(change))

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
        # Get all schedule IDs from the appropriate index
        index_key = self._time_schedules_index_key(flag_id)
        schedule_ids = await self._redis.smembers(index_key)

        if not schedule_ids:
            if flag_id is not None:
                # No schedules for this flag
                return []
            # Try global index
            schedule_ids = await self._redis.smembers(self._time_schedules_index_key())

        if not schedule_ids:
            return []

        # Get all schedules
        result = []
        for schedule_id in schedule_ids:
            key = self._time_schedule_key(UUID(schedule_id))
            data = await self._redis.get(key)
            if data:
                schedule = self._deserialize_time_schedule(data)
                # Filter by flag_id if provided
                if flag_id is not None and schedule.flag_id != flag_id:
                    continue
                result.append(schedule)

        return result

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

        # Store the schedule
        key = self._time_schedule_key(schedule.id)
        await self._redis.set(key, self._serialize_time_schedule(schedule))

        # Add to global index
        await self._redis.sadd(self._time_schedules_index_key(), str(schedule.id))

        # Add to flag-specific index
        await self._redis.sadd(self._time_schedules_index_key(schedule.flag_id), str(schedule.id))

        return schedule

    async def delete_time_schedule(self, schedule_id: UUID) -> bool:
        """Delete a time schedule.

        Args:
            schedule_id: The UUID of the time schedule to delete.

        Returns:
            True if the schedule was deleted, False if not found.

        """
        key = self._time_schedule_key(schedule_id)
        data = await self._redis.get(key)

        if data is None:
            return False

        schedule = self._deserialize_time_schedule(data)

        # Delete the schedule
        await self._redis.delete(key)

        # Remove from global index
        await self._redis.srem(self._time_schedules_index_key(), str(schedule_id))

        # Remove from flag-specific index
        await self._redis.srem(self._time_schedules_index_key(schedule.flag_id), str(schedule_id))

        return True

    # Rollout phase methods

    async def get_rollout_phases(self, flag_id: UUID) -> list[RolloutPhase]:
        """Get rollout phases for a flag.

        Args:
            flag_id: The UUID of the flag.

        Returns:
            List of rollout phases for the flag, ordered by phase number.

        """
        # Get all phase IDs from the flag-specific index
        index_key = self._rollout_phases_index_key(flag_id)
        phase_ids = await self._redis.smembers(index_key)

        if not phase_ids:
            return []

        # Get all phases
        result = []
        for phase_id in phase_ids:
            key = self._rollout_phase_key(UUID(phase_id))
            data = await self._redis.get(key)
            if data:
                phase = self._deserialize_rollout_phase(data)
                result.append(phase)

        # Sort by phase_number
        result.sort(key=lambda p: p.phase_number)
        return result

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

        # Store the phase
        key = self._rollout_phase_key(phase.id)
        await self._redis.set(key, self._serialize_rollout_phase(phase))

        # Add to flag-specific index
        await self._redis.sadd(self._rollout_phases_index_key(phase.flag_id), str(phase.id))

        return phase
