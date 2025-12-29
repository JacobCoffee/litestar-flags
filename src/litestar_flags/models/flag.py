"""Feature flag model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from litestar_flags.models.base import HAS_ADVANCED_ALCHEMY
from litestar_flags.types import FlagStatus, FlagType

if TYPE_CHECKING:
    from litestar_flags.models.override import FlagOverride
    from litestar_flags.models.rule import FlagRule
    from litestar_flags.models.schedule import RolloutPhase, ScheduledFlagChange, TimeSchedule
    from litestar_flags.models.variant import FlagVariant

__all__ = ["FeatureFlag"]


if HAS_ADVANCED_ALCHEMY:
    from advanced_alchemy.base import UUIDv7AuditBase
    from sqlalchemy import JSON, Index
    from sqlalchemy.orm import Mapped, mapped_column, relationship

    class FeatureFlag(UUIDv7AuditBase):
        """Core feature flag model.

        Uses UUIDv7 for time-sortable IDs and automatic audit timestamps.

        Attributes:
            key: Unique identifier for the flag (used in code).
            name: Human-readable name for the flag.
            description: Optional description of the flag's purpose.
            flag_type: The type of value the flag returns.
            status: Current lifecycle status of the flag.
            default_enabled: Default boolean value when flag type is BOOLEAN.
            default_value: Default value for non-boolean flags (stored as JSON).
            tags: List of tags for organizing flags.
            metadata: Additional metadata stored as JSON.
            rules: Targeting rules for conditional evaluation.
            overrides: Entity-specific overrides.
            variants: Variants for A/B testing.

        """

        __tablename__ = "feature_flags"

        # Identifiers
        key: Mapped[str] = mapped_column(unique=True, index=True)
        name: Mapped[str]
        description: Mapped[str | None] = mapped_column(default=None)

        # Flag configuration
        flag_type: Mapped[FlagType] = mapped_column(default=FlagType.BOOLEAN)
        status: Mapped[FlagStatus] = mapped_column(default=FlagStatus.ACTIVE, index=True)

        # Default values
        default_enabled: Mapped[bool] = mapped_column(default=False)
        default_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)

        # Metadata
        tags: Mapped[list[str]] = mapped_column(JSON, default=list)
        metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

        # Relationships
        rules: Mapped[list[FlagRule]] = relationship(
            "FlagRule",
            back_populates="flag",
            cascade="all, delete-orphan",
            order_by="FlagRule.priority",
            lazy="selectin",
        )
        overrides: Mapped[list[FlagOverride]] = relationship(
            "FlagOverride",
            back_populates="flag",
            cascade="all, delete-orphan",
            lazy="selectin",
        )
        variants: Mapped[list[FlagVariant]] = relationship(
            "FlagVariant",
            back_populates="flag",
            cascade="all, delete-orphan",
            lazy="selectin",
        )
        scheduled_changes: Mapped[list[ScheduledFlagChange]] = relationship(
            "ScheduledFlagChange",
            back_populates="flag",
            cascade="all, delete-orphan",
            order_by="ScheduledFlagChange.scheduled_at",
            lazy="selectin",
        )
        time_schedules: Mapped[list[TimeSchedule]] = relationship(
            "TimeSchedule",
            back_populates="flag",
            cascade="all, delete-orphan",
            lazy="selectin",
        )
        rollout_phases: Mapped[list[RolloutPhase]] = relationship(
            "RolloutPhase",
            back_populates="flag",
            cascade="all, delete-orphan",
            order_by="RolloutPhase.phase_number",
            lazy="selectin",
        )

        __table_args__ = (Index("ix_feature_flags_status_key", "status", "key"),)

        def __repr__(self) -> str:
            return f"<FeatureFlag(key={self.key!r}, status={self.status.value!r})>"

else:
    # Fallback for when advanced-alchemy is not installed
    from dataclasses import dataclass, field
    from uuid import uuid4

    @dataclass(slots=True)
    class FeatureFlag:  # type: ignore[no-redef]
        """Feature flag model (dataclass fallback when advanced-alchemy not installed)."""

        key: str
        name: str
        id: UUID = field(default_factory=uuid4)
        description: str | None = None
        flag_type: FlagType = FlagType.BOOLEAN
        status: FlagStatus = FlagStatus.ACTIVE
        default_enabled: bool = False
        default_value: dict[str, Any] | None = None
        tags: list[str] = field(default_factory=list)
        metadata_: dict[str, Any] = field(default_factory=dict)
        rules: list[FlagRule] = field(default_factory=list)
        overrides: list[FlagOverride] = field(default_factory=list)
        variants: list[FlagVariant] = field(default_factory=list)
        scheduled_changes: list[ScheduledFlagChange] = field(default_factory=list)
        time_schedules: list[TimeSchedule] = field(default_factory=list)
        rollout_phases: list[RolloutPhase] = field(default_factory=list)
        created_at: datetime | None = None
        updated_at: datetime | None = None

        def __repr__(self) -> str:
            return f"<FeatureFlag(key={self.key!r}, status={self.status.value!r})>"
