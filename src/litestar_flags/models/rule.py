"""Flag rule model for targeting conditions."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from litestar_flags.models.base import HAS_ADVANCED_ALCHEMY

if TYPE_CHECKING:
    from litestar_flags.models.flag import FeatureFlag

__all__ = ["FlagRule"]


if HAS_ADVANCED_ALCHEMY:
    from advanced_alchemy.base import UUIDv7AuditBase
    from sqlalchemy import JSON, ForeignKey, Index
    from sqlalchemy.orm import Mapped, mapped_column, relationship

    class FlagRule(UUIDv7AuditBase):
        """Targeting rule for conditional flag evaluation.

        Rules are evaluated in priority order (lower number = higher priority).
        The first matching rule determines the flag value.

        Attributes:
            flag_id: Reference to the parent flag.
            name: Name of the rule for identification.
            description: Optional description of what this rule targets.
            priority: Evaluation order (lower = evaluated first).
            enabled: Whether this rule is active.
            conditions: JSON array of condition objects.
            serve_enabled: Boolean value to serve when rule matches (for boolean flags).
            serve_value: Value to serve when rule matches (for non-boolean flags).
            rollout_percentage: Optional percentage rollout (0-100).
            flag: Reference to the parent FeatureFlag.

        Example conditions format::

            [
                {"attribute": "country", "operator": "in", "value": ["US", "CA"]},
                {"attribute": "plan", "operator": "eq", "value": "premium"}
            ]

        """

        __tablename__ = "flag_rules"

        flag_id: Mapped[UUID] = mapped_column(ForeignKey("feature_flags.id", ondelete="CASCADE"))

        # Rule identification
        name: Mapped[str]
        description: Mapped[str | None] = mapped_column(default=None)
        priority: Mapped[int] = mapped_column(default=0, index=True)
        enabled: Mapped[bool] = mapped_column(default=True)

        # Conditions (JSON array of condition objects)
        conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

        # Rule outcome
        serve_enabled: Mapped[bool] = mapped_column(default=True)
        serve_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)

        # Percentage rollout (0-100, None = 100%)
        rollout_percentage: Mapped[int | None] = mapped_column(default=None)

        # Relationships
        flag: Mapped[FeatureFlag] = relationship("FeatureFlag", back_populates="rules")

        __table_args__ = (Index("ix_flag_rules_flag_priority", "flag_id", "priority"),)

        def __repr__(self) -> str:
            return f"<FlagRule(name={self.name!r}, priority={self.priority})>"

else:
    from dataclasses import dataclass, field
    from uuid import uuid4

    @dataclass
    class FlagRule:  # type: ignore[no-redef]
        """Flag rule model (dataclass fallback when advanced-alchemy not installed)."""

        name: str
        flag_id: UUID | None = None
        id: UUID = field(default_factory=uuid4)
        description: str | None = None
        priority: int = 0
        enabled: bool = True
        conditions: list[dict[str, Any]] = field(default_factory=list)
        serve_enabled: bool = True
        serve_value: dict[str, Any] | None = None
        rollout_percentage: int | None = None
        flag: FeatureFlag | None = None
        created_at: datetime | None = None
        updated_at: datetime | None = None

        def __repr__(self) -> str:
            return f"<FlagRule(name={self.name!r}, priority={self.priority})>"
