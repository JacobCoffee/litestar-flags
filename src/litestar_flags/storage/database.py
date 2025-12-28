"""Database storage backend using Advanced-Alchemy."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from litestar_flags.models.base import HAS_ADVANCED_ALCHEMY
from litestar_flags.types import FlagStatus

if not HAS_ADVANCED_ALCHEMY:
    raise ImportError(
        "Database backend requires 'advanced-alchemy'. Install with: pip install litestar-flags[database]"
    )

from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from litestar_flags.models.flag import FeatureFlag
from litestar_flags.models.override import FlagOverride
from litestar_flags.models.schedule import RolloutPhase, ScheduledFlagChange, TimeSchedule

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

__all__ = [
    "DatabaseStorageBackend",
    "FeatureFlagRepository",
    "FlagOverrideRepository",
    "RolloutPhaseRepository",
    "ScheduledFlagChangeRepository",
    "TimeScheduleRepository",
]


class FeatureFlagRepository(SQLAlchemyAsyncRepository[FeatureFlag]):
    """Repository for feature flag CRUD operations."""

    model_type = FeatureFlag

    async def get_by_key(self, key: str) -> FeatureFlag | None:
        """Get a flag by its unique key.

        Args:
            key: The flag key.

        Returns:
            The flag if found, None otherwise.

        """
        return await self.get_one_or_none(FeatureFlag.key == key)

    async def get_by_keys(self, keys: Sequence[str]) -> list[FeatureFlag]:
        """Get multiple flags by their keys.

        Args:
            keys: The flag keys.

        Returns:
            List of found flags.

        """
        if not keys:
            return []
        return await self.list(FeatureFlag.key.in_(keys))

    async def get_active_flags(self) -> list[FeatureFlag]:
        """Get all active flags.

        Returns:
            List of active flags.

        """
        return await self.list(FeatureFlag.status == FlagStatus.ACTIVE)


class FlagOverrideRepository(SQLAlchemyAsyncRepository[FlagOverride]):
    """Repository for flag override CRUD operations."""

    model_type = FlagOverride

    async def get_override(
        self,
        flag_id: UUID,
        entity_type: str,
        entity_id: str,
    ) -> FlagOverride | None:
        """Get an override for a specific entity.

        Args:
            flag_id: The flag's UUID.
            entity_type: Type of entity.
            entity_id: The entity's identifier.

        Returns:
            The override if found, None otherwise.

        """
        return await self.get_one_or_none(
            FlagOverride.flag_id == flag_id,
            FlagOverride.entity_type == entity_type,
            FlagOverride.entity_id == entity_id,
        )


class ScheduledFlagChangeRepository(SQLAlchemyAsyncRepository[ScheduledFlagChange]):
    """Repository for scheduled flag change CRUD operations."""

    model_type = ScheduledFlagChange

    async def get_pending_changes(
        self,
        flag_id: UUID | None = None,
    ) -> list[ScheduledFlagChange]:
        """Get pending (not yet executed) scheduled changes.

        Args:
            flag_id: If provided, filter to changes for this flag only.

        Returns:
            List of pending scheduled changes, ordered by scheduled_at.

        """
        if flag_id is not None:
            return await self.list(
                ScheduledFlagChange.executed == False,  # noqa: E712
                ScheduledFlagChange.flag_id == flag_id,
                order_by=[ScheduledFlagChange.scheduled_at],
            )
        return await self.list(
            ScheduledFlagChange.executed == False,  # noqa: E712
            order_by=[ScheduledFlagChange.scheduled_at],
        )

    async def get_all_changes(
        self,
        flag_id: UUID | None = None,
    ) -> list[ScheduledFlagChange]:
        """Get all scheduled changes (pending and executed).

        Args:
            flag_id: If provided, filter to changes for this flag only.

        Returns:
            List of scheduled changes, ordered by scheduled_at.

        """
        if flag_id is not None:
            return await self.list(
                ScheduledFlagChange.flag_id == flag_id,
                order_by=[ScheduledFlagChange.scheduled_at],
            )
        return await self.list(order_by=[ScheduledFlagChange.scheduled_at])


class TimeScheduleRepository(SQLAlchemyAsyncRepository[TimeSchedule]):
    """Repository for time schedule CRUD operations."""

    model_type = TimeSchedule

    async def get_schedules_for_flag(self, flag_id: UUID) -> list[TimeSchedule]:
        """Get all time schedules for a flag.

        Args:
            flag_id: The flag's UUID.

        Returns:
            List of time schedules for the flag.

        """
        return await self.list(TimeSchedule.flag_id == flag_id)

    async def get_enabled_schedules(
        self,
        flag_id: UUID | None = None,
    ) -> list[TimeSchedule]:
        """Get all enabled time schedules.

        Args:
            flag_id: If provided, filter to schedules for this flag only.

        Returns:
            List of enabled time schedules.

        """
        if flag_id is not None:
            return await self.list(
                TimeSchedule.enabled == True,  # noqa: E712
                TimeSchedule.flag_id == flag_id,
            )
        return await self.list(TimeSchedule.enabled == True)  # noqa: E712


class RolloutPhaseRepository(SQLAlchemyAsyncRepository[RolloutPhase]):
    """Repository for rollout phase CRUD operations."""

    model_type = RolloutPhase

    async def get_phases_for_flag(self, flag_id: UUID) -> list[RolloutPhase]:
        """Get all rollout phases for a flag.

        Args:
            flag_id: The flag's UUID.

        Returns:
            List of rollout phases, ordered by phase_number.

        """
        return await self.list(
            RolloutPhase.flag_id == flag_id,
            order_by=[RolloutPhase.phase_number],
        )

    async def get_pending_phases(self, flag_id: UUID) -> list[RolloutPhase]:
        """Get pending (not yet executed) rollout phases for a flag.

        Args:
            flag_id: The flag's UUID.

        Returns:
            List of pending rollout phases, ordered by phase_number.

        """
        return await self.list(
            RolloutPhase.flag_id == flag_id,
            RolloutPhase.executed == False,  # noqa: E712
            order_by=[RolloutPhase.phase_number],
        )


class DatabaseStorageBackend:
    """Database storage backend using Advanced-Alchemy.

    This backend stores feature flags and related data in a relational
    database using SQLAlchemy async operations.

    Example:
        >>> storage = await DatabaseStorageBackend.create(
        ...     connection_string="postgresql+asyncpg://user:pass@localhost/db"
        ... )
        >>> flag = await storage.get_flag("my-feature")

    """

    def __init__(
        self,
        engine: AsyncEngine,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        """Initialize the database storage backend.

        Args:
            engine: The SQLAlchemy async engine.
            session_maker: The session maker factory.

        """
        self._engine = engine
        self._session_maker = session_maker

    @classmethod
    async def create(
        cls,
        connection_string: str,
        table_prefix: str = "ff_",
        create_tables: bool = True,
        **engine_kwargs: dict,
    ) -> DatabaseStorageBackend:
        """Create a new database storage backend.

        Args:
            connection_string: Database connection string.
            table_prefix: Prefix for table names (not currently used).
            create_tables: Whether to create tables on startup.
            **engine_kwargs: Additional arguments for create_async_engine.

        Returns:
            Configured DatabaseStorageBackend instance.

        """
        engine = create_async_engine(
            connection_string,
            echo=engine_kwargs.pop("echo", False),
            **engine_kwargs,
        )

        if create_tables:
            from litestar_flags.models.flag import FeatureFlag
            from litestar_flags.models.override import FlagOverride
            from litestar_flags.models.rule import FlagRule
            from litestar_flags.models.schedule import (
                RolloutPhase,
                ScheduledFlagChange,
                TimeSchedule,
            )
            from litestar_flags.models.variant import FlagVariant

            # Import to register models
            _ = FeatureFlag, FlagOverride, FlagRule, FlagVariant
            _ = ScheduledFlagChange, TimeSchedule, RolloutPhase

            async with engine.begin() as conn:
                from advanced_alchemy.base import orm_registry

                await conn.run_sync(orm_registry.metadata.create_all)

        session_maker = async_sessionmaker(engine, expire_on_commit=False)

        return cls(engine=engine, session_maker=session_maker)

    async def get_flag(self, key: str) -> FeatureFlag | None:
        """Retrieve a single flag by key.

        Args:
            key: The unique flag key.

        Returns:
            The FeatureFlag if found, None otherwise.

        """
        async with self._session_maker() as session:
            repo = FeatureFlagRepository(session=session)
            return await repo.get_by_key(key)

    async def get_flags(self, keys: Sequence[str]) -> dict[str, FeatureFlag]:
        """Retrieve multiple flags by keys.

        Args:
            keys: Sequence of flag keys to retrieve.

        Returns:
            Dictionary mapping flag keys to FeatureFlag objects.

        """
        async with self._session_maker() as session:
            repo = FeatureFlagRepository(session=session)
            flags = await repo.get_by_keys(keys)
            return {flag.key: flag for flag in flags}

    async def get_all_active_flags(self) -> list[FeatureFlag]:
        """Retrieve all active flags.

        Returns:
            List of all FeatureFlag objects with ACTIVE status.

        """
        async with self._session_maker() as session:
            repo = FeatureFlagRepository(session=session)
            return await repo.get_active_flags()

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
        async with self._session_maker() as session:
            repo = FlagOverrideRepository(session=session)
            return await repo.get_override(flag_id, entity_type, entity_id)

    async def create_flag(self, flag: FeatureFlag) -> FeatureFlag:
        """Create a new flag.

        Args:
            flag: The flag to create.

        Returns:
            The created flag with any generated fields populated.

        """
        async with self._session_maker() as session:
            repo = FeatureFlagRepository(session=session)
            created = await repo.add(flag)
            await session.commit()
            await session.refresh(created)
            return created

    async def update_flag(self, flag: FeatureFlag) -> FeatureFlag:
        """Update an existing flag.

        Args:
            flag: The flag with updated values.

        Returns:
            The updated flag.

        """
        async with self._session_maker() as session:
            repo = FeatureFlagRepository(session=session)
            updated = await repo.update(flag)
            await session.commit()
            await session.refresh(updated)
            return updated

    async def delete_flag(self, key: str) -> bool:
        """Delete a flag by key.

        Args:
            key: The unique flag key.

        Returns:
            True if the flag was deleted, False if not found.

        """
        async with self._session_maker() as session:
            repo = FeatureFlagRepository(session=session)
            flag = await repo.get_by_key(key)
            if flag is None:
                return False
            await repo.delete(flag.id)
            await session.commit()
            return True

    async def create_override(self, override: FlagOverride) -> FlagOverride:
        """Create a new override.

        Args:
            override: The override to create.

        Returns:
            The created override.

        """
        async with self._session_maker() as session:
            repo = FlagOverrideRepository(session=session)
            created = await repo.add(override)
            await session.commit()
            await session.refresh(created)
            return created

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
        async with self._session_maker() as session:
            repo = FlagOverrideRepository(session=session)
            override = await repo.get_override(flag_id, entity_type, entity_id)
            if override is None:
                return False
            await repo.delete(override.id)
            await session.commit()
            return True

    async def health_check(self) -> bool:
        """Check storage backend health.

        Returns:
            True if the backend is healthy, False otherwise.

        """
        try:
            async with self._session_maker() as session:
                await session.execute(select(1))
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close database connections."""
        await self._engine.dispose()

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
        async with self._session_maker() as session:
            repo = ScheduledFlagChangeRepository(session=session)
            if pending_only:
                return await repo.get_pending_changes(flag_id)
            return await repo.get_all_changes(flag_id)

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
        async with self._session_maker() as session:
            repo = ScheduledFlagChangeRepository(session=session)
            created = await repo.add(change)
            await session.commit()
            await session.refresh(created)
            return created

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
        async with self._session_maker() as session:
            repo = ScheduledFlagChangeRepository(session=session)
            updated = await repo.update(change)
            await session.commit()
            await session.refresh(updated)
            return updated

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
        async with self._session_maker() as session:
            repo = TimeScheduleRepository(session=session)
            if flag_id is not None:
                return await repo.get_schedules_for_flag(flag_id)
            return await repo.list()

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
        async with self._session_maker() as session:
            repo = TimeScheduleRepository(session=session)
            created = await repo.add(schedule)
            await session.commit()
            await session.refresh(created)
            return created

    async def delete_time_schedule(self, schedule_id: UUID) -> bool:
        """Delete a time schedule.

        Args:
            schedule_id: The UUID of the time schedule to delete.

        Returns:
            True if the schedule was deleted, False if not found.

        """
        async with self._session_maker() as session:
            repo = TimeScheduleRepository(session=session)
            schedule = await repo.get(schedule_id)
            if schedule is None:
                return False
            await repo.delete(schedule_id)
            await session.commit()
            return True

    # Rollout phase methods

    async def get_rollout_phases(self, flag_id: UUID) -> list[RolloutPhase]:
        """Get rollout phases for a flag.

        Args:
            flag_id: The UUID of the flag.

        Returns:
            List of rollout phases for the flag, ordered by phase number.

        """
        async with self._session_maker() as session:
            repo = RolloutPhaseRepository(session=session)
            return await repo.get_phases_for_flag(flag_id)

    async def create_rollout_phase(self, phase: RolloutPhase) -> RolloutPhase:
        """Create a new rollout phase.

        Args:
            phase: The rollout phase to create.

        Returns:
            The created rollout phase with any generated fields populated.

        """
        async with self._session_maker() as session:
            repo = RolloutPhaseRepository(session=session)
            created = await repo.add(phase)
            await session.commit()
            await session.refresh(created)
            return created
