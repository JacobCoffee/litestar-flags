"""Base model configuration for feature flags."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from advanced_alchemy.base import UUIDv7AuditBase

    HAS_ADVANCED_ALCHEMY = True
except ImportError:
    HAS_ADVANCED_ALCHEMY = False
    UUIDv7AuditBase = None  # type: ignore[misc, assignment]

if TYPE_CHECKING:
    pass

__all__ = ["HAS_ADVANCED_ALCHEMY", "UUIDv7AuditBase"]
