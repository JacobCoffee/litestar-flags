"""Background processor for scheduled flag changes."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from litestar_flags.types import ChangeType, FlagStatus

if TYPE_CHECKING:
    from litestar_flags.models.schedule import ScheduledFlagChange
    from litestar_flags.protocols import StorageBackend

__all__ = ["ScheduleProcessor"]

logger = logging.getLogger(__name__)


class ScheduleProcessor:
    """Background processor for scheduled flag changes.

    Processes pending scheduled changes that are due for execution,
    applying the specified changes to feature flags.

    This processor should be run periodically (e.g., via a cron job,
    background task, or async scheduler) to process due changes.

    Attributes:
        storage: The storage backend for flag operations.

    Example:
        >>> storage = MemoryStorageBackend()
        >>> processor = ScheduleProcessor(storage)
        >>>
        >>> # Process all pending changes
        >>> executed = await processor.process_pending_changes()
        >>> for change in executed:
        ...     print(f"Executed: {change.change_type} for {change.flag_key}")

    """

    def __init__(self, storage: StorageBackend) -> None:
        """Initialize the schedule processor.

        Args:
            storage: The storage backend for flag operations.

        """
        self.storage = storage

    async def process_pending_changes(
        self,
        now: datetime | None = None,
    ) -> list[ScheduledFlagChange]:
        """Process all pending scheduled changes that are due.

        Retrieves all scheduled changes that have passed their scheduled
        time and executes them in order.

        Args:
            now: Current time for determining due changes. Defaults to UTC now.

        Returns:
            List of successfully executed changes.

        """
        if now is None:
            now = datetime.now(UTC)

        executed_changes: list[ScheduledFlagChange] = []

        # Get pending changes from storage
        pending_changes = await self._get_pending_changes(now)

        for change in pending_changes:
            try:
                success = await self.execute_change(change, now)
                if success:
                    executed_changes.append(change)
            except Exception as e:
                logger.exception(
                    "Failed to execute scheduled change %s for flag %s: %s",
                    change.id,
                    getattr(change, "flag_id", "unknown"),
                    e,
                )
                # Mark as failed
                await self._mark_change_failed(change, str(e))

        return executed_changes

    async def execute_change(
        self,
        change: ScheduledFlagChange,
        now: datetime | None = None,
    ) -> bool:
        """Execute a single scheduled change.

        Applies the specified change to the target flag and marks the
        change as executed.

        Args:
            change: The scheduled change to execute.
            now: Current time for the executed_at timestamp.

        Returns:
            True if the change was successfully executed.

        """
        if now is None:
            now = datetime.now(UTC)

        # Check if already executed
        if hasattr(change, "executed_at") and change.executed_at is not None:
            logger.debug(
                "Change %s already executed at %s",
                change.id,
                change.executed_at,
            )
            return False

        # Check if due
        if hasattr(change, "is_due") and not change.is_due:
            logger.debug("Change %s is not yet due", change.id)
            return False
        elif change.scheduled_at > now:
            logger.debug("Change %s is not yet due", change.id)
            return False

        # Get the flag
        flag = await self._get_flag_for_change(change)
        if flag is None:
            logger.warning(
                "Flag not found for scheduled change %s",
                change.id,
            )
            await self._mark_change_failed(change, "Flag not found")
            return False

        # Apply the change
        try:
            success = await self._apply_change(flag, change)
            if success:
                await self._mark_change_executed(change, now)
                logger.info(
                    "Executed scheduled change %s (%s) for flag %s",
                    change.id,
                    change.change_type.value,
                    flag.key,
                )
            return success
        except Exception as e:
            logger.exception(
                "Error applying change %s to flag %s: %s",
                change.id,
                flag.key,
                e,
            )
            await self._mark_change_failed(change, str(e))
            return False

    async def _get_pending_changes(
        self,
        now: datetime,
    ) -> list[ScheduledFlagChange]:
        """Get all pending scheduled changes that are due.

        This method should be overridden or the storage backend should
        provide a method to query pending changes.

        Args:
            now: Current time for determining due changes.

        Returns:
            List of pending changes that are due for execution.

        """
        # Try to get pending changes from storage if method exists
        if hasattr(self.storage, "get_pending_scheduled_changes"):
            return await self.storage.get_pending_scheduled_changes(now)

        # Fallback: return empty list if storage doesn't support this
        logger.warning("Storage backend does not support get_pending_scheduled_changes")
        return []

    async def _get_flag_for_change(
        self,
        change: ScheduledFlagChange,
    ) -> Any:
        """Get the flag associated with a scheduled change.

        Args:
            change: The scheduled change.

        Returns:
            The FeatureFlag or None if not found.

        """
        # Try to get flag by ID if we have a relationship
        if hasattr(change, "flag") and change.flag is not None:
            return change.flag

        # Try to get by flag_id
        if hasattr(change, "flag_id") and hasattr(self.storage, "get_flag_by_id"):
            return await self.storage.get_flag_by_id(change.flag_id)

        return None

    async def _apply_change(
        self,
        flag: Any,
        change: ScheduledFlagChange,
    ) -> bool:
        """Apply a scheduled change to a flag.

        Args:
            flag: The flag to modify.
            change: The change to apply.

        Returns:
            True if the change was successfully applied.

        """
        match change.change_type:
            case ChangeType.ENABLE:
                flag.status = FlagStatus.ACTIVE
                flag.default_enabled = True
                await self.storage.update_flag(flag)
                return True

            case ChangeType.DISABLE:
                flag.status = FlagStatus.INACTIVE
                flag.default_enabled = False
                await self.storage.update_flag(flag)
                return True

            case ChangeType.UPDATE_VALUE:
                if hasattr(change, "change_value") and change.change_value is not None:
                    flag.default_value = change.change_value
                elif hasattr(change, "new_value") and change.new_value is not None:
                    flag.default_value = change.new_value
                await self.storage.update_flag(flag)
                return True

            case ChangeType.UPDATE_ROLLOUT:
                percentage = None
                if hasattr(change, "rollout_percentage"):
                    percentage = change.rollout_percentage
                elif hasattr(change, "new_rollout_percentage"):
                    percentage = change.new_rollout_percentage

                if percentage is not None:
                    # Update rollout percentage on all rules
                    for rule in flag.rules:
                        rule.rollout_percentage = percentage
                    await self.storage.update_flag(flag)
                return True

            case _:
                logger.warning(
                    "Unknown change type: %s",
                    change.change_type,
                )
                return False

    async def _mark_change_executed(
        self,
        change: ScheduledFlagChange,
        executed_at: datetime,
    ) -> None:
        """Mark a scheduled change as executed.

        Args:
            change: The change to mark as executed.
            executed_at: The execution timestamp.

        """
        change.executed_at = executed_at
        if hasattr(change, "executed"):
            change.executed = True

        # Update in storage if method exists
        if hasattr(self.storage, "update_scheduled_change"):
            await self.storage.update_scheduled_change(change)

    async def _mark_change_failed(
        self,
        change: ScheduledFlagChange,
        error: str,
    ) -> None:
        """Mark a scheduled change as failed.

        Args:
            change: The change to mark as failed.
            error: The error message.

        """
        if hasattr(change, "error"):
            change.error = error

        # Update in storage if method exists
        if hasattr(self.storage, "update_scheduled_change"):
            await self.storage.update_scheduled_change(change)


class ScheduleProcessorTask:
    """Async task runner for the schedule processor.

    Provides a convenient way to run the schedule processor as a
    background task with configurable intervals.

    Example:
        >>> storage = MemoryStorageBackend()
        >>> task = ScheduleProcessorTask(storage, interval_seconds=60)
        >>> await task.start()
        >>> # ... application runs ...
        >>> await task.stop()

    """

    def __init__(
        self,
        storage: StorageBackend,
        interval_seconds: int = 60,
    ) -> None:
        """Initialize the schedule processor task.

        Args:
            storage: The storage backend.
            interval_seconds: How often to check for pending changes.

        """
        self.processor = ScheduleProcessor(storage)
        self.interval_seconds = interval_seconds
        self._running = False
        self._task: Any = None

    async def start(self) -> None:
        """Start the background processing task."""
        import asyncio

        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Schedule processor started with %d second interval",
            self.interval_seconds,
        )

    async def stop(self) -> None:
        """Stop the background processing task."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.debug("Schedule processor task cancelled")
            self._task = None
        logger.info("Schedule processor stopped")

    async def _run_loop(self) -> None:
        """Run the main processing loop."""
        while self._running:
            try:
                executed = await self.processor.process_pending_changes()
                if executed:
                    logger.info(
                        "Processed %d scheduled changes",
                        len(executed),
                    )
            except Exception as e:
                logger.exception("Error in schedule processor loop: %s", e)

            await asyncio.sleep(self.interval_seconds)

    @property
    def is_running(self) -> bool:
        """Check if the processor is currently running."""
        return self._running
