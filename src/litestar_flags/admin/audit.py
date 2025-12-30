"""Audit logging for admin operations.

This module provides comprehensive audit logging functionality for tracking
all administrative actions performed on feature flags, rules, overrides,
segments, and environments.

Example:
    >>> from litestar_flags.admin.audit import (
    ...     AuditAction,
    ...     InMemoryAuditLogger,
    ...     ResourceType,
    ...     create_audit_entry,
    ... )
    >>> logger = InMemoryAuditLogger()
    >>> entry = create_audit_entry(
    ...     action=AuditAction.CREATE,
    ...     resource_type=ResourceType.FLAG,
    ...     resource_id="550e8400-e29b-41d4-a716-446655440000",
    ...     resource_key="new_feature",
    ...     actor_id="user-123",
    ... )
    >>> await logger.log(entry)

"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "AuditAction",
    "AuditEntry",
    "AuditLogger",
    "InMemoryAuditLogger",
    "ResourceType",
    "audit_admin_action",
    "create_audit_entry",
    "diff_changes",
]


class AuditAction(StrEnum):
    """Actions that can be performed on resources.

    Represents the types of administrative operations that are tracked
    in the audit log.

    Attributes:
        CREATE: Resource creation.
        UPDATE: Resource modification.
        DELETE: Resource deletion.
        READ: Resource access (for sensitive operations).
        ENABLE: Enabling a flag or resource.
        DISABLE: Disabling a flag or resource.
        PROMOTE: Promoting a flag to a new environment.
        ARCHIVE: Archiving a resource.

    """

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    READ = "read"
    ENABLE = "enable"
    DISABLE = "disable"
    PROMOTE = "promote"
    ARCHIVE = "archive"


class ResourceType(StrEnum):
    """Types of resources that can be audited.

    Represents the different entity types that are tracked in the
    audit log for administrative operations.

    Attributes:
        FLAG: Feature flag.
        RULE: Targeting rule.
        OVERRIDE: Entity-specific override.
        SEGMENT: User segment.
        ENVIRONMENT: Deployment environment.
        ENVIRONMENT_FLAG: Environment-specific flag configuration.

    """

    FLAG = "flag"
    RULE = "rule"
    OVERRIDE = "override"
    SEGMENT = "segment"
    ENVIRONMENT = "environment"
    ENVIRONMENT_FLAG = "environment_flag"


@dataclass(slots=True, frozen=True)
class AuditEntry:
    """Immutable record of an administrative action.

    Captures comprehensive information about who performed what action
    on which resource, including the changes made and relevant context.

    Attributes:
        id: Unique identifier for this audit entry.
        timestamp: When the action occurred (UTC).
        action: The type of action performed.
        resource_type: The type of resource affected.
        resource_id: The unique identifier of the affected resource.
        resource_key: Optional human-readable key (e.g., flag key, segment name).
        actor_id: Identifier of who performed the action.
        actor_type: Type of actor (user, system, api_key, etc.).
        ip_address: IP address of the actor if available.
        user_agent: User agent string if available.
        changes: Before/after values for update operations.
        metadata: Additional context about the action.

    Example:
        >>> entry = AuditEntry(
        ...     id=uuid4(),
        ...     timestamp=datetime.now(UTC),
        ...     action=AuditAction.UPDATE,
        ...     resource_type=ResourceType.FLAG,
        ...     resource_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        ...     resource_key="checkout_v2",
        ...     actor_id="user-456",
        ...     actor_type="user",
        ...     changes={"before": {"enabled": False}, "after": {"enabled": True}},
        ...     metadata={"reason": "Rolling out to beta"},
        ... )

    """

    id: UUID
    timestamp: datetime
    action: AuditAction
    resource_type: ResourceType
    resource_id: UUID | str
    resource_key: str | None = None
    actor_id: str | None = None
    actor_type: str = "system"
    ip_address: str | None = None
    user_agent: str | None = None
    changes: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary representation suitable for serialization.

        """
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat(),
            "action": self.action.value,
            "resource_type": self.resource_type.value,
            "resource_id": str(self.resource_id),
            "resource_key": self.resource_key,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "changes": self.changes,
            "metadata": self.metadata,
        }


