"""Flag override model for entity-specific overrides."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from litestar_flags.models.base import HAS_ADVANCED_ALCHEMY

if TYPE_CHECKING:
    from litestar_flags.models.flag import FeatureFlag

__all__ = ["FlagOverride"]


if HAS_ADVANCED_ALCHEMY:
    from advanced_alchemy.base import UUIDv7AuditBase
    from sqlalchemy import JSON, ForeignKey, Index
    from sqlalchemy.orm import Mapped, mapped_column, relationship

    class FlagOverride(UUIDv7AuditBase):
        """Entity-specific flag override.

        Overrides take precedence over rules and default values.
        They allow specific users, organizations, or other entities
        to have a different flag value than what rules would determine.

        Attributes:
            flag_id: Reference to the parent flag.
            entity_type: Type of entity (e.g., "user", "organization", "tenant").
            entity_id: Identifier of the specific entity.
            enabled: Whether the flag is enabled for this entity.
            value: Optional value override for non-boolean flags.
            expires_at: Optional expiration time for the override.
            flag: Reference to the parent FeatureFlag.

        Example::

            # Enable beta feature for specific user
            override = FlagOverride(
                entity_type="user",
                entity_id="user-123",
                enabled=True,
            )

            # Temporary override with expiration
            override = FlagOverride(
                entity_type="organization",
                entity_id="org-456",
                enabled=True,
                expires_at=datetime(2024, 12, 31),
            )

        """

        __tablename__ = "flag_overrides"

        flag_id: Mapped[UUID] = mapped_column(ForeignKey("feature_flags.id", ondelete="CASCADE"))

        # Target entity
        entity_type: Mapped[str]
        entity_id: Mapped[str] = mapped_column(index=True)

        # Override value
        enabled: Mapped[bool]
        value: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)

        # Expiration (optional)
        expires_at: Mapped[datetime | None] = mapped_column(default=None)

        # Relationships
        flag: Mapped[FeatureFlag] = relationship("FeatureFlag", back_populates="overrides")

        __table_args__ = (
            Index("ix_flag_overrides_entity", "flag_id", "entity_type", "entity_id", unique=True),
            Index("ix_flag_overrides_expires", "expires_at"),
        )

        def __repr__(self) -> str:
            return f"<FlagOverride(entity_type={self.entity_type!r}, entity_id={self.entity_id!r})>"

        def is_expired(self, now: datetime | None = None) -> bool:
            """Check if this override has expired.

            Args:
                now: Current time to check against. Defaults to UTC now.

            Returns:
                True if the override has expired.

            """
            if self.expires_at is None:
                return False
            if now is None:
                from datetime import datetime

                now = datetime.now(UTC)
            return now > self.expires_at

else:
    from dataclasses import dataclass, field
    from uuid import uuid4

    @dataclass
    class FlagOverride:  # type: ignore[no-redef]
        """Flag override model (dataclass fallback when advanced-alchemy not installed)."""

        entity_type: str
        entity_id: str
        enabled: bool
        flag_id: UUID | None = None
        id: UUID = field(default_factory=uuid4)
        value: dict[str, Any] | None = None
        expires_at: datetime | None = None
        flag: FeatureFlag | None = None
        created_at: datetime | None = None
        updated_at: datetime | None = None

        def __repr__(self) -> str:
            return f"<FlagOverride(entity_type={self.entity_type!r}, entity_id={self.entity_id!r})>"

        def is_expired(self, now: datetime | None = None) -> bool:
            """Check if this override has expired."""
            if self.expires_at is None:
                return False
            if now is None:
                from datetime import datetime

                now = datetime.now(UTC)
            return now > self.expires_at
