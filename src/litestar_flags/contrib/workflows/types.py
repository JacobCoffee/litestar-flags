"""Types for workflow integration."""

from __future__ import annotations

from enum import Enum

__all__ = ["ChangeType", "RolloutStage"]


class ChangeType(str, Enum):
    """Type of flag change being requested."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    TOGGLE = "toggle"
    ROLLOUT = "rollout"


class RolloutStage(str, Enum):
    """Stages for gradual rollout workflows."""

    INITIAL = "initial"  # 5%
    EARLY = "early"  # 25%
    HALF = "half"  # 50%
    MAJORITY = "majority"  # 75%
    FULL = "full"  # 100%

    @property
    def percentage(self) -> int:
        """Get the rollout percentage for this stage."""
        percentages = {
            RolloutStage.INITIAL: 5,
            RolloutStage.EARLY: 25,
            RolloutStage.HALF: 50,
            RolloutStage.MAJORITY: 75,
            RolloutStage.FULL: 100,
        }
        return percentages[self]
