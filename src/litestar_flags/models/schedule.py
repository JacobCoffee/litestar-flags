"""Schedule models for time-based flag rules."""

from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from litestar_flags.models.base import HAS_ADVANCED_ALCHEMY
from litestar_flags.types import ChangeType, RecurrenceType

if TYPE_CHECKING:
    from litestar_flags.models.flag import FeatureFlag

__all__ = ["RolloutPhase", "ScheduledFlagChange", "TimeSchedule"]


if HAS_ADVANCED_ALCHEMY:
    from advanced_alchemy.base import UUIDv7AuditBase
    from sqlalchemy import JSON, ForeignKey, Index
    from sqlalchemy.orm import Mapped, mapped_column, relationship

    class ScheduledFlagChange(UUIDv7AuditBase):
        """Scheduled change to a feature flag.

        Allows scheduling flag state changes (enable/disable) or value updates
        to occur at a specific time in the future.

        Attributes:
            flag_id: Reference to the target flag.
            change_type: Type of change to make (enable, disable, update_value, update_rollout).
            scheduled_at: When the change should be executed (timezone-aware).
            executed: Whether this scheduled change has been executed.
            executed_at: When the change was actually executed.
            new_value: New value for UPDATE_VALUE changes (stored as JSON).
            new_rollout_percentage: New rollout percentage for UPDATE_ROLLOUT changes.
            created_by: User or system that created this scheduled change.
            flag: Reference to the parent FeatureFlag.

        """

        __tablename__ = "scheduled_flag_changes"

        flag_id: Mapped[UUID] = mapped_column(ForeignKey("feature_flags.id", ondelete="CASCADE"))

        # Change configuration
        change_type: Mapped[ChangeType] = mapped_column(default=ChangeType.ENABLE)
        scheduled_at: Mapped[datetime] = mapped_column(index=True)

        # Execution tracking
        executed: Mapped[bool] = mapped_column(default=False, index=True)
        executed_at: Mapped[datetime | None] = mapped_column(default=None)

        # Change values
        new_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
        new_rollout_percentage: Mapped[int | None] = mapped_column(default=None)

        # Audit
        created_by: Mapped[str | None] = mapped_column(default=None)

        # Relationships
        flag: Mapped[FeatureFlag] = relationship("FeatureFlag", back_populates="scheduled_changes")

        __table_args__ = (
            Index("ix_scheduled_flag_changes_pending", "executed", "scheduled_at"),
            Index("ix_scheduled_flag_changes_flag", "flag_id", "scheduled_at"),
        )

        def __repr__(self) -> str:
            return f"<ScheduledFlagChange(type={self.change_type.value!r}, scheduled_at={self.scheduled_at!r})>"

    class TimeSchedule(UUIDv7AuditBase):
        """Recurring time schedule for flag activation.

        Defines time windows when a flag should be active based on
        recurring patterns (daily, weekly, monthly, or cron expressions).

        Attributes:
            flag_id: Reference to the target flag.
            name: Human-readable name for the schedule.
            recurrence_type: Type of recurrence pattern.
            start_time: Start time of the active window (time of day).
            end_time: End time of the active window (time of day).
            days_of_week: Days when schedule is active for WEEKLY (0=Monday, 6=Sunday).
            days_of_month: Days when schedule is active for MONTHLY (1-31).
            cron_expression: Cron expression for CRON type schedules.
            timezone: Timezone for schedule evaluation (default: UTC).
            enabled: Whether this schedule is active.
            flag: Reference to the parent FeatureFlag.

        """

        __tablename__ = "time_schedules"

        flag_id: Mapped[UUID] = mapped_column(ForeignKey("feature_flags.id", ondelete="CASCADE"))

        # Schedule identification
        name: Mapped[str]
        recurrence_type: Mapped[RecurrenceType] = mapped_column(default=RecurrenceType.DAILY)

        # Time window
        start_time: Mapped[time]
        end_time: Mapped[time]

        # Recurrence configuration
        days_of_week: Mapped[list[int] | None] = mapped_column(JSON, default=None)
        days_of_month: Mapped[list[int] | None] = mapped_column(JSON, default=None)
        cron_expression: Mapped[str | None] = mapped_column(default=None)

        # Timezone and status
        timezone: Mapped[str] = mapped_column(default="UTC")
        enabled: Mapped[bool] = mapped_column(default=True, index=True)

        # Validity period (optional bounds for when the schedule is effective)
        valid_from: Mapped[datetime | None] = mapped_column(default=None)
        valid_until: Mapped[datetime | None] = mapped_column(default=None)

        # Relationships
        flag: Mapped[FeatureFlag] = relationship("FeatureFlag", back_populates="time_schedules")

        __table_args__ = (Index("ix_time_schedules_flag_enabled", "flag_id", "enabled"),)

        def __repr__(self) -> str:
            return f"<TimeSchedule(name={self.name!r}, type={self.recurrence_type.value!r})>"

    class RolloutPhase(UUIDv7AuditBase):
        """Phased rollout schedule for gradual flag enablement.

        Defines a series of percentage targets to be reached at specific times,
        allowing for gradual rollout of features.

        Attributes:
            flag_id: Reference to the target flag.
            phase_number: Sequential phase number (starting from 1).
            target_percentage: Target rollout percentage for this phase (0-100).
            scheduled_at: When this phase should be executed.
            executed: Whether this phase has been executed.
            executed_at: When this phase was actually executed.
            flag: Reference to the parent FeatureFlag.

        """

        __tablename__ = "rollout_phases"

        flag_id: Mapped[UUID] = mapped_column(ForeignKey("feature_flags.id", ondelete="CASCADE"))

        # Phase configuration
        phase_number: Mapped[int] = mapped_column(index=True)
        target_percentage: Mapped[int]
        scheduled_at: Mapped[datetime] = mapped_column(index=True)

        # Execution tracking
        executed: Mapped[bool] = mapped_column(default=False, index=True)
        executed_at: Mapped[datetime | None] = mapped_column(default=None)

        # Relationships
        flag: Mapped[FeatureFlag] = relationship("FeatureFlag", back_populates="rollout_phases")

        __table_args__ = (
            Index("ix_rollout_phases_flag_phase", "flag_id", "phase_number"),
            Index("ix_rollout_phases_pending", "executed", "scheduled_at"),
        )

        def __repr__(self) -> str:
            return f"<RolloutPhase(phase={self.phase_number}, target={self.target_percentage}%)>"