@runtime_checkable
class AuditLogger(Protocol):
    """Protocol for audit logging implementations.

    All audit logger implementations must implement this protocol.
    Methods are async to support both sync and async backends.

    Implementations:
        - InMemoryAuditLogger: In-memory storage for development/testing.
        - (Future) DatabaseAuditLogger: Persistent database storage.
        - (Future) ExternalAuditLogger: External service integration.

    Example:
        >>> class MyAuditLogger:
        ...     async def log(self, entry: AuditEntry) -> None:
        ...         # Store the audit entry
        ...         pass
        ...
        ...     async def get_entries(
        ...         self,
        ...         resource_type: ResourceType | None = None,
        ...         resource_id: UUID | str | None = None,
        ...         limit: int = 100,
        ...         offset: int = 0,
        ...     ) -> list[AuditEntry]:
        ...         # Query audit entries
        ...         return []
        >>> isinstance(MyAuditLogger(), AuditLogger)
        True

    """

    async def log(self, entry: AuditEntry) -> None:
        """Log an audit entry.

        Args:
            entry: The audit entry to log.

        """
        ...

    async def get_entries(
        self,
        resource_type: ResourceType | None = None,
        resource_id: UUID | str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Query audit entries with optional filtering.

        Args:
            resource_type: Filter by resource type.
            resource_id: Filter by specific resource ID.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip (for pagination).

        Returns:
            List of matching audit entries.

        """
        ...


class InMemoryAuditLogger:
    """In-memory audit logger for development and testing.

    Thread-safe implementation that stores audit entries in memory with
    a configurable maximum size. When the maximum size is reached, the
    oldest entries are automatically removed.

    Attributes:
        max_entries: Maximum number of entries to retain.

    Example:
        >>> logger = InMemoryAuditLogger(max_entries=1000)
        >>> entry = create_audit_entry(
        ...     action=AuditAction.CREATE,
        ...     resource_type=ResourceType.FLAG,
        ...     resource_id=uuid4(),
        ...     resource_key="my_flag",
        ... )
        >>> await logger.log(entry)
        >>> entries = await logger.get_entries(resource_type=ResourceType.FLAG)

    """

    __slots__ = ("_entries", "_lock", "_max_entries")

    def __init__(self, max_entries: int = 10000) -> None:
        """Initialize the in-memory audit logger.

        Args:
            max_entries: Maximum number of entries to retain. Defaults to 10000.

        """
        self._entries: list[AuditEntry] = []
        self._max_entries = max_entries
        self._lock = asyncio.Lock()

    @property
    def max_entries(self) -> int:
        """Maximum number of entries to retain."""
        return self._max_entries

    async def log(self, entry: AuditEntry) -> None:
        """Log an audit entry.

        Thread-safe operation that adds the entry and trims old entries
        if the maximum size is exceeded.

        Args:
            entry: The audit entry to log.

        """
        async with self._lock:
            self._entries.append(entry)
            # Trim oldest entries if we exceed max
            if len(self._entries) > self._max_entries:
                excess = len(self._entries) - self._max_entries
                self._entries = self._entries[excess:]

    async def get_entries(
        self,
        resource_type: ResourceType | None = None,
        resource_id: UUID | str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Query audit entries with optional filtering.

        Returns entries in reverse chronological order (newest first).

        Args:
            resource_type: Filter by resource type.
            resource_id: Filter by specific resource ID.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip (for pagination).

        Returns:
            List of matching audit entries.

        """
        async with self._lock:
            # Filter entries
            filtered = self._entries

            if resource_type is not None:
                filtered = [e for e in filtered if e.resource_type == resource_type]

            if resource_id is not None:
                # Convert to string for comparison
                resource_id_str = str(resource_id)
                filtered = [e for e in filtered if str(e.resource_id) == resource_id_str]

            # Sort by timestamp descending (newest first)
            sorted_entries = sorted(filtered, key=lambda e: e.timestamp, reverse=True)

            # Apply pagination
            return sorted_entries[offset : offset + limit]

    async def get_entries_by_actor(
        self,
        actor_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Query audit entries by actor.

        Args:
            actor_id: The actor identifier to filter by.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip (for pagination).

        Returns:
            List of matching audit entries.

        """
        async with self._lock:
            filtered = [e for e in self._entries if e.actor_id == actor_id]
            sorted_entries = sorted(filtered, key=lambda e: e.timestamp, reverse=True)
            return sorted_entries[offset : offset + limit]

    async def get_entries_by_action(
        self,
        action: AuditAction,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Query audit entries by action type.

        Args:
            action: The action type to filter by.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip (for pagination).

        Returns:
            List of matching audit entries.

        """
        async with self._lock:
            filtered = [e for e in self._entries if e.action == action]
            sorted_entries = sorted(filtered, key=lambda e: e.timestamp, reverse=True)
            return sorted_entries[offset : offset + limit]

    async def get_entries_in_timerange(
        self,
        start: datetime,
        end: datetime,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Query audit entries within a time range.

        Args:
            start: Start of the time range (inclusive).
            end: End of the time range (inclusive).
            limit: Maximum number of entries to return.
            offset: Number of entries to skip (for pagination).

        Returns:
            List of matching audit entries.

        """
        async with self._lock:
            filtered = [e for e in self._entries if start <= e.timestamp <= end]
            sorted_entries = sorted(filtered, key=lambda e: e.timestamp, reverse=True)
            return sorted_entries[offset : offset + limit]

    async def count_entries(
        self,
        resource_type: ResourceType | None = None,
        resource_id: UUID | str | None = None,
    ) -> int:
        """Count audit entries with optional filtering.

        Args:
            resource_type: Filter by resource type.
            resource_id: Filter by specific resource ID.

        Returns:
            Number of matching entries.

        """
        async with self._lock:
            filtered = self._entries

            if resource_type is not None:
                filtered = [e for e in filtered if e.resource_type == resource_type]

            if resource_id is not None:
                resource_id_str = str(resource_id)
                filtered = [e for e in filtered if str(e.resource_id) == resource_id_str]

            return len(filtered)

    async def clear(self) -> None:
        """Clear all audit entries.

        Primarily useful for testing.
        """
        async with self._lock:
            self._entries.clear()


def create_audit_entry(
    action: AuditAction,
    resource_type: ResourceType,
    resource_id: UUID | str,
    *,
    resource_key: str | None = None,
    actor_id: str | None = None,
    actor_type: str = "system",
    ip_address: str | None = None,
    user_agent: str | None = None,
    changes: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEntry:
    """Create an audit entry with generated ID and timestamp.

    Factory function that creates an AuditEntry with a generated UUID
    and current timestamp.

    Args:
        action: The action being performed.
        resource_type: The type of resource being acted upon.
        resource_id: The unique identifier of the resource.
        resource_key: Optional human-readable key for the resource.
        actor_id: Identifier of who performed the action.
        actor_type: Type of actor (user, system, api_key, etc.).
        ip_address: IP address of the actor.
        user_agent: User agent string of the actor.
        changes: Before/after values for update operations.
        metadata: Additional context about the action.

    Returns:
        A new AuditEntry instance.

    Example:
        >>> entry = create_audit_entry(
        ...     action=AuditAction.UPDATE,
        ...     resource_type=ResourceType.FLAG,
        ...     resource_id=uuid4(),
        ...     resource_key="dark_mode",
        ...     actor_id="user-123",
        ...     actor_type="user",
        ...     changes={"before": {"enabled": False}, "after": {"enabled": True}},
        ... )

    """
    return AuditEntry(
        id=uuid4(),
        timestamp=datetime.now(UTC),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_key=resource_key,
        actor_id=actor_id,
        actor_type=actor_type,
        ip_address=ip_address,
        user_agent=user_agent,
        changes=changes,
        metadata=metadata or {},
    )


async def audit_admin_action(
    logger: AuditLogger,
    action: AuditAction,
    resource_type: ResourceType,
    resource_id: UUID | str,
    *,
    resource_key: str | None = None,
    actor_id: str | None = None,
    actor_type: str = "system",
    ip_address: str | None = None,
    user_agent: str | None = None,
    changes: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEntry:
    """Create and log an audit entry in a single call.

    Combines create_audit_entry and logger.log into one operation.

    Args:
        logger: The audit logger to use.
        action: The action being performed.
        resource_type: The type of resource being acted upon.
        resource_id: The unique identifier of the resource.
        resource_key: Optional human-readable key for the resource.
        actor_id: Identifier of who performed the action.
        actor_type: Type of actor (user, system, api_key, etc.).
        ip_address: IP address of the actor.
        user_agent: User agent string of the actor.
        changes: Before/after values for update operations.
        metadata: Additional context about the action.

    Returns:
        The logged AuditEntry instance.

    Example:
        >>> logger = InMemoryAuditLogger()
        >>> entry = await audit_admin_action(
        ...     logger,
        ...     AuditAction.DELETE,
        ...     ResourceType.FLAG,
        ...     uuid4(),
        ...     resource_key="old_feature",
        ...     actor_id="admin-1",
        ...     actor_type="user",
        ... )

    """
    entry = create_audit_entry(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_key=resource_key,
        actor_id=actor_id,
        actor_type=actor_type,
        ip_address=ip_address,
        user_agent=user_agent,
        changes=changes,
        metadata=metadata,
    )
    await logger.log(entry)
    return entry


def diff_changes(
    before: dict[str, Any] | object | None,
    after: dict[str, Any] | object | None,
    *,
    include_unchanged: bool = False,
    excluded_keys: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Compute the differences between two states.

    Compares two dictionaries (or objects with __dict__) and returns
    a structured representation of what changed.

    Args:
        before: The state before the change.
        after: The state after the change.
        include_unchanged: Whether to include unchanged fields.
        excluded_keys: Keys to exclude from the diff.

    Returns:
        Dictionary with 'before', 'after', and 'changed_fields' keys.

    Example:
        >>> before = {"enabled": False, "name": "My Flag", "version": 1}
        >>> after = {"enabled": True, "name": "My Flag", "version": 2}
        >>> diff = diff_changes(before, after)
        >>> diff["changed_fields"]
        ['enabled', 'version']
        >>> diff["before"]
        {'enabled': False, 'version': 1}
        >>> diff["after"]
        {'enabled': True, 'version': 2}

    """
    excluded = set(excluded_keys or [])

    # Convert objects to dicts if needed
    def to_dict(obj: Any) -> dict[str, Any]:
        if obj is None:
            return {}
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "__dict__"):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        return {}

    before_dict = to_dict(before)
    after_dict = to_dict(after)

    # Find all keys
    all_keys = set(before_dict.keys()) | set(after_dict.keys())
    all_keys -= excluded

    changed_fields: list[str] = []
    before_values: dict[str, Any] = {}
    after_values: dict[str, Any] = {}

    for key in sorted(all_keys):
        before_val = before_dict.get(key)
        after_val = after_dict.get(key)

        if before_val != after_val:
            changed_fields.append(key)
            before_values[key] = before_val
            after_values[key] = after_val
        elif include_unchanged:
            before_values[key] = before_val
            after_values[key] = after_val

    return {
        "before": before_values,
        "after": after_values,
        "changed_fields": changed_fields,
    }
