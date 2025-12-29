"""EnvironmentFlag model for environment-specific flag overrides."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from litestar_flags.models.base import HAS_ADVANCED_ALCHEMY

if TYPE_CHECKING:
    from litestar_flags.models.environment import Environment
    from litestar_flags.models.flag import FeatureFlag
    from litestar_flags.models.rule import FlagRule
    from litestar_flags.models.variant import FlagVariant

__all__ = ["EnvironmentFlag"]


if HAS_ADVANCED_ALCHEMY:
    from advanced_alchemy.base import UUIDv7AuditBase
    from sqlalchemy import JSON, ForeignKey, Index
    from sqlalchemy.orm import Mapped, mapped_column, relationship

    class EnvironmentFlag(UUIDv7AuditBase):
        """Environment-specific flag configuration override.

        EnvironmentFlag allows flags to have different configurations per
        environment. Values set to None indicate inheritance from the base
        flag configuration, while explicit values override the base.

        Attributes:
            environment_id: Reference to the environment this applies to.
            flag_id: Reference to the base flag this overrides.
            enabled: Override enabled state (None = inherit from base flag).
            percentage: Override rollout percentage (None = inherit).
            rules: Override targeting rules as JSON (None = inherit).
            variants: Override variants as JSON (None = inherit).
            environment: Reference to the Environment.
            flag: Reference to the base FeatureFlag.

        Example::

            # Override flag to be disabled in staging
            env_flag = EnvironmentFlag(
                environment_id=staging.id,
                flag_id=new_feature.id,
                enabled=False,
            )

            # Override rollout percentage in production
            env_flag = EnvironmentFlag(
                environment_id=production.id,
                flag_id=new_feature.id,
                percentage=10.0,  # 10% rollout in prod
            )

        """

        __tablename__ = "environment_flags"

        # Foreign keys
        environment_id: Mapped[UUID] = mapped_column(
            ForeignKey("environments.id", ondelete="CASCADE"),
            index=True,
        )
        flag_id: Mapped[UUID] = mapped_column(
            ForeignKey("feature_flags.id", ondelete="CASCADE"),
            index=True,
        )

        # Override values (None = inherit from base flag)
        enabled: Mapped[bool | None] = mapped_column(default=None)
        percentage: Mapped[float | None] = mapped_column(default=None)

        # Complex overrides stored as JSON (None = inherit)
        rules: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, default=None)
        variants: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, default=None)

        # Relationships
        environment: Mapped[Environment] = relationship(
            "Environment",
            foreign_keys=[environment_id],
            lazy="selectin",
        )
        flag: Mapped[FeatureFlag] = relationship(
            "FeatureFlag",
            foreign_keys=[flag_id],
            lazy="selectin",
        )

        __table_args__ = (
            Index(
                "ix_environment_flags_env_flag",
                "environment_id",
                "flag_id",
                unique=True,
            ),
            Index("ix_environment_flags_flag", "flag_id"),
        )

        def __repr__(self) -> str:
            return f"<EnvironmentFlag(environment_id={self.environment_id!r}, flag_id={self.flag_id!r})>"

else:
    from dataclasses import dataclass, field
    from uuid import uuid4

    @dataclass(slots=True)
    class EnvironmentFlag:  # type: ignore[no-redef]
        """EnvironmentFlag model (dataclass fallback when advanced-alchemy not installed).

        Represents environment-specific flag configuration overrides. Values
        set to None indicate inheritance from the base flag configuration.

        Attributes:
            environment_id: Reference to the environment this applies to.
            flag_id: Reference to the base flag this overrides.
            id: Unique UUID for this environment flag instance.
            enabled: Override enabled state (None = inherit from base flag).
            percentage: Override rollout percentage (None = inherit).
            rules: Override targeting rules (None = inherit).
            variants: Override variants (None = inherit).
            environment: Reference to the Environment.
            flag: Reference to the base FeatureFlag.
            created_at: Timestamp when the override was created.
            updated_at: Timestamp when the override was last updated.

        """

        environment_id: UUID
        flag_id: UUID
        id: UUID = field(default_factory=uuid4)
        enabled: bool | None = None
        percentage: float | None = None
        rules: list[FlagRule] | None = None
        variants: list[FlagVariant] | None = None
        environment: Environment | None = None
        flag: FeatureFlag | None = None
        created_at: datetime | None = None
        updated_at: datetime | None = None

        def __repr__(self) -> str:
            return f"<EnvironmentFlag(environment_id={self.environment_id!r}, flag_id={self.flag_id!r})>"
