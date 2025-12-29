"""Segment model for reusable user targeting groups."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from litestar_flags.models.base import HAS_ADVANCED_ALCHEMY

if TYPE_CHECKING:
    pass

__all__ = ["Segment"]


if HAS_ADVANCED_ALCHEMY:
    from advanced_alchemy.base import UUIDv7AuditBase
    from sqlalchemy import JSON, ForeignKey, Index
    from sqlalchemy.orm import Mapped, mapped_column, relationship

    class Segment(UUIDv7AuditBase):
        """Reusable user segment for targeting rules.

        Segments define groups of users based on shared attributes, enabling
        consistent targeting across multiple flags. Segments can be nested
        to create hierarchical targeting structures.

        Attributes:
            name: Unique identifier for the segment (e.g., "premium_users").
            description: Optional description of what users this segment targets.
            conditions: JSON array of condition objects defining segment membership.
            parent_segment_id: Optional reference to parent segment for nesting.
            enabled: Whether this segment is active for evaluation.
            parent: Reference to the parent Segment (for nested segments).
            children: Child segments that inherit from this segment.

        Example conditions format::

            [
                {"attribute": "country", "operator": "in", "value": ["US", "CA"]},
                {"attribute": "plan", "operator": "eq", "value": "premium"}
            ]

        Nested segments example:
            A "premium_us_users" segment could have "premium_users" as parent,
            adding a country="US" condition to the inherited conditions.

        """

        __tablename__ = "segments"

        # Segment identification
        name: Mapped[str] = mapped_column(unique=True, index=True)
        description: Mapped[str | None] = mapped_column(default=None)

        # Conditions (JSON array of condition objects - same format as FlagRule)
        conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

        # Nested segment support
        parent_segment_id: Mapped[UUID | None] = mapped_column(
            ForeignKey("segments.id", ondelete="SET NULL"),
            default=None,
            index=True,
        )

        # Status
        enabled: Mapped[bool] = mapped_column(default=True, index=True)

        # Self-referential relationships for nested segments
        parent: Mapped[Segment | None] = relationship(
            "Segment",
            back_populates="children",
            remote_side="Segment.id",
            foreign_keys=[parent_segment_id],
        )
        children: Mapped[list[Segment]] = relationship(
            "Segment",
            back_populates="parent",
            foreign_keys=[parent_segment_id],
            lazy="selectin",
        )

        __table_args__ = (
            Index("ix_segments_enabled_name", "enabled", "name"),
            Index("ix_segments_parent", "parent_segment_id"),
        )

        def __repr__(self) -> str:
            return f"<Segment(name={self.name!r}, enabled={self.enabled})>"

else:
    from dataclasses import dataclass, field
    from uuid import uuid4

    @dataclass
    class Segment:  # type: ignore[no-redef]
        """Segment model (dataclass fallback when advanced-alchemy not installed).

        Represents a reusable user segment for targeting rules. Segments define
        groups of users based on shared attributes.

        Attributes:
            name: Unique identifier for the segment.
            id: Unique UUID for the segment instance.
            description: Optional description of what users this segment targets.
            conditions: List of condition dictionaries defining segment membership.
            parent_segment_id: Optional reference to parent segment for nesting.
            enabled: Whether this segment is active for evaluation.
            parent: Reference to the parent Segment (for nested segments).
            children: Child segments that inherit from this segment.
            created_at: Timestamp when the segment was created.
            updated_at: Timestamp when the segment was last updated.

        """

        name: str
        id: UUID = field(default_factory=uuid4)
        description: str | None = None
        conditions: list[dict[str, Any]] = field(default_factory=list)
        parent_segment_id: UUID | None = None
        enabled: bool = True
        parent: Segment | None = None
        children: list[Segment] = field(default_factory=list)
        created_at: datetime | None = None
        updated_at: datetime | None = None

        def __repr__(self) -> str:
            return f"<Segment(name={self.name!r}, enabled={self.enabled})>"
