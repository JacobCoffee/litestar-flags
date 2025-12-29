"""Environment model for multi-environment flag management."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from litestar_flags.models.base import HAS_ADVANCED_ALCHEMY

if TYPE_CHECKING:
    pass

__all__ = ["Environment"]


if HAS_ADVANCED_ALCHEMY:
    from advanced_alchemy.base import UUIDv7AuditBase
    from sqlalchemy import JSON, ForeignKey, Index
    from sqlalchemy.orm import Mapped, mapped_column, relationship

    class Environment(UUIDv7AuditBase):
        """Environment model for multi-environment flag management.

        Environments allow flags to have different configurations across
        deployment targets (e.g., development, staging, production).
        Environments can inherit from parent environments, allowing
        hierarchical configuration where staging inherits from dev.

        Attributes:
            name: Human-readable display name (e.g., "Production", "Staging").
            slug: URL-safe unique identifier (e.g., "production", "staging").
            description: Optional description of the environment's purpose.
            parent_id: Optional reference to parent environment for inheritance.
            settings: Environment-specific settings stored as JSON.
            is_active: Whether this environment is active for evaluation.
            parent: Reference to the parent Environment (for inheritance).
            children: Child environments that inherit from this environment.

        Example::

            # Create production environment
            prod = Environment(
                name="Production",
                slug="production",
                description="Live production environment",
                settings={"require_approval": True},
            )

            # Create staging that inherits from production
            staging = Environment(
                name="Staging",
                slug="staging",
                parent_id=prod.id,
                settings={"require_approval": False},
            )

        """

        __tablename__ = "environments"

        # Environment identification
        name: Mapped[str] = mapped_column(index=True)
        slug: Mapped[str] = mapped_column(unique=True, index=True)
        description: Mapped[str | None] = mapped_column(default=None)

        # Inheritance support
        parent_id: Mapped[UUID | None] = mapped_column(
            ForeignKey("environments.id", ondelete="SET NULL"),
            default=None,
            index=True,
        )

        # Environment configuration
        settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

        # Status
        is_active: Mapped[bool] = mapped_column(default=True, index=True)

        # Self-referential relationships for inheritance
        parent: Mapped[Environment | None] = relationship(
            "Environment",
            back_populates="children",
            remote_side="Environment.id",
            foreign_keys=[parent_id],
        )
        children: Mapped[list[Environment]] = relationship(
            "Environment",
            back_populates="parent",
            foreign_keys=[parent_id],
            lazy="selectin",
        )

        __table_args__ = (
            Index("ix_environments_active_slug", "is_active", "slug"),
            Index("ix_environments_parent", "parent_id"),
        )

        def __repr__(self) -> str:
            return f"<Environment(slug={self.slug!r}, is_active={self.is_active})>"

else:
    from dataclasses import dataclass, field
    from uuid import uuid4

    @dataclass(slots=True)
    class Environment:  # type: ignore[no-redef]
        """Environment model (dataclass fallback when advanced-alchemy not installed).

        Represents a deployment environment for multi-environment flag management.
        Environments allow flags to have different configurations across targets.

        Attributes:
            name: Human-readable display name (e.g., "Production", "Staging").
            slug: URL-safe unique identifier (e.g., "production", "staging").
            id: Unique UUID for the environment instance.
            description: Optional description of the environment's purpose.
            parent_id: Optional reference to parent environment for inheritance.
            settings: Environment-specific settings dictionary.
            is_active: Whether this environment is active for evaluation.
            parent: Reference to the parent Environment (for inheritance).
            children: Child environments that inherit from this environment.
            created_at: Timestamp when the environment was created.
            updated_at: Timestamp when the environment was last updated.

        """

        name: str
        slug: str
        id: UUID = field(default_factory=uuid4)
        description: str | None = None
        parent_id: UUID | None = None
        settings: dict[str, Any] = field(default_factory=dict)
        is_active: bool = True
        parent: Environment | None = None
        children: list[Environment] = field(default_factory=list)
        created_at: datetime | None = None
        updated_at: datetime | None = None

        def __repr__(self) -> str:
            return f"<Environment(slug={self.slug!r}, is_active={self.is_active})>"
