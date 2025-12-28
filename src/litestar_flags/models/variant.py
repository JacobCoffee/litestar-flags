"""Flag variant model for A/B testing."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from litestar_flags.models.base import HAS_ADVANCED_ALCHEMY

if TYPE_CHECKING:
    from litestar_flags.models.flag import FeatureFlag

__all__ = ["FlagVariant"]


if HAS_ADVANCED_ALCHEMY:
    from advanced_alchemy.base import UUIDv7AuditBase
    from sqlalchemy import JSON, ForeignKey, Index
    from sqlalchemy.orm import Mapped, mapped_column, relationship

    class FlagVariant(UUIDv7AuditBase):
        """Variant for multivariate flags and A/B testing.

        Weights should sum to 100 for percentage-based distribution.
        If weights don't sum to 100, they will be normalized.

        Attributes:
            flag_id: Reference to the parent flag.
            key: Unique key for this variant within the flag.
            name: Human-readable name for the variant.
            description: Optional description of the variant.
            value: The value to return when this variant is selected.
            weight: Distribution weight (0-100) for this variant.
            flag: Reference to the parent FeatureFlag.

        Example:
            # A/B test with 50/50 split
            variant_a = FlagVariant(key="control", name="Control", weight=50, value={})
            variant_b = FlagVariant(key="treatment", name="Treatment", weight=50, value={"new_ui": True})

        """

        __tablename__ = "flag_variants"

        flag_id: Mapped[UUID] = mapped_column(ForeignKey("feature_flags.id", ondelete="CASCADE"))

        # Variant identification
        key: Mapped[str]
        name: Mapped[str]
        description: Mapped[str | None] = mapped_column(default=None)

        # Variant value
        value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

        # Distribution weight (0-100)
        weight: Mapped[int] = mapped_column(default=0)

        # Relationships
        flag: Mapped[FeatureFlag] = relationship("FeatureFlag", back_populates="variants")

        __table_args__ = (Index("ix_flag_variants_flag_key", "flag_id", "key", unique=True),)

        def __repr__(self) -> str:
            return f"<FlagVariant(key={self.key!r}, weight={self.weight})>"

else:
    from dataclasses import dataclass, field
    from uuid import uuid4

    @dataclass
    class FlagVariant:  # type: ignore[no-redef]
        """Flag variant model (dataclass fallback when advanced-alchemy not installed)."""

        key: str
        name: str
        flag_id: UUID | None = None
        id: UUID = field(default_factory=uuid4)
        description: str | None = None
        value: dict[str, Any] = field(default_factory=dict)
        weight: int = 0
        flag: FeatureFlag | None = None
        created_at: datetime | None = None
        updated_at: datetime | None = None

        def __repr__(self) -> str:
            return f"<FlagVariant(key={self.key!r}, weight={self.weight})>"
