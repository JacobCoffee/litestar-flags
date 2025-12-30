"""Database analytics collector using SQLAlchemy async sessions."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from litestar_flags.models.base import HAS_ADVANCED_ALCHEMY

if not HAS_ADVANCED_ALCHEMY:
    raise ImportError(
        "Database analytics collector requires 'advanced-alchemy'. Install with: pip install litestar-flags[database]"
    )

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from litestar_flags.analytics.models import AnalyticsEventModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from litestar_flags.analytics.models import FlagEvaluationEvent

__all__ = ["DatabaseAnalyticsCollector"]

logger = logging.getLogger(__name__)


class DatabaseAnalyticsCollector:
    """Database analytics collector with batch writes.

    Buffers evaluation events in memory and periodically flushes them to
    the database in batches for optimal write performance. Uses SQLAlchemy
    async sessions for non-blocking database operations.

    Features:
        - Configurable batch size and flush interval
        - Background task for periodic flushing
        - Thread-safe event buffering with asyncio.Lock
        - Automatic flush on close for data integrity
        - Proper cleanup of database connections

    Attributes:
        batch_size: Maximum events to buffer before auto-flush.
        flush_interval_seconds: Time between automatic flushes.

    Example:
        >>> collector = await DatabaseAnalyticsCollector.create(
        ...     connection_string="postgresql+asyncpg://user:pass@localhost/db",
        ...     batch_size=100,
        ...     flush_interval_seconds=5.0,
        ... )
        >>> try:
        ...     await collector.record(event)
        ... finally:
        ...     await collector.close()

    """

    def __init__(
        self,
        engine: AsyncEngine,
        session_maker: async_sessionmaker[AsyncSession],
        batch_size: int = 100,
        flush_interval_seconds: float = 5.0,
    ) -> None:
        """Initialize the database analytics collector.

        Args:
            engine: The SQLAlchemy async engine.
            session_maker: The session maker factory.
            batch_size: Maximum events to buffer before auto-flush. Defaults to 100.
            flush_interval_seconds: Seconds between automatic flushes. Defaults to 5.0.

        """
        self._engine = engine
        self._session_maker = session_maker
        self._batch_size = batch_size
        self._flush_interval_seconds = flush_interval_seconds
        self._buffer: list[FlagEvaluationEvent] = []
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._closed = False

    @classmethod
    async def create(
        cls,
        connection_string: str,
        batch_size: int = 100,
        flush_interval_seconds: float = 5.0,
        create_tables: bool = True,
        **engine_kwargs: Any,
    ) -> DatabaseAnalyticsCollector:
        """Create a new database analytics collector.

        Factory method that sets up the database connection and optionally
        creates the analytics_events table.

        Args:
            connection_string: Database connection string (SQLAlchemy format).
            batch_size: Maximum events to buffer before auto-flush. Defaults to 100.
            flush_interval_seconds: Seconds between automatic flushes. Defaults to 5.0.
            create_tables: Whether to create tables on startup. Defaults to True.
            **engine_kwargs: Additional arguments for create_async_engine.

        Returns:
            Configured DatabaseAnalyticsCollector instance with background flush task running.

        Example:
            >>> collector = await DatabaseAnalyticsCollector.create(
            ...     connection_string="sqlite+aiosqlite:///analytics.db",
            ...     batch_size=50,
            ...     flush_interval_seconds=10.0,
            ... )

        """
        engine = create_async_engine(
            connection_string,
            echo=engine_kwargs.pop("echo", False),
            **engine_kwargs,
        )

        if create_tables:
            async with engine.begin() as conn:
                from advanced_alchemy.base import orm_registry

                # Import to register the model
                from litestar_flags.analytics.models import AnalyticsEventModel

                _ = AnalyticsEventModel  # Ensure model is registered
                await conn.run_sync(orm_registry.metadata.create_all)

        session_maker = async_sessionmaker(engine, expire_on_commit=False)

        collector = cls(
            engine=engine,
            session_maker=session_maker,
            batch_size=batch_size,
            flush_interval_seconds=flush_interval_seconds,
        )

        # Start the background flush task
        collector._start_flush_task()

        return collector

    @property
    def batch_size(self) -> int:
        """Return the configured batch size.

        Returns:
            The maximum number of events to buffer before auto-flush.

        """
        return self._batch_size

    @property
    def flush_interval_seconds(self) -> float:
        """Return the configured flush interval.

        Returns:
            The time in seconds between automatic flushes.

        """
        return self._flush_interval_seconds

    def _start_flush_task(self) -> None:
        """Start the background flush task."""
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._periodic_flush())

    async def _periodic_flush(self) -> None:
        """Periodically flush buffered events to the database.

        Runs in a background task and flushes events at the configured interval.
        Continues running until the collector is closed.

        """
        while not self._closed:
            try:
                await asyncio.sleep(self._flush_interval_seconds)
                if not self._closed:
                    await self.flush()
            except asyncio.CancelledError:
                # Task was cancelled, exit gracefully
                break
            except Exception:
                logger.exception("Error during periodic flush")

    async def record(self, event: FlagEvaluationEvent) -> None:
        """Record a flag evaluation event.

        Buffers the event in memory. If the buffer reaches batch_size,
        automatically triggers a flush to the database.

        Thread-safe method using asyncio.Lock.

        Args:
            event: The evaluation event to record.

        Raises:
            RuntimeError: If the collector has been closed.

        """
        if self._closed:
            raise RuntimeError("Cannot record to a closed collector")

        async with self._lock:
            self._buffer.append(event)
            should_flush = len(self._buffer) >= self._batch_size

        if should_flush:
            await self.flush()

    async def flush(self) -> None:
        """Flush buffered events to the database.

        Writes all buffered events to the database in a single transaction.
        This method is thread-safe and can be called concurrently with record().

        If there are no buffered events, this is a no-op.

        """
        async with self._lock:
            if not self._buffer:
                return
            events_to_flush = self._buffer.copy()
            self._buffer.clear()

        if not events_to_flush:
            return

        try:
            async with self._session_maker() as session:
                models = [self._event_to_model(event) for event in events_to_flush]
                session.add_all(models)
                await session.commit()
                logger.debug("Flushed %d analytics events to database", len(models))
        except Exception:
            # On failure, re-add events to buffer for retry
            async with self._lock:
                self._buffer = events_to_flush + self._buffer
            logger.exception("Failed to flush analytics events to database")
            raise

    def _event_to_model(self, event: FlagEvaluationEvent) -> AnalyticsEventModel:
        """Convert a FlagEvaluationEvent to an AnalyticsEventModel.

        Args:
            event: The evaluation event to convert.

        Returns:
            SQLAlchemy model ready for database insertion.

        """
        # Convert the value to a JSON-serializable format
        value: dict[str, Any] | None = None
        if event.value is not None:
            if isinstance(event.value, dict):
                value = event.value
            else:
                value = {"value": event.value}

        return AnalyticsEventModel(
            timestamp=event.timestamp,
            flag_key=event.flag_key,
            value=value,
            reason=event.reason.value if hasattr(event.reason, "value") else str(event.reason),
            variant=event.variant,
            targeting_key=event.targeting_key,
            context_attributes=event.context_attributes,
            evaluation_duration_ms=event.evaluation_duration_ms,
        )

    async def close(self) -> None:
        """Close the collector and release resources.

        Flushes any remaining buffered events, cancels the background
        flush task, and disposes of the database engine connection pool.

        This method is idempotent - calling it multiple times is safe.

        """
        if self._closed:
            return

        self._closed = True

        # Cancel the periodic flush task
        if self._flush_task is not None and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Flush any remaining events
        try:
            # Temporarily unset closed flag to allow flush
            self._closed = False
            async with self._lock:
                if self._buffer:
                    events_to_flush = self._buffer.copy()
                    self._buffer.clear()
                else:
                    events_to_flush = []

            if events_to_flush:
                async with self._session_maker() as session:
                    models = [self._event_to_model(event) for event in events_to_flush]
                    session.add_all(models)
                    await session.commit()
                    logger.debug("Flushed %d remaining analytics events on close", len(models))
        except Exception:
            logger.exception("Failed to flush remaining events on close")
        finally:
            self._closed = True

        # Dispose of the engine
        await self._engine.dispose()
        logger.debug("Database analytics collector closed")

    async def get_buffer_size(self) -> int:
        """Get the current number of buffered events.

        Returns:
            The number of events currently in the buffer.

        """
        async with self._lock:
            return len(self._buffer)

    async def health_check(self) -> bool:
        """Check if the database connection is healthy.

        Executes a simple query to verify connectivity.

        Returns:
            True if the database is reachable, False otherwise.

        """
        try:
            from sqlalchemy import select

            async with self._session_maker() as session:
                await session.execute(select(1))
            return True
        except Exception:
            return False