else:
    from dataclasses import dataclass, field
    from uuid import uuid4

    @dataclass
    class ScheduledFlagChange:  # type: ignore[no-redef]
        """Scheduled flag change model (dataclass fallback)."""

        flag_id: UUID
        change_type: ChangeType
        scheduled_at: datetime
        id: UUID = field(default_factory=uuid4)
        executed: bool = False
        executed_at: datetime | None = None
        new_value: dict[str, Any] | None = None
        new_rollout_percentage: int | None = None
        created_by: str | None = None
        flag: FeatureFlag | None = None
        created_at: datetime | None = None
        updated_at: datetime | None = None

        def __repr__(self) -> str:
            return f"<ScheduledFlagChange(type={self.change_type.value!r}, scheduled_at={self.scheduled_at!r})>"

    @dataclass
    class TimeSchedule:  # type: ignore[no-redef]
        """Time schedule model (dataclass fallback)."""

        flag_id: UUID
        name: str
        start_time: time
        end_time: time
        id: UUID = field(default_factory=uuid4)
        recurrence_type: RecurrenceType = RecurrenceType.DAILY
        days_of_week: list[int] | None = None
        days_of_month: list[int] | None = None
        cron_expression: str | None = None
        timezone: str = "UTC"
        enabled: bool = True
        valid_from: datetime | None = None
        valid_until: datetime | None = None
        flag: FeatureFlag | None = None
        created_at: datetime | None = None
        updated_at: datetime | None = None

        def __repr__(self) -> str:
            return f"<TimeSchedule(name={self.name!r}, type={self.recurrence_type.value!r})>"

    @dataclass
    class RolloutPhase:  # type: ignore[no-redef]
        """Rollout phase model (dataclass fallback)."""

        flag_id: UUID
        phase_number: int
        target_percentage: int
        scheduled_at: datetime
        id: UUID = field(default_factory=uuid4)
        executed: bool = False
        executed_at: datetime | None = None
        flag: FeatureFlag | None = None
        created_at: datetime | None = None
        updated_at: datetime | None = None

        def __repr__(self) -> str:
            return f"<RolloutPhase(phase={self.phase_number}, target={self.target_percentage}%)>"
